"""China vs US Tech (/china-us-tech): who leads in each layer of the tech stack, and where is the gap closing?

overview   one row per layer (models, compute, leaderboards, patents, research, EV adoption, batteries, EV makers, chipmaking, export
           controls, chip imports, markets): who leads, by how much, and whether the gap moved towards China (+1) or the US (-1)
models     notable AI models per year by country of the developer, and the largest training run by country (Epoch AI CSV, automated);
           best US vs best Chinese model on the LMArena text leaderboard (hand-entered snapshots: leaderboard.csv)
research   PCT international patent filings by origin (WIPO, hand-entered: pct.csv); AI papers and highly cited AI papers by country
           of the authors' institutions (OpenAlex API, automated); the AI Index count of the 100 most-cited AI papers (top_cited.csv)
ev         electric share of new car sales (IEA Global EV Outlook via Our World in Data, automated; ev_share.csv fills gaps and Hong
           Kong), China's NEV exports (CAAM), BYD vs Tesla battery-electric deliveries and EV battery makers' shares (SNE Research)
chips      China's integrated-circuit imports and exports (GACC, hand-entered yearly), the leading node in volume
           at TSMC vs SMIC, the export-control timeline (US, allies, China's counter-measures) and SMIC/Huawei milestones
markets    an equal-weighted US tech basket against US-listed Chinese tech (ADRs, KWEB) from the Nasdaq quote API, the Hang Seng TECH
           index's yearly return (hstech.csv) and listing notes for London, Hong Kong and New York

Leans: +1 means China gaining relative to the US, -1 the US gaining (see data/china-us-tech/README.md for each reading's rule).
"""
from __future__ import annotations

import time
from io import StringIO

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from ._base import DAY, _pts, _r, fetch, fetch_json, manual, manual_rows, manual_sources, payload

SLUG = "china-us-tech"
TOPIC = Topic(SLUG, "China vs US Tech",
              "Who leads each layer of the tech stack, and where is the gap closing? AI models, patents and research, EVs and batteries, "
              "chips trade and controls, and tech shares, for the US and China, with the UK and Hong Kong alongside.",
              "china_us_tech", (("overview", "Overview"), ("models", "AI models"), ("research", "Patents & research"), ("ev", "EVs & batteries"),
                                ("chips", "Chips trade"), ("markets", "Markets")),
              ("models", "research", "ev", "chips", "markets"), icon="globe")

EPOCH = "https://epoch.ai/data/notable_ai_models.csv"
OWID = "https://ourworldindata.org/grapher/{name}.csv?v=1&csvType=full&useColumnShortNames=false"
OWID_SHARE, OWID_SALES = "electric-car-sales-share", "electric-car-sales"
AI_CONCEPT = "C154945302"           # OpenAlex concept: Artificial intelligence
OPENALEX = ("https://api.openalex.org/works?filter=concepts.id:" + AI_CONCEPT + ",institutions.country_code:{cc},publication_year:2005-{y}{extra}"
            "&group_by=publication_year")
NEW_DAYS = 30                       # an export-control row counts as a new rule for this many days after its date
CITED = 100                         # "highly cited": more than this many citations
NASDAQ_HEADERS = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
US_TECH = ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META")
CN_TECH = ("BABA", "PDD", "JD", "BIDU", "NTES")
CN_ETF = "KWEB"
START = "2019-01-01"
OA_COUNTRIES = {"US": "US", "CN": "China", "GB": "UK", "HK": "Hong Kong"}
OWID_NAMES = {"China": "China", "United States": "US", "United Kingdom": "UK", "World": "World"}

SOURCES = [{"name": "Epoch AI: notable AI models", "url": "https://epoch.ai/data/notable-ai-models", "cadence": "weekly"},
           {"name": "LMArena text leaderboard (hand-entered snapshots)", "url": "https://lmarena.ai/leaderboard/text", "cadence": "as entered"},
           {"name": "WIPO PCT Yearly Review (hand-entered)", "url": "https://www.wipo.int/en/web/pct-system/", "cadence": "yearly"},
           {"name": "OpenAlex works API", "url": "https://docs.openalex.org/", "cadence": "daily"},
           {"name": "IEA Global EV Outlook via Our World in Data", "url": "https://ourworldindata.org/grapher/electric-car-sales-share", "cadence": "yearly"},
           {"name": "CAAM, SNE Research, BYD and Tesla filings (hand-entered)", "url": "http://en.caam.org.cn/", "cadence": "as published"},
           {"name": "GACC customs statistics (hand-entered)", "url": "http://english.customs.gov.cn/statics/report/monthly.html", "cadence": "yearly"},
           {"name": "BIS, MOFCOM, TechInsights, company announcements (hand-entered)", "url": "https://www.bis.gov/", "cadence": "as events happen"},
           {"name": "Nasdaq quote API (share prices)", "url": "https://www.nasdaq.com/market-activity/stocks/baba", "cadence": "daily"}]
NOTES = ("Leans on this page: +1 = China gaining relative to the US, -1 = the US gaining. Rows marked verify were entered from memory or "
         "from a secondary summary and still need checking against the cited page. Country is where the developer, applicant or author's "
         "institution is based; Hong Kong is shown on its own where the source separates it.")


def _year_pts(s: pd.Series, d: int = 3) -> list[list]:
    """[[year, value]] for svg charts (x is the year, not a date)."""
    s = pd.to_numeric(s, errors="coerce").dropna()
    return [[int(pd.Timestamp(t).year), _r(v, d)] for t, v in s.items()]


def _hand(name: str) -> dict[str, pd.Series]:
    m = manual(SLUG, name)
    return m if isinstance(m, dict) else {}


# ------------------------------------------------------------------ AI models (Epoch AI)
def _country(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    if "Hong Kong" in s:
        return "Hong Kong"
    if s.startswith("United States") or s in ("USA", "US"):
        return "US"
    if s.startswith("China"):
        return "China"
    if s.startswith("United Kingdom") or s == "UK":
        return "UK"
    return "Other"


def _col(d: pd.DataFrame, *words: str) -> str | None:
    return next((c for c in d.columns if all(w in c.lower() for w in words)), None)


def parse_epoch(text: str) -> pd.DataFrame:
    """One row per model and country of its developer (a model from a US and a Chinese lab counts for both)."""
    d = pd.read_csv(StringIO(text), dtype=str)
    date, ctry = _col(d, "publication date"), _col(d, "country")
    if not (date and ctry):
        raise ValueError("Epoch layout changed")
    flop, org, acc = _col(d, "training compute", "flop"), _col(d, "organization"), _col(d, "accessibility")
    x = pd.DataFrame({"model": d[_col(d, "model") or d.columns[0]], "date": pd.to_datetime(d[date], errors="coerce"),
                      "flop": pd.to_numeric(d[flop], errors="coerce") if flop else np.nan, "org": d[org].fillna("") if org else "",
                      "open": d[acc].fillna("").str.lower().str.contains("open weights") if acc else False,
                      "country": d[ctry].fillna("").map(lambda s: sorted({_country(c) for c in s.split(",")} - {""}))})
    x["joint"] = x["country"].map(len) > 1
    x = x.dropna(subset=["date"]).explode("country").dropna(subset=["country"])
    return x.sort_values("date").reset_index(drop=True)


def controls_rows() -> list[dict]:
    """The export-control timeline (data/china-us-tech/controls.csv), oldest first; shared with the AI Model Iteration dashboard."""
    return sorted(manual_rows(SLUG, "controls"), key=lambda r: r["date"])


def leaderboard_rows() -> list[dict]:
    """The dated LMArena copies (data/china-us-tech/leaderboard.csv: best US and best Chinese model per snapshot), oldest first."""
    return sorted(manual_rows(SLUG, "leaderboard"), key=lambda r: r["date"])


def _models_now() -> dict:
    def epoch():
        x = parse_epoch(fetch(EPOCH, DAY, min_bytes=1000))
        x = x[x["date"] <= pd.Timestamp.now()]                              # announced but not yet published
        last_full = pd.Timestamp.now().year - 1
        years = list(range(2015, int(x["date"].dt.year.max()) + 1))
        per = x.groupby([x["date"].dt.year, "country"]).size()
        cnt = {c: [int(per.get((y, c), 0)) for y in years] for c in ("US", "China", "UK", "Hong Kong", "Other")}
        share = [[y, _r(c / (u + c), 4)] for y, u, c in zip(years, cnt["US"], cnt["China"]) if u + c and y <= last_full]   # a partial year swings
        op = x[x["open"]].groupby([x["date"].dt.year, "country"]).size()
        open_cnt = {c: [int(op.get((y, c), 0)) for y in years] for c in ("US", "China")}
        f = x[~x["joint"]].dropna(subset=["flop"]).query("flop > 0")        # a joint US-China model would give both the same maximum
        frontier, top = {}, {}
        for c in ("US", "China", "UK"):
            s = f[f["country"] == c]
            if len(s):
                run = pd.Series(s["flop"].cummax().values, index=s["date"].values).groupby(level=0).max()
                frontier[c] = _pts(run[run.index >= "2012-01-01"], 0)
                top[c] = [{"model": r["model"], "org": r["org"], "date": str(r["date"].date()), "flop": float(r["flop"])}
                          for _, r in s.sort_values("flop", ascending=False).head(5).iterrows()]

        def gap_at(t):
            m = {c: f[(f["country"] == c) & (f["date"] <= t)]["flop"].max() for c in ("US", "China")}
            return _r(np.log10(m["US"] / m["China"]), 2) if all(pd.notna(v) and v > 0 for v in m.values()) else None
        now = f["date"].max() if len(f) else pd.Timestamp.now()
        recent = x[x["date"] > pd.Timestamp.now() - pd.Timedelta(days=365)]
        t12 = {c: int((recent["country"] == c).sum()) for c in ("US", "China", "UK", "Hong Kong")}
        return {"years": years, "counts": cnt, "china_share": share, "trailing_12m": t12, "open": open_cnt, "frontier": frontier, "top": top,
                "gap_oom": gap_at(now), "gap_oom_year_ago": gap_at(now - pd.Timedelta(days=365)), "last_full": last_full,
                "latest": str(x["date"].max().date()), "n": int(x["model"].nunique())}

    def arena():
        rows = sorted(manual_rows(SLUG, "leaderboard"), key=lambda r: r["date"])
        s = _hand("leaderboard")
        us, cn = s.get("US best", pd.Series(dtype=float)), s.get("China best", pd.Series(dtype=float))
        gap = (us - cn).dropna()
        return {"lines": {"Best US model": _pts(us, 0), "Best Chinese model": _pts(cn, 0)}, "gap": _pts(gap, 0), "rows": rows[::-1],
                "cited": manual_sources(SLUG, "leaderboard")[:4]}
    out = payload({"epoch": epoch, "arena": arena}, sources=[EPOCH])
    out["as_of"] = (out.get("epoch") or {}).get("latest")
    return out


# ------------------------------------------------------------------ patents & research
def parse_openalex(j: dict) -> pd.Series:
    """group_by=publication_year -> Series {year (1 January): count}."""
    rows = (j or {}).get("group_by")
    if rows is None:
        raise ValueError("OpenAlex layout changed")
    s = pd.Series({pd.Timestamp(f"{int(r['key'])}-01-01"): int(r["count"]) for r in rows if str(r.get("key", "")).isdigit()}, dtype=float)
    return s.sort_index()


def openalex(cc: str, cited: bool = False) -> pd.Series:
    y = pd.Timestamp.now().year - 1
    url = OPENALEX.format(cc=cc, y=y, extra=f",cited_by_count:>{CITED}" if cited else "")
    return parse_openalex(fetch_json(url, DAY, min_bytes=40))


def _research_now() -> dict:
    pct = _hand("pct")
    errors = {}
    papers, cited = {}, {}
    for cc, name in OA_COUNTRIES.items():
        try:
            papers[name] = openalex(cc)
            cited[name] = openalex(cc, cited=True)
        except Exception as e:
            errors[name] = type(e).__name__

    def cited_share():
        if "US" not in cited or "China" not in cited:
            raise LookupError("OpenAlex not reachable")
        d = pd.DataFrame({"US": cited["US"], "China": cited["China"]}).fillna(0)
        d = d[(d.sum(axis=1) >= 20)]
        return _year_pts(d["China"] / (d["US"] + d["China"]), 4)

    def gap():
        if "China" not in pct or "US" not in pct:
            raise LookupError("no PCT rows")
        return _year_pts((pct["China"] - pct["US"]).dropna(), 0)
    out = payload({"pct": lambda: {k: _year_pts(v, 0) for k, v in pct.items()}, "pct_gap": gap,
                   "papers": lambda: {k: _year_pts(v[v.index >= "2005-01-01"], 0) for k, v in papers.items()} or None,
                   "cited": lambda: {k: _year_pts(v[v.index >= "2005-01-01"], 0) for k, v in cited.items()} or None,
                   "cited_share": cited_share},
                  sources=[OPENALEX.format(cc=c, y=pd.Timestamp.now().year - 1, extra=e) for c in OA_COUNTRIES for e in ("", f",cited_by_count:>{CITED}")])
    out["errors"] = errors
    out["top_cited"] = manual_rows(SLUG, "top_cited")
    out["pct_rows"] = sorted(manual_rows(SLUG, "pct"), key=lambda r: (r["date"], r["series"]), reverse=True)
    out["cited_threshold"] = CITED
    out["as_of"] = B.latest_date(*pct.values()) if pct else None
    return out


# ------------------------------------------------------------------ EVs & batteries
def parse_owid(text: str) -> dict[str, pd.Series]:
    """Our World in Data grapher CSV (Entity, Code, Year, <value>) -> {US/China/UK/World: yearly Series}."""
    d = pd.read_csv(StringIO(text))
    if not {"Entity", "Year"} <= set(d.columns) or len(d.columns) < 4:
        raise ValueError("OWID layout changed")
    val = d.columns[3]
    out = {}
    for ent, name in OWID_NAMES.items():
        s = d[d["Entity"] == ent]
        if len(s):
            out[name] = pd.Series(pd.to_numeric(s[val], errors="coerce").values, index=pd.to_datetime(s["Year"].astype(int).astype(str) + "-01-01")).dropna().sort_index()
    if not out:
        raise ValueError("OWID: none of the countries")
    return out


def _ev_now() -> dict:
    hand = _hand("ev_share")
    try:
        live, ok = parse_owid(fetch(OWID.format(name=OWID_SHARE), DAY, min_bytes=500)), True
    except Exception:
        live, ok = {}, False
    share = {}
    for k in dict.fromkeys([*live, *hand]):
        a, b = live.get(k, pd.Series(dtype=float)), hand.get(k, pd.Series(dtype=float))
        share[k] = pd.concat([a, b[~b.index.isin(a.index)]]).sort_index()

    def sales():
        return {k: _year_pts(v / 1e6, 3) for k, v in parse_owid(fetch(OWID.format(name=OWID_SALES), DAY, min_bytes=500)).items()}
    bt = _hand("byd_tesla")
    rows = manual_rows(SLUG, "battery_share")
    years = sorted({r["date"][:4] for r in rows})
    makers = list(dict.fromkeys(r["series"] for r in rows))
    table = {m: [next((_r(r["value"], 1) for r in rows if r["series"] == m and r["date"][:4] == y), None) for y in years] for m in makers}
    country = {r["series"]: r.get("country", "") for r in rows}
    by_country = {}
    for c in ("China", "Korea", "Japan"):
        by_country[c] = [_r(sum(v[i] or 0 for m, v in table.items() if country.get(m) == c), 1) for i in range(len(years))]
    out = payload({"share": lambda: {k: _year_pts(v, 1) for k, v in share.items()}, "sales": sales,
                   "exports": lambda: _year_pts(manual(SLUG, "ev_exports"), 3),
                   "byd_tesla": lambda: {k: _year_pts(v / 1e6, 3) for k, v in bt.items()}},
                  sources=[OWID.format(name=OWID_SHARE), OWID.format(name=OWID_SALES)])
    out["owid_live"] = ok
    out["battery"] = {"years": years, "makers": table, "country": country, "by_country": by_country}
    out["cited"] = (manual_sources(SLUG, "ev_exports")[:2] + manual_sources(SLUG, "battery_share")[:2] + manual_sources(SLUG, "byd_tesla")[:2])
    out["as_of"] = B.latest_date(*share.values()) if share else None
    return out


# ------------------------------------------------------------------ chips trade, nodes, controls
def node_gap() -> list[dict]:
    """For each node SMIC reached, how many years after TSMC (series TSMC/SMIC, value = node in nm, date = volume production)."""
    s = manual_rows(SLUG, "node_gap")
    tsmc = {float(r["value"]): pd.Timestamp(r["date"]) for r in s if r["series"] == "TSMC"}
    out = []
    for r in sorted((r for r in s if r["series"] == "SMIC"), key=lambda r: r["date"]):
        nm, t = float(r["value"]), pd.Timestamp(r["date"])
        if nm in tsmc:
            out.append({"node": nm, "smic": str(t.date()), "tsmc": str(tsmc[nm].date()), "years": _r((t - tsmc[nm]).days / 365.25, 1), "note": r.get("note", "")})
    return out


def _chips_now() -> dict:
    trade = _hand("ic_trade")
    controls = sorted(manual_rows(SLUG, "controls"), key=lambda r: r["date"], reverse=True)
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365)
    recent = [r for r in controls if pd.Timestamp(r["date"]) >= cutoff and not r["actor"].startswith("China")]
    out = {"trade": {k: _year_pts(v, 1) for k, v in trade.items()},
           "nodes": node_gap(), "controls": controls, "milestones": sorted(manual_rows(SLUG, "milestones"), key=lambda r: r["date"], reverse=True),
           "recent_direction": sum(int(r.get("direction") or 0) for r in recent), "recent_n": len(recent),
           "cited": manual_sources(SLUG, "ic_trade")[:3], "stale": {}, "updated": int(time.time())}
    imp = trade.get("Imports")
    out["imports_yoy"] = _r(imp.iloc[-1] / imp.iloc[-2] - 1, 4) if imp is not None and len(imp) >= 2 else None
    out["as_of"] = max([r["date"] for r in controls + out["milestones"]] + ([str(imp.index[-1].date())] if imp is not None and len(imp) else []), default=None)
    return out


# ------------------------------------------------------------------ markets
def nasdaq(sym: str) -> pd.Series:
    return B.nasdaq_daily(sym, START, lambda *a, **k: fetch_json(*a, **k))


def nasdaq_etf(sym: str) -> pd.Series:
    return B.nasdaq_daily(sym, START, lambda *a, **k: fetch_json(*a, **k), assetclass="etf")


def basket(px: dict[str, pd.Series]) -> pd.Series:
    """Equal-weighted buy and hold from the first day every member trades, rebased to 100."""
    d = pd.DataFrame(px).sort_index().ffill().dropna()
    if d.empty:
        raise LookupError("no common dates")
    return 100 * (d / d.iloc[0]).mean(axis=1)


def _year_returns(s: pd.Series) -> dict[int, float]:
    ye = s.groupby(s.index.year).last()
    return {int(y): _r(ye[y] / ye[y - 1] - 1, 4) for y in ye.index if y - 1 in ye.index}


def _markets_now() -> dict:
    px, errors = {}, {}
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    for sym in US_TECH + CN_TECH:
        try:
            px[sym] = nasdaq(sym)
        except Exception as e:
            errors[sym] = type(e).__name__
    try:
        etf = nasdaq_etf(CN_ETF)
    except Exception as e:
        etf, errors[CN_ETF] = None, type(e).__name__
    us = {k: v for k, v in px.items() if k in US_TECH}
    cn = {k: v for k, v in px.items() if k in CN_TECH}
    b = {}
    if us:
        b["US tech basket"] = basket(us)
    if cn:
        b["China tech ADRs"] = basket(cn)
    if etf is not None and len(b):
        e = etf[etf.index >= max(s.index[0] for s in b.values())]
        b[CN_ETF] = 100 * e / e.iloc[0]

    def ratio():
        r = (b["China tech ADRs"] / b["US tech basket"]).dropna()
        return _pts(100 * r / r.iloc[0], 2)

    def rel_1y():
        r = (b["China tech ADRs"] / b["US tech basket"]).dropna()
        ago = r[r.index <= r.index[-1] - pd.Timedelta(days=365)]
        return _r(r.iloc[-1] / ago.iloc[-1] - 1, 4) if len(ago) else None
    hs = manual(SLUG, "hstech")
    years = {k: _year_returns(v) for k, v in b.items()}
    if isinstance(hs, pd.Series) and len(hs):
        years["Hang Seng TECH"] = {int(t.year): _r(v / 100, 4) for t, v in hs.items()}
    def gap_90d():
        """China basket's 90-day return minus the US basket's, in percentage points."""
        r = {}
        for k in ("China tech ADRs", "US tech basket"):
            s = b[k]
            ago = s[s.index <= s.index[-1] - pd.Timedelta(days=90)]
            r[k] = 100 * (s.iloc[-1] / ago.iloc[-1] - 1) if len(ago) else None
        return None if None in r.values() else {"gap": _r(r["China tech ADRs"] - r["US tech basket"], 1), "china": _r(r["China tech ADRs"], 1), "us": _r(r["US tech basket"], 1)}
    out = payload({"baskets": lambda: {k: _pts(v, 2) for k, v in b.items()} or None, "ratio": ratio, "rel_1y": rel_1y, "gap_90d": gap_90d},
                  sources=[B.NASDAQ.format(sym=s, a=START, b=today) for s in US_TECH + CN_TECH] + [B.NASDAQ_ANY.format(sym=CN_ETF, cls="etf", a=START, b=today)])
    out["years"] = years
    out["last"] = {k: {"v": _r(v.iloc[-1], 1), "y1": _r(v.iloc[-1] / v[v.index <= v.index[-1] - pd.Timedelta(days=365)].iloc[-1] - 1, 4)
                       if (v.index <= v.index[-1] - pd.Timedelta(days=365)).any() else None} for k, v in b.items()}
    out["members"] = {"US tech basket": [s for s in US_TECH if s in px], "China tech ADRs": [s for s in CN_TECH if s in px]}
    out["errors"] = errors
    out["listings"] = sorted(manual_rows(SLUG, "listings"), key=lambda r: r["date"], reverse=True)
    out["as_of"] = B.latest_date(*b.values()) if b else None
    return out


# ------------------------------------------------------------------ layers: overview and READINGS
def _band(x, lo, hi):
    """+1 above hi, -1 below lo, 0 between; None when x is None."""
    return None if x is None else (1 if x > hi else -1 if x < lo else 0)


def layers(got) -> list[dict]:
    """One row per layer from the tab payloads (got(name) -> payload or {}). lean +1 = China gaining on the US, -1 = the US gaining."""
    out = []

    def add(tab, key, layer, label, value, lean, leader, detail, rule):
        if value is not None:
            out.append({"tab": tab, "key": key, "layer": layer, "label": label, "value": value, "lean": lean or 0, "leader": leader, "detail": detail, "rule": rule})
    E = got("models").get("epoch") or {}
    ys, C = E.get("years") or [], E.get("counts") or {}
    if E.get("last_full") in ys and len(ys) >= 4:
        i = ys.index(E["last_full"])
        u, c = C["US"][i], C["China"][i]
        sh = lambda j: C["China"][j] / (C["US"][j] + C["China"][j]) if C["US"][j] + C["China"][j] else None
        now, before = sh(i), [sh(j) for j in range(max(0, i - 3), i) if sh(j) is not None]
        diff = None if now is None or not before else now - sum(before) / len(before)
        add("models", "models_share", "Notable AI models", f"China's share of US + China notable models, {ys[i]} (%)", _r(100 * now, 1) if now is not None else None,
            _band(diff, -0.03, 0.03), "US" if u >= c else "China", f"US {u}, China {c} in {ys[i]}", "+1 when the share is 3 points above the 3 years before, -1 when 3 below")
    g, g0 = E.get("gap_oom"), E.get("gap_oom_year_ago")
    if g is not None:
        add("models", "compute_gap", "Frontier training compute", "Largest US run over largest Chinese run (orders of magnitude)", g,
            _band(None if g0 is None else g0 - g, -0.1, 0.1), "US" if g > 0 else "China", f"{g0} a year earlier" if g0 is not None else "", "+1 when the gap shrank by 0.1 or more over a year, -1 when it grew")
    A = (got("models").get("arena") or {}).get("gap") or []
    if A:
        prev = A[-2][1] if len(A) >= 2 else None
        add("models", "arena_gap", "Best model (LMArena)", "Best US minus best Chinese model, Arena score", A[-1][1], _band(None if prev is None else prev - A[-1][1], -5, 5),
            "US" if A[-1][1] > 0 else "China", f"{prev} at the snapshot before" if prev is not None else "", "+1 when the gap narrowed by more than 5 points since the last snapshot")
    R = got("research")
    pg = R.get("pct_gap") or []
    if pg:
        prev = pg[-2][1] if len(pg) >= 2 else None
        add("research", "pct_gap", "Patents (PCT filings)", f"China minus US PCT applications, {pg[-1][0]}", pg[-1][1], _band(None if prev is None else pg[-1][1] - prev, -500, 500),
            "China" if pg[-1][1] > 0 else "US", f"{prev:+,.0f} a year earlier" if prev is not None else "", "+1 when China's margin widened by 500 or more, -1 when it narrowed")
    cs = R.get("cited_share") or []
    cs = [p for p in cs if p[0] <= pd.Timestamp.now().year - 2]        # the last two years have not gathered their citations yet
    if cs:
        before = next((p[1] for p in cs if p[0] == cs[-1][0] - 3), None)
        add("research", "cited_share", "Highly cited AI research", f"China's share of US + China AI papers with >{CITED} citations, {cs[-1][0]} (%)", _r(100 * cs[-1][1], 1),
            _band(None if before is None else cs[-1][1] - before, -0.02, 0.02), "China" if cs[-1][1] > 0.5 else "US",
            f"{_r(100 * before, 1)}% three years earlier" if before is not None else "", "+1 when the share rose 2 points or more over three years")
    V = got("ev")
    S = V.get("share") or {}
    if S.get("China") and S.get("US"):
        us = dict(S["US"])
        d = [(y, v - us[y]) for y, v in S["China"] if y in us]
        if d:
            prev = d[-2][1] if len(d) >= 2 else None
            add("ev", "ev_share_gap", "EV adoption", f"EV share of new cars, China minus US, {d[-1][0]} (points)", _r(d[-1][1], 1), _band(None if prev is None else d[-1][1] - prev, -1, 1),
                "China" if d[-1][1] > 0 else "US", f"{_r(prev, 1)} points a year earlier" if prev is not None else "", "+1 when China's lead widened by more than a point")
    bc = ((V.get("battery") or {}).get("by_country") or {}).get("China") or []
    by = (V.get("battery") or {}).get("years") or []
    if bc:
        prev = bc[-2] if len(bc) >= 2 else None
        add("ev", "battery_china", "EV batteries", f"Chinese makers' share of EV battery installations, {by[-1]} (%)", bc[-1], _band(None if prev is None else bc[-1] - prev, -1, 1),
            "China", "no US maker is in the top ten (Panasonic and the Korean makers supply US plants)", "+1 when the share rose more than a point")
    bt = V.get("byd_tesla") or {}
    if bt.get("BYD") and bt.get("Tesla"):
        t = dict(bt["Tesla"])
        r = [(y, v / t[y]) for y, v in bt["BYD"] if t.get(y)]
        if r:
            prev = r[-2][1] if len(r) >= 2 else None
            add("ev", "byd_tesla", "EV makers", f"BYD over Tesla battery-electric deliveries, {r[-1][0]}", _r(r[-1][1], 2), _band(None if prev is None else r[-1][1] - prev, -0.05, 0.05),
                "China" if r[-1][1] > 1 else "US", f"{_r(prev, 2)} a year earlier" if prev is not None else "", "+1 when the ratio rose by more than 0.05")
    K = got("chips")
    ng = K.get("nodes") or []
    if ng:
        prev = ng[-2]["years"] if len(ng) >= 2 else None
        add("chips", "node_gap", "Chipmaking", f"SMIC's {ng[-1]['node']:.0f}nm-class node, years after TSMC", ng[-1]["years"],
            _band(None if prev is None else prev - ng[-1]["years"], -0.5, 0.5), "US & allies (TSMC)", f"{prev} years at the node before" if prev is not None else "",
            "+1 when the gap is half a year shorter than at the node before, -1 when longer")
    if K.get("recent_n") is not None and K.get("controls"):
        dv = K.get("recent_direction", 0)
        add("chips", "controls", "Export controls", "US and allied steps in the last 12 months, net (-1 each tightening, +1 each easing)", dv,
            1 if dv > 0 else -1 if dv < 0 else 0, "US", f"{K['recent_n']} step{'s' if K['recent_n'] != 1 else ''}", "+1 when easings outnumber tightenings")
    if K.get("imports_yoy") is not None:
        add("chips", "ic_imports", "Chip import dependence", "China's IC imports vs the year before (%)", _r(100 * K["imports_yoy"], 1), _band(-K["imports_yoy"], -0.05, 0.05),
            "US & allies", "falling imports alongside rising domestic output read as China gaining", "+1 when imports fell more than 5%, -1 when they rose more than 5%")
    M = got("markets")
    if M.get("rel_1y") is not None:
        add("markets", "rel_1y", "Tech shares", "China tech ADRs vs US tech basket, last 12 months (%)", _r(100 * M["rel_1y"], 1), _band(M["rel_1y"], -0.05, 0.05),
            "US", "relative total price return, equal-weighted baskets", "+1 when China's basket beat the US basket by more than 5%")
    return out


def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


def _overview_now() -> dict:
    got, errors = {}, {}
    for name in ("models", "research", "ev", "chips", "markets"):
        try:
            got[name] = ENDPOINTS[name]()
        except Exception as e:
            got[name], errors[name] = {}, type(e).__name__
    rows = layers(lambda n: got.get(n) or {})
    stale = {k: v for p in got.values() for k, v in (p.get("stale") or {}).items()}
    return {"layers": rows, "errors": errors, "stale": stale, "updated": int(time.time()),
            "as_of": max([p.get("as_of") for p in got.values() if p.get("as_of")], default=None),
            "tally": {"china": sum(r["lean"] > 0 for r in rows), "us": sum(r["lean"] < 0 for r in rows), "flat": sum(r["lean"] == 0 for r in rows)}}


def READINGS() -> list[dict]:
    """Each layer as it reads now, from the cached tab payloads only. lean +1 = China gaining relative to the US, -1 = the US gaining."""
    return [{"tab": r["tab"], "key": r["key"], "label": r["label"], "value": r["value"], "lean": r["lean"], "note": r["rule"]} for r in layers(_cached_payload)]


def _year_back(s: pd.Series):
    """(latest value, value about a year before it, whether the series is monthly): works for yearly rows and for monthly ones."""
    s = s.dropna().sort_index()
    if len(s) < 2:
        return (s.iloc[-1] if len(s) else None), None, False
    monthly = (s.index[-1] - s.index[-2]).days < 60
    ago = s[s.index <= s.index[-1] - pd.Timedelta(days=350 if monthly else 300)]
    return s.iloc[-1], (ago.iloc[-1] if len(ago) else None), monthly


def SIGNALS() -> list[dict]:
    """The owner's approved signals (data/signals/watchlist.json), from cached payloads and hand-entered rows only.
    lean +1 = China gaining relative to the US, -1 = the US gaining."""
    out = []

    def add(key, tab, label, value, unit, lean, watch, crossed, note=None):
        out.append({"key": key, "tab": tab, "label": label, "value": value, "unit": unit, "lean": lean, "watch": watch, "crossed": bool(crossed),
                    **({"note": note} if note else {})})
    t12 = (_cached_payload("models").get("epoch") or {}).get("trailing_12m")
    if t12:
        us, cn = t12.get("US", 0), t12.get("China", 0)
        add("models_12m", "models", "Notable AI models, last 12 months: China minus US", cn - us, "", 1 if cn > us else -1 if us > cn else 0,
            "China's count exceeds the US's", cn > us, f"US {us}, China {cn} (Epoch AI, by developer country)")
    ex = manual(SLUG, "ev_exports")
    if isinstance(ex, pd.Series) and len(ex):
        now, ago, monthly = _year_back(ex)
        chg = None if ago is None else now / ago - 1
        high = now >= ex.max() and len(ex) > 1
        add("ev_exports", "ev", "China NEV exports" + (" a month" if monthly else ", latest year") + " (million)", _r(now, 3), "m",
            0 if chg is None else 1 if chg > 0 else -1, "new high, or down 20% on a year", high or (chg is not None and chg <= -0.2),
            ("a record" if high else "below the record") + (f"; {chg:+.0%} on a year" if chg is not None else "") + ("" if monthly else "; yearly rows until monthly CAAM figures are entered"))
    trade = _hand("ic_trade")
    imp = trade.get("Imports")
    if imp is not None and len(imp) >= 2:
        now, ago, monthly = _year_back(imp)
        if ago:
            chg = 100 * (now / ago - 1)
            add("chip_imports", "chips", "China IC imports, change on a year", _r(chg, 1), "%", 1 if chg < -5 else -1 if chg > 5 else 0,
                "down more than 15%", chg < -15, f"US${now:,.0f}bn {'that month' if monthly else 'in ' + str(imp.dropna().index[-1].year)} (GACC)")
    g = _cached_payload("markets").get("gap_90d")
    if g:
        add("basket_gap", "markets", "China tech ADRs minus US tech basket, 90-day return", g["gap"], " pts", 1 if g["gap"] > 5 else -1 if g["gap"] < -5 else 0,
            "20-point gap either way", abs(g["gap"]) >= 20, f"China {g['china']:+.1f}%, US {g['us']:+.1f}%")
    rows = sorted(manual_rows(SLUG, "controls"), key=lambda r: r["date"])
    if rows:
        r = rows[-1]
        age = (pd.Timestamp.now().normalize() - pd.Timestamp(r["date"])).days
        add("controls", "chips", "Latest export-control step", f"{r['date']}: {r['actor']}", "", max(-1, min(1, int(r.get("direction") or 0))),
            "any new rule or exemption", 0 <= age <= NEW_DAYS, f"{r['event']} ({age} days ago; counts as new for {NEW_DAYS} days after its date)")
    return out


def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, size, start of body). Read with Actions > show-json on
    /api/china-us-tech/layout."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    y = pd.Timestamp.now().year - 1
    urls = {"epoch": EPOCH, "owid share": OWID.format(name=OWID_SHARE), "owid sales": OWID.format(name=OWID_SALES),
            "openalex CN": OPENALEX.format(cc="CN", y=y, extra=""), "openalex US cited": OPENALEX.format(cc="US", y=y, extra=f",cited_by_count:>{CITED}"),
            "nasdaq BABA": B.NASDAQ.format(sym="BABA", a="2026-09-01", b=pd.Timestamp.now().strftime("%Y-%m-%d")),
            "nasdaq KWEB etf": B.NASDAQ_ANY.format(sym="KWEB", cls="etf", a="2026-09-01", b=pd.Timestamp.now().strftime("%Y-%m-%d"))}

    def one(item):
        k, u = item
        h = {**B.UA, **(NASDAQ_HEADERS if "nasdaq" in k else {})}
        try:
            r = requests.get(u, headers=h, timeout=25)
            return k, {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type", ""), "start": r.text[:300]}
        except Exception as e:
            return k, {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(one, urls.items()))


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"overview": _cached_ep("overview", _overview_now, 600), "models": _cached_ep("models", _models_now), "research": _cached_ep("research", _research_now),
             "ev": _cached_ep("ev", _ev_now), "chips": _cached_ep("chips", _chips_now, 600), "markets": _cached_ep("markets", _markets_now),
             "layout": _cached_ep("layout", _layout_now, 1800)}
