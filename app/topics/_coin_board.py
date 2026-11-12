"""One altcoin's signal board, built the way the trading bot's BTC spot signal is (trading-system: src/hl/signal_board.py). Pure: no network.

Each gauge scores a day from +1 (in its buy zone, where past lows sat) to -1 (in its sell zone, near past tops), 0 in between, with a linear
ramp through each zone. The aggregate is the weighted average of the gauges that have data that day (valuation gauges count double, as on
the BTC board); the same five levels: >= +0.5 STRONG BUY, >= +0.2 BUY, <= -0.2 SELL, <= -0.5 STRONG SELL. Sell signal, two levels:
TAKE PROFIT when the aggregate is at a sell reading; SELL - TREND BREAK when the valuation was stretched in the last 4 months AND the price
is below its 20-week average AND the aggregate is not a buy. Zone thresholds are the BTC board's where a gauge exists for both (Mayer, RSI)
widened for altcoin volatility, and own (marked) elsewhere; all are hand-set, so the track record by zone is shown next to them.
Information only: the altcoin engine does not trade this.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

LEVELS = {"strong_buy": 0.5, "buy": 0.2, "sell": -0.2, "strong_sell": -0.5}
MIN_GAUGES = 4
TREND_DAYS = 140                    # the 20-week average
STRETCH_LOOKBACK = 120              # stretched at some point in the last 4 months
ZONES = ("STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL")


@dataclass(frozen=True)
class Gauge:
    key: str
    name: str
    group: str                      # valuation (counts double) / momentum / supply / market / volume zones
    buy_extreme: float | None
    buy_start: float | None
    sell_start: float | None
    sell_extreme: float | None
    source: str
    fmt: str = "{:.2f}"
    weight: float = 1.0
    direct: bool = False            # the input is already a score in -1..+1


GAUGES = [
    Gauge("mayer", "Price / 200-day average", "valuation", 0.6, 0.8, 1.6, 2.4, "BTC Mayer multiple zones (0.8 / 2.4) widened for altcoins: < 0.6 washed out, > 2.4 stretched", "{:.2f}x", 2.0),
    Gauge("p_fees_rel", "Price-to-fees vs its own 1-year median", "valuation", 0.5, 0.75, 1.5, 2.5, "own: market cap / annualised 30-day fees (DefiLlama), divided by its 1-year median", "{:.2f}x", 2.0),
    Gauge("p_tvl_rel", "Market cap / TVL vs its own 1-year median", "valuation", 0.5, 0.75, 1.5, 2.5, "own: market cap / TVL (DefiLlama), divided by its 1-year median", "{:.2f}x", 2.0),
    Gauge("from_high", "Price / 1-year high", "valuation", 0.3, 0.5, 0.9, 1.0, "own: 70%+ below the 1-year high = washed out, at the high = stretched", "{:.0%}", 2.0),
    Gauge("rsi", "RSI 14 (daily)", "momentum", 25.0, 35.0, 65.0, 80.0, "contrarian, as the BTC board's Fear and Greed: oversold = buy, overbought = sell", "{:.0f}"),
    Gauge("unlock_30d", "Supply unlocking in the next 30 days (% of circulating)", "supply", None, None, 2.0, 8.0, "own: sell side only; 2% starts, 8%+ fully; DefiLlama schedule or the hand-entered unlock file", "{:.1f}%"),
    Gauge("btc_mayer", "BTC price / its 200-day average", "market", 0.8, 1.0, 1.8, 2.4, "BTC Mayer multiple zones (Glassnode): altcoins bottom when BTC is washed out and top when it is stretched", "{:.2f}x"),
    Gauge("zone_pos", "Volume zone the price sits in", "volume zones", None, None, None, None, "the Volume zones tab, flipped: inside volume-backed resistance +1, inside support -1 (rank correlation +0.05 to +0.08 at 7-30 days)", "{:+.0f}", 1.0, True),
    Gauge("zone_score", "Twenty-signal final score (7 days)", "volume zones", None, None, None, None, "the Signals tab's weighted score, walk-forward weights", "{:+.2f}", 1.0, True),
    # ---- coin-specific: positioning, sector and narrative, product, supply (app/topics/_narrative.py)
    Gauge("funding_z", "Funding vs its last quarter", "positioning", -2.0, -1.0, 1.0, 2.0, "Hyperliquid hourly funding, 7-day mean against the 90-day mean in standard deviations; contrarian as on the BTC board: crowded shorts = buy, crowded longs = sell", "{:+.1f}"),
    Gauge("sector_rs", "Strength against its sector, 90 days", "narrative", None, None, None, None, "the coin's 90-day return minus its sector basket's (HYPE: AAVE UNI PENDLE; ENA: AAVE PENDLE ETHFI; SOL: ETH SUI AVAX; NEAR: TAO FET RENDER; memes: the other memes); +-30% = full score", "{:+.2f}", 1.0, True),
    Gauge("sector_heat", "Sector heat against BTC, 30 days", "narrative", None, None, None, None, "the sector basket's 30-day return minus BTC's; +-20% = full score", "{:+.2f}", 1.0, True),
    Gauge("alt_share", "Altcoin share of BTC, 30-day change", "narrative", None, None, None, None, "the ten coins' market caps over BTC's, 30-day change; +-15% = full score (CoinGecko)", "{:+.2f}", 1.0, True),
    Gauge("meme_season", "Meme season, 90 days", "narrative", None, None, None, None, "the six memecoins' market cap over BTC's, 90-day change; +-25% = full score", "{:+.2f}", 1.0, True),
    Gauge("stable_growth", "Stablecoin supply growth, 30 days", "product", None, None, None, None, "ENA: USDe supply; SOL, NEAR, HYPE: stablecoins on the chain (DefiLlama); +-15% = full score", "{:+.2f}", 1.0, True),
    Gauge("fees_momentum", "Fees momentum, 30 days", "product", None, None, None, None, "30-day fees against the previous 30 days (DefiLlama); +-50% = full score", "{:+.2f}", 1.0, True),
    Gauge("dex_momentum", "Chain DEX volume momentum, 30 days", "product", None, None, None, None, "the chain's DEX volume, last 30 days against the 30 before (DefiLlama; Solana for SOL BONK WIF TRUMP, Ethereum for SHIB PEPE); +-50% = full score", "{:+.2f}", 1.0, True),
    Gauge("basis_yield", "Basis yield (BTC + ETH funding, annualised)", "product", None, None, None, None, "ENA's product earns perp funding: the 30-day mean of BTC and ETH funding on Hyperliquid, annualised; 5% = 0, 20% = +1", "{:+.2f}", 1.0, True),
    Gauge("post_unlock", "Relief after an unlock", "supply", None, None, None, None, "+1 for the 10 days after an unlock of 1%+ of circulating (the hand-entered file or DefiLlama's curve): the supply has landed", "{:+.0f}", 1.0, True),
]
NAMES = {g.key: g for g in GAUGES}
SELL_WORDS = {2: "SELL - TREND BREAK", 1: "TAKE PROFIT (early warning)", 0: "no sell signal"}


def score(v, g: Gauge) -> float:
    if v is None or not np.isfinite(v):
        return np.nan
    if g.direct:
        return float(max(-1.0, min(1.0, v)))
    if g.buy_extreme is not None and g.buy_start is not None:
        if v <= g.buy_extreme:
            return 1.0
        if v < g.buy_start:
            return (g.buy_start - v) / (g.buy_start - g.buy_extreme)
    if g.sell_start is not None and g.sell_extreme is not None:
        if v >= g.sell_extreme:
            return -1.0
        if v > g.sell_start:
            return -(v - g.sell_start) / (g.sell_extreme - g.sell_start)
    return 0.0


def label(agg) -> str:
    if agg is None or not np.isfinite(agg):
        return "no data"
    L = LEVELS
    return "STRONG BUY" if agg >= L["strong_buy"] else "BUY" if agg >= L["buy"] else "STRONG SELL" if agg <= L["strong_sell"] else "SELL" if agg <= L["sell"] else "NEUTRAL"


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


# ------------------------------------------------------------------ inputs: one column per gauge, daily
def inputs(price: pd.Series, btc: pd.Series | None = None, market_cap: pd.Series | None = None, fees_30d: pd.Series | None = None, tvl: pd.Series | None = None,
           unlocked: pd.Series | None = None, circulating: float | pd.Series | None = None, zone_pos: pd.Series | None = None, zone_score: pd.Series | None = None,
           extra: dict | None = None) -> pd.DataFrame:
    """Daily gauge values on the price's index. price: daily closes. btc: BTC daily closes (any index). market_cap, fees_30d (rolling 30-day fees),
    tvl: daily series. unlocked: cumulative unlocked tokens over time (past and scheduled). circulating: tokens now, or a series.
    zone_pos / zone_score: already scores in -1..+1. Everything is forward-filled onto the price index and uses nothing later than the day."""
    idx = price.index
    d = pd.DataFrame(index=idx)
    d["price"] = price.astype(float)
    ma200 = price.rolling(200, min_periods=120).mean()
    d["mayer"] = price / ma200
    d["from_high"] = price / price.rolling(365, min_periods=120).max()
    d["rsi"] = rsi(price)
    d["ma20w"] = price.rolling(TREND_DAYS, min_periods=100).mean()
    if btc is not None and len(btc) > 120:
        b = btc.astype(float).sort_index()
        b = b[~b.index.duplicated()]
        d["btc_mayer"] = (b / b.rolling(200, min_periods=120).mean()).reindex(idx, method="ffill")
    if market_cap is not None and len(market_cap):
        mc = market_cap.astype(float).sort_index().reindex(idx, method="ffill")
        if fees_30d is not None and len(fees_30d) > 30:
            f = fees_30d.astype(float).sort_index().reindex(idx, method="ffill")
            pf = (mc / (f * 365 / 30)).replace([np.inf, -np.inf], np.nan)
            d["p_fees_rel"] = pf / pf.rolling(365, min_periods=90).median()
        if tvl is not None and len(tvl) > 30:
            t = tvl.astype(float).sort_index().reindex(idx, method="ffill")
            pt = (mc / t).replace([np.inf, -np.inf], np.nan)
            d["p_tvl_rel"] = pt / pt.rolling(365, min_periods=90).median()
    if unlocked is not None and len(unlocked) > 2 and circulating is not None:
        u = unlocked.astype(float).sort_index()
        u = u[~u.index.duplicated()]
        full = pd.date_range(min(u.index[0], idx[0]), max(u.index[-1], idx[-1] + pd.Timedelta(days=31)), freq="D")
        ui = u.reindex(full).interpolate(method="time").ffill().bfill()
        ahead = ui.shift(-30) - ui                                           # tokens unlocking over the next 30 days, known in advance
        circ = circulating.astype(float).reindex(idx, method="ffill") if isinstance(circulating, pd.Series) else float(circulating)
        d["unlock_30d"] = (ahead.reindex(idx) / circ * 100).clip(lower=0)
    if zone_pos is not None and len(zone_pos):
        d["zone_pos"] = zone_pos.astype(float).reindex(idx).fillna(0.0)
    if zone_score is not None and len(zone_score):
        d["zone_score"] = zone_score.astype(float).reindex(idx)              # NaN before the first weight fit: the gauge is simply absent then
    for k, s in (extra or {}).items():                                       # the coin-specific series (_narrative.py), already on this index
        if k in NAMES and s is not None and len(s):
            d[k] = s.astype(float).reindex(idx)
    return d


# ------------------------------------------------------------------ the board over time
def board(d: pd.DataFrame) -> pd.DataFrame:
    sc = pd.DataFrame(index=d.index)
    for g in GAUGES:
        if g.key in d:
            sc[g.key] = [score(v, g) for v in d[g.key].to_numpy()]
    vals = sc.copy()
    w = pd.Series({k: NAMES[k].weight for k in vals.columns})
    sc["n"] = vals.notna().sum(axis=1)
    sc["weight_sum"] = vals.notna().mul(w, axis=1).sum(axis=1)
    sc["aggregate"] = (vals.fillna(0).mul(w, axis=1).sum(axis=1) / sc["weight_sum"].replace(0, np.nan)).where(sc["n"] >= MIN_GAUGES)
    sc["n_buy"] = (vals >= LEVELS["strong_buy"]).sum(axis=1)
    sc["n_sell"] = (vals <= -0.5).sum(axis=1)
    return sc


def sell_checks(d: pd.DataFrame, sc: pd.DataFrame) -> pd.DataFrame:
    """Per day: stretched (a valuation gauge was fully in its sell zone in the last 4 months), trend break (price below its 20-week average)."""
    val_keys = [g.key for g in GAUGES if g.group == "valuation" and g.key in sc]
    hot = (sc[val_keys] <= -0.999).any(axis=1) if val_keys else pd.Series(False, index=d.index)
    ch = pd.DataFrame(index=d.index)
    ch["stretched"] = hot.rolling(STRETCH_LOOKBACK, min_periods=1).max().astype(bool)
    ch["trend_break"] = (d["price"] < d["ma20w"]) & d["ma20w"].notna()
    ch["ma20w"] = d["ma20w"]
    return ch


def sell_state(sc: pd.DataFrame, ch: pd.DataFrame) -> pd.Series:
    agg = sc["aggregate"]
    top = ch["stretched"] & ch["trend_break"] & (agg <= 0) & agg.notna()
    tp = (agg <= LEVELS["sell"]) & agg.notna()
    return pd.Series(np.where(top, 2, np.where(tp, 1, 0)), index=sc.index)


def zone_words(sv: float) -> str:
    if sv >= 0.999:
        return "fully in its buy zone"
    if sv > 0:
        return f"{sv:.0%} of the way into its buy zone"
    if sv <= -0.999:
        return "fully in its sell zone"
    if sv < 0:
        return f"{-sv:.0%} of the way into its sell zone"
    return "neutral"


def action_for(agg: float, st: int) -> dict:
    if st == 2:
        return {"action": "SELL", "words": "SELL - trend break after a stretched valuation (information only)"}
    if st == 1:
        return {"action": "SELL", "words": "TAKE PROFIT - the score is at a sell reading; historically early (information only)"}
    if agg == agg and agg >= LEVELS["strong_buy"]:
        return {"action": "BUY", "words": "BUY - the gauges sit where past lows sat (information only)"}
    return {"action": "HOLD", "words": "HOLD - no buy or sell reading today"}


def latest(d: pd.DataFrame, sc: pd.DataFrame) -> dict:
    agg_s = sc["aggregate"].dropna()
    if agg_s.empty:
        return {"status": "no data", "why": f"fewer than {MIN_GAUGES} gauges have data"}
    day = agg_s.index[-1]
    rows = []
    for g in GAUGES:
        if g.key in sc and np.isfinite(sc.loc[day, g.key]):
            rows.append({"key": g.key, "name": g.name, "group": g.group, "value": g.fmt.format(d.loc[day, g.key]), "raw": float(d.loc[day, g.key]), "score": float(sc.loc[day, g.key]),
                         "zone": zone_words(float(sc.loc[day, g.key])), "weight": g.weight, "source": g.source})
    agg = float(agg_s.loc[day])
    ch = sell_checks(d, sc)
    st = int(sell_state(sc, ch).loc[day])
    c = ch.loc[day]
    sell = {"state": st, "words": SELL_WORDS[st], "take_profit": agg <= LEVELS["sell"], "checks": [
        [bool(c["stretched"]), f"Valuation stretched in the last 4 months (a valuation gauge fully in its sell zone): {'yes' if c['stretched'] else 'no'}"],
        [bool(c["trend_break"]), f"Trend break (price below its 20-week average{(' of ' + _px(c['ma20w'])) if np.isfinite(c['ma20w']) else ''}): {'yes' if c['trend_break'] else 'no'}"],
        [agg <= 0, f"Score not a buy ({agg:+.2f}): {'yes' if agg <= 0 else 'no'}"]]}
    i = agg_s.index.get_loc(day)
    return {"status": "ok", "day": str(day.date()), "price": float(d.loc[day, "price"]), "aggregate": agg, "label": label(agg), "rows": rows, "n": int(sc.loc[day, "n"]),
            "n_buy": int(sc.loc[day, "n_buy"]), "n_sell": int(sc.loc[day, "n_sell"]), "weight_sum": float(sc.loc[day, "weight_sum"]),
            "prev": float(agg_s.iloc[i - 1]) if i > 0 else None, "week": float(agg_s.iloc[i - 7]) if i >= 7 else None, "sell": sell, "levels": LEVELS, **action_for(agg, st)}


def _px(v: float) -> str:
    return f"${v:,.0f}" if v >= 1000 else f"${v:,.2f}" if v >= 1 else f"${v:.4f}"


def explain(d: pd.DataFrame, sc: pd.DataFrame) -> list[str]:
    agg_s = sc["aggregate"].dropna()
    if agg_s.empty:
        return []
    day = agg_s.index[-1]
    keys = [g.key for g in GAUGES if g.key in sc and np.isfinite(sc.loc[day, g.key])]
    pos = sorted([k for k in keys if sc.loc[day, k] > 0], key=lambda k: -sc.loc[day, k])
    neg = sorted([k for k in keys if sc.loc[day, k] < 0], key=lambda k: sc.loc[day, k])
    val = lambda k: NAMES[k].fmt.format(d.loc[day, k])
    lines = []
    if pos:
        lines.append("Pushing towards BUY: " + "; ".join(f"{NAMES[k].name} {val(k)} ({zone_words(sc.loc[day, k])}, {sc.loc[day, k]:+.2f})" for k in pos[:4]) + ".")
    if neg:
        lines.append("Pushing towards SELL: " + "; ".join(f"{NAMES[k].name} {val(k)} ({zone_words(sc.loc[day, k])}, {sc.loc[day, k]:+.2f})" for k in neg[:4]) + ".")
    neutral = len(keys) - len(pos) - len(neg)
    lines.append(f"{neutral} of {len(keys)} gauges are neutral (between their zones), which pulls the average towards 0.")
    i = sc.index.get_loc(day)
    if i > 0:
        moves = sorted(((k, float(sc.loc[day, k] - sc[k].iloc[i - 1])) for k in keys if np.isfinite(sc[k].iloc[i - 1])), key=lambda x: -abs(x[1]))
        moves = [m for m in moves if abs(m[1]) >= 0.02][:3]
        wsum = float(sc.loc[day, "weight_sum"])
        if moves:
            k0 = moves[0][0]
            lines.append("Since the day before: " + "; ".join(f"{NAMES[k].name} {m:+.2f}" for k, m in moves)
                         + f" ({NAMES[k0].name} counts {NAMES[k0].weight:g}/{wsum:g} of the score, so its move shifted the score by {abs(moves[0][1]) * NAMES[k0].weight / wsum:.3f}).")
        else:
            lines.append("Since the day before: no gauge moved by more than 0.02.")
    score_ = float(agg_s.loc[day])
    levels = {0.5: "STRONG BUY", 0.2: "BUY", -0.2: "SELL (take profit)", -0.5: "STRONG SELL"}
    up = min([l for l in levels if l > score_], default=None)
    down = max([l for l in levels if l < score_], default=None)
    wsum = float(sc.loc[day, "weight_sum"])
    dist = [f"{levels[l]} is {abs(l - score_):.2f} {'up' if l > score_ else 'down'} (about {abs(l - score_) * wsum:.1f} gauge moves fully into {'buy' if l > score_ else 'sell'} zones; valuation gauges count double)"
            for l in (up, down) if l is not None]
    if dist:
        lines.append("Distance: " + "; ".join(dist) + ".")
    last12 = agg_s.loc[day - pd.Timedelta(days=365):day]
    st12 = sell_state(sc, sell_checks(d, sc)).loc[last12.index]
    lines.append(f"Last 12 months: score between {last12.min():+.2f} and {last12.max():+.2f}; {int((last12 >= 0.5).sum())} strong-buy days, {int((st12 == 1).sum())} take-profit days, {int((st12 == 2).sum())} trend-break sell days.")
    return lines


def flips(d: pd.DataFrame, sc: pd.DataFrame) -> list[dict]:
    """What price would move each price-based gauge to the edge of its buy zone and of its sell zone, from today's averages and high."""
    agg_s = sc["aggregate"].dropna()
    if agg_s.empty:
        return []
    day = agg_s.index[-1]
    px = float(d.loc[day, "price"])
    out = []
    ma = d.loc[day, "price"] / d.loc[day, "mayer"] if "mayer" in d and np.isfinite(d.loc[day, "mayer"]) else np.nan
    if np.isfinite(ma):
        g = NAMES["mayer"]
        out.append({"gauge": g.name, "buy_at": g.buy_start * ma, "buy_full_at": g.buy_extreme * ma, "sell_at": g.sell_start * ma, "sell_full_at": g.sell_extreme * ma, "price": px})
    hi = d.loc[day, "price"] / d.loc[day, "from_high"] if "from_high" in d and np.isfinite(d.loc[day, "from_high"]) else np.nan
    if np.isfinite(hi):
        g = NAMES["from_high"]
        out.append({"gauge": g.name, "buy_at": g.buy_start * hi, "buy_full_at": g.buy_extreme * hi, "sell_at": g.sell_start * hi, "sell_full_at": g.sell_extreme * hi, "price": px})
    for r in out:
        for k in ("buy_at", "buy_full_at", "sell_at", "sell_full_at"):
            r[k + "_pct"] = r[k] / px - 1
    if "ma20w" in d and np.isfinite(d.loc[day, "ma20w"]):
        out.append({"gauge": "20-week average (trend break line)", "level": float(d.loc[day, "ma20w"]), "level_pct": float(d.loc[day, "ma20w"]) / px - 1, "price": px})
    return out


def zone_returns(d: pd.DataFrame, sc: pd.DataFrame, horizons=(30, 90, 180)) -> list[dict]:
    """The coin's median move over the next N days, grouped by the aggregate's zone the day before (information, not a strategy)."""
    px = d["price"]
    zone = sc["aggregate"].shift(1).map(lambda a: label(a) if a == a else None)
    rows = []
    for z in ZONES:
        m = zone == z
        r = {"zone": z, "days": int(m.sum())}
        for h in horizons:
            f = (px.shift(-h) / px - 1)[m].dropna()
            r[f"{h}d"] = float(f.median()) if len(f) else None
            r[f"{h}d_up"] = float((f > 0).mean()) if len(f) else None
        rows.append(r)
    allr = {"zone": "ALL DAYS", "days": int(sc["aggregate"].notna().sum())}
    for h in horizons:
        f = (px.shift(-h) / px - 1)[sc["aggregate"].notna()].dropna()
        allr[f"{h}d"], allr[f"{h}d_up"] = (float(f.median()), float((f > 0).mean())) if len(f) else (None, None)
    rows.append(allr)
    return rows


def payload(d: pd.DataFrame, years: float = 2.0) -> dict:
    """Everything the tab needs: today's board, the explanation, flips, the record by zone, and the score / price / sell-state series."""
    sc = board(d)
    out = latest(d, sc)
    if out.get("status") != "ok":
        return out
    st = sell_state(sc, sell_checks(d, sc))
    since = d.index[-1] - pd.Timedelta(days=int(years * 365))
    ser = [[int(t.timestamp()), None if not np.isfinite(sc.loc[t, "aggregate"]) else round(float(sc.loc[t, "aggregate"]), 3), round(float(d.loc[t, "price"]), 8), int(st.loc[t])]
           for t in d.index if t >= since]
    out |= {"explain": explain(d, sc), "flips": flips(d, sc), "record": zone_returns(d, sc), "series": ser, "history_from": str(sc["aggregate"].dropna().index[0].date()),
            "gauges_available": [g.key for g in GAUGES if g.key in d and d[g.key].notna().any()], "gauges_missing": [g.key for g in GAUGES if g.key not in d or not d[g.key].notna().any()],
            "sell_days_12m": int((st.loc[d.index[-1] - pd.Timedelta(days=365):] > 0).sum())}
    return out


# ------------------------------------------------------------------ the fitted board: the same gauges, signs and weights learned from their record
FIT_HORIZON = 30                 # days ahead the gauges are judged on (the record tables start at 30 days)
FIT_MIN_T = 2.0                  # a gauge earns weight when its rank correlation is this many standard errors from zero (either sign),
                                 # counting one observation per horizon on which it was active, not one per coin-day
FIT_MIN_ACTIVE = 100             # ... on at least this many coin-days where the gauge was not neutral
FIT_MAX_WEIGHT = 0.4             # no gauge above this share of the final score (by absolute weight)
FIT_REFIT_DAYS = 30
FIT_MIN_TRAIN = 180


def gauge_record(scores: pd.DataFrame, fwd: pd.Series, h: int = FIT_HORIZON) -> list[dict]:
    """Per gauge: rank correlation of its zone score with the forward return (sign kept: negative means the zone is backwards),
    the t-stat, the average forward return after buy-zone and sell-zone readings, and the hit rate of its sign."""
    out = []
    f = fwd.reindex(scores.index)
    for g in GAUGES:
        if g.key not in scores:
            continue
        s = scores[g.key]
        m = f.notna() & s.notna() & (s != 0)
        n = int(m.sum())
        row = {"key": g.key, "name": g.name, "group": g.group, "days_active": n}
        if n >= 30 and s[m].nunique() > 1:
            ic = float(s[m].rank().corr(f[m].rank()))
            dates = int(pd.Index(scores.index[m.to_numpy()]).nunique())            # t counts coin-days; t_adj one observation per horizon (windows overlap, coins move together)
            row |= {"ic": ic, "t": ic * np.sqrt(n), "dates": dates, "t_adj": ic * np.sqrt(max(dates / h, 1.0)), "after_buy": float(f[m & (s > 0)].mean()) if (m & (s > 0)).any() else None,
                    "after_sell": float(f[m & (s < 0)].mean()) if (m & (s < 0)).any() else None, "hit_rate": float((np.sign(s[m]) == np.sign(f[m])).mean())}
        else:
            row |= {"ic": None, "t": None, "dates": None, "t_adj": None, "after_buy": None, "after_sell": None, "hit_rate": None}
        out.append(row)
    return out


def fitted_weights(scores: pd.DataFrame, fwd: pd.Series, h: int = FIT_HORIZON) -> tuple[dict, str]:
    """Signed weights: a gauge's rank correlation with the forward return (so a backwards zone gets a negative weight), kept when at least
    FIT_MIN_T standard errors from zero on FIT_MIN_ACTIVE+ active coin-days, scaled so the absolute weights sum to 1 with none above
    FIT_MAX_WEIGHT; empty (no reading) when nothing qualifies."""
    rec = gauge_record(scores, fwd, h)
    w = {r["key"]: r["ic"] for r in rec if r["ic"] is not None and r["t_adj"] is not None and abs(r["t_adj"]) >= FIT_MIN_T and r["days_active"] >= FIT_MIN_ACTIVE}
    w = {k: v for k, v in w.items() if v != 0}
    if not w:
        return {}, "no gauge cleared the bar"
    for _ in range(len(w)):
        tot = sum(abs(v) for v in w.values())
        w = {k: v / tot for k, v in w.items()}
        over = {k for k, v in w.items() if abs(v) > FIT_MAX_WEIGHT + 1e-12}
        if not over or len(over) == len(w):
            break
        excess = sum(abs(w[k]) - FIT_MAX_WEIGHT for k in over)
        free = sum(abs(v) for k, v in w.items() if k not in over)
        w = {k: (np.sign(v) * FIT_MAX_WEIGHT if k in over else v + np.sign(v) * excess * abs(v) / free) for k, v in w.items()}
    flipped = sorted(k for k, v in w.items() if v < 0)
    return w, f"{len(w)} gauges by rank correlation" + (f", {len(flipped)} with the sign reversed ({', '.join(NAMES[k].name for k in flipped)})" if flipped else "")


def fitted_composite(scores: pd.DataFrame, w: dict) -> pd.Series:
    if not w:
        return pd.Series(np.nan, index=scores.index)
    cols = [k for k in w if k in scores]
    return (scores[cols].fillna(0).mul(pd.Series({k: w[k] for k in cols}), axis=1).sum(axis=1)).clip(-1, 1).where(scores[cols].notna().any(axis=1))


def fitted_walk_forward(per_coin: dict[str, tuple[pd.DataFrame, pd.Series]], h: int = FIT_HORIZON, refit: int = FIT_REFIT_DAYS, min_train: int = FIT_MIN_TRAIN) -> dict:
    """per_coin: {coin: (gauge zone scores frame, close)}. Weights re-fitted every `refit` days on every coin's rows whose forward return was
    known at the fit date, applied until the next fit; today's weights fitted on everything known."""
    keys = [g.key for g in GAUGES]
    pooled = pd.concat([S.reindex(columns=keys).assign(_fwd=(c.shift(-h) / c - 1).reindex(S.index), _coin=k) for k, (S, c) in per_coin.items()]).sort_index()
    dates = pooled.index.unique().sort_values()
    comp = {k: pd.Series(np.nan, index=S.index) for k, (S, _) in per_coin.items()}
    if len(dates) < min_train + h + 1:
        return {"composite": comp, "fits": [], "weights_now": {}, "how_now": "not enough history"}
    fit_dates = dates[min_train::refit]
    fits = []
    for j, t in enumerate(fit_dates):
        train = pooled[pooled.index < t - pd.Timedelta(days=h)]
        w, how = fitted_weights(train[keys], train["_fwd"], h)
        until = fit_dates[j + 1] if j + 1 < len(fit_dates) else dates[-1] + pd.Timedelta(days=1)
        fits.append({"date": str(t.date()), "until": str((until - pd.Timedelta(days=1)).date()), "weights": w, "how": how, "train_rows": int(len(train))})
        for k, (S, _) in per_coin.items():
            m = (S.index >= t) & (S.index < until)
            if m.any() and w:
                comp[k][m] = fitted_composite(S[m].reindex(columns=keys), w).to_numpy()
    known = pooled[pooled["_fwd"].notna()]
    w_now, how_now = fitted_weights(known[keys], known["_fwd"], h)
    return {"composite": comp, "fits": fits, "weights_now": w_now, "how_now": how_now, "train_rows_now": int(len(known)), "record": gauge_record(known[keys], known["_fwd"], h)}


def zone_returns_of(score_series: pd.Series, px: pd.Series, horizons=(30, 90, 180)) -> list[dict]:
    """The record-by-zone table for any score series (the fitted board's composite, for instance)."""
    zone = score_series.shift(1).map(lambda a: label(a) if a == a else None)
    rows = []
    for z in ZONES:
        m = zone == z
        r = {"zone": z, "days": int(m.sum())}
        for h in horizons:
            f = (px.shift(-h) / px - 1)[m].dropna()
            r[f"{h}d"] = float(f.median()) if len(f) else None
            r[f"{h}d_up"] = float((f > 0).mean()) if len(f) else None
        rows.append(r)
    allr = {"zone": "ALL DAYS", "days": int(score_series.notna().sum())}
    for h in horizons:
        f = (px.shift(-h) / px - 1)[score_series.notna()].dropna()
        allr[f"{h}d"], allr[f"{h}d_up"] = (float(f.median()), float((f > 0).mean())) if len(f) else (None, None)
    return rows + [allr]


def fitted_backtest(comp: pd.Series, px: pd.Series, enter: float = LEVELS["buy"], cost: float = 0.00095, long_short: bool = True, h: int = FIT_HORIZON) -> dict:
    """Trade the fitted score close to close: long at or above `enter`, short at or below -enter (or flat), the next day's move, costs on every change;
    a short losing over 100% in a day ends the account at zero."""
    x = comp.dropna()
    if len(x) < 60:
        return {"days": int(len(x))}
    p = px.reindex(x.index)
    pos = pd.Series(np.where(x >= enter, 1.0, np.where(x <= -enter, -1.0 if long_short else 0.0, 0.0)), index=x.index)
    r = p.pct_change().shift(-1)
    turn = pos.diff().abs().fillna(pos.abs())
    strat = (pos * r - turn * cost).dropna().clip(lower=-1.0)
    eq = (1 + strat).cumprod()
    hold = p / p.iloc[0]
    days = len(strat)
    direction = np.sign(x.where(x.abs() >= enter)).dropna()
    hit = float((direction == np.sign((p.shift(-h) / p - 1).reindex(direction.index))).mean()) if len(direction) else None
    return {"days": days, "from": str(x.index[0].date()), "to": str(x.index[-1].date()), "total": float(eq.iloc[-1] - 1), "hold": float(hold.iloc[-1] - 1),
            "a_year": float(eq.iloc[-1] ** (365 / days) - 1) if eq.iloc[-1] > 0 else -1.0, "hold_a_year": float(hold.iloc[-1] ** (365 / days) - 1),
            "sharpe": float(strat.mean() / strat.std() * np.sqrt(365)) if strat.std() > 0 else None, "worst_drop": float((eq / eq.cummax() - 1).min()),
            "hold_worst_drop": float((hold / hold.cummax() - 1).min()), "time_long": float((pos > 0).mean()), "time_short": float((pos < 0).mean()), "changes": int((turn > 0).sum()),
            "hit_rate": hit, "hit_horizon": h, "readings": int(len(direction)),
            "equity": [[int(t.timestamp()), round(float(v), 5)] for t, v in eq.items()], "hold_curve": [[int(t.timestamp()), round(float(v), 5)] for t, v in hold.reindex(eq.index).items()]}


def fitted_today(scores: pd.DataFrame, d: pd.DataFrame, w: dict) -> dict:
    """Today's fitted reading: the score, label, and each gauge's signed weight and push."""
    if not w or scores.empty:
        return {"status": "no reading"}
    day = scores.index[-1]
    comp = fitted_composite(scores.iloc[[-1]].reindex(columns=[g.key for g in GAUGES]), w).iloc[0]
    if not np.isfinite(comp):
        return {"status": "no reading"}
    rows = []
    for g in GAUGES:
        if g.key in scores and np.isfinite(scores.loc[day, g.key]):
            sc = float(scores.loc[day, g.key]); wt = float(w.get(g.key, 0.0))
            rows.append({"key": g.key, "name": g.name, "value": g.fmt.format(d.loc[day, g.key]) if g.key in d else "", "zone_score": sc, "weight": wt, "push": sc * wt,
                         "flipped": wt < 0})
    rows.sort(key=lambda r: -abs(r["push"]))
    return {"status": "ok", "score": float(comp), "label": label(float(comp)), "lean": 1 if comp >= LEVELS["buy"] else -1 if comp <= LEVELS["sell"] else 0, "rows": rows,
            "weights": {k: float(v) for k, v in w.items()}}
