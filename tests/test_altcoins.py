"""Altcoin Study (/altcoins) on fixtures (no network): the registry and old-page redirects, the buy-zone rule, each candidate's tab payload
(built from btc_cycles' background fill), the zones table across candidates and memecoins, READINGS, and every tab through the server.
smoke_patch() fills the memecoin prices for scripts/smoke.py (btc_cycles' own fixtures fill the candidates)."""
import asyncio
import json

import numpy as np
import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import altcoins as A
from app.topics import btc_cycles as C
from app.topics import memecoins as M
from tests import test_memecoins as TM
from tests.test_topics import _chart


def smoke_patch():
    TM.smoke_patch()


@pytest.fixture()
def filled(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(C, "FUND_DIR", tmp_path / "snaps" / "btc_fundamentals")
    monkeypatch.setattr(M, "SHARE_LOG", tmp_path / "share.csv")
    monkeypatch.setattr(C, "PACE", 0)
    B.STALE.clear()
    from app import cache
    cache._cache.clear()
    monkeypatch.setattr(B, "_download", TM._fake_download(_chart(mult=1.5)))
    C.fill_coins()
    M.fill()
    cache._cache.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


def _px(values):
    return pd.Series(values, index=pd.date_range("2025-10-01", periods=len(values), freq="D"), dtype=float)


def test_registry_and_redirects():
    t = topics.REGISTRY["altcoins"]
    assert t.title == "Altcoin Study" and topics.category("altcoins") == "Money & markets" and not t.private
    assert [k for k, _ in t.tabs] == ["zones", "hype", "ena", "sol", "near", "basket", "season"] and set(A.ENDPOINTS) == {k for k, _ in t.tabs}
    for old in ("hype", "ena", "sol", "near", "memecoins"):
        assert old not in topics.REGISTRY and topics.REDIRECTS[old][0] == "altcoins"
    assert topics.REDIRECTS["sol"] == ("altcoins", "sol") and topics.script("altcoins") == "altcoins.js"
    js = (B.MANUAL_DIR.parent / "app/static/topics/btc-cycles.js").read_text()
    assert all(f'{c}: "/altcoins#{c.lower()}"' in js for c in A.CANDIDATES)              # each candidate row links its tab


def test_buy_zone_rule():
    up = _px(np.linspace(50, 100, 365))                         # a steady climb: price far above its 200-day average
    z = A.buy_zone(up)
    assert z["status"] == "above zone" and z["basis"] == "200-day average" and z["floor"] == 50 and z["top"] == pytest.approx(up.iloc[-200:].mean())
    assert z["vs_top"] == pytest.approx(z["top"] / 100 - 1, abs=1e-4) and z["mid"] == pytest.approx((z["top"] + 50) / 2)
    down = _px(np.linspace(100, 40, 365))                       # a slide: below the average, so in the zone
    z = A.buy_zone(down)
    assert z["status"] == "in zone" and z["vs_top"] < 0 and z["floor"] == 40
    z = A.buy_zone(down, base_2028=100)                          # base ÷ 2 = 50 is under the 200-day average: it sets the top
    assert z["basis"] == "base case ÷ 2" and z["top"] == 50 and z["status"] == "in zone"
    z = A.buy_zone(down, base_2028=60)                           # base ÷ 2 = 30 is under the year's low: no zone
    assert z["status"] == "no zone" and z["mid"] is None and "double" in z["why"]
    z = A.buy_zone(down, base_2028=1000)                         # a high base case does not lift the top above the average
    assert z["basis"] == "200-day average"
    assert A.buy_zone(_px(np.linspace(1, 2, 150)))["status"] == "no data"
    old = _px(np.r_[np.full(300, 5.0), np.linspace(100, 90, 400)])          # only the last 365 days count for the floor
    assert A.buy_zone(old)["floor"] > 5


def test_coin_tab_and_zones(filled):
    f = A.ENDPOINTS["sol"]()
    B.json_safe(f)
    assert f["ticker"] == "SOL" and len(f["series"]["price"]) > 300 and len(f["projection"]) == 2
    assert f["sibling_pages"] == {"HYPE": "#hype", "ENA": "#ena", "SOL": "#sol", "NEAR": "#near"}
    z = f["zone"]
    assert z["status"] in ("in zone", "above zone", "no zone") and z["floor"] <= z["price"]
    if z["status"] != "no zone":
        assert z["floor"] <= z["mid"] <= z["top"] <= z["ma200"] + 1e-9
    d = A.ENDPOINTS["zones"]()
    B.json_safe(d)
    assert [r["ticker"] for r in d["coins"]] == [*A.CANDIDATES, *(c["ticker"] for c in M.coins_list())]
    assert all(r["status"] in ("in zone", "above zone", "no zone") for r in d["coins"]), [r for r in d["coins"] if "why" in r]
    assert sum(d["counts"].values()) == len(d["coins"]) and next(r for r in d["coins"] if r["ticker"] == "SOL")["top"] == z["top"]
    assert all(r["group"] == "Memecoin" and r["basis"] == "200-day average" for r in d["coins"][4:])         # no projection for memes
    r = A.READINGS()
    assert {x["key"] for x in r} >= {"zone_sol", "zone_doge", "state"} and all(x["lean"] in (-1, 0, 1) for x in r)


def test_before_the_fill_says_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(B, "_download", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline")))
    from app import cache
    cache._cache.clear()
    d = A._zones_now()
    assert all(r["status"] in ("loading", "error") for r in d["coins"]) and d["counts"]["in zone"] == 0
    cache._cache.clear()


def test_through_the_server(filled):
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            for k, _ in topics.REGISTRY["altcoins"].tabs:
                r = await c.get(f"/api/altcoins/{k}")
                assert r.status == 200, k
                json.loads(await r.text())
            assert (await c.get("/altcoins")).status == 200
            r = await c.get("/altcoins.js")
            assert r.status == 200 and "window.TOPIC" in await r.text()
            for old, tab in (("hype", "hype"), ("near", "near"), ("memecoins", "basket")):
                r = await c.get(f"/{old}", allow_redirects=False)
                assert r.status == 301 and r.headers["Location"] == f"/altcoins#{tab}"
            assert (await c.get("/coin.js")).status == 404
            idx = await (await c.get("/api/index")).json()
            assert "altcoins" in json.dumps(idx) and '"slug": "sol"' not in json.dumps(idx)
    asyncio.run(go())
