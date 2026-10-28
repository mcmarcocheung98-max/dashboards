"""A standalone page for one BTC Cycles candidate coin (/ena, /sol, /near): the same data the Candidates tab shows in a row, in full.

Nothing is downloaded here: btc_cycles' background fill already keeps each candidate's 365-day price and market cap (CoinGecko) and its
fundamentals (DefiLlama TVL, fees, unlock schedule; CoinGecko supply). A page module is three lines (see coin_ena.py):

    from ._coin_page import page
    TOPIC, ENDPOINTS, SOURCES, NOTES = page("ENA", order=12)

Tabs: overview (price against BTC, RSI, market cap, the notes and what stands out today), fundamentals (fees, TVL, supply and unlocks
against price, with the multiples) and projection (bear / base / bull at the scenario dates). All three read one payload. The pages
share static/topics/coin.js, which reads SLUG to know which coin it shows.
"""
from __future__ import annotations

from ..cache import _cached
from . import Topic
from . import btc_cycles as C

TABS = (("overview", "Overview"), ("fundamentals", "Fundamentals"), ("projection", "Projection"))


def coin_row(ticker: str) -> dict:
    """The coin's row in coins.csv (KeyError if it is not a candidate)."""
    return next(c for c in C.coins_list() if c["ticker"] == ticker)


def payload(ticker: str) -> dict:
    """The coin's full series and projection, plus the Candidates tab's 'Today' sentences and its place among the other candidates."""
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
    except Exception:                                    # the ranking is a nicety: the page works without it
        pass
    out["scenarios"] = C.scenarios()
    out["sibling_pages"] = {t.upper(): f"/{t}" for t in PAGES}
    return out


PAGES: dict[str, int] = {}                               # slug -> order, filled by page() so each page can link the others


def page(ticker: str, order: int) -> tuple:
    c = coin_row(ticker)
    slug = ticker.lower()
    PAGES[slug] = order
    topic = Topic(slug, f"{c['name']} ({ticker})",
                  f"{c['name']} on its own page: price against BTC, RSI, market cap, fees, TVL and unlocks, and the BTC Cycles bear / base / bull "
                  f"projection to end-2028. One of the candidates in the {c['sector']} sector.",
                  f"coin_{slug}", TABS, (), icon="chart", order=order, script="coin")
    ep = lambda: _cached(f"topic:{slug}:coin", 3600, lambda: payload(ticker))
    endpoints = {k: ep for k, _ in TABS}
    sources = [{"name": f"{c['name']} price and market cap (CoinGecko)", "url": f"https://www.coingecko.com/en/coins/{c['coingecko_id']}", "cadence": "daily"},
               {"name": "Fees, TVL and unlocks (DefiLlama free API)", "url": f"https://defillama.com/protocol/{c['defillama_slug']}" if c.get("defillama_slug") else "https://defillama.com", "cadence": "daily"},
               {"name": "Projection levels and coin notes (BTC Cycles & Sector Rotation)", "url": "/btc-cycles#candidates", "cadence": "as revised"}]
    notes = ("Research, not investment advice. The same numbers as the coin's row on BTC Cycles > Candidates, from the same background download; "
             "the projection is mechanical (BTC scenario, beta, dilution and valuation), not a forecast.")
    return topic, endpoints, sources, notes
