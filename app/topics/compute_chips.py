"""AI compute, power and chips (/compute-chips): is power or chips the binding limit on AI, and does Taiwan's share actually fall?

overview   the headline numbers from every tab side by side: power share, capex growth, compute growth, chip revenue growth, Taiwan's share
power      data-centre electricity (TWh) for the US, China, UK and the world (IEA, LBNL, NESO; hand-entered: data/compute-chips/dc_power.csv)
           against total electricity demand (Ember yearly release, automated; demand.csv fills gaps), so the share of demand is computed here.
           Largest AI supercomputers by power (Epoch AI GPU clusters CSV, automated)
capex      quarterly capital expenditure of Microsoft, Alphabet, Amazon, Meta and Oracle from their 10-Q/10-K filings (SEC EDGAR companyfacts)
compute    training compute of notable AI models (Epoch AI notable models CSV): the frontier, its growth per year, models over 1e25 FLOP by country
chips      quarterly revenue of Nvidia and AMD (EDGAR) and TSMC, ASML, SMIC (IR pages, hand-entered: chip_revenue.csv); share prices from Nasdaq
supply     leading-edge (<10nm) capacity share by country (SIA/BCG, hand-entered), fab milestones (TSMC Arizona, Kumamoto, Dresden...) and the
           export-control timeline (US, Netherlands, Japan, China; Hong Kong under the China rules)

The large downloads (Ember's yearly file, EDGAR companyfacts) are cut down to the rows this page uses before they are cached and snapshotted.
"""
from __future__ import annotations

import json
import os
import time
from io import StringIO

import numpy as np
import pandas as pd
import requests

from . import Topic
from . import _base as B
from ._base import DAY, _part, _pts, _r, fetch, fetch_json, manual, manual_rows, manual_sources, payload, stale_info

SLUG = "compute-chips"
TOPIC = Topic(SLUG, "AI Compute, Power & Chips",
              "Is power or chips the binding limit on AI? Data-centre electricity, hyperscaler capex, frontier training compute, chip revenue and "
              "where leading-edge chips are made, for the US, UK, Hong Kong and China.",
              "compute_chips", (("overview", "Overview"), ("power", "Power"), ("capex", "Capex"), ("compute", "Compute"), ("chips", "Chips"),
                                ("supply", "Supply chain")),
              ("overview", "power", "capex", "compute", "chips"), icon="chip")

EMBER = "https://storage.googleapis.com/emb-prod-bkt-publicdata/public-downloads/yearly_full_release_long_format.csv"
EPOCH = "https://epoch.ai/data/notable_ai_models.csv"
EPOCH_CLUSTERS = "https://epoch.ai/data/gpu_clusters.csv"
EDGAR = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
# The SEC asks for a User-Agent of the form "Name email" and answers 403 to anything else (a descriptive one with a URL was refused
# from Railway, this form answered 200); SEC_UA overrides it on the server
SEC_HEADERS = {"User-Agent": os.environ.get("SEC_UA", "Dashboards admin@dashboards-production-bde6.up.railway.app"),
               "Accept": "application/json"}
HYPERSCALERS = {"Microsoft": 789019, "Alphabet": 1652044, "Amazon": 1018724, "Meta": 1326801, "Oracle": 1341439}
CHIPMAKERS = {"Nvidia": 1045810, "AMD": 2488}
CAPEX_TAGS = ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets")
REVENUE_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet")
TICKERS = ("NVDA", "TSM", "ASML", "AMD", "AVGO", "MU", "INTC")
ISO = {"USA": "US", "GBR": "UK", "CHN": "China", "HKG": "Hong Kong"}

SOURCES = [{"name": "IEA Energy & AI, LBNL US Data Center Energy Usage Report, NESO (hand-entered, cited per row)", "url": "https://www.iea.org/reports/energy-and-ai", "cadence": "as published"},
           {"name": "Ember yearly electricity data", "url": "https://ember-energy.org/data/yearly-electricity-data/", "cadence": "yearly"},
           {"name": "SEC EDGAR companyfacts (10-Q, 10-K)", "url": "https://www.sec.gov/edgar/sec-api-documentation", "cadence": "quarterly"},
           {"name": "Epoch AI: notable AI models, GPU clusters", "url": "https://epoch.ai/data", "cadence": "weekly"},
           {"name": "TSMC, ASML, SMIC investor relations (hand-entered)", "url": "https://investor.tsmc.com/english/quarterly-results", "cadence": "quarterly"},
           {"name": "Nasdaq quote API (share prices)", "url": "https://www.nasdaq.com/market-activity/stocks/nvda", "cadence": "daily"},
           {"name": "SIA/BCG, BIS, company announcements (hand-entered)", "url": "https://www.semiconductors.org/emerging-resilience-in-the-semiconductor-supply-chain/", "cadence": "as published"}]
NOTES = ("Power: data-centre electricity is an estimate (no country meters it); the share divides it by Ember's total demand for the same year. "
         "Capex is cash spent on property and equipment, all businesses, not only AI. Rows marked verify were entered from memory and still need checking against the cited page.")


# ------------------------------------------------------------------ downloads cut down before caching
def _get(url: str, headers: dict | None = None, keep=None) -> str:
    """The body of `url`, streamed; with keep(line) only the header line and the lines it accepts are kept (a 40 MB CSV becomes a few kB)."""
    with requests.get(url, headers={**B.UA, **(headers or {})}, stream=True, timeout=180) as r:
        r.raise_for_status()
        r.encoding = r.encoding or "utf-8"
        if keep is None:
            return r.text
        lines = r.iter_lines(decode_unicode=True)
        out = [next(lines)]
        out += [ln for ln in lines if ln and keep(ln)]
        return "\n".join(out)


def slim_fetch(url: str, ttl: float = DAY, *, headers: dict | None = None, keep=None, reduce=None, min_bytes: int = 50) -> str:
    """Like _base.fetch (memory cache, snapshot on the volume, the snapshot served and marked stale when the source is down, reported in
    /api/health), but only the reduced text is kept: keep(line) filters a CSV while it streams, reduce(text) cuts a JSON down."""
    def go():
        snap = B.SNAP_DIR / ("compute-chips-" + B._snap(url).name)
        h = B.HEALTH.setdefault(url, {"module": "compute_chips", "ok": None, "fail": None, "error": None})
        try:
            text = _get(url, headers, keep)
            text = reduce(text) if reduce else text
            if len(text) < min_bytes:
                raise ValueError(f"short response ({len(text)} bytes)")
            B.SNAP_DIR.mkdir(parents=True, exist_ok=True)
            snap.write_text(text, encoding="utf-8")
            B.STALE.pop(url, None)
            h.update(ok=time.time(), error=None)
            return text
        except Exception as e:
            h.update(fail=time.time(), error=f"{type(e).__name__}: {str(e)[:160]}")
            if snap.exists():
                B.STALE[url] = snap.stat().st_mtime
                return snap.read_text(encoding="utf-8")
            raise
    from ..cache import _cached
    return _cached(f"topic:{url}", ttl, go)


# ------------------------------------------------------------------ power
def _ember_keep(line: str) -> bool:
    return ",Demand,TWh," in line and (line.startswith("World,") or any(f",{c}," in line for c in ISO))


def parse_ember(text: str) -> dict[str, pd.Series]:
    """Ember long format (Area, ISO 3 code, Year, ..., Variable, Unit, Value) -> {region: yearly demand in TWh}, dated 1 January."""
    d = pd.read_csv(StringIO(text), dtype=str)
    cols = {c.lower().strip(): c for c in d.columns}
    need = ["area", "iso 3 code", "year", "variable", "unit", "value"]
    if not set(need) <= set(cols):
        raise ValueError("Ember layout changed")
    d = d[(d[cols["variable"]].str.strip() == "Demand") & (d[cols["unit"]].str.strip() == "TWh")]
    out = {}
    for _, r in d.iterrows():
        name = "World" if r[cols["area"]].strip() == "World" else ISO.get(str(r[cols["iso 3 code"]]).strip())
        v = pd.to_numeric(r[cols["value"]], errors="coerce")
        if name and pd.notna(v):
            out.setdefault(name, {})[pd.Timestamp(f"{int(r[cols['year']])}-01-01")] = float(v)
    return {k: pd.Series(v).sort_index() for k, v in out.items()}


def demand() -> tuple[dict[str, pd.Series], bool]:
    """Total electricity demand by region (TWh a year): Ember where it answers, the hand-entered demand.csv for years Ember lacks."""
    hand = manual(SLUG, "demand")
    hand = hand if isinstance(hand, dict) else {}
    try:
        live, ok = parse_ember(slim_fetch(EMBER, DAY, keep=_ember_keep, min_bytes=200)), True
    except Exception:
        live, ok = {}, False
    out = {}
    for k in set(hand) | set(live):
        a, b = live.get(k, pd.Series(dtype=float)), hand.get(k, pd.Series(dtype=float))
        out[k] = pd.concat([a, b[~b.index.isin(a.index)]]).sort_index()
    return out, ok


def _power_now() -> dict:
    dc = manual(SLUG, "dc_power")
    dc = dc if isinstance(dc, dict) else {}
    outlook = manual(SLUG, "dc_power_outlook")
    outlook = outlook if isinstance(outlook, dict) else {}
    dem, live = demand()

    def share():
        out = {}
        for k, s in dc.items():
            d = dem.get(k)
            if d is None:
                continue
            by_year = {t.year: v for t, v in d.items()}
            pts = [[int(t.timestamp()), _r(v / by_year[t.year], 5)] for t, v in s.items() if by_year.get(t.year)]
            if pts:
                out[k] = pts
        return out
    out = payload({"dc": lambda: {k: _pts(v, 1) for k, v in dc.items()}, "outlook": lambda: {k: _pts(v, 1) for k, v in outlook.items()},
                   "share": share, "demand": lambda: {k: _pts(v, 0) for k, v in dem.items()}, "clusters": clusters},
                  sources=[EMBER, EPOCH_CLUSTERS])
    out["ember_live"] = live
    out["rows"] = sorted(manual_rows(SLUG, "dc_power") + manual_rows(SLUG, "dc_power_outlook"), key=lambda r: (r["series"], r["date"]))
    out["cited"] = manual_sources(SLUG, "dc_power")[:6]
    out["as_of"] = B.latest_date(*dc.values()) if dc else None
    return out


# ------------------------------------------------------------------ Epoch AI
def _col(d: pd.DataFrame, *words: str) -> str | None:
    """The first column whose lower-cased name contains every word."""
    return next((c for c in d.columns if all(w in c.lower() for w in words)), None)


def clusters() -> dict:
    """Epoch AI GPU clusters: the largest cluster's power (MW) by when it came online, and today's operational power by country."""
    d = pd.read_csv(StringIO(fetch(EPOCH_CLUSTERS, DAY, min_bytes=500)), dtype=str)
    mw, when, ctry = _col(d, "power", "mw"), _col(d, "first operational") or _col(d, "operational", "date"), _col(d, "country")
    if not (mw and when and ctry):
        raise ValueError("Epoch clusters layout changed")
    x = pd.DataFrame({"mw": pd.to_numeric(d[mw].str.replace(",", ""), errors="coerce"), "date": pd.to_datetime(d[when], errors="coerce"),
                      "country": d[ctry].fillna("").map(_country), "name": d[_col(d, "name") or d.columns[0]]})
    status = _col(d, "status")
    if status:
        x["status"] = d[status].fillna("")
    x = x.dropna(subset=["mw", "date"]).sort_values("date")
    now = pd.Timestamp.now()
    x = x[x["date"] <= now + pd.Timedelta(days=366 * 3)]
    best = x["mw"].cummax()
    frontier = x[x["mw"] >= best]
    running = pd.Series(frontier["mw"].values, index=frontier["date"].values).groupby(level=0).max()
    live = x[x["date"] <= now]
    if "status" in x:
        live = live[~live["status"].str.lower().str.contains("planned|cancel", na=False)]
    by = live.groupby("country")["mw"].sum().sort_values(ascending=False)
    top = frontier.tail(8).iloc[::-1]
    return {"largest": _pts(running, 0), "by_country": {k: _r(v, 0) for k, v in by.items()},
            "top": [{"name": r["name"], "country": r["country"], "date": str(r["date"].date()), "mw": _r(r["mw"], 0)} for _, r in top.iterrows()],
            "n": int(len(x))}


def _country(s: str) -> str:
    s = str(s).split(",")[0].strip()
    if "Hong Kong" in s:
        return "Hong Kong"
    if "United States" in s or s in ("USA", "US"):
        return "US"
    if "China" in s:
        return "China"
    if "United Kingdom" in s or s == "UK":
        return "UK"
    return "Other" if s else "Unknown"


def parse_epoch(text: str) -> pd.DataFrame:
    d = pd.read_csv(StringIO(text), dtype=str)
    name, date, flop = _col(d, "model") or d.columns[0], _col(d, "publication date"), _col(d, "training compute", "flop")
    ctry, org = _col(d, "country"), _col(d, "organization")
    if not (date and flop):
        raise ValueError("Epoch layout changed")
    x = pd.DataFrame({"model": d[name], "date": pd.to_datetime(d[date], errors="coerce"), "flop": pd.to_numeric(d[flop], errors="coerce"),
                      "country": d[ctry].fillna("").map(_country) if ctry else "Unknown", "org": d[org].fillna("") if org else ""})
    return x.dropna(subset=["date", "flop"]).query("flop > 0").sort_values("date").reset_index(drop=True)


def _compute_now() -> dict:
    def frontier():
        x = parse_epoch(fetch(EPOCH, DAY, min_bytes=1000))
        lf = np.log10(x["flop"])
        # frontier = in the top 10 by compute of everything released up to that day
        tenth = lf.expanding().apply(lambda a: np.sort(a)[-10] if len(a) >= 10 else -np.inf, raw=True)
        x["frontier"] = lf >= tenth
        f = x[x["frontier"] & (x["date"] >= "2010-01-01")]
        recent = f[f["date"] >= "2018-01-01"]
        slope = np.polyfit((recent["date"] - pd.Timestamp("2018-01-01")).dt.days / 365.25, np.log10(recent["flop"]), 1)[0] if len(recent) >= 5 else None
        run = pd.Series(x["flop"].cummax().values, index=x["date"].values).groupby(level=0).max()
        big = x[x["flop"] >= 1e25]
        years = list(range(max(2020, int(x["date"].dt.year.min())), int(x["date"].dt.year.max()) + 1))
        cnt = {c: [int(((big["date"].dt.year == y) & (big["country"] == c)).sum()) for y in years] for c in ("US", "China", "UK", "Other")}
        top = x.sort_values("flop", ascending=False).head(12)
        return {"max": _pts(run[run.index >= "2010-01-01"], 0), "frontier": [[int(t.timestamp()), float(v)] for t, v in zip(f["date"], f["flop"])],
                "growth_per_year": _r(10 ** slope, 2) if slope is not None else None, "years": years, "over_1e25": cnt,
                "top": [{"model": r["model"], "org": r["org"], "country": r["country"], "date": str(r["date"].date()), "flop": float(r["flop"])} for _, r in top.iterrows()],
                "latest": str(x["date"].max().date()), "n": int(len(x))}
    out = payload({"epoch": frontier}, sources=[EPOCH])
    out["as_of"] = (out.get("epoch") or {}).get("latest")
    return out


# ------------------------------------------------------------------ SEC EDGAR
def _edgar_reduce(tags):
    def go(text: str) -> str:
        g = json.loads(text).get("facts", {}).get("us-gaap", {})
        keep = {t: [{k: f.get(k) for k in ("start", "end", "val", "filed", "form")} for f in g[t]["units"].get("USD", []) if f.get("start")]
                for t in tags if t in g}
        if not keep:
            raise ValueError("none of " + ", ".join(tags) + " in this filer's facts")
        return json.dumps(keep)
    return go


def quarterly(facts: list[dict]) -> pd.Series:
    """Quarterly values from EDGAR duration facts: a ~3-month fact as it is, otherwise a year-to-date fact minus the year-to-date fact one
    quarter shorter with the same start (how Q4 comes out of a 10-K, and quarters out of cash-flow statements, which are year to date)."""
    per = {}
    for f in sorted(facts, key=lambda f: f.get("filed") or ""):          # a later filing (restatement) wins
        if f.get("start") and f.get("end") and f.get("val") is not None:
            per[(pd.Timestamp(f["start"]), pd.Timestamp(f["end"]))] = float(f["val"])
    q = {e: v for (s, e), v in per.items() if 80 <= (e - s).days <= 100}
    by_start: dict = {}
    for (s, e), v in per.items():
        by_start.setdefault(s, []).append((e, v))
    for (s, e), v in per.items():
        if (e - s).days > 100 and e not in q:
            prev = [(e2, v2) for e2, v2 in by_start[s] if e2 < e and 80 <= (e - e2).days <= 100]
            if prev:
                q[e] = v - prev[0][1]
    return pd.Series(q, dtype=float).sort_index()


def edgar_series(cik: int, tags) -> pd.Series:
    """Quarterly series (by period end) for the first tags that cover each quarter; the tag with the latest data wins where they overlap."""
    j = json.loads(slim_fetch(EDGAR.format(cik=cik), DAY, headers=SEC_HEADERS, reduce=_edgar_reduce(tags), min_bytes=100))
    ss = sorted((quarterly(j[t]) for t in tags if t in j), key=lambda s: s.index.max() if len(s) else pd.Timestamp(0))
    out = pd.Series(dtype=float)
    for s in ss:
        out = s.combine_first(out) if len(out) else s
    return out.sort_index()


def cal_quarter(s: pd.Series) -> pd.Series:
    """Fiscal quarter ends -> calendar quarter start (the calendar quarter holding most of it: Oracle's
    quarter to end-August is Q3, Nvidia's to late October Q3, to late January Q4)."""
    idx = (pd.DatetimeIndex(s.index) - pd.Timedelta(days=45)).to_period("Q").to_timestamp()
    return pd.Series(s.values, index=idx).groupby(level=0).last()


def _capex_now() -> dict:
    co = {}
    errors = {}
    for name, cik in HYPERSCALERS.items():
        try:
            co[name] = cal_quarter(edgar_series(cik, CAPEX_TAGS)) / 1e9
        except Exception as e:
            errors[name] = type(e).__name__

    def total():
        if len(co) < len(HYPERSCALERS):
            raise LookupError("not every company answered")
        d = pd.DataFrame(co).dropna()
        return d.sum(axis=1)
    out = payload({"companies": lambda: {k: _pts(v[v.index >= "2015-01-01"], 2) for k, v in co.items()}}, sources=[EDGAR.format(cik=c) for c in HYPERSCALERS.values()])
    _part(out, "total", lambda: _pts(total()[lambda s: s.index >= "2015-01-01"], 2))
    t = out.get("total")
    if t and len(t) >= 8:
        v = [p[1] for p in t]
        out["kpi"] = {"quarter": t[-1][1], "quarter_yoy": _r(v[-1] / v[-5] - 1, 4), "ttm": _r(sum(v[-4:]), 1), "ttm_yoy": _r(sum(v[-4:]) / sum(v[-8:-4]) - 1, 4),
                      "date": pd.Timestamp(t[-1][0], unit="s").strftime("%Y-%m-%d")}
        out["ttm"] = [[t[i][0], _r(sum(v[i - 3:i + 1]), 1)] for i in range(3, len(v))]
    out["errors"] = errors
    out["as_of"] = B.latest_date(*co.values()) if co else None
    return out


# ------------------------------------------------------------------ chips
def nasdaq(sym: str) -> pd.Series:
    return B.nasdaq_daily(sym, "2019-01-01", lambda *a, **k: fetch_json(*a, **k))


def _chips_now() -> dict:
    rev, errors = {}, {}
    for name, cik in CHIPMAKERS.items():
        try:
            rev[name] = cal_quarter(edgar_series(cik, REVENUE_TAGS)) / 1e9
        except Exception as e:
            errors[name] = type(e).__name__
    hand = manual(SLUG, "chip_revenue")
    for k, v in (hand.items() if isinstance(hand, dict) else []):
        rev[k] = cal_quarter(v)
    px, perr = {}, {}
    for sym in TICKERS:
        try:
            px[sym] = nasdaq(sym)
        except Exception as e:
            perr[sym] = type(e).__name__

    def rebased():
        if not px:
            raise LookupError("no prices")
        start = max(s.index.min() for s in px.values())
        return {k: _pts(100 * s[s.index >= start] / s[s.index >= start].iloc[0], 2) for k, s in px.items()}

    def yoy():
        out = {}
        for k, s in rev.items():
            s = s[s.index >= "2016-01-01"]
            if len(s) >= 5:
                out[k] = _pts((s / s.shift(4) - 1).dropna(), 4)
        return out
    out = payload({"revenue": lambda: {k: _pts(v[v.index >= "2016-01-01"], 3) for k, v in rev.items()}, "revenue_yoy": yoy, "prices": rebased},
                  sources=[EDGAR.format(cik=c) for c in CHIPMAKERS.values()])
    out["last"] = {k: {"price": _r(s.iloc[-1], 2), "y1": _r(s.iloc[-1] / s[s.index <= s.index[-1] - pd.Timedelta(days=365)].iloc[-1] - 1, 4)
                       if (s.index <= s.index[-1] - pd.Timedelta(days=365)).any() else None} for k, s in px.items()}
    out["errors"] = {**errors, **perr}
    out["rows"] = sorted(manual_rows(SLUG, "chip_revenue"), key=lambda r: r["date"], reverse=True)
    out["as_of"] = B.latest_date(*px.values(), *rev.values()) if (px or rev) else None
    return out


# ------------------------------------------------------------------ supply chain
def _supply_now() -> dict:
    cap = manual_rows(SLUG, "capacity_share")
    years = sorted({r["date"][:4] for r in cap})
    regions = list(dict.fromkeys(r["series"] for r in cap))
    table = {reg: [next((_r(r["value"], 1) for r in cap if r["series"] == reg and r["date"][:4] == y), None) for y in years] for reg in regions}
    out = {"capacity": {"years": years, "regions": table, "rows": cap}, "fabs": sorted(manual_rows(SLUG, "fabs"), key=lambda r: r["date"], reverse=True),
           "controls": sorted(manual_rows(SLUG, "export_controls"), key=lambda r: r["date"], reverse=True), "stale": {}, "updated": int(time.time())}
    tw = table.get("Taiwan", [])
    out["taiwan"] = {"from": tw[0], "to": tw[-1], "years": [years[0], years[-1]]} if tw and years else None
    out["as_of"] = max([r["date"] for r in out["fabs"] + out["controls"]], default=None)
    return out


# ------------------------------------------------------------------ overview: one number from each tab
def _overview_now() -> dict:
    out = {"updated": int(time.time()), "stale": {}}
    for name, fn in (("power", _power), ("capex", _capex), ("compute", _compute), ("chips", _chips), ("supply", _supply)):
        try:
            out[name] = fn()
        except Exception as e:
            out[name] = None
            out[f"{name}_error"] = type(e).__name__
    p, c, k, ch, s = (out.get(x) or {} for x in ("power", "capex", "compute", "chips", "supply"))
    us = (p.get("share") or {}).get("US") or []
    nv = ((ch.get("revenue_yoy") or {}).get("Nvidia") or [])
    big = (p.get("clusters") or {}).get("largest") or []
    out["kpi"] = {"us_dc_share": us[-1][1] if us else None, "us_dc_share_year": pd.Timestamp(us[-1][0], unit="s").year if us else None,
                  "capex_ttm": (c.get("kpi") or {}).get("ttm"), "capex_ttm_yoy": (c.get("kpi") or {}).get("ttm_yoy"),
                  "compute_growth": (k.get("epoch") or {}).get("growth_per_year"), "nvidia_yoy": nv[-1][1] if nv else None,
                  "largest_cluster_mw": big[-1][1] if big else None, "taiwan": s.get("taiwan")}
    out["as_of"] = max([x.get("as_of") for x in (p, c, k, ch) if x.get("as_of")], default=None)
    out["stale"] = {**p.get("stale", {}), **c.get("stale", {}), **k.get("stale", {}), **ch.get("stale", {})}
    return out


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


_power, _capex, _compute, _chips, _supply = (_cached_ep("power", _power_now), _cached_ep("capex", _capex_now), _cached_ep("compute", _compute_now),
                                             _cached_ep("chips", _chips_now), _cached_ep("supply", _supply_now, 600))
ENDPOINTS = {"overview": _cached_ep("overview", _overview_now, 600), "power": _power, "capex": _capex, "compute": _compute, "chips": _chips, "supply": _supply}
