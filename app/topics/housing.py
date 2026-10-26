"""Housing: London, US & Hong Kong (/housing). Free data only, monthly.

prices   UK House Price Index for London and for the UK (HM Land Registry, monthly, ~6 weeks behind): average price, index, yearly change;
         London average price in today's money (deflated with CPIH, ONS series L522 in dataset MM23)
market   London average price by property type (detached / semi / terraced / flat) and monthly sales volume (same UK HPI download)
afford   Bank Rate (Bank of England IADB series IUDBEDR), the London price-to-earnings ratio (London average price / median full-time
         pay of people working in London, ONS ASHE via Nomis, yearly) and, as a monthly trend, the same price / UK average weekly regular pay
         (ONS KAB9 / LMS)

prices   also London and England average monthly private rent (ONS Price Index of Private Rents, newest monthly workbook)

Hand-entered (data/housing/): none required. Everything is cached a day and kept on disk; a source that is down leaves its last
snapshot on the page with a 'stale since' note.
"""
from __future__ import annotations

from io import StringIO
from urllib.parse import quote

import time

import numpy as np
import pandas as pd

from ._base import DAY, _part, _pts, _r, fetch, fetch_json, latest_date, manual, manual_rows, payload, yoy

HPI_URL = ("https://landregistry.data.gov.uk/app/ukhpi/download/new.csv?from=1995-01-01&to=2035-01-01&location={loc}"
           "&thm%5B%5D=property_type%2Fall&thm%5B%5D=property_type%2Fdetached&thm%5B%5D=property_type%2Fsemi-detached"
           "&thm%5B%5D=property_type%2Fterraced&thm%5B%5D=property_type%2Fflat-maisonette"
           "&in%5B%5D=avg&in%5B%5D=index&in%5B%5D=pc_ann&in%5B%5D=vol&lang=en")
LONDON = HPI_URL.format(loc=quote("http://landregistry.data.gov.uk/id/region/london", safe=""))
UK = HPI_URL.format(loc=quote("http://landregistry.data.gov.uk/id/region/united-kingdom", safe=""))
# ONS retired its timeseries API in 2026; the website's CSV download of the same series still works (checked from Railway)
ONS = "https://www.ons.gov.uk/generator?format=csv&uri={uri}"
CPIH = ONS.format(uri="/economy/inflationandpriceindices/timeseries/l522/mm23")            # CPIH all items index, 2015 = 100, monthly
AWE = ONS.format(uri="/employmentandlabourmarket/peopleinwork/earningsandworkinghours/timeseries/kab9/lms")   # avg weekly earnings, regular pay, £
# The Land Registry's per-region download refuses cloud servers (403 from Railway); its monthly full file (every region and borough,
# ~33 MB) is served from publicdata.landregistry.gov.uk and is reachable. The file name carries the month: the newest one is found.
FULL_FILE = "http://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/UK-HPI-full-file-{ym}.csv"
BOE_FIXED = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/1995&Dateto=now"
             "&SeriesCodes=IUMBV34&CSVF=TN&UsingCodes=Y&Filter=N&title=2y%20fixed&VPD=Y")      # quoted 2-year fixed mortgage rate, 75% LTV, monthly
HPI_ONE = ("https://landregistry.data.gov.uk/app/ukhpi/download/new.csv?from=2005-01-01&to=2035-01-01&location={loc}"
           "&thm%5B%5D=property_type%2Fall&in%5B%5D=avg&in%5B%5D=pc_ann&lang=en")
BOROUGHS = ["barking-and-dagenham", "barnet", "bexley", "brent", "bromley", "camden", "city-of-london", "croydon", "ealing", "enfield", "greenwich",
            "hackney", "hammersmith-and-fulham", "haringey", "harrow", "havering", "hillingdon", "hounslow", "islington", "kensington-and-chelsea",
            "kingston-upon-thames", "lambeth", "lewisham", "merton", "newham", "redbridge", "richmond-upon-thames", "southwark", "sutton",
            "tower-hamlets", "waltham-forest", "wandsworth", "city-of-westminster"]
# ASHE median gross annual pay, full-time workers, people working in London (workplace analysis, as in ONS's own affordability ratios);
# yearly, April reference date, published each autumn. Nomis API, reachable from Railway.
ASHE_LONDON = ("https://www.nomisweb.co.uk/api/v01/dataset/NM_99_1.data.csv?geography=2013265927&sex=8&item=2&pay=7&measures=20100"
               "&select=date_name,geography_name,sex_name,item_name,pay_name,obs_value")
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
US_HPI = {"US national (Case-Shiller)": "CSUSHPISA", "New York (Case-Shiller)": "NYXRSA", "San Francisco (Case-Shiller)": "SFXRSA"}   # FRED: unreachable from Railway
FHFA = "https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv"   # FHFA house price indexes (US, states, metros); reachable, ~17 MB
US_MORTGAGE = "MORTGAGE30US"                                    # Freddie Mac 30-year fixed, weekly (FRED copy; FRED is unreachable from Railway)
PMMS = "https://www.freddiemac.com/pmms/docs/historicalweeklydata.xlsx"   # the same series from Freddie Mac directly
HK_RVD = "https://www.rvd.gov.hk/doc/en/statistics/his_data_4.xls"   # private domestic price index, territory-wide, monthly (URL: verify)
HK_HIBOR = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-endperiod?pagesize=100&offset={offset}"
BOE = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/1995&Dateto=now"
       "&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y&Filter=N&title=Bank%20Rate&VPD=Y")

SOURCES = [{"name": "UK House Price Index (HM Land Registry / ONS)", "url": "https://landregistry.data.gov.uk/app/ukhpi", "cadence": "monthly"},
           {"name": "CPIH inflation (ONS, series L522)", "url": "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/l522/mm23", "cadence": "monthly"},
           {"name": "Average weekly earnings (ONS, series KAB9)", "url": "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/timeseries/kab9/lms", "cadence": "monthly"},
           {"name": "London median full-time pay (ONS Annual Survey of Hours and Earnings, workplace analysis, via Nomis)", "url": "https://www.nomisweb.co.uk/datasets/ashe", "cadence": "yearly"},
           {"name": "Bank Rate and quoted 2-year fixed mortgage rate (Bank of England)", "url": "https://www.bankofengland.co.uk/boeapps/database/", "cadence": "monthly"},
           {"name": "FHFA House Price Indexes (US purchase-only; New York and San Francisco metros)", "url": "https://www.fhfa.gov/data/hpi", "cadence": "monthly / quarterly"},
           {"name": "30-year fixed mortgage rate (Freddie Mac PMMS)", "url": "https://www.freddiemac.com/pmms", "cadence": "weekly"},
           {"name": "Hong Kong private domestic price index (Rating and Valuation Department)", "url": "https://www.rvd.gov.hk/en/publications/property_market_statistics.html", "cadence": "monthly"},
           {"name": "HIBOR (Hong Kong Monetary Authority open API)", "url": "https://apidocs.hkma.gov.hk/", "cadence": "monthly"},
           {"name": "Private rents, London and England (ONS Price Index of Private Rents)", "url": "https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics", "cadence": "monthly"}]
NOTES = "Prices are HM Land Registry averages (completed sales, so about two months behind the market). Real terms uses CPIH. Contains public sector information licensed under the Open Government Licence v3.0."
TTL = DAY
PACE = 0.4


# ------------------------------------------------------------------ parsers (each takes text, so tests can feed fixtures)
def parse_hpi(text: str) -> pd.DataFrame:
    """UK HPI download CSV -> monthly frame with plain column names: avg, index, pc_ann, vol, avg_detached, avg_semi, avg_terraced, avg_flat."""
    d = pd.read_csv(StringIO(text))
    cols = {c.lower(): c for c in d.columns}
    period = next((cols[c] for c in cols if c.startswith("period") or c == "date" or "month" in c), d.columns[0])
    d.index = pd.to_datetime(d[period].astype(str).str[:7], format="%Y-%m", errors="coerce")
    d = d[d.index.notna()].sort_index()

    def col(*needles):
        for c in d.columns:
            lc = c.lower()
            if all(n in lc for n in needles):
                return pd.to_numeric(d[c], errors="coerce")
        return pd.Series(index=d.index, dtype=float)
    out = pd.DataFrame({"avg": col("average price", "all property"), "index": col("index", "all property"),
                        "pc_ann": col("yearly", "all property"), "vol": col("sales volume"),
                        "avg_semi": col("average price", "semi"), "avg_terraced": col("average price", "terraced"),
                        "avg_flat": col("average price", "flat")})
    # "detached" also matches "semi-detached": take the column that does not say semi
    det = [c for c in d.columns if "average price" in c.lower() and "detached" in c.lower() and "semi" not in c.lower()]
    out["avg_detached"] = pd.to_numeric(d[det[0]], errors="coerce") if det else float("nan")
    out = out[~out.index.duplicated(keep="last")]
    out = out.reindex(pd.date_range(out.index.min(), out.index.max(), freq="MS"))        # a month with no row is a gap, so shift(12) is a year
    if out["pc_ann"].isna().all() and out["avg"].notna().any():
        out["pc_ann"] = yoy(out["avg"]) * 100
    return out


def parse_full_file(text: str, regions: list[str]) -> dict[str, pd.DataFrame]:
    """UK HPI full file -> {region name: monthly frame with avg, index, pc_ann, vol, avg_detached, avg_semi, avg_terraced, avg_flat}."""
    want = {r.lower() for r in regions}
    cols = ["Date", "RegionName", "AveragePrice", "Index", "12m%Change", "SalesVolume", "DetachedPrice", "SemiDetachedPrice", "TerracedPrice", "FlatPrice"]
    head = pd.read_csv(StringIO(text), nrows=0).columns
    d = pd.read_csv(StringIO(text), usecols=[c for c in cols if c in head], dtype={"RegionName": str}, low_memory=False)
    d = d[d["RegionName"].str.lower().isin(want)]
    d["Date"] = pd.to_datetime(d["Date"], dayfirst=True, errors="coerce")
    ren = {"AveragePrice": "avg", "Index": "index", "12m%Change": "pc_ann", "SalesVolume": "vol", "DetachedPrice": "avg_detached",
           "SemiDetachedPrice": "avg_semi", "TerracedPrice": "avg_terraced", "FlatPrice": "avg_flat"}
    out = {}
    for name, g in d.groupby("RegionName"):
        f = g.set_index("Date").sort_index().rename(columns=ren).drop(columns=["RegionName"])
        f = f[~f.index.duplicated(keep="last")].apply(pd.to_numeric, errors="coerce")
        f = f.reindex(pd.date_range(f.index.min(), f.index.max(), freq="MS"))
        for c in ren.values():
            if c not in f:
                f[c] = np.nan
        out[name] = f
    return out


def full_file_url() -> str:
    """The newest monthly full file: the Land Registry publishes about two months behind, so try the last six months, newest first."""
    import requests

    def go():
        now = pd.Timestamp.now()
        for k in range(1, 7):
            url = FULL_FILE.format(ym=(now - pd.DateOffset(months=k)).strftime("%Y-%m"))
            try:
                if requests.head(url, timeout=20, allow_redirects=True).status_code == 200:
                    return url
            except Exception:
                continue
        raise LookupError("no UK HPI full file found for the last six months")
    from ..cache import _cached
    return _cached("housing:full-file-url", TTL, go)


REGIONS = None          # filled below: London, United Kingdom and the 33 boroughs, as the full file names them


def regions() -> dict[str, pd.DataFrame]:
    from ..cache import _cached

    def go():
        from ._base import SNAP_DIR
        mark = SNAP_DIR / "housing_full_file_url.txt"
        try:
            url = full_file_url()
            SNAP_DIR.mkdir(parents=True, exist_ok=True)
            mark.write_text(url)
        except LookupError:                                  # nothing reachable: the file used last time, which fetch serves from its snapshot
            if not mark.exists():
                raise
            url = mark.read_text().strip()
        return parse_full_file(fetch(url, TTL, min_bytes=1_000_000, timeout=180), REGIONS)
    return _cached("housing:regions", TTL, go)


def parse_ons_csv(text: str) -> pd.Series:
    """ONS website CSV (metadata lines, then "1988 JAN","46.9" rows) -> monthly Series."""
    import re
    rows = re.findall(r'^"(\d{4} [A-Z]{3})","(-?[\d.]+)"', text, flags=re.M)
    s = pd.Series({pd.to_datetime(d, format="%Y %b"): float(v) for d, v in rows})
    if s.empty:
        raise ValueError("ONS CSV layout changed: no monthly rows")
    return s.sort_index()


def parse_ons(j: dict) -> pd.Series:
    """ONS timeseries API JSON -> monthly Series (the 'months' block; dates like '2024 JAN')."""
    rows = j.get("months") or []
    s = pd.Series({pd.to_datetime(r["date"], format="%Y %b", errors="coerce"): pd.to_numeric(r["value"], errors="coerce") for r in rows})
    return s[s.index.notna()].sort_index().dropna()


def parse_nomis(text: str) -> pd.Series:
    """Nomis CSV (DATE_NAME year, ..., OBS_VALUE) -> yearly Series dated April of each year (the ASHE reference month); empty years dropped."""
    d = pd.read_csv(StringIO(text))
    d.columns = [c.upper() for c in d.columns]
    yr = pd.to_numeric(d["DATE_NAME"].astype(str).str[:4], errors="coerce")
    s = pd.Series(pd.to_numeric(d["OBS_VALUE"], errors="coerce").to_numpy(), index=pd.to_datetime(yr.astype("Int64").astype(str) + "-04-01", errors="coerce"))
    s = s[s.index.notna()].dropna().sort_index()
    if s.empty:
        raise ValueError("Nomis ASHE: no values")
    return s


def parse_boe(text: str) -> pd.Series:
    """Bank of England IADB CSV ('DATE,IUDBEDR' with dates like 02 Jan 1995) -> Series of Bank Rate (%), one point per change."""
    d = pd.read_csv(StringIO(text))
    d.columns = [c.strip() for c in d.columns]
    date = next((c for c in d.columns if c.lower().startswith("date")), d.columns[0])
    val = [c for c in d.columns if c != date][0]
    s = pd.Series(pd.to_numeric(d[val], errors="coerce").to_numpy(), index=pd.to_datetime(d[date], dayfirst=True, errors="coerce"))
    return s[s.index.notna()].sort_index().dropna()


def pipr_url(html: str) -> str:
    """ONS PIPR dataset page -> link to the newest monthly workbook (each release sits in a folder named by its date, e.g. 21october2026)."""
    import re
    links = re.findall(r'href="(/file\?uri=[^"]*/priceindexofprivaterentsukmonthlypricestatistics/(\d{1,2}[a-z]+\d{4})/[^"]+\.xlsx)"', html)
    dated = [(pd.to_datetime(d, format="%d%B%Y", errors="coerce"), u) for u, d in links]
    dated = [x for x in dated if pd.notna(x[0])]
    if not dated:
        raise ValueError("ONS PIPR page layout changed: no dated workbook links")
    return "https://www.ons.gov.uk" + max(dated)[1]


RENT_AREAS = {"E12000007": "London average rent", "E92000001": "England average rent"}


def parse_pipr(content: bytes) -> dict[str, pd.DataFrame]:
    """ONS PIPR workbook, sheet "Table 1" (one row per area and month: Time period, Area code, Area name, ..., Index, Monthly change,
    Annual change, Rental price, then the same by bedrooms and type) -> {series name: frame with rent (£ a month) and yoy (%)} for
    RENT_AREAS, and {borough code (E09...): the same plus rent_2bed} for the London boroughs. Streams the sheet (~19 MB)."""
    from io import BytesIO
    import openpyxl
    wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    ws = wb["Table 1"] if "Table 1" in wb.sheetnames else wb[wb.sheetnames[-1]]
    head, rows = None, {}
    for r in ws.iter_rows(values_only=True):
        if head is None:
            if r and str(r[0]).strip().lower() == "time period":
                head = [str(c or "").strip().lower() for c in r]
                code, rent, ann = head.index("area code"), head.index("rental price"), head.index("annual change")
                two = head.index("rental price two bed") if "rental price two bed" in head else None
            continue
        c = r[code]
        if c in RENT_AREAS or str(c).startswith("E09"):          # E09: the London boroughs, kept for the map
            num = lambda i: pd.to_numeric(r[i], errors="coerce") if i is not None else np.nan
            rows.setdefault(c, []).append((pd.Timestamp(r[0]), num(rent), num(ann), num(two)))
    wb.close()
    if head is None:
        raise ValueError("PIPR layout changed: no 'Time period' header row")
    out = {RENT_AREAS.get(k, k): pd.DataFrame(v, columns=["t", "rent", "yoy", "rent_2bed"]).set_index("t").sort_index() for k, v in rows.items() if v}
    if "London average rent" not in out or out["London average rent"]["rent"].dropna().empty:
        raise ValueError("PIPR layout changed: no London rents")
    return out


# ------------------------------------------------------------------ data
def hpi(which: str) -> pd.DataFrame:
    return regions()["London" if which == "london" else "United Kingdom"]


def cpih() -> pd.Series:
    return parse_ons_csv(fetch(CPIH, TTL))


def earnings() -> pd.Series:
    return parse_ons_csv(fetch(AWE, TTL))


def rents() -> dict[str, pd.DataFrame]:
    """The newest PIPR workbook (its link is read from the dataset page, a new dated folder each month)."""
    from ..cache import _cached

    def go():
        url = pipr_url(fetch(PIPR_PAGE, TTL, min_bytes=5000))
        return parse_pipr(fetch(url, TTL, binary=True, min_bytes=1_000_000, timeout=180).encode("latin-1"))
    return _cached("housing:rents", TTL, go)


def london_pay() -> pd.Series:
    return parse_nomis(fetch(ASHE_LONDON, TTL))


def bank_rate() -> pd.Series:
    return parse_boe(fetch(BOE, TTL))


def boe_fixed() -> pd.Series:
    return parse_boe(fetch(BOE_FIXED, TTL))


def borough_name(slug: str) -> str:
    return slug.replace("-", " ").title().replace(" And ", " and ").replace(" Upon ", " upon ").replace(" Of ", " of ")


def borough(slug: str) -> pd.DataFrame:
    return regions()[borough_name(slug)]


def parse_fred(text: str) -> pd.Series:
    d = pd.read_csv(StringIO(text))
    s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors="coerce").to_numpy(), index=pd.to_datetime(d.iloc[:, 0], errors="coerce"))
    return s[s.index.notna()].dropna().sort_index()


def fred(sid: str) -> pd.Series:
    return parse_fred(fetch(FRED.format(sid=sid), TTL, curl=True))


def parse_pmms(content: bytes) -> pd.Series:
    """Freddie Mac PMMS workbook -> weekly 30-year fixed rate (%). Finds the header row naming the 30-year rate and the date column."""
    from io import BytesIO
    d = pd.read_excel(BytesIO(content), header=None)
    for i in range(min(15, len(d))):
        row = [str(x).lower() for x in d.iloc[i].tolist()]
        j = next((k for k, x in enumerate(row) if "30" in x and ("frm" in x or "fixed" in x or "yr" in x)), None)
        if j is None:
            continue
        dates = pd.to_datetime(d.iloc[i + 1:, 0], errors="coerce")
        vals = pd.to_numeric(d.iloc[i + 1:, j], errors="coerce")
        s = pd.Series(vals.to_numpy(), index=dates.to_numpy()).dropna()
        s = s[s.index.notna()].sort_index()
        if len(s) > 100:
            return s
    raise ValueError("PMMS layout changed: no 30-year column")


def us_mortgage() -> pd.Series:
    return parse_pmms(fetch(PMMS, TTL, binary=True, min_bytes=10000).encode("latin-1"))


def parse_rvd(content: bytes) -> pd.Series:
    """RVD price-index workbook -> monthly territory-wide private domestic index. Finds rows that start with a year and month and takes
    the first numeric column after them (the all-classes index). Best effort: the layout is checked by the network test."""
    from io import BytesIO
    xl = pd.ExcelFile(BytesIO(content))
    out = {}
    for sheet in xl.sheet_names:
        d = xl.parse(sheet, header=None)
        year = None
        for _, row in d.iterrows():
            cells = [c for c in row.tolist() if not (isinstance(c, float) and np.isnan(c))]
            if not cells:
                continue
            first = str(cells[0]).strip()
            if first.isdigit() and 1979 <= int(first) <= 2100:
                year, cells = int(first), cells[1:]
            if year is None or not cells:
                continue
            m = pd.to_datetime(str(cells[0]).strip()[:3], format="%b", errors="coerce")
            nums = [c for c in cells[1:] if isinstance(c, (int, float)) and not isinstance(c, bool)]
            if pd.notna(m) and nums:
                out[pd.Timestamp(year=year, month=m.month, day=1)] = float(nums[0])
        if len(out) > 100:
            break
    if len(out) < 100:
        raise ValueError(f"RVD layout changed ({len(out)} months parsed)")
    return pd.Series(out).sort_index()


def hk_index() -> pd.Series:
    auto, why = pd.Series(dtype=float), ""
    try:
        auto = parse_rvd(fetch(HK_RVD, TTL, binary=True, min_bytes=1000).encode("latin-1"))
    except Exception as e:          # a legacy .xls needs xlrd, which requirements.txt does not have yet (see README, requests for shared code)
        why = f" ({type(e).__name__}: {str(e)[:120]})"
    hand = manual("housing", "hk_price_index")
    s = pd.concat([hand if isinstance(hand, pd.Series) else pd.Series(dtype=float), auto])
    if s.empty:
        raise ValueError(f"no Hong Kong price index: RVD workbook not readable{why} and data/housing/hk_price_index.csv empty")
    return s[~s.index.duplicated(keep="last")].sort_index()


def hk_hibor() -> pd.Series:
    """HKMA open API, 100 records a page (a larger page is refused with HTTP 405)."""
    rows = []
    for k in range(12):
        recs = (fetch_json(HK_HIBOR.format(offset=k * 100), TTL).get("result") or {}).get("records") or []
        rows += recs
        if len(recs) < 100:
            break
    s = pd.Series({pd.to_datetime(r.get("end_of_month"), errors="coerce"): pd.to_numeric(r.get("ir_1m"), errors="coerce") for r in rows})
    s = s[s.index.notna()].dropna().sort_index()
    if s.empty:
        raise ValueError("HKMA HIBOR: no records")
    return s


def parse_fhfa(text: str) -> dict[str, pd.Series]:
    """FHFA master CSV -> US national purchase-only index (monthly, seasonally adjusted) and the New York and San Francisco metro
    divisions (quarterly, all transactions)."""
    d = pd.read_csv(StringIO(text), dtype=str)
    d["t"] = pd.to_datetime(d["yr"].astype(int).astype(str) + "-" + (d["period"].astype(int) * (d["frequency"].str.startswith("quarter").map({True: 3, False: 1})) - (d["frequency"].str.startswith("quarter").map({True: 2, False: 0}))).astype(str) + "-01", errors="coerce")
    out = {}
    us = d[(d["frequency"] == "monthly") & (d["hpi_flavor"] == "purchase-only") & (d["place_id"] == "USA")]
    if len(us):
        col = "index_sa" if us["index_sa"].notna().any() else "index_nsa"
        out["US national (FHFA)"] = pd.Series(pd.to_numeric(us[col], errors="coerce").to_numpy(), index=us["t"].to_numpy()).dropna().sort_index()
    for label, needle in (("New York metro (FHFA)", "New York-Jersey City"), ("San Francisco metro (FHFA)", "San Francisco-San Mateo")):
        m = d[(d["frequency"] == "quarterly") & (d["hpi_flavor"] == "all-transactions") & d["place_name"].str.contains(needle, na=False)]
        if len(m):
            out[label] = pd.Series(pd.to_numeric(m["index_nsa"], errors="coerce").to_numpy(), index=m["t"].to_numpy()).dropna().sort_index()
    if not out:
        raise ValueError("FHFA layout changed: no US or metro rows")
    return out


def fhfa() -> dict[str, pd.Series]:
    return parse_fhfa(fetch(FHFA, TTL, min_bytes=100_000, timeout=120))


def _rebase(s: pd.Series, at: str = "2015-01-01") -> pd.Series:
    s = s.dropna()
    base = s[s.index >= at]
    return s / base.iloc[0] * 100 if len(base) else s


def _real(avg: pd.Series, cpi: pd.Series) -> pd.Series:
    """avg in the money of the latest CPIH month."""
    cpi = cpi.reindex(avg.index, method="ffill")
    return (avg * cpi.dropna().iloc[-1] / cpi).dropna()


def _month_steps(s: pd.Series) -> pd.Series:
    """A rate that changes on odd days -> a month-start series (value in force at each month start), so it lines up with the monthly data."""
    s = s.sort_index()
    idx = pd.date_range(s.index[0].normalize().replace(day=1), pd.Timestamp.now().normalize().replace(day=1), freq="MS")
    return s.reindex(s.index.union(idx)).ffill().reindex(idx)


# ------------------------------------------------------------------ endpoints
def _prices_now() -> dict:
    lon = hpi("london")
    out = payload({"london_avg": lambda: _pts(lon["avg"], 0), "london_index": lambda: _pts(lon["index"], 1), "london_yoy": lambda: _pts(lon["pc_ann"], 2),
                   "uk_avg": lambda: _pts(hpi("uk")["avg"], 0), "uk_index": lambda: _pts(hpi("uk")["index"], 1), "uk_yoy": lambda: _pts(hpi("uk")["pc_ann"], 2),
                   "london_real": lambda: _pts(_real(lon["avg"].dropna(), cpih()), 0)},
                  sources=[CPIH], as_of=latest_date(lon["avg"]))
    a = lon["avg"].dropna()

    def rent_lines():
        """ONS PIPR (automated) first; rows in data/housing/rents.csv add series or months the workbook lacks."""
        hand = manual("housing", "rents")
        try:
            auto = {k: f["rent"].dropna() for k, f in rents().items() if k in RENT_AREAS.values()}
        except Exception:
            if not isinstance(hand, dict) or not hand:
                raise
            auto = {}
        for k, v in (hand.items() if isinstance(hand, dict) else []):
            auto[k] = v.combine_first(auto[k]) if k in auto else v
        return {k: _pts(v, 0) for k, v in auto.items() if len(v)}
    _part(out, "rents", rent_lines)
    out["rents"] = out.get("rents") or {}
    try:
        lr = rents()["London average rent"].dropna()
        out["rent_now"] = {"rent": _r(lr["rent"].iloc[-1], 0), "yoy": _r(lr["yoy"].iloc[-1], 2), "month": str(lr.index[-1].date()),
                           "rent_to_price": _r(lr["rent"].iloc[-1] * 12 / a.iloc[-1], 4) if len(a) else None}
    except Exception:
        out["rent_now"] = {}
    out["now"] = {"avg": _r(a.iloc[-1], 0) if len(a) else None, "yoy": _r(lon["pc_ann"].dropna().iloc[-1], 2) if lon["pc_ann"].notna().any() else None,
                  "peak": _r(a.max(), 0) if len(a) else None, "peak_month": str(a.idxmax().date()) if len(a) else None,
                  "from_peak": _r(a.iloc[-1] / a.max() - 1, 4) if len(a) else None,
                  "change_5y": _r(a.iloc[-1] / a[a.index <= a.index[-1] - pd.DateOffset(years=5)].iloc[-1] - 1, 4) if len(a) > 60 else None,
                  "change_10y": _r(a.iloc[-1] / a[a.index <= a.index[-1] - pd.DateOffset(years=10)].iloc[-1] - 1, 4) if len(a) > 120 else None}
    return out


def _market_now() -> dict:
    lon = hpi("london")
    types = {"Detached": "avg_detached", "Semi-detached": "avg_semi", "Terraced": "avg_terraced", "Flat / maisonette": "avg_flat"}
    out = payload({"by_type": lambda: {k: _pts(lon[c], 0) for k, c in types.items()},
                   "by_type_yoy": lambda: {k: _pts(yoy(lon[c].dropna()) * 100, 2) for k, c in types.items()},
                   "volume": lambda: _pts(lon["vol"].dropna(), 0), "volume_12m": lambda: _pts(lon["vol"].dropna().rolling(12).sum(), 0)},
                  sources=[], as_of=latest_date(lon["avg"]))
    v = lon["vol"].dropna()
    out["now"] = {"volume_last": _r(v.iloc[-1], 0) if len(v) else None, "volume_month": str(v.index[-1].date()) if len(v) else None,
                  "volume_12m": _r(v.iloc[-12:].sum(), 0) if len(v) >= 12 else None,
                  "volume_12m_prev": _r(v.iloc[-24:-12].sum(), 0) if len(v) >= 24 else None,
                  "types": {k: _r(lon[c].dropna().iloc[-1], 0) for k, c in types.items() if lon[c].notna().any()}}
    return out


def _afford_now() -> dict:
    lon = hpi("london")
    avg = lon["avg"].dropna()

    def ratio():
        """London average price / UK annual regular pay: monthly, UK-wide, so a trend line rather than a London level."""
        w = earnings()
        annual = (w * 52).reindex(avg.index, method="ffill")
        return _pts((avg / annual).dropna(), 2)

    def ratio_london():
        """London average price / median full-time pay of people working in London (ASHE, yearly, carried forward to the next survey)."""
        p = london_pay()
        annual = p.reindex(p.index.union(avg.index)).ffill().reindex(avg.index)
        return _pts((avg / annual)[avg.index >= p.index[0]].dropna(), 2)

    basis = {"rate": "the Bank of England's quoted 2-year fixed rate at 75% loan-to-value"}

    def mortgage():
        """Illustrative monthly payment on 75% of the London average price over 25 years at the quoted 2-year fixed rate (75% LTV); Bank Rate
        + 1.5 points before that series starts or when it is unavailable."""
        fallback = _month_steps(bank_rate()).reindex(avg.index, method="ffill") / 100 + 0.015
        try:
            fixed = boe_fixed().resample("MS").last().reindex(avg.index, method="ffill") / 100
            rate = fixed.fillna(fallback)
        except Exception:
            rate = fallback
            basis["rate"] = "Bank Rate + 1.5 points (the quoted fixed rate was unavailable)"
        r = rate / 12
        n = 25 * 12
        pay = avg * 0.75 * r / (1 - (1 + r) ** -n)
        return _pts(pay.dropna(), 0)
    out = payload({"bank_rate": lambda: _pts(_month_steps(bank_rate()), 2), "fixed_2y": lambda: _pts(boe_fixed(), 2), "price_to_earnings": ratio, "mortgage": mortgage,
                   "price_to_london_pay": ratio_london, "london_pay": lambda: _pts(london_pay(), 0),
                   "earnings_annual": lambda: _pts((earnings() * 52).dropna(), 0)},
                  sources=[AWE, BOE, ASHE_LONDON], as_of=latest_date(avg))
    br = out.get("bank_rate") or []
    pe = out.get("price_to_london_pay") or out.get("price_to_earnings") or []
    lp = out.get("london_pay") or []
    out["now"] = {"bank_rate": br[-1][1] if br else None, "price_to_earnings": pe[-1][1] if pe else None,
                  "pe_basis": "london" if out.get("price_to_london_pay") else "uk",
                  "london_pay": lp[-1][1] if lp else None, "london_pay_year": pd.Timestamp(lp[-1][0], unit="s").year if lp else None,
                  "mortgage": out["mortgage"][-1][1] if out.get("mortgage") else None,
                  "pe_peak": max((p[1] for p in pe if p[1] is not None), default=None),
                  "fixed_2y": out["fixed_2y"][-1][1] if out.get("fixed_2y") else None}
    out["mortgage_basis"] = basis["rate"]
    return out


MAP_HISTORY = {"flat": "avg_flat", "terraced": "avg_terraced", "semi": "avg_semi", "detached": "avg_detached", "rent_2bed": "rent_2bed"}   # map measure -> column
MAP_SINCE = "2005-01-01"        # the map's timeline starts here (rents start in 2015 and are blank before)


def borough_map() -> dict:
    """data/housing/london_boroughs.json: SVG outlines of the 33 boroughs (ONS boundaries, simplified), keyed by ONS code."""
    import json
    from ._base import MANUAL_DIR
    return json.loads((MANUAL_DIR / "housing" / "london_boroughs.json").read_text())


def _boroughs_now() -> dict:
    """Every London borough's average price (all, flat, and the three house types) and yearly change from the UK HPI, the 2-bed and
    all-property rent from ONS PIPR, and the outlines for the map."""
    rows, series, errors, rents_error = [], {}, {}, None
    hist: dict[str, dict] = {m: {} for m in MAP_HISTORY}
    geo = borough_map()
    code_of = {g["name"]: g["code"] for g in geo["boroughs"]} | {"City of Westminster": "E09000033"}
    try:
        rent = {k: f for k, f in rents().items() if k.startswith("E09")}
    except Exception as e:
        rent, rents_error = {}, type(e).__name__
    last = lambda s: _r(s.dropna().iloc[-1], 0) if s.notna().any() else None
    for i, b in enumerate(BOROUGHS):
        try:
            d = borough(b)
            a = d["avg"].dropna()
            five = a[a.index <= a.index[-1] - pd.DateOffset(years=5)]
            name = borough_name(b)
            code = code_of.get(name)
            rf = rent.get(code)
            rows.append({"borough": name, "code": code, "avg": _r(a.iloc[-1], 0), "yoy": _r(d["pc_ann"].dropna().iloc[-1], 2) if d["pc_ann"].notna().any() else None,
                         "change_5y": _r(a.iloc[-1] / five.iloc[-1] - 1, 4) if len(five) else None, "month": str(a.index[-1].date()),
                         "flat": last(d["avg_flat"]), "terraced": last(d["avg_terraced"]), "semi": last(d["avg_semi"]), "detached": last(d["avg_detached"]),
                         "rent_2bed": last(rf["rent_2bed"]) if rf is not None else None, "rent": last(rf["rent"]) if rf is not None else None,
                         "rent_month": str(rf["rent_2bed"].dropna().index[-1].date()) if rf is not None and rf["rent_2bed"].notna().any() else None})
            series[name] = _pts(_rebase(a, "2015-01-01"), 1)
            if code:
                for m, col in MAP_HISTORY.items():
                    frame = rf if m == "rent_2bed" else d
                    if frame is not None:
                        hist[m][code] = frame[col]
        except Exception as e:
            errors[b] = type(e).__name__
    if not [r for r in rows if r["avg"]]:
        raise ValueError(f"no borough could be read ({len(errors)} failed)")
    rows.sort(key=lambda r: -(r["avg"] or 0))
    return {"rows": rows, "indexed": series, "errors": errors, "rents_error": rents_error, "as_of": max(r["month"] for r in rows), "stale": {},
            "updated": int(time.time()), "map": {"viewBox": geo["viewBox"], "source": geo["source"], "shapes": [{"code": g["code"], "d": g["d"]} for g in geo["boroughs"]],
                                                 "history": _map_history(hist)}}


def _map_history(hist: dict[str, dict[str, pd.Series]]) -> dict:
    """Monthly values per measure and borough on one month axis from MAP_SINCE to the latest month any measure has, for the map's
    timeline: {"start": "YYYY-MM", "months": n, "values": {measure: {code: [int or None, ...]}}}. Prices are rounded to £100."""
    ends = [s.dropna().index.max() for by in hist.values() for s in by.values() if s.notna().any()]
    if not ends:
        return {}
    idx = pd.date_range(MAP_SINCE, max(ends), freq="MS")
    vals = {}
    for m, by in hist.items():
        step = 1 if m == "rent_2bed" else 100
        vals[m] = {c: [None if pd.isna(v) else int(round(v / step) * step) for v in s.groupby(s.index).last().reindex(idx).to_numpy()] for c, s in by.items()}
    return {"start": idx[0].strftime("%Y-%m"), "months": len(idx), "values": vals}


def _rates(missing: dict) -> dict:
    """Each borrowing cost on its own, so one refused source (HKMA refuses Railway) leaves the others on the chart; missing names it."""
    out = {}
    for name, fn in (("UK 2-year fixed (75% LTV)", boe_fixed), ("US 30-year fixed", lambda: us_mortgage().resample("MS").last()), ("HK 1-month HIBOR", hk_hibor)):
        try:
            out[name] = _pts(fn(), 2)
        except Exception as e:
            missing[name] = f"{type(e).__name__}: {str(e)[:120]}"
    if not out:
        raise ValueError("no borrowing-cost series reachable")
    return out


def _global_now() -> dict:
    lon = hpi("london")
    missing: dict = {}
    out = payload({"london": lambda: _pts(_rebase(lon["index"].dropna()), 1),
                   "us": lambda: {k: _pts(_rebase(v), 1) for k, v in fhfa().items()},
                   "hk": lambda: _pts(_rebase(hk_index()), 1),
                   "rates": lambda: _rates(missing)},
                  sources=[HK_RVD, HK_HIBOR, BOE_FIXED] + [PMMS, FHFA],
                  as_of=latest_date(lon["index"]))
    out["rates_missing"] = missing

    def yy(pts):
        """Change on the point a year before the latest (by date, so monthly and quarterly series both work)."""
        if not pts:
            return None
        t = pts[-1][0] - 365 * 86400
        prev = [p for p in pts if p[0] <= t + 20 * 86400]
        return _r(pts[-1][1] / prev[-1][1] - 1, 4) if prev and prev[-1][0] >= t - 40 * 86400 else None
    table = []
    if out.get("london"):
        table.append({"market": "London", "index": out["london"][-1][1], "yoy": yy(out["london"]), "month": pd.Timestamp(out["london"][-1][0], unit="s").strftime("%Y-%m")})
    for k, pts in (out.get("us") or {}).items():
        if pts:
            table.append({"market": k, "index": pts[-1][1], "yoy": yy(pts), "month": pd.Timestamp(pts[-1][0], unit="s").strftime("%Y-%m")})
    if out.get("hk"):
        table.append({"market": "Hong Kong (RVD)", "index": out["hk"][-1][1], "yoy": yy(out["hk"]), "month": pd.Timestamp(out["hk"][-1][0], unit="s").strftime("%Y-%m")})
    out["table"] = table
    return out


LAYOUT_PROBES = {
    "hkma json accept": (HK_HIBOR.format(offset=0).replace("pagesize=100", "pagesize=3"), {"Accept": "application/json"}),
    "hkma plain ua": (HK_HIBOR.format(offset=0).replace("pagesize=100", "pagesize=3"), {"User-Agent": "python-requests/2.32", "Accept": "*/*"}),
    "nomis ashe london": ("https://www.nomisweb.co.uk/api/v01/dataset/NM_30_1.data.csv?geography=2013265927&sex=8&item=2&pay=7&measures=20100"
                          "&select=date_name,geography_name,sex_name,item_name,pay_name,obs_value", None),
    "nomis ashe london workplace": ("https://www.nomisweb.co.uk/api/v01/dataset/NM_99_1.data.csv?geography=2013265927&sex=8&item=2&pay=7&measures=20100"
                                    "&select=date_name,geography_name,sex_name,item_name,pay_name,obs_value", None),
}
PIPR_PAGE = "https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics"
LAYOUT_PAGES = [PIPR_PAGE,
                "https://www.ons.gov.uk/economy/inflationandpriceindices/bulletins/privaterentandhousepricesuk/latest"]


def _layout_now() -> dict:
    """Not a tab: what the server sees at sources whose layout or reachability is uncertain (RVD workbooks, HKMA, ONS rents, Nomis ASHE),
    so parsers can be written against the real files. Read with Actions > show-json on /api/housing/layout."""
    import re
    from concurrent.futures import ThreadPoolExecutor
    from io import BytesIO
    import requests
    from ._base import UA

    def rvd(url):
        r = requests.get(url, headers=UA, timeout=20)
        row = {"status": r.status_code, "bytes": len(r.content)}
        if r.ok:
            xl = pd.ExcelFile(BytesIO(r.content))
            row["sheets"] = xl.sheet_names
            for sh in [x for x in xl.sheet_names if "lond" in x.lower() or x in xl.sheet_names[:4]][:8]:
                d = xl.parse(sh, header=None).dropna(how="all")
                rows = [" | ".join(str(c)[:40] for c in rw if not (isinstance(c, float) and np.isnan(c))) for rw in d.values.tolist()]
                row[sh] = {"shape": list(d.shape), "head": rows[:10], "tail": rows[-2:], "london": [r for r in rows if "London" in r][-2:]}
        return row

    def probe(url, headers):
        r = requests.get(url, headers=headers or UA, timeout=20)
        return {"status": r.status_code, "type": r.headers.get("content-type", ""), "bytes": len(r.content), "start": r.text[:600]}

    def page(url):
        r = requests.get(url, headers=UA, timeout=20)
        return {"status": r.status_code, "links": sorted(set(re.findall(r'href="(/file\?uri=[^"]+|[^"]*/timeseries/[^"]+)"', r.text)))[:60]}

    jobs = {("rvd", f"{k}.{e}"): (rvd, f"https://www.rvd.gov.hk/doc/en/statistics/his_data_{k}.{e}") for k in range(1, 7) for e in ("xls", "xlsx")}
    jobs.update({("probes", name): (probe, url, headers) for name, (url, headers) in LAYOUT_PROBES.items()})
    jobs.update({("pages", url): (page, url) for url in LAYOUT_PAGES})

    def pipr():
        url = pipr_url(requests.get(PIPR_PAGE, headers=UA, timeout=20).text)
        return {"url": url, **rvd(url)}
    jobs[("pages", "pipr newest workbook")] = (pipr,)

    def run(job):
        try:
            return job[0](*job[1:])
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    out: dict = {"rvd": {}, "probes": {}, "pages": {}}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (group, key), res in zip(jobs, ex.map(run, jobs.values())):
            out[group][key] = res
    return out


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:housing:{name}", ttl, fn)


ENDPOINTS = {"prices": _cached_ep("prices", _prices_now), "market": _cached_ep("market", _market_now), "afford": _cached_ep("afford", _afford_now),
             "boroughs": _cached_ep("boroughs", _boroughs_now), "global": _cached_ep("global", _global_now),
             "layout": _cached_ep("layout", _layout_now, 1800)}


REGIONS = ["London", "United Kingdom"] + [borough_name(b) for b in BOROUGHS]
