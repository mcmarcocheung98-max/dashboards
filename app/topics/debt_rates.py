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

from ._base import (DAY, _part, _pts, _r, fetch, fetch_json, latest_date, manual, manual_rows, manual_sources, payload)
from . import Topic

SLUG = "debt-rates"
TOPIC = Topic(SLUG, "Global Debt & Rates",
              "Government debt, interest bills, 10-year yields and policy rates in the US, UK, Hong Kong and China: which hits fiscal stress first, "
              "and when interest overtakes defence or education.",
              "debt_rates", (("debt", "Debt"), ("interest", "Interest cost"), ("yields", "Yields"), ("policy", "Policy rates"), ("stress", "Stress")),
              ("debt", "interest", "yields", "policy", "stress"), icon="chart", order=60)

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

SOURCES = [{"name": "IMF World Economic Outlook (DataMapper API): gross debt, overall and primary balance, revenue, growth, inflation", "url": "https://www.imf.org/external/datamapper/", "cadence": "April and October"},
           {"name": "US Treasury Fiscal Data: debt to the penny, Monthly Treasury Statement table 9, average interest rates", "url": "https://fiscaldata.treasury.gov/", "cadence": "daily / monthly"},
           {"name": "US Treasury par and real yield curves", "url": "https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics", "cadence": "daily"},
           {"name": "Federal funds target range and EFFR (Federal Reserve Bank of New York)", "url": "https://www.newyorkfed.org/markets/reference-rates/effr", "cadence": "daily"},
           {"name": "Bank Rate and gilt yield curves (Bank of England database)", "url": "https://www.bankofengland.co.uk/boeapps/database/", "cadence": "daily"},
           {"name": "Public sector finances: net debt, debt interest, receipts (ONS PUSF)", "url": "https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance", "cadence": "monthly"},
           {"name": "Exchange Fund Bills and Notes yields, HIBOR (HKMA open API)", "url": "https://apidocs.hkma.gov.hk/", "cadence": "monthly"},
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
                   "uk_psnd": lambda: _pts(ons("psnd"), 1)},
                  sources=[PENNY, ONS.format(sid="hf6x")])
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
    out = payload({"fed": fed, "boe": lambda: _pts(steps(boe("bank_rate")), 2), "hk": lambda: _pts(hk_base(), 2),
                   "pboc": lambda: {k: _pts(steps(v), 2) for k, v in pb.items()}},
                  sources=[NYFED.format(end=pd.Timestamp.now().strftime("%Y-%m-%d")), BOE.format(y=1995, code="IUDBEDR")])
    last = lambda p: p[-1][1] if p else None
    out["now"] = {"Fed (upper)": last((out.get("fed") or {}).get("upper")), "Bank of England": last(out.get("boe")), "HKMA base rate": last(out.get("hk")),
                  "PBoC 7-day reverse repo": last((out.get("pboc") or {}).get("7-day reverse repo"))}
    out["cites"] = {n: manual_sources(SLUG, n) for n in ("pboc", "fed_target")}
    out["as_of"] = str(pd.Timestamp.now().date())
    return out


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

    def one(u):
        try:
            r = requests.get(u, headers=UA, timeout=25)
            return {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type", ""), "start": r.text[:300]}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(urls, ex.map(one, urls.values())))


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
             "policy": _cached_ep("policy", _policy_now), "stress": _cached_ep("stress", _stress_now), "layout": _cached_ep("layout", _layout_now, 1800)}
