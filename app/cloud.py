"""OneDrive as the off-site home of the month-end archive (app/archive.py), through rclone (installed in the Docker image).
Ported from the trading bot (trading-system src/hl/cloud.py), which uses the same login.

Set-up, once: give this Railway service the variable ONEDRIVE_RCLONE_CONF with the same text as the trading bot's (copy it from the
bot's Variables tab, or reference it: ${{<bot service>.ONEDRIVE_RCLONE_CONF}}). It is the output of `rclone config show onedrive`
and may be pasted in any shape (one line, quoted, literal \n): normalize() repairs it. Optional: ONEDRIVE_FOLDER (default Dashboards).
The server writes it to SNAPSHOT_DIR/rclone.conf (owner-only, never in the archive) and rclone keeps its refreshed token there.

Layout in OneDrive:  <folder>/Archive/<YYYY-MM>/dashboards-<YYYY-MM-DD>.zip
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import SNAP_DIR

CONF = SNAP_DIR / "rclone.conf"
CONF_SRC = SNAP_DIR / "rclone.conf.src"            # hash of the Railway variable the file was written from: a new paste replaces the file
KEYS = ("type", "token", "drive_id", "drive_type", "region", "client_id", "client_secret", "auth_url", "token_url", "tenant")
REMOTE = "onedrive"
ENV_CONF, ENV_FOLDER = "ONEDRIVE_RCLONE_CONF", "ONEDRIVE_FOLDER"
TIMEOUT_S = 900


def folder(env=None) -> str:
    env = os.environ if env is None else env
    return (env.get(ENV_FOLDER) or "Dashboards").strip("/")


def binary() -> str | None:
    return shutil.which("rclone")


def normalize(text: str) -> str:
    """The pasted `rclone config show` block as an rclone config file, whatever the paste did to it: quotes around it, literal \\n instead of
    line breaks, or everything on one line (Railway's variable editor can do that). The section is always named [onedrive]."""
    t = text.strip().strip("'\"").strip()
    if "\\n" in t and "\n" not in t:
        t = t.replace("\\n", "\n")
    if "\n" not in t:
        t = re.sub(r"^\[[^\]]*\]\s*", "[onedrive]\n", t)
        t = re.sub(r"\s+(?=(?:%s)\s*=)" % "|".join(KEYS), "\n", t)
    lines: list[str] = []
    for x in (y.strip() for y in t.splitlines() if y.strip()):
        if lines and not re.match(r"^\[.*\]$|^\w+\s*=", x):
            lines[-1] += x                                 # a wrapped line (the token is long): glue it back onto the line above
        else:
            lines.append(x)
    if lines and lines[0].startswith("["):
        lines[0] = f"[{REMOTE}]"
    else:
        lines.insert(0, f"[{REMOTE}]")
    return "\n".join(lines) + "\n"


def conf_shape(env=None) -> dict:
    """What the config looks like, without any value: for the disk report when OneDrive does not work."""
    env = os.environ if env is None else env
    text = env.get(ENV_CONF) or ""
    out = {"env_chars": len(text), "env_lines": text.count("\n") + 1 if text else 0, "env_literal_newlines": "\\n" in text, "rclone": bool(binary())}
    try:
        lines = CONF.read_text().splitlines()
        keys = [x.split("=", 1)[0].strip() for x in lines[1:] if "=" in x]
        out.update({"file_lines": len(lines), "file_first": lines[0][:20] if lines else "", "file_keys": [k if k in KEYS else f"<unknown, {len(k)} chars>" for k in keys],
                    "file_odd_lines": sum(1 for x in lines[1:] if "=" not in x)})      # only known key names are shown: a pasted value can never end up here
    except OSError:
        out["file_lines"] = 0
    return out


def ensure_conf(env=None) -> bool:
    """Write data/hl/rclone.conf from the Railway variable when it is new or changed; otherwise rclone owns the file (it rotates the token)."""
    env = os.environ if env is None else env
    text = (env.get(ENV_CONF) or "").strip()
    if not text:
        return CONF.exists()
    digest = hashlib.sha256((text + "|normalize-v2").encode()).hexdigest()      # bump the suffix when normalize() changes: the file is rebuilt
    try:
        same = CONF.exists() and CONF_SRC.read_text().strip() == digest
    except OSError:
        same = False
    if same:
        return True
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(normalize(text))
    CONF.chmod(0o600)
    CONF_SRC.write_text(digest)
    return True


def configured(env=None) -> bool:
    env = os.environ if env is None else env
    return bool(binary()) and (CONF.exists() or bool(env.get(ENV_CONF)))


SECRET_PATTERNS = [re.compile(p) for p in (r"(?<![0-9a-fA-F])(?:0x)?[0-9a-fA-F]{64}(?![0-9a-fA-F])", r'"(?:access|refresh)_token"\s*:\s*"[^"]*"',
                                            r"\bEw[A-Za-z0-9+/=_\-]{40,}", r"github_pat_[A-Za-z0-9_]+", r"\bghp_[A-Za-z0-9]+")]


def _scrub(text: str) -> str:
    """Hide anything that looks like a token before it is stored or shown on /api/health."""
    for p in SECRET_PATTERNS:
        text = p.sub("[hidden]", text)
    return text


def _run(args: list[str], timeout: float = TIMEOUT_S) -> str:
    if not ensure_conf():
        raise RuntimeError("OneDrive is not set up (ONEDRIVE_RCLONE_CONF)")
    rc = binary()
    if not rc:
        raise RuntimeError("rclone is not installed in this image")
    p = subprocess.run([rc, "--config", str(CONF), "--retries", "3", "--low-level-retries", "5", *args], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        err = " ".join((p.stderr or p.stdout).strip().splitlines()[-3:])
        raise RuntimeError(f"rclone {args[0]} failed ({p.returncode}): {_scrub(err)[:300]}")
    return p.stdout


def remote(path: str = "") -> str:
    return f"{REMOTE}:{folder()}" + (f"/{path.strip('/')}" if path else "")


def upload(local: Path, remote_dir: str, name: str | None = None) -> str:
    """Copy one file, then check its size on OneDrive. Returns the remote path (relative to the folder)."""
    name = name or local.name
    dest = f"{remote_dir.strip('/')}/{name}"
    _run(["copyto", str(local), remote(dest)])
    size = local.stat().st_size
    got = ls(remote_dir, name)
    if not got or got[0].get("Size") != size:
        raise RuntimeError(f"OneDrive upload of {name} did not verify (local {size} bytes, remote {got[0].get('Size') if got else 'missing'})")
    return dest


def upload_bytes(data: bytes, remote_dir: str, name: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / name
        p.write_bytes(data)
        return upload(p, remote_dir)


def ls(remote_dir: str, name: str | None = None) -> list[dict]:
    """Files in a OneDrive folder (rclone lsjson), or just one file; [] when the folder does not exist yet."""
    target = remote(remote_dir if name is None else f"{remote_dir.strip('/')}/{name}")
    try:
        out = _run(["lsjson", "--files-only", target] if name is None else ["lsjson", "--files-only", "--stat", target], timeout=120)
    except RuntimeError as e:
        if "directory not found" in str(e) or "object not found" in str(e):
            return []
        raise
    j = json.loads(out or "[]")
    return [j] if isinstance(j, dict) else j


def about() -> dict:
    """Space on the drive: {'total', 'used', 'free'} in bytes (whatever OneDrive reports)."""
    j = json.loads(_run(["about", f"{REMOTE}:", "--json"], timeout=120) or "{}")
    return {k: j.get(k) for k in ("total", "used", "free")}


def status_line() -> str:
    """One line for the /disk card; never raises."""
    if not configured():
        return "OneDrive: not set up (Railway variable ONEDRIVE_RCLONE_CONF, see docs/ARCHIVE.md)"
    try:
        a = about()
        h = lambda b: f"{b / 1e9:.1f} GB" if b else "?"
        return f"OneDrive: {h(a.get('used'))} used of {h(a.get('total'))}, {h(a.get('free'))} free"
    except Exception as e:
        return f"⚠ OneDrive not reachable: {str(e)[:160]}"
