"""Export the graphify map for the /graphify dashboard: data/graphify/map.json (clusters, god nodes, audit counts, surprises, every
node and link in compact form) and data/graphify/savings.json (tokens a session spends answering real tasks from this project with
the map against reading the files a search would point to).

    python scripts/graphify_export.py            # map.json from graphify-out/graph.json
    python scripts/graphify_export.py --bench    # also run the task benchmark (needs the graphify command; ~1 minute)

Run after /graphify (the full build, docs included) so the map carries the documentation layer; `graphify update .` alone keeps the
code half current. graphify-out/ itself stays out of git; these two files are what the live site serves.
"""
from __future__ import annotations

import collections
import glob
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "graphify"
GRAPH = ROOT / "graphify-out" / "graph.json"

# What a session would otherwise read: real questions from this project and the words a grep for them would use.
TASKS = [
    ("Where does the top card follow the timeline, and how do dashboards use it?", ["followHead", "datedHead"]),
    ("What does _r() do and who depends on it?", ["_r("]),
    ("How does the month-end archive reach OneDrive?", ["archive", "rclone"]),
    ("How are Ask Claude questions rate-limited?", ["ASK_PER_HOUR", "Limit"]),
    ("How does a private dashboard check the passcode?", ["PRIVATE_PASSCODE", "dash_auth"]),
    ("Where are NBA odds de-vigged into a fair price?", ["devig", "fair_p"]),
    ("How is the Pokemon heat score built?", ["heat", "cooldown"]),
    ("How does what-changed-since-yesterday save a snapshot a day?", ["save_today", "READINGS"]),
    ("Which sources does the housing dashboard download?", ["housing", "fetch("]),
    ("How does fetch fall back to a disk snapshot when a source is down?", ["snapshot", "STALE"]),
]


def dash_of(path: str) -> str:
    for pat in (r"app/topics/([a-z_]+)\.py", r"app/static/topics/([a-z-]+)\.js", r"data/([a-z-]+)/", r"tests/test_([a-z_]+)\.py"):
        m = re.match(pat, path or "")
        if m:
            return m.group(1).replace("-", "_")
    return "shared"


def export_map() -> dict:
    g = json.loads(GRAPH.read_text())
    nodes = {n["id"]: n for n in g["nodes"]}
    deg: collections.Counter = collections.Counter()
    for e in g["links"]:
        deg[e["source"]] += 1
        deg[e["target"]] += 1
    com: dict[str, list] = collections.defaultdict(list)
    for n in g["nodes"]:
        com[n.get("community_name") or "Other"].append(n)
    cidx = {c: i for i, c in enumerate(com)}
    cc: collections.Counter = collections.Counter()
    for e in g["links"]:
        a, b = nodes.get(e["source"]), nodes.get(e["target"])
        if a and b:
            ca, cb = a.get("community_name") or "Other", b.get("community_name") or "Other"
            if ca != cb:
                cc[tuple(sorted((ca, cb)))] += 1
    communities = []
    for c, ns in com.items():
        files = collections.Counter(n.get("source_file") for n in ns)
        top = sorted(ns, key=lambda n: -deg[n["id"]])[:6]
        communities.append({"id": cidx[c], "name": c, "size": len(ns), "files": [f for f, _ in files.most_common(3) if f],
                            "types": dict(collections.Counter(n.get("file_type") for n in ns)),
                            "dash": collections.Counter(dash_of(n.get("source_file")) for n in ns).most_common(1)[0][0],
                            "top": [{"id": n["id"], "label": n["label"], "deg": deg[n["id"]], "file": n.get("source_file"), "loc": n.get("source_location")} for n in top]})
    gods = [{"id": i, "label": nodes[i]["label"], "deg": d, "file": nodes[i].get("source_file"), "community": nodes[i].get("community_name")}
            for i, d in deg.most_common(30) if i in nodes and nodes[i].get("source_file")]
    godlinks = {}
    for gd in gods[:12]:
        cs: collections.Counter = collections.Counter()
        for e in g["links"]:
            o = e["target"] if e["source"] == gd["id"] else e["source"] if e["target"] == gd["id"] else None
            if o in nodes:
                cs[nodes[o].get("community_name") or "Other"] += 1
        godlinks[gd["id"]] = [{"c": cidx[c], "n": n} for c, n in cs.most_common(40) if c in cidx]
    surprises, seen = [], set()
    for e in sorted(g["links"], key=lambda e: -(e.get("confidence_score") or 0)):
        if e.get("confidence") == "EXTRACTED" or e["relation"] in ("indirect_call", "calls", "contains", "imports", "imports_from"):
            continue
        a, b = nodes.get(e["source"]), nodes.get(e["target"])
        if not a or not b or not a.get("source_file") or not b.get("source_file") or a["source_file"] == b["source_file"]:
            continue
        if (a["label"], b["label"]) in seen:
            continue
        seen.add((a["label"], b["label"]))
        surprises.append({"a": a["label"], "b": b["label"], "rel": e["relation"], "conf": e["confidence"], "score": e.get("confidence_score"), "fa": a["source_file"], "fb": b["source_file"]})
    small_nodes = [{"id": n["id"], "l": n["label"][:60], "c": cidx[n.get("community_name") or "Other"], "t": n.get("file_type"), "f": n.get("source_file"), "d": deg[n["id"]], "loc": n.get("source_location")}
                   for n in g["nodes"] if n.get("source_file")]
    keep = {n["id"] for n in small_nodes}
    small_edges = [[e["source"], e["target"], e["relation"][:12], e["confidence"][0]] for e in g["links"] if e["source"] in keep and e["target"] in keep]
    return {"built_at": (g.get("built_at_commit") or "")[:7], "exported": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "stats": {"nodes": len(g["nodes"]), "edges": len(g["links"]), "communities": len(com), "files": len({n.get("source_file") for n in g["nodes"] if n.get("source_file")}),
                      "rel": dict(collections.Counter(e["relation"] for e in g["links"])), "conf": dict(collections.Counter(e["confidence"] for e in g["links"])),
                      "types": dict(collections.Counter(n.get("file_type") for n in g["nodes"])), "hyperedges": len(g.get("hyperedges", []))},
            "communities": sorted(communities, key=lambda c: -c["size"]), "comm_edges": [{"a": cidx[a], "b": cidx[b], "w": w} for (a, b), w in cc.items() if w >= 2],
            "gods": gods, "godlinks": godlinks, "surprises": surprises[:40],
            "dashboards": dict(collections.Counter(dash_of(n.get("source_file")) for n in g["nodes"] if n.get("source_file"))),
            "hyperedges": [{"label": h["label"], "n": len(h["nodes"]), "file": h.get("source_file")} for h in g.get("hyperedges", [])],
            "nodes": small_nodes, "edges": small_edges}


def export_savings() -> dict:
    files = [f for f in glob.glob("app/**/*.*", recursive=True) + glob.glob("data/**/*.md", recursive=True) + glob.glob("docs/*.md") + glob.glob("tests/*.py") + ["README.md"]
             if not f.endswith((".pyc", ".png", ".json"))]
    text = {f: Path(f).read_text(encoding="utf-8", errors="replace") for f in files}
    tok = lambda s: len(s) // 4                                   # four characters per token, the usual rule of thumb
    tasks = []
    for q, needles in TASKS:
        hits = sorted({f for f in files for n in needles if n in text[f]})
        naive = sum(tok(text[f]) for f in hits)
        r = subprocess.run(["graphify", "query", q, "--budget", "1500"], capture_output=True, text=True, timeout=180)
        m = re.search(r"\| (\d+) nodes found", r.stdout)
        tasks.append({"task": q, "keywords": needles, "files": len(hits), "naive_tokens": naive, "graph_tokens": tok(r.stdout),
                      "nodes_found": int(m.group(1)) if m else None, "example_files": hits[:4]})
    bench = subprocess.run(["graphify", "benchmark"], capture_output=True, text=True, timeout=300).stdout
    corpus_tokens = re.search(r"~([\d,]+) tokens \(naive\)", bench)
    avg = re.search(r"Avg query cost:\s+~([\d,]+)", bench)
    red = re.search(r"Reduction:\s+([\d.]+)x", bench)
    return {"measured": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "tasks": tasks,
            "repo_tokens": sum(tok(t) for t in text.values()), "repo_files": len(files),
            "graphify_benchmark": {"corpus_tokens": int(corpus_tokens.group(1).replace(",", "")) if corpus_tokens else None,
                                   "avg_query_tokens": int(avg.group(1).replace(",", "")) if avg else None, "reduction_x": float(red.group(1)) if red else None},
            "method": "tokens = characters / 4. Naive = every file a search for the task's keywords would point you to, read whole, which is what a session "
                      "does without the map. Graph = the text graphify query returns for the same question, capped at 1,500 tokens. graphify's own benchmark "
                      "compares an average query with reading the whole corpus."}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    m = export_map()
    (OUT / "map.json").write_text(json.dumps(m, separators=(",", ":")))
    print(f"map.json: {m['stats']['nodes']} nodes, {m['stats']['edges']} edges, {m['stats']['communities']} clusters")
    if "--bench" in sys.argv:
        s = export_savings()
        (OUT / "savings.json").write_text(json.dumps(s, indent=1))
        for t in s["tasks"]:
            print(f"  {t['graph_tokens']:6d} vs {t['naive_tokens']:7d} ({(1 - t['graph_tokens'] / max(1, t['naive_tokens'])) * 100:5.1f}% saved)  {t['task']}")
        print("savings.json:", s["graphify_benchmark"])
