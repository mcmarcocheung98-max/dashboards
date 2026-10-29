"""Memecoins, the Memecoins and Meme season tabs of Altcoin Study (/altcoins#basket, #season; see altcoins.py): the largest memecoins as one
basket, against BTC, and whether it is meme season. (Was its own dashboard at /memecoins, which now redirects.)

basket   one row per coin (data/memecoins/coins.csv): price, 24h, 7-day, 30-day and 1-year change, distance from the 1-year high, market cap,
         RSI 14 in USD and against BTC, beta to BTC, 90 days against BTC, a 90-day sparkline; the basket's total market cap; and every coin's
         price rebased to 100 a year ago against BTC
season   the basket against BTC: total basket market cap ÷ BTC market cap (rising = memes beating BTC), its RSI and 90-day change, an
         equal-weight price index against BTC, and the memecoin sector's share of the whole crypto market (CoinGecko's "Meme" category ÷
         total market cap, logged once a day from the first deploy: CoinGecko has no free history of either)

Downloads are slow and paced (BACKGROUND fill(), like btc_cycles, sharing its pace so the two never call CoinGecko at once): each coin's
365-day price and market cap, then the category list and the global total once a day. Pages read what the fill already has.
"""
from __future__ import annotations

import csv
import json
import time

import numpy as np
import pandas as pd

from ..cache import _cached
from ..config import DATA_DIR, SNAP_DIR
from . import btc_cycles as C
from ._base import _pts, _r, cached_only, fetch_json, stale_info

SLUG = "memecoins"                          # its data folder (data/memecoins/) and cache keys; the page is Altcoin Study
DASHBOARD = "altcoins"
COINS = DATA_DIR / SLUG / "coins.csv"
CG_CATEGORIES = "https://api.coingecko.com/api/v3/coins/categories"
CG_GLOBAL = C.CG_GLOBAL
MEME_CATEGORY = "meme-token"
SHARE_LOG = SNAP_DIR / "memecoin_share_log.csv"
SOURCES = [{"name": "Memecoin prices and market caps (CoinGecko)", "url": "https://www.coingecko.com/en/categories/meme-token", "cadence": "daily"},
           {"name": "BTC price and market cap (CoinGecko)", "url": "https://www.coingecko.com/en/coins/bitcoin", "cadence": "daily"},
           {"name": "Memecoin sector and total crypto market cap (CoinGecko categories and global)", "url": "https://www.coingecko.com/en/global-charts", "cadence": "logged daily"}]
NOTES = ("Research, not investment advice. Memecoins have no cash flows: the page only measures price, size and momentum against BTC. "
         "'Meme season' is a mechanical reading of the basket against BTC, not a forecast.")
HOT, COLD = 0.25, -0.25                     # 90-day change of the basket ÷ BTC that counts as meme season / out of season


def coins_list() -> list[dict]:
    with COINS.open(newline="", encoding="utf-8") as f:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    return [r for r in rows if r.get("ticker") and not r["ticker"].startswith("#")]


# ------------------------------------------------------------------ the background fill
def _paced(url: str, ttl: float, min_bytes: int):
    from ..cache import _cache
    if f"topic:{url}" not in _cache:
        wait = C.PACE - (time.time() - C._last_download[0])
        if wait > 0:
            time.sleep(wait)
        C._last_download[0] = time.time()
    return fetch_json(url, ttl, min_bytes=min_bytes)


def log_share() -> dict:
    """Today's memecoin sector market cap and the whole market's, appended once a day to the share log."""
    cats = _paced(CG_CATEGORIES, 6 * 3600, 100)
    meme = next((c for c in cats if c.get("id") == MEME_CATEGORY), None)
    total = (_paced(CG_GLOBAL, 6 * 3600, 50).get("data") or {}).get("total_market_cap", {}).get("usd")
    if not meme or not meme.get("market_cap") or not total:
        raise ValueError("no meme category or total market cap")
    row = {"date": time.strftime("%Y-%m-%d"), "meme_mcap": round(float(meme["market_cap"])), "total_mcap": round(float(total)),
           "meme_volume_24h": round(float(meme.get("volume_24h") or 0))}
    rows = share_log()
    if not rows or rows[-1]["date"] != row["date"]:
        SHARE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SHARE_LOG.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if not rows:
                w.writeheader()
            w.writerow(row)
    return row


def share_log() -> list[dict]:
    if not SHARE_LOG.exists():
        return []
    with SHARE_LOG.open(newline="") as f:
        return list(csv.DictReader(f))


def fill(pause_on_limit: float = 75.0) -> dict:
    """Background job: BTC, then each coin's 365 days, then the sector share, one CoinGecko call at a time. Returns {name: 'ok' | error}."""
    done = {}
    jobs = [("BTC", lambda: _paced(C.CG_VOLUME, C.TTL, 1000))] + \
           [(c["ticker"], (lambda cid: lambda: C.coin_chart(cid, live=True))(c["coingecko_id"])) for c in coins_list()] + [("share", log_share)]
    for name, job in jobs:
        for attempt in range(2):
            try:
                job()
                done[name] = "ok"
                break
            except Exception as e:
                done[name] = f"{type(e).__name__}: {str(e)[:80]}"
                if "429" in str(e) and attempt == 0:
                    time.sleep(pause_on_limit)
                else:
                    break
    from ..cache import _cache
    for k in [k for k in _cache if k.startswith(f"topic:{SLUG}:")]:      # the next page view rebuilds from the fresh data
        _cache.pop(k, None)
    return done


BACKGROUND = [fill]


# ------------------------------------------------------------------ payloads
def btc_series() -> tuple[pd.Series, pd.Series]:
    """BTC's daily price and market cap, from what either fill already has."""
    try:
        return C.parse_chart(json.loads(cached_only(C.CG_VOLUME)))
    except LookupError:
        return C.parse_chart(C.fetch_json(C.CG_VOLUME, C.TTL, min_bytes=1000))


def _change(s: pd.Series, days: int):
    if len(s) < 2:
        return None
    then = s.asof(s.index[-1] - pd.Timedelta(days=days))
    return _r(float(s.iloc[-1]) / float(then) - 1, 4) if then and not pd.isna(then) else None


def coin_now(c: dict, btc: pd.Series) -> dict:
    px, mc = C.coin_chart(c["coingecko_id"])
    both = pd.concat([px, btc], axis=1, join="inner").dropna()
    coin_px, btc_px = both.iloc[:, 0], both.iloc[:, 1]
    ratio = coin_px / btc_px
    r_coin, r_ratio, beta = C.rsi(coin_px), C.rsi(ratio), C.beta_to_btc(coin_px, btc_px)
    last = lambda s: _r(float(s.dropna().iloc[-1]), 1) if s.notna().any() else None
    return {"ticker": c["ticker"], "name": c["name"], "chain": c.get("chain", ""), "launched": c.get("launched", ""),
            "link": f"https://www.coingecko.com/en/coins/{c['coingecko_id']}",
            "kpi": {"price": _r(float(coin_px.iloc[-1]), 10), "date": str(coin_px.index[-1].date()), "change_24h": _change(coin_px, 1), "change_7d": _change(coin_px, 7),
                    "change_30d": _change(coin_px, 30), "change_1y": _r(float(coin_px.iloc[-1] / coin_px.iloc[0]) - 1, 4),
                    "from_high": _r(float(coin_px.iloc[-1] / coin_px.max()) - 1, 4), "market_cap": _r(float(mc.iloc[-1]), 0) if len(mc) else None,
                    "rsi": last(r_coin), "rsi_vs_btc": last(r_ratio), "beta": _r(beta, 2) if beta is not None else None, "vs_btc_90d": _change(ratio, 90)},
            "spark": _pts(coin_px.iloc[-90:], 10), "rebased": _pts(coin_px / coin_px.iloc[0] * 100, 2), "mcap": mc}


def _all_now() -> tuple[list[dict], pd.Series, pd.Series]:
    btc_px, btc_mc = btc_series()
    rows = []
    for c in coins_list():
        try:
            rows.append(coin_now(c, btc_px))
        except Exception as e:
            rows.append({"ticker": c["ticker"], "name": c["name"], "chain": c.get("chain", ""), "link": f"https://www.coingecko.com/en/coins/{c['coingecko_id']}",
                         "error": "loading in the background, back in a few minutes" if isinstance(e, LookupError) else type(e).__name__})
    return rows, btc_px, btc_mc


def _strip(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if k != "mcap"} for r in rows]


def _basket_now() -> dict:
    rows, btc_px, _ = _all_now()
    live = [r for r in rows if "kpi" in r]
    total = sum(r["kpi"]["market_cap"] or 0 for r in live)
    for r in live:
        r["kpi"]["share"] = _r((r["kpi"]["market_cap"] or 0) / total, 4) if total else None
    return {"coins": _strip(rows), "basket_mcap": _r(total, 0), "btc_rebased": _pts(btc_px / btc_px.iloc[0] * 100, 2),
            "as_of": max((r["kpi"]["date"] for r in live), default=None), "updated": int(time.time()),
            "stale": stale_info([C.CG_CHART.format(id=c["coingecko_id"]) for c in coins_list()] + [C.CG_VOLUME])}


def season_state(vs_btc_90d, rsi_vs_btc) -> tuple[str, int]:
    """'Meme season' when the basket has beaten BTC by 25%+ over 90 days or its RSI against BTC is 70+; 'out of season' when it trails
    by 25%+ and its RSI against BTC is under 50; else 'in between'. Lean +1 / -1 / 0."""
    if vs_btc_90d is None:
        return "no data", 0
    if vs_btc_90d >= HOT or (rsi_vs_btc or 0) >= 70:
        return "meme season", 1
    if vs_btc_90d <= COLD and (rsi_vs_btc if rsi_vs_btc is not None else 50) < 50:
        return "out of season", -1
    return "in between", 0


def _season_now() -> dict:
    rows, btc_px, btc_mc = _all_now()
    live = [r for r in rows if "kpi" in r]
    out: dict = {"coins_in": [r["ticker"] for r in live], "coins_missing": [r["ticker"] for r in rows if "kpi" not in r], "updated": int(time.time())}
    if live:
        mcs = pd.concat([r["mcap"] for r in live], axis=1, join="inner").dropna()
        basket = mcs.sum(axis=1)
        ratio = (basket / btc_mc.reindex(basket.index)).dropna()
        r_ratio = C.rsi(ratio)
        px = pd.concat([pd.Series({pd.to_datetime(t, unit="s"): v for t, v in r["rebased"]}) for r in live], axis=1, join="inner").dropna()
        ew = px.mean(axis=1)
        vs90, rsi_now = _change(ratio, 90), (_r(float(r_ratio.dropna().iloc[-1]), 1) if r_ratio.notna().any() else None)
        state, lean = season_state(vs90, rsi_now)
        out |= {"basket_mcap": _pts(basket, 0), "btc_mcap": _pts(btc_mc.reindex(basket.index).dropna(), 0), "ratio": _pts(ratio, 6), "rsi_vs_btc": _pts(r_ratio, 1),
                "equal_weight": _pts(ew, 2), "btc_rebased": _pts((btc_px / btc_px.asof(ew.index[0]) * 100).reindex(ew.index).dropna(), 2),
                "kpi": {"basket_mcap": _r(float(basket.iloc[-1]), 0), "ratio": _r(float(ratio.iloc[-1]), 6), "vs_btc_90d": vs90, "vs_btc_30d": _change(ratio, 30),
                        "rsi_vs_btc": rsi_now, "from_high": _r(float(ratio.iloc[-1] / ratio.max()) - 1, 4), "basket_1y": _r(float(basket.iloc[-1] / basket.iloc[0]) - 1, 4),
                        "state": state, "lean": lean, "date": str(basket.index[-1].date())}}
    log = share_log()
    out["share_log"] = [{"t": int(pd.Timestamp(r["date"]).timestamp()), "share": _r(float(r["meme_mcap"]) / float(r["total_mcap"]), 5),
                         "meme_mcap": float(r["meme_mcap"]), "volume": float(r.get("meme_volume_24h") or 0)} for r in log if float(r.get("total_mcap") or 0) > 0]
    out["rules"] = {"hot": HOT, "cold": COLD}
    out["stale"] = stale_info([C.CG_CHART.format(id=c["coingecko_id"]) for c in coins_list()] + [C.CG_VOLUME])
    return out


def READINGS() -> list[dict]:
    """The season tab's headline as it reads now (from cached data only)."""
    k = (ENDPOINTS["season"]() or {}).get("kpi")
    if not k:
        return []
    return [{"tab": "season", "key": "state", "label": "Meme season", "value": k["state"], "lean": k["lean"]},
            {"tab": "season", "key": "vs_btc_90d", "label": "Basket vs BTC, 90 days", "value": k["vs_btc_90d"],
             "lean": 1 if (k["vs_btc_90d"] or 0) > 0 else -1 if (k["vs_btc_90d"] or 0) < 0 else 0}]


def _cached_ep(name, fn, ttl=3600):
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"basket": _cached_ep("basket", _basket_now), "season": _cached_ep("season", _season_now)}
