"""Token unlock schedules (data/altcoins/unlocks/<COIN>.csv) and what a coin did around them. Pure: no network.

schedule(coin): every row, dates parsed. events(coin): one row per unlock DAY (same-day tranches summed), only rows counted as sellable
supply (use=1) at or above a confidence level, with the running total unlocked and each day's size as % of what already circulated.
event_table / averages: the coin's move before, into and after each unlock day against every day. rules: short-before / buy-after rules
at daily closes with perp costs, before and after 1 Jul 2025, with a placebo of random dates. Same method as the trading bot's study
(trading-system: src/study/ena_unlocks.py, docs/ENA_Unlock_Study.xlsx).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import DATA_DIR
from ._volume_zones import big_days

DIR = DATA_DIR / "altcoins" / "unlocks"
CONF = {"low": 0, "medium": 1, "high": 2}
OOS = pd.Timestamp("2025-07-01")
COST_PER_SIDE = 0.00045 + 0.0005            # Hyperliquid perp taker fee + slippage allowance, each side (the bot's figure)
HORIZONS = (1, 3, 7, 14)
RULES = {"short 7 days before, cover on the day": (-1, -7, 0), "short 3 days before, cover on the day": (-1, -3, 0), "short 1 day before, cover the day after": (-1, -1, 1),
         "buy the unlock close, sell 7 days later": (1, 0, 7), "buy the day after, sell 14 days later": (1, 1, 14)}
THRESHOLDS = {"every unlock": 0.0, ">= 1% of circulating": 1.0}


def coins() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.csv")) if DIR.exists() else []


def schedule(coin: str) -> pd.DataFrame:
    f = DIR / f"{coin.upper()}.csv"
    cols = ["date", "amount_m", "pct_supply", "category", "kind", "confidence", "use", "source", "note"]
    if not f.exists():
        return pd.DataFrame(columns=cols)
    d = pd.read_csv(f, comment="#")
    amt = next(c for c in d.columns if c.endswith("_m"))
    d = d.rename(columns={amt: "amount_m"})
    d["date"] = pd.to_datetime(d["date"])
    d["use"] = d["use"].fillna(1).astype(int)
    d["confidence"] = d["confidence"].fillna("medium").str.lower()
    return d.sort_values(["date", "category"]).reset_index(drop=True)


def events(coin: str, min_confidence: str = "medium", sched: pd.DataFrame | None = None) -> pd.DataFrame:
    s = schedule(coin) if sched is None else sched
    s = s[(s.use == 1) & (s.confidence.map(CONF).fillna(1) >= CONF[min_confidence]) & (s.amount_m > 0)]
    cols = ["date", "amount_m", "pct_supply", "kinds", "categories", "n_tranches", "cumulative_m", "pct_of_circulating"]
    if s.empty:
        return pd.DataFrame(columns=cols)
    g = s.groupby("date")
    e = pd.DataFrame({"amount_m": g.amount_m.sum(), "pct_supply": g.pct_supply.sum(), "kinds": g.kind.agg(lambda x: "+".join(sorted(set(x)))),
                      "categories": g.category.agg("; ".join), "n_tranches": g.size()}).reset_index()
    e["cumulative_m"] = e.amount_m.cumsum()
    before = e.cumulative_m - e.amount_m
    e["pct_of_circulating"] = (e.amount_m / before.where(before > 0)) * 100
    return e[cols]


def days_to_next(ts: pd.Timestamp, ev: pd.DataFrame) -> int | None:
    day = pd.Timestamp(ts).normalize()
    nxt = ev[ev["date"].dt.normalize() >= day]
    return int((nxt["date"].iloc[0].normalize() - day).days) if len(nxt) else None


def _row(r) -> dict:
    return {"date": str(r.date.date()), "ts": int(r.date.timestamp()), "amount_m": round(float(r.amount_m), 2), "pct_supply": round(float(r.pct_supply), 2),
            "pct_of_circulating": None if pd.isna(r.pct_of_circulating) else round(float(r.pct_of_circulating), 1), "kinds": r.kinds, "who": r.categories,
            "cumulative_m": round(float(r.cumulative_m), 1)}


def for_chart(coin: str, start=None, end=None) -> list[dict]:
    e = events(coin)
    if start is not None:
        e = e[e.date >= pd.Timestamp(start)]
    if end is not None:
        e = e[e.date <= pd.Timestamp(end)]
    return [_row(r) for r in e.itertuples()]


# ------------------------------------------------------------------ event study
def _ret(c: pd.Series, i: int, a: int, b: int) -> float | None:
    if i + a < 0 or i + b >= len(c):
        return None
    return float(c.iloc[i + b] / c.iloc[i + a] - 1)


def event_table(price: pd.DataFrame, ev: pd.DataFrame) -> list[dict]:
    """Per unlock day inside the price history: run-up (close 8 days before to the day before), into the day, after 1 / 3 / 7 / 14 days,
    the day's volume ratio, and the highest-volume day within +-4 days (a date check: trackers disagree on some days)."""
    c = price.close
    bd = big_days(price, 60, 3.0)
    v = price.usd_volume if "usd_volume" in price else price.volume * price.close
    rows = []
    for r in ev.itertuples():
        day = r.date.normalize()
        pos = price.index.get_indexer([day])
        if pos[0] < 0:
            continue
        i = int(pos[0])
        row = {**_row(r), "run_up_7d": _ret(c, i, -8, -1), "into_day": _ret(c, i, -1, 0), **{f"after_{h}d": _ret(c, i, 0, h) for h in HORIZONS},
               "vol_ratio": float(bd.ratio.iloc[i]) if np.isfinite(bd.ratio.iloc[i]) else None, "sample": "in-sample" if day < OOS else "out-of-sample"}
        lo, hi = max(0, i - 4), min(len(price), i + 5)
        j = int(np.argmax(v.iloc[lo:hi].to_numpy())) + lo
        row["max_vol_day_offset"] = j - i
        rows.append(row)
    return rows


def averages(et: list[dict], price: pd.DataFrame) -> list[dict]:
    """Average moves by group, with every day as the baseline."""
    df = pd.DataFrame(et)
    cols = ["run_up_7d", "into_day", *[f"after_{h}d" for h in HORIZONS]]
    if df.empty:
        return []
    pc = df.pct_of_circulating.fillna(np.inf)
    groups = [("all unlocks", df), ("big (>= 5% of circulating)", df[pc >= 5]), ("monthly team + investors (1-5%)", df[(pc >= 1) & (pc < 5)]),
              ("monthly Foundation only (< 1%)", df[pc < 1]), ("before Jul 2025", df[df["sample"] == "in-sample"]), ("Jul 2025 on", df[df["sample"] == "out-of-sample"])]
    rows = []
    for name, g in groups:
        if len(g) == 0:
            continue
        row = {"group": name, "events": int(len(g))}
        for cc in cols:
            x = pd.to_numeric(g[cc], errors="coerce").dropna()
            row[cc] = float(x.mean()) if len(x) else None
            if cc in ("run_up_7d", "after_7d"):
                row[f"{cc}_down"] = float((x < 0).mean()) if len(x) else None
        rows.append(row)
    c = price.close
    base = {"group": "every day", "events": int(len(c)), "run_up_7d": float((c.shift(1) / c.shift(8) - 1).mean()), "into_day": float(c.pct_change().mean()),
            **{f"after_{h}d": float((c.shift(-h) / c - 1).mean()) for h in HORIZONS}}
    base["run_up_7d_down"] = float(((c.shift(1) / c.shift(8) - 1) < 0).mean()); base["after_7d_down"] = float(((c.shift(-7) / c - 1) < 0).mean())
    return rows + [base]


# ------------------------------------------------------------------ rules
def _trades(price: pd.DataFrame, days, side: int, a: int, b: int) -> pd.DataFrame:
    c = price.close
    pos = c.index.get_indexer(pd.DatetimeIndex(days).normalize())
    rows = []
    for t, i in zip(days, pos):
        if i < 0 or i + a < 0 or i + b >= len(c):
            continue
        gross = side * (float(c.iloc[i + b]) / float(c.iloc[i + a]) - 1)
        rows.append({"unlock": t, "entry_t": c.index[i + a], "exit_t": c.index[i + b], "net": gross - 2 * COST_PER_SIDE, "sample": "in-sample" if t < OOS else "out-of-sample"})
    t = pd.DataFrame(rows)
    if len(t):
        keep, last = [], pd.Timestamp.min
        for r in t.itertuples():
            if r.entry_t >= last:
                keep.append(r.Index); last = r.exit_t
        t = t.loc[keep].reset_index(drop=True)
    return t


def _placebo(price: pd.DataFrame, n_events: int, side: int, a: int, b: int, actual: float, n: int = 300, seed: int = 7) -> float | None:
    rng = np.random.default_rng(seed)
    c = price.close.to_numpy()
    lo, hi = max(0, -a), len(c) - b - 1
    if hi <= lo or n_events == 0:
        return None
    idx = rng.integers(lo, hi, size=(n, n_events))
    r = side * (c[idx + b] / c[idx + a] - 1) - 2 * COST_PER_SIDE
    return float((r.mean(axis=1) >= actual).mean())


def rules(price: pd.DataFrame, ev: pd.DataFrame) -> list[dict]:
    ev = ev[(ev.date >= price.index[0]) & (ev.date <= price.index[-1])]
    out = []
    for th_name, th in THRESHOLDS.items():
        sel = ev[ev.pct_of_circulating.fillna(np.inf) >= th] if th > 0 else ev
        for name, (side, a, b) in RULES.items():
            t = _trades(price, pd.DatetimeIndex(sel.date), side, a, b)
            row = {"rule": name, "unlocks": th_name, "trades": int(len(t))}
            if len(t):
                eq = (1 + t.net).cumprod()
                row |= {"total": float(eq.iloc[-1] - 1), "avg": float(t.net.mean()), "win_rate": float((t.net > 0).mean()), "worst": float(t.net.min()),
                        "in_sample": float((1 + t.net[t["sample"] == "in-sample"]).prod() - 1), "out_of_sample": float((1 + t.net[t["sample"] == "out-of-sample"]).prod() - 1),
                        "placebo_p": _placebo(price, len(t), side, a, b, float(t.net.mean()))}
            out.append(row)
    return out
