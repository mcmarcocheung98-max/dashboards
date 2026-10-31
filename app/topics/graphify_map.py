"""Graphify Map (/graphify): how the knowledge graph of this repo is built, what it shows, and the tokens it saves a session.

Data is the committed export in data/graphify/ (scripts/graphify_export.py): map.json is the graph summarised (clusters, god nodes,
audit counts, surprises, every node and link in compact form), savings.json the token benchmark on real tasks from this project.
Nothing is downloaded: this dashboard reads files only.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import Topic
from ..config import DATA_DIR

SLUG = "graphify"
DIR = DATA_DIR / "graphify"
TOPIC = Topic(SLUG, "Graphify Map",
              "Every function, source and document of this site as one living map: how graphify builds it, what depends on what, and how many "
              "tokens a Claude session saves by asking the map instead of reading the files.",
              "graphify_map", (("map", "Map"), ("savings", "Token savings"), ("how", "How it works"), ("gods", "God nodes"), ("audit", "Audit trail"),
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
    return out


ENDPOINTS = {"map": map_data, "savings": savings}
SOURCES = [{"name": "graphify (graphifyy on PyPI)", "url": "https://github.com/Graphify-Labs/graphify", "cadence": "rebuilt each session"},
           {"name": "This repository", "url": "https://github.com/mcmarcocheung98-max/dashboards", "cadence": "every push"}]
NOTES = ("The map is a snapshot exported from graphify-out/ by scripts/graphify_export.py; the commit it was built from is shown on the Map tab. "
         "Token counts use four characters per token. Nothing on this page is live data about the world: it is about the site itself.")
