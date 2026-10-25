"""Autonomous car adoption (/robotaxi). Mostly hand-entered: operators announce numbers, they do not publish feeds.

rides      paid driverless rides per week by operator (announcements, hand-entered: data/robotaxi/rides.csv) and quarterly ride
           counts where that is what the operator reports (Baidu Apollo Go)
footprint  where each operator offers public driverless rides and since when (data/robotaxi/cities.csv)
safety     crash reports filed by automated-driving-system operators under NHTSA's Standing General Order (CSV, monthly, automated),
           counted per month and per reporting entity (current file plus the pre-June-2025 archive), and per million driverless miles for
           operators that publish miles (data/robotaxi/miles.csv)

Each hand-entered row carries the source it came from. NHTSA data is cached a day and snapshotted.
"""
from __future__ import annotations

from io import StringIO

import pandas as pd

from ._base import DAY, _pts, _r, fetch, fetch_json, manual, manual_rows, manual_sources, payload

SGO = "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/SGO-2021-01_Incident_Reports_ADS.csv"
SGO_ARCHIVE = "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/Archive-2021-2025/SGO-2021-01_Incident_Reports_ADS.csv"   # Jul 2021 to Jun 2025
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


def sgo_parts() -> tuple[pd.DataFrame, bool]:
    """Current file plus the archive (reports filed before the June 2025 amendment moved to their own file); False when the archive is missing."""
    d, archived = parse_sgo(fetch(SGO, TTL, min_bytes=1000)), True
    try:
        d = pd.concat([d, parse_sgo(fetch(SGO_ARCHIVE, 30 * TTL, min_bytes=1000))])
    except Exception:
        archived = False
    return (d.drop_duplicates("rid") if "rid" in d else d), archived


def sgo() -> pd.DataFrame:
    return sgo_parts()[0]


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
    out["regulation"] = sorted(manual_rows(SLUG, "regulation"), key=lambda r: r["date"], reverse=True)
    cp = manual(SLUG, "cpuc_trips")
    out["cpuc"] = {k: _pts(v, 0) for k, v in cp.items()} if isinstance(cp, dict) else {}
    return out


def _safety_now() -> dict:
    def counts():
        d, archived = sgo_parts()
        d = d[d["month"] >= "2021-07-01"]
        top = d["entity"].value_counts().head(6).index.tolist()
        by = d.assign(entity=d["entity"].where(d["entity"].isin(top), "Others")).groupby(["month", "entity"]).size().unstack(fill_value=0)
        by = by.reindex(pd.date_range(by.index.min(), by.index.max(), freq="MS"), fill_value=0)
        miles = manual(SLUG, "miles")
        rate = []
        for op, m in (miles.items() if isinstance(miles, dict) and archived else []):     # without the archive, reports to date would be undercounted
            mine = d["entity"].str.lower().str.startswith(op.lower())                         # "Waymo" matches "Waymo LLC"
            for t, v in m.items():
                n = int((mine & (d["month"] <= t)).sum())
                if v:
                    rate.append({"operator": op, "date": str(t.date()), "miles": _r(v, 0), "reports": n, "per_million": _r(n / (v / 1e6), 3)})
        return {"months": [int(t.timestamp()) for t in by.index], "entities": {e: [int(x) for x in by[e]] for e in by.columns}, "rate": rate,
                "total": _pts(by.sum(axis=1), 0), "total_12m": _pts(by.sum(axis=1).rolling(12).sum(), 0),
                "latest_month": str(by.index[-1].date()), "n": int(len(d)), "archived": archived}
    out = payload({"reports": counts}, sources=[SGO, SGO_ARCHIVE])
    out["as_of"] = (out.get("reports") or {}).get("latest_month")
    return out


def yahoo(sym: str, start: str = "2019-01-01") -> pd.Series:
    from ._base import yahoo_daily
    return yahoo_daily(sym, start, lambda *a, **k: fetch_json(*a, **k))


def _tesla_now() -> dict:
    t = manual(SLUG, "tesla")
    t = t if isinstance(t, dict) else {}
    out = payload({"tsla": lambda: _pts(yahoo("TSLA"), 2)}, sources=[])
    out["quarterly"] = {k: _pts(v, 0) for k, v in t.items() if k in ("Deliveries", "Production")}
    out["fsd_miles"] = _pts(t.get("FSD (Supervised) cumulative miles", pd.Series(dtype=float)), 0)
    d = t.get("Deliveries")
    if d is not None and len(d) >= 5:
        out["kpi"] = {"deliveries_last": _r(d.iloc[-1], 0), "quarter": str(d.index[-1].date()), "yoy": _r(d.iloc[-1] / d.iloc[-5] - 1, 4),
                      "ttm": _r(d.iloc[-4:].sum(), 0)}
    ms = sorted(manual_rows(SLUG, "tesla_milestones"), key=lambda r: r["date"], reverse=True)
    out["milestones"] = ms
    out["fsd_markets"] = sorted({r["market"] for r in ms if r.get("area") == "FSD"})
    out["rows"] = sorted(manual_rows(SLUG, "tesla"), key=lambda r: r["date"], reverse=True)
    if out.get("tsla"):
        px = out["tsla"]
        out.setdefault("kpi", {})["tsla"] = px[-1][1]
        out["kpi"]["tsla_1y"] = _r(px[-1][1] / next((v for t0, v in reversed(px) if t0 <= px[-1][0] - 365 * 86400), px[0][1]) - 1, 4)
    out["as_of"] = max([r["date"] for r in out["rows"]] + ([pd.Timestamp(out["tsla"][-1][0], unit="s").strftime("%Y-%m-%d")] if out.get("tsla") else []), default=None)
    return out


CPUC_PAGE = ("https://www.cpuc.ca.gov/regulatory-services/licensing/transportation-licensing-and-analysis-branch/autonomous-vehicle-programs/"
             "quarterly-reporting")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def cpuc_links(html: str) -> list[dict]:
    """Data files linked from the CPUC quarterly-reporting page, in page order: [{"text", "url"}]."""
    import re
    out = []
    for href, text in re.findall(r'<a[^>]+href="([^"]+\.(?:xlsx|xls|csv|zip)[^"]*)"[^>]*>(.*?)</a>', html, flags=re.I | re.S):
        url = href if href.startswith("http") else "https://www.cpuc.ca.gov" + ("" if href.startswith("/") else "/") + href
        out.append({"text": re.sub(r"<[^>]+>|\s+", " ", text).strip()[:120], "url": url.replace("&amp;", "&")})
    return out


def _cpuc_probe() -> dict:
    """Not a tab: what the server sees at the CPUC quarterly-reporting page and inside its deployment zips, to write the trips parser
    against the real layout (/api/robotaxi/cpuc)."""
    import requests
    import zipfile
    from io import BytesIO
    r = requests.get(CPUC_PAGE, headers=UA, timeout=30)
    links = cpuc_links(r.text)
    dep = [ln["url"] for ln in links if "deploy" in ln["url"].lower() and ln["url"].lower().endswith(".zip")]
    out = {"status": r.status_code, "n_links": len(links), "deployment_zips": dep, "zips": {}}

    def head(name, raw):
        if name.lower().endswith(".csv"):
            return [ln[:300] for ln in raw.decode("utf-8", "replace").splitlines()[:6]]
        if name.lower().endswith((".xlsx", ".xls")):
            xl = pd.ExcelFile(BytesIO(raw))
            return {sh: [" | ".join(str(c)[:30] for c in rw) for rw in xl.parse(sh, header=None, nrows=6).fillna("").values.tolist()] for sh in xl.sheet_names[:4]}
        return None
    for url in [u for u in dep if "2026q2" in u or "2025-q1" in u or "dec-2024" in u][:3]:
        try:
            z = zipfile.ZipFile(BytesIO(requests.get(url, headers=UA, timeout=120).content))
            info = {"members": [[m.filename, m.file_size] for m in z.infolist()][:40], "heads": {}}
            for m in z.infolist():
                if "month" in m.filename.lower() and not "tract" in m.filename.lower() and m.file_size < 5_000_000:
                    info["heads"][m.filename] = head(m.filename, z.read(m))
            out["zips"][url] = info
        except Exception as e:
            out["zips"][url] = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    return out


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"rides": _cached_ep("rides", _rides_now, 600), "footprint": _cached_ep("footprint", _footprint_now, 600), "safety": _cached_ep("safety", _safety_now),
             "tesla": _cached_ep("tesla", _tesla_now), "cpuc": _cached_ep("cpuc", _cpuc_probe, 3600)}
