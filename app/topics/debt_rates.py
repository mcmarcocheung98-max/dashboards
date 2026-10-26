"""Global Debt & Rates (/debt-rates): which country hits fiscal stress first, and when interest overtakes defence or education.

debt      general government gross debt, % of GDP, US / UK / HK / China, actual and IMF projections (IMF WEO via the DataMapper API);
          US federal debt outstanding, daily (Treasury Fiscal Data, debt to the penny); UK public sector net debt % GDP (ONS HF6X, monthly)
interest  net interest, % of GDP and % of revenue (IMF WEO: primary balance minus overall balance, over revenue), actual and projected;
          US net interest against defence and education, rolling 12 months (Monthly Treasury Statement table 9, Fiscal Data API) and the
          average rate on marketable Treasury debt; UK central government debt interest over public sector receipts, rolling 12 months
          (ONS NMFX / ANBT); UK, HK and China interest vs defence vs education and the CBO projection (hand-entered, data/debt-rates/)
yields    10-year yields: US Treasury par and real (TIPS) curves (home.treasury.gov CSV, one file a year), UK nominal and real
          (Bank of England IADB), HK (HKMA Exchange Fund Note 10-year to 2015, then HKGB tender yields, hand-entered), China (hand-entered)
policy    Fed funds target range and EFFR (New York Fed API; hand-entered target before 2016), Bank Rate (BoE IUDBEDR), HKMA base rate
          (the HKMA formula on the Fed range and month-end HIBOR), PBoC 1-year LPR and 7-day reverse repo (hand-entered)
stress    10-year yield minus policy rate (a term-premium proxy), r - g and the debt-stabilising primary balance against the IMF's
          projected primary balance, and hand-entered auction and market-stress notes

Hand-entered (data/debt-rates/*.csv): spending (UK/HK/CN interest, defence, education), cbo (US projections), cn_10y, hk_10y, pboc,
fed_target (before the NY Fed API starts), stress_events. Every row cites a source; rows from memory say verify in the note.
"""
from __future__ import annotations

import json
import time
from io import StringIO

import numpy as np
import pandas as pd

from ._base import (DAY, HOUR, _part, _pts, _r, fetch, fetch_json, latest_date, manual, manual_rows, manual_sources, payload)
from . import Topic

SLUG = "debt-rates"
TOPIC = Topic(SLUG, "Global Debt & Rates",
              "Government debt, interest bills, 10-year yields and policy rates in the US, UK, Hong Kong and China: which hits fiscal stress first, "
              "and when interest overtakes defence or education.",
              "debt_rates", (("policy", "Interest rates & CPI"), ("odds", "FOMC history & odds"), ("debt", "Debt"), ("interest", "Interest cost"),
                             ("yields", "Yields"), ("qe", "Fed & Treasury buying"), ("stress", "Stress")),
              ("policy", "odds", "debt", "interest", "yields", "qe", "stress"), icon="chart", order=60)

TTL = DAY
COUNTRIES = {"USA": "US", "GBR": "UK", "HKG": "Hong Kong", "CHN": "China"}
IMF = "https://www.imf.org/external/datamapper/api/v1/{ind}"            # returns every country; the country filter is ignored
# WEO debt, growth, inflation; Fiscal Monitor (FM) balances and revenue, which the DataMapper carries under _G01_GDP_PT codes
IMF_IND = {"debt": "GGXWDG_NGDP", "balance": "GGXCNL_G01_GDP_PT", "primary": "GGXONLB_G01_GDP_PT", "revenue": "GGR_G01_GDP_PT",
           "growth": "NGDP_RPCH", "inflation": "PCPIPCH"}
# imf.org answers GitHub runners but refuses the Railway server (HTTP 403), so the page reads data/debt-rates/imf.csv, a copy of the
# DataMapper values (series "<ISO> <indicator>"), refreshed after each WEO; /layout keeps checking whether the server can reach imf.org.
FISCAL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
PENNY = FISCAL + "v2/accounting/od/debt_to_penny?fields=record_date,tot_pub_debt_out_amt,debt_held_public_amt&filter=record_date:gte:2000-01-01&page%5Bsize%5D=10000"
MTS9 = (FISCAL + "v1/accounting/mts/mts_table_9?fields=record_date,classification_desc,line_code_nbr,current_month_rcpt_outly_amt"
        "&filter=record_date:gte:2014-10-01&page%5Bsize%5D=10000")
AVG_RATE = (FISCAL + "v2/accounting/od/avg_interest_rates?fields=record_date,security_desc,avg_interest_rate_amt"
            "&filter=security_desc:eq:Total%20Marketable&page%5Bsize%5D=10000")
TSY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all"
       "?type={kind}&field_tdr_date_value={y}&page&_format=csv")
TSY_FROM = {"daily_treasury_yield_curve": 2000, "daily_treasury_real_yield_curve": 2003}
BOE = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/{y}&Dateto=now"
       "&SeriesCodes={code}&CSVF=TN&UsingCodes=Y&Filter=N&title={code}&VPD=Y")
BOE_CODES = {"bank_rate": ["IUDBEDR"], "uk10": ["IUDMNPY", "IUDMNZC"], "uk10_real": ["IUDMRZC", "IUDMRPY"]}   # first code that answers wins
ONS = "https://www.ons.gov.uk/generator?format=csv&uri=/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/{sid}/pusf"
ONS_SERIES = {"psnd": "hf6x", "interest": "nmfx", "receipts": "anbt"}
HKMA = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/{path}?pagesize=100&offset={offset}"
HK_EFBN, HK_HIBOR = "efbn/efbn-yield-endperiod", "er-ir/hk-interbank-ir-endperiod"
NYFED = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2000-01-01&endDate={end}"
# CPI, all items, year-on-year %: UK from ONS D7G7, Hong Kong from C&SD table 510-60001, China hand-entered, and the US from Treasury's
# TIPS reference CPI: by definition the reference CPI on the 1st of a month is the CPI-U (NSA) of the third month before, so the TIPS
# table on Fiscal Data carries BLS's index exactly (from February 2008). BLS itself refuses the Railway server (403, both its bulk files
# and, after the ai dashboard's 25 daily queries, its API).
TIPS_CPI = FISCAL + "v1/accounting/od/tips_cpi_data_detail?fields=index_date,ref_cpi&filter=cusip:eq:{cusip}&page%5Bsize%5D=10000"
TIPS_CUSIPS = ("912810FQ6", "912810FH6")         # TIPS maturing 2032 and 2029, both in the table since 2008
ONS_CPI = "https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/d7g7/mm23"
CSD_CPI = "https://www.censtatd.gov.hk/api/get.php?id=510-60001&lang=en&full_series=1"
# Polymarket: open markets on Fed rates and Treasury yields (Gamma API), and the price history of a market's Yes token (CLOB API)
POLY = "https://gamma-api.polymarket.com/events?tag_slug={tag}&closed=false&limit=50"
POLY_TAGS = ("fed-rates",)
POLY_MIN_VOLUME = 100_000          # side markets ("Hike flips No change by ...") trade a few thousand dollars; show the ones people bet on
POLY_HIST = "https://clob.polymarket.com/prices-history?market={token}&interval=max&fidelity=720"
# Kalshi (a CFTC-regulated exchange): series KXFED, one event per FOMC meeting, one market per strike: "upper bound above X%"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={series}&status=open&with_nested_markets=true&limit=8"
KALSHI_SERIES = ("KXFED",)
# Fed holdings (System Open Market Account, weekly, New York Fed), the Treasury's marketable debt by type (Monthly Statement of the
# Public Debt, table 1) and Treasury's own buybacks (since May 2024)
SOMA = "https://markets.newyorkfed.org/api/soma/summary.json"
MSPD = (FISCAL + "v1/debt/mspd/mspd_table_1?fields=record_date,security_type_desc,security_class_desc,total_mil_amt"
        "&filter=record_date:gte:2001-01-01,security_type_desc:in:(Marketable,Total%20Marketable)&page%5Bsize%5D=10000")
BUYBACKS = FISCAL + "v1/accounting/od/buybacks_operations?fields=operation_date,operation_type,security_type,maturity_bucket,total_par_amt_accepted&page%5Bsize%5D=2000"
FOMC_YEARS = 20                     # the FOMC history and its insights cover the last 20 years

SOURCES = [{"name": "IMF World Economic Outlook (DataMapper API): gross debt, overall and primary balance, revenue, growth, inflation", "url": "https://www.imf.org/external/datamapper/", "cadence": "April and October"},
           {"name": "US Treasury Fiscal Data: debt to the penny, Monthly Treasury Statement table 9, average interest rates", "url": "https://fiscaldata.treasury.gov/", "cadence": "daily / monthly"},
           {"name": "US Treasury par and real yield curves", "url": "https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics", "cadence": "daily"},
           {"name": "Federal funds target range and EFFR (Federal Reserve Bank of New York)", "url": "https://www.newyorkfed.org/markets/reference-rates/effr", "cadence": "daily"},
           {"name": "Bank Rate and gilt yield curves (Bank of England database)", "url": "https://www.bankofengland.co.uk/boeapps/database/", "cadence": "daily"},
           {"name": "Public sector finances: net debt, debt interest, receipts (ONS PUSF)", "url": "https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance", "cadence": "monthly"},
           {"name": "Exchange Fund Bills and Notes yields, HIBOR (HKMA open API)", "url": "https://apidocs.hkma.gov.hk/", "cadence": "monthly"},
           {"name": "CPI: US (CPI-U from Treasury's TIPS reference CPI, Fiscal Data), UK (ONS D7G7), Hong Kong (C&SD composite CPI)", "url": "https://fiscaldata.treasury.gov/datasets/tips-cpi-data/", "cadence": "monthly"},
           {"name": "Prediction-market odds (Polymarket Gamma and CLOB APIs; Kalshi trade API, series KXFED)", "url": "https://kalshi.com/markets/kxfed", "cadence": "hourly"},
           {"name": "Fed holdings of Treasuries and MBS (New York Fed SOMA summary)", "url": "https://www.newyorkfed.org/markets/soma-holdings", "cadence": "weekly"},
           {"name": "Marketable Treasury debt by type (Monthly Statement of the Public Debt) and Treasury buybacks (Fiscal Data)", "url": "https://fiscaldata.treasury.gov/datasets/monthly-statement-public-debt/", "cadence": "monthly / per operation"},
           {"name": "Hand-entered: HM Treasury PESA, OBR, CBO, HK Budget, China MoF, ChinaBond, PBoC, HKGB tenders (see data/debt-rates/README.md)", "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/debt-rates", "cadence": "as published"}]
NOTES = ("General government figures (IMF) are comparable across countries; national series (US federal, UK central government) are what each "
         "treasury reports. Net interest = primary balance minus overall balance. Projections are the IMF's latest WEO and, for the US, CBO. "
         "Contains public sector information licensed under the Open Government Licence v3.0.")


# ------------------------------------------------------------------ parsers (text in, so tests can feed fixtures)
def parse_imf(j: dict, ind: str) -> dict[str, pd.Series]:
    """DataMapper JSON {"values": {IND: {ISO: {"2001": v, ...}}}} -> {ISO: yearly Series dated 1 January} for COUNTRIES."""
    vals = ((j or {}).get("values") or {}).get(ind) or {}
    out = {}
    for iso in COUNTRIES:
        d = vals.get(iso) or {}
        s = pd.Series({pd.Timestamp(f"{y}-01-01"): pd.to_numeric(v, errors="coerce") for y, v in d.items() if str(y).isdigit()}, dtype=float)
        if len(s.dropna()):
            out[iso] = s.dropna().sort_index()
    if not out:
        raise ValueError(f"IMF {ind}: no values for {', '.join(COUNTRIES)}")
    return out


def parse_fiscal(j: dict) -> pd.DataFrame:
    d = pd.DataFrame((j or {}).get("data") or [])
    if d.empty:
        raise ValueError("Fiscal Data: no rows")
    d["record_date"] = pd.to_datetime(d["record_date"], errors="coerce")
    return d[d["record_date"].notna()]


MTS_LINES = {"interest": "net interest", "defence": "national defense", "education": "education, training"}


def parse_mts9(j: dict) -> pd.DataFrame:
    """MTS table 9 rows -> monthly frame ($bn): receipts, outlays, interest, defence, education. The two 'Total' lines are told apart by
    position: the one before the 'Net Outlays' heading is receipts."""
    d = parse_fiscal(j)
    d["amt"] = pd.to_numeric(d["current_month_rcpt_outly_amt"], errors="coerce") / 1e9
    d["line"] = pd.to_numeric(d["line_code_nbr"], errors="coerce")
    d["desc"] = d["classification_desc"].astype(str).str.strip().str.lower()
    rows = {}
    for t, g in d.groupby("record_date"):
        r = {}
        head = g.loc[g["desc"].str.startswith("net outlays"), "line"]
        cut = head.iloc[0] if len(head) else None
        for _, x in g[g["desc"] == "total"].iterrows():
            r["receipts" if cut is not None and x["line"] < cut else "outlays"] = x["amt"]
        for k, needle in MTS_LINES.items():
            m = g[g["desc"].str.startswith(needle)]
            if len(m):
                r[k] = m["amt"].iloc[0]
        rows[t.to_period("M").to_timestamp()] = r
    out = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    if out.empty or "interest" not in out:
        raise ValueError("MTS table 9 layout changed: no Net Interest line")
    return out.reindex(pd.date_range(out.index.min(), out.index.max(), freq="MS"))


def parse_treasury_csv(text: str) -> dict[str, pd.Series]:
    """Treasury daily yield-curve CSV ('Date,1 Mo,...,10 Yr,...' or the real curve 'Date,5 YR,...,10 YR,...') -> {'10y': ..., '2y': ...}."""
    d = pd.read_csv(StringIO(text))
    d.columns = [str(c).strip() for c in d.columns]
    t = pd.to_datetime(d[d.columns[0]], format="%m/%d/%Y", errors="coerce")
    out = {}
    for key, names in (("10y", ("10 yr", "10 year")), ("2y", ("2 yr", "2 year"))):
        col = next((c for c in d.columns if c.lower() in names), None)
        if col:
            s = pd.Series(pd.to_numeric(d[col], errors="coerce").to_numpy(), index=t)
            out[key] = s[s.index.notna()].dropna().sort_index()
    if not out.get("10y", pd.Series(dtype=float)).size:
        raise ValueError("Treasury CSV layout changed: no 10-year column")
    return out


def parse_boe(text: str) -> pd.Series:
    """IADB CSV ('DATE,CODE' rows like '02 Jan 2024,5.25') -> Series. An HTML error page (bad code) raises."""
    if text.lstrip().startswith("<"):
        raise ValueError("BoE IADB returned a web page, not CSV (series code refused?)")
    d = pd.read_csv(StringIO(text))
    d.columns = [str(c).strip() for c in d.columns]
    date = next((c for c in d.columns if c.lower().startswith("date")), d.columns[0])
    val = [c for c in d.columns if c != date][0]
    s = pd.Series(pd.to_numeric(d[val], errors="coerce").to_numpy(), index=pd.to_datetime(d[date], format="%d %b %Y", errors="coerce"))
    s = s[s.index.notna()].sort_index().dropna()
    if s.empty:
        raise ValueError("BoE IADB: no values")
    return s


def parse_ons(text: str) -> pd.Series:
    """ONS website CSV ('"1997 JAN","12.3"' rows after metadata) -> monthly Series; quarterly or yearly rows when there are no months."""
    import re
    m = re.findall(r'^"(\d{4} [A-Z]{3})","(-?[\d.]+)"', text, flags=re.M)
    if m:
        s = pd.Series({pd.to_datetime(d, format="%Y %b"): float(v) for d, v in m})
    else:
        q = re.findall(r'^"(\d{4}) Q([1-4])","(-?[\d.]+)"', text, flags=re.M)
        s = pd.Series({pd.Timestamp(year=int(y), month=3 * int(k) - 2, day=1): float(v) for y, k, v in q})
    if s.empty:
        raise ValueError("ONS CSV layout changed: no monthly or quarterly rows")
    return s.sort_index()


def parse_hkma(pages: list[dict], field: str) -> pd.Series:
    rows = [r for p in pages for r in (((p or {}).get("result") or {}).get("records") or [])]
    s = pd.Series({pd.to_datetime(r.get("end_of_month"), format="%Y-%m", errors="coerce"): pd.to_numeric(r.get(field), errors="coerce") for r in rows}, dtype=float)
    return s[s.index.notna()].dropna().sort_index()


def parse_nyfed(j: dict) -> pd.DataFrame:
    rows = (j or {}).get("refRates") or []
    d = pd.DataFrame([{"t": r.get("effectiveDate"), "effr": r.get("percentRate"), "lo": r.get("targetRateFrom"), "hi": r.get("targetRateTo")} for r in rows])
    if d.empty:
        raise ValueError("NY Fed: no EFFR rows")
    d["t"] = pd.to_datetime(d["t"], errors="coerce")
    d = d[d["t"].notna()].set_index("t").sort_index().apply(pd.to_numeric, errors="coerce")
    return d[~d.index.duplicated(keep="last")]


def parse_tips_cpi(j: dict) -> pd.Series:
    """Fiscal Data TIPS reference CPI (daily, one CUSIP) -> monthly CPI-U, NSA. The value on the 1st of month M is CPI-U for M-3. Within
    a month the reference CPI moves in a straight line to the next month's, so the last day published also gives CPI-U for M-2:
    CPI(M-2) = r1 + (r_d - r1) x days_in_month / (d - 1)."""
    rows = (j or {}).get("data") or []
    if not rows:
        raise ValueError("TIPS reference CPI: no rows")
    r = pd.Series({pd.to_datetime(x.get("index_date"), errors="coerce"): pd.to_numeric(x.get("ref_cpi"), errors="coerce") for x in rows}, dtype=float)
    r = r[r.index.notna()].dropna().sort_index()
    r = r[~r.index.duplicated(keep="last")]
    first = r[r.index.day == 1]
    if len(first) < 15:
        raise ValueError(f"TIPS reference CPI: {len(first)} month starts")
    out = pd.Series({t - pd.DateOffset(months=3): v for t, v in first.items()})
    m0 = first.index[-1]
    tail = r[(r.index > m0) & (r.index.to_period("M") == m0.to_period("M"))]
    if len(tail):
        t, v = tail.index[-1], tail.iloc[-1]
        out[m0 - pd.DateOffset(months=2)] = first.iloc[-1] + (v - first.iloc[-1]) * m0.days_in_month / (t.day - 1)
    return out.sort_index()


def parse_csd_cpi(j: dict) -> pd.Series:
    """C&SD web table JSON (dataSet: freq, period YYYYMM, sv, svDesc, figure) -> monthly year-on-year % of the composite CPI
    (series codes starting A_CM; the first year-on-year series otherwise)."""
    rows = [r for r in ((j or {}).get("dataSet") or []) if r.get("freq") == "M" and "year-on-year" in str(r.get("svDesc", "")).lower()]
    if not rows:
        raise ValueError("C&SD 510-60001: no monthly year-on-year rows")
    svs = sorted({r.get("sv") for r in rows}, key=lambda v: (not str(v).startswith("A_CM"), str(v)))
    rows = [r for r in rows if r.get("sv") == svs[0]]
    s = pd.Series({pd.to_datetime(str(r["period"]), format="%Y%m", errors="coerce"): pd.to_numeric(r.get("figure"), errors="coerce") for r in rows})
    return s[s.index.notna()].dropna().sort_index()


def _jlist(v) -> list:
    """Gamma API fields such as outcomes and outcomePrices are JSON arrays sent as strings."""
    if isinstance(v, list):
        return v
    try:
        return json.loads(v or "[]")
    except (TypeError, ValueError):
        return []


def parse_poly(events: list) -> list[dict]:
    """Gamma API events -> [{title, slug, end, volume, markets: [{label, yes, volume, token}]}], open markets only, by end date."""
    out = []
    for e in events or []:
        ms = []
        for m in e.get("markets") or []:
            if m.get("closed") or m.get("active") is False:
                continue
            outs, prices, toks = _jlist(m.get("outcomes")), _jlist(m.get("outcomePrices")), _jlist(m.get("clobTokenIds"))
            if not outs or len(prices) != len(outs):
                continue
            i = next((k for k, o in enumerate(outs) if str(o).lower() == "yes"), 0)
            yes = pd.to_numeric(prices[i], errors="coerce")
            if pd.isna(yes):
                continue
            ms.append({"label": m.get("groupItemTitle") or m.get("question") or "", "question": m.get("question") or "", "yes": round(float(yes), 4),
                       "volume": _r(m.get("volume"), 0), "token": toks[i] if i < len(toks) else None})
        if ms:
            out.append({"title": e.get("title") or "", "slug": e.get("slug") or "", "end": str(e.get("endDate") or "")[:10],
                        "volume": _r(e.get("volume"), 0), "markets": ms})
    return sorted(out, key=lambda e: (e["end"] or "9999", e["title"]))


def parse_poly_history(j: dict) -> pd.Series:
    h = (j or {}).get("history") or []
    s = pd.Series({pd.Timestamp(int(x["t"]), unit="s").normalize(): float(x["p"]) for x in h if "t" in x and "p" in x})
    return s[~s.index.duplicated(keep="last")].sort_index()


# ------------------------------------------------------------------ data
def imf_live(key: str) -> dict[str, pd.Series]:
    ind = IMF_IND[key]
    return parse_imf(fetch_json(IMF.format(ind=ind), TTL, timeout=60, min_bytes=1000), ind)


def imf(key: str) -> dict[str, pd.Series]:
    """The committed copy of the IMF DataMapper values (see IMF above): {ISO: yearly Series}."""
    ind = IMF_IND[key]
    out = {k.split(" ", 1)[0]: v for k, v in hand("imf").items() if k.endswith(" " + ind) and len(v)}
    if not out:
        raise ValueError(f"data/debt-rates/imf.csv has no {ind} rows")
    return {iso: out[iso] for iso in COUNTRIES if iso in out}


def imf_interest() -> dict[str, pd.Series]:
    """Net interest, % of GDP = primary balance - overall balance (both % of GDP; a deficit is negative)."""
    p, b = imf("primary"), imf("balance")
    return {iso: (p[iso] - b[iso]).dropna() for iso in p if iso in b and len((p[iso] - b[iso]).dropna())}


def imf_interest_revenue() -> dict[str, pd.Series]:
    i, r = imf_interest(), imf("revenue")
    return {iso: (i[iso] / r[iso] * 100).replace([np.inf, -np.inf], np.nan).dropna() for iso in i if iso in r}


def penny() -> pd.DataFrame:
    d = parse_fiscal(fetch_json(PENNY, TTL, timeout=90, min_bytes=1000)).set_index("record_date").sort_index()
    return d[["tot_pub_debt_out_amt", "debt_held_public_amt"]].apply(pd.to_numeric, errors="coerce") / 1e12


def mts() -> pd.DataFrame:
    return parse_mts9(fetch_json(MTS9, TTL, timeout=90, min_bytes=1000))


def avg_rate() -> pd.Series:
    d = parse_fiscal(fetch_json(AVG_RATE, TTL, timeout=60, min_bytes=500))
    s = pd.Series(pd.to_numeric(d["avg_interest_rate_amt"], errors="coerce").to_numpy(), index=d["record_date"].to_numpy())
    return s.dropna().sort_index()


def treasury(kind: str) -> dict[str, pd.Series]:
    """Every year's CSV from TSY_FROM to this year; past years change rarely, so they are kept a month."""
    from concurrent.futures import ThreadPoolExecutor
    now = pd.Timestamp.now().year

    def one(y):
        try:
            return parse_treasury_csv(fetch(TSY.format(y=y, kind=kind), TTL if y >= now - 1 else 30 * DAY, timeout=45, min_bytes=100))
        except Exception:
            return {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        parts = list(ex.map(one, range(TSY_FROM[kind], now + 1)))
    out = {}
    for k in ("10y", "2y"):
        ss = [p[k] for p in parts if k in p and len(p[k])]
        if ss:
            s = pd.concat(ss).sort_index()
            out[k] = s[~s.index.duplicated(keep="last")]
    if "10y" not in out:
        raise ValueError(f"Treasury {kind}: no year could be read")
    return out


def boe(key: str, since: int = 1995) -> pd.Series:
    last = None
    for code in BOE_CODES[key]:
        try:
            return parse_boe(fetch(BOE.format(y=since, code=code), TTL, min_bytes=100))
        except Exception as e:
            last = e
    raise last


def ons(key: str) -> pd.Series:
    return parse_ons(fetch(ONS.format(sid=ONS_SERIES[key]), TTL, min_bytes=200))


def hkma(path: str, field: str) -> pd.Series:
    pages = []
    for k in range(8):
        j = fetch_json(HKMA.format(path=path, offset=k * 100), TTL, min_bytes=50)
        pages.append(j)
        if len(((j or {}).get("result") or {}).get("records") or []) < 100:
            break
    s = parse_hkma(pages, field)
    if s.empty:
        raise ValueError(f"HKMA {path}: no {field} values")
    return s


def nyfed() -> pd.DataFrame:
    return parse_nyfed(fetch_json(NYFED.format(end=pd.Timestamp.now().strftime("%Y-%m-%d")), TTL, timeout=90, min_bytes=500))


def cpi() -> tuple[dict[str, pd.Series], dict[str, str]]:
    """CPI year-on-year % by country, monthly (China yearly, hand-entered), and why any is missing."""
    out, why = {}, {}

    def us():
        last = None
        for c in TIPS_CUSIPS:
            try:
                idx = parse_tips_cpi(fetch_json(TIPS_CPI.format(cusip=c), TTL, min_bytes=1000, timeout=90))
                break
            except Exception as e:
                last = e
        else:
            raise last
        idx = idx.reindex(pd.date_range(idx.index[0], idx.index[-1], freq="MS"))
        return (idx / idx.shift(12) * 100 - 100).dropna()
    for name, fn in (("US", us), ("UK", lambda: parse_ons(fetch(ONS_CPI, TTL, min_bytes=200))),
                     ("Hong Kong", lambda: parse_csd_cpi(fetch_json(CSD_CPI, TTL, min_bytes=500, timeout=60))),
                     ("China", lambda: hand("cn_cpi").get("value", pd.Series(dtype=float)))):
        try:
            s = fn()
            if len(s):
                out[name] = s
        except Exception as e:
            why[name] = f"{type(e).__name__}: {str(e)[:100]}"
    return out, why


def poly_events(min_volume: float = POLY_MIN_VOLUME) -> list[dict]:
    """Open events from POLY_TAGS with at least `min_volume` dollars traded, the most traded first."""
    seen, out = set(), []
    for tag in POLY_TAGS:
        for e in parse_poly(fetch_json(POLY.format(tag=tag), HOUR, min_bytes=20, timeout=30)):
            if e["slug"] not in seen and (e["volume"] or 0) >= min_volume:
                seen.add(e["slug"])
                out.append(e)
    return sorted(out, key=lambda e: -(e["volume"] or 0))


def next_decision(events: list[dict]) -> dict | None:
    """The Fed-decision event that closes first (the next meeting), e.g. 'Fed Decision in October?'."""
    ds = [e for e in events if "fed decision" in e["title"].lower()]
    return min(ds, key=lambda e: e["end"] or "9999") if ds else None


def poly_history(token: str) -> pd.Series:
    return parse_poly_history(fetch_json(POLY_HIST.format(token=token), HOUR, min_bytes=10, timeout=30))


def fomc_decisions(r: pd.DataFrame | None = None) -> list[dict]:
    """Every change in the Fed's target (the top of the range from December 2008), newest first: {date, from, to, bp}. Dates are the
    day the new rate took effect (the day after the meeting, or the day of an unscheduled cut)."""
    r = fed_range() if r is None else r
    hi = r["hi"].dropna()
    hi = hi[~hi.index.duplicated(keep="last")].sort_index()
    ch = hi.diff()
    out = [{"date": str(t.date()), "from": _r(hi.shift(1)[t], 2), "to": _r(v, 2), "bp": int(round(ch[t] * 100))} for t, v in hi[ch.abs() > 0.001].items()]
    return list(reversed(out))


def parse_kalshi(j: dict) -> list[dict]:
    """Kalshi KXFED events -> [{title, ticker, close, volume, levels: [{label, upper, p}]}]. Each market pays if the upper bound is above
    its strike, so P(upper = X) = P(above X - 0.25) - P(above X); prices are last trades (the bid/ask mid when nothing traded)."""
    out = []
    for e in (j or {}).get("events") or []:
        above = {}
        vol = 0.0
        close = None
        for m in e.get("markets") or []:
            k = pd.to_numeric(m.get("floor_strike"), errors="coerce")
            if pd.isna(k) or m.get("strike_type") not in (None, "greater"):
                continue
            last = pd.to_numeric(m.get("last_price_dollars"), errors="coerce")
            bid, ask = pd.to_numeric(m.get("yes_bid_dollars"), errors="coerce"), pd.to_numeric(m.get("yes_ask_dollars"), errors="coerce")
            # a live quote beats a stale last trade on thinly traded strikes
            p = (bid + ask) / 2 if pd.notna(bid) and pd.notna(ask) and 0 < bid <= ask else last if pd.notna(last) and last > 0 else None
            if p is None or pd.isna(p):
                continue
            above[round(float(k), 2)] = float(p)
            vol += float(pd.to_numeric(m.get("volume_fp"), errors="coerce") or 0)
            close = close or str(m.get("close_time") or "")[:10]
        if len(above) < 2:
            continue
        ks = sorted(above)
        for a, b in zip(ks, ks[1:]):              # P(above k) cannot rise with k: clamp stale prices so no level gets a negative chance
            above[b] = min(above[b], above[a])
        probs = [{"upper": ks[0], "label": f"{ks[0]:.2f}% or lower", "p": 1 - above[ks[0]]}]
        for lo, hi in zip(ks, ks[1:]):
            probs.append({"upper": hi, "label": f"{hi:.2f}%", "p": above[lo] - above[hi]})
        probs.append({"upper": ks[-1] + 0.25, "label": f"above {ks[-1]:.2f}%", "p": above[ks[-1]]})
        total = sum(max(0.0, x["p"]) for x in probs) or 1.0       # last trades need not add up to exactly 1: rescale
        for x in probs:
            x["p"] = round(max(0.0, x["p"]) / total, 4)
        out.append({"title": e.get("title") or "", "ticker": e.get("event_ticker") or "", "close": close, "volume": round(vol), "levels": probs})
    return sorted(out, key=lambda e: e["close"] or "9999")


def kalshi_events() -> list[dict]:
    out = []
    for s in KALSHI_SERIES:
        out += parse_kalshi(fetch_json(KALSHI.format(series=s), HOUR, min_bytes=20, timeout=30))
    return out


def parse_soma(j: dict) -> pd.DataFrame:
    """NY Fed SOMA summary -> weekly frame ($tn): treasuries (bills + notes/bonds + TIPS + FRN), bills, notesbonds, mbs, total."""
    rows = ((j or {}).get("soma") or {}).get("summary") or []
    d = pd.DataFrame(rows)
    if d.empty or "asOfDate" not in d:
        raise ValueError("SOMA summary: no rows")
    d.index = pd.to_datetime(d.pop("asOfDate"), errors="coerce")
    d = d[d.index.notna()].apply(pd.to_numeric, errors="coerce").fillna(0) / 1e12
    out = pd.DataFrame({"bills": d.get("bills", 0), "notesbonds": d.get("notesbonds", 0), "mbs": d.get("mbs", 0) + d.get("cmbs", 0),
                        "tips": d.get("tips", 0), "frn": d.get("frn", 0), "total": d.get("total", 0)})
    out["treasuries"] = out[["bills", "notesbonds", "tips", "frn"]].sum(axis=1)
    return out.sort_index()


def parse_mspd(j: dict) -> pd.DataFrame:
    """MSPD table 1 -> monthly frame ($tn): bills, notes, bonds, tips, frn, marketable (total marketable)."""
    d = parse_fiscal(j)
    d["v"] = pd.to_numeric(d["total_mil_amt"], errors="coerce") / 1e6
    name = d["security_class_desc"].str.lower()
    key = pd.Series(None, index=d.index, dtype=object)
    for k, needle in (("bills", "bills"), ("notes", "notes"), ("bonds", "bonds"), ("tips", "inflation"), ("frn", "floating")):
        key[name.str.startswith(needle) & key.isna() & (d["security_type_desc"] == "Marketable")] = k
    key[d["security_type_desc"] == "Total Marketable"] = "marketable"
    d["k"] = key
    out = d.dropna(subset=["k"]).pivot_table(index="record_date", columns="k", values="v", aggfunc="sum").sort_index()
    if "bills" not in out or "marketable" not in out:
        raise ValueError("MSPD layout changed: no bills or total marketable")
    out.index = out.index.to_period("M").to_timestamp()
    return out


def parse_buybacks(j: dict) -> pd.DataFrame:
    rows = (j or {}).get("data") or []
    d = pd.DataFrame(rows)
    if d.empty:
        raise ValueError("Treasury buybacks: no rows")
    d["t"] = pd.to_datetime(d["operation_date"], errors="coerce")
    # the 2000-02 buybacks (retiring debt out of surpluses) carry no operation type
    d["operation_type"] = d["operation_type"].where(~d["operation_type"].isin([None, "null", ""]) & d["operation_type"].notna(),
                                                    d["t"].dt.year.map(lambda y: "Debt reduction (2000-02)" if y < 2003 else "Other"))
    d["amt"] = pd.to_numeric(d["total_par_amt_accepted"], errors="coerce") / 1e9
    return d[d["t"].notna()].sort_values("t")


def soma() -> pd.DataFrame:
    return parse_soma(fetch_json(SOMA, TTL, min_bytes=1000, timeout=60))


def mspd() -> pd.DataFrame:
    return parse_mspd(fetch_json(MSPD, TTL, min_bytes=1000, timeout=90))


def buybacks() -> pd.DataFrame:
    return parse_buybacks(fetch_json(BUYBACKS, TTL, min_bytes=200, timeout=60))


def hand(name: str) -> dict[str, pd.Series]:
    m = manual(SLUG, name)
    return m if isinstance(m, dict) else ({"value": m} if len(m) else {})


def month_end(s: pd.Series) -> pd.Series:
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    return s.resample("MS").last().dropna()


def steps(s: pd.Series, end: pd.Timestamp | None = None) -> pd.Series:
    """A rate that changes on given days -> its value at each month start (carried forward to `end`, default this month)."""
    s = s.dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    end = end or pd.Timestamp.now().normalize().replace(day=1)
    idx = pd.date_range(s.index[0].normalize().replace(day=1), end, freq="MS")
    return s.reindex(s.index.union(idx)).ffill().reindex(idx).dropna()


# ------------------------------------------------------------------ helpers for payloads
def _split(s: pd.Series, d: int = 2) -> dict:
    """Yearly IMF series -> {"actual": pts, "proj": pts}; this calendar year onwards is projection, and proj starts at the last actual so
    the dashed line joins the solid one."""
    cut = pd.Timestamp(f"{pd.Timestamp.now().year}-01-01")
    a, p = s[s.index < cut], s[s.index >= cut]
    if len(a) and len(p):
        p = pd.concat([a.iloc[-1:], p])
    return {"actual": _pts(a, d), "proj": _pts(p, d)}


def _by_country(fn, d: int = 2) -> dict:
    return {COUNTRIES[iso]: _split(s, d) for iso, s in fn().items()}


def _at(s: pd.Series, year: int):
    v = s[s.index.year == year]
    return _r(v.iloc[-1], 2) if len(v) else None


def first_above(a: pd.Series, b: pd.Series):
    """First date a > b and stays above for the rest of the shared history (None if never, 'always' if from the start)."""
    j = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
    if j.empty:
        return None
    above = j["a"] > j["b"]
    if not above.iloc[-1]:
        return None
    below = above[~above]
    if below.empty:
        return "always"
    return str(above[above.index > below.index[-1]].index[0].date())


# ------------------------------------------------------------------ endpoints
def _debt_now() -> dict:
    yr = pd.Timestamp.now().year
    out = payload({"imf": lambda: _by_country(lambda: imf("debt"), 1),
                   "us_total": lambda: _pts(month_end(penny()["tot_pub_debt_out_amt"]), 3),
                   "us_public": lambda: _pts(month_end(penny()["debt_held_public_amt"]), 3),
                   "uk_psnd": lambda: _pts(ons("psnd"), 1), "maturity": maturity_mix},
                  sources=[PENNY, ONS.format(sid="hf6x"), MSPD])
    out["maturity_avg"] = manual_rows(SLUG, "maturity")
    try:
        d = imf("debt")
        out["table"] = [{"country": COUNTRIES[iso], "y2007": _at(s, 2007), "y2019": _at(s, 2019), "now": _at(s, yr - 1), "proj5": _at(s, yr + 4),
                         "change10": _r(_at(s, yr - 1) - _at(s, yr - 11), 1) if _at(s, yr - 1) is not None and _at(s, yr - 11) is not None else None}
                        for iso, s in d.items()]
        out["years"] = {"now": yr - 1, "proj5": yr + 4}
    except Exception as e:
        out["table"], out["table_error"] = [], type(e).__name__
    out["imf_cites"] = [c for c in manual_sources(SLUG, "imf")]
    p = out.get("us_total") or []
    out["as_of"] = str(pd.Timestamp(p[-1][0], unit="s").date()) if p else None
    try:
        raw = penny()["tot_pub_debt_out_amt"].dropna()
        yago = raw[raw.index <= raw.index[-1] - pd.DateOffset(years=1)]
        out["us_now"] = {"total": _r(raw.iloc[-1], 3), "date": str(raw.index[-1].date()),
                         "per_day_bn": _r((raw.iloc[-1] - yago.iloc[-1]) / ((raw.index[-1] - yago.index[-1]).days) * 1000, 1) if len(yago) else None}
    except Exception:
        out["us_now"] = {}
    return out


def _us_spending() -> dict:
    m = mts()
    roll = m.rolling(12, min_periods=12).sum().dropna(how="all")
    fy = m[m.index.month == 9].index    # September closes the US fiscal year
    annual = m.rolling(12, min_periods=12).sum().loc[fy].dropna(how="all")
    pts = {k: _pts(roll[k], 1) for k in ("interest", "defence", "education") if k in roll}
    share = (roll["interest"] / roll["receipts"] * 100) if "receipts" in roll else pd.Series(dtype=float)
    cross = {k: first_above(annual["interest"], annual[k]) for k in ("defence", "education") if k in annual}
    return {"rolling": pts, "share": _pts(share, 2), "annual": [{"fy": int(t.year), **{k: _r(annual.loc[t, k], 1) for k in annual.columns}} for t in annual.index],
            "cross": {k: (v if v in (None, "always") else int(v[:4])) for k, v in cross.items()}, "month": str(m.dropna(how="all").index[-1].date())}


def _uk_share() -> list:
    i, r = ons("interest"), ons("receipts")
    j = pd.concat([i, r], axis=1, keys=["i", "r"]).dropna()
    j = j.reindex(pd.date_range(j.index.min(), j.index.max(), freq="MS"))
    s = (j["i"].rolling(12, min_periods=12).sum() / j["r"].rolling(12, min_periods=12).sum() * 100).dropna()
    return _pts(s, 2)


def _hand_spending() -> dict:
    """data/debt-rates/spending.csv: date,series,value,... with series '<country> <item>' (UK interest, UK defence, ...), in each currency's
    billions per fiscal year."""
    out = {}
    for k, s in hand("spending").items():
        country, _, item = k.partition(" ")
        out.setdefault(country, {})[item] = _pts(s, 1)
    return out


def _interest_now() -> dict:
    out = payload({"imf_gdp": lambda: _by_country(imf_interest), "imf_revenue": lambda: _by_country(imf_interest_revenue, 1),
                   "us": _us_spending, "us_avg_rate": lambda: _pts(avg_rate(), 3), "uk_share": _uk_share,
                   "hand": _hand_spending, "cbo": lambda: {k: _pts(v, 2) for k, v in hand("cbo").items()}},
                  sources=[MTS9, AVG_RATE, ONS.format(sid="nmfx"), ONS.format(sid="anbt")])
    out["cites"] = {n: manual_sources(SLUG, n) for n in ("spending", "cbo", "imf")}
    out["rows"] = {n: manual_rows(SLUG, n) for n in ("spending", "cbo")}
    out["as_of"] = (out.get("us") or {}).get("month")
    return out


def hk10() -> pd.Series:
    """data/debt-rates/hk_10y.csv: the EFN 10-year to 2015 (copied from the HKMA API, which refuses the Railway server), then HKGB
    10-year yields."""
    s = hand("hk_10y").get("value", pd.Series(dtype=float))
    if s.empty:
        raise ValueError("data/debt-rates/hk_10y.csv is empty")
    return s


def yields10_why() -> tuple[dict[str, pd.Series], dict[str, str]]:
    """Nominal 10-year yields, month-end, by country, and why any is missing (a source that fails is left out)."""
    out, why = {}, {}
    for name, fn in (("US", lambda: treasury("daily_treasury_yield_curve")["10y"]), ("UK", lambda: boe("uk10", 2000)), ("Hong Kong", hk10),
                     ("China", lambda: hand("cn_10y").get("value", pd.Series(dtype=float)))):
        try:
            s = fn()
            if len(s):
                out[name] = month_end(s) if name in ("US", "UK") else s
        except Exception as e:
            why[name] = type(e).__name__
    return out, why


def yields10() -> dict[str, pd.Series]:
    return yields10_why()[0]


def _yields_now() -> dict:
    missing: dict = {}

    def nominal():
        y, why = yields10_why()
        missing.update(why)
        return {k: _pts(v, 3) for k, v in y.items()}
    out = payload({"nominal": nominal,
                   "real": lambda: {k: _pts(v, 3) for k, v in (("US 10-year TIPS", month_end(treasury("daily_treasury_real_yield_curve")["10y"])),
                                                              ("UK 10-year index-linked", month_end(boe("uk10_real", 2000))))},
                   "us2": lambda: _pts(month_end(treasury("daily_treasury_yield_curve").get("2y", pd.Series(dtype=float))), 3)},
                  sources=[TSY.format(y=pd.Timestamp.now().year, kind="daily_treasury_yield_curve"), BOE.format(y=2000, code=BOE_CODES["uk10"][0])])
    out["missing"] = missing
    out["cites"] = {n: manual_sources(SLUG, n) for n in ("cn_10y", "hk_10y")}
    nom = out.get("nominal") or {}
    out["now"] = {k: {"v": p[-1][1], "t": str(pd.Timestamp(p[-1][0], unit="s").date())} for k, p in nom.items() if p}
    out["as_of"] = max((v["t"] for v in out["now"].values()), default=None)
    return out


def fed_range() -> pd.DataFrame:
    """Daily target range from the NY Fed (2016 on) after the hand-entered target changes before it (lower = upper - 0.25 from
    December 2008; a single target before that)."""
    h = hand("fed_target").get("value", pd.Series(dtype=float))
    try:
        n = nyfed()
        n["hi"] = n["hi"].fillna(n["lo"])          # a single target (before December 2008) can come as targetRateFrom alone
    except Exception:
        n = pd.DataFrame(columns=["effr", "lo", "hi"], dtype=float)
    if len(h):
        lo = h.where(h.index < "2008-12-16", h - 0.25)
        pre = pd.DataFrame({"hi": h, "lo": lo})
        api = n["hi"].dropna() if "hi" in n else pd.Series(dtype=float)
        if len(api):
            pre = pre[pre.index < api.index[0]]
        n = pd.concat([pre, n]).sort_index()
        n = n[~n.index.duplicated(keep="last")]
    if n.empty:
        raise ValueError("no Fed target: NY Fed unreachable and data/debt-rates/fed_target.csv empty")
    return n


def hk_base(hibor: pd.Series | None = None) -> pd.Series:
    """HKMA base rate from its formula (March 2009 on): the higher of the Fed range's lower end + 0.5 and the average of overnight and
    1-month HIBOR. The HKMA API refuses the Railway server, so the page uses the Fed term alone, which has set the base rate since 2009;
    `hibor` (monthly average of the two HIBORs) adds the other term where it is available."""
    f = steps(fed_range()["lo"])
    base = f[f.index >= "2009-04-01"] + 0.5
    if hibor is not None and len(hibor):
        base = pd.concat([base, hibor.reindex(base.index)], axis=1).max(axis=1)
    return base


def _policy_now() -> dict:
    def fed():
        r = fed_range()
        return {"upper": _pts(steps(r["hi"]), 2), "lower": _pts(steps(r["lo"]), 2), "effr": _pts(month_end(r["effr"]) if "effr" in r else pd.Series(dtype=float), 2)}
    pb = hand("pboc")
    why: dict = {}

    def infl():
        c, w = cpi()
        why.update(w)
        return {k: _pts(v, 2) for k, v in c.items()}

    def real():
        """Policy rate minus CPI inflation, monthly: below zero, money is cheap after inflation."""
        c, _ = cpi()
        pol = {"US": lambda: steps(fed_range()["hi"]), "UK": lambda: steps(boe("bank_rate")), "Hong Kong": hk_base,
               "China": lambda: steps(pb.get("7-day reverse repo", pd.Series(dtype=float)))}
        out = {}
        for k, s in c.items():
            try:
                p = pol[k]()
                s = s if k != "China" else s.resample("MS").last().dropna()
                out[k] = _pts((p.reindex(s.index, method="ffill") - s).dropna(), 2)
            except Exception:
                continue
        return out
    out = payload({"fed": fed, "boe": lambda: _pts(steps(boe("bank_rate")), 2), "hk": lambda: _pts(hk_base(), 2),
                   "pboc": lambda: {k: _pts(steps(v), 2) for k, v in pb.items()}, "cpi": infl, "real": real,
                   "decisions": lambda: fomc_decisions()[:40]},
                  sources=[NYFED.format(end=pd.Timestamp.now().strftime("%Y-%m-%d")), BOE.format(y=1995, code="IUDBEDR"), TIPS_CPI.format(cusip=TIPS_CUSIPS[0]), ONS_CPI, CSD_CPI])
    out["cpi_missing"] = why
    c = out.get("cpi") or {}
    out["cpi_now"] = {k: {"v": p[-1][1], "t": str(pd.Timestamp(p[-1][0], unit="s").date())[:7]} for k, p in c.items() if p}
    last = lambda p: p[-1][1] if p else None
    out["now"] = {"Fed (upper)": last((out.get("fed") or {}).get("upper")), "Bank of England": last(out.get("boe")), "HKMA base rate": last(out.get("hk")),
                  "PBoC 7-day reverse repo": last((out.get("pboc") or {}).get("7-day reverse repo"))}
    out["cites"] = {n: manual_sources(SLUG, n) for n in ("pboc", "fed_target", "cn_cpi")}
    out["as_of"] = str(pd.Timestamp.now().date())
    return out


def next_meetings(now: pd.Timestamp | None = None) -> list[dict]:
    """data/debt-rates/fomc.csv (date = the decision day, the second day of the meeting): meetings from today on."""
    now = (now or pd.Timestamp.now()).normalize()
    rows = sorted(manual_rows(SLUG, "fomc"), key=lambda r: r["date"])
    return [r for r in rows if pd.Timestamp(r["date"]) >= now]


def _odds_now() -> dict:
    """Next FOMC meetings, recent decisions, and Polymarket odds on Fed rates and Treasury yields; the price history of the markets in
    the next decision's event (one line per outcome that has a 2%+ chance now)."""
    def history():
        ev = next_decision(poly_events())
        if not ev:
            return {}
        out = {}
        for m in sorted(ev["markets"], key=lambda m: -m["yes"])[:5]:
            if m["token"] and m["yes"] >= 0.02:
                s = poly_history(m["token"])
                if len(s):
                    out[m["label"]] = _pts(s * 100, 1)
        return {"title": ev["title"], "lines": out}
    def fomc():
        h = fomc_history()
        c = fomc_cycles(h)
        return {"decisions": list(reversed(h)), "cycles": list(reversed(c)), "insights": fomc_insights(h, c), "since": h[0]["date"] if h else None}
    out = payload({"events": lambda: poly_events()[:10], "history": history, "decisions": lambda: fomc_decisions()[:12],
                   "kalshi": lambda: kalshi_events()[:2], "fomc": fomc},
                  sources=[POLY.format(tag=t) for t in POLY_TAGS] + [KALSHI.format(series=s) for s in KALSHI_SERIES])
    out["meetings"] = next_meetings()
    out["fed_now"] = (out.get("decisions") or [{}])[0].get("to") if out.get("decisions") else None
    out["cites"] = {n: manual_sources(SLUG, n) for n in ("fomc", "fomc_events")}
    out["as_of"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return out


def fomc_history(years: int = FOMC_YEARS) -> list[dict]:
    """Every change in the target over the last `years` years, oldest first, each with the events in data/debt-rates/fomc_events.csv
    from 45 days before the change to the change itself (the context the FOMC was reacting to), and the US 10-year yield and CPI then."""
    since = pd.Timestamp.now().normalize() - pd.DateOffset(years=years)
    dec = [d for d in reversed(fomc_decisions()) if pd.Timestamp(d["date"]) >= since]
    ev = sorted(manual_rows(SLUG, "fomc_events"), key=lambda r: r["date"])
    try:
        y10 = treasury("daily_treasury_yield_curve")["10y"]
    except Exception:
        y10 = pd.Series(dtype=float)
    try:
        c, _ = cpi()
        us_cpi = c.get("US", pd.Series(dtype=float))
    except Exception:
        us_cpi = pd.Series(dtype=float)
    asof = lambda s, t: _r(s[s.index <= t].iloc[-1], 2) if len(s) and len(s[s.index <= t]) else None
    used = set()
    for d in dec:
        t = pd.Timestamp(d["date"])
        d["events"] = [{"date": r["date"], "event": r["event"], "source": r["source"], "note": r.get("note", "")}
                       for r in ev if t - pd.Timedelta(days=45) <= pd.Timestamp(r["date"]) <= t and r["date"] not in used]
        used.update(e["date"] for e in d["events"])
        d["emergency"] = any(r.get("emergency") == "yes" and abs((pd.Timestamp(r["date"]) - t).days) <= 2 for r in ev)
        d["y10"], d["cpi"] = asof(y10, t), asof(us_cpi, t)
    return dec


def fomc_cycles(hist: list[dict]) -> list[dict]:
    """Runs of moves in one direction (a pause of more than 18 months also ends a run): start, end, moves, total bp, months, largest
    move, rate before and after, the 10-year yield change from the day before the first move to the last, and to a year after the first."""
    try:
        y10 = treasury("daily_treasury_yield_curve")["10y"]
    except Exception:
        y10 = pd.Series(dtype=float)
    at = lambda t: y10[y10.index <= t].iloc[-1] if len(y10[y10.index <= t]) else None
    cycles, cur = [], None
    for d in hist:
        sign = 1 if d["bp"] > 0 else -1
        t = pd.Timestamp(d["date"])
        if cur and cur["sign"] == sign and (t - pd.Timestamp(cur["moves"][-1]["date"])).days <= 548:
            cur["moves"].append(d)
        else:
            cur = {"sign": sign, "moves": [d]}
            cycles.append(cur)
    out = []
    for c in cycles:
        m = c["moves"]
        t0, t1 = pd.Timestamp(m[0]["date"]), pd.Timestamp(m[-1]["date"])
        a, b, c1 = at(t0 - pd.Timedelta(days=1)), at(t1), at(t0 + pd.DateOffset(years=1)) if t0 + pd.DateOffset(years=1) <= pd.Timestamp.now() else None
        out.append({"direction": "hiking" if c["sign"] > 0 else "cutting", "start": m[0]["date"], "end": m[-1]["date"], "moves": len(m),
                    "bp": sum(x["bp"] for x in m), "months": round((t1 - t0).days / 30.44, 1), "largest": max((x["bp"] for x in m), key=abs),
                    "from": m[0]["from"], "to": m[-1]["to"], "emergency": sum(1 for x in m if x.get("emergency")),
                    "y10_during": _r((b - a) * 100, 0) if None not in (a, b) else None, "y10_year": _r((c1 - a) * 100, 0) if None not in (a, c1) else None,
                    "context": [e["event"] for x in m for e in x.get("events", [])][:3]})
    return out


def fomc_insights(hist: list[dict], cyc: list[dict]) -> list[str]:
    """Plain-language observations computed from the decisions and cycles above (nothing here is hand-written except the wording)."""
    out = []
    if not hist:
        return out
    ups, downs = [d for d in hist if d["bp"] > 0], [d for d in hist if d["bp"] < 0]
    out.append(f"Since {hist[0]['date'][:4]} the Fed has raised rates {len(ups)} times (+{sum(d['bp'] for d in ups)} bp in all) and cut "
               f"{len(downs)} times ({sum(d['bp'] for d in downs)} bp).")
    hk, ct = [c for c in cyc if c["direction"] == "hiking" and c["moves"] > 1], [c for c in cyc if c["direction"] == "cutting" and c["moves"] > 1]
    if hk and ct:
        mh, mc = np.mean([c["months"] for c in hk]), np.mean([c["months"] for c in ct])
        out.append(f"Cutting cycles took {mc:.0f} months on average against {mh:.0f} for hiking cycles: the Fed climbs by stairs and falls by lift "
                   f"(average step {np.mean([abs(c['bp']) / c['moves'] for c in ct]):.0f} bp cutting vs {np.mean([c['bp'] / c['moves'] for c in hk]):.0f} bp hiking).")
    first_bp = {d["date"]: d["bp"] for d in hist}
    allc = [c for c in cyc if c["direction"] == "cutting"]
    big = [c for c in allc if first_bp.get(c["start"], 0) <= -50]
    if allc:
        out.append(f"{len(big)} of {len(allc)} cutting cycles opened with a cut of 50 bp or more: when the Fed starts cutting into a shock, it starts big.")
    em = [d for d in hist if d.get("emergency")]
    if em:
        out.append(f"{len(em)} move{'s' if len(em) > 1 else ''} came between scheduled meetings ({', '.join(d['date'] for d in em)}), every one a cut in a crisis.")
    ys = [c for c in cyc if c["direction"] == "cutting" and c["y10_year"] is not None]
    if ys:
        rose = [c for c in ys if c["y10_year"] > 0]
        out.append(f"A year after the first cut, the 10-year yield was higher in {len(rose)} of {len(ys)} cutting cycles"
                   + " (" + ", ".join(f"{c['start'][:4]}: {c['y10_year']:+.0f} bp" for c in ys) + ")"
                   + ": rate cuts do not guarantee cheaper long-term borrowing for the government.")
    pauses = []
    for a, b in zip(cyc, cyc[1:]):
        if a["direction"] == "hiking" and b["direction"] == "cutting":
            pauses.append((a["end"], b["start"], (pd.Timestamp(b["start"]) - pd.Timestamp(a["end"])).days / 30.44))
    if pauses:
        out.append("From the last hike to the first cut: " + "; ".join(f"{p[0][:7]} to {p[1][:7]}, {p[2]:.0f} months" for p in pauses)
                   + f". On average the Fed held at the peak for {np.mean([p[2] for p in pauses]):.0f} months.")
    return out


def _qe_now() -> dict:
    """Fed holdings (QE/QT), the Fed's share of marketable Treasuries, Treasury buybacks, and the programmes in data/debt-rates/qe_programs.csv
    with the change in Fed holdings and in the 10-year yield over each."""
    def holdings():
        s = soma()
        return {k: _pts(s[k], 3) for k in ("treasuries", "mbs", "bills", "notesbonds")}

    def share():
        s, m = soma(), mspd()
        tm = s["treasuries"].resample("MS").last()
        j = pd.concat([tm, m["marketable"]], axis=1, keys=["fed", "mkt"], sort=True).dropna()
        return _pts(j["fed"] / j["mkt"] * 100, 2)

    def bb():
        b = buybacks()
        done = b[b["amt"].notna()]
        now_era = done[done["t"] >= "2024-01-01"]           # the current programme; the 2000-02 buybacks are totalled apart
        mon = now_era.groupby([now_era["t"].dt.to_period("M").dt.to_timestamp(), "operation_type"])["amt"].sum().unstack(fill_value=0)
        old = done[done["t"] < "2003-01-01"]
        return {"monthly": {k: _pts(mon[k], 2) for k in mon.columns}, "total": _r(now_era["amt"].sum(), 1), "ops": int(len(now_era)),
                "first": str(now_era["t"].min().date()) if len(now_era) else None,
                "past": {"total": _r(old["amt"].sum(), 1), "ops": int(len(old)), "from": str(old["t"].min().date()) if len(old) else None,
                         "to": str(old["t"].max().date()) if len(old) else None},
                "next": [{"date": str(r.t.date()), "type": r.operation_type,
                "security": r.security_type, "bucket": r.maturity_bucket} for r in b[b["amt"].isna() & (b["t"] >= pd.Timestamp.now().normalize())].itertuples()][:5],
                "by_type": {k: _r(v, 1) for k, v in now_era.groupby("operation_type")["amt"].sum().items()}}

    def programmes():
        rows = sorted(manual_rows(SLUG, "qe_programs"), key=lambda r: r["date"])
        try:
            s = soma()["total"]
        except Exception:
            s = pd.Series(dtype=float)
        try:
            y10 = treasury("daily_treasury_yield_curve")["10y"]
        except Exception:
            y10 = pd.Series(dtype=float)
        at = lambda x, t: x[x.index <= t].iloc[-1] if len(x[x.index <= t]) else None
        out = []
        for r in rows:
            t0 = pd.Timestamp(r["date"])
            t1 = pd.Timestamp(r["end"]) if r.get("end") else pd.Timestamp.now().normalize()
            a, b = at(s, t0), at(s, t1)
            ya, yb = at(y10, t0), at(y10, t1)
            fed_ok = r.get("kind") != "Treasury" and None not in (a, b) and len(s) and s.index[0] <= t0
            out.append({**r, "fed_change_tn": _r(b - a, 2) if fed_ok else None,
                        "y10_change_bp": _r((yb - ya) * 100, 0) if None not in (ya, yb) else None})
        return out
    out = payload({"holdings": holdings, "share": share, "buybacks": bb, "programmes": programmes},
                  sources=[SOMA, MSPD, BUYBACKS])
    out["cites"] = {"qe_programs": manual_sources(SLUG, "qe_programs")}
    out["as_of"] = str(pd.Timestamp.now().date())
    return out


def maturity_mix() -> dict:
    """US marketable debt by type (MSPD): the share in bills (one year or less) against notes, bonds, TIPS and FRNs, monthly."""
    m = mspd()
    longer = m[[c for c in ("notes", "bonds", "tips", "frn") if c in m]].sum(axis=1)
    return {"bills_share": _pts(m["bills"] / m["marketable"] * 100, 2), "bills": _pts(m["bills"], 3), "longer": _pts(longer, 3),
            "now": {"bills_share": _r(m["bills"].iloc[-1] / m["marketable"].iloc[-1] * 100, 1), "bills": _r(m["bills"].iloc[-1], 2),
                    "marketable": _r(m["marketable"].iloc[-1], 2), "month": str(m.index[-1].date())[:7]}}


def scorecard() -> list[dict]:
    """Per country: debt now and in five years (IMF), net interest % of revenue now and in five years, the 10-year yield, nominal growth
    (IMF real growth + inflation, average of the next five years), r - g, the debt-stabilising primary balance d(r-g)/(1+g) and the gap
    to the IMF's projected primary balance (average of the next five years). A positive gap: debt keeps rising on current plans."""
    yr = pd.Timestamp.now().year
    debt, prim, gr, inf, ir = imf("debt"), imf("primary"), imf("growth"), imf("inflation"), imf_interest_revenue()
    y10 = yields10()
    rows = []
    for iso, name in COUNTRIES.items():
        d = debt.get(iso)
        if d is None:
            continue
        fut = lambda s: s[(s.index.year >= yr) & (s.index.year < yr + 5)] if s is not None else pd.Series(dtype=float)
        g_real, g_inf = fut(gr.get(iso)), fut(inf.get(iso))
        g = ((1 + g_real / 100) * (1 + g_inf / 100) - 1).mean() * 100 if len(g_real) and len(g_inf) else None
        r = y10[name].iloc[-1] if name in y10 and len(y10[name]) else None
        dnow = _at(d, yr - 1)
        pb_star = dnow * (r - g) / (100 + g) if None not in (dnow, r, g) else None
        pb = fut(prim.get(iso)).mean() if iso in prim and len(fut(prim.get(iso))) else None
        rows.append({"country": name, "debt": dnow, "debt5": _at(d, yr + 4), "int_rev": _at(ir.get(iso, pd.Series(dtype=float)), yr - 1),
                     "int_rev5": _at(ir.get(iso, pd.Series(dtype=float)), yr + 4), "r": _r(r, 2), "g": _r(g, 2), "r_g": _r(r - g, 2) if None not in (r, g) else None,
                     "pb_star": _r(pb_star, 2), "pb": _r(pb, 2), "gap": _r(pb_star - pb, 2) if None not in (pb_star, pb) else None})
    rows.sort(key=lambda x: -(x["gap"] if x["gap"] is not None else -99))
    return rows


def _stress_now() -> dict:
    def spreads():
        y = yields10()
        pol = {"US": lambda: steps(fed_range()["hi"]), "UK": lambda: steps(boe("bank_rate")), "Hong Kong": hk_base,
               "China": lambda: steps(hand("pboc").get("7-day reverse repo", pd.Series(dtype=float)))}
        out = {}
        for k, s in y.items():
            try:
                p = pol[k]()
                s = month_end(s)
                out[k] = _pts((s - p.reindex(s.index, method="ffill")).dropna(), 2)
            except Exception:
                continue
        return out

    def us_slope():
        t = treasury("daily_treasury_yield_curve")
        return _pts(month_end(t["10y"] - t["2y"]), 2) if "2y" in t else []
    out = payload({"spread": spreads, "us_slope": us_slope, "score": scorecard}, sources=[])
    out["events"] = sorted(manual_rows(SLUG, "stress_events"), key=lambda r: r["date"], reverse=True)
    out["years"] = {"now": pd.Timestamp.now().year - 1, "proj5": pd.Timestamp.now().year + 4}
    out["as_of"] = str(pd.Timestamp.now().date())
    return out


def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, size, start of body), to check reachability and layouts from
    Railway. Read with Actions > show-json on /api/debt-rates/layout."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    from ._base import UA
    y = pd.Timestamp.now().year
    urls = {"imf debt": IMF.format(ind="GGXWDG_NGDP"), "imf revenue (FM)": IMF.format(ind="GGR_G01_GDP_PT"), "penny": PENNY.replace("10000", "2"),
            "mts9": MTS9.replace("10000", "3"), "avg rate": AVG_RATE.replace("10000", "2"),
            "tsy nominal": TSY.format(y=y, kind="daily_treasury_yield_curve"), "tsy real": TSY.format(y=y, kind="daily_treasury_real_yield_curve"),
            "nyfed": NYFED.format(end=f"{y}-01-10").replace("2000-01-01", f"{y}-01-01"),
            "hkma efbn": HKMA.format(path=HK_EFBN, offset=0).replace("pagesize=100", "pagesize=2"), "hkma hibor": HKMA.format(path=HK_HIBOR, offset=0).replace("pagesize=100", "pagesize=2")}
    urls.update({f"boe {c}": BOE.format(y=y, code=c) for cs in BOE_CODES.values() for c in cs})
    urls.update({f"ons {s}": ONS.format(sid=s) for s in ONS_SERIES.values()})
    urls.update({"ons d7g7 cpi": ONS_CPI, "csd cpi": CSD_CPI, "polymarket": POLY.format(tag="fed-rates").replace("limit=50", "limit=2"),
                 "polymarket clob": "https://clob.polymarket.com/time"})
    urls["tips cpi"] = TIPS_CPI.format(cusip=TIPS_CUSIPS[0]).replace("10000", "2")
    urls.update({"kalshi": KALSHI.format(series="KXFED").replace("limit=8", "limit=1"), "soma": SOMA, "mspd": MSPD.replace("10000", "3"),
                 "buybacks": BUYBACKS.replace("2000", "2")})
    heads = {"bls cpi (bulk file, refused from Railway on 2026-10-26)": ("https://download.bls.gov/pub/time.series/cu/cu.data.1.AllItems", None)}

    def one(u):
        try:
            r = requests.get(u, headers=UA, timeout=25)
            return {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type", ""), "start": r.text[:300]}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    def two(item):
        u, h = item
        try:
            r = requests.get(u, headers=h or UA, timeout=40, stream=True)
            body = next(r.iter_content(400), b"")
            r.close()
            return {"status": r.status_code, "type": r.headers.get("content-type", ""), "length": r.headers.get("content-length"), "start": body.decode("latin-1")[:300]}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        out = dict(zip(urls, ex.map(one, urls.values())))
        out.update(zip(heads, ex.map(two, heads.values())))
        return out


def READINGS() -> list[dict]:
    """Headline readings for 'what changed since yesterday', from cached payloads only. lean +1 = more fiscal stress, -1 = less."""
    from ..cache import _cache
    got = lambda name: (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}
    last = lambda p: p[-1][1] if p else None
    band = lambda v, hi, lo: None if v is None else (1 if v >= hi else -1 if v <= lo else 0)
    out = []

    def add(tab, key, label, value, lean, note=None):
        if value is not None:
            out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": lean or 0, **({"note": note} if note else {})})
    d = got("debt")
    for row in d.get("table") or []:
        add("debt", f"debt_{row['country']}", f"{row['country']}: debt, % of GDP (IMF, latest year)", row.get("now"),
            band(row.get("now"), 100, 60) if row["country"] in ("US", "UK") else 0)
    add("debt", "us_per_day", "US federal debt added a day, last 12 months ($bn)", (d.get("us_now") or {}).get("per_day_bn"),
        band((d.get("us_now") or {}).get("per_day_bn"), 6, 3))
    us = got("interest").get("us") or {}
    share, r = last(us.get("share")), us.get("rolling") or {}
    add("interest", "us_int_share", "US net interest, % of federal receipts", share, band(share, 15, 10), "+1 at 15% or more, -1 at 10% or less")
    i, dfn = last(r.get("interest")), last(r.get("defence"))
    if None not in (i, dfn):
        add("interest", "us_int_vs_def", "US net interest minus defence, last 12 months ($bn)", round(i - dfn, 1), 1 if i > dfn else -1)
    add("interest", "uk_int_share", "UK debt interest, % of receipts", last(got("interest").get("uk_share")), band(last(got("interest").get("uk_share")), 10, 7))
    for k, v in (got("yields").get("now") or {}).items():
        add("yields", f"y10_{k}", f"{k} 10-year yield (%)", v.get("v"), band(v.get("v"), 4.5, 3.0) if k in ("US", "UK") else 0)
    for k, v in (got("policy").get("now") or {}).items():
        add("policy", f"rate_{k}", f"{k} (%)", v, 0)
    for k, v in (got("policy").get("cpi_now") or {}).items():
        add("policy", f"cpi_{k}", f"{k} CPI inflation, year on year (%)", v.get("v"), band(v.get("v"), 3, 2) if k in ("US", "UK") else 0,
            "+1 at 3% or more, -1 at 2% or less" if k in ("US", "UK") else None)
    q = got("qe")
    sh = last(q.get("share"))
    add("qe", "fed_share", "Fed share of marketable Treasuries (%)", sh, band(-sh if sh is not None else None, -15, -20),
        "+1 at 15% or less (private buyers must take more), -1 at 20% or more")
    add("qe", "fed_treasuries", "Fed holdings of Treasuries ($tn)", last((q.get("holdings") or {}).get("treasuries")), 0)
    add("debt", "us_bills_share", "US bills as a share of marketable debt (%)", ((d.get("maturity") or {}).get("now") or {}).get("bills_share"),
        band(((d.get("maturity") or {}).get("now") or {}).get("bills_share"), 22, 15), "+1 at 22% or more (fast repricing), -1 at 15% or less")
    od = got("odds")
    hist = (od.get("history") or {}).get("lines") or {}
    for k, pts in list(hist.items())[:3]:
        add("odds", f"next_{k}", f"Next Fed decision, Polymarket: {k} (%)", pts[-1][1] if pts else None, 0)
    ks = od.get("kalshi") or []
    if ks and od.get("fed_now") is not None:
        hold = sum(x["p"] for x in ks[0]["levels"] if abs(x["upper"] - od["fed_now"]) < 0.01)
        add("odds", "kalshi_hold", "Next Fed decision, Kalshi: no change (%)", round(hold * 100, 1), 0)
    st = got("stress")
    for row in st.get("score") or []:
        g = row.get("gap")
        add("stress", f"gap_{row['country']}", f"{row['country']}: debt-stabilising primary balance minus IMF projection (pts of GDP)", g,
            None if g is None else (1 if g > 0.5 else -1 if g < -0.5 else 0))
    for k, pts in (st.get("spread") or {}).items():
        v = last(pts)
        add("stress", f"spread_{k}", f"{k}: 10-year minus policy rate (pts)", v, band(v, 1.5, 0) if k in ("US", "UK") else 0)
    return out


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"debt": _cached_ep("debt", _debt_now), "interest": _cached_ep("interest", _interest_now), "yields": _cached_ep("yields", _yields_now),
             "policy": _cached_ep("policy", _policy_now), "odds": _cached_ep("odds", _odds_now, 1800), "qe": _cached_ep("qe", _qe_now), "stress": _cached_ep("stress", _stress_now), "layout": _cached_ep("layout", _layout_now, 1800)}
