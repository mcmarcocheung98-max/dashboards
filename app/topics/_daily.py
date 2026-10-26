"""What changed since yesterday: one snapshot a day of each dashboard's indicator readings, and the difference between the last two.

A dashboard module opts in with READINGS() -> [{"tab", "key", "label", "value", "lean", "note"?}]: its headline indicators as they read
now, each with a lean of +1, 0 or -1 (what +1 means is the dashboard's call, and its README says so). READINGS should only read data
its endpoints already cache. The server calls save_today() for every dashboard from the warmer; the first good save of a UTC day is
kept, and files older than KEEP_DAYS are removed. /api/<slug>/changes serves changes(slug).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..config import SNAP_DIR

KEEP_DAYS = 400
STRIP_DAYS = 90


def _dir(slug: str):
    return SNAP_DIR / "daily" / slug


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _clean(rows) -> list[dict]:
    out = []
    for r in rows or []:
        if not isinstance(r, dict) or not r.get("key") or not r.get("tab"):
            continue
        lean = r.get("lean")
        lean = 0 if lean is None else max(-1, min(1, int(round(float(lean)))))
        v = r.get("value")
        if isinstance(v, float):
            v = round(v, 6)
        out.append({"tab": str(r["tab"]), "key": str(r["key"]), "label": str(r.get("label") or r["key"]), "value": v, "lean": lean,
                    **({"note": str(r["note"])} if r.get("note") else {})})
    return out


def save_today(slug: str, readings_fn, today: str | None = None) -> str:
    """Write today's readings once. Returns 'saved', 'exists' or 'empty'."""
    today = today or _today()
    d = _dir(slug)
    f = d / f"{today}.json"
    if f.exists():
        return "exists"
    rows = _clean(readings_fn())
    if not rows:
        return "empty"
    d.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"date": today, "readings": rows}, default=str))
    tmp.replace(f)
    for old in sorted(d.glob("*.json"))[:-KEEP_DAYS]:
        old.unlink(missing_ok=True)
    return "saved"


def _days(slug: str) -> list[dict]:
    out = []
    for f in sorted(_dir(slug).glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            continue
    return out


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def changes(slug: str, tabs: list | tuple = ()) -> dict:
    days = _days(slug)
    labels = {k: l for k, l in tabs}
    out = {"available": True, "first": days[0]["date"] if days else None, "latest": days[-1]["date"] if days else None, "since": None,
           "flipped": [], "moved": [], "new": [], "tabs": []}
    if len(days) >= 2:
        prev = {r["key"]: r for r in days[-2]["readings"]}
        out["since"] = days[-2]["date"]
        for r in days[-1]["readings"]:
            p = prev.get(r["key"])
            row = {**r, "tab_label": labels.get(r["tab"], r["tab"])}
            if p is None:
                out["new"].append(row)
            elif p["lean"] != r["lean"]:
                out["flipped"].append({**row, "was": p["value"], "was_lean": p["lean"]})
            elif p["value"] != r["value"]:
                out["moved"].append({**row, "was": p["value"]})
    order = [k for k, _ in tabs] or sorted({r["tab"] for d in days for r in d["readings"]})
    for t in order:
        strip = []
        for d in days[-STRIP_DAYS:]:
            rs = [r for r in d["readings"] if r["tab"] == t]
            strip.append({"date": d["date"], "lean": _sign(sum(r["lean"] for r in rs)) if rs else None, "n": len(rs)})
        if any(s["lean"] is not None for s in strip):
            out["tabs"].append({"tab": t, "label": labels.get(t, t), "days": strip})
    return out
