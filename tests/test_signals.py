"""Signals (app/signals.py, /signals, /newsletter): the approved watchlist, SIGNALS merging, the front line and the email."""
import asyncio
import sys
import types

import pytest

from app import signals as S, topics
from app.cache import _cache


def smoke_patch():
    """Used by scripts/smoke.py. Nothing to patch: signals read what other dashboards cached and the committed watchlist."""


@pytest.fixture
def clean(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "SNAP_DIR", tmp_path / "snaps")          # the kept readings (signals_kept.json) stay out of the repo
    _cache.clear()
    yield
    _cache.clear()


def test_a_restart_keeps_the_last_reading(clean, monkeypatch):
    """After a restart a dashboard's payloads are not in memory, so its SIGNALS read nothing: the board shows the kept reading, marked."""
    import datetime as dt
    from app.topics import housing
    row = {"key": "price_yoy", "tab": "prices", "label": "London price change on a year", "value": -2.2, "unit": "%", "lean": -1, "watch": "turns negative", "crossed": True}
    monkeypatch.setattr(housing, "SIGNALS", lambda: [row], raising=False)
    first = S.collect()
    h = next(d for d in first["dashboards"] if d["slug"] == "housing")
    r = next(x for x in h["signals"] if x["key"] == "price_yoy")
    assert r["value"] == -2.2 and r["crossed"] and "kept" not in r and first["totals"]["kept"] == 0
    for cold in (lambda: [], lambda: [{**row, "value": None, "crossed": False}]):          # the module returns nothing, or the row without a value
        monkeypatch.setattr(housing, "SIGNALS", cold, raising=False)
        again = S.collect()
        h2 = next(d for d in again["dashboards"] if d["slug"] == "housing")
        r2 = next(x for x in h2["signals"] if x["key"] == "price_yoy")
        assert r2["value"] == -2.2 and r2["crossed"] and r2["wired"] and r2["kept"].endswith("UTC") and again["totals"]["kept"] == 1
        assert again["totals"]["wired"] == first["totals"]["wired"] and again["totals"]["crossed"] == first["totals"]["crossed"]
    # a reading older than KEEP_HOURS no longer stands in: an empty signal then shows as empty, and the old reading is forgotten
    kept = S._kept_load()
    kept["housing"]["price_yoy"]["t"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=S.KEEP_HOURS + 1)).isoformat(timespec="seconds")
    S._kept_save(kept)
    late = S.collect()
    r3 = next(x for x in next(d for d in late["dashboards"] if d["slug"] == "housing")["signals"] if x["key"] == "price_yoy")
    assert r3["value"] is None and "kept" not in r3 and late["totals"]["kept"] == 0 and "price_yoy" not in S._kept_load().get("housing", {})


def test_watchlist_covers_the_approved_dashboards():
    wl = S.watchlist()
    assert set(wl) >= {"housing", "ai", "robotaxi", "compute-chips", "china-us-tech", "demographics", "debt-rates", "climate", "longevity", "space", "pokemon-cards", "prediction-markets", "trends", "nba-odds"}
    assert "btc-cycles" not in wl and "altcoins" not in wl
    for slug, rows in wl.items():
        assert slug in topics.REGISTRY, slug
        assert 3 <= len(rows) <= (6 if slug == "luxury" else 5) and len({r["key"] for r in rows}) == len(rows)    # luxury: a sixth, the liquidity signal (approved 7 Nov 2026)
        assert all(r["signal"] and r["watch"] for r in rows)


def test_board_merges_signals_readings_and_not_wired(clean, monkeypatch):
    housing = topics.module("housing")
    monkeypatch.setattr(housing, "SIGNALS", lambda: [{"key": "price_yoy", "tab": "prices", "label": "London price change on a year", "value": -0.4, "unit": "%", "lean": -1, "watch": "turns negative, or passes +5%", "crossed": True},
                                                      {"key": "extra", "tab": "prices", "label": "An extra one", "value": 3, "lean": 0, "watch": "", "crossed": False}], raising=False)
    monkeypatch.setattr(housing, "READINGS", lambda: [{"tab": "prices", "key": "r1", "label": "A reading", "value": 1.0, "lean": 1}], raising=False)
    b = S.collect()
    h = next(d for d in b["dashboards"] if d["slug"] == "housing")
    keys = [r["key"] for r in h["signals"]]
    assert keys[:5] == ["price_yoy", "fixed_2y", "price_to_pay", "boroughs_up", "rent_real"] and "extra" in keys
    assert h["signals"][0]["crossed"] and h["signals"][0]["wired"] and not h["signals"][1]["wired"]
    assert h["wired"] == 2 and h["crossed"] == 1 and b["totals"]["crossed"] >= 1
    assert "signals" not in [d["slug"] for d in b["dashboards"]] and "status" not in [d["slug"] for d in b["dashboards"]]
    t = S.top(h)
    assert t["kind"] == "crossed" and t["key"] == "price_yoy"
    other = next(d for d in b["dashboards"] if d["slug"] != "housing" and not d["wired"])
    assert S.top(other) is None or S.top(other)["kind"] == "reading"


def test_front_and_newsletter(clean, monkeypatch):
    housing = topics.module("housing")
    monkeypatch.setattr(housing, "SIGNALS", lambda: [{"key": "fixed_2y", "tab": "afford", "label": "2-year fixed mortgage rate (BoE)", "value": 3.9, "unit": "%", "lean": 1, "watch": "below 4.0%", "crossed": True}], raising=False)
    f = S.front()
    assert f["dashboards"]["housing"]["kind"] == "crossed" and f["crossed"] >= 1
    n = S.newsletter()
    assert n["subject"].startswith("Dashboards: ") and "watch point" in n["subject"]
    assert "Watch points crossed" in n["html"] and "2-year fixed mortgage rate" in n["html"] and "<script" not in n["html"]
    assert "WATCH POINTS CROSSED" in n["text"] and "3.9%" in n["text"]
    assert S.fmt(3.9, "%") == "3.9%" and S.fmt(1234567) == "1,234,567" and S.fmt(None) == "–" and S.fmt(True) == "yes"


def test_routes(clean):
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            page = await c.get("/newsletter")
            api = await c.get("/api/signals/front")
            board = await c.get("/api/signals/board")
            return page.status, page.headers.get("Content-Type", ""), await page.text(), api.status, (await board.json())["totals"]
    st, ct, body, ast, totals = asyncio.run(go())
    assert st == 200 and "text/html" in ct and "Dashboards" in body and ast == 200 and totals["signals"] >= 60
