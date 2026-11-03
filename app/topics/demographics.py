"""Demographics & Ageing (/demographics): who pays for pensions in 2045, and which of the US, UK, Hong Kong and China shrinks fastest.

births     total fertility rate 1950-2100 (UN WPP 2024, estimates then the medium projection) against each agency's own latest TFR
           (CDC NCHS, ONS, C&SD; hand-entered: data/demographics/tfr.csv), and births per year from the national statistics offices
           (CDC NCHS, ONS, C&SD, NBS; hand-entered: births.csv), indexed to 2019
ageing     old-age dependency (people 65+ per 100 aged 15-64) and median age, 1950-2100 (UN WPP 2024; the World Bank's projections
           to 2050 stand in when the WPP age file cannot be read), and the national projections (hand-entered: projections.csv)
migration  net migration per 1,000 people, 1950-2100 (UN WPP), and the national counts: ONS LTIM, Census Bureau, C&SD net movement
           and one-way permit holders (hand-entered: migration.csv)
workforce  people aged 15-64, 1950-2100 (UN WPP, index 2025 = 100), labour force participation (World Bank, ILO modelled estimates)
           and people aged 15-64 per person 65+
pensions   public pension spending as a share of GDP where it is published (OBR, CBO; hand-entered: pensions.csv), and the answer card:
           workers per pensioner in 2025 and 2045 and how fast each working-age population shrinks

The two UN WPP files are large (the age file is tens of MB); each is streamed once a month, reduced to the four places, and the
reduction kept on the snapshot volume, so the server never holds a whole file. World Bank JSON goes through fetch() like any source.
"""
from __future__ import annotations

import hashlib
import time

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from ._base import DAY, _pts, _r, fetch_json, manual, manual_rows, manual_sources, payload

SLUG = "demographics"
TOPIC = Topic(SLUG, "Demographics & Ageing",
              "Births, ageing, migration, workers and pension costs in the US, UK, Hong Kong and China, 1950 to 2100: who pays for pensions in 2045, and which shrinks fastest.",
              "demographics", (("births", "Births"), ("ageing", "Ageing"), ("migration", "Migration"), ("workforce", "Workforce"), ("pensions", "Pensions")),
              ("births", "ageing", "migration", "workforce", "pensions"), icon="people", order=60)

PLACES = {"USA": "US", "GBR": "UK", "HKG": "Hong Kong", "CHN": "China"}       # WPP's "China" is the mainland (no HK, Macao or Taiwan)
WPP_DIR = "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/"
WPP_IND = WPP_DIR + "WPP2024_Demographic_Indicators_Medium.csv.gz"
WPP_AGE = WPP_DIR + "WPP2024_PopulationByAge5GroupSex_Medium.csv.gz"
WB = "https://api.worldbank.org/v2/country/USA;GBR;HKG;CHN/indicator/{ind}?format=json&per_page=20000&date=1960:2100{src}"
WPP_TTL = 30 * DAY                    # a WPP revision comes every two years; a month between checks is plenty
SOURCES = [{"name": "UN World Population Prospects 2024 (estimates 1950-2023, medium projection to 2100)", "url": "https://population.un.org/wpp/downloads", "cadence": "every two years"},
           {"name": "World Bank WDI and Population Estimates and Projections (API)", "url": "https://data.worldbank.org/", "cadence": "yearly"},
           {"name": "CDC NCHS, ONS, HK C&SD, NBS China, OBR, CBO, US Census Bureau (hand-entered, cited per row)", "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/demographics",
            "cadence": "as published"}]
NOTES = ("UN WPP 2024 is the one source that covers all four places the same way from 1950 to 2100: lines are estimates to 2023 and the UN's medium "
         "projection after (dashed). The national figures (CDC, ONS, C&SD, NBS) are the agencies' own and can differ from the UN's: the UK series from ONS "
         "is England and Wales, and the UN's China excludes Hong Kong, Macao and Taiwan. Rows marked 'verify' were entered from memory or press reports.")
CUT = 2023                            # last WPP 2024 estimate year; later years are the projection


def _ts(year: int) -> int:
    return int(pd.Timestamp(f"{int(year)}-07-01").timestamp())


def _annual(s: pd.Series) -> pd.Series:
    """{year: v} -> Series on 1 July of each year, the date every annual point on this page uses."""
    s = s.dropna()
    return pd.Series(s.values, index=pd.to_datetime([f"{int(y)}-07-01" for y in s.index]), dtype=float)


# ------------------------------------------------------------------ UN WPP: stream, reduce, keep the reduction
def _open(url: str):
    """The decompressed CSV as a binary stream (requests streams, gzip decompresses as pandas reads)."""
    import gzip
    import requests
    r = requests.get(url, headers=B.UA, timeout=300, stream=True)
    r.raise_for_status()
    return gzip.GzipFile(fileobj=r.raw)


def _read(url: str, cols: list[str]) -> pd.DataFrame:
    """Rows for the four places, only `cols` (+ ISO3_code, Time); read in chunks so the full file is never in memory."""
    want = {"ISO3_code", "Time", *cols}
    parts = []
    with _open(url) as fh:
        for ch in pd.read_csv(fh, usecols=lambda c: c in want, chunksize=200_000, encoding="latin-1", low_memory=False):
            if "ISO3_code" not in ch or "Time" not in ch:
                raise ValueError("WPP layout changed: no ISO3_code/Time column")
            parts.append(ch[ch["ISO3_code"].isin(PLACES)])
    d = pd.concat(parts) if parts else pd.DataFrame()
    if d.empty:
        raise ValueError("WPP: none of the four places found")
    return d


def reduce_indicators(d: pd.DataFrame) -> pd.DataFrame:
    keep = [c for c in ("TFR", "Births", "MedianAgePop", "NetMigrations", "CNMR", "TPopulation1July", "CBR") if c in d]
    if "TFR" not in keep or "MedianAgePop" not in keep:
        raise ValueError("WPP indicators layout changed")
    d = d[["ISO3_code", "Time", *keep]].copy()
    d["Time"] = pd.to_numeric(d["Time"], errors="coerce")
    return d.dropna(subset=["Time"]).drop_duplicates(["ISO3_code", "Time"], keep="last").sort_values(["ISO3_code", "Time"])


def reduce_ages(d: pd.DataFrame) -> pd.DataFrame:
    """Five-year age groups -> per place and year: children (0-14), working age (15-64), 65+ and total, in thousands."""
    if not {"AgeGrpStart", "PopTotal"} <= set(d.columns):
        raise ValueError("WPP age layout changed")
    d = d.assign(Time=pd.to_numeric(d["Time"], errors="coerce"), a=pd.to_numeric(d["AgeGrpStart"], errors="coerce"),
                 p=pd.to_numeric(d["PopTotal"], errors="coerce")).dropna(subset=["Time", "a", "p"])
    d["band"] = pd.cut(d["a"], [-1, 14, 64, 1000], labels=["p0_14", "p15_64", "p65"])
    out = d.pivot_table(index=["ISO3_code", "Time"], columns="band", values="p", aggfunc="sum", observed=False).reset_index()
    out.columns.name = None
    out["total"] = out[["p0_14", "p15_64", "p65"]].sum(axis=1)
    return out


def wpp(url: str, cols: list[str], reducer) -> pd.DataFrame:
    """The reduced WPP table for `url`. Downloaded at most every WPP_TTL; between downloads (and when the UN site is down) the reduction
    kept in the snapshot folder is served, marked stale in the second case. Reported in /api/health like every fetch()."""
    def go():
        snap = B.SNAP_DIR / f"wpp-{hashlib.sha1(url.encode()).hexdigest()[:16]}.csv"
        h = B.HEALTH.setdefault(url, {"module": "demographics", "ok": None, "fail": None, "error": None})
        if snap.exists() and time.time() - snap.stat().st_mtime < WPP_TTL:
            h["ok"] = h["ok"] or snap.stat().st_mtime
            return pd.read_csv(snap)
        try:
            d = reducer(_read(url, cols))
            B.SNAP_DIR.mkdir(parents=True, exist_ok=True)
            d.to_csv(snap, index=False)
            B.STALE.pop(url, None)
            h.update(ok=time.time(), error=None)
            return d
        except Exception as e:
            h.update(fail=time.time(), error=f"{type(e).__name__}: {str(e)[:160]}")
            if snap.exists():
                B.STALE[url] = snap.stat().st_mtime
                return pd.read_csv(snap)
            raise
    from ..cache import _cached
    return _cached(f"topic:{SLUG}:wpp:{url}", DAY, go)


def indicators() -> pd.DataFrame:
    return wpp(WPP_IND, ["TFR", "Births", "MedianAgePop", "NetMigrations", "CNMR", "TPopulation1July", "CBR"], reduce_indicators)


def ages() -> pd.DataFrame:
    return wpp(WPP_AGE, ["AgeGrpStart", "PopTotal"], reduce_ages)


def by_place(d: pd.DataFrame, col: str) -> dict[str, pd.Series]:
    """{"US": Series(year -> value), ...} in PLACES order."""
    out = {}
    for iso, name in PLACES.items():
        x = d[d["ISO3_code"] == iso]
        if col in x and len(x):
            out[name] = pd.Series(pd.to_numeric(x[col], errors="coerce").values, index=x["Time"].astype(int).values).dropna()
    return out


def split(s: pd.Series, d: int = 3) -> tuple[list, list]:
    """Estimates (to CUT) and projection (from CUT, so the dashed line joins the solid one) as chart points."""
    a = _annual(s)
    return _pts(a[a.index.year <= CUT], d), _pts(a[a.index.year >= CUT], d)


# ------------------------------------------------------------------ World Bank API
def parse_wb(j) -> dict[str, pd.Series]:
    """World Bank v2 JSON ([meta, rows]) -> {"US": Series(year -> value)}."""
    rows = j[1] if isinstance(j, list) and len(j) > 1 and isinstance(j[1], list) else []
    if not rows:
        raise ValueError("World Bank: no rows" + (f" ({j[0].get('message')})" if isinstance(j, list) and j and isinstance(j[0], dict) and j[0].get("message") else ""))
    out: dict[str, dict] = {}
    for r in rows:
        iso = r.get("countryiso3code") or (r.get("country") or {}).get("id")
        if iso in PLACES and r.get("value") is not None and str(r.get("date", "")).isdigit():
            out.setdefault(PLACES[iso], {})[int(r["date"])] = float(r["value"])
    return {k: pd.Series(v).sort_index() for k, v in out.items()}


def wb(ind: str, source: int | None = None) -> dict[str, pd.Series]:
    url = WB.format(ind=ind, src=f"&source={source}" if source else "")
    return parse_wb(fetch_json(url, DAY, min_bytes=200))


def wb_urls(*pairs) -> list[str]:
    return [WB.format(ind=i, src=f"&source={s}" if s else "") for i, s in pairs]


# ------------------------------------------------------------------ hand-entered
def hand(name: str) -> dict[str, pd.Series]:
    m = manual(SLUG, name)
    return m if isinstance(m, dict) else {}


def rows(name: str) -> list[dict]:
    return sorted(manual_rows(SLUG, name), key=lambda r: (r.get("series", ""), r["date"]))


def index_to(s: pd.Series, year: int) -> pd.Series:
    base = s[s.index.year == year]
    return s / base.iloc[0] * 100 if len(base) and base.iloc[0] else pd.Series(dtype=float)


def at(s: pd.Series, year: int):
    """Value in `year` from a year-indexed series, or None."""
    return _r(s.get(year), 3) if s is not None and year in s.index else None


# ------------------------------------------------------------------ endpoints
def _births_now() -> dict:
    def tfr():
        t = by_place(indicators(), "TFR")
        return {k: dict(zip(("est", "proj"), split(v))) for k, v in t.items()}

    def wpp_births():
        b = by_place(indicators(), "Births")                # thousands
        return {k: dict(zip(("est", "proj"), split(v, 1))) for k, v in b.items()}
    nat = hand("births")
    out = payload({"tfr": tfr, "wpp_births": wpp_births,
                   "national": lambda: {k: _pts(v, 0) for k, v in nat.items()},
                   "national_index": lambda: {k: _pts(index_to(v, 2019), 1) for k, v in nat.items() if len(index_to(v, 2019))},
                   "national_tfr": lambda: {k: _pts(v, 3) for k, v in hand("tfr").items()}}, sources=[WPP_IND])
    out["latest"] = {k: {"date": str(v.index[-1].date()), "value": _r(v.iloc[-1], 0),
                         "vs_2019": _r(v.iloc[-1] / v[v.index.year == 2019].iloc[0] - 1, 4) if (v.index.year == 2019).any() else None}
                     for k, v in nat.items() if len(v)}
    out["latest_tfr"] = {k: {"date": str(v.index[-1].date()), "value": _r(v.iloc[-1], 3)} for k, v in hand("tfr").items() if len(v)}
    out["rows"] = rows("births") + rows("tfr")
    out["cited"] = (manual_sources(SLUG, "births") + manual_sources(SLUG, "tfr"))[:8]
    out["as_of"] = max([x["date"] for x in out["latest"].values()], default=None)
    return out


def dependency() -> tuple[dict[str, pd.Series], str]:
    """Old-age dependency (65+ per 100 aged 15-64) by year: WPP to 2100, else the World Bank's projections to 2050."""
    try:
        a = ages()
        a = a.assign(r=a["p65"] / a["p15_64"] * 100)
        return by_place(a, "r"), "wpp"
    except Exception:
        return wb("SP.POP.DPND.OL", 40), "worldbank"


def working_age() -> tuple[dict[str, pd.Series], str]:
    try:
        return by_place(ages(), "p15_64"), "wpp"             # thousands
    except Exception:
        return {k: v / 1000 for k, v in wb("SP.POP.1564.TO", 40).items()}, "worldbank"


def _ageing_now() -> dict:
    out = payload({"dependency": lambda: _dep_payload(), "median_age": lambda: {k: dict(zip(("est", "proj"), split(v, 1))) for k, v in by_place(indicators(), "MedianAgePop").items()}},
                  sources=[WPP_IND, WPP_AGE, *wb_urls(("SP.POP.DPND.OL", 40))])
    dep = out.get("dependency") or {}
    out["kpi"] = dep.pop("kpi", {}) if dep else {}
    med = by_place(indicators(), "MedianAgePop") if out.get("median_age") else {}
    for k, v in med.items():
        out["kpi"].setdefault(k, {}).update({"median_2025": at(v, 2025), "median_2050": at(v, 2050), "median_2100": at(v, 2100)})
    out["projections"] = rows("projections")
    out["as_of"] = str(CUT) + " (UN WPP 2024 estimates; projections after)"
    return out


def _dep_payload() -> dict:
    d, src = dependency()
    kpi = {k: {"oadr_2025": at(v, 2025), "oadr_2045": at(v, 2045), "oadr_2050": at(v, 2050), "oadr_2100": at(v, 2100)} for k, v in d.items()}
    return {"series": {k: dict(zip(("est", "proj"), split(v, 1))) for k, v in d.items()}, "source": src, "kpi": kpi}


def _migration_now() -> dict:
    out = payload({"rate": lambda: {k: dict(zip(("est", "proj"), split(v, 2))) for k, v in by_place(indicators(), "CNMR").items()},
                   "net": lambda: {k: dict(zip(("est", "proj"), split(v, 1))) for k, v in by_place(indicators(), "NetMigrations").items()},
                   "national": lambda: {k: _pts(v, 0) for k, v in hand("migration").items()}}, sources=[WPP_IND])
    out["rows"] = sorted(manual_rows(SLUG, "migration"), key=lambda r: r["date"], reverse=True)
    out["cited"] = manual_sources(SLUG, "migration")[:8]
    out["as_of"] = out["rows"][0]["date"] if out["rows"] else None
    return out


def _workforce_now() -> dict:
    def wa():
        w, src = working_age()
        idx = {k: v / v.get(2025) * 100 for k, v in w.items() if v.get(2025)}
        return {"index": {k: dict(zip(("est", "proj"), split(v, 1))) for k, v in idx.items()}, "level": {k: _pts(_annual(v), 0) for k, v in w.items()},
                "source": src, "change": {k: {"to_2045": _r(at(v, 2045) / 100 - 1 if at(v, 2045) else None, 4), "to_2050": _r(at(v, 2050) / 100 - 1 if at(v, 2050) else None, 4),
                                               "to_2100": _r(at(v, 2100) / 100 - 1 if at(v, 2100) else None, 4), "now_m": _r((w[k].get(2025) or 0) / 1000, 1)} for k, v in idx.items()}}

    def support():
        d, _ = dependency()
        return {k: dict(zip(("est", "proj"), split(100 / v[v > 0], 2))) for k, v in d.items()}

    def lfpr():
        return {k: _pts(_annual(v), 1) for k, v in wb("SL.TLF.CACT.ZS").items()}

    def lfpr_1564():
        return {k: _pts(_annual(v), 1) for k, v in wb("SL.TLF.ACTI.ZS").items()}
    out = payload({"working_age": wa, "support": support, "lfpr": lfpr, "lfpr_1564": lfpr_1564},
                  sources=[WPP_AGE, *wb_urls(("SL.TLF.CACT.ZS", None), ("SL.TLF.ACTI.ZS", None), ("SP.POP.1564.TO", 40), ("SP.POP.DPND.OL", 40))])
    lf = out.get("lfpr") or {}
    out["as_of"] = max((pd.Timestamp(v[-1][0], unit="s").strftime("%Y") for v in lf.values() if v), default=None)
    return out


def answer() -> dict:
    """The page's question in numbers: people 15-64 per person 65+ in 2025 and 2045, the change in working-age people, and the
    pension bill in 2045 where an agency projects one; ranked by how fast the working-age population shrinks to 2045."""
    d, src = dependency()
    w, _ = working_age()
    pen = hand("pensions")
    out = []
    for k in PLACES.values():
        dep, wk = d.get(k), w.get(k)
        r25, r45 = at(dep, 2025) if dep is not None else None, at(dep, 2045) if dep is not None else None
        w25, w45 = at(wk, 2025) if wk is not None else None, at(wk, 2045) if wk is not None else None
        p = next((v for n, v in pen.items() if n.startswith(k + " ")), None)
        p45 = None
        if p is not None and len(p):
            yrs = pd.Series(p.values, index=p.index.year).groupby(level=0).last()
            if yrs.index.min() <= 2045 <= yrs.index.max():    # a straight line between the published points either side of 2045
                p45 = _r(np.interp(2045, yrs.index, yrs.values), 2)
        out.append({"place": k, "workers_per_65_2025": _r(100 / r25, 2) if r25 else None, "workers_per_65_2045": _r(100 / r45, 2) if r45 else None,
                    "oadr_2025": r25, "oadr_2045": r45, "working_age_2025_m": _r(w25 / 1000, 2) if w25 else None, "working_age_2045_m": _r(w45 / 1000, 2) if w45 else None,
                    "working_age_change": _r(w45 / w25 - 1, 4) if w25 and w45 else None, "pension_2045": p45})
    out.sort(key=lambda r: (r["working_age_change"] is None, r["working_age_change"] or 0))
    return {"rows": out, "source": src}


def _pensions_now() -> dict:
    pen = hand("pensions")
    out = payload({"series": lambda: {k: _pts(v, 2) for k, v in pen.items()}, "answer": answer}, sources=[WPP_AGE, WPP_IND, *wb_urls(("SP.POP.DPND.OL", 40), ("SP.POP.1564.TO", 40))])
    out["rows"] = sorted(manual_rows(SLUG, "pensions"), key=lambda r: (r["series"], r["date"]))
    out["cited"] = manual_sources(SLUG, "pensions")[:8]
    now = pd.Timestamp.now()
    past = [r["date"] for r in out["rows"] if pd.Timestamp(r["date"]) <= now]
    out["as_of"] = max(past, default=None)
    return out


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"births": _cached_ep("births", _births_now), "ageing": _cached_ep("ageing", _ageing_now), "migration": _cached_ep("migration", _migration_now),
             "workforce": _cached_ep("workforce", _workforce_now), "pensions": _cached_ep("pensions", _pensions_now)}


# ------------------------------------------------------------------ what changed since yesterday
def _band(v, good, bad, higher_is_good=True):
    """+1 past `good`, -1 past `bad`, 0 between."""
    if v is None:
        return 0
    if higher_is_good:
        return 1 if v >= good else -1 if v <= bad else 0
    return 1 if v <= good else -1 if v >= bad else 0


def _step(pts):
    """+1 / -1 / 0: the direction of the last move in a [[ts, v], ...] series."""
    vals = [p[1] for p in pts or [] if p[1] is not None]
    return 0 if len(vals) < 2 or vals[-1] == vals[-2] else 1 if vals[-1] > vals[-2] else -1


def readings_for(tab: str, d: dict) -> list[dict]:
    """Headline readings of one tab's payload. Lean: +1 easier to pay for pensions (more births, workers, inflows; fewer pensioners per
    worker; a smaller pension bill), -1 harder, 0 in between (thresholds in data/demographics/README.md)."""
    out = []

    def add(key, label, value, lean, note=None):
        if value is not None:
            out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": lean, **({"note": note} if note else {})})
    if tab == "births":
        for k, pts in (d.get("national_tfr") or {}).items():
            if pts:
                add(f"tfr:{k}", f"{k}: fertility rate, official ({pd.Timestamp(pts[-1][0], unit='s').year})", pts[-1][1], _step(pts), "lean: direction since the previous official figure")
    elif tab == "ageing":
        for k, v in (d.get("kpi") or {}).items():
            add(f"oadr2045:{k}", f"{k}: people 65+ per 100 aged 15–64 in 2045", v.get("oadr_2045"), _band(v.get("oadr_2045"), 35, 50, higher_is_good=False))
    elif tab == "migration":
        for k, pts in (d.get("national") or {}).items():
            if pts and "natural change" not in k:
                add(f"net:{k}", f"{k}, 12 months to {pd.Timestamp(pts[-1][0], unit='s').date()}", pts[-1][1], _step(pts), "lean: direction since the previous figure")
    elif tab == "workforce":
        for k, v in ((d.get("working_age") or {}).get("change") or {}).items():
            add(f"wa2045:{k}", f"{k}: change in people aged 15–64, 2025 to 2045", v.get("to_2045"), _band(v.get("to_2045"), 0.02, -0.02))
    elif tab == "pensions":
        rows = (d.get("answer") or {}).get("rows") or []
        known = [r for r in rows if r.get("working_age_change") is not None]
        if known:
            add("fastest_shrinking", "Working-age population shrinking fastest to 2045", known[0]["place"], 0)
        for r in rows:
            add(f"pension2045:{r['place']}", f"{r['place']}: public pension spend in 2045, % GDP", r.get("pension_2045"), _band(r.get("pension_2045"), 5, 7, higher_is_good=False))
    return out


def READINGS() -> list[dict]:
    """Each tab's readings from the payloads the endpoints already cached; a tab not computed yet is left out, never downloaded here."""
    from ..cache import _cache
    rows = []
    for t, _ in TOPIC.tabs:
        hit = _cache.get(f"topic:{SLUG}:{t}")
        if hit and isinstance(hit[1], dict):
            rows += readings_for(t, hit[1])
    return rows


# ------------------------------------------------------------------ signals (the owner's watch points: data/signals/watchlist.json)
def _tab(t: str) -> dict:
    from ..cache import _cache
    hit = _cache.get(f"topic:{SLUG}:{t}")
    return hit[1] if hit and isinstance(hit[1], dict) else {}


def _last(pts):
    return pts[-1] if pts else None


def SIGNALS() -> list[dict]:
    """One row per approved key, read only from the cached tab payloads; a key whose tab is not computed yet is left out."""
    out = []
    b = _tab("births")
    if b:
        tfr, src = {}, {}
        for k in PLACES.values():
            p = _last((b.get("national_tfr") or {}).get(k))
            if p and pd.Timestamp(p[0], unit="s").year >= CUT:          # an official rate from the last few years
                tfr[k], src[k] = p[1], f"official {pd.Timestamp(p[0], unit='s').year}"
            else:                                                       # China publishes no annual rate: the UN's latest estimate
                p = _last(((b.get("tfr") or {}).get(k) or {}).get("est"))
                if p:
                    tfr[k], src[k] = p[1], f"UN estimate {pd.Timestamp(p[0], unit='s').year}"
        if tfr:
            low = [k for k, v in tfr.items() if v < 1.0]
            hk = tfr.get("Hong Kong") is not None and tfr["Hong Kong"] < 0.7
            crossed = bool(low) or hk
            out.append({"key": "tfr", "tab": "births", "label": "Total fertility rate, children per woman",
                        "value": " · ".join(f"{'HK' if k == 'Hong Kong' else k} {v:.2f}" for k, v in tfr.items()),
                        "lean": -1 if crossed else 0, "watch": "any below 1.0; HK below 0.7", "crossed": crossed,
                        "note": "; ".join(f"{k}: {s}" for k, s in src.items()) + (f". Below 1.0: {', '.join(low)}" if low else "")})
    p = _tab("pensions")
    rows = {r["place"]: r for r in (p.get("answer") or {}).get("rows") or []}
    w = {k: rows[k].get("workers_per_65_2045") for k in ("UK", "US") if k in rows and rows[k].get("workers_per_65_2045") is not None}
    if w:
        crossed = any(v < 2.0 for v in w.values())
        out.append({"key": "workers_per_65", "tab": "pensions", "label": "People aged 15–64 per person 65+ in 2045 (UN projection)",
                    "value": " · ".join(f"{k} {v:.2f}" for k, v in w.items()), "lean": -1 if crossed else 0,
                    "watch": "revised below 2.0 for the UK or the US", "crossed": crossed,
                    "note": "UN WPP medium projection; " + ", ".join(f"{k} {rows[k]['workers_per_65_2025']:.2f} in 2025" for k in w if rows[k].get("workers_per_65_2025"))})
    m = (_tab("migration").get("national") or {})
    uk = next((v for k, v in m.items() if k.startswith("UK net migration")), None)
    us = next((v for k, v in m.items() if k.startswith("US net international migration")), None)
    if uk or us:
        u, s = _last(uk), _last(us)
        crossed = bool((u and u[1] < 200_000) or (s and s[1] < 0))
        out.append({"key": "net_migration", "tab": "migration", "label": "Net migration, latest 12 months",
                    "value": " · ".join(x for x in (f"UK {u[1] / 1000:,.0f}k" if u else "", f"US {s[1] / 1e6:,.2f}m" if s else "") if x),
                    "lean": -1 if crossed else _step(uk or us), "watch": "UK below 200k a year; US turns negative", "crossed": crossed,
                    "note": "; ".join(x for x in (f"UK: ONS LTIM, 12 months to {pd.Timestamp(u[0], unit='s').date()}" if u else "",
                                                  f"US: Census, year to {pd.Timestamp(s[0], unit='s').date()}" if s else "") if x)})
    ser = p.get("series") or {}
    ukp = next((v for k, v in ser.items() if k.startswith("UK ")), None)
    if ukp:
        now = time.time()
        future = [x for x in ukp if x[0] > now] or ukp
        top = max(future, key=lambda x: x[1])
        crossed = top[1] > 8
        out.append({"key": "pension_gdp", "tab": "pensions", "label": "UK state pension, % of GDP, highest OBR projection",
                    "value": top[1], "unit": "%", "lean": -1 if crossed else _band(top[1], 5, 7, higher_is_good=False),
                    "watch": "above 8% for the UK", "crossed": crossed,
                    "note": f"OBR projection for {pd.Timestamp(top[0], unit='s').year}; now {ukp[0][1]}% ({pd.Timestamp(ukp[0][0], unit='s').year})"})
    return out
