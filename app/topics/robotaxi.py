"""Autonomous car adoption (/robotaxi). Mostly hand-entered: operators announce numbers, they do not publish feeds.

rides      paid driverless rides per week by operator (announcements, hand-entered: data/robotaxi/rides.csv) and quarterly ride
           counts where that is what the operator reports (Baidu Apollo Go)
footprint  where each operator offers public driverless rides and since when (data/robotaxi/cities.csv)
safety     crash reports filed by automated-driving-system operators under NHTSA's Standing General Order (CSV, monthly, automated),
           counted per month and per reporting entity; incidents are not normalised by miles (operators report miles irregularly)

Each hand-entered row carries the source it came from. NHTSA data is cached a day and snapshotted.
"""
from __future__ import annotations

from io import StringIO

import pandas as pd

from ._base import DAY, _pts, _r, fetch, manual, manual_rows, manual_sources, payload

SGO = "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/SGO-2021-01_Incident_Reports_ADS.csv"
SLUG = "robotaxi"
SOURCES = [{"name": "Operator announcements and press reports (hand-entered, cited per point)", "url": "", "cadence": "as announced"},
           {"name": "NHTSA Standing General Order crash reports, ADS", "url": "https://www.nhtsa.gov/laws-regulations/standing-general-order-crash-reporting", "cadence": "monthly"}]
NOTES = "Rides are operator-reported paid, fully driverless trips. Crash reports are all incidents an operator had to report under the Standing General Order (including minor ones and those caused by other road users); more rides mean more reports, so read them with the ride counts."
TTL = DAY


# ------------------------------------------------------------------ NHTSA SGO
def parse_sgo(text: str) -> pd.DataFrame:
    d = pd.read_csv(StringIO(text), dtype=str, on_bad_lines="skip")
    cols = {c.lower().strip(): c for c in d.columns}
    ent = next((cols[c] for c in cols if "reporting entity" in c), None)
    date = next((cols[c] for c in cols if c.startswith("incident date")), None)
    if ent is None or date is None:
        raise ValueError("SGO layout changed")
    raw = d[date].astype(str).str.strip()
    when = pd.to_datetime(raw, format="%b-%Y", errors="coerce")
    when = when.fillna(pd.to_datetime(raw, errors="coerce"))
    out = pd.DataFrame({"entity": d[ent].astype(str).str.strip(), "month": when.dt.to_period("M").dt.to_timestamp()})
    rid = next((cols[c] for c in cols if c.startswith("report id")), None)
    if rid:                                                  # several versions of one report are filed; count each incident once
        out["rid"] = d[rid]
        out = out.drop_duplicates("rid")
    return out.dropna(subset=["month"])


def sgo() -> pd.DataFrame:
    return parse_sgo(fetch(SGO, TTL, min_bytes=1000))


# ------------------------------------------------------------------ endpoints
def _rides_now() -> dict:
    weekly = manual(SLUG, "rides")
    quarterly = manual(SLUG, "rides_quarterly")
    out = payload({"weekly": lambda: {k: _pts(v, 0) for k, v in weekly.items()} if isinstance(weekly, dict) else {},
                   "quarterly": lambda: {k: _pts(v, 0) for k, v in quarterly.items()} if isinstance(quarterly, dict) else {},
                   "rows": lambda: sorted(manual_rows(SLUG, "rides") + manual_rows(SLUG, "rides_quarterly"), key=lambda r: r["date"], reverse=True)[:40]})
    latest = {k: {"value": _r(v.iloc[-1], 0), "date": str(v.index[-1].date())} for k, v in (weekly.items() if isinstance(weekly, dict) else []) if len(v)}
    out["latest"] = latest
    out["as_of"] = max((x["date"] for x in latest.values()), default=None)
    out["cited"] = manual_sources(SLUG, "rides")[:5]
    return out


def _footprint_now() -> dict:
    rows = sorted(manual_rows(SLUG, "cities"), key=lambda r: r["date"])
    ops = sorted({r["operator"] for r in rows})

    def cumulative():
        out = {}
        for op in ops:
            n, pts = 0, []
            for r in rows:
                if r["operator"] == op:
                    n += 1
                    pts.append([int(pd.Timestamp(r["date"]).timestamp()), n])
            out[op] = pts
        return out
    out = payload({"rows": lambda: rows[::-1], "cumulative": cumulative, "operators": lambda: ops,
                   "by_operator": lambda: {op: sum(r["operator"] == op for r in rows) for op in ops}})
    out["as_of"] = rows[-1]["date"] if rows else None
    return out


def _safety_now() -> dict:
    def counts():
        d = sgo()
        d = d[d["month"] >= "2021-07-01"]
        top = d["entity"].value_counts().head(6).index.tolist()
        by = d.assign(entity=d["entity"].where(d["entity"].isin(top), "Others")).groupby(["month", "entity"]).size().unstack(fill_value=0)
        by = by.reindex(pd.date_range(by.index.min(), by.index.max(), freq="MS"), fill_value=0)
        return {"months": [int(t.timestamp()) for t in by.index], "entities": {e: [int(x) for x in by[e]] for e in by.columns},
                "total": _pts(by.sum(axis=1), 0), "total_12m": _pts(by.sum(axis=1).rolling(12).sum(), 0),
                "latest_month": str(by.index[-1].date()), "n": int(len(d))}
    out = payload({"reports": counts}, sources=[SGO])
    out["as_of"] = (out.get("reports") or {}).get("latest_month")
    return out


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"rides": _cached_ep("rides", _rides_now, 600), "footprint": _cached_ep("footprint", _footprint_now, 600), "safety": _cached_ep("safety", _safety_now)}
