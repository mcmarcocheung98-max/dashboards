"""Shared plumbing for the dashboards: fetch with a disk snapshot, hand-entered series, payload helpers.

Every dashboard module (housing.py, ai_jobs.py, ...) follows public_charts.py: ENDPOINTS = {name: fn}, each fn cached, each chart
built with _part so one dead source blanks one chart. What is new here:

  fetch(url, ttl)      download, cache in memory for `ttl` seconds AND keep the raw text on the volume (SNAPSHOT_DIR, see config.py). When the source
                       is down the last snapshot is served instead and the payload says since when ("stale"), so a visitor sees the last
                       good chart with a small warning rather than nothing.
  manual(slug, name)   a hand-entered series from data/<slug>/<name>.csv (date,value,source,note; or date,series,value,...)
                       for data that has no free API (announcements, surveys). Adding a point = one committed line; Railway redeploys.
  payload(parts)       builds {key: value, key_error: ..., as_of, stale} from {key: fn}.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ..cache import _cached, _num
from ..config import DATA_DIR, SNAP_DIR

MANUAL_DIR = DATA_DIR
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/csv,application/json,text/plain,*/*"}
HOUR, DAY = 3600, 86400


def _r(x, d: int = 4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, d) if np.isfinite(x) else None


def _pts(s: pd.Series, d: int = 4, since: pd.Timestamp | None = None) -> list[list]:
    s = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if since is not None:
        s = s[s.index >= since]
    return [[int(pd.Timestamp(t).timestamp()), _r(v, d)] for t, v in s.items()]


def _part(out: dict, key: str, fn) -> None:
    """Fill out[key] from fn(); on failure leave None and say why (type only), so one dead source blanks one chart."""
    try:
        out[key] = fn()
    except Exception as e:
        out[key] = None
        out[f"{key}_error"] = type(e).__name__


def _years_ago(n: float) -> pd.Timestamp:
    return pd.Timestamp.now("UTC").tz_localize(None).normalize() - pd.Timedelta(days=int(n * 365.25))


def _last(s: pd.Series):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return (str(s.index[-1].date()), _r(s.iloc[-1], 4)) if len(s) else (None, None)


# ------------------------------------------------------------------ fetch with a disk snapshot
STALE: dict[str, float] = {}            # url -> snapshot time, for sources served from the snapshot because the download failed


def _snap(url: str) -> Path:
    return SNAP_DIR / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")


def _download(url: str, timeout: int = 60, curl: bool = False, headers: dict | None = None, binary: bool = False) -> str:
    """The body as text. binary=True returns the bytes decoded as latin-1 (lossless: .encode("latin-1") gives the bytes back), so a
    workbook or zip goes through the same snapshot path as a CSV."""
    if curl:    # FRED (and some UK sites) reset python-requests connections (TLS fingerprinting); plain curl is unaffected (see events._curl)
        cmd = ["curl", "-s", "-f", "-L", "--retry", "2", "--max-time", str(timeout), "-A", UA["User-Agent"], url]
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    r = requests.get(url, headers={**UA, **(headers or {})}, timeout=timeout)
    r.raise_for_status()
    return r.content.decode("latin-1") if binary else r.text


def fetch(url: str, ttl: float = DAY, *, curl: bool = False, headers: dict | None = None, timeout: int = 60, min_bytes: int = 50, binary: bool = False) -> str:
    """The text at `url`, cached in memory for `ttl` seconds and kept on disk; the disk copy is served (and STALE[url] set) when the
    download fails. Raises only when there is neither."""
    def go():
        snap = _snap(url)
        try:
            text = _download(url, timeout, curl, headers, binary)
            if len(text) < min_bytes:
                raise ValueError(f"short response ({len(text)} bytes)")
            SNAP_DIR.mkdir(parents=True, exist_ok=True)
            snap.write_text(text, encoding="utf-8")
            STALE.pop(url, None)
            return text
        except Exception:
            if snap.exists():
                STALE[url] = snap.stat().st_mtime
                return snap.read_text(encoding="utf-8")
            raise
    return _cached(f"topic:{url}", ttl, go)


def fetch_csv(url: str, ttl: float = DAY, **kw) -> pd.DataFrame:
    from io import StringIO
    read = {k: kw.pop(k) for k in list(kw) if k in ("sep", "skiprows", "header", "names", "usecols", "dtype", "engine")}
    return pd.read_csv(StringIO(fetch(url, ttl, **kw)), **read)


def fetch_json(url: str, ttl: float = DAY, **kw):
    return json.loads(fetch(url, ttl, **kw))


def stale_info(urls: list[str]) -> dict:
    """{url: 'YYYY-MM-DD'} for the sources served from a snapshot (empty when everything is fresh)."""
    return {u: pd.Timestamp(STALE[u], unit="s").strftime("%Y-%m-%d") for u in urls if u in STALE}


# ------------------------------------------------------------------ hand-entered series (data/<slug>/<name>.csv)
def manual_rows(slug: str, name: str) -> list[dict]:
    f = MANUAL_DIR / slug / f"{name}.csv"
    if not f.exists():
        return []
    with f.open(newline="", encoding="utf-8") as fh:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(fh)]
    return [r for r in rows if r.get("date") and not r["date"].startswith("#")]


def manual(slug: str, name: str) -> pd.Series | dict[str, pd.Series]:
    """date,value[,source,note] -> Series (float, sorted); date,series,value,... -> {series: Series}."""
    rows = manual_rows(slug, name)
    if not rows:
        return pd.Series(dtype=float)

    def ser(rs):
        s = pd.Series({pd.Timestamp(r["date"]): pd.to_numeric(r["value"], errors="coerce") for r in rs if r.get("value") not in (None, "")}, dtype=float)
        return s.sort_index().dropna()
    if "series" in rows[0]:
        out: dict[str, list] = {}
        for r in rows:
            out.setdefault(r["series"], []).append(r)
        return {k: ser(v) for k, v in out.items()}
    return ser(rows)


def manual_sources(slug: str, name: str) -> list[dict]:
    """Distinct sources cited in a manual file, newest first: [{source, date}]."""
    seen, out = set(), []
    for r in sorted(manual_rows(slug, name), key=lambda r: r["date"], reverse=True):
        s = r.get("source", "")
        if s and s not in seen:
            seen.add(s)
            out.append({"source": s, "date": r["date"]})
    return out


# ------------------------------------------------------------------ payloads
def payload(parts: dict, sources: list[str] = (), as_of=None) -> dict:
    """{key: fn()} with _part; adds as_of (latest date seen, or the one given) and stale ({url: since} for snapshot-served sources)."""
    out: dict = {}
    for k, fn in parts.items():
        _part(out, k, fn)
    out["as_of"] = as_of
    out["stale"] = stale_info(list(sources))
    out["updated"] = int(time.time())
    return out


def latest_date(*series: pd.Series | None) -> str | None:
    ds = [s.dropna().index.max() for s in series if s is not None and len(s.dropna())]
    return str(max(ds).date()) if ds else None


def yoy(s: pd.Series, periods: int = 12) -> pd.Series:
    return s / s.shift(periods) - 1


def monthly(s: pd.Series, how: str = "last") -> pd.Series:
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    return getattr(s.resample("MS"), how)().dropna()


def weekly(s: pd.Series, how: str = "mean") -> pd.Series:
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    return getattr(s.resample("W"), how)().dropna()


def json_safe(obj):
    """What the server does to every payload (json.dumps allow_nan=False) must not fail: a quick check used in tests."""
    return json.loads(json.dumps(obj, default=str, allow_nan=False))


__all__ = ["fetch", "fetch_csv", "fetch_json", "manual", "manual_rows", "manual_sources", "payload", "_pts", "_part", "_r", "_num",
           "_years_ago", "_last", "latest_date", "yoy", "monthly", "weekly", "stale_info", "STALE", "SNAP_DIR", "MANUAL_DIR", "HOUR", "DAY"]
