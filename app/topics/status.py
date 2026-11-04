"""Dev Agent & Roadmap (/status): the development agent's notes, what it proposes and waits on the owner's OK for, what the owner has
to do, what the sessions are working on, the roadmap, and the morning check's log. One file, data/status/items.json, kept current by
the dev agent (a daily Claude routine that follows data/status/AGENT.md) and by hand.
"""
from __future__ import annotations

import json
from datetime import date

from . import Topic
from ..config import DATA_DIR

SLUG = "status"
FILE = DATA_DIR / "status" / "items.json"
TOPIC = Topic(SLUG, "Dev Agent & Roadmap",
              "The development agent's notes on what changed across the dashboards and why, what it proposes next and waits for your OK on, what needs your hand, the roadmap, and each morning's check.",
              "status", (("notes", "Dev notes"), ("actions", "Action items"), ("pending", "Pending"), ("roadmap", "Roadmap"), ("log", "Check log")), ("actions",), order=910)


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


def proposals(d: dict | None = None) -> list[dict]:
    """Roadmap items the agent proposed that wait for the owner's OK."""
    return [r for r in (d or items())["roadmap"] if r.get("status") == "proposed"]


def notes() -> dict:
    d = items()
    N = sorted(d.get("notes", []), key=lambda n: n.get("date", ""), reverse=True)
    week = (date.today() - date.fromisoformat(N[0]["date"])).days if N else None
    shipped = sum(1 for n in N if (date.today() - date.fromisoformat(n["date"])).days < 7 for c in n.get("changes", []) if c.get("commit"))
    return {"updated": d.get("updated"), "notes": N, "proposals": proposals(d), "shipped_7d": shipped, "last_note_days": week,
            "last_check": (d["log"][-1] if d.get("log") else None)}


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
    out.append({"tab": "notes", "key": "awaiting_ok", "label": "Agent proposals waiting for your OK", "value": len(proposals(d)), "lean": 0})
    if last:
        out.append({"tab": "log", "key": "last_check", "label": "Last daily check", "value": last.get("result"), "lean": 1 if last.get("result") == "ok" else -1, "note": last.get("date")})
    return out


ENDPOINTS = {"notes": notes, "actions": _tab("actions"), "pending": _tab("pending"), "roadmap": _tab("roadmap"), "log": _tab("log")}
SOURCES = [{"name": "data/status/items.json in this repository", "url": "https://github.com/mcmarcocheung98-max/dashboards/blob/main/data/status/items.json", "cadence": "daily, by the dev agent"}]
NOTES = ("Nothing here is live data about the world: it is the development log, to-do list and roadmap of this site. The dev agent edits the file each "
         "morning after it has checked every dashboard and worked on the roadmap; data/status/AGENT.md is its playbook.")
