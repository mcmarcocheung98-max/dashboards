"""AI jobs vs law & finance: the jobs half of /ai. Free data only.

openings   Indeed Hiring Lab job postings index by sector (daily, 1 Feb 2020 = 100, refreshed weekly; US and UK): Software Development
           and Data & Analytics (where AI roles sit) against Legal, Banking & Finance, Accounting and Insurance; plus the share of all
           postings that mention AI (Indeed AI Tracker, monthly refresh, several countries)
headcount  US payroll employment (BLS via FRED, monthly, thousands): legal services, finance & insurance, securities & investments,
           computer systems design. BLS.gov itself blocks automated downloads, so FRED's CSV is used (through curl, see _base._download)
ratio      the AI share of postings against the professions' postings index, and headcount growth since 2020 side by side

hk headcount  C&SD table 215-16001 (quarterly persons engaged by industry section, JSON API): financing & insurance, professional,
           scientific & technical, information & communications

Hand-entered (data/ai/): uk_headcount.csv (ONS workforce jobs for legal and financial services, quarterly: no stable
free API, so a few points copied by hand with their source). Indeed data: CC BY 4.0, cite Indeed Hiring Lab.
"""
from __future__ import annotations

import hashlib
import json
import time
from io import StringIO

import pandas as pd

from . import _base
from ._base import DAY, _pts, _r, fetch, fetch_csv, latest_date, manual, manual_rows, monthly, payload, weekly, yoy

IND = "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/{cc}/job_postings_by_sector_{cc}.csv"
IND_ALL = "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/{cc}/aggregate_job_postings_{cc}.csv"
AI_SHARE = "https://raw.githubusercontent.com/hiring-lab/ai-tracker/main/AI_posting.csv"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"     # kept for the network test; FRED times out from Railway
BLS = "https://api.bls.gov/publicAPI/v1/timeseries/data/"            # BLS public API v1: no key, 25 queries a day, 10 years per query
CSD = "https://www.censtatd.gov.hk/api/get.php?id=215-16001&lang=en&full_series=1"   # C&SD web table 215-16001, quarterly, JSON
HK_INDUSTRIES = {"ind_K": "Financing & insurance", "ind_M": "Professional, scientific & technical", "ind_J": "Information & communications"}
SECTORS = {"ai": ["Software Development", "Data & Analytics"], "ai_wide": ["IT Systems & Solutions"], "professions": ["Legal", "Banking & Finance", "Accounting", "Insurance"]}
US_SERIES = {"Legal services": "CES6054110001", "Finance & insurance": "CES5552000001", "Securities & investments": "CES5552300001",
             "Computer systems design": "CES6054150001", "All private": "CES0500000001"}
# average hourly earnings, all employees, same industries (the "...03" twin of each employment series)
US_WAGES = {n: sid[:-2] + "03" for n, sid in US_SERIES.items()}
SOURCES = [{"name": "Indeed Hiring Lab job postings index", "url": "https://github.com/hiring-lab/job_postings_tracker", "cadence": "weekly"},
           {"name": "Indeed Hiring Lab AI tracker", "url": "https://github.com/hiring-lab/ai-tracker", "cadence": "monthly"},
           {"name": "US employment and pay by industry (BLS Current Employment Statistics, public API)", "url": "https://www.bls.gov/ces/", "cadence": "monthly"},
           {"name": "Hong Kong persons engaged by industry (C&SD table 215-16001)", "url": "https://www.censtatd.gov.hk/en/web_table.html?id=215-16001", "cadence": "quarterly"},
           {"name": "UK workforce jobs (ONS JOBS03, hand-entered)", "url": "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/workforcejobsbyindustryjobs03", "cadence": "quarterly"}]
NOTES = "Postings indexes are Indeed's seasonally adjusted counts relative to 1 February 2020 (= 100), 7-day average. 'AI share' counts postings whose text mentions AI terms (machine learning, data science, generative AI...), not only AI engineering jobs. Headcount is payroll employment, thousands."
TTL = DAY


# ------------------------------------------------------------------ parsers
def parse_sectors(text: str, names: list[str]) -> dict[str, pd.Series]:
    d = pd.read_csv(StringIO(text))
    d = d[(d["variable"] == "total postings") & d["display_name"].isin(names)]
    d["date"] = pd.to_datetime(d["date"])
    return {n: g.set_index("date")["indeed_job_postings_index"].astype(float).sort_index() for n, g in d.groupby("display_name")}


def parse_aggregate(text: str) -> pd.Series:
    d = pd.read_csv(StringIO(text))
    d = d[d["variable"] == "total postings"]
    return pd.Series(d["indeed_job_postings_index_SA"].astype(float).to_numpy(), index=pd.to_datetime(d["date"])).sort_index()


def parse_ai_share(text: str, countries=("US", "GB")) -> dict[str, pd.Series]:
    d = pd.read_csv(StringIO(text))
    d["date"] = pd.to_datetime(d["date"])
    return {cc: g.set_index("date")["AI_share_postings"].astype(float).sort_index() for cc, g in d.groupby("jobcountry") if cc in countries}


def parse_fred(text: str) -> pd.Series:
    d = pd.read_csv(StringIO(text))
    s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors="coerce").to_numpy(), index=pd.to_datetime(d.iloc[:, 0], errors="coerce"))
    return s[s.index.notna()].dropna().sort_index()


def parse_csd_persons(j: dict) -> dict[str, pd.Series]:
    """C&SD table 215-16001 JSON -> {industry: persons engaged, thousands}, dated at the survey month (Mar, Jun, Sep, Dec).
    Records look like {"IND": "ind_K", "period": "202606", "sv": "PE", "svDesc": "No.", "figure": 238500}; sv PE also comes as a
    year-on-year % change (svDesc), and a suppressed figure is "" with a note in sd_value."""
    if (j.get("header") or {}).get("status", {}).get("code") not in (0, None):
        raise ValueError(f"C&SD: {j['header']['status'].get('message')}")
    out: dict[str, dict] = {}
    for r in j.get("dataSet") or []:
        name = HK_INDUSTRIES.get(r.get("IND"))
        if name and r.get("sv") == "PE" and r.get("svDesc") == "No." and r.get("figure") not in ("", None):
            out.setdefault(name, {})[pd.Timestamp(year=int(r["period"][:4]), month=int(r["period"][4:6]), day=1)] = float(r["figure"]) / 1000
    if not out:
        raise ValueError("C&SD 215-16001: no persons-engaged rows for the chosen industries")
    return {n: pd.Series(v, dtype=float).sort_index() for n, v in out.items()}


# ------------------------------------------------------------------ data
def sectors(cc: str) -> dict[str, pd.Series]:
    return parse_sectors(fetch(IND.format(cc=cc), TTL, min_bytes=10000), SECTORS["ai"] + SECTORS["ai_wide"] + SECTORS["professions"])


def aggregate(cc: str) -> pd.Series:
    return parse_aggregate(fetch(IND_ALL.format(cc=cc), TTL))


def ai_share() -> dict[str, pd.Series]:
    return parse_ai_share(fetch(AI_SHARE, TTL), ("US", "GB", "CA", "DE", "FR", "AU", "IE", "NL", "IT"))


def parse_bls(j: dict) -> dict[str, pd.Series]:
    """BLS API JSON -> {series id: monthly Series} (periods M01..M12; M13 annual averages dropped)."""
    if j.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS: {j.get('status')} {'; '.join(j.get('message') or [])[:120]}")
    out = {}
    for ser in (j.get("Results") or {}).get("series", []):
        pts = {pd.Timestamp(year=int(d["year"]), month=int(d["period"][1:]), day=1): float(d["value"]) for d in ser.get("data", [])
               if d.get("period", "").startswith("M") and d["period"] != "M13" and d.get("value") not in ("-", "")}
        out[ser["seriesID"]] = pd.Series(pts, dtype=float).sort_index()
    return out


def _bls_query(body: dict) -> dict[str, pd.Series]:
    """One BLS query, keeping the last reply that parsed. BLS answers an over-limit request with HTTP 200 and an error body, which
    the shared snapshot would keep in place of good data, and every restart re-asks (25 queries a day for the whole server). So a
    good reply younger than a day is used without asking, and an error falls back to the last good reply, marked stale."""
    good = _base.SNAP_DIR / ("bls-good-" + hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16] + ".json")
    if good.exists() and time.time() - good.stat().st_mtime < TTL:
        return parse_bls(json.loads(good.read_text(encoding="utf-8")))
    try:
        text = fetch(BLS, TTL, post=body)
        out = parse_bls(json.loads(text))
    except Exception:
        if not good.exists():
            raise
        _base.STALE[BLS] = good.stat().st_mtime
        return parse_bls(json.loads(good.read_text(encoding="utf-8")))
    good.parent.mkdir(parents=True, exist_ok=True)
    good.write_text(text, encoding="utf-8")
    _base.STALE.pop(BLS, None)
    return out


def bls_all() -> dict[str, pd.Series]:
    """Every employment and pay series in two queries (2010-19 and 2020-now), cached a day: well inside the 25-a-day limit."""
    ids = sorted(set(US_SERIES.values()) | set(US_WAGES.values()))
    now = pd.Timestamp.now().year
    parts = [_bls_query({"seriesid": ids, "startyear": str(a), "endyear": str(b)}) for a, b in ((2010, 2019), (2020, now))]
    return {i: pd.concat([p[i] for p in parts if i in p]).sort_index() for i in ids if any(i in p for p in parts)}


def fred(sid: str) -> pd.Series:
    """A BLS series by id (name kept from when these came from FRED)."""
    s = bls_all().get(sid)
    if s is None or s.empty:
        raise ValueError(f"BLS returned no data for {sid}")
    return s


# ------------------------------------------------------------------ endpoints
def _openings_now() -> dict:
    def country(cc):
        s = sectors(cc)
        return {"sectors": {n: _pts(weekly(x), 1) for n, x in s.items()}, "all": _pts(weekly(aggregate(cc)), 1),
                "latest": {n: {"index": _r(x.iloc[-1], 1), "yoy": _r(yoy(x, 365).dropna().iloc[-1], 4) if len(x) > 400 else None} for n, x in s.items()}}
    out = payload({"US": lambda: country("US"), "GB": lambda: country("GB"),
                   "ai_share": lambda: {cc: _pts(monthly(s, "mean"), 3) for cc, s in ai_share().items()}},
                  sources=[IND.format(cc="US"), IND.format(cc="GB"), IND_ALL.format(cc="US"), IND_ALL.format(cc="GB"), AI_SHARE])
    try:
        out["as_of"] = latest_date(*sectors("US").values())
        sh = ai_share()
        out["ai_share_latest"] = {cc: {"share": _r(s.iloc[-1], 2), "year_ago": _r(s[s.index <= s.index[-1] - pd.DateOffset(years=1)].iloc[-1], 2), "date": str(s.index[-1].date())}
                                  for cc, s in sh.items() if len(s) > 400}
    except Exception:
        pass
    return out


def _headcount_now() -> dict:
    def us():
        series = {n: fred(sid) for n, sid in US_SERIES.items()}
        since = pd.Timestamp("2010-01-01")
        return {"levels": {n: _pts(s[s.index >= since], 1) for n, s in series.items()},
                "indexed": {n: _pts((s / s[s.index >= "2020-02-01"].iloc[0] * 100)[s.index >= since], 2) for n, s in series.items()},
                "yoy": {n: _pts(yoy(s)[s.index >= since] * 100, 2) for n, s in series.items()},
                "latest": {n: {"level": _r(s.iloc[-1], 1), "yoy": _r(yoy(s).iloc[-1] * 100, 2), "since_2020": _r((s.iloc[-1] / s[s.index >= "2020-02-01"].iloc[0] - 1) * 100, 2),
                               "date": str(s.index[-1].date())} for n, s in series.items()}}

    def uk():
        m = manual("ai", "uk_headcount")
        return {n: _pts(s, 0) for n, s in m.items()} if isinstance(m, dict) else {}

    def hk():
        series = parse_csd_persons(json.loads(fetch(CSD, TTL, min_bytes=10000)))
        m = manual("ai", "hk_headcount")                              # a hand-entered quarter wins
        for n, v in (m.items() if isinstance(m, dict) else []):
            x = pd.concat([series.get(n, pd.Series(dtype=float)), v])
            series[n] = x[~x.index.duplicated(keep="last")].sort_index()
        return {n: _pts(s[s.index >= "2010-01-01"], 1) for n, s in series.items()}
    out = payload({"US": us, "UK": uk, "HK": hk}, sources=[BLS, CSD])
    try:
        out["as_of"] = (out.get("US") or {}).get("latest", {}).get("Legal services", {}).get("date")
    except Exception:
        pass
    return out


def _ratio_now() -> dict:
    def ai_vs_professions(cc):
        s = sectors(cc)
        ai = pd.concat([s[n] for n in SECTORS["ai"] if n in s], axis=1).mean(axis=1)
        wide = pd.concat([s[n] for n in SECTORS["ai"] + SECTORS["ai_wide"] if n in s], axis=1).mean(axis=1)
        prof = pd.concat([s[n] for n in SECTORS["professions"] if n in s], axis=1).mean(axis=1)
        return {"ai_index": _pts(weekly(ai), 1), "ai_wide_index": _pts(weekly(wide), 1), "professions_index": _pts(weekly(prof), 1),
                "ai_over_professions": _pts(weekly(ai / prof), 3), "ai_wide_over_professions": _pts(weekly(wide / prof), 3),
                "ai_share": _pts(monthly(ai_share()[cc], "mean"), 3)}
    out = payload({"US": lambda: ai_vs_professions("US"), "GB": lambda: ai_vs_professions("GB")},
                  sources=[IND.format(cc="US"), IND.format(cc="GB"), AI_SHARE])
    try:
        out["as_of"] = latest_date(*sectors("US").values())
    except Exception:
        pass
    return out


def _wages_now() -> dict:
    """US average hourly earnings in the same industries: level, yearly change, and each against all private-sector pay."""
    try:
        have, err = bls_all(), None
    except Exception as e:                                             # BLS down and nothing kept: the page still opens, with the reason
        have, err = {}, f"{type(e).__name__}: {str(e)[:120]}"
    series = {n: have[sid] for n, sid in US_WAGES.items() if sid in have and len(have[sid])}
    allp = series.get("All private")
    since = pd.Timestamp("2010-01-01")

    def need():
        if allp is None:
            raise ValueError(err or "BLS returned no all-private pay series")
    out = payload({"levels": lambda: need() or {n: _pts(s[s.index >= since], 2) for n, s in series.items()},
                   "yoy": lambda: need() or {n: _pts(yoy(s)[s.index >= since] * 100, 2) for n, s in series.items()},
                   "premium": lambda: need() or {n: _pts((s / allp - 1).dropna()[lambda x: x.index >= since] * 100, 1) for n, s in series.items() if n != "All private"},
                   "latest": lambda: need() or {n: {"level": _r(s.iloc[-1], 2), "yoy": _r(yoy(s).iloc[-1] * 100, 2), "premium": _r((s.iloc[-1] / allp.iloc[-1] - 1) * 100, 1),
                                                    "date": str(s.index[-1].date())} for n, s in series.items()}},
                  sources=[BLS])
    out["missing"] = [n for n in US_WAGES if n not in series] if series else []      # industries BLS does not publish hourly pay for
    out["bls_error"] = err
    out["uk_hk"] = sorted(manual_rows("ai", "pay_uk_hk"), key=lambda r: r["date"], reverse=True)
    out["as_of"] = (out.get("latest") or {}).get("All private", {}).get("date")
    return out


def _cached_ep(name, fn):
    from ..cache import _cached
    return lambda: _cached(f"topic:ai-jobs:{name}", 6 * 3600, fn)


ENDPOINTS = {"openings": _cached_ep("openings", _openings_now), "headcount": _cached_ep("headcount", _headcount_now), "ratio": _cached_ep("ratio", _ratio_now),
             "wages": _cached_ep("wages", _wages_now)}
