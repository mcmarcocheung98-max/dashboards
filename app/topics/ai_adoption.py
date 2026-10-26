"""AI tool & agent adoption: the adoption half of /ai. Free data where it exists; the rest hand-entered with its source.

firms    share of US businesses using AI in the last two weeks, national and by sector (US Census Bureau Business Trends and Outlook
         Survey, every two weeks, from the National workbook; data/ai/btos_ai_use_us.csv adds periods by hand if it lacks one); Ramp AI Index (share of US businesses paying for AI tools,
         monthly, read from the records its page embeds); UK share of firms using AI (ONS BICS, quarterly, newest wave workbook that carries the AI questions)
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
RAMP_PAGE = "https://ramp.com/data/ai-index"
RAMP_KEYS = {"date_month", "adoption_rate_pct", "mom_change_pp", "yoy_change_pp"}      # the overall series; breakdowns carry a dimension key
BICS_PAGE = "https://www.ons.gov.uk/economy/economicoutputandproductivity/output/datasets/businessinsightsandimpactontheukeconomy"
BICS_SHEET = "AI Current Usage TS (WTD)"
BICS_BANDS = {"All businesses": "UK: all businesses (ONS BICS)", "All size bands excluding 0 - 9": "UK: 10+ employees (ONS BICS)"}
AI_SHARE = "https://raw.githubusercontent.com/hiring-lab/ai-tracker/main/AI_posting.csv"
SLUG = "ai"
SOURCES = [{"name": "US Census Bureau, Business Trends and Outlook Survey (AI questions)", "url": "https://www.census.gov/hfp/btos/", "cadence": "every 2 weeks"},
           {"name": "ONS Business Insights and Conditions Survey (AI questions)", "url": BICS_PAGE, "cadence": "quarterly"},
           {"name": "Ramp AI Index", "url": RAMP_PAGE, "cadence": "monthly"},
           {"name": "Indeed Hiring Lab AI tracker", "url": "https://github.com/hiring-lab/ai-tracker", "cadence": "monthly"},
           {"name": "Company announcements and press reports (hand-entered, cited per point)", "url": "", "cadence": "as announced"}]
NOTES = "Survey shares are the percentage of responding businesses answering yes. Hand-entered points carry the source they were copied from; Census reworded its AI question for the period ending 16 Nov 2025 (now 'Super Intelligence or SI (formerly AI) in any of its business functions'); the US line starts there."
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


# ------------------------------------------------------------------ Ramp AI Index: the page embeds its chart data
def parse_ramp(html: str) -> pd.Series:
    """Share of US businesses on Ramp paying for AI tools, %, monthly, from the records the Ramp AI Index page embeds (Next.js payload,
    Oct 2026): the overall series is the set of {"date_month", "adoption_rate_pct", "mom_change_pp", "yoy_change_pp"} records;
    breakdowns by vendor, sector, size and state add a key of their own and are left out."""
    import json
    import re
    t = html.replace('\\"', '"')
    pts = {}
    for m in re.finditer(r'\{[^{}]*"date_month":\s*"[^{}]*\}', t):
        try:
            r = json.loads(m.group(0))
        except ValueError:
            continue
        if set(r) == RAMP_KEYS and isinstance(r["adoption_rate_pct"], (int, float)):
            pts[pd.Timestamp(r["date_month"])] = float(r["adoption_rate_pct"])
    s = pd.Series(pts, dtype=float).sort_index()
    if len(s) < 12 or not s.between(0, 100).all():
        raise ValueError(f"Ramp AI Index layout changed ({len(s)} overall points found)")
    return s


def ramp() -> pd.Series:
    """Automated points plus ramp_ai_index.csv; a hand-entered month wins."""
    auto = pd.Series(dtype=float)
    try:
        auto = parse_ramp(fetch(RAMP_PAGE, TTL, headers={"Accept": "text/html,*/*"}, min_bytes=50000))
    except Exception:
        pass
    hand = manual(SLUG, "ramp_ai_index")
    s = pd.concat([auto, hand if isinstance(hand, pd.Series) else pd.Series(dtype=float)])
    return s[~s.index.duplicated(keep="last")].sort_index()


# ------------------------------------------------------------------ ONS BICS (UK): the AI questions are asked every sixth wave or so
def parse_bics_ai(content: bytes) -> dict[str, pd.Series]:
    """Share of UK businesses using at least one AI technology, %, by survey period end, for all businesses and for 10+ employees.
    Sheet 'AI Current Usage TS (WTD)' of a BICS wave workbook: title lines, then Dates | Wave | Industry/Size Band | <technology>...
    | Not sure | Business does not currently use artificial intelligence technologies, as fractions; using = 1 - not sure - does not use
    (the same arithmetic gives ONS's published 'around 3 in 10' for September 2026)."""
    import re
    d = pd.read_excel(BytesIO(content), sheet_name=BICS_SHEET, header=None, dtype=str)
    h = next(i for i in range(len(d)) if str(d.iat[i, 0]).strip() == "Dates")
    cols = [str(c).strip() for c in d.iloc[h]]
    body = pd.DataFrame(d.iloc[h + 1:].to_numpy(), columns=cols)
    no = next(c for c in cols if c.lower().startswith("business does not"))
    out = {}
    for band, name in BICS_BANDS.items():
        rows = body[body["Industry/Size Band"].fillna("").str.strip() == band]
        end = pd.to_datetime(rows["Dates"].map(lambda x: re.split(r"\s+to\s+", str(x))[-1]), errors="coerce", format="%d %B %Y")
        use = (1 - pd.to_numeric(rows[no], errors="coerce") - pd.to_numeric(rows["Not sure"], errors="coerce")) * 100
        s = pd.Series(use.to_numpy(), index=end.to_numpy()).dropna()
        s = s[s.index.notna()].sort_index()
        if len(s):
            out[name] = s.round(1)
    if not out:
        raise ValueError("BICS AI usage: no all-business rows")
    return out


def bics_ai(tries: int = 7) -> dict[str, pd.Series]:
    """The newest wave workbook that carries the AI sheet (it holds the whole series back to 2023), newest wave first."""
    import re
    page = fetch(BICS_PAGE, TTL, headers={"Accept": "text/html,*/*"}, min_bytes=5000)
    links = {int(n): u for u, n in re.findall(r'href="(/file\?uri=[^"]+/bicswave(\d+)/[^"]+\.xlsx)"', page)}
    last = None
    for n in sorted(links, reverse=True)[:tries]:
        try:
            return parse_bics_ai(fetch("https://www.ons.gov.uk" + links[n], TTL, min_bytes=10000, binary=True).encode("latin-1"))
        except Exception as e:
            last = e
    raise ValueError(f"no BICS wave with AI questions among the newest {tries} ({last})")


def firm_adoption_intl() -> dict[str, pd.Series]:
    """UK from ONS BICS (automated) plus anything hand-entered in firm_adoption_uk_hk.csv; a hand-entered date wins."""
    out = {}
    try:
        out.update(bics_ai())
    except Exception:
        pass
    m = manual(SLUG, "firm_adoption_uk_hk")
    for k, v in (m.items() if isinstance(m, dict) else []):
        s = pd.concat([out.get(k, pd.Series(dtype=float)), v])
        out[k] = s[~s.index.duplicated(keep="last")].sort_index()
    return out


# ------------------------------------------------------------------ endpoints
def _year_ago(pts: list) -> float | None:
    """The value nearest one year before the last point, if one lies within 60 days of it."""
    if not pts:
        return None
    want = pts[-1][0] - 365 * 86400
    t, v = min(pts, key=lambda p: abs(p[0] - want))
    return v if abs(t - want) <= 60 * 86400 else None


def _firms_now() -> dict:
    def sectors():
        m = manual(SLUG, "btos_ai_use_by_sector")
        return {k: _pts(v, 2) for k, v in m.items()} if isinstance(m, dict) else {}
    def countries():
        return {k: _pts(v, 2) for k, v in firm_adoption_intl().items()}
    out = payload({"btos_us": lambda: _pts(btos(), 2), "btos_expect": lambda: _pts(btos("six months", "btos_ai_expect_us"), 2), "btos_sectors": sectors,
                   "ramp": lambda: _pts(ramp(), 2), "uk_hk": countries},
                  sources=[BTOS_XLSX, BICS_PAGE, RAMP_PAGE])
    b = out.get("btos_us") or []
    out["now"] = {"btos": b[-1][1] if b else None, "btos_date": pd.Timestamp(b[-1][0], unit="s").strftime("%Y-%m-%d") if b else None,
                  "btos_year_ago": _year_ago(b),
                  "ramp": out["ramp"][-1][1] if out.get("ramp") else None}
    out["as_of"] = out["now"]["btos_date"]
    out["cited"] = manual_sources(SLUG, "btos_ai_use_us")[:3] + manual_sources(SLUG, "ramp_ai_index")[:3]
    out["uk_hk_rows"] = sorted(manual_rows(SLUG, "firm_adoption_uk_hk"), key=lambda r: r["date"], reverse=True)
    out["uk_hk_latest"] = {k: {"value": p[-1][1], "date": pd.Timestamp(p[-1][0], unit="s").strftime("%Y-%m-%d"), "year_ago": _year_ago(p)}
                           for k, p in (out.get("uk_hk") or {}).items() if p}
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
