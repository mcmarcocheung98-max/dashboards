"""Graphify Map (/graphify): how the knowledge graph of this repo is built, what it shows, and the tokens it saves a session.

Data is the committed export in data/graphify/ (scripts/graphify_export.py): map.json is the graph summarised (clusters, god nodes,
audit counts, surprises, every node and link in compact form), savings.json the token benchmark on real tasks from this project.
Nothing is downloaded: this dashboard reads files only.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from . import Topic
from ..config import DATA_DIR

SLUG = "graphify"
DIR = DATA_DIR / "graphify"
TOPIC = Topic(SLUG, "Graphify Map",
              "Every function, source and document of this site as one living map: how graphify builds it, what depends on what, and how many "
              "tokens a Claude session saves by asking the map instead of reading the files.",
              "graphify_map", (("map", "Map"), ("savings", "Token savings"), ("usage", "Daily tokens"), ("how", "How it works"), ("gods", "God nodes"), ("audit", "Audit trail"),
                               ("explore", "Explorer"), ("use", "In practice")), ("map", "savings"), order=900)


def _read(name: str) -> dict:
    p = DIR / name
    if not p.exists():
        raise FileNotFoundError(f"{name} is not exported yet: run scripts/graphify_export.py")
    return json.loads(p.read_text())


def map_data() -> dict:
    return _read("map.json")


def savings() -> dict:
    return _read("savings.json")


INSTALLED = "2026-10-30"      # graphify was installed in the sessions on this day; lookups before it are zero by definition


def usage() -> dict:
    """Daily tokens across the dashboard sessions, and the tokens graphify saved (data/graphify/usage.json, scripts/graphify_usage.py).

    Tokens are measured: the dev agent's own transcript day by day, the other sessions from the change in their running totals.
    Saved tokens = lookups x the median saving per lookup in savings.json. Lookups are counted in the dev agent's transcript;
    for the other sessions they are estimated at the dev agent's rate of lookups per token since graphify was installed."""
    d = _read("usage.json")
    per = int(d.get("saving_per_lookup") or 0)
    rows = d.get("days", [])
    tot = lambda r: sum(int(r.get(k) or 0) for k in ("input", "cache_write", "cache_read", "output"))
    mine = [r for r in rows if r["session"] == "dev-agent" and r["date"] >= INSTALLED]
    rate = sum(int(r.get("lookups") or 0) for r in mine) / max(1, sum(tot(r) for r in mine))          # lookups per token
    days: dict[str, dict] = {}
    for r in rows:
        x = days.setdefault(r["date"], {"date": r["date"], "input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "total": 0, "cost_usd": 0.0,
                                         "lookups": 0, "lookups_est": 0.0, "saved": 0, "saved_est": 0, "sessions": 0})
        for k in ("input", "cache_write", "cache_read", "output"):
            x[k] += int(r.get(k) or 0)
        x["total"] += tot(r)
        x["cost_usd"] = round(x["cost_usd"] + float(r.get("cost_usd") or 0), 2)
        x["sessions"] += 1
        if r.get("lookups") is not None:
            x["lookups"] += int(r["lookups"])
        elif r["date"] >= INSTALLED:
            x["lookups_est"] += tot(r) * rate
    out = []
    for x in sorted(days.values(), key=lambda v: v["date"]):
        x["saved"], x["saved_est"], x["lookups_est"] = x["lookups"] * per, round(x["lookups_est"] * per), round(x["lookups_est"], 1)
        out.append(x)
    by = defaultdict(lambda: {"total": 0, "days": 0, "last": "", "to_date": None, "cost_to_date": None})
    for r in rows:
        b = by[r["session"]]; b["total"] += tot(r); b["days"] += 1; b["last"] = max(b["last"], r["date"])
    for k, s in (d.get("snapshots") or {}).items():            # each session's running total since it started, as of its last run
        b = by[k]; b["to_date"] = tot(s); b["cost_to_date"] = s.get("cost_usd"); b["last"] = max(b["last"], (s.get("as_of") or "")[:10])
    return {"updated": d.get("updated"), "saving_per_lookup": per, "saving_measured": d.get("saving_measured"), "installed": INSTALLED,
            "lookups_per_million": round(rate * 1e6, 3), "days": out,
            "sessions": sorted(({"session": k, **v} for k, v in by.items()), key=lambda v: -(v["to_date"] or v["total"]))}


def READINGS() -> list[dict]:
    """The map's own headline figures, so 'what changed since yesterday' shows when the export grows."""
    out = []
    try:
        m = map_data()["stats"]
        out += [{"tab": "map", "key": "nodes", "label": "Nodes in the map", "value": m["nodes"], "lean": 0},
                {"tab": "audit", "key": "inferred_share", "label": "Share of links inferred rather than read", "value": round(100 * m["conf"].get("INFERRED", 0) / max(1, m["edges"]), 1), "lean": 0}]
    except Exception:
        pass
    try:
        s = savings()
        ts = s["tasks"]
        saved = sum(1 - t["graph_tokens"] / max(1, t["naive_tokens"]) for t in ts) / max(1, len(ts)) * 100
        out.append({"tab": "savings", "key": "avg_saving", "label": "Average tokens saved per task (%)", "value": round(saved, 1), "lean": 1 if saved >= 90 else 0})
    except Exception:
        pass
    try:
        u = usage()["days"]
        if u:
            out.append({"tab": "usage", "key": "tokens_last_day", "label": "Tokens used by the sessions, latest day (millions)", "value": round(u[-1]["total"] / 1e6, 1), "lean": 0,
                        "note": u[-1]["date"]})
    except Exception:
        pass
    return out


def _slice(*keys):
    """A tab's own endpoint: the parts of map.json it draws (the page itself loads 'map' once and reuses it)."""
    return lambda: {k: v for k, v in map_data().items() if k in keys}


COMMANDS = [["graphify query \"<question>\"", "walk the graph from the matching nodes; a small, scoped subgraph"],
            ["graphify explain \"<node>\"", "one node and its most connected neighbours"],
            ["graphify path \"<A>\" \"<B>\"", "the shortest path between two things"],
            ["graphify update .", "rebuild the code half of the map (no model, no key)"],
            ["bash scripts/graphify-setup.sh", "install graphify if missing and build graphify-out/"],
            ["python scripts/graphify_export.py --bench", "refresh this dashboard's data"]]

ENDPOINTS = {"map": map_data, "savings": savings, "usage": usage, "how": _slice("built_at", "exported", "stats"), "gods": _slice("gods", "godlinks", "communities"),
             "audit": _slice("stats", "surprises", "hyperedges"), "explore": _slice("nodes", "edges", "communities", "gods"), "use": lambda: {"commands": COMMANDS}}
SOURCES = [{"name": "graphify (graphifyy on PyPI)", "url": "https://github.com/Graphify-Labs/graphify", "cadence": "rebuilt each session"},
           {"name": "This repository", "url": "https://github.com/mcmarcocheung98-max/dashboards", "cadence": "every push"}]
NOTES = ("The map is a snapshot exported from graphify-out/ by scripts/graphify_export.py; the commit it was built from is shown on the Map tab. "
         "Token counts use four characters per token. Nothing on this page is live data about the world: it is about the site itself.")
