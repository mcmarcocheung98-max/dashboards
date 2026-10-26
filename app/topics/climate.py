"""Climate Signals (/climate): how fast are physical changes and their costs compounding?

temperature  global surface temperature anomaly against 1850-1900: NASA GISTEMP v4 (monthly, rebased from 1951-80 to its own 1880-1900
             mean), Copernicus ERA5 (Climate Pulse daily series; monthly means; the C3S offset of +0.88 °C from 1991-2020 to 1850-1900)
             and Met Office HadCRUT5 (monthly, rebased from 1961-90 to 1850-1900); the 1.5 °C line, 12-month means, the warming rate
             per decade and the year the 30-year trend reaches 1.5 °C
co2          Mauna Loa CO2, monthly and its yearly growth, and global methane (NOAA GML CSVs); fossil CO2 emissions for China, the US,
             the UK, Hong Kong and the world (Global Carbon Budget, through Our World in Data's CSV on GitHub)
sea          global mean sea level from satellite altimetry (NOAA STAR), tide gauges at New York (the Battery), Newlyn and Hong Kong
             (PSMSL monthly RLR files), Arctic and Antarctic sea-ice extent (NSIDC Sea Ice Index v3, daily)
heat         hot days, hot nights and calendar-day record highs and lows: Hong Kong Observatory (HKO open data, daily max/min since
             1884), London Heathrow and New York Central Park (NOAA NCEI GHCN-Daily via the Access Data Service), and Heathrow monthly
             mean maximum since 1948 (Met Office historic station data)
costs        insured natural-catastrophe losses (Swiss Re sigma), US billion-dollar disasters (NOAA NCEI, ended after 2024; the archive
             file when it answers, else the hand-entered counts), China's direct economic losses from natural disasters (Ministry of
             Emergency Management) and notable events in the US, UK, Hong Kong and China

Hand-entered (data/climate/*.csv): insured_losses, billion_dollar, china_losses, events. Every row cites a source; rows from memory say
verify in the note. READINGS() reads the cached tab payloads only; +1 means improving or cooler, -1 worsening.
"""
from __future__ import annotations

import re
from io import StringIO

import numpy as np
import pandas as pd

from ._base import DAY, _pts, _r, fetch, manual, manual_rows, manual_sources, payload
from . import Topic

SLUG = "climate"
TOPIC = Topic(SLUG, "Climate Signals",
              "Global temperature against the 1.5 °C line, CO₂, sea level and sea ice, hot days and record highs in Hong Kong, London and "
              "New York, and what disasters cost: how fast physical changes and their costs are compounding.",
              "climate", (("temperature", "Temperature"), ("co2", "CO₂"), ("sea", "Sea level & ice"), ("heat", "Local heat"), ("costs", "Costs")),
              ("temperature", "co2", "sea", "heat", "costs"), icon="globe", order=70)

TTL, WEEK = DAY, 7 * DAY
GISTEMP = "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv"
ERA5 = "https://sites.ecmwf.int/data/climatepulse/data/series/era5_daily_series_2t_global.csv"
ERA5_PI = 0.88          # C3S: 1991-2020 was 0.88 °C warmer than 1850-1900 (used for every ERA5 figure against pre-industrial)
HADCRUT = ("https://www.metoffice.gov.uk/hadobs/hadcrut5/data/HadCRUT.5.0.2.0/analysis/diagnostics/"
           "HadCRUT.5.0.2.0.analysis.summary_series.global.monthly.csv")
GML = "https://gml.noaa.gov/webdata/ccgg/trends/"
CO2_MM, CO2_GR, CH4_MM = GML + "co2/co2_mm_mlo.csv", GML + "co2/co2_gr_mlo.csv", GML + "ch4/ch4_mm_gl.csv"
OWID = "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv"
EMITTERS = ("China", "United States", "United Kingdom", "Hong Kong", "World")
NSIDC = "https://noaadata.apps.nsidc.org/NOAA/G02135/{h}/daily/data/{H}_seaice_extent_daily_v3.0.csv"
STAR = ["https://www.star.nesdis.noaa.gov/socd/lsa/SeaLevelRise/slr/slr_sla_gbl_free_txj1j2_90.csv",
        "https://www.star.nesdis.noaa.gov/socd/lsa/SeaLevelRise/slr/slr_sla_gbl_keep_txj1j2_90.csv"]
PSMSL = "https://psmsl.org/data/obtaining/rlr.monthly.data/{id}.rlrdata"
GAUGES = {"New York (Battery)": [12], "Newlyn (UK)": [202], "Hong Kong (Quarry Bay / North Point)": [333, 1799]}   # first with recent data wins
HKO = "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType={t}&rformat=csv&station=HKO"
NCEI = ("https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations={st}&dataTypes=TMAX,TMIN"
        "&startDate={a}-01-01&endDate={b}&format=csv&units=metric")
STATIONS = {"London": (["UKM00003772"], 1948), "New York": (["USW00094728"], 1869)}
HEATHROW = "https://www.metoffice.gov.uk/pub/data/weather/uk/climate/stationdata/heathrowdata.txt"
BILLIONS = ["https://www.ncei.noaa.gov/access/billions/events-US-1980-2024.csv"]
# a hot day by each city's own convention: HKO "very hot day" (max >= 33 °C) and "hot night" (min >= 28 °C); the Met Office's 30 °C;
# New York's 90 °F (32.2 °C)
HOT = {"Hong Kong": 33.0, "London": 30.0, "New York": 32.2}
HOT_NIGHT = {"Hong Kong": 28.0, "London": 20.0, "New York": 24.0}
CITIES = ("Hong Kong", "London", "New York")

SOURCES = [{"name": "NASA GISS Surface Temperature Analysis (GISTEMP v4)", "url": "https://data.giss.nasa.gov/gistemp/", "cadence": "monthly, mid-month"},
           {"name": "Copernicus Climate Change Service, ERA5 (Climate Pulse)", "url": "https://pulse.climate.copernicus.eu/", "cadence": "daily, 2-day lag"},
           {"name": "Met Office Hadley Centre HadCRUT5", "url": "https://www.metoffice.gov.uk/hadobs/hadcrut5/", "cadence": "monthly"},
           {"name": "NOAA Global Monitoring Laboratory: Mauna Loa CO₂, global CH₄", "url": "https://gml.noaa.gov/ccgg/trends/", "cadence": "monthly"},
           {"name": "Global Carbon Budget fossil CO₂ (Our World in Data CSV)", "url": "https://github.com/owid/co2-data", "cadence": "yearly, November"},
           {"name": "NOAA STAR Laboratory for Satellite Altimetry: global mean sea level", "url": "https://www.star.nesdis.noaa.gov/socd/lsa/SeaLevelRise/", "cadence": "about monthly"},
           {"name": "PSMSL tide gauges (monthly RLR)", "url": "https://psmsl.org/", "cadence": "yearly"},
           {"name": "NSIDC Sea Ice Index v3 (G02135)", "url": "https://nsidc.org/data/g02135", "cadence": "daily"},
           {"name": "Hong Kong Observatory climatological data (open data API)", "url": "https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf", "cadence": "daily"},
           {"name": "NOAA NCEI GHCN-Daily (Access Data Service): Central Park, Heathrow", "url": "https://www.ncei.noaa.gov/access/services/data/v1", "cadence": "daily"},
           {"name": "Met Office historic station data: Heathrow", "url": "https://www.metoffice.gov.uk/research/climate/maps-and-data/historic-station-data", "cadence": "monthly"},
           {"name": "NOAA NCEI Billion-Dollar Weather and Climate Disasters (1980-2024)", "url": "https://www.ncei.noaa.gov/access/billions/", "cadence": "ended 2025"},
           {"name": "Hand-entered: Swiss Re sigma, China MEM, notable events (see data/climate/README.md)", "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/climate", "cadence": "as published"}]
NOTES = ("Temperatures are anomalies against 1850-1900, the IPCC's pre-industrial baseline: each dataset is rebased to it (GISTEMP to its "
         "1880-1900 mean, since it starts in 1880). A single month or year above 1.5 °C is not the Paris threshold, which is a 20-year average. "
         "Contains Met Office data © Crown copyright, Open Government Licence v3.0; Copernicus data © ECMWF; HKO data © HKSAR Government.")


# ------------------------------------------------------------------ parsers (text in, so tests can feed fixtures)
def parse_gistemp(text: str) -> pd.Series:
    """GLB.Ts+dSST.csv ('Year,Jan,...,Dec,J-D,...', missing '***') -> monthly anomaly Series (°C vs 1951-1980)."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(\d{4}),(.*)$", line)
        if not m:
            continue
        for k, v in enumerate(m.group(2).split(",")[:12]):
            try:
                out[pd.Timestamp(year=int(m.group(1)), month=k + 1, day=1)] = float(v)
            except ValueError:
                continue
    if len(out) < 24:
        raise ValueError("GISTEMP layout changed: no monthly rows")
    return pd.Series(out).sort_index()


def parse_era5(text: str) -> pd.Series:
    """Climate Pulse daily CSV ('#' comments, then date,2t,clim_91-20,ano_91-20,status or similar) -> daily anomaly vs 1850-1900."""
    d = pd.read_csv(StringIO(text), comment="#")
    d.columns = [str(c).strip().lower() for c in d.columns]
    t = pd.to_datetime(d[d.columns[0]], errors="coerce")
    pi = next((c for c in d.columns if "ano" in c and ("pi" in c or "1850" in c)), None)
    ano = next((c for c in d.columns if "ano" in c and "91" in c), None)
    if pi:
        v = pd.to_numeric(d[pi], errors="coerce")
    elif ano:
        v = pd.to_numeric(d[ano], errors="coerce") + ERA5_PI
    elif {"2t", "clim_91-20"} <= set(d.columns):
        v = pd.to_numeric(d["2t"], errors="coerce") - pd.to_numeric(d["clim_91-20"], errors="coerce") + ERA5_PI
    else:
        raise ValueError(f"ERA5 layout changed: columns {list(d.columns)[:6]}")
    s = pd.Series(v.to_numpy(), index=t)
    s = s[s.index.notna()].dropna().sort_index()
    if s.empty:
        raise ValueError("ERA5: no values")
    return s[~s.index.duplicated(keep="last")]


def parse_hadcrut(text: str) -> pd.Series:
    """HadCRUT5 summary CSV ('Time,Anomaly (deg C),Lower...,Upper...', Time '1850-01') -> monthly Series (°C vs 1961-1990)."""
    m = re.findall(r"^\s*(\d{4})-(\d{2}),\s*(-?[\d.]+)", text, flags=re.M)
    if not m:
        raise ValueError("HadCRUT5 layout changed: no 'YYYY-MM,value' rows")
    return pd.Series({pd.Timestamp(year=int(y), month=int(mo), day=1): float(v) for y, mo, v in m}).sort_index()


def parse_gml_monthly(text: str) -> pd.DataFrame:
    """NOAA GML monthly CSV ('#' comments; year,month,decimal date,average,deseasonalized,... or year,month,decimal,average,average_unc,
    trend,...) -> DataFrame [average, trend] by month. Missing values (-99.99, -9.99) are dropped."""
    d = pd.read_csv(StringIO(text), comment="#")
    d.columns = [str(c).strip().lower() for c in d.columns]
    t = pd.to_datetime({"year": d["year"], "month": d["month"], "day": 1}, errors="coerce")
    trend = next((c for c in d.columns if c in ("deseasonalized", "trend")), None)
    out = pd.DataFrame({"average": pd.to_numeric(d["average"], errors="coerce").to_numpy(),
                        "trend": pd.to_numeric(d[trend], errors="coerce").to_numpy() if trend else np.nan}, index=t)
    out = out[out.index.notna()].where(out > 0)
    out = out.dropna(how="all").sort_index()
    if out.empty:
        raise ValueError("NOAA GML: no monthly rows")
    return out


def parse_gml_growth(text: str) -> pd.Series:
    """co2_gr_mlo.csv ('#' comments; year,ann inc,unc) -> yearly growth, ppm a year, dated 1 January."""
    d = pd.read_csv(StringIO(text), comment="#")
    d.columns = [str(c).strip().lower() for c in d.columns]
    col = next(c for c in d.columns if c != "year" and "unc" not in c)
    s = pd.Series(pd.to_numeric(d[col], errors="coerce").to_numpy(), index=pd.to_datetime(d["year"].astype(int).astype(str) + "-01-01"))
    return s.dropna().sort_index()


def parse_owid(text: str) -> dict[str, pd.DataFrame]:
    """OWID co2-data CSV -> {country: DataFrame[co2 (Mt), co2_per_capita (t)] by year} for EMITTERS."""
    d = pd.read_csv(StringIO(text), usecols=lambda c: c in ("country", "year", "co2", "co2_per_capita"))
    d = d[d["country"].isin(EMITTERS)]
    out = {}
    for c, g in d.groupby("country"):
        g = g.set_index(pd.to_datetime(g["year"].astype(int).astype(str) + "-01-01"))[["co2", "co2_per_capita"]].apply(pd.to_numeric, errors="coerce")
        g = g.dropna(how="all").sort_index()
        if len(g):
            out[c] = g
    if not out:
        raise ValueError("OWID CO2: none of the countries found")
    return out


def parse_nsidc(text: str) -> pd.Series:
    """Sea Ice Index daily CSV ('Year, Month, Day, Extent, Missing, Source Data' + a units row) -> daily extent, million km²."""
    m = re.findall(r"^\s*(\d{4}),\s*(\d{1,2}),\s*(\d{1,2}),\s*([\d.]+)", text, flags=re.M)
    if not m:
        raise ValueError("NSIDC layout changed: no daily rows")
    s = pd.Series({pd.Timestamp(year=int(y), month=int(mo), day=int(dd)): float(v) for y, mo, dd, v in m}).sort_index()
    return s[s > 0]


def parse_star(text: str) -> pd.Series:
    """NOAA STAR GMSL CSV ('year,TOPEX/Poseidon,Jason-1,...', one column per mission) -> Series (mm) on decimal-year dates, the mean
    of the missions reporting at each time (they are cross-calibrated)."""
    out = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if not parts or not re.match(r"^\d{4}(\.\d+)?$", parts[0]):
            continue
        vals = [float(p) for p in parts[1:] if re.match(r"^-?\d+(\.\d+)?$", p)]
        if vals:
            out[_decimal_year(float(parts[0]))] = float(np.mean(vals))
    if len(out) < 12:
        raise ValueError("NOAA STAR layout changed: no 'year,value' rows")
    s = pd.Series(out).sort_index()
    return s[~s.index.duplicated(keep="last")]


def _decimal_year(y: float) -> pd.Timestamp:
    year = int(y)
    start = pd.Timestamp(year=year, month=1, day=1)
    return (start + pd.Timedelta(days=(y - year) * (pd.Timestamp(year=year + 1, month=1, day=1) - start).days)).normalize()


def parse_psmsl(text: str) -> pd.Series:
    """PSMSL monthly RLR file ('1856.0417;  -99999;00;000') -> monthly Series, mm (on the RLR datum, about 7000 mm)."""
    m = re.findall(r"^\s*(\d{4}\.\d+);\s*(-?\d+);", text, flags=re.M)
    s = pd.Series({_decimal_year(float(t)).replace(day=1): float(v) for t, v in m if int(v) > -99999})
    if s.empty:
        raise ValueError("PSMSL: no monthly values")
    return s.sort_index()


def parse_hko(text: str) -> pd.Series:
    """HKO CLMMAXT / CLMMINT CSV (bilingual header; rows 'year,month,day,value,completeness'; '***' missing) -> daily Series, °C."""
    m = re.findall(r'^\s*"?(\d{4})"?,\s*"?(\d{1,2})"?,\s*"?(\d{1,2})"?,\s*"?(-?\d+(?:\.\d+)?)"?', text, flags=re.M)
    if not m:
        raise ValueError("HKO layout changed: no daily rows")
    return pd.Series({pd.Timestamp(year=int(y), month=int(mo), day=int(d)): float(v) for y, mo, d, v in m}).sort_index()


def parse_ncei(text: str) -> pd.DataFrame:
    """Access Data Service CSV ("STATION","DATE","TMAX","TMIN"; units=metric gives °C) -> daily DataFrame [tmax, tmin]."""
    d = pd.read_csv(StringIO(text), skipinitialspace=True)
    d.columns = [str(c).strip().upper() for c in d.columns]
    if "DATE" not in d or "TMAX" not in d:
        raise ValueError(f"NCEI layout changed: columns {list(d.columns)[:6]}")
    out = pd.DataFrame({"tmax": pd.to_numeric(d["TMAX"], errors="coerce").to_numpy(),
                        "tmin": pd.to_numeric(d["TMIN"], errors="coerce").to_numpy() if "TMIN" in d else np.nan},
                       index=pd.to_datetime(d["DATE"], errors="coerce"))
    out = out[out.index.notna()].dropna(how="all").sort_index()
    if out.empty:
        raise ValueError("NCEI: no daily values")
    return out[~out.index.duplicated(keep="last")]


def parse_metoffice_station(text: str) -> pd.Series:
    """Met Office historic station file ('yyyy  mm   tmax    tmin ...', estimates marked '*') -> monthly mean daily maximum, °C."""
    m = re.findall(r"^\s*(\d{4})\s+(\d{1,2})\s+(-?\d+(?:\.\d+)?)\*?\s", text, flags=re.M)
    if not m:
        raise ValueError("Met Office station layout changed: no monthly rows")
    return pd.Series({pd.Timestamp(year=int(y), month=int(mo), day=1): float(v) for y, mo, v in m}).sort_index()


def parse_billions(text: str) -> pd.DataFrame:
    """NCEI billion-dollar events CSV (title lines, then Name,Disaster,Begin Date,End Date,CPI-Adjusted Cost,...; dates YYYYMMDD, costs
    in $ millions) -> yearly DataFrame [count, cost ($bn, CPI-adjusted)]."""
    lines = text.splitlines()
    head = next((i for i, l in enumerate(lines) if "Begin Date" in l), None)
    if head is None:
        raise ValueError("NCEI billions layout changed: no 'Begin Date' header")
    d = pd.read_csv(StringIO("\n".join(lines[head:])))
    d.columns = [str(c).strip() for c in d.columns]
    t = pd.to_datetime(d["Begin Date"].astype(str).str[:8], format="%Y%m%d", errors="coerce")
    cost = next((c for c in d.columns if c.lower().startswith("cpi")), None)
    d = pd.DataFrame({"year": t.dt.year, "cost": pd.to_numeric(d[cost], errors="coerce") / 1000 if cost else np.nan}).dropna(subset=["year"])
    g = d.groupby("year").agg(count=("year", "size"), cost=("cost", "sum"))
    g.index = pd.to_datetime(g.index.astype(int).astype(str) + "-12-31")       # year-end, like the hand-entered yearly rows
    return g


# ------------------------------------------------------------------ data
def _rebase(s: pd.Series, a: int, b: int) -> pd.Series:
    base = s[(s.index.year >= a) & (s.index.year <= b)]
    return s - base.mean() if len(base) else s


def gistemp() -> pd.Series:
    """Monthly anomaly, °C, rebased to GISTEMP's own 1880-1900 mean (it starts in 1880, so that stands in for 1850-1900)."""
    return _rebase(parse_gistemp(fetch(GISTEMP, TTL, min_bytes=1000)), 1880, 1900)


def era5_daily() -> pd.Series:
    return parse_era5(fetch(ERA5, TTL, timeout=90, min_bytes=1000))


def hadcrut() -> pd.Series:
    return _rebase(parse_hadcrut(fetch(HADCRUT, TTL, min_bytes=1000)), 1850, 1900)


def co2() -> pd.DataFrame:
    return parse_gml_monthly(fetch(CO2_MM, TTL, min_bytes=1000))


def co2_growth() -> pd.Series:
    return parse_gml_growth(fetch(CO2_GR, TTL, min_bytes=200))


def ch4() -> pd.DataFrame:
    return parse_gml_monthly(fetch(CH4_MM, TTL, min_bytes=1000))


def emissions() -> dict[str, pd.DataFrame]:
    """The OWID file is ~14 MB: parsed once a day, not on every call."""
    from ..cache import _cached
    return _cached(f"topic:{SLUG}:owid", DAY, lambda: parse_owid(fetch(OWID, WEEK, timeout=120, min_bytes=100000)))


def sea_ice(h: str) -> pd.Series:
    return parse_nsidc(fetch(NSIDC.format(h=h, H=h[0].upper()), TTL, timeout=90, min_bytes=1000))


def gmsl() -> pd.Series:
    last = None
    for u in STAR:
        try:
            return parse_star(fetch(u, TTL, min_bytes=500))
        except Exception as e:
            last = e
    raise last


def gauge(name: str) -> pd.Series:
    """The first PSMSL station for `name` with data in the last six years, else the longest that answered."""
    found, last = [], None
    for sid in GAUGES[name]:
        try:
            s = parse_psmsl(fetch(PSMSL.format(id=sid), WEEK, min_bytes=200))
            if s.index[-1].year >= pd.Timestamp.now().year - 6:
                return s
            found.append(s)
        except Exception as e:
            last = e
    if found:
        return max(found, key=len)
    raise last or ValueError(f"PSMSL: nothing for {name}")


def hko(kind: str) -> pd.Series:
    return parse_hko(fetch(HKO.format(t={"max": "CLMMAXT", "min": "CLMMINT"}[kind]), TTL, timeout=90, min_bytes=1000))


def station(city: str) -> pd.DataFrame:
    """Daily tmax / tmin for a city: HKO for Hong Kong, NCEI GHCN-Daily for London and New York (first station id that answers)."""
    if city == "Hong Kong":
        mx = hko("max")
        try:
            mn = hko("min")
        except Exception:
            mn = pd.Series(dtype=float)
        return pd.concat([mx, mn], axis=1, keys=["tmax", "tmin"]).sort_index()
    ids, start = STATIONS[city]
    last = None
    for st in ids:
        try:
            return parse_ncei(fetch(ncei_url(city, st), TTL, timeout=150, min_bytes=1000))
        except Exception as e:
            last = e
    raise last


def ncei_url(city: str, st: str | None = None) -> str:
    """The station's whole record; the end date is the end of this year, so the URL (and its disk snapshot) stays the same all year."""
    ids, start = STATIONS[city]
    return NCEI.format(st=st or ids[0], a=start, b=f"{pd.Timestamp.now().year}-12-31")


def heathrow_monthly() -> pd.Series:
    return parse_metoffice_station(fetch(HEATHROW, WEEK, min_bytes=1000))


def hand(name: str) -> dict[str, pd.Series]:
    m = manual(SLUG, name)
    return m if isinstance(m, dict) else ({"value": m} if len(m) else {})


def billion_dollar() -> tuple[pd.DataFrame, str]:
    """Yearly count and CPI-adjusted cost of US billion-dollar disasters: NCEI's archive file when it answers, else the hand-entered
    counts (data/climate/billion_dollar.csv). Returns (frame, where it came from)."""
    for u in BILLIONS:
        try:
            g = parse_billions(fetch(u, WEEK, min_bytes=1000))
            if len(g) >= 20:
                return g, u
        except Exception:
            continue
    h = hand("billion_dollar")
    if not h:
        raise ValueError("no billion-dollar disaster counts: NCEI unreachable and data/climate/billion_dollar.csv empty")
    return pd.DataFrame({"count": h.get("count", pd.Series(dtype=float)), "cost": h.get("cost", pd.Series(dtype=float))}), "hand-entered"


# ------------------------------------------------------------------ calculations
def monthly_mean(s: pd.Series) -> pd.Series:
    """Daily -> calendar-month means, months with at least 25 days (so the running month is left out until it is nearly complete)."""
    s = s.dropna()
    g = s.resample("MS")
    m = g.mean()
    return m[g.count() >= 25].dropna()


def annual(s: pd.Series, how: str = "mean", min_n: int = 12) -> pd.Series:
    g = s.dropna().resample("YS")
    v = getattr(g, how)()
    return v[g.count() >= min_n].dropna()


def trend_per_decade(s: pd.Series, years: int) -> float | None:
    """OLS slope of a yearly series over its last `years` points, per decade."""
    s = s.dropna().iloc[-years:]
    if len(s) < max(5, years // 2):
        return None
    x = s.index.year.to_numpy(dtype=float)
    return float(np.polyfit(x, s.to_numpy(dtype=float), 1)[0] * 10)


def trend_crossing(s: pd.Series, level: float = 1.5, years: int = 30):
    """Year the straight-line trend through the last `years` yearly values reaches `level` (fractional year); None if it never does."""
    s = s.dropna().iloc[-years:]
    if len(s) < 10:
        return None
    a, b = np.polyfit(s.index.year.to_numpy(dtype=float), s.to_numpy(dtype=float), 1)
    return float((level - b) / a) if a > 0 else None


def rolling12(s: pd.Series) -> pd.Series:
    return s.rolling(12, min_periods=12).mean().dropna()


def doy_frame(s: pd.Series) -> pd.DataFrame:
    """Daily series -> columns year, doy (1-366, 29 Feb shares 28 Feb's slot moved on by one in leap years), value."""
    s = s.dropna()
    idx = pd.DatetimeIndex(s.index)
    doy = idx.dayofyear - ((idx.is_leap_year) & (idx.month > 2)).astype(int)
    return pd.DataFrame({"year": idx.year, "doy": doy, "v": s.to_numpy()})


def by_doy(s: pd.Series, years: list[int]) -> dict[str, list]:
    """{year: [[doy, value], ...]} for the given years."""
    f = doy_frame(s)
    return {str(y): [[int(d), _r(v, 3)] for d, v in zip(g["doy"], g["v"])] for y, g in f.groupby("year") if y in years}


def doy_band(s: pd.Series, a: int, b: int) -> list[list]:
    """Mean by day of year over years a..b: [[doy, mean], ...]."""
    f = doy_frame(s)
    f = f[(f["year"] >= a) & (f["year"] <= b)]
    m = f.groupby("doy")["v"].mean()
    return [[int(d), _r(v, 3)] for d, v in m.items()]


def same_day_vs(s: pd.Series, a: int, b: int):
    """Latest daily value against the a..b mean for that day of year: (date, value, normal)."""
    s = s.dropna()
    if s.empty:
        return None, None, None
    f = doy_frame(s)
    doy = int(f["doy"].iloc[-1])
    base = f[(f["year"] >= a) & (f["year"] <= b) & ((f["doy"] - doy).abs() <= 1)]["v"]
    return str(s.index[-1].date()), _r(s.iloc[-1], 3), _r(base.mean(), 3) if len(base) else None


def yearly_counts(s: pd.Series, threshold: float, min_days: int = 300) -> pd.Series:
    """Days a year at or above `threshold`, for years with at least `min_days` values (the running year is counted to date)."""
    s = s.dropna()
    g = (s >= threshold).groupby(s.index.year)
    n, c = g.size(), g.sum()
    now = pd.Timestamp.now().year
    keep = (n >= min_days) | (n.index == now)
    out = c[keep].astype(float)
    out.index = pd.to_datetime(out.index.astype(str) + "-01-01")
    return out


def records(s: pd.Series, high: bool = True, burn_in: int = 30) -> pd.Series:
    """Calendar-day records a year: days whose value beat (strictly) every earlier year's value for the same day. Counted from the
    station's first year + burn_in, so early years (which set records easily) are left out. 29 February is dropped."""
    s = s.dropna()
    s = s[~((s.index.month == 2) & (s.index.day == 29))]
    if s.empty:
        return pd.Series(dtype=float)
    v = s if high else -s
    md = s.index.month * 100 + s.index.day
    prior = v.groupby(md).transform(lambda x: x.cummax().shift())
    hit = (v > prior) & prior.notna()
    first = s.index.year.min() + burn_in
    out = hit.groupby(s.index.year).sum().astype(float)
    out = out[out.index >= first]
    out.index = pd.to_datetime(out.index.astype(str) + "-01-01")
    return out


def ytd_vs_normal(s: pd.Series, threshold: float, a: int = 1991, b: int = 2020):
    """Hot days this year so far against the a..b average to the same day of the year: (this year, normal, up to)."""
    s = s.dropna()
    if s.empty:
        return None, None, None
    f = doy_frame(s)
    last = s.index[-1]
    y, doy = last.year, int(f["doy"].iloc[-1])
    cur = int((f[(f["year"] == y)]["v"] >= threshold).sum())
    base = f[(f["year"] >= a) & (f["year"] <= b) & (f["doy"] <= doy)]
    per = base.groupby("year")["v"].apply(lambda v: (v >= threshold).sum())
    return cur, _r(per.mean(), 1) if len(per) >= 15 else None, str(last.date())


def log_trend(s: pd.Series):
    """Growth a year (%) of the log-linear trend through a yearly series, and the trend's value at each year."""
    s = s.dropna()
    s = s[s > 0]
    if len(s) < 5:
        return None, pd.Series(dtype=float)
    x = s.index.year.to_numpy(dtype=float)
    a, b = np.polyfit(x, np.log(s.to_numpy(dtype=float)), 1)
    return float((np.exp(a) - 1) * 100), pd.Series(np.exp(a * x + b), index=s.index)


def lean(x, tol: float = 0.0) -> int:
    """+1 / -1 / 0 from a 'how much better' number (positive = better), with a dead band of tol."""
    if x is None or not np.isfinite(x):
        return 0
    return 1 if x > tol else -1 if x < -tol else 0


# ------------------------------------------------------------------ endpoints
def _temperature_now() -> dict:
    sets, why = {}, {}

    def series():
        for name, fn in (("NASA GISTEMP", gistemp), ("Copernicus ERA5", lambda: monthly_mean(era5_daily())), ("Met Office HadCRUT5", hadcrut)):
            try:
                sets[name] = fn()
            except Exception as e:
                why[name] = type(e).__name__
        if not sets:
            raise ValueError("no temperature dataset answered: " + ", ".join(f"{k} ({v})" for k, v in why.items()))
        return {k: _pts(v, 3) for k, v in sets.items()}
    out = payload({"monthly": series}, sources=[GISTEMP, ERA5, HADCRUT])
    out["missing"] = why
    out["rolling"] = {k: _pts(rolling12(s), 3) for k, s in sets.items()}
    yearly = {k: annual(s) for k, s in sets.items()}
    out["annual"] = {k: _pts(s, 3) for k, s in yearly.items()}
    out["kpis"] = {}
    for k, s in sets.items():
        y = yearly[k]
        r12 = rolling12(s)
        out["kpis"][k] = {"month": str(s.index[-1].date())[:7], "latest": _r(s.iloc[-1], 2), "r12": _r(r12.iloc[-1], 2) if len(r12) else None,
                          "r12_prev": _r(r12.iloc[-13], 2) if len(r12) > 12 else None, "rate20": _r(trend_per_decade(y, 20), 3),
                          "rate_long": _r(trend_per_decade(y[(y.index.year >= 1970) & (y.index.year < 2000)], 30), 3),
                          "cross": _r(trend_crossing(y), 1), "warmest": int(y.idxmax().year) if len(y) else None,
                          "warmest_v": _r(y.max(), 2) if len(y) else None, "yoy": _r(s.iloc[-1] - s.iloc[-13], 2) if len(s) > 12 else None}
    try:
        d = era5_daily()
        now = d.index[-1].year
        top = annual(d, min_n=360).sort_values().index.year[-3:].tolist()
        out["daily"] = {"years": by_doy(d, sorted({now, now - 1, *top})), "normal": doy_band(d, 1991, 2020), "now": now, "last": str(d.index[-1].date()),
                        "above15": int((d[d.index.year == now] >= 1.5).sum()), "days": int((d.index.year == now).sum())}
    except Exception as e:
        out["daily"], out["daily_error"] = None, type(e).__name__
    main = next((k for k in ("Copernicus ERA5", "NASA GISTEMP", "Met Office HadCRUT5") if k in out["kpis"]), None)
    out["main"] = main
    out["as_of"] = max((v["month"] for v in out["kpis"].values()), default=None)
    rows = []
    if main:
        k = out["kpis"][main]
        rows += [{"tab": "temperature", "key": "t_r12", "label": f"Last 12 months vs 1850-1900 ({main})", "value": k["r12"],
                  "lean": lean(None if k["r12"] is None else 1.5 - k["r12"]), "note": "above 1.5 °C reads -1"},
                 {"tab": "temperature", "key": "t_r12_change", "label": "12-month mean, change on a year earlier",
                  "value": _r(k["r12"] - k["r12_prev"], 2) if None not in (k["r12"], k["r12_prev"]) else None,
                  "lean": lean(None if None in (k["r12"], k["r12_prev"]) else k["r12_prev"] - k["r12"], 0.03)},
                 {"tab": "temperature", "key": "t_month_yoy", "label": f"Latest month ({k['month']}) vs the same month a year earlier", "value": k["yoy"],
                  "lean": lean(None if k["yoy"] is None else -k["yoy"], 0.05)},
                 {"tab": "temperature", "key": "t_rate20", "label": "Warming rate, last 20 years (°C a decade)", "value": k["rate20"],
                  "lean": lean(None if k["rate20"] is None else 0.2 - k["rate20"], 0.03), "note": "against the IPCC's ~0.2 °C a decade"}]
    out["readings"] = rows
    return out


def _co2_now() -> dict:
    def mlo():
        c = co2()
        return {"average": _pts(c["average"], 2), "trend": _pts(c["trend"], 2)}

    def growth12(df):
        t = df["trend"].dropna()
        return (t - t.shift(12)).dropna()

    def emis():
        e = emissions()
        return {k: {"co2": _pts(v["co2"], 1), "per_capita": _pts(v["co2_per_capita"], 2)} for k, v in e.items()}
    out = payload({"mlo": mlo, "growth": lambda: _pts(co2_growth(), 2), "growth12": lambda: _pts(growth12(co2()), 2),
                   "ch4": lambda: {"average": _pts(ch4()["average"], 1), "trend": _pts(ch4()["trend"], 1)},
                   "ch4_growth12": lambda: _pts(growth12(ch4()), 2), "emissions": emis},
                  sources=[CO2_MM, CO2_GR, CH4_MM, OWID])
    rows, k = [], {}
    try:
        c = co2()
        g = growth12(c)
        gy = co2_growth()
        dec = gy[gy.index.year >= gy.index.year.max() - 9]
        k.update(ppm=_r(c["average"].iloc[-1], 2), month=str(c.index[-1].date())[:7], growth12=_r(g.iloc[-1], 2), growth10=_r(dec.mean(), 2),
                 growth_1960s=_r(gy[(gy.index.year >= 1960) & (gy.index.year < 1970)].mean(), 2), ppm_yago=_r(c["average"].iloc[-13], 2) if len(c) > 12 else None,
                 last_year=int(gy.index[-1].year), last_growth=_r(gy.iloc[-1], 2))
        rows.append({"tab": "co2", "key": "co2_growth", "label": "Mauna Loa CO₂ growth, last 12 months vs the 10-year average (ppm a year)",
                     "value": k["growth12"], "lean": lean(k["growth10"] - k["growth12"], 0.15), "note": f"10-year average {k['growth10']}"})
        rows.append({"tab": "co2", "key": "co2_ppm", "label": f"Mauna Loa CO₂ ({k['month']}), ppm", "value": k["ppm"], "lean": -1 if k["growth12"] > 0 else 1})
    except Exception as e:
        k["error"] = type(e).__name__
    try:
        m = ch4()
        g = growth12(m)
        ten = g[g.index >= g.index[-1] - pd.DateOffset(years=10)]
        k.update(ch4=_r(m["average"].iloc[-1], 1), ch4_month=str(m.index[-1].date())[:7], ch4_growth12=_r(g.iloc[-1], 2), ch4_growth10=_r(ten.mean(), 2))
        rows.append({"tab": "co2", "key": "ch4_growth", "label": "Global methane growth, last 12 months vs the 10-year average (ppb a year)",
                     "value": k["ch4_growth12"], "lean": lean(k["ch4_growth10"] - k["ch4_growth12"], 1.0)})
    except Exception:
        pass
    try:
        e = emissions()
        for name, key in (("China", "china"), ("World", "world"), ("United States", "us")):
            s = e[name]["co2"].dropna()
            ch = (s.iloc[-1] / s.iloc[-2] - 1) * 100
            k[f"{key}_co2"], k[f"{key}_chg"], k[f"{key}_year"] = _r(s.iloc[-1], 0), _r(ch, 2), int(s.index[-1].year)
            rows.append({"tab": "co2", "key": f"emis_{key}", "label": f"{name} fossil CO₂, change in {s.index[-1].year} (%)", "value": _r(ch, 2), "lean": lean(-ch, 0.25)})
        w, cn = e["World"]["co2"].dropna(), e["China"]["co2"].dropna()
        k["china_share"] = _r(cn.iloc[-1] / w.reindex(cn.index).iloc[-1] * 100, 1)
    except Exception:
        pass
    out["kpis"] = k
    out["readings"] = rows
    out["as_of"] = k.get("month")
    return out


def _sea_now() -> dict:
    ice, gauges, why = {}, {}, {}

    def ice_part():
        o = {}
        for h in ("north", "south"):
            try:
                ice[h] = sea_ice(h)
            except Exception as e:
                why[h] = type(e).__name__
                continue
            s = ice[h]
            now = s.index[-1].year
            mn = s[s.index.year < now].groupby(s.index.year[s.index.year < now]).min()
            mn = mn[(mn.index > 1978)]
            mn.index = pd.to_datetime(mn.index.astype(str) + "-01-01")
            o[h] = {"daily": _pts(s[s.index >= "1979-01-01"].resample("MS").mean().dropna(), 3), "min": _pts(mn, 3),
                    "years": by_doy(s, [now, now - 1, int(mn.idxmin().year) if len(mn) else now - 2]),
                    "normal": doy_band(s, 1981, 2010), "recent": doy_band(s, 2011, 2020), "now": now}
        if not o:
            raise ValueError("NSIDC unreachable")
        return o

    def gauge_part():
        for name in GAUGES:
            try:
                s = gauge(name)
                y = annual(s, min_n=10)
                gauges[name] = y - y[(y.index.year >= 1991) & (y.index.year <= 2020)].mean()
            except Exception as e:
                why[name] = type(e).__name__
        if not gauges:
            raise ValueError("PSMSL unreachable")
        return {k: _pts(v, 0) for k, v in gauges.items()}
    out = payload({"gmsl": lambda: _pts(gmsl(), 1), "ice": ice_part, "gauges": gauge_part},
                  sources=[*STAR, NSIDC.format(h="north", H="N"), NSIDC.format(h="south", H="S"), PSMSL.format(id=12)])
    out["missing"] = why
    k, rows = {}, []
    try:
        g = gmsl()
        ann = annual(g, min_n=10)
        last10 = trend_per_decade(ann[ann.index.year < pd.Timestamp.now().year], 10)
        prev10 = trend_per_decade(ann[ann.index.year < pd.Timestamp.now().year - 10], 10)
        all_ = trend_per_decade(ann, 60)
        k.update(gmsl=_r(g.iloc[-1], 1), gmsl_date=str(g.index[-1].date()), rate10=_r(last10 / 10 if last10 else None, 2),
                 rate_prev10=_r(prev10 / 10 if prev10 else None, 2), rate_all=_r(all_ / 10 if all_ else None, 2),
                 since1993=_r(rolling12(g).iloc[-1] - g.iloc[:12].mean(), 0) if len(g) > 24 else None)
        rows.append({"tab": "sea", "key": "gmsl_rate", "label": "Global sea level: rise a year over the last 10 years (mm)", "value": k["rate10"],
                     "lean": lean(None if None in (k["rate10"], k["rate_prev10"]) else k["rate_prev10"] - k["rate10"], 0.3),
                     "note": f"the 10 years before: {k['rate_prev10']} mm a year"})
    except Exception:
        pass
    for h, label in (("north", "Arctic"), ("south", "Antarctic")):
        if h in ice:
            t, v, recent = same_day_vs(ice[h], 2011, 2020)
            _, _, normal = same_day_vs(ice[h], 1981, 2010)
            k[h] = {"date": t, "v": v, "recent": recent, "normal": normal}
            rows.append({"tab": "sea", "key": f"ice_{h}", "label": f"{label} sea-ice extent vs the 2011-2020 average for the date (million km²)",
                         "value": _r(v - recent, 2) if None not in (v, recent) else None, "lean": lean(None if None in (v, recent) else v - recent, 0.1)})
    for name, s in gauges.items():
        r = trend_per_decade(s[s.index.year >= 1993], 40)
        rl = trend_per_decade(s, 200)
        k.setdefault("gauges", {})[name] = {"since1993": _r(r / 10 if r else None, 1), "full": _r(rl / 10 if rl else None, 1),
                                            "from": int(s.index[0].year), "to": int(s.index[-1].year)}
    out["kpis"] = k
    out["readings"] = rows
    out["as_of"] = max([v["date"] for h, v in k.items() if h in ("north", "south") and v.get("date")] + ([k["gmsl_date"]] if "gmsl_date" in k else []), default=None)
    return out


def _city(city: str) -> dict:
    d = station(city)
    tx = d["tmax"].dropna()
    tn = d["tmin"].dropna() if "tmin" in d else pd.Series(dtype=float)
    now = pd.Timestamp.now().year
    hi, lo = records(tx), records(tn, high=False) if len(tn) else pd.Series(dtype=float)
    ratio = pd.Series(dtype=float)
    if len(hi) and len(lo):
        j = pd.concat([hi, lo], axis=1, keys=["h", "l"]).dropna()
        j = j[j.index.year < now]
        r = j.rolling(10, min_periods=10).sum()
        ratio = (r["h"] / (r["h"] + r["l"]).replace(0, np.nan) * 100).dropna()     # share of records that were highs; 50 in a stable climate
    mean_max = annual(tx, min_n=300)
    cur, normal, upto = ytd_vs_normal(tx, HOT[city])
    nights = yearly_counts(tn, HOT_NIGHT[city]) if len(tn) else pd.Series(dtype=float)
    last365 = tx.index[-1] - pd.Timedelta(days=365)
    h365 = _records_since(tx, last365, True)
    l365 = _records_since(tn, last365, False) if len(tn) else None
    return {"hot": _pts(yearly_counts(tx, HOT[city]), 0), "nights": _pts(nights, 0), "rec_hi": _pts(hi, 0), "rec_lo": _pts(lo, 0),
            "ratio": _pts(ratio, 1), "mean_max": _pts(mean_max[mean_max.index.year < now], 2), "threshold": HOT[city], "night_threshold": HOT_NIGHT[city],
            "ytd": cur, "ytd_normal": normal, "upto": upto, "from": int(tx.index[0].year), "rec365": [h365, l365],
            "hottest": {"v": _r(tx.max(), 1), "date": str(tx.idxmax().date())}}


def _records_since(s: pd.Series, since: pd.Timestamp, high: bool) -> int | None:
    s = s.dropna()
    s = s[~((s.index.month == 2) & (s.index.day == 29))]
    if s.index.year.min() + 30 > since.year:
        return None
    v = s if high else -s
    md = s.index.month * 100 + s.index.day
    prior = v.groupby(md).transform(lambda x: x.cummax().shift())
    return int(((v > prior) & prior.notna() & (s.index > since)).sum())


def _heat_now() -> dict:
    parts = {c: (lambda c=c: _city(c)) for c in CITIES}
    parts["heathrow"] = lambda: _pts(annual(heathrow_monthly())[lambda s: s.index.year < pd.Timestamp.now().year], 2)
    out = payload(parts, sources=[HKO.format(t="CLMMAXT"), HKO.format(t="CLMMINT"), HEATHROW] + [ncei_url(c) for c in STATIONS])
    rows = []
    for c in CITIES:
        d = out.get(c) or {}
        if d.get("ytd") is not None and d.get("ytd_normal") is not None:
            diff = d["ytd"] - d["ytd_normal"]
            rows.append({"tab": "heat", "key": f"hot_{c}", "label": f"{c}: hot days this year (≥{d['threshold']} °C) vs the 1991-2020 average to date",
                         "value": d["ytd"], "lean": lean(-diff, max(1.0, 0.15 * d["ytd_normal"])), "note": f"average {d['ytd_normal']} to {d['upto'][5:]}"})
        h, l = (d.get("rec365") or [None, None])
        if h is not None and l is not None:
            rows.append({"tab": "heat", "key": f"rec_{c}", "label": f"{c}: record highs vs record lows, last 365 days", "value": f"{h}:{l}",
                         "lean": lean(l - h, 0)})
    out["readings"] = rows
    out["as_of"] = max([(out.get(c) or {}).get("upto") or "" for c in CITIES]) or None
    return out


def _costs_now() -> dict:
    src = {}

    def insured():
        h = hand("insured_losses")
        o = {k: _pts(v, 1) for k, v in h.items()}
        g, tr = log_trend(h.get("nat cat", pd.Series(dtype=float)))
        src["insured_growth"], src["insured_trend"] = _r(g, 2), tr
        o["trend"] = _pts(tr, 1)
        return o

    def billions():
        g, where = billion_dollar()
        src["billions_from"] = where
        src["billions"] = g
        return {"count": _pts(g["count"], 0), "cost": _pts(g["cost"].dropna(), 1)}
    out = payload({"insured": insured, "billions": billions, "china": lambda: _pts(hand("china_losses").get("value", pd.Series(dtype=float)), 1)},
                  sources=BILLIONS)
    out["billions_from"] = src.get("billions_from")
    out["insured_growth"] = src.get("insured_growth")
    out["events"] = sorted(manual_rows(SLUG, "events"), key=lambda r: r["date"], reverse=True)
    out["cites"] = {n: manual_sources(SLUG, n) for n in ("insured_losses", "billion_dollar", "china_losses", "events")}
    rows, k = [], {}
    nat = hand("insured_losses").get("nat cat", pd.Series(dtype=float))
    tr = src.get("insured_trend")
    if len(nat) and tr is not None and len(tr):
        k["insured"] = {"year": int(nat.index[-1].year), "v": _r(nat.iloc[-1], 0), "trend": _r(tr.iloc[-1], 0), "growth": out["insured_growth"]}
        rows.append({"tab": "costs", "key": "insured_vs_trend", "label": f"Insured nat-cat losses {nat.index[-1].year} vs their trend ($bn)",
                     "value": _r(nat.iloc[-1], 0), "lean": lean((tr.iloc[-1] - nat.iloc[-1]) / tr.iloc[-1], 0.1), "note": f"trend {_r(tr.iloc[-1], 0)}"})
    b = src.get("billions")
    if b is not None and len(b["count"].dropna()) > 10:
        c = b["count"].dropna()
        prev = c.iloc[-11:-1].mean()
        k["billions"] = {"year": int(c.index[-1].year), "n": int(c.iloc[-1]), "avg10": _r(prev, 1), "avg_1980s": _r(c[c.index.year < 1990].mean(), 1)}
        rows.append({"tab": "costs", "key": "billions", "label": f"US billion-dollar disasters in {c.index[-1].year} vs the 10 years before",
                     "value": int(c.iloc[-1]), "lean": lean(prev - c.iloc[-1], 2), "note": f"10-year average {_r(prev, 1)}"})
    cn = hand("china_losses").get("value", pd.Series(dtype=float))
    if len(cn) > 5:
        prev = cn.iloc[-6:-1].mean()
        k["china"] = {"year": int(cn.index[-1].year), "v": _r(cn.iloc[-1], 0), "avg5": _r(prev, 0)}
        rows.append({"tab": "costs", "key": "china_losses", "label": f"China direct disaster losses {cn.index[-1].year} vs the 5 years before (CN¥bn)",
                     "value": _r(cn.iloc[-1], 0), "lean": lean((prev - cn.iloc[-1]) / prev, 0.1)})
    out["kpis"] = k
    out["readings"] = rows
    out["as_of"] = max((r["date"] for r in manual_rows(SLUG, "insured_losses")), default=None)
    return out


def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, size, start of body), to check reachability and layouts from
    Railway. Read with Actions > show-json on /api/climate/layout."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    from ._base import UA
    y = pd.Timestamp.now().year
    urls = {"gistemp": GISTEMP, "era5": ERA5, "hadcrut": HADCRUT, "co2": CO2_MM, "co2 growth": CO2_GR, "ch4": CH4_MM, "owid": OWID,
            "nsidc north": NSIDC.format(h="north", H="N"), "heathrow monthly": HEATHROW, "hko max": HKO.format(t="CLMMAXT"), "hko min": HKO.format(t="CLMMINT")}
    urls.update({f"star {i}": u for i, u in enumerate(STAR)})
    urls.update({f"psmsl {sid}": PSMSL.format(id=sid) for ids in GAUGES.values() for sid in ids})
    urls.update({f"psmsl page {sid}": f"https://psmsl.org/data/obtaining/stations/{sid}.php" for ids in GAUGES.values() for sid in ids})
    urls.update({f"ncei {st}": NCEI.format(st=st, a=y, b=f"{y}-12-31") for ids, _ in STATIONS.values() for st in ids})
    urls.update({f"billions {i}": u for i, u in enumerate(BILLIONS)})

    def one(u):
        try:
            r = requests.get(u, headers=UA, timeout=40, stream=True)
            body = next(r.iter_content(4000), b"").decode("utf-8", "replace")
            r.close()
            return {"status": r.status_code, "bytes": r.headers.get("content-length"), "type": r.headers.get("content-type", ""), "start": body[:600]}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(urls, ex.map(one, urls.values())))


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"temperature": _cached_ep("temperature", _temperature_now), "co2": _cached_ep("co2", _co2_now), "sea": _cached_ep("sea", _sea_now),
             "heat": _cached_ep("heat", _heat_now), "costs": _cached_ep("costs", _costs_now), "layout": _cached_ep("layout", _layout_now, 1800)}


def READINGS() -> list[dict]:
    """Each tab's headline readings from the payloads the endpoints already cached (the warmer computes them just before the daily
    save); a tab not computed yet is left out rather than downloaded here."""
    from ..cache import _cache
    rows = []
    for t, _ in TOPIC.tabs:
        hit = _cache.get(f"topic:{SLUG}:{t}")
        if hit and isinstance(hit[1], dict):
            rows += [r for r in hit[1].get("readings") or [] if r.get("value") is not None]
    return rows
