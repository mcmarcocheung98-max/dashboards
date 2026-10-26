"""Longevity & Biotech (/longevity): do healthy life years start rising again, and does biotech deliver it?

lifespan   life expectancy at birth 1960 on (World Bank, which carries Hong Kong; US, UK, Hong Kong, China), healthy life expectancy
           (WHO GHO HALE; US, UK, China, as WHO does not report Hong Kong) and the years lived in poor health between the two, plus each
           agency's own latest figures (CDC NCHS, ONS, C&SD/DH, NHC; hand-entered: life_expectancy.csv, healthy.csv)
causes     US age-adjusted death rates for heart disease, cancer, Alzheimer disease and drug overdoses, 12 months ending each quarter
           (CDC NCHS VSRR quarterly provisional estimates, Socrata JSON), the WHO's chance of dying 30-70 from the four main NCDs
           (US, UK, China), and England and Wales drug and dementia deaths (ONS; hand-entered: causes_uk.csv, causes_hk.csv)
glp1       NHS England primary-care prescriptions of semaglutide, tirzepatide, liraglutide and dulaglutide (OpenPrescribing API),
           Lilly and Novo Nordisk revenue (SEC EDGAR companyconcept: Lilly's 10-K/10-Q, Novo's 20-F in DKK), brand revenue and survey
           uptake (hand-entered: products.csv, uptake.csv)
approvals  FDA CDER novel drug approvals per year, cell and gene therapy approvals (FDA CBER, MHRA), and regulatory milestones
           (hand-entered: fda_novel.csv, cgt.csv, milestones.csv)
markets    XBI and IBB (biotech ETFs) against SPY, and Lilly and Novo shares (Nasdaq quote API)

Leans in READINGS(): +1 means improving health or faster innovation, -1 the opposite (data/longevity/README.md lists every rule).
"""
from __future__ import annotations

import os
from urllib.parse import quote

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from ._base import DAY, _pts, _r, fetch_json, manual, manual_rows, manual_sources, payload

SLUG = "longevity"
TOPIC = Topic(SLUG, "Longevity & Biotech",
              "Life expectancy and healthy life years in the US, UK, Hong Kong and China, what people die of, GLP-1 drugs, new drug approvals "
              "and biotech shares: do healthy years start rising again, and does biotech deliver it?",
              "longevity", (("lifespan", "Lifespan"), ("causes", "Causes"), ("glp1", "GLP-1"), ("approvals", "Approvals"), ("markets", "Biotech markets")),
              ("lifespan", "causes", "glp1", "markets"), icon="heart", order=75)

PLACES = {"USA": "US", "GBR": "UK", "HKG": "Hong Kong", "CHN": "China"}
WB_LE = "https://api.worldbank.org/v2/country/USA;GBR;HKG;CHN/indicator/SP.DYN.LE00.IN?format=json&per_page=20000&date=1960:2100"
GHO = "https://ghoapi.azureedge.net/api/{code}?$filter=" + quote("SpatialDim eq 'USA' or SpatialDim eq 'GBR' or SpatialDim eq 'CHN'", safe="'")
GHO_LE, GHO_HALE, GHO_NCD = "WHOSIS_000001", "WHOSIS_000002", "NCDMORT3070"
CDC_Q = "https://data.cdc.gov/resource/489q-934x.json?$limit=50000"
CDC_Q_SLIM = CDC_Q + "&$select=year_and_quarter,time_period,cause_of_death,rate_type,rate_overall"
CAUSES = {"Heart disease": "heart", "Cancer": "cancer", "Alzheimer disease": "alzheimer", "Drug overdose": "overdose", "All causes": "all"}
OP_SEARCH = "https://openprescribing.net/api/1.0/bnf_code/?q={q}&format=json"
OP_SPEND = "https://openprescribing.net/api/1.0/spending/?code={code}&format=json"
GLP1 = ("semaglutide", "tirzepatide", "liraglutide", "dulaglutide")
OP_FALLBACK = {"semaglutide": "0601023AW"}             # used when the BNF search does not answer
CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/{tax}/{tag}.json"
# The SEC answers 403 unless the User-Agent reads "Name email" (see data/compute-chips/README.md); SEC_UA overrides it on the server
SEC_HEADERS = {"User-Agent": os.environ.get("SEC_UA", "Dashboards admin@dashboards-production-bde6.up.railway.app"), "Accept": "application/json"}
FIRMS = {"Eli Lilly": (59478, "USD", (("us-gaap", "Revenues"), ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"))),
         "Novo Nordisk": (353278, "DKK", (("ifrs-full", "Revenue"),))}
NASDAQ_ETF = "https://api.nasdaq.com/api/quote/{sym}/historical?assetclass={cls}&fromdate={a}&todate={b}&limit=9999"
NASDAQ_HEADERS = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
TICKERS = {"XBI": "etf", "IBB": "etf", "SPY": "etf", "LLY": "stocks", "NVO": "stocks"}
START = "2016-01-04"

SOURCES = [{"name": "World Bank WDI: life expectancy at birth (API)", "url": "https://data.worldbank.org/indicator/SP.DYN.LE00.IN", "cadence": "yearly"},
           {"name": "WHO Global Health Observatory: HALE, life expectancy, NCD mortality 30-70 (OData API)", "url": "https://www.who.int/data/gho/info/gho-odata-api", "cadence": "every few years"},
           {"name": "CDC NCHS VSRR quarterly provisional mortality estimates (data.cdc.gov 489q-934x)", "url": "https://www.cdc.gov/nchs/nvss/vsrr/mortality.htm", "cadence": "quarterly"},
           {"name": "OpenPrescribing (NHS England prescribing data, API)", "url": "https://openprescribing.net/api/", "cadence": "monthly"},
           {"name": "SEC EDGAR companyconcept (Eli Lilly 10-K/10-Q, Novo Nordisk 20-F)", "url": "https://www.sec.gov/edgar/sec-api-documentation", "cadence": "quarterly"},
           {"name": "Nasdaq quote API (XBI, IBB, SPY, LLY, NVO)", "url": "https://www.nasdaq.com/market-activity/etf/xbi", "cadence": "daily"},
           {"name": "CDC NCHS, ONS, HK C&SD and DH, NHC, FDA, MHRA, NMPA, KFF, Gallup, company reports (hand-entered, cited per row)",
            "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/longevity", "cadence": "as published"}]
NOTES = ("Life expectancy is a period measure: what a baby born this year would live if today's death rates held, so a bad year (Covid, "
         "overdoses) shows at once. Healthy life expectancy (WHO HALE) counts years in full health; WHO publishes it every few years and not for "
         "Hong Kong. UK national figures are ONS three-year periods, England only for healthy life expectancy. Rows marked 'verify' were "
         "entered from memory when the dashboard was built and still need checking against the cited page.")


def _ts(year: int) -> pd.Timestamp:
    return pd.Timestamp(f"{int(year)}-07-01")


def _annual(d: dict | pd.Series) -> pd.Series:
    """{year: v} -> Series on 1 July of each year (the date every yearly point on this page uses)."""
    d = pd.Series(d, dtype=float).dropna().sort_index()
    return pd.Series(d.values, index=pd.DatetimeIndex([_ts(y) for y in d.index]), dtype=float)


def _band(x, lo, hi) -> int:
    return 0 if x is None else 1 if x > hi else -1 if x < lo else 0


def _change(s: pd.Series, years: float):
    """Latest value minus the value `years` earlier (nearest point at or before), or None."""
    s = s.dropna()
    if len(s) < 2:
        return None
    ago = s[s.index <= s.index[-1] - pd.Timedelta(days=int(years * 365.25) - 45)]
    return _r(s.iloc[-1] - ago.iloc[-1], 4) if len(ago) else None


def _latest(s: pd.Series, d: int = 2) -> dict | None:
    s = s.dropna()
    return {"date": str(s.index[-1].date()), "value": _r(s.iloc[-1], d)} if len(s) else None


# ------------------------------------------------------------------ World Bank and WHO GHO
def parse_wb(j) -> dict[str, pd.Series]:
    """World Bank v2 JSON ([meta, rows]) -> {"US": Series on 1 July}."""
    rows = j[1] if isinstance(j, list) and len(j) > 1 and isinstance(j[1], list) else []
    if not rows:
        raise ValueError("World Bank: no rows")
    out: dict[str, dict] = {}
    for r in rows:
        iso = r.get("countryiso3code") or (r.get("country") or {}).get("id")
        if iso in PLACES and r.get("value") is not None and str(r.get("date", "")).isdigit():
            out.setdefault(PLACES[iso], {})[int(r["date"])] = float(r["value"])
    return {k: _annual(v) for k, v in out.items()}


def parse_gho(j) -> dict[str, pd.Series]:
    """GHO OData ({"value": [...]}) -> {"US": Series on 1 July}, both sexes only."""
    rows = (j or {}).get("value") or []
    out: dict[str, dict] = {}
    for r in rows:
        sex = str(r.get("Dim1") or "SEX_BTSX").upper()
        if r.get("SpatialDim") in PLACES and sex.endswith("BTSX") and r.get("NumericValue") is not None and r.get("TimeDim"):
            out.setdefault(PLACES[r["SpatialDim"]], {})[int(r["TimeDim"])] = float(r["NumericValue"])
    if not out:
        raise ValueError("GHO: no rows for the three places")
    return {k: _annual(v) for k, v in out.items()}


def life_wb() -> dict[str, pd.Series]:
    return parse_wb(fetch_json(WB_LE, DAY, min_bytes=200))


def gho(code: str) -> dict[str, pd.Series]:
    return parse_gho(fetch_json(GHO.format(code=code), DAY, min_bytes=200))


# ------------------------------------------------------------------ CDC NCHS quarterly provisional mortality
def _quarter_end(s: str):
    """'2024 Q2' (or '2024Q2', 'Q2 2024') -> 2024-06-30."""
    import re
    m = re.search(r"(\d{4})\s*Q([1-4])|Q([1-4])\s*(\d{4})", str(s))
    if not m:
        return None
    y, q = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    return pd.Period(f"{y}Q{q}", "Q").end_time.normalize()


def parse_cdc(rows: list[dict]) -> dict[str, pd.Series]:
    """Socrata rows -> {"heart": Series of age-adjusted deaths per 100,000, 12 months ending each quarter}."""
    out: dict[str, dict] = {}
    for r in rows or []:
        low = {str(k).lower(): v for k, v in r.items()}
        cause = low.get("cause_of_death") or low.get("cause") or ""
        key = CAUSES.get(cause) or next((v for k, v in CAUSES.items() if cause.lower() == k.lower()), None)
        if not key or "age" not in str(low.get("rate_type", "")).lower() or "adjust" not in str(low.get("rate_type", "")).lower():
            continue
        if "12" not in str(low.get("time_period", "12 month")):
            continue
        t = _quarter_end(low.get("year_and_quarter") or low.get("quarter") or "")
        v = pd.to_numeric(low.get("rate_overall") if low.get("rate_overall") is not None else low.get("rate"), errors="coerce")
        if t is not None and pd.notna(v):
            out.setdefault(key, {})[t] = float(v)
    if not out:
        raise ValueError("CDC: no age-adjusted 12-month rows (layout changed?)")
    return {k: pd.Series(v, dtype=float).sort_index() for k, v in out.items()}


def cdc() -> dict[str, pd.Series]:
    try:
        return parse_cdc(fetch_json(CDC_Q_SLIM, DAY, min_bytes=200))
    except Exception:
        return parse_cdc(fetch_json(CDC_Q, DAY, min_bytes=200))      # a renamed column breaks $select: take every column


# ------------------------------------------------------------------ OpenPrescribing (NHS England)
def bnf_code(drug: str) -> str:
    """The chemical-level BNF code for `drug` from OpenPrescribing's search, else the known one."""
    try:
        hits = fetch_json(OP_SEARCH.format(q=drug), 30 * DAY, min_bytes=2)
        for h in hits or []:
            if str(h.get("type", "")).lower() == "chemical" and str(h.get("name", "")).lower().startswith(drug):
                return str(h["id"])
    except Exception:
        pass
    if drug in OP_FALLBACK:
        return OP_FALLBACK[drug]
    raise LookupError(f"no BNF code for {drug}")


def parse_spend(rows) -> pd.DataFrame:
    d = pd.DataFrame(rows or [])
    if d.empty or "date" not in d:
        raise ValueError("OpenPrescribing: no rows")
    d["date"] = pd.to_datetime(d["date"])
    for c in ("items", "actual_cost", "quantity"):
        d[c] = pd.to_numeric(d[c], errors="coerce") if c in d else np.nan
    return d.set_index("date").sort_index()[["items", "actual_cost", "quantity"]]


def england(drug: str) -> pd.DataFrame:
    return parse_spend(fetch_json(OP_SPEND.format(code=bnf_code(drug)), DAY, min_bytes=2))


# ------------------------------------------------------------------ SEC EDGAR companyconcept
def parse_concept(j, unit: str) -> tuple[pd.Series, pd.Series]:
    """companyconcept JSON -> (annual by fiscal-year end, quarterly by quarter end). Quarters: the ~3-month facts, and Q4 as the year
    less the three quarters before it. A later filing (a restatement) wins."""
    facts = ((j or {}).get("units") or {}).get(unit) or []
    per = {}
    for f in sorted(facts, key=lambda f: f.get("filed") or ""):
        if f.get("start") and f.get("end") and f.get("val") is not None:
            per[(pd.Timestamp(f["start"]), pd.Timestamp(f["end"]))] = float(f["val"])
    yr = {e: v for (s, e), v in per.items() if 350 <= (e - s).days <= 380}
    q = {e: v for (s, e), v in per.items() if 80 <= (e - s).days <= 100}
    for (s, e), v in per.items():
        if 350 <= (e - s).days <= 380 and e not in q:
            three = [q[x] for x in q if s < x < e]
            if len(three) == 3:
                q[e] = v - sum(three)
    return pd.Series(yr, dtype=float).sort_index(), pd.Series(q, dtype=float).sort_index()


def revenue(firm: str) -> dict:
    cik, unit, tags = FIRMS[firm]
    best = None
    for tax, tag in tags:                                  # the tag with the latest data wins; older years filled from the others
        try:
            a, q = parse_concept(fetch_json(CONCEPT.format(cik=cik, tax=tax, tag=tag), DAY, headers=SEC_HEADERS, min_bytes=100), unit)
        except Exception:
            continue
        if not len(a) and not len(q):
            continue
        if best is None:
            best = (a, q)
        else:
            newer = (a, q) if (a.index.max() if len(a) else pd.Timestamp(0)) > (best[0].index.max() if len(best[0]) else pd.Timestamp(0)) else best
            older = best if newer is not best else (a, q)
            best = (newer[0].combine_first(older[0]), newer[1].combine_first(older[1]))
    if best is None:
        raise ValueError(f"EDGAR: no revenue facts for {firm}")
    return {"annual": best[0], "quarterly": best[1], "unit": unit}


def concept_urls() -> list[str]:
    return [CONCEPT.format(cik=c, tax=t, tag=g) for c, _, tags in FIRMS.values() for t, g in tags]


# ------------------------------------------------------------------ Nasdaq
def nasdaq(sym: str) -> pd.Series:
    url = NASDAQ_ETF.format(sym=sym, cls=TICKERS[sym], a=START, b=pd.Timestamp.now().strftime("%Y-%m-%d"))
    j = fetch_json(url, DAY, headers=NASDAQ_HEADERS)
    rows = (((j or {}).get("data") or {}).get("tradesTable") or {}).get("rows") or []
    s = pd.Series({pd.to_datetime(r["date"], format="%m/%d/%Y"): float(str(r["close"]).replace("$", "").replace(",", "")) for r in rows if r.get("close")})
    if len(s) < 20:
        raise ValueError(f"Nasdaq: {len(s)} rows for {sym}")
    return s.sort_index()


def nasdaq_urls() -> list[str]:
    b = pd.Timestamp.now().strftime("%Y-%m-%d")
    return [NASDAQ_ETF.format(sym=s, cls=c, a=START, b=b) for s, c in TICKERS.items()]


# ------------------------------------------------------------------ hand-entered
def hand(name: str) -> dict[str, pd.Series]:
    m = manual(SLUG, name)
    return m if isinstance(m, dict) else {}


def rows(name: str) -> list[dict]:
    return sorted(manual_rows(SLUG, name), key=lambda r: (r.get("series", ""), r["date"]))


def cited(*names) -> list[dict]:
    return sorted([s for n in names for s in manual_sources(SLUG, n)], key=lambda s: s["date"], reverse=True)[:10]


# ------------------------------------------------------------------ tabs
def _lifespan_now() -> dict:
    def le():
        return {k: _pts(v, 2) for k, v in life_wb().items()}

    def hale():
        h, l = gho(GHO_HALE), gho(GHO_LE)
        gap = {k: (l[k] - h[k]).dropna() for k in h if k in l}
        return {"hale": {k: _pts(v, 2) for k, v in h.items()}, "le": {k: _pts(v, 2) for k, v in l.items()}, "gap": {k: _pts(v, 2) for k, v in gap.items()},
                "kpi": {k: {"hale": _latest(h[k]), "gap": _latest(gap.get(k, pd.Series(dtype=float))), "hale_10y": _change(h[k], 10)} for k in h}}
    nat, hl = hand("life_expectancy"), hand("healthy")
    out = payload({"le": le, "hale": hale, "national": lambda: {k: _pts(v, 2) for k, v in nat.items()},
                   "healthy": lambda: {k: _pts(v, 2) for k, v in hl.items()}},
                  sources=[WB_LE, GHO.format(code=GHO_HALE), GHO.format(code=GHO_LE)])
    out["kpi"] = {}
    for k, v in (life_wb().items() if out.get("le") else []):
        pre = v[v.index.year == 2019]
        out["kpi"][k] = {**(_latest(v) or {}), "vs_2019": _r(v.iloc[-1] - pre.iloc[0], 2) if len(pre) else None, "chg_3y": _change(v, 3)}
    out["national_latest"] = {k: {**(_latest(v) or {}), "chg_3y": _change(v, 3)} for k, v in nat.items() if len(v)}
    out["healthy_latest"] = {k: {**(_latest(v) or {}), "prev": _r(v.iloc[-2], 2) if len(v) > 1 else None} for k, v in hl.items() if len(v)}
    out["rows"] = rows("life_expectancy") + rows("healthy")
    out["cited"] = cited("life_expectancy", "healthy")
    out["as_of"] = max([x["date"] for x in out["national_latest"].values()] + [x.get("date") for x in out["kpi"].values() if x.get("date")], default=None)
    return out


def _causes_now() -> dict:
    def us():
        c = cdc()
        kpi = {}
        for k, s in c.items():
            ago = s[s.index <= s.index[-1] - pd.Timedelta(days=360)]
            pre = s[(s.index.year == 2019) & (s.index.month == 12)]
            kpi[k] = {**(_latest(s, 1) or {}), "year_ago": _r(ago.iloc[-1], 1) if len(ago) else None,
                      "yoy": _r(s.iloc[-1] / ago.iloc[-1] - 1, 4) if len(ago) and ago.iloc[-1] else None,
                      "vs_2019": _r(s.iloc[-1] / pre.iloc[0] - 1, 4) if len(pre) and pre.iloc[0] else None}
        return {"series": {k: _pts(v, 1) for k, v in c.items()}, "kpi": kpi}

    def ncd():
        n = gho(GHO_NCD)
        return {"series": {k: _pts(v, 2) for k, v in n.items()}, "latest": {k: {**(_latest(v) or {}), "chg_10y": _change(v, 10)} for k, v in n.items()}}
    uk, hk = hand("causes_uk"), hand("causes_hk")
    out = payload({"us": us, "ncd": ncd, "uk": lambda: {k: _pts(v, 2) for k, v in uk.items()}, "hk": lambda: {k: _pts(v, 2) for k, v in hk.items()}},
                  sources=[CDC_Q_SLIM, CDC_Q, GHO.format(code=GHO_NCD)])
    out["uk_latest"] = {k: {**(_latest(v) or {}), "prev": _r(v.iloc[-2], 2) if len(v) > 1 else None} for k, v in uk.items() if len(v)}
    out["rows"] = rows("causes_uk") + rows("causes_hk")
    out["cited"] = cited("causes_uk", "causes_hk")
    us_k = (out.get("us") or {}).get("kpi") or {}
    out["as_of"] = max([v["date"] for v in us_k.values() if v.get("date")] + [v["date"] for v in out["uk_latest"].values()], default=None)
    return out


def _glp1_now() -> dict:
    eng, errs = {}, {}
    for d in GLP1:
        try:
            eng[d] = england(d)
        except Exception as e:
            errs[d] = type(e).__name__

    def nhs():
        if not eng:
            raise LookupError("OpenPrescribing: " + ", ".join(f"{k} {v}" for k, v in errs.items()))
        tot = pd.concat([v["items"] for v in eng.values()], axis=1).sum(axis=1, min_count=1).dropna()
        y12 = tot.rolling(12).sum().dropna()
        cost = pd.concat([v["actual_cost"] for v in eng.values()], axis=1).sum(axis=1, min_count=1).dropna()
        return {"items": {k.capitalize(): _pts(v["items"], 0) for k, v in eng.items()}, "cost": {k.capitalize(): _pts(v["actual_cost"] / 1e6, 2) for k, v in eng.items()},
                "total": _pts(tot, 0), "kpi": {"month": str(tot.index[-1].date()), "items": _r(tot.iloc[-1], 0),
                                               "items_12m": _r(y12.iloc[-1], 0) if len(y12) else None,
                                               "yoy_12m": _r(y12.iloc[-1] / y12.iloc[-13] - 1, 4) if len(y12) > 12 and y12.iloc[-13] else None,
                                               "cost_12m_m": _r(cost.iloc[-12:].sum() / 1e6, 1) if len(cost) >= 12 else None},
                "missing": errs}

    def rev():
        out = {}
        for f in FIRMS:
            r = revenue(f)
            a, q = r["annual"], r["quarterly"]
            out[f] = {"unit": r["unit"], "annual": [[int(t.year), _r(v / 1e9, 2)] for t, v in a.items()], "quarterly": _pts(q / 1e9, 3),
                      "latest_year": int(a.index[-1].year) if len(a) else None, "growth": _r(a.iloc[-1] / a.iloc[-2] - 1, 4) if len(a) > 1 and a.iloc[-2] else None,
                      "q_yoy": _r(q.iloc[-1] / q.iloc[-5] - 1, 4) if len(q) > 4 and q.iloc[-5] else None, "q_last": str(q.index[-1].date()) if len(q) else None}
        return out
    prod, up = hand("products"), hand("uptake")
    out = payload({"nhs": nhs, "revenue": rev, "products": lambda: {k: [[int(t.year), _r(v, 2)] for t, v in s.items()] for k, s in prod.items()},
                   "uptake": lambda: {k: _pts(v, 1) for k, v in up.items()}},
                  sources=[OP_SPEND.format(code=OP_FALLBACK["semaglutide"]), *concept_urls()])
    out["uptake_latest"] = {k: {**(_latest(v, 1) or {}), "prev": _r(v.iloc[-2], 1) if len(v) > 1 else None} for k, v in up.items() if len(v)}
    out["rows"] = rows("products") + rows("uptake")
    out["cited"] = cited("products", "uptake")
    out["as_of"] = ((out.get("nhs") or {}).get("kpi") or {}).get("month")
    return out


def _approvals_now() -> dict:
    fda = manual(SLUG, "fda_novel")
    cgt = sorted(manual_rows(SLUG, "cgt"), key=lambda r: r["date"])
    ms = sorted(manual_rows(SLUG, "milestones"), key=lambda r: r["date"], reverse=True)
    out = payload({"fda": lambda: [[int(t.year), int(v)] for t, v in fda.items()]})
    years = sorted({int(r["date"][:4]) for r in cgt})
    agencies = sorted({r.get("agency", "") for r in cgt})
    out["cgt_by_year"] = {"years": list(range(years[0], years[-1] + 1)) if years else [],
                          "counts": {a: [sum(1 for r in cgt if r.get("agency") == a and int(r["date"][:4]) == y) for y in range(years[0], years[-1] + 1)] for a in agencies} if years else {}}
    out["cgt"] = list(reversed(cgt))
    out["milestones"] = ms
    if len(fda) > 1:
        last = fda.iloc[-1]
        prev10 = fda.iloc[-11:-1]
        out["kpi"] = {"year": int(fda.index[-1].year), "count": int(last), "avg10": _r(prev10.mean(), 1), "vs_avg": _r(last / prev10.mean() - 1, 4), "record": int(fda.max()),
                      "record_year": int(fda.idxmax().year)}
    out["cited"] = cited("fda_novel", "cgt", "milestones")
    out["as_of"] = max([r["date"] for r in cgt] + [str(fda.index[-1].date())] if len(fda) else [r["date"] for r in cgt], default=None)
    return out


def _markets_now() -> dict:
    px, errs = {}, {}
    for s in TICKERS:
        try:
            px[s] = nasdaq(s)
        except Exception as e:
            errs[s] = type(e).__name__

    def rebased():
        if not px:
            raise LookupError("Nasdaq: " + ", ".join(f"{k} {v}" for k, v in errs.items()))
        d = pd.DataFrame(px).sort_index().ffill()
        d = d[d.index >= d.dropna().index[0]] if len(d.dropna()) else d
        return {k: _pts(100 * d[k] / d[k].dropna().iloc[0], 2) for k in d}

    def stats():
        out = {}
        for k, s in px.items():
            def ret(days):
                ago = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
                return _r(s.iloc[-1] / ago.iloc[-1] - 1, 4) if len(ago) else None
            ma = s.rolling(200).mean()
            out[k] = {"date": str(s.index[-1].date()), "close": _r(s.iloc[-1], 2), "r1y": ret(365), "r5y": ret(1826), "from_peak": _r(s.iloc[-1] / s.max() - 1, 4),
                      "peak_date": str(s.idxmax().date()), "vs_200d": _r(s.iloc[-1] / ma.iloc[-1] - 1, 4) if pd.notna(ma.iloc[-1]) else None}
        return out

    def rel():
        if "XBI" not in px or "SPY" not in px:
            raise LookupError("XBI or SPY missing")
        r = (px["XBI"] / px["SPY"]).dropna()
        return _pts(100 * r / r.iloc[0], 2)
    out = payload({"rebased": rebased, "stats": stats, "xbi_spy": rel}, sources=nasdaq_urls())
    out["missing"] = errs
    out["as_of"] = max((str(s.index[-1].date()) for s in px.values()), default=None)
    return out


# ------------------------------------------------------------------ the answer and READINGS
def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


def readings(got) -> list[dict]:
    """Each tab's headline indicators from the tab payloads (got(name) -> payload or {}). lean +1 = improving health or faster innovation."""
    out = []

    def add(tab, key, label, value, lean, note):
        if value is not None:
            out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": lean, "note": note})
    L = got("lifespan")
    for k, v in (L.get("kpi") or {}).items():
        add("lifespan", f"le_{k}", f"{k} life expectancy at birth, {str(v.get('date', ''))[:4]} (World Bank)", v.get("value"), _band(v.get("chg_3y"), -0.1, 0.1),
            "+1 when up more than 0.1 years over 3 years, -1 when down")
    for k, v in (L.get("national_latest") or {}).items():
        add("lifespan", f"nat_{k}", f"{k} life expectancy, {str(v.get('date', ''))[:4]} (national)", v.get("value"), _band(v.get("chg_3y"), -0.1, 0.1),
            "+1 when up more than 0.1 years over 3 years, -1 when down")
    for k, v in (((L.get("hale") or {}).get("kpi")) or {}).items():
        h = v.get("hale") or {}
        add("lifespan", f"hale_{k}", f"{k} healthy life expectancy, {str(h.get('date', ''))[:4]} (WHO)", h.get("value"), _band(v.get("hale_10y"), -0.2, 0.2),
            "+1 when up more than 0.2 years over 10 years, -1 when down")
    for k, v in (L.get("healthy_latest") or {}).items():
        d = None if v.get("prev") is None else v["value"] - v["prev"]
        add("lifespan", f"hle_{k}", f"{k}, {str(v.get('date', ''))[:4]}", v.get("value"), _band(d, -0.1, 0.1), "+1 when up more than 0.1 years on the previous period")
    C = got("causes")
    names = {"heart": "heart disease", "cancer": "cancer", "alzheimer": "Alzheimer disease", "overdose": "drug overdose", "all": "all causes"}
    for k, v in (((C.get("us") or {}).get("kpi")) or {}).items():
        add("causes", f"us_{k}", f"US {names.get(k, k)} deaths per 100,000 (age-adjusted, 12 months to {v.get('date')})", v.get("value"), -_band(v.get("yoy"), -0.01, 0.01),
            "+1 when the rate fell more than 1% on a year earlier, -1 when it rose")
    for k, v in (((C.get("ncd") or {}).get("latest")) or {}).items():
        add("causes", f"ncd_{k}", f"{k} chance of dying 30-70 from heart disease, cancer, diabetes or lung disease, {str(v.get('date', ''))[:4]} (%)", v.get("value"),
            -_band(v.get("chg_10y"), -0.5, 0.5), "+1 when down more than 0.5 points over 10 years")
    for k, v in (C.get("uk_latest") or {}).items():
        d = None if v.get("prev") in (None, 0) else v["value"] / v["prev"] - 1
        add("causes", f"uk_{k}", f"{k}, {str(v.get('date', ''))[:4]}", v.get("value"), -_band(d, -0.02, 0.02), "+1 when down more than 2% on the year before, -1 when up")
    G = got("glp1")
    n = ((G.get("nhs") or {}).get("kpi")) or {}
    add("glp1", "nhs_items", f"NHS England GLP-1 prescription items, 12 months to {n.get('month')}", n.get("items_12m"), _band(n.get("yoy_12m"), 0, 0.10),
        "+1 when up more than 10% on the 12 months before, -1 when down")
    for f, r in ((G.get("revenue") or {}).items()):
        g = r.get("q_yoy") if r.get("q_yoy") is not None else r.get("growth")
        last = r["annual"][-1][1] if r.get("annual") else None
        add("glp1", f"rev_{f.split()[0].lower()}", f"{f} revenue growth, latest {'quarter' if r.get('q_yoy') is not None else 'year'} on a year earlier",
            g, _band(g, 0, 0.10), f"+1 above 10% a year, -1 when shrinking; latest full year {last} bn {r.get('unit')}")
    for k, v in (G.get("uptake_latest") or {}).items():
        if v.get("prev") is not None:
            add("glp1", f"up_{k}", k + f" ({str(v.get('date', ''))[:7]})", v.get("value"), _band(v["value"] - v["prev"], -0.5, 0.5) * (-1 if "obes" in k.lower() else 1),
                "+1 when uptake rose (or obesity fell) since the survey before")
    A = got("approvals").get("kpi") or {}
    add("approvals", "fda_novel", f"FDA novel drug approvals, {A.get('year')}", A.get("count"), _band(A.get("vs_avg"), -0.1, 0.1),
        "+1 when 10% above the 10 years before, -1 when 10% below")
    cg = got("approvals").get("cgt_by_year") or {}
    if cg.get("years"):
        tot = np.sum([np.array(v) for v in cg["counts"].values()], axis=0)
        this_year = pd.Timestamp.now().year
        full = [(y, int(c)) for y, c in zip(cg["years"], tot) if y < this_year]
        if len(full) >= 4:
            y, c = full[-1]
            avg = float(np.mean([x for _, x in full[-4:-1]]))
            add("approvals", "cgt", f"Cell and gene therapy approvals (FDA + MHRA), {y}", c, _band(c - avg, -1, 1), "+1 when more than one above the 3 years before")
    M = got("markets").get("stats") or {}
    x, s = M.get("XBI") or {}, M.get("SPY") or {}
    if x.get("r1y") is not None and s.get("r1y") is not None:
        d = x["r1y"] - s["r1y"]
        add("markets", "xbi_vs_spy", "XBI 1-year return minus SPY's (points)", _r(100 * d, 1), _band(d, -0.05, 0.05), "+1 when biotech beat the S&P 500 by 5 points over a year")
    if x.get("vs_200d") is not None:
        add("markets", "xbi_200d", "XBI vs its 200-day average", _r(100 * x["vs_200d"], 1), _band(x["vs_200d"], -0.02, 0.02), "+1 more than 2% above, -1 more than 2% below")
    if x.get("from_peak") is not None:
        add("markets", "xbi_peak", f"XBI below its {x.get('peak_date', '')[:4]} peak (%)", _r(100 * x["from_peak"], 1), 1 if x["from_peak"] > -0.1 else -1 if x["from_peak"] < -0.4 else 0,
            "+1 within 10% of the peak, -1 more than 40% below")
    return out


def READINGS() -> list[dict]:
    """Each tab's indicators as they read now, from the cached tab payloads only (nothing is fetched)."""
    return readings(_cached_payload)


def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, size, start of body), for checking the parsers against the live
    layouts. Read it with Actions > show-json on /api/longevity/layout."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    b = pd.Timestamp.now().strftime("%Y-%m-%d")
    urls = {"worldbank": WB_LE, "gho hale": GHO.format(code=GHO_HALE), "gho ncd": GHO.format(code=GHO_NCD), "cdc slim": CDC_Q_SLIM.replace("50000", "3"),
            "openprescribing search": OP_SEARCH.format(q="tirzepatide"), "openprescribing spend": OP_SPEND.format(code=OP_FALLBACK["semaglutide"]),
            "sec lilly": CONCEPT.format(cik=59478, tax="us-gaap", tag="Revenues"), "sec novo": CONCEPT.format(cik=353278, tax="ifrs-full", tag="Revenue"),
            "nasdaq XBI": NASDAQ_ETF.format(sym="XBI", cls="etf", a="2026-09-01", b=b),
            "gho one country": "https://ghoapi.azureedge.net/api/WHOSIS_000002?$filter=SpatialDim%20eq%20%27GBR%27",
            "gho no filter": "https://ghoapi.azureedge.net/api/WHOSIS_000002?$top=3",
            "gho indicator list": "https://ghoapi.azureedge.net/api/Indicator?$top=2",
            "who xmart": "https://xmart-api-public.who.int/DATA_/RELAY_WHS?$top=3",
            "nhsbsa epd package": "https://opendata.nhsbsa.net/api/3/action/package_show?id=english-prescribing-data-epd",
            "nhsbsa pca package": "https://opendata.nhsbsa.net/api/3/action/package_show?id=prescription-cost-analysis-pca-monthly-data",
            "nhsbsa package list": "https://opendata.nhsbsa.net/api/3/action/package_list"}

    def one(item):
        k, u = item
        h = {**B.UA, **(NASDAQ_HEADERS if "nasdaq" in k else SEC_HEADERS if "sec" in k else {})}
        try:
            r = requests.get(u, headers=h, timeout=25)
            return k, {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type", ""), "start": r.text[:400]}
        except Exception as e:
            return k, {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=16) as ex:
        return dict(ex.map(one, urls.items()))


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"lifespan": _cached_ep("lifespan", _lifespan_now), "causes": _cached_ep("causes", _causes_now), "glp1": _cached_ep("glp1", _glp1_now),
             "approvals": _cached_ep("approvals", _approvals_now, 600), "markets": _cached_ep("markets", _markets_now),
             "layout": _cached_ep("layout", _layout_now, 1800)}
