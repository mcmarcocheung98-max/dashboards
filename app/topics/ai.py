"""AI dashboard (/ai): AI jobs against law and finance, and how fast firms and people adopt AI tools and agents, US, UK and Hong Kong.

The two halves keep their own modules (ai_jobs.py: Indeed postings, BLS headcount and pay; ai_adoption.py: Census BTOS,
Ramp, user and agent milestones, Indeed AI tracker); this module joins their endpoints, sources and notes into one page.
Hand-entered data for both halves lives in data/ai/.
"""
from __future__ import annotations

from . import ai_adoption, ai_jobs

RAMP_PAGE = "https://ramp.com/data/ai-index"


def _layout_now() -> dict:
    """Not a tab: what the server sees at the Ramp AI Index page (records embedded in the page, grouped by shape), so the parser is
    written against the real page. Read with Actions > show-json on /api/ai/layout."""
    import json
    import re
    import requests
    from ._base import UA

    try:
        t = requests.get(RAMP_PAGE, headers={**UA, "Accept": "text/html,*/*"}, timeout=20).text.replace('\\"', '"')
    except Exception as e:
        return {"ramp": {"error": f"{type(e).__name__}: {str(e)[:160]}"}}
    groups: dict = {}
    for m in re.finditer(r'\{[^{}]*"date_month":\s*"[^{}]*\}', t):
        try:
            r = json.loads(m.group(0))
        except ValueError:
            continue
        k = ",".join(sorted(r)) + "|" + str(r.get("dimension_type", ""))
        g = groups.setdefault(k, {"n": 0, "dims": set(), "sample": [], "dates": set(), "near_559": []})
        g["n"] += 1
        g["dims"].add(str(r.get("dimension_value", r.get("state_code", r.get("naics_sector", r.get("business_size", ""))))))
        g["dates"].add(r["date_month"])
        if len(g["sample"]) < 2:
            g["sample"].append(r)
        if any(isinstance(v, (int, float)) and 55.8 <= v <= 56.0 for v in r.values()) and len(g["near_559"]) < 3:
            g["near_559"].append(r)
    return {"ramp": {"bytes": len(t), "groups": {k: {**g, "dims": sorted(g["dims"])[:25], "dates": [min(g["dates"]), max(g["dates"]), len(g["dates"])]}
                                                 for k, g in groups.items()}}}


def _cached_layout():
    from ..cache import _cached
    return _cached("topic:ai:layout:v4", 1800, _layout_now)


ENDPOINTS = {**ai_jobs.ENDPOINTS, **ai_adoption.ENDPOINTS, "layout": _cached_layout}
SOURCES = ai_jobs.SOURCES + [s for s in ai_adoption.SOURCES if s["url"] not in {x["url"] for x in ai_jobs.SOURCES}]
NOTES = ai_jobs.NOTES + " " + ai_adoption.NOTES
