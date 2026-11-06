"""Daily Claude token usage and graphify lookups, for the Graphify Map's "Daily tokens" tab (data/graphify/usage.json).

Two inputs, both optional, both idempotent (a day already recorded for a session is replaced, not added twice):

    python scripts/graphify_usage.py --transcript PATH [--session dev-agent]
        A Claude Code transcript (.jsonl) on this machine: tokens per day from each model response (input, cache writes, cache
        reads, output; a response split over several lines is counted once) and graphify lookups per day (query, explain and
        path commands in Bash calls). Measured. The dev agent runs this on its own session each morning.

    python scripts/graphify_usage.py --totals FILE
        Running totals per session collected from the sessions' run records ({"collected_at", "sessions": {slug: {"as_of",
        "input", "cache_write", "cache_read", "output", "cost_usd"}}}). The difference from the previous snapshot is that
        session's use since then, recorded on the snapshot's date; the first snapshot of a session is only a starting point.

Lookups are known only where a transcript was read; data/graphify/README.md explains how the tab estimates the rest.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "graphify" / "usage.json"
SAVINGS = ROOT / "data" / "graphify" / "savings.json"
KINDS = ("input", "cache_write", "cache_read", "output")
LOOKUP = re.compile(r"\bgraphify (?:query|explain|path)\b")


def load() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text())
    return {"days": [], "snapshots": {}}


def save(d: dict) -> None:
    d["days"].sort(key=lambda r: (r["date"], r["session"]))
    try:
        t = json.loads(SAVINGS.read_text())["tasks"]
        d["saving_per_lookup"] = int(statistics.median(x["naive_tokens"] - x["graph_tokens"] for x in t))
        d["saving_measured"] = json.loads(SAVINGS.read_text()).get("measured")
    except (OSError, KeyError, ValueError):
        pass
    d["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    OUT.write_text(json.dumps(d, indent=1) + "\n")


def put(d: dict, row: dict) -> None:
    d["days"] = [r for r in d["days"] if not (r["date"] == row["date"] and r["session"] == row["session"])] + [row]


def from_transcript(d: dict, path: Path, session: str) -> int:
    day: dict[str, dict] = defaultdict(lambda: {k: 0 for k in (*KINDS, "lookups")})
    seen = set()
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "assistant":
            continue
        m, date = e.get("message") or {}, (e.get("timestamp") or "")[:10]
        if not date:
            continue
        u = m.get("usage") or {}
        if u and m.get("id") not in seen:
            seen.add(m.get("id"))
            r = day[date]
            r["input"] += u.get("input_tokens") or 0
            r["cache_write"] += u.get("cache_creation_input_tokens") or 0
            r["cache_read"] += u.get("cache_read_input_tokens") or 0
            r["output"] += u.get("output_tokens") or 0
        for c in m.get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Bash":
                day[date]["lookups"] += len(LOOKUP.findall((c.get("input") or {}).get("command", "")))
    for date, r in day.items():
        put(d, {"date": date, "session": session, **r, "source": "transcript"})
    return len(day)


def from_totals(d: dict, path: Path) -> int:
    snap = json.loads(path.read_text())
    n = 0
    for slug, s in (snap.get("sessions") or {}).items():
        if not s:
            continue
        prev = d["snapshots"].get(slug)
        if prev and prev.get("as_of") and s.get("as_of") and s["as_of"] > prev["as_of"]:
            delta = {k: max(0, int(s.get(k) or 0) - int(prev.get(k) or 0)) for k in KINDS}
            cost = max(0.0, float(s.get("cost_usd") or 0) - float(prev.get("cost_usd") or 0))
            if any(delta.values()):
                put(d, {"date": s["as_of"][:10], "session": slug, **delta, "cost_usd": round(cost, 2), "source": "totals",
                        "since": prev["as_of"][:16]})
                n += 1
        d["snapshots"][slug] = {k: s.get(k) for k in ("id", "as_of", *KINDS, "cost_usd")}
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", type=Path)
    ap.add_argument("--session", default="dev-agent")
    ap.add_argument("--totals", type=Path)
    a = ap.parse_args()
    d = load()
    if a.transcript:
        print(f"{a.session}: {from_transcript(d, a.transcript, a.session)} days from the transcript")
    if a.totals:
        print(f"{from_totals(d, a.totals)} session-days from the totals")
    save(d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
