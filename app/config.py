"""Paths. Hand-entered data is committed in data/; downloaded snapshots go to SNAPSHOT_DIR (a persistent volume on Railway)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SNAP_DIR = Path(os.environ.get("SNAPSHOT_DIR", ROOT / "snapshots"))
