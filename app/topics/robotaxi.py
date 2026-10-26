"""Autonomous car adoption (/robotaxi). Mostly hand-entered: operators announce numbers, they do not publish feeds.

rides      paid driverless rides per week by operator (announcements, hand-entered: data/robotaxi/rides.csv) and quarterly ride
           counts where that is what the operator reports (Baidu Apollo Go)
footprint  where each operator offers public driverless rides and since when (data/robotaxi/cities.csv), rules and pilots
           (regulation.csv), and California driverless trips per quarter from the CPUC deployment files (automated)
safety     crash reports filed by automated-driving-system operators under NHTSA's Standing General Order (CSV, monthly, automated),
           counted per month and per reporting entity (current file plus the pre-June-2025 archive), and per million driverless miles for
           operators that publish miles (data/robotaxi/miles.csv)

Each hand-entered row carries the source it came from. NHTSA data is cached a day and snapshotted.
"""
from __future__ import annotations

from io import StringIO

import pandas as pd

from . import _base as B
from ._base import DAY, _part, _pts, _r, fetch, fetch_json, manual, manual_rows, manual_sources, payload, stale_info

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
    _part(out, "cpuc", lambda: {k: _pts(v, 0) for k, v in cpuc_trips().items()})
    out["stale"] = stale_info([CPUC_PAGE])
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


# Quarterly series in tesla.csv set against the TSLA price; "pct" metrics compare by % change, "diff" ones (margins, EPS, cash flow,
# which can be negative) by change in level. "release" = published in the production and deliveries release, about the 2nd of
# the month after the quarter.
CORR_METRICS = [("Deliveries", "pct", True), ("Production", "pct", True), ("Energy storage deployed (GWh)", "pct", True),
                ("Revenue ($M)", "pct", False), ("GAAP gross margin (%)", "diff", False), ("Operating margin (%)", "diff", False),
                ("Non-GAAP EPS ($)", "diff", False), ("Free cash flow ($M)", "diff", False), ("Active FSD subscriptions (M)", "pct", False)]


def tesla_vs_price(px: pd.Series, t: dict[str, pd.Series], min_n: int = 6) -> dict:
    """Pearson correlations between Tesla's quarterly figures and TSLA: level vs quarter-end close, change on a year vs the
    share price's change on a year, change on the quarter vs the quarter's return, and (for the deliveries release) the
    change vs the share price's move on the release day. Contemporaneous, not predictive: a quarter's figures come out after
    its last close."""
    px = px.dropna().sort_index()
    qs = t.get("Deliveries", pd.Series(dtype=float)).index
    if not len(px) or not len(qs):
        return {"rows": [], "quarters": []}

    def close_by(d):
        s = px[:d]
        return float(s.iloc[-1]) if len(s) else float("nan")

    def release_move(q):
        day = q + pd.DateOffset(months=3) + pd.Timedelta(days=1)                   # the 2nd of the month after the quarter
        i = px.index.searchsorted(day)
        if i == 0 or i >= len(px) or px.index[i] - day > pd.Timedelta(days=5):
            return float("nan")
        return float(px.iloc[i] / px.iloc[i - 1] - 1)
    end = pd.Series([close_by(q + pd.DateOffset(months=3) - pd.Timedelta(days=1)) for q in qs], index=qs)
    prev = pd.Series([close_by(q - pd.Timedelta(days=1)) for q in qs], index=qs)
    ret = end / prev - 1
    yoy = end / end.shift(4) - 1
    move = pd.Series([release_move(q) for q in qs], index=qs)
    rows = []

    def add(metric, basis, a, b):
        ok = pd.concat([a, b], axis=1).dropna()
        if len(ok) >= min_n:
            rows.append({"metric": metric, "basis": basis, "n": int(len(ok)), "r": _r(ok.iloc[:, 0].corr(ok.iloc[:, 1]), 2),
                         "from": str(ok.index[0].date()), "to": str(ok.index[-1].date())})
    table = {"quarter": [str(q.date()) for q in qs], "close": [_r(x, 2) for x in end], "quarter_return": [_r(x, 4) for x in ret],
             "release_move": [_r(x, 4) for x in move]}
    for name, how, release in CORR_METRICS:
        m = t.get(name)
        if m is None or not len(m):
            continue
        m = m.reindex(qs)
        y = m.pct_change(4, fill_method=None) if how == "pct" else m.diff(4)
        qq = m.pct_change(1, fill_method=None) if how == "pct" else m.diff(1)
        add(name, "level vs quarter-end close", m, end)
        add(name, "change on a year vs TSLA change on a year", y, yoy)
        add(name, "change on the quarter vs TSLA return that quarter", qq, ret)
        if release:
            add(name, "change on a year vs TSLA move on release day", y, move)
            add(name, "change on the quarter vs TSLA move on release day", qq, move)
        table[name] = [None if pd.isna(x) else _r(x, 2) for x in m]
    return {"rows": rows, "quarters": table}


FIN_LAG = pd.Timedelta(days=35)      # financials count as known 35 days after the quarter: after Tesla's earnings call (about day 20-29)
COST = 0.001                         # per switch between TSLA and cash


def _known(q: pd.Timestamp, release: bool) -> pd.Timestamp:
    """When a quarter's figure became public: the deliveries release on the 2nd of the following month, else the earnings lag."""
    end = q + pd.DateOffset(months=3)
    return end + pd.Timedelta(days=1) if release else end - pd.Timedelta(days=1) + FIN_LAG


def tesla_signal(px: pd.Series, t: dict[str, pd.Series], threshold: float = 0.0) -> dict:
    """A composite of every quarterly figure in CORR_METRICS, rebuilt on each day a figure came out using only what was public then:
    each metric votes +1 if better than a year earlier, -1 if worse (volumes and revenue by % change, margins/EPS/cash flow/FSD by
    level), and the signal is the mean vote. Backtest: hold TSLA from the next trading day while the signal is above `threshold`,
    otherwise cash (no interest), COST per switch; against buy-and-hold over the same days."""
    px = px.dropna().sort_index()
    known: list[tuple[pd.Timestamp, str, int]] = []           # (date public, metric, vote)
    for name, how, release in CORR_METRICS:
        m = t.get(name)
        if m is None or len(m) < 5:
            continue
        m = m.sort_index()
        chg = m.pct_change(4, fill_method=None) if how == "pct" else m.diff(4)
        for q, c in chg.dropna().items():
            if q - pd.DateOffset(years=1) in m.index:                 # four rows back really is the same quarter a year earlier
                known.append((_known(q, release), name, 1 if c > 0 else -1 if c < 0 else 0))
    if not known or len(px) < 30:
        return {"events": [], "stats": None}
    known.sort()
    dates = sorted({d for d, _, _ in known if px.index[0] <= d <= px.index[-1]})
    events, latest = [], {}
    for d in dates:
        for k_d, name, v in known:
            if k_d <= d:
                latest[name] = v
        sig = sum(latest.values()) / len(latest)
        events.append({"date": str(d.date()), "signal": _r(sig, 3), "votes": dict(latest), "long": bool(sig > threshold)})
    if not events:
        return {"events": [], "stats": None}
    # position from the trading day after each event (the release lands that morning or after the close)
    start = pd.Timestamp(events[0]["date"])
    days = px[px.index > start]
    ret = px.pct_change().reindex(days.index).fillna(0.0)
    pos = pd.Series(0.0, index=days.index)
    sig_daily = pd.Series(float("nan"), index=days.index)
    for e in events:
        after = days.index > pd.Timestamp(e["date"])
        pos[after] = 1.0 if e["long"] else 0.0
        sig_daily[after] = e["signal"]
    switches = pos.diff().abs().fillna(pos.iloc[0])
    strat = (1 + pos * ret - switches * COST).cumprod()
    hold = (1 + ret).cumprod()
    years = max((days.index[-1] - days.index[0]).days / 365.25, 1e-9)

    def stats(eq):
        dd = eq / eq.cummax() - 1
        return {"total": _r(eq.iloc[-1] - 1, 4), "cagr": _r(eq.iloc[-1] ** (1 / years) - 1, 4), "max_drawdown": _r(dd.min(), 4)}
    for i, e in enumerate(events):                        # what TSLA did until the next event: did the signal call it?
        a = px[px.index > pd.Timestamp(e["date"])]
        b_date = pd.Timestamp(events[i + 1]["date"]) if i + 1 < len(events) else px.index[-1]
        b = px[px.index <= b_date]
        e["tsla_next"] = _r(float(b.iloc[-1] / a.iloc[0] - 1), 4) if len(a) and len(b) and b.index[-1] >= a.index[0] else None
    called = [e for e in events if e["tsla_next"] is not None and e["tsla_next"] != 0]
    hits = sum((e["long"] and e["tsla_next"] > 0) or (not e["long"] and e["tsla_next"] < 0) for e in called)
    first = float(px[px.index <= start].iloc[-1]) if len(px[px.index <= start]) else float(days.iloc[0])
    return {"events": events, "threshold": threshold, "cost": COST,
            "stats": {"from": str(days.index[0].date()), "to": str(days.index[-1].date()), "years": _r(years, 2),
                      "strategy": stats(strat), "buy_hold": stats(hold), "invested": _r(float(pos.mean()), 3),
                      "switches": int(switches.sum()), "periods": len(called), "hits": int(hits), "metrics": len(latest)},
            "equity": _pts(strat * first, 2), "hold": _pts(hold * first, 2), "signal": _pts(sig_daily.dropna(), 3)}


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
    if out.get("tsla"):                                                             # last, so a log tail of /api/robotaxi/tesla shows it
        px = pd.Series([v for _, v in out["tsla"]], index=pd.to_datetime([ts for ts, _ in out["tsla"]], unit="s"))
        _part(out, "correlation", lambda: tesla_vs_price(px, t))
        _part(out, "signal", lambda: tesla_signal(px, t))
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


CARRIERS = {"PSG0038152": "Waymo", "PSG0039080": "Cruise"}     # CPUC carrier (TCP) ids


def parse_cpuc_month(text: str) -> list[dict]:
    """A deployment zip's month-level file (TCPID,Year,Month,TotalTrips,...; numbers with thousands commas) -> rows."""
    d = pd.read_csv(StringIO(text), dtype=str)
    d.columns = [c.strip() for c in d.columns]
    if not {"TCPID", "Year", "Month", "TotalTrips"} <= set(d.columns):
        raise ValueError("CPUC month-level layout changed")
    trips = pd.to_numeric(d["TotalTrips"].str.replace(",", "", regex=False), errors="coerce")
    return [{"carrier": CARRIERS.get(t.strip().upper(), t.strip()), "month": f"{int(y):04d}-{int(m):02d}-01", "trips": int(v)}
            for t, y, m, v in zip(d["TCPID"], d["Year"], d["Month"], trips) if pd.notna(v) and str(y).strip().isdigit()]


def _cpuc_zip(url: str) -> bytes:
    import requests
    r = requests.get(url, headers=UA, timeout=300)
    r.raise_for_status()
    return r.content


def cpuc_zip_months(url: str) -> list[dict]:
    """Month rows of one deployment zip, read once and kept on the snapshot volume (the zips are ~60 MB; only the month file is kept)."""
    import hashlib
    import json
    import zipfile
    from io import BytesIO
    snap = B.SNAP_DIR / f"cpuc-{hashlib.sha1(url.encode()).hexdigest()[:16]}.json"
    if snap.exists():
        return json.loads(snap.read_text())
    z = zipfile.ZipFile(BytesIO(_cpuc_zip(url)))
    rows = []
    for m in z.infolist():
        name = m.filename.lower()
        if "_av_month" in name.replace(" ", "_").replace("-", "_") and "tract" not in name and name.endswith(".csv"):
            rows += parse_cpuc_month(z.read(m).decode("utf-8-sig", "replace"))
    B.SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps(rows))                       # an empty list too: a zip without a month file is not fetched again
    return rows


def cpuc_trips(max_new: int = 3) -> dict[str, pd.Series]:
    """Completed driverless passenger trips per quarter per carrier (date = quarter start), from the CPUC deployment zips; quarters
    with all three months only. At most `max_new` zips are downloaded per call, so the first run fills in over a few warm cycles.
    Hand-entered rows in cpuc_trips.csv are kept for quarters the files do not cover."""
    try:
        page = fetch(CPUC_PAGE, TTL, headers=UA, min_bytes=1000)
    except Exception:
        page = ""                                           # never reached and no snapshot: the hand-entered rows only
    links = [ln["url"] for ln in cpuc_links(page) if "deploy" in ln["url"].lower() and ln["url"].lower().split("?")[0].endswith(".zip")]
    import hashlib
    seen, new = {}, 0
    for url in dict.fromkeys(links):                       # page order: newest first, so a later revision wins over an older file
        cached = (B.SNAP_DIR / f"cpuc-{hashlib.sha1(url.encode()).hexdigest()[:16]}.json").exists()
        if not cached:
            if new >= max_new:
                continue
            new += 1
        try:
            for r in cpuc_zip_months(url):
                seen.setdefault((r["carrier"], r["month"]), r["trips"])
        except Exception:
            continue                                        # one unreadable zip does not blank the card
    out: dict[str, pd.Series] = {}
    if seen:
        m = pd.Series(seen)
        for carrier in sorted({k[0] for k in seen}):
            s = m[carrier]
            s.index = pd.to_datetime(s.index)
            q = s.groupby(s.index.to_period("Q"))
            full = q.sum()[q.size() == 3]
            out[carrier] = pd.Series(full.values, index=full.index.to_timestamp(), dtype=float)
    hand = manual(SLUG, "cpuc_trips")
    for k, v in (hand.items() if isinstance(hand, dict) else []):
        cur = out.get(k, pd.Series(dtype=float))
        out[k] = pd.concat([cur, v[~v.index.isin(cur.index)]]).sort_index()
    return out


ENERGY_PROBES = {
    "ember yearly": "https://storage.googleapis.com/emb-prod-bkt-publicdata/public-downloads/yearly_full_release_long_format.csv",
    "ember monthly": "https://storage.googleapis.com/emb-prod-bkt-publicdata/public-downloads/monthly_full_release_long_format.csv",
    "ember page": "https://ember-energy.org/data/yearly-electricity-data/",
    "iea evs csv": "https://api.iea.org/evs?parameters=EV%20sales%20share&category=Historical&mode=Cars&csv=true",
    "iea evs json": "https://api.iea.org/evs/?parameters=EV%20sales%20share&category=Historical&mode=Cars",
}


def _energy_probe() -> dict:
    """Not a tab: status, type, size and the first bytes of each candidate Energy source as this server sees them
    (/api/robotaxi/energy_probe), to write the parsers against the real layouts."""
    import re
    import requests
    out = {}
    for k, u in ENERGY_PROBES.items():
        try:
            r = requests.get(u, headers=UA, timeout=40, stream=True)
            head = r.raw.read(4000, decode_content=True).decode("utf-8", "replace")
            r.close()
            out[k] = {"status": r.status_code, "type": r.headers.get("content-type", ""), "length": r.headers.get("content-length"),
                      "start": head[:1200], "csv_links": sorted(set(re.findall(r'https?://[^"\' ]+\.csv', head)))[:20]}
        except Exception as e:
            out[k] = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    return out


# ------------------------------------------------------------------ READINGS
def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


def _cmp(a, b, better_up: bool = True) -> int:
    if a is None or b is None or a == b:
        return 0
    return (1 if a > b else -1) * (1 if better_up else -1)


def readings(got) -> list[dict]:
    """Headline indicators per tab from the tab payloads. +1 = adoption speeding up, safety improving or TSLA leaning up; -1 the
    opposite; 0 flat or unknown."""
    out: list[dict] = []
    now = pd.Timestamp.now().normalize()
    r = got("rides")
    for key, op, src in (("waymo_weekly", "Waymo", "weekly"), ("baidu_quarterly", "Baidu Apollo Go", "quarterly")):
        pts = (r.get(src) or {}).get(op) or []
        if pts:
            prev = pts[-2][1] if len(pts) > 1 else None
            out.append({"tab": "rides", "key": key, "label": f"{op}: rides a {'week' if src == 'weekly' else 'quarter'}", "value": pts[-1][1],
                        "lean": _cmp(pts[-1][1], prev), "note": f"as announced {pd.Timestamp(pts[-1][0], unit='s').date()}; previous {prev}"})
    f = got("footprint")
    rows = f.get("rows") or []
    if rows:
        recent = [x for x in rows if pd.Timestamp(x["date"]) >= now - pd.Timedelta(days=180)]
        out.append({"tab": "footprint", "key": "cities", "label": "Cities with public driverless rides", "value": len(rows),
                    "lean": 1 if recent else 0, "note": f"{len(recent)} opened in the last 180 days"})
    cp = (f.get("cpuc") or {}).get("Waymo") or []
    if cp:
        out.append({"tab": "footprint", "key": "cpuc_waymo", "label": "California driverless trips, latest quarter (CPUC)", "value": cp[-1][1],
                    "lean": _cmp(cp[-1][1], cp[-2][1] if len(cp) > 1 else None), "note": f"quarter from {pd.Timestamp(cp[-1][0], unit='s').date()}"})
    reg = f.get("regulation") or []
    if reg:
        new = [x for x in reg if pd.Timestamp(x["date"]) >= now - pd.Timedelta(days=90)]
        out.append({"tab": "footprint", "key": "rules_90d", "label": "New rules, licences and pilots, last 90 days", "value": len(new),
                    "lean": 1 if new else 0})
    rate = [x for x in ((got("safety").get("reports") or {}).get("rate") or []) if x.get("operator") == "Waymo"]
    if rate:
        prev = rate[-2]["per_million"] if len(rate) > 1 else None
        out.append({"tab": "safety", "key": "waymo_per_million", "label": "Waymo crash reports per million driverless miles", "value": rate[-1]["per_million"],
                    "lean": _cmp(rate[-1]["per_million"], prev, better_up=False), "note": f"to {rate[-1]['date']}; previous {prev} (lower is better)"})
    t = got("tesla")
    px = t.get("tsla") or []
    if len(px) >= 200:
        avg = sum(v for _, v in px[-200:]) / 200
        out.append({"tab": "tesla", "key": "tsla_vs_200d", "label": "TSLA vs its 200-day average", "value": _r(px[-1][1] / avg - 1, 4),
                    "lean": _cmp(px[-1][1], avg), "note": f"close {px[-1][1]}, 200-day average {_r(avg, 2)}"})
    k = t.get("kpi") or {}
    if k.get("yoy") is not None:
        out.append({"tab": "tesla", "key": "deliveries_yoy", "label": "Tesla deliveries vs a year earlier", "value": k["yoy"], "lean": _cmp(k["yoy"], 0),
                    "note": f"quarter from {k.get('quarter')}"})
    ev = (t.get("signal") or {}).get("events") or []
    if ev:
        out.append({"tab": "tesla", "key": "fundamentals_signal", "label": "Tesla fundamentals signal (mean of yearly votes)", "value": ev[-1]["signal"],
                    "lean": 1 if ev[-1]["long"] else -1 if ev[-1]["signal"] < 0 else 0, "note": f"as of {ev[-1]['date']}"})
    return out


def READINGS() -> list[dict]:
    """Each tab's indicators as they read now, from the cached tab payloads only (nothing is fetched)."""
    return readings(_cached_payload)


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"rides": _cached_ep("rides", _rides_now, 600), "footprint": _cached_ep("footprint", _footprint_now, 600), "safety": _cached_ep("safety", _safety_now),
             "tesla": _cached_ep("tesla", _tesla_now), "energy_probe": _cached_ep("energy_probe", _energy_probe, 3600)}
