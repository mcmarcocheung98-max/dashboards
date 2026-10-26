"""One zip of every dashboard, for the month-end archive (.github/workflows/archive.yml uploads it to OneDrive).

archive/<date>/
  index.json, health.json
  <slug>/meta.json, <slug>/<endpoint>.json   every endpoint as the page sees it (<endpoint>.error.txt when it failed)
  <slug>/changes.json, <slug>/daily/*.json   what changed since yesterday and every daily snapshot behind it
  data/...                                   the hand-entered CSVs and notes, as committed
"""
from __future__ import annotations

import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import topics
from .config import DATA_DIR, SNAP_DIR

PER_ENDPOINT = 180          # seconds; a cold endpoint is usually served from the warmer's cache in well under a second


def _dump(obj) -> str:
    return json.dumps(obj, default=str, indent=1)


def build() -> bytes:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    root = f"archive-{day}/"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, ThreadPoolExecutor(4) as pool:
        z.writestr(root + "index.json", _dump(topics.index()))
        try:
            z.writestr(root + "health.json", _dump(topics.health()))
        except Exception as e:
            z.writestr(root + "health.error.txt", f"{type(e).__name__}: {e}")
        for slug in topics.REGISTRY:
            base = f"{root}{slug}/"
            z.writestr(base + "meta.json", _dump(topics.meta(slug)))
            jobs = {name: pool.submit(fn) for name, fn in topics.endpoints(slug).items()}
            for name, job in jobs.items():
                try:
                    z.writestr(f"{base}{name}.json", _dump(job.result(timeout=PER_ENDPOINT)))
                except Exception as e:
                    z.writestr(f"{base}{name}.error.txt", f"{type(e).__name__}: {e}")
            try:
                z.writestr(base + "changes.json", _dump(topics.changes(slug)))
            except Exception as e:
                z.writestr(base + "changes.error.txt", f"{type(e).__name__}: {e}")
            for f in sorted((SNAP_DIR / "daily" / slug).glob("*.json")):
                z.write(f, f"{base}daily/{f.name}")
        for f in sorted(DATA_DIR.rglob("*")):
            if f.is_file():
                z.write(f, root + "data/" + f.relative_to(DATA_DIR).as_posix())
    return buf.getvalue()
