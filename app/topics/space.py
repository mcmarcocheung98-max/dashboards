"""Space Economy (/space): when does orbit become routine infrastructure?

launches   orbital launch attempts per year by country and provider, 1957 on, the trailing 12-month count, SpaceX's share and payload
           mass reaching orbit (Jonathan McDowell's GCAT: launch.tsv, orgs.tsv and satcat.tsv), plus the "routine infrastructure"
           checklist that the other tabs feed
cost       cost per kg to low Earth orbit by vehicle and the cheapest flown price over time (hand-entered: cost.csv)
satellites active satellites by operator and owner, and still-active satellites by launch year (CelesTrak SATCAT CSV), and Starlink
           subscribers (SpaceX announcements, hand-entered: starlink.csv)
industry   size of the space economy (Space Foundation, OECD, UK Space Agency; hand-entered: economy.csv) and space stocks RKLB, ASTS,
           IRDM, PL and the UFO ETF against SPY (Nasdaq quote API)
ukhk       UK launch attempts and the SaxaVord / Cornwall timeline, Hong Kong and China milestones (hand-entered: milestones.csv), and
           China's launches by provider (GCAT)

Leans in READINGS(): +1 means faster growth or cheaper access, -1 the opposite (data/space/README.md lists every rule).
"""
from __future__ import annotations

import re
from io import StringIO

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from ._base import DAY, _pts, _r, fetch, fetch_json, manual_rows, manual_sources, payload

SLUG = "space"
TOPIC = Topic(SLUG, "Space Economy",
              "Orbital launches by country and provider, cost per kg to orbit, active satellites and Starlink, the size of the space economy and "
              "space stocks, and the UK, Hong Kong and China: when does orbit become routine infrastructure?",
              "space", (("launches", "Launches"), ("cost", "Cost to orbit"), ("satellites", "Starlink & satellites"), ("industry", "Industry"),
                        ("ukhk", "UK, HK & China")),
              ("launches", "satellites", "industry", "ukhk"), icon="rocket", order=80)

GCAT = "https://planet4589.org/space/gcat/tsv/"
GCAT_LAUNCH, GCAT_ORGS, GCAT_SATCAT = GCAT + "launch/launch.tsv", GCAT + "tables/orgs.tsv", GCAT + "cat/satcat.tsv"
CELESTRAK = "https://celestrak.org/pub/satcat.csv"
NASDAQ = "https://api.nasdaq.com/api/quote/{sym}/historical?assetclass={cls}&fromdate={a}&todate={b}&limit=9999"
NASDAQ_HEADERS = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
TICKERS = {"RKLB": "stocks", "ASTS": "stocks", "IRDM": "stocks", "PL": "stocks", "UFO": "etf", "SPY": "etf"}
NAMES = {"RKLB": "Rocket Lab", "ASTS": "AST SpaceMobile", "IRDM": "Iridium", "PL": "Planet Labs", "UFO": "Procure Space ETF", "SPY": "S&P 500 (SPY)"}
BASKET = ("RKLB", "ASTS", "IRDM", "PL")
START = "2021-01-04"

# GCAT state codes -> the groups drawn on the page
COUNTRY = {"US": "US", "CN": "China", "RU": "Russia", "SU": "Russia", "UK": "UK", "GB": "UK", "J": "Japan", "IN": "India", "HK": "Hong Kong"}
EUROPE = {"F", "D", "I", "I-ESA", "I-ESRO", "I-ELDO", "I-EU", "IT", "E", "NL", "B", "S", "N", "L", "CH", "A", "DK"}
GROUPS = ("US", "China", "Russia", "Europe", "Japan", "India", "UK", "Other")
# used only when orgs.tsv cannot be read: the providers that fly most often
ORG_FALLBACK = {"SPX": ("SpaceX", "US"), "CASC": ("CASC", "CN"), "RVSN": ("RVSN", "SU"), "VKS": ("VKS", "RU"), "RKA": ("Roscosmos", "RU"),
                "RLABU": ("Rocket Lab", "US"), "ULA": ("ULA", "US"), "ARIANE": ("Arianespace", "F"), "ISRO": ("ISRO", "IN"), "MHI": ("MHI", "J")}

# CelesTrak SATCAT: operational status codes counted as active, and the constellations named on the page
ACTIVE = set("+PBSX")
CONSTELLATIONS = (("Starlink (SpaceX)", r"^STARLINK"), ("OneWeb (Eutelsat)", r"^ONEWEB"), ("Kuiper (Amazon)", r"^KUIPER"),
                  ("Qianfan (China)", r"^(QIANFAN|G60|QIANFAN-)"), ("Guowang (China)", r"^(GUOWANG|SATNET|HULIANWANG)"),
                  ("Planet", r"^(FLOCK|SKYSAT|PELICAN|TANAGER)"), ("Iridium", r"^IRIDIUM"), ("Spire", r"^LEMUR"), ("Globalstar", r"^GLOBALSTAR"),
                  ("Orbcomm", r"^ORBCOMM"))
OWNERS = {"US": "US other", "PRC": "China other", "CIS": "Russia", "UK": "UK other", "ESA": "Europe", "FR": "Europe", "GER": "Europe", "IT": "Europe",
          "JPN": "Japan", "IND": "India"}

SOURCES = [{"name": "Jonathan McDowell, GCAT: launch list, organisations and satellite catalog (TSV)", "url": "https://planet4589.org/space/gcat/", "cadence": "weekly"},
           {"name": "CelesTrak SATCAT (CSV)", "url": "https://celestrak.org/satcat/", "cadence": "daily"},
           {"name": "Nasdaq quote API (RKLB, ASTS, IRDM, PL, UFO, SPY)", "url": "https://www.nasdaq.com/market-activity/stocks/rklb", "cadence": "daily"},
           {"name": "CSIS Aerospace Security, Space Foundation, OECD, UK Space Agency, CAA, SpaceX, CNSA, CMSA (hand-entered, cited per row)",
            "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/space", "cadence": "as published"}]
NOTES = ("A launch counts when it tries for orbit (or beyond), success or not; the country is the launch provider's, so Rocket Lab's New Zealand "
         "launches count for the US. Cost per kg is a published estimate for a full rocket, not what any one customer paid. Active satellites "
         "are the payloads CelesTrak marks operational today. Rows marked 'verify' were entered from memory when the dashboard was built and "
         "still need checking against the cited page.")


def _band(x, lo, hi) -> int:
    return 0 if x is None else 1 if x > hi else -1 if x < lo else 0


def _now() -> pd.Timestamp:
    return pd.Timestamp.now("UTC").tz_localize(None).normalize()


def _year(y: int) -> pd.Timestamp:
    return pd.Timestamp(f"{int(y)}-07-01")


# ------------------------------------------------------------------ GCAT (planet4589.org)
def parse_tsv(text: str, keep: tuple = ()) -> pd.DataFrame:
    """A GCAT TSV: the first line is the header (starting with #), later # lines are comments; every value is a stripped string.
    keep: the column names to read (any case), so a 20 MB catalog is not held as 40 string columns."""
    nl = text.find("\n")
    if nl < 0:
        raise ValueError("GCAT: empty file")
    names = [c.strip() for c in text[:nl].lstrip("#").rstrip("\r").split("\t")]
    want = {k.lower() for k in keep}
    use = [i for i, c in enumerate(names) if not want or c.lower() in want or i == 0]
    d = pd.read_csv(StringIO(text[nl + 1:]), sep="\t", header=None, names=names, usecols=use, dtype=str, keep_default_na=False, quoting=3,
                    on_bad_lines="skip", engine="c")
    d = d[~d[names[0]].str.startswith("#")]
    return d.apply(lambda c: c.str.strip())


def _col(d: pd.DataFrame, *names) -> str:
    low = {c.lower(): c for c in d.columns}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    raise KeyError(f"none of {names} in {list(d.columns)[:12]}")


MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def gcat_date(s: str):
    """'2024 Jan  5 0412:34' (also '2024 Jan 5', '2024 Jan', '2024') -> Timestamp, or None."""
    m = re.match(r"\s*(\d{4})(?:\s+([A-Z][a-z]{2}))?(?:\s+(\d{1,2}))?", str(s or ""))
    if not m:
        return None
    mo = MONTHS.get(m.group(2) or "", 1 if not m.group(2) else None)
    if mo is None:
        return None
    try:
        return pd.Timestamp(int(m.group(1)), mo, int(m.group(3) or 1))
    except ValueError:
        return None


def parse_orgs(text: str) -> dict[str, tuple[str, str]]:
    """orgs.tsv -> {code: (short name, state code)}."""
    d = parse_tsv(text, ("Code", "StateCode", "State", "ShortEName", "ShortName", "EName", "Name"))
    code, state = _col(d, "Code"), _col(d, "StateCode", "State")
    name = next((c for c in ("ShortEName", "ShortName", "EName", "Name") if c in d.columns), code)
    return {r[code]: (r[name] or r[code], r[state]) for _, r in d.iterrows() if r[code]}


def group_of(state: str) -> str:
    s = (state or "").strip()
    return COUNTRY.get(s) or ("Europe" if s in EUROPE or s.startswith("I-E") else "Other")


def parse_launches(text: str, orgs: dict) -> pd.DataFrame:
    """launch.tsv -> one row per orbital or deep-space attempt: date, year, agency, provider, state, country, success, vehicle."""
    d = parse_tsv(text, ("Launch_Code", "LaunchCode", "Launch_Date", "LDate", "Agency", "LV_Agency", "LV_Type", "LVType"))
    code, date, agency = _col(d, "Launch_Code", "LaunchCode"), _col(d, "Launch_Date", "LDate"), _col(d, "Agency", "LV_Agency")
    lv = next((c for c in ("LV_Type", "LVType") if c in d.columns), None)
    d = d[d[code].str[:1].isin(["O", "D"])].copy()
    out = pd.DataFrame({"date": d[date].map(gcat_date), "code": d[code], "agency": d[agency].str.split(r"[/,\s]").str[0].fillna(""),
                        "vehicle": d[lv] if lv else ""})
    out = out.dropna(subset=["date"])
    if out.empty:
        raise ValueError("GCAT: no orbital launches (layout changed?)")
    info = {**ORG_FALLBACK, **(orgs or {})}
    out["provider"] = out["agency"].map(lambda a: info.get(a, (a or "unknown", ""))[0])
    out["state"] = out["agency"].map(lambda a: info.get(a, ("", ""))[1])
    out["country"] = out["state"].map(group_of)
    out["success"] = out["code"].str[1:2] == "S"
    out["year"] = out["date"].map(lambda t: t.year)
    return out.sort_values("date").reset_index(drop=True)


def parse_payload_mass(text: str) -> pd.DataFrame:
    """GCAT satcat.tsv -> payload launch mass (tonnes) per launch year: total and Starlink."""
    d = parse_tsv(text, ("Type", "Mass", "LDate", "Launch_Date", "Name", "PLName"))
    typ, mass, ld = _col(d, "Type"), _col(d, "Mass"), _col(d, "LDate", "Launch_Date")
    name = [c for c in ("Name", "PLName") if c in d.columns]
    d = d[d[typ].str.startswith("P")]
    yr = d[ld].str[:4]
    m = pd.to_numeric(d[mass], errors="coerce")
    star = pd.Series(False, index=d.index)
    for c in name:
        star |= d[c].str.contains("starlink", case=False, na=False)
    out = pd.DataFrame({"year": pd.to_numeric(yr, errors="coerce"), "mass": m, "starlink": star}).dropna(subset=["year", "mass"])
    if out.empty:
        raise ValueError("GCAT satcat: no payload masses")
    g = out.groupby("year")
    res = pd.DataFrame({"total": g["mass"].sum() / 1000, "starlink": out[out["starlink"]].groupby("year")["mass"].sum() / 1000, "count": g.size()})
    res.index = res.index.astype(int)
    return res.fillna(0)


def polite(url: str, ttl: float = DAY, max_age: float = 20 * 3600, **kw) -> str:
    """fetch(), but a disk snapshot younger than max_age is used as it is: CelesTrak answers 403 to a client that downloads the same
    file again within a few hours, and every redeploy empties the memory cache."""
    import time
    from ..cache import _cached
    snap = B._snap(url)
    if snap.exists() and time.time() - snap.stat().st_mtime < max_age:
        return _cached(f"topic:{url}", ttl, lambda: snap.read_text(encoding="utf-8"))
    return fetch(url, ttl, **kw)


def orgs() -> dict:
    try:
        return parse_orgs(polite(GCAT_ORGS, 7 * DAY, 7 * DAY, timeout=90))
    except Exception:
        return {}


def launches() -> pd.DataFrame:
    """The parsed launch list, cached so the Launches and China tabs parse the 14 MB file once."""
    from ..cache import _cached
    return _cached(f"topic:{SLUG}:launch-list", 6 * 3600, lambda: parse_launches(polite(GCAT_LAUNCH, DAY, timeout=120, min_bytes=10000), orgs()))


def payload_mass() -> pd.DataFrame:
    return parse_payload_mass(polite(GCAT_SATCAT, DAY, timeout=180, min_bytes=10000))


# ------------------------------------------------------------------ CelesTrak SATCAT
def operator_of(name: str, owner: str) -> str:
    n = (name or "").upper()
    for label, pat in CONSTELLATIONS:
        if re.match(pat, n):
            return label
    return OWNERS.get((owner or "").upper(), "Other")


def parse_celestrak(text: str) -> pd.DataFrame:
    """satcat.csv -> active payloads: name, owner, operator, launch date."""
    d = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
    d.columns = [c.strip().upper() for c in d.columns]
    st, nm, ow, ld = (_col(d, "OPS_STATUS_CODE"), _col(d, "OBJECT_NAME", "SATNAME"), _col(d, "OWNER", "COUNTRY"), _col(d, "LAUNCH_DATE"))
    act = d[st].str.strip().isin(ACTIVE)
    if "OBJECT_TYPE" in d.columns:
        act &= d["OBJECT_TYPE"].str.strip().str.upper().isin(["PAY", "PAYLOAD", ""])
    if "DECAY_DATE" in d.columns:
        act &= d["DECAY_DATE"].str.strip() == ""
    a = d[act]
    if a.empty:
        raise ValueError("CelesTrak: no active payloads (layout changed?)")
    out = pd.DataFrame({"name": a[nm].str.strip(), "owner": a[ow].str.strip(), "launch": pd.to_datetime(a[ld].str.strip(), errors="coerce")})
    out["operator"] = [operator_of(n, o) for n, o in zip(out["name"], out["owner"])]
    return out.reset_index(drop=True)


def active() -> pd.DataFrame:
    return parse_celestrak(polite(CELESTRAK, DAY, timeout=120, min_bytes=10000))


# ------------------------------------------------------------------ Nasdaq
def nasdaq(sym: str) -> pd.Series:
    url = NASDAQ.format(sym=sym, cls=TICKERS[sym], a=START, b=pd.Timestamp.now().strftime("%Y-%m-%d"))
    j = fetch_json(url, DAY, headers=NASDAQ_HEADERS)
    rows = (((j or {}).get("data") or {}).get("tradesTable") or {}).get("rows") or []
    s = pd.Series({pd.to_datetime(r["date"], format="%m/%d/%Y"): float(str(r["close"]).replace("$", "").replace(",", "")) for r in rows if r.get("close")})
    if len(s) < 20:
        raise ValueError(f"Nasdaq: {len(s)} rows for {sym}")
    return s.sort_index()


def nasdaq_urls() -> list[str]:
    b = pd.Timestamp.now().strftime("%Y-%m-%d")
    return [NASDAQ.format(sym=s, cls=c, a=START, b=b) for s, c in TICKERS.items()]


# ------------------------------------------------------------------ hand-entered
def rows(name: str) -> list[dict]:
    return sorted(manual_rows(SLUG, name), key=lambda r: r["date"])


def cited(*names) -> list[dict]:
    return sorted([s for n in names for s in manual_sources(SLUG, n)], key=lambda s: s["date"], reverse=True)[:10]


def _f(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def cost_rows() -> list[dict]:
    return [{**r, "value": _f(r.get("value"))} for r in rows("cost") if _f(r.get("value")) is not None]


def frontier(rs: list[dict]) -> pd.Series:
    """The cheapest flown cost per kg available each year: the running minimum over vehicles by first flight."""
    flown = [r for r in rs if r.get("kind", "flown") == "flown"]
    if not flown:
        return pd.Series(dtype=float)
    first = pd.Series({int(r["date"][:4]): r["value"] for r in sorted(flown, key=lambda r: -r["value"])}, dtype=float)
    first = first.groupby(level=0).min().sort_index()
    yrs = range(int(first.index.min()), _now().year + 1)
    best = first.reindex(yrs).cummin().ffill()
    return pd.Series(best.values, index=pd.DatetimeIndex([_year(y) for y in yrs]), dtype=float)


def starlink_subs() -> pd.Series:
    return pd.Series({pd.Timestamp(r["date"]): _f(r["value"]) for r in rows("starlink") if _f(r.get("value")) is not None}, dtype=float).sort_index()


def _at(s: pd.Series, t: pd.Timestamp):
    """Linear interpolation of a sparse series at t (None outside its range)."""
    s = s.dropna()
    if not len(s) or t < s.index[0] or t > s.index[-1]:
        return None
    sec = lambda i: (pd.DatetimeIndex(i) - pd.Timestamp("1970-01-01")).total_seconds()
    return float(np.interp(sec([t])[0], sec(s.index), s.values))


# ------------------------------------------------------------------ tabs
def _ytd(L: pd.DataFrame, year: int, today: pd.Timestamp) -> int:
    cut = pd.Timestamp(year, today.month, min(today.day, 28))
    return int(((L["year"] == year) & (L["date"] <= cut)).sum())


def _launches_now() -> dict:
    today = _now()

    def main():
        L = launches()
        this = today.year
        yrs = list(range(int(L["year"].min()), this + 1))
        by = L.groupby(["year", "country"]).size().unstack(fill_value=0).reindex(yrs, fill_value=0)
        full = by[by.index < this]
        countries = {g: _pts(pd.Series(full[g].values, index=[_year(y) for y in full.index]), 0) for g in GROUPS if g in full}
        tot = full.sum(axis=1)
        ok = L[L["success"]].groupby("year").size().reindex(full.index, fill_value=0)
        mon = L.set_index("date").resample("MS").size()
        mon = mon[mon.index <= today]
        r12 = mon.rolling(12).sum().dropna()
        r12c = {g: L[L["country"] == g].set_index("date").resample("MS").size().reindex(mon.index, fill_value=0).rolling(12).sum().dropna() for g in ("US", "China")}
        spx = L["provider"].str.contains("SpaceX", case=False) | (L["agency"] == "SPX")
        share = (L[spx].groupby("year").size().reindex(full.index, fill_value=0) / tot.replace(0, np.nan)).dropna()
        last = this - 1
        top = L[L["year"] == last].groupby(["provider", "country"]).size().sort_values(ascending=False)
        ytd = L[L["year"] == this].groupby(["provider", "country"]).size()
        prov = [{"provider": p, "country": c, "last": int(n), "share": _r(n / max(1, tot.get(last, 0)), 4), "ytd": int(ytd.get((p, c), 0))} for (p, c), n in top.head(12).items()]
        y12 = L[L["date"] > today - pd.Timedelta(days=365)]
        p12 = L[(L["date"] <= today - pd.Timedelta(days=365)) & (L["date"] > today - pd.Timedelta(days=730))]
        nonspx_12 = int((~y12["provider"].str.contains("SpaceX", case=False) & (y12["agency"] != "SPX")).sum())
        second = y12[~y12["provider"].str.contains("SpaceX", case=False) & (y12["agency"] != "SPX")].groupby("provider").size().sort_values(ascending=False)
        kpi = {"year": this, "ytd": _ytd(L, this, today), "ytd_prev": _ytd(L, this - 1, today), "last_year": last, "last_total": int(tot.get(last, 0)),
               "last_ok": _r(ok.get(last, 0) / max(1, tot.get(last, 0)), 4), "r12": int(len(y12)), "r12_prev": int(len(p12)),
               "r12_yoy": _r(len(y12) / len(p12) - 1, 4) if len(p12) else None, "spacex_share": _r(share.get(last), 4),
               "china_12": int((y12["country"] == "China").sum()), "china_prev": int((p12["country"] == "China").sum()),
               "us_12": int((y12["country"] == "US").sum()), "nonspx_12": nonspx_12, "nonspx_prev": int((~p12["provider"].str.contains("SpaceX", case=False) & (p12["agency"] != "SPX")).sum()),
               "second": {"provider": second.index[0], "n": int(second.iloc[0])} if len(second) else None, "latest": str(L["date"].max().date())}
        return {"countries": countries, "total": _pts(pd.Series(tot.values, index=[_year(y) for y in tot.index]), 0),
                "success_rate": _pts(pd.Series((ok / tot.replace(0, np.nan)).values, index=[_year(y) for y in tot.index]), 4),
                "rolling": _pts(r12, 0), "rolling_by": {g: _pts(s, 0) for g, s in r12c.items()}, "spacex_share": _pts(pd.Series(share.values, index=[_year(y) for y in share.index]), 4),
                "providers": prov, "kpi": kpi}

    def mass():
        m = payload_mass()
        m = m[m.index < today.year]
        m = m.reindex(range(int(m.index.min()), int(m.index.max()) + 1), fill_value=0)       # no gap years: every yearly chart shares one axis
        idx = [_year(y) for y in m.index]
        last = int(m.index[-1])
        prev = m["total"].get(last - 1)
        return {"total": _pts(pd.Series(m["total"].values, index=idx), 1), "starlink": _pts(pd.Series(m["starlink"].values, index=idx), 1),
                "other": _pts(pd.Series((m["total"] - m["starlink"]).values, index=idx), 1),
                "kpi": {"year": last, "tonnes": _r(m["total"].iloc[-1], 1), "starlink_share": _r(m["starlink"].iloc[-1] / m["total"].iloc[-1], 4) if m["total"].iloc[-1] else None,
                        "yoy": _r(m["total"].iloc[-1] / prev - 1, 4) if prev else None, "tonnes_10y": _r(m["total"].get(last - 10), 1)}}
    out = payload({"launches": main, "mass": mass}, sources=[GCAT_LAUNCH, GCAT_SATCAT, GCAT_ORGS])
    out["as_of"] = ((out.get("launches") or {}).get("kpi") or {}).get("latest")
    return out


def _cost_now() -> dict:
    rs = cost_rows()
    fr = frontier(rs)
    flown = sorted([r for r in rs if r.get("kind", "flown") == "flown"], key=lambda r: r["date"])
    out = payload({"frontier": lambda: _pts(fr, 0)})
    out["vehicles"] = [{"date": r["date"], "vehicle": r.get("series", ""), "country": r.get("country", ""), "usd_kg": _r(r["value"], 0), "kind": r.get("kind", "flown"),
                        "price_musd": _f(r.get("price_musd")), "leo_kg": _f(r.get("leo_kg")), "source": r.get("source", ""), "note": r.get("note", "")} for r in rs]
    if len(fr):
        now_best = fr.iloc[-1]
        ago = fr[fr.index <= fr.index[-1] - pd.DateOffset(years=10)]
        ago20 = fr[fr.index <= fr.index[-1] - pd.DateOffset(years=20)]
        best = min(flown, key=lambda r: r["value"]) if flown else {}
        recent = [r for r in flown if int(r["date"][:4]) >= _now().year - 10]
        older = [r for r in flown if int(r["date"][:4]) < _now().year - 10]
        out["kpi"] = {"best": _r(now_best, 0), "best_vehicle": best.get("series"), "best_year": best.get("date", "")[:4], "ten_y": _r(ago.iloc[-1], 0) if len(ago) else None,
                      "twenty_y": _r(ago20.iloc[-1], 0) if len(ago20) else None, "fall_10y": _r(now_best / ago.iloc[-1] - 1, 4) if len(ago) else None,
                      "recent_best": _r(min((r["value"] for r in recent), default=np.nan), 0), "older_best": _r(min((r["value"] for r in older), default=np.nan), 0)}
    out["cited"] = cited("cost")
    out["as_of"] = max((r["date"] for r in rs), default=None)
    return out


def _satellites_now() -> dict:
    today = _now()

    def act():
        a = active()
        by_op = a.groupby("operator").size().sort_values(ascending=False)
        yrs = a["launch"].dt.year.dropna().astype(int)
        by_year = yrs.value_counts().sort_index()
        by_year = by_year[by_year.index >= 2000]
        star = a["operator"].str.startswith("Starlink")
        cum = a.dropna(subset=["launch"]).set_index("launch").sort_index().resample("MS").size().cumsum()
        cum_s = a[star].dropna(subset=["launch"]).set_index("launch").sort_index().resample("MS").size().cumsum()
        y12 = int((a["launch"] > today - pd.Timedelta(days=365)).sum())
        p12 = int(((a["launch"] <= today - pd.Timedelta(days=365)) & (a["launch"] > today - pd.Timedelta(days=730))).sum())
        china = a["operator"].str.contains("China")
        return {"by_operator": [{"operator": k, "n": int(v), "share": _r(v / len(a), 4)} for k, v in by_op.items()],
                "by_year": {"years": [int(y) for y in by_year.index], "all": [int(v) for v in by_year.values],
                            "starlink": [int(((a["launch"].dt.year == y) & star).sum()) for y in by_year.index]},
                "cumulative": _pts(cum, 0), "cumulative_starlink": _pts(cum_s, 0),
                "kpi": {"active": int(len(a)), "starlink": int(star.sum()), "starlink_share": _r(star.mean(), 4), "china": int(china.sum()),
                        "added_12m": y12, "added_prev": p12, "added_yoy": _r(y12 / p12 - 1, 4) if p12 else None,
                        "operators_1000": int((by_op >= 1000).sum())}}
    subs = starlink_subs()
    out = payload({"active": act, "subs": lambda: _pts(subs / 1e6, 2)}, sources=[CELESTRAK])
    if len(subs):
        last = subs.index[-1]
        ago = _at(subs, last - pd.Timedelta(days=365))
        out["subs_kpi"] = {"date": str(last.date()), "m": _r(subs.iloc[-1] / 1e6, 2), "yoy": _r(subs.iloc[-1] / ago - 1, 4) if ago else None,
                           "m_year_ago": _r(ago / 1e6, 2) if ago else None}
    out["rows"] = rows("starlink")
    out["cited"] = cited("starlink")
    out["as_of"] = str(today.date()) if out.get("active") else (out.get("subs_kpi") or {}).get("date")
    return out


def _industry_now() -> dict:
    px, errs = {}, {}
    for s in TICKERS:
        try:
            px[s] = nasdaq(s)
        except Exception as e:
            errs[s] = type(e).__name__

    def rebased():
        if not px:
            raise LookupError("Nasdaq: " + ", ".join(f"{k} {v}" for k, v in errs.items()))
        d = pd.DataFrame(px).sort_index().ffill()
        d = d[d.index >= d.dropna().index[0]] if len(d.dropna()) else d
        return {k: _pts(100 * d[k] / d[k].dropna().iloc[0], 2) for k in d}

    def stats():
        out = {}
        for k, s in px.items():
            def ret(days):
                ago = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
                return _r(s.iloc[-1] / ago.iloc[-1] - 1, 4) if len(ago) else None
            ma = s.rolling(200).mean()
            out[k] = {"date": str(s.index[-1].date()), "close": _r(s.iloc[-1], 2), "r1y": ret(365), "r3y": ret(1096), "from_peak": _r(s.iloc[-1] / s.max() - 1, 4),
                      "peak_date": str(s.idxmax().date()), "vs_200d": _r(s.iloc[-1] / ma.iloc[-1] - 1, 4) if pd.notna(ma.iloc[-1]) else None}
        b = [out[k]["r1y"] for k in BASKET if k in out and out[k]["r1y"] is not None]
        out["basket"] = {"r1y": _r(float(np.mean(b)), 4) if b else None, "n": len(b)}
        return out
    eco = {}
    for r in rows("economy"):
        v = _f(r.get("value"))
        if v is not None:
            eco.setdefault(r["series"], {})[pd.Timestamp(r["date"])] = v
    eco = {k: pd.Series(v, dtype=float).sort_index() for k, v in eco.items()}
    out = payload({"rebased": rebased, "stats": stats, "economy": lambda: {k: _pts(v, 1) for k, v in eco.items()}}, sources=nasdaq_urls())
    g = eco.get("Global space economy (Space Foundation USD bn)")
    if g is not None and len(g) > 1:
        y5 = g[g.index <= g.index[-1] - pd.DateOffset(years=5)]
        out["eco_kpi"] = {"date": str(g.index[-1].date()), "bn": _r(g.iloc[-1], 0), "yoy": _r(g.iloc[-1] / g.iloc[-2] - 1, 4),
                          "cagr5": _r((g.iloc[-1] / y5.iloc[-1]) ** (1 / 5) - 1, 4) if len(y5) else None}
    out["missing"] = errs
    out["rows"] = rows("economy")
    out["cited"] = cited("economy")
    out["as_of"] = max((str(s.index[-1].date()) for s in px.values()), default=(out.get("eco_kpi") or {}).get("date"))
    return out


UK_SITES = ("SaxaVord", "Spaceport Cornwall", "Sutherland", "Prestwick", "Snowdonia")


def _uk_soil(r: dict) -> bool:
    return any(x.lower() in (r.get("site") or "").lower() for x in UK_SITES)


def _ukhk_now() -> dict:
    ms = rows("milestones")

    def china():
        L = launches()
        this = _now().year
        c = L[L["country"] == "China"]
        top = c[c["year"] >= this - 3].groupby("provider").size().sort_values(ascending=False).head(6).index
        yrs = list(range(2010, this))
        lines = {p: _pts(pd.Series([int(((c["provider"] == p) & (c["year"] == y)).sum()) for y in yrs], index=[_year(y) for y in yrs]), 0) for p in top}
        state = c["provider"].str.contains("CASC|CALT|SAST|PLA", case=False, regex=True)
        com = [int(((~state) & (c["year"] == y)).sum()) for y in yrs]
        uk = L[L["country"] == "UK"]
        return {"providers": lines, "commercial": _pts(pd.Series(com, index=[_year(y) for y in yrs]), 0),
                "kpi": {"last_year": this - 1, "total": int((c["year"] == this - 1).sum()), "commercial": com[-1] if com else None,
                        "commercial_prev": com[-2] if len(com) > 1 else None, "ytd": int((c["year"] == this).sum())},
                "uk_attempts": [{"date": str(r["date"].date()), "provider": r["provider"], "vehicle": r["vehicle"], "success": bool(r["success"])} for _, r in uk.iterrows()]}
    out = payload({"china": china}, sources=[GCAT_LAUNCH])
    out["milestones"] = list(reversed(ms))
    uk = [r for r in ms if r.get("place") == "UK" and r.get("kind") == "launch"]
    out["uk_launches"] = uk
    last_uk = uk[-1] if uk else None
    out["uk_kpi"] = {"attempts": len(uk), "successes": sum(1 for r in uk if r.get("outcome") == "success"),
                     "from_uk_soil": sum(1 for r in uk if _uk_soil(r)),
                     "uk_soil_ok": sum(1 for r in uk if _uk_soil(r) and r.get("outcome") == "success"),
                     "last": last_uk["date"] if last_uk else None, "last_event": last_uk["event"] if last_uk else None,
                     "days_since": int((_now() - pd.Timestamp(last_uk["date"])).days) if last_uk else None}
    out["cited"] = cited("milestones")
    out["as_of"] = ms[-1]["date"] if ms else None
    return out


# ------------------------------------------------------------------ the answer and READINGS
def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


def checklist(got) -> list[dict]:
    """Signs that orbit is routine infrastructure, each met (True), not yet (False) or unknown (None) from the cached tabs."""
    L = ((got("launches").get("launches") or {}).get("kpi")) or {}
    C = got("cost").get("kpi") or {}
    S = (got("satellites").get("active") or {}).get("kpi") or {}
    SK = got("satellites").get("subs_kpi") or {}
    U = got("ukhk").get("uk_kpi") or {}
    sec = L.get("second") or {}

    def chk(key, label, value, ok, target):
        return {"key": key, "label": label, "value": value, "met": None if value is None else bool(ok), "target": target}
    return [chk("daily", "A launch a day worldwide (last 12 months)", L.get("r12"), (L.get("r12") or 0) >= 365, "365+"),
            chk("cheap", "Cheapest flown cost to LEO (USD/kg)", C.get("best"), (C.get("best") or 1e9) < 1000, "under $1,000"),
            chk("second", "A second provider flying weekly (last 12 months)", sec.get("n"), (sec.get("n") or 0) >= 52, "52+ besides SpaceX"),
            chk("fleet", "Active satellites", S.get("active"), (S.get("active") or 0) >= 10000, "10,000+"),
            chk("subs", "Starlink subscribers (millions)", SK.get("m"), (SK.get("m") or 0) >= 10, "10m+"),
            chk("uk", "Successful orbital launches from UK soil", U.get("uk_soil_ok"), (U.get("uk_soil_ok") or 0) >= 1, "at least one")]


def readings(got) -> list[dict]:
    """Each tab's headline indicators from the tab payloads (got(name) -> payload or {}). lean +1 = faster growth or cheaper access."""
    out = []

    def add(tab, key, label, value, lean, note):
        if value is not None:
            out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": lean, "note": note})
    L = ((got("launches").get("launches") or {}).get("kpi")) or {}
    add("launches", "orbital_12m", "Orbital launch attempts, last 12 months", L.get("r12"), _band(L.get("r12_yoy"), -0.05, 0.05),
        "+1 when up more than 5% on the 12 months before, -1 when down more than 5%")
    if L.get("china_prev"):
        d = L["china_12"] / L["china_prev"] - 1
        add("launches", "china_12m", "China orbital launches, last 12 months", L.get("china_12"), _band(d, -0.05, 0.05), "+1 when up more than 5% on the 12 months before")
    if L.get("nonspx_prev"):
        d = L["nonspx_12"] / L["nonspx_prev"] - 1
        add("launches", "non_spacex_12m", "Launches by everyone but SpaceX, last 12 months", L.get("nonspx_12"), _band(d, -0.05, 0.05),
            "+1 when up more than 5% on the 12 months before: access is widening beyond one firm")
    M = ((got("launches").get("mass") or {}).get("kpi")) or {}
    add("launches", "mass", f"Payload mass launched to orbit, {M.get('year')} (tonnes)", M.get("tonnes"), _band(M.get("yoy"), -0.05, 0.10),
        "+1 when up more than 10% on the year before, -1 when down more than 5%")
    C = got("cost").get("kpi") or {}
    if C.get("recent_best") is not None and C.get("older_best"):
        d = C["recent_best"] / C["older_best"] - 1
        add("cost", "cost_frontier", "Cheapest flown cost to LEO, vehicles first flown in the last 10 years (USD/kg)", C["recent_best"], _band(-d, -0.05, 0.20),
            "+1 when at least 20% cheaper than the best older vehicle, -1 when dearer")
    add("cost", "cost_10y", "Cheapest flown cost to LEO now vs 10 years ago (change)", C.get("fall_10y"), _band(-(C.get("fall_10y") or 0), -0.01, 0.25),
        "+1 when at least 25% cheaper than 10 years ago")
    S = (got("satellites").get("active") or {}).get("kpi") or {}
    add("satellites", "active", "Active satellites (CelesTrak)", S.get("active"), _band(S.get("added_yoy"), -0.05, 0.05),
        "+1 when the still-active satellites launched in the last 12 months outnumber the 12 months before by 5%")
    add("satellites", "starlink_share", "Starlink share of active satellites", S.get("starlink_share"), 1 if (S.get("starlink_share") or 1) < 0.5 else 0,
        "+1 when below half (more operators), 0 otherwise: concentration is not a lean against growth")
    SK = got("satellites").get("subs_kpi") or {}
    add("satellites", "starlink_subs", f"Starlink subscribers, {SK.get('date')} (millions)", SK.get("m"), _band(SK.get("yoy"), 0.20, 0.50),
        "+1 when up more than 50% on a year earlier, -1 when under 20%")
    I = got("industry")
    E = I.get("eco_kpi") or {}
    add("industry", "economy", f"Global space economy, {str(E.get('date', ''))[:4]} (USD bn, Space Foundation)", E.get("bn"), _band(E.get("yoy"), 0, 0.05),
        "+1 when up more than 5% on the year before, -1 when it shrank")
    st = I.get("stats") or {}
    b, spy = (st.get("basket") or {}).get("r1y"), (st.get("SPY") or {}).get("r1y")
    if b is not None and spy is not None:
        add("industry", "stocks_vs_spy", "Space stocks (RKLB, ASTS, IRDM, PL) 1-year return minus SPY's (points)", _r(100 * (b - spy), 1), _band(b - spy, -0.05, 0.05),
            "+1 when the basket beat the S&P 500 by 5 points over a year")
    u = st.get("UFO") or {}
    if u.get("vs_200d") is not None:
        add("industry", "ufo_200d", "UFO space ETF vs its 200-day average (%)", _r(100 * u["vs_200d"], 1), _band(u["vs_200d"], -0.02, 0.02), "+1 more than 2% above, -1 more than 2% below")
    H = got("ukhk")
    U = H.get("uk_kpi") or {}
    if U.get("days_since") is not None:
        add("ukhk", "uk_last_attempt", f"Days since the last UK orbital launch attempt ({U.get('last')})", U["days_since"], 1 if U["days_since"] <= 365 else 0,
            "+1 when a UK attempt happened in the last year, 0 otherwise")
    K = (H.get("china") or {}).get("kpi") or {}
    if K.get("commercial_prev"):
        d = K["commercial"] / K["commercial_prev"] - 1
        add("ukhk", "china_commercial", f"China commercial (non-CASC) launches, {K.get('last_year')}", K.get("commercial"), _band(d, -0.05, 0.10),
            "+1 when up more than 10% on the year before")
    met = [c for c in checklist(got) if c["met"] is not None]
    if met:
        n = sum(c["met"] for c in met)
        add("launches", "routine", f"Routine-infrastructure checklist: signs met (of {len(met)})", n, 1 if n * 2 > len(met) else 0,
            "+1 when more than half of the signs are met")
    return out


def READINGS() -> list[dict]:
    """Each tab's indicators as they read now, from the cached tab payloads only (nothing is fetched)."""
    return readings(_cached_payload)


def _answer_now() -> dict:
    """Not a tab: the checklist on its own, built from the tab payloads (each cached; a tab that fails counts as unknown)."""
    def got(name):
        try:
            return ENDPOINTS[name]() or {}
        except Exception:
            return {}
    return {"checklist": checklist(got)}


def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, size, start of body), for checking the parsers against the live
    layouts. Read it with Actions > show-json on /api/space/layout."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    b = pd.Timestamp.now().strftime("%Y-%m-%d")
    # CelesTrak is left out: it answers 403 to repeat downloads, and the Satellites tab already shows whether it answers
    urls = {"gcat launch": GCAT_LAUNCH, "gcat orgs": GCAT_ORGS, "gcat satcat": GCAT_SATCAT,
            "nasdaq RKLB": NASDAQ.format(sym="RKLB", cls="stocks", a="2026-09-01", b=b), "nasdaq UFO": NASDAQ.format(sym="UFO", cls="etf", a="2026-09-01", b=b)}

    def one(item):
        k, u = item
        h = {**B.UA, **(NASDAQ_HEADERS if "nasdaq" in k else {})}
        try:
            r = requests.get(u, headers=h, timeout=40, stream=True)
            head = r.raw.read(1200, decode_content=True).decode("utf-8", "replace")
            r.close()
            return k, {"status": r.status_code, "type": r.headers.get("content-type", ""), "length": r.headers.get("content-length"), "start": head}
        except Exception as e:
            return k, {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(one, urls.items()))


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"launches": _cached_ep("launches", _launches_now), "cost": _cached_ep("cost", _cost_now, 600), "satellites": _cached_ep("satellites", _satellites_now),
             "industry": _cached_ep("industry", _industry_now), "ukhk": _cached_ep("ukhk", _ukhk_now), "answer": lambda: _answer_now(),
             "layout": _cached_ep("layout", _layout_now, 1800)}
