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


def fake_fetch(url, ttl=0, **k):
    if url == E.EMBER_YEARLY:
        return YEARLY
    if url == E.EMBER_MONTHLY:
        return MONTHLY
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
