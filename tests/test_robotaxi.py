"""Energy tab of /robotaxi (app/topics/robotaxi_energy.py), on fixtures in Ember's July 2026 layout. The other robotaxi tests are in
test_topics.py."""
import pandas as pd
import pytest

from app.topics import _base as B
from app.topics import robotaxi as R
from app.topics import robotaxi_energy as E

HEAD = ("Area,ISO 3 code,{when},Area type,Electricity source,Is aggregated source,Generation (TWh),Generation YoY change (TWh),"
        "Generation YoY change (%),Share of generation (%),Share of generation YoY change (% points),Capacity (GW),Emissions (MtCO2e)\n")
AREAS = {"United States": ("USA", 10.0, 0.6), "United Kingdom": ("GBR", 25.0, 1.5), "China": ("CHN", 8.0, 1.8), "Hong Kong (China)": ("HKG", 0.1, 0.02),
         "Germany": ("DEU", 30.0, 1.0)}


def _ember(periods, when="Year", per=1.0):
    rows = []
    for area, (iso, base, step) in AREAS.items():
        for i, p in enumerate(periods):
            for src, frac in (("Solar", 0.4), ("Wind", 0.6), ("Coal", None), ("Total generation", None)):
                share = round((base + step * per * i) * frac, 3) if frac else 50.0
                agg = "True" if src == "Total generation" else "False"
                rows.append(f"{area},{iso},{p},Country,{src},{agg},1.0,,,{share if src != 'Total generation' else 100.0},,,")
    return HEAD.format(when=when) + "\n".join(rows) + "\n"


YEARLY = _ember(range(2015, 2026))
MONTHLY = _ember([d.strftime("%Y-%m-01") for d in pd.date_range("2021-01-01", "2026-08-01", freq="MS")], when="Date", per=1 / 12)

EV_HEAD = ("Area,ISO 3 code,Area type,Date,Data frequency,Drivetrain,Is aggregate drivetrain,Registrations,Registrations YoY change,"
           "Registrations YoY change (%),Share of registrations (%),Year-to-date registrations,Year-to-date share of registrations (%),"
           "Rolling 3-month registrations,Rolling 3-month share of registrations (%),Rolling 12-month registrations,Rolling 12-month share of registrations (%)\n")
EV_AREAS = {"United States": 7.0, "United Kingdom": 25.0, "China": 45.0, "Hong Kong (SAR of China)": 70.0, "Germany": 20.0}


def _ember_ev():
    rows = []
    for area, base in EV_AREAS.items():
        for i, d in enumerate(pd.date_range("2022-01-01", "2026-09-01", freq="MS")):
            share = round(base + 0.2 * i + (2 if d.month == 3 else 0), 2)
            for dt, sh, agg in (("Electric vehicle (BEV+PHEV)", share, "True"), ("Combustion (unspecified)", round(100 - share, 2), "False"),
                                ("All drivetrains", 100.0, "True")):
                rows.append(f"{area},X,Country or economy,{d.date()},Monthly,{dt},{agg},100,,,{sh},,,,,,{round(sh - 0.5, 2)}")
    return EV_HEAD + "\n".join(rows) + "\n"


EV = _ember_ev()


def fake_fetch(url, ttl=0, **k):
    if url == E.EMBER_YEARLY:
        return YEARLY
    if url == E.EMBER_MONTHLY:
        return MONTHLY
    if url == E.EMBER_EV:
        return EV
    raise OSError(f"no fixture for {url}")


def smoke_patch():
    """Used by scripts/smoke.py: Ember answers from the fixtures above (robotaxi's own sources are patched there directly)."""
    E.fetch = fake_fetch


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(E, "fetch", fake_fetch)


def test_parse_ember_keeps_the_four_markets_and_solar_wind():
    d = E.parse_ember(YEARLY)
    assert set(d["market"]) == {"US", "UK", "China", "Hong Kong"} and set(d["source"]) == {"Solar", "Wind"}   # Germany and coal dropped
    ws = E.wind_solar(d)
    assert ws["UK"].index[0] == pd.Timestamp("2015-01-01") and ws["UK"].iloc[-1] == pytest.approx(25.0 + 1.5 * 10)
    m = E.wind_solar(E.parse_ember(MONTHLY))
    assert m["China"].index[-1] == pd.Timestamp("2026-08-01")
    with pytest.raises(ValueError):
        E.parse_ember("Area,Year,Value\nX,2020,1\n")


def test_energy_payload_and_readings(mocked):
    p = E.energy_now()
    B.json_safe(p)
    assert not [k for k in p if k.endswith("_error")], p
    pw = p["power"]
    assert pw["latest"]["US"] == {"year": 2025, "share": 16.0, "change": 0.6} and pw["latest"]["Hong Kong"]["share"] == pytest.approx(0.3, abs=0.01)
    assert len(pw["monthly"]["UK"]) == 61 and pw["monthly_latest"]["UK"]["year_ago"] is not None    # last five years of months
    ev = p["ev"]
    assert {"UK: battery-electric", "Hong Kong: electric share of new private cars"} <= set(ev["yearly"]) and ev["months"][0]["date"] >= ev["months"][-1]["date"]
    assert {"US", "UK", "China", "Hong Kong"} == {r["market"] for r in p["checks"]}
    r = {x["key"]: x for x in E.readings(p)}
    assert set(r) == {"ev_uk_bev", "ev_china_nev", "ws_china", "ws_us"} and r["ws_us"]["lean"] == 1 and r["ev_uk_bev"]["value"] == 26.2
    assert all(x["tab"] == "energy" for x in r.values()) and E.readings({}) == []


def test_energy_without_monthly_file(mocked, monkeypatch):
    monkeypatch.setattr(E, "fetch", lambda url, ttl=0, **k: YEARLY if url == E.EMBER_YEARLY else (_ for _ in ()).throw(OSError("down")))
    p = E.energy_now()
    assert p["power"]["yearly"] and p["power"]["monthly_error"] == "OSError"            # the yearly card stands on its own


def test_robotaxi_registers_itself_with_the_energy_tab():
    from app import topics
    t = topics.REGISTRY["robotaxi"]
    assert t is R.TOPIC and ("energy", "Energy") in t.tabs and "energy" in R.ENDPOINTS
    assert "robotaxi" not in {b.slug for b in topics.BUILTIN} and topics.helpers().get("robotaxi_energy") == "robotaxi"


def test_ember_ev_shares_for_the_four_markets(mocked):
    ev = E.parse_ember_ev(EV)
    assert set(ev) == {"US", "UK", "China", "Hong Kong"} and ev["UK"].index[-1] == pd.Timestamp("2026-09-01")   # Germany and other drivetrains dropped
    p = E.energy_now()
    x = p["ev_ember"]["latest"]["Hong Kong"]
    assert x["month"] == "2026-09-01" and x["share"] == pytest.approx(70 + 0.2 * 56) and x["r12_year_ago"] == pytest.approx(70 + 0.2 * 44 - 0.5)
    assert len(p["ev_ember"]["r12"]["China"]) == 57 and p["as_of"] == "2026-09-01"
    with pytest.raises(ValueError):
        E.parse_ember_ev("Area,Date,Value\nX,2026-01-01,1\n")


LIVE_RATE = [{"operator": "Waymo", "date": d, "miles": m, "reports": n} for d, m, n in (       # the live safety tab, 25 Oct 2026
    ("2024-06-30", 22e6, 382), ("2025-01-31", 56.7e6, 778), ("2025-03-31", 71e6, 917), ("2025-06-30", 96e6, 1169), ("2025-09-30", 127e6, 1332),
    ("2025-12-31", 170.7e6, 1611), ("2026-03-31", 220.6e6, 1899), ("2026-06-30", 271.3e6, 2221))]


def test_crash_quarter_against_the_year_before():
    c = R.crash_quarter(LIVE_RATE)
    assert c["now"] == pytest.approx(322 / 50.7, abs=0.01) and c["year"] == pytest.approx(982 / 149.6, abs=0.01) and c["year_from"] == "2025-03-31"
    worse = LIVE_RATE + [{"operator": "Waymo", "date": "2026-09-30", "miles": 300e6, "reports": 2221 + 400}]
    assert R.crash_quarter(worse)["now"] > R.crash_quarter(worse)["year"]
    assert R.crash_quarter(LIVE_RATE[:2]) is None


def test_signals_cover_the_approved_keys():
    import json
    from pathlib import Path
    pay = {"rides": {"weekly": {"Waymo": [[1774483200, 500000.0], [1777420800, 500000.0]]}},
           "safety": {"reports": {"rate": LIVE_RATE}},
           "footprint": {"rows": [{"date": "2020-10-08", "operator": "Waymo", "city": "Phoenix", "country": "US", "note": ""},
                                  {"date": "2022-08-08", "operator": "Baidu Apollo Go", "city": "Wuhan", "country": "CN", "note": ""}]},
           "energy": {"ev_ember": {"latest": {"UK": {"r12": 40.16, "r12_year_ago": 33.53}, "US": {"r12": 7.1, "r12_year_ago": 10.41},
                                              "China": {"r12": 58.26, "r12_year_ago": 51.95}, "Hong Kong": {"r12": 90.03, "r12_year_ago": 81.57}}}},
           "tesla": {"milestones": [{"date": "2026-01-28", "area": "Robotaxi", "event": "Tesla reports it began removing the safety monitor from some Austin customer rides"},
                                    {"date": "2026-04-22", "area": "Robotaxi", "event": "unsupervised Robotaxi rides launched in Dallas and Houston"}]}}
    s = {x["key"]: x for x in R.signals(lambda n: pay[n])}
    approved = {r["key"] for r in json.loads(Path("data/signals/watchlist.json").read_text())["robotaxi"]}
    assert set(s) == approved
    assert s["waymo_rides"]["crossed"] and s["waymo_rides"]["lean"] == 0 and "1m not yet" in s["waymo_rides"]["note"]
    assert not s["crash_rate"]["crossed"] and s["crash_rate"]["lean"] == 1
    assert not s["cities"]["crossed"] and s["cities"]["value"] == 2
    assert s["ev_share"]["crossed"] and "UK above 30%" in s["ev_share"]["note"] and "US not above 15%" in s["ev_share"]["note"]
    assert s["tesla_unsupervised"]["crossed"] and s["tesla_unsupervised"]["value"] == "2026-01-28"
    pay["footprint"]["rows"].append({"date": str(pd.Timestamp.now().date()), "operator": "Waymo", "city": "London", "country": "UK", "note": ""})
    pay["footprint"]["rows"].append({"date": "2023-08-10", "operator": "Cruise", "city": "San Francisco", "country": "US", "note": "suspended Oct 2023"})
    c = {x["key"]: x for x in R.signals(lambda n: pay[n])}["cities"]
    assert c["crossed"] and c["lean"] == -1 and "UK" in c["note"] and "Cruise" in c["note"]
    assert R.signals(lambda n: {}) == [] and isinstance(R.SIGNALS(), list)
