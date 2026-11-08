"""Luxury Tracker (/luxury): watches and bags on the second-hand market.

The question: for each item, what does it cost new today, what does it sell for second-hand, and what return (or loss) would a buyer
at retail see after platform fees, over time. Not investment advice: no buy or sell calls.

overview   the Rolex basket's resale premium or discount to retail (median across the starter references), the bag basket's
           resale-to-retail ratio, one line on where the market is, and a card per item (retail, latest resale, premium, 1-year change,
           a photo, whether the brand site has it in stock (stock.csv, hand-entered and dated: the brand sites refuse servers), how many
           are listed second-hand (Chrono24 from the weekly log, eBay UK from the daily feed), and links to the retail and resale pages)
watches    retail vs resale over time per reference, the premium-to-retail line, a table (retail, resale, premium, 1y and 3y change)
bags       the same for bags, plus retail price inflation per brand per year (the price-increase calendar)
roi        for a buyer at retail on a chosen date, what they would net today after the selling platform's fee, by platform; a
           calculator (item, buy date, buy price, platform) against the S&P 500 and UK CPI over the same period; nothing is stored
heat       a heat score for watches and one for bags, like Pokémon's: the basket premium against its own history, the 1-year change,
           the share of items above retail, and the public indices' direction
fees       the platform fee table with links
liquidity  how easily each item trades: attention (monthly Wikipedia pageviews per item since July 2015, a demand proxy: the Wikimedia
           REST API, free, as trends.py uses it), with the 12-month z-score per item and the basket's attention line; auction results
           (auctions.csv, one row per lot at Phillips, Christie's, Sotheby's, Bonhams: hammer or price with premium against the estimate
           midpoint) and the sell-through rate per sale (auction_sales.csv, lots sold / offered) as a liquidity series; eBay UK active
           listings per item once a day (luxury_ebay.py: the Browse API with the owner's EBAY_APP_ID and EBAY_CERT_ID, a daily snapshot
           on the volume so history accrues; "not set up yet" until the keys are set); the weekly manual log (liquidity.csv: Chrono24
           listing counts per reference, StockX bid, ask and last sale for bags, WatchCharts days to sell, Fashionphile sold counts where
           visible), with the StockX bid-ask spread per bag; and a liquidity score per market, like the heat score: supply (listings
           against their own history, more = looser), the spread, auction sell-through, days to sell and attention

Data. The brand sites and the resale platforms have no free API and refuse servers, so prices are hand-entered, dated and sourced
(data/luxury/*.csv): items.csv (one row per item), retail.csv (official list prices as they change), resale.csv (asking or sold points
per item), fees.csv (platform fee schedules), indices.csv (public resale indices' headline figures). Rows marked 'verify' were not
confirmed on the cited page. Live context from FRED: US and UK CPI (prices in real terms), USD, CHF and EUR to GBP, the S&P 500.

Leans in READINGS(): +1 means the market is heating (resale above retail, score up), -1 cooling, 0 neutral.
"""
from __future__ import annotations

import re
import time
from io import StringIO
from urllib.parse import quote

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from ._base import DAY, _pts, _r, fetch, handled, manual_rows, manual_sources
from .trends import BOT as WIKI_BOT, parse_wiki
from . import luxury_ebay as EBAY

SLUG = "luxury"
TOPIC = Topic(SLUG, "Luxury Tracker: watches & bags",
              "Rolex steel sports references and designer bags: what they cost new, what they sell for second-hand, the premium or discount to "
              "retail over time, what a buyer at retail would net after platform fees, and a heat score for each market.",
              "luxury", (("overview", "Overview"), ("watches", "Watches"), ("bags", "Bags"), ("roi", "ROI"), ("heat", "Market heat"), ("liquidity", "Liquidity"), ("fees", "Fees & how to sell")),
              ("overview", "watches", "bags", "roi", "heat", "liquidity", "fees"), icon="chart", order=36)

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
FRED_IDS = {"cpi_us": "CPIAUCSL", "cpi_uk": "GBRCPIALLMINMEI", "gbpusd": "DEXUSUK", "chfusd": "DEXSZUS", "eurusd": "DEXUSEU", "sp500": "SP500"}
ONS_CPI = "https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/d7bt/mm23"   # UK CPI index (2015=100)
NASDAQ_SPX = "https://api.nasdaq.com/api/quote/SPX/historical?assetclass=index&fromdate={a}&todate={b}&limit=9999"
PLAIN_UA = {"User-Agent": "dashboards/1.0 (+https://github.com/mcmarcocheung98-max/dashboards)"}   # FRED answers a plain client at once where the browser UA stalls
NASDAQ_HEADERS = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
WIKI_MONTHLY = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/monthly/2015070100/{b}"
WIKI_HEALTH = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"     # the article's lead image (freely licensed), for the item cards
FX_FALLBACK = {"USD": 0.78, "CHF": 0.88, "EUR": 0.86, "HKD": 0.10}        # GBP per unit, rough 2020-2026 averages, only when FRED has never answered
CATEGORIES = (("watch", "Watches"), ("bag", "Bags"))
DEFAULT_PLATFORM = {"watch": "Chrono24", "bag": "Vestiaire Collective"}
WINDOW_DAYS = 3 * 365
MAX_POINT_AGE = 550          # a resale point older than this (days, 18 months) no longer stands for an item in the monthly basket: hand-entered points come about yearly
MIN_ITEMS = {"watch": 4, "bag": 3}

SOURCES = [{"name": "Hand-entered, cited per row: brand list prices (Rolex, Hermès, Chanel, Louis Vuitton, Celine, Saint Laurent), resale asking and sold prices "
                    "(Chrono24, WatchCharts, Bob's Watches, Watchfinder, Subdial, Vestiaire Collective, Fashionphile, Rebag, The RealReal, Sotheby's, eBay), "
                    "platform fee schedules, and the public indices' headline figures",
            "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/luxury", "cadence": "monthly / as prices change"},
           {"name": "Chrono24 ChronoPulse and WatchCharts market indices (headline figures, hand-entered)", "url": "https://watchcharts.com/watches/market_index", "cadence": "monthly"},
           {"name": "Rebag Clair report, The RealReal resale report, Knight Frank Luxury Investment Index (hand-entered)", "url": "https://www.knightfrank.com/wealthreport", "cadence": "yearly"},
           {"name": "Wikimedia REST API: monthly pageviews of each item's English Wikipedia article since July 2015 (attention, a demand proxy)", "url": "https://wikimedia.org/api/rest_v1/", "cadence": "daily"},
           {"name": "Wikipedia page summaries: each article's lead image for the item cards (an owner-supplied image URL in items.csv takes precedence)", "url": "https://en.wikipedia.org/api/rest_v1/", "cadence": "daily"},
           {"name": "Hand-entered, dated: whether the brand site has each item in stock (stock.csv), read by hand because the brand sites refuse servers", "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/luxury", "cadence": "weekly"},
           {"name": "eBay Browse API (eBay UK): active fixed-price listings per item, count and asking prices, one snapshot a day once EBAY_APP_ID and EBAY_CERT_ID are set", "url": "https://developer.ebay.com/api-docs/buy/browse/overview.html", "cadence": "daily"},
           {"name": "FRED: US CPI (CPIAUCSL), UK CPI (GBRCPIALLMINMEI; ONS D7BT when it answers), USD, CHF and EUR to GBP (DEXUSUK, DEXSZUS, DEXUSEU), S&P 500 (SP500)",
            "url": "https://fred.stlouisfed.org/", "cadence": "daily"}]
NOTES = ("Hand-entered points are sparse: a premium is the last resale point against the list price in force on that date, not a daily market. "
         "Asking prices run above sold prices; condition, box and papers, and VAT or import duty on cross-border sales all move the figure. "
         "Rows marked 'verify' were not confirmed on the cited page. Not investment advice: the page gives no buy or sell calls.")
FOOTER = "Not investment advice. Prices are hand-entered, dated and cited; a return shown here is what a past buyer would have seen, not a forecast."

HEAT = {"level": ("Premium vs its own history", "The basket's resale premium to retail as a z-score against its last three years: +1 is one standard deviation hotter than usual for this market."),
        "change_1y": ("1-year change in resale prices", "The equal-weight resale index, change on a year: +15% scores +1, -15% scores -1."),
        "breadth": ("Share of items above retail", "The share of the basket's items selling above their list price: all of them scores +2, none -2, half 0."),
        "indices": ("Public indices' direction", "The hand-entered public indices (ChronoPulse, WatchCharts, Subdial, Rebag, Knight Frank) for this market, each scored on its change on a year (+10% = +1; a premium quoted in percentage points: +5 points = +1), then averaged.")}


def _now() -> pd.Timestamp:
    return pd.Timestamp.now("UTC").tz_localize(None).normalize()


def _f(v):
    try:
        v = float(str(v).replace(",", "").replace("£", "").replace("$", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _verify(r: dict) -> bool:
    return "verify" in (r.get("note") or "").lower()


# ------------------------------------------------------------------ the hand-entered files
def items(with_watchlist: bool = False) -> list[dict]:
    """items.csv (the source of truth) and, when asked, watchlist.csv rows the owner added in the same shape."""
    out, seen = [], set()
    for name in ("items",) + (("watchlist",) if with_watchlist else ()):
        for r in manual_rows(SLUG, name):
            if r.get("id") and r.get("category") in dict(CATEGORIES) and r["id"] not in seen:
                seen.add(r["id"])
                out.append({**r, "name": f"{r.get('brand', '')} {r.get('model', '')}".strip(), "launched": r.get("date"), "currency": r.get("currency") or "GBP",
                            "from_watchlist": name == "watchlist"})
    return out


def rows(name: str) -> list[dict]:
    return sorted(manual_rows(SLUG, name), key=lambda r: r["date"])


def cited(*names) -> list[dict]:
    out = [x for n in names for x in manual_sources(SLUG, n)]
    return sorted(out, key=lambda x: x["date"], reverse=True)[:12]


def fees() -> list[dict]:
    out = []
    for r in rows("fees"):
        out.append({**r, "seller_pct": _f(r.get("seller_pct")), "buyer_pct": _f(r.get("buyer_pct")) or 0.0, "payout_days": _f(r.get("payout_days")), "verify": _verify(r)})
    return out


# ------------------------------------------------------------------ FRED: CPI, FX, S&P 500
def parse_fred(text: str) -> pd.Series:
    """observation_date,<ID> with '.' for missing days -> daily/monthly Series."""
    df = pd.read_csv(StringIO(text))
    if df.shape[1] < 2:
        raise ValueError("FRED: unexpected layout")
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values, index=pd.to_datetime(df.iloc[:, 0], errors="coerce")).dropna()
    if len(s) < 12:
        raise ValueError(f"FRED: {len(s)} rows")
    return s.sort_index()


def parse_ons(text: str) -> pd.Series:
    """ONS generator CSV: '"2015 JAN","100.0"' rows after a few header lines -> monthly index."""
    out = {}
    for ln in text.splitlines():
        m = re.match(r'^"?(\d{4}) ([A-Z]{3})"?,"?([\d.]+)"?', ln.strip())
        if m:
            out[pd.Timestamp(f"{m.group(1)}-{m.group(2).title()}-01")] = float(m.group(3))
    if len(out) < 12:
        raise ValueError("ONS: no monthly rows")
    return pd.Series(out).sort_index()


def fred(key: str) -> pd.Series:
    """FRED's CSV through curl first (FRED resets python-requests connections from Railway, see _base._download), then through
    requests with a plain user-agent (some proxies stall the browser UA and break curl's HTTP/2 stream); either way the disk snapshot serves when both fail."""
    url = FRED.format(id=FRED_IDS[key])
    try:
        return parse_fred(fetch(url, DAY, curl=True, timeout=25, min_bytes=300))
    except Exception as e:
        try:
            return parse_fred(fetch(url, DAY, curl=False, timeout=40, min_bytes=300, headers=PLAIN_UA))
        except Exception:
            raise e


def cpi_uk() -> tuple[pd.Series, str]:
    """ONS CPI (D7BT) when it answers, else FRED's copy of the OECD series (which stops in 2025); the ONS failure is then handled."""
    try:
        return parse_ons(fetch(ONS_CPI, DAY, timeout=25, min_bytes=300)), "ONS"
    except Exception:
        s = fred("cpi_uk")
        handled(ONS_CPI, "ONS did not answer; UK CPI from FRED's copy of the OECD series")
        return s, "FRED"


def sp500() -> tuple[pd.Series, str]:
    """S&P 500 daily closes: FRED first, Nasdaq's index quote API when FRED fails (then the FRED failure is handled)."""
    try:
        return fred("sp500"), "FRED"
    except Exception as e:
        try:
            s = B.nasdaq_daily("SPX", "2016-01-01", lambda url, ttl, **k: __import__("json").loads(fetch(url, ttl, headers=NASDAQ_HEADERS, **k)), assetclass="index")
            handled(FRED.format(id=FRED_IDS["sp500"]), "FRED did not answer; S&P 500 from Nasdaq's quote API")
            return s, "Nasdaq"
        except Exception:
            raise e


def fx() -> dict:
    """GBP per USD, CHF and EUR, monthly means, from FRED's daily fixings; FX_FALLBACK (flagged) when FRED has never answered."""
    out, fallback = {"GBP": None}, False
    try:
        usd_per_gbp = fred("gbpusd").resample("MS").mean()
        out["USD"] = 1 / usd_per_gbp
        try:
            out["CHF"] = 1 / (fred("chfusd").resample("MS").mean() * usd_per_gbp)
        except Exception:
            out["CHF"] = None
        try:
            out["EUR"] = fred("eurusd").resample("MS").mean() / usd_per_gbp
        except Exception:
            out["EUR"] = None
    except Exception:
        fallback = True
    for k, v in FX_FALLBACK.items():
        if out.get(k) is None:
            out[k] = v
            fallback = fallback or k in ("USD",)
    return {"rates": out, "fallback": fallback}


def _fx_cached() -> dict:
    from ..cache import _cached
    return _cached(f"topic:{SLUG}:fx", 6 * 3600, fx)


def to_gbp(price: float, cur: str, date: pd.Timestamp, FX: dict | None = None) -> float | None:
    cur = (cur or "GBP").upper()
    if cur == "GBP":
        return price
    FX = FX or _fx_cached()
    r = FX["rates"].get(cur)
    if r is None:
        return None
    if isinstance(r, pd.Series):
        m = date.to_period("M").to_timestamp()
        v = r.get(m)
        if v is None or not np.isfinite(v):
            v = r[r.index <= m].iloc[-1] if (r.index <= m).any() else r.iloc[0]
        return price * float(v)
    return price * float(r)


# ------------------------------------------------------------------ per item: retail steps, resale points, premium
def retail_series(item: dict, FX: dict | None = None) -> pd.Series:
    """List price (GBP) as it changed: one point per change, carried forward by callers (a step)."""
    pts = {}
    for r in rows("retail"):
        if r.get("item") == item["id"] and _f(r.get("price")) is not None:
            v = to_gbp(_f(r["price"]), r.get("currency") or item["currency"], pd.Timestamp(r["date"]), FX)
            if v is not None:
                pts[pd.Timestamp(r["date"])] = v
    return pd.Series(pts, dtype=float).sort_index()


def retail_at(steps: pd.Series, t: pd.Timestamp):
    if not len(steps):
        return None
    s = steps[steps.index <= t]
    return float(s.iloc[-1]) if len(s) else None


def resale_points(item: dict, FX: dict | None = None) -> list[dict]:
    """Every resale row for the item in GBP, oldest first: {date, price, kind, condition, platform, source, note, verify}."""
    out = []
    for r in rows("resale"):
        if r.get("item") != item["id"] or _f(r.get("price")) is None:
            continue
        t = pd.Timestamp(r["date"])
        v = to_gbp(_f(r["price"]), r.get("currency") or "GBP", t, FX)
        if v is None:
            continue
        out.append({"date": str(t.date()), "t": t, "price": _r(v, 0), "kind": (r.get("kind") or "asking").lower(), "condition": r.get("condition") or "",
                    "platform": r.get("platform") or "", "source": r.get("source"), "note": r.get("note") or "", "verify": _verify(r), "orig": f"{r['price']} {r.get('currency') or 'GBP'}"})
    return sorted(out, key=lambda x: (x["t"], x["kind"] != "sold"))      # on one date a sold point comes first


def resale_series(points: list[dict]) -> pd.Series:
    """One price per date (sold over asking on the same date)."""
    s = {}
    for p in points:
        if p["t"] not in s or (p["kind"] == "sold" and s[p["t"]][1] != "sold"):
            s[p["t"]] = (p["price"], p["kind"])
    return pd.Series({t: v for t, (v, _) in s.items()}, dtype=float).sort_index()


def premium_series(resale: pd.Series, steps: pd.Series) -> pd.Series:
    out = {}
    for t, v in resale.items():
        rt = retail_at(steps, t)
        if rt:
            out[t] = v / rt - 1
    return pd.Series(out, dtype=float)


def _near(s: pd.Series, t: pd.Timestamp, tol_days: int):
    """The point of s nearest to t within tol_days, else None."""
    if not len(s):
        return None
    d = (s.index - t).days
    i = int(np.argmin(np.abs(d)))
    return float(s.iloc[i]) if abs(d[i]) <= tol_days else None


def change_over(s: pd.Series, years: int, tol_days: int):
    if len(s) < 2:
        return None
    last_t, last = s.index[-1], float(s.iloc[-1])
    was = _near(s[s.index < last_t], last_t - pd.Timedelta(days=int(365.25 * years)), tol_days)
    return _r(last / was - 1, 4) if was else None


def item_view(item: dict, FX: dict | None = None) -> dict:
    """Everything one item's cards and charts need."""
    steps, pts = retail_series(item, FX), resale_points(item, FX)
    res = resale_series(pts)
    prem = premium_series(res, steps)
    now = _now()
    latest = pts[-1] if pts else None
    if latest and latest["kind"] != "sold":                             # a sold point within 90 days of the latest asking price stands for it
        sold = [p for p in pts if p["kind"] == "sold" and (latest["t"] - p["t"]).days <= 90]
        if sold:
            latest = sold[-1]
    retail_now = retail_at(steps, now)
    prem_now = _r(latest["price"] / retail_now - 1, 4) if latest and retail_now else None
    res_l = res                                                          # the 1y and 3y changes end at the same point the card shows
    if latest:
        res_l = res[res.index <= latest["t"]].copy()
        res_l.loc[latest["t"]] = latest["price"]
    return {"id": item["id"], "name": item["name"], "brand": item.get("brand"), "model": item.get("model"), "reference": item.get("reference"), "category": item["category"],
            "launched": item.get("launched"), "url": item.get("source"), "note": item.get("note") or "", "from_watchlist": item.get("from_watchlist", False),
            "retail_now": _r(retail_now, 0), "retail_date": str(steps.index[-1].date()) if len(steps) else None, "retail_points": _pts(steps, 0),
            "retail_first": _r(float(steps.iloc[0]), 0) if len(steps) else None, "retail_change_1y": change_over(_step_monthly(steps), 1, 40) if len(steps) else None,
            "resale_points": [{k: v for k, v in p.items() if k != "t"} for p in pts], "resale_series": _pts(res, 0), "premium_series": _pts(prem, 4),
            "latest": {k: v for k, v in latest.items() if k != "t"} if latest else None, "premium": prem_now,
            "change_1y": change_over(res_l, 1, 180), "change_3y": change_over(res_l, 3, 180),
            "n_points": len(pts), "n_verify": sum(1 for p in pts if p["verify"]) + sum(1 for r in rows("retail") if r.get("item") == item["id"] and _verify(r))}


def _step_monthly(steps: pd.Series, start: str = "2019-12-01") -> pd.Series:
    """A step series sampled at month ends up to now (list price in force)."""
    if not len(steps):
        return pd.Series(dtype=float)
    months = pd.date_range(max(pd.Timestamp(start), steps.index[0].to_period("M").to_timestamp("M")), _now(), freq="ME")
    return pd.Series({m: retail_at(steps, m) for m in months}, dtype=float).dropna()


# ------------------------------------------------------------------ baskets: monthly premium, ratio, index, breadth
def chain_index(df: pd.DataFrame, min_items: int = 3) -> pd.Series:
    """Equal-weight chain-linked index (100 at the first month with min_items prices), as in pokemon_cards: each month's change is the
    mean log change of the items priced in both months, so an item joining or leaving does not move it."""
    if df.empty:
        return pd.Series(dtype=float)
    r = np.log(df).diff().clip(-1.5, 1.5)
    n = r.notna().sum(axis=1)
    m = r.mean(axis=1).where(n >= min_items)
    have = df.notna().sum(axis=1)
    if not (have >= min_items).any():
        return pd.Series(dtype=float)
    start = have[have >= min_items].index.min()
    m = m[m.index >= start].fillna(0)
    m.iloc[0] = 0.0
    return 100 * np.exp(m.cumsum())


def rolling_z(s: pd.Series, min_n: int = 12, window_days: int = WINDOW_DAYS) -> pd.Series:
    s = s.dropna().sort_index()
    out = {}
    for t, v in s.items():
        w = s[(s.index > t - pd.Timedelta(days=window_days)) & (s.index <= t)]
        if len(w) < min_n:
            continue
        sd = float(w.std(ddof=0))
        out[t] = 0.0 if sd == 0 else float(np.clip((v - w.mean()) / sd, -3, 3))
    return pd.Series(out, dtype=float)


def basket(cat: str, views: list[dict] | None = None, FX: dict | None = None) -> dict:
    """Month by month (month ends from Dec 2019): each item's last resale point within MAX_POINT_AGE days against the list price then in
    force; the median premium, the median resale/retail ratio, the equal-weight resale index, the share of items above retail."""
    views = views if views is not None else [item_view(i, FX) for i in items() if i["category"] == cat]
    months = pd.date_range("2019-12-31", _now(), freq="ME")
    prem, res = {}, {}
    for v in views:
        steps = pd.Series({pd.Timestamp(t, unit="s"): p for t, p in v["retail_points"]}, dtype=float)
        r = pd.Series({pd.Timestamp(t, unit="s"): p for t, p in v["resale_series"]}, dtype=float)
        if not len(steps) or not len(r):
            continue
        pr, rs = {}, {}
        for m in months:
            past = r[(r.index <= m) & (r.index > m - pd.Timedelta(days=MAX_POINT_AGE))]
            rt = retail_at(steps, m)
            if len(past) and rt:
                pr[m], rs[m] = float(past.iloc[-1]) / rt - 1, float(past.iloc[-1])
        prem[v["id"]], res[v["id"]] = pd.Series(pr, dtype=float), pd.Series(rs, dtype=float)
    P, R = pd.DataFrame(prem).reindex(months), pd.DataFrame(res).reindex(months)
    need = MIN_ITEMS.get(cat, 3)
    enough = P.notna().sum(axis=1) >= need
    premium = P.median(axis=1).where(enough).dropna()
    ratio = (1 + P).median(axis=1).where(enough).dropna()
    share = (P > 0).sum(axis=1).div(P.notna().sum(axis=1).replace(0, np.nan)).where(enough).dropna()
    index = chain_index(R.dropna(how="all"), min_items=need)
    return {"premium": premium, "ratio": ratio, "share_above": share, "index": index, "n": P.notna().sum(axis=1), "items": list(P.columns), "need": need}


def _indices_for(cat: str) -> dict[str, tuple[pd.Series, str]]:
    """The public indices for a category as (series, unit). unit 'level' is an index or ratio; 'pct' is a published 12-month change,
    chained into a level (100 before its first reading); 'pts' is a level in percentage points (a premium to retail), whose direction is
    the difference in points, not a ratio."""
    out: dict[str, dict] = {}
    units: dict[str, str] = {}
    for r in rows("indices"):
        c = (r.get("category") or "both").lower()
        if c in (cat, "both", cat + "es", cat + "s") and _f(r.get("value")) is not None:
            out.setdefault(r["series"], {})[pd.Timestamp(r["date"])] = _f(r["value"])
            units[r["series"]] = (r.get("unit") or "level").lower()
    res = {}
    for k, v in out.items():
        s = pd.Series(v, dtype=float).sort_index()
        if units[k] == "pct":
            s = 100 * (1 + s / 100).cumprod()
        if len(s) >= 2:
            res[k] = (s, "pts" if units[k] == "pts" else "level")
    return res


def index_change_1y(s: pd.Series, unit: str = "level") -> pd.Series:
    """Change on a year at each point of a sparse series (against the nearest earlier point to a year before, within 120 days): a
    ratio minus one for a level, the difference for a series in percentage points."""
    out = {}
    for t, v in s.items():
        was = _near(s[s.index < t], t - pd.Timedelta(days=365), 120)
        if was is not None and (unit == "pts" or was):
            out[t] = (v - was) if unit == "pts" else v / was - 1
    return pd.Series(out, dtype=float)


def index_score(s: pd.Series, unit: str = "level") -> pd.Series:
    """One index's direction on the heat scale: +10% on a year = +1 (a level), +5 points on a year = +1 (percentage points), clipped to +-2."""
    c = index_change_1y(s, unit)
    return (c / (5.0 if unit == "pts" else 0.10)).clip(-2, 2)


def heat(cat: str, bk: dict | None = None) -> dict:
    """The four components, the score (mean of those available, at least 2, clipped to -2 ... +2), the words, and the month-by-month history."""
    bk = bk or basket(cat)
    months = bk["premium"].index
    comp = {}
    z = rolling_z(bk["premium"], min_n=12)
    if len(z):
        comp["level"] = z.clip(-2, 2)
    if len(bk["index"]):
        c1 = (bk["index"] / bk["index"].shift(12) - 1).dropna()
        if len(c1):
            comp["change_1y"] = (c1 / 0.15).clip(-2, 2)
    if len(bk["share_above"]):
        comp["breadth"] = ((bk["share_above"] - 0.5) * 4).clip(-2, 2)
    idx = _indices_for(cat)
    scores = [index_score(s, u) for s, u in idx.values()]
    scores = [c for c in scores if len(c)]
    if scores:                                       # each index scored on its own scale first, then the mean, so no single index dominates
        d = pd.DataFrame({i: c for i, c in enumerate(scores)}).sort_index()
        d = d.reindex(d.index.union(months)).ffill(limit=None)
        d = d[d.index.isin(months)]
        comp["indices"] = d.mean(axis=1).clip(-2, 2).dropna()
    hist = pd.DataFrame(comp).sort_index()
    hist = hist[hist.index <= _now()].ffill(limit=3) if len(hist) else hist
    score_s = hist.mean(axis=1).where(hist.notna().sum(axis=1) >= 2).clip(-2, 2).dropna() if len(hist) else pd.Series(dtype=float)
    score = _r(float(score_s.iloc[-1]), 2) if len(score_s) else None
    parts = []
    for k, (label, words) in HEAT.items():
        s = comp.get(k)
        s = s.dropna() if s is not None else None
        parts.append({"key": k, "label": label, "words": words, "value": _r(float(s.iloc[-1]), 2) if s is not None and len(s) else None,
                      "date": str(s.index[-1].date()) if s is not None and len(s) else None, "history": _pts(s, 3) if s is not None else []})
    return {"category": cat, "score": score, "verdict": verdict(score), "words": plain_words(cat, score, bk), "components": parts, "history": _pts(score_s, 3),
            "as_of": str(score_s.index[-1].date()) if len(score_s) else None,
            "indices": {k: {"points": _pts(s, 2), "unit": u, "change_1y": _r(float(index_change_1y(s, u).iloc[-1]), 4) if len(index_change_1y(s, u)) else None,
                            "score": _r(float(index_score(s, u).iloc[-1]), 2) if len(index_score(s, u)) else None} for k, (s, u) in idx.items()}}


def verdict(x) -> str:
    if x is None:
        return "not enough data yet"
    return "overheated" if x >= 1 else "running hot" if x >= 0.5 else "cold" if x <= -1 else "cooling" if x <= -0.5 else "neutral"


def plain_words(cat: str, score, bk: dict) -> str:
    name = dict(CATEGORIES).get(cat, cat).lower()
    if score is None:
        return f"Not enough resale points yet to score {name}."
    p = bk["premium"].iloc[-1] if len(bk["premium"]) else None
    where = ("above retail" if p is not None and p > 0.02 else "below retail" if p is not None and p < -0.02 else "around retail") if p is not None else ""
    v = verdict(score)
    tail = {"overheated": "resale premiums far above their own norm and prices rising across the basket",
            "running hot": "premiums above their norm and rising", "neutral": "premiums near their norm and little change on a year",
            "cooling": "premiums below their norm or prices falling on a year", "cold": "premiums far below their norm and prices falling across the basket"}[v]
    return f"{dict(CATEGORIES)[cat]}: {v} ({score:+.1f}); the basket trades {where}, with {tail}."


def lean(z, cut: float = 0.5) -> int:
    return 0 if z is None else 1 if z >= cut else -1 if z <= -cut else 0


# ------------------------------------------------------------------ ROI
def net_after_fee(gross: float, fee: dict) -> dict:
    pct = fee.get("seller_pct") or 0.0
    return {"platform": fee["platform"], "fee_pct": pct, "fee": _r(gross * pct / 100, 0), "net": _r(gross * (1 - pct / 100), 0), "payout_days": fee.get("payout_days"), "verify": fee.get("verify", False)}


def annualised(ret: float, days: int):
    if ret is None or days < 30 or 1 + ret <= 0:
        return None
    return _r((1 + ret) ** (365.25 / days) - 1, 4)


def series_change(s: pd.Series | None, t0: pd.Timestamp, t1: pd.Timestamp):
    if s is None or not len(s):
        return None
    a, b = s[s.index <= t0], s[s.index <= t1]
    if not len(a) or not len(b) or (t0 - a.index[-1]).days > 45:
        return None
    return _r(float(b.iloc[-1]) / float(a.iloc[-1]) - 1, 4)


def roi_rows(views: list[dict], fee_list: list[dict], spx: pd.Series | None, cpi: pd.Series | None) -> list[dict]:
    """For each item and each 1 January from 2020 (or its launch): bought at the list price then in force, sold today at the latest resale
    point through the category's default platform; the S&P 500 and UK CPI over the same period."""
    out, now = [], _now()
    for v in views:
        if not v["latest"] or not v["retail_points"]:
            continue
        steps = pd.Series({pd.Timestamp(t, unit="s"): p for t, p in v["retail_points"]}, dtype=float)
        fee = next((f for f in fee_list if f["platform"] == DEFAULT_PLATFORM.get(v["category"])), None) or (fee_list[0] if fee_list else {"platform": "none", "seller_pct": 0.0})
        gross = v["latest"]["price"]
        for y in range(2020, now.year + 1):
            t0 = max(pd.Timestamp(f"{y}-01-01"), steps.index[0])
            if t0.year != y or (now - t0).days < 90:
                continue
            p0 = retail_at(steps, t0)
            if not p0:
                continue
            days = (now - t0).days
            n = net_after_fee(gross, fee)
            ret = n["net"] / p0 - 1
            cp = series_change(cpi, t0, now)
            out.append({"item": v["id"], "name": v["name"], "category": v["category"], "buy_date": str(t0.date()), "buy_price": _r(p0, 0), "gross": gross, "sold_kind": v["latest"]["kind"],
                        "sold_date": v["latest"]["date"], "platform": n["platform"], "fee_pct": n["fee_pct"], "fee": n["fee"], "net": n["net"], "ret": _r(ret, 4), "annual": annualised(ret, days),
                        "spx": series_change(spx, t0, now), "cpi": cp, "real": _r((1 + ret) / (1 + cp) - 1, 4) if cp is not None else None, "days": days})
    return out


# ------------------------------------------------------------------ item cards: photo, stock on the brand site, resale stock, links
def parse_summary(j: dict) -> dict | None:
    """Wikipedia page summary -> {src, width, height, page} from its thumbnail (the article's lead image), None when the article has none."""
    th = (j or {}).get("thumbnail") or {}
    if not th.get("source"):
        return None
    return {"src": th["source"], "width": th.get("width"), "height": th.get("height"), "page": ((j.get("content_urls") or {}).get("desktop") or {}).get("page") or ("https://en.wikipedia.org/wiki/" + quote(str(j.get("title") or "").replace(" ", "_")))}


def wiki_image(title: str) -> dict | None:
    """The article's lead image, cached a day with a snapshot (None when the article has none)."""
    j = __import__("json").loads(fetch(WIKI_SUMMARY.format(title=quote(title.replace(" ", "_"), safe="")), DAY, headers=WIKI_BOT, timeout=20, min_bytes=40))
    return parse_summary(j)


def photo(item: dict, used_title: str | None = None) -> dict | None:
    """An owner-supplied image URL (items.csv `image`) first; else the lead image of the item's Wikipedia article (the title that answered for
    attention, else the first listed), credited and linked to the article. Not the exact reference: the brand page link is."""
    if (item.get("image") or "").strip():
        return {"src": item["image"].strip(), "credit": "the owner's image link", "page": item.get("source"), "exact": True}
    for t in ([used_title] if used_title else []) + wiki_titles(item.get("wiki")):
        try:
            im = wiki_image(t)
        except Exception:
            im = None
        if im:
            return {**im, "credit": f"Wikipedia: {t} (free licence; the article's lead image, not this exact reference)", "exact": False, "title": t}
    return None


def stock_status(item_id: str) -> dict | None:
    """The latest hand-entered availability on the brand site (stock.csv, channel retail): status, date, source, note."""
    rs = [r for r in rows("stock") if r.get("item") == item_id and (r.get("channel") or "retail") == "retail" and r.get("status")]
    if not rs:
        return None
    r = rs[-1]
    return {"status": r["status"], "date": r["date"], "quantity": _f(r.get("quantity")), "source": r.get("source"), "note": r.get("note") or "", "verify": _verify(r)}


def resale_stock(item_id: str, log: dict | None, ebay: dict | None) -> list[dict]:
    """How many are listed second-hand: Chrono24's count from the weekly log, eBay UK's from the daily feed (when set up)."""
    out = []
    for x in (log or {}).get("latest") or []:
        if x["item"] == item_id and x["metric"] in ("chrono24_listings", "watchcharts_listings", "fashionphile_listings", "watchfinder_stock") and x["value"] is not None:
            out.append({"platform": {"chrono24_listings": "Chrono24", "watchcharts_listings": "WatchCharts", "fashionphile_listings": "Fashionphile", "watchfinder_stock": "Watchfinder"}[x["metric"]],
                        "count": int(x["value"]), "date": x["date"], "url": x.get("source"), "verify": x.get("verify", False)})
    e = ((ebay or {}).get("items") or {}).get(item_id) or {}
    if e.get("latest"):
        out.append({"platform": "eBay UK", "count": e["latest"]["count"], "date": e["latest"]["date"], "url": "https://www.ebay.co.uk/sch/i.html?_nkw=" + quote(e.get("query") or ""), "verify": False})
    return out


# ------------------------------------------------------------------ attention: Wikipedia pageviews (a demand proxy)
def wiki_url(title: str, end: pd.Timestamp | None = None) -> str:
    end = end or _now()
    return WIKI_MONTHLY.format(title=quote(title.replace(" ", "_"), safe=""), b=end.strftime("%Y%m%d") + "00")


def wiki_key(title: str) -> str:
    """The stable address of one article's series for the snapshot and /api/health (the end date moves every day)."""
    return WIKI_MONTHLY.format(title=quote(title.replace(" ", "_"), safe=""), b="now")


MIN_WIKI_MONTHS = 24           # an article with less history than this is a recent stub or redirect: the next title in the item's list is tried


def wiki_titles(spec: str) -> list[str]:
    """An item's `wiki` cell: one title, or several separated by | in order of preference (the first with enough history is used)."""
    return [t.strip() for t in (spec or "").split("|") if t.strip()]


def wiki_views(title: str) -> pd.Series:
    """Monthly pageviews of an English Wikipedia article (users, all access) since July 2015, indexed by month start. Raises when the
    article has fewer than MIN_WIKI_MONTHS months (a recent stub), so the caller can try the next title."""
    j = __import__("json").loads(fetch(wiki_url(title), DAY, headers=WIKI_BOT, timeout=30, min_bytes=40, key=wiki_key(title)))
    d = parse_wiki(j)
    s = pd.Series({pd.Timestamp(k): v for k, v in d.items()}, dtype=float).sort_index()
    if len(s) < MIN_WIKI_MONTHS:
        raise ValueError(f"Wikimedia: only {len(s)} months for {title} (a recent article)")
    return s


def wiki_pick(spec: str) -> tuple[str | None, pd.Series | None, dict[str, str]]:
    """The first title of an item's list with enough history: (title, series, {title: error} for those tried and skipped)."""
    errs = {}
    for t in wiki_titles(spec):
        try:
            return t, wiki_views(t), errs
        except Exception as e:
            errs[t] = f"{type(e).__name__}: {str(e)[:120]}"
    return None, None, errs


def z12(s: pd.Series) -> pd.Series:
    """Each month against the 12 months before it: (x - mean) / sd, clipped to +-3."""
    prev = s.shift(1)
    m, sd = prev.rolling(12).mean(), prev.rolling(12).std(ddof=0)
    return ((s - m) / sd.replace(0, np.nan)).clip(-3, 3).dropna()


def attention(views: dict[str, pd.Series], its: list[dict] | None = None) -> dict:
    """Per item (by its article): monthly views, the last full month, its 12-month z; per category the basket line (each article's
    views as a share of its own whole-history mean, averaged, x100) and the basket's 12-month z."""
    its = its if its is not None else items()
    last_full = (_now().to_period("M") - 1).to_timestamp()
    per_title = {}
    for title, s in views.items():
        s = s[s.index <= last_full]
        if not len(s):
            continue
        z = z12(s)
        per_title[title] = {"title": title, "url": "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_")), "points": _pts(s, 0), "last": {"month": str(s.index[-1].date()), "views": _r(float(s.iloc[-1]), 0)},
                            "z12": _r(float(z.iloc[-1]), 2) if len(z) else None, "z_points": _pts(z, 2), "change_1y": _r(float(s.iloc[-1] / s.iloc[-13] - 1), 4) if len(s) > 13 and s.iloc[-13] else None}
    used = {i["id"]: next((t for t in wiki_titles(i.get("wiki")) if t in views), None) for i in its}      # the title that answered for each item
    per_item = [{"id": i["id"], "name": i["name"], "category": i["category"], "title": used[i["id"]] or (wiki_titles(i.get("wiki")) or [""])[0],
                 "fallback": bool(used[i["id"]] and used[i["id"]] != wiki_titles(i.get("wiki"))[0]),
                 **({k: per_title[used[i["id"]]][k] for k in ("last", "z12", "change_1y", "url")} if used[i["id"]] in per_title else {"last": None, "z12": None, "change_1y": None, "url": None})} for i in its]
    baskets = {}
    for cat, name in CATEGORIES:
        titles = sorted({used[i["id"]] for i in its if i["category"] == cat and used[i["id"]] in views})
        norm = [views[t][views[t].index <= last_full] / views[t][views[t].index <= last_full].mean() for t in titles]
        if not norm:
            continue
        line = (pd.concat(norm, axis=1).mean(axis=1) * 100).dropna()
        z = z12(line)
        baskets[cat] = {"name": name, "titles": titles, "points": _pts(line, 1), "z12": _r(float(z.iloc[-1]), 2) if len(z) else None, "z_points": _pts(z, 2),
                        "change_1y": _r(float(line.iloc[-1] / line.iloc[-13] - 1), 4) if len(line) > 13 else None, "last_month": str(line.index[-1].date())}
    return {"articles": per_title, "items": per_item, "baskets": baskets, "last_full_month": str(last_full.date())}


def _wiki_all(its: list[dict]) -> tuple[dict[str, pd.Series], dict[str, str]]:
    """Every item's article series, each item failing on its own: ({title: series}, {title: error}). An item lists its titles in order
    of preference (wiki = "A|B"); the first with enough history is used, the stubs before it are reported, not errors."""
    out, errs = {}, {}
    for spec in sorted({i["wiki"] for i in its if i.get("wiki")}):
        if any(t in out for t in wiki_titles(spec)):
            continue
        title, s, tried = wiki_pick(spec)
        if title:
            out[title] = s
            for t, e in tried.items():
                errs[t] = e + "; used " + title + " instead"
        else:
            errs.update(tried)
    return out, errs


# ------------------------------------------------------------------ auction results: hammer vs estimate, sell-through
def auction_lots(FX: dict | None = None) -> list[dict]:
    """auctions.csv, one row per lot: price and estimates in GBP (converted at the month's rate), the ratio of price to the estimate
    midpoint, and whether the lot sold; a lot with no price is unsold (bought in)."""
    its = {i["id"]: i for i in items(with_watchlist=True)}
    out = []
    for r in rows("auctions"):
        t = pd.Timestamp(r["date"])
        cur = r.get("currency") or "GBP"
        price = _f(r.get("price"))
        lo, hi = _f(r.get("est_low")), _f(r.get("est_high"))
        sold = (r.get("sold") or ("yes" if price else "no")).strip().lower() in ("yes", "y", "true", "1", "sold")
        g = lambda v: _r(to_gbp(v, cur, t, FX), 0) if v is not None else None
        mid = (lo + hi) / 2 if lo is not None and hi is not None else None
        out.append({"date": str(t.date()), "t": t, "house": r.get("house") or "", "sale": r.get("sale") or "", "lot": r.get("lot") or "", "item": r.get("item") or "",
                    "name": its.get(r.get("item"), {}).get("name") or r.get("item") or "", "category": its.get(r.get("item"), {}).get("category"),
                    "price": g(price), "est_low": g(lo), "est_high": g(hi), "est_mid": g(mid), "orig": f"{r.get('price') or '-'} {cur}", "basis": (r.get("basis") or "").lower(),
                    "vs_estimate": _r(price / mid - 1, 4) if price and mid else None, "sold": sold, "source": r.get("source"), "note": r.get("note") or "", "verify": _verify(r)})
    return sorted(out, key=lambda x: x["t"])


def sell_through(lots: list[dict]) -> dict:
    """Per category: the sell-through rate per sale, from auction_sales.csv (lots sold / offered, the house's own count) and, where a sale
    has no such row, from the lots entered for it (fewer, so marked 'from lots entered'); a monthly series of the rate, each sale's point
    carried to the month end; the share of lots sold overall."""
    out = {}
    its = {i["id"]: i for i in items(with_watchlist=True)}
    sales = rows("auction_sales")
    for cat, name in CATEGORIES:
        pts, table = {}, []
        for r in sales:
            if (r.get("category") or "").lower() not in (cat, cat + "es", cat + "s"):
                continue
            off, sold = _f(r.get("offered")), _f(r.get("sold"))
            if off and sold is not None:
                t = pd.Timestamp(r["date"])
                rate = sold / off
                pts.setdefault(t.to_period("M").to_timestamp("M"), []).append(rate)
                table.append({"date": r["date"], "house": r.get("house"), "sale": r.get("sale"), "offered": int(off), "sold": int(sold), "rate": _r(rate, 4), "total": r.get("total"),
                              "currency": r.get("currency"), "source": r.get("source"), "note": r.get("note") or "", "basis": "house count", "verify": _verify(r)})
        seen = {(x["house"], x["sale"]) for x in table}
        by_sale: dict[tuple, list] = {}
        for l in lots:
            if l["category"] == cat and (l["house"], l["sale"]) not in seen:
                by_sale.setdefault((l["house"], l["sale"], l["date"]), []).append(l)
        for (house, sale, date), ls in by_sale.items():
            if len(ls) >= 3:                                      # one or two lots say nothing about a sale
                rate = sum(1 for l in ls if l["sold"]) / len(ls)
                pts.setdefault(pd.Timestamp(date).to_period("M").to_timestamp("M"), []).append(rate)
                table.append({"date": date, "house": house, "sale": sale, "offered": len(ls), "sold": sum(1 for l in ls if l["sold"]), "rate": _r(rate, 4), "total": None, "currency": None,
                              "source": ls[0]["source"], "note": "", "basis": "from lots entered", "verify": any(l["verify"] for l in ls)})
        series = pd.Series({t: float(np.mean(v)) for t, v in pts.items()}, dtype=float).sort_index()
        cat_lots = [l for l in lots if l["category"] == cat]
        out[cat] = {"name": name, "points": _pts(series, 4), "latest": _r(float(series.iloc[-1]), 4) if len(series) else None, "latest_date": str(series.index[-1].date()) if len(series) else None,
                    "sales": sorted(table, key=lambda x: x["date"], reverse=True), "lots_sold_share": _r(sum(1 for l in cat_lots if l["sold"]) / len(cat_lots), 4) if cat_lots else None, "n_lots": len(cat_lots)}
    return out


def vs_estimate_series(lots: list[dict]) -> dict:
    """Per category: each sold lot's price against the estimate midpoint over time, and the median per half-year as a line."""
    out = {}
    for cat, name in CATEGORIES:
        ls = [l for l in lots if l["category"] == cat and l["vs_estimate"] is not None and l["sold"]]
        s = pd.Series({l["t"]: l["vs_estimate"] for l in ls}, dtype=float).sort_index() if ls else pd.Series(dtype=float)
        s = s[~s.index.duplicated(keep="last")]
        half = s.groupby(s.index.to_period("2Q").to_timestamp("Q")).median() if len(s) else pd.Series(dtype=float)
        out[cat] = {"name": name, "lots": _pts(s, 4), "half_year_median": _pts(half, 4), "latest": _r(float(s.iloc[-1]), 4) if len(s) else None,
                    "by_item": {i: _pts(pd.Series({l["t"]: l["vs_estimate"] for l in ls if l["item"] == i}, dtype=float).sort_index(), 4) for i in sorted({l["item"] for l in ls})}}
    return out


# ------------------------------------------------------------------ the weekly manual log (liquidity.csv)
LOG_METRICS = {"chrono24_listings": ("Chrono24 listings", "count", "active listings for the reference on Chrono24, worldwide"),
               "chrono24_price": ("Chrono24 price", "money", "Chrono24's approximate price for the reference"),
               "stockx_last_sale": ("StockX last sale", "money", "the last sale on StockX"), "stockx_bid": ("StockX highest bid", "money", "the highest standing offer"),
               "stockx_ask": ("StockX lowest ask", "money", "the lowest standing ask"),
               "fashionphile_sold_count": ("Fashionphile sold", "count", "sold items visible on Fashionphile"), "fashionphile_listings": ("Fashionphile in stock", "count", "items in stock on Fashionphile"),
               "watchcharts_days_to_sell": ("Days to sell (WatchCharts)", "days", "median days on market, WatchCharts"), "watchcharts_listings": ("WatchCharts listings", "count", "listings tracked by WatchCharts"),
               "watchfinder_stock": ("Watchfinder stock", "count", "pieces in stock at Watchfinder")}


def liquidity_log(FX: dict | None = None) -> dict:
    """liquidity.csv (date, item, platform, metric, value, currency, source, note), appended weekly: per item and metric the series (money
    in GBP at the month's rate) and the latest reading; the StockX bid-ask spread per bag (ask / bid - 1, needing both within 14 days);
    the Chrono24 listing count summed over the watches that have one, week by week."""
    its = {i["id"]: i for i in items(with_watchlist=True)}
    series: dict[str, dict[str, dict]] = {}
    latest: list[dict] = []
    for r in rows("liquidity"):
        v = _f(r.get("value"))
        if v is None or r.get("metric") not in LOG_METRICS or r.get("item") not in its:
            continue
        t = pd.Timestamp(r["date"])
        kind = LOG_METRICS[r["metric"]][1]
        gv = to_gbp(v, r.get("currency") or "GBP", t, FX) if kind == "money" else v
        if gv is None:
            continue
        series.setdefault(r["item"], {}).setdefault(r["metric"], {})[t] = float(gv)
        latest.append({"item": r["item"], "name": its[r["item"]]["name"], "category": its[r["item"]]["category"], "metric": r["metric"], "label": LOG_METRICS[r["metric"]][0], "kind": kind,
                       "value": _r(gv, 0 if kind != "days" else 1), "orig": f"{r['value']} {r.get('currency') or ''}".strip(), "date": str(t.date()), "platform": r.get("platform") or "", "source": r.get("source"),
                       "note": r.get("note") or "", "verify": _verify(r)})
    newest: dict[tuple, dict] = {}
    for x in latest:
        k = (x["item"], x["metric"])
        if k not in newest or x["date"] > newest[k]["date"]:
            newest[k] = x
    spreads = {}
    for item, ms in series.items():
        bid, ask = ms.get("stockx_bid"), ms.get("stockx_ask")
        if bid and ask:
            tb, ta = max(bid), max(ask)
            if abs((tb - ta).days) <= 14 and bid[tb] > 0:
                spreads[item] = {"name": its[item]["name"], "bid": _r(bid[tb], 0), "ask": _r(ask[ta], 0), "spread": _r(ask[ta] / bid[tb] - 1, 4), "date": str(max(tb, ta).date())}
    c24 = {}
    for item, ms in series.items():
        for t, v in (ms.get("chrono24_listings") or {}).items():
            c24.setdefault(t.to_period("W").to_timestamp("W"), {})[item] = v
    c24_pts = [[int(w.timestamp()), int(sum(d.values()))] for w, d in sorted(c24.items())]
    return {"series": {i: {m: _pts(pd.Series(d, dtype=float).sort_index(), 1) for m, d in ms.items()} for i, ms in series.items()},
            "latest": sorted(newest.values(), key=lambda x: (x["category"], x["name"], x["metric"])), "spreads": spreads,
            "chrono24_total": c24_pts, "chrono24_items": sorted({i for d in c24.values() for i in d}), "metrics": {k: {"label": v[0], "kind": v[1], "words": v[2]} for k, v in LOG_METRICS.items()},
            "n_rows": len(latest), "n_verify": sum(1 for x in latest if x["verify"]), "weeks": len({x["date"][:7] + str(pd.Timestamp(x["date"]).week) for x in latest}),
            "first": min((x["date"] for x in latest), default=None), "last": max((x["date"] for x in latest), default=None)}


# ------------------------------------------------------------------ the liquidity score
LIQ = {"supply": ("Supply: listings vs own history", "The basket's listing count (eBay UK daily once 60 days exist, else the Chrono24 weekly total once 8 weeks exist) as a z-score against its own history, sign flipped: more listings than usual scores negative (a looser market)."),
       "spread": ("Bid-ask spread (StockX)", "Median StockX lowest-ask / highest-bid spread across the bags with both: 0% scores +2, 10% +1, 20% 0, 30% -1."),
       "sell_through": ("Auction sell-through", "The latest sale's lots sold / offered: 95% scores +1, 85% 0, 75% -1."),
       "days_to_sell": ("Days to sell (WatchCharts)", "Median days on market across the references logged in the last 60 days: 20 days scores +1, 30 days 0, 40 days -1."),
       "attention": ("Attention (Wikipedia, 12-month z)", "The basket's attention z: people looking the items up is demand looking for supply.")}


def liquidity_verdict(x) -> str:
    if x is None:
        return "not enough data yet"
    return "tight" if x >= 1 else "liquid" if x >= 0.5 else "stuck" if x <= -1 else "loosening" if x <= -0.5 else "normal"


def liquidity_score(cat: str, att: dict, auc: dict, ebay: dict, log: dict) -> dict:
    """The five components for one market (each -2 ... +2, None where no source gives one yet), the score (mean of those present, at least
    two), the words, and the signal's inputs: the listing count's change on a year and whether the premium fell."""
    comp: dict[str, float | None] = {}
    # supply: eBay daily once 60 days, else Chrono24 weekly once 8 weeks; z against own history, sign flipped
    counts = ((ebay.get("categories") or {}).get(cat) or {}).get("count") or []
    src = "eBay UK"
    if len(counts) < 60 and cat == "watch":
        counts, src = log.get("chrono24_total") or [], "Chrono24"
    if (len(counts) >= 60 and src == "eBay UK") or (len(counts) >= 8 and src == "Chrono24"):
        c = pd.Series({pd.Timestamp(t, unit="s"): v for t, v in counts}, dtype=float)
        sd = float(c.std(ddof=0))
        comp["supply"] = None if sd == 0 else float(np.clip(-(c.iloc[-1] - c.mean()) / sd, -2, 2))
    else:
        comp["supply"] = None
    sp = [v["spread"] for v in (log.get("spreads") or {}).values() if v.get("spread") is not None] if cat == "bag" else []
    comp["spread"] = float(np.clip((0.20 - float(np.median(sp))) / 0.10, -2, 2)) if sp else None
    st = ((auc.get("sell_through") or {}).get(cat) or {}).get("latest")
    comp["sell_through"] = float(np.clip((st - 0.85) / 0.10, -2, 2)) if st is not None else None
    days = [x["value"] for x in (log.get("latest") or []) if x["category"] == cat and x["metric"] == "watchcharts_days_to_sell" and x["value"] is not None
            and (_now() - pd.Timestamp(x["date"])).days <= 60]
    comp["days_to_sell"] = float(np.clip((30 - float(np.median(days))) / 10, -2, 2)) if days else None
    az = ((att.get("baskets") or {}).get(cat) or {}).get("z12")
    comp["attention"] = float(np.clip(az, -2, 2)) if az is not None else None
    have = [v for v in comp.values() if v is not None]
    score = _r(float(np.clip(np.mean(have), -2, 2)), 2) if len(have) >= 2 else None
    # the signal's inputs
    listings_1y = None
    if len(counts) >= 2:
        c = pd.Series({pd.Timestamp(t, unit="s"): v for t, v in counts}, dtype=float)
        past = c[c.index <= c.index[-1] - pd.Timedelta(days=365)]
        if len(past) and past.iloc[-1]:
            listings_1y = _r(float(c.iloc[-1] / past.iloc[-1] - 1), 4)
    return {"category": cat, "name": dict(CATEGORIES)[cat], "score": score, "verdict": liquidity_verdict(score),
            "components": [{"key": k, "label": LIQ[k][0], "words": LIQ[k][1], "value": _r(v, 2) if v is not None else None} for k, v in comp.items()],
            "supply_source": src if comp["supply"] is not None else None, "listings_1y": listings_1y, "listings_source": src if listings_1y is not None else None,
            "sell_through_latest": _r(st, 4) if st is not None else None, "n_components": len(have)}


# ------------------------------------------------------------------ tab payloads
def _views(cat: str | None = None) -> list[dict]:
    FX = _fx_cached()
    return [item_view(i, FX) for i in items() if cat is None or i["category"] == cat]


def _context() -> dict:
    """FRED context with each part failing on its own."""
    out: dict = {}
    B._part(out, "cpi_us", lambda: fred("cpi_us"))
    B._part(out, "cpi_uk", lambda: cpi_uk())
    B._part(out, "sp500", lambda: sp500())
    return out


def card_extras(item_id: str) -> dict:
    """What an item card shows beyond prices: the photo, the brand-site stock status, the resale stock counts, the links. Reads the
    liquidity payload if cached (never computes it here, so the overview stays quick)."""
    it = next((i for i in items(with_watchlist=True) if i["id"] == item_id), None)
    if not it:
        return {}
    L = _cached_payload("liquidity")
    used = next((x.get("title") for x in ((L.get("attention") or {}).get("items") or []) if x.get("id") == item_id and x.get("last")), None)
    log = L.get("log") or liquidity_log(_fx_cached())                  # cheap local reads, so the cards never wait for the liquidity tab
    try:
        ebay = L.get("ebay") or EBAY.payload()
    except Exception:
        ebay = None
    return {"photo": photo(it, used), "stock": stock_status(item_id), "resale_stock": resale_stock(item_id, log, ebay),
            "retail_url": it.get("source"), "resale_url": it.get("resale_url") or None}


def _overview_now() -> dict:
    views = _views()
    FX = _fx_cached()
    W, G = basket("watch", [v for v in views if v["category"] == "watch"]), basket("bag", [v for v in views if v["category"] == "bag"])
    hw, hb = heat("watch", W), heat("bag", G)
    score = _r(float(np.mean([s for s in (hw["score"], hb["score"]) if s is not None])), 2) if hw["score"] is not None or hb["score"] is not None else None
    line = " ".join(x["words"] for x in (hw, hb) if x["score"] is not None) or "Not enough points yet to say where the market is."
    return {"rolex_premium": _pts(W["premium"], 4), "bags_ratio": _pts(G["ratio"], 4), "rolex_index": _pts(W["index"], 2), "bags_index": _pts(G["index"], 2),
            "rolex_share_above": _pts(W["share_above"], 3), "bags_share_above": _pts(G["share_above"], 3),
            "kpi": {"rolex_premium": _r(float(W["premium"].iloc[-1]), 4) if len(W["premium"]) else None, "bags_ratio": _r(float(G["ratio"].iloc[-1]), 4) if len(G["ratio"]) else None,
                    "rolex_1y": _r(float(W["index"].iloc[-1] / W["index"].iloc[-13] - 1), 4) if len(W["index"]) > 13 else None,
                    "bags_1y": _r(float(G["index"].iloc[-1] / G["index"].iloc[-13] - 1), 4) if len(G["index"]) > 13 else None,
                    "heat_watches": hw["score"], "heat_bags": hb["score"], "heat": score, "n_watches": len(W["items"]), "n_bags": len(G["items"])},
            "where": line, "items": [{**{k: v[k] for k in ("id", "name", "brand", "reference", "category", "url", "retail_now", "retail_date", "latest", "premium", "change_1y", "change_3y", "n_points", "n_verify", "note")},
                                      **card_extras(v["id"])} for v in views],
            "counts": {"points": sum(v["n_points"] for v in views), "verify": sum(v["n_verify"] for v in views)},
            "fx_fallback": FX["fallback"], "as_of": max((v["latest"]["date"] for v in views if v["latest"]), default=None),
            "stale": B.stale_info([FRED.format(id=i) for i in FRED_IDS.values()]), "cited": cited("resale", "retail"), "updated": int(time.time())}


def _cat_now(cat: str) -> dict:
    views = _views(cat)
    bk = basket(cat, views)
    FX = _fx_cached()
    out = {"items": views, "premium": _pts(bk["premium"], 4), "ratio": _pts(bk["ratio"], 4), "index": _pts(bk["index"], 2), "share_above": _pts(bk["share_above"], 3),
           "n": _pts(bk["n"], 0), "need": bk["need"], "fx_fallback": FX["fallback"], "cited": cited("resale", "retail"), "updated": int(time.time()),
           "as_of": max((v["latest"]["date"] for v in views if v["latest"]), default=None),
           "stale": B.stale_info([FRED.format(id=i) for i in FRED_IDS.values()])}
    if cat == "bag":
        out["calendar"], out["retail_rise"] = retail_calendar(views)
    else:
        out["retail_rise"] = retail_calendar(views)[1]
    return out


YEAR_AGO_WINDOW = (274, 457)      # a list price counts as "a year ago" only if a row is dated 9 to 15 months before today


def retail_calendar(views: list[dict]) -> tuple[list[dict], dict]:
    """Per brand per year: list price at year end vs the year before (mean across the brand's items). And the 12-month rise, kept
    honest: the latest list price against a price dated 9 to 15 months earlier (the row nearest to a year ago); a brand with no row
    in that window gets no 12-month figure ("no price a year ago") and cannot cross the signal. The longer rise stays visible as
    'since <date>': the latest price against the price in force a year ago, dated by the row that set it."""
    now = _now()
    by_brand: dict[str, list] = {}
    for v in views:
        by_brand.setdefault(v["brand"] or v["name"], []).append(pd.Series({pd.Timestamp(t, unit="s"): p for t, p in v["retail_points"]}, dtype=float))
    years = list(range(2020, now.year + 1))
    cal, rise = [], {}
    lo, hi = now - pd.Timedelta(days=YEAR_AGO_WINDOW[1]), now - pd.Timedelta(days=YEAR_AGO_WINDOW[0])
    for brand, steps_list in sorted(by_brand.items()):
        row = {"brand": brand, "years": {}}
        for y in years:
            chs = []
            for st in steps_list:
                a, b = retail_at(st, pd.Timestamp(f"{y - 1}-12-31")), retail_at(st, min(pd.Timestamp(f"{y}-12-31"), now))
                if a and b:
                    chs.append(b / a - 1)
            row["years"][str(y)] = _r(float(np.mean(chs)), 4) if chs else None
        row["changes"] = sum(1 for st in steps_list for t in st.index if t >= pd.Timestamp("2020-01-01"))
        m12, since, since_dates = [], [], []
        for st in steps_list:
            cur = retail_at(st, now)
            if not cur:
                continue
            w = st[(st.index >= lo) & (st.index <= hi)]
            if len(w):
                near = w.index[int(np.argmin(np.abs((w.index - (now - pd.Timedelta(days=365))).days)))]
                m12.append(cur / float(w[near]) - 1)
            past = st[st.index <= now - pd.Timedelta(days=365)]
            if len(past):
                since.append(cur / float(past.iloc[-1]) - 1)
                since_dates.append(past.index[-1])
        r = {"rise_12m": _r(float(np.mean(m12)), 4) if m12 else None, "n_12m": len(m12), "n_items": len(steps_list),
             "since": {"value": _r(float(np.mean(since)), 4), "date": str(min(since_dates).date())} if since else None}
        row.update(r)
        rise[brand] = r
        cal.append(row)
    with_12m = {b: r["rise_12m"] for b, r in rise.items() if r["rise_12m"] is not None}
    top = max(with_12m.items(), key=lambda kv: kv[1]) if with_12m else (None, None)
    return cal, {"by_brand": rise, "brand": top[0], "value": top[1], "window_months": [9, 15],
                 "note": None if with_12m else "no brand has a list price dated 9 to 15 months ago"}


def _roi_now() -> dict:
    views = _views()
    fee_list = fees()
    ctx = _context()
    spx = ctx.get("sp500")[0] if ctx.get("sp500") else None
    cpi = ctx.get("cpi_uk")[0] if ctx.get("cpi_uk") else None
    cpi_us = ctx.get("cpi_us")
    return {"rows": roi_rows(views, fee_list, spx, cpi), "fees": fee_list, "default_platform": DEFAULT_PLATFORM,
            "items": [{k: v[k] for k in ("id", "name", "category", "retail_points", "latest", "retail_now")} for v in views],
            "sp500": _pts(spx.resample("ME").last(), 2) if spx is not None else None, "sp500_source": ctx["sp500"][1] if ctx.get("sp500") else None, "sp500_error": ctx.get("sp500_error"),
            "cpi_uk": _pts(cpi, 3) if cpi is not None else None, "cpi_uk_source": ctx["cpi_uk"][1] if ctx.get("cpi_uk") else None, "cpi_uk_error": ctx.get("cpi_uk_error"),
            "cpi_us": _pts(cpi_us, 3) if cpi_us is not None else None, "cpi_us_error": ctx.get("cpi_us_error"),
            "stale": B.stale_info([FRED.format(id=i) for i in FRED_IDS.values()] + [ONS_CPI]), "as_of": str(_now().date()), "updated": int(time.time())}


def _heat_now() -> dict:
    views = _views()
    out = {}
    for cat, _ in CATEGORIES:
        out[cat] = heat(cat, basket(cat, [v for v in views if v["category"] == cat]))
    scores = [out[c]["score"] for c, _ in CATEGORIES if out[c]["score"] is not None]
    out["score"] = _r(float(np.mean(scores)), 2) if scores else None
    out["verdict"] = verdict(out["score"])
    out["bands"] = [["+1 or more", "overheated"], ["+0.5 to +1", "running hot"], ["-0.5 to +0.5", "neutral"], ["-1 to -0.5", "cooling"], ["-1 or less", "cold"]]
    out["cited"] = cited("indices")
    out["as_of"] = max((out[c]["as_of"] for c, _ in CATEGORIES if out[c]["as_of"]), default=None)
    out["updated"] = int(time.time())
    return out


def _liquidity_now() -> dict:
    its = items()
    views, errs = _wiki_all(its)
    att = attention(views, its) if views else {"articles": {}, "items": [], "baskets": {}, "last_full_month": None}
    FX = _fx_cached()
    lots = auction_lots(FX)
    auc = {"lots": [{k: v for k, v in l.items() if k != "t"} for l in reversed(lots)], "vs_estimate": vs_estimate_series(lots), "sell_through": sell_through(lots),
           "n_lots": len(lots), "n_verify": sum(1 for l in lots if l["verify"]), "houses": sorted({l["house"] for l in lots}), "cited": cited("auctions", "auction_sales")}
    try:
        ebay = EBAY.payload(its)
    except Exception as e:
        ebay = {"set_up": EBAY.set_up(), "message": f"{type(e).__name__}: {str(e)[:120]}", "items": {}, "categories": {}, "days": 0}
    log = liquidity_log(FX)
    scores = {cat: liquidity_score(cat, att, auc, ebay, log) for cat, _ in CATEGORIES}
    both = [x["score"] for x in scores.values() if x["score"] is not None]
    scores["score"] = _r(float(np.mean(both)), 2) if both else None
    scores["verdict"] = liquidity_verdict(scores["score"])
    scores["bands"] = [["+1 or more", "tight: few listings, narrow spreads, everything sells"], ["+0.5 to +1", "liquid"], ["-0.5 to +0.5", "normal"], ["-1 to -0.5", "loosening"], ["-1 or less", "stuck: listings pile up, spreads widen, lots bought in"]]
    return {"attention": att, "attention_errors": errs, "auctions": auc, "ebay": ebay, "log": log, "liquidity": scores, "fx_fallback": FX["fallback"],
            "as_of": max([d for d in (att.get("last_full_month"), lots[-1]["date"] if lots else None) if d], default=None),
            "stale": B.stale_info([wiki_key(t) for i in its for t in wiki_titles(i.get("wiki"))]), "updated": int(time.time())}


def _fees_now() -> dict:
    return {"fees": fees(), "cited": cited("fees"), "as_of": max((r["date"] for r in rows("fees")), default=None), "updated": int(time.time())}


def _items_now() -> dict:
    return {"items": items(with_watchlist=True), "watchlist": [r for r in manual_rows(SLUG, "watchlist")], "updated": int(time.time())}


def _cached_ep(name, fn, ttl=3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


BACKGROUND = [EBAY.fill]          # the daily eBay snapshot (the server runs it at start and every 6 hours; it does nothing until the keys are set)

ENDPOINTS = {"overview": _cached_ep("overview", _overview_now), "watches": _cached_ep("watches", lambda: _cat_now("watch")), "bags": _cached_ep("bags", lambda: _cat_now("bag")),
             "roi": _cached_ep("roi", _roi_now), "heat": _cached_ep("heat", _heat_now), "liquidity": _cached_ep("liquidity", _liquidity_now), "fees": _cached_ep("fees", _fees_now, 600), "items": _cached_ep("items", _items_now, 600)}


# ------------------------------------------------------------------ READINGS and SIGNALS (cached payloads only)
def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


def readings(got) -> list[dict]:
    out = []

    def add(tab, key, label, value, ln, note):
        if value is not None:
            out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": ln, "note": note})
    K = got("overview").get("kpi") or {}
    p = K.get("rolex_premium")
    add("overview", "rolex_premium", "Rolex basket: resale premium to retail (median)", _r(100 * p, 1) if p is not None else None, lean(p, 0.0) if p is not None and abs(p) > 0.02 else 0,
        "%; +1 above retail, -1 below retail (within 2% is neutral)")
    r = K.get("bags_ratio")
    add("overview", "bags_ratio", "Bag basket: resale / retail (median)", r, 1 if r is not None and r >= 1 else -1 if r is not None and r < 0.7 else 0, "x; +1 at or above retail, -1 under 0.7x")
    H = got("heat")
    for cat, name in CATEGORIES:
        s = (H.get(cat) or {}).get("score")
        add("heat", f"heat_{cat}", f"{name} heat score (-2 cold ... +2 overheated)", s, lean(s), f"{verdict(s)}; +1 at +0.5 or above, -1 at -0.5 or below")
    LS = got("liquidity").get("liquidity") or {}
    for cat, name in CATEGORIES:
        v = (LS.get(cat) or {}).get("score")
        add("liquidity", f"liquidity_{cat}", f"{name} liquidity score (-2 stuck ... +2 tight)", v, lean(v), f"{liquidity_verdict(v)}; +1 at +0.5 or above, -1 at -0.5 or below")
    A = (got("liquidity").get("attention") or {}).get("baskets") or {}
    for cat, name in CATEGORIES:
        z = (A.get(cat) or {}).get("z12")
        add("liquidity", f"attention_{cat}", f"{name}: Wikipedia attention, 12-month z (demand proxy)", z, lean(z, 1.0), "last full month against the 12 before; +1 at +1 sd or above, -1 at -1 sd or below")
    EB = (got("liquidity").get("ebay") or {}).get("categories") or {}
    for cat, name in CATEGORIES:
        c = (EB.get(cat) or {})
        if c.get("latest") and c.get("count") and len(c["count"]) >= 2:
            v = c["latest"]["count"]
            add("liquidity", f"ebay_listings_{cat}", f"{name}: active eBay UK listings (basket)", v, 0, "a supply count; neutral until a year of history gives a z-score")
    LG = got("liquidity").get("log") or {}
    sp = [v["spread"] for v in (LG.get("spreads") or {}).values() if v.get("spread") is not None]
    if sp:
        v = float(np.median(sp))
        add("liquidity", "stockx_spread", "Bags: StockX bid-ask spread (median of the bags with both)", _r(100 * v, 1), 1 if v < 0.10 else -1 if v > 0.30 else 0, "%; +1 under 10% (a tight market), -1 over 30% (bids far below asks)")
    ST = (got("liquidity").get("auctions") or {}).get("sell_through") or {}
    for cat, name in CATEGORIES:
        v = (ST.get(cat) or {}).get("latest")
        add("liquidity", f"sell_through_{cat}", f"{name}: auction sell-through, latest sale", _r(100 * v, 1) if v is not None else None, 1 if v is not None and v >= 0.9 else -1 if v is not None and v < 0.7 else 0,
            "%; +1 at 90% or more (bidders for everything), -1 under 70% (lots bought in)")
    return out


def merged_rise(parts: list) -> dict:
    """The retail_rise of the watches and bags payloads as one: the brand with the largest 12-month rise across both (None when no brand
    has a list price dated 9-15 months ago); a payload without by_brand (an older cache) counts by its value alone."""
    parts = [x for x in parts if x]
    if not parts:
        return {}
    best = (None, None)
    for x in parts:
        cands = {b: r["rise_12m"] for b, r in (x.get("by_brand") or {}).items() if isinstance(r, dict) and r.get("rise_12m") is not None} or \
                ({x["brand"]: x["value"]} if x.get("value") is not None and x.get("brand") else {})
        for b, v in cands.items():
            if best[1] is None or v > best[1]:
                best = (b, v)
    return {"brand": best[0], "value": best[1], "note": None if best[1] is not None else "no brand has a list price dated 9 to 15 months ago"}


def READINGS() -> list[dict]:
    return readings(_cached_payload)


def SIGNALS() -> list[dict]:
    """The owner's approved watch points (data/signals/watchlist.json, approved 7 Nov 2026), from cached payloads only."""
    out = []

    def add(key, tab, label, value, unit, ln, watch, crossed, note=None):
        out.append({"key": key, "tab": tab, "label": label, "value": value, "unit": unit, "lean": ln, "watch": watch, "crossed": bool(crossed), **({"note": note} if note else {})})
    O, H, Bg = _cached_payload("overview"), _cached_payload("heat"), _cached_payload("bags")
    K = O.get("kpi") or {}
    p = K.get("rolex_premium")
    if p is not None:
        add("rolex_premium", "overview", "Rolex basket: median resale premium to retail", _r(100 * p, 1), "%", 1 if p > 0.02 else -1 if p < -0.02 else 0,
            "below 0% (steel sports below retail) or above +50%", p < 0 or p > 0.5, "steel sports below retail" if p < 0 else "far above retail" if p > 0.5 else None)
    c = K.get("rolex_1y")
    if c is not None:
        add("rolex_1y", "watches", "Rolex basket resale, change on a year", _r(100 * c, 1), "%", 1 if c > 0.03 else -1 if c < -0.03 else 0, "a 15% move either way", abs(c) >= 0.15)
    r = K.get("bags_ratio")
    if r is not None:
        add("bags_ratio", "overview", "Bag basket: resale / retail", r, "x", 1 if r >= 1 else -1 if r < 0.7 else 0, "below 0.5 or above 1.0", r < 0.5 or r > 1.0)
    rr = merged_rise([(Bg or {}).get("retail_rise"), (_cached_payload("watches") or {}).get("retail_rise")])
    if rr:                                          # every brand, Rolex included; a brand needs a list price dated 9-15 months ago to have a 12-month figure
        v = rr.get("value")
        add("retail_rise", "bags", "Largest brand retail increase, last 12 months", _r(100 * v, 1) if v is not None else None, "%", 0, "any brand above 10%",
            v is not None and v > 0.10, rr.get("brand") if v is not None else (rr.get("note") or "no price a year ago"))
    s = H.get("score")
    if s is not None:
        add("heat", "heat", "Luxury market heat score (watches and bags)", s, "", lean(s), "above +1.5 or below -1", s > 1.5 or s < -1, verdict(s))
    LS = (_cached_payload("liquidity") or {}).get("liquidity") or {}
    if LS.get("score") is not None or any((LS.get(c) or {}).get("sell_through_latest") is not None for c, _ in CATEGORIES):
        stuck, low, notes = [], [], []
        for cat, name in CATEGORIES:
            x = LS.get(cat) or {}
            prem = O.get("rolex_premium") if cat == "watch" else O.get("bags_ratio")
            falling = None
            if prem and len(prem) > 12:
                falling = prem[-1][1] < prem[-13][1]
            if x.get("listings_1y") is not None and x["listings_1y"] >= 0.5 and falling:
                stuck.append(name)
            if x.get("sell_through_latest") is not None and x["sell_through_latest"] < 0.7:
                low.append(name)
            notes.append(f"{name}: listings {'+' if (x.get('listings_1y') or 0) >= 0 else ''}{round(100 * x['listings_1y'])}% on a year" if x.get("listings_1y") is not None else f"{name}: no year of listings yet")
            if x.get("sell_through_latest") is not None:
                notes[-1] += f", sell-through {round(100 * x['sell_through_latest'])}%"
        add("liquidity", "liquidity", "Liquidity score (watches and bags, -2 stuck ... +2 tight)", LS.get("score"), "", lean(LS.get("score")),
            "listings up 50% on a year with the premium falling (sellers stuck), or sell-through below 70% at auction", bool(stuck or low),
            ("sellers stuck: " + ", ".join(stuck) + "; " if stuck else "") + ("sell-through under 70%: " + ", ".join(low) + "; " if low else "") + "; ".join(notes))
    return out
