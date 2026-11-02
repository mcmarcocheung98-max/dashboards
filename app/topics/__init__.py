"""The dashboards: / (index), /<slug> (page), /<slug>.js (its tabs), /api/<slug>/<name> (data).

Each dashboard is one module here (ENDPOINTS = {name: fn}, SOURCES = [...] for the page footer), one static/topics/<slug>.js
(its tabs and cards) and, where a source has no free API, hand-entered CSVs in data/<slug>/. The shared page shell is
static/topic.html. See _base.py for fetching, snapshots and manual series.

To add a dashboard: write topics/<name>.py with TOPIC = Topic(...), static/topics/<slug>.js, data/<slug>/ and tests/test_<slug>.py
(optionally with smoke_patch(), which points the module's fetchers at fixtures for scripts/smoke.py). The module is found on its own:
nothing shared changes. A helper module that only feeds a dashboard sets DASHBOARD = "<slug>" so /api/health files it there.

Shared scripts: Topic(..., script="<name>") serves static/topics/<name>.js at /<slug>.js, for dashboards that are the same page on
different data.

Private dashboards: TOPIC = Topic(..., private=True) keeps it off the index and puts its page data, script and Ask Claude behind
the PRIVATE_PASSCODE cookie (app/auth.py); /api/health shows only its counts and the public /api/archive.zip leaves it out.

What changed since yesterday: a module may define READINGS() -> [{"tab", "key", "label", "value", "lean": +1/0/-1, "note"?}], its
headline indicators as they read now (from cached data only). One snapshot a day is saved and the page shows what flipped and each
tab's lean day by day (see _daily.py). Without READINGS the dashboard simply shows no such card.

A top card that follows the timeline: in the dashboard's JS, build each tab's top KPI card with followHead([{label, points, fmt,
delta?}], opts) or datedHead(items, opts) from static/topic.html. Hovering any chart in the tab shows that day's figures, a click
keeps the day, "Back to latest" returns; scripts/smoke.py checks it on every tab that has one.
"""
from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Topic:
    slug: str
    title: str
    blurb: str
    module: str                       # module name in this package
    tabs: tuple = ()                  # (key, label) pairs, first is the default
    slow: tuple = ()                  # endpoints the background warmer keeps computed
    icon: str = "chart"
    order: int = 100                  # position on the index page
    private: bool = False             # off the index; page, data and Ask Claude need the passcode (app/auth.py)
    script: str = ""                  # static/topics/<script>.js when several dashboards share one script (default: the slug)


BUILTIN = (
    Topic("housing", "Housing: London, US & Hong Kong", "London house prices, boroughs, sales, rents and affordability, against the UK, the US and Hong Kong.",
          "housing", (("prices", "London"), ("boroughs", "Boroughs: homes & rents"), ("market", "Types & volume"), ("afford", "Rates & affordability"), ("calc", "Rent or buy"), ("global", "London vs US vs HK")),
          ("prices", "market", "afford", "boroughs", "calc", "global")),
    Topic("ai", "AI: Jobs & Adoption", "AI job openings against hiring, headcount and pay in law and finance, and how fast firms and people take up AI tools and agents, in the US, UK and Hong Kong.",
          "ai", (("openings", "Openings"), ("headcount", "Headcount"), ("wages", "Pay"), ("ratio", "AI vs the professions"), ("firms", "Firms adopting"),
                 ("users", "Users"), ("agents", "Agents"), ("skills", "Skills demand")), ("openings", "headcount", "wages", "ratio", "firms", "skills")),
    Topic("btc-cycles", "BTC Cycles & Sector Rotation", "Four Bitcoin cycles, which altcoin sectors won each one, what the winners had in common, and the 2026-27 candidates, checked daily against live data.",
          "btc_cycles", (("cycles", "Cycles"), ("sectors", "Sectors"), ("metrics", "Winner metrics"), ("candidates", "Candidates 2026-27"), ("etf", "ETFs"),
                         ("mstr", "Strategy (MSTR)"), ("signals", "Signals")),
          ("cycles", "metrics", "candidates", "signals", "etf", "mstr")),
)


def _discover() -> list[Topic]:
    """Topics declared by modules in this package (TOPIC = Topic(...)), so a new dashboard needs no edit here."""
    found = []
    for m in pkgutil.iter_modules(__path__):
        if m.name.startswith("_") or m.name in {t.module for t in BUILTIN}:
            continue
        mod = importlib.import_module(f".{m.name}", __name__)
        t = getattr(mod, "TOPIC", None)
        if isinstance(t, Topic):
            found.append(t)
    return found


def helpers() -> dict[str, str]:
    """module name -> dashboard slug, for helper modules that declare DASHBOARD = "<slug>"."""
    out = {}
    for m in pkgutil.iter_modules(__path__):
        if not m.name.startswith("_"):
            slug = getattr(importlib.import_module(f".{m.name}", __name__), "DASHBOARD", None)
            if slug:
                out[m.name] = slug
    return out


REGISTRY: dict[str, Topic] = {t.slug: t for t in sorted((*BUILTIN, *_discover()), key=lambda t: t.order)}


def script(slug: str) -> str:
    """The file name under static/topics/ that /<slug>.js serves."""
    return (REGISTRY[slug].script or slug) + ".js"


def module(slug: str):
    return importlib.import_module(f".{REGISTRY[slug].module}", __name__)


def endpoints(slug: str) -> dict:
    return module(slug).ENDPOINTS


def meta(slug: str) -> dict:
    t, m = REGISTRY[slug], module(slug)
    return {"slug": t.slug, "title": t.title, "blurb": t.blurb, "category": category(slug), "private": t.private, "tabs": [list(x) for x in t.tabs], "sources": list(getattr(m, "SOURCES", [])),
            "notes": getattr(m, "NOTES", ""), "method": bool(method(slug)["sections"])}


# README sections shown on the page's Method tab (/<slug>#about): how the numbers are worked out and their caveats, not upkeep
METHOD_HEADINGS = re.compile(r"calculat|method|the measures|caveat|gaps|notes on the data|\brule\b|heat score", re.I)


def method(slug: str) -> dict:
    """The calculation and caveat sections of data/<slug>/README.md as [{title, markdown}], for the Method tab. A section runs to
    the next heading of its level or higher; a section under a part heading (# Jobs half) is titled with the part as well."""
    from ..config import DATA_DIR
    f = Path(DATA_DIR) / slug / "README.md"
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    heads, fenced = [], False
    for i, ln in enumerate(lines):
        fenced ^= ln.lstrip().startswith("```")               # a "# comment" inside a code block is not a heading
        if not fenced and (m := re.match(r"(#{1,4})\s+(.+)", ln)):
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    out, inside = [], False
    for n, (i, level, text) in enumerate(heads):
        if n == 0 and level == 1:
            continue                                         # the document title
        if inside and level > inside:
            continue                                         # a sub-heading of a section already taken whole
        inside = False
        if not METHOD_HEADINGS.search(text):
            continue
        end = next((j for j, lv, _ in heads[n + 1:] if lv <= level), len(lines))
        part = next((t for j, lv, t in reversed(heads[1:n]) if lv < level), None)
        body = "\n".join(lines[i + 1:end]).strip()
        if body:
            text = re.sub(r"\s*\([^)]*`[^)]*\)", "", text)          # "The buy zone rule (`app/topics/altcoins.py`)" -> "The buy zone rule"
            out.append({"title": f"{part} · {text}" if part else text, "markdown": body})
            inside = level
    return {"slug": slug, "sections": out}


def save_daily(slug: str) -> str:
    from . import _daily
    fn = getattr(module(slug), "READINGS", None)
    return _daily.save_today(slug, fn) if fn else "none"


def changes(slug: str) -> dict:
    from . import _daily
    if not hasattr(module(slug), "READINGS"):
        return {"available": False}
    return _daily.changes(slug, REGISTRY[slug].tabs)


# The index page groups dashboards under these headings, in this order. A dashboard not listed here goes under "More".
CATEGORIES = (
    ("Money & markets", "Prices, rates and where capital is flowing.", ("btc-cycles", "altcoins", "debt-rates", "housing", "pokemon-cards")),
    ("AI & technology", "How fast AI, chips and machines are arriving, and who leads.", ("ai", "compute-chips", "china-us-tech", "robotaxi", "space")),
    ("People & planet", "The slow forces: population, health and climate.", ("demographics", "longevity", "climate")),
    ("Sentiment & attention", "What people are betting on and paying attention to.", ("prediction-markets", "trends")),
    ("About this site", "How the dashboards are built, mapped and kept honest, and what is still to do.", ("status", "graphify")),
)


def category(slug: str) -> str:
    return next((name for name, _, slugs in CATEGORIES if slug in slugs), "More")


def public() -> dict[str, Topic]:
    return {s: t for s, t in REGISTRY.items() if not t.private}


def index() -> dict:
    tile = lambda t: {"slug": t.slug, "title": t.title, "blurb": t.blurb, "icon": t.icon, "category": category(t.slug)}
    pub = public()
    groups = [{"name": n, "blurb": b, "dashboards": [tile(pub[s]) for s in slugs if s in pub]} for n, b, slugs in CATEGORIES]
    listed = {s for _, _, slugs in CATEGORIES for s in slugs}
    groups.append({"name": "More", "blurb": "", "dashboards": [tile(t) for t in pub.values() if t.slug not in listed]})
    groups = [g for g in groups if g["dashboards"]]
    return {"categories": groups, "dashboards": [d for g in groups for d in g["dashboards"]]}


# old addresses of dashboards that were merged or renamed: slug -> (new slug, tab)
REDIRECTS = {"ai-jobs": ("ai", "openings"), "ai-adoption": ("ai", "firms"),
             **{t: ("altcoins", t) for t in ("hype", "ena", "sol", "near")}, "memecoins": ("altcoins", "basket")}


def health() -> dict:
    """Source health for /api/health, grouped by dashboard slug (helper modules map to the dashboard that uses them)."""
    from ._base import health as h
    m2s = {t.module: t.slug for t in REGISTRY.values()}
    m2s.update({"ai_jobs": "ai", "ai_adoption": "ai", "btc_flows": "btc-cycles", "_narrative": "altcoins", **helpers()})   # _narrative starts with "_", so helpers() skips it
    out = h(m2s)
    for t in REGISTRY.values():
        out["dashboards"].setdefault(t.slug, {"fresh": 0, "stale": 0, "failing": 0, "alerts": 0, "sources": []})
    for t in REGISTRY.values():
        if t.private and t.slug in out["dashboards"]:
            d = out["dashboards"][t.slug]
            out["dashboards"][t.slug] = {k: d.get(k, 0) for k in ("fresh", "stale", "failing", "alerts")} | {"sources": [], "private": True}
    return out


PROBE_URLS = {   # fixed list: what each dashboard downloads, to see from the server itself which sources answer and how
    "landregistry csv": "https://landregistry.data.gov.uk/app/ukhpi/download/new.csv?from=2024-01-01&to=2035-01-01&location=http%3A%2F%2Flandregistry.data.gov.uk%2Fid%2Fregion%2Flondon&thm%5B%5D=property_type%2Fall&in%5B%5D=avg&lang=en",
    "landregistry json": "https://landregistry.data.gov.uk/data/ukhpi/region/london/month/2025-06.json",
    "landregistry full file index": "https://www.gov.uk/government/statistical-data-sets/uk-house-price-index-data-downloads-august-2025",
    "fred csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CES6054110001",
    "fred alfred": "https://alfred.stlouisfed.org/graph/fredgraph.csv?id=CES6054110001",
    "ons api": "https://api.ons.gov.uk/timeseries/L522/dataset/MM23/data",
    "boe": "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/2024&Dateto=now&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y",
    "yahoo": "https://query1.finance.yahoo.com/v8/finance/chart/TSLA?range=1mo&interval=1d",
    "stooq": "https://stooq.com/q/d/l/?s=tsla.us&i=d",
    "coingecko chart": "https://api.coingecko.com/api/v3/coins/solana/market_chart?vs_currency=usd&days=365&interval=daily",
    "coingecko markets": "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=solana,hyperliquid",
    "binance mirror": "https://data-api.binance.vision/api/v3/klines?symbol=SOLUSDT&interval=1d&limit=5",
    "llama derivatives": "https://api.llama.fi/overview/derivatives?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true",
    "llama hl revenue": "https://api.llama.fi/summary/fees/hyperliquid?dataType=dailyRevenue",
    "census btos": "https://www.census.gov/hfp/btos/downloads/National.xlsx",
    "rvd": "https://www.rvd.gov.hk/doc/en/statistics/his_data_4.xls",
    "hkma": "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-endperiod?pagesize=3",
    "farside": "https://farside.co.uk/bitcoin-etf-flow-all-data/",
    "landregistry full file": "http://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/UK-HPI-full-file-2025-08.csv",
    "ons generator csv": "https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/l522/mm23",
    "ons beta api": "https://api.beta.ons.gov.uk/v1/datasets/cpih01",
    "bls api v1": "https://api.bls.gov/publicAPI/v1/timeseries/data/CES6054110001",
    "freddie mac pmms": "https://www.freddiemac.com/pmms/docs/historicalweeklydata.xlsx",
    "llama dexs overview": "https://api.llama.fi/overview/dexs?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true",
    "llama hl derivatives": "https://api.llama.fi/summary/derivatives/hyperliquid",
    "llama hl fees": "https://api.llama.fi/summary/fees/hyperliquid?dataType=dailyFees",
    "nasdaq": "https://api.nasdaq.com/api/quote/TSLA/historical?assetclass=stocks&fromdate=2026-09-01&limit=50",
    "fhfa master csv": "https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv",
    "fhfa master csv (old path)": "https://www.fhfa.gov/DataTools/Downloads/Documents/HPI/HPI_master.csv",
}


def probe() -> dict:
    """Try each PROBE_URLS entry from this server with requests and with curl, all at once (12 s each), and report status, size and the
    start of the body."""
    import subprocess
    from concurrent.futures import ThreadPoolExecutor
    import requests
    from ._base import UA

    def one(item):
        name, url = item
        row = {"url": url}
        try:
            r = requests.get(url, headers=UA, timeout=12)
            row["requests"] = {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type", ""), "start": r.text[:120]}
        except Exception as e:
            row["requests"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
        try:
            c = subprocess.run(["curl", "-s", "-L", "--max-time", "12", "-A", UA["User-Agent"], "-o", "/dev/null", "-w", "%{http_code} %{size_download}", url],
                               capture_output=True, text=True, timeout=20)
            row["curl"] = c.stdout.strip() or f"exit {c.returncode}"
        except Exception as e:
            row["curl"] = type(e).__name__
        return name, row
    with ThreadPoolExecutor(max_workers=len(PROBE_URLS)) as ex:
        return dict(ex.map(one, PROBE_URLS.items()))
