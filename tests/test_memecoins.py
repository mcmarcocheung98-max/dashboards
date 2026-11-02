"""Memecoins on fixtures (no network): the basket file, the paced fill and the daily share log, the basket and season payloads, the
season rule, READINGS, and every tab through the server. smoke_patch() points the downloads at the same fixtures for scripts/smoke.py.
The live CoinGecko ids are checked by the network test."""
import asyncio
import json

import pytest

from app import topics
from app.topics import _base as B
from app.topics import btc_cycles as C
from app.topics import memecoins as M
from tests.test_topics import _chart

CATS = [{"id": "layer-1", "market_cap": 2.5e12, "volume_24h": 9e10}, {"id": "meme-token", "market_cap": 6.2e10, "volume_24h": 4.1e9}]
GLOBAL = {"data": {"total_market_cap": {"usd": 3.1e12}, "market_cap_percentage": {"btc": 59.0}, "total_volume": {"usd": 1e11}}}


def _fake_download(charts):
    def dl(url, *a, **k):
        if url.startswith(M.CG_CATEGORIES):
            return json.dumps(CATS)
        if url.startswith(M.CG_GLOBAL):
            return json.dumps(GLOBAL)
        if "coins/bitcoin/" in url:
            return json.dumps(charts["btc"])
        seed = sum(map(ord, url)) % 7 + 2                                 # each coin its own path
        return json.dumps(_chart(mult=1.0 + seed / 4, seed=seed)["coin"])
    return dl


def smoke_patch():
    import tempfile
    from pathlib import Path
    M.SHARE_LOG = Path(tempfile.mkdtemp()) / "share.csv"
    real = B._download
    fake = _fake_download(_chart(mult=1.0))
    B._download = lambda url, *a, **k: fake(url) if "coingecko" in url else real(url, *a, **k)
    C.PACE = 0
    M.fill()


@pytest.fixture()
def mocked(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "SHARE_LOG", tmp_path / "share.csv")
    monkeypatch.setattr(C, "PACE", 0)
    B.STALE.clear()
    from app import cache
    cache._cache.clear()
    monkeypatch.setattr(B, "_download", _fake_download(_chart(mult=1.0)))
    yield
    cache._cache.clear()
    B.STALE.clear()


def test_basket_file():
    coins = M.coins_list()
    assert [c["ticker"] for c in coins] == ["DOGE", "SHIB", "PEPE", "BONK", "WIF", "TRUMP"]
    assert all(c["coingecko_id"] and c["chain"] for c in coins)
    assert "memecoins" not in topics.REGISTRY and topics.REDIRECTS["memecoins"] == ("altcoins", "basket")       # now tabs of Altcoin Study
    assert "memes" in {k for k, _ in topics.REGISTRY["altcoins"].tabs} and {"basket", "season"} <= set(topics.endpoints("altcoins")) and topics.helpers()["memecoins"] == "altcoins"


def test_before_the_fill_the_page_says_loading(mocked):
    d = M._basket_now()
    assert all(c["error"].startswith("loading") for c in d["coins"])
    assert "kpi" not in M._season_now() and M._season_now()["coins_missing"]


def test_fill_and_payloads(mocked):
    done = M.fill()
    assert set(done.values()) == {"ok"} and set(done) == {"BTC", "share", *(c["ticker"] for c in M.coins_list())}
    assert M.fill()["share"] == "ok" and len(M.share_log()) == 1                    # one log row a day
    b = M.ENDPOINTS["basket"]()
    B.json_safe(b)
    assert len(b["coins"]) == 6 and all("kpi" in c for c in b["coins"]) and b["basket_mcap"] > 0
    assert abs(sum(c["kpi"]["share"] for c in b["coins"]) - 1) < 1e-3
    k = b["coins"][0]["kpi"]
    assert 0 <= k["rsi"] <= 100 and 0 <= k["rsi_vs_btc"] <= 100 and k["from_high"] <= 0 and len(b["coins"][0]["spark"]) == 90
    assert "mcap" not in b["coins"][0]                                              # the series behind the totals stay server-side
    s = M.ENDPOINTS["season"]()
    B.json_safe(s)
    K = s["kpi"]
    assert K["state"] in ("meme season", "out of season", "in between") and K["lean"] in (-1, 0, 1)
    assert len(s["ratio"]) > 300 and len(s["equal_weight"]) > 300 and s["equal_weight"][0][1] == 100
    assert abs(s["ratio"][-1][1] - K["basket_mcap"] / s["btc_mcap"][-1][1]) < 1e-5
    assert s["share_log"][0]["share"] == pytest.approx(6.2e10 / 3.1e12, rel=1e-3)
    r = M.READINGS()
    assert {x["key"] for x in r} == {"state", "vs_btc_90d"} and all(x["tab"] == "season" for x in r)


def test_season_rule():
    assert M.season_state(0.4, 55) == ("meme season", 1)
    assert M.season_state(0.0, 72) == ("meme season", 1)
    assert M.season_state(-0.3, 40) == ("out of season", -1)
    assert M.season_state(-0.3, 55) == ("in between", 0)                             # trailing but turning up
    assert M.season_state(0.1, 50) == ("in between", 0)
    assert M.season_state(None, None) == ("no data", 0)


def test_through_the_server(mocked):
    M.fill()
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            for k in ("basket", "season"):
                r = await c.get(f"/api/altcoins/{k}")
                assert r.status == 200, k
                json.loads(await r.text())
            r = await c.get("/memecoins", allow_redirects=False)
            assert r.status == 301 and r.headers["Location"] == "/altcoins#basket"                  # old links keep working
    asyncio.run(go())


@pytest.mark.network
def test_live_ids():
    import requests
    ids = ",".join(c["coingecko_id"] for c in M.coins_list())
    got = requests.get(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}", timeout=30).json()
    assert {g["id"] for g in got} == {c["coingecko_id"] for c in M.coins_list()}
    cats = requests.get(M.CG_CATEGORIES, timeout=30).json()
    assert any(c.get("id") == M.MEME_CATEGORY for c in cats)
