"""BTC Cycles & Sector Rotation (/btc-cycles): the research doc as structured data, plus a live layer that checks its signals daily.

cycles      BTC price since 2010 (Coin Metrics community API), each cycle overlaid from its halving, drawdown from the running high,
            and the doc's cycle-anatomy table and bottom line
sectors     the doc's per-cycle sector tables (coins, low -> peak, multiple, burst window, metric) and the cross-cycle comparison
metrics     the doc's "common metrics of cycle winners" table with live versions of the measurable ones: DeFi TVL, stablecoin supply,
            Hyperliquid TVL and revenue, perp-DEX volume (all DefiLlama)
candidates  the doc's ranked 2026-27 candidates with an evidence series per candidate where one exists (live or hand-entered)
signals     the doc's six signals, each with a computed or hand-entered status

The research text lives in data/btc-cycles/research.json (every table on the page is rendered from it; edit it to update the research).
Hand-entered evidence (figures with no free API: RWA value, prediction-market volume, x402, launches per day, perp-DEX share, Google
Trends) in data/btc-cycles/evidence.csv. Live sources are cached a day and snapshotted; CoinGecko's dominance and volume have no free
history, so each day's reading is appended to a log in the snapshot folder and the chart grows from the deploy date.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..cache import _cached
from ..config import DATA_DIR, SNAP_DIR
from ._base import DAY, _pts, _r, fetch_json, manual, manual_rows, payload

SLUG = "btc-cycles"
CM = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=PriceUSD&start_time=2010-07-18&page_size=10000&frequency=1d"
LLAMA_TVL = "https://api.llama.fi/v2/historicalChainTvl"
LLAMA_STABLES = "https://stablecoins.llama.fi/stablecoincharts/all"
LLAMA_HL = "https://api.llama.fi/protocol/hyperliquid"
LLAMA_HL_REV = "https://api.llama.fi/summary/fees/hyperliquid?dataType=dailyRevenue"
LLAMA_PERPS = "https://api.llama.fi/overview/derivatives?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true"
CG_GLOBAL = "https://api.coingecko.com/api/v3/global"
CG_VOLUME = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=365&interval=daily"
SOURCES = [{"name": "The research doc (BTC Cycles & Sector Rotation)", "url": "https://claude.ai/artifact/5Z9ca6X7eka9R3XdxZKcb3", "cadence": "as revised"},
           {"name": "BTC price (Coin Metrics community data)", "url": "https://coinmetrics.io/community-network-data/", "cadence": "daily"},
           {"name": "DeFi TVL, stablecoin supply, Hyperliquid, perp DEX volume (DefiLlama)", "url": "https://defillama.com", "cadence": "daily"},
           {"name": "BTC dominance and spot volume (CoinGecko)", "url": "https://www.coingecko.com/en/global-charts", "cadence": "daily"}]
NOTES = ("Research, not investment advice. Pre-2024 cycle figures in the tables are approximate, as the doc says. Live series are free public data; "
         "the signal statuses are mechanical readings of the doc's rules, not a view.")
HALVINGS = [pd.Timestamp(d) for d in ("2012-11-28", "2016-07-09", "2020-05-11", "2024-04-19")]
NEXT_HALVING = pd.Timestamp("2028-04-15")
TTL = DAY
RESEARCH = DATA_DIR / SLUG / "research.json"
DOM_LOG = SNAP_DIR / "btc_dominance_log.csv"


# ------------------------------------------------------------------ research (the doc)
def research() -> dict:
    return _cached(f"topic:{SLUG}:research", 600, lambda: json.loads(RESEARCH.read_text(encoding="utf-8")))


# ------------------------------------------------------------------ live data
def parse_coinmetrics(j: dict) -> pd.Series:
    d = pd.DataFrame(j.get("data", []))
    s = pd.Series(pd.to_numeric(d["PriceUSD"], errors="coerce").to_numpy(), index=pd.to_datetime(d["time"]).dt.tz_localize(None).dt.normalize())
    return s.dropna().sort_index()


def price() -> pd.Series:
    return parse_coinmetrics(fetch_json(CM, TTL, min_bytes=1000))


def _ts_series(rows, key_t, key_v, unit="s") -> pd.Series:
    s = pd.Series({pd.to_datetime(int(r[key_t]), unit=unit): float(r[key_v]) for r in rows if r.get(key_v) is not None})
    return s.sort_index()


def defi_tvl() -> pd.Series:
    return _ts_series(fetch_json(LLAMA_TVL, TTL), "date", "tvl")


def stablecoins() -> pd.Series:
    rows = fetch_json(LLAMA_STABLES, TTL)
    return pd.Series({pd.to_datetime(int(r["date"]), unit="s"): float((r.get("totalCirculatingUSD") or {}).get("peggedUSD", 0)) for r in rows}).sort_index()


def hl_tvl() -> pd.Series:
    j = fetch_json(LLAMA_HL, TTL, min_bytes=1000)
    return _ts_series(j.get("tvl", []), "date", "totalLiquidityUSD")


def hl_revenue() -> pd.Series:
    j = fetch_json(LLAMA_HL_REV, TTL)
    return pd.Series({pd.to_datetime(int(t), unit="s"): float(v) for t, v in j.get("totalDataChart", [])}).sort_index()


def perps() -> tuple[pd.Series, list[dict]]:
    j = fetch_json(LLAMA_PERPS, TTL, min_bytes=1000)
    total = pd.Series({pd.to_datetime(int(t), unit="s"): float(v) for t, v in j.get("totalDataChart", [])}).sort_index()
    top = sorted((p for p in j.get("protocols", []) if p.get("total30d")), key=lambda p: -p["total30d"])[:8]
    return total, [{"name": p["name"], "volume_30d": _r(p["total30d"], 0), "share_30d": _r(p["total30d"] / sum(x["total30d"] for x in top), 4)} for p in top]


def coingecko_global() -> dict:
    """Today's BTC dominance and total volume, appended to a log on the volume so the chart grows from the first deploy."""
    j = fetch_json(CG_GLOBAL, 6 * 3600).get("data", {})
    dom, vol = j.get("market_cap_percentage", {}).get("btc"), j.get("total_volume", {}).get("usd")
    today = time.strftime("%Y-%m-%d")
    try:
        DOM_LOG.parent.mkdir(parents=True, exist_ok=True)
        rows = dominance_log()
        if dom is not None and (not rows or rows[-1]["date"] != today):
            with DOM_LOG.open("a", newline="") as f:
                w = csv.writer(f)
                if not rows:
                    w.writerow(["date", "btc_dominance", "total_volume_usd"])
                w.writerow([today, round(float(dom), 3), round(float(vol or 0))])
    except OSError:
        pass
    return {"dominance": _r(dom, 2), "total_volume": _r(vol, 0), "date": today}


def dominance_log() -> list[dict]:
    if not DOM_LOG.exists():
        return []
    with DOM_LOG.open(newline="") as f:
        return [r for r in csv.DictReader(f)]


def btc_volume() -> pd.Series:
    j = fetch_json(CG_VOLUME, TTL, min_bytes=1000)
    return pd.Series({pd.to_datetime(int(t), unit="ms").normalize(): float(v) for t, v in j.get("total_volumes", [])}).sort_index()


# ------------------------------------------------------------------ computations
def halving_overlay(px: pd.Series, before: int = 550, after: int = 730, step: int = 3) -> dict:
    """Each cycle's price divided by its price on halving day, by days since the halving: [[days, multiple], ...] per cycle."""
    out = {}
    for i, h in enumerate(HALVINGS + [NEXT_HALVING]):
        if h > px.index[-1]:
            continue
        base = px.asof(h)
        if not base or not np.isfinite(base):
            continue
        pts = []
        for d in range(-(before // step) * step, after + 1, step):         # a multiple of step, so day 0 (= 1.0) is always a point
            t = h + pd.Timedelta(days=d)
            if t < px.index[0] or t > px.index[-1]:
                continue
            v = px.asof(t)
            if v and np.isfinite(v):
                pts.append([d, _r(v / base, 4)])
        out[f"Cycle {i + 1} ({h.year})"] = pts
    return out


def drawdown(px: pd.Series) -> pd.Series:
    return px / px.cummax() - 1


def _weekly(s: pd.Series) -> pd.Series:
    return s.resample("W").last().dropna()


def rising_weeks(s: pd.Series) -> int:
    w = _weekly(s)
    n = 0
    for a, b in zip(w.iloc[-2::-1], w.iloc[::-1]):
        if b > a:
            n += 1
        else:
            break
    return n


# ------------------------------------------------------------------ endpoints
def _cycles_now() -> dict:
    R = research()
    peak, low = R["cycle_peak"], R["cycle_low"]
    out: dict = {"research": {"title": R["title"], "as_of": R["as_of"], "doc_url": R["doc_url"], "bottom_line": R["bottom_line"], "anatomy": R["anatomy"]},
                 "halvings": [int(h.timestamp()) for h in HALVINGS], "markers": [{**m, "ts": int(pd.Timestamp(m["date"]).timestamp())} for m in R["markers"]],
                 "next_halving": NEXT_HALVING.strftime("%Y-%m-%d"), "as_of": R["as_of"]}
    try:
        px = price()
    except Exception as e:                                # no price feed: the research still renders, the charts say why
        out.update({"price": None, "price_error": type(e).__name__, "now": None, "stale": {}, "updated": int(time.time())})
        return out
    now, t_now = float(px.iloc[-1]), px.index[-1]
    ma200 = px.rolling(200).mean()
    live = payload({"price": lambda: _pts(_weekly(px), 2), "price_recent": lambda: _pts(px[px.index >= t_now - pd.Timedelta(days=730)], 2),
                    "ma200": lambda: _pts(_weekly(ma200), 2), "overlay": lambda: halving_overlay(px), "drawdown": lambda: _pts(_weekly(drawdown(px)), 4)},
                   sources=[CM], as_of=str(t_now.date()))
    out.update(live)
    out["now"] = {"price": _r(now, 0), "date": str(t_now.date()), "vs_peak": _r(now / peak["price"] - 1, 4), "vs_low": _r(now / low["price"] - 1, 4),
                  "vs_ma200": _r(now / float(ma200.iloc[-1]) - 1, 4) if np.isfinite(ma200.iloc[-1]) else None,
                  "days_since_halving": (t_now - HALVINGS[-1]).days, "days_to_next_halving": (NEXT_HALVING - t_now).days,
                  "months_since_peak": round((t_now - pd.Timestamp(peak["date"])).days / 30.4, 1), "drawdown_now": _r(float(drawdown(px).iloc[-1]), 4)}
    return out


def _sectors_now() -> dict:
    R = research()
    return {"cycles": R["cycles"], "cross_cycle": R["cross_cycle"], "as_of": R["as_of"], "stale": {}, "updated": int(time.time())}


def _metrics_now() -> dict:
    R = research()
    out = payload({"defi_tvl": lambda: _pts(_weekly(defi_tvl()), 0), "stablecoins": lambda: _pts(_weekly(stablecoins()), 0),
                   "hl_tvl": lambda: _pts(_weekly(hl_tvl()), 0), "hl_revenue_30d": lambda: _pts(hl_revenue().rolling(30).sum().dropna().iloc[::7], 0),
                   "perp_volume_30d": lambda: _pts(perps()[0].rolling(30).sum().dropna().iloc[::7], 0), "perp_top": lambda: perps()[1]},
                  sources=[LLAMA_TVL, LLAMA_STABLES, LLAMA_HL, LLAMA_HL_REV, LLAMA_PERPS])
    out["latest"] = {k: (out[k][-1][1] if out.get(k) else None) for k in ("defi_tvl", "stablecoins", "hl_tvl", "hl_revenue_30d", "perp_volume_30d")}
    out["research"] = R["metrics"]
    out["as_of"] = max((pd.Timestamp(out[k][-1][0], unit="s").strftime("%Y-%m-%d") for k in out["latest"] if out.get(k)), default=None)
    return out


def _candidates_now() -> dict:
    R = research()
    ev = manual(SLUG, "evidence")
    ev = ev if isinstance(ev, dict) else {}
    out = payload({"evidence": lambda: {k: _pts(v, 2) for k, v in ev.items()},
                   "perp_volume_30d": lambda: _pts(perps()[0].rolling(30).sum().dropna().iloc[::7], 0),
                   "hl_revenue_30d": lambda: _pts(hl_revenue().rolling(30).sum().dropna().iloc[::7], 0),
                   "stablecoins": lambda: _pts(_weekly(stablecoins()), 0)},
                  sources=[LLAMA_PERPS, LLAMA_HL_REV, LLAMA_STABLES])
    out["research"] = R["candidates"]
    out["rows_cited"] = sorted(manual_rows(SLUG, "evidence"), key=lambda r: r["date"], reverse=True)[:30]
    out["as_of"] = R["as_of"]
    return out


def _signals_now() -> dict:
    R = research()
    ev = manual(SLUG, "evidence")
    ev = ev if isinstance(ev, dict) else {}
    status = []

    def add(name, state, reading, note=""):
        status.append({"signal": name, "state": state, "reading": reading, "note": note})

    def latest(series_name):
        s = ev.get(series_name)
        return (float(s.iloc[-1]), str(s.index[-1].date())) if s is not None and len(s) else (None, None)
    # 1 launches/day (hand-entered)
    v, d = latest("Launchpad launches per day")
    add("New issuance primitive > 1,000 launches/day", "firing" if v and v > 1000 else "not yet" if v is not None else "no data",
        f"{v:,.0f}/day ({d})" if v is not None else "add rows to evidence.csv (series: Launchpad launches per day)", "hand-entered")
    # 2 stablecoin supply rising 8+ weeks
    try:
        s = stablecoins(); n = rising_weeks(s)
        add("Stablecoin supply up 8+ weeks running", "firing" if n >= 8 else "not yet", f"{n} weeks rising; ${s.iloc[-1] / 1e9:,.0f}bn", "DefiLlama, total supply; the doc asks per chain, which DefiLlama's chain endpoints add later")
    except Exception as e:
        add("Stablecoin supply up 8+ weeks running", "no data", type(e).__name__)
    # 3 perp revenue rising while price falls
    try:
        rev = hl_revenue(); px = price()
        r_now, r_prev = rev.iloc[-90:].sum(), rev.iloc[-180:-90].sum()
        p_chg = px.iloc[-1] / px.asof(px.index[-1] - pd.Timedelta(days=90)) - 1
        add("Perp-DEX revenue rising while BTC falls", "firing" if r_now > r_prev and p_chg < 0 else "not yet",
            f"Hyperliquid revenue last 90d ${r_now / 1e6:,.0f}m vs ${r_prev / 1e6:,.0f}m before; BTC {p_chg * 100:+.0f}% over 90d", "DefiLlama + Coin Metrics")
    except Exception as e:
        add("Perp-DEX revenue rising while BTC falls", "no data", type(e).__name__)
    # 4 spot volume >= $10bn/day
    try:
        vol = btc_volume(); avg = vol.iloc[-30:].mean()
        add("BTC spot volume sustainably above $10bn/day", "firing" if avg >= 10e9 else "not yet", f"30-day average ${avg / 1e9:,.1f}bn/day", "CoinGecko, all exchanges; the doc's figure is spot + ETF")
    except Exception as e:
        add("BTC spot volume sustainably above $10bn/day", "no data", type(e).__name__)
    # 5 dominance rolling over from ~60% after a new high
    try:
        g = coingecko_global(); log = dominance_log()
        hi = max((float(r["btc_dominance"]) for r in log), default=g["dominance"] or 0)
        dom = g["dominance"]
        state = "firing" if dom is not None and hi >= 58 and dom < hi - 3 else "not yet"
        add("BTC dominance rolling over from ~60% after a new high", state, f"{dom:.1f}% now; highest logged {hi:.1f}% (log since {log[0]['date'] if log else g['date']})",
            "CoinGecko; the log starts on first deploy, so 'highest' is only meaningful after a few months")
    except Exception as e:
        add("BTC dominance rolling over from ~60% after a new high", "no data", type(e).__name__)
    # 6 Google Trends (hand-entered)
    v, d = latest("Google Trends: sector search index")
    add("Google Trends for a sector name rising from a low base", "watch" if v is not None else "no data",
        f"index {v:,.0f} ({d})" if v is not None else "add rows to evidence.csv (series: Google Trends: sector search index)", "hand-entered; entry when rising from a low base, exit at a multi-year high")
    out = {"status": status, "research": R["signals"], "as_of": time.strftime("%Y-%m-%d"), "stale": {}, "updated": int(time.time())}
    try:
        log = dominance_log()
        out["dominance_log"] = [[int(pd.Timestamp(r["date"]).timestamp()), float(r["btc_dominance"])] for r in log]
        out["volume"] = _pts(btc_volume().rolling(30).mean().dropna(), 0)
    except Exception:
        pass
    return out


def _cached_ep(name, fn, ttl=6 * 3600):
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"cycles": _cached_ep("cycles", _cycles_now), "sectors": _cached_ep("sectors", _sectors_now, 600), "metrics": _cached_ep("metrics", _metrics_now),
             "candidates": _cached_ep("candidates", _candidates_now), "signals": _cached_ep("signals", _signals_now, 3600)}
