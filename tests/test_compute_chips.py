"""AI Compute, Power & Chips (/compute-chips) on fixtures: Ember, Epoch AI, SEC EDGAR companyfacts and Nasdaq, no network.
smoke_patch() points the module's fetchers at the same fixtures for scripts/smoke.py."""
import json

import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import compute_chips as M


# ------------------------------------------------------------------ fixtures
def ember_csv() -> str:
    head = "Area,ISO 3 code,Year,Area type,Continent,Ember region,EU,OECD,G20,G7,ASEAN,Category,Subcategory,Variable,Unit,Value,YoY absolute change,YoY % change"
    rows = [head]
    for area, iso, base in (("United States of America", "USA", 3900), ("China", "CHN", 6000), ("United Kingdom", "GBR", 300), ("World", "", 22000), ("France", "FRA", 450)):
        for y in range(2012, 2026):
            v = base * (1.03 if iso == "CHN" else 1.01) ** (y - 2012)
            rows.append(f"{area},{iso},{y},Country,,,0,1,1,1,0,Electricity demand,Demand,Demand,TWh,{v:.1f},,")
            rows.append(f"{area},{iso},{y},Country,,,0,1,1,1,0,Electricity demand,Demand,Demand per capita,MWh,7.1,,")
            rows.append(f"{area},{iso},{y},Country,,,0,1,1,1,0,Electricity generation,Fuel,Coal,TWh,100,,")
    return "\n".join(rows)


def epoch_csv() -> str:
    rows = ["Model,Domain,Organization,Publication date,Parameters,Training compute (FLOP),Country (of organization),Notability criteria"]
    countries = ["United States of America", "China", "United Kingdom of Great Britain and Northern Ireland", "United States of America,China", "Canada"]
    for i in range(160):
        d = pd.Timestamp("2012-01-01") + pd.Timedelta(days=int(i * 31))
        flop = 10 ** (17 + i * 0.065 + (i % 4) * 0.3)
        rows.append(f'Model {i},Language,Org {i % 7},{d.date()},1e9,{flop:.3e},"{countries[i % 5]}",Training cost')
    rows.append("No compute,Language,Org,2024-01-01,1e9,,United States of America,")
    return "\n".join(rows)


def clusters_csv() -> str:
    rows = ["Name,Country,First Operational Date,Status,Power Capacity (MW),H100 equivalents"]
    for i in range(40):
        d = pd.Timestamp("2017-01-01") + pd.Timedelta(days=int(i * 70))
        rows.append(f"Cluster {i},{['United States of America', 'China', 'United Kingdom', 'Hong Kong'][i % 4]},{d.date()},{'Planned' if i > 36 else 'Existing'},{20 * 1.12 ** i:.0f},{1000 * i}")
    return "\n".join(rows)


def companyfacts(scale: float = 1.0, tag: str = "PaymentsToAcquirePropertyPlantAndEquipment", year_to_date: bool = True) -> str:
    """10-Q/10-K style facts for calendar fiscal years: cash flows as year-to-date durations (the 10-K's full year included), or
    three-month facts plus the 10-K full year (income statements)."""
    facts = []
    for y in range(2014, 2027):
        qv = [scale * 1e9 * (1 + 0.04 * ((y - 2014) * 4 + q)) for q in range(4)]
        ends = [f"{y}-03-31", f"{y}-06-30", f"{y}-09-30", f"{y}-12-31"]
        for q in range(4):
            if y == 2026 and q > 1:
                break
            filed = f"{y + (q == 3)}-{['05', '08', '11', '02'][q]}-01"
            form = "10-K" if q == 3 else "10-Q"
            if year_to_date:
                facts.append({"start": f"{y}-01-01", "end": ends[q], "val": sum(qv[:q + 1]), "filed": filed, "form": form})
            else:
                if q < 3:
                    facts.append({"start": [f"{y}-01-01", f"{y}-04-01", f"{y}-07-01"][q], "end": ends[q], "val": qv[q], "filed": filed, "form": form})
                    if q:
                        facts.append({"start": f"{y}-01-01", "end": ends[q], "val": sum(qv[:q + 1]), "filed": filed, "form": form})
                else:
                    facts.append({"start": f"{y}-01-01", "end": ends[q], "val": sum(qv), "filed": filed, "form": form})
    return json.dumps({"cik": 1, "facts": {"us-gaap": {tag: {"units": {"USD": facts}}, "Assets": {"units": {"USD": [{"end": "2020-12-31", "val": 1}]}}}}})


def nasdaq_json(p0: float = 100.0) -> dict:
    days = pd.bdate_range("2019-01-02", "2026-10-23")
    return {"data": {"tradesTable": {"rows": [{"date": d.strftime("%m/%d/%Y"), "close": f"${p0 * (1 + i * 0.002):,.2f}"} for i, d in enumerate(days)][::-1]}}}


CIK_SCALE = {789019: 10, 1652044: 9, 1018724: 15, 1326801: 7, 1341439: 2, 1045810: 5, 2488: 3}


def fake_get(url, headers=None, keep=None):
    if "emb-prod" in url:
        text = ember_csv()
        if keep:
            lines = text.split("\n")
            text = "\n".join([lines[0]] + [ln for ln in lines[1:] if keep(ln)])
        return text
    if "companyfacts" in url:
        cik = int(url.rsplit("CIK", 1)[1].split(".")[0])
        if cik in (1045810, 2488):
            return companyfacts(CIK_SCALE[cik], "Revenues", year_to_date=False)
        return companyfacts(CIK_SCALE[cik], "PaymentsToAcquireProductiveAssets" if cik == 1018724 else "PaymentsToAcquirePropertyPlantAndEquipment")
    raise ConnectionError("fixture: unknown url " + url)


def fake_fetch(url, ttl=0, **k):
    if "gpu_clusters" in url:
        return clusters_csv()
    if "notable_ai_models" in url:
        return epoch_csv()
    raise ConnectionError("fixture: unknown url " + url)


def fake_fetch_json(url, ttl=0, **k):
    sym = url.split("/quote/")[1].split("/")[0]
    return nasdaq_json(50 + 10 * M.TICKERS.index(sym))


def smoke_patch():
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above."""
    M._get = fake_get
    M.fetch = fake_fetch
    M.fetch_json = fake_fetch_json


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "_get", fake_get)
    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(M, "fetch_json", fake_fetch_json)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


# ------------------------------------------------------------------ tests
def test_registered():
    t = topics.REGISTRY["compute-chips"]
    assert t.module == "compute_chips" and set(k for k, _ in t.tabs) <= set(M.ENDPOINTS)
    m = topics.meta("compute-chips")
    assert m["sources"] and m["notes"]


def test_quarterly_from_year_to_date_and_three_month_facts():
    ytd = json.loads(companyfacts(1.0))["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"]
    q = M.quarterly(ytd)
    assert q[pd.Timestamp("2015-12-31")] == pytest.approx(1e9 * (1 + 0.04 * 7))          # Q4 = full year minus nine months
    assert q[pd.Timestamp("2015-06-30")] == pytest.approx(1e9 * (1 + 0.04 * 5))
    three = json.loads(companyfacts(1.0, "Revenues", year_to_date=False))["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
    q2 = M.quarterly(three)
    assert q2[pd.Timestamp("2020-12-31")] == pytest.approx(1e9 * (1 + 0.04 * 27))
    assert len(q2) == len(q) and q2.index.max() == pd.Timestamp("2026-06-30")


def test_restated_fact_wins():
    facts = [{"start": "2024-01-01", "end": "2024-03-31", "val": 1, "filed": "2024-05-01"}, {"start": "2024-01-01", "end": "2024-03-31", "val": 2, "filed": "2025-05-01"}]
    assert M.quarterly(facts).iloc[0] == 2


def test_fiscal_quarters_map_to_calendar_quarters():
    nvidia = M.cal_quarter(pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2025-07-27", "2025-10-26", "2026-01-25"])))
    assert list(nvidia.index) == list(pd.to_datetime(["2025-04-01", "2025-07-01", "2025-10-01"]))
    oracle = M.cal_quarter(pd.Series([1.0, 2.0], index=pd.to_datetime(["2025-08-31", "2026-02-28"])))
    assert list(oracle.index) == list(pd.to_datetime(["2025-07-01", "2026-01-01"]))


def test_ember_filter_and_parse():
    lines = ember_csv().split("\n")
    kept = [ln for ln in lines[1:] if M._ember_keep(ln)]
    assert kept and all(",Demand,TWh," in ln for ln in kept) and not any(ln.startswith("France") for ln in kept)
    d = M.parse_ember("\n".join([lines[0]] + kept))
    assert set(d) == {"US", "China", "UK", "World"} and d["US"].index[0] == pd.Timestamp("2012-01-01")
    with pytest.raises(ValueError):
        M.parse_ember("a,b\n1,2")


def test_power_share_and_snapshot_fallback(mocked, monkeypatch):
    p = B.json_safe(M._power_now())
    assert p["ember_live"] and {"US", "China", "UK", "World"} <= set(p["share"])
    us = dict(p["share"]["US"])
    t2023 = int(pd.Timestamp("2023-01-01").timestamp())
    assert 0.03 < us[t2023] < 0.06                             # 176 TWh of ~4,300
    assert p["clusters"]["largest"] and p["clusters"]["by_country"]["US"] > 0
    assert all(r.get("source") for r in p["rows"])
    # Ember down: the snapshot written above is served and marked stale
    from app import cache
    cache._cache.clear()
    monkeypatch.setattr(M, "_get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    p2 = M._power_now()
    assert p2["share"] and M.EMBER in p2["stale"]
    assert B.HEALTH[M.EMBER]["error"].startswith("ConnectionError")


def test_power_without_ember_uses_hand_entered_demand(tmp_path, monkeypatch):
    from app import cache
    cache._cache.clear()
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "empty")
    monkeypatch.setattr(M, "_get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    monkeypatch.setattr(M, "fetch", fake_fetch)
    p = M._power_now()
    assert p["ember_live"] is False and "US" in p["share"]
    cache._cache.clear()


def test_capex(mocked):
    c = B.json_safe(M._capex_now())
    assert set(c["companies"]) == set(M.HYPERSCALERS) and not c["errors"]
    assert c["total"][-1][0] == int(pd.Timestamp("2026-04-01").timestamp())
    assert c["kpi"]["ttm_yoy"] > 0 and c["ttm"]


def test_capex_one_filer_down(mocked, monkeypatch):
    real = fake_get
    monkeypatch.setattr(M, "_get", lambda url, *a, **k: (_ for _ in ()).throw(ConnectionError("x")) if "1341439" in url else real(url, *a, **k))
    c = M._capex_now()
    assert c["errors"] == {"Oracle": "ConnectionError"} and c["total"] is None and c["total_error"] == "LookupError" and len(c["companies"]) == 4


def test_compute(mocked):
    k = B.json_safe(M._compute_now())
    e = k["epoch"]
    assert e["max"] and e["frontier"] and e["growth_per_year"] > 1
    assert sum(sum(v) for v in e["over_1e25"].values()) > 0 and set(e["over_1e25"]) == {"US", "China", "UK", "Other"}
    assert e["top"][0]["flop"] >= e["top"][-1]["flop"]


def test_chips(mocked):
    c = B.json_safe(M._chips_now())
    assert {"Nvidia", "AMD", "TSMC", "ASML (EUR)", "SMIC"} <= set(c["revenue"]) and not c["errors"]
    assert set(c["prices"]) == set(M.TICKERS) and all(v[0][1] == 100 for v in c["prices"].values())
    assert c["revenue_yoy"]["Nvidia"] and c["last"]["NVDA"]["y1"] > 0


def test_supply_and_overview(mocked):
    s = B.json_safe(M._supply_now())
    assert s["capacity"]["years"] == ["2022", "2032"] and s["taiwan"]["from"] > s["taiwan"]["to"]
    assert s["fabs"] and s["controls"] and any("Hong Kong" in r["market"] for r in s["controls"])
    o = B.json_safe(M._overview_now())
    assert all(o["kpi"][k] is not None for k in ("us_dc_share", "capex_ttm", "compute_growth", "nvidia_yoy", "largest_cluster_mw", "taiwan"))


def test_every_endpoint_through_the_server(mocked):
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            for name in ["meta", *(k for k in M.ENDPOINTS if k != "sec_probe")]:     # sec_probe is a live diagnostic
                r = await c.get(f"/api/compute-chips/{name}")
                assert r.status == 200, name
            assert (await c.get("/compute-chips.js")).status == 200
    asyncio.run(go())


@pytest.mark.network
def test_live_sources():
    from app import cache
    cache._cache.clear()
    assert M.parse_ember(M._get(M.EMBER, keep=M._ember_keep))["US"].index.max().year >= 2024
    assert len(M.parse_epoch(M._get(M.EPOCH))) > 100
    assert M.clusters()["largest"]
    assert len(M.edgar_series(789019, M.CAPEX_TAGS)) > 20
    assert len(M.nasdaq("NVDA")) > 200
