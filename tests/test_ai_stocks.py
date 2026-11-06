"""AI Stocks: the setup after the dip (/ai-stocks) on fixtures: Nasdaq closes, FRED/Cboe VIX and EDGAR companyfacts, no network.
smoke_patch() points the module's fetchers at the same fixtures for scripts/smoke.py."""
import asyncio
import json

import numpy as np
import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import ai_stocks as M
from app.topics import compute_chips as CC
from tests import test_compute_chips as TC

DAYS = pd.bdate_range("2019-01-02", "2026-11-04")
# market path: up-trend with drawdowns in 2020 (-30%), 2022 (-45%), mid-2024 (-18%), spring 2025 (-28%) and a dip now (Oct-Nov 2026)
SHOCKS = [("2020-02-20", "2020-03-20", -0.35, 60), ("2022-01-01", "2022-10-14", -0.50, 250), ("2024-07-10", "2024-08-07", -0.20, 50),
          ("2025-02-19", "2025-04-08", -0.32, 70), ("2026-10-01", "2026-11-04", -0.17, 0)]


def market() -> pd.Series:
    t = np.arange(len(DAYS))
    logp = 0.0009 * t + 0.01 * np.sin(t / 9)
    s = pd.Series(logp, index=DAYS)
    for a, b, depth, rec in SHOCKS:
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        fall = (DAYS >= a) & (DAYS <= b)
        k = np.cumsum(fall) / max(1, fall.sum())
        hit = np.log(1 + depth)
        drop = np.where(DAYS < a, 0.0, np.where(DAYS <= b, hit * k, hit))
        if rec:
            after = (DAYS > b)
            j = np.cumsum(after)
            drop = np.where(after, hit * np.clip(1 - j / rec, 0, 1), drop)
        s = s + drop
    return s


MKT = market()


def closes(sym: str) -> pd.Series:
    rng = np.random.default_rng(sum(map(ord, sym)))
    beta = 0.7 + (sum(map(ord, sym)) % 9) / 10
    noise = np.cumsum(rng.normal(0, 0.008, len(DAYS)))
    s = pd.Series(np.exp(beta * MKT.values + noise) * (20 + len(sym) * 15), index=DAYS)
    return s[s.index >= "2023-09-14"] if sym == "ARM" else s


def nasdaq_json(sym: str) -> dict:
    s = closes(sym) if sym not in ("QQQ", "SPY", "SMH") else pd.Series(np.exp({"QQQ": 0.8, "SPY": 0.55, "SMH": 1.1}[sym] * MKT.values) * 300, index=DAYS)
    return {"data": {"tradesTable": {"rows": [{"date": d.strftime("%m/%d/%Y"), "close": f"${v:,.2f}"} for d, v in s.items()][::-1]}}}


def vix_csv(cboe: bool = False) -> str:
    v = 15 + 25 * np.clip(-(MKT - MKT.cummax()) * 2.5, 0, 2)
    if cboe:
        return "DATE,OPEN,HIGH,LOW,CLOSE\n" + "\n".join(f"{d.strftime('%m/%d/%Y')},{x:.2f},{x + 1:.2f},{x - 1:.2f},{x:.2f}" for d, x in v.items())
    rows = [f"{d.date()},{x:.2f}" for d, x in v.items()]
    rows[5] = rows[5].split(",")[0] + ",."                                # FRED marks holidays with '.'
    return "observation_date,VIXCLS\n" + "\n".join(rows)


def revenue_facts(cik: int) -> str:
    return TC.companyfacts(1 + cik % 7, "Revenues", year_to_date=False)


def fake_fetch(url, ttl=0, **k):
    if "fredgraph" in url:
        return vix_csv()
    if "cboe" in url:
        return vix_csv(cboe=True)
    if "companyfacts" in url:
        text = revenue_facts(int(url.rsplit("CIK", 1)[1].split(".")[0]))
        return k["reduce"](text) if k.get("reduce") else text
    raise ConnectionError("fixture: unknown url " + url)


def fake_fetch_json(url, ttl=0, **k):
    if "api.nasdaq.com" in url:
        return nasdaq_json(url.split("/quote/")[1].split("/")[0])
    raise ConnectionError("fixture: unknown url " + url)


def smoke_patch():
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above (capex through compute_chips' fixtures)."""
    M.fetch = fake_fetch
    M.fetch_json = fake_fetch_json
    TC.smoke_patch()


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(M, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(CC, "_get", TC.fake_get)
    monkeypatch.setattr(CC, "fetch", TC.fake_fetch)
    monkeypatch.setattr(CC, "fetch_json", TC.fake_fetch_json)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


# ------------------------------------------------------------------ pure pieces
def test_registered():
    t = topics.REGISTRY["ai-stocks"]
    assert t.module == "ai_stocks" and {k for k, _ in t.tabs} == {"setup", "drawdown", "trend", "dips", "fear", "fundamentals"} <= set(M.ENDPOINTS)
    assert topics.category("ai-stocks") == "Money & markets"
    m = topics.meta("ai-stocks")
    assert m["sources"] and "Not investment advice" in m["notes"] and "Not investment advice" in m["footer"] and m["method"]


def test_basket_index_is_equal_weight_and_joins_late_members():
    d = pd.bdate_range("2019-12-30", periods=6)
    a = pd.Series([10, 10, 11, 11, 11, 11.0], index=d)       # +10% on day 3
    b = pd.Series([50, 50, 50, 45, 45, 45.0], index=d)       # -10% on day 4
    c = pd.Series([7, 14.0], index=d[4:])                   # lists on day 5, doubles on day 6
    s = M.basket_index({"A": a, "B": b, "C": c})
    assert s.loc["2020-01-01"] == pytest.approx(100) and s.loc["2019-12-31"] == pytest.approx(100 / 1.05)   # A's +10% that day, averaged with B's 0
    assert s.iloc[-2] / s.iloc[-3] == pytest.approx(1.0)     # C's first close is not a return
    assert s.iloc[-1] / s.iloc[-2] == pytest.approx(1 + 1.0 / 3)


def test_full_months_joins_picks_from_their_first_full_month():
    s = pd.Series(np.arange(1, 41, dtype=float), index=pd.bdate_range("2025-02-24", periods=40))
    j = M.full_months(s)
    assert j.index[0] == pd.Timestamp("2025-02-28") and j.index[1] == pd.Timestamp("2025-03-03")   # base: the last close before March
    old = pd.Series(np.arange(1, 41, dtype=float), index=pd.bdate_range("2019-01-02", periods=40))
    assert M.full_months(old).equals(old)
    on_first = pd.Series(np.arange(1, 41, dtype=float), index=pd.bdate_range("2025-04-01", periods=40))
    assert M.full_months(on_first).index[0] == pd.Timestamp("2025-04-01")


def test_drawdown_and_episodes():
    d = pd.bdate_range("2020-01-01", periods=12)
    s = pd.Series([100, 110, 99, 88, 90, 112, 105, 100, 95, 92, 93, 94.0], index=d)
    dd = M.drawdown(s)
    assert dd.iloc[1] == 0 and dd.iloc[3] == pytest.approx(88 / 110 - 1)
    eps = M.episodes(s, -0.10)
    assert len(eps) == 2
    first, cur = eps
    assert first["depth"] == pytest.approx(-0.2, abs=1e-4) and first["recovered"] == str(d[5].date()) and first["cross15"] == str(d[3].date())
    assert first["days_to_bottom"] == (d[3] - d[1]).days and first["days_to_recover"] == (d[5] - d[3]).days and not first["ongoing"]
    assert cur["ongoing"] and cur["recovered"] is None and cur["days_to_recover"] is None and cur["cross15"] == str(d[8].date())


def test_breadth_and_rsi():
    d = pd.bdate_range("2019-01-01", periods=300)
    up = pd.Series(np.linspace(10, 30, 300), index=d)
    down = pd.Series(np.linspace(30, 10, 300), index=d)
    b = M.breadth({"NVDA": up, "AMD": down}, 50)
    assert b.iloc[-1] == pytest.approx(0.5) and b.index[0] == d[49]
    assert M.rsi(up).iloc[-1] > 90 and M.rsi(down).iloc[-1] < 10


def test_parse_vix_both_layouts():
    f, c = M.parse_vix(vix_csv()), M.parse_vix(vix_csv(cboe=True))
    assert len(f) == len(DAYS) - 1 and len(c) == len(DAYS) and f.index.is_monotonic_increasing
    assert f.iloc[-1] == pytest.approx(c.iloc[-1])
    with pytest.raises(ValueError):
        M.parse_vix("a,b\n1,2")


# ------------------------------------------------------------------ endpoints on fixtures
def test_setup(mocked):
    p = M.ENDPOINTS["setup"]()
    assert len(p["cards"]) == 13 and {c["sym"] for c in p["cards"]} == set(M.BASKET)
    c = p["cards"][0]
    assert c["dd52"] <= 0 and c["vs50"] is not None and 0 <= c["rsi"] <= 100
    assert set(p["lines"]) == {"AI basket", "Owner's picks", "QQQ", "SPY"} and p["lines"]["AI basket"][0][1] == 100
    assert p["now"]["dd"] < -0.1 and p["vix_source"] == "FRED" and "below its high" in p["where"]
    assert "buy" not in p["where"].lower() and "sell" not in p["where"].lower()
    assert [c["sym"] for c in p["pick_cards"]] == list(M.PICKS) and "Owner's picks" in p["lines"]
    assert p["picks_now"]["since"]["SNDK"] == "2025-03-03" and p["picks_now"]["since"]["NBIS"] == "2024-11-01"
    assert p["picks_dd"][-1][1] <= 0 and p["picks_now"]["n"] == 10
    B.json_safe(p)


def test_vix_falls_back_to_cboe_and_marks_fred_handled(mocked, monkeypatch):
    def no_fred(url, ttl=0, **k):
        if "fredgraph" in url:
            B.HEALTH[url] = {"module": "ai_stocks", "ok": None, "fail": time_now(), "error": "Timeout"}
            raise TimeoutError("fred")
        return fake_fetch(url, ttl, **k)
    monkeypatch.setattr(M, "fetch", no_fred)
    s, src = M.vix()
    assert src == "Cboe" and len(s) > 100 and B.HEALTH[M.FRED_VIX].get("handled_how")


def time_now():
    import time
    return time.time()


def test_drawdown_tab(mocked):
    p = M.ENDPOINTS["drawdown"]()
    assert len(p["stocks"]) == 13 and p["basket"][-1][1] < 0
    eps = p["episodes"]
    assert all(e["depth"] <= -0.10 for e in eps) and sum(e["ongoing"] for e in eps) == 1
    assert p["current"]["episode"]["ongoing"] and p["current"]["peak"] >= "2026-09-01"
    closed = [e for e in eps if not e["ongoing"]]
    assert len(closed) >= 3 and all(e["days_to_recover"] is not None for e in closed)
    assert set(p["pick_stocks"]) == set(M.PICKS) and p["picks_basket"][-1][1] <= 0 and p["picks_current"]["dd"] <= 0
    assert p["pick_since"]["NBIS"] == "2024-10-21" and p["pick_since"]["RKLB"] == "2021-08-25"      # own history: from the listing
    assert p["pick_since"]["NVDA"] == "2020-01-01"
    B.json_safe(p)


def test_trend_tab(mocked):
    p = M.ENDPOINTS["trend"]()
    assert all(0 <= v <= 1 for _, v in p["breadth50"]) and p["now"]["state"] in ("golden", "death")
    assert p["crosses"] and {x["kind"] for x in p["crosses"]} <= {"golden", "death"}
    assert p["crosses"] == sorted(p["crosses"], key=lambda x: x["date"], reverse=True)
    B.json_safe(p)


def test_dips_tab(mocked):
    p = M.ENDPOINTS["dips"]()
    assert p["n"] >= 3 and p["threshold"] == -0.15
    for r in p["rows"]:
        assert r["depth"] <= -0.15 and r["cross15"] <= r["trough"] and r["further"] <= 0
    cur = [r for r in p["rows"] if r["ongoing"]]
    assert cur and cur[0]["cross"]["6m"] is None                              # the future is not known yet
    s = p["cross"]["3m"]
    assert s["n"] == p["n"] and s["min"] <= s["median"] <= s["max"]
    B.json_safe(p)


def test_fear_tab(mocked):
    p = M.ENDPOINTS["fear"]()
    assert p["vix"] and p["ai_qqq"][0][1] == 100 and p["smh_spy"][0][1] == 100
    r = p["relative"]["AI basket vs QQQ"]
    assert set(r) == {"3m", "12m"} and r["3m"]["gap"] == pytest.approx(100 * (r["3m"]["a"] - r["3m"]["b"]), abs=0.06)
    assert p["vix_now"]["max_1m"] >= p["vix_now"]["v"]
    B.json_safe(p)


def test_fundamentals_tab(mocked):
    p = M.ENDPOINTS["fundamentals"]()
    assert set(p["revenue_yoy"]) == set(M.REV_CIKS) and p["basket_yoy"] and p["capex_ttm"] and p["capex_yoy"]
    assert set(p["left_out"]) == {"TSM", "ASML", "ARM"} and not p["errors"]
    B.json_safe(p)


def test_revenue_uses_its_own_cache_key_not_compute_chips_capex_copy(mocked):
    CC._capex()                                                             # caches Microsoft's companyfacts cut down to capex tags
    s = M.revenue(M.REV_CIKS["MSFT"])
    assert len(s) > 20 and s.iloc[-1] > 0


def test_readings_and_signals(mocked):
    assert M.SIGNALS() == [] and M.READINGS() == []                         # nothing cached: nothing downloaded
    for k in ("setup", "drawdown", "trend", "dips", "fear", "fundamentals"):
        M.ENDPOINTS[k]()
    r = M.READINGS()
    assert {x["tab"] for x in r} == {t for t, _ in topics.REGISTRY["ai-stocks"].tabs} and all(x["lean"] in (-1, 0, 1) for x in r)
    sig = {x["key"]: x for x in M.SIGNALS()}
    wl = json.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())["ai-stocks"]
    assert set(sig) == {w["key"] for w in wl} and all(w.get("approved") and not w.get("proposed") for w in wl)
    assert all(isinstance(x["crossed"], bool) and x["lean"] in (-1, 0, 1) for x in sig.values())
    dd = sig["basket_drawdown"]["value"]
    assert not sig["basket_drawdown"]["crossed"] or dd < -20 or dd >= -5
    assert sig["rsi_basket"]["crossed"] == (sig["rsi_basket"]["value"] < 30 or sig["rsi_basket"]["value"] > 70)
    assert sig["ai_vs_qqq"]["crossed"] == (abs(sig["ai_vs_qqq"]["value"]) >= 10)


def test_signal_tests_at_the_edges(monkeypatch):
    day = 86400
    pts = lambda vals: [[1_700_000_000 + i * day, v] for i, v in enumerate(vals)]
    pay = {"setup": {"dd": pts([-0.12] * 30 + [-0.04]), "breadth50": pts([0.3] * 30 + [0.65]), "vix": pts([28] * 20 + [19])},
           "trend": {"now": {"rsi": 72}}, "fear": {"relative": {"AI basket vs QQQ": {"3m": {"a": 0.02, "b": 0.13, "gap": -11.0}}}}}
    monkeypatch.setattr(M, "_cached_payload", lambda n: pay.get(n, {}))
    sig = {x["key"]: x for x in M.SIGNALS()}
    assert all(sig[k]["crossed"] for k in ("basket_drawdown", "breadth_50d", "rsi_basket", "vix", "ai_vs_qqq"))
    pay["setup"] = {"dd": pts([-0.03] * 31), "breadth50": pts([0.7] * 31), "vix": pts([21] * 21)}       # at a high all along: nothing to repair
    pay["trend"] = {"now": {"rsi": 55}}
    sig = {x["key"]: x for x in M.SIGNALS()}
    assert not any(sig[k]["crossed"] for k in ("basket_drawdown", "breadth_50d", "rsi_basket", "vix"))


def test_every_endpoint_through_the_server(mocked):
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            for name in ("setup", "drawdown", "trend", "dips", "fear", "fundamentals", "meta"):
                r = await c.get(f"/api/ai-stocks/{name}")
                assert r.status == 200, name
            r = await c.get("/ai-stocks")
            assert r.status == 200
    asyncio.run(go())


@pytest.mark.network
def test_live_sources():
    assert len(M.nasdaq("NVDA")) > 1000 and len(M.nasdaq("SMH", "etf")) > 1000
    for s in M.PICKS:
        assert len(M.nasdaq(s)) > 100, s
    assert len(M.vix()[0]) > 1000
