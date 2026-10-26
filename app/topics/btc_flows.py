"""ETF and Strategy (MSTR) tabs of /btc-cycles: who is buying the bitcoin, from the first US spot ETF day to now.

etf   US spot BTC ETFs since 11 Jan 2024: daily net flows by issuer (Farside, US$ millions, HTML table), total daily flows in BTC
      (bitbo, the trading bot's proven parser) as a cross-check and fallback; cumulative flows, 30-day flows, flows vs BTC price.
      Hong Kong spot ETFs (since 30 Apr 2024) and UK ETNs (retail since 8 Oct 2025): holdings hand-entered with sources
      (data/btc-cycles/etf_holdings.csv). Milestones: data/btc-cycles/etf_milestones.csv.
mstr  Strategy Inc.: BTC held and share counts from a public dataset built from its SEC filings (the same one the trading bot uses),
      MSTR and BTC daily closes from Yahoo; every purchase (change in holdings), approximate cost basis, BTC per 1,000 shares, mNAV,
      90-day correlation and beta of daily returns. UK and HK treasury companies: data/btc-cycles/treasuries.csv + prices
      from Yahoo, else CNBC (Yahoo answers 429 to cloud servers), else holdings only.
"""
from __future__ import annotations

import csv
import json
import re
import time
from html.parser import HTMLParser

import numpy as np
import pandas as pd

from ..cache import _cached
from ..config import DATA_DIR
from ._base import DAY, _pts, _r, fetch, fetch_json, manual, manual_rows, payload, stale_info

SLUG = "btc-cycles"
FARSIDE = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
BITBO = "https://bitbo.io/treasuries/etf-flows/"
MSTR_HISTORY = "https://raw.githubusercontent.com/jefferych1/mstr-nav-tracker/main/data/history.json"
LAUNCH = pd.Timestamp("2024-01-11")
ISSUERS = {"IBIT": "BlackRock", "FBTC": "Fidelity", "GBTC": "Grayscale", "BTC": "Grayscale Mini", "BITB": "Bitwise", "ARKB": "ARK 21Shares",
           "HODL": "VanEck", "BRRR": "Valkyrie / CoinShares", "EZBC": "Franklin", "BTCO": "Invesco Galaxy", "BTCW": "WisdomTree", "MSBT": "Morgan Stanley"}
TTL = DAY


def yahoo_daily(sym: str, start: str = "2020-01-01") -> pd.Series:
    from ._base import yahoo_daily as yd
    return yd(sym, start, lambda *a, **k: fetch_json(*a, **k))      # looked up at call time, so a test can replace fetch_json here


# London and Hong Kong closes when Yahoo refuses the server (429): CNBC's chart bars, symbol derived from the Yahoo ticker
# (SWC.L -> SWC-GB, 0434.HK -> 434-HK). CNBC writes HK codes without the leading zero (0434-HK answers with no bars), so that form
# goes first. Stooq was tried and dropped: it answers Railway with an HTML page, not its CSV (Oct 2026).
CNBC_BARS = "https://ts-api.cnbc.com/harmony/app/bars/{sym}/1D/{a}000000/{b}000000/adjusted/EST5EDT.json"
_SUFFIX = {"L": "GB", "HK": "HK"}


def alt_symbols(yahoo: str) -> list[str]:
    """CNBC symbols to try after Yahoo, e.g. SWC.L -> ["SWC-GB"], 0434.HK -> ["434-HK", "0434-HK"]."""
    code, _, exch = yahoo.upper().rpartition(".")
    if exch not in _SUFFIX:
        return []
    codes = list(dict.fromkeys([code.lstrip("0") or code, code])) if exch == "HK" else [code]
    return [f"{c}-{_SUFFIX[exch]}" for c in codes]


def parse_cnbc(j: dict) -> pd.Series:
    bars = ((j or {}).get("barData") or {}).get("priceBars") or []
    s = pd.Series({pd.to_datetime(int(b["tradeTimeinMills"]), unit="ms").normalize(): float(b["close"]) for b in bars if b.get("close") not in (None, "")})
    return s[~s.index.duplicated(keep="last")].sort_index()


def stock_daily(yahoo: str, start: str = "2024-01-01") -> tuple[pd.Series, str, list[str]]:
    """(closes, source name, what failed) for a listed stock: Yahoo (with Nasdaq for US tickers), then CNBC."""
    tried = []
    try:
        return yahoo_daily(yahoo, start), "Yahoo" if "." in yahoo else "Yahoo / Nasdaq", tried
    except Exception as e:
        tried.append(f"Yahoo {yahoo}: {type(e).__name__}: {str(e)[:100]}")
    a, b = pd.Timestamp(start), pd.Timestamp.now()
    for sym in alt_symbols(yahoo):
        try:
            s = parse_cnbc(fetch_json(CNBC_BARS.format(sym=sym, a=a.strftime("%Y%m%d"), b=b.strftime("%Y%m%d")), TTL, min_bytes=20))
            if len(s) < 20:
                raise ValueError(f"{len(s)} rows")
            return s, "CNBC", tried
        except Exception as e:
            tried.append(f"CNBC {sym}: {type(e).__name__}: {str(e)[:100]}")
    raise LookupError("; ".join(tried))


# ------------------------------------------------------------------ ETF flows
class _Table(HTMLParser):
    """Rows of the first <table class="etf"> (or the first table) as lists of cell text."""
    def __init__(self):
        super().__init__(); self.rows, self._row, self._cell, self._in, self._depth, self._done = [], None, None, False, 0, False

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        if tag == "table":
            self._depth += 1
            self._in = True
        elif self._in and tag == "tr":
            self._row = []
        elif self._in and tag in ("td", "th") and self._row is not None:
            self._cell = ""

    def handle_endtag(self, tag):
        if self._done:
            return
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", self._cell).strip()); self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table" and self._in:
            self._depth -= 1
            if self._depth == 0 and len(self.rows) > 20:
                self._done = True
            elif self._depth == 0:
                self.rows, self._in = [], False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell += data


def _num(x: str):
    x = x.replace(",", "").strip()
    if x in ("", "-", "–", "—"):
        return 0.0
    neg = x.startswith("(") and x.endswith(")")
    try:
        v = float(x.strip("()"))
    except ValueError:
        return None
    return -v if neg else v


def parse_farside(html: str) -> pd.DataFrame:
    """Farside's all-data page -> daily net flow per issuer in US$ millions (columns = tickers), one row per trading day."""
    t = _Table(); t.feed(html)
    rows = t.rows
    head_i = next((i for i, r in enumerate(rows) if sum(c.upper() in ISSUERS for c in r) >= 5), None)
    if head_i is None:
        raise ValueError("Farside layout changed: no header row with issuer tickers")
    head = [c.upper() for c in rows[head_i]]
    data = {}
    for r in rows[head_i + 1:]:
        if not r:
            continue
        d = pd.to_datetime(r[0], format="%d %b %Y", errors="coerce")
        if pd.isna(d):
            continue
        data[d] = {h: _num(v) for h, v in zip(head[1:], r[1:]) if h in ISSUERS}
    df = pd.DataFrame.from_dict(data, orient="index").sort_index()
    if len(df) < 50:
        raise ValueError(f"Farside layout changed ({len(df)} days parsed)")
    return df


def parse_bitbo(page: str) -> pd.Series:
    """Ported from the trading bot: daily total US spot ETF flows in BTC from bitbo's chart data."""
    i = page.find("historyBtc"); j = page.find("mergedHistoryBtc", i)
    rows = re.findall(r"getPreviousBusinessDay\((\d+)\),\s*truncate\(([-\d.eE]+),\s*2\)", page[i:j] if i >= 0 and j > i else "")
    if len(rows) < 100:
        raise ValueError(f"bitbo ETF page format changed ({len(rows)} rows found)")
    s = pd.Series([float(v) for _, v in rows], index=pd.to_datetime([int(t) for t, _ in rows], unit="ms").normalize())
    return s.groupby(level=0).sum().sort_index()


def farside() -> pd.DataFrame:
    return parse_farside(fetch(FARSIDE, TTL, curl=True, min_bytes=5000))


def bitbo() -> pd.Series:
    return parse_bitbo(fetch(BITBO, TTL, min_bytes=5000))


def _rows(name: str) -> list[dict]:
    f = DATA_DIR / SLUG / f"{name}.csv"
    if not f.exists():
        return []
    with f.open(newline="", encoding="utf-8") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(fh) if (r.get("date") or "").strip() and not r["date"].startswith("#")]


def _etf_now() -> dict:
    from .btc_cycles import price
    out: dict = {"issuers": ISSUERS, "milestones": sorted(_rows("etf_milestones"), key=lambda r: r["date"]), "stale": {}, "updated": int(time.time())}
    try:
        fs = farside()
        total = fs.sum(axis=1)
        top = list(fs.sum().sort_values(ascending=False).index[:7])
        cum = fs.cumsum()
        out["daily_usd_m"] = _pts(total, 1)
        out["cum_usd_m"] = _pts(total.cumsum(), 1)
        out["roll30_usd_m"] = _pts(total.rolling(30).sum().dropna(), 1)
        out["cum_by_issuer"] = {k: _pts(cum[k], 1) for k in top}
        if len(fs.columns) > len(top):
            out["cum_by_issuer"]["Others"] = _pts(cum[[c for c in fs.columns if c not in top]].sum(axis=1), 1)
        last30 = fs.iloc[-21:].sum()                                    # about 30 calendar days of trading
        out["table"] = sorted([{"ticker": k, "issuer": ISSUERS.get(k, k), "since_launch": _r(fs[k].sum(), 1), "last_30d": _r(last30[k], 1),
                                "last_day": _r(fs[k].iloc[-1], 1), "best_day": _r(fs[k].max(), 1), "worst_day": _r(fs[k].min(), 1)} for k in fs.columns],
                              key=lambda r: -(r["since_launch"] or 0))
        streak, sign = 0, np.sign(total.iloc[-1])
        for v in total.iloc[::-1]:
            if np.sign(v) == sign and v != 0:
                streak += 1
            else:
                break
        out["kpi"] = {"since_launch_usd_m": _r(total.sum(), 0), "last_30d_usd_m": _r(total.iloc[-21:].sum(), 0), "last_day_usd_m": _r(total.iloc[-1], 1),
                      "last_day": str(total.index[-1].date()), "streak": int(streak * sign), "best_day_usd_m": _r(total.max(), 0),
                      "best_day": str(total.idxmax().date()), "worst_day_usd_m": _r(total.min(), 0), "worst_day": str(total.idxmin().date()),
                      "ibit_share": _r(fs["IBIT"].sum() / total.sum(), 4) if "IBIT" in fs and total.sum() else None}
        out["as_of"] = str(total.index[-1].date())
    except Exception as e:
        out["farside_error"] = type(e).__name__
    try:
        b = bitbo()
        b = b[b.index >= LAUNCH - pd.Timedelta(days=3)]
        out["daily_btc"] = _pts(b, 1)
        out["cum_btc"] = _pts(b.cumsum(), 0)
        out.setdefault("kpi", {})["since_launch_btc"] = _r(b.sum(), 0)
        out["as_of"] = out.get("as_of") or str(b.index[-1].date())
    except Exception as e:
        out["bitbo_error"] = type(e).__name__
    try:
        px = price()
        out["btc_price"] = _pts(px[px.index >= LAUNCH - pd.Timedelta(days=30)], 0)
    except Exception as e:
        out["btc_price_error"] = type(e).__name__
    hold = manual(SLUG, "etf_holdings")
    out["intl"] = {k: _pts(v, 0) for k, v in (hold.items() if isinstance(hold, dict) else [])}
    out["intl_rows"] = sorted(_rows("etf_holdings"), key=lambda r: r["date"], reverse=True)
    out["stale"] = stale_info([FARSIDE, BITBO])
    return out


# ------------------------------------------------------------------ Strategy (MSTR)
def mstr_history() -> pd.DataFrame:
    j = fetch_json(MSTR_HISTORY, TTL, min_bytes=1000)
    pts = pd.DataFrame(j["points"])
    pts["date"] = pd.to_datetime(pts["d"]).dt.normalize()
    return pts.drop_duplicates("date", keep="last").set_index("date").sort_index()


def corr_beta(a: pd.Series, b: pd.Series, n: int = 90) -> tuple[pd.Series, pd.Series]:
    r = pd.concat([np.log(a).diff(), np.log(b).diff()], axis=1, join="inner").dropna()
    r.columns = ["a", "b"]
    corr = r["a"].rolling(n).corr(r["b"])
    beta = r["a"].rolling(n).cov(r["b"]) / r["b"].rolling(n).var()
    return corr.dropna(), beta.dropna()


# ------------------------------------------------------------------ mNAV strategies and the exit window
HALVINGS = pd.to_datetime(["2016-07-09", "2020-05-11", "2024-04-20", "2028-04-15"])      # the 2028 date is the usual block-time estimate


def _weekly(mstr: pd.Series, btc: pd.Series, hold: pd.Series, shares: pd.Series) -> pd.DataFrame:
    w = pd.DataFrame({"mstr": mstr, "btc": btc, "hold": hold, "shares": shares}).resample("W-FRI").last().dropna()
    w["mnav"] = w.mstr * w.shares / (w.btc * w.hold)
    w["bps"] = w.hold / w.shares
    w["trend"] = (w.btc > w.btc.rolling(40, min_periods=30).mean()).astype(float)      # 40 weeks ~ the 200-day average
    w["divergence"] = (w.mstr >= 0.9 * w.mstr.rolling(52, min_periods=26).max()) & (w.mnav <= 0.7 * w.mnav.rolling(52, min_periods=26).max())
    return w


def backtest(w: pd.DataFrame, in_mstr: pd.Series, in_btc: pd.Series, cost: float = 0.002) -> dict:
    """Weekly: the position chosen at a week's close earns the next week's return; `cost` per full switch."""
    pm, pb = in_mstr.shift(1).fillna(0), in_btc.shift(1).fillna(0)
    r = pm * w.mstr.pct_change().fillna(0) + pb * w.btc.pct_change().fillna(0) - (pm.diff().abs() + pb.diff().abs()).fillna(0) * cost / 2
    eq = (1 + r).cumprod()
    yrs = (w.index[-1] - w.index[0]).days / 365.25
    return {"multiple": _r(float(eq.iloc[-1]), 2), "cagr": _r(float(eq.iloc[-1] ** (1 / yrs) - 1), 3), "max_dd": _r(float((eq / eq.cummax() - 1).min()), 3),
            "in_mstr": _r(float(pm.mean()), 2), "switches": int((pm.diff().abs() > 0).sum()), "equity": _pts(eq, 3)}


def _hysteresis(out_when: pd.Series, back_when: pd.Series) -> pd.Series:
    st, s = 1.0, []
    for o, b in zip(out_when, back_when):
        st = 0.0 if o else 1.0 if b else st
        s.append(st)
    return pd.Series(s, index=out_when.index)


def mnav_strategies(mstr: pd.Series, btc: pd.Series, hold: pd.Series, shares: pd.Series, h: pd.DataFrame) -> dict:
    """Exit checklist on today's data, rule backtests since 2021, and the halving-clock windows. Thresholds come from published practice
    (2.5x where short sellers and Strategy's old issuance tiers sat, 1.2-1.3x where Chanos covered), not from fitting this history."""
    w = _weekly(mstr, btc, hold, shares)
    w = w[w.index >= "2021-01-01"]                       # before 2021 the premium also priced the software business
    one, zero = pd.Series(1.0, index=w.index), pd.Series(0.0, index=w.index)
    band = _hysteresis(w.mnav > 2.5, w.mnav < 1.25)
    div = _hysteresis(w.divergence, w.mnav < 1.25)
    rules = [("Hold MSTR", "Buy and hold MSTR.", one, zero), ("Hold BTC", "Buy and hold BTC.", zero, one),
             ("MSTR + BTC trend", "MSTR while BTC is above its 40-week average, else cash.", w.trend, zero),
             ("mNAV band", "MSTR; switch to BTC when mNAV goes above 2.5x, back to MSTR below 1.25x.", band, 1 - band),
             ("Band + trend", "The mNAV band, and cash while BTC is below its 40-week average.", band * w.trend, (1 - band) * w.trend),
             ("Divergence + trend", "Leave MSTR on a premium divergence (checklist), back below 1.25x; cash while BTC is below its 40-week average.", div * w.trend, zero)]
    tests = [{"rule": n, "how": how, **backtest(w, m, b)} for n, how, m, b in rules]
    last = w.iloc[-1]
    hi52, mh52 = w.mstr.tail(52).max(), w.mnav.tail(52).max()
    bps_yoy = float(last.bps / w.bps.iloc[-53] - 1) if len(w) > 53 else None
    ma40 = float(w.btc.rolling(40).mean().iloc[-1])
    nxt = HALVINGS[HALVINGS > w.index[-1]].min()
    prev = HALVINGS[HALVINGS <= w.index[-1]].max()
    months = (w.index[-1] - prev).days / 30.44
    m_add = lambda t, k: (t + pd.DateOffset(months=k)).strftime("%b %Y")
    in_top_window = 13 <= months <= 19
    check = [
        {"rule": "Premium extreme", "test": "basic mNAV at or above 2.5x", "now": f"{last.mnav:.2f}x", "state": "exit" if last.mnav >= 2.5 else "clear",
         "why": "Where Kerrisdale and Chanos shorted MSTR against BTC, and where Strategy's 2025 guidance started to issue stock to buy BTC."},
        {"rule": "Premium divergence", "test": "MSTR within 10% of its 52-week high while mNAV is 30% or more below its own 52-week high",
         "now": f"MSTR {last.mstr / hi52 - 1:+.0%} from its high; mNAV {last.mnav / mh52 - 1:+.0%} from its high", "state": "exit" if last.divergence else "clear",
         "why": "The premium peaked before the price in both cycles (Feb 2021 vs Nov 2021; Nov 2024 vs Jul 2025). This fired only in 2025 (Jan, May-Aug), before MSTR fell 59% in 26 weeks."},
        {"rule": "BTC trend", "test": "BTC below its 40-week (about 200-day) average", "now": f"BTC ${last.btc:,.0f} vs ${ma40:,.0f}", "state": "exit" if last.btc < ma40 else "clear",
         "why": "The one rule that held up in every test: it roughly halved MSTR's worst drawdown in 2021-26 and out of sample in 2024-26."},
        {"rule": "Accretion floor", "test": "basic mNAV below 1.0x", "now": f"{last.mnav:.2f}x", "state": "caution" if last.mnav < 1 else "clear",
         "why": "Below 1x a new share buys less than a share's worth of BTC, so the flywheel stops; Strategy has funded dividends by selling BTC and buying back its preferreds instead."},
        {"rule": "BTC per share", "test": "BTC per basic share lower than a year ago", "now": "–" if bps_yoy is None else f"{bps_yoy:+.1%} over 52 weeks",
         "state": "caution" if bps_yoy is not None and bps_yoy < 0 else "clear",
         "why": "Negative BTC Yield means dilution is outrunning buying; TD Cowen calls it dilution drag."},
        {"rule": "Halving clock", "test": "13-19 months after a halving (MSTR's price tops: 18 months in 2021, 15 in 2025)", "now": f"{months:.0f} months after the {prev:%b %Y} halving",
         "state": "watch" if in_top_window else "clear",
         "why": f"Two cycles only. Next halving about {nxt:%b %Y}: mNAV peaked 7-9 months after (window {m_add(nxt, 7)}-{m_add(nxt, 9)}), MSTR's price 15-18 months after ({m_add(nxt, 15)}-{m_add(nxt, 18)})."},
    ]
    measures = {"basic": _r(float(last.mnav), 3)}
    if "dil" in h:
        d = h["dil"].astype(float).dropna()
        if len(d):
            measures["diluted"] = _r(float(last.mstr * d.iloc[-1] / (last.btc * last.hold)), 3)
    ev = h.dropna(subset=[c for c in ("debt", "pref", "cash", "dil") if c in h]) if {"debt", "pref", "cash", "dil"} <= set(h.columns) else h.iloc[0:0]
    if len(ev):
        e = ev.iloc[-1]
        measures["ev"] = _r(float((last.mstr * float(e.dil) + float(e.debt) + float(e.pref) - float(e.cash)) / (last.btc * last.hold)), 3)
        measures["ev_inputs_date"] = str(ev.index[-1].date())
    return {"checklist": check, "backtests": tests, "measures": measures, "since": str(w.index[0].date()), "as_of": str(w.index[-1].date()),
            "research": _research()}


def _research() -> dict:
    f = DATA_DIR / SLUG / "mstr_research.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _mstr_now() -> dict:
    out: dict = {"stale": {}, "updated": int(time.time())}
    h = mstr_history()
    days = pd.date_range(h.index[0], pd.Timestamp.now().normalize(), freq="D")
    hold = h["hold"].astype(float).reindex(days).ffill()
    shares = h["basic"].astype(float).reindex(days).ffill()
    try:
        from .btc_cycles import price as cm_price
        m_raw = yahoo_daily("MSTR", "2020-08-01")
        try:
            b_raw = cm_price()
        except Exception:
            b_raw = yahoo_daily("BTC-USD", "2020-08-01")
        out["price_source"] = "daily closes (MSTR: Yahoo or Nasdaq; BTC: Coin Metrics)"
    except Exception as e:
        m_raw, b_raw = h["mstr"].astype(float).dropna(), h["btc"].astype(float).dropna()
        out["yahoo_error"] = type(e).__name__
        out["price_source"] = "the dataset's own closes (Yahoo unavailable; weekly in 2021-25, so correlation is on those points)"
    mstr = m_raw.reindex(days).fillna(h["mstr"].astype(float).reindex(days)).ffill()
    btc = b_raw.reindex(days).fillna(h["btc"].astype(float).reindex(days)).ffill()
    # purchases: every increase in holdings between dataset points
    d = h["hold"].astype(float).diff()
    buys = [{"date": str(t.date()), "btc": _r(v, 0), "held_after": _r(float(h["hold"].loc[t]), 0), "btc_price": _r(float(btc.asof(t)), 0),
             "approx_usd": _r(v * float(btc.asof(t)), 0)} for t, v in d.items() if v and v > 0]
    held_first = float(h["hold"].iloc[0])
    cost = held_first * float(btc.asof(h.index[0])) + sum(b["approx_usd"] or 0 for b in buys)
    mnav = (mstr * shares / (btc * hold)).dropna()
    # returns on MSTR's own trading days only: a weekend forward-filled into zero returns would understate the link to BTC
    corr, beta = corr_beta(m_raw, btc.reindex(m_raw.index).dropna(), n=90 if out.get("price_source", "").startswith("daily") else 26)
    w = lambda s: s.resample("W").last().dropna()
    out.update({
        "held": _pts(w(hold), 0), "btc_per_1000_shares": _pts(w(hold / shares * 1000), 4), "mnav": _pts(w(mnav), 3),
        "nav_per_share": _pts(w((btc * hold / shares).dropna()), 2),     # MSTR price at mNAV 1: its bitcoin per share, in US$
        "mstr": _pts(w(mstr), 2), "btc": _pts(w(btc), 0), "corr90": _pts(w(corr), 3), "beta90": _pts(w(beta), 3),
        "mstr_rebased": _pts(w(mstr / mstr.dropna().iloc[0]), 4), "btc_rebased": _pts(w(btc / btc.dropna().iloc[0]), 4),
        "purchases": buys[::-1],
        "kpi": {"held": _r(float(hold.iloc[-1]), 0), "approx_cost_usd": _r(cost, 0), "approx_avg_cost": _r(cost / float(hold.iloc[-1]), 0),
                "value_usd": _r(float(hold.iloc[-1] * btc.iloc[-1]), 0), "mnav": _r(float(mnav.iloc[-1]), 3), "corr90": _r(float(corr.iloc[-1]), 3) if len(corr) else None,
                "beta90": _r(float(beta.iloc[-1]), 2) if len(beta) else None, "share_of_supply": _r(float(hold.iloc[-1]) / 21e6, 5),
                "purchases": len(buys), "last_purchase": buys[-1]["date"] if buys else None, "mstr": _r(float(mstr.iloc[-1]), 2)},
        "note": j_note(),
        "as_of": str(h.index[-1].date()),
    })
    try:
        out["strategies"] = mnav_strategies(mstr, btc, hold, shares, h)
    except Exception as e:
        out["strategies_error"] = type(e).__name__
    # UK and HK treasury companies (hand-entered holdings; prices from Yahoo or CNBC, or holdings only)
    comps = {}
    for r in _rows("treasuries"):
        comps.setdefault(r["company"], {"company": r["company"], "country": r["country"], "yahoo": r["yahoo"], "rows": []})["rows"].append(r)
    cards = []
    for c in comps.values():
        rows = sorted(c["rows"], key=lambda r: r["date"])
        item = {"company": c["company"], "country": c["country"], "yahoo": c["yahoo"], "held": [[int(pd.Timestamp(r["date"]).timestamp()), float(r["btc_held"])] for r in rows if r.get("btc_held")],
                "rows": rows[::-1]}
        if item["held"]:
            item["held_value_usd"] = _r(item["held"][-1][1] * float(btc.iloc[-1]), 0)
        try:
            px, item["price_source"], item["price_tried"] = stock_daily(c["yahoo"], "2024-01-01")
            item["price"] = _pts(px, 4)
            co, be = corr_beta(px, btc.dropna())
            item["corr90"] = _r(float(co.iloc[-1]), 3) if len(co) else None
        except Exception as e:
            item["price_error"] = "no price source reachable from the server"
            item["price_tried"] = str(e).split("; ")
        cards.append(item)
    out["treasuries"] = cards
    out["stale"] = stale_info([MSTR_HISTORY])
    return out


def j_note() -> str:
    return ("Holdings and share counts: public dataset built from Strategy's SEC filings and purchase announcements (forward-filled between "
            "updates; some periods are weekly, so several purchases can appear as one). Cost basis = BTC added × BTC close that day: approximate; "
            "Strategy's own reported cost basis is the authority.")


def _cached_ep(name, fn, ttl=6 * 3600):
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"etf": _cached_ep("etf", _etf_now), "mstr": _cached_ep("mstr", _mstr_now)}
