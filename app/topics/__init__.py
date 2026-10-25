"""The dashboards: / (index), /<slug> (page), /<slug>.js (its tabs), /api/<slug>/<name> (data).

Each dashboard is one module here (ENDPOINTS = {name: fn}, SOURCES = [...] for the page footer), one static/topics/<slug>.js
(its tabs and cards) and, where a source has no free API, hand-entered CSVs in data/<slug>/. The shared page shell is
static/topic.html. See _base.py for fetching, snapshots and manual series.

To add a dashboard: write topics/<name>.py and static/topics/<slug>.js, add a Topic below and a data/<slug>/ folder. Nothing else changes.
"""
from __future__ import annotations

import importlib
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


REGISTRY: dict[str, Topic] = {t.slug: t for t in (
    Topic("housing", "Housing: London, US & Hong Kong", "London house prices, boroughs, sales, rents and affordability, against the UK, the US and Hong Kong.",
          "housing", (("prices", "Prices"), ("market", "Types & volume"), ("boroughs", "Boroughs"), ("afford", "Rates & affordability"), ("global", "London vs US vs HK")),
          ("prices", "market", "afford", "boroughs", "global")),
    Topic("robotaxi", "Autonomous Car Adoption", "Driverless ride-hailing and Tesla: paid rides, where it operates in the US, UK, Hong Kong and China, safety reports per mile, and every Tesla autonomy milestone.",
          "robotaxi", (("rides", "Rides"), ("footprint", "Footprint & rules"), ("safety", "Safety"), ("tesla", "Tesla")), ("safety", "tesla")),
    Topic("ai", "AI: Jobs & Adoption", "AI job openings against hiring, headcount and pay in law and finance, and how fast firms and people take up AI tools and agents, in the US, UK and Hong Kong.",
          "ai", (("openings", "Openings"), ("headcount", "Headcount"), ("wages", "Pay"), ("ratio", "AI vs the professions"), ("firms", "Firms adopting"),
                 ("users", "Users"), ("agents", "Agents"), ("skills", "Skills demand")), ("openings", "headcount", "wages", "ratio", "firms", "skills")),
    Topic("btc-cycles", "BTC Cycles & Sector Rotation", "Four Bitcoin cycles, which altcoin sectors won each one, what the winners had in common, and the 2026-27 candidates, checked daily against live data.",
          "btc_cycles", (("cycles", "Cycles"), ("sectors", "Sectors"), ("metrics", "Winner metrics"), ("candidates", "Candidates 2026-27"), ("etf", "ETFs"),
                         ("mstr", "Strategy (MSTR)"), ("signals", "Signals")),
          ("cycles", "metrics", "candidates", "signals", "coins", "etf", "mstr")),
)}


def module(slug: str):
    return importlib.import_module(f".{REGISTRY[slug].module}", __name__)


def endpoints(slug: str) -> dict:
    return module(slug).ENDPOINTS


def meta(slug: str) -> dict:
    t, m = REGISTRY[slug], module(slug)
    return {"slug": t.slug, "title": t.title, "blurb": t.blurb, "tabs": [list(x) for x in t.tabs], "sources": list(getattr(m, "SOURCES", [])),
            "notes": getattr(m, "NOTES", "")}


def index() -> dict:
    return {"dashboards": [{"slug": t.slug, "title": t.title, "blurb": t.blurb, "icon": t.icon} for t in REGISTRY.values()]}


# old addresses of dashboards that were merged or renamed: slug -> (new slug, tab)
REDIRECTS = {"ai-jobs": ("ai", "openings"), "ai-adoption": ("ai", "firms")}


def health() -> dict:
    """Source health for /api/health, grouped by dashboard slug (helper modules map to the dashboard that uses them)."""
    from ._base import health as h
    m2s = {t.module: t.slug for t in REGISTRY.values()}
    m2s.update({"ai_jobs": "ai", "ai_adoption": "ai", "btc_flows": "btc-cycles"})
    out = h(m2s)
    for t in REGISTRY.values():
        out["dashboards"].setdefault(t.slug, {"fresh": 0, "stale": 0, "failing": 0, "alerts": 0, "sources": []})
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
}


def probe() -> dict:
    """Try each PROBE_URLS entry from this server with requests and with curl; report status, size and the start of the body."""
    import subprocess
    import requests
    from ._base import UA
    out = {}
    for name, url in PROBE_URLS.items():
        row = {"url": url}
        try:
            r = requests.get(url, headers=UA, timeout=25)
            row["requests"] = {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type", ""), "start": r.text[:120]}
        except Exception as e:
            row["requests"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
        try:
            c = subprocess.run(["curl", "-s", "-L", "--max-time", "25", "-A", UA["User-Agent"], "-o", "/dev/null", "-w", "%{http_code} %{size_download}", url],
                               capture_output=True, text=True, timeout=40)
            row["curl"] = c.stdout.strip() or f"exit {c.returncode}"
        except Exception as e:
            row["curl"] = f"{type(e).__name__}"
        out[name] = row
    return out
