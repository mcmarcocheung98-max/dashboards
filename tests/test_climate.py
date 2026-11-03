"""Climate Signals (/climate): parsers and payloads on fixtures shaped like each source; live checks are marked network."""
import numpy as np
import pandas as pd
import pytest

from app.topics import _base as B
from app.topics import climate as C

NOW = pd.Timestamp.now().normalize()


# ------------------------------------------------------------------ fixtures in each source's own layout
def _months(start: str):
    return pd.date_range(start, NOW - pd.DateOffset(months=1), freq="MS")


def gistemp_csv() -> str:
    rows = ["Land-Ocean: Global Means", "Year,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,J-D,D-N,DJF,MAM,JJA,SON"]
    for y in range(1880, NOW.year + 1):
        vals = []
        for m in range(1, 13):
            t = pd.Timestamp(year=y, month=m, day=1)
            vals.append("***" if t >= NOW - pd.DateOffset(months=1) else f"{-0.3 + 0.012 * max(0, y - 1900) + 0.05 * np.sin(m):.2f}")
        rows.append(f"{y}," + ",".join(vals) + ",***,***,***,***,***,***")
    return "\n".join(rows)


def era5_csv() -> str:
    days = pd.date_range("1940-01-01", NOW - pd.Timedelta(days=2))
    i = np.arange(len(days))
    ano = -0.6 + 0.0000700 * i + 0.1 * np.sin(i / 50)
    clim = 14 + 2 * np.sin(2 * np.pi * days.dayofyear / 365)
    head = "# Copernicus Climate Change Service\n# ERA5 daily global 2m temperature\ndate,2t,clim_91-20,ano_91-20,status\n"
    return head + "\n".join(f"{t:%Y-%m-%d},{c + a:.3f},{c:.3f},{a:.3f},final" for t, c, a in zip(days, clim, ano))


def hadcrut_csv() -> str:
    ms = _months("1850-01-01")
    return "Time,Anomaly (deg C),Lower confidence limit (2.5%),Upper confidence limit (97.5%)\n" + "\n".join(
        f"{t:%Y-%m},{-0.4 + 0.009 * max(0, t.year - 1900):.3f},-0.5,0.5" for t in ms)


def gml_csv(kind: str) -> str:
    ms = _months("1958-03-01" if kind == "co2" else "1983-07-01")
    if kind == "co2":
        head = "# NOAA GML Mauna Loa\nyear,month,decimal date,average,deseasonalized,ndays,sdev,unc\n"
        row = lambda i, t: f"{t.year},{t.month},{t.year + t.month / 12:.4f},{315 + 0.13 * i + 3 * np.sin(t.month):.2f},{315 + 0.13 * i:.2f},-1,-9.99,-0.99"
    else:
        head = "# NOAA GML global CH4\nyear,month,decimal,average,average_unc,trend,trend_unc\n"
        row = lambda i, t: f"{t.year},{t.month},{t.year + t.month / 12:.4f},{1640 + 0.6 * i + 5 * np.sin(t.month):.2f},1.0,{1640 + 0.6 * i:.2f},1.0"
    return head + "\n".join(row(i, t) for i, t in enumerate(ms))


def gml_growth_csv() -> str:
    return "# NOAA GML annual increase\nyear,ann inc,unc\n" + "\n".join(f"{y},{0.8 + 0.025 * (y - 1959):.2f},0.1" for y in range(1959, NOW.year))


def owid_csv() -> str:
    rows = ["country,year,iso_code,population,gdp,co2,co2_per_capita,methane"]
    base = {"China": (80, 0.1), "United States": (900, 7.0), "United Kingdom": (500, 10.0), "Hong Kong": (5, 1.0), "World": (6000, 2.0), "France": (300, 6)}
    for c, (b, pc) in base.items():
        for y in range(1900, NOW.year - 1):
            rows.append(f"{c},{y},X,1,,{b * (1 + 0.02 * (y - 1900)):.1f},{pc * (1 + 0.005 * (y - 1900)):.2f},")
    return "\n".join(rows)


def nsidc_csv(h: str) -> str:
    days = pd.date_range("1978-10-26", NOW - pd.Timedelta(days=1), freq="2D")
    i = np.arange(len(days))
    base = 11.5 if h == "north" else 11.0
    sign = 1 if h == "north" else -1
    ext = base + sign * 3.5 * np.cos(2 * np.pi * (days.dayofyear - 60) / 365) - 0.00006 * i
    return ("Year, Month, Day,     Extent,    Missing, Source Data\n YYYY,    MM,  DD, 10^6 sq km, 10^6 sq km, Source data product web sites\n" +
            "\n".join(f" {t.year},    {t.month:02d},    {t.day:02d},     {e:.3f},      0.000, ['https://x/nt_{t:%Y%m%d}.bin']" for t, e in zip(days, ext)))


def star_csv() -> str:
    days = pd.date_range("1993-01-01", NOW - pd.Timedelta(days=20), freq="10D")
    rows = ["# NOAA/NESDIS/STAR global mean sea level", "year,TOPEX/Poseidon,Jason-1,Jason-2,Jason-3,Sentinel-6MF"]
    for k, t in enumerate(days):
        y = t.year + (t.dayofyear - 1) / 365.25
        v = f"{-20 + 0.009 * k + 0.0000035 * k * k:.2f}"
        cols = ["", "", "", "", ""]
        cols[min(4, (t.year - 1993) // 7)] = v
        rows.append(f"{y:.4f}," + ",".join(cols))
    return "\n".join(rows)


def psmsl_txt(sid: int) -> str:
    start = {12: 1856, 202: 1915, 333: 1954, 1799: 1986}.get(sid, 1950)
    out = []
    for y in range(start, NOW.year):
        for m in range(1, 13):
            v = -99999 if (y, m) == (start, 1) else int(7000 + 3 * (y - start) + 40 * np.sin(m))
            out.append(f"{y + (m - 0.5) / 12:.4f};{v:8d};00;000")
    return "\n".join(out)


def _daily_temps(start: int, warm: float, amp: float, slope: float):
    days = pd.date_range(f"{start}-01-01", NOW - pd.Timedelta(days=1))
    k = np.arange(len(days))
    seas = amp * np.sin(2 * np.pi * (days.dayofyear - 110) / 365)
    noise = 3 * np.sin(k * 1.7) * np.cos(k * 0.31)
    tmax = warm + seas + noise + slope * (days.year - start)
    return days, tmax, tmax - 7


def hko_csv(kind: str) -> str:
    days, tmax, tmin = _daily_temps(1884, 26, 6, 0.02)
    v = tmax if kind == "CLMMAXT" else tmin + 3
    head = '"每日最高氣溫","Daily Maximum Temperature (degree Celsius) at the Hong Kong Observatory"\n年/Year,月/Month,日/Day,數值/Value,數據完整性/data Completeness\n'
    body = "\n".join(f"{t.year},{t.month},{t.day},{'***' if 1940 <= t.year <= 1946 else f'{x:.1f}'},{'' if 1940 <= t.year <= 1946 else 'C'}" for t, x in zip(days, v))
    return head + body + '\n"*** 沒有數據/unavailable",\n"C 數據完整/data Complete",'


def ncei_csv(st: str, start: int) -> str:
    warm, amp = (15, 7) if st.startswith("UK") else (17, 12)
    days, tmax, tmin = _daily_temps(max(start, 1973 if st.startswith("UK") else start), warm, amp, 0.025)
    return '"STATION","DATE","TMAX","TMIN"\n' + "\n".join(f'"{st}","{t:%Y-%m-%d}","{a:6.1f}","{b:6.1f}"' for t, a, b in zip(days, tmax, tmin))


def heathrow_txt() -> str:
    head = "Heathrow (London Airport)\nLocation 507800E 176700N, Lat 51.479 Lon -0.449, 25 metres amsl\n   yyyy  mm   tmax    tmin      af    rain     sun\n              degC    degC    days      mm   hours\n"
    return head + "\n".join(f"   {t.year}  {t.month:2d}   {14 + 7 * np.sin(t.month / 2) + 0.02 * (t.year - 1948):4.1f}{'*' if t.year == NOW.year else ''}     3.3    ---    85.0    ---"
                            for t in _months("1948-01-01"))


def billions_csv() -> str:
    rows = ["Billion-Dollar Weather and Climate Disasters: Events", "Name,Disaster,Begin Date,End Date,CPI-Adjusted Cost,Unadjusted Cost,Deaths"]
    for y in range(1980, 2025):
        for k in range(3 + (y - 1980) // 3):
            rows.append(f'"Storm {y}-{k}",Severe Storm,{y}0{1 + k % 9}15,{y}0{1 + k % 9}17,{1100 + 50 * k:.1f},{900 + 40 * k:.1f},1')
    return "\n".join(rows)


def fake_fetch(url, ttl=0, **k):
    if "GLB.Ts+dSST" in url:
        return gistemp_csv()
    if "climatepulse" in url:
        return era5_csv()
    if "hadcrut" in url:
        return hadcrut_csv()
    if "co2_mm_mlo" in url:
        return gml_csv("co2")
    if "ch4_mm_gl" in url:
        return gml_csv("ch4")
    if "co2_gr_mlo" in url:
        return gml_growth_csv()
    if "owid" in url:
        return owid_csv()
    if "nsidc" in url:
        return nsidc_csv("north" if "/north/" in url else "south")
    if "star.nesdis" in url:
        return star_csv()
    if "psmsl" in url:
        return psmsl_txt(int(url.rsplit("/", 1)[1].split(".")[0]))
    if "weather.gov.hk" in url:
        return hko_csv(url.split("dataType=")[1].split("&")[0])
    if "ncei.noaa.gov/access/services" in url:
        return ncei_csv(url.split("stations=")[1].split("&")[0], int(url.split("startDate=")[1][:4]))
    if "heathrowdata" in url:
        return heathrow_txt()
    if "billions" in url:
        return billions_csv()
    raise ConnectionError(f"fixture: no text for {url}")


def smoke_patch() -> None:
    """scripts/smoke.py: every climate source answered from the fixtures above."""
    C.fetch = fake_fetch


@pytest.fixture
def fixtures(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(C, "fetch", fake_fetch)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()


# ------------------------------------------------------------------ parsers
def test_gistemp_skips_missing_months_and_rebases_to_1880_1900():
    s = C.parse_gistemp(gistemp_csv())
    assert s.index[0] == pd.Timestamp("1880-01-01") and s.index[-1] < NOW
    assert not s.isna().any() and s.index[-1] >= NOW - pd.DateOffset(months=2)
    with pytest.raises(ValueError):
        C.parse_gistemp("Year,Jan\nnothing")


def test_era5_adds_the_pre_industrial_offset():
    s = C.parse_era5(era5_csv())
    assert s.index[0] == pd.Timestamp("1940-01-01")
    assert s.iloc[0] == pytest.approx(-0.6 + C.ERA5_PI, abs=1e-3)
    pi = C.parse_era5("# x\ndate,2t,ano_pi\n2024-01-01,14.0,1.61\n")       # a column against pre-industrial is used as is
    assert pi.iloc[0] == pytest.approx(1.61)
    with pytest.raises(ValueError):
        C.parse_era5("date,foo\n2024-01-01,1\n")


def test_gml_monthly_both_layouts_and_growth():
    co2, ch4 = C.parse_gml_monthly(gml_csv("co2")), C.parse_gml_monthly(gml_csv("ch4"))
    assert co2.index[0] == pd.Timestamp("1958-03-01") and co2["trend"].iloc[0] == pytest.approx(315)
    assert ch4["trend"].iloc[0] == pytest.approx(1640)
    g = C.parse_gml_growth(gml_growth_csv())
    assert g.index[0] == pd.Timestamp("1959-01-01") and g.iloc[0] == pytest.approx(0.8)


def test_owid_keeps_the_five_emitters():
    e = C.parse_owid(owid_csv())
    assert set(e) == set(C.EMITTERS)
    assert list(e["China"].columns) == ["co2", "co2_per_capita"]


def test_nsidc_star_psmsl_layouts():
    n = C.parse_nsidc(nsidc_csv("north"))
    assert n.index[0] == pd.Timestamp("1978-10-26") and 5 < n.iloc[0] < 16
    s = C.parse_star(star_csv())
    assert s.index[0].year == 1993 and s.iloc[0] == pytest.approx(-20)
    p = C.parse_psmsl(psmsl_txt(12))
    assert p.index[0] == pd.Timestamp("1856-02-01")          # the -99999 month is dropped
    assert C._decimal_year(2000.5).month in (6, 7)


def test_hko_ncei_metoffice_layouts():
    h = C.parse_hko(hko_csv("CLMMAXT"))
    assert h.index[0] == pd.Timestamp("1884-01-01") and not ((h.index.year >= 1940) & (h.index.year <= 1946)).any()
    n = C.parse_ncei(ncei_csv("USW00094728", 1869))
    assert list(n.columns) == ["tmax", "tmin"] and n.index[0] == pd.Timestamp("1869-01-01")
    m = C.parse_metoffice_station(heathrow_txt())
    assert m.index[0] == pd.Timestamp("1948-01-01") and m.index[-1].year == NOW.year or NOW.month == 1
    with pytest.raises(ValueError):
        C.parse_ncei('"STATION","DATE","PRCP"\n"x","2024-01-01","1"')


def test_billions_counts_by_year():
    g = C.parse_billions(billions_csv())
    assert g.index[0] == pd.Timestamp("1980-12-31") and g["count"].iloc[0] == 3
    assert g["cost"].iloc[0] == pytest.approx(1.1 + 1.15 + 1.2)


# ------------------------------------------------------------------ calculations
def test_records_count_only_beaten_days_after_burn_in():
    days = pd.date_range("1950-01-01", "2000-12-31")
    s = pd.Series(10.0, index=days)
    s[s.index.year == 1999] = 11.0                   # every day of 1999 a record, 2000 ties nothing
    s[s.index.year == 2000] = 11.0
    r = C.records(s, burn_in=30)
    assert r.index[0] == pd.Timestamp("1980-01-01")
    assert r[pd.Timestamp("1999-01-01")] == 365 and r[pd.Timestamp("2000-01-01")] == 0 and r[pd.Timestamp("1990-01-01")] == 0
    lo = C.records(-s, high=False)
    assert lo[pd.Timestamp("1999-01-01")] == 365


def test_hot_days_ytd_and_trend_helpers():
    days = pd.date_range("1990-01-01", NOW - pd.Timedelta(days=1))
    s = pd.Series(np.where(days.year == NOW.year, 35.0, np.where(days.dayofyear % 10 == 0, 35.0, 20.0)), index=days)
    cur, normal, upto = C.ytd_vs_normal(s, 33)
    assert cur == (days.year == NOW.year).sum() and normal is not None and normal < cur
    assert C.yearly_counts(s, 33)[pd.Timestamp("1991-01-01")] == 36
    y = pd.Series([0.1 * k for k in range(40)], index=pd.to_datetime([f"{1990 + k}-01-01" for k in range(40)]))
    assert C.trend_per_decade(y, 20) == pytest.approx(1.0)
    assert C.trend_crossing(y, 1.5) == pytest.approx(2005.0)
    g, tr = C.log_trend(pd.Series([100 * 1.05 ** k for k in range(10)], index=pd.to_datetime([f"{2000 + k}-12-31" for k in range(10)])))
    assert g == pytest.approx(5.0) and tr.iloc[-1] == pytest.approx(100 * 1.05 ** 9)
    assert (C.lean(0.5), C.lean(-0.5), C.lean(0.01, 0.1), C.lean(None)) == (1, -1, 0, 0)


# ------------------------------------------------------------------ payloads
def test_every_tab_payload_is_json_safe_and_complete(fixtures):
    for name in ("temperature", "co2", "sea", "heat", "costs"):
        p = B.json_safe(C.ENDPOINTS[name]())
        assert not [k for k in p if k.endswith("_error")], (name, {k: v for k, v in p.items() if k.endswith("_error")})
        assert p["readings"], name
        for r in p["readings"]:
            assert r["tab"] == name and r["lean"] in (-1, 0, 1) and r["key"] and r["label"]
    t = C.ENDPOINTS["temperature"]()
    assert set(t["monthly"]) == {"NASA GISTEMP", "Copernicus ERA5", "Met Office HadCRUT5"} and t["main"] == "Copernicus ERA5"
    assert t["daily"]["now"] == (NOW - pd.Timedelta(days=2)).year
    h = C.ENDPOINTS["heat"]()
    assert set(C.CITIES) <= set(h) and h["Hong Kong"]["rec_hi"] and h["London"]["hot"] and h["heathrow"]
    s = C.ENDPOINTS["sea"]()
    assert set(s["gauges"]) == set(C.GAUGES) and s["kpis"]["rate10"] > s["kpis"]["rate_prev10"]
    c = C.ENDPOINTS["costs"]()
    assert c["billions_from"].startswith("https://") and c["kpis"]["insured"]["year"] >= 2024 and c["events"]


def test_one_dead_source_blanks_one_line(fixtures, monkeypatch):
    def no_gistemp(url, ttl=0, **k):
        if "giss" in url or "billions" in url:
            raise ConnectionError("down")
        return fake_fetch(url, ttl, **k)
    monkeypatch.setattr(C, "fetch", no_gistemp)
    t = C._temperature_now()
    assert "NASA GISTEMP" not in t["monthly"] and t["missing"] == {"NASA GISTEMP": "ConnectionError"} and t["readings"]
    c = C._costs_now()
    assert c["billions_from"] == "hand-entered" and c["kpis"]["billions"]["year"] == 2024


def test_readings_come_from_the_cache_only(fixtures, monkeypatch):
    assert C.READINGS() == []                                   # nothing computed yet: nothing downloaded here
    monkeypatch.setattr(C, "fetch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("READINGS must not download")))
    from app.cache import _cache
    import time
    _cache[f"topic:{C.SLUG}:co2"] = (time.time(), {"readings": [{"tab": "co2", "key": "x", "label": "x", "value": 1.0, "lean": -1},
                                                                {"tab": "co2", "key": "y", "label": "y", "value": None, "lean": 1}]})
    assert [r["key"] for r in C.READINGS()] == ["x"]


def test_readings_feed_the_daily_snapshot(fixtures, tmp_path, monkeypatch):
    from app.topics import _daily
    monkeypatch.setattr(_daily, "SNAP_DIR", tmp_path)
    for name in ("temperature", "co2", "sea", "heat", "costs"):
        C.ENDPOINTS[name]()
    rows = C.READINGS()
    assert {r["tab"] for r in rows} == {"temperature", "co2", "sea", "heat", "costs"}
    assert len({r["key"] for r in rows}) == len(rows)
    assert _daily.save_today(C.SLUG, C.READINGS, "2026-10-01") == "saved"


def test_hand_entered_rows_cite_a_source():
    for name in ("insured_losses", "billion_dollar", "china_losses", "events"):
        rows = B.manual_rows(C.SLUG, name)
        assert rows, name
        for r in rows:
            assert r["source"].startswith("http"), (name, r)


def test_registered_with_its_tabs():
    from app import topics
    t = topics.REGISTRY["climate"]
    assert [k for k, _ in t.tabs] == ["temperature", "co2", "sea", "heat", "costs"] and set(t.slow) <= set(C.ENDPOINTS)
    assert hasattr(topics.module("climate"), "READINGS")


# ------------------------------------------------------------------ live
@pytest.mark.network
def test_live_sources_parse():
    from app.cache import _cache
    _cache.clear()
    assert len(C.gistemp()) > 1000 and len(C.co2()) > 700 and len(C.sea_ice("north")) > 10000
    assert len(C.station("Hong Kong")) > 40000 and len(C.station("New York")) > 50000


def test_a_station_that_stopped_gives_no_reading_for_today(fixtures, monkeypatch):
    def old_london(url, ttl=0, **k):
        text = fake_fetch(url, ttl, **k)
        if "UKM00003772" in url:                   # Heathrow in GHCN stops in August 2025
            text = "\n".join(l for l in text.splitlines() if not l.startswith('"UKM') or l[15:25] <= "2025-08-24")
        return text
    monkeypatch.setattr(C, "fetch", old_london)
    h = C._heat_now()
    keys = {r["key"] for r in h["readings"]}
    assert h["London"]["upto"] == "2025-08-24" and "hot_London" not in keys and "rec_London" not in keys and "hot_New York" in keys


def test_signals_cover_the_approved_list(fixtures):
    import json
    from app.config import DATA_DIR
    assert C.SIGNALS() == []                                    # nothing cached yet: nothing downloaded here
    for name in ("temperature", "co2", "sea", "heat", "costs"):
        C.ENDPOINTS[name]()
    rows = C.SIGNALS()
    want = [w["key"] for w in json.loads((DATA_DIR / "signals" / "watchlist.json").read_text())["climate"]]
    assert [r["key"] for r in rows] == want
    for r in rows:
        assert {"tab", "label", "value", "lean", "watch", "crossed"} <= set(r) and r["lean"] in (-1, 0, 1) and isinstance(r["crossed"], bool)
    by = {r["key"]: r for r in rows}
    assert by["disasters_ytd"]["crossed"] is False and "no year-to-date" in by["disasters_ytd"]["note"]
    B.json_safe(rows)


def test_signal_watch_points(fixtures):
    import time
    from app.cache import _cache
    ts = lambda s: int(pd.Timestamp(s).timestamp())
    months = pd.date_range("2024-01-01", periods=14, freq="MS")
    temp = {"main": "X", "monthly": {"X": [[ts(m), 1.4 if i < 2 else 1.6] for i, m in enumerate(months)]}, "kpis": {"X": {"r12": 1.6, "month": "2025-02"}}}
    _cache[f"topic:{C.SLUG}:temperature"] = (time.time(), temp)
    r = {x["key"]: x for x in C.SIGNALS()}["anomaly_12m"]
    assert r["crossed"] and r["note"].startswith("12 consecutive months")
    temp["monthly"]["X"][-1][1] = 1.5                           # the latest month at 1.5 breaks the run
    assert not {x["key"]: x for x in C.SIGNALS()}["anomaly_12m"]["crossed"]
    sept = [[ts(f"{y}-09-01"), 5.0 - 0.1 * (y - 2010)] for y in range(2010, 2021)]
    assert C._month_record_low(sept)["record"] and C._month_record_low(sept)["low_year"] == 2019
    assert not C._month_record_low(sept[:-1] + [[ts("2020-09-01"), 9.0]])["record"]


def test_hot_days_signal_skips_a_stale_station(fixtures, monkeypatch):
    import time
    from app.cache import _cache
    now = pd.Timestamp.now()
    yrs = lambda vals, y0: [[int(pd.Timestamp(f"{y0 + i}-01-01").timestamp()), v] for i, v in enumerate(vals)]
    _cache[f"topic:{C.SLUG}:heat"] = (time.time(), {
        "Hong Kong": {"hot": yrs([10, 40, 41], now.year - 2), "upto": now.strftime("%Y-%m-%d")},
        "London": {"hot": yrs([3, 99], now.year - 2), "upto": "2025-08-24"}})
    r = {x["key"]: x for x in C.SIGNALS()}["hot_days"]
    assert r["crossed"] and r["value"] == "HK 41" and "London: no current daily data" in r["note"]
