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
    B._download = lambda url, *a, **k: hl_candles(_post(a, k)) if url.startswith(A.HL_INFO) else real(url, *a, **k)


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


def fake_download(charts):
    cg = TM._fake_download(charts)
    return lambda url, *a, **k: hl_candles(_post(a, k)) if url.startswith(A.HL_INFO) else cg(url, *a, **k)


@pytest.fixture()
def filled(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(C, "FUND_DIR", tmp_path / "snaps" / "btc_fundamentals")
    monkeypatch.setattr(M, "SHARE_LOG", tmp_path / "share.csv")
    monkeypatch.setattr(C, "PACE", 0)
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
    assert t.title == "Altcoin Study" and topics.category("altcoins") == "Money & markets" and not t.private
    assert [k for k, _ in t.tabs] == ["zones", "volume", "hype", "ena", "sol", "near", "unlocks", "basket", "season"] and set(A.ENDPOINTS) == {k for k, _ in t.tabs}
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
    assert f["unlocks"]["tab"] == "#unlocks" and f["unlocks"]["coming"] and all("date" in r for r in f["unlocks"]["coming"])
    assert "unlocks" not in A.ENDPOINTS["sol"]()
    r = {x["key"]: x for x in A.READINGS()}
    assert {"vz_ena", "vz_pepe", "ena_next_unlock"} <= set(r) and r["vz_ena"]["tab"] == "volume" and r["ena_next_unlock"]["lean"] in (-1, 0)
    m = topics.method("altcoins")
    assert [s["title"] for s in m["sections"]] == ["The buy zone rule", "The volume-zone rule", "The unlock study method"]


def test_offline_volume_and_unlocks_degrade(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(B, "_download", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline")))
    from app import cache
    cache._cache.clear()
    d = A._volume_now()
    assert all(c["status"] in ("error", "not on Hyperliquid") for c in d["coins"]) and d["counts"]["coins"] == 0
    u = A._unlocks_now()
    assert u["study_error"] == "ConnectionError" and u["next"] and len(u["events"]) > 80 and "price" not in u
    B.json_safe(u)
    cache._cache.clear()
