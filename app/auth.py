"""Private dashboards: a Topic with private=True is left off the index and its page data, script and Ask Claude answers need a
passcode (Railway variable PRIVATE_PASSCODE). POST /api/unlock checks it and sets an HttpOnly cookie for 30 days; POST /api/lock
clears it. Changing the passcode signs everyone out. Wrong guesses: 5 per visitor per 15 minutes (visitors by hashed IP).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time

COOKIE = "dash_auth"
DAYS = 30
TRIES, WINDOW = 5, 15 * 60
_fails: dict[str, list[float]] = {}
_lock = threading.Lock()


def passcode() -> str:
    return os.environ.get("PRIVATE_PASSCODE", "")


def configured() -> bool:
    return bool(passcode())


def _key() -> bytes:
    secret = os.environ.get("AUTH_SECRET") or ("dashboards-auth|" + passcode())
    return hashlib.sha256(secret.encode()).digest()


def _sig(exp: int) -> str:
    return hmac.new(_key(), f"{exp}|{passcode()}".encode(), hashlib.sha256).hexdigest()


def token(now: float | None = None) -> str:
    exp = int((now or time.time()) + DAYS * 86400)
    return f"{exp}.{_sig(exp)}"


def valid(cookie: str | None, now: float | None = None) -> bool:
    if not configured() or not cookie or "." not in cookie:
        return False
    exp, sig = cookie.split(".", 1)
    try:
        if int(exp) < (now or time.time()):
            return False
        return hmac.compare_digest(sig, _sig(int(exp)))
    except ValueError:
        return False


def _visitor(ip: str) -> str:
    return hashlib.sha256(("dashboards-unlock|" + (ip or "?")).encode()).hexdigest()[:16]


class TooMany(Exception):
    pass


def unlock(given: str, ip: str, now: float | None = None) -> str | None:
    """A cookie value for the right passcode, None for a wrong one; TooMany after too many wrong tries."""
    now = now or time.time()
    vid = _visitor(ip)
    with _lock:
        recent = [t for t in _fails.get(vid, []) if now - t < WINDOW]
        _fails[vid] = recent
        if len(recent) >= TRIES:
            raise TooMany("Too many wrong passcodes; try again in 15 minutes.")
    if configured() and hmac.compare_digest(hashlib.sha256((given or "").encode()).digest(), hashlib.sha256(passcode().encode()).digest()):
        with _lock:
            _fails.pop(vid, None)
        return token(now)
    with _lock:
        _fails.setdefault(vid, []).append(now)
    return None


def allowed(slug: str, cookie: str | None) -> bool:
    """Public dashboards always; private ones only with a valid cookie."""
    from . import topics
    t = topics.REGISTRY.get(slug)
    return t is None or not getattr(t, "private", False) or valid(cookie)
