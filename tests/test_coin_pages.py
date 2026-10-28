"""The standalone coin pages (/ena, /sol, /near) on fixtures (no network): registry and shared script, the payload built from btc_cycles'
background fill (series, projection, today's sentences, rank among the candidates), and every tab, page and script through the server."""
import asyncio
import json

import pytest

from app import topics
from app.topics import _base as B
from app.topics import _coin_page as P
from app.topics import btc_cycles as C
from tests.test_topics import _chart

PAGES = ("ena", "sol", "near")


@pytest.fixture()
def filled(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(C, "FUND_DIR", tmp_path / "snaps" / "btc_fundamentals")
    monkeypatch.setattr(C, "PACE", 0)
    B.STALE.clear()
    from app import cache
    cache._cache.clear()
    charts = _chart(mult=1.5)
    monkeypatch.setattr(B, "_download", lambda url, *a, **k: json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"]))
    C.fill_coins()
    yield
    cache._cache.clear()
    B.STALE.clear()


def test_pages_are_registered_and_share_one_script():
    for slug in PAGES:
        t = topics.REGISTRY[slug]
        assert t.script == "coin" and topics.script(slug) == "coin.js" and not t.private
        assert [k for k, _ in t.tabs] == ["overview", "fundamentals", "projection"]
        assert topics.category(slug) == "Money & markets" and slug.upper() in t.title
    assert topics.script("btc-cycles") == "btc-cycles.js"                     # the default is still the slug
    assert set(P.PAGES) == set(PAGES)
    js = (B.MANUAL_DIR.parent / "app/static/topics/btc-cycles.js").read_text()
    assert all(f'{s.upper()}: "/{s}"' in js for s in PAGES)                    # each candidate row links its page


def test_payload(filled):
    f = P.payload("SOL")
    B.json_safe(f)
    assert f["ticker"] == "SOL" and f["sector"].startswith("High-throughput") and len(f["series"]["price"]) > 300
    assert len(f["projection"]) == 2 and all(p["bear"] < p["base"] < p["bull"] for p in f["projection"])
    assert abs(f["kpi"]["beta"] - 1.5) < 0.05 and f["notes"].get("narrative")
    assert f["peers"]["n"] == len(C.coins_list()) and 1 <= f["peers"]["market_cap"] <= f["peers"]["n"]
    assert isinstance(f["now"], list) and f["sibling_pages"] == {"ENA": "/ena", "SOL": "/sol", "NEAR": "/near"}
    assert f["scenarios"]["scenarios"]
    eps = topics.endpoints("near")
    assert eps["overview"]()["ticker"] == "NEAR" and eps["projection"]() is eps["overview"]()       # one cached payload for the three tabs


def test_through_the_server(filled):
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            for slug in PAGES:
                for k, _ in topics.REGISTRY[slug].tabs:
                    r = await c.get(f"/api/{slug}/{k}")
                    assert r.status == 200, (slug, k)
                    assert json.loads(await r.text())["ticker"] == slug.upper()
                assert (await c.get(f"/{slug}")).status == 200
                r = await c.get(f"/{slug}.js")
                assert r.status == 200 and "window.TOPIC" in await r.text()
            assert (await c.get("/coin.js")).status == 404                   # the shared script only under a dashboard's name
            assert (await c.get("/btc-cycles.js")).status == 200
    asyncio.run(go())
