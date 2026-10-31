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
# DefiLlama made its derivatives (perp volume) endpoints paid in 2026 (402 from the free API); spot-DEX volume and per-protocol fees are free
LLAMA_DEXS = "https://api.llama.fi/overview/dexs?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true"
LLAMA_HL_FEES = "https://api.llama.fi/summary/fees/hyperliquid?dataType=dailyFees"
CG_GLOBAL = "https://api.coingecko.com/api/v3/global"
CG_VOLUME = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=365&interval=daily"
CG_CHART = "https://api.coingecko.com/api/v3/coins/{id}/market_chart?vs_currency=usd&days=365&interval=daily"
COINS = DATA_DIR / SLUG / "coins.csv"
SCENARIOS = DATA_DIR / SLUG / "scenarios.json"
NOTES_FILE = DATA_DIR / SLUG / "coin_notes.json"
PACE = 13.0                                # seconds between CoinGecko downloads in the background fill (public limit is a few calls a minute)
SOURCES = [{"name": "The research doc (BTC Cycles & Sector Rotation)", "url": "https://claude.ai/artifact/5Z9ca6X7eka9R3XdxZKcb3", "cadence": "as revised"},
           {"name": "BTC price (Coin Metrics community data)", "url": "https://coinmetrics.io/community-network-data/", "cadence": "daily"},
           {"name": "DeFi TVL, stablecoin supply, Hyperliquid TVL, fees and revenue, DEX volume (DefiLlama free API)", "url": "https://defillama.com", "cadence": "daily"},
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


def hl_fees() -> pd.Series:
    j = fetch_json(LLAMA_HL_FEES, TTL)
    return pd.Series({pd.to_datetime(int(t), unit="s"): float(v) for t, v in j.get("totalDataChart", [])}).sort_index()


def dexs() -> tuple[pd.Series, list[dict]]:
    """Spot DEX volume, all chains (DefiLlama, free), and the top protocols by 30-day volume."""
    j = fetch_json(LLAMA_DEXS, TTL, min_bytes=1000)
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


def coin_notes() -> dict:
    return _cached(f"topic:{SLUG}:notes", 600, lambda: json.loads(NOTES_FILE.read_text(encoding="utf-8")) if NOTES_FILE.exists() else {"coins": {}})


def stands_out(k: dict, peers: list[dict]) -> list[str]:
    """Plain sentences on what is unusual about a coin today, from its live numbers and how they rank among the other candidates."""
    out = []
    if k.get("rsi_vs_btc") is not None:
        if k["rsi_vs_btc"] >= 70:
            out.append(f"Running hot against BTC (RSI vs BTC {k['rsi_vs_btc']:.0f}).")
        elif k["rsi_vs_btc"] <= 30:
            out.append(f"Washed out against BTC (RSI vs BTC {k['rsi_vs_btc']:.0f}).")
    v = k.get("vs_btc_90d")
    vals = sorted(x["vs_btc_90d"] for x in peers if x.get("vs_btc_90d") is not None)
    if v is not None and len(vals) >= 8:
        q = sum(x <= v for x in vals) / len(vals)
        if q >= 0.85:
            out.append(f"Among the strongest candidates over 90 days: {v * 100:+.0f}% against BTC.")
        elif q <= 0.15:
            out.append(f"Among the weakest candidates over 90 days: {v * 100:+.0f}% against BTC.")
    if k.get("from_high") is not None:
        if k["from_high"] > -0.1:
            out.append("Within 10% of its 1-year high.")
        elif k["from_high"] < -0.7:
            out.append(f"{-k['from_high'] * 100:.0f}% below its 1-year high.")
    b = k.get("beta")
    if b is not None:
        if b >= 2:
            out.append(f"High beta ({b:.1f}): moves about {b:.1f}x BTC's daily moves, so its projection band is wide.")
        elif b <= 0.8:
            out.append(f"Low beta ({b:.1f}): has moved less than BTC, so its projection band is narrow.")
    mcs = sorted((x["market_cap"] for x in peers if x.get("market_cap")), reverse=True)
    if k.get("market_cap") and mcs:
        out.append(f"Market cap rank {mcs.index(k['market_cap']) + 1} of {len(mcs)} candidates.")
    return out


def parse_chart(j: dict) -> tuple[pd.Series, pd.Series]:
    px = pd.Series({pd.to_datetime(int(t), unit="ms").normalize(): float(v) for t, v in j.get("prices", [])}).sort_index()
    mc = pd.Series({pd.to_datetime(int(t), unit="ms").normalize(): float(v) for t, v in j.get("market_caps", [])}).sort_index()
    return px[~px.index.duplicated(keep="last")], mc[~mc.index.duplicated(keep="last")]


def coin_chart(cg_id: str, live: bool = False) -> tuple[pd.Series, pd.Series]:
    """A coin's daily price and market cap for the last 365 days. Pages read what the background fill already has (live=False:
    memory or snapshot, LookupError if never fetched); the fill downloads (live=True), paced and backing off on 429."""
    from ..cache import _cache
    from ._base import cached_only
    url = CG_CHART.format(id=cg_id)
    if not live:
        return parse_chart(json.loads(cached_only(url)))
    if f"topic:{url}" not in _cache:
        wait = PACE - (time.time() - _last_download[0])
        if wait > 0:
            time.sleep(wait)
        _last_download[0] = time.time()
    return parse_chart(fetch_json(url, TTL, min_bytes=1000))


# ------------------------------------------------------------------ sector leaders: the largest token of each sector, candidate or not
CG_MARKETS = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&per_page=100&page=1"


def leader_ids() -> list[str]:
    cfg = json.loads((DATA_DIR / SLUG / "sector_status.json").read_text(encoding="utf-8"))
    return sorted({i for s in cfg["sectors"] for i in s.get("benchmarks", [])})


def classification() -> dict:
    f = DATA_DIR / SLUG / "classification.json"
    return json.loads(f.read_text(encoding="utf-8")).get("coins", {}) if f.exists() else {}


def sector_check(rank: int, categories: list[str]) -> dict | None:
    """Does CoinGecko file the coin under its sector? {ok, matched, categories}; None when the categories are not fetched yet.
    A sector's `cg_match` (sector_status.json) lists substrings of CoinGecko category names that count as that sector."""
    if not categories:
        return None
    cfg = json.loads((DATA_DIR / SLUG / "sector_status.json").read_text(encoding="utf-8"))
    keys = next((s.get("cg_match", []) for s in cfg["sectors"] if s["rank"] == rank), [])
    hit = [c for c in categories if any(k.lower() in c.lower() for k in keys)]
    return {"ok": bool(hit), "matched": hit[:4], "categories": [c for c in categories if not c.lower().endswith(" ecosystem") and "portfolio" not in c.lower()][:12]}


def sector_leaders(coins: list[dict]) -> dict:
    """{rank: {name, symbol, market_cap, candidate}}: the largest market cap among a sector's candidates and its benchmark tokens.
    Benchmarks come from one CoinGecko markets call made by the background fill; without it, the largest candidate."""
    from ._base import cached_only
    cfg = json.loads((DATA_DIR / SLUG / "sector_status.json").read_text(encoding="utf-8"))
    try:
        mk = {m["id"]: m for m in json.loads(cached_only(CG_MARKETS.format(ids=",".join(leader_ids()))))}
    except Exception:
        mk = {}
    out = {}
    for s in cfg["sectors"]:
        pool = [{"name": c["name"], "symbol": c["ticker"], "market_cap": c["kpi"]["market_cap"], "candidate": True}
                for c in coins if c.get("rank") == s["rank"] and c.get("kpi", {}).get("market_cap")]
        tick = {c["symbol"] for c in pool}
        for i in s.get("benchmarks", []):
            m = mk.get(i)
            if m and m.get("market_cap") and m["symbol"].upper() not in tick:
                pool.append({"name": m["name"], "symbol": m["symbol"].upper(), "market_cap": float(m["market_cap"]), "candidate": False})
        if pool:
            out[s["rank"]] = max(pool, key=lambda x: x["market_cap"])
    return out


# ------------------------------------------------------------------ per-coin fundamentals: TVL, fees, unlock schedule, supply
LLAMA_PROTO = "https://api.llama.fi/protocol/{slug}"
LLAMA_FEES = "https://api.llama.fi/summary/fees/{slug}?dataType=dailyFees"
LLAMA_CHAIN_TVL = "https://api.llama.fi/v2/historicalChainTvl/{chain}"
LLAMA_EMISSIONS = "https://defillama-datasets.llama.fi/emissions/{slug}"         # the free dataset; api.llama.fi/emission is paid (402)
CG_DETAIL = "https://api.coingecko.com/api/v3/coins/{id}?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false"
FUND_DIR = SNAP_DIR / "btc_fundamentals"                                          # one compact file per coin, written by the background fill


def parse_tvl(j) -> pd.Series:
    """Protocol TVL ({"tvl": [{"date", "totalLiquidityUSD"}]}) or chain TVL ([{"date", "tvl"}]), daily."""
    rows = j.get("tvl") if isinstance(j, dict) else j
    s = pd.Series({pd.to_datetime(int(r["date"]), unit="s").normalize(): float(r.get("totalLiquidityUSD", r.get("tvl")) or 0) for r in rows or []})
    return s[~s.index.duplicated(keep="last")].sort_index()


def parse_fees(j: dict) -> pd.Series:
    s = pd.Series({pd.to_datetime(int(t), unit="s").normalize(): float(v or 0) for t, v in (j or {}).get("totalDataChart") or []})
    return s[~s.index.duplicated(keep="last")].sort_index()


def parse_emissions(j: dict) -> pd.Series:
    """Total unlocked supply over time, past and scheduled: the sum over every allocation of its cumulative `unlocked`."""
    parts = []
    for alloc in (((j or {}).get("documentedData") or {}).get("data") or []):
        pts = {pd.to_datetime(int(p["timestamp"]), unit="s").normalize(): float(p.get("unlocked") or 0) for p in alloc.get("data") or [] if p.get("timestamp") is not None}
        if pts:
            parts.append(pd.Series(pts).sort_index())
    if not parts:
        raise ValueError("emissions: no documented allocations")
    idx = sorted(set().union(*[p.index for p in parts]))
    return sum(p.reindex(idx).ffill().fillna(0) for p in parts).sort_index()


def _optional_json(url: str):
    """For sources a coin may simply not have (an unlock schedule, a child protocol's fees): a plain download, so a 404 is not
    recorded as a failing source in /api/health."""
    from ._base import _download
    return json.loads(_download(url, 60))


def _llama_json(url: str):
    """A DefiLlama download used once by the fill: parsed, then dropped from memory (protocol files run to megabytes; the disk snapshot stays)."""
    from ..cache import _cache
    try:
        return fetch_json(url, TTL, min_bytes=200)
    finally:
        _cache.pop(f"topic:{url}", None)


def _llama_slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-").replace("--", "-")


def fill_fundamentals(c: dict) -> dict:
    """Download one coin's fundamentals and keep a compact copy (daily TVL and fees for 400 days, the unlock schedule weekly to its end,
    supply now). Every part is optional; what failed is recorded. CoinGecko is paced like the price fill; DefiLlama is not rate-limited."""
    out, err = {"ticker": c["ticker"], "updated": int(time.time()), "sources": {}}, {}
    slug, chain = (c.get("defillama_slug") or "").strip(), (c.get("llama_chain") or "").strip()
    cut = pd.Timestamp.now().normalize() - pd.Timedelta(days=400)
    keep = lambda s: _pts(s[s.index >= cut], 2)
    try:
        url = LLAMA_PROTO.format(slug=slug) if slug else LLAMA_CHAIN_TVL.format(chain=chain) if chain else None
        if url:
            out["tvl"], out["sources"]["tvl"] = keep(parse_tvl(_llama_json(url))), url
    except Exception as e:
        err["tvl"] = f"{type(e).__name__}: {str(e)[:80]}"
    try:
        url = LLAMA_FEES.format(slug=slug or _llama_slug(chain)) if (slug or chain) else None
        if url:
            j = _llama_json(url)
            fees = parse_fees(j)
            for child in ([] if len(fees) else (j.get("childProtocols") or [])):       # a parent protocol carries no daily history; its children do
                name = child if isinstance(child, str) else (child.get("slug") or child.get("name") or "")
                try:
                    url = LLAMA_FEES.format(slug=_llama_slug(name))
                    fees = parse_fees(_optional_json(url))
                    if len(fees):
                        break
                except Exception:
                    continue
            if len(fees):
                out["fees"], out["sources"]["fees"] = keep(fees), url
    except Exception as e:
        if getattr(getattr(e, "response", None), "status_code", None) in (400, 404):   # DefiLlama tracks no fees for it (Babylon): not a failing source
            from ._base import HEALTH
            HEALTH.pop(url, None)
            err["fees"] = "none on DefiLlama"
        else:
            err["fees"] = f"{type(e).__name__}: {str(e)[:80]}"
    for key in [k for k in dict.fromkeys([slug, c["coingecko_id"]]) if k]:
        url = LLAMA_EMISSIONS.format(slug=key)
        try:
            sched = parse_emissions(_optional_json(url))
            out["schedule"], out["sources"]["schedule"] = _pts(sched.resample("W").last().dropna(), 0), url
            break
        except Exception as e:
            err["schedule"] = f"{type(e).__name__}: {str(e)[:80]}"
    if "schedule" in out:
        err.pop("schedule", None)
    try:
        url = CG_DETAIL.format(id=c["coingecko_id"])
        from ..cache import _cache
        if f"topic:{url}" not in _cache:
            wait = PACE - (time.time() - _last_download[0])
            if wait > 0:
                time.sleep(wait)
            _last_download[0] = time.time()
        j = fetch_json(url, TTL, min_bytes=500)
        md = j.get("market_data") or {}
        out["supply"] = {k: md.get(k) for k in ("circulating_supply", "total_supply", "max_supply")}
        out["categories"] = [c for c in (j.get("categories") or []) if c][:40]          # CoinGecko's own classification, checked against the sector
        out["sources"]["supply"] = f"https://www.coingecko.com/en/coins/{c['coingecko_id']}"
    except Exception as e:
        err["supply"] = f"{type(e).__name__}: {str(e)[:80]}"
    out["errors"] = err
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    (FUND_DIR / f"{c['ticker']}.json").write_text(json.dumps(out))
    return out


def fundamentals(ticker: str) -> dict:
    f = FUND_DIR / f"{ticker}.json"
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def _ser(pts) -> pd.Series:
    return pd.Series({pd.to_datetime(int(t), unit="s"): v for t, v in pts or []}, dtype=float).sort_index()


def fund_factors(fd: dict, px: pd.Series, mc: pd.Series, dates: list[str]) -> dict:
    """Indicators and the two projection factors for one coin.
    dilution(T) = supply now / supply at T: from the unlock schedule when there is one, else from the past year's supply growth (at most
    50% a year) carried forward and capped at max (or total) supply; 1 when neither a schedule nor a supply cap is known. valuation = (1-year median price-to-fees / price-to-fees now) ^ 0.5, clamped to 0.67-1.5:
    half-way back to the coin's own usual multiple; price-to-TVL when there are no fees; 1 when neither exists."""
    out: dict = {"series": {}, "kpi": {}}
    now = px.index[-1]
    circ = (mc / px).replace([np.inf, -np.inf], np.nan).dropna()
    out["series"]["supply"] = _pts(circ, 0)
    fees, tvl = _ser(fd.get("fees")), _ser(fd.get("tvl"))
    K = out["kpi"]
    basis, ratio_now, ratio_med = None, None, None
    if len(fees) >= 60:
        f30 = fees.rolling(30).sum().dropna()
        out["series"]["fees_30d"] = _pts(f30.iloc[::7], 0)
        pf = (mc / (f30.reindex(mc.index, method="ffill") * 365 / 30)).replace([np.inf, -np.inf], np.nan).dropna()
        pf = pf[pf > 0]
        K["fees_30d"], K["fees_annual"] = _r(float(f30.iloc[-1]), 0), _r(float(f30.iloc[-1] * 365 / 30), 0)
        if len(pf) >= 30:
            K["p_fees"], K["p_fees_median"] = _r(float(pf.iloc[-1]), 1), _r(float(pf.median()), 1)
            out["series"]["p_fees"] = _pts(pf, 2)
            basis, ratio_now, ratio_med = "price-to-fees", float(pf.iloc[-1]), float(pf.median())
    if len(tvl) >= 30:
        out["series"]["tvl"] = _pts(tvl.iloc[::7] if len(tvl) > 120 else tvl, 0)
        K["tvl"] = _r(float(tvl.iloc[-1]), 0)
        pt = (mc / tvl.reindex(mc.index, method="ffill")).replace([np.inf, -np.inf], np.nan).dropna()
        pt = pt[pt > 0]
        if len(pt) >= 30:
            K["p_tvl"], K["p_tvl_median"] = _r(float(pt.iloc[-1]), 2), _r(float(pt.median()), 2)
            if basis is None:
                basis, ratio_now, ratio_med = "price-to-TVL", float(pt.iloc[-1]), float(pt.median())
    tilt = float(np.clip((ratio_med / ratio_now) ** 0.5, 0.67, 1.5)) if basis and ratio_now and ratio_med else 1.0
    sup = fd.get("supply") or {}
    cap = sup.get("max_supply") or sup.get("total_supply")
    c_now = float(circ.iloc[-1]) if len(circ) else sup.get("circulating_supply")
    if c_now and cap:
        K["unlocked_share"] = _r(min(1.0, c_now / float(cap)), 3)
    sched = _ser(fd.get("schedule"))
    dil, how = {}, None
    if len(sched) >= 4 and sched.asof(now) and sched.iloc[-1] > 0:
        # DefiLlama's "unlocked" and CoinGecko's circulating supply count differently, so the schedule supplies the tokens added
        # between now and the date, which go on top of today's circulating supply, capped at max supply
        how = "unlock schedule (DefiLlama), added to circulating supply" + (" and capped at max supply" if cap else "")
        s_now = float(sched.asof(now))
        out["series"]["schedule"] = fd.get("schedule")
        added = lambda t: max(0.0, float(sched.asof(t) if t <= sched.index[-1] else sched.iloc[-1]) - s_now)
        base_c = float(c_now) if c_now else s_now
        c_at = lambda t: min(base_c + added(t), float(cap)) if cap else base_c + added(t)
        K["unlock_12m"] = _r(c_at(now + pd.Timedelta(days=365)) / base_c - 1, 3)
        for d in dates:
            dil[d] = min(1.0, base_c / c_at(pd.Timestamp(d)))
    elif len(circ) > 200 and c_now and cap:               # without a known cap an extrapolated emission rate has no ceiling: no factor then
        yrs0 = (circ.index[-1] - circ.index[0]).days / 365.25
        g = float(circ.iloc[-1] / circ.iloc[0]) ** (1 / yrs0) - 1 if yrs0 > 0.5 and circ.iloc[0] > 0 else 0.0
        g = float(np.clip(g, 0, 0.5))
        how = "past year's supply growth (at most 50% a year), carried forward and capped at max supply"
        K["unlock_12m"] = _r(g, 3)
        for d in dates:
            yrs = max(0.0, (pd.Timestamp(d) - now).days / 365.25)
            c_t = c_now * (1 + g) ** yrs
            if cap:
                c_t = min(c_t, float(cap))
            dil[d] = min(1.0, c_now / c_t) if c_t else 1.0
    out["factors"] = {"valuation": _r(tilt, 3), "valuation_basis": basis, "dilution": {d: _r(v, 3) for d, v in dil.items()}, "dilution_basis": how}
    out["sources"], out["errors"], out["updated"] = fd.get("sources", {}), fd.get("errors", {}), fd.get("updated")
    return out


def fill_coins(pause_on_limit: float = 75.0) -> dict:
    """Background job: download BTC and every candidate coin from CoinGecko one at a time (PACE apart), waiting longer after a 429.
    Coins already fetched within a day come from memory and cost nothing. Returns {ticker: 'ok' | error}."""
    done = {}
    by_tick = {c["ticker"]: c for c in coins_list()}
    for cid, tick in [("bitcoin", "BTC")] + [(c["coingecko_id"], c["ticker"]) for c in coins_list()]:
        for attempt in range(2):
            try:
                if cid == "bitcoin":
                    fetch_json(CG_VOLUME, TTL, min_bytes=1000)
                    try:                                  # the sector leaders' market caps: one call for all of them
                        time.sleep(max(0.0, PACE - (time.time() - _last_download[0])))
                        _last_download[0] = time.time()
                        fetch_json(CG_MARKETS.format(ids=",".join(leader_ids())), TTL, min_bytes=100)
                    except Exception as e:
                        done["leaders"] = f"{type(e).__name__}: {str(e)[:80]}"
                else:
                    coin_chart(cid, live=True)
                done[tick] = "ok"
                break
            except Exception as e:
                done[tick] = f"{type(e).__name__}: {str(e)[:80]}"
                if "429" in str(e) and attempt == 0:
                    time.sleep(pause_on_limit)
                else:
                    break
        if tick in by_tick:                               # then that coin's fees, TVL, unlocks and supply, unless fetched in the last 20 hours,
            fd0 = fundamentals(tick)                          # (a file from before categories were kept is refetched once)
            if time.time() - (fd0.get("updated") or 0) < 20 * 3600 and "categories" in fd0:    # so a redeploy mid-fill resumes instead of starting over
                done[tick + ":fundamentals"] = "fresh"
                continue
            try:
                fd = fill_fundamentals(by_tick[tick])
                done[tick + ":fundamentals"] = "ok" if not fd.get("errors") else "partial: " + ", ".join(fd["errors"])
            except Exception as e:
                done[tick + ":fundamentals"] = f"{type(e).__name__}: {str(e)[:80]}"
    from ..cache import _cache
    for k in [k for k in _cache if k.startswith(f"topic:{SLUG}:coin")]:      # the next page view rebuilds from the fresh data
        _cache.pop(k, None)
    return done


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
    sc = scenarios()
    proj = project(now, btc_now, beta, sc) if beta is not None else []
    F = fund_factors(fundamentals(c["ticker"]), coin_px, mc.reindex(coin_px.index).ffill(), [p["date"] for p in proj])
    for p in proj:                                       # BTC beta x dilution from unlocks x half-way valuation reversion
        dl = F["factors"]["dilution"].get(p["date"])
        dl = 1.0 if dl is None else dl
        p["factor"] = _r(dl * F["factors"]["valuation"], 4)
        p["dilution"], p["valuation"] = dl, F["factors"]["valuation"]
        for k in ("bear", "base", "bull"):
            p[k + "_beta_only"] = p[k]
            p[k] = _r(p[k] * p["factor"], 4)
    return {"ticker": c["ticker"], "name": c["name"], "rank": int(c["rank"]), "sector": c["sector"], "note": c.get("note", ""),
            "links": {"coinmarketcap": f"https://coinmarketcap.com/currencies/{c['cmc_slug']}/" if c.get("cmc_slug") else None,
                      "defillama": f"https://defillama.com/protocol/{c['defillama_slug']}" if c.get("defillama_slug") else None,
                      "coingecko": f"https://www.coingecko.com/en/coins/{c['coingecko_id']}"},
            "notes": coin_notes()["coins"].get(c["ticker"], {}),
            "kpi": {"price": _r(now, 6), "date": str(coin_px.index[-1].date()), "from_high": _r(now / float(coin_px.max()) - 1, 4), "change_24h": _r(now / float(coin_px.iloc[-2]) - 1, 4) if len(coin_px) > 1 else None,
                    "change_1y": _r(now / float(coin_px.iloc[0]) - 1, 4), "market_cap": _r(float(mc.iloc[-1]), 0) if len(mc) else None,
                    "rsi": _r(float(r_coin.dropna().iloc[-1]), 1) if r_coin.notna().any() else None,
                    "rsi_vs_btc": _r(float(r_ratio.dropna().iloc[-1]), 1) if r_ratio.notna().any() else None,
                    "beta": _r(beta, 2) if beta is not None else None, "vs_btc_90d": vs_btc_90,
                    "base_2027": proj[0]["base"] if proj else None, "base_2028": proj[1]["base"] if len(proj) > 1 else None,
                    **{f"{k}_{p['date'][:4]}": p[k] for p in proj for k in ("bear", "bull")},
                    **{f"mcap_base_{p['date'][:4]}": _r(p["base"] * supply / p["dilution"], 0) for p in proj if supply and p.get("dilution")},
                    "factor_2028": proj[1].get("factor") if len(proj) > 1 else None},
            "spark": _pts(coin_px.iloc[-90:], 6),
            "series": {"price": _pts(coin_px, 6), "btc_indexed": _pts(btc_px / btc_px.iloc[0] * coin_px.iloc[0], 6), "ratio": _pts(ratio, 10),
                       "rsi": _pts(r_coin, 1), "rsi_vs_btc": _pts(r_ratio, 1), "market_cap": _pts(mc, 0)},
            "fundamentals": F,
            "projection": proj, "implied_mcap_base": [{"date": p["date"], "mcap": _r(p["base"] * supply / p["dilution"], 0) if p.get("dilution") else None} for p in proj] if supply else []}


def btc_chart() -> pd.Series:
    from ._base import cached_only
    try:
        return parse_chart(json.loads(cached_only(CG_VOLUME)))[0]
    except LookupError:
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
            row = {k: full[k] for k in ("ticker", "name", "rank", "sector", "note", "links", "kpi", "spark", "notes")}
            row["cg_check"] = sector_check(int(c["rank"]), fundamentals(c["ticker"]).get("categories") or [])
            row["classification"] = classification().get(c["ticker"])
            out["coins"].append(row)
        except Exception as e:
            out["coins"].append({"ticker": c["ticker"], "name": c["name"], "rank": int(c["rank"]), "sector": c["sector"], "note": c.get("note", ""),
                                 "error": "loading in the background, back in a few minutes" if isinstance(e, LookupError) else type(e).__name__,
                                 "links": {"coinmarketcap": f"https://coinmarketcap.com/currencies/{c['cmc_slug']}/" if c.get("cmc_slug") else None,
                                           "defillama": f"https://defillama.com/protocol/{c['defillama_slug']}" if c.get("defillama_slug") else None}})
    peers = [c["kpi"] for c in out["coins"] if "kpi" in c]
    for c in out["coins"]:
        if "kpi" in c:
            c["now"] = stands_out(c["kpi"], peers)
        else:
            c["notes"] = coin_notes()["coins"].get(c["ticker"], {})
    out["leaders"] = sector_leaders(out["coins"])
    out["notes_about"] = coin_notes().get("about", "")
    out["btc_now"] = _r(float(btc.iloc[-1]), 0)
    out["as_of"] = max((c["kpi"]["date"] for c in out["coins"] if "kpi" in c), default=None)
    from ._base import stale_info
    out["stale"] = stale_info([CG_CHART.format(id=c["coingecko_id"]) for c in coins_list()] + [CG_VOLUME])
    return out


def _coin_now(ticker: str) -> dict:
    c = next((x for x in coins_list() if x["ticker"] == ticker), None)
    if c is None:
        raise ValueError("unknown coin")
    try:
        out = _coin_full(c, btc_chart())
    except LookupError:                                  # not reached by the background fill yet: fetch this one coin now
        coin_chart(c["coingecko_id"], live=True)
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
                   "hl_fees_30d": lambda: _pts(hl_fees().rolling(30).sum().dropna().iloc[::7], 0),
                   "dex_volume_30d": lambda: _pts(dexs()[0].rolling(30).sum().dropna().iloc[::7], 0), "dex_top": lambda: dexs()[1]},
                  sources=[LLAMA_TVL, LLAMA_STABLES, LLAMA_HL, LLAMA_HL_REV, LLAMA_HL_FEES, LLAMA_DEXS])
    out["latest"] = {k: (out[k][-1][1] if out.get(k) else None) for k in ("defi_tvl", "stablecoins", "hl_tvl", "hl_revenue_30d", "hl_fees_30d", "dex_volume_30d")}
    out["research"] = R["metrics"]
    out["as_of"] = max((pd.Timestamp(out[k][-1][0], unit="s").strftime("%Y-%m-%d") for k in out["latest"] if out.get(k)), default=None)
    return out


def _candidates_now() -> dict:
    R = research()
    ev = manual(SLUG, "evidence")
    ev = ev if isinstance(ev, dict) else {}
    out = payload({"evidence": lambda: {k: _pts(v, 2) for k, v in ev.items()},
                   "hl_fees_30d": lambda: _pts(hl_fees().rolling(30).sum().dropna().iloc[::7], 0),
                   "hl_revenue_30d": lambda: _pts(hl_revenue().rolling(30).sum().dropna().iloc[::7], 0),
                   "stablecoins": lambda: _pts(_weekly(stablecoins()), 0)},
                  sources=[LLAMA_HL_FEES, LLAMA_HL_REV, LLAMA_STABLES])
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


# ------------------------------------------------------------------ sector rotation: four cycles on one timeline, and each candidate sector's status
ROTATION = DATA_DIR / SLUG / "rotation.csv"
SECTOR_STATUS = DATA_DIR / SLUG / "sector_status.json"
CYCLE_PEAKS = {1: "2013-12-04", 2: "2017-12-17", 3: "2021-11-10", 4: "2025-10-06"}       # the doc's BTC peaks (research.json markers)
CYCLE_HALVING = {1: HALVINGS[0], 2: HALVINGS[1], 3: HALVINGS[2], 4: HALVINGS[3]}


def rotation_rows() -> list[dict]:
    out = []
    with ROTATION.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not (r.get("cycle") or "").strip() or r["cycle"].startswith("#"):
                continue
            c = int(r["cycle"])
            a = pd.Timestamp(r["start"] + "-01")
            b = pd.Timestamp(r["end"] + "-01") + pd.offsets.MonthEnd(0)
            h = CYCLE_HALVING[c]
            out.append({"cycle": c, "sector": r["sector"], "family": r["family"], "start": int(a.timestamp()), "end": int(b.timestamp()),
                        "m_start": _r((a - h).days / 30.44, 1), "m_end": _r((b - h).days / 30.44, 1), "source": r["source"], "note": r.get("note", "")})
    return out


def sector_status(coins: list[dict], metrics: dict, evidence: dict) -> list[dict]:
    """One row per candidate sector: representatives' medians against BTC, the usage trend, and a status from the rules in
    sector_status.json, checked in order: overvalued, priced in, undervalued, awaiting rotation, else neutral."""
    cfg = json.loads(SECTOR_STATUS.read_text(encoding="utf-8"))
    by = {c["ticker"]: c for c in coins if "kpi" in c}
    hist = rotation_rows()
    cls_ = classification()
    med = lambda xs: float(np.median(xs)) if xs else None
    rows = []
    for s in cfg["sectors"]:
        reps = [by[t] for t in s.get("reps", []) if t in by]
        k = lambda f: med([c["kpi"][f] for c in reps if c["kpi"].get(f) is not None])
        rel, rsi_b, high = k("vs_btc_90d"), k("rsi_vs_btc"), k("from_high")
        usage, u = None, s.get("usage")
        if u:
            if u["source"] == "metrics" and metrics.get(u["key"]):
                pts = metrics[u["key"]]
                old = [v for t, v in pts if t <= pts[-1][0] - 85 * 86400]
                usage = pts[-1][1] / old[-1] - 1 if old and old[-1] else None
            elif u["source"] == "evidence" and u["key"] in evidence:
                ser = evidence[u["key"]].dropna()
                ser = ser[ser > 0]
                if len(ser) >= 2 and (ser.index[-1] - ser.index[-2]).days <= 200:
                    usage = float(ser.iloc[-1] / ser.iloc[-2] - 1)
        if rsi_b is not None and (rsi_b >= 70 or (rel or 0) >= 0.5):
            st = "Overvalued"
        elif rel is not None and rel >= 0.15 and high is not None and high >= -0.25:
            st = "Priced in"
        elif usage is not None and usage >= 0.10 and (rel is None or rel <= -0.15):
            st = "Undervalued"
        elif high is not None and high <= -0.6 and rel is not None and rel > -0.15 and (usage is None or usage >= 0):
            st = "Awaiting rotation"
        else:
            st = "Neutral"
        past = [h for h in hist if h["family"] == s["family"]]
        rows.append({"rank": s["rank"], "sector": s["sector"], "status": st,
                     "reps": [{"ticker": c["ticker"], "name": c["name"], "vs_btc_90d": c["kpi"].get("vs_btc_90d"), "rsi_vs_btc": c["kpi"].get("rsi_vs_btc"),
                               "from_high": c["kpi"].get("from_high"),
                               "secondary": cls_.get(c["ticker"], {}).get("classifiers") if cls_.get(c["ticker"], {}).get("doc_sector") == "secondary" else None} for c in reps],
                     "no_token": s.get("no_token", []), "vs_btc_90d": _r(rel, 3), "rsi_vs_btc": _r(rsi_b, 1), "from_high": _r(high, 3),
                     "usage": _r(usage, 3), "usage_label": u["label"] if u else None,
                     "past": [{"cycle": h["cycle"], "sector": h["sector"], "m_start": h["m_start"], "m_end": h["m_end"]} for h in past]})
    return rows


def _rotation_now() -> dict:
    coins = ENDPOINTS["coins"]().get("coins", [])
    try:
        m = ENDPOINTS["metrics"]()
    except Exception:
        m = {}
    ev = manual(SLUG, "evidence")
    now = pd.Timestamp.now()
    last_h = max(h for h in HALVINGS if h <= now)
    cfg = json.loads(SECTOR_STATUS.read_text(encoding="utf-8"))
    return {"rotation": rotation_rows(), "halvings": [int(h.timestamp()) for h in HALVINGS], "next_halving": int(NEXT_HALVING.timestamp()),
            "peaks": {c: int(pd.Timestamp(d).timestamp()) for c, d in CYCLE_PEAKS.items()},
            "peak_months": {c: _r((pd.Timestamp(d) - CYCLE_HALVING[c]).days / 30.44, 1) for c, d in CYCLE_PEAKS.items()},
            "months_now": _r((now - last_h).days / 30.44, 1), "months_to_next": _r((NEXT_HALVING - now).days / 30.44, 1),
            "status": sector_status(coins, m, ev if isinstance(ev, dict) else {}), "rules": cfg["rules"], "about": cfg["about"],
            "as_of": now.strftime("%Y-%m-%d"), "stale": {}, "updated": int(time.time())}


# ------------------------------------------------------------------ diagnostic: what the server sees at the per-coin fundamentals sources
PROBE_URLS = {
    "protocol (TVL)": "https://api.llama.fi/protocol/ethena",
    "fees (protocol)": "https://api.llama.fi/summary/fees/ethena?dataType=dailyFees",
    "fees (chain: solana)": "https://api.llama.fi/summary/fees/solana?dataType=dailyFees",
    "fees overview (chain)": "https://api.llama.fi/overview/fees/solana?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true&dataType=dailyFees",
    "chain TVL": "https://api.llama.fi/v2/historicalChainTvl/Solana",
    "emission (unlocks)": "https://api.llama.fi/emission/ethena",
    "emissions list": "https://api.llama.fi/emissions",
    "emissions dataset": "https://defillama-datasets.llama.fi/emissions/ethena",
    "coingecko detail": "https://api.coingecko.com/api/v3/coins/ethena?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false",
}


def _fund_probe() -> dict:
    """Not a tab: status, size, keys and the start of each body, read from the server's own network (Actions > show-json)."""
    import requests
    from ._base import UA
    out = {}
    for name, url in PROBE_URLS.items():
        try:
            r = requests.get(url, headers=UA, timeout=20)
            row = {"status": r.status_code, "bytes": len(r.content), "start": r.text[:300]}
            try:
                j = r.json()
                row["keys"] = list(j)[:40] if isinstance(j, dict) else f"list[{len(j)}]"
                if isinstance(j, dict):
                    row["shapes"] = {k: (type(v).__name__ + (f"[{len(v)}]" if isinstance(v, (list, dict)) else "")) for k, v in list(j.items())[:40]}
                    for k in ("documentedData", "realTimeData", "data", "metadata", "categories"):
                        if k in j:
                            v = j[k]
                            row[k] = (list(v)[:20] if isinstance(v, dict) else str(v)[:400])
                    if isinstance(j.get("market_data"), dict):
                        md = j["market_data"]
                        row["supply"] = {k: md.get(k) for k in ("circulating_supply", "total_supply", "max_supply")}
            except ValueError:
                pass
        except Exception as e:
            row = {"error": f"{type(e).__name__}: {str(e)[:150]}"}
        out[name] = {"url": url, **row}
    return out


# ------------------------------------------------------------------ what changed since yesterday (app/topics/_daily.py)
def READINGS() -> list[dict]:
    """Headline readings per tab, from what the endpoints already cache. lean: +1 = favourable for holding crypto / the doc's
    risk-on reading, -1 = unfavourable, 0 = neither (see the README)."""
    out = []
    add = lambda tab, key, label, value, lean, note=None: out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": lean, **({"note": note} if note else {})})
    try:
        n = ENDPOINTS["cycles"]().get("now") or {}
        if n.get("vs_ma200") is not None:
            add("cycles", "btc_vs_200d", "BTC vs its 200-day average", _r(n["vs_ma200"], 3), 1 if n["vs_ma200"] > 0 else -1)
        if n.get("days_since_halving") is not None:
            m = n["days_since_halving"] / 30.44
            add("cycles", "halving_clock", "Months since the last halving", _r(m, 1), 1 if 6 <= m <= 18 else -1 if 18 < m <= 30 else 0,
                "6-18 months after: the doc's bull window; 18-30: its bear year")
    except Exception:
        pass
    try:
        for s in ENDPOINTS["signals"]().get("status", []):
            add("signals", "sig:" + s["signal"][:40], s["signal"], s["state"], 1 if s["state"] == "firing" else 0)
    except Exception:
        pass
    try:
        e = _flows.ENDPOINTS["etf"]()
        d = e.get("daily_usd_m") or []
        if d:
            v = sum(p[1] for p in d[-5:])
            add("etf", "etf_5d", "US spot ETF net flows, last 5 days (US$m)", _r(v, 0), 1 if v > 0 else -1 if v < 0 else 0)
    except Exception:
        pass
    try:
        m = _flows.ENDPOINTS["mstr"]()
        k = m.get("kpi") or {}
        if k.get("mnav") is not None:
            add("mstr", "mnav", "MSTR mNAV (basic)", _r(k["mnav"], 2), 1 if k["mnav"] >= 1 else -1, "above 1 the issuance engine works; below it stalls")
        held = m.get("held") or []
        if len(held) >= 2:
            add("mstr", "mstr_bought_week", "BTC Strategy added in the last week", _r(held[-1][1] - held[-2][1], 0), 1 if held[-1][1] > held[-2][1] else 0)
        for c in (m.get("strategies") or {}).get("checklist", []):
            add("mstr", "exit:" + c["rule"], "Exit checklist: " + c["rule"], c["state"], -1 if c["state"] in ("exit", "caution") else 0)
    except Exception:
        pass
    try:
        cs = [c for c in ENDPOINTS["coins"]().get("coins", []) if "kpi" in c]
        if cs:
            up = sum(1 for c in cs if (c["kpi"].get("rsi_vs_btc") or 0) > 50)
            add("candidates", "rsi_breadth", "Candidates with RSI vs BTC above 50", f"{up}/{len(cs)}", 1 if up > len(cs) / 2 else -1 if up < len(cs) / 4 else 0)
            ranked = sorted((c for c in cs if c["kpi"].get("vs_btc_90d") is not None), key=lambda c: c["kpi"]["vs_btc_90d"])
            if ranked:
                add("candidates", "strongest", "Strongest candidate vs BTC, 90 days", ranked[-1]["ticker"], 0, f"{ranked[-1]['kpi']['vs_btc_90d']:+.0%}")
                add("candidates", "weakest", "Weakest candidate vs BTC, 90 days", ranked[0]["ticker"], 0, f"{ranked[0]['kpi']['vs_btc_90d']:+.0%}")
        for s in ENDPOINTS["rotation"]().get("status", []):
            add("sectors", "sector:" + str(s["rank"]), "Sector " + str(s["rank"]) + ": " + s["sector"], s["status"],
                {"Undervalued": 1, "Awaiting rotation": 1, "Overvalued": -1, "Priced in": -1}.get(s["status"], 0))
    except Exception:
        pass
    return out


def _cached_ep(name, fn, ttl=6 * 3600):
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"cycles": _cached_ep("cycles", _cycles_now), "sectors": _cached_ep("sectors", _sectors_now, 600), "metrics": _cached_ep("metrics", _metrics_now),
             "candidates": _cached_ep("candidates", _candidates_now), "signals": _cached_ep("signals", _signals_now, 3600),
             "coins": _cached_ep("coins", _coins_now), "rotation": _cached_ep("rotation", _rotation_now, 3600),
             "fund-probe": _cached_ep("fund-probe", _fund_probe, 1800)}
from . import btc_flows as _flows                                    # ETF and MSTR tabs
ENDPOINTS.update(_flows.ENDPOINTS)
BACKGROUND = [fill_coins]                    # slow, rate-limited downloads the server runs outside page requests
ENDPOINTS.update({f"coin-{c['ticker'].lower()}": _cached_ep(f"coin-{c['ticker'].lower()}", (lambda t: lambda: _coin_now(t))(c["ticker"])) for c in coins_list()})
