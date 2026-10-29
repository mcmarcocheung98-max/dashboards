"""Altcoin Study (/altcoins): the four BTC Cycles candidates with a tab each (HYPE, ENA, SOL, NEAR), the memecoin basket and meme season,
and a buy zone for every coin on one tab.

zones    every coin's buy zone (rule below), where today's price sits against it, RSI and the 30-day move
hype ... one tab per candidate (_coin_page.py): price against BTC, RSI, market cap, the case for it, fundamentals and the projection
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

Nothing is downloaded here: btc_cycles' and memecoins' background fills keep every coin's 365 days of prices.
"""
from __future__ import annotations

import time

import pandas as pd

from ..cache import _cached
from . import Topic
from . import _coin_page as P
from . import btc_cycles as C
from . import memecoins as M
from ._base import _r

SLUG = "altcoins"
CANDIDATES = ("HYPE", "ENA", "SOL", "NEAR")
TABS = (("zones", "Buy zones"), *((t.lower(), t) for t in CANDIDATES), ("basket", "Memecoins"), ("season", "Meme season"))
TOPIC = Topic(SLUG, "Altcoin Study",
              "HYPE, ENA, SOL and NEAR in full (price against BTC, fundamentals, the bear / base / bull projection), the memecoin basket and meme "
              "season, and a buy zone for every coin: below its 200-day average and, for the candidates, with the base case at least doubling.",
              "altcoins", TABS, ("zones", "basket", "season"), icon="chart", order=12)
MA_DAYS = 200
VALUE_MULT = 2.0                               # the base case to end-2028 must at least double from the top of the zone
SIBLINGS = {t: f"#{t.lower()}" for t in CANDIDATES}
SOURCES = [*(s for t in CANDIDATES for s in P.sources(t)), *M.SOURCES,
           {"name": "Projection levels and coin notes (BTC Cycles & Sector Rotation)", "url": "/btc-cycles#candidates", "cadence": "as revised"}]
NOTES = ("Research, not investment advice. Buy zones are mechanical: below the coin's 200-day average and, for the four candidates, low enough "
         "that the base-case projection at least doubles by end-2028. They say nothing about whether a coin survives or what its news will be.")


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
    return pd.Series([v for _, v in pts], index=pd.to_datetime([t for t, _ in pts], unit="s"))


def _coin_tab(ticker: str) -> dict:
    f = P.payload(ticker, SIBLINGS)
    pts = (f.get("series") or {}).get("price")
    if pts:
        f["zone"] = buy_zone(_series(pts), (f.get("kpi") or {}).get("base_2028"))
    return f


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


def READINGS() -> list[dict]:
    """Each coin's zone status (+1 in zone, 0 otherwise) plus the meme season headline, from cached data only."""
    out = [{"tab": "zones", "key": f"zone_{r['ticker'].lower()}", "label": f"{r['ticker']} buy zone", "value": r["status"],
            "lean": 1 if r["status"] == "in zone" else 0}
           for r in (ENDPOINTS["zones"]() or {}).get("coins", []) if r["status"] in ("in zone", "above zone", "no zone")]
    return out + M.READINGS()


def _cached_ep(name, fn, ttl=3600):
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"zones": _cached_ep("zones", _zones_now, 900),
             **{t.lower(): _cached_ep(t.lower(), (lambda t: lambda: _coin_tab(t))(t)) for t in CANDIDATES},
             "basket": M.ENDPOINTS["basket"], "season": M.ENDPOINTS["season"]}
BACKGROUND = M.BACKGROUND                       # the memecoin prices; the candidates come with btc_cycles' own fill
