"""Coin-specific gauges for the signal boards: positioning (Hyperliquid funding), the coin's sector and narrative (relative strength against a
sector basket, the sector's heat against BTC, the altcoin share of BTC, meme season), its product (stablecoin supply, fees momentum, chain
DEX volume, Hyperliquid's share of perp volume, ENA's basis yield) and its supply (relief after an unlock). Each is a daily series the board
scores; the fitted board learns what each is worth. Sources: Hyperliquid (candles, funding), DefiLlama (stablecoins, DEX and derivatives
volume, emissions), CoinGecko (market caps, via the fills). Every fetch is cached and snapshotted like the rest of the site.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from ._base import DAY, fetch_json

HL_INFO = "https://api.hyperliquid.xyz/info"
LLAMA_STABLE_LIST = "https://stablecoins.llama.fi/stablecoins?includePrices=false"
LLAMA_STABLE_ONE = "https://stablecoins.llama.fi/stablecoincharts/all?stablecoin={id}"
LLAMA_STABLE_CHAIN = "https://stablecoins.llama.fi/stablecoincharts/{chain}"
LLAMA_DEX_CHAIN = "https://api.llama.fi/overview/dexs/{chain}?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true"
LLAMA_EMISSIONS = "https://defillama-datasets.llama.fi/emissions/{slug}"
TTL = 6 * 3600
FUNDING_WINDOW_DAYS = 15          # Hyperliquid returns at most 500 hourly records per call: 15 days = 360
FUNDING_DAYS = 730

FUNDING_PACE = 0.08          # seconds between uncached funding windows (Hyperliquid rate-limits a cold burst); tests set it to 0
FUNDING_RETRY_WAIT = 1.0     # seconds before the one retry of a failed window

# per coin: the sector basket (Hyperliquid markets), the stablecoin or chain whose supply is its product, the chain whose DEX volume is its activity,
# whether it is a memecoin, and extras. Baskets are hand-picked proxies for the narrative each coin trades on.
COINS = {
    "HYPE": {"sector": ["AAVE", "UNI", "PENDLE"], "chain_stables": "Hyperliquid L1", "fees": True},     # perp-DEX share dropped 2 Nov 2026: DefiLlama's derivatives overview went behind a paid key (402)
    "ENA": {"sector": ["AAVE", "PENDLE", "ETHFI"], "stable": "USDe", "basis": ["BTC", "ETH"], "fees": True},
    "SOL": {"sector": ["ETH", "SUI", "AVAX"], "chain_stables": "Solana", "dex_chain": "Solana", "fees": True},
    "NEAR": {"sector": ["TAO", "FET", "RENDER"], "chain_stables": "Near", "fees": True},
    "DOGE": {"meme": True}, "SHIB": {"meme": True, "dex_chain": "Ethereum"}, "PEPE": {"meme": True, "dex_chain": "Ethereum"},
    "BONK": {"meme": True, "dex_chain": "Solana"}, "WIF": {"meme": True, "dex_chain": "Solana"}, "TRUMP": {"meme": True, "dex_chain": "Solana"},
}
MEMES = [k for k, v in COINS.items() if v.get("meme")]


# ------------------------------------------------------------------ fetchers
def funding_daily(coin: str, days: int = FUNDING_DAYS) -> pd.Series:
    """Daily mean of Hyperliquid's hourly funding rate (per hour) for a market, fetched in fixed 15-day windows so past windows cache for good."""
    today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    start = today - pd.Timedelta(days=days)
    edge = pd.Timestamp("2023-01-01") + pd.Timedelta(days=((start - pd.Timestamp("2023-01-01")).days // FUNDING_WINDOW_DAYS) * FUNDING_WINDOW_DAYS)
    rows = []
    t = edge
    from ..cache import _cache
    while t <= today:
        a, b = t, min(t + pd.Timedelta(days=FUNDING_WINDOW_DAYS), today + pd.Timedelta(days=1))
        post = {"type": "fundingHistory", "coin": coin, "startTime": int(a.timestamp() * 1000), "endTime": int(b.timestamp() * 1000)}
        cached = f"topic:{HL_INFO}#" + __import__("json").dumps(post, sort_keys=True) in _cache
        for attempt in range(2):                                        # Hyperliquid rate-limits a cold burst: pace the downloads and retry once
            try:
                j = fetch_json(HL_INFO, TTL if b >= today else 30 * DAY, post=post, min_bytes=2)
                rows += [(int(r["time"]), float(r["fundingRate"])) for r in j if "time" in r and "fundingRate" in r]
                break
            except Exception:
                if attempt == 0:
                    time.sleep(FUNDING_RETRY_WAIT)
        if not cached:
            time.sleep(FUNDING_PACE)
        t = b
    if not rows:
        return pd.Series(dtype=float)
    ts, vals = zip(*rows)
    s = pd.Series(vals, index=pd.to_datetime(list(ts), unit="ms"), dtype=float).sort_index()      # one conversion, not one per hourly row
    return s[~s.index.duplicated()].resample("1D").mean().dropna()


def stable_supply(symbol: str) -> pd.Series:
    """A stablecoin's circulating supply over time (DefiLlama), found by symbol (USDe)."""
    lst = fetch_json(LLAMA_STABLE_LIST, DAY, min_bytes=100)
    hit = next((x for x in lst.get("peggedAssets", []) if str(x.get("symbol", "")).upper() == symbol.upper()), None)
    if not hit:
        raise LookupError(symbol)
    rows = fetch_json(LLAMA_STABLE_ONE.format(id=hit["id"]), TTL, min_bytes=100)
    return pd.Series({pd.to_datetime(int(r["date"]), unit="s"): float((r.get("totalCirculating") or {}).get("peggedUSD") or (r.get("totalCirculatingUSD") or {}).get("peggedUSD") or 0) for r in rows}).sort_index()


def chain_stables(chain: str) -> pd.Series:
    rows = fetch_json(LLAMA_STABLE_CHAIN.format(chain=chain.replace(" ", "%20")), TTL, min_bytes=100)
    return pd.Series({pd.to_datetime(int(r["date"]), unit="s"): float((r.get("totalCirculatingUSD") or {}).get("peggedUSD") or 0) for r in rows}).sort_index()


def chain_dex_volume(chain: str) -> pd.Series:
    j = fetch_json(LLAMA_DEX_CHAIN.format(chain=chain), TTL, min_bytes=100)
    return pd.Series({pd.to_datetime(int(t), unit="s"): float(v) for t, v in (j.get("totalDataChart") or [])}).sort_index()


def emissions_curve(slug: str) -> pd.Series:
    """Cumulative unlocked supply over time from DefiLlama's free emissions dataset (the sum of every allocation's unlocked curve)."""
    from .btc_cycles import _optional_json, parse_emissions
    return parse_emissions(_optional_json(LLAMA_EMISSIONS.format(slug=slug)))       # plain download: a coin without a page (most memecoins) is not a failing source


# ------------------------------------------------------------------ gauge series (pure)
def _ret(s: pd.Series, n: int) -> pd.Series:
    return s / s.shift(n) - 1


def funding_z(f: pd.Series, idx: pd.DatetimeIndex, short: int = 7, long: int = 90) -> pd.Series:
    """The last week's funding against the last quarter's: (7-day mean - 90-day mean) / 90-day standard deviation."""
    if f is None or len(f) < long:
        return pd.Series(np.nan, index=idx)
    z = (f.rolling(short).mean() - f.rolling(long).mean()) / f.rolling(long).std().replace(0, np.nan)
    return z.reindex(idx, method="ffill")


def basket_return(members: dict[str, pd.Series], n: int, idx: pd.DatetimeIndex) -> pd.Series:
    """Equal-weight average of the members' n-day returns on idx (members: name -> daily close)."""
    rs = [_ret(c.reindex(idx, method="ffill"), n) for c in members.values() if c is not None and len(c) > n]
    return pd.concat(rs, axis=1).mean(axis=1) if rs else pd.Series(np.nan, index=idx)


def extra_inputs(ticker: str, price: pd.Series, ctx: dict) -> dict[str, pd.Series]:
    """The coin's extra gauge series on the price's index. ctx: {"closes": {market: close series}, "funding": {market: daily funding}, "mcaps": {ticker: series},
    "btc_mcap": series, "stables": {key: series}, "dex": {chain: series}, "fees30": series|None, "unlock_events": DatetimeIndex|None}."""
    cfg = COINS.get(ticker, {})
    idx = price.index
    out: dict[str, pd.Series] = {}
    closes, funding = ctx.get("closes", {}), ctx.get("funding", {})
    if ticker in funding and len(funding[ticker]):
        out["funding_z"] = funding_z(funding[ticker], idx)
    members = cfg.get("sector") or ([m for m in MEMES if m != ticker] if cfg.get("meme") else [])
    mem = {m: closes[m] for m in members if m in closes}
    if len(mem) >= 2:
        out["sector_rs"] = (_ret(price, 90) - basket_return(mem, 90, idx)).clip(-0.3, 0.3) / 0.3
        if "BTC" in closes:
            out["sector_heat"] = (basket_return(mem, 30, idx) - _ret(closes["BTC"].reindex(idx, method="ffill"), 30)).clip(-0.2, 0.2) / 0.2
    mcaps, btc_mc = ctx.get("mcaps", {}), ctx.get("btc_mcap")
    if mcaps and btc_mc is not None and len(btc_mc):
        tot = pd.concat([s.reindex(idx, method="ffill") for s in mcaps.values() if s is not None and len(s)], axis=1).sum(axis=1, min_count=3)
        share = tot / btc_mc.reindex(idx, method="ffill")
        out["alt_share"] = (_ret(share, 30)).clip(-0.15, 0.15) / 0.15
        if cfg.get("meme"):
            memes = pd.concat([mcaps[m].reindex(idx, method="ffill") for m in MEMES if m in mcaps and len(mcaps[m])], axis=1).sum(axis=1, min_count=3)
            out["meme_season"] = (_ret(memes / btc_mc.reindex(idx, method="ffill"), 90)).clip(-0.25, 0.25) / 0.25
    st = ctx.get("stables", {})
    key = cfg.get("stable") or cfg.get("chain_stables")
    if key and key in st and len(st[key]) > 60:
        out["stable_growth"] = (_ret(st[key].reindex(idx, method="ffill"), 30)).clip(-0.15, 0.15) / 0.15
    f30 = ctx.get("fees30")
    if cfg.get("fees") and f30 is not None and len(f30) > 60:
        f = f30.reindex(idx, method="ffill")
        out["fees_momentum"] = (_ret(f, 30)).clip(-0.5, 0.5) / 0.5
    dex = ctx.get("dex", {})
    if cfg.get("dex_chain") in dex and len(dex[cfg["dex_chain"]]) > 60:
        v = dex[cfg["dex_chain"]].reindex(idx, method="ffill").rolling(30).sum()
        out["dex_momentum"] = (_ret(v, 30)).clip(-0.5, 0.5) / 0.5
    if cfg.get("basis"):
        fs = [funding[m] for m in cfg["basis"] if m in funding and len(funding[m])]
        if fs:
            apr = pd.concat([x.reindex(idx, method="ffill") for x in fs], axis=1).mean(axis=1).rolling(30).mean() * 24 * 365
            out["basis_yield"] = ((apr - 0.05) / 0.15).clip(-1, 1)
    ev = ctx.get("unlock_events")
    if ev is not None and len(ev):
        days = idx.normalize()
        rel = np.zeros(len(idx))
        for t in pd.DatetimeIndex(ev):
            diff = np.asarray((days - t.normalize()).days)
            rel[(diff >= 1) & (diff <= 10)] = 1
        out["post_unlock"] = pd.Series(rel, index=idx)
    return out


def unlock_event_days(curve: pd.Series, min_pct: float = 1.0) -> pd.DatetimeIndex:
    """Days when the cumulative unlocked supply jumped by at least min_pct % of what was unlocked before (from a DefiLlama curve)."""
    if curve is None or len(curve) < 3:
        return pd.DatetimeIndex([])
    c = curve.sort_index()
    daily = c.resample("1D").last().ffill()
    jump = daily.diff() / daily.shift(1).replace(0, np.nan) * 100
    return pd.DatetimeIndex(jump[jump >= min_pct].index)
