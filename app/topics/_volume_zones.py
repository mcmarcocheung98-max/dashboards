"""Big-volume days and the buy / sell zones they leave behind, as pure functions of DAILY candles (no network, no files).
Same rules as the trading bot's research (trading-system: src/hl/alts/volume_zones.py, docs/Alt_Volume_Zones_Study.xlsx).

A day is a BIG-VOLUME day when its USD volume is at least `mult` times the median of the previous `lookback` closed days (nothing is
known early). An up close makes it a BUY day (a lot of selling was absorbed, or buyers chased it), a down close a SELL day. Each big day
leaves a ZONE = the day's body (open to close), the prices where most of that volume changed hands: a buy day's zone is support, a sell
day's zone resistance. A zone is live from the next day; it dies when a close goes through its far side by more than `break_atr` ATRs or
after `max_age` days. A RETEST is the first day price comes back into a live zone from the right side (into support from above, into
resistance from below).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DEFAULTS = {"lookback": 60, "mult": 3.0, "min_history": 20, "max_age": 180, "break_atr": 1.0, "atr_len": 14, "flip": False, "min_gap_days": 2}


def usd_volume(d: pd.DataFrame) -> pd.Series:
    if "usd_volume" in d and d.usd_volume.notna().any():
        return d.usd_volume.astype(float)
    return d.volume.astype(float) * d.close.astype(float)


def atr(d: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = d.close.shift()
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def big_days(d: pd.DataFrame, lookback: int = DEFAULTS["lookback"], mult: float = DEFAULTS["mult"], min_history: int = DEFAULTS["min_history"]) -> pd.DataFrame:
    """Per day: volume ratio against the trailing median of CLOSED days, whether it is a big day, and its kind (buy / sell / '')."""
    v = usd_volume(d)
    base = v.rolling(lookback, min_periods=min_history).median().shift(1)
    ratio = (v / base).replace([np.inf, -np.inf], np.nan)
    big = ratio >= mult
    up, flat = d.close > d.open, d.close == d.open
    kind = np.where(~big, "", np.where(up, "buy", np.where(flat, np.where(d.close >= (d.high + d.low) / 2, "buy", "sell"), "sell")))
    return pd.DataFrame({"ratio": ratio, "big": big.fillna(False), "kind": kind}, index=d.index)


@dataclass
class Zone:
    coin: str
    born: pd.Timestamp
    kind: str                   # "buy" (support) or "sell" (resistance)
    lo: float
    hi: float
    ratio: float
    died: pd.Timestamp | None = None
    why: str = ""               # "broken", "aged" or "" (live)
    flipped_from: str = ""
    retests: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"born": int(self.born.timestamp()), "kind": self.kind, "lo": self.lo, "hi": self.hi, "ratio": round(float(self.ratio), 2),
                "died": int(self.died.timestamp()) if self.died is not None else None, "why": self.why, "retests": [int(t.timestamp()) for t in self.retests]}


def zones(d: pd.DataFrame, coin: str = "", **kw) -> list[Zone]:
    """Every zone a big day created, with its life and its retests; each day uses only its own and earlier candles."""
    p = {**DEFAULTS, **kw}
    b = big_days(d, p["lookback"], p["mult"], p["min_history"])
    a = atr(d, p["atr_len"])
    o, h, l, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    idx = d.index
    live: list[Zone] = []
    out: list[Zone] = []
    for i in range(len(d)):
        t = idx[i]
        day_atr = a.iloc[i] if np.isfinite(a.iloc[i]) else (h[i] - l[i])
        for z in list(live):
            age = (t - z.born).days
            if age >= p["min_gap_days"]:
                if z.kind == "buy" and c[i - 1] > z.hi and l[i] <= z.hi:
                    z.retests.append(t)
                elif z.kind == "sell" and c[i - 1] < z.lo and h[i] >= z.lo:
                    z.retests.append(t)
            broken = (z.kind == "buy" and c[i] < z.lo - p["break_atr"] * day_atr) or (z.kind == "sell" and c[i] > z.hi + p["break_atr"] * day_atr)
            if broken or age > p["max_age"]:
                z.died, z.why = t, "broken" if broken else "aged"
                live.remove(z)
                if broken and p["flip"] and age <= p["max_age"]:
                    live.append(Zone(coin, t, "sell" if z.kind == "buy" else "buy", z.lo, z.hi, z.ratio, flipped_from=z.kind))
                    out.append(live[-1])
        if b.big.iloc[i]:
            z = Zone(coin, t, str(b.kind.iloc[i]), float(min(o[i], c[i])), float(max(o[i], c[i])), float(b.ratio.iloc[i]))
            live.append(z)
            out.append(z)
    return out


def live_zones(zs: list[Zone], at: pd.Timestamp | None = None) -> list[Zone]:
    if at is None:
        return [z for z in zs if z.died is None]
    return [z for z in zs if z.born < at and (z.died is None or z.died >= at)]


def nearest(zs: list[Zone], price: float) -> dict:
    """The closest live support below and resistance above a price, as distances in %, and the zone the price sits in, if any."""
    sup = [z for z in zs if z.kind == "buy" and z.hi <= price]
    res = [z for z in zs if z.kind == "sell" and z.lo >= price]
    out = {}
    if sup:
        z = max(sup, key=lambda z: z.hi)
        out["support"] = {"lo": z.lo, "hi": z.hi, "below_pct": price / z.hi - 1, "born": str(z.born.date()), "ratio": round(z.ratio, 1)}
    if res:
        z = min(res, key=lambda z: z.lo)
        out["resistance"] = {"lo": z.lo, "hi": z.hi, "above_pct": z.lo / price - 1, "born": str(z.born.date()), "ratio": round(z.ratio, 1)}
    inside = [z for z in zs if z.lo <= price <= z.hi]
    if inside:
        z = max(inside, key=lambda z: z.ratio)
        out["inside"] = {"kind": z.kind, "lo": z.lo, "hi": z.hi, "born": str(z.born.date()), "ratio": round(z.ratio, 1)}
    return out


def after_big_days(d: pd.DataFrame, b: pd.DataFrame | None = None, horizons=(7, 30)) -> dict:
    """What this coin did after its own big days: average close-to-close return h days later, buy days and sell days apart, against every day."""
    b = big_days(d) if b is None else b
    c = d.close
    out = {"buy_days": int((b.kind == "buy").sum()), "sell_days": int((b.kind == "sell").sum())}
    for h in horizons:
        fwd = c.shift(-h) / c - 1
        out[f"every_{h}d"] = float(fwd.mean()) if fwd.notna().any() else None
        for k in ("buy", "sell"):
            x = fwd[b.kind == k].dropna()
            out[f"{k}_{h}d"] = float(x.mean()) if len(x) else None
            out[f"{k}_{h}d_up"] = float((x > 0).mean()) if len(x) else None
    return out


def retest_stats(zs: list[Zone], d: pd.DataFrame, h: int = 7) -> dict:
    """The move over the next h days after the FIRST retest of each zone, support and resistance apart."""
    c = d.close
    out = {}
    for k in ("buy", "sell"):
        rs = []
        for z in zs:
            if z.kind == k and z.retests and not z.flipped_from:
                i = int(d.index.get_loc(z.retests[0]))
                if i + h < len(c):
                    rs.append(float(c.iloc[i + h] / c.iloc[i] - 1))
        out[f"{k}_retests"] = len(rs)
        out[f"{k}_retest_{h}d"] = float(np.mean(rs)) if rs else None
        out[f"{k}_retest_{h}d_up"] = float(np.mean([r > 0 for r in rs])) if rs else None
    return out


def chart_payload(d: pd.DataFrame, coin: str, days: int = 400, **kw) -> dict:
    """Bars (with USD volume) for the last `days`, the big days, every zone alive in that window (live and dead) and the nearest levels now."""
    zs = zones(d, coin, **kw)
    b = big_days(d, kw.get("lookback", DEFAULTS["lookback"]), kw.get("mult", DEFAULTS["mult"]), kw.get("min_history", DEFAULTS["min_history"]))
    v = usd_volume(d)
    x = d.iloc[-days:]
    t0 = int(x.index[0].timestamp())
    bars = [[int(t.timestamp()), float(r.open), float(r.high), float(r.low), float(r.close), float(v.loc[t]) if np.isfinite(v.loc[t]) else 0.0] for t, r in x.iterrows()]
    big = [{"ts": int(t.timestamp()), "kind": str(k), "ratio": round(float(r), 1)} for t, k, r, g in zip(b.index, b.kind, b.ratio, b.big) if g and int(t.timestamp()) >= t0]
    price = float(d.close.iloc[-1])
    live = live_zones(zs)
    return {"coin": coin, "bars": bars, "big_days": big, "zones": [z.as_dict() for z in zs if z.died is None or int(z.died.timestamp()) >= t0],
            "live": len(live), "now": nearest(live, price), "price": price, "history_days": len(d), "since": str(d.index[0].date()),
            "stats": {**after_big_days(d, b), **retest_stats(zs, d)}}
