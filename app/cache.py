"""In-memory cache with a time to live: every endpoint and every download goes through _cached, so traffic costs nothing extra."""
from __future__ import annotations

import math
import time

_cache: dict = {}


def _cached(key: str, ttl: float, fn):
    hit = _cache.get(key)
    if hit and hit[0] > time.time() - ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def _num(v):
    """JSON has no NaN / infinity: send null instead."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v
