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
    Topic("housing", "London Housing Index", "House prices, sales, rents and what buyers can afford in London, against the UK and inflation.",
          "housing", (("prices", "Prices"), ("market", "Types & volume"), ("afford", "Rates & affordability")), ("prices", "market", "afford")),
    Topic("robotaxi", "Autonomous Car Adoption", "Driverless ride-hailing: paid rides, where it operates, and safety reports.",
          "robotaxi", (("rides", "Rides"), ("footprint", "Footprint"), ("safety", "Safety")), ("safety",)),
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
