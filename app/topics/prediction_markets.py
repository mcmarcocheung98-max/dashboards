"""Prediction Markets (/prediction-markets): what the money says will happen, where the odds moved, and how well the markets have called it.

overview    biggest movers over 24 hours and 7 days (change in the Yes price, in points of probability), the most traded markets and events,
            and money by category (Polymarket Gamma API: open events by 24-hour volume, plus a few tags for the regions)
markets     the watchlist (data/prediction-markets/watchlist.csv): each market's daily odds history (Polymarket CLOB prices-history) with the
            volume and liquidity behind it (logged here once a day, since the API has no history of either)
categories  elections & politics, central banks & macro, crypto, AI & tech, sports, geopolitics: their markets and the money on them
venues      the same question on Polymarket, Kalshi, Manifold and PredictIt side by side and the gap between them; each venue's price is
            logged once a day, so the gap gets a history
regions     the watchlist and the most traded listed markets for the US (elections, the Fed, CPI), the UK (politics, the BoE) and Hong Kong
            and China (HSI, PBoC, Taiwan)
accuracy    resolved Polymarket markets: the Yes price 30 and 7 days before each closed against what happened, as a calibration chart and a
            Brier score (a paced background job, kept on the volume and added to each run)

Watchlist rows find their market on each venue by keywords (see data/prediction-markets/README.md), so a new Fed meeting or a new
contract is picked up without editing the file. Downloads are paced (PACE seconds between calls to the same host) and cached an hour.
Not investment or betting advice.
"""
from __future__ import annotations

import csv
import json
import time
from urllib.parse import quote, urlparse

import numpy as np
import pandas as pd

from . import _base as B
from ._base import DAY, HOUR, _pts, _r, fetch_json, manual_rows, manual_sources
from . import Topic

SLUG = "prediction-markets"
TOPIC = Topic(SLUG, "Prediction Markets",
              "What the money says will happen: the biggest moves in the odds, the most traded markets, the same question on Polymarket, Kalshi, "
              "Manifold and PredictIt, the US, UK and Hong Kong, and how well resolved markets called it.",
              "prediction_markets", (("overview", "Overview"), ("markets", "Markets"), ("categories", "Categories"), ("venues", "Cross-venue"),
                                     ("regions", "US / UK / HK"), ("accuracy", "Accuracy")),
              ("overview", "markets", "categories", "venues", "regions", "accuracy"), icon="chart", order=75)

GAMMA = "https://gamma-api.polymarket.com"
POLY_TOP = GAMMA + "/events?closed=false&order=volume24hr&ascending=false&limit=100&offset={offset}"
POLY_PAGES = 3                     # the 300 open events with the most volume in the last 24 hours
POLY_TAG = GAMMA + "/events?closed=false&tag_slug={tag}&order=volume24hr&ascending=false&limit=50"
POLY_TAGS = ("fed-rates", "economy", "inflation", "uk", "china", "hong-kong", "taiwan", "ai", "geopolitics")   # so smaller regional markets are in the pool
POLY_CLOSED = GAMMA + "/events?closed=true&order=volume&ascending=false&limit=50&offset={offset}&end_date_min={since}"   # events carry the tags; /markets does not
CLOB = "https://clob.polymarket.com"
CLOB_HIST = CLOB + "/prices-history?market={token}&interval=max&fidelity=1440"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_SERIES = KALSHI + "/markets?series_ticker={series}&status=open&limit=200"
MANIFOLD = "https://api.manifold.markets/v0/search-markets?term={term}&filter=open&sort=liquidity&limit=20"
PREDICTIT = "https://www.predictit.org/api/marketdata/all/"
TTL = HOUR
PACE = 0.5                         # seconds between downloads from the same host
MIN_VOL24 = 25_000                 # a mover must have traded this much in the last 24 hours (7 days: MIN_VOL1WK) to count
MIN_VOL1WK = 100_000
ACC_MIN_VOLUME = 50_000            # resolved markets with less traded are left out of the calibration
ACC_PER_RUN = 120                  # price histories fetched per background run (paced), the rest wait for the next run

# category key, label, Polymarket tag slugs (the first category with a matching tag wins, in this order), Kalshi categories
CATEGORIES = (
    ("sports", "Sports", {"sports", "soccer", "nba", "nfl", "mlb", "nhl", "tennis", "golf", "f1", "formula-1", "ufc", "mma", "boxing", "cricket", "epl",
                          "champions-league", "ncaa", "cfb", "college-football", "esports", "olympics", "baseball", "basketball", "football", "hockey",
                          "world-series", "world-cup", "premier-league", "la-liga", "chess"}, {"Sports"}),
    ("crypto", "Crypto", {"crypto", "bitcoin", "ethereum", "solana", "crypto-prices", "xrp", "memecoins", "airdrops", "stablecoins", "btc", "eth"}, {"Crypto"}),
    ("macro", "Central banks & macro", {"economy", "fed", "fed-rates", "inflation", "cpi", "interest-rates", "finance", "business", "stocks", "macro",
                                        "recession", "gdp", "jobs-report", "central-banks", "boe", "bank-of-england", "ecb", "pboc", "tariffs", "commodities",
                                        "fomc", "earnings", "economic-policy", "hang-seng", "indices", "jerome-powell"}, {"Economics", "Financials", "Companies"}),
    ("ai", "AI & tech", {"ai", "tech", "technology", "openai", "science", "big-tech", "chatgpt", "nvidia", "apple", "google", "anthropic", "spacex",
                         "space"}, {"Science and Technology", "Tech", "Technology"}),
    ("geo", "Geopolitics", {"geopolitics", "world", "middle-east", "ukraine", "russia", "israel", "iran", "china", "taiwan", "gaza", "war", "nato",
                            "foreign-policy", "ceasefire", "north-korea", "venezuela", "world-affairs"}, {"World"}),
    ("politics", "Elections & politics", {"politics", "elections", "us-politics", "world-elections", "uk", "uk-politics", "trump", "congress", "midterms",
                                          "us-elections", "global-elections", "senate", "house", "government", "us-government", "mayoral-elections",
                                          "primaries"}, {"Politics", "Elections"}),
)
CAT_LABEL = {k: l for k, l, _, _ in CATEGORIES} | {"other": "Other"}
# region tags: markets listed under these tags appear on the US / UK / HK tab next to the watchlist
REGION_TAGS = {"US": {"fed", "fed-rates", "cpi", "inflation", "us-politics", "midterms", "us-elections", "congress", "senate", "house", "fomc"},
               "UK": {"uk", "uk-politics", "boe", "bank-of-england", "starmer", "reform-uk", "ftse"},
               "HK": {"china", "hong-kong", "taiwan", "hang-seng", "pboc", "xi-jinping", "hsi"}}
REGION_LABEL = {"US": "United States", "UK": "United Kingdom", "HK": "Hong Kong & China"}

SOURCES = [{"name": "Polymarket Gamma API (open and resolved markets, events, tags, volume, liquidity, 24-hour and 7-day price changes)", "url": "https://docs.polymarket.com/", "cadence": "hourly"},
           {"name": "Polymarket CLOB API (daily price history)", "url": "https://docs.polymarket.com/", "cadence": "hourly"},
           {"name": "Kalshi public trade API v2 (markets by series)", "url": "https://docs.kalshi.com/", "cadence": "hourly"},
           {"name": "Manifold API (search; play money, not dollars)", "url": "https://docs.manifold.markets/api", "cadence": "hourly"},
           {"name": "PredictIt market data (all markets)", "url": "https://www.predictit.org/api/marketdata/all/", "cadence": "hourly"},
           {"name": "Watchlist (data/prediction-markets/watchlist.csv)", "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/prediction-markets", "cadence": "as edited"}]
NOTES = ("A market's price is the cost of a share that pays $1 if the event happens, so 0.62 reads as a 62% chance. Prices include fees and a "
         "spread, thin markets move on small trades, and Manifold trades play money. Changes are in points of probability. Volume and "
         "liquidity are what each venue reports, in US dollars (Kalshi: contracts of $1). Not investment or betting advice.")


# ------------------------------------------------------------------ small helpers
def _now() -> pd.Timestamp:
    return pd.Timestamp.now("UTC").tz_localize(None)


def _f(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _jlist(v) -> list:
    """Gamma API fields such as outcomes and outcomePrices are JSON arrays sent as strings."""
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v or "[]")
        return out if isinstance(out, list) else []
    except (TypeError, ValueError):
        return []


_last: dict[str, float] = {}


def get_json(url: str, ttl: float = TTL, **kw):
    """fetch_json, paced: a download (not a cache hit) waits until PACE seconds have passed since the last one to the same host."""
    from ..cache import _cache
    hit = _cache.get(f"topic:{url}")
    if not (hit and hit[0] > time.time() - ttl) and PACE:
        host = urlparse(url).netloc
        wait = PACE - (time.time() - _last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
    return fetch_json(url, ttl, **kw)


def matches(text: str, spec: str) -> bool:
    """spec: words that must all appear in text (any case), each starting a word ('boe' is not in 'Nijboer'; 'democrat' is in
    'Democratic'); a/b means either; an underscore stands for a space ('no_change'); !word means the word must not appear."""
    import re
    t = (text or "").lower()
    has = lambda alt: re.search(r"(?<![a-z0-9])" + re.escape(alt.replace("_", " ")), t) is not None
    words = [w for w in (spec or "").lower().split() if w]
    need = [w for w in words if not w.startswith("!")]
    return bool(need) and all(any(has(a) for a in w.split("/") if a) for w in need) and not any(has(w[1:]) for w in words if w.startswith("!") and len(w) > 1)


def category(tags, kalshi: str | None = None) -> str:
    tags = {str(t).lower() for t in tags or ()}
    for key, _, poly, kal in CATEGORIES:
        if tags & poly or (kalshi and kalshi in kal):
            return key
    return "other"


def regions_of(tags) -> list[str]:
    tags = {str(t).lower() for t in tags or ()}
    return [k for k, v in REGION_TAGS.items() if tags & v]


# ------------------------------------------------------------------ parsers (JSON in, so tests can feed fixtures)
def parse_poly_events(events: list) -> tuple[list[dict], list[dict]]:
    """Gamma events -> (events [{title, slug, cat, volume, vol24, liq, n}], markets [{id, q, label, event, slug, url, cat, tags, yes, d1, d7,
    vol, vol24, vol1wk, liq, end, token}]), open markets with a Yes price only."""
    evs, mks = [], []
    for e in events or []:
        if not isinstance(e, dict):
            continue
        tags = [t.get("slug") for t in e.get("tags") or [] if isinstance(t, dict) and t.get("slug")]
        cat, slug = category(tags), e.get("slug") or ""
        n = 0
        for m in e.get("markets") or []:
            if m.get("closed") or m.get("active") is False:
                continue
            outs, prices, toks = _jlist(m.get("outcomes")), _jlist(m.get("outcomePrices")), _jlist(m.get("clobTokenIds"))
            if not outs or len(prices) != len(outs):
                continue
            i = next((k for k, o in enumerate(outs) if str(o).lower() == "yes"), 0)
            yes = _f(prices[i])
            if yes is None:
                continue
            n += 1
            q = m.get("question") or ""
            mks.append({"id": str(m.get("id") or m.get("conditionId") or q), "q": q, "label": m.get("groupItemTitle") or q, "event": e.get("title") or "",
                        "slug": slug, "url": f"https://polymarket.com/event/{slug}" if slug else None, "cat": cat, "tags": tags, "yes": round(yes, 4),
                        "d1": _f(m.get("oneDayPriceChange")), "d7": _f(m.get("oneWeekPriceChange")),
                        "vol": _f(m.get("volumeNum")) if m.get("volumeNum") is not None else _f(m.get("volume")),
                        "vol24": _f(m.get("volume24hr")) or 0.0, "vol1wk": _f(m.get("volume1wk")) or 0.0,
                        "liq": _f(m.get("liquidityNum")) if m.get("liquidityNum") is not None else _f(m.get("liquidity")),
                        "end": str(m.get("endDate") or e.get("endDate") or "")[:10], "token": toks[i] if i < len(toks) else None,
                        "two": len(outs) == 2})
        if n:
            evs.append({"title": e.get("title") or "", "slug": slug, "url": f"https://polymarket.com/event/{slug}" if slug else None, "cat": cat, "tags": tags,
                        "volume": _f(e.get("volume")) or 0.0, "vol24": _f(e.get("volume24hr")) or 0.0, "liq": _f(e.get("liquidity")) or 0.0, "n": n,
                        "end": str(e.get("endDate") or "")[:10]})
    return evs, mks


def parse_history(j: dict) -> pd.Series:
    """CLOB prices-history {"history": [{t, p}]} -> daily Series of the Yes price (the last point of each UTC day)."""
    h = (j or {}).get("history") or []
    s = pd.Series({pd.Timestamp(int(x["t"]), unit="s").normalize(): float(x["p"]) for x in h if "t" in x and "p" in x}, dtype=float)
    return s[~s.index.duplicated(keep="last")].sort_index()


def parse_kalshi(j: dict) -> list[dict]:
    """Kalshi /markets -> [{ticker, event, title, sub, yes, prev, vol, vol24, oi, close, url}]. Prices are dollars per $1 contract: the last
    trade, or the middle of the bid and ask when nothing has traded."""
    out = []
    for m in (j or {}).get("markets") or []:
        if m.get("status") not in (None, "active", "open"):
            continue
        last, bid, ask = _f(m.get("last_price_dollars")), _f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars"))
        yes = last if last else ((bid + ask) / 2 if bid is not None and ask and ask > 0 else None)
        if yes is None:
            continue
        ev = m.get("event_ticker") or ""
        out.append({"ticker": m.get("ticker") or "", "event": ev, "title": m.get("title") or "", "sub": m.get("yes_sub_title") or m.get("subtitle") or "",
                    "yes": round(yes, 4), "prev": _f(m.get("previous_price_dollars")), "vol": _f(m.get("volume_fp")) or 0.0, "vol24": _f(m.get("volume_24h_fp")) or 0.0,
                    "oi": _f(m.get("open_interest_fp")), "close": str(m.get("close_time") or "")[:10],
                    "url": f"https://kalshi.com/markets/{ev.split('-')[0].lower()}" if ev else None})
    return out


def parse_manifold(j: list) -> list[dict]:
    """Manifold search -> open binary markets [{id, q, prob, vol, liq, bettors, close, url}] (multiple-choice markets have no single probability)."""
    out = []
    for m in j or []:
        if not isinstance(m, dict) or m.get("isResolved") or m.get("outcomeType") != "BINARY" or _f(m.get("probability")) is None:
            continue
        close = m.get("closeTime")
        out.append({"id": m.get("id"), "q": m.get("question") or "", "prob": round(_f(m["probability"]), 4), "vol": _f(m.get("volume")) or 0.0,
                    "liq": _f(m.get("totalLiquidity")), "bettors": m.get("uniqueBettorCount"), "url": m.get("url"),
                    "close": str(pd.Timestamp(int(close), unit="ms").date()) if isinstance(close, (int, float)) else ""})
    return out


def parse_predictit(j: dict) -> list[dict]:
    """PredictIt all markets -> open contracts [{market, contract, title, yes, prev, url}]; yes = last trade, prev = yesterday's close."""
    out = []
    for m in (j or {}).get("markets") or []:
        if m.get("status") not in (None, "Open"):
            continue
        for c in m.get("contracts") or []:
            if c.get("status") not in (None, "Open"):
                continue
            yes = _f(c.get("lastTradePrice"))
            if not yes:
                continue
            name = m.get("name") or ""
            cn = c.get("name") or ""
            out.append({"market": name, "contract": cn, "title": name if cn in ("", name) else f"{name}: {cn}", "yes": round(yes, 4),
                        "prev": _f(c.get("lastClosePrice")), "url": m.get("url")})
    return out


def parse_closed(items: list) -> list[dict]:
    """Resolved binary Gamma markets, or closed events with their markets -> [{id, q, closed (unix s), outcome 1/0, vol, token, cat}]; markets
    whose final price is not 1 or 0 are left out. An event's tags give its markets' category."""
    out = []
    pairs = [(m, e.get("tags")) for e in items or [] if isinstance(e, dict) and "markets" in e for m in e.get("markets") or []]
    pairs += [(m, [t for ev in m.get("events") or [] for t in ev.get("tags") or []]) for m in items or [] if isinstance(m, dict) and "markets" not in m]
    for m, etags in pairs:
        outs, prices, toks = _jlist(m.get("outcomes")), [_f(p) for p in _jlist(m.get("outcomePrices"))], _jlist(m.get("clobTokenIds"))
        if [str(o).lower() for o in outs] != ["yes", "no"] or len(prices) != 2 or len(toks) < 1 or prices[0] not in (0.0, 1.0) or prices[0] + prices[1] != 1:
            continue
        t = pd.to_datetime(m.get("closedTime") or m.get("umaEndDate") or m.get("endDate"), utc=True, errors="coerce")
        if pd.isna(t):
            continue
        tags = [x.get("slug") for x in etags or [] if isinstance(x, dict)]
        out.append({"id": str(m.get("id")), "q": m.get("question") or "", "closed": int(t.timestamp()), "outcome": int(prices[0]),
                    "vol": _f(m.get("volumeNum")) or _f(m.get("volume")) or 0.0, "token": toks[0], "cat": category(tags)})
    return out


def price_before(hist: list, closed: int, days: int, tol: int = 3):
    """The Yes price `days` before `closed` from CLOB history points [{t, p}]: the last point at or before then, if it is no more than
    `tol` days older."""
    at = closed - days * 86400
    pts = sorted((int(x["t"]), float(x["p"])) for x in hist or [] if "t" in x and "p" in x and int(x["t"]) <= at)
    return _r(pts[-1][1], 4) if pts and at - pts[-1][0] <= tol * 86400 else None


# ------------------------------------------------------------------ data
def poly_pool() -> tuple[list[dict], list[dict]]:
    """Open Polymarket events and markets: the POLY_PAGES x 100 events with the most 24-hour volume, plus each POLY_TAGS tag's top 50."""
    from ..cache import _cached

    def go():
        raw, errs = [], []
        for k in range(POLY_PAGES):
            try:
                page = get_json(POLY_TOP.format(offset=k * 100), TTL, min_bytes=20, timeout=40)
                raw += page if isinstance(page, list) else []
                if not isinstance(page, list) or len(page) < 100:
                    break
            except Exception as e:
                errs.append(e)
                break
        for tag in POLY_TAGS:
            try:
                page = get_json(POLY_TAG.format(tag=tag), TTL, min_bytes=2, timeout=40)
                raw += page if isinstance(page, list) else []
            except Exception as e:
                errs.append(e)
        if not raw and errs:
            raise errs[0]
        seen, uniq = set(), []
        for e in raw:
            k = e.get("slug") or e.get("id")
            if k not in seen:
                seen.add(k)
                uniq.append(e)
        evs, mks = parse_poly_events(uniq)
        if not mks:
            raise ValueError("Polymarket: no open markets in the response")
        return evs, mks
    return _cached(f"{SLUG}:pool", TTL, go)


def poly_history(token: str) -> pd.Series:
    return parse_history(get_json(CLOB_HIST.format(token=token), TTL, min_bytes=10, timeout=30))


def kalshi_series(series: str) -> list[dict]:
    return parse_kalshi(get_json(KALSHI_SERIES.format(series=quote(series)), TTL, min_bytes=10, timeout=30))


def manifold_search(term: str) -> list[dict]:
    return parse_manifold(get_json(MANIFOLD.format(term=quote(term)), TTL, min_bytes=2, timeout=30))


def predictit_all() -> list[dict]:
    return parse_predictit(get_json(PREDICTIT, TTL, min_bytes=100, timeout=40))


def watchlist() -> list[dict]:
    return [r for r in manual_rows(SLUG, "watchlist") if r.get("key")]


def _pick(cands: list[dict], how: str, vol: str, end: str, price: str = "yes") -> dict | None:
    """volume: the most traded match; soonest: the most traded of those that close first; favourite: the highest priced (the leading
    team, candidate or band of a many-outcome event)."""
    if not cands:
        return None
    if how == "favourite":
        return max(cands, key=lambda c: c.get(price) or 0)
    if how == "soonest":
        today = str(_now().date())
        live = [c for c in cands if (c.get(end) or "9999") >= today] or cands
        first = min(c.get(end) or "9999" for c in live)
        live = [c for c in live if (c.get(end) or "9999") == first]
        return max(live, key=lambda c: c.get(vol) or 0)
    return max(cands, key=lambda c: c.get(vol) or 0)


def resolve_row(row: dict, pool: list[dict] | None, why: dict) -> dict:
    """One watchlist row -> {key, label, cat, region, poly, kalshi, manifold, predictit, gap}; a venue left blank or with no match is None."""
    how = row.get("pick") or "volume"
    out = {"key": row["key"], "label": row.get("label") or row["key"], "cat": row.get("category") or "other", "region": row.get("region") or "",
           "note": row.get("note") or "", "source": row.get("source") or ""}
    p = None
    if row.get("polymarket") and pool is not None:
        p = _pick([m for m in pool if m.get("two") and matches(m["event"] + " " + m["q"] + " " + m["label"], row["polymarket"])], how, "vol", "end")
    out["poly"] = {k: p.get(k) for k in ("yes", "d1", "d7", "vol", "vol24", "vol1wk", "liq", "end", "token", "url", "id")} | {"title": p["q"]} if p else None
    k = None
    if row.get("kalshi") and ":" in row["kalshi"]:
        series, spec = row["kalshi"].split(":", 1)
        try:
            k = _pick([m for m in kalshi_series(series.strip()) if matches(m["title"] + " " + m["sub"] + " " + m["ticker"], spec)], how, "vol", "close")
        except Exception as e:
            why[f"Kalshi {series}"] = type(e).__name__
    out["kalshi"] = {"yes": k["yes"], "prev": k["prev"], "vol": k["vol"], "title": k["title"], "url": k["url"], "ticker": k["ticker"], "end": k["close"]} if k else None
    mf = None
    if row.get("manifold") and ":" in row["manifold"]:
        term, spec = row["manifold"].split(":", 1)
        try:
            mf = _pick([m for m in manifold_search(term.strip()) if matches(m["q"], spec)], "volume", "vol", "close")
        except Exception as e:
            why["Manifold"] = type(e).__name__
    out["manifold"] = {"yes": mf["prob"], "vol": mf["vol"], "title": mf["q"], "url": mf["url"], "bettors": mf["bettors"]} if mf else None
    pi = None
    if row.get("predictit"):
        try:
            pi = next((c for c in predictit_all() if matches(c["title"], row["predictit"])), None)
        except Exception as e:
            why["PredictIt"] = type(e).__name__
    out["predictit"] = {"yes": pi["yes"], "prev": pi["prev"], "title": pi["title"], "url": pi["url"]} if pi else None
    money = [v["yes"] for v in (out["poly"], out["kalshi"], out["predictit"]) if v]
    every = money + ([out["manifold"]["yes"]] if out["manifold"] else [])
    out["gap"] = _r(max(money) - min(money), 4) if len(money) >= 2 else None
    out["gap_all"] = _r(max(every) - min(every), 4) if len(every) >= 2 else None
    out["venues"] = len(every)
    return out


def rows_now() -> tuple[list[dict], dict]:
    """Every watchlist row resolved on every venue (cached an hour), and why any venue failed."""
    from ..cache import _cached

    def go():
        why: dict = {}
        try:
            pool = poly_pool()[1]
        except Exception as e:
            pool, why["Polymarket"] = None, type(e).__name__
        return [resolve_row(r, pool, why) for r in watchlist()], why
    return _cached(f"{SLUG}:rows", TTL, go)


# ------------------------------------------------------------------ the daily log (volume, liquidity and every venue's price, once a day)
LOG_FIELDS = ["date", "key", "series", "value"]


def _log_file():
    return B.SNAP_DIR / SLUG / "daily.csv"


def read_log() -> dict[tuple[str, str], pd.Series]:
    """{(key, series): daily Series} from the log; series are poly / kalshi / manifold / predictit (price), vol, liq, and cat:<key> totals."""
    f = _log_file()
    if not f.exists():
        return {}
    rows: dict = {}
    with f.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            v = _f(r.get("value"))
            if v is not None and r.get("date"):
                rows.setdefault((r["key"], r["series"]), {})[pd.Timestamp(r["date"])] = v
    return {k: pd.Series(v, dtype=float).sort_index() for k, v in rows.items()}


def log_today(today: str | None = None) -> dict:
    """Append today's readings once (the first good run of a UTC day). Background job: the server runs it at start and every 6 hours."""
    today = today or str(_now().date())
    f = _log_file()
    if f.exists() and any(line.startswith(today + ",") for line in f.read_text(encoding="utf-8").splitlines()[-400:]):
        return {"log": "exists"}
    out = []
    rows, _ = rows_now()
    for r in rows:
        for venue in ("poly", "kalshi", "manifold", "predictit"):
            if r.get(venue):
                out.append([today, r["key"], venue, r[venue]["yes"]])
        if r.get("poly"):
            out += [[today, r["key"], s, r["poly"].get(s)] for s in ("vol", "vol24", "liq") if r["poly"].get(s) is not None]
    try:
        for c in category_totals(poly_pool()[0]):
            out += [[today, f"cat:{c['key']}", s, c[s]] for s in ("vol24", "volume", "liq")]
    except Exception:
        pass
    if not out:
        return {"log": "empty"}
    f.parent.mkdir(parents=True, exist_ok=True)
    new = not f.exists()
    with f.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(LOG_FIELDS)
        w.writerows(out)
    return {"log": f"{len(out)} rows"}


# ------------------------------------------------------------------ accuracy (resolved markets, background)
def _acc_file():
    return B.SNAP_DIR / SLUG / "resolved.json"


def read_resolved() -> list[dict]:
    try:
        return json.loads(_acc_file().read_text())
    except (OSError, ValueError):
        return []


def fill_accuracy(max_new: int = ACC_PER_RUN) -> dict:
    """Resolved Polymarket markets of the last year with ACC_MIN_VOLUME or more traded: the Yes price 30 and 7 days before each closed.
    Adds up to max_new markets a run (one paced price-history call each) to resolved.json on the volume, so the sample grows."""
    have = {r["id"]: r for r in read_resolved()}
    since = (_now() - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    cands = []
    for k in range(4):
        try:
            page = get_json(POLY_CLOSED.format(offset=k * 50, since=since), DAY, min_bytes=20, timeout=40)
        except Exception:
            break
        cands += parse_closed(page if isinstance(page, list) else [])
        if not isinstance(page, list) or len(page) < 50:
            break
    fixed = 0
    for c in cands:                  # records saved before the events carried their tags: fill in the category
        r = have.get(c["id"])
        if r and r.get("cat") in (None, "other") and c["cat"] != "other":
            r["cat"], fixed = c["cat"], fixed + 1
    todo = [c for c in cands if c["id"] not in have and c["vol"] >= ACC_MIN_VOLUME][:max_new]
    added = 0
    for c in todo:
        try:      # the whole daily history (interval=max): Polymarket answers 400 to a 40-day startTs/endTs window
            h = (get_json(CLOB_HIST.format(token=c["token"]), 30 * DAY, min_bytes=10, timeout=30) or {}).get("history") or []
        except Exception:
            continue
        rec = {k: c[k] for k in ("id", "q", "closed", "outcome", "vol", "cat")} | {"p30": price_before(h, c["closed"], 30), "p7": price_before(h, c["closed"], 7)}
        have[c["id"]] = rec
        added += 1
    if added or fixed:
        _acc_file().parent.mkdir(parents=True, exist_ok=True)
        tmp = _acc_file().with_suffix(".tmp")
        tmp.write_text(json.dumps(sorted(have.values(), key=lambda r: -r["closed"])))
        tmp.replace(_acc_file())
    return {"resolved": f"{added} added, {len(have)} kept" + (f", {fixed} categorised" if fixed else "")}


def calibration(recs: list[dict], key: str, bins: int = 10) -> dict:
    """Bucket the price `key` (p30 or p7) into `bins`: per bucket the mean price, how often Yes happened, and n; plus the Brier score."""
    xs = [(r[key], r["outcome"]) for r in recs if r.get(key) is not None]
    if not xs:
        return {"n": 0, "buckets": [], "brier": None}
    p, o = np.array([x[0] for x in xs]), np.array([x[1] for x in xs])
    b = np.minimum((p * bins).astype(int), bins - 1)
    out = []
    for i in range(bins):
        m = b == i
        if m.any():
            out.append({"lo": i / bins, "hi": (i + 1) / bins, "n": int(m.sum()), "price": _r(p[m].mean(), 4), "freq": _r(o[m].mean(), 4)})
    return {"n": len(xs), "buckets": out, "brier": _r(((p - o) ** 2).mean(), 4), "base": _r(o.mean(), 4)}


BACKGROUND = [log_today, fill_accuracy]


# ------------------------------------------------------------------ payload helpers
def category_totals(evs: list[dict]) -> list[dict]:
    out = []
    for key, label in list(CAT_LABEL.items()):
        es = [e for e in evs if e["cat"] == key]
        if es:
            out.append({"key": key, "label": label, "events": len(es), "markets": sum(e["n"] for e in es), "vol24": _r(sum(e["vol24"] for e in es), 0),
                        "volume": _r(sum(e["volume"] for e in es), 0), "liq": _r(sum(e["liq"] for e in es), 0)})
    return sorted(out, key=lambda c: -c["vol24"])


def _slim(m: dict) -> dict:
    return {k: m.get(k) for k in ("q", "label", "event", "url", "cat", "yes", "d1", "d7", "vol", "vol24", "liq", "end")}


def movers(mks: list[dict], key: str, floor_key: str, floor: float, n: int = 10) -> list[dict]:
    """The n biggest absolute price changes among markets that traded at least `floor` (over the same window); one per event, so a
    ten-outcome event does not fill the list."""
    seen, out = set(), []
    for m in sorted((m for m in mks if m.get(key) is not None and (m.get(floor_key) or 0) >= floor and 0.005 < m["yes"] < 0.995),
                    key=lambda m: -abs(m[key])):
        if m["slug"] in seen:
            continue
        seen.add(m["slug"])
        out.append(_slim(m))
        if len(out) == n:
            break
    return out


def _cat_log(log: dict, series: str) -> dict:
    return {CAT_LABEL.get(k[4:], k[4:]): _pts(s, 0) for (k, ser), s in sorted(log.items()) if k.startswith("cat:") and ser == series}


def _hist_of(r: dict) -> list:
    tok = (r.get("poly") or {}).get("token")
    if not tok:
        return []
    try:
        return _pts(poly_history(tok) * 100, 2)
    except Exception:
        return []


def _flows(log: dict, key: str) -> dict:
    """Daily money behind a market from the log: volume traded each day (difference of the cumulative volume) and liquidity."""
    v, l = log.get((key, "vol")), log.get((key, "liq"))
    return {"volume": _pts(v.diff().clip(lower=0).dropna(), 0) if v is not None and len(v) > 1 else [],
            "liq": _pts(l, 0) if l is not None else []}


# ------------------------------------------------------------------ endpoints
def _overview_now() -> dict:
    out = B.payload({}, sources=[POLY_TOP.format(offset=0)])
    try:
        evs, mks = poly_pool()
        out["movers24"] = movers(mks, "d1", "vol24", MIN_VOL24)
        out["movers7"] = movers(mks, "d7", "vol1wk", MIN_VOL1WK)
        top, seen = [], set()
        for m in sorted(mks, key=lambda m: -(m["vol24"] or 0)):
            if m["slug"] not in seen:
                seen.add(m["slug"])
                top.append(_slim(m))
            if len(top) == 12:
                break
        out["top"] = top
        out["events"] = [{k: e[k] for k in ("title", "url", "cat", "volume", "vol24", "liq", "n", "end")} for e in sorted(evs, key=lambda e: -e["vol24"])[:12]]
        out["cats"] = category_totals(evs)
        out["totals"] = {"events": len(evs), "markets": len(mks), "vol24": _r(sum(e["vol24"] for e in evs), 0), "liq": _r(sum(e["liq"] for e in evs), 0)}
    except Exception as e:
        out["pool_error"] = type(e).__name__
    log = read_log()
    out["cat_log"] = _cat_log(log, "vol24")
    out["log_since"] = min((str(s.index[0].date()) for s in log.values() if len(s)), default=None)
    out["thresholds"] = {"vol24": MIN_VOL24, "vol1wk": MIN_VOL1WK}
    out["as_of"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return out


def _markets_now() -> dict:
    out = B.payload({}, sources=[POLY_TOP.format(offset=0)])
    rows, why = rows_now()
    log = read_log()
    items = []
    for r in rows:
        items.append({**{k: r[k] for k in ("key", "label", "cat", "region", "note", "source")}, "poly": r["poly"], "hist": _hist_of(r), **_flows(log, r["key"])})
    out["items"] = items
    out["missing"] = why
    out["cites"] = manual_sources(SLUG, "watchlist")
    out["as_of"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return out


def _categories_now() -> dict:
    out = B.payload({}, sources=[POLY_TOP.format(offset=0)])
    try:
        evs, mks = poly_pool()
        tot = {c["key"]: c for c in category_totals(evs)}
        cats = []
        for key, label, _, _ in CATEGORIES:
            ms = sorted((m for m in mks if m["cat"] == key), key=lambda m: -(m["vol24"] or 0))
            top, seen = [], set()
            for m in ms:
                if m["slug"] not in seen:
                    seen.add(m["slug"])
                    top.append(_slim(m))
                if len(top) == 8:
                    break
            cats.append({"key": key, "label": label, "totals": tot.get(key), "top": top})
        out["cats"] = cats
    except Exception as e:
        out["cats"], out["pool_error"] = [], type(e).__name__
    log = read_log()
    out["log"] = {s: _cat_log(log, s) for s in ("vol24", "liq")}
    out["as_of"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return out


def _venues_now() -> dict:
    out = B.payload({}, sources=[POLY_TOP.format(offset=0), PREDICTIT])
    rows, why = rows_now()
    log = read_log()
    items = []
    for r in rows:
        hist = {v: _pts(log[(r["key"], v)] * 100, 2) for v in ("poly", "kalshi", "manifold", "predictit") if (r["key"], v) in log}
        items.append({**r, "log": hist})
    out["items"] = sorted(items, key=lambda r: (-(r["venues"]), -(r["gap"] or 0)))
    out["missing"] = why
    out["as_of"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return out


def _regions_now() -> dict:
    out = B.payload({}, sources=[POLY_TOP.format(offset=0)])
    rows, why = rows_now()
    try:
        mks = poly_pool()[1]
    except Exception as e:
        mks, out["pool_error"] = [], type(e).__name__
    taken = {(r.get("poly") or {}).get("id") for r in rows}
    regs = []
    for reg, label in REGION_LABEL.items():
        mine = [{**{k: r[k] for k in ("key", "label", "cat", "note")}, "poly": r["poly"], "kalshi": r["kalshi"], "manifold": r["manifold"], "predictit": r["predictit"],
                 "hist": _hist_of(r)} for r in rows if r["region"] == reg]
        listed, seen = [], set()
        for m in sorted((m for m in mks if reg in regions_of(m["tags"]) and m["id"] not in taken and m.get("two")), key=lambda m: -(m["vol24"] or 0)):
            if m["slug"] not in seen:
                seen.add(m["slug"])
                listed.append(_slim(m))
            if len(listed) == 8:
                break
        regs.append({"key": reg, "label": label, "watch": mine, "listed": listed})
    out["regions"] = regs
    out["missing"] = why
    out["as_of"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return out


def _accuracy_now() -> dict:
    recs = read_resolved()
    out = {"n": len(recs), "p30": calibration(recs, "p30"), "p7": calibration(recs, "p7"),
           "by_cat": [{"cat": CAT_LABEL.get(c, c), **{k: v for k, v in calibration([r for r in recs if r.get("cat") == c], "p7").items() if k in ("n", "brier", "base")}}
                      for c in sorted({r.get("cat") or "other" for r in recs})],
           "misses": sorted(({k: r[k] for k in ("q", "closed", "outcome", "p7", "p30", "vol")} for r in recs if r.get("p7") is not None and abs(r["p7"] - r["outcome"]) >= 0.7),
                            key=lambda r: -r["vol"])[:12],
           "since": time.strftime("%Y-%m-%d", time.gmtime(min(r["closed"] for r in recs))) if recs else None,
           "latest": time.strftime("%Y-%m-%d", time.gmtime(max(r["closed"] for r in recs))) if recs else None,
           "min_volume": ACC_MIN_VOLUME, "stale": {}, "updated": int(time.time()),
           "retired": sorted(manual_rows(SLUG, "retired"), key=lambda r: r["date"], reverse=True)}
    out["as_of"] = out["latest"]
    return out


def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, size, start of the body), to check reachability and layouts from
    Railway. Read with Actions > show-json on /api/prediction-markets/layout."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    from ._base import UA
    tok = None
    try:
        tok = next((m["token"] for m in poly_pool()[1] if m.get("token")), None)
    except Exception:
        pass
    urls = {"polymarket events": POLY_TOP.format(offset=0).replace("limit=100", "limit=1"), "polymarket tag fed-rates": POLY_TAG.format(tag="fed-rates").replace("limit=50", "limit=1"),
            "polymarket closed": POLY_CLOSED.format(offset=0, since="2026-01-01").replace("limit=50", "limit=1"), "clob time": CLOB + "/time",
            "kalshi KXFEDDECISION": KALSHI_SERIES.format(series="KXFEDDECISION").replace("limit=200", "limit=1"),
            "manifold search": MANIFOLD.format(term="fed").replace("limit=20", "limit=1"), "predictit all": PREDICTIT}
    if tok:
        urls["clob history"] = CLOB_HIST.format(token=tok)
    for r in watchlist():
        if r.get("kalshi") and ":" in r["kalshi"]:
            s = r["kalshi"].split(":", 1)[0].strip()
            urls[f"kalshi {s}"] = KALSHI_SERIES.format(series=s).replace("limit=200", "limit=1")

    def one(u):
        try:
            r = requests.get(u, headers=UA, timeout=25)
            return {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type", ""), "start": r.text[:300]}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=4) as ex:
        out = dict(zip(urls, ex.map(one, urls.values())))
    out["log rows"] = sum(len(s) for s in read_log().values())
    out["resolved kept"] = len(read_resolved())
    return out


def READINGS() -> list[dict]:
    """What changed since yesterday, from cached payloads only: each watchlist market's Polymarket probability (%), lean +1 when its odds
    rose over 24 hours and -1 when they fell (half a point or more); the three biggest moves say so in the note."""
    from ..cache import _cache
    d = (_cache.get(f"topic:{SLUG}:markets") or (0, {}))[1] or {}
    items = [i for i in d.get("items") or [] if (i.get("poly") or {}).get("yes") is not None]
    big = {i["key"] for i in sorted(items, key=lambda i: -abs((i["poly"].get("d1") or 0)))[:3] if abs(i["poly"].get("d1") or 0) >= 0.005}
    out = []
    for i in items:
        p, d1 = i["poly"], i["poly"].get("d1") or 0
        lean = 1 if d1 >= 0.005 else -1 if d1 <= -0.005 else 0
        out.append({"tab": "markets", "key": f"p_{i['key']}", "label": f"{i['label']} (Polymarket, %)", "value": round(p["yes"] * 100, 1), "lean": lean,
                    **({"note": f"biggest mover: {d1 * 100:+.1f} pts in 24 hours"} if i["key"] in big else {})})
    return out


def watchlist_daily_volume(log: dict | None = None) -> pd.Series:
    """Money traded on the watchlist's Polymarket markets each logged day: the sum of each market's logged 24-hour volume, or, for days
    logged before that was kept (26 Oct to 3 Nov 2026), the day's change in its all-time volume."""
    log = read_log() if log is None else log
    keys = {k for (k, ser) in log if not k.startswith("cat:") and ser in ("vol", "vol24")}
    days = {}
    for k in keys:
        v24, v = log.get((k, "vol24")), log.get((k, "vol"))
        diff = v.diff().clip(lower=0).dropna() if v is not None and len(v) > 1 else pd.Series(dtype=float)
        for t, x in (diff if v24 is None else pd.concat([diff[~diff.index.isin(v24.index)], v24])).items():
            days[t] = days.get(t, 0.0) + float(x)
    return pd.Series(days, dtype=float).sort_index()


def monthly_brier(recs: list[dict], key: str = "p30", min_n: int = 10) -> pd.Series:
    """Brier score of `key` (the price 30 days before resolution) by the calendar month the markets resolved in (UTC), months with
    min_n or more markets."""
    xs = [(pd.Timestamp(r["closed"], unit="s").to_period("M"), (r[key] - r["outcome"]) ** 2) for r in recs if r.get(key) is not None]
    if not xs:
        return pd.Series(dtype=float)
    d = pd.DataFrame(xs, columns=["m", "sq"]).groupby("m")["sq"].agg(["mean", "size"])
    return d.loc[d["size"] >= min_n, "mean"]


def SIGNALS() -> list[dict]:
    """The owner's approved signals (data/signals/watchlist.json, 3 Nov 2026), from cached data only: the watchlist rows as last
    resolved (memory), the daily log and resolved.json (the volume). Each row's `crossed` is this module's own test of its watch point."""
    from ..cache import _cache
    rows = ((_cache.get(f"{SLUG}:rows") or (0, ([], {})))[1] or ([], {}))[0]
    out = []

    # biggest_move: the largest 24-hour change in a watchlist market's Polymarket price
    # a market in its last day, or already priced as settled (1% or less, 99% or more), is resolving, not moving
    tomorrow = str((_now() + pd.Timedelta(days=1)).date())
    moves = [(abs(r["poly"]["d1"]), r) for r in rows if r.get("poly") and r["poly"].get("d1") is not None
             and (r["poly"].get("end") or "9999") > tomorrow and 0.01 < (r["poly"].get("yes") or 0) < 0.99]
    if moves:
        _, r = max(moves, key=lambda x: x[0])
        d1 = round(r["poly"]["d1"] * 100, 1)
        out.append({"key": "biggest_move", "tab": "markets", "label": "Biggest 24-hour move on the watchlist", "value": round(d1, 1), "unit": " pts",
                    "lean": 1 if d1 > 0 else -1 if d1 < 0 else 0, "watch": "any market moves 10 points in a day", "crossed": bool(abs(d1) >= 10),
                    "note": f"{r['label']}: {r['poly']['yes'] * 100:.0f}% on Polymarket"})
    else:
        out.append({"key": "biggest_move", "tab": "markets", "label": "Biggest 24-hour move on the watchlist", "value": None, "lean": 0,
                    "watch": "any market moves 10 points in a day", "crossed": False,
                    "note": "no open watchlist market outside its last day" if rows else "waiting for the first fetch of the watchlist"})

    # venue_gap: Polymarket against Kalshi on the rows that matched both (the same question, checked by the watchlist keywords)
    gaps = [(round(abs(r["poly"]["yes"] - r["kalshi"]["yes"]) * 100, 1), r) for r in rows if r.get("poly") and r.get("kalshi")]
    if gaps:
        g, r = max(gaps, key=lambda x: x[0])
        out.append({"key": "venue_gap", "tab": "venues", "label": "Cross-venue gap (Polymarket vs Kalshi)", "value": round(g, 1), "unit": " pts", "lean": 0,
                    "watch": "above 5 points on the same event", "crossed": bool(g > 5),
                    "note": f"{r['label']}: Polymarket {r['poly']['yes'] * 100:.1f}%, Kalshi {r['kalshi']['yes'] * 100:.1f}% ({len(gaps)} questions on both)"})
    else:
        out.append({"key": "venue_gap", "tab": "venues", "label": "Cross-venue gap (Polymarket vs Kalshi)", "value": None, "lean": 0,
                    "watch": "above 5 points on the same event", "crossed": False, "note": "no watchlist question matched on both venues yet"})

    # volume: today's 24-hour volume on the watchlist against the average logged day of the last 30
    today = sum(r["poly"].get("vol24") or 0 for r in rows if r.get("poly"))
    daily = watchlist_daily_volume()
    base = daily[daily.index >= daily.index.max() - pd.Timedelta(days=29)] if len(daily) else daily
    ok = bool(rows) and len(base) >= 5 and base.mean() > 0
    ratio = today / base.mean() if ok else None
    out.append({"key": "volume", "tab": "markets", "label": "Daily volume on the watchlist", "value": round(today) if rows else None, "unit": " $",
                "lean": 0 if ratio is None else 1 if ratio >= 1.2 else -1 if ratio <= 0.8 else 0, "watch": "doubles its 30-day average",
                "crossed": bool(ratio is not None and ratio >= 2),
                "note": f"{ratio:.1f}x the average logged day (${base.mean() / 1e6:.1f}m, {len(base)} days)" if ok
                else f"the 30-day average builds from the daily log ({len(base)} of 5 days needed)"})

    # calibration: Brier score of the price 30 days out, by month of resolution; worse = higher
    mb = monthly_brier(read_resolved())
    done = mb[mb.index < pd.Timestamp(_now()).to_period("M")].tail(3)
    if len(done):
        last = float(done.iloc[-1])
        months = list(done.index)
        back_to_back = len(months) == 3 and months[1] == months[0] + 1 and months[2] == months[1] + 1   # a month under 10 markets breaks the run
        worse2 = back_to_back and done.iloc[0] < done.iloc[1] < done.iloc[2]
        prev = float(done.iloc[-2]) if len(done) > 1 else None
        out.append({"key": "calibration", "tab": "accuracy", "label": "Calibration: resolved markets priced 30 days out (Brier)", "value": round(last, 3),
                    "lean": 0 if prev is None else 1 if last < prev else -1 if last > prev else 0, "watch": "Brier score worsens two months running",
                    "crossed": bool(worse2), "note": ", ".join(f"{m.strftime('%b %Y')} {v:.3f}" for m, v in done.items()) + " (lower is better)"})
    else:
        out.append({"key": "calibration", "tab": "accuracy", "label": "Calibration: resolved markets priced 30 days out (Brier)", "value": None, "lean": 0,
                    "watch": "Brier score worsens two months running", "crossed": False, "note": "the resolved-market sample is still being built"})
    return out


def _cached_ep(name, fn, ttl=TTL):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"overview": _cached_ep("overview", _overview_now), "markets": _cached_ep("markets", _markets_now), "categories": _cached_ep("categories", _categories_now),
             "venues": _cached_ep("venues", _venues_now), "regions": _cached_ep("regions", _regions_now), "accuracy": _cached_ep("accuracy", _accuracy_now, 1800),
             "layout": _cached_ep("layout", _layout_now, 1800)}
