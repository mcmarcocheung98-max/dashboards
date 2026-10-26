"""Demographics & Ageing on fixtures (no network): the WPP stream reducers, the World Bank parser, every payload, and the WPP snapshot
fallback. smoke_patch() points the module at the same fixtures for scripts/smoke.py."""
import io
import json

import pandas as pd
import pytest

from app.topics import _base as B
from app.topics import demographics as D

ISOS = {"USA": (1.8, 330_000, 2.0), "GBR": (1.6, 68_000, 3.0), "HKG": (0.8, 7_500, 1.0), "CHN": (1.1, 1_400_000, -0.1), "FRA": (1.8, 66_000, 1.0)}


def wpp_indicators_csv() -> str:
    """The WPP 2024 Demographic Indicators layout (a subset of its 60-odd columns, in its order), 1950-2100, with one place we do not use."""
    rows = ["SortOrder,LocID,Notes,ISO3_code,ISO2_code,SDMX_code,LocTypeID,LocTypeName,ParentID,Location,VarID,Variant,Time,TPopulation1July,MedianAgePop,"
            "Births,CBR,TFR,NetMigrations,CNMR"]
    for iso, (tfr, pop, mig) in ISOS.items():
        for y in range(1950, 2101):
            t = tfr * (1.6 - 0.6 * min(1, (y - 1950) / 70))
            rows.append(f'1,1,,{iso},XX,1,4,Country/Area,1,"Place, {iso}",2,Medium,{y},{pop * (1 + (y - 1950) / 300):.3f},{25 + (y - 1950) * 0.15:.3f},'
                        f"{pop * t / 60:.3f},{t * 8:.3f},{t:.4f},{pop * mig / 1000:.3f},{mig:.3f}")
    return "\n".join(rows)


def wpp_ages_csv() -> str:
    rows = ["SortOrder,LocID,Notes,ISO3_code,ISO2_code,SDMX_code,LocTypeID,LocTypeName,ParentID,Location,VarID,Variant,Time,MidPeriod,AgeGrp,AgeGrpStart,AgeGrpSpan,"
            "PopMale,PopFemale,PopTotal"]
    for k, iso in enumerate(ISOS):
        for y in range(1950, 2101):
            old = 1 + (y - 1950) / (40 - 5 * k)               # the 65+ groups grow, faster for the later places
            for a in range(0, 101, 5):
                p = (900 - y + 1950 if a < 15 else 1000 - (y - 1950) * (k + 1) if a < 65 else 150 * old) / 10
                rows.append(f"1,1,,{iso},XX,1,4,Country/Area,1,{iso},2,Medium,{y},{y}.5,{a}-{a + 4},{a},5,{p / 2:.3f},{p / 2:.3f},{p:.3f}")
    return "\n".join(rows)


IND, AGE = wpp_indicators_csv(), wpp_ages_csv()


def wb_json(url: str):
    ind = url.split("/indicator/")[1].split("?")[0]
    rows = []
    for iso2, iso3 in (("US", "USA"), ("GB", "GBR"), ("HK", "HKG"), ("CN", "CHN")):
        for y in range(1990, 2051 if "source=40" in url else 2025):
            v = {"SL.TLF.CACT.ZS": 60 - (y - 1990) * 0.1, "SL.TLF.ACTI.ZS": 72 + (y - 1990) * 0.05, "SP.POP.DPND.OL": 15 + (y - 1990) * 0.5,
                 "SP.POP.1564.TO": 5e6 * (1 - (y - 1990) / 200)}.get(ind, 1.0)
            rows.append({"indicator": {"id": ind, "value": ind}, "country": {"id": iso2, "value": iso3}, "countryiso3code": iso3, "date": str(y), "value": v,
                         "unit": "", "obs_status": "", "decimal": 0})
    rows.append({"indicator": {"id": ind}, "country": {"id": "US"}, "countryiso3code": "USA", "date": "2025", "value": None})
    return [{"page": 1, "pages": 1, "per_page": 20000, "total": len(rows)}, rows]


def fake_open(url: str):
    if url == D.WPP_IND:
        return io.BytesIO(IND.encode())
    if url == D.WPP_AGE:
        return io.BytesIO(AGE.encode())
    raise ConnectionError(url)


def smoke_patch() -> None:
    D._open = fake_open
    D.fetch_json = lambda url, ttl, **k: wb_json(url)


@pytest.fixture
def demo(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(D, "_open", fake_open)
    monkeypatch.setattr(D, "fetch_json", lambda url, ttl, **k: wb_json(url))
    cache._cache.clear()
    B.STALE.clear()
    yield tmp_path / "snaps"
    cache._cache.clear()
    B.STALE.clear()


def test_topic_is_registered():
    from app import topics
    t = topics.REGISTRY["demographics"]
    assert t.module == "demographics" and [k for k, _ in t.tabs] == ["births", "ageing", "migration", "workforce", "pensions"]
    m = topics.meta("demographics")
    assert m["sources"] and "WPP" in m["notes"]


def test_reducers_keep_four_places_and_bands(demo):
    ind = D.indicators()
    assert set(ind["ISO3_code"]) == {"USA", "GBR", "HKG", "CHN"} and ind["Time"].min() == 1950 and ind["Time"].max() == 2100
    a = D.ages()
    us = a[(a["ISO3_code"] == "USA") & (a["Time"] == 2025)].iloc[0]
    assert us["p0_14"] == pytest.approx(3 * (900 - 75) / 10) and us["p15_64"] == pytest.approx(10 * (1000 - 75) / 10)
    assert us["p65"] == pytest.approx(8 * 15 * (1 + 75 / 40))
    assert us["total"] == pytest.approx(us["p0_14"] + us["p15_64"] + us["p65"])


def test_reducers_reject_a_changed_layout():
    with pytest.raises(ValueError):
        D.reduce_indicators(pd.DataFrame({"ISO3_code": ["USA"], "Time": [2000], "Births": [1]}))
    with pytest.raises(ValueError):
        D.reduce_ages(pd.DataFrame({"ISO3_code": ["USA"], "Time": [2000], "AgeGrp": ["0-4"], "Pop": [1]}))


def test_wpp_snapshot_serves_when_the_un_is_down(demo, monkeypatch):
    from app import cache
    D.indicators()
    snap = next(demo.glob("wpp-*.csv"))
    import os
    import time
    old = time.time() - 40 * 86400                       # past WPP_TTL: a fresh download is due
    os.utime(snap, (old, old))
    monkeypatch.setattr(D, "_open", lambda url: (_ for _ in ()).throw(ConnectionError("down")))
    cache._cache.clear()
    d = D.indicators()
    assert len(d) and D.WPP_IND in B.STALE
    assert B.HEALTH[D.WPP_IND]["error"].startswith("ConnectionError")


def test_wpp_fresh_snapshot_skips_the_download(demo, monkeypatch):
    from app import cache
    D.ages()
    monkeypatch.setattr(D, "_open", lambda url: (_ for _ in ()).throw(AssertionError("should not download")))
    cache._cache.clear()
    assert len(D.ages()) and D.WPP_AGE not in B.STALE


def test_world_bank_parser():
    s = D.parse_wb(wb_json(D.WB.format(ind="SL.TLF.CACT.ZS", src="")))
    assert set(s) == {"US", "UK", "Hong Kong", "China"} and s["US"].index.max() == 2024
    with pytest.raises(ValueError):
        D.parse_wb([{"message": [{"id": "120", "value": "Invalid value"}]}])


def test_payloads(demo):
    for name, fn in D.ENDPOINTS.items():
        out = B.json_safe(fn())
        assert not [k for k in out if k.endswith("_error")], (name, {k: v for k, v in out.items() if k.endswith("_error")})
    b = D.ENDPOINTS["births"]()
    assert b["tfr"]["US"]["est"][-1][0] == b["tfr"]["US"]["proj"][0][0]          # the dashed projection starts where the estimates end
    assert pd.Timestamp(b["tfr"]["US"]["proj"][-1][0], unit="s").year == 2100
    assert b["latest"]["China"]["value"] == 7920000 and b["latest"]["China"]["vs_2019"] < 0
    a = D.ENDPOINTS["ageing"]()
    assert a["dependency"]["source"] == "wpp" and a["kpi"]["US"]["oadr_2045"] > a["kpi"]["US"]["oadr_2025"] and a["kpi"]["UK"]["median_2100"]
    w = D.ENDPOINTS["workforce"]()
    assert w["working_age"]["change"]["US"]["to_2045"] < 0 and w["lfpr"]["UK"]
    p = D.ENDPOINTS["pensions"]()
    rows = p["answer"]["rows"]
    ch = [r["working_age_change"] for r in rows]
    assert ch == sorted(ch) and rows[0]["place"] == "China"                     # fastest shrinking first
    uk = next(r for r in rows if r["place"] == "UK")
    assert 5.0 < uk["pension_2045"] < 7.7                                        # between OBR's published points
    assert next(r for r in rows if r["place"] == "Hong Kong")["pension_2045"] is None


def test_dependency_falls_back_to_the_world_bank(demo, monkeypatch):
    monkeypatch.setattr(D, "_open", lambda url: fake_open(url) if url == D.WPP_IND else (_ for _ in ()).throw(ConnectionError("no age file")))
    a = D.ENDPOINTS["ageing"]()
    assert a["dependency"]["source"] == "worldbank" and a["kpi"]["US"]["oadr_2050"] == pytest.approx(15 + 60 * 0.5)
    assert a["median_age"]["US"]["est"]


def test_seed_files():
    for name in ("births", "tfr", "migration", "pensions", "projections"):
        rows = B.manual_rows("demographics", name)
        assert rows, name
        for r in rows:
            pd.Timestamp(r["date"])
            float(r["value"])
            assert r["source"].startswith("http"), (name, r)
            assert r["series"]


@pytest.mark.network
def test_live_sources():
    from app import cache
    cache._cache.clear()
    assert len(D.parse_wb(json.loads(B._download(D.WB.format(ind="SL.TLF.CACT.ZS", src=""))))) == 4
    d = D.reduce_indicators(D._read(D.WPP_IND, ["TFR", "MedianAgePop"]))
    assert set(d["ISO3_code"]) == set(D.PLACES) and d["Time"].max() == 2100
    a = D.reduce_ages(D._read(D.WPP_AGE, ["AgeGrpStart", "PopTotal"]))
    assert set(a["ISO3_code"]) == set(D.PLACES)


def test_readings(demo):
    from app.topics import _daily
    from app import cache
    assert D.READINGS() == []                                    # nothing cached yet: nothing is downloaded
    for fn in D.ENDPOINTS.values():
        fn()
    rows = _daily._clean(D.READINGS())
    by = {r["key"]: r for r in rows}
    assert {r["tab"] for r in rows} == {"births", "ageing", "migration", "workforce", "pensions"}
    assert len(by) == len(rows) and all(r["lean"] in (-1, 0, 1) for r in rows)
    assert by["tfr:UK"]["value"] == 1.41 and by["tfr:UK"]["lean"] == -1           # 1.42 -> 1.41
    assert by["fastest_shrinking"]["value"] == "China"
    assert by["wa2045:China"]["lean"] == -1
    assert "net:Hong Kong natural change (C&SD)" not in by
    cache._cache.clear()
