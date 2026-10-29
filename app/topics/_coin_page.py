"""One BTC Cycles candidate coin in full, for its tab on Altcoin Study (/altcoins#hype, #ena, #sol, #near; see altcoins.py).

Nothing is downloaded here: btc_cycles' background fill already keeps each candidate's 365-day price and market cap (CoinGecko) and its
fundamentals (DefiLlama TVL, fees, unlock schedule; CoinGecko supply). The tab shows price against BTC, RSI, market cap, the notes and what
stands out today, the fundamentals (fees, TVL, supply and unlocks against price, with the multiples) and the bear / base / bull projection,
all from one payload.
"""
from __future__ import annotations

from . import btc_cycles as C


def coin_row(ticker: str) -> dict:
    """The coin's row in coins.csv (StopIteration if it is not a candidate)."""
    return next(c for c in C.coins_list() if c["ticker"] == ticker)


def payload(ticker: str, siblings: dict | None = None) -> dict:
    """The coin's full series and projection, plus the Candidates tab's 'Today' sentences and its place among the other candidates.
    siblings: {ticker: href} of the other coin tabs, for the header's links."""
    out = C.ENDPOINTS[f"coin-{ticker.lower()}"]()
    out = {**out, "now": [], "peers": None}
    try:
        k = C.ENDPOINTS["coins"]()
        row = next((c for c in k["coins"] if c["ticker"] == ticker), {})
        out["now"] = row.get("now") or []
        live = [c for c in k["coins"] if "kpi" in c]
        rank = lambda key: 1 + sum((c["kpi"].get(key) or float("-inf")) > (out["kpi"].get(key) or float("-inf")) for c in live)
        out["peers"] = {"n": len(live), "market_cap": rank("market_cap"), "vs_btc_90d": rank("vs_btc_90d"), "change_1y": rank("change_1y"),
                        "classification": row.get("classification"), "btc_now": k.get("btc_now")}
    except Exception:                                    # the ranking is a nicety: the tab works without it
        pass
    out["scenarios"] = C.scenarios()
    out["sibling_pages"] = dict(siblings or {})
    return out


def sources(ticker: str) -> list[dict]:
    c = coin_row(ticker)
    return [{"name": f"{c['name']} price and market cap (CoinGecko)", "url": f"https://www.coingecko.com/en/coins/{c['coingecko_id']}", "cadence": "daily"},
            {"name": f"{c['name']} fees, TVL and unlocks (DefiLlama free API)",
             "url": f"https://defillama.com/protocol/{c['defillama_slug']}" if c.get("defillama_slug") else "https://defillama.com", "cadence": "daily"}]
