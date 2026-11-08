"""Options Setup (/options) on fixtures: a synthetic Cboe-layout chain per symbol (Black-Scholes prices and Greeks), Cboe index histories and
the AI Stocks closes, no network. smoke_patch() points the module at the same fixtures for scripts/smoke.py and seeds a few days of history."""
import asyncio
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import ai_stocks as AI
from app.topics import options as M
from tests import test_ai_stocks as TA

TRADE = date(2026, 11, 6)                     # the chain's session (a Friday); "today" in the tests is the Sunday after
TODAY = date(2026, 11, 8)
SPOTS = {"SPY": 735.29, "QQQ": 650.0, "IWM": 240.0, "SMH": 330.0, "NVDA": 188.7}
IVS = {"SPY": 0.20, "QQQ": 0.24, "IWM": 0.26, "SMH": 0.38, "NVDA": 0.60}


def expiries(trade: date = TRADE) -> list[date]:
    """Three weeklies, then the monthlies (third Fridays) out to about a year, plus one LEAPS beyond MAX_DTE (dropped by the reducer)."""
    out = [trade + timedelta(days=d) for d in (3, 5, 7)]
    y, m = trade.year, trade.month
    for i in range(0, 13):
        mm = (m - 1 + i) % 12 + 1
        yy = y + (m - 1 + i) // 12
        if M.third_friday(yy, mm) > trade:
            out.append(M.third_friday(yy, mm))
    out.append(M.third_friday(trade.year + 2, 1))
    return sorted(set(out))


def chain_json(sym: str, spot: float | None = None, iv: float | None = None, trade: date = TRADE, skew: float = 0.10, unusual: bool = True) -> dict:
    """A Cboe delayed-quotes file: quote + options with OCC symbols (and a few adjusted "B1" series), IV fractions, Greeks, OI and volume.
    Puts carry a smile (IV rises below spot), so the 25-delta put IV is above the call's by about `skew`."""
    spot = spot or SPOTS.get(sym, 100.0)
    iv = iv or IVS.get(sym, 0.35)
    rng = np.random.default_rng(sum(map(ord, sym)))
    step = 1.0 if spot < 50 else 2.5 if spot < 150 else 5.0
    opts = []
    for exp in expiries(trade):
        dte = (exp - trade).days
        t = dte / 365
        term = iv * (1 + 0.15 * math.exp(-dte / 60))                   # a little higher near term
        for k in np.arange(math.floor(spot * 0.45 / step) * step, spot * 1.7, step):
            k = float(round(k, 2))
            m = math.log(k / spot)
            z = m / (term * math.sqrt(max(t, 1 / 365)))                      # standardised moneyness, so the smile is the same in vol points at every expiry
            for cp in ("C", "P"):
                sig = term + (-skew * 1.1 * z if m < 0 else -skew * 0.4 * z)   # smile: puts below spot richer, calls above a little cheaper
                sig = max(0.05, sig)
                g = M.bs(cp, spot, k, t, sig, M.RATE)
                price = g["price"]
                spread = max(0.01, price * 0.03)
                dist = abs(k - spot) / spot
                oi = float(int(50000 * math.exp(-8 * dist) * (1.3 if cp == "P" else 1.0) * (1 + (k % (step * 4) == 0)))) if dte > 0 else 0.0
                vol = float(int(oi * 0.15 * rng.uniform(0.5, 1.5)))
                code = f"{sym}{exp.strftime('%y%m%d')}{cp}{int(round(k * 1000)):08d}"
                opts.append({"option": code, "bid": round(max(0, price - spread / 2), 2), "ask": round(price + spread / 2, 2), "bid_size": 10.0, "ask_size": 10.0, "iv": round(sig, 4),
                             "open_interest": oi, "volume": vol, "delta": round(g["delta"], 4), "gamma": round(g["gamma"], 5), "vega": round(g["vega"], 4), "theta": round(g["theta"], 4),
                             "rho": 0.0, "theo": round(price, 4), "change": 0.0, "open": 0.0, "high": 0.0, "low": 0.0, "tick": "no_change", "last_trade_price": round(price, 2),
                             "last_trade_time": f"{trade}T15:59:00", "percent_change": 0.0, "prev_day_close": round(price, 2)})
    if unusual:                                                          # one line with volume far above its open interest
        e = expiries(trade)[4]
        k = float(round(spot * 1.1 / step) * step)
        opts.append({"option": f"{sym}{e.strftime('%y%m%d')}C{int(round(k * 1000)):08d}", "bid": 1.0, "ask": 1.1, "iv": iv, "open_interest": 120.0, "volume": 5000.0,
                     "delta": 0.2, "gamma": 0.01, "vega": 0.1, "theta": -0.05, "last_trade_price": 1.05, "last_trade_time": f"{trade}T15:00:00"})
    opts.insert(0, {"option": f"B1{sym[1:]}{expiries(trade)[0].strftime('%y%m%d')}C{int(round(spot * 1000)):08d}", "bid": 0.85, "ask": 0.0, "iv": 0.0, "open_interest": 0.0, "volume": 0.0,
                    "delta": 0.0089, "gamma": -0.0003, "vega": -0.0024, "theta": 0.0216, "last_trade_price": 0.0, "last_trade_time": None})   # an adjusted series: ignored
    return {"timestamp": f"{trade + timedelta(days=2)} 01:30:19", "symbol": sym,
            "data": {"symbol": sym, "security_type": "stock", "current_price": spot, "price_change": 2.0, "price_change_percent": 1.07, "bid": spot - 0.02, "ask": spot + 0.02,
                     "open": spot, "high": spot * 1.02, "low": spot * 0.98, "close": spot, "prev_day_close": spot - 2.0, "volume": 1000000, "iv30": round(iv * 100, 3),
                     "iv30_change": 0.0, "iv30_change_percent": 0.0, "seqno": 0, "last_trade_time": f"{trade}T16:00:00", "tick": "up", "options": opts}}


def hist_csv(name: str) -> str:
    days = pd.bdate_range("2023-01-02", str(TRADE))
    t = np.arange(len(days))
    if name == "VIX":
        v = 18 + 6 * np.sin(t / 40) + 4 * (t > len(t) - 15)
        return "DATE,OPEN,HIGH,LOW,CLOSE\n" + "\n".join(f"{d.strftime('%m/%d/%Y')},{x:.2f},{x + 1:.2f},{x - 1:.2f},{x:.2f}" for d, x in zip(days, v))
    if name == "VIX3M":
        v = 20 + 5 * np.sin(t / 40) + 1.5 * (t > len(t) - 15)
        return "DATE,OPEN,HIGH,LOW,CLOSE\n" + "\n".join(f"{d.strftime('%m/%d/%Y')},{x:.2f},{x + 1:.2f},{x - 1:.2f},{x:.2f}" for d, x in zip(days, v))
    if name == "VVIX":
        v = 95 + 15 * np.sin(t / 30)
        return "DATE,VVIX\n" + "\n".join(f"{d.strftime('%m/%d/%Y')},{x:.2f}" for d, x in zip(days, v))
    v = 135 + 12 * np.sin(t / 50)
    return "DATE,SKEW\n" + "\n".join(f"{d.strftime('%m/%d/%Y')},{x:.2f}" for d, x in zip(days, v))


def fake_fetch(url, ttl=0, **k):
    if "delayed_quotes/options/" in url:
        sym = url.rsplit("/", 1)[1].split(".")[0].lstrip("_")
        text = json.dumps(chain_json(sym))
        return k["reduce"](text) if k.get("reduce") else text
    if "_History.csv" in url:
        return hist_csv(url.rsplit("/", 1)[1].split("_")[0])
    raise ConnectionError("fixture: unknown url " + url)


def fake_closes(sym: str, group: str = "") -> pd.Series:
    s = TA.closes(sym) if sym not in ("QQQ", "SPY", "SMH", "IWM") else pd.Series(np.exp({"QQQ": 0.8, "SPY": 0.55, "SMH": 1.1, "IWM": 0.5}[sym] * TA.MKT.values) * 300, index=TA.DAYS)
    return s[s.index <= str(TRADE)]


SMALL_UNIVERSE = [{"sym": "SPY", "name": "S&P 500 ETF", "group": "index", "cboe": "SPY", "both": False}, {"sym": "QQQ", "name": "Nasdaq-100 ETF", "group": "index", "cboe": "QQQ", "both": False},
                  {"sym": "NVDA", "name": "Nvidia", "group": "core", "cboe": "NVDA", "both": True}, {"sym": "AMD", "name": "AMD", "group": "core", "cboe": "AMD", "both": True},
                  {"sym": "MSFT", "name": "Microsoft", "group": "core", "cboe": "MSFT", "both": False}, {"sym": "RKLB", "name": "Rocket Lab", "group": "picks", "cboe": "RKLB", "both": False}]


def seed_history(days: int = 15, syms=None) -> None:
    """A few trading days of daily entries before TRADE, so the history charts and ranks have something to show."""
    syms = syms or [u["sym"] for u in SMALL_UNIVERSE]
    for sym in syms:
        spot, iv = SPOTS.get(sym, 100.0), IVS.get(sym, 0.35)
        for i, d in enumerate(pd.bdate_range(end=str(TRADE - timedelta(days=1)), periods=days)):
            f = 1 + 0.25 * math.sin(i / 3)
            exps = {str(e): {"dte": (e - d.date()).days, "atm_iv": round(iv * f, 4), "put25": round(iv * f + 0.08, 4), "call25": round(iv * f - 0.02, 4), "skew": round(0.10 * f, 4),
                             "pc_oi": 1.1, "pc_vol": 0.9, "oi": 100000.0, "em_straddle": round(0.8 * iv * f * math.sqrt(max((e - d.date()).days, 1) / 365), 4),
                             "em_iv": round(iv * f * math.sqrt(max((e - d.date()).days, 1) / 365), 4), "straddle": 10.0, "max_pain": spot}
                    for e in expiries(d.date()) if (e - d.date()).days > 0}
            M.save_daily(sym, str(d.date()), {"spot": round(spot * (1 + 0.01 * math.sin(i)), 2), "iv30": round(iv * 100, 2), "front": None, "atm_iv": round(iv * f, 4), "skew": round(0.10 * f, 4),
                                               "rr": round(-0.10 * f, 4), "pc_oi": 1.1, "pc_vol": 0.9, "oi": 100000.0, "rv10": round(iv * 0.8, 4), "rv30": round(iv * 0.85, 4), "gex": 1e8, "exp": exps})


def smoke_patch():
    """Used by scripts/smoke.py: chains and index histories from the fixtures, closes from the AI Stocks fixtures, history on a temp dir."""
    import tempfile
    M.fetch = fake_fetch
    M.closes = fake_closes
    M.DIR = Path(tempfile.mkdtemp()) / "options"
    seed_history(15, [u["sym"] for u in M.universe()])


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "DIR", tmp_path / "options")
    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(M, "closes", fake_closes)
    monkeypatch.setattr(M, "universe", lambda: SMALL_UNIVERSE)
    monkeypatch.setattr(M.date, "today", classmethod(lambda cls: TODAY)) if False else None
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()


class _Today(date):
    @classmethod
    def today(cls):
        return TODAY


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(M, "date", _Today)


# ------------------------------------------------------------------ registry, files
def test_topic_is_registered():
    t = topics.REGISTRY["options"]
    assert [k for k, _ in t.tabs] == ["setup", "chains", "vol", "skew", "moves", "lab"] and set(t.slow) <= set(M.ENDPOINTS)
    assert topics.category("options") == "Money & markets"
    assert "chain-NVDA" in M.ENDPOINTS and "chain-SPY" in M.ENDPOINTS
    assert "Not investment advice" in M.NOTES and "Not investment advice" in M.FOOTER
    assert "Method" in (B.MANUAL_DIR / "options" / "README.md").read_text()
    assert topics.method("options")["sections"]


def test_universe_and_events():
    u = M.universe()
    syms = [x["sym"] for x in u]
    assert syms[:4] == ["SPY", "QQQ", "IWM", "SMH"] and set(AI.STOCKS) <= set(syms) and len(syms) == len(set(syms))
    assert all(x["group"] in ("index", "core", "picks", "owner") for x in u)
    evs = M.events(date(2026, 11, 8))
    kinds = {e["kind"] for e in evs}
    assert {"earnings", "fomc", "opex"} <= kinds and all(e["source"] for e in evs) and evs == sorted(evs, key=lambda e: e["date"])
    assert M.next_earnings("NVDA", evs, date(2026, 11, 8))["date"] == "2026-11-19"
    for e in evs:
        if e["kind"] == "opex":
            d = pd.Timestamp(e["date"]).date()
            assert d == M.third_friday(d.year, d.month), e
    assert M.is_monthly(date(2026, 11, 20)) and not M.is_monthly(date(2026, 11, 19), {date(2026, 11, 19), date(2026, 11, 20)}) and M.is_monthly(date(2026, 11, 19), {date(2026, 11, 19)})


def test_market_hours_and_ttl():
    ny = M.ET
    assert M.market_open(datetime(2026, 11, 6, 10, 0, tzinfo=ny)) and M.ttl_now(datetime(2026, 11, 6, 10, 0, tzinfo=ny)) == 900
    assert not M.market_open(datetime(2026, 11, 6, 16, 30, tzinfo=ny)) and not M.market_open(datetime(2026, 11, 7, 11, 0, tzinfo=ny))
    assert M.ttl_now(datetime(2026, 11, 8, 12, 0, tzinfo=ny)) == 3600


# ------------------------------------------------------------------ the parser and the reducer
def test_reduce_and_parse_the_cboe_layout():
    raw = json.dumps(chain_json("NVDA"))
    red = M.reduce_chain("NVDA")(raw)
    assert len(red) < len(raw) * 0.8
    j = json.loads(red)
    assert j["reduced"] and j["data"]["current_price"] == SPOTS["NVDA"] and all(not o["option"].startswith("B1") for o in j["data"]["options"])
    assert max(M.OCC.match(o["option"]).group("ymd") for o in j["data"]["options"]) < "280101"          # the LEAPS past 400 days is gone
    for text in (raw, red):
        ch = M.parse_chain(text, "NVDA")
        assert ch["spot"] == SPOTS["NVDA"] and ch["trade_date"] == "2026-11-06" and ch["iv30"] == 60.0
        df = ch["options"]
        assert set(df["cp"]) == {"C", "P"} and (df["iv"] > 0).all() and (df["dte"] >= 0).all()
        assert df["strike"].min() >= 0.6 * SPOTS["NVDA"] or text is raw
    with pytest.raises(ValueError):
        M.parse_chain(json.dumps({"data": {"current_price": 0, "options": []}}), "X")
    with pytest.raises(ValueError):
        M.parse_chain(json.dumps({"data": {"current_price": 100, "options": [{"option": "X261120C00100000", "iv": 0.0}]}}), "X")


def test_parse_history_layouts():
    v = M.parse_history(hist_csv("VIX"), "VIX")
    s = M.parse_history(hist_csv("SKEW"), "SKEW")
    assert v.index[-1] == pd.Timestamp("2026-11-06") and 15 < v.iloc[-1] < 40 and 120 < s.iloc[-1] < 160
    with pytest.raises(ValueError):
        M.parse_history("a,b\n1,2\n", "VIX")


# ------------------------------------------------------------------ every calculation on the fixture chain
def test_black_scholes_and_probabilities():
    c, p = M.bs("C", 100, 100, 0.25, 0.3), M.bs("P", 100, 100, 0.25, 0.3)
    assert abs(c["price"] - p["price"] - (100 - 100 * math.exp(-M.RATE * 0.25))) < 1e-9        # put-call parity
    assert 0.5 < c["delta"] < 0.6 and -0.5 < p["delta"] < -0.4 and c["gamma"] == p["gamma"] > 0 and c["theta"] < 0
    assert abs(M.prob_above(100, 100, 1, 0.2) - M.ncdf((M.RATE - 0.02) / 0.2)) < 1e-9
    assert M.prob_above(100, 90, 0, 0.2) == 1.0 and M.bs("C", 100, 90, 0, 0.2)["price"] == 10


def test_expiry_table_skew_moves_max_pain_gex_pc_unusual():
    ch = M.parse_chain(json.dumps(chain_json("NVDA")), "NVDA")
    spot, df = ch["spot"], ch["options"]
    rows = M.expiry_table(ch)
    assert [r["exp"] for r in rows] == sorted(r["exp"] for r in rows) and all(r["dte"] >= 0 for r in rows)
    front = M.front_expiry(rows)
    assert front["exp"] == "2026-11-20" and front["monthly"] and front["dte"] == 14
    assert 0.5 < front["atm_iv"] < 0.8 and front["put25"] > front["call25"] and front["skew"] > 0.05 and front["rr"] == -front["skew"]
    # the straddle and the IV move agree to the usual factor (straddle ~ 0.8 x spot x iv x sqrt(T))
    assert 0.7 < front["em_straddle"] / front["em_iv"] < 0.9
    g = df[df["exp"].astype(str) == front["exp"]]
    assert abs(M.straddle(g, spot) - (M._mid_at(g, "C", M.atm_strike(g, spot)) + M._mid_at(g, "P", M.atm_strike(g, spot)))) < 1e-9
    assert abs(M.delta_iv(g, "C", 0.5) - M.atm_iv(g, spot)) < 0.08                    # the 50-delta call sits near the money
    mp = M.max_pain(g)
    assert abs(mp - spot) / spot < 0.08                                                 # OI piles up near spot in the fixture
    gex, total = M.gex_by_strike(g, spot)
    assert gex == sorted(gex) and total is not None and sum(v for _, v in gex) == pytest.approx(total, rel=1e-6)
    calls = g[g["cp"] == "C"]
    assert M.gex_by_strike(calls, spot)[1] > 0 > M.gex_by_strike(g[g["cp"] == "P"], spot)[1]        # calls positive, puts negative
    pc = M.pc_ratios(df)
    assert pc["pc_oi"] > 1 and pc["oi"] == pc["call_oi"] + pc["put_oi"] and pc["pc_vol"] > 0
    u = M.unusual(df, "NVDA", spot)
    assert u and u[0]["vol"] == 5000 and u[0]["oi"] == 120 and u[0]["ratio"] > 40 and u[0]["cp"] == "C" and u[0]["otm"] > 0.05
    assert not M.unusual(df, "NVDA", spot, volume=10000)
    assert M.unusual(M.parse_chain(json.dumps(chain_json("NVDA", unusual=False)), "NVDA")["options"], "NVDA", spot) == []


def test_realised_vol_rank_and_percentile():
    px = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.02, 300))), index=pd.bdate_range("2025-09-01", periods=300))
    rv = M.realised_vol(px, 30)
    assert len(rv) == 300 - 30 and 0.2 < rv.iloc[-1] < 0.45                            # 2% daily ~ 32% annualised
    r = M.rank_pct(pd.Series([0.3, 0.4, 0.5, 0.6]), 0.55)
    assert r == {"rank": 83.3, "pct": 75.0, "days": 4}
    assert M.rank_pct(pd.Series([0.3]), 0.3)["rank"] is None and M.rank_pct(pd.Series([0.3, 0.3]), 0.3)["rank"] == 50.0
    h = M._rank_hist([[1, 0.2], [2, 0.4], [3, 0.3], [4, 0.5]])
    assert h == [[2, 100.0], [3, 50.0], [4, 100.0]]


# ------------------------------------------------------------------ the store and the model
def test_daily_store_upserts(mocked):
    M.save_daily("X", "2026-11-05", {"atm_iv": 0.3})
    M.save_daily("X", "2026-11-06", {"atm_iv": 0.4})
    M.save_daily("X", "2026-11-06", {"atm_iv": 0.45})
    d = M.load_daily("X")
    assert list(d) == ["2026-11-05", "2026-11-06"] and d["2026-11-06"]["atm_iv"] == 0.45
    assert M.load_daily("nothing") == {}


def test_symbol_model_saves_today_and_ranks_on_history(mocked, frozen):
    evs = M.events(TODAY)
    s = M.symbol_model(SMALL_UNIVERSE[2], evs, TODAY)                                   # NVDA, no history yet
    assert s["sym"] == "NVDA" and s["spot"] == SPOTS["NVDA"] and s["trade_date"] == "2026-11-06" and s["history_days"] == 1
    assert s["rank"]["rank"] is None and s["rank"]["days"] == 1 and s["front"]["exp"] == "2026-11-20"
    assert s["rv30"] and s["rv10"] and s["rv"]["rv30"] and s["earnings"]["date"] == "2026-11-19" and s["earnings"]["verify"]
    assert "2026-11-06" in M.load_daily("NVDA") and M.load_daily("NVDA")["2026-11-06"]["exp"]["2026-11-20"]["atm_iv"] == s["front"]["atm_iv"]
    seed_history(15, ["NVDA"])
    s2 = M.symbol_model(SMALL_UNIVERSE[2], evs, TODAY)
    assert s2["history_days"] == 16 and s2["rank"]["rank"] is not None and 0 <= s2["rank"]["rank"] <= 100 and len(s2["hist"]["atm_iv"]) == 16
    assert all(e["date"] >= str(TODAY) for e in s2["events"]) and any(e["sym"] is None for e in s2["events"])


def test_setup_payload_head_table_fallbacks_and_where_line(mocked, frozen):
    seed_history(15, ["NVDA", "AMD", "MSFT"])                                            # the stocks have history, the ETFs do not
    d = M.ENDPOINTS["setup"]()
    B.json_safe(d)
    H, T, Bk = d["head"], d["table"], d["basket"]
    assert H["vix"] and H["vix3m"] and H["vix_term"] == pytest.approx(H["vix3m"] - H["vix"], abs=0.02) and H["skew_index"] and H["vvix"]
    assert H["ai_iv_rank"] is not None and H["vrp_share"] is not None and H["ai_skew"] > 0 and H["spy_pc_oi"] > 0
    assert "Not investment advice" in H["where"] and "VIX is" in H["where"]
    assert [r["sym"] for r in T] == [u["sym"] for u in SMALL_UNIVERSE]
    spy = next(r for r in T if r["sym"] == "SPY")
    assert spy["rank_basis"] == "VIX fallback" and spy["rank"] is not None and spy["rank_days"] == 1          # an index with thin history reads the VIX's rank
    nv = next(r for r in T if r["sym"] == "NVDA")
    assert nv["rank_basis"] == "thin history" and nv["rank_days"] == 16 and nv["earnings"] == "2026-11-19" and nv["em_exp"] == "2026-11-20"
    assert nv["atm_iv"] > spy["atm_iv"] and nv["skew"] is not None and nv["pc_oi"] is not None and nv["vrp"] is not None
    assert Bk["history_days"] == 16 and Bk["min_history"] == 60 and "NVDA" in Bk["thin"] and Bk["vrp_n"] == 6
    assert len(d["vix"]) > 200 and len(d["vix_term"]) > 200 and d["ai_rank_hist"] and d["vrp_hist"] and len(d["ai_iv_hist"]) == 16
    assert d["as_of"] == "2026-11-06" and d["errors"] == {} and d["stale"] == {}


def test_chains_vol_skew_moves_lab_payloads(mocked, frozen):
    seed_history(15)
    c = M.ENDPOINTS["chains"]()
    assert c["default"] == "NVDA" and [s["sym"] for s in c["symbols"]] == [u["sym"] for u in SMALL_UNIVERSE] and c["symbols"][0]["expiries"][0]["dte"] >= 0
    ch = M.ENDPOINTS["chain-NVDA"]() if "chain-NVDA" in M.ENDPOINTS else M.chain_detail(SMALL_UNIVERSE[2])
    ch = M.chain_detail(SMALL_UNIVERSE[2])
    B.json_safe(ch)
    e = ch["chains"]["2026-11-20"]
    assert e["atm"] == 190.0 and e["lines"] and {"k", "cp", "bid", "ask", "mid", "vol", "oi", "iv", "delta", "gamma"} <= set(e["lines"][0]) and e["gex"] and e["gex_total"] is not None
    assert all(0.6 * ch["spot"] <= l["k"] <= 1.5 * ch["spot"] for l in e["lines"])
    v = M.ENDPOINTS["vol"]()
    B.json_safe(v)
    nv = v["symbols"]["NVDA"]
    assert nv["term"] and nv["term"][0][0] < nv["term"][-1][0] and nv["term_week_ago"] and nv["term_week_ago"]["points"] and len(nv["iv_hist"]) == 16 and nv["rank_hist"] and nv["rv30_hist"]
    assert v["basket"]["vrp_share"] is not None and v["vix"] and v["order"][0] == "SPY"
    k = M.ENDPOINTS["skew"]()
    B.json_safe(k)
    assert k["unusual"] and all(u["ratio"] > 5 and u["vol"] >= 1000 for u in k["unusual"]) and k["skew_index"] and k["ai_skew_hist"]
    sp = k["symbols"]["SPY"]
    assert sp["oi_by_strike"] and len(sp["oi_by_strike"][0]) == 3 and sp["skew_term"] and sp["next_monthly"]["exp"] == "2026-11-20"
    assert k["basket"]["skew_index_rank"]["pct"] is not None and k["basket"]["skew_pct_own"]["days"] == 16
    m = M.ENDPOINTS["moves"]()
    B.json_safe(m)
    nv = m["symbols"]["NVDA"]
    assert nv["cone"] and nv["cone"][0]["em_iv"] < nv["cone"][-1]["em_iv"] and nv["earnings"]["date"] == "2026-11-19" and nv["spot_hist"]
    assert nv["past_n"] > 0 and all(p["exp"] <= "2026-11-08" for p in nv["past"]) and nv["past_inside"] is not None        # the seeded weeklies have expired
    assert any(e["kind"] == "fomc" for e in m["events"])
    l = M.ENDPOINTS["lab"]()
    assert l["default"] == "NVDA" and l["rate"] == M.RATE and len(l["structures"]) == 9 and l["symbols"][0]["expiries"][0]["atm_iv"]


def test_past_moves_compare_the_snapshot_with_the_close_at_expiry():
    s = {"daily": {"2026-10-01": {"spot": 100.0, "exp": {"2026-10-17": {"dte": 16, "em_iv": 0.05, "em_straddle": 0.04}, "2026-12-18": {"dte": 78, "em_iv": 0.12}}}},
         "rv": {"close": [[int(pd.Timestamp("2026-10-16").timestamp()), 103.0], [int(pd.Timestamp("2026-10-20").timestamp()), 110.0]]}}
    out = M.past_moves(s, "2026-11-08")
    assert len(out) == 1 and out[0]["exp"] == "2026-10-17" and out[0]["end"] == 103.0 and out[0]["realised"] == 0.03 and out[0]["inside"]   # the Friday's close stands for the Saturday expiry


def test_readings_and_signals_from_cached_payloads(mocked, frozen):
    assert M.READINGS() == [] and M.SIGNALS() == []                                   # nothing cached yet, nothing invented
    seed_history(15)
    M.ENDPOINTS["setup"](); M.ENDPOINTS["skew"]()
    r = {x["key"]: x for x in M.READINGS()}
    assert {"vix_term", "ai_iv_rank", "vrp_share", "ai_skew", "spy_pc_oi", "spy_em"} <= set(r)
    assert all(x["tab"] in {t for t, _ in topics.REGISTRY["options"].tabs} and x["lean"] in (-1, 0, 1) for x in r.values())
    s = {x["key"]: x for x in M.SIGNALS()}
    want = {w["key"] for w in json.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())["options"]}
    assert set(s) == want == {"vix_term", "ai_iv_rank", "skew_ai", "vrp", "pc_oi"}
    for x in s.values():
        assert x["watch"] and isinstance(x["crossed"], bool) and x["lean"] in (-1, 0, 1) and x["value"] is not None
    assert s["vix_term"]["crossed"] == (s["vix_term"]["value"] < 0 or s["vix_term"]["value"] > 5)
    assert s["vrp"]["crossed"] == (s["vrp"]["value"] < 30 or s["vrp"]["value"] > 90)
    assert s["pc_oi"]["crossed"] == (s["pc_oi"]["value"] > 2 or s["pc_oi"]["value"] < 1)
    assert "fallback" in s["skew_ai"]["note"]                                            # 16 days of own history: the SKEW index stands in
    assert all(w.get("proposed") for w in json.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())["options"])


def test_setup_without_history_still_answers_and_handles_a_dead_source(mocked, frozen, monkeypatch):
    def dl(url, ttl=0, **k):
        if "VVIX" in url or "IWM" in url:
            raise ConnectionError("down")
        return fake_fetch(url, ttl, **k)
    monkeypatch.setattr(M, "fetch", dl)
    monkeypatch.setattr(M, "universe", lambda: SMALL_UNIVERSE + [{"sym": "IWM", "name": "Russell", "group": "index", "cboe": "IWM", "both": False}])
    d = M.ENDPOINTS["setup"]()
    assert d["errors"] == {"IWM": "ConnectionError: down"} and d["index_errors"] == {"vvix_error": "ConnectionError"} and d["head"]["vvix"] is None
    assert next(r for r in d["table"] if r["sym"] == "IWM")["error"] and d["head"]["vix_term"] is not None
    assert d["basket"]["history_days"] == 1 and d["ai_rank_hist"] == [] and d["head"]["ai_iv_rank"] is None      # one day: no rank yet, nothing invented
    r = {x["key"]: x for x in M.READINGS()}
    assert "vix_term" in r and "ai_iv_rank" not in r


def test_routes(mocked, frozen):
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    seed_history(15)

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            page = await c.get("/options")
            setup = await c.get("/api/options/setup")
            chain = await c.get("/api/options/chain-NVDA")
            meta = await (await c.get("/api/options/meta")).json()
            method = await (await c.get("/api/options/method")).json()
            return page.status, setup.status, (await setup.json())["head"]["vix"], chain.status, (await chain.json())["spot"], meta, method
    st, ss, vix, cs, spot, meta, method = asyncio.run(go())
    assert st == 200 and ss == 200 and vix and cs == 200 and spot == SPOTS["NVDA"]
    assert meta["category"] == "Money & markets" and meta["method"] and "Not investment advice" in meta["footer"] and len(meta["tabs"]) == 6
    assert any("Method" in s["title"] for s in method["sections"])
