"""AI tool & agent adoption: the adoption half of /ai. Free data where it exists; the rest hand-entered with its source.

firms    share of US businesses using AI in the last two weeks, national and by sector (US Census Bureau Business Trends and Outlook
         Survey, every two weeks; the national workbook is parsed when reachable, and data/ai-adoption/btos_ai_use_us.csv holds
         the headline figures by hand so the chart survives a layout change); Ramp AI Index (share of US businesses paying for AI tools,
         monthly, hand-entered)
users    consumer reach: weekly active users of ChatGPT and other reported milestones (hand-entered, each with its source)
agents   a dated timeline of agent products and protocols (hand-entered)
skills   the share of job postings mentioning AI by country (Indeed Hiring Lab AI tracker, shared with /ai-jobs)

Everything cached a day and snapshotted; a dead source leaves its last chart with a 'stale since' note.
"""
from __future__ import annotations

from io import BytesIO

import pandas as pd

from ._base import DAY, _pts, _r, fetch, manual, manual_rows, manual_sources, monthly, payload

BTOS_XLSX = "https://www.census.gov/hfp/btos/downloads/National.xlsx"
AI_SHARE = "https://raw.githubusercontent.com/hiring-lab/ai-tracker/main/AI_posting.csv"
SLUG = "ai"
SOURCES = [{"name": "US Census Bureau, Business Trends and Outlook Survey (AI questions)", "url": "https://www.census.gov/hfp/btos/", "cadence": "every 2 weeks"},
           {"name": "Ramp AI Index (hand-entered)", "url": "https://ramp.com/data", "cadence": "monthly"},
           {"name": "Indeed Hiring Lab AI tracker", "url": "https://github.com/hiring-lab/ai-tracker", "cadence": "monthly"},
           {"name": "Company announcements and press reports (hand-entered, cited per point)", "url": "", "cadence": "as announced"}]
NOTES = "Survey shares are the percentage of responding businesses answering yes. Hand-entered points carry the source they were copied from; a point marked 'verify' in its note is a seed value to be checked against the source."
TTL = DAY


# ------------------------------------------------------------------ BTOS workbook (best effort: layout may change, then the hand-entered file carries the chart)
def _pct(x) -> float:
    try:
        return float(str(x).strip().rstrip("%"))
    except ValueError:
        return float("nan")


def parse_btos(content: bytes, needle: str = "two weeks") -> pd.Series:
    """The 'Yes' share by reference period for a national AI question in the BTOS National workbook ('two weeks' = used AI recently,
    'six months' = expects to use AI). Census calls it "Super Intelligence or SI (formerly referred to as Artificial Intelligence or
    AI)" since 2026. Layout (Oct 2026): sheet 'Response Estimates' with Question ID | Question | Answer ID | Answer | 202621 | ...
    (period codes, newest first, values like '24.6%' or '.'), and sheet 'Collection and Reference Dates' mapping each code (Smpdt)
    to its reference period end (Ref End), which is the date used here."""
    xl = pd.ExcelFile(BytesIO(content))
    if "Response Estimates" in xl.sheet_names and "Collection and Reference Dates" in xl.sheet_names:
        d = xl.parse("Response Estimates", header=None, dtype=str)
        head = d.iloc[0].tolist()
        q, a = d[1].fillna("").str.lower(), d[3].fillna("").str.strip().str.lower()
        hit = d[(q.str.contains("artificial intelligence") | q.str.contains("super intelligence")) & q.str.contains(needle) & a.eq("yes")]
        if hit.empty:
            raise ValueError(f"BTOS AI question ({needle}) not found")
        dates = xl.parse("Collection and Reference Dates", dtype=str)
        dates.columns = [str(c).strip() for c in dates.columns]
        ref = dict(zip(dates["Smpdt"].str.strip(), pd.to_datetime(dates["Ref End"], errors="coerce")))
        pts = {ref[str(c).strip()]: _pct(v) for c, v in zip(head[4:], hit.iloc[0].tolist()[4:]) if str(c).strip() in ref}
        s = pd.Series(pts, dtype=float).dropna().sort_index()
        if s.empty:
            raise ValueError("BTOS AI question has no values")
        return s[s.index.notna()]
    for sheet in xl.sheet_names:                                       # older layout: dates in a header row, question and answer text in the rows
        d = xl.parse(sheet, header=None, dtype=str)
        text = d.astype(str).apply(lambda c: c.str.lower())
        mask = text.apply(lambda c: c.str.contains("artificial intelligence", na=False) & c.str.contains(needle, na=False)).any(axis=1)
        if not mask.any():
            continue
        yes = text.apply(lambda c: c.str.strip().eq("yes")).any(axis=1) & mask
        if not yes.any():
            continue
        row = d[yes].iloc[0]
        header = next((d.iloc[i] for i in range(d.shape[0]) if pd.to_datetime(d.iloc[i].astype(str), errors="coerce", format="mixed").notna().sum() >= 2), None)
        if header is None:
            continue
        dates = pd.to_datetime(header.astype(str), errors="coerce", format="mixed").to_numpy()
        vals = pd.to_numeric(row, errors="coerce").to_numpy()
        keep = ~pd.isna(dates)
        s = pd.Series(vals[keep], index=pd.DatetimeIndex(dates[keep])).dropna().sort_index()
        if len(s):
            return s
    raise ValueError("BTOS AI question not found")


def btos(needle: str = "two weeks", hand_file: str = "btos_ai_use_us") -> pd.Series:
    auto = pd.Series(dtype=float)
    try:
        auto = parse_btos(fetch(BTOS_XLSX, TTL, min_bytes=1000, binary=True).encode("latin-1"), needle)
    except Exception:
        pass
    hand = manual(SLUG, hand_file)
    s = pd.concat([hand if isinstance(hand, pd.Series) else pd.Series(dtype=float), auto])
    return s[~s.index.duplicated(keep="last")].sort_index()


# ------------------------------------------------------------------ endpoints
def _firms_now() -> dict:
    def sectors():
        m = manual(SLUG, "btos_ai_use_by_sector")
        return {k: _pts(v, 2) for k, v in m.items()} if isinstance(m, dict) else {}
    def countries():
        m = manual(SLUG, "firm_adoption_uk_hk")
        return {k: _pts(v, 2) for k, v in m.items()} if isinstance(m, dict) else {}
    out = payload({"btos_us": lambda: _pts(btos(), 2), "btos_expect": lambda: _pts(btos("six months", "btos_ai_expect_us"), 2), "btos_sectors": sectors,
                   "ramp": lambda: _pts(manual(SLUG, "ramp_ai_index"), 2), "uk_hk": countries},
                  sources=[BTOS_XLSX])
    b = out.get("btos_us") or []
    out["now"] = {"btos": b[-1][1] if b else None, "btos_date": pd.Timestamp(b[-1][0], unit="s").strftime("%Y-%m-%d") if b else None,
                  "btos_year_ago": next((v for t, v in reversed(b) if t <= b[-1][0] - 365 * 86400), None) if b else None,
                  "ramp": out["ramp"][-1][1] if out.get("ramp") else None}
    out["as_of"] = out["now"]["btos_date"]
    out["cited"] = manual_sources(SLUG, "btos_ai_use_us")[:3] + manual_sources(SLUG, "ramp_ai_index")[:3]
    out["uk_hk_rows"] = sorted(manual_rows(SLUG, "firm_adoption_uk_hk"), key=lambda r: r["date"], reverse=True)
    return out


def _users_now() -> dict:
    m = manual(SLUG, "users")
    series = {k: _pts(v, 0) for k, v in m.items()} if isinstance(m, dict) else {}
    out = payload({"series": lambda: series, "rows": lambda: sorted(manual_rows(SLUG, "users"), key=lambda r: r["date"], reverse=True)})
    out["as_of"] = max((r["date"] for r in out["rows"] or []), default=None)
    return out


def _agents_now() -> dict:
    rows = sorted(manual_rows(SLUG, "agent_milestones"), key=lambda r: r["date"], reverse=True)
    out = payload({"rows": lambda: rows, "by_year": lambda: pd.Series([r["date"][:4] for r in rows]).value_counts().sort_index().to_dict()})
    out["as_of"] = rows[0]["date"] if rows else None
    return out


def _skills_now() -> dict:
    from .ai_jobs import ai_share
    sh = ai_share()
    out = payload({"share": lambda: {cc: _pts(monthly(s, "mean"), 3) for cc, s in sh.items()},
                   "latest": lambda: {cc: {"share": _r(s.iloc[-1], 2), "year_ago": _r(s[s.index <= s.index[-1] - pd.DateOffset(years=1)].iloc[-1], 2),
                                           "two_years_ago": _r(s[s.index <= s.index[-1] - pd.DateOffset(years=2)].iloc[-1], 2)} for cc, s in sh.items() if len(s) > 800}},
                  sources=[AI_SHARE], as_of=str(max(s.index[-1] for s in sh.values()).date()) if sh else None)
    return out


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"firms": _cached_ep("firms", _firms_now), "users": _cached_ep("users", _users_now, 600), "agents": _cached_ep("agents", _agents_now, 600),
             "skills": _cached_ep("skills", _skills_now)}
