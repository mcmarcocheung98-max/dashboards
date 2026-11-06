"""AI Stocks: the setup after the dip (/ai-stocks): after the pullback in AI stocks, how deep is the dip, is it washing out or still
breaking down, and what has happened after dips like this before? Not investment advice: no buy or sell calls, only where the numbers stand.

setup         one card per stock (drawdown from its 52-week high, against its 50- and 200-day averages, RSI 14), the equal-weight AI
              basket and the owner's picks (a second group with its own index) against QQQ and SPY, and a plain-English "where we are" line
drawdown      the basket's and each stock's drawdown from its running peak since 2020, the current dip, and every basket drawdown over 10%
trend         share of the basket above its 50- and 200-day averages, the basket's RSI 14, and its 50/200-day crosses
dips          every past basket drawdown of 15% or more: returns 1, 3 and 6 months after the 15% point and after the bottom
fear          VIX (FRED VIXCLS, Cboe's history file when FRED does not answer), the basket against QQQ and SMH against SPY over 3 and 12 months
fundamentals  revenue growth on a year for the basket's US filers (SEC EDGAR companyfacts) and hyperscaler capex (compute_chips' series)
layout        not a tab: what this server gets back from each source, to check reachability from Railway

Prices: daily closes from Nasdaq's quote API (Yahoo answers Railway with 429). The basket is an equal-weight index rebalanced daily
(the average of its members' daily returns, chained), 100 on the first trading day of 2020; a member joins the day after its first close
(Arm listed in September 2023). The owner's picks (PICKS) are a second equal-weight index on the same method, each stock from its
first full month of trading (full_months). Leans: +1 = the setup reads healthier (shallower drawdown, broader trend, calmer VIX, AI ahead),
-1 = more stress. A lean describes the numbers, not a trade.
"""
from __future__ import annotations

import json
import time
from io import StringIO

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from . import compute_chips as CC
from ._base import DAY, _pts, _r, fetch, fetch_json, handled, payload

SLUG = "ai-stocks"
TOPIC = Topic(SLUG, "AI Stocks: the setup after the dip",
              "After the pullback in AI stocks: how deep is the dip, is it washing out or still breaking down, and what happened after "
              "dips like this before? Thirteen AI leaders in an equal-weight basket, and the owner's ten picks as a second group, against QQQ, "
              "SPY and SMH, with VIX and revenue growth.",
              "ai_stocks", (("setup", "Setup"), ("drawdown", "Drawdown"), ("trend", "Trend & breadth"), ("dips", "After past dips"),
                            ("fear", "Fear & relative"), ("fundamentals", "Fundamentals")),
              ("setup", "drawdown", "trend", "dips", "fear", "fundamentals"), icon="chart")

BASKET = ("NVDA", "AVGO", "AMD", "TSM", "ASML", "MU", "ARM", "MSFT", "GOOGL", "AMZN", "META", "ORCL", "PLTR")
ETFS = ("QQQ", "SPY", "SMH")
# the owner's picks (5-6 Nov 2026: "sandisk, nebius, bloom, marvell, oracle, iren, applive, AMD, rocket lab, nvidia"; "applive" read as
# AppLovin), a second group with its own equal-weight index; ORCL, AMD and NVDA are in both groups
PICKS = ("SNDK", "NBIS", "BE", "MRVL", "ORCL", "IREN", "APP", "AMD", "RKLB", "NVDA")
STOCKS = BASKET + tuple(s for s in PICKS if s not in BASKET)
NAMES = {"NVDA": "Nvidia", "AVGO": "Broadcom", "AMD": "AMD", "TSM": "TSMC", "ASML": "ASML", "MU": "Micron", "ARM": "Arm", "MSFT": "Microsoft",
         "GOOGL": "Alphabet", "AMZN": "Amazon", "META": "Meta", "ORCL": "Oracle", "PLTR": "Palantir", "SNDK": "SanDisk", "NBIS": "Nebius",
         "BE": "Bloom Energy", "MRVL": "Marvell", "IREN": "IREN", "APP": "AppLovin", "RKLB": "Rocket Lab"}
GROUPS = {"core": "AI basket", "picks": "Owner's picks"}
# first day of trading as the company it is now: closes before it are dropped. Nasdaq's history for NBIS runs back through Yandex
# (suspended Feb 2022, its price repeated until the Nebius relisting); RKLB's through the Vector Acquisition SPAC; SanDisk's starts with
# when-issued trading before the spin-off from Western Digital
LISTED = {"SNDK": "2025-02-24", "NBIS": "2024-10-21", "RKLB": "2021-08-25", "IREN": "2021-11-17", "APP": "2021-04-15"}
DATA_START = "2019-01-01"           # a year before the index starts, so the 200-day averages exist from its first day
INDEX_START = pd.Timestamp("2020-01-01")
DD_TABLE = -0.10                    # drawdowns listed on the Drawdown tab
DD_STUDY = -0.15                    # drawdowns studied on the After past dips tab
HORIZONS = {"1m": 21, "3m": 63, "6m": 126}          # trading days
# SEC filers reporting in US GAAP with quarterly 10-Qs; TSMC, ASML and Arm file 20-F/6-K under IFRS without quarterly facts in companyfacts
# every dashboard stock's SEC CIK (www.sec.gov/files/company_tickers.json, checked 6 Nov 2026): Form 4 insider filings, companyfacts
CIKS = {"NVDA": 1045810, "AVGO": 1730168, "AMD": 2488, "TSM": 1046179, "ASML": 937966, "MU": 723125, "ARM": 1973239, "MSFT": 789019,
        "GOOGL": 1652044, "AMZN": 1018724, "META": 1326801, "ORCL": 1341439, "PLTR": 1321655, "SNDK": 2023554, "NBIS": 1513845,
        "BE": 1664703, "MRVL": 1835632, "IREN": 1878848, "APP": 1751008, "RKLB": 1819994}
FORM4_LIST = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type=4&dateb=&owner=include&count=40"
REV_CIKS = {"NVDA": 1045810, "AVGO": 1730168, "AMD": 2488, "MU": 723125, "MSFT": 789019, "GOOGL": 1652044, "AMZN": 1018724, "META": 1326801,
            "ORCL": 1341439, "PLTR": 1321655}

FRED_VIX = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
CBOE_VIX = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
EDGAR = CC.EDGAR

SOURCES = [{"name": "Nasdaq quote API (daily closes of the 13 basket stocks, the owner's 10 picks, QQQ, SPY, SMH)", "url": "https://www.nasdaq.com/market-activity/stocks/nvda/historical", "cadence": "daily"},
           {"name": "FRED: CBOE Volatility Index (VIXCLS)", "url": "https://fred.stlouisfed.org/series/VIXCLS", "cadence": "daily"},
           {"name": "Cboe VIX history (fallback when FRED does not answer)", "url": "https://www.cboe.com/tradable_products/vix/vix_historical_data/", "cadence": "daily"},
           {"name": "SEC EDGAR companyfacts (10-Q, 10-K revenue)", "url": "https://www.sec.gov/edgar/sec-api-documentation", "cadence": "quarterly"},
           {"name": "Hyperscaler capex from the AI Compute, Power & Chips dashboard", "url": "/compute-chips#capex", "cadence": "quarterly"}]
NOTES = ("Not investment advice: this page shows where AI share prices stand against their own history and makes no buy or sell call. "
         "The basket is an equal-weight index of 13 AI stocks, rebalanced daily, 100 on 2 January 2020; prices exclude dividends. "
         "After past dips draws on a handful of drawdowns since 2020: a small sample, history and not a forecast. "
         "Leans: +1 = the setup reads healthier, -1 = more stress.")
FOOTER = "Read-only. Not investment advice: no buy or sell calls, and past drawdowns say nothing certain about the next one."


# ------------------------------------------------------------------ prices
def nasdaq(sym: str, cls: str = "stocks") -> pd.Series:
    return B.nasdaq_daily(sym, DATA_START, lambda *a, **k: fetch_json(*a, **k), assetclass=cls)


def _src(sym: str, cls: str) -> str:
    return B.NASDAQ_ANY.format(sym=sym, cls=cls, a=DATA_START, b=pd.Timestamp.now().strftime("%Y-%m-%d"))


def _prices_now() -> dict:
    px, errors = {}, {}
    for sym, cls in [(s, "stocks") for s in STOCKS] + [(s, "etf") for s in ETFS]:
        try:
            s = nasdaq(sym, cls)
            if sym in LISTED:
                s = s[s.index >= LISTED[sym]]
                if len(s) < 2:
                    raise LookupError("no closes since listing")
            px[sym] = s
        except Exception as e:
            errors[sym] = type(e).__name__
    return {"px": px, "errors": errors, "sources": [_src(s, "stocks") for s in STOCKS] + [_src(s, "etf") for s in ETFS]}


def full_months(s: pd.Series) -> pd.Series:
    """A stock joins the picks index from its first full month of trading: the closes from the last one before that month starts
    (so the month's first day is its first return). A stock trading since before DATA_START is unchanged."""
    s = s.dropna()
    if not len(s) or s.index[0] <= pd.Timestamp(DATA_START) + pd.Timedelta(days=7):
        return s
    first = s.index[0]
    start = first if first.day <= 4 else first + pd.offsets.MonthBegin(1)         # listed on the month's first trading day or a later one
    before = s.index[s.index < start]
    return s[s.index >= before[-1]] if len(before) else s


def basket_index(px: dict[str, pd.Series], start: pd.Timestamp = INDEX_START) -> pd.Series:
    """Equal-weight, rebalanced daily: the mean of the members' daily returns (members with a close that day and the day before),
    chained from DATA_START and rebased to 100 on the first trading day on or after `start`."""
    d = pd.DataFrame(px).sort_index()
    if d.empty:
        raise LookupError("no prices")
    r = d.pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0.0)
    lvl = (1 + r).cumprod()
    base = lvl[lvl.index >= start]
    if base.empty:
        raise LookupError("no prices after the index start")
    return 100 * lvl / base.iloc[0]


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI (the same smoothing as _signals.rsi)."""
    d = s.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    out = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    return out.mask((dn == 0) & (up > 0), 100.0)                # no down days at all: 100, not a gap


def drawdown(s: pd.Series, since: pd.Timestamp = INDEX_START) -> pd.Series:
    """Fall from the running peak, counted from `since` (0 at a new high, -0.2 = 20% below the peak)."""
    s = s[s.index >= since].dropna()
    return s / s.cummax() - 1


def episodes(s: pd.Series, threshold: float = DD_TABLE, since: pd.Timestamp = INDEX_START) -> list[dict]:
    """Every drawdown deeper than `threshold`: from a peak to the next new high (or today, if not yet recovered)."""
    s = s[s.index >= since].dropna()
    if s.empty:
        return []
    out, peak_t, peak_v, trough_t, trough_v = [], s.index[0], s.iloc[0], s.index[0], s.iloc[0]

    def close(end_t):
        depth = trough_v / peak_v - 1
        if depth <= threshold:
            cross = s[(s.index >= peak_t) & (s / peak_v - 1 <= DD_STUDY)]
            out.append({"peak": str(peak_t.date()), "trough": str(trough_t.date()), "recovered": str(end_t.date()) if end_t is not None else None,
                        "depth": _r(depth, 4), "days_to_bottom": int((trough_t - peak_t).days),
                        "days_to_recover": int((end_t - trough_t).days) if end_t is not None else None,
                        "cross15": str(cross.index[0].date()) if len(cross) and cross.index[0] <= trough_t else None, "ongoing": end_t is None})
    for t, v in s.items():
        if v >= peak_v:
            if trough_v < peak_v:
                close(t)
            peak_t, peak_v, trough_t, trough_v = t, v, t, v
        elif v < trough_v:
            trough_t, trough_v = t, v
    if trough_v < peak_v:
        close(None)
    return out


def _ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def stock_card(sym: str, s: pd.Series) -> dict:
    s = s.dropna()
    hi = s.rolling(252, min_periods=20).max()
    m50, m200, r = _ma(s, 50), _ma(s, 200), rsi(s)
    last = lambda x: _r(x.iloc[-1], 4) if len(x) and pd.notna(x.iloc[-1]) else None
    return {"sym": sym, "name": NAMES.get(sym, sym), "price": _r(s.iloc[-1], 2), "date": str(s.index[-1].date()),
            "dd52": last(s / hi - 1), "vs50": last(s / m50 - 1), "vs200": last(s / m200 - 1), "rsi": _r(r.iloc[-1], 1),
            "high52": _r(hi.iloc[-1], 2), "high52_date": str(s[s.index >= s.index[-1] - pd.Timedelta(days=366)].idxmax().date())}


def strip(px: dict[str, pd.Series]) -> list[dict]:
    """The row at the top of Setup: SPY, QQQ and SMH, then every stock of both groups, with the last close and the day's move."""
    out = []
    for sym, group in [(e, "index") for e in ("SPY", "QQQ", "SMH")] + [(s, "core") for s in BASKET] + [(s, "picks") for s in PICKS if s not in BASKET]:
        s = px.get(sym)
        if s is None or len(s.dropna()) < 2:
            continue
        s = s.dropna()
        out.append({"sym": sym, "name": NAMES.get(sym, sym), "group": group, "both": sym in BASKET and sym in PICKS, "price": _r(s.iloc[-1], 2),
                    "day": _r(s.iloc[-1] / s.iloc[-2] - 1, 4), "date": str(s.index[-1].date()),
                    **({"form4": FORM4_LIST.format(cik=CIKS[sym])} if sym in CIKS else {})})
    return out


def breadth(px: dict[str, pd.Series], n: int, members: tuple = BASKET) -> pd.Series:
    """Share (0-1) of a group's members above their own n-day average, among members that have one that day."""
    above, have = [], []
    for sym in members:
        s = px.get(sym)
        if s is None:
            continue
        m = _ma(s, n)
        above.append((s > m).where(m.notna()))
        have.append(m.notna())
    if not above:
        raise LookupError("no members")
    a, h = pd.concat(above, axis=1).sort_index(), pd.concat(have, axis=1).sort_index()
    cnt = h.sum(axis=1)
    return (a.fillna(0).sum(axis=1) / cnt.replace(0, np.nan)).dropna()


def ret(s: pd.Series, n: int):
    """Return over the last n trading days."""
    s = s.dropna()
    return _r(s.iloc[-1] / s.iloc[-1 - n] - 1, 4) if len(s) > n else None


def _model() -> dict:
    """Everything the tabs share, from the cached prices: the basket, its averages, RSI, breadth, drawdowns and episodes."""
    p = _prices()
    px = p["px"]
    members = {k: v for k, v in px.items() if k in BASKET}
    idx = basket_index(members)
    m50, m200 = _ma(idx, 50), _ma(idx, 200)
    b50, b200 = breadth(members, 50), breadth(members, 200)
    picks = {k: v for k, v in px.items() if k in PICKS}
    pidx = basket_index({k: full_months(v) for k, v in picks.items()}) if picks else None
    return {"px": px, "members": members, "idx": idx, "m50": m50, "m200": m200, "rsi": rsi(idx), "b50": b50, "b200": b200,
            "dd": drawdown(idx), "episodes": episodes(idx), "errors": p["errors"], "sources": p["sources"],
            "picks": picks, "pidx": pidx, "pdd": drawdown(pidx) if pidx is not None else None,
            "pb50": breadth(picks, 50, PICKS) if picks else None}


def crosses(m50: pd.Series, m200: pd.Series) -> list[dict]:
    d = (m50 - m200).dropna()
    d = d[d.index >= INDEX_START - pd.Timedelta(days=30)]
    sign = np.sign(d)
    flips = sign[(sign != sign.shift(1)) & sign.shift(1).notna() & (sign != 0)]
    return [{"date": str(t.date()), "kind": "golden" if v > 0 else "death"} for t, v in flips.items()]


def where_line(dd: float | None, b50: float | None, r: float | None, vix: float | None, idx: pd.Series, m50: pd.Series, study: dict | None) -> str:
    """The plain-English line on Setup, from the same figures as the signals. Describes, never recommends."""
    if dd is None:
        return "Not enough data yet to say where the basket stands."
    depth = ("near its high" if dd > -0.05 else "in a pullback" if dd > -0.10 else "in a correction" if dd > -0.20 else "in a bear market")
    parts = [f"The AI basket is {abs(dd) * 100:.0f}% below its high, {depth}."]
    low20 = idx.iloc[-1] <= idx.iloc[-20:].min() * 1.0001 if len(idx) >= 20 else False
    below50 = pd.notna(m50.iloc[-1]) and idx.iloc[-1] < m50.iloc[-1]
    if (b50 is not None and b50 < 0.20) or (r is not None and r < 30):
        parts.append("Breadth or momentum is at washout levels (" + ", ".join(x for x in (f"{b50 * 100:.0f}% of stocks above their 50-day" if b50 is not None else "",
                                                                                          f"RSI {r:.0f}" if r is not None else "") if x) + ").")
    elif low20 and below50:
        parts.append("It is still making new lows below its 50-day average: breaking down, not yet washing out.")
    elif below50:
        parts.append("It is below its 50-day average but has stopped making new lows.")
    elif dd <= -0.05:
        parts.append("It is back above its 50-day average" + (f", with {b50 * 100:.0f}% of the stocks above theirs." if b50 is not None else "."))
    if vix is not None:
        parts.append(f"VIX is {vix:.0f}" + (" (fear)." if vix > 30 else " (elevated)." if vix > 20 else " (calm)."))
    if study and study.get("n") and dd <= DD_STUDY:
        m = ((study.get("cross") or {}).get("3m") or {})
        if m.get("median") is not None:
            parts.append(f"In the {study['n']} past basket drawdowns of 15% or more since 2020, the median return 3 months after the 15% point was "
                         f"{m['median'] * 100:+.0f}% (range {m['min'] * 100:+.0f}% to {m['max'] * 100:+.0f}%): a small sample, not a forecast.")
    return " ".join(parts)


# ------------------------------------------------------------------ AI Setup Score
# 0 = fear or washout, 100 = euphoria. Bands: (low, high, key, label); the colours live in ai-stocks.js
BANDS = ((0, 10, "washout", "Washout: past bottoms"), (10, 20, "fear", "Fear"), (20, 50, "soft", "Soft"), (50, 80, "neutral", "Neutral"),
         (80, 90, "warm", "Warm"), (90, 100.01, "stretched", "Stretched: drawdown risk"))
SCORE_PARTS = {"dd": "Basket drawdown", "b50": "Share above the 50-day", "rsi": "Basket RSI 14", "vix": "VIX (inverted)", "rel": "AI minus QQQ, 3 months"}
SMOOTH = 5                          # days in the moving mean of the score
EPISODE_GAP = 30                    # calendar days without a day in the band before a new episode starts
FWD = {"1m": 21, "3m": 63, "6m": 126}


def pct_rank(s: pd.Series) -> pd.Series:
    """Percentile rank 0-100 of each day against every day of the series since INDEX_START (ties share the average rank)."""
    s = s[s.index >= INDEX_START].dropna()
    return 100 * (s.rank(method="average") - 0.5) / len(s) if len(s) else s


def score_parts(idx: pd.Series, b50: pd.Series, r: pd.Series, vix: pd.Series | None, qqq: pd.Series | None) -> pd.DataFrame:
    """The five components on the basket's dates, each as its percentile rank (higher = more euphoric): drawdown (0 at a high ranks
    highest), breadth, RSI, VIX inverted, and the basket's 63-day return minus QQQ's."""
    days = idx[idx.index >= INDEX_START].index
    raw = {"dd": drawdown(idx), "b50": b50, "rsi": r}
    if vix is not None and len(vix):
        raw["vix"] = -vix.reindex(vix.index.union(days)).ffill(limit=5).reindex(days)
    if qqq is not None and len(qqq):
        q = qqq.reindex(qqq.index.union(idx.index)).ffill(limit=5).reindex(idx.index)
        raw["rel"] = idx.pct_change(63, fill_method=None) - q.pct_change(63, fill_method=None)
    return pd.DataFrame({k: pct_rank(v.reindex(days)) for k, v in raw.items()}, index=days)


def setup_score(parts: pd.DataFrame) -> pd.Series:
    """The mean of the components a day has (at least three), smoothed with a SMOOTH-day moving mean."""
    raw = parts.mean(axis=1, skipna=True).where(parts.notna().sum(axis=1) >= 3)
    return raw.rolling(SMOOTH, min_periods=SMOOTH).mean().dropna()


def band_of(v) -> str | None:
    if v is None or pd.isna(v):
        return None
    return next(k for lo, hi, k, _ in BANDS if lo <= v < hi) if v < 100.01 else BANDS[-1][2]


def band_changes(score: pd.Series, days: int = 90) -> int:
    """How many times the band changed in the last `days` calendar days: the whipsaw count."""
    if not len(score):
        return 0
    b = score.map(band_of)
    b = b[b.index >= score.index[-1] - pd.Timedelta(days=days - 1)]
    return int((b != b.shift(1)).iloc[1:].sum())


def band_runs(score: pd.Series, inside) -> list[pd.Timestamp]:
    """First day of each episode: a day in the band (inside(v) true) more than EPISODE_GAP calendar days after the last day in it."""
    starts, last = [], None
    for t, v in score.items():
        if inside(v):
            if last is None or (t - last).days > EPISODE_GAP:
                starts.append(t)
            last = t
    return starts


def _events() -> list[tuple[pd.Timestamp, str]]:
    return [(pd.Timestamp(r["date"]), r.get("name", "")) for r in B.manual_rows(SLUG, "events") if r.get("name")]


def _event_name(t: pd.Timestamp, events) -> str | None:
    near = [(abs((d - t).days), n) for d, n in events if abs((d - t).days) <= EPISODE_GAP]
    return min(near)[1] if near else None


def score_episodes(score: pd.Series, idx: pd.Series) -> dict:
    """Washout (<10) episodes with the best gain over the next 6 and 12 months, and stretched (>90) episodes with the worst fall over
    the next 90 calendar days. A horizon not yet complete gives its value so far, marked partial."""
    ev = _events()
    i_of = {t: i for i, t in enumerate(idx.index)}

    def best(t, n):
        i = i_of.get(t)
        if i is None:
            return None, True
        fut = idx.iloc[i + 1:i + 1 + n]
        return (_r(fut.max() / idx.iloc[i] - 1, 4) if len(fut) else None), len(fut) < n

    def worst(t, cal):
        fut = idx[(idx.index > t) & (idx.index <= t + pd.Timedelta(days=cal))]
        done = idx.index[-1] >= t + pd.Timedelta(days=cal)
        return (_r(min(0.0, fut.min() / idx.loc[t] - 1), 4) if len(fut) else None), not done
    green = []
    for t in band_runs(score, lambda v: v < 10):
        g6, p6 = best(t, 126)
        g12, p12 = best(t, 252)
        green.append({"date": str(t.date()), "score": _r(score.loc[t], 1), "level": _r(idx.loc[t], 2), "best6m": g6, "partial6m": p6,
                      "best12m": g12, "partial12m": p12, "name": _event_name(t, ev)})
    red = []
    for t in band_runs(score, lambda v: v >= 90):
        w, p = worst(t, 90)
        red.append({"date": str(t.date()), "score": _r(score.loc[t], 1), "level": _r(idx.loc[t], 2), "worst90d": w, "partial": p,
                    "name": _event_name(t, ev)})
    return {"green": green[::-1], "red": red[::-1]}


def band_stats(score: pd.Series, idx: pd.Series) -> list[dict]:
    """For every day in each band since 2020: forward 1-, 3- and 6-month basket returns (21, 63, 126 trading days), median and hit rate
    (share of days higher), over the days whose horizon is complete; with the days and the independent episodes in the band."""
    lvl = idx.reindex(score.index)
    pos = pd.Series(range(len(idx)), index=idx.index).reindex(score.index)
    bands = score.map(band_of)
    out = []
    for lo, hi, k, label in BANDS:
        days = bands[bands == k].index
        row = {"band": k, "label": label, "lo": lo, "hi": min(hi, 100), "days": int(len(days)),
               "episodes": len(band_runs(score, lambda v, lo=lo, hi=hi: lo <= v < hi))}
        for h, n in FWD.items():
            fw = [idx.iloc[int(pos[t]) + n] / lvl[t] - 1 for t in days if int(pos[t]) + n < len(idx)]
            row[h] = {"n": len(fw), "median": _r(float(np.median(fw)), 4) if fw else None, "hit": _r(float(np.mean([x > 0 for x in fw])), 3) if fw else None}
        out.append(row)
    return out


def band_sentence(stats: list[dict], band: str | None) -> str:
    row = next((r for r in stats if r["band"] == band), None)
    if not row or not row["days"]:
        return "No day since 2020 sat in this band, so there is no history to compare."
    m = row["3m"]
    head = f"Since 2020 the score spent {row['days']} trading days in this band, in {row['episodes']} separate episode{'s' if row['episodes'] != 1 else ''}"
    if m["median"] is None:
        return head + "; none has a full 3 months behind it yet. Small sample, not a forecast."
    return (head + f"; 3 months later the basket's median return was {m['median'] * 100:+.0f}%, and it was higher on {m['hit'] * 100:.0f}% "
            f"of those days ({m['n']} days with 3 months known). Small-sample history, not a forecast.")


# ------------------------------------------------------------------ VIX
def parse_vix(text: str) -> pd.Series:
    """FRED (observation_date,VIXCLS with '.' for holidays) or Cboe (DATE,OPEN,HIGH,LOW,CLOSE, dates MM/DD/YYYY) -> daily closes."""
    d = pd.read_csv(StringIO(text), dtype=str)
    cols = {c.strip().upper(): c for c in d.columns}
    date = cols.get("OBSERVATION_DATE") or cols.get("DATE")
    val = cols.get("VIXCLS") or cols.get("CLOSE")
    if not (date and val):
        raise ValueError("VIX layout changed")
    s = pd.Series(pd.to_numeric(d[val], errors="coerce").values, index=pd.to_datetime(d[date], errors="coerce", format="mixed"))
    s = s[s.index.notna()].dropna().sort_index()
    if len(s) < 20:
        raise ValueError(f"VIX: {len(s)} rows")
    return s[~s.index.duplicated(keep="last")]


def vix() -> tuple[pd.Series, str]:
    """VIX daily closes and which source answered: FRED first (through curl, see _base._download), Cboe's history file when FRED fails;
    the FRED failure is then marked handled in /api/health."""
    try:
        return parse_vix(fetch(FRED_VIX, DAY, curl=True, timeout=25, min_bytes=500)), "FRED"
    except Exception as e:
        first = e
    try:
        s = parse_vix(fetch(CBOE_VIX, DAY, min_bytes=500))
        handled(FRED_VIX, "FRED did not answer; VIX from Cboe's history file")
        return s, "Cboe"
    except Exception:
        raise first


# ------------------------------------------------------------------ endpoints
def _setup_now() -> dict:
    M = _model()
    px, idx = M["px"], M["idx"]
    def group_cards(syms):
        out = []
        for sym in syms:
            if sym in px:
                try:
                    out.append(stock_card(sym, px[sym]))
                except Exception:
                    pass
        return out
    cards, pick_cards = group_cards(BASKET), group_cards(PICKS)
    try:
        V, vsrc = vix()
    except Exception:
        V, vsrc = None, None

    def lines():
        out = {"AI basket": _pts(idx[idx.index >= INDEX_START], 2)}
        if M["pidx"] is not None:
            out["Owner's picks"] = _pts(M["pidx"][M["pidx"].index >= INDEX_START], 2)
        for e in ("QQQ", "SPY"):
            if e in px:
                s = px[e][px[e].index >= INDEX_START]
                out[e] = _pts(100 * s / s.iloc[0], 2)
        return out
    dd, b50, r = M["dd"], M["b50"], M["rsi"]
    last = lambda s: _r(s.dropna().iloc[-1], 4) if s is not None and len(s.dropna()) else None
    study = _study(M)
    out = payload({"lines": lines, "dd": lambda: _pts(dd, 4), "breadth50": lambda: _pts(b50[b50.index >= INDEX_START], 3),
                   "rsi": lambda: _pts(r[r.index >= INDEX_START], 1), "vix": lambda: _pts(V[V.index >= INDEX_START], 2) if V is not None else None},
                  sources=M["sources"] + [FRED_VIX, CBOE_VIX])
    out["cards"] = cards
    out["pick_cards"] = pick_cards
    out["strip"] = strip(px)
    out["picks_dd"] = _pts(M["pdd"], 4) if M["pdd"] is not None else None
    out["picks_now"] = {"dd": last(M["pdd"]) if M["pdd"] is not None else None, "breadth50": last(M["pb50"]) if M["pb50"] is not None else None,
                        "above200": sum(1 for c in pick_cards if (c["vs200"] or 0) > 0), "n": len(pick_cards),
                        "since": {s: str(full_months(px[s]).index[1].date()) for s in PICKS if s in px and s in LISTED}}
    out["now"] = {"dd": last(dd), "breadth50": last(b50), "breadth200": last(M["b200"]), "rsi": _r(r.iloc[-1], 1), "vix": last(V) if V is not None else None,
                  "above200": sum(1 for c in cards if (c["vs200"] or 0) > 0), "n": len(cards)}
    out["where"] = where_line(out["now"]["dd"], out["now"]["breadth50"], out["now"]["rsi"], out["now"]["vix"], idx, M["m50"], study)
    out["vix_source"] = vsrc
    out |= _score_block(M, V)
    out["errors"] = M["errors"]
    out["as_of"] = B.latest_date(idx)
    return out


def _score_block(M: dict, V: pd.Series | None) -> dict:
    """The AI Setup Score and its backtest for the Setup tab; {} pieces with score_error when it cannot be built."""
    try:
        idx = M["idx"]
        parts = score_parts(idx, M["b50"], M["rsi"], V, M["px"].get("QQQ"))
        sc = setup_score(parts)
        if not len(sc):
            raise LookupError("no score")
        vix_only = pct_rank(-V).rolling(SMOOTH, min_periods=SMOOTH).mean().dropna() if V is not None else None
        now = parts.iloc[-1]
        stats = band_stats(sc, idx)
        band = band_of(sc.iloc[-1])
        return {"score": _pts(sc, 1), "score_now": {"v": _r(sc.iloc[-1], 1), "date": str(sc.index[-1].date()), "band": band,
                                                     "parts": {k: _r(now.get(k), 0) for k in SCORE_PARTS if k in parts}, "names": SCORE_PARTS,
                                                     "changes90": band_changes(sc), "vix_only_changes90": band_changes(vix_only) if vix_only is not None else None,
                                                     "sentence": band_sentence(stats, band)},
                "bands": [{"lo": lo, "hi": min(hi, 100), "key": k, "label": lab} for lo, hi, k, lab in BANDS],
                "score_episodes": score_episodes(sc, idx), "band_stats": stats}
    except Exception as e:
        return {"score": None, "score_error": type(e).__name__}


def _drawdown_now() -> dict:
    M = _model()
    eps = M["episodes"]
    cur = next((e for e in eps if e["ongoing"]), None)
    dd = M["dd"]
    out = payload({"basket": lambda: _pts(dd, 4), "stocks": lambda: {s: _pts(drawdown(v), 4) for s, v in M["members"].items()}},
                  sources=M["sources"])
    out["episodes"] = sorted(eps, key=lambda e: e["peak"], reverse=True)
    peak_t = dd[dd >= 0].index[-1] if (dd >= 0).any() else None
    out["current"] = {"dd": _r(dd.iloc[-1], 4), "peak": str(peak_t.date()) if peak_t is not None else None,
                      "low": _r(dd[dd.index >= peak_t].min(), 4) if peak_t is not None else None,
                      "low_date": str(dd[dd.index >= peak_t].idxmin().date()) if peak_t is not None else None,
                      "days": int((dd.index[-1] - peak_t).days) if peak_t is not None else None, "episode": cur}
    out["stock_now"] = {s: _r(drawdown(v).iloc[-1], 4) for s, v in M["members"].items()}
    pdd = M["pdd"]
    out["picks_basket"] = _pts(pdd, 4) if pdd is not None else None
    out["pick_stocks"] = {s: _pts(drawdown(v), 4) for s, v in M["picks"].items()}
    out["pick_now"] = {s: _r(drawdown(v).iloc[-1], 4) for s, v in M["picks"].items()}
    out["pick_since"] = {s: str(drawdown(v).index[0].date()) for s, v in M["picks"].items()}
    if pdd is not None and len(pdd):
        pk = pdd[pdd >= 0].index[-1] if (pdd >= 0).any() else pdd.index[0]
        out["picks_current"] = {"dd": _r(pdd.iloc[-1], 4), "peak": str(pk.date()), "low": _r(pdd[pdd.index >= pk].min(), 4),
                                "low_date": str(pdd[pdd.index >= pk].idxmin().date()), "days": int((pdd.index[-1] - pk).days)}
    out["errors"] = M["errors"]
    out["as_of"] = B.latest_date(M["idx"])
    return out


def _trend_now() -> dict:
    M = _model()
    idx, m50, m200, r = M["idx"], M["m50"], M["m200"], M["rsi"]
    since = lambda s: s[s.index >= INDEX_START]
    cx = crosses(m50, m200)
    out = payload({"breadth50": lambda: _pts(since(M["b50"]), 3), "breadth200": lambda: _pts(since(M["b200"]), 3), "rsi": lambda: _pts(since(r), 1),
                   "basket": lambda: _pts(since(idx), 2), "ma50": lambda: _pts(since(m50), 2), "ma200": lambda: _pts(since(m200), 2),
                   "spread": lambda: _pts(since(m50 / m200 - 1).dropna(), 4)}, sources=M["sources"])
    out["crosses"] = cx[::-1]
    state = "golden" if m50.iloc[-1] > m200.iloc[-1] else "death"
    out["now"] = {"breadth50": _r(M["b50"].iloc[-1], 3), "breadth200": _r(M["b200"].iloc[-1], 3), "rsi": _r(r.iloc[-1], 1), "state": state,
                  "since": cx[-1]["date"] if cx else None, "vs50": _r(idx.iloc[-1] / m50.iloc[-1] - 1, 4), "vs200": _r(idx.iloc[-1] / m200.iloc[-1] - 1, 4)}
    out["errors"] = M["errors"]
    out["as_of"] = B.latest_date(idx)
    return out


def _fwd(s: pd.Series, t: str, n: int):
    i = s.index.get_indexer([pd.Timestamp(t)])[0]
    return _r(s.iloc[i + n] / s.iloc[i] - 1, 4) if i >= 0 and i + n < len(s) else None


def _summary(vals: list) -> dict:
    v = [x for x in vals if x is not None]
    return {"n": len(v), "median": _r(float(np.median(v)), 4) if v else None, "min": _r(min(v), 4) if v else None, "max": _r(max(v), 4) if v else None,
            "up": sum(1 for x in v if x > 0)}


def _study(M: dict) -> dict:
    idx = M["idx"]
    rows = []
    for e in M["episodes"]:
        if e["depth"] is None or e["depth"] > DD_STUDY or not e["cross15"]:
            continue
        lvl15 = idx.loc[pd.Timestamp(e["cross15"])]
        rows.append({**e, "further": _r(idx.loc[pd.Timestamp(e["trough"])] / lvl15 - 1, 4),
                     "cross": {h: _fwd(idx, e["cross15"], n) for h, n in HORIZONS.items()},
                     "bottom": {h: _fwd(idx, e["trough"], n) for h, n in HORIZONS.items()}})
    past = [r for r in rows if not r["ongoing"]]
    return {"rows": rows, "n": len(past),
            "cross": {h: _summary([r["cross"][h] for r in past]) for h in HORIZONS},
            "bottom": {h: _summary([r["bottom"][h] for r in past]) for h in HORIZONS}}


def _dips_now() -> dict:
    M = _model()
    st = _study(M)
    dd = M["dd"]
    out = payload({"dd": lambda: _pts(dd, 4)}, sources=M["sources"])
    out |= {"rows": sorted(st["rows"], key=lambda r: r["peak"], reverse=True), "n": st["n"], "cross": st["cross"], "bottom": st["bottom"],
            "now": {"dd": _r(dd.iloc[-1], 4)}, "horizons": HORIZONS, "threshold": DD_STUDY}
    out["errors"] = M["errors"]
    out["as_of"] = B.latest_date(M["idx"])
    return out


def _fear_now() -> dict:
    M = _model()
    px, idx = M["px"], M["idx"]
    try:
        V, vsrc = vix()
    except Exception:
        V, vsrc = None, None

    def rel(a: pd.Series, b: pd.Series) -> pd.Series:
        d = pd.concat([a, b], axis=1).dropna()
        d = d[d.index >= INDEX_START]
        r = d.iloc[:, 0] / d.iloc[:, 1]
        return 100 * r / r.iloc[0]

    def vix_pts():
        if V is None:
            raise LookupError("no VIX source answered")
        return _pts(V[V.index >= INDEX_START], 2)
    out = payload({"vix": vix_pts, "ai_qqq": lambda: _pts(rel(idx, px["QQQ"]), 2), "smh_spy": lambda: _pts(rel(px["SMH"], px["SPY"]), 2)},
                  sources=M["sources"] + [FRED_VIX, CBOE_VIX])
    table = {}
    for name, a, b in (("AI basket vs QQQ", idx, px.get("QQQ")), ("SMH vs SPY", px.get("SMH"), px.get("SPY"))):
        if a is None or b is None:
            continue
        row = {}
        for h, n in (("3m", 63), ("12m", 252)):
            ra, rb = ret(a, n), ret(b, n)
            row[h] = {"a": ra, "b": rb, "gap": _r(100 * (ra - rb), 1) if ra is not None and rb is not None else None}
        table[name] = row
    out["relative"] = table
    if V is not None and len(V):
        m = V[V.index >= V.index[-1] - pd.Timedelta(days=31)]
        out["vix_now"] = {"v": _r(V.iloc[-1], 2), "date": str(V.index[-1].date()), "max_1m": _r(m.max(), 2), "pct_since_2020": _r((V[V.index >= INDEX_START] <= V.iloc[-1]).mean(), 3)}
    out["vix_source"] = vsrc
    out["errors"] = M["errors"]
    out["as_of"] = B.latest_date(idx)
    return out


def revenue(cik: int) -> pd.Series:
    """Quarterly revenue ($bn, calendar quarters) from EDGAR, kept under its own cache key: compute_chips caches the same companyfacts
    URLs cut down to capex tags, so its edgar_series would find no revenue in that copy."""
    url = EDGAR.format(cik=cik)
    j = json.loads(fetch(url, DAY, headers=CC.SEC_HEADERS, key=url + "#revenue", reduce=CC._edgar_reduce(CC.REVENUE_TAGS), min_bytes=100))
    ss = sorted((CC.quarterly(j[t]) for t in CC.REVENUE_TAGS if t in j), key=lambda s: s.index.max() if len(s) else pd.Timestamp(0))
    out = pd.Series(dtype=float)
    for s in ss:
        out = s.combine_first(out) if len(out) else s
    return CC.cal_quarter(out.sort_index()) / 1e9


def _fundamentals_now() -> dict:
    rev, errors = {}, {}
    for sym, cik in REV_CIKS.items():
        try:
            rev[sym] = revenue(cik)
        except Exception as e:
            errors[sym] = type(e).__name__

    def yoy():
        return {k: _pts((v / v.shift(4) - 1).dropna()[lambda s: s.index >= "2018-01-01"], 4) for k, v in rev.items() if len(v) >= 5}

    def total_yoy():
        """Revenue of the companies that reported both this quarter and the same quarter a year before, summed, against a year before."""
        d = pd.DataFrame(rev).sort_index()
        if d.empty:
            raise LookupError("no revenue")
        out = {}
        for i in range(4, len(d)):
            now, ago = d.iloc[i], d.iloc[i - 4]
            both = now.notna() & ago.notna()
            if both.sum() >= max(3, len(rev) // 2):
                out[d.index[i]] = now[both].sum() / ago[both].sum() - 1
        s = pd.Series(out, dtype=float)
        return _pts(s[s.index >= "2018-01-01"], 4)
    cap = {}
    try:
        cap = CC._capex()
    except Exception as e:
        errors["capex"] = type(e).__name__

    def capex_yoy():
        t = cap.get("ttm") or []
        return [[t[i][0], _r(t[i][1] / t[i - 4][1] - 1, 4)] for i in range(4, len(t)) if t[i - 4][1]]
    out = payload({"revenue_yoy": yoy, "basket_yoy": total_yoy, "capex_ttm": lambda: cap.get("ttm") or None, "capex_yoy": lambda: capex_yoy() or None},
                  sources=[EDGAR.format(cik=c) + "#revenue" for c in REV_CIKS.values()])
    last = {}
    for k, v in rev.items():
        if len(v) >= 5:
            last[k] = {"quarter": str(v.index[-1].to_period("Q")), "revenue": _r(v.iloc[-1], 2), "yoy": _r(v.iloc[-1] / v.iloc[-5] - 1, 4) if v.iloc[-5] else None}
    out["last"] = last
    out["capex_kpi"] = cap.get("kpi")
    out["left_out"] = [s for s in BASKET if s not in REV_CIKS]
    out["errors"] = errors
    out["as_of"] = B.latest_date(*rev.values()) if rev else None
    out["stale"] = {**out.get("stale", {}), **(cap.get("stale") or {})}
    return out


def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, size, start of body). /api/ai-stocks/layout."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    a, b = (pd.Timestamp.now() - pd.Timedelta(days=40)).strftime("%Y-%m-%d"), pd.Timestamp.now().strftime("%Y-%m-%d")
    nh = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
    urls = {"fred vix": (FRED_VIX, {}), "cboe vix": (CBOE_VIX, {}),
            "nasdaq NVDA": (B.NASDAQ_ANY.format(sym="NVDA", cls="stocks", a=a, b=b), nh), "nasdaq SMH etf": (B.NASDAQ_ANY.format(sym="SMH", cls="etf", a=a, b=b), nh),
            "edgar PLTR": (EDGAR.format(cik=REV_CIKS["PLTR"]), CC.SEC_HEADERS)}

    def one(item):
        k, (u, h) = item
        try:
            r = requests.get(u, headers={**B.UA, **h}, timeout=25)
            return k, {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type", ""), "start": r.text[:300]}
        except Exception as e:
            return k, {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=6) as ex:
        out = dict(ex.map(one, urls.items()))
    import subprocess                                         # FRED resets python-requests connections; _base fetches it with curl
    try:
        c = subprocess.run(["curl", "-s", "-L", "--max-time", "20", "-A", B.UA["User-Agent"], "-o", "/dev/null", "-w", "%{http_code} %{size_download}", FRED_VIX],
                           capture_output=True, text=True, timeout=30)
        out["fred vix (curl)"] = c.stdout.strip() or f"exit {c.returncode}"
    except Exception as e:
        out["fred vix (curl)"] = type(e).__name__
    return out


# ------------------------------------------------------------------ readings and signals (cached payloads only)
def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


def _band(x, lo, hi):
    return 0 if x is None else 1 if x > hi else -1 if x < lo else 0


def READINGS() -> list[dict]:
    """Headline figures per tab as they read now, from cached payloads. lean +1 = healthier setup, -1 = more stress."""
    out = []

    def add(tab, key, label, value, lean, note):
        if value is not None:
            out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": lean, "note": note})
    s, d, t, p, f, u = (_cached_payload(n) for n in ("setup", "drawdown", "trend", "dips", "fear", "fundamentals"))
    n = s.get("now") or {}
    if n.get("n"):
        add("setup", "above200", "Stocks above their 200-day average (of 13)", n.get("above200"), _band(n["above200"] / n["n"], 0.4, 0.6),
            "+1 when more than 60% are above, -1 when fewer than 40%")
    sn = s.get("score_now") or {}
    if sn.get("v") is not None:
        add("setup", "setup_score", "AI Setup Score (0 = washout, 100 = euphoria)", sn["v"], _band(sn["v"], 20, 80),
            "+1 above 80 (broad strength), -1 below 20 (fear); below 10 or above 90 is the signal")
    dd = (d.get("current") or {}).get("dd")
    if dd is not None:
        add("drawdown", "basket_drawdown", "AI basket below its high (%)", _r(100 * dd, 1), 1 if dd > -0.05 else -1 if dd < -0.10 else 0,
            "+1 within 5% of the high, -1 more than 10% below")
    tn = t.get("now") or {}
    if tn.get("breadth50") is not None:
        add("trend", "breadth_50d", "Share of the basket above its 50-day average (%)", _r(100 * tn["breadth50"], 0), _band(tn["breadth50"], 0.4, 0.6),
            "+1 above 60%, -1 below 40%")
    if tn.get("rsi") is not None:
        add("trend", "rsi_basket", "Basket RSI 14", tn["rsi"], _band(tn["rsi"], 40, 60), "+1 above 60, -1 below 40")
    if tn.get("state"):
        add("trend", "cross", "Basket 50-day vs 200-day average", "50 above 200" if tn["state"] == "golden" else "50 below 200",
            1 if tn["state"] == "golden" else -1, "+1 while the 50-day is above the 200-day")
    if p.get("rows") is not None:
        add("dips", "past_dips", "Past basket drawdowns of 15% or more since 2020", p.get("n"), 0, "context only: the sample the forward returns come from")
    v = (f.get("vix_now") or {}).get("v")
    if v is not None:
        add("fear", "vix", "VIX", v, 1 if v < 20 else -1 if v > 25 else 0, "+1 below 20, -1 above 25")
    g = (((f.get("relative") or {}).get("AI basket vs QQQ") or {}).get("3m") or {}).get("gap")
    if g is not None:
        add("fear", "ai_vs_qqq", "AI basket minus QQQ, 3-month return (pts)", g, _band(g, -3, 3), "+1 when AI leads by more than 3 points, -1 when it lags by more")
    by = u.get("basket_yoy") or []
    if by:
        add("fundamentals", "revenue_yoy", "Basket revenue growth on a year, latest quarter (%)", _r(100 * by[-1][1], 1),
            _band(by[-1][1] - (by[-2][1] if len(by) >= 2 else by[-1][1]), -0.02, 0.02), "+1 when growth sped up by more than 2 points on the quarter before, -1 when it slowed")
    return out


def SIGNALS() -> list[dict]:
    """The owner's approved watch points (data/signals/watchlist.json, approved 6 Nov 2026), from cached payloads only.
    lean +1 = healthier setup, -1 = more stress. Each crossed comes from its own test."""
    out = []

    def add(key, tab, label, value, unit, lean, watch, crossed, note=None):
        out.append({"key": key, "tab": tab, "label": label, "value": value, "unit": unit, "lean": lean, "watch": watch, "crossed": bool(crossed),
                    **({"note": note} if note else {})})
    s, t, f = _cached_payload("setup"), _cached_payload("trend"), _cached_payload("fear")
    dd = s.get("dd") or []
    if dd:
        now = dd[-1][1]
        recent = [v for ts, v in dd if ts >= dd[-1][0] - 91 * 86400]
        was_deep = min(recent) <= -0.10
        repaired = now >= -0.05 and was_deep
        add("basket_drawdown", "drawdown", "AI basket drawdown from its high", _r(100 * now, 1), "%", 1 if now > -0.05 else -1 if now < -0.10 else 0,
            "deeper than -20% (a bear market), or back within -5% (dip repaired)", now < -0.20 or repaired,
            "bear market" if now < -0.20 else f"repaired: within 5% of the high after {min(recent) * 100:.0f}% in the last 3 months" if repaired
            else f"low in the last 3 months {min(recent) * 100:.1f}%; 'repaired' counts only after a 10%+ dip")
    b = s.get("breadth50") or []
    if b:
        now = b[-1][1]
        low3m = min(v for ts, v in b if ts >= b[-1][0] - 91 * 86400)
        back = now > 0.60 and low3m < 0.40
        add("breadth_50d", "trend", "Share of the basket above its 50-day average", _r(100 * now, 0), "%", _band(now, 0.4, 0.6),
            "below 20% (washout) or back above 60% (recovery broadening)", now < 0.20 or back,
            "washout" if now < 0.20 else "recovery broadening" if back else f"low in the last 3 months {low3m * 100:.0f}%; 'back above 60%' counts after a dip below 40%")
    sc = s.get("score") or []
    if sc:
        v = sc[-1][1]
        add("setup_score", "setup", "AI Setup Score", v, "", _band(v, 20, 80), "below 10 (washout) or above 90 (stretched)", v < 10 or v >= 90,
            "washout: the band that has come near past bottoms" if v < 10 else "stretched: the band that has come before drawdowns" if v >= 90
            else f"band: {band_of(v)}")
    vn = f.get("vix_now") or {}
    v = vn.get("v")
    if v is None and s.get("vix"):
        v = s["vix"][-1][1]
        m = max(x for ts, x in s["vix"] if ts >= s["vix"][-1][0] - 31 * 86400)
    else:
        m = vn.get("max_1m")
    if v is not None:
        calm = v < 20 and m is not None and m > 25
        add("vix", "fear", "VIX", v, "", 1 if v < 20 else -1 if v > 25 else 0, "above 30 (fear), or back below 20 after being above 25 in the last month",
            v > 30 or calm, "fear" if v > 30 else f"back below 20 after {m:.0f} in the last month" if calm else (f"high in the last month {m:.1f}" if m is not None else None))
    g = ((f.get("relative") or {}).get("AI basket vs QQQ") or {}).get("3m") or {}
    if g.get("gap") is not None:
        add("ai_vs_qqq", "fear", "AI basket minus QQQ, 3-month return", g["gap"], " pts", _band(g["gap"], -3, 3), "a 10-point gap either way", abs(g["gap"]) >= 10,
            f"AI basket {g['a'] * 100:+.1f}%, QQQ {g['b'] * 100:+.1f}%")
    return out


# ------------------------------------------------------------------ cached endpoints
def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


_prices = _cached_ep("prices", _prices_now)
ENDPOINTS = {"setup": _cached_ep("setup", _setup_now), "drawdown": _cached_ep("drawdown", _drawdown_now), "trend": _cached_ep("trend", _trend_now),
             "dips": _cached_ep("dips", _dips_now), "fear": _cached_ep("fear", _fear_now), "fundamentals": _cached_ep("fundamentals", _fundamentals_now),
             "layout": _cached_ep("layout", _layout_now, 1800)}
