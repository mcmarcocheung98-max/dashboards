"""Luxury Tracker (/luxury): watches and bags on the second-hand market.

The question: for each item, what does it cost new today, what does it sell for second-hand, and what return (or loss) would a buyer
at retail see after platform fees, over time. Not investment advice: no buy or sell calls.

overview   the Rolex basket's resale premium or discount to retail (median across the starter references), the bag basket's
           resale-to-retail ratio, one line on where the market is, and a card per item (retail, latest resale, premium, 1-year change)
watches    retail vs resale over time per reference, the premium-to-retail line, a table (retail, resale, premium, 1y and 3y change)
bags       the same for bags, plus retail price inflation per brand per year (the price-increase calendar)
roi        for a buyer at retail on a chosen date, what they would net today after the selling platform's fee, by platform; a
           calculator (item, buy date, buy price, platform) against the S&P 500 and UK CPI over the same period; nothing is stored
heat       a heat score for watches and one for bags, like Pokémon's: the basket premium against its own history, the 1-year change,
           the share of items above retail, and the public indices' direction
fees       the platform fee table with links

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

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from ._base import DAY, _pts, _r, fetch, handled, manual_rows, manual_sources

SLUG = "luxury"
TOPIC = Topic(SLUG, "Luxury Tracker: watches & bags",
              "Rolex steel sports references and designer bags: what they cost new, what they sell for second-hand, the premium or discount to "
              "retail over time, what a buyer at retail would net after platform fees, and a heat score for each market.",
              "luxury", (("overview", "Overview"), ("watches", "Watches"), ("bags", "Bags"), ("roi", "ROI"), ("heat", "Market heat"), ("fees", "Fees & how to sell")),
              ("overview", "watches", "bags", "roi", "heat", "fees"), icon="chart", order=36)

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
FRED_IDS = {"cpi_us": "CPIAUCSL", "cpi_uk": "GBRCPIALLMINMEI", "gbpusd": "DEXUSUK", "chfusd": "DEXSZUS", "eurusd": "DEXUSEU", "sp500": "SP500"}
ONS_CPI = "https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/d7bt/mm23"   # UK CPI index (2015=100)
NASDAQ_SPX = "https://api.nasdaq.com/api/quote/SPX/historical?assetclass=index&fromdate={a}&todate={b}&limit=9999"
PLAIN_UA = {"User-Agent": "dashboards/1.0 (+https://github.com/mcmarcocheung98-max/dashboards)"}   # FRED answers a plain client at once where the browser UA stalls
NASDAQ_HEADERS = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
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
            "where": line, "items": [{k: v[k] for k in ("id", "name", "brand", "reference", "category", "url", "retail_now", "retail_date", "latest", "premium", "change_1y", "change_3y", "n_points", "n_verify", "note")} for v in views],
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


def retail_calendar(views: list[dict]) -> tuple[list[dict], dict]:
    """Per brand per year: list price at year end vs the year before (mean across the brand's items), and the largest rise over the
    last 12 months (per brand, mean across its items)."""
    now = _now()
    by_brand: dict[str, list] = {}
    for v in views:
        by_brand.setdefault(v["brand"] or v["name"], []).append(pd.Series({pd.Timestamp(t, unit="s"): p for t, p in v["retail_points"]}, dtype=float))
    years = list(range(2020, now.year + 1))
    cal = []
    rise = {}
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
        cal.append(row)
        chs = [retail_at(st, now) / retail_at(st, now - pd.Timedelta(days=365)) - 1 for st in steps_list if retail_at(st, now) and retail_at(st, now - pd.Timedelta(days=365))]
        if chs:
            rise[brand] = _r(float(np.mean(chs)), 4)
    top = max(rise.items(), key=lambda kv: kv[1]) if rise else (None, None)
    return cal, {"by_brand": rise, "brand": top[0], "value": top[1]}


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


def _fees_now() -> dict:
    return {"fees": fees(), "cited": cited("fees"), "as_of": max((r["date"] for r in rows("fees")), default=None), "updated": int(time.time())}


def _items_now() -> dict:
    return {"items": items(with_watchlist=True), "watchlist": [r for r in manual_rows(SLUG, "watchlist")], "updated": int(time.time())}


def _cached_ep(name, fn, ttl=3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"overview": _cached_ep("overview", _overview_now), "watches": _cached_ep("watches", lambda: _cat_now("watch")), "bags": _cached_ep("bags", lambda: _cat_now("bag")),
             "roi": _cached_ep("roi", _roi_now), "heat": _cached_ep("heat", _heat_now), "fees": _cached_ep("fees", _fees_now, 600), "items": _cached_ep("items", _items_now, 600)}


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
    return out


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
    rr = (Bg.get("retail_rise") or {}) if Bg else {}
    if rr.get("value") is not None:
        add("retail_rise", "bags", "Largest brand retail increase, last 12 months", _r(100 * rr["value"], 1), "%", 0, "any brand above 10%", rr["value"] > 0.10, rr.get("brand"))
    s = H.get("score")
    if s is not None:
        add("heat", "heat", "Luxury market heat score (watches and bags)", s, "", lean(s), "above +1.5 or below -1", s > 1.5 or s < -1, verdict(s))
    return out
