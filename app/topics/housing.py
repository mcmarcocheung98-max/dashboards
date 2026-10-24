"""London Housing Index (/housing). Free data only, monthly.

prices   UK House Price Index for London and for the UK (HM Land Registry, monthly, ~6 weeks behind): average price, index, yearly change;
         London average price in today's money (deflated with CPIH, ONS series L522 in dataset MM23)
market   London average price by property type (detached / semi / terraced / flat) and monthly sales volume (same UK HPI download)
afford   Bank Rate (Bank of England IADB series IUDBEDR), UK average weekly earnings (ONS KAB9 / LMS, regular pay) and the London
         price-to-earnings ratio (London average price / UK annual regular pay: a UK-wide wage, so a conservative London ratio)

Hand-entered (data/housing/): none required. Everything is cached a day and kept on disk; a source that is down leaves its last
snapshot on the page with a 'stale since' note.
"""
from __future__ import annotations

from io import StringIO
from urllib.parse import quote

import pandas as pd

from ._base import DAY, _pts, _r, fetch, fetch_json, latest_date, payload, yoy

HPI_URL = ("https://landregistry.data.gov.uk/app/ukhpi/download/new.csv?from=1995-01-01&to=2035-01-01&location={loc}"
           "&thm%5B%5D=property_type%2Fall&thm%5B%5D=property_type%2Fdetached&thm%5B%5D=property_type%2Fsemi-detached"
           "&thm%5B%5D=property_type%2Fterraced&thm%5B%5D=property_type%2Fflat-maisonette"
           "&in%5B%5D=avg&in%5B%5D=index&in%5B%5D=pc_ann&in%5B%5D=vol&lang=en")
LONDON = HPI_URL.format(loc=quote("http://landregistry.data.gov.uk/id/region/london", safe=""))
UK = HPI_URL.format(loc=quote("http://landregistry.data.gov.uk/id/region/united-kingdom", safe=""))
ONS = "https://api.ons.gov.uk/timeseries/{sid}/dataset/{ds}/data"
CPIH = ONS.format(sid="L522", ds="MM23")                       # CPIH all items index, 2015 = 100, monthly
AWE = ONS.format(sid="KAB9", ds="LMS")                         # average weekly earnings, regular pay, whole economy, £ (seasonally adjusted)
BOE = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/1995&Dateto=now"
       "&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y&Filter=N&title=Bank%20Rate&VPD=Y")

SOURCES = [{"name": "UK House Price Index (HM Land Registry / ONS)", "url": "https://landregistry.data.gov.uk/app/ukhpi", "cadence": "monthly"},
           {"name": "CPIH inflation (ONS, series L522)", "url": "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/l522/mm23", "cadence": "monthly"},
           {"name": "Average weekly earnings (ONS, series KAB9)", "url": "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/timeseries/kab9/lms", "cadence": "monthly"},
           {"name": "Bank Rate (Bank of England)", "url": "https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp", "cadence": "on change"}]
NOTES = "Prices are HM Land Registry averages (completed sales, so about two months behind the market). Real terms uses CPIH. Contains public sector information licensed under the Open Government Licence v3.0."
TTL = DAY


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


def parse_ons(j: dict) -> pd.Series:
    """ONS timeseries API JSON -> monthly Series (the 'months' block; dates like '2024 JAN')."""
    rows = j.get("months") or []
    s = pd.Series({pd.to_datetime(r["date"], format="%Y %b", errors="coerce"): pd.to_numeric(r["value"], errors="coerce") for r in rows})
    return s[s.index.notna()].sort_index().dropna()


def parse_boe(text: str) -> pd.Series:
    """Bank of England IADB CSV ('DATE,IUDBEDR' with dates like 02 Jan 1995) -> Series of Bank Rate (%), one point per change."""
    d = pd.read_csv(StringIO(text))
    d.columns = [c.strip() for c in d.columns]
    date = next((c for c in d.columns if c.lower().startswith("date")), d.columns[0])
    val = [c for c in d.columns if c != date][0]
    s = pd.Series(pd.to_numeric(d[val], errors="coerce").to_numpy(), index=pd.to_datetime(d[date], dayfirst=True, errors="coerce"))
    return s[s.index.notna()].sort_index().dropna()


# ------------------------------------------------------------------ data
def hpi(which: str) -> pd.DataFrame:
    return parse_hpi(fetch(LONDON if which == "london" else UK, TTL, curl=True))


def cpih() -> pd.Series:
    return parse_ons(fetch_json(CPIH, TTL))


def earnings() -> pd.Series:
    return parse_ons(fetch_json(AWE, TTL))


def bank_rate() -> pd.Series:
    return parse_boe(fetch(BOE, TTL))


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
                  sources=[LONDON, UK, CPIH], as_of=latest_date(lon["avg"]))
    a = lon["avg"].dropna()
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
                  sources=[LONDON], as_of=latest_date(lon["avg"]))
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
        w = earnings()
        annual = (w * 52).reindex(avg.index, method="ffill")
        return _pts((avg / annual).dropna(), 2)

    def mortgage():
        """Illustrative monthly payment on 75% of the London average price, 25 years, at Bank Rate + 1.5 points (a typical margin, not a quote)."""
        rate = _month_steps(bank_rate()).reindex(avg.index, method="ffill") / 100 + 0.015
        r = rate / 12
        n = 25 * 12
        pay = avg * 0.75 * r / (1 - (1 + r) ** -n)
        return _pts(pay.dropna(), 0)
    out = payload({"bank_rate": lambda: _pts(_month_steps(bank_rate()), 2), "price_to_earnings": ratio, "mortgage": mortgage,
                   "earnings_annual": lambda: _pts((earnings() * 52).dropna(), 0)},
                  sources=[LONDON, AWE, BOE], as_of=latest_date(avg))
    br = out.get("bank_rate") or []
    pe = out.get("price_to_earnings") or []
    out["now"] = {"bank_rate": br[-1][1] if br else None, "price_to_earnings": pe[-1][1] if pe else None,
                  "mortgage": out["mortgage"][-1][1] if out.get("mortgage") else None,
                  "pe_peak": max((p[1] for p in pe if p[1] is not None), default=None)}
    return out


def _cached_ep(name, fn):
    from ..cache import _cached
    return lambda: _cached(f"topic:housing:{name}", 6 * 3600, fn)


ENDPOINTS = {"prices": _cached_ep("prices", _prices_now), "market": _cached_ep("market", _market_now), "afford": _cached_ep("afford", _afford_now)}
