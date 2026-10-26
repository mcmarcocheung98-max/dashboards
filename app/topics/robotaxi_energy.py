"""Energy tab of /robotaxi: how fast the US, UK, Hong Kong and mainland China move to electric cars and to wind and solar power.

ev     electric (BEV + PHEV) share of new car registrations per market and month, rolling 12 months, from Ember's EV sales data
       (CSV, automated; Hong Kong included); the official yearly figures per market and definition (hand-entered from SMMT, CPCA, Cox/KBB, DOE/Argonne and HK government papers:
       data/robotaxi/ev_share.csv), and the latest month or quarter (ev_latest.csv)
power  solar and wind share of electricity generation per market and year, and per month, from Ember's yearly and monthly
       electricity data (CSV, CC BY 4.0, automated); official cross-checks hand-entered in power_checks.csv

Batteries store electricity rather than generate it, so they are not in the generation shares (README).
"""
from __future__ import annotations

from io import StringIO

import pandas as pd

from ._base import DAY, _pts, _r, fetch, manual, manual_rows, payload

DASHBOARD = "robotaxi"
SLUG = "robotaxi"
EMBER_YEARLY = "https://files.ember-energy.org/public-downloads/generation/outputs/release_generation_yearly_global.csv"
EMBER_MONTHLY = "https://files.ember-energy.org/public-downloads/generation/outputs/release_generation_monthly_global.csv"
EMBER_EV = "https://storage.googleapis.com/emb-prod-bkt-publicdata/public-downloads/transport/outputs/monthly_ev_sales.csv"
EV_DRIVETRAIN = "Electric vehicle (BEV+PHEV)"
MARKETS = {"United States": "US", "United Kingdom": "UK", "China": "China", "Hong Kong": "Hong Kong"}   # Ember area -> label
SOURCES_SW = ("Solar", "Wind")


def _market(area: str) -> str | None:
    a = area.strip()
    if a in MARKETS:
        return MARKETS[a]
    if "hong kong" in a.lower():
        return "Hong Kong"
    return None


def parse_ember(text: str) -> pd.DataFrame:
    """Ember generation CSV (one row per area, period and electricity source) -> rows for the four markets and solar/wind:
    market, period (Timestamp), source, share (% of generation)."""
    d = pd.read_csv(StringIO(text), dtype=str)
    cols = {c.strip().lower(): c for c in d.columns}
    area, src, share = cols.get("area"), cols.get("electricity source"), cols.get("share of generation (%)")
    when = cols.get("date") or cols.get("year") or cols.get("month")
    if not (area and src and share and when):
        raise ValueError("Ember layout changed")
    d = d[d[src].isin(SOURCES_SW)].copy()
    d["market"] = d[area].map(_market)
    d = d.dropna(subset=["market"])
    raw = d[when].astype(str).str.strip()
    period = pd.to_datetime(raw.where(~raw.str.fullmatch(r"\d{4}"), raw + "-01-01"), errors="coerce")
    out = pd.DataFrame({"market": d["market"], "period": period, "source": d[src], "share": pd.to_numeric(d[share], errors="coerce")})
    return out.dropna(subset=["period", "share"])


def wind_solar(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Solar + wind share of generation per market, by period."""
    out = {}
    for m, g in df.groupby("market"):
        s = g.pivot_table(index="period", columns="source", values="share", aggfunc="sum")
        if set(SOURCES_SW) <= set(s.columns):
            out[m] = (s["Solar"] + s["Wind"]).dropna().sort_index()
    return out


def _power() -> dict:
    y = parse_ember(fetch(EMBER_YEARLY, DAY, min_bytes=100000))
    yearly = wind_solar(y)
    split = {m: {src: _pts(g[g["source"] == src].set_index("period")["share"].sort_index(), 2) for src in SOURCES_SW}
             for m, g in y.groupby("market")}
    out = {"yearly": {m: _pts(s, 2) for m, s in yearly.items()}, "split": split,
           "latest": {m: {"year": int(s.index[-1].year), "share": _r(s.iloc[-1], 2), "change": _r(s.iloc[-1] - s.iloc[-2], 2) if len(s) > 1 else None}
                      for m, s in yearly.items() if len(s)}}
    try:                                                          # the monthly file adds the last 12 months; the card stands without it
        mo = wind_solar(parse_ember(fetch(EMBER_MONTHLY, DAY, min_bytes=100000)))
        out["monthly"] = {m: _pts(s[s.index >= s.index[-1] - pd.DateOffset(years=5)], 2) for m, s in mo.items() if len(s)}
        out["monthly_latest"] = {m: {"month": str(s.index[-1].date()), "share": _r(s.iloc[-1], 2),
                                     "year_ago": _r(s.get(s.index[-1] - pd.DateOffset(years=1)), 2)} for m, s in mo.items() if len(s)}
    except Exception as e:
        out["monthly_error"] = type(e).__name__
    return out


def parse_ember_ev(text: str) -> dict[str, pd.DataFrame]:
    """Ember's monthly EV sales CSV -> per market, a monthly frame with share (%) and rolling 12-month share (%) of registrations that
    are battery-electric or plug-in hybrid."""
    d = pd.read_csv(StringIO(text), dtype=str)
    need = {"Area", "Date", "Drivetrain", "Share of registrations (%)", "Rolling 12-month share of registrations (%)"}
    if not need <= set(d.columns):
        raise ValueError("Ember EV layout changed")
    if "Data frequency" in d.columns:
        d = d[d["Data frequency"].str.strip().str.lower() == "monthly"]
    d = d[d["Drivetrain"].str.strip() == EV_DRIVETRAIN].copy()
    d["market"] = d["Area"].map(_market)
    d = d.dropna(subset=["market"])
    out = {}
    for m, g in d.groupby("market"):
        f = pd.DataFrame({"share": pd.to_numeric(g["Share of registrations (%)"], errors="coerce").values,
                          "r12": pd.to_numeric(g["Rolling 12-month share of registrations (%)"], errors="coerce").values},
                         index=pd.to_datetime(g["Date"], errors="coerce")).sort_index()
        f = f[f.index.notna()]
        if len(f):
            out[m] = f
    return out


def _ev_ember() -> dict:
    ev = parse_ember_ev(fetch(EMBER_EV, DAY, min_bytes=100000))

    def year_ago(s, t):
        v = s.get(t - pd.DateOffset(years=1))
        return None if v is None or pd.isna(v) else _r(v, 2)
    return {"r12": {m: _pts(f["r12"].dropna(), 2) for m, f in ev.items()},
            "monthly": {m: _pts(f["share"].dropna(), 2) for m, f in ev.items()},
            "latest": {m: {"month": str(f.index[-1].date()), "share": _r(f["share"].iloc[-1], 2), "r12": _r(f["r12"].iloc[-1], 2),
                           "r12_year_ago": year_ago(f["r12"], f.index[-1])} for m, f in ev.items()}}


def _ev() -> dict:
    ev = manual(SLUG, "ev_share")
    ev = ev if isinstance(ev, dict) else {}
    latest = {k: {"year": int(s.index[-1].year), "share": _r(s.iloc[-1], 2), "change": _r(s.iloc[-1] - s.iloc[-2], 2) if len(s) > 1 else None}
              for k, s in ev.items() if len(s)}
    return {"yearly": {k: _pts(s, 2) for k, s in ev.items()}, "latest": latest,
            "months": sorted(manual_rows(SLUG, "ev_latest"), key=lambda r: r["date"], reverse=True),
            "rows": sorted(manual_rows(SLUG, "ev_share"), key=lambda r: (r["series"], r["date"]))}


def energy_now() -> dict:
    out = payload({"ev": _ev, "ev_ember": _ev_ember, "power": _power}, sources=[EMBER_YEARLY, EMBER_MONTHLY, EMBER_EV])
    out["checks"] = sorted(manual_rows(SLUG, "power_checks"), key=lambda r: (r["market"], r["date"]))
    dates = [r["date"] for r in (out.get("ev") or {}).get("months", [])] + [x["month"] for x in ((out.get("ev_ember") or {}).get("latest") or {}).values()]
    out["as_of"] = max(dates, default=None)
    return out


def readings(p: dict) -> list[dict]:
    """Energy tab readings: +1 = the share moved towards electric cars or wind and solar since the previous year, -1 away."""
    out = []
    ev = (p.get("ev") or {}).get("latest") or {}
    for key, name in (("ev_uk_bev", "UK: battery-electric"), ("ev_china_nev", "China: new energy vehicles (battery + plug-in hybrid + range-extender)")):
        x = ev.get(name)
        if x:
            out.append({"tab": "energy", "key": key, "label": f"{name.split(' (')[0]} share of new cars, {x['year']}", "value": x["share"],
                        "lean": 0 if not x["change"] else (1 if x["change"] > 0 else -1), "note": f"{x['change']:+} points on the year before" if x["change"] is not None else None})
    pw = (p.get("power") or {}).get("latest") or {}
    for key, m in (("ws_china", "China"), ("ws_us", "US")):
        x = pw.get(m)
        if x:
            out.append({"tab": "energy", "key": key, "label": f"{m}: wind and solar share of electricity, {x['year']}", "value": x["share"],
                        "lean": 0 if not x["change"] else (1 if x["change"] > 0 else -1), "note": f"{x['change']:+} points on the year before" if x["change"] is not None else None})
    return out
