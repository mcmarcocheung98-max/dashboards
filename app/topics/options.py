"""Options Setup: what the options market is pricing on the AI stocks and the indexes (/options).

Read-only analysis, not investment advice: the page describes what the listed options imply (volatility, skew, positioning, expected
moves) and makes no buy or sell call. A trading portal, if one comes, is a separate dashboard.

Data
  Cboe delayed option chains  https://cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json (an index takes an underscore: _SPX),
                              one file per symbol: the underlying quote and every listed option with bid, ask, last, volume, open
                              interest, IV, delta, gamma, theta, vega, rho. Delayed 15 minutes. Fetched per symbol with a 15-minute
                              cache during US market hours and hourly outside, through _base.fetch (a disk snapshot serves when Cboe is
                              down), reduced on download to the symbol's own listings within 400 days and 60-150% of spot.
  Cboe index histories        VIX_History.csv, VIX3M_History.csv, VVIX_History.csv, SKEW_History.csv (daily closes since 1990 / 2006 / 2009).
  Closes                      from the AI Stocks dashboard (Nasdaq's quote API, imported, never fetched twice) for realised volatility.
  data/options/universe.csv   the symbols (SPY, QQQ, IWM, SMH and every AI Stocks ticker); events.csv: earnings, FOMC and monthly OPEX dates.

History accrues on the volume: once per trading day, per symbol, the per-expiry figures (ATM IV, 25-delta IVs, put/call ratios, open
interest, expected moves, max pain) are kept in SNAPSHOT_DIR/options/daily/<SYM>.json (the way nba_odds keeps its state), so IV rank,
IV vs realised and expected-vs-realised fill in from the first day the server ran this dashboard.

Formulas (see data/options/README.md, Method): ATM IV = mean of the call and put IV at the strike nearest spot; 25-delta IVs by linear
interpolation in delta; skew = put25 - call25; risk reversal = call25 - put25; expected move = ATM straddle mid, and spot x IV x sqrt(T);
IV rank = (IV - low) / (high - low) over the accrued history (up to a year), IV percentile = share of days below today; max pain = the
strike with the smallest total intrinsic value of open interest; dealer GEX per strike = gamma x OI x 100 x spot^2 x 1% with calls
positive and puts negative (dealers long calls, short puts: a convention, not a fact about any book); realised vol = annualised standard
deviation of daily log returns over 10 and 30 days; unusual activity = volume / OI above 5 with volume above 1,000.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import Topic, _base as B
from ._base import DAY, HOUR, _pts, _r, fetch, fetch_json, handled, manual_rows, payload
from . import ai_stocks as AI

SLUG = "options"
TOPIC = Topic(SLUG, "Options Setup: what the market is pricing",
              "What the listed options say about the AI stocks and the indexes: implied against realised volatility, the VIX term structure, "
              "skew and put/call positioning, dealer gamma, expected moves against the event calendar, and a payoff calculator on the live "
              "chains. Read-only analysis, not advice.",
              "options", (("setup", "Setup"), ("chains", "Chains"), ("vol", "Volatility"), ("skew", "Skew & flow"), ("moves", "Expected moves"), ("lab", "Strategy lab")),
              ("setup", "vol", "skew", "moves"), icon="chart", order=31)

CBOE_CHAIN = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
CBOE_HIST = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv"
VIX_URL, VIX3M_URL, VVIX_URL, SKEW_URL = (CBOE_HIST.format(name=n) for n in ("VIX", "VIX3M", "VVIX", "SKEW"))
INDEXES = ("SPY", "QQQ", "IWM", "SMH")           # the index proxies: their IV rank falls back to the VIX percentile until history accrues
MIN_HISTORY = 60                                  # days of accrued history before IV rank and skew percentiles stand on their own
MAX_DTE = 400                                     # expiries kept
KEEP_LO, KEEP_HI = 0.6, 1.5                       # strikes kept, as a share of spot
UNUSUAL_RATIO, UNUSUAL_VOLUME = 5.0, 1000         # volume / OI and volume for the unusual-activity table
RATE = 0.04                                       # risk-free rate for the Strategy lab's default (editable on the page)
ET = ZoneInfo("America/New_York")

SOURCES = [{"name": "Cboe delayed option chains (one JSON per symbol: quote, every listed option with bid, ask, last, volume, open interest, IV and Greeks; 15 minutes delayed)",
            "url": "https://www.cboe.com/delayed_quotes/", "cadence": "15 min in US market hours, hourly outside"},
           {"name": "Cboe index histories: VIX, VIX3M, VVIX and SKEW daily closes", "url": "https://www.cboe.com/tradable_products/vix/vix_historical_data/", "cadence": "daily"},
           {"name": "Nasdaq quote API daily closes, through the AI Stocks dashboard (realised volatility)", "url": "https://www.nasdaq.com/market-activity/stocks/nvda/historical", "cadence": "daily"},
           {"name": "Event calendar: earnings dates (company investor-relations pages), FOMC meetings (Federal Reserve), monthly expirations (Cboe)",
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "cadence": "hand-entered"}]
NOTES = ("Not investment advice: this page describes what listed options imply and makes no buy or sell call; the Strategy lab is a calculator, not an order ticket. "
         "Quotes are Cboe's delayed feed (15 minutes); outside market hours they are the last session's. IV rank and percentile need history, which accrues "
         "one day per trading day from the day this dashboard first ran; until 60 days exist the index proxies use the VIX's percentile and the stocks show "
         "their thin history with its day count. Dealer gamma exposure assumes dealers are long calls and short puts, a convention, not a fact about any book. "
         "Leans: +1 = calmer pricing (options cheap against movement, upright term structure), -1 = stress (inverted VIX curve, rich puts, high IV rank).")
FOOTER = "Read-only analysis. Not investment advice: no buy or sell calls; the Strategy lab is a calculator, nothing is traded or stored."

OCC = re.compile(r"^(?P<root>[A-Z0-9]+?)(?P<ymd>\d{6})(?P<cp>[CP])(?P<k>\d{8})$")


# ------------------------------------------------------------------ universe and events (data/options/*.csv)
def _csv_rows(name: str) -> list[dict]:
    """All rows of data/options/<name>.csv (manual_rows keeps only dated rows; universe.csv has none)."""
    import csv
    f = B.MANUAL_DIR / SLUG / f"{name}.csv"
    if not f.exists():
        return []
    with f.open(newline="", encoding="utf-8") as fh:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(fh)]
    return [r for r in rows if r and not next(iter(r.values()), "").startswith("#")]


def universe() -> list[dict]:
    """[{sym, name, group, cboe}] from universe.csv, plus any AI Stocks ticker the file does not list (core, then picks), in file order."""
    rows = [r for r in _csv_rows("universe") if r.get("symbol")]
    seen = {r["symbol"].upper() for r in rows}
    for sym in AI.STOCKS:
        if sym not in seen:
            rows.append({"symbol": sym, "name": AI.NAMES.get(sym, sym), "group": "core" if sym in AI.BASKET else "picks", "cboe": sym})
            seen.add(sym)
    out = []
    for r in rows:
        sym = r["symbol"].upper()
        group = r.get("group") or ("index" if sym in INDEXES else "core" if sym in AI.BASKET else "picks" if sym in AI.PICKS else "owner")
        out.append({"sym": sym, "name": r.get("name") or AI.NAMES.get(sym, sym), "group": group, "cboe": (r.get("cboe") or sym).upper(),
                    "both": sym in AI.BASKET and sym in AI.PICKS})
    return out


def events(today: date | None = None) -> list[dict]:
    """events.csv rows (date, symbol, kind, label, source, note, verify) from a week ago on, soonest first."""
    today = today or date.today()
    out = []
    for r in manual_rows(SLUG, "events"):
        try:
            d = pd.Timestamp(r["date"]).date()
        except (ValueError, TypeError):
            continue
        if d < today - timedelta(days=7):
            continue
        out.append({"date": str(d), "sym": (r.get("symbol") or "").upper() or None, "kind": r.get("kind") or "event", "label": r.get("label") or r.get("kind") or "",
                    "source": r.get("source") or "", "note": r.get("note") or "", "verify": (r.get("verify") or "").lower() in ("yes", "y", "true", "1", "verify")})
    return sorted(out, key=lambda e: e["date"])


def next_earnings(sym: str, evs: list[dict], today: date | None = None) -> dict | None:
    today = today or date.today()
    for e in evs:
        if e["sym"] == sym and e["kind"] == "earnings" and e["date"] >= str(today):
            return e
    return None


# ------------------------------------------------------------------ market hours and fetching
def market_open(now: datetime | None = None) -> bool:
    """US regular session (9:30-16:15 New York, a quarter hour for the delayed feed to catch up), weekdays; holidays count as open (a cheap refresh)."""
    t = (now or datetime.now(tz=ET)).astimezone(ET)
    return t.weekday() < 5 and (9, 30) <= (t.hour, t.minute) < (16, 15)


def ttl_now(now: datetime | None = None) -> float:
    return 15 * 60 if market_open(now) else HOUR


def chain_url(cboe_sym: str) -> str:
    return CBOE_CHAIN.format(sym=cboe_sym)


def reduce_chain(sym: str):
    """text -> text: the quote and the symbol's own listings (root SYM or SYMW, within MAX_DTE days and KEEP_LO-KEEP_HI of spot), the fields the
    page uses, compact. Applied to each fresh download before it is cached and snapshotted: an index file is 13 MB, a stock's 2 MB."""
    keep = ("bid", "ask", "last_trade_price", "volume", "open_interest", "iv", "delta", "gamma", "vega", "theta", "last_trade_time")

    def go(text: str) -> str:
        j = json.loads(text)
        d = j.get("data") or {}
        spot = float(d.get("current_price") or d.get("close") or 0) or None
        today = date.today()
        roots = {sym, sym + "W"}
        rows = []
        for o in d.get("options") or []:
            m = OCC.match(str(o.get("option", "")))
            if not m or m.group("root") not in roots:
                continue
            exp = datetime.strptime(m.group("ymd"), "%y%m%d").date()
            k = int(m.group("k")) / 1000
            if (exp - today).days > MAX_DTE or exp < today - timedelta(days=3):
                continue
            if spot and not (KEEP_LO * spot <= k <= KEEP_HI * spot):
                continue
            rows.append({"option": o["option"], **{f: o.get(f) for f in keep}})
        quote = {k: v for k, v in d.items() if k != "options"}
        return json.dumps({"timestamp": j.get("timestamp"), "symbol": j.get("symbol"), "reduced": True, "data": {**quote, "options": rows}}, separators=(",", ":"))
    return go


def chain_text(sym: str, cboe_sym: str | None = None) -> str:
    url = chain_url(cboe_sym or sym)
    return fetch(url, ttl_now(), min_bytes=400, timeout=90, reduce=reduce_chain(sym))


# ------------------------------------------------------------------ parsing
def parse_chain(text_or_obj, sym: str) -> dict:
    """Cboe's layout ({timestamp, symbol, data: {current_price, ..., options: [{option, bid, ask, iv, open_interest, volume, delta, gamma, ...}]}})
    -> {sym, spot, iv30, trade_date, asof, options: DataFrame[exp, dte, cp, strike, bid, ask, mid, last, vol, oi, iv, delta, gamma, vega, theta]}.
    IV comes as a fraction (0.32 = 32%); iv30 on the quote as a percent. Rows with no IV (unquoted) are dropped; roots other than the symbol's
    own (adjusted series such as B1VDA) are left out."""
    j = json.loads(text_or_obj) if isinstance(text_or_obj, str) else text_or_obj
    d = j.get("data") or {}
    spot = d.get("current_price") or d.get("close")
    if not spot or float(spot) <= 0:
        raise ValueError(f"{sym}: no price on the quote")
    spot = float(spot)
    stamp = str(d.get("last_trade_time") or j.get("timestamp") or "")
    trade_date = stamp[:10] if stamp else None
    rows, roots = [], {sym, sym + "W"}
    for o in d.get("options") or []:
        m = OCC.match(str(o.get("option", "")))
        if not m or m.group("root") not in roots:
            continue
        iv = o.get("iv")
        if not iv or iv <= 0:
            continue
        exp = datetime.strptime(m.group("ymd"), "%y%m%d").date()
        bid, ask = float(o.get("bid") or 0), float(o.get("ask") or 0)
        rows.append((exp, m.group("cp"), int(m.group("k")) / 1000, bid, ask, (bid + ask) / 2 if ask > 0 else None, o.get("last_trade_price") or None,
                     float(o.get("volume") or 0), float(o.get("open_interest") or 0), float(iv), o.get("delta"), o.get("gamma"), o.get("vega"), o.get("theta")))
    if not rows:
        raise ValueError(f"{sym}: no quoted options (layout changed?)")
    df = pd.DataFrame(rows, columns=["exp", "cp", "strike", "bid", "ask", "mid", "last", "vol", "oi", "iv", "delta", "gamma", "vega", "theta"])
    for c in ("last", "delta", "gamma", "vega", "theta"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    base = pd.Timestamp(trade_date).date() if trade_date else date.today()
    df["dte"] = [(e - base).days for e in df["exp"]]
    df = df[df["dte"] >= 0].sort_values(["exp", "strike", "cp"]).reset_index(drop=True)
    return {"sym": sym, "spot": spot, "iv30": _r(d.get("iv30"), 2), "trade_date": trade_date, "asof": stamp or None, "timestamp": j.get("timestamp"),
            "quote": {k: d.get(k) for k in ("bid", "ask", "open", "high", "low", "prev_day_close", "volume", "price_change_percent")}, "options": df}


def parse_history(text: str, col: str | None = None) -> pd.Series:
    """Cboe's daily history CSVs: DATE,OPEN,HIGH,LOW,CLOSE (VIX, VIX3M) or DATE,<NAME> (VVIX, SKEW); MM/DD/YYYY dates -> daily closes."""
    d = pd.read_csv(StringIO(text), dtype=str)
    cols = {c.strip().upper(): c for c in d.columns}
    val = cols.get("CLOSE") or (cols.get(col.upper()) if col else None) or next((c for k, c in cols.items() if k != "DATE"), None)
    if "DATE" not in cols or not val:
        raise ValueError("Cboe history layout changed")
    s = pd.Series(pd.to_numeric(d[val], errors="coerce").values, index=pd.to_datetime(d[cols["DATE"]], errors="coerce", format="mixed"))
    s = s[s.index.notna()].dropna().sort_index()
    if len(s) < 20:
        raise ValueError(f"history: {len(s)} rows")
    return s[~s.index.duplicated(keep="last")]


def index_history(name: str) -> pd.Series:
    url = CBOE_HIST.format(name=name)
    return parse_history(fetch(url, DAY, min_bytes=500), name)


# ------------------------------------------------------------------ Black-Scholes (the fixture chains, probability of profit; the Strategy lab repeats it in JS)
def ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs(cp: str, s: float, k: float, t: float, iv: float, r: float = RATE) -> dict:
    """Price, delta, gamma, vega (per 1 vol point), theta (per day) of a European option; t in years."""
    if t <= 0 or iv <= 0:
        intr = max(0.0, s - k) if cp == "C" else max(0.0, k - s)
        return {"price": intr, "delta": (1.0 if s > k else 0.0) if cp == "C" else (-1.0 if s < k else 0.0), "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    sq = iv * math.sqrt(t)
    d1 = (math.log(s / k) + (r + iv * iv / 2) * t) / sq
    d2 = d1 - sq
    disc = math.exp(-r * t)
    if cp == "C":
        price, delta = s * ncdf(d1) - k * disc * ncdf(d2), ncdf(d1)
        theta = (-s * npdf(d1) * iv / (2 * math.sqrt(t)) - r * k * disc * ncdf(d2)) / 365
    else:
        price, delta = k * disc * ncdf(-d2) - s * ncdf(-d1), ncdf(d1) - 1
        theta = (-s * npdf(d1) * iv / (2 * math.sqrt(t)) + r * k * disc * ncdf(-d2)) / 365
    return {"price": price, "delta": delta, "gamma": npdf(d1) / (s * sq), "vega": s * npdf(d1) * math.sqrt(t) / 100, "theta": theta}


def prob_above(s: float, k: float, t: float, iv: float, r: float = RATE) -> float:
    """P(S_T > k) under the lognormal (risk-neutral) model: N(d2)."""
    if t <= 0 or iv <= 0:
        return 1.0 if s > k else 0.0
    sq = iv * math.sqrt(t)
    return ncdf((math.log(s / k) + (r - iv * iv / 2) * t) / sq)


# ------------------------------------------------------------------ per-expiry calculations (pure functions of the options frame)
def _mid_at(df: pd.DataFrame, cp: str, strike: float):
    r = df[(df["cp"] == cp) & (df["strike"] == strike)]
    if r.empty:
        return None
    m = r["mid"].iloc[0]
    return float(m) if pd.notna(m) and m > 0 else None


def atm_strike(df: pd.DataFrame, spot: float) -> float | None:
    ks = sorted(set(df["strike"]))
    return min(ks, key=lambda k: abs(k - spot)) if ks else None


def atm_iv(df: pd.DataFrame, spot: float) -> float | None:
    """Mean of the call and put IV at the strike nearest spot (either alone if one is missing)."""
    k = atm_strike(df, spot)
    if k is None:
        return None
    ivs = [float(v) for v in df[df["strike"] == k]["iv"] if v > 0]
    return sum(ivs) / len(ivs) if ivs else None


def delta_iv(df: pd.DataFrame, cp: str, target: float) -> float | None:
    """IV at |delta| = target (0.25 for the 25-delta) by linear interpolation across the expiry's strikes of that side; None outside the range."""
    side = df[(df["cp"] == cp) & df["delta"].notna() & (df["iv"] > 0)].copy()
    if side.empty:
        return None
    side["ad"] = side["delta"].abs()
    side = side[(side["ad"] > 0.02) & (side["ad"] < 0.98)].sort_values("ad")
    if len(side) < 2 or not (side["ad"].iloc[0] <= target <= side["ad"].iloc[-1]):
        return None
    return float(np.interp(target, side["ad"].values, side["iv"].values))


def straddle(df: pd.DataFrame, spot: float) -> float | None:
    """ATM call mid + ATM put mid: what the market charges for the move to expiry in either direction."""
    k = atm_strike(df, spot)
    if k is None:
        return None
    c, p = _mid_at(df, "C", k), _mid_at(df, "P", k)
    return c + p if c is not None and p is not None else None


def max_pain(df: pd.DataFrame) -> float | None:
    """The strike at which the open interest, settled there, would pay the least: argmin over strikes S of sum calls max(0,S-K)xOI + puts max(0,K-S)xOI."""
    oi = df[df["oi"] > 0]
    if oi.empty:
        return None
    ks = np.array(sorted(set(oi["strike"])))
    calls, puts = oi[oi["cp"] == "C"], oi[oi["cp"] == "P"]
    pay = [np.sum(np.maximum(0, s - calls["strike"].values) * calls["oi"].values) + np.sum(np.maximum(0, puts["strike"].values - s) * puts["oi"].values) for s in ks]
    return float(ks[int(np.argmin(pay))])


def gex_by_strike(df: pd.DataFrame, spot: float) -> tuple[list[list], float | None]:
    """Dealer gamma exposure per strike in dollars per 1% move: gamma x OI x 100 x spot^2 x 0.01, calls positive, puts negative (dealers taken as long
    calls and short puts). Returns ([[strike, gex], ...] sorted by strike, total)."""
    g = df[df["gamma"].notna() & (df["oi"] > 0)]
    if g.empty:
        return [], None
    sign = np.where(g["cp"] == "C", 1.0, -1.0)
    val = g["gamma"].values * g["oi"].values * 100 * spot * spot * 0.01 * sign
    by = pd.Series(val, index=g["strike"].values).groupby(level=0).sum().sort_index()
    return [[float(k), _r(v, 0)] for k, v in by.items()], _r(by.sum(), 0)


def pc_ratios(df: pd.DataFrame) -> dict:
    c, p = df[df["cp"] == "C"], df[df["cp"] == "P"]
    cv, pv, co, po = c["vol"].sum(), p["vol"].sum(), c["oi"].sum(), p["oi"].sum()
    return {"pc_vol": _r(pv / cv, 2) if cv > 0 else None, "pc_oi": _r(po / co, 2) if co > 0 else None,
            "vol": _r(cv + pv, 0), "oi": _r(co + po, 0), "call_oi": _r(co, 0), "put_oi": _r(po, 0)}


def unusual(df: pd.DataFrame, sym: str, spot: float, ratio: float = UNUSUAL_RATIO, volume: float = UNUSUAL_VOLUME) -> list[dict]:
    """Lines whose day's volume is more than `ratio` times their open interest and above `volume`: new positions, not rolls of old ones."""
    u = df[(df["vol"] >= volume) & (df["oi"] > 0) & (df["vol"] / df["oi"] > ratio)]
    out = [{"sym": sym, "exp": str(r.exp), "dte": int(r.dte), "cp": r.cp, "strike": float(r.strike), "vol": _r(r.vol, 0), "oi": _r(r.oi, 0), "ratio": _r(r.vol / r.oi, 1),
            "iv": _r(r.iv, 4), "mid": _r(r.mid, 2), "otm": _r(r.strike / spot - 1, 4), "premium": _r(r.vol * (r.mid or 0) * 100, 0)} for r in u.itertuples()]
    return sorted(out, key=lambda x: -x["ratio"])


def third_friday(y: int, m: int) -> date:
    d = date(y, m, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def is_monthly(exp: date, listed: set | None = None) -> bool:
    """A standard monthly expiry: the third Friday, or the Thursday before it when that Friday is a holiday (no Friday listed)."""
    tf = third_friday(exp.year, exp.month)
    return exp == tf or (exp == tf - timedelta(days=1) and (listed is None or tf not in listed))


def expiry_table(chain: dict) -> list[dict]:
    """One row per expiry: dte, T, ATM IV, 25-delta put and call IV, skew, risk reversal, straddle and IV expected moves, put/call ratios, OI, max pain, monthly flag."""
    spot, df = chain["spot"], chain["options"]
    listed = set(df["exp"])
    out = []
    for exp, g in df.groupby("exp", sort=True):
        dte = int(g["dte"].iloc[0])
        t = max(dte, 0.5) / 365
        iv = atm_iv(g, spot)
        p25, c25 = delta_iv(g, "P", 0.25), delta_iv(g, "C", 0.25)
        st = straddle(g, spot)
        row = {"exp": str(exp), "dte": dte, "monthly": is_monthly(exp, listed), "atm_iv": _r(iv, 4), "put25": _r(p25, 4), "call25": _r(c25, 4),
               "skew": _r(p25 - c25, 4) if p25 is not None and c25 is not None else None, "rr": _r(c25 - p25, 4) if p25 is not None and c25 is not None else None,
               "straddle": _r(st, 2), "em_straddle": _r(st / spot, 4) if st else None, "em_iv": _r(iv * math.sqrt(t), 4) if iv else None,
               "max_pain": max_pain(g), **pc_ratios(g)}
        out.append(row)
    return out


def front_expiry(rows: list[dict], min_dte: int = 5) -> dict | None:
    """The front month: the nearest monthly expiry at least `min_dte` days out (so the week-of OPEX does not stand for the month); else the nearest expiry."""
    ok = [r for r in rows if r["monthly"] and r["dte"] >= min_dte and r["atm_iv"]]
    if ok:
        return ok[0]
    ok = [r for r in rows if r["dte"] >= min_dte and r["atm_iv"]]
    return ok[0] if ok else (rows[0] if rows else None)


def realised_vol(closes: pd.Series, n: int) -> pd.Series:
    """Annualised standard deviation of daily log returns over the last n trading days, as a series."""
    s = pd.to_numeric(closes, errors="coerce").dropna()
    lr = np.log(s / s.shift(1)).dropna()
    return (lr.rolling(n).std() * math.sqrt(252)).dropna()


def rank_pct(hist: pd.Series | list, today: float) -> dict:
    """IV rank = (today - low) / (high - low) over the history; IV percentile = share of history days below today; both 0-100."""
    vals = np.array([v for v in (hist.values if isinstance(hist, pd.Series) else hist) if v is not None and np.isfinite(v)], dtype=float)
    if len(vals) < 2 or today is None:
        return {"rank": None, "pct": None, "days": int(len(vals))}
    lo, hi = vals.min(), vals.max()
    return {"rank": _r(100 * (today - lo) / (hi - lo), 1) if hi > lo else 50.0, "pct": _r(100 * np.mean(vals < today), 1), "days": int(len(vals))}


# ------------------------------------------------------------------ the daily store (SNAPSHOT_DIR/options/daily/<SYM>.json)
_lock = threading.RLock()
DIR: Path | None = None            # set to keep this dashboard's files elsewhere (tests, smoke runs)


def _dir() -> Path:
    return DIR or B.SNAP_DIR / SLUG


def _read(name: str, default):
    try:
        return json.loads((_dir() / name).read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, obj) -> None:
    d = _dir() / Path(name).parent
    d.mkdir(parents=True, exist_ok=True)
    tmp = _dir() / (name + ".tmp")
    tmp.write_text(json.dumps(obj, default=str, allow_nan=False, separators=(",", ":")))
    tmp.replace(_dir() / name)


def load_daily(sym: str) -> dict:
    """{trade_date: {spot, iv30, front, atm_iv, skew, pc_oi, pc_vol, rv10, rv30, exp: {exp: {...}}}}, oldest first."""
    d = _read(f"daily/{sym}.json", {})
    return dict(sorted(d.items())) if isinstance(d, dict) else {}


def save_daily(sym: str, trade_date: str, entry: dict) -> None:
    """Upsert the day's entry (the last computation of a trading day stands: the end-of-day chain)."""
    with _lock:
        d = load_daily(sym)
        d[trade_date] = entry
        _write(f"daily/{sym}.json", d)


# ------------------------------------------------------------------ one symbol
def closes(sym: str, group: str) -> pd.Series:
    """Daily closes: the AI Stocks dashboard's cached prices for its tickers (never fetched twice), Nasdaq's quote API for the others (IWM, additions)."""
    try:
        px = AI._prices()["px"]
    except Exception:
        px = {}
    if sym in px:
        return px[sym]
    return B.nasdaq_daily(sym, AI.DATA_START, lambda *a, **k: fetch_json(*a, **k), assetclass="etf" if group == "index" else "stocks")


def symbol_model(u: dict, evs: list[dict], today: date | None = None) -> dict:
    """Everything the tabs need for one symbol, from its chain (fetched or cached), its closes and its accrued daily history; saves today's entry."""
    sym, today = u["sym"], today or date.today()
    chain = parse_chain(chain_text(sym, u["cboe"]), sym)
    spot, df = chain["spot"], chain["options"]
    rows = expiry_table(chain)
    front = front_expiry(rows)
    nxt = next((r for r in rows if r["monthly"] and r["dte"] >= 5), None)
    pc = pc_ratios(df)
    gex, gex_total = gex_by_strike(df, spot)
    rv10 = rv30 = None
    rv_hist = {}
    try:
        px = closes(sym, u["group"])
        r10, r30 = realised_vol(px, 10), realised_vol(px, 30)
        rv10, rv30 = _r(r10.iloc[-1], 4) if len(r10) else None, _r(r30.iloc[-1], 4) if len(r30) else None
        rv_hist = {"rv10": _pts(r10.tail(400), 4), "rv30": _pts(r30.tail(400), 4), "close": _pts(px.tail(400), 2)}
    except Exception as e:
        rv_hist = {"error": type(e).__name__}
    entry = {"spot": _r(spot, 4), "iv30": chain["iv30"], "front": front["exp"] if front else None, "atm_iv": front["atm_iv"] if front else None,
             "skew": front["skew"] if front else None, "rr": front["rr"] if front else None, "pc_oi": pc["pc_oi"], "pc_vol": pc["pc_vol"], "oi": pc["oi"],
             "rv10": rv10, "rv30": rv30, "gex": gex_total,
             "exp": {r["exp"]: {k: r[k] for k in ("dte", "atm_iv", "put25", "call25", "skew", "pc_oi", "pc_vol", "oi", "em_straddle", "em_iv", "straddle", "max_pain")} for r in rows}}
    if chain["trade_date"]:
        try:
            save_daily(sym, chain["trade_date"], entry)
        except OSError:
            pass
    hist = load_daily(sym)
    ivs = pd.Series({pd.Timestamp(k): v["atm_iv"] for k, v in hist.items() if v.get("atm_iv")}, dtype=float).sort_index()
    rank = rank_pct(ivs.tail(252), entry["atm_iv"])
    rank["basis"] = "history"
    earn = next_earnings(sym, evs, today)
    return {"sym": sym, "name": u["name"], "group": u["group"], "both": u.get("both", False), "spot": _r(spot, 2), "iv30": chain["iv30"], "trade_date": chain["trade_date"],
            "asof": chain["asof"], "quote": chain["quote"], "front": front, "next_monthly": nxt, "expiries": rows, "pc": pc, "gex_total": gex_total, "gex": gex,
            "rv10": rv10, "rv30": rv30, "rv": rv_hist, "rank": rank, "history_days": len(hist), "unusual": unusual(df, sym, spot),
            "earnings": earn, "events": [e for e in evs if e["sym"] in (None, sym) and e["date"] >= str(today)][:12],
            "hist": {"atm_iv": _pts(ivs, 4), "skew": [[int(pd.Timestamp(k).timestamp()), v["skew"]] for k, v in hist.items() if v.get("skew") is not None],
                     "pc_oi": [[int(pd.Timestamp(k).timestamp()), v["pc_oi"]] for k, v in hist.items() if v.get("pc_oi") is not None],
                     "rv30": [[int(pd.Timestamp(k).timestamp()), v["rv30"]] for k, v in hist.items() if v.get("rv30") is not None],
                     "spot": [[int(pd.Timestamp(k).timestamp()), v["spot"]] for k, v in hist.items() if v.get("spot") is not None]},
            "daily": hist}


def chain_detail(u: dict) -> dict:
    """The Chains tab's data for one symbol: the quoted lines per expiry (strikes within 60-150% of spot), the per-expiry table, max pain and GEX by strike per expiry."""
    sym = u["sym"]
    chain = parse_chain(chain_text(sym, u["cboe"]), sym)
    spot, df = chain["spot"], chain["options"]
    rows = expiry_table(chain)
    per = {}
    for exp, g in df.groupby("exp", sort=True):
        gex, total = gex_by_strike(g, spot)
        lines = [{"k": float(r.strike), "cp": r.cp, "bid": _r(r.bid, 2), "ask": _r(r.ask, 2), "mid": _r(r.mid, 2), "last": _r(r.last, 2), "vol": _r(r.vol, 0), "oi": _r(r.oi, 0),
                  "iv": _r(r.iv, 4), "delta": _r(r.delta, 4), "gamma": _r(r.gamma, 5), "theta": _r(r.theta, 4), "vega": _r(r.vega, 4)} for r in g.itertuples()]
        per[str(exp)] = {"lines": lines, "gex": gex, "gex_total": total, "atm": atm_strike(g, spot)}
    return {"sym": sym, "name": u["name"], "spot": _r(spot, 2), "iv30": chain["iv30"], "trade_date": chain["trade_date"], "asof": chain["asof"], "quote": chain["quote"],
            "expiries": rows, "chains": per, "stale": B.stale_info([chain_url(u["cboe"])]), "updated": int(time.time()), "rate": RATE}


# ------------------------------------------------------------------ the shared model (every symbol, cached for the chain TTL)
def _cached_model():
    from ..cache import _cached
    return _cached(f"topic:{SLUG}:model", ttl_now(), _model_now)


def _model_now() -> dict:
    evs = events()
    today = date.today()
    syms, errors = {}, {}
    for u in universe():
        try:
            syms[u["sym"]] = symbol_model(u, evs, today)
        except Exception as e:
            errors[u["sym"]] = f"{type(e).__name__}: {str(e)[:80]}"
    idx = {}
    for name, url in (("vix", VIX_URL), ("vix3m", VIX3M_URL), ("vvix", VVIX_URL), ("skew", SKEW_URL)):
        try:
            idx[name] = index_history(name.upper())
        except Exception as e:
            idx[name + "_error"] = type(e).__name__
    return {"syms": syms, "errors": errors, "idx": idx, "events": evs, "universe": universe(), "today": str(today),
            "sources": [chain_url(u["cboe"]) for u in universe()] + [VIX_URL, VIX3M_URL, VVIX_URL, SKEW_URL]}


def _median(vals):
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return _r(float(np.median(v)), 2) if v else None


def _idx_series(idx: dict, name: str, years: float = 3) -> pd.Series | None:
    s = idx.get(name)
    if s is None:
        return None
    return s[s.index >= B._years_ago(years)]


def basket_now(M: dict) -> dict:
    """The AI basket's (core 13) medians today: IV rank, skew, share with front IV above 30-day realised; the index proxies' fallbacks applied."""
    S = M["syms"]
    ai = [s for s in S.values() if s["group"] in ("core", "picks")]
    core = [s for s in S.values() if s["group"] == "core"] or ai
    vix = M["idx"].get("vix")
    vix_rank = rank_pct(vix.tail(252), float(vix.iloc[-1])) if vix is not None and len(vix) > 20 else {"rank": None, "pct": None, "days": 0}
    for s in S.values():                                  # the fallback: an index proxy with thin history reads the VIX's rank and percentile
        if s["rank"]["days"] < MIN_HISTORY and s["group"] == "index" and vix_rank["rank"] is not None:
            s["rank"] = {**vix_rank, "basis": "VIX fallback", "own_days": s["rank"]["days"]}
        elif s["rank"]["days"] < MIN_HISTORY:
            s["rank"] = {**s["rank"], "basis": "thin history"}
    ranks = [s["rank"]["rank"] for s in core]
    skews = [s["front"]["skew"] for s in core if s.get("front") and s["front"].get("skew") is not None]
    vrp = [(s["front"]["atm_iv"] > s["rv30"]) for s in S.values() if s.get("front") and s["front"].get("atm_iv") and s.get("rv30")]
    thin = [s["sym"] for s in core if s["rank"].get("basis") != "history"]
    return {"iv_rank": _median(ranks), "iv_rank_n": len([r for r in ranks if r is not None]), "skew": _median(skews), "skew_n": len(skews),
            "vrp_share": _r(100 * sum(vrp) / len(vrp), 1) if vrp else None, "vrp_n": len(vrp), "vrp_above": int(sum(vrp)),
            "thin": thin, "history_days": max([s["history_days"] for s in S.values()] or [0]), "min_history": MIN_HISTORY, "vix_rank": vix_rank}


def where_line(h: dict) -> str:
    """One plain sentence on where the options are pricing the AI dip."""
    parts = []
    if h.get("vix") is not None and h.get("vix_term") is not None:
        parts.append(f"VIX is {h['vix']:.1f} with the three-month at {h['vix3m']:.1f}: the curve is " + ("inverted, the stress sign" if h["vix_term"] < 0 else "flat" if h["vix_term"] < 1.5 else "upright, calm"))
    if h.get("ai_iv_rank") is not None:
        parts.append(f"the AI basket's median IV rank is {h['ai_iv_rank']:.0f}" + (" (thin history, see the day count)" if h.get("thin") else "") +
                     (", options are pricing fear" if h["ai_iv_rank"] > 80 else ", options are cheap against their own range" if h["ai_iv_rank"] < 20 else ""))
    if h.get("vrp_share") is not None:
        parts.append(f"implied is above 30-day realised on {h['vrp_share']:.0f}% of symbols" + (": options carry a premium to the movement seen" if h["vrp_share"] >= 70 else ": the market is moving more than options priced" if h["vrp_share"] < 30 else ""))
    if h.get("ai_skew") is not None:
        parts.append(f"25-delta skew runs {h['ai_skew'] * 100:.1f} vol points for the puts")
    return ("; ".join(parts) + "." if parts else "No chain answered yet.") + " Not investment advice."


def _setup_now() -> dict:
    M = _cached_model()
    S, idx = M["syms"], M["idx"]
    vix, vix3m, skew, vvix = (idx.get(k) for k in ("vix", "vix3m", "skew", "vvix"))
    bk = basket_now(M)
    term = None
    if vix is not None and vix3m is not None:
        both = pd.concat([vix.rename("vix"), vix3m.rename("vix3m")], axis=1).dropna()
        term = (both["vix3m"] - both["vix"])
    head = {"vix": _r(vix.iloc[-1], 2) if vix is not None else None, "vix3m": _r(vix3m.iloc[-1], 2) if vix3m is not None else None,
            "vix_term": _r(term.iloc[-1], 2) if term is not None and len(term) else None, "skew_index": _r(skew.iloc[-1], 2) if skew is not None else None,
            "vvix": _r(vvix.iloc[-1], 2) if vvix is not None else None, "vix_date": str(vix.index[-1].date()) if vix is not None else None,
            "ai_iv_rank": bk["iv_rank"], "ai_skew": bk["skew"], "vrp_share": bk["vrp_share"], "thin": bool(bk["thin"]),
            "spy_pc_oi": (S.get("SPY") or {}).get("pc", {}).get("pc_oi")}
    head["where"] = where_line(head)
    table = []
    for u in M["universe"]:
        s = S.get(u["sym"])
        if not s:
            table.append({"sym": u["sym"], "name": u["name"], "group": u["group"], "error": M["errors"].get(u["sym"], "no data")})
            continue
        f, n = s.get("front") or {}, s.get("next_monthly") or {}
        table.append({"sym": s["sym"], "name": s["name"], "group": s["group"], "both": s["both"], "spot": s["spot"], "chg": _r(s["quote"].get("price_change_percent"), 2),
                      "iv30": s["iv30"], "front": f.get("exp"), "front_dte": f.get("dte"), "atm_iv": f.get("atm_iv"), "rank": s["rank"].get("rank"), "pct": s["rank"].get("pct"),
                      "rank_basis": s["rank"].get("basis"), "rank_days": s["rank"].get("own_days", s["rank"].get("days")), "em_exp": n.get("exp"), "em_dte": n.get("dte"),
                      "em_straddle": n.get("em_straddle"), "em_iv": n.get("em_iv"), "skew": f.get("skew"), "pc_oi": s["pc"]["pc_oi"], "pc_vol": s["pc"]["pc_vol"],
                      "rv30": s["rv30"], "vrp": _r(f["atm_iv"] - s["rv30"], 4) if f.get("atm_iv") and s.get("rv30") else None, "gex_total": s["gex_total"],
                      "earnings": (s["earnings"] or {}).get("date"), "earnings_verify": (s["earnings"] or {}).get("verify"), "trade_date": s["trade_date"], "history_days": s["history_days"]})
    # the basket's history for the head's followHead: median IV rank is only as long as the accrued history; the VIX lines run years
    def basket_hist(key, rank=False):
        frames = [pd.Series({t: v for t, v in (_rank_hist(s["hist"][key]) if rank else s["hist"][key])}) for s in S.values() if s["group"] == "core" and s["hist"].get(key)]
        frames = [f for f in frames if len(f)]
        if not frames:
            return []
        df = pd.concat(frames, axis=1)
        return [[int(t), _r(v, 4)] for t, v in df.median(axis=1).dropna().items()]
    vrp_hist = []
    days = sorted({d for s in S.values() for d in s["daily"]})
    for d in days:
        vals = [(s["daily"][d]["atm_iv"] > s["daily"][d]["rv30"]) for s in S.values() if d in s["daily"] and s["daily"][d].get("atm_iv") and s["daily"][d].get("rv30")]
        if vals:
            vrp_hist.append([int(pd.Timestamp(d).timestamp()), _r(100 * sum(vals) / len(vals), 1)])
    out = payload({"head": lambda: head, "table": lambda: table, "basket": lambda: bk,
                   "vix": lambda: _pts(_idx_series(idx, "vix", 3), 2) if vix is not None else None,
                   "vix3m": lambda: _pts(_idx_series(idx, "vix3m", 3), 2) if vix3m is not None else None,
                   "vix_term": lambda: _pts(term[term.index >= B._years_ago(3)], 2) if term is not None else None,
                   "skew_index": lambda: _pts(_idx_series(idx, "skew", 3), 2) if skew is not None else None,
                   "vvix": lambda: _pts(_idx_series(idx, "vvix", 3), 2) if vvix is not None else None,
                   "ai_iv_hist": lambda: basket_hist("atm_iv"), "ai_rank_hist": lambda: basket_hist("atm_iv", rank=True), "ai_skew_hist": lambda: basket_hist("skew"), "vrp_hist": lambda: vrp_hist,
                   "events": lambda: M["events"][:20]},
                  sources=M["sources"], as_of=max([s["trade_date"] for s in S.values() if s["trade_date"]] or [head["vix_date"]]))
    out["errors"] = M["errors"]
    out["index_errors"] = {k: v for k, v in idx.items() if k.endswith("_error")}
    out["delayed"] = "Cboe delayed quotes (15 minutes); outside market hours the last session's."
    return out


def _chains_now() -> dict:
    M = _cached_model()
    S = M["syms"]
    return payload({"symbols": lambda: [{"sym": u["sym"], "name": u["name"], "group": u["group"], "spot": (S.get(u["sym"]) or {}).get("spot"),
                                          "expiries": [{"exp": r["exp"], "dte": r["dte"], "monthly": r["monthly"]} for r in (S.get(u["sym"]) or {}).get("expiries", [])],
                                          "error": M["errors"].get(u["sym"])} for u in M["universe"]],
                    "default": lambda: next((s for s in ("NVDA", "SPY") if s in S), next(iter(S), None)), "rate": lambda: RATE},
                   sources=M["sources"], as_of=M["today"])


def _vol_now() -> dict:
    M = _cached_model()
    S, idx = M["syms"], M["idx"]
    per = {}
    for sym, s in S.items():
        wk = None                                  # the term structure a week ago, from the daily store
        for d in reversed(list(s["daily"])):
            if (pd.Timestamp(M["today"]) - pd.Timestamp(d)).days >= 6:
                wk = {"date": d, "points": [[v["dte"], v["atm_iv"]] for v in s["daily"][d]["exp"].values() if v.get("atm_iv")]}
                break
        per[sym] = {"name": s["name"], "group": s["group"], "spot": s["spot"], "iv30": s["iv30"], "rank": s["rank"], "history_days": s["history_days"], "rv10": s["rv10"], "rv30": s["rv30"],
                    "front": s["front"], "term": [[r["dte"], r["atm_iv"], r["exp"], r["monthly"]] for r in s["expiries"] if r["atm_iv"]], "term_week_ago": wk,
                    "iv_hist": s["hist"]["atm_iv"], "rv30_hist": s["rv"].get("rv30") or s["hist"]["rv30"], "rv10_hist": s["rv"].get("rv10"),
                    "rank_hist": _rank_hist(s["hist"]["atm_iv"])}
    bk = basket_now(M)
    return payload({"symbols": lambda: per, "basket": lambda: bk, "order": lambda: [u["sym"] for u in M["universe"]],
                    "vix": lambda: _pts(_idx_series(idx, "vix", 3), 2) if idx.get("vix") is not None else None,
                    "vix3m": lambda: _pts(_idx_series(idx, "vix3m", 3), 2) if idx.get("vix3m") is not None else None,
                    "vvix": lambda: _pts(_idx_series(idx, "vvix", 3), 2) if idx.get("vvix") is not None else None,
                    "skew_index": lambda: _pts(_idx_series(idx, "skew", 3), 2) if idx.get("skew") is not None else None},
                   sources=M["sources"], as_of=M["today"])


def _rank_hist(iv_pts: list) -> list:
    """IV rank day by day over the accrued history (each day against the year before it)."""
    out = []
    for i, (t, v) in enumerate(iv_pts):
        prior = [x for _, x in iv_pts[max(0, i - 252):i + 1]]
        if len(prior) >= 2:
            lo, hi = min(prior), max(prior)
            out.append([t, _r(100 * (v - lo) / (hi - lo), 1) if hi > lo else 50.0])
    return out


def _skew_now() -> dict:
    M = _cached_model()
    S, idx = M["syms"], M["idx"]
    bk = basket_now(M)
    skew_idx = idx.get("skew")
    sk_rank = rank_pct(skew_idx.tail(252), float(skew_idx.iloc[-1])) if skew_idx is not None and len(skew_idx) > 20 else None
    per = {}
    for sym, s in S.items():
        nxt = s.get("next_monthly") or s.get("front") or {}
        oi = []
        if nxt.get("exp"):
            # OI by strike for the next monthly: from the chain detail's lines (recomputed cheaply from the cached text)
            try:
                ch = parse_chain(chain_text(sym, next(u["cboe"] for u in M["universe"] if u["sym"] == sym)), sym)
                g = ch["options"][ch["options"]["exp"].astype(str) == nxt["exp"]]
                by = g.groupby(["strike", "cp"])["oi"].sum().unstack(fill_value=0)
                oi = [[float(k), _r(row.get("C", 0), 0), _r(row.get("P", 0), 0)] for k, row in by.iterrows()]
            except Exception:
                oi = []
        per[sym] = {"name": s["name"], "group": s["group"], "spot": s["spot"], "front": s["front"], "next_monthly": nxt, "pc": s["pc"], "skew_hist": s["hist"]["skew"],
                    "pc_oi_hist": s["hist"]["pc_oi"], "oi_by_strike": oi, "skew_term": [[r["dte"], r["skew"], r["exp"]] for r in s["expiries"] if r["skew"] is not None],
                    "history_days": s["history_days"], "gex_total": s["gex_total"]}
    unusual_rows = sorted([x for s in S.values() for x in s["unusual"]], key=lambda x: -x["ratio"])[:60]
    sk_hist = [pd.Series({t: v for t, v in s["hist"]["skew"]}) for s in S.values() if s["group"] == "core" and s["hist"].get("skew")]
    med = pd.concat(sk_hist, axis=1).median(axis=1).dropna() if sk_hist else pd.Series(dtype=float)
    own = rank_pct(med.tail(252), float(med.iloc[-1])) if len(med) >= 2 else {"rank": None, "pct": None, "days": int(len(med))}
    return payload({"symbols": lambda: per, "order": lambda: [u["sym"] for u in M["universe"]], "basket": lambda: {**bk, "skew_pct_own": own, "skew_index_rank": sk_rank},
                    "unusual": lambda: unusual_rows, "ai_skew_hist": lambda: [[int(t), _r(v, 4)] for t, v in med.items()],
                    "skew_index": lambda: _pts(_idx_series(idx, "skew", 3), 2) if skew_idx is not None else None,
                    "thresholds": lambda: {"ratio": UNUSUAL_RATIO, "volume": UNUSUAL_VOLUME}},
                   sources=M["sources"], as_of=M["today"])


def past_moves(s: dict, today: str) -> list[dict]:
    """Expected vs realised: for each (snapshot day, expiry) with the expiry past and a close on both days: the IV expected move that day against the move seen."""
    spots = {d: v["spot"] for d, v in s["daily"].items() if v.get("spot")}
    close = {str(pd.Timestamp(t, unit="s").date()): v for t, v in (s["rv"].get("close") or [])}
    out = []
    for d, v in s["daily"].items():
        for exp, e in (v.get("exp") or {}).items():
            if exp <= today and e.get("em_iv") and d in spots:
                end = spots.get(exp) or close.get(exp)        # the store's own spot on the expiry day first (same feed), else the close
                if end is None:                    # the expiry fell on a holiday or a day with no close: the nearest close before it
                    before = [k for k in close if k <= exp]
                    end = close[max(before)] if before else None
                if end is None:
                    continue
                real = end / spots[d] - 1
                out.append({"date": d, "exp": exp, "dte": e["dte"], "spot": spots[d], "end": _r(end, 2), "em_iv": e["em_iv"], "em_straddle": e.get("em_straddle"),
                            "realised": _r(real, 4), "inside": abs(real) <= e["em_iv"]})
    return sorted(out, key=lambda x: (x["exp"], x["date"]), reverse=True)


def _moves_now() -> dict:
    M = _cached_model()
    S = M["syms"]
    per = {}
    for sym, s in S.items():
        cone = [{"exp": r["exp"], "dte": r["dte"], "monthly": r["monthly"], "em_iv": r["em_iv"], "em_straddle": r["em_straddle"], "straddle": r["straddle"], "atm_iv": r["atm_iv"]}
                for r in s["expiries"] if r["em_iv"]]
        past = past_moves(s, M["today"])
        per[sym] = {"name": s["name"], "group": s["group"], "spot": s["spot"], "trade_date": s["trade_date"], "cone": cone, "events": s["events"], "earnings": s["earnings"],
                    "past": past[:40], "past_n": len(past), "past_inside": _r(100 * sum(p["inside"] for p in past) / len(past), 0) if past else None,
                    "spot_hist": s["rv"].get("close") or s["hist"]["spot"]}
    return payload({"symbols": lambda: per, "order": lambda: [u["sym"] for u in M["universe"]], "events": lambda: M["events"]}, sources=M["sources"], as_of=M["today"])


def _lab_now() -> dict:
    M = _cached_model()
    S = M["syms"]
    return payload({"symbols": lambda: [{"sym": u["sym"], "name": u["name"], "group": u["group"], "spot": (S.get(u["sym"]) or {}).get("spot"),
                                          "expiries": [{"exp": r["exp"], "dte": r["dte"], "monthly": r["monthly"], "atm_iv": r["atm_iv"]} for r in (S.get(u["sym"]) or {}).get("expiries", [])]}
                                         for u in M["universe"] if u["sym"] in S],
                    "default": lambda: next((s for s in ("NVDA", "SPY") if s in S), next(iter(S), None)), "rate": lambda: RATE,
                    "structures": lambda: ["long_call", "long_put", "bull_call", "bear_put", "straddle", "strangle", "iron_condor", "covered_call", "csp"]},
                   sources=M["sources"], as_of=M["today"])


def _chain_ep(u: dict):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:chain:{u['sym']}", ttl_now(), lambda: chain_detail(u))


# ------------------------------------------------------------------ readings and signals (cached payloads only)
def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


def READINGS() -> list[dict]:
    """Headline figures per tab from the cached payloads. lean +1 = calmer pricing, -1 = stress."""
    out = []

    def add(tab, key, label, value, lean, note):
        if value is not None:
            out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": lean, "note": note})
    s = _cached_payload("setup")
    h = s.get("head") or {}
    if h.get("vix_term") is not None:
        add("setup", "vix_term", "VIX term structure: VIX3M minus VIX (points)", h["vix_term"], -1 if h["vix_term"] < 0 else 1 if h["vix_term"] > 2 else 0,
            "-1 when inverted (the three-month below spot VIX, a stress sign), +1 when upright by more than 2 points")
    if h.get("ai_iv_rank") is not None:
        add("setup", "ai_iv_rank", "AI basket median IV rank (0-100)", h["ai_iv_rank"], -1 if h["ai_iv_rank"] > 80 else 1 if h["ai_iv_rank"] < 20 else 0,
            "-1 above 80 (options pricing fear), +1 below 20 (cheap against their own range)" + ("; thin history" if h.get("thin") else ""))
    if h.get("vrp_share") is not None:
        add("vol", "vrp_share", "Share of symbols with front-month IV above 30-day realised (%)", h["vrp_share"], -1 if h["vrp_share"] < 30 else 1 if h["vrp_share"] > 70 else 0,
            "-1 below 30% (the market moving more than options priced), +1 above 70% (a volatility premium is being paid)")
    if h.get("ai_skew") is not None:
        add("skew", "ai_skew", "AI basket median 25-delta skew, front month (vol points)", _r(100 * h["ai_skew"], 1), -1 if h["ai_skew"] > 0.08 else 1 if h["ai_skew"] < 0.02 else 0,
            "-1 above 8 points (puts rich), +1 below 2 points")
    if h.get("spy_pc_oi") is not None:
        add("chains", "spy_pc_oi", "SPY put/call open-interest ratio", h["spy_pc_oi"], -1 if h["spy_pc_oi"] > 2 else 1 if h["spy_pc_oi"] < 1.2 else 0, "-1 above 2.0 (heavy put positioning), +1 below 1.2")
    row = next((r for r in s.get("table") or [] if r.get("sym") == "SPY" and r.get("em_iv")), None)
    if row:
        add("moves", "spy_em", "SPY expected move to the next monthly expiry (%)", _r(100 * row["em_iv"], 2), 0, "context: spot x IV x sqrt(T), one standard deviation")
    return out


def SIGNALS() -> list[dict]:
    """The proposed watch points (data/signals/watchlist.json, "options", proposed 8 Nov 2026, awaiting the owner's approval), from cached payloads only."""
    out = []

    def add(key, tab, label, value, unit, lean, watch, crossed, note=None):
        out.append({"key": key, "tab": tab, "label": label, "value": value, "unit": unit, "lean": lean, "watch": watch, "crossed": bool(crossed), **({"note": note} if note else {})})
    s = _cached_payload("setup")
    h, bk = s.get("head") or {}, s.get("basket") or {}
    if h.get("vix_term") is not None:
        t = h["vix_term"]
        add("vix_term", "setup", "VIX term structure: VIX3M minus VIX", t, " pts", -1 if t < 0 else 1 if t > 2 else 0, "below 0 (inverted) or above +5", t < 0 or t > 5,
            f"VIX {h.get('vix')}, VIX3M {h.get('vix3m')}" + (": inverted, the stress sign" if t < 0 else ": steep, a calm market paying up for later cover" if t > 5 else ""))
    if h.get("ai_iv_rank") is not None:
        v = h["ai_iv_rank"]
        add("ai_iv_rank", "setup", "AI basket median IV rank", v, "", -1 if v > 80 else 1 if v < 20 else 0, "above 80 or below 20", v > 80 or v < 20,
            (f"thin history ({bk.get('history_days', 0)} of {MIN_HISTORY} days): " if h.get("thin") else "") + f"median of {bk.get('iv_rank_n', 0)} core stocks")
    sk = _cached_payload("skew").get("basket") or {}
    if h.get("ai_skew") is not None:
        v = _r(100 * h["ai_skew"], 1)
        own, idx = sk.get("skew_pct_own") or {}, sk.get("skew_index_rank") or {}
        if own.get("days", 0) >= MIN_HISTORY and own.get("pct") is not None:
            crossed, basis = own["pct"] > 90 or own["pct"] < 10, f"own history {own['days']} days, percentile {own['pct']}"
        elif idx.get("pct") is not None:
            crossed, basis = idx["pct"] > 90 or idx["pct"] < 10, f"fallback until {MIN_HISTORY} days of own history: Cboe SKEW index percentile {idx['pct']} (1 year)"
        else:
            crossed, basis = False, "no percentile yet"
        add("skew_ai", "skew", "AI basket median 25-delta skew (put IV minus call IV)", v, " pts", -1 if v > 8 else 1 if v < 2 else 0,
            "above the 90th or below the 10th percentile of its history (SKEW index fallback until 60 days)", crossed, basis)
    if h.get("vrp_share") is not None:
        v = h["vrp_share"]
        add("vrp", "vol", "Share of symbols with front-month IV above 30-day realised", v, "%", -1 if v < 30 else 1 if v > 70 else 0, "below 30% or above 90%", v < 30 or v > 90,
            f"{bk.get('vrp_above', 0)} of {bk.get('vrp_n', 0)} symbols")
    if h.get("spy_pc_oi") is not None:
        v = h["spy_pc_oi"]
        add("pc_oi", "chains", "SPY put/call open-interest ratio", v, "", -1 if v > 2 else 1 if v < 1.2 else 0, "above 2.0 or below 1.0", v > 2 or v < 1,
            "all listed SPY expiries within 400 days, strikes 60-150% of spot")
    return out


# ------------------------------------------------------------------ endpoints
def _cached_ep(name, fn):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl_now(), fn)


ENDPOINTS = {"setup": _cached_ep("setup", _setup_now), "chains": _cached_ep("chains", _chains_now), "vol": _cached_ep("vol", _vol_now),
             "skew": _cached_ep("skew", _skew_now), "moves": _cached_ep("moves", _moves_now), "lab": _cached_ep("lab", _lab_now)}
for _u in universe():
    ENDPOINTS[f"chain-{_u['sym']}"] = _chain_ep(_u)
