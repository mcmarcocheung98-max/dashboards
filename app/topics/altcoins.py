"""Altcoin Study (/altcoins): the four BTC Cycles candidates with a tab each (HYPE, ENA, SOL, NEAR), the memecoin basket and meme season,
and a buy zone for every coin on one tab.

zones    every coin's buy zone (rule below), where today's price sits against it, RSI and the 30-day move
boards   every coin's signal board (_coin_board.py): the BTC spot signal's set-up per coin, and the fitted board (the same gauges with signs and
         weights learned from their pooled record, walk-forward); the candidates' tabs show their own
volume   big-volume days (3x the 60-day median) and the support / resistance zones they leave, per coin, from Hyperliquid daily candles
         (_volume_zones.py); what each coin did after its own big days and zone retests
signals  twenty daily signals on top of the zones (zone position, retests, breaks, big-day balance, trend, RSI, BTC, unlock windows ...),
         each judged on the next 7, 14 and 30 days, weighted by rank correlation on the pooled past of every coin and re-fitted every 30
         days, one final score per coin and horizon with a walk-forward backtest of trading it (_signals.py)
hype ... one tab per candidate (_coin_page.py): its signal board (_coin_board.py: the BTC spot signal's set-up per coin - gauges scored
         -1..+1 in buy / sell zones, a weighted aggregate with the five levels, take-profit and trend-break sell states, the record by
         zone and what would flip it), price against BTC, RSI, market cap, the case for it, fundamentals and the projection
unlocks  ENA's full unlock schedule (data/altcoins/unlocks/ENA.csv) and what the price did before, into and after each unlock, with the
         simple short-before / buy-after rules and a placebo (_unlocks.py)
basket   the memecoin basket (memecoins.py): prices, momentum against BTC, a sortable table
season   whether memes are beating BTC (memecoins.py)

Buy zone (mechanical, recomputed with each day's prices; research, not advice):
  top    the 200-day average price, or, for a candidate with a projection, the price from which the base case to end-2028 at least doubles
         (base ÷ 2) when that is lower: below its own long average AND with room in the base case
  floor  the lowest close of the last 365 days
  mid    half-way between, so a buyer can stage entries (top, mid, floor)
  status 'in zone' when today's price is at or below the top; 'above zone' with the fall needed to reach the top; 'no zone' when the top is
         below the year's low (the base case does not double from any price seen this year)
A coin can sit 'in zone' while still falling: the 30-day move and RSI are shown beside it for that reason.

Only the Hyperliquid daily candles are downloaded here (one POST per coin, cached for 6 hours, kept as a snapshot): btc_cycles' and
memecoins' background fills keep every coin's 365 days of CoinGecko prices for the other tabs.
"""
from __future__ import annotations

import time

import pandas as pd

import numpy as np

from ..cache import _cached
from . import Topic
from . import _coin_board as CB
from . import _coin_page as P
from . import _narrative as NR
from . import _signals as SG
from . import _unlocks as UL
from . import _volume_zones as VZ
from . import btc_cycles as C
from . import memecoins as M
from ._base import DAY, _r, fetch_json, stale_info

SLUG = "altcoins"
CANDIDATES = ("HYPE", "ENA", "SOL", "NEAR")
TABS = (("zones", "Buy zones"), ("boards", "Signal boards"), ("volume", "Volume zones"), ("signals", "Signals"), *((t.lower(), t) for t in CANDIDATES), ("unlocks", "ENA unlocks"), ("basket", "Memecoins"), ("season", "Meme season"))
TOPIC = Topic(SLUG, "Altcoin Study",
              "HYPE, ENA, SOL and NEAR in full (price against BTC, fundamentals, the bear / base / bull projection), the memecoin basket and meme "
              "season, a buy zone for every coin, the big-volume days and the support / resistance zones they leave, and ENA around every token unlock.",
              "altcoins", TABS, ("zones", "boards", "volume", "signals", "unlocks", "basket", "season"), icon="chart", order=12)
MA_DAYS = 200
VALUE_MULT = 2.0                               # the base case to end-2028 must at least double from the top of the zone
SIBLINGS = {t: f"#{t.lower()}" for t in CANDIDATES}
SOURCES = [*(s for t in CANDIDATES for s in P.sources(t)), *M.SOURCES,
           {"name": "Projection levels and coin notes (BTC Cycles & Sector Rotation)", "url": "/btc-cycles#candidates", "cadence": "as revised"},
           {"name": "Daily candles with volume for the volume zones and the unlock study (Hyperliquid public API)", "url": "https://api.hyperliquid.xyz/info", "cadence": "every 6 hours"},
           {"name": "ENA unlock schedule (hand-entered from Ethena docs, Binance, Tokenomist, news; data/altcoins/unlocks/ENA.csv)", "url": "https://docs.ethena.fi/overview/ena/tokenomics", "cadence": "as revised"}]
NOTES = ("Research, not investment advice. Buy zones are mechanical: below the coin's 200-day average and, for the four candidates, low enough "
         "that the base-case projection at least doubles by end-2028. They say nothing about whether a coin survives or what its news will be. "
         "Volume zones and the unlock study are descriptive statistics on a few years of one coin's prices: a hint to watch, not a rule to trade.")

# Hyperliquid perp names for the coins (k-prefixed markets quote 1,000 tokens); coins not listed there have no volume zones
HL_INFO = "https://api.hyperliquid.xyz/info"
HL_COINS = {"HYPE": ("HYPE", 1), "ENA": ("ENA", 1), "SOL": ("SOL", 1), "NEAR": ("NEAR", 1), "DOGE": ("DOGE", 1), "WIF": ("WIF", 1), "TRUMP": ("TRUMP", 1),
            "PEPE": ("kPEPE", 1000), "BONK": ("kBONK", 1000), "SHIB": ("kSHIB", 1000)}
HL_TTL = 6 * 3600
CHART_DAYS = 400


# ------------------------------------------------------------------ the buy zone
def buy_zone(prices: pd.Series, base_2028: float | None = None) -> dict:
    """Buy zone from a daily price series (the last 365 days) and, if there is one, the base-case price at end-2028. See the module doc."""
    s = prices.dropna()
    s = s[s.index >= s.index[-1] - pd.Timedelta(days=365)] if len(s) else s
    if len(s) < MA_DAYS:
        return {"status": "no data", "why": f"needs {MA_DAYS} days of prices, has {len(s)}"}
    price, ma, low = float(s.iloc[-1]), float(s.iloc[-MA_DAYS:].mean()), float(s.min())
    cap = base_2028 / VALUE_MULT if base_2028 and base_2028 > 0 else None
    top, basis = (cap, "base case ÷ 2") if cap is not None and cap < ma else (ma, "200-day average")
    out = {"price": _r(price, 10), "ma200": _r(ma, 10), "value_cap": _r(cap, 10) if cap is not None else None, "floor": _r(low, 10), "basis": basis,
           "change_30d": _r(price / float(s.asof(s.index[-1] - pd.Timedelta(days=30))) - 1, 4)}
    if top < low:
        return out | {"status": "no zone", "top": _r(top, 10), "mid": None,
                      "why": "the base case does not double from any price seen in the last year"}
    out |= {"top": _r(top, 10), "mid": _r((top + low) / 2, 10)}
    if price <= top:
        return out | {"status": "in zone", "vs_top": _r(price / top - 1, 4)}
    return out | {"status": "above zone", "vs_top": _r(top / price - 1, 4)}      # negative: the fall needed to reach the top


def _series(pts) -> pd.Series:
    return pd.Series({pd.to_datetime(int(t), unit="s"): v for t, v in (pts or []) if v is not None}, dtype=float).sort_index()


def _coin_tab(ticker: str) -> dict:
    f = P.payload(ticker, SIBLINGS)
    pts = (f.get("series") or {}).get("price")
    if pts:
        f["zone"] = buy_zone(_series(pts), (f.get("kpi") or {}).get("base_2028"))
    if ticker in UL.coins():
        ev = UL.events(ticker)
        now = pd.Timestamp.now("UTC").tz_localize(None).normalize()
        f["unlocks"] = {"recent": [UL._row(r) for r in ev[(ev.date < now) & (ev.date >= now - pd.Timedelta(days=90))].itertuples()],
                        "coming": [UL._row(r) for r in ev[ev.date >= now].head(6).itertuples()], "tab": "#unlocks"}
    f["board"] = _board_for(ticker, f)
    return f


def _board_for(ticker: str, f: dict | None = None) -> dict:
    """The coin's board from the shared boards endpoint (one computation for every coin, so the fitted weights see all of them)."""
    try:
        all_ = ENDPOINTS["boards"]()
    except Exception as e:
        return {"status": "error", "why": type(e).__name__}
    row = next((c for c in (all_ or {}).get("coins", []) if c["ticker"] == ticker), None)
    if row is None:
        return {"status": "error", "why": "not in the boards"}
    if row.get("status") != "ok":
        return {"status": row.get("status", "error"), "why": row.get("why")}
    return {**row["board"], "fitted": row.get("fitted"), "fitted_weights": (all_.get("fitted") or {}).get("weights_now"), "fitted_how": (all_.get("fitted") or {}).get("how_now")}


def _board_context(coins: list[dict], btc: pd.DataFrame) -> dict:
    """What the coin-specific gauges share: closes and funding for every market involved, market caps, stablecoin, DEX and derivatives series.
    Each piece is optional and fetched once; a failure leaves that gauge out for the coins that need it."""
    ctx = {"closes": {"BTC": btc.close}, "funding": {}, "mcaps": {}, "btc_mcap": None, "stables": {}, "dex": {}, "deriv_share": {}}
    markets = {c["ticker"] for c in coins if c["ticker"] in HL_COINS}
    for t in markets:
        cfg = NR.COINS.get(t, {})
        markets_needed = set(cfg.get("sector") or []) | set(cfg.get("basis") or [])
        for m in markets_needed:
            if m not in ctx["closes"]:
                try:
                    ctx["closes"][m] = hl_daily(m).close
                except Exception:
                    pass
    for t in markets:
        try:
            ctx["closes"].setdefault(t, hl_daily(t).close)
        except Exception:
            pass
    for m in markets | {"BTC", "ETH"}:
        try:
            f = NR.funding_daily(HL_COINS.get(m, (m, 1))[0])
            if len(f):
                ctx["funding"][m] = f
        except Exception:
            pass
    cg = {c["ticker"]: c["coingecko_id"] for c in C.coins_list()} | {c["ticker"]: c["coingecko_id"] for c in M.coins_list()}
    for t in markets:
        try:
            _, mc = C.coin_chart(cg[t])
            if len(mc):
                ctx["mcaps"][t] = mc
        except Exception:
            pass
    try:
        _, ctx["btc_mcap"] = C.coin_chart("bitcoin")
    except Exception:
        pass
    sources = {("stable", k): (lambda k=k: NR.stable_supply(k)) for k in {v.get("stable") for v in NR.COINS.values() if v.get("stable")}}
    sources |= {("chain", k): (lambda k=k: NR.chain_stables(k)) for k in {v.get("chain_stables") for v in NR.COINS.values() if v.get("chain_stables")}}
    for key, fn in sources.items():
        try:
            ctx["stables"][key[1]] = fn()
        except Exception:
            pass
    for ch in {v.get("dex_chain") for v in NR.COINS.values() if v.get("dex_chain")}:
        try:
            ctx["dex"][ch] = NR.chain_dex_volume(ch)
        except Exception:
            pass
    for pr in {v.get("deriv_share") for v in NR.COINS.values() if v.get("deriv_share")}:
        try:
            ctx["deriv_share"][pr] = NR.derivatives_share(pr)
        except Exception:
            pass
    return ctx


def _coin_inputs(c: dict, btc: pd.DataFrame, zone_scores: dict, ctx: dict | None = None) -> pd.DataFrame:
    """Everything the board needs for one coin: Hyperliquid daily closes, BTC's, CoinGecko market cap (what the fills already hold), DefiLlama daily
    fees and TVL (candidates), the unlock schedule (hand-entered file, else DefiLlama's curve), the flipped zone position and the 20-signal score."""
    t = c["ticker"]
    d = hl_daily(t)
    if len(d) < 120:
        raise ValueError(f"only {len(d)} days")
    mc = None
    try:
        _, mc = C.coin_chart(c["coingecko_id"])
    except Exception:
        pass
    raw = C.fundamentals(t)
    fees_daily, tvl_daily = C._ser(raw.get("fees")), C._ser(raw.get("tvl"))
    fees_30d = fees_daily.rolling(30, min_periods=20).sum().dropna() if len(fees_daily) else None
    tvl = tvl_daily if len(tvl_daily) else None
    unlocked = circ = None
    unlock_days = None
    now = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    try:
        if t in UL.coins():
            ev = UL.events(t)
            unlocked = pd.Series(ev.cumulative_m.to_numpy() * 1e6, index=pd.DatetimeIndex(ev.date))
            circ = float(ev[ev.date <= now].amount_m.sum()) * 1e6 or None
            unlock_days = pd.DatetimeIndex(ev[ev.pct_of_circulating.fillna(np.inf) >= 1.0].date)
        else:
            curve = C._ser(raw["schedule"]) if raw.get("schedule") else NR.emissions_curve(c.get("coingecko_id") or t.lower())      # memecoins have no fill file: DefiLlama's curve
            if len(curve) > 2:
                unlocked = curve
                circ = (raw.get("supply") or {}).get("circulating_supply") or (float(mc.iloc[-1] / d.close.iloc[-1]) if mc is not None and len(mc) else None)
                unlock_days = NR.unlock_event_days(curve)
    except Exception:
        unlocked = circ = None
    ev_sig = UL.events(t) if t in UL.coins() else None
    zone_pos = None
    try:
        zone_pos = SG.signals(d, btc, VZ.zones(d, t), ev_sig)["in_zone"]
    except Exception:
        pass
    extra = {}
    if ctx is not None:
        try:
            extra = NR.extra_inputs(t, d.close, {**ctx, "fees30": fees_30d, "unlock_events": unlock_days})
        except Exception:
            extra = {}
    return CB.inputs(d.close, btc.close, mc, fees_30d, tvl, unlocked, circ, zone_pos, zone_scores.get(t), extra)


def _boards_now() -> dict:
    """Every coin's board (the BTC board's set-up) plus the fitted board: the same gauges with signs and weights learned from their pooled record,
    walk-forward. Memecoins have no fees or TVL, so their boards run on the price, BTC, unlock and zone gauges."""
    try:
        btc = hl_daily("BTC")
    except Exception as e:
        return _scrub({"coins": [{**c, "status": "error", "why": f"BTC candles: {type(e).__name__}"} for c in _all_coins()], "fitted": {}, "updated": int(time.time()), "stale": stale_info([HL_INFO])})
    zone_scores = {}
    try:
        blk = (ENDPOINTS["signals"]() or {}).get("by_horizon", {}).get(str(SG.HORIZON), {}).get("coins", {})
        zone_scores = {t: _series(r.get("composite")) for t, r in blk.items() if r.get("composite")}
    except Exception:
        pass
    cg = {c["ticker"]: c["coingecko_id"] for c in C.coins_list()} | {c["ticker"]: c["coingecko_id"] for c in M.coins_list()}
    coins, per, frames = [], {}, {}
    all_coins = _all_coins()
    try:
        ctx = _board_context(all_coins, btc)
    except Exception:
        ctx = None
    for c in all_coins:
        if c["ticker"] not in HL_COINS:
            coins.append({**c, "status": "not on Hyperliquid"})
            continue
        try:
            d = _coin_inputs({**c, "coingecko_id": cg.get(c["ticker"])}, btc, zone_scores, ctx)
            sc = CB.board(d)
            per[c["ticker"]] = (sc[[g.key for g in CB.GAUGES if g.key in sc]], d["price"])
            frames[c["ticker"]] = (d, sc)
            coins.append({**c, "status": "ok", "board": CB.payload(d)})
        except Exception as e:
            coins.append({**c, "status": "error", "why": f"{type(e).__name__}: {e}"})
    out = {"coins": coins, "fitted": {"horizon": CB.FIT_HORIZON, "levels": CB.LEVELS, "refit_days": CB.FIT_REFIT_DAYS, "min_train_days": CB.FIT_MIN_TRAIN}, "updated": int(time.time()), "stale": stale_info([HL_INFO]),
           "context": {k: sorted(v) for k, v in {"funding": (ctx or {}).get("funding", {}), "market_caps": (ctx or {}).get("mcaps", {}), "stablecoins": (ctx or {}).get("stables", {}),
                                                 "dex_volume": (ctx or {}).get("dex", {}), "derivatives_share": (ctx or {}).get("deriv_share", {}), "closes": (ctx or {}).get("closes", {})}.items()}}
    if not per:
        return _scrub(out)
    try:
        wf = CB.fitted_walk_forward(per)
    except Exception as e:
        out["fitted"]["error"] = f"{type(e).__name__}: {e}"
        return _scrub(out)
    out["fitted"] |= {"weights_now": wf["weights_now"], "how_now": wf["how_now"], "train_rows": wf.get("train_rows_now"), "record": wf.get("record", []),
                      "fits": [{k: v for k, v in f.items() if k != "weights"} for f in wf["fits"]], "flipped": sorted(k for k, v in (wf["weights_now"] or {}).items() if v < 0)}
    for c in coins:
        if c["status"] != "ok":
            continue
        t = c["ticker"]
        d, sc = frames[t]
        comp = wf["composite"][t]
        try:
            today = CB.fitted_today(per[t][0], d, wf["weights_now"])
            since = d.index[-1] - pd.Timedelta(days=730)
            c["fitted"] = {**today, "series": [[int(x.timestamp()), None if not np.isfinite(comp.loc[x]) else round(float(comp.loc[x]), 3), round(float(d.loc[x, "price"]), 8)] for x in d.index if x >= since],
                           "record": CB.zone_returns_of(comp, d["price"]), "backtest": CB.fitted_backtest(comp, d["price"]),
                           "backtest_long_only": {k: v for k, v in CB.fitted_backtest(comp, d["price"], long_short=False).items() if k not in ("equity", "hold_curve")},
                           "history_from": str(comp.dropna().index[0].date()) if comp.notna().any() else None}
        except Exception as e:
            c["fitted"] = {"status": "error", "why": f"{type(e).__name__}: {e}"}
    ok = [c for c in coins if c["status"] == "ok"]
    out["counts"] = {"classic": {"buy": sum("BUY" in c["board"]["label"] for c in ok), "sell": sum("SELL" in c["board"]["label"] for c in ok)},
                     "fitted": {"buy": sum((c.get("fitted") or {}).get("lean") == 1 for c in ok), "sell": sum((c.get("fitted") or {}).get("lean") == -1 for c in ok), "readings": sum((c.get("fitted") or {}).get("status") == "ok" for c in ok)}}
    bts = [c["fitted"]["backtest"] for c in ok if (c.get("fitted") or {}).get("backtest", {}).get("total") is not None]
    if bts:
        med = lambda key: (lambda xs: float(np.median(xs)) if xs else None)([b[key] for b in bts if b.get(key) is not None and np.isfinite(b[key])])
        out["fitted"]["pooled_backtest"] = {"coins": len(bts), "beat_hold": sum(b["total"] > b["hold"] for b in bts), "median_a_year": med("a_year"), "median_hold_a_year": med("hold_a_year"),
                                            "median_sharpe": med("sharpe"), "median_worst_drop": med("worst_drop"), "median_hit_rate": med("hit_rate")}
    return _scrub(out)


def _zones_now() -> dict:
    rows = []
    for t in CANDIDATES:
        try:
            f = ENDPOINTS[t.lower()]()
            if "zone" not in f:
                raise LookupError
            rows.append({"ticker": t, "name": f.get("name", t), "group": "Candidate", "tab": t.lower(), "rsi": f["kpi"].get("rsi"),
                         "base_2028": f["kpi"].get("base_2028"), **f["zone"]})
        except Exception as e:
            rows.append({"ticker": t, "name": t, "group": "Candidate", "tab": t.lower(),
                         "status": "loading" if isinstance(e, LookupError) else "error", "why": type(e).__name__})
    for c in M.coins_list():
        try:
            px, _ = C.coin_chart(c["coingecko_id"])
            r = C.rsi(px)
            rows.append({"ticker": c["ticker"], "name": c["name"], "group": "Memecoin", "tab": "basket",
                         "rsi": _r(float(r.dropna().iloc[-1]), 1) if r.notna().any() else None, **buy_zone(px)})
        except Exception as e:
            rows.append({"ticker": c["ticker"], "name": c["name"], "group": "Memecoin", "tab": "basket",
                         "status": "loading" if isinstance(e, LookupError) else "error", "why": type(e).__name__})
    count = lambda st: sum(r["status"] == st for r in rows)
    return {"coins": rows, "counts": {"in zone": count("in zone"), "above zone": count("above zone"), "no zone": count("no zone")},
            "rule": {"ma_days": MA_DAYS, "value_mult": VALUE_MULT}, "updated": int(time.time())}


# ------------------------------------------------------------------ volume zones: Hyperliquid daily candles, big days, support / resistance
def _hl_post(coin: str) -> dict:
    """Up to 5,000 daily candles (the whole history of the market); the window is rounded to the day so the download is cached per day."""
    today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    return {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": int((today - pd.Timedelta(days=4999)).timestamp() * 1000),
                                               "endTime": int((today + pd.Timedelta(days=1)).timestamp() * 1000)}}


def hl_daily(ticker: str) -> pd.DataFrame:
    """Closed daily candles (open, high, low, close, volume in coins, usd_volume) for a coin's Hyperliquid market, scaled to one token."""
    name, k = HL_COINS.get(ticker, (ticker, 1))
    raw = fetch_json(HL_INFO, HL_TTL, post=_hl_post(name), min_bytes=100)
    if not raw:
        raise ValueError(f"no Hyperliquid candles for {name}")
    d = pd.DataFrame(raw)
    d["ts"] = pd.to_datetime(d["t"].astype("int64"), unit="ms")
    d = d.set_index("ts")[["o", "h", "l", "c", "v"]].astype(float)
    d.columns = ["open", "high", "low", "close", "volume"]
    d[["open", "high", "low", "close"]] /= k
    d["volume"] *= k
    d["usd_volume"] = d.volume * d.close
    today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    return d[d.index < today].sort_index()


def _all_coins() -> list[dict]:
    out = [{"ticker": t, "name": P.coin_row(t)["name"], "group": "Candidate", "tab": t.lower()} for t in CANDIDATES]
    return out + [{"ticker": c["ticker"], "name": c["name"], "group": "Memecoin", "tab": "basket"} for c in M.coins_list()]


def zone_read(now: dict) -> tuple[str, int]:
    """One line on where the price sits: inside support (+1), inside resistance (-1), within 3% under resistance (-1), within 3% over support (+1), else between (0)."""
    if "inside" in now:
        k = now["inside"]["kind"]
        return (f"inside a {'support' if k == 'buy' else 'resistance'} zone", 1 if k == "buy" else -1)
    r, s = now.get("resistance"), now.get("support")
    if r and r["above_pct"] <= 0.03:
        return (f"{r['above_pct']:.1%} under resistance", -1)
    if s and s["below_pct"] <= 0.03:
        return (f"{s['below_pct']:.1%} over support", 1)
    if r or s:
        return ("between zones", 0)
    return ("no live zone", 0)


def _volume_now() -> dict:
    coins, t0 = [], pd.Timestamp.now("UTC").tz_localize(None).normalize() - pd.Timedelta(days=CHART_DAYS)
    for c in _all_coins():
        if c["ticker"] not in HL_COINS:
            coins.append({**c, "status": "not on Hyperliquid"})
            continue
        try:
            d = hl_daily(c["ticker"])
            if len(d) < 90:
                raise ValueError(f"only {len(d)} days of candles")
            p = VZ.chart_payload(d, c["ticker"], CHART_DAYS)
            read, lean = zone_read(p["now"])
            big30 = [b for b in p["big_days"] if b["ts"] >= int((d.index[-1] - pd.Timedelta(days=30)).timestamp())]
            coins.append({**c, **p, "status": "ok", "market": HL_COINS[c["ticker"]][0], "read": read, "lean": lean, "big_days_30d": len(big30),
                          "unlocks": UL.for_chart(c["ticker"], t0, d.index[-1] + pd.Timedelta(days=90)) if c["ticker"] in UL.coins() else []})
        except Exception as e:
            coins.append({**c, "status": "error", "why": type(e).__name__})
    ok = [c for c in coins if c["status"] == "ok"]
    return {"coins": coins, "counts": {"inside support": sum(c["lean"] > 0 for c in ok), "under resistance": sum(c["lean"] < 0 for c in ok), "coins": len(ok)},
            "settings": VZ.DEFAULTS, "stale": stale_info([HL_INFO]), "updated": int(time.time())}


# ------------------------------------------------------------------ 20 signals on top of the zones, weighted into one reading per coin
def _signals_now() -> dict:
    """Every horizon in SG.HORIZONS is fitted and backtested separately; the page switches between them, READINGS use SG.HORIZON."""
    try:
        btc = hl_daily("BTC")
    except Exception as e:
        btc = None
        btc_err = type(e).__name__
    else:
        btc_err = None
    per, coins = {}, []
    for c in _all_coins():
        if c["ticker"] not in HL_COINS:
            coins.append({**c, "status": "not on Hyperliquid"})
            continue
        try:
            d = hl_daily(c["ticker"])
            if len(d) < 120:
                raise ValueError(f"only {len(d)} days")
            ev = UL.events(c["ticker"]) if c["ticker"] in UL.coins() else None
            S = SG.signals(d, btc, VZ.zones(d, c["ticker"]), ev)
            per[c["ticker"]] = (S, d.close)
            coins.append({**c, "status": "ok", "price": float(d.close.iloc[-1]), "since": str(d.index[0].date()), "days": len(d), "unlock_schedule": ev is not None,
                          "today": {k: float(S[k].iloc[-1]) for k in SG.SIGNALS}})
        except Exception as e:
            coins.append({**c, "status": "error", "why": type(e).__name__})
    out = {"coins": coins, "signals": [{"key": k, "label": v[0], "family": v[1], "means": v[2]} for k, v in SG.SIGNALS.items()], "horizon": SG.HORIZON, "horizons": list(SG.HORIZONS),
           "enter": SG.ENTER, "refit_days": SG.REFIT_DAYS, "min_train_days": SG.MIN_TRAIN_DAYS, "cost_per_side": SG.COST_PER_SIDE, "btc_error": btc_err,
           "stale": stale_info([HL_INFO]), "updated": int(time.time()), "by_horizon": {}}
    if not per:
        return _scrub(out)
    for h in SG.HORIZONS:
        out["by_horizon"][str(h)] = _horizon_block(per, h)
    main = out["by_horizon"].get(str(SG.HORIZON), {})
    out |= {k: main.get(k) for k in ("weights", "how", "train_rows", "weights_drift", "per_signal", "pooled_backtest", "counts", "error")}
    for c in coins:                                   # the default horizon's reading on the coin itself, for READINGS and the table
        if c["status"] == "ok" and c["ticker"] in (main.get("coins") or {}):
            r = main["coins"][c["ticker"]]
            if r.get("status") == "ok":
                c |= {k: r[k] for k in ("score", "label", "lean", "contributions", "backtest", "backtest_long_only")}
            else:
                c["status"], c["why"] = "error", r.get("why")
    return _scrub(out)


def _horizon_block(per: dict, h: int) -> dict:
    """Weights, per-signal record, every coin's composite and backtest, all judged on the return `h` days ahead."""
    block = {"horizon": h, "coins": {}}
    try:
        wf = SG.walk_forward(per, h=h)
    except Exception as e:
        block["error"] = f"weights: {type(e).__name__}: {e}"
        return block
    block |= {"weights": wf["weights_now"], "how": wf["how_now"], "fits": [{k: v for k, v in f.items() if k != "weights"} for f in wf["fits"]], "train_rows": wf.get("train_rows_now")}
    if wf["fits"] and wf["weights_now"]:
        last = wf["fits"][-1]["weights"]
        block["weights_drift"] = float(sum(abs(wf["weights_now"][k] - last[k]) for k in SG.SIGNALS) / 2)
    try:
        pooled = pd.concat([S.assign(_fwd=SG.forward(c, h).reindex(S.index)) for S, c in per.values()])
        block["per_signal"] = SG.evaluate(pooled[list(SG.SIGNALS)], pooled["_fwd"])
    except Exception as e:
        block["per_signal"], block["per_signal_error"] = [], f"{type(e).__name__}: {e}"
    for ticker, (S, close) in per.items():
        try:
            comp = wf["composite"][ticker]
            today = SG.composite(S.iloc[[-1]], wf["weights_now"]).iloc[0] if wf["weights_now"] else None
            score = None if today is None or not np.isfinite(today) else float(today)
            r = {"status": "ok", "score": score, "label": SG.label(score), "lean": 0 if score is None else (1 if score >= SG.ENTER else -1 if score <= -SG.ENTER else 0),
                 "contributions": SG.contributions(S.iloc[-1], wf["weights_now"] or {}),
                 "composite": [[int(t.timestamp()), round(float(v), 3)] for t, v in comp.dropna().items()],
                 "price_series": [[int(t.timestamp()), float(v)] for t, v in close.reindex(comp.dropna().index).items()],
                 "backtest": SG.backtest(comp, close, h=h), "backtest_long_only": {k: v for k, v in SG.backtest(comp, close, long_short=False, h=h).items() if k not in ("equity", "hold_curve")},
                 "own_eval": SG.evaluate(S, SG.forward(close, h))}
        except Exception as e:
            r = {"status": "error", "why": f"{type(e).__name__}: {e}"}
        block["coins"][ticker] = r
    ok = [r for r in block["coins"].values() if r.get("status") == "ok" and r.get("score") is not None]
    block["counts"] = {"buy": sum(r["lean"] > 0 for r in ok), "sell": sum(r["lean"] < 0 for r in ok), "neutral": sum(r["lean"] == 0 for r in ok)}
    bts = [r["backtest"] for r in ok if r["backtest"].get("total") is not None]
    if bts:
        med = lambda key: (lambda xs: float(np.median(xs)) if xs else None)([b[key] for b in bts if b.get(key) is not None and np.isfinite(b[key])])
        lo = [r["backtest_long_only"] for r in ok if r["backtest_long_only"].get("total") is not None]
        medl = lambda key: (lambda xs: float(np.median(xs)) if xs else None)([b[key] for b in lo if b.get(key) is not None and np.isfinite(b[key])])
        block["pooled_backtest"] = {"coins": len(bts), "beat_hold": sum(b["total"] > b["hold"] for b in bts), "median_a_year": med("a_year"), "median_hold_a_year": med("hold_a_year"),
                                    "median_sharpe": med("sharpe"), "median_worst_drop": med("worst_drop"), "median_hit_rate_7d": med("hit_rate_7d"),
                                    "long_only_beat_hold": sum(b["total"] > b["hold"] for b in lo), "long_only_median_a_year": medl("a_year"), "long_only_median_sharpe": medl("sharpe"),
                                    "long_only_median_worst_drop": medl("worst_drop"), "signals_with_weight": sum(1 for v in (wf["weights_now"] or {}).values() if v > 0)}
    return block


def _scrub(x):
    """JSON has no NaN or infinity: None instead, all the way down (the server refuses a payload with either)."""
    if isinstance(x, dict):
        return {k: _scrub(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_scrub(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    return x


# ------------------------------------------------------------------ ENA unlocks: the schedule and what the price did around each one
UNLOCK_COIN = "ENA"


def _unlocks_now() -> dict:
    sched, ev = UL.schedule(UNLOCK_COIN), UL.events(UNLOCK_COIN)
    now = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    out = {"coin": UNLOCK_COIN, "schedule": [{**r._asdict(), "date": str(r.date.date())} for r in sched.fillna("").itertuples(index=False)],
           "events": [UL._row(r) for r in ev.itertuples()], "next": None, "updated": int(time.time()), "stale": stale_info([HL_INFO])}
    future = ev[ev.date >= now]
    if len(future):
        r = future.iloc[0]
        out["next"] = {**UL._row(r), "days": int((r.date.normalize() - now).days)}
        nb = future[future.pct_of_circulating.fillna(0) >= 1]
        if len(nb):
            out["next_big"] = {**UL._row(nb.iloc[0]), "days": int((nb.iloc[0].date.normalize() - now).days)}
    out["unlocked_m"] = float(ev[ev.date <= now].amount_m.sum()) if len(ev) else None
    out["total_m"] = 15000.0
    try:
        d = hl_daily(UNLOCK_COIN)
        et = UL.event_table(d, ev)
        out |= {"price": VZ.chart_payload(d, UNLOCK_COIN, 10000)["bars"], "event_table": et, "averages": UL.averages(et, d), "rules": UL.rules(d, ev),
                "history_since": str(d.index[0].date()), "events_in_history": len(et),
                "date_check": sum(1 for r in et if r["max_vol_day_offset"] == 0), "date_check_off": sum(1 for r in et if abs(r["max_vol_day_offset"]) >= 2)}
    except Exception as e:
        out["study_error"] = type(e).__name__
    return out


def READINGS() -> list[dict]:
    """Each coin's buy-zone status (+1 in zone), where it sits against its volume zones (+1 support / -1 resistance), days to the next
    sizeable ENA unlock (-1 inside the 3 days before), plus the meme season headline, from cached data only."""
    out = [{"tab": "zones", "key": f"zone_{r['ticker'].lower()}", "label": f"{r['ticker']} buy zone", "value": r["status"],
            "lean": 1 if r["status"] == "in zone" else 0}
           for r in (ENDPOINTS["zones"]() or {}).get("coins", []) if r["status"] in ("in zone", "above zone", "no zone")]
    out += [{"tab": "volume", "key": f"vz_{c['ticker'].lower()}", "label": f"{c['ticker']} volume zones", "value": c["read"], "lean": c["lean"]}
            for c in (ENDPOINTS["volume"]() or {}).get("coins", []) if c.get("status") == "ok"]
    for c in (ENDPOINTS["boards"]() or {}).get("coins", []):
        if c.get("status") != "ok":
            continue
        t, b, ft = c["ticker"], c["board"], c.get("fitted") or {}
        tab = t.lower() if t in CANDIDATES else "boards"
        out.append({"tab": tab, "key": f"board_{t.lower()}", "label": f"{t} signal board", "value": b["label"], "lean": 1 if "BUY" in b["label"] else -1 if "SELL" in b["label"] else 0,
                    "note": f"score {b['aggregate']:+.2f}, {b['sell']['words']}"})
        if ft.get("status") == "ok":
            out.append({"tab": "boards", "key": f"fitted_{t.lower()}", "label": f"{t} fitted board", "value": ft["label"], "lean": ft["lean"], "note": f"score {ft['score']:+.2f}"})
    out += [{"tab": "signals", "key": f"sig_{c['ticker'].lower()}", "label": f"{c['ticker']} final signal", "value": c["label"], "lean": c["lean"],
             "note": f"score {c['score']:+.2f}"} for c in (ENDPOINTS["signals"]() or {}).get("coins", []) if c.get("status") == "ok" and c.get("score") is not None]
    u = ENDPOINTS["unlocks"]() or {}
    nb = u.get("next_big") or u.get("next")
    if nb:
        out.append({"tab": "unlocks", "key": "ena_next_unlock", "label": "Days to the next ENA unlock of 1%+", "value": nb["days"], "lean": -1 if nb["days"] <= 3 else 0,
                    "note": f"{nb['amount_m']:,.0f}M ENA on {nb['date']}"})
    return out + M.READINGS()


def _cached_ep(name, fn, ttl=3600):
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"zones": _cached_ep("zones", _zones_now, 900), "boards": _cached_ep("boards", _boards_now, HL_TTL), "volume": _cached_ep("volume", _volume_now, HL_TTL), "signals": _cached_ep("signals", _signals_now, HL_TTL),
             **{t.lower(): _cached_ep(t.lower(), (lambda t: lambda: _coin_tab(t))(t)) for t in CANDIDATES},
             "unlocks": _cached_ep("unlocks", _unlocks_now, HL_TTL), "basket": M.ENDPOINTS["basket"], "season": M.ENDPOINTS["season"]}
BACKGROUND = M.BACKGROUND                       # the memecoin prices; the candidates come with btc_cycles' own fill
