"""AI dashboard (/ai): AI jobs against law and finance, and how fast firms and people adopt AI tools and agents, US, UK and Hong Kong.

The two halves keep their own modules (ai_jobs.py: Indeed postings, BLS headcount and pay; ai_adoption.py: Census BTOS,
Ramp, user and agent milestones, Indeed AI tracker); this module joins their endpoints, sources and notes into one page.
Hand-entered data for both halves lives in data/ai/.
"""
from __future__ import annotations

import pandas as pd

from . import ai_adoption, ai_jobs

ONS_BICS_PAGE = "https://www.ons.gov.uk/economy/economicoutputandproductivity/output/datasets/businessinsightsandimpactontheukeconomy"
CSD_API = "https://www.censtatd.gov.hk/api/get.php?id={tid}&lang=en&full_series=1"
RAMP_PAGE = "https://ramp.com/data/ai-index"


def _layout_now() -> dict:
    """Not a tab: what the server sees at sources the AI page could automate (ONS BICS AI tables, C&SD table 215-16001, Ramp AI Index),
    so parsers are written against the real files. Read with Actions > show-json on /api/ai/layout."""
    import re
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor
    from io import BytesIO
    import requests
    from ._base import UA

    def ramp():
        t = requests.get(RAMP_PAGE, headers={**UA, "Accept": "text/html,*/*"}, timeout=20).text.replace('\\"', '"')
        num = [m.start() for m in re.finditer(r"(?<![\d.])(?:55\.9\d*|0\.559\d*)(?![\d%])", t)]
        return {"bytes": len(t), "numeric hits": len(num), "around": [t[max(0, i - 500):i + 300] for i in num[:5]],
                "links": sorted(set(re.findall(r'(?:href|src)="([^"]*(?:csv|json|xlsx|download|api)[^"]*)"', t)))[:30],
                "keys": Counter(re.findall(r'"([a-zA-Z_]{3,30})":', t)).most_common(60)}

    def csd(tid):
        j = requests.get(CSD_API.format(tid=tid), headers=UA, timeout=40).json()
        recs = j.get("dataSet") or next((v for v in j.values() if isinstance(v, list)), [])
        out = {"keys": list(j), "records": len(recs), "first": recs[:3], "last": recs[-2:]}
        if recs and isinstance(recs[0], dict):
            out["values"] = {k: sorted({str(r.get(k)) for r in recs})[:60] for k in recs[0] if k not in ("figure", "value", "obs_value")}
        return out

    def ons():
        t = requests.get(ONS_BICS_PAGE, headers=UA, timeout=20).text
        url = "https://www.ons.gov.uk" + re.findall(r'href="(/file\?uri=[^"]+/bicswave165/[^"]+\.xlsx)"', t)[0]
        xl = pd.ExcelFile(BytesIO(requests.get(url, headers=UA, timeout=40).content))
        out = {"url": url, "sheets": xl.sheet_names[:12]}
        for sh in ("AI Current Usage TS (WTD)", "AI Plan to Adopt TS (WTD)"):
            d = xl.parse(sh, header=None, dtype=str)
            h = next(i for i in range(len(d)) if str(d.iat[i, 0]).strip() == "Dates")
            body = d.iloc[h + 1:]
            out[sh] = {"header": d.iloc[h].tolist(), "rows": len(body), "dates": sorted(set(body[0].dropna()))[:80],
                       "bands": sorted(set(body[2].dropna())),
                       "all rows": [" | ".join(map(str, r)) for r in body.values.tolist() if re.search(r"^all|total|all (?:business|industr)", str(r[2]), re.I)][:40]}
        return out

    jobs = {("pages", "ramp"): (ramp,), ("csd", "215-16001"): (csd, "215-16001"), ("files", "ons bics wave 165"): (ons,)}

    def run(job):
        try:
            return job[0](*job[1:])
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    out: dict = {"pages": {}, "csd": {}, "files": {}}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for (group, key), res in zip(jobs, ex.map(run, jobs.values())):
            out[group][key] = res
    return out


def _cached_layout():
    from ..cache import _cached
    return _cached("topic:ai:layout:v3", 1800, _layout_now)


ENDPOINTS = {**ai_jobs.ENDPOINTS, **ai_adoption.ENDPOINTS, "layout": _cached_layout}
SOURCES = ai_jobs.SOURCES + [s for s in ai_adoption.SOURCES if s["url"] not in {x["url"] for x in ai_jobs.SOURCES}]
NOTES = ai_jobs.NOTES + " " + ai_adoption.NOTES
