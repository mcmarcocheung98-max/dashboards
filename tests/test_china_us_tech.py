"""China vs US Tech (/china-us-tech) on fixtures: Epoch AI, OpenAlex, Our World in Data and Nasdaq, no network.
smoke_patch() points the module's fetchers at the same fixtures for scripts/smoke.py."""
import json

import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import china_us_tech as M


# ------------------------------------------------------------------ fixtures
def epoch_csv() -> str:
    rows = ["Model,Domain,Organization,Publication date,Parameters,Training compute (FLOP),Country (of organization),Model accessibility"]
    countries = ["United States of America", "China", "United States of America", "United Kingdom of Great Britain and Northern Ireland",
                 "United States of America,China", "Hong Kong", "Canada", "China"]
    for i in range(240):
        d = pd.Timestamp("2014-01-01") + pd.Timedelta(days=int(i * 20))
        c = countries[i % len(countries)]
        flop = 10 ** (18 + i * 0.035 - (1.2 if c == "China" else 0))
        acc = "Open weights (unrestricted)" if i % 3 == 0 else "API access"
        rows.append(f'Model {i},Language,Org {i % 9},{d.date()},1e9,{flop:.3e},"{c}",{acc}')
    rows.append('No country,Language,Org,2024-01-01,1e9,1e20,,API access')
    return "\n".join(rows)


def openalex_json(cc: str, cited: bool) -> dict:
    base = {"US": 9000, "CN": 7000, "GB": 1500, "HK": 400}[cc] * (0.01 if cited else 1)
    growth = 1.12 if cc == "CN" else 1.05
    return {"meta": {"count": 1, "groups_count": 20}, "results": [],
            "group_by": [{"key": str(y), "key_display_name": str(y), "count": int(base * growth ** (y - 2005))} for y in range(2005, 2026)][::-1]}


def owid_csv(name: str) -> str:
    col = "Electric car sales share" if "share" in name else "Electric car sales"
    rows = [f"Entity,Code,Year,{col}"]
    for ent, code, v0 in (("China", "CHN", 1.0), ("United States", "USA", 0.5), ("United Kingdom", "GBR", 0.6), ("World", "OWID_WRL", 0.7), ("France", "FRA", 0.6)):
        for y in range(2012, 2025):
            v = v0 * 1.4 ** (y - 2012) if "share" in name else v0 * 1e5 * 1.5 ** (y - 2012)
            rows.append(f"{ent},{code},{y},{v:.2f}")
    return "\n".join(rows)


def nasdaq_json(p0: float, drift: float) -> dict:
    days = pd.bdate_range("2019-01-02", "2026-10-23")
    return {"data": {"tradesTable": {"rows": [{"date": d.strftime("%m/%d/%Y"), "close": f"${p0 * (1 + i * drift):,.2f}"} for i, d in enumerate(days)][::-1]}}}


def fake_fetch(url, ttl=0, **k):
    if "notable_ai_models" in url:
        return epoch_csv()
    if "ourworldindata" in url:
        return owid_csv(url)
    raise ConnectionError("fixture: unknown url " + url)


def fake_fetch_json(url, ttl=0, **k):
    if "openalex" in url:
        cc = url.split("country_code:")[1].split(",")[0]
        return openalex_json(cc, "cited_by_count" in url)
    if "nasdaq" in url:
        sym = url.split("/quote/")[1].split("/")[0]
        return nasdaq_json(40 + 5 * len(sym), 0.0002 if sym in M.CN_TECH + (M.CN_ETF,) else 0.002)
    raise ConnectionError("fixture: unknown url " + url)


def smoke_patch():
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above."""
    M.fetch = fake_fetch
    M.fetch_json = fake_fetch_json


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(M, "fetch_json", fake_fetch_json)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


# ------------------------------------------------------------------ tests
def test_registered():
    t = topics.REGISTRY["china-us-tech"]
    assert t.module == "china_us_tech" and set(k for k, _ in t.tabs) <= set(M.ENDPOINTS)
    m = topics.meta("china-us-tech")
    assert m["sources"] and "China gaining" in m["notes"]


def test_epoch_counts_a_joint_model_for_both_countries():
    x = M.parse_epoch(epoch_csv())
    joint = x[x["model"] == "Model 4"]
    assert set(joint["country"]) == {"US", "China"}
    assert set(x["country"]) == {"US", "China", "UK", "Hong Kong", "Other"}
    assert "No country" not in set(x["model"])
    with pytest.raises(ValueError):
        M.parse_epoch("a,b\n1,2")


def test_models(mocked):
    p = M.ENDPOINTS["models"]()
    E = p["epoch"]
    assert E["years"][0] == 2015 and len(E["counts"]["US"]) == len(E["years"])
    assert E["gap_oom"] > 0 and set(E["frontier"]) >= {"US", "China"}
    assert all(0 <= s <= 1 for _, s in E["china_share"])
    assert p["arena"]["gap"] and p["arena"]["lines"]["Best US model"]
    B.json_safe(p)


def test_research_and_openalex_parser(mocked):
    s = M.parse_openalex(openalex_json("CN", False))
    assert s.index.is_monotonic_increasing and s.iloc[-1] > s.iloc[0]
    with pytest.raises(ValueError):
        M.parse_openalex({"results": []})
    p = M.ENDPOINTS["research"]()
    assert set(p["papers"]) == {"US", "China", "UK", "Hong Kong"} and p["cited_share"]
    assert dict(p["pct_gap"])[2025] == 73718 - 52617
    B.json_safe(p)


def test_research_without_openalex_still_shows_patents(mocked, monkeypatch):
    monkeypatch.setattr(M, "fetch_json", lambda url, ttl=0, **k: (_ for _ in ()).throw(ConnectionError("down")))
    p = M.ENDPOINTS["research"]()
    assert p["pct"]["China"] and p["cited_share"] is None and p["cited_share_error"] == "LookupError"
    assert set(p["errors"]) == {"US", "China", "UK", "Hong Kong"}


def test_ev_merges_owid_with_hand_entered_rows(mocked):
    p = M.ENDPOINTS["ev"]()
    assert p["owid_live"] is True
    china = dict(p["share"]["China"])
    assert china[2012] == pytest.approx(1.0)                  # from OWID
    assert "Hong Kong" in p["share"]                          # hand-entered only
    assert p["battery"]["by_country"]["China"][-1] > 50 and p["exports"] and p["byd_tesla"]["BYD"]
    B.json_safe(p)


def test_ev_without_owid_uses_the_hand_entered_shares(mocked, monkeypatch):
    monkeypatch.setattr(M, "fetch", lambda url, ttl=0, **k: (_ for _ in ()).throw(ConnectionError("down")))
    p = M.ENDPOINTS["ev"]()
    assert p["owid_live"] is False and dict(p["share"]["China"])[2024] == 48 and p["sales"] is None


def test_owid_parser_rejects_a_changed_layout():
    with pytest.raises(ValueError):
        M.parse_owid("Country,Value\nChina,1")


def test_shared_rows_for_other_dashboards():
    assert [r["date"] for r in M.controls_rows()] == sorted(r["date"] for r in M.controls_rows()) and M.leaderboard_rows()[-1]["series"] == "China best"


def test_chips_node_gap_and_controls():
    from app import cache
    cache._cache.clear()
    p = M.ENDPOINTS["chips"]()
    nodes = {n["node"]: n["years"] for n in p["nodes"]}
    assert nodes[7.0] == pytest.approx(4.3, abs=0.1) and 14.0 in nodes
    assert p["trade"]["Imports"] and p["imports_yoy"] is not None and p["controls"]
    B.json_safe(p)
    cache._cache.clear()


def test_markets_baskets(mocked):
    p = M.ENDPOINTS["markets"]()
    b = p["baskets"]
    assert set(b) == {"US tech basket", "China tech ADRs", "KWEB"} and b["US tech basket"][0][1] == pytest.approx(100)
    assert p["rel_1y"] < 0 and p["ratio"][-1][1] < 100                     # the fixture's US basket rises faster
    assert "Hang Seng TECH" in p["years"] and p["years"]["US tech basket"]
    B.json_safe(p)


def test_markets_one_ticker_down(mocked, monkeypatch):
    def no_baba(url, ttl=0, **k):
        if "/BABA/" in url:
            raise ConnectionError("down")
        return fake_fetch_json(url, ttl, **k)
    monkeypatch.setattr(M, "fetch_json", no_baba)
    p = M.ENDPOINTS["markets"]()
    assert "BABA" in p["errors"] and "BABA" not in p["members"]["China tech ADRs"] and p["baskets"]["China tech ADRs"]


def test_basket_is_equal_weighted():
    idx = pd.date_range("2020-01-01", periods=3)
    s = M.basket({"A": pd.Series([10, 20, 20], index=idx), "B": pd.Series([5, 5, 10], index=idx)})
    assert list(s) == [100, 150, 200]


def test_overview_and_readings(mocked):
    assert M.READINGS() == []                       # nothing cached yet: nothing to report, nothing fetched
    o = M.ENDPOINTS["overview"]()
    keys = {r["key"] for r in o["layers"]}
    assert {"models_share", "compute_gap", "arena_gap", "pct_gap", "cited_share", "ev_share_gap", "battery_china", "byd_tesla",
            "node_gap", "controls", "ic_imports", "rel_1y"} <= keys
    assert sum(o["tally"].values()) == len(o["layers"])
    rows = M.READINGS()
    assert {r["key"] for r in rows} == keys
    assert all(r["lean"] in (-1, 0, 1) and r["tab"] in M.ENDPOINTS for r in rows)
    lean = {r["key"]: r["lean"] for r in rows}
    assert lean["rel_1y"] == -1 and lean["ev_share_gap"] == 1          # the fixture's US shares rise faster; China's EV lead widens
    B.json_safe(rows)


def test_every_endpoint_through_the_server(mocked):
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            for k, _ in topics.REGISTRY["china-us-tech"].tabs:
                r = await c.get(f"/api/china-us-tech/{k}")
                assert r.status == 200, k
                json.loads(await r.text())
            assert (await c.get("/china-us-tech")).status == 200
            assert (await c.get("/china-us-tech.js")).status == 200
    asyncio.run(go())


def test_hand_entered_rows_cite_a_source_and_memory_rows_say_verify():
    for f in (B.MANUAL_DIR / M.SLUG).glob("*.csv"):
        for r in B.manual_rows(M.SLUG, f.stem):
            assert r["source"].startswith("http"), (f.name, r)
            if "memory" in r.get("note", ""):
                assert "verify" in r["note"], (f.name, r)


def test_signals_cover_the_watchlist_from_cached_payloads(mocked):
    keys = [w["key"] for w in json.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())["china-us-tech"]]
    assert {r["key"] for r in M.SIGNALS()} == {"ev_exports", "chip_imports", "controls"}    # hand-entered rows only: nothing downloaded
    M.ENDPOINTS["models"]()
    M.ENDPOINTS["markets"]()
    rows = M.SIGNALS()
    assert [r["key"] for r in rows] == keys
    assert all(isinstance(r["crossed"], bool) and r["lean"] in (-1, 0, 1) and r["watch"] for r in rows)
    sig = {r["key"]: r for r in rows}
    assert sig["basket_gap"]["value"] < 0 and sig["models_12m"]["note"].startswith("US ")
    B.json_safe(rows)


def test_year_back_reads_yearly_and_monthly_rows():
    yearly = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2023-01-01", "2024-01-01", "2025-01-01"]))
    assert M._year_back(yearly) == (3.0, 2.0, False)
    monthly = pd.Series(range(1, 15), index=pd.date_range("2025-01-01", periods=14, freq="MS"), dtype=float)
    assert M._year_back(monthly) == (14.0, 2.0, True)


def test_signal_watch_points(monkeypatch):
    from app import cache
    cache._cache.clear()
    today = pd.Timestamp.now().normalize()
    real_rows, real_manual = M.manual_rows, M.manual
    monkeypatch.setattr(M, "manual_rows", lambda slug, name: [{"date": str((today - pd.Timedelta(days=3)).date()), "actor": "US", "event": "new rule",
                                                               "direction": "-1", "source": "https://x"}] if name == "controls" else real_rows(slug, name))
    falling = pd.Series([2.0, 1.5], index=pd.to_datetime(["2024-01-01", "2025-01-01"]))
    monkeypatch.setattr(M, "manual", lambda slug, name: falling if name == "ev_exports" else real_manual(slug, name))
    sig = {r["key"]: r for r in M.SIGNALS()}
    assert sig["controls"]["crossed"] and sig["controls"]["lean"] == -1
    assert sig["ev_exports"]["crossed"] and sig["ev_exports"]["lean"] == -1          # down 25% on a year


@pytest.mark.network
def test_live_sources():
    from app import cache
    cache._cache.clear()
    assert M.parse_epoch(B.fetch(M.EPOCH, 0, min_bytes=1000))["country"].isin(["US", "China"]).any()
    assert "China" in M.parse_owid(B.fetch(M.OWID.format(name=M.OWID_SHARE), 0))
    assert len(M.parse_openalex(B.fetch_json(M.OPENALEX.format(cc="CN", y=2024, extra=""), 0))) > 10
