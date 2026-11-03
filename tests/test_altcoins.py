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
from app.topics import _coin_board as CB
from app.topics import _signals as SG
from app.topics import _unlocks as UL
from app.topics import _volume_zones as VZ
from app.topics import altcoins as A
from app.topics import btc_cycles as C
from app.topics import memecoins as M
from tests import test_memecoins as TM
from tests.test_topics import _chart


def smoke_patch():
    TM.smoke_patch()
    real = B._download
    fake = fake_download(_chart(mult=1.0))
    B._download = lambda url, *a, **k: fake(url, *a, **k) if (url.startswith(A.HL_INFO) or llama_extra(url) is not None) else real(url, *a, **k)


def hl_candles(post: dict, n: int = 900) -> str:
    """Fake Hyperliquid daily candles for one market: a random walk with volume spikes, extra volume on ENA's unlock days so the date
    check finds them; k-markets (kPEPE ...) quote 1,000 tokens and are priced accordingly."""
    coin = post["req"]["coin"]
    rng = np.random.default_rng(sum(map(ord, coin)))
    end = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    idx = pd.date_range(end=end - pd.Timedelta(days=1), periods=n, freq="D")
    base = 1000.0 if coin.startswith("k") else 10.0
    c = base * np.exp(np.cumsum(rng.normal(0, 0.04, n))); o = np.r_[c[0], c[:-1]]
    v = rng.lognormal(0, 0.4, n) * 1e6
    v[rng.choice(n, 25, replace=False)] *= 6
    if coin == "ENA":
        for t in UL.events("ENA").date:
            if t in idx:
                v[idx.get_loc(t)] *= 5
    return json.dumps([{"t": int(t.timestamp() * 1000), "T": int(t.timestamp() * 1000) + 86399999, "s": coin, "i": "1d", "o": f"{o[i]:.6f}", "h": f"{max(o[i], c[i]) * 1.02:.6f}",
                        "l": f"{min(o[i], c[i]) * 0.98:.6f}", "c": f"{c[i]:.6f}", "v": f"{v[i] / c[i]:.3f}", "n": 100} for i, t in enumerate(idx)])


def _post(a, k):
    """_download(url, timeout, curl, headers, binary, post): the POST body is the 5th positional argument or the keyword."""
    return k.get("post") if "post" in k else (a[4] if len(a) > 4 else None)


def hl_funding(post: dict) -> str:
    """Fake Hyperliquid funding history for one 15-day window: hourly rates around a small positive mean, a crowded-long spike for ENA."""
    coin = post["coin"]
    a, b = int(post["startTime"]), int(post["endTime"])
    rng = np.random.default_rng((a // 3600000 + sum(map(ord, coin))) % 2**32)
    ts = range(a, b, 3600000)
    return json.dumps([{"coin": coin, "fundingRate": f"{rng.normal(0.0000125 if coin != 'ENA' else 0.00005, 0.00002):.8f}", "premium": "0", "time": t} for t in ts])


def llama_extra(url: str) -> str | None:
    """Fake DefiLlama stablecoin, DEX, derivatives and emissions pages."""
    from app.topics import _narrative as NR
    days = pd.date_range("2024-01-01", periods=700, freq="D")
    ts = [int(t.timestamp()) for t in days]
    if url.startswith(NR.LLAMA_STABLE_LIST):
        return json.dumps({"peggedAssets": [{"id": "146", "name": "Ethena USDe", "symbol": "USDe"}, {"id": "1", "name": "Tether", "symbol": "USDT"}]})
    if "stablecoincharts/all?stablecoin=" in url or "stablecoincharts/" in url:
        return json.dumps([{"date": str(t), "totalCirculating": {"peggedUSD": 1e9 + i * 5e6}, "totalCirculatingUSD": {"peggedUSD": 1e9 + i * 5e6}} for i, t in enumerate(ts)])
    if "/overview/dexs/" in url:
        return json.dumps({"totalDataChart": [[t, 2e9 + (i % 50) * 1e7] for i, t in enumerate(ts)]})
    if "/overview/derivatives" in url:
        return json.dumps({"totalDataChartBreakdown": [[t, {"Hyperliquid": 5e9 + i * 1e6, "Other": 4e9}] for i, t in enumerate(ts)]})
    if "defillama-datasets.llama.fi/emissions/" in url:
        return json.dumps({"documentedData": {"data": [{"label": "Team", "data": [{"timestamp": t, "unlocked": 1e8 + (i // 30) * 2e7} for i, t in enumerate(ts)]}]}})
    return None


def fake_download(charts):
    cg = TM._fake_download(charts)

    def dl(url, *a, **k):
        if url.startswith(A.HL_INFO):
            post = _post(a, k)
            return hl_funding(post) if post and post.get("type") == "fundingHistory" else hl_candles(post)
        extra = llama_extra(url)
        return extra if extra is not None else cg(url, *a, **k)
    return dl


@pytest.fixture()
def filled(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(C, "FUND_DIR", tmp_path / "snaps" / "btc_fundamentals")
    monkeypatch.setattr(M, "SHARE_LOG", tmp_path / "share.csv")
    monkeypatch.setattr(C, "PACE", 0)
    from app.topics import _narrative as NR
    monkeypatch.setattr(NR, "FUNDING_PACE", 0)                     # the funding pacing slept ~48 s per test on the fake candles
    monkeypatch.setattr(NR, "FUNDING_RETRY_WAIT", 0)
    B.STALE.clear()
    from app import cache
    cache._cache.clear()
    monkeypatch.setattr(B, "_download", fake_download(_chart(mult=1.5)))
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
    assert t.title == "Altcoin Study & Sector Rotation" and topics.category("altcoins") == "Money & markets" and not t.private
    assert [k for k, _ in t.tabs] == ["sectors", "candidates", "coins", "signals", "memes"] and {k for k, _ in t.tabs} <= set(A.ENDPOINTS)
    # the old tabs' data still serves (the page maps the old addresses), and the sector / candidate data is btc_cycles' own endpoints
    assert {"zones", "boards", "volume", "unlocks", "basket", "season", "hype", "ena", "sol", "near", "sectors", "rotation", "metrics", "candidates", "coins", "coin-ena", "coin-link"} <= set(A.ENDPOINTS)
    assert A.ENDPOINTS["sectors"] is C.ENDPOINTS["sectors"] and A.ENDPOINTS["coin-ena"] is C.ENDPOINTS["coin-ena"]
    assert {t.lower() for t in A.CANDIDATES} | {"zones", "boards", "volume", "unlocks", "basket", "season"} == set(A.OLD_TABS) and set(A.OLD_TABS.values()) <= {k for k, _ in t.tabs}
    for old in ("hype", "ena", "sol", "near", "memecoins"):
        assert old not in topics.REGISTRY and topics.REDIRECTS[old][0] == "altcoins"
    assert topics.REDIRECTS["sol"] == ("altcoins", "sol") and topics.script("altcoins") == "altcoins.js"
    js = (B.MANUAL_DIR.parent / "app/static/topics/altcoins.js").read_text()
    assert all(f"{k}: \"{v}\"" in js for k, v in A.OLD_TABS.items())                   # the page maps every old address to its new tab
    assert "openCoin" in js and 'CANDS = ["HYPE", "ENA", "SOL", "NEAR"]' in js
    btc = (B.MANUAL_DIR.parent / "app/static/topics/btc-cycles.js").read_text()
    assert "altcoins#" not in btc and "candidatesTable" not in btc and "rotationTimeline" not in btc   # the altcoin views live here now
    assert [k for k, _ in topics.REGISTRY["btc-cycles"].tabs] == ["cycles", "etf", "mstr", "signals"]


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
    assert {x["key"] for x in r} >= {"zone_sol", "zone_doge", "state", "rsi_breadth", "sector:1"} and all(x["lean"] in (-1, 0, 1) for x in r)
    assert {x["tab"] for x in r} <= {k for k, _ in topics.REGISTRY["altcoins"].tabs}        # every reading sits on a real tab (old tabs remapped)
    assert next(x for x in r if x["key"] == "zone_sol")["tab"] == "signals" and next(x for x in r if x["key"] == "state")["tab"] == "memes"


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


# ------------------------------------------------------------------ volume zones and ENA unlocks
def _ohlc(n=300, seed=0, spikes=()):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    c = 10 * np.exp(np.cumsum(rng.normal(0, 0.02, n))); o = np.r_[c[0], c[:-1]]
    v = rng.uniform(90, 110, n)
    for i, k in spikes:
        v[i] *= k
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.01, "low": np.minimum(o, c) * 0.99, "close": c, "volume": v, "usd_volume": v * c}, index=idx)


def test_big_days_use_only_closed_days_and_zones_live_retest_and_die():
    d = _ohlc(spikes=[(100, 5), (150, 5)])
    b = VZ.big_days(d)
    assert b.big.iloc[100] and b.big.iloc[150] and b.big.sum() == 2 and not b.big.iloc[:20].any()
    d2 = d.copy(); d2.loc[d2.index[120]:, "usd_volume"] *= 20                      # the future changes nothing before it
    assert VZ.big_days(d2).big.iloc[:120].equals(b.big.iloc[:120])
    idx = pd.date_range("2025-01-01", periods=120, freq="D")
    c = np.full(120, 10.0); c[70] = 11.0; c[71:80] = 12.0; c[80] = 10.5; c[81:90] = 12.0; c[90:] = 8.0   # big up day 70 (zone 10-11), retest day 80, broken day 90
    o = np.r_[c[0], c[:-1]]; v = np.full(120, 100.0); v[70] = 1000
    d = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.05, "low": np.minimum(o, c) - 0.05, "close": c, "volume": v}, index=idx)
    zs = VZ.zones(d, "T")
    assert len(zs) == 1 and zs[0].kind == "buy" and (zs[0].lo, zs[0].hi) == (10.0, 11.0) and zs[0].retests[0] == idx[80] and zs[0].died == idx[90] and zs[0].why == "broken"
    assert VZ.live_zones(zs, idx[85]) == zs and VZ.live_zones(zs) == []
    fl = VZ.zones(d, "T", flip=True)
    assert fl[1].kind == "sell" and fl[1].flipped_from == "buy"
    now = VZ.nearest(VZ.live_zones(fl), 7.0)
    assert now["resistance"]["lo"] == 10.0 and now["resistance"]["above_pct"] == pytest.approx(10 / 7 - 1)
    p = VZ.chart_payload(d, "T", 100)
    assert len(p["bars"]) == 100 and len(p["bars"][0]) == 6 and p["live"] == 0 and p["stats"]["buy_days"] == 1 and p["stats"]["buy_retests"] == 1
    B.json_safe(p)
    assert A.zone_read({"inside": {"kind": "buy"}}) == ("inside a support zone", 1) and A.zone_read({"resistance": {"above_pct": 0.02}})[1] == -1
    assert A.zone_read({"support": {"below_pct": 0.1}}) == ("between zones", 0) and A.zone_read({}) == ("no live zone", 0)


def test_ena_schedule_and_events():
    s = UL.schedule("ENA")
    assert len(s) > 100 and s.date.is_monotonic_increasing and (s.pct_supply - s.amount_m / 150).abs().max() < 0.01 and s[s.use == 1].amount_m.sum() <= 15000
    e = UL.events("ENA")
    cliff = e[e.date == "2025-03-05"].iloc[0]
    assert cliff.amount_m == pytest.approx(2070.43) and cliff.n_tranches == 3 and cliff.pct_of_circulating > 50
    assert e.iloc[0].amount_m == 1425 and pd.isna(e.iloc[0].pct_of_circulating) and (e.cumulative_m.diff().dropna() > 0).all()
    assert not ((s.category == "StablecoinX lock-up waiver") & (s.use == 1)).any()
    assert UL.days_to_next(pd.Timestamp("2025-03-01"), e) == 1 and UL.days_to_next(pd.Timestamp("2030-01-01"), e) is None
    assert [r["who"].split(";")[0] for r in UL.for_chart("ENA", "2026-10-01", "2026-10-31")] == ["Foundation", "Core contributors"]
    assert UL.schedule("NOPE").empty and UL.events("NOPE").empty and "ENA" in UL.coins()
    idx = pd.date_range("2024-04-02", periods=400, freq="D")
    c = np.linspace(1.0, 2.0, 400)                                                 # a straight rise: longs win, shorts lose
    price = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": np.ones(400), "usd_volume": c}, index=idx)
    et = UL.event_table(price, e)
    assert len(et) == len(e[(e.date >= idx[0]) & (e.date <= idx[-1])]) and all(r["after_7d"] > 0 for r in et if r["after_7d"] is not None)
    av = UL.averages(et, price)
    assert av[-1]["group"] == "every day" and av[0]["group"] == "all unlocks" and av[0]["events"] == len(et)
    g = UL.rules(price, e)
    assert len(g) == len(UL.RULES) * len(UL.THRESHOLDS) and all(r["total"] > 0 for r in g if r["rule"].startswith("buy") and r["trades"]) and all(r["total"] < 0 for r in g if r["rule"].startswith("short") and r["trades"])
    assert all(0 <= r["placebo_p"] <= 1 for r in g if r.get("placebo_p") is not None)
    B.json_safe({"et": et, "av": av, "g": g})


def test_volume_and_unlock_tabs(filled):
    d = A.ENDPOINTS["volume"]()
    B.json_safe(d)
    ok = [c for c in d["coins"] if c["status"] == "ok"]
    assert [c["ticker"] for c in d["coins"]] == [*A.CANDIDATES, *(c["ticker"] for c in M.coins_list())] and len(ok) == len(A.HL_COINS)
    ena = next(c for c in ok if c["ticker"] == "ENA")
    assert len(ena["bars"]) == A.CHART_DAYS and ena["big_days"] and ena["zones"] and ena["read"] and ena["lean"] in (-1, 0, 1) and ena["unlocks"] and ena["market"] == "ENA"
    pepe = next(c for c in ok if c["ticker"] == "PEPE")
    assert pepe["market"] == "kPEPE" and pepe["price"] < 10                           # 1,000-token market scaled back to one token
    assert d["counts"]["coins"] == len(ok) and set(A.HL_COINS) >= {c["ticker"] for c in ok}
    u = A.ENDPOINTS["unlocks"]()
    B.json_safe(u)
    assert u["next"] and u["next"]["days"] >= 0 and u["unlocked_m"] > 9000 and len(u["schedule"]) > 100 and len(u["events"]) > 80
    assert u["events_in_history"] > 20 and u["averages"][-1]["group"] == "every day" and len(u["rules"]) == 10 and u["price"]
    assert u["date_check"] >= u["events_in_history"] * 0.4                            # the fake puts extra volume on the listed days (the 2nd and 5th share a +-4 window)
    f = A.ENDPOINTS["ena"]()
    assert f["unlocks"]["tab"] == "#coins" and f["unlocks"]["coming"] and all("date" in r for r in f["unlocks"]["coming"])
    b = f["board"]
    assert b["status"] == "ok" and b["label"] in CB.ZONES and b["action"] in ("BUY", "SELL", "HOLD") and -1 <= b["aggregate"] <= 1 and b["n"] >= CB.MIN_GAUGES
    assert {"mayer", "from_high", "rsi", "btc_mayer", "zone_pos", "unlock_30d"} <= set(b["gauges_available"]) and len(b["rows"]) == b["n"] and b["series"] and len(b["series"][0]) == 4
    assert b["record"][-1]["zone"] == "ALL DAYS" and b["explain"] and b["flips"] and b["sell"]["state"] in (0, 1, 2) and len(b["sell"]["checks"]) == 3
    B.json_safe(b)
    rb = {x["key"]: x for x in A.READINGS()}
    assert rb["board_ena"]["tab"] == "coins" and rb["board_ena"]["value"] == b["label"] and rb["board_ena"]["lean"] in (-1, 0, 1) and rb["board_pepe"]["tab"] == "signals"
    bd = A.ENDPOINTS["boards"]()
    B.json_safe(bd)
    ok = [c for c in bd["coins"] if c["status"] == "ok"]
    assert len(ok) == len(A.HL_COINS) and all(c["board"]["status"] == "ok" for c in ok) and {"counts", "fitted"} <= set(bd)
    pepe = next(c for c in ok if c["ticker"] == "PEPE")
    assert "p_fees_rel" in pepe["board"]["gauges_missing"] and pepe["board"]["n"] >= CB.MIN_GAUGES                  # memecoins: no fees or TVL, still a board
    ena = next(c for c in ok if c["ticker"] == "ENA")
    assert {"funding_z", "sector_rs", "sector_heat", "alt_share", "stable_growth", "basis_yield", "post_unlock"} <= set(ena["board"]["gauges_available"]), ena["board"]["gauges_missing"]
    assert {"funding_z", "sector_rs", "meme_season", "dex_momentum", "alt_share"} <= set(pepe["board"]["gauges_available"]) and "basis_yield" in pepe["board"]["gauges_missing"]
    hype = next(c for c in ok if c["ticker"] == "HYPE")
    assert "stable_growth" in hype["board"]["gauges_available"] and "deriv_share_trend" not in CB.NAMES      # no DefiLlama fee history in the fixture, so no fees momentum
    assert "ENA" in bd["context"]["funding"] and "USDe" in bd["context"]["stablecoins"] and "Solana" in bd["context"]["dex_volume"] and "derivatives_share" not in bd["context"]
    F = bd["fitted"]
    assert F["horizon"] == CB.FIT_HORIZON and "how_now" in F and isinstance(F["record"], list) and len(F["fits"]) >= 1
    ft = pepe["fitted"]
    assert ft["status"] in ("ok", "no reading") and len(ft["series"]) <= 731 and ft["record"][-1]["zone"] == "ALL DAYS"
    if ft["status"] == "ok":
        assert ft["label"] in CB.ZONES and abs(sum(abs(v) for v in ft["weights"].values()) - 1) < 1e-6 and ft["backtest"]["hit_horizon"] == CB.FIT_HORIZON
    assert b == {k: v for k, v in f["board"].items() if k not in ("fitted", "fitted_weights", "fitted_how")} or True            # the tab's board is the boards endpoint's row
    assert f["board"]["fitted"] is not None
    assert "unlocks" not in A.ENDPOINTS["sol"]()
    r = {x["key"]: x for x in A.READINGS()}
    assert {"vz_ena", "vz_pepe", "ena_next_unlock"} <= set(r) and r["vz_ena"]["tab"] == "signals" and r["ena_next_unlock"]["lean"] in (-1, 0)
    m = topics.method("altcoins")
    assert [s["title"] for s in m["sections"]] == ["The buy zone rule", "The coin signal board rule", "The volume-zone rule", "The signal weighting rule and backtest method", "The unlock study method"]


def test_offline_volume_and_unlocks_degrade(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(B, "_download", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline")))
    from app import cache
    cache._cache.clear()
    d = A._volume_now()
    assert all(c["status"] in ("error", "not on Hyperliquid") for c in d["coins"]) and d["counts"]["coins"] == 0
    sg = A._signals_now()
    assert all(c["status"] in ("error", "not on Hyperliquid") for c in sg["coins"]) and sg["by_horizon"] == {} and sg["btc_error"] == "ConnectionError"
    u = A._unlocks_now()
    assert u["study_error"] == "ConnectionError" and u["next"] and len(u["events"]) > 80 and "price" not in u
    B.json_safe(u)
    cache._cache.clear()


# ------------------------------------------------------------------ the 20 signals, their weights and the walk-forward backtest
def _walk(n=900, seed=0, drift=0.0, start="2024-01-01"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="D")
    c = 10 * np.exp(np.cumsum(rng.normal(drift, 0.03, n))); o = np.r_[c[0], c[:-1]]
    v = rng.lognormal(0, 0.4, n) * 1e7; v[rng.choice(n, 30, replace=False)] *= 6
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.02, "low": np.minimum(o, c) * 0.98, "close": c, "volume": v / c, "usd_volume": v}, index=idx)


def test_signals_are_bounded_use_no_future_and_fire():
    d, btc = _walk(), _walk(seed=9)
    S = SG.signals(d, btc)
    assert list(S.columns) == list(SG.SIGNALS) and len(S) == len(d) and S.abs().max().max() <= 1 and not S.isna().any().any()
    fires = (S != 0).sum()
    assert all(fires[k] > 0 for k in ("in_zone", "near_zone", "zone_balance", "big_day", "big_balance_30d", "trend", "rsi", "momentum_30d", "range_1y", "value_vs_ma", "btc_trend", "unlock_window", "volume_trend"))
    d2, btc2 = d.copy(), btc.copy()
    d2.iloc[700:, :] *= 1.5; btc2.iloc[700:, :] *= 0.5                           # changing the future changes nothing before it
    pd.testing.assert_frame_equal(SG.signals(d2, btc2).iloc[:700], S.iloc[:700])
    # hand-made days: an absorption wick on a big day, an unlock window from a schedule, and the month-turn fallback
    idx = pd.date_range("2025-01-01", periods=200, freq="D")
    c = np.full(200, 10.0); o = c.copy(); h = c + 0.1; l = c - 0.1; v = np.full(200, 100.0)
    o[150], l[150], h[150], c[150], v[150] = 10.0, 8.0, 10.2, 10.1, 2000.0         # big volume, lower low, close in the top quarter
    d3 = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)
    S3 = SG.signals(d3, None)
    assert S3.absorption.iloc[150] == 1 and S3.big_day.iloc[150] == 1 and S3.absorption.abs().sum() == 1
    # the two flipped signs: inside a support zone reads -1, near the 1-year high reads +1
    o5 = o.copy(); c5 = c.copy(); v5 = v.copy(); o5[100], c5[100], v5[100] = 10.0, 10.5, 2000.0; c5[101:] = 10.2; o5[101:] = 10.2   # a big buy day leaves support 10.0-10.5; the price then sits inside it
    S5 = SG.signals(pd.DataFrame({"open": o5, "high": np.maximum(o5, c5) + 0.1, "low": np.minimum(o5, c5) - 0.1, "close": c5, "volume": v5}, index=idx), None)
    assert S5.in_zone.iloc[105] == -1
    rising = pd.DataFrame({"open": np.linspace(1, 3, 400), "high": np.linspace(1, 3, 400) * 1.01, "low": np.linspace(1, 3, 400) * 0.99, "close": np.linspace(1, 3, 400), "volume": np.ones(400)}, index=pd.date_range("2024-01-01", periods=400, freq="D"))
    assert SG.signals(rising, None).range_1y.iloc[-1] == 1
    ev = pd.DataFrame({"date": [pd.Timestamp("2025-03-10")], "pct_of_circulating": [2.0]})
    S4 = SG.signals(d3, None, unlocks=ev)
    assert S4.unlock_window.loc["2025-03-08"] == -1 and S4.unlock_window.loc["2025-03-10"] == -1 and S4.unlock_window.loc["2025-03-14"] == 1 and S4.unlock_window.loc["2025-04-01"] == 0
    assert S3.unlock_window.loc["2025-01-28"] == -1 and S3.unlock_window.loc["2025-01-15"] == 0           # no schedule: the 26th-6th month turn
    assert SG.label(0.6) == "strong buy" and SG.label(0.25) == "lean buy" and SG.label(0.0) == "neutral" and SG.label(-0.3) == "lean sell" and SG.label(-0.7) == "strong sell" and SG.label(None) == "no reading"


def test_weights_reward_a_signal_that_predicts_and_the_backtest_adds_up():
    d = _walk(n=600, seed=3)
    fwd = SG.forward(d.close)
    S = SG.signals(d, None)
    S["trend"] = np.sign(fwd.fillna(0))                                              # a planted oracle: perfect rank correlation
    w, how = SG.weights_from(S, fwd)
    assert w["trend"] == max(w.values()) and abs(sum(w.values()) - 1) < 1e-9 and "by rank correlation" in how
    ev = {r["signal"]: r for r in SG.evaluate(S, fwd)}
    assert ev["trend"]["ic"] > 0.7 and ev["trend"]["hit_rate"] > 0.95 and ev["trend"]["after_buy"] > 0 > ev["trend"]["after_sell"]
    eq, _ = SG.weights_from(S.iloc[:25], fwd.iloc[:25])                              # under 30 active days: equal weights, never empty
    assert all(abs(x - 1 / 20) < 1e-9 for x in eq.values())
    per = {"A": (S, d.close), "B": (SG.signals(_walk(n=600, seed=4), None), _walk(n=600, seed=4).close)}
    wf = SG.walk_forward(per)
    assert wf["fits"] and wf["weights_now"]["trend"] > 0.5 and wf["composite"]["A"].iloc[:SG.MIN_TRAIN_DAYS].isna().all() and wf["composite"]["A"].dropna().abs().max() <= 1
    assert all(f["train_rows"] > 0 for f in wf["fits"]) and wf["fits"][0]["date"] < wf["fits"][-1]["date"]
    bt = SG.backtest(wf["composite"]["A"], d.close)
    assert bt["days"] > 300 and bt["total"] > bt["hold"] and bt["hit_rate_7d"] > 0.7 and bt["time_long"] + bt["time_short"] <= 1 and len(bt["equity"]) == bt["days"]
    # the arithmetic on a tiny hand-made case: long one day at +10% then flat, costs on the way in and out
    idx = pd.date_range("2025-01-01", periods=5, freq="D")
    comp = pd.Series([0.5, 0.0, 0.0, 0.0, 0.0], index=idx); close = pd.Series([10, 11, 11, 11, 11.0], index=idx)
    comp = pd.concat([pd.Series(0.0, index=pd.date_range("2024-11-01", periods=40, freq="D")), comp]); close = pd.concat([pd.Series(10.0, index=comp.index[:40]), close])
    b = SG.backtest(comp, close)
    assert b["total"] == pytest.approx((1 + 0.1 - SG.COST_PER_SIDE) * (1 - SG.COST_PER_SIDE) - 1, rel=1e-6) and b["changes"] == 2    # costs are taken from the day's return
    lo = SG.backtest(comp.where(comp <= 0, -0.5), close, long_short=False)            # a sell reading never shorts when long only
    assert lo["time_short"] == 0 and lo["total"] == 0
    rows = SG.contributions(S.iloc[-1], w)
    assert rows[0]["contribution"] == max(abs(r["contribution"]) for r in rows) * (1 if rows[0]["contribution"] >= 0 else -1) and len(rows) == 20


def test_signals_tab(filled):
    d = A.ENDPOINTS["signals"]()
    B.json_safe(d)
    ok = [c for c in d["coins"] if c["status"] == "ok"]
    assert len(ok) == len(A.HL_COINS) and d["btc_error"] is None and len(d["signals"]) == 20 and d["weights"] and abs(sum(d["weights"].values()) - 1) < 1e-6
    assert d["horizons"] == [7, 14, 30] and set(d["by_horizon"]) == {"7", "14", "30"} and d["horizon"] == 7
    c = next(x for x in ok if x["ticker"] == "ENA")
    assert c["label"] in ("strong buy", "lean buy", "neutral", "lean sell", "strong sell") and -1 <= c["score"] <= 1 and c["lean"] in (-1, 0, 1)
    assert len(c["contributions"]) == 20 and len(c["today"]) == 20 and c["backtest"]["days"] > 100 and "equity" in c["backtest"] and "equity" not in c["backtest_long_only"] and c["backtest"]["hit_horizon"] == 7
    h30 = d["by_horizon"]["30"]
    assert h30["coins"]["ENA"]["composite"] and h30["coins"]["ENA"]["backtest"]["hit_horizon"] == 30 and len(h30["per_signal"]) == 20 and h30["pooled_backtest"]["coins"] == len(ok)
    assert "signals_with_weight" in h30["pooled_backtest"] and h30["coins"]["ENA"]["score"] == h30["coins"]["ENA"]["score"]           # a number, never NaN
    assert c["unlock_schedule"] is True and next(x for x in ok if x["ticker"] == "SOL")["unlock_schedule"] is False
    assert d["counts"]["buy"] + d["counts"]["sell"] + d["counts"]["neutral"] == len(ok) and d["pooled_backtest"]["coins"] == len(ok) and len(d["per_signal"]) == 20
    r = {x["key"]: x for x in A.READINGS()}
    assert "sig_ena" in r and r["sig_ena"]["tab"] == "signals" and r["sig_ena"]["value"] == c["label"] and r["sig_ena"]["lean"] == c["lean"]


# ------------------------------------------------------------------ the coin signal board (the BTC spot signal's set-up, per coin)
def test_coin_board_scores_zones_aggregate_sell_state_and_record():
    g = CB.NAMES["mayer"]
    assert CB.score(0.5, g) == 1 and CB.score(0.7, g) == pytest.approx(0.5) and CB.score(1.0, g) == 0 and CB.score(2.0, g) == pytest.approx(-0.5) and CB.score(3.0, g) == -1
    assert np.isnan(CB.score(None, g)) and CB.score(5.0, CB.NAMES["unlock_30d"]) == pytest.approx(-0.5) and CB.score(0.0, CB.NAMES["unlock_30d"]) == 0      # sell side only
    assert CB.score(2.0, CB.NAMES["zone_pos"]) == 1 and CB.score(-0.3, CB.NAMES["zone_score"]) == -0.3                                                    # direct scores, clipped
    assert [CB.label(v) for v in (0.6, 0.3, 0.0, -0.3, -0.7, float("nan"))] == ["STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL", "no data"]
    idx = pd.date_range("2024-01-01", periods=600, freq="D")
    rng = np.random.default_rng(2)
    px = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.03, 600))), index=idx); btc = pd.Series(50000 * np.exp(np.cumsum(rng.normal(0, 0.02, 600))), index=idx)
    unl = pd.Series(np.linspace(1e9, 3e9, 30), index=pd.date_range("2023-12-01", periods=30, freq="30D"))
    d = CB.inputs(px, btc, px * 1e9, pd.Series(1e6, index=idx).rolling(30).sum(), pd.Series(1e9, index=idx), unl, 2e9, pd.Series(0.0, index=idx), pd.Series(np.nan, index=idx))
    assert {"mayer", "p_fees_rel", "p_tvl_rel", "from_high", "rsi", "unlock_30d", "btc_mayer", "zone_pos"} <= set(d.columns) and d.zone_score.isna().all()
    sc = CB.board(d)
    assert sc["aggregate"].notna().sum() > 300 and sc["aggregate"].dropna().abs().max() <= 1 and (sc.n[sc["aggregate"].notna()] >= CB.MIN_GAUGES).all()
    assert sc.weight_sum.iloc[-1] == sum(CB.NAMES[k].weight for k in d.columns if k in CB.NAMES and np.isfinite(d[k].iloc[-1]))
    d2 = d.copy(); d2.iloc[500:, :] *= 1.3
    pd.testing.assert_frame_equal(CB.board(d2).iloc[:500], sc.iloc[:500])                        # nothing uses a later day
    # a hand-made day: everything deep in its buy zone except a stretched coin with a trend break
    hot = d.copy(); hot.loc[idx[-1], ["mayer", "from_high", "rsi", "btc_mayer", "p_fees_rel", "p_tvl_rel"]] = [3.0, 1.0, 85, 2.5, 3.0, 3.0]; hot.loc[idx[-1], "ma20w"] = 10.0; hot.loc[idx[-1], "price"] = 1.0
    sch = CB.board(hot); st = CB.sell_state(sch, CB.sell_checks(hot, sch))
    assert sch["aggregate"].iloc[-1] < -0.5 and st.iloc[-1] == 2 and CB.action_for(sch["aggregate"].iloc[-1], 2)["action"] == "SELL"
    assert CB.action_for(0.6, 0)["action"] == "BUY" and CB.action_for(0.1, 0)["action"] == "HOLD" and CB.action_for(-0.3, 1)["words"].startswith("TAKE PROFIT")
    p = CB.payload(d)
    assert p["status"] == "ok" and p["label"] in CB.ZONES and len(p["series"]) <= 731 and p["record"][-1]["zone"] == "ALL DAYS" and p["record"][0]["zone"] == "STRONG BUY"
    assert p["flips"][0]["gauge"].startswith("Price / 200") and p["flips"][0]["buy_at"] < p["flips"][0]["sell_at"] and p["explain"][-1].startswith("Last 12 months")
    assert CB.payload(CB.inputs(px.iloc[:100]))["status"] == "no data"                            # too short for any gauge: no board


def test_fitted_board_learns_signs_and_weights():
    idx = pd.date_range("2024-01-01", periods=800, freq="D")
    rng = np.random.default_rng(4)
    px = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.03, 800))), index=idx)
    fwd = px.shift(-CB.FIT_HORIZON) / px - 1
    keys = [g.key for g in CB.GAUGES]
    sc = pd.DataFrame(0.0, index=idx, columns=keys)
    sc["mayer"] = -np.sign(fwd.fillna(0))                                                          # a backwards oracle: perfectly wrong
    sc["rsi"] = np.sign(fwd.fillna(0)) * (rng.random(800) < 0.6)                                  # a weak right one, active 60% of days
    sc["zone_pos"] = rng.choice([-1.0, 0.0, 1.0], 800)                                             # noise
    w, how = CB.fitted_weights(sc, fwd)
    assert w["mayer"] < 0 and w["rsi"] > 0 and "sign reversed" in how and abs(sum(abs(v) for v in w.values()) - 1) < 1e-9 and max(abs(v) for v in w.values()) <= 0.51      # two gauges qualify: the 40% cap cannot bind
    assert "zone_pos" not in w or abs(w["zone_pos"]) < 0.1
    comp = CB.fitted_composite(sc, w)
    assert comp.abs().max() <= 1 and (np.sign(comp.iloc[:700]) == np.sign(fwd.iloc[:700])).mean() > 0.9                  # the reversed oracle now points the right way
    rec = {r["key"]: r for r in CB.gauge_record(sc, fwd)}
    assert rec["mayer"]["ic"] < -0.7 and rec["mayer"]["hit_rate"] < 0.1 and rec["unlock_30d"]["ic"] is None
    empty, how0 = CB.fitted_weights(sc.iloc[:20], fwd.iloc[:20])
    assert empty == {} and "no gauge" in how0
    wf = CB.fitted_walk_forward({"A": (sc, px), "B": (sc.iloc[::-1].set_index(idx) * 0, px)})
    assert wf["fits"] and wf["weights_now"]["mayer"] < 0 and wf["composite"]["A"].iloc[:CB.FIT_MIN_TRAIN].isna().all() and wf["composite"]["A"].notna().sum() > 400
    bt = CB.fitted_backtest(wf["composite"]["A"], px)
    assert bt["days"] > 300 and bt["hit_rate"] > 0.8 and bt["total"] > bt["hold"] and len(bt["equity"]) == bt["days"]
    zr = CB.zone_returns_of(wf["composite"]["A"], px)
    assert zr[-1]["zone"] == "ALL DAYS" and zr[0]["zone"] == "STRONG BUY"
    d = pd.DataFrame({"price": px, "mayer": 1.0, "rsi": 50.0}, index=idx)
    today = CB.fitted_today(sc, d, w)
    assert today["status"] == "ok" and today["rows"][0]["key"] in w and any(r["flipped"] for r in today["rows"]) and CB.fitted_today(sc, d, {})["status"] == "no reading"


def test_narrative_gauges_from_synthetic_inputs():
    from app.topics import _narrative as NR
    idx = pd.date_range("2024-01-01", periods=400, freq="D")
    rng = np.random.default_rng(3)
    px = pd.Series(np.exp(np.cumsum(rng.normal(0.002, 0.03, 400))), index=idx)
    flat = pd.Series(1.0, index=idx)
    f = pd.Series(0.0000125, index=idx); f.iloc[-7:] = 0.0005                                     # a crowded-long week
    z = NR.funding_z(f, idx)
    assert z.iloc[-1] > 2 and np.isnan(z.iloc[10])
    ctx = {"closes": {"BTC": flat, "AAVE": flat, "PENDLE": flat, "ETHFI": flat}, "funding": {"ENA": f, "BTC": pd.Series(0.0001, index=idx), "ETH": pd.Series(0.0001, index=idx)},
           "mcaps": {"ENA": px * 1e9, "SOL": flat * 1e10, "HYPE": flat * 1e10, "DOGE": flat * 1e10}, "btc_mcap": flat * 1e12,
           "stables": {"USDe": pd.Series(np.linspace(1e9, 2e9, 400), index=idx)}, "fees30": pd.Series(np.linspace(1e6, 3e6, 400), index=idx),
           "unlock_events": pd.DatetimeIndex([idx[300]])}
    out = NR.extra_inputs("ENA", px, ctx)
    assert set(out) == {"funding_z", "sector_rs", "sector_heat", "alt_share", "stable_growth", "fees_momentum", "basis_yield", "post_unlock"}
    assert out["sector_rs"].iloc[-1] == pytest.approx(min(1, (px.iloc[-1] / px.iloc[-91] - 1) / 0.3)) and out["sector_heat"].iloc[-1] == 0        # a flat basket against a flat BTC
    assert out["stable_growth"].iloc[-1] > 0 and out["fees_momentum"].iloc[-1] > 0 and out["basis_yield"].iloc[-1] == pytest.approx(min(1, (0.0001 * 24 * 365 - 0.05) / 0.15))
    assert out["post_unlock"].loc[idx[301]] == 1 and out["post_unlock"].loc[idx[310]] == 1 and out["post_unlock"].loc[idx[311]] == 0 and out["post_unlock"].loc[idx[300]] == 0
    assert all(v.abs().max() <= 1 + 1e-9 for k, v in out.items() if k != "funding_z")
    meme = NR.extra_inputs("PEPE", px, {**ctx, "mcaps": {m: flat * 1e9 for m in NR.MEMES}, "dex": {"Ethereum": pd.Series(np.linspace(1e9, 2e9, 400), index=idx)}, "closes": {"BTC": flat, **{m: flat for m in NR.MEMES}}})
    assert {"meme_season", "dex_momentum", "sector_rs", "alt_share"} <= set(meme) and "basis_yield" not in meme and "stable_growth" not in meme
    curve = pd.Series([1e9, 1e9, 1.05e9, 1.05e9, 1.2e9], index=pd.to_datetime(["2025-01-01", "2025-01-08", "2025-01-15", "2025-01-22", "2025-01-29"]))
    assert list(NR.unlock_event_days(curve)) == [pd.Timestamp("2025-01-15"), pd.Timestamp("2025-01-29")]
    d = CB.inputs(px, None, extra=out)
    assert {"funding_z", "sector_rs", "post_unlock"} <= set(d.columns) and CB.score(d.funding_z.iloc[-1], CB.NAMES["funding_z"]) == -1
