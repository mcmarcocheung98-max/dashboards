"""AI dashboard (/ai): AI jobs against law and finance, and how fast firms and people adopt AI tools and agents, US, UK and Hong Kong.

The two halves keep their own modules (ai_jobs.py: Indeed postings, BLS headcount and pay; ai_adoption.py: Census BTOS,
Ramp, user and agent milestones, Indeed AI tracker); this module joins their endpoints, sources and notes into one page.
Hand-entered data for both halves lives in data/ai/.
"""
from __future__ import annotations

import pandas as pd

from . import ai_adoption, ai_jobs

ONS_BICS_PAGE = "https://www.ons.gov.uk/economy/economicoutputandproductivity/output/datasets/businessinsightsandimpactontheukeconomy"
CSD_API = "https://www.censtatd.gov.hk/api/get.php?id={tid}&lang=en"
LAYOUT_PAGES = {"ons bics datasets": ONS_BICS_PAGE,
                "ramp ai index": "https://ramp.com/data/ai-index",
                "ramp data": "https://ramp.com/data"}
CSD_TABLES = [f"215-16{n:03d}" for n in range(1, 13)] + ["210-06101", "210-06102"]


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
        t = r.text
        nums = sorted(set(re.findall(r"[^<>]{0,80}\d{1,2}\.\d%[^<>]{0,60}", t)))[:40]
        return {"status": r.status_code, "bytes": len(t), "files": sorted(set(re.findall(r'href="(/file\?uri=[^"]+|[^"]+\.(?:xlsx|csv|xls))"', t)))[:40],
                "percents": nums, "next_data": t[t.find("__NEXT_DATA__"):][:400] if "__NEXT_DATA__" in t else None}

    def csd(tid):
        r = requests.get(CSD_API.format(tid=tid), headers=UA, timeout=20)
        row = {"status": r.status_code, "type": r.headers.get("content-type", ""), "bytes": len(r.content)}
        try:
            j = r.json()
            row["keys"] = list(j)[:12] if isinstance(j, dict) else type(j).__name__
            row["start"] = str(j)[:900]
        except Exception:
            row["start"] = r.text[:300]
        return row

    def btos():
        r = requests.get(ai_adoption.BTOS_XLSX, headers=UA, timeout=30)
        row = {"status": r.status_code, "bytes": len(r.content)}
        if r.ok:
            xl = pd.ExcelFile(BytesIO(r.content))
            row["sheets"] = xl.sheet_names[:20]
            for sh in xl.sheet_names[:6]:
                d = xl.parse(sh, header=None, dtype=str).dropna(how="all")
                rows = [" | ".join(str(c)[:30] for c in rw if isinstance(c, str)) for rw in d.values.tolist()]
                ai = [i for i, x in enumerate(rows) if "artificial intelligence" in x.lower()]
                row[sh] = {"shape": list(d.shape), "head": [x[:400] for x in rows[:4]],
                           "ai": [rows[j][:600] for i in ai[:2] for j in range(i, min(i + 4, len(rows)))]}
        return row

    def ons_newest():
        t = requests.get(ONS_BICS_PAGE, headers=UA, timeout=20).text
        links = re.findall(r'href="(/file\?uri=[^"]+\.xlsx)"', t)
        if not links:
            return {"error": "no xlsx link on the page"}
        url = "https://www.ons.gov.uk" + links[0]
        r = requests.get(url, headers=UA, timeout=30)
        xl = pd.ExcelFile(BytesIO(r.content))
        out = {"url": url, "bytes": len(r.content), "sheets": xl.sheet_names}
        for sh in [s for s in xl.sheet_names if "ai" in s.lower() or "artificial" in s.lower()][:4]:
            d = xl.parse(sh, header=None, dtype=str).dropna(how="all")
            out[sh] = [" | ".join(str(c)[:30] for c in rw if isinstance(c, str))[:400] for rw in d.values.tolist()[:14]]
        return out

    jobs = {("pages", k): (page, u) for k, u in LAYOUT_PAGES.items()}
    jobs.update({("csd", t): (csd, t) for t in CSD_TABLES})
    jobs[("files", "btos national")] = (btos,)
    jobs[("files", "ons bics newest workbook")] = (ons_newest,)

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
    return _cached("topic:ai:layout", 1800, _layout_now)


ENDPOINTS = {**ai_jobs.ENDPOINTS, **ai_adoption.ENDPOINTS, "layout": _cached_layout}
SOURCES = ai_jobs.SOURCES + [s for s in ai_adoption.SOURCES if s["url"] not in {x["url"] for x in ai_jobs.SOURCES}]
NOTES = ai_jobs.NOTES + " " + ai_adoption.NOTES
