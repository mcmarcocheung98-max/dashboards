"""Count hand-entered rows still marked verify, per dashboard and file (the roadmap's r-verify-rows).

    python scripts/verify_count.py [data]        prints JSON: total, by_dashboard, files {slug: {file: [marked, rows]}}

A data row (not a comment, not the header) of data/<slug>/**/*.csv counts when one of its fields has a part, split on ";", that
starts with "verify" or ends with it ("verify", "verify: level from a press report", "from memory; verify", "context verify").
A part that says the mark was cleared ("checked 2026-11-09, verify cleared") does not count. A file with a column named "verify" counts its rows that say yes there."""
import csv, json, re, sys
from pathlib import Path
MARK = re.compile(r"^\s*verify\b|\bverify\s*$", re.I)
root = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
out = {}
for f in sorted(root.rglob("*.csv")):
    slug = f.relative_to(root).parts[0]
    n = rows = 0
    with f.open(newline="", encoding="utf-8", errors="replace") as fh:
        lines = [l for l in fh if l.strip() and not l.lstrip().startswith("#")]
    vcol = None
    for i, r in enumerate(csv.reader(lines)):
        if i == 0:
            vcol = next((k for k, c in enumerate(r) if c.strip().lower() == "verify"), None)       # some files carry a verify column: yes / blank
            continue
        rows += 1
        if vcol is not None and vcol < len(r) and r[vcol].strip().lower() in ("yes", "y", "true", "1", "verify"):
            n += 1
            continue
        if any(MARK.search(part) and "cleared" not in part.lower() for c in r for part in c.split(";")): n += 1
    if n: out.setdefault(slug, {})[str(f.relative_to(root / slug))] = [n, rows]
tot = {s: sum(v[0] for v in fs.values()) for s, fs in out.items()}
print(json.dumps({"total": sum(tot.values()), "by_dashboard": dict(sorted(tot.items(), key=lambda x: -x[1])), "files": out}, indent=1))
