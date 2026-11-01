"""Actions & Roadmap (/status): what the owner has to do, what the sessions and the daily check are working on, what comes next, and
the daily check's log. One file, data/status/items.json, kept current by the daily check routine (it closes actions it sees resolved,
adds new ones, records handoffs and appends to the log) and by hand.
"""
from __future__ import annotations

import json
from datetime import date

from . import Topic
from ..config import DATA_DIR

SLUG = "status"
FILE = DATA_DIR / "status" / "items.json"
TOPIC = Topic(SLUG, "Actions & Roadmap",
              "What needs your hand, what the dashboard sessions and the daily check are working on, what comes next, and how each morning's check went.",
              "status", (("actions", "Action items"), ("pending", "Pending"), ("roadmap", "Roadmap"), ("log", "Check log")), ("actions",), order=910)


def items() -> dict:
    if not FILE.exists():
        raise FileNotFoundError("data/status/items.json is missing")
    d = json.loads(FILE.read_text())
    today = date.today()
    for key in ("actions", "pending"):
        for it in d.get(key, []):
            since = it.get("since")
            it["age_days"] = (today - date.fromisoformat(since)).days if since else None
    return d


def _tab(key):
    return lambda: {"updated": items().get("updated"), key: items().get(key, [])}


def READINGS() -> list[dict]:
    d = items()
    open_actions = [a for a in d["actions"] if a.get("status") == "open"]
    high = sum(1 for a in open_actions if a.get("priority") == "high")
    pend = [p for p in d["pending"] if p.get("status") != "done"]
    last = d["log"][-1] if d["log"] else None
    out = [{"tab": "actions", "key": "open_actions", "label": "Open action items for the owner", "value": len(open_actions), "lean": -1 if high else 0,
            "note": f"{high} high priority" if high else ""},
           {"tab": "pending", "key": "pending", "label": "Items in progress or waiting", "value": len(pend), "lean": 0},
           {"tab": "roadmap", "key": "roadmap_done", "label": "Roadmap items done", "value": sum(1 for r in d["roadmap"] if r.get("status") == "done"), "lean": 1}]
    if last:
        out.append({"tab": "log", "key": "last_check", "label": "Last daily check", "value": last.get("result"), "lean": 1 if last.get("result") == "ok" else -1, "note": last.get("date")})
    return out


ENDPOINTS = {"actions": _tab("actions"), "pending": _tab("pending"), "roadmap": _tab("roadmap"), "log": _tab("log")}
SOURCES = [{"name": "data/status/items.json in this repository", "url": "https://github.com/mcmarcocheung98-max/dashboards/blob/main/data/status/items.json", "cadence": "daily, by the check routine"}]
NOTES = "Nothing here is live data about the world: it is the to-do list and roadmap of this site. The daily check routine edits the file each morning; the Check log tab shows what it found."
