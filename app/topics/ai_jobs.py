"""AI jobs vs law & finance (/ai-jobs). Free data only.

openings   Indeed Hiring Lab job postings index by sector (daily, 1 Feb 2020 = 100, refreshed weekly; US and UK): Software Development
           and Data & Analytics (where AI roles sit) against Legal, Banking & Finance, Accounting and Insurance; plus the share of all
           postings that mention AI (Indeed AI Tracker, monthly refresh, several countries)
headcount  US payroll employment (BLS via FRED, monthly, thousands): legal services, finance & insurance, securities & investments,
           computer systems design. BLS.gov itself blocks automated downloads, so FRED's CSV is used (through curl, see _base._download)
ratio      the AI share of postings against the professions' postings index, and headcount growth since 2020 side by side

Hand-entered (data/ai-jobs/): uk_headcount.csv (ONS workforce jobs for legal and financial services, quarterly: no stable
free API, so a few points copied by hand with their source). Indeed data: CC BY 4.0, cite Indeed Hiring Lab.
"""
from __future__ import annotations

from io import StringIO

import pandas as pd

from ._base import DAY, _pts, _r, fetch, fetch_csv, latest_date, manual, monthly, payload, weekly, yoy

IND = "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/{cc}/job_postings_by_sector_{cc}.csv"
IND_ALL = "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/{cc}/aggregate_job_postings_{cc}.csv"
AI_SHARE = "https://raw.githubusercontent.com/hiring-lab/ai-tracker/main/AI_posting.csv"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
SECTORS = {"ai": ["Software Development", "Data & Analytics"], "professions": ["Legal", "Banking & Finance", "Accounting", "Insurance"]}
US_SERIES = {"Legal services": "CES6054110001", "Finance & insurance": "CES5552000001", "Securities & investments": "CES5552300001",
             "Computer systems design": "CES6054150001", "All private": "CES0500000001"}
SOURCES = [{"name": "Indeed Hiring Lab job postings index", "url": "https://github.com/hiring-lab/job_postings_tracker", "cadence": "weekly"},
           {"name": "Indeed Hiring Lab AI tracker", "url": "https://github.com/hiring-lab/ai-tracker", "cadence": "monthly"},
           {"name": "US employment by industry (BLS CES via FRED)", "url": "https://fred.stlouisfed.org/series/CES6054110001", "cadence": "monthly"},
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


# ------------------------------------------------------------------ data
def sectors(cc: str) -> dict[str, pd.Series]:
    return parse_sectors(fetch(IND.format(cc=cc), TTL, min_bytes=10000), SECTORS["ai"] + SECTORS["professions"])


def aggregate(cc: str) -> pd.Series:
    return parse_aggregate(fetch(IND_ALL.format(cc=cc), TTL))


def ai_share() -> dict[str, pd.Series]:
    return parse_ai_share(fetch(AI_SHARE, TTL), ("US", "GB", "CA", "DE", "FR", "AU", "IE", "NL", "IT"))


def fred(sid: str) -> pd.Series:
    return parse_fred(fetch(FRED.format(sid=sid), TTL, curl=True))


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
        m = manual("ai-jobs", "uk_headcount")
        return {n: _pts(s, 0) for n, s in m.items()} if isinstance(m, dict) else {}
    out = payload({"US": us, "UK": uk}, sources=[FRED.format(sid=s) for s in US_SERIES.values()])
    try:
        out["as_of"] = (out.get("US") or {}).get("latest", {}).get("Legal services", {}).get("date")
    except Exception:
        pass
    return out


def _ratio_now() -> dict:
    def ai_vs_professions(cc):
        s = sectors(cc)
        ai = pd.concat([s[n] for n in SECTORS["ai"] if n in s], axis=1).mean(axis=1)
        prof = pd.concat([s[n] for n in SECTORS["professions"] if n in s], axis=1).mean(axis=1)
        return {"ai_index": _pts(weekly(ai), 1), "professions_index": _pts(weekly(prof), 1), "ai_over_professions": _pts(weekly(ai / prof), 3),
                "ai_share": _pts(monthly(ai_share()[cc], "mean"), 3)}
    out = payload({"US": lambda: ai_vs_professions("US"), "GB": lambda: ai_vs_professions("GB")},
                  sources=[IND.format(cc="US"), IND.format(cc="GB"), AI_SHARE])
    try:
        out["as_of"] = latest_date(*sectors("US").values())
    except Exception:
        pass
    return out


def _cached_ep(name, fn):
    from ..cache import _cached
    return lambda: _cached(f"topic:ai-jobs:{name}", 6 * 3600, fn)


ENDPOINTS = {"openings": _cached_ep("openings", _openings_now), "headcount": _cached_ep("headcount", _headcount_now), "ratio": _cached_ep("ratio", _ratio_now)}
