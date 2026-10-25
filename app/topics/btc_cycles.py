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
CG_CHART = "https://api.coingecko.com/api/v3/coins/{id}/market_chart?vs_currency=usd&days=365&interval=daily"
COINS = DATA_DIR / SLUG / "coins.csv"
SCENARIOS = DATA_DIR / SLUG / "scenarios.json"
PACE = 2.2                                 # seconds between real CoinGecko downloads (public limit ~30/min)
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


# ------------------------------------------------------------------ candidate coins (price, RSI vs BTC, market cap, scenario projection)
_last_download = [0.0]


def coins_list() -> list[dict]:
    with COINS.open(newline="", encoding="utf-8") as f:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    return [r for r in rows if r.get("ticker") and not r["rank"].startswith("#")]


def scenarios() -> dict:
    return _cached(f"topic:{SLUG}:scenarios", 600, lambda: json.loads(SCENARIOS.read_text(encoding="utf-8")))


def parse_chart(j: dict) -> tuple[pd.Series, pd.Series]:
    px = pd.Series({pd.to_datetime(int(t), unit="ms").normalize(): float(v) for t, v in j.get("prices", [])}).sort_index()
    mc = pd.Series({pd.to_datetime(int(t), unit="ms").normalize(): float(v) for t, v in j.get("market_caps", [])}).sort_index()
    return px[~px.index.duplicated(keep="last")], mc[~mc.index.duplicated(keep="last")]


def coin_chart(cg_id: str) -> tuple[pd.Series, pd.Series]:
    """A coin's daily price and market cap for the last 365 days; real downloads are paced so a burst of 28 coins stays under CoinGecko's limit."""
    from ..cache import _cache
    url = CG_CHART.format(id=cg_id)
    if f"topic:{url}" not in _cache:
        wait = PACE - (time.time() - _last_download[0])
        if wait > 0:
            time.sleep(wait)
        _last_download[0] = time.time()
    return parse_chart(fetch_json(url, TTL, min_bytes=1000))


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    ad = dn.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    return (100 - 100 / (1 + au / ad.replace(0, np.nan))).fillna(100).where(au.notna())


def beta_to_btc(coin: pd.Series, btc: pd.Series) -> float | None:
    r = pd.concat([np.log(coin).diff(), np.log(btc).diff()], axis=1, join="inner").dropna()
    if len(r) < 60 or r.iloc[:, 1].var() == 0:
        return None
    b = float(np.polyfit(r.iloc[:, 1], r.iloc[:, 0], 1)[0])
    return float(min(3.0, max(0.5, b)))


def project(price_now: float, btc_now: float, beta: float, sc: dict) -> list[dict]:
    """Bear / base / bull price at each scenario date: price_now x (btc_scenario / btc_now) ^ beta."""
    out = []
    for s in sc["scenarios"]:
        row = {"date": s["date"], "label": s["label"]}
        for k in ("bear", "base", "bull"):
            row[k] = _r(price_now * (s[k]["btc"] / btc_now) ** beta, 4)
            row[k + "_btc"] = s[k]["btc"]
        out.append(row)
    return out


def _coin_full(c: dict, btc: pd.Series) -> dict:
    px, mc = coin_chart(c["coingecko_id"])
    both = pd.concat([px, btc], axis=1, join="inner").dropna()
    coin_px, btc_px = both.iloc[:, 0], both.iloc[:, 1]
    ratio = coin_px / btc_px
    beta = beta_to_btc(coin_px, btc_px)
    now, btc_now = float(coin_px.iloc[-1]), float(btc_px.iloc[-1])
    supply = float(mc.iloc[-1] / px.iloc[-1]) if len(mc) and px.iloc[-1] else None
    d90 = coin_px.index[-1] - pd.Timedelta(days=90)
    vs_btc_90 = _r(ratio.iloc[-1] / ratio.asof(d90) - 1, 4) if ratio.asof(d90) else None
    r_coin, r_ratio = rsi(coin_px), rsi(ratio)
    proj = project(now, btc_now, beta, scenarios()) if beta is not None else []
    return {"ticker": c["ticker"], "name": c["name"], "rank": int(c["rank"]), "sector": c["sector"], "note": c.get("note", ""),
            "links": {"coinmarketcap": f"https://coinmarketcap.com/currencies/{c['cmc_slug']}/" if c.get("cmc_slug") else None,
                      "defillama": f"https://defillama.com/protocol/{c['defillama_slug']}" if c.get("defillama_slug") else None,
                      "coingecko": f"https://www.coingecko.com/en/coins/{c['coingecko_id']}"},
            "kpi": {"price": _r(now, 6), "date": str(coin_px.index[-1].date()), "change_24h": _r(now / float(coin_px.iloc[-2]) - 1, 4) if len(coin_px) > 1 else None,
                    "change_1y": _r(now / float(coin_px.iloc[0]) - 1, 4), "market_cap": _r(float(mc.iloc[-1]), 0) if len(mc) else None,
                    "rsi": _r(float(r_coin.dropna().iloc[-1]), 1) if r_coin.notna().any() else None,
                    "rsi_vs_btc": _r(float(r_ratio.dropna().iloc[-1]), 1) if r_ratio.notna().any() else None,
                    "beta": _r(beta, 2) if beta is not None else None, "vs_btc_90d": vs_btc_90,
                    "base_2027": proj[0]["base"] if proj else None, "base_2028": proj[1]["base"] if len(proj) > 1 else None},
            "spark": _pts(coin_px.iloc[-90:], 6),
            "series": {"price": _pts(coin_px, 6), "btc_indexed": _pts(btc_px / btc_px.iloc[0] * coin_px.iloc[0], 6), "ratio": _pts(ratio, 10),
                       "rsi": _pts(r_coin, 1), "rsi_vs_btc": _pts(r_ratio, 1), "market_cap": _pts(mc, 0)},
            "projection": proj, "implied_mcap_base": [{"date": p["date"], "mcap": _r(p["base"] * supply, 0)} for p in proj] if supply else []}


def btc_chart() -> pd.Series:
    return parse_chart(fetch_json(CG_VOLUME, TTL, min_bytes=1000))[0]


def _coins_now() -> dict:
    """Every candidate coin's KPI strip and sparkline (the full charts load per coin). A coin whose fetch fails is listed with its error."""
    sc = scenarios()
    out = {"coins": [], "scenarios": sc, "as_of": None, "stale": {}, "updated": int(time.time())}
    try:
        btc = btc_chart()
    except Exception as e:
        out["btc_error"] = type(e).__name__
        out["coins"] = [{"ticker": c["ticker"], "name": c["name"], "rank": int(c["rank"]), "sector": c["sector"], "error": type(e).__name__,
                         "links": {"coinmarketcap": f"https://coinmarketcap.com/currencies/{c['cmc_slug']}/" if c.get("cmc_slug") else None}} for c in coins_list()]
        return out
    for c in coins_list():
        try:
            full = _coin_full(c, btc)
            out["coins"].append({k: full[k] for k in ("ticker", "name", "rank", "sector", "note", "links", "kpi", "spark")})
        except Exception as e:
            out["coins"].append({"ticker": c["ticker"], "name": c["name"], "rank": int(c["rank"]), "sector": c["sector"], "note": c.get("note", ""), "error": type(e).__name__,
                                 "links": {"coinmarketcap": f"https://coinmarketcap.com/currencies/{c['cmc_slug']}/" if c.get("cmc_slug") else None,
                                           "defillama": f"https://defillama.com/protocol/{c['defillama_slug']}" if c.get("defillama_slug") else None}})
    out["btc_now"] = _r(float(btc.iloc[-1]), 0)
    out["as_of"] = max((c["kpi"]["date"] for c in out["coins"] if "kpi" in c), default=None)
    from ._base import stale_info
    out["stale"] = stale_info([CG_CHART.format(id=c["coingecko_id"]) for c in coins_list()] + [CG_VOLUME])
    return out


def _coin_now(ticker: str) -> dict:
    c = next((x for x in coins_list() if x["ticker"] == ticker), None)
    if c is None:
        raise ValueError("unknown coin")
    out = _coin_full(c, btc_chart())
    from ._base import stale_info
    out["stale"] = stale_info([CG_CHART.format(id=c["coingecko_id"]), CG_VOLUME])
    out["as_of"] = out["kpi"]["date"]
    return out


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
             "candidates": _cached_ep("candidates", _candidates_now), "signals": _cached_ep("signals", _signals_now, 3600),
             "coins": _cached_ep("coins", _coins_now)}
ENDPOINTS.update({f"coin-{c['ticker'].lower()}": _cached_ep(f"coin-{c['ticker'].lower()}", (lambda t: lambda: _coin_now(t))(c["ticker"])) for c in coins_list()})
