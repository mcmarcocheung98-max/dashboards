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
ONS_AI_ARTICLE = "https://www.ons.gov.uk/businessindustryandtrade/business/businessservices/articles/artificialintelligenceinukbusinesses/2023to2026"
CSD_TABLES = [f"215-16{n:03d}" for n in range(1, 12)]


def _layout_now() -> dict:
    """Not a tab: what the server sees at sources the AI page could automate (ONS BICS AI tables, C&SD 215 tables, Ramp AI Index,
    the BTOS National workbook), so parsers are written against the real files. Read with Actions > show-json on /api/ai/layout."""
    import re
    from concurrent.futures import ThreadPoolExecutor
    from io import BytesIO
    import requests
    from ._base import UA

    def page(url):
        r = requests.get(url, headers={**UA, "Accept": "text/html,*/*"}, timeout=20)
        return {"status": r.status_code, "bytes": len(r.text), "files": sorted(set(re.findall(r'href="(/file\?uri=[^"]+|[^"]+\.(?:xlsx|csv|xls))"', r.text)))[:40]}

    def ramp():
        t = requests.get(RAMP_PAGE, headers={**UA, "Accept": "text/html,*/*"}, timeout=20).text.replace('\\"', '"')
        hits = [m.start() for m in re.finditer(r"2026-0[89]|Sep(?:tember)? 2026|55\.9", t)]
        return {"bytes": len(t), "hits": len(hits), "around": [t[max(0, i - 300):i + 300] for i in hits[:6]],
                "series_like": sorted(set(re.findall(r'.{0,60}"(?:date|month|x)":"?20\d\d-\d\d[^}]{0,120}', t)))[:30]}

    def csd(tid):
        r = requests.get(CSD_API.format(tid=tid), headers=UA, timeout=20)
        row = {"status": r.status_code, "type": r.headers.get("content-type", ""), "bytes": len(r.content)}
        try:
            j = r.json()
            row["keys"] = list(j)[:12] if isinstance(j, dict) else type(j).__name__
            row["start"] = str(j)[:1500]
        except Exception:
            row["start"] = r.text[:300]
        return row

    def btos():
        r = requests.get(ai_adoption.BTOS_XLSX, headers=UA, timeout=30)
        row = {"status": r.status_code, "bytes": len(r.content)}
        if r.ok:
            xl = pd.ExcelFile(BytesIO(r.content))
            row["sheets"] = xl.sheet_names[:20]
            d = xl.parse("Response Estimates", header=None, dtype=str)
            row["questions"] = sorted({f"{a} {b}" for a, b in zip(d[0], d[1]) if isinstance(b, str)})[:60]
            row["ai rows"] = [" | ".join(str(c) for c in rw[:12]) for rw in d.values.tolist() if any(isinstance(c, str) and ("intelligence" in c.lower() or " AI" in c) for c in rw)]
            dd = xl.parse("Collection and Reference Dates", header=None, dtype=str).dropna(how="all")
            row["dates"] = [" | ".join(str(c) for c in rw) for rw in dd.values.tolist()[:6]]
        return row

    def ons_wave(n):
        t = requests.get(ONS_BICS_PAGE, headers=UA, timeout=20).text
        links = re.findall(rf'href="(/file\?uri=[^"]+/bicswave{n}/[^"]+\.xlsx)"', t)
        if not links:
            return {"error": f"no wave {n} xlsx on the page"}
        url = "https://www.ons.gov.uk" + links[0]
        r = requests.get(url, headers=UA, timeout=30)
        xl = pd.ExcelFile(BytesIO(r.content))
        out = {"url": url, "bytes": len(r.content), "ai sheets": [s for s in xl.sheet_names if re.search(r"\bAI\b|artificial", s, re.I)]}
        for sh in out["ai sheets"][:5]:
            d = xl.parse(sh, header=None, dtype=str).dropna(how="all")
            out[sh] = [" | ".join(str(c)[:60] for c in rw if isinstance(c, str))[:300] for rw in d.values.tolist()[:12]]
        return out

    jobs = {("pages", "ons ai article"): (page, ONS_AI_ARTICLE), ("pages", "ramp"): (ramp,)}
    jobs.update({("csd", t): (csd, t) for t in CSD_TABLES})
    jobs[("files", "btos national")] = (btos,)
    jobs.update({("files", f"ons bics wave {n}"): (ons_wave, n) for n in (165, 164, 163)})

    def run(job):
        try:
            return job[0](*job[1:])
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    out: dict = {"pages": {}, "csd": {}, "files": {}}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (group, key), res in zip(jobs, ex.map(run, jobs.values())):
            out[group][key] = res
    return out


def _cached_layout():
    from ..cache import _cached
    return _cached("topic:ai:layout:v2", 1800, _layout_now)


ENDPOINTS = {**ai_jobs.ENDPOINTS, **ai_adoption.ENDPOINTS, "layout": _cached_layout}
SOURCES = ai_jobs.SOURCES + [s for s in ai_adoption.SOURCES if s["url"] not in {x["url"] for x in ai_jobs.SOURCES}]
NOTES = ai_jobs.NOTES + " " + ai_adoption.NOTES
