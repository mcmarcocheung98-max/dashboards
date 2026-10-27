"""AI dashboard (/ai): AI jobs against law and finance, and how fast firms and people adopt AI tools and agents, US, UK and Hong Kong.

The two halves keep their own modules (ai_jobs.py: Indeed postings, BLS headcount and pay; ai_adoption.py: Census BTOS,
Ramp, user and agent milestones, Indeed AI tracker); this module joins their endpoints, sources and notes into one page.
Hand-entered data for both halves lives in data/ai/.
"""
from __future__ import annotations

from . import ai_adoption, ai_jobs

DAY_S = 86400


def READINGS() -> list[dict]:
    """Headline readings for 'what changed since yesterday', from cached payloads only.
    lean +1 = the balance is moving towards AI (more AI postings or use, AI-side pay or jobs outgrowing law and finance, the
    professions shrinking); -1 = the reverse; 0 = steady. Thresholds are in each note."""
    from ..cache import _cache
    got = lambda key: (_cache.get(key) or (0, {}))[1] or {}
    jobs = lambda name: got(f"topic:ai-jobs:{name}")
    adopt = lambda name: got(f"topic:{ai_adoption.SLUG}:{name}")
    band = lambda d, hi, lo=None: None if d is None else (1 if d >= hi else -1 if d <= (-hi if lo is None else lo) else 0)

    def back(pts, days):
        """(last value, value nearest `days` before it) of a [[t, v], ...] list."""
        pts = [p for p in pts or [] if p[1] is not None]
        if len(pts) < 2:
            return (pts[-1][1] if pts else None), None
        want = pts[-1][0] - days * DAY_S
        return pts[-1][1], min(pts[:-1], key=lambda p: abs(p[0] - want))[1]
    out = []

    def add(tab, key, label, value, lean, note=None):
        if value is not None:
            out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": lean or 0, **({"note": note} if note else {})})

    for cc, name in (("US", "US"), ("GB", "UK")):
        v = (jobs("openings").get("ai_share_latest") or {}).get(cc) or {}
        if v.get("share") is not None and v.get("year_ago") is not None:
            add("openings", f"ai_share_{cc.lower()}", f"{name}: job postings mentioning AI (%)", v["share"], band(v["share"] - v["year_ago"], 0.2),
                "+1 if 0.2 points or more above a year ago, -1 if 0.2 below")
    ratio = (jobs("ratio").get("US") or {}).get("ai_over_professions")
    now, before = back(ratio, 91)
    if None not in (now, before):
        add("ratio", "ai_over_prof_us", "US: AI-sector postings ÷ law & finance postings", now, band(now - before, 0.02), "+1 if up 0.02 or more on 13 weeks ago, -1 if down 0.02")
    lat = (jobs("headcount").get("US") or {}).get("latest") or {}
    for n, key in (("Legal services", "us_legal_yoy"), ("Finance & insurance", "us_finance_yoy")):
        y = (lat.get(n) or {}).get("yoy")
        add("headcount", key, f"US {n.lower()} jobs, change on a year (%)", y, None if y is None else (1 if y <= -0.5 else -1 if y >= 0.5 else 0),
            "+1 if down 0.5% or more on a year (the profession shrinking), -1 if up 0.5% or more")
    fin, fin_before = back((jobs("headcount").get("HK") or {}).get("Financing & insurance"), 365)
    if None not in (fin, fin_before):
        ch = round((fin / fin_before - 1) * 100, 2)
        add("headcount", "hk_finance_yoy", "Hong Kong financing & insurance persons engaged, change on a year (%)", ch, 1 if ch <= -0.5 else -1 if ch >= 0.5 else 0,
            "+1 if down 0.5% or more, -1 if up 0.5% or more")
    pay = jobs("wages").get("latest") or {}
    tech, legal = (pay.get("Computer systems design") or {}).get("yoy"), (pay.get("Legal services") or {}).get("yoy")
    if None not in (tech, legal):
        add("wages", "pay_tech_minus_legal", "US pay growth: computer systems design minus legal services (points)", round(tech - legal, 2), band(tech - legal, 0.5),
            "+1 if tech pay grows 0.5 points a year faster, -1 if 0.5 slower")
    f = adopt("firms")
    for key, label, pts, days, step in (("btos_us", "US businesses using AI (Census BTOS, %)", f.get("btos_us"), 84, 0.5),
                                        ("ramp_us", "US businesses paying for AI tools (Ramp, %)", f.get("ramp"), 90, 0.5),
                                        ("uk_firms", "UK businesses using AI (ONS BICS, %)", (f.get("uk_hk") or {}).get("UK: all businesses (ONS BICS)"), 91, 0.5)):
        now, before = back(pts, days)
        if now is not None:
            add("firms", key, label, now, None if before is None else band(now - before, step),
                f"+1 if up {step} points or more on about {days // 7} weeks before, -1 if down as much")
    users = (adopt("users").get("series") or {}).get("ChatGPT weekly active users") or []
    if users:
        high = len(users) > 1 and users[-1][1] > max(v for _, v in users[:-1])
        add("users", "chatgpt_wau", "ChatGPT weekly active users, latest announced", users[-1][1], 1 if high else 0, "+1 when the latest announcement is a new high")
    rows = adopt("agents").get("rows") or []
    if rows:
        import pandas as pd
        last = pd.Timestamp(rows[0]["date"])
        a = sum(1 for r in rows if pd.Timestamp(r["date"]) > last - pd.DateOffset(years=1))
        b = sum(1 for r in rows if last - pd.DateOffset(years=2) < pd.Timestamp(r["date"]) <= last - pd.DateOffset(years=1))
        add("agents", "launches_12m", "Agent launches and protocols in the 12 months to the latest", a, 1 if a > b else -1 if a < b else 0,
            "+1 if more than in the 12 months before, -1 if fewer")
    sk = adopt("skills").get("latest") or {}
    moves = [v["share"] - v["year_ago"] for v in sk.values() if v.get("share") is not None and v.get("year_ago") is not None]
    if moves:
        up = sum(m > 0 for m in moves)
        add("skills", "countries_rising", f"Countries where the AI share of postings rose on a year (of {len(moves)})", up,
            1 if up > len(moves) / 2 else -1 if up < len(moves) / 2 else 0, "+1 if more than half rose, -1 if more than half fell")
    return out

ENDPOINTS = {**ai_jobs.ENDPOINTS, **ai_adoption.ENDPOINTS}
SOURCES = ai_jobs.SOURCES + [s for s in ai_adoption.SOURCES if s["url"] not in {x["url"] for x in ai_jobs.SOURCES}]
NOTES = ai_jobs.NOTES + " " + ai_adoption.NOTES
