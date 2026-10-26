"""One zip of every dashboard, for the month-end archive (.github/workflows/archive.yml uploads it to OneDrive).

archive/<date>/
  index.json, health.json
  <slug>/meta.json, <slug>/<endpoint>.json   every endpoint as the page sees it (<endpoint>.error.txt when it failed)
  <slug>/changes.json, <slug>/daily/*.json   what changed since yesterday and every daily snapshot behind it
  data/...                                   the hand-entered CSVs and notes, as committed

run() copies it to OneDrive (app/cloud.py) on the last day of each month, plus once as soon as OneDrive is set up; due() decides.
The status (no secrets) is in SNAPSHOT_DIR/archive_status.json and on /api/health under "archive".
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


# ---- month end: build the zip and copy it to OneDrive (app/cloud.py), from the server's warmer loop
STATUS = SNAP_DIR / "archive_status.json"


def status() -> dict:
    try:
        return json.loads(STATUS.read_text())
    except (OSError, ValueError):
        return {}


def _month_end(d: datetime) -> bool:
    from datetime import timedelta
    return (d + timedelta(days=1)).day == 1


def _prev_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def due(now: datetime | None = None, st: dict | None = None) -> bool:
    """Once on the last day of each month (UTC); after downtime, a missed month end is caught up the next time the server runs; and
    straight away the first time OneDrive works, so the set-up shows a file the same day. A failed attempt is retried after an hour."""
    now = now or datetime.now(timezone.utc)
    st = status() if st is None else st
    if not st.get("ok", True) and st.get("last_try") and now.timestamp() - st["last_try"] < 3600:
        return False
    if not st.get("first"):
        return True
    month, done = now.strftime("%Y-%m"), set(st.get("months_done", []))
    if _month_end(now):
        return month not in done
    prev = _prev_month(month)
    return prev >= st["first"][:7] and prev not in done


def run(now: datetime | None = None) -> dict:
    from . import cloud
    now = now or datetime.now(timezone.utc)
    st = status()
    st["last_try"] = now.timestamp()
    if not cloud.configured():
        st.update(ok=False, error="OneDrive not set up (ONEDRIVE_RCLONE_CONF)")
    else:
        try:
            first = not st.get("first")
            label = now.strftime("%Y-%m") if (first or _month_end(now)) else _prev_month(now.strftime("%Y-%m"))   # a catch-up files under the month it stands for
            data = build()
            path = cloud.upload_bytes(data, f"Archive/{label}", f"dashboards-{now.strftime('%Y-%m-%d')}.zip")
            st.update(ok=True, error="", path=f"{cloud.folder()}/{path}", bytes=len(data), ts=now.timestamp())
            if first:
                st["first"] = now.strftime("%Y-%m-%d")
            else:
                st["months_done"] = sorted(set(st.get("months_done", [])) | {label})
        except Exception as e:
            st.update(ok=False, error=f"{type(e).__name__}: {cloud._scrub(str(e))[:300]}")
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(st))
    return st


def health() -> dict:
    from . import cloud
    st = status()
    return {"onedrive": cloud.status_line() if cloud.configured() else "OneDrive: not set up (ONEDRIVE_RCLONE_CONF)", "conf": cloud.conf_shape(),
            "last": {k: st.get(k) for k in ("ok", "path", "bytes", "error", "ts", "last_try", "first", "months_done")}}
