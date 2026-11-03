"""Signals (/signals): the owner's approved signal per dashboard with its watch point, in one place. Data from app/signals.py, which
reads each dashboard's SIGNALS() (or its READINGS until SIGNALS is wired) and the approved list in data/signals/watchlist.json.
Also serves the daily email: /api/signals/newsletter (subject, html, text) and the /newsletter page.
"""
from __future__ import annotations

from . import Topic


def _S():
    from .. import signals   # lazy: app/signals.py imports app.topics, which discovers this module
    return signals

SLUG = "signals"
TOPIC = Topic(SLUG, "Signals",
              "The one thing to watch on each dashboard, its watch point, and whether it has been crossed. What flipped since yesterday, and the email that goes out each morning.",
              "signals", (("board", "Board"), ("watch", "Watch points"), ("flips", "Flipped today"), ("newsletter", "Newsletter")), ("board",), order=1)


def READINGS() -> list[dict]:
    b = _S().board()
    return [{"tab": "board", "key": "crossed", "label": "Watch points crossed", "value": b["totals"]["crossed"], "lean": -1 if b["totals"]["crossed"] else 0},
            {"tab": "watch", "key": "wired", "label": "Signals wired, of approved", "value": b["totals"]["wired"], "lean": 0, "note": f"of {b['totals']['signals']}"}]


ENDPOINTS = {"board": lambda: _S().board(), "front": lambda: _S().front(), "watch": lambda: _S().board(),
             "flips": lambda: _S().flips(), "newsletter": lambda: _S().newsletter()}
SOURCES = [{"name": "data/signals/watchlist.json (the approved list)", "url": "https://github.com/mcmarcocheung98-max/dashboards/blob/main/data/signals/watchlist.json", "cadence": "on approval"}]
NOTES = ("Each dashboard computes its own signals from the data it already caches; this page only gathers them. A signal shown as 'not wired yet' is "
         "approved but its dashboard has not implemented it; the first readings stand in on the front page meanwhile. Not investment advice.")
