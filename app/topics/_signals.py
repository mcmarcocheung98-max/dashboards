"""Twenty daily signals built on the volume-zone work, their backtest, and one weighted final signal per coin. Pure: no network.

signals(d, btc, zones, unlocks): a frame with one column per signal, each day a score from -1 (sell) to +1 (buy), using only that day's and
earlier candles. evaluate(): what each signal was worth on its own (rank correlation with the next 7 days' return, average return after a
+1 vs a -1, hit rate). walk_forward(): weights learned on the pooled past of every coin and re-fitted every 30 days, the composite score
(sum of weight x signal, clipped to +-1), and a close-to-close backtest of trading it (long above +0.2, short below -0.2, costs on every
change), judged only on days after each fit. Same conventions as the trading bot's studies (trading-system repo).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import _volume_zones as VZ

HORIZON = 7                       # days ahead the signals are judged and weighted on
COST_PER_SIDE = 0.00045 + 0.0005  # Hyperliquid perp taker fee + slippage allowance
ENTER = 0.2                       # composite needed to be long (above) or short (below the negative)
REFIT_DAYS = 30
MIN_TRAIN_DAYS = 180
MIN_T = 1.5                       # a signal earns weight only if its rank correlation is this many standard errors from zero

# key: (label, family, what +1 means)
SIGNALS = {
    "in_zone": ("Inside a zone", "volume zones", "close inside a live support zone (+1) or resistance zone (-1)"),
    "near_zone": ("Near a zone", "volume zones", "within 3% above live support (+1, closer = stronger) or below live resistance (-1)"),
    "retest": ("Zone retest", "volume zones", "first day back into live support from above (+1) or into resistance from below (-1)"),
    "dry_retest": ("Retest on thin volume", "volume zones", "a retest on under 0.7x the usual volume: the sellers (buyers) are gone"),
    "zone_balance": ("Zones below minus above", "volume zones", "live support zones within 10% below minus resistance zones within 10% above, clipped"),
    "zone_break": ("Break through a zone on volume", "volume zones", "a big buy day closing up through live resistance (+1) or a big sell day down through support (-1)"),
    "big_day": ("Big-volume day", "volume", "a big buy day today (+1) or a big sell day (-1)"),
    "big_balance_30d": ("Big days, 30-day balance", "volume", "big buy days minus big sell days over 30 days, 3 or more = full score"),
    "failed_break": ("Failed break", "volume zones", "closed below support within 3 days and back above it now (+1); the mirror at resistance (-1)"),
    "absorption": ("Absorption wick", "volume", "a big-volume day closing in the top quarter of its range after a lower low (+1); the mirror (-1)"),
    "own_volume": ("Coin-specific volume", "volume", "a big day on this coin while BTC had an ordinary day (+1 buy / -1 sell); market-wide days score 0"),
    "vs_btc_day": ("Strength against BTC on volume", "volume", "a big buy day while BTC fell (+1) or a big sell day while BTC rose (-1)"),
    "trend": ("Trend", "price", "close above the 50-day average and the 50 above the 200 (+1); below both (-1)"),
    "rsi": ("RSI 14", "price", "oversold under 30 (+1) to overbought over 70 (-1), scaled between"),
    "momentum_30d": ("30-day momentum", "price", "the 30-day return, +-20% = full score"),
    "range_1y": ("Place in the 1-year range", "price", "within 10% of the 1-year low (+1) to within 10% of the 1-year high (-1)"),
    "volume_trend": ("Volume trend with price", "volume", "20-day volume 30% over the 60-day with price up over 20 days (+1), with price down (-1)"),
    "btc_trend": ("BTC trend", "market", "BTC above its 200-day average (+1) or below (-1)"),
    "unlock_window": ("Unlock window", "supply", "1-7 days after an unlock of 1%+ of circulating (+1); the 3 days before one (-1); without a schedule, the 26th-6th month-turn (-1)"),
    "value_vs_ma": ("Price against its 200-day average", "price", "20% or more under the 200-day average (+1) to 50% or more over it (-1)"),
}
LABELS = [(0.5, "strong buy"), (ENTER, "lean buy"), (-ENTER, "neutral"), (-0.5, "lean sell"), (-9, "strong sell")]


def label(score: float | None) -> str:
    if score is None or not np.isfinite(score):
        return "no reading"
    for lo, name in LABELS:
        if score >= lo:
            return name
    return "strong sell"


def _clip(x, index=None) -> pd.Series:
    return pd.Series(np.asarray(x, float), index=index).clip(-1, 1).fillna(0.0)


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def signals(d: pd.DataFrame, btc: pd.DataFrame | None = None, zs: list | None = None, unlocks: pd.DataFrame | None = None, mult: float = 3.0) -> pd.DataFrame:
    """One row per day of `d`, one column per signal in SIGNALS, scores in [-1, 1]. btc: BTC daily candles (any index; aligned by day)."""
    zs = VZ.zones(d, "", mult=mult) if zs is None else zs
    b = VZ.big_days(d, mult=mult)
    v = VZ.usd_volume(d)
    c, o, h, l = d.close, d.open, d.high, d.low
    idx = d.index
    n = len(d)
    a = VZ.atr(d)
    S = pd.DataFrame(index=idx)
    # ---- zone geometry per day
    in_zone, near, balance, retest, dry, zbreak, failed = (np.zeros(n) for _ in range(7))
    vmed = v.rolling(60, min_periods=20).median().shift(1)
    recent_break = {}                                                   # zone id -> day index of its break, for failed breaks
    for i in range(n):
        t = idx[i]
        px = c.iloc[i]
        live = [z for z in zs if z.born < t and (z.died is None or z.died >= t)]
        inside = [z for z in live if z.lo <= px <= z.hi]
        if inside:
            z = max(inside, key=lambda z: z.ratio)
            in_zone[i] = 1 if z.kind == "buy" else -1
        sup = [z for z in live if z.kind == "buy" and z.hi < px]
        res = [z for z in live if z.kind == "sell" and z.lo > px]
        if sup:
            gap = px / max(z.hi for z in sup) - 1
            if gap <= 0.03:
                near[i] = 1 - gap / 0.03
        if res and near[i] == 0:
            gap = min(z.lo for z in res) / px - 1
            if gap <= 0.03:
                near[i] = -(1 - gap / 0.03)
        balance[i] = max(-1, min(1, (sum(1 for z in sup if px / z.hi - 1 <= 0.10) - sum(1 for z in res if z.lo / px - 1 <= 0.10)) / 2))
        for z in live:
            if t in z.retests and z.retests[0] == t:
                retest[i] = 1 if z.kind == "buy" else -1
                if np.isfinite(vmed.iloc[i]) and v.iloc[i] < 0.7 * vmed.iloc[i]:
                    dry[i] = retest[i]
        if b.big.iloc[i] and i > 0:
            if b.kind.iloc[i] == "buy" and any(z.kind == "sell" and c.iloc[i - 1] <= z.hi and px > z.hi for z in live):
                zbreak[i] = 1
            elif b.kind.iloc[i] == "sell" and any(z.kind == "buy" and c.iloc[i - 1] >= z.lo and px < z.lo for z in live):
                zbreak[i] = -1
        for z in zs:                                                     # failed breaks: a zone broken within the last 3 days, price back on the right side
            if z.died == t and z.why == "broken":
                recent_break[id(z)] = (i, z)
        for k, (j, z) in list(recent_break.items()):
            if i - j > 3:
                del recent_break[k]
            elif i > j and ((z.kind == "buy" and px >= z.lo) or (z.kind == "sell" and px <= z.hi)):
                failed[i] = 1 if z.kind == "buy" else -1
                del recent_break[k]
    S["in_zone"], S["near_zone"], S["retest"], S["dry_retest"], S["zone_balance"], S["zone_break"], S["failed_break"] = in_zone, near, retest, dry, balance, zbreak, failed
    # ---- volume signals
    sign = np.where(b.kind == "buy", 1.0, np.where(b.kind == "sell", -1.0, 0.0))
    S["big_day"] = sign
    S["big_balance_30d"] = _clip(pd.Series(sign, index=idx).rolling(30, min_periods=1).sum() / 3, idx).to_numpy()
    rng_pos = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5)
    lower_low, higher_high = l < l.shift(1), h > h.shift(1)
    S["absorption"] = np.where(b.big & (rng_pos >= 0.75) & lower_low, 1.0, np.where(b.big & (rng_pos <= 0.25) & higher_high, -1.0, 0.0))
    if btc is not None and len(btc) > 70:
        bb = VZ.big_days(btc, mult=2.0).reindex(idx)
        btc_c = btc.close.reindex(idx).ffill()
        btc_up = (btc_c.pct_change() > 0).reindex(idx).fillna(False)
        S["own_volume"] = np.where(b.big & ~(bb.ratio.fillna(0) >= 2.0), sign, 0.0)
        S["vs_btc_day"] = np.where((sign > 0) & ~btc_up, 1.0, np.where((sign < 0) & btc_up, -1.0, 0.0))
        ma200b = btc_c.rolling(200, min_periods=100).mean()
        S["btc_trend"] = np.where(ma200b.isna(), 0.0, np.where(btc_c > ma200b, 1.0, -1.0))
    else:
        S["own_volume"], S["vs_btc_day"], S["btc_trend"] = sign, 0.0, 0.0
    # ---- price context
    ma50, ma200 = c.rolling(50, min_periods=30).mean(), c.rolling(200, min_periods=100).mean()
    S["trend"] = np.where(ma200.isna() | ma50.isna(), 0.0, np.where((c > ma50) & (ma50 > ma200), 1.0, np.where((c < ma50) & (ma50 < ma200), -1.0, 0.0)))
    S["rsi"] = _clip((50 - rsi(c)) / 20, idx).to_numpy()
    S["momentum_30d"] = _clip((c / c.shift(30) - 1) / 0.2, idx).to_numpy()
    lo1, hi1 = l.rolling(365, min_periods=120).min(), h.rolling(365, min_periods=120).max()
    pos = ((c - lo1) / (hi1 - lo1).replace(0, np.nan))
    S["range_1y"] = _clip(np.where(pos <= 0.1, 1.0, np.where(pos >= 0.9, -1.0, 0.0)), idx).where(pos.notna(), 0.0).to_numpy()
    vt = v.rolling(20, min_periods=10).mean() / v.rolling(60, min_periods=30).mean()
    p20 = c / c.shift(20) - 1
    S["volume_trend"] = np.where((vt > 1.3) & (p20 > 0), 1.0, np.where((vt > 1.3) & (p20 < 0), -1.0, 0.0))
    S["value_vs_ma"] = _clip(np.where(c < ma200, (1 - c / ma200) / 0.2, -(c / ma200 - 1) / 0.5), idx).where(ma200.notna(), 0.0).to_numpy()
    # ---- supply
    uw = np.zeros(n)
    if unlocks is not None and len(unlocks):
        big = pd.DatetimeIndex(unlocks[unlocks.pct_of_circulating.fillna(np.inf) >= 1.0].date).normalize()
        days = idx.normalize()
        for t in big:                                                    # +1 in the week after, then -1 in the 3 days before (the caution wins where they overlap)
            diff = np.asarray((days - t).days)
            uw[(diff >= 1) & (diff <= 7)] = 1
        for t in big:
            diff = np.asarray((days - t).days)
            uw[(diff >= -3) & (diff <= 0)] = -1
    else:
        day = idx.day
        uw = np.where((day >= 26) | (day <= 6), -1.0, 0.0)
    S["unlock_window"] = uw
    return S[list(SIGNALS)].astype(float).fillna(0.0)


# ------------------------------------------------------------------ what each signal was worth on its own
def forward(c: pd.Series, h: int = HORIZON) -> pd.Series:
    return c.shift(-h) / c - 1


def evaluate(S: pd.DataFrame, fwd: pd.Series) -> list[dict]:
    """Per signal: rank correlation with the forward return (IC) and its t-stat, average forward return after +1-ish and -1-ish days, hit rate."""
    out = []
    f = fwd.reindex(S.index)
    for k in SIGNALS:
        s = S[k]
        m = f.notna() & (s != 0)
        n = int(m.sum())
        row = {"signal": k, "days_active": n, "share_active": float((s != 0).mean())}
        if n >= 30 and s[m].nunique() > 1:
            ic = float(s[m].corr(f[m], method="spearman"))
            row |= {"ic": ic, "t": ic * np.sqrt(n), "after_buy": float(f[m & (s > 0)].mean()) if (m & (s > 0)).any() else None,
                    "after_sell": float(f[m & (s < 0)].mean()) if (m & (s < 0)).any() else None,
                    "hit_rate": float((np.sign(s[m]) == np.sign(f[m])).mean())}
        else:
            row |= {"ic": None, "t": None, "after_buy": None, "after_sell": None, "hit_rate": None}
        out.append(row)
    return out


def weights_from(S: pd.DataFrame, fwd: pd.Series) -> tuple[dict, str]:
    """Weight = the signal's rank correlation with the forward return when it is positive and at least MIN_T standard errors from zero,
    scaled so the weights sum to 1; equal weights when nothing qualifies (so the composite is never silently empty)."""
    ev = evaluate(S, fwd)
    w = {r["signal"]: max(0.0, r["ic"]) for r in ev if r["ic"] is not None and r["t"] is not None and r["t"] >= MIN_T}
    tot = sum(w.values())
    if tot <= 0:
        return {k: 1 / len(SIGNALS) for k in SIGNALS}, "equal (no signal cleared the bar)"
    return {k: w.get(k, 0.0) / tot for k in SIGNALS}, f"{sum(1 for x in w.values() if x > 0)} signals by rank correlation"


def composite(S: pd.DataFrame, w: dict) -> pd.Series:
    return (S * pd.Series(w)).sum(axis=1).clip(-1, 1)


# ------------------------------------------------------------------ walk-forward: weights from the pooled past, judged on the days after each fit
def walk_forward(per_coin: dict[str, tuple[pd.DataFrame, pd.Series]], h: int = HORIZON, refit: int = REFIT_DAYS, min_train: int = MIN_TRAIN_DAYS) -> dict:
    """per_coin: {coin: (signals frame, close)}. Weights are re-fitted every `refit` days on every coin's rows whose forward return was
    already known at that date (dates < fit date - h), starting once `min_train` days of pooled history exist. Returns the composite per coin
    (NaN before the first fit), the weights at each fit, and today's weights fitted on everything known."""
    pooled = pd.concat([S.assign(_fwd=forward(c, h).reindex(S.index), _coin=k) for k, (S, c) in per_coin.items()])
    pooled = pooled.sort_index()
    dates = pooled.index.unique().sort_values()
    if len(dates) < min_train + h + 1:
        return {"composite": {k: pd.Series(np.nan, index=S.index) for k, (S, _) in per_coin.items()}, "fits": [], "weights_now": None, "how_now": "not enough history"}
    fit_dates = dates[min_train::refit]
    fits = []
    comp = {k: pd.Series(np.nan, index=S.index) for k, (S, _) in per_coin.items()}
    for j, t in enumerate(fit_dates):
        train = pooled[pooled.index < t - pd.Timedelta(days=h)]
        w, how = weights_from(train[list(SIGNALS)], train["_fwd"])
        until = fit_dates[j + 1] if j + 1 < len(fit_dates) else dates[-1] + pd.Timedelta(days=1)
        fits.append({"date": str(t.date()), "until": str((until - pd.Timedelta(days=1)).date()), "weights": w, "how": how, "train_rows": int(len(train))})
        for k, (S, _) in per_coin.items():
            m = (S.index >= t) & (S.index < until)
            if m.any():
                comp[k][m] = composite(S[m], w).to_numpy()
    known = pooled[pooled["_fwd"].notna()]
    w_now, how_now = weights_from(known[list(SIGNALS)], known["_fwd"])
    return {"composite": comp, "fits": fits, "weights_now": w_now, "how_now": how_now, "train_rows_now": int(len(known))}


def backtest(comp: pd.Series, c: pd.Series, enter: float = ENTER, cost: float = COST_PER_SIDE, long_short: bool = True) -> dict:
    """Trade the composite close to close: position decided at each close from that day's score (+1 above `enter`, -1 below -enter, else 0),
    earning the next day's return; costs on every change of position. Judged over the days the composite exists (after the first fit)."""
    x = comp.dropna()
    if len(x) < 30:
        return {"days": int(len(x))}
    px = c.reindex(x.index)
    pos = pd.Series(np.where(x >= enter, 1.0, np.where(x <= -enter, -1.0 if long_short else 0.0, 0.0)), index=x.index)
    r = px.pct_change().shift(-1)                                       # the return earned by the position taken at this close
    turn = pos.diff().abs().fillna(pos.abs())
    strat = (pos * r - turn * cost).dropna()
    eq = (1 + strat).cumprod()
    hold = (px / px.iloc[0])
    dd = float((eq / eq.cummax() - 1).min())
    days = len(strat)
    direction = np.sign(x.where(x.abs() >= enter)).dropna()
    hit = float((direction == np.sign(forward(px, HORIZON).reindex(direction.index))).mean()) if len(direction) else None
    return {"days": days, "from": str(x.index[0].date()), "to": str(x.index[-1].date()), "total": float(eq.iloc[-1] - 1), "hold": float(hold.iloc[-1] - 1),
            "a_year": float(eq.iloc[-1] ** (365 / days) - 1) if days > 60 else None, "hold_a_year": float(hold.iloc[-1] ** (365 / days) - 1) if days > 60 else None,
            "sharpe": float(strat.mean() / strat.std() * np.sqrt(365)) if strat.std() > 0 else None, "worst_drop": dd,
            "hold_worst_drop": float((hold / hold.cummax() - 1).min()), "time_long": float((pos > 0).mean()), "time_short": float((pos < 0).mean()),
            "changes": int((turn > 0).sum()), "hit_rate_7d": hit, "readings": int(len(direction)),
            "equity": [[int(t.timestamp()), round(float(v), 5)] for t, v in eq.items()], "hold_curve": [[int(t.timestamp()), round(float(v), 5)] for t, v in hold.reindex(eq.index).items()]}


def contributions(S_today: pd.Series, w: dict) -> list[dict]:
    rows = [{"signal": k, "label": SIGNALS[k][0], "family": SIGNALS[k][1], "value": float(S_today[k]), "weight": float(w.get(k, 0.0)), "contribution": float(S_today[k] * w.get(k, 0.0))} for k in SIGNALS]
    return sorted(rows, key=lambda r: -abs(r["contribution"]))
