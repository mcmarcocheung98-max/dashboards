"""Fear and Greed and our own BTC signal board, studied the same way (the Signals tab of /btc-cycles). Pure: no network.

Two daily scores:
  fng     alternative.me's Fear and Greed index (0-100, one value a day, published at 00:00 UTC). Zones as alternative.me and the
          trading bot's board use them: below 25 extreme fear, 25-46 fear, 47-54 neutral, 55-75 greed, above 75 extreme greed.
  board   the trading bot's BTC spot signal (trading-system: src/hl/signal_board.py), rebuilt from free data: each gauge scores a day
          from +1 (in its buy zone, where past cycle lows sat) to -1 (in its sell zone, near past tops) with a straight ramp through
          the zone; the score is the weighted average of the gauges with data (the three on-chain valuation gauges count double; at
          least five gauges or no score). >= +0.5 STRONG BUY, >= +0.2 BUY, <= -0.2 SELL, <= -0.5 STRONG SELL. The bot's funding-rate
          and hash-ribbon gauges are not rebuilt here (no free history on this server), so the score can differ a little from the bot's.

Both are one figure per UTC day. Neither exists intraday (the index is published once, the on-chain inputs are daily), so there is no
"9am New York" reading to choose: the day's value is fixed at midnight UTC, which is the evening before in New York, and it is paired
with that UTC day's closing price. Forward returns run from that close, so nothing later than the reading is used.

study() answers the same questions for either score: how long the stretches in each zone run (consecutive days), what the score
averaged in the doc's bull and bear legs, and what BTC did after each zone, with the number of separate spells behind every figure
(a 60-day stretch of extreme fear is one event, not sixty).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# key, name, buy_extreme (+1 at or beyond), buy_start, sell_start, sell_extreme (-1 at or beyond), weight, source
GAUGES = [
    ("mvrv_zscore", "MVRV Z-score", 0.0, 1.0, 5.0, 7.0, 2.0, "Glassnode / LookIntoBitcoin: < 0 lows, > 7 tops"),
    ("nupl", "NUPL (holders' unrealised profit)", 0.0, 0.25, 0.5, 0.75, 2.0, "Glassnode zones: < 0 capitulation, > 0.75 euphoria"),
    ("puell", "Puell multiple", 0.5, 0.8, 2.0, 4.0, 1.0, "Glassnode / CryptoQuant: < 0.5 lows, > 4 tops"),
    ("mayer", "Mayer multiple (price / 200-day average)", 0.8, 1.0, 1.8, 2.4, 1.0, "Glassnode: < 0.8 oversold, > 2.4 overbought"),
    ("ma2y_mult", "2-year MA multiplier", 1.0, 1.3, 3.0, 5.0, 1.0, "Glassnode: below the 2-year average lows, above 5x tops"),
    ("wma200_mult", "Price / 200-week average", 1.0, 1.5, 3.0, 5.0, 1.0, "LookIntoBitcoin 200-week heatmap (sell levels the bot's own)"),
    ("pi_ratio", "Pi Cycle Top (111-day / 2x 350-day average)", None, None, 0.9, 1.0, 1.0, "Pi Cycle Top: >= 1 marked the 2013, 2017, 2021 tops (sell side only)"),
    ("thermocap_mult", "Thermocap multiple (value / all miner revenue)", 5.0, 8.0, 25.0, 40.0, 2.0, "levels the bot's own, from past cycles"),
    ("fng", "Fear and Greed index", 10.0, 25.0, 75.0, 90.0, 1.0, "alternative.me: < 25 extreme fear, > 75 extreme greed"),
    ("ssr_pct", "Stablecoin supply ratio (1-year percentile)", 0.1, 0.3, 0.7, 0.9, 1.0, "CryptoQuant SSR: low = lots of stablecoin buying power"),
]
MIN_GAUGES = 5
LEVELS = {"strong_buy": 0.5, "buy": 0.2, "sell": -0.2, "strong_sell": -0.5}
FNG_NAMES = {2: "extreme fear", 1: "fear", 0: "neutral", -1: "greed", -2: "extreme greed"}
BOARD_NAMES = {2: "STRONG BUY", 1: "BUY", 0: "NEUTRAL", -1: "SELL", -2: "STRONG SELL"}
HORIZONS = (30, 90, 180)


def gauge_score(v: pd.Series, be, bs, ss, se) -> pd.Series:
    """+1 at or beyond the buy extreme, a straight ramp from 0 at the zone's start, the mirror on the sell side, 0 between; NaN stays NaN."""
    x = v.astype(float)
    out = pd.Series(0.0, index=x.index)
    if be is not None and bs is not None:
        out = out.where(~(x < bs), (bs - x) / (bs - be)).where(~(x <= be), 1.0)
    if ss is not None and se is not None:
        out = out.where(~(x > ss), -(x - ss) / (se - ss)).where(~(x >= se), -1.0)
    return out.where(x.notna())


def indicators(c: pd.DataFrame, fng: pd.Series | None = None, stables: pd.Series | None = None) -> pd.DataFrame:
    """Every gauge's raw value by UTC day from Coin Metrics' daily frame (PriceUSD, and when present CapMrktCurUSD, CapMVRVCur, IssTotUSD,
    FeeTotNtv), the Fear and Greed series and total stablecoin supply. Same definitions as the bot's cycle.indicators."""
    px = c["PriceUSD"].astype(float)
    d = pd.DataFrame({"price": px})
    d["mayer"] = px / px.rolling(200, min_periods=200).mean()
    d["ma2y_mult"] = px / px.rolling(730, min_periods=730).mean()
    d["wma200_mult"] = px / px.rolling(1400, min_periods=1400).mean()
    d["pi_ratio"] = px.rolling(111).mean() / (2 * px.rolling(350).mean())
    mc = c["CapMrktCurUSD"].astype(float) if "CapMrktCurUSD" in c else None
    if mc is not None and "CapMVRVCur" in c:
        mvrv = c["CapMVRVCur"].astype(float)
        rc = mc / mvrv
        d["mvrv_zscore"] = (mc - rc) / mc.expanding(min_periods=365).std()
        d["nupl"] = 1 - 1 / mvrv
    if "IssTotUSD" in c:
        revenue = c["IssTotUSD"].astype(float) + (c["FeeTotNtv"].astype(float) * px if "FeeTotNtv" in c else 0.0)
        d["puell"] = revenue / revenue.rolling(365, min_periods=365).mean()
        if mc is not None:
            thermo = revenue.fillna(0).cumsum()
            d["thermocap_mult"] = mc / thermo.where(thermo > 0)
    if fng is not None and len(fng):
        d["fng"] = fng.reindex(d.index)
    if stables is not None and len(stables) and mc is not None:
        ssr = mc / stables.reindex(d.index).ffill()
        d["ssr_pct"] = ssr.rolling(365, min_periods=182).apply(lambda w: (w[:-1] < w[-1]).mean(), raw=True)
    return d


def board(d: pd.DataFrame) -> pd.DataFrame:
    """Each gauge's score per day plus 'aggregate' (weighted average of the gauges with data, at least MIN_GAUGES) and 'n'."""
    sc, w = pd.DataFrame(index=d.index), {}
    for key, _, be, bs, ss, se, weight, _ in GAUGES:
        if key in d:
            sc[key] = gauge_score(d[key], be, bs, ss, se)
            w[key] = weight
    ws = pd.Series(w)
    n = sc.notna().sum(axis=1)
    weight_sum = sc.notna().mul(ws, axis=1).sum(axis=1)
    agg = (sc.fillna(0).mul(ws, axis=1).sum(axis=1) / weight_sum.replace(0, np.nan)).where(n >= MIN_GAUGES)
    return sc.assign(n=n, aggregate=agg)


def board_zone(agg: pd.Series) -> pd.Series:
    z = pd.Series(0, index=agg.index, dtype=float)
    z[agg >= LEVELS["buy"]] = 1
    z[agg >= LEVELS["strong_buy"]] = 2
    z[agg <= LEVELS["sell"]] = -1
    z[agg <= LEVELS["strong_sell"]] = -2
    return z.where(agg.notna())


def fng_zone(v: pd.Series) -> pd.Series:
    """Contrarian sign, as on the board: fear is the buy side (+), greed the sell side (-)."""
    z = pd.Series(0, index=v.index, dtype=float)
    z[v < 47] = 1
    z[v < 25] = 2
    z[v > 54] = -1
    z[v > 75] = -2
    return z.where(v.notna())


def legs(markers: list[dict], end: pd.Timestamp) -> list[dict]:
    """The doc's bull and bear legs from its peak / low markers: peak to the next low is a bear leg, low to the next peak a bull leg;
    the stretch after the last marker is open (still running)."""
    ms = sorted(({"t": pd.Timestamp(m["date"]), "peak": m["label"].lower().startswith("peak")} for m in markers), key=lambda m: m["t"])
    out, prev = [], None
    for m in ms:
        if prev is not None:
            out.append({"kind": "bear" if prev["peak"] else "bull", "start": prev["t"], "end": m["t"], "open": False})
        else:
            out.append({"kind": "bull" if m["peak"] else "bear", "start": pd.Timestamp("2009-01-03"), "end": m["t"], "open": False})
        prev = m
    if prev is not None and prev["t"] < end:
        out.append({"kind": "bear" if prev["peak"] else "bull", "start": prev["t"], "end": end + pd.Timedelta(days=1), "open": True})
    for g in out:
        g["label"] = (f"{g['kind'].capitalize()} since {g['start'].strftime('%b %Y')} (so far)" if g["open"] else
                      f"{g['kind'].capitalize()} to {g['end'].strftime('%b %Y')}" if g["start"].year < 2010 else f"{g['kind'].capitalize()} {g['start'].year}-{str(g['end'].year)[2:]}")
    return out


def runs(mask: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    """Stretches of consecutive True days as (first day, last day, days)."""
    m = mask.fillna(False).astype(bool)
    grp = (m != m.shift()).cumsum()
    return [(g.index[0], g.index[-1], len(g)) for _, g in m[m].groupby(grp[m])]


def _pct(x, d=3):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


def _med(s: pd.Series):
    s = s.dropna()
    return _pct(s.median()) if len(s) else None


def _spearman(a: pd.Series, b: pd.Series, h: int) -> dict:
    x = pd.concat([a, b], axis=1).dropna()
    if len(x) < 60:
        return {"ic": None, "t": None, "n": len(x)}
    rho = float(x.iloc[:, 0].rank().corr(x.iloc[:, 1].rank()))
    n_eff = max(len(x) / h, 3)                          # overlapping forward windows: about n / h independent observations
    return {"ic": round(rho, 3), "t": round(rho * np.sqrt(n_eff - 2) / np.sqrt(max(1 - rho * rho, 1e-9)), 1), "n": len(x)}


def study(value: pd.Series, zone: pd.Series, price: pd.Series, markers: list[dict], names: dict, digits: int = 0, min_mark: int = 5) -> dict:
    """Streaks, bull / bear averages and what BTC did afterwards, for one daily score. zone: +2 .. -2, + = the buy side."""
    idx = pd.date_range(value.dropna().index[0], value.dropna().index[-1], freq="D")
    v = value.reindex(idx).ffill(limit=3)                # a missing day or two keeps the last reading; longer gaps break a streak
    z = zone.reindex(idx).ffill(limit=3)
    px = price.reindex(idx).ffill(limit=3)
    df = pd.DataFrame({"v": v, "z": z, "px": px}).dropna(subset=["v", "z"])
    L = legs(markers, idx[-1])
    df["kind"], df["leg"] = None, None
    for g in L:
        m = (df.index >= g["start"]) & (df.index < g["end"])
        df.loc[m, "kind"], df.loc[m, "leg"] = g["kind"], g["label"]
    for h in HORIZONS:
        df[f"f{h}"] = px.shift(-h).reindex(df.index) / df.px - 1
    ts = lambda t: int(pd.Timestamp(t).timestamp())
    ext = {2: runs(df.z == 2), -2: runs(df.z == -2)}
    side = {1: runs(df.z > 0), -1: runs(df.z < 0)}

    def run_rows(rs, code):
        out = []
        for a, b, n in rs:
            p0, p1 = df.px.get(a), df.px.get(b)
            out.append({"from": str(a.date()), "to": str(b.date()), "ts_from": ts(a), "ts_to": ts(b), "days": n, "zone": code, "open": b == df.index[-1],
                        "move": _pct(p1 / p0 - 1) if p0 and p1 else None, "after_90": _pct(df.f90.get(b))})
        return out

    def run_stats(rs):
        d = [n for _, _, n in rs]
        longest = max(rs, key=lambda r: r[2]) if rs else None
        return {"spells": len(rs), "days": int(sum(d)), "median_days": _pct(np.median(d), 0) if d else None, "mean_days": _pct(np.mean(d), 1) if d else None,
                "longest": {"days": longest[2], "from": str(longest[0].date()), "to": str(longest[1].date())} if longest else None}

    # today: the zone, and how many days in a row on this side and in this exact zone
    last_z = int(df.z.iloc[-1])
    streak = lambda mask: int((~mask[::-1]).values.argmax()) if not mask.all() else len(mask)
    now = {"date": str(df.index[-1].date()), "value": _pct(df.v.iloc[-1], max(digits, 2)), "zone": last_z, "zone_name": names[last_z],
           "zone_days": streak(df.z == last_z), "side": int(np.sign(last_z)),
           "side_days": streak(df.z > 0) if last_z > 0 else streak(df.z < 0) if last_z < 0 else streak(df.z == 0),
           "leg": df.leg.iloc[-1], "kind": df.kind.iloc[-1]}

    def regime_row(label, g, kind=None):
        if not len(g):
            return {"label": label, "kind": kind, "days": 0}
        return {"label": label, "kind": kind, "days": len(g), "mean": _pct(g.v.mean(), 2), "median": _pct(g.v.median(), 2),
                "buy_extreme": _pct((g.z == 2).mean()), "buy_side": _pct((g.z > 0).mean()), "sell_side": _pct((g.z < 0).mean()), "sell_extreme": _pct((g.z == -2).mean()),
                "from": str(g.index[0].date()), "to": str(g.index[-1].date())}
    regimes = [regime_row("All bull legs", df[df.kind == "bull"], "bull"), regime_row("All bear legs", df[df.kind == "bear"], "bear")] if df.kind.notna().any() else []
    regimes = [r for r in regimes if r["days"]]
    leg_rows = [regime_row(g["label"], df[df.leg == g["label"]], g["kind"]) for g in L if (df.leg == g["label"]).any()]
    ma = px.rolling(200, min_periods=200).mean().reindex(df.index)
    trend = [regime_row("BTC above its 200-day average", df[df.px > ma], "bull"), regime_row("BTC below its 200-day average", df[df.px < ma], "bear")]
    trend = [r for r in trend if r["days"]]

    def fwd_row(label, g, spells=None, code=None):
        r = {"label": label, "zone": code, "days": len(g), "spells": spells}
        for h in HORIZONS:
            f = g[f"f{h}"].dropna()
            r[f"med_{h}"], r[f"up_{h}"], r[f"n_{h}"] = _med(f), _pct((f > 0).mean()) if len(f) else None, len(f)
        return r
    forward = [fwd_row(names[c].capitalize() if names[c].islower() else names[c], df[df.z == c], len(runs(df.z == c)), c) for c in (2, 1, 0, -1, -2)]
    forward.append(fwd_row("All days", df))
    by_regime = [fwd_row(f"{names[c]} in {k} legs", df[(df.z == c) & (df.kind == k)], len(runs((df.z == c) & (df.kind == k))), c) for c in (2, -2) for k in ("bull", "bear")]
    by_regime += [fwd_row(f"All days in {k} legs", df[df.kind == k]) for k in ("bull", "bear")]
    # does a long streak mean more than a short one? Extreme days grouped by how deep into their spell they are
    depth = []
    for code in (2, -2):
        m = df.z == code
        day_in = m.groupby((m != m.shift()).cumsum()).cumcount() + 1
        for lo, hi, lab in ((1, 7, "days 1-7 of a spell"), (8, 30, "days 8-30"), (31, 10 ** 6, "day 31 on")):
            g = df[m & (day_in >= lo) & (day_in <= hi)]
            if len(g):
                depth.append({**fwd_row(f"{names[code]}: {lab}", g, int((m & (day_in == lo)).sum()), code)})
    ic = {str(h): _spearman(df.v, df[f"f{h}"], h) for h in HORIZONS}

    # plain readings of the tables
    reads = []
    by = {r["kind"]: r for r in regimes}
    f_ = lambda x: "–" if x is None else f"{x:+.0%}"
    num = lambda x: "–" if x is None else (f"{x:.{digits}f}" if digits else f"{x:.0f}")
    if "bull" in by and "bear" in by:
        reads.append(f"Average reading {num(by['bull']['mean'])} in bull legs against {num(by['bear']['mean'])} in bear legs. {names[2].capitalize() if names[2].islower() else names[2]} on "
                     f"{by['bear']['buy_extreme']:.0%} of bear-leg days and {by['bull']['buy_extreme']:.0%} of bull-leg days; {names[-2]} on {by['bull']['sell_extreme']:.0%} of bull-leg days and {by['bear']['sell_extreme']:.0%} of bear-leg days.")
    allr = forward[-1]
    for code in (2, -2):
        r = next(x for x in forward if x["zone"] == code)
        if r["n_90"]:
            reads.append(f"After a day of {names[code]}, BTC's median move over the next 90 days was {f_(r['med_90'])} ({r['up_90']:.0%} of days higher) against {f_(allr['med_90'])} "
                         f"({allr['up_90']:.0%}) for all days: {r['days']} days in {r['spells']} separate spells, so the evidence is {r['spells']} episodes, not {r['days']}.")
    br = {(x["zone"], x["label"].split(" in ")[-1].split(" ")[0]): x for x in by_regime if x["zone"]}
    for code in (2, -2):
        a, b = br.get((code, "bull")), br.get((code, "bear"))
        if a and b and a["n_90"] and b["n_90"]:
            reads.append(f"{names[code].capitalize() if names[code].islower() else names[code]} inside a bull leg was followed by {f_(a['med_90'])} over 90 days ({a['spells']} spells); inside a bear leg by {f_(b['med_90'])} ({b['spells']} spells).")
    if ic["90"]["ic"] is not None:
        reads.append(f"Rank correlation of the reading with BTC's next 90 days: {ic['90']['ic']:+.2f} (t about {ic['90']['t']:+.1f} after allowing for overlapping windows; beyond ±2 would be notable). "
                     + ("Negative = high readings were followed by weaker returns." if names is FNG_NAMES else "Positive = buy readings were followed by stronger returns."))

    marks = sorted((r for code in (2, -2) for r in run_rows(ext[code], code) if r["days"] >= min_mark), key=lambda r: r["ts_from"])
    return {"now": now, "since": str(df.index[0].date()), "days": len(df), "names": {str(k): n for k, n in names.items()},
            "series": [[ts(t), round(float(a), max(digits, 2)), None if not np.isfinite(p) else round(float(p), 2), int(c)] for t, a, p, c in zip(df.index, df.v, df.px, df.z)],
            "extreme": {"buy": run_stats(ext[2]), "sell": run_stats(ext[-2])}, "side": {"buy": run_stats(side[1]), "sell": run_stats(side[-1])},
            "marks": marks, "longest": sorted((r for code in (2, -2) for r in run_rows(ext[code], code)), key=lambda r: -r["days"])[:12],
            "regimes": regimes, "legs": leg_rows, "trend": trend, "forward": forward, "forward_by_regime": by_regime, "depth": depth, "ic": ic, "reads": reads,
            "horizons": list(HORIZONS), "min_mark": min_mark}


def board_today(d: pd.DataFrame, sc: pd.DataFrame) -> list[dict]:
    """The gauges behind today's score: value, score, weight."""
    day = sc["aggregate"].dropna().index[-1]
    rows = []
    for key, name, be, bs, ss, se, weight, source in GAUGES:
        if key in sc and np.isfinite(sc.loc[day, key]):
            rows.append({"key": key, "name": name, "value": _pct(d.loc[day, key], 2), "score": _pct(sc.loc[day, key], 2), "weight": weight, "source": source,
                         "buy": None if bs is None else f"< {bs:g} ({be:g})", "sell": None if ss is None else f"> {ss:g} ({se:g})"})
    return rows


def label(agg: float) -> str:
    return "STRONG BUY" if agg >= LEVELS["strong_buy"] else "BUY" if agg >= LEVELS["buy"] else "STRONG SELL" if agg <= LEVELS["strong_sell"] else "SELL" if agg <= LEVELS["sell"] else "NEUTRAL"
