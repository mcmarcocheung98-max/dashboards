"""What changed since yesterday: daily snapshots of READINGS and the difference between the last two (app/topics/_daily.py)."""
import asyncio

import pytest

from app import topics
from app.topics import _daily as D

TABS = (("prices", "Prices"), ("rates", "Rates"))


def rows(price, plean, rate=4.0, rlean=-1):
    return [{"tab": "prices", "key": "hpi", "label": "House prices YoY", "value": price, "lean": plean},
            {"tab": "rates", "key": "bank", "label": "Bank Rate", "value": rate, "lean": rlean}]


@pytest.fixture
def daily(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "SNAP_DIR", tmp_path)
    return tmp_path


def test_one_save_a_day_and_pruning(daily, monkeypatch):
    assert D.save_today("x", lambda: rows(1.0, 1), "2026-10-01") == "saved"
    assert D.save_today("x", lambda: rows(9.0, -1), "2026-10-01") == "exists"     # the first good save of the day stays
    assert D.save_today("x", lambda: [], "2026-10-02") == "empty"
    monkeypatch.setattr(D, "KEEP_DAYS", 2)
    for day in ("2026-10-02", "2026-10-03"):
        D.save_today("x", lambda: rows(1.0, 1), day)
    assert sorted(f.stem for f in (daily / "daily" / "x").glob("*.json")) == ["2026-10-02", "2026-10-03"]


def test_changes_flipped_moved_and_strip(daily):
    assert D.changes("x", TABS)["since"] is None                                   # nothing to compare yet
    D.save_today("x", lambda: rows(1.0, 1), "2026-10-01")
    one = D.changes("x", TABS)
    assert one["first"] == "2026-10-01" and one["since"] is None and not one["flipped"]
    D.save_today("x", lambda: rows(-0.5, -1, 3.75, -1) + [{"tab": "rates", "key": "new", "value": 1, "lean": 0.4}], "2026-10-02")
    c = D.changes("x", TABS)
    assert c["since"] == "2026-10-01" and c["latest"] == "2026-10-02"
    assert [(r["key"], r["was"], r["value"], r["was_lean"], r["lean"], r["tab_label"]) for r in c["flipped"]] == [("hpi", 1.0, -0.5, 1, -1, "Prices")]
    assert [r["key"] for r in c["moved"]] == ["bank"] and [r["key"] for r in c["new"]] == ["new"]
    strips = {t["tab"]: [d["lean"] for d in t["days"]] for t in c["tabs"]}
    assert strips == {"prices": [1, -1], "rates": [-1, -1]}


def test_dashboard_without_readings_and_endpoint(daily, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    slug = next(iter(topics.REGISTRY))
    mod = topics.module(slug)
    monkeypatch.delattr(mod, "READINGS", raising=False)
    assert topics.changes(slug) == {"available": False} and topics.save_daily(slug) == "none"
    monkeypatch.setattr(mod, "READINGS", lambda: rows(2.0, 1), raising=False)
    assert topics.save_daily(slug) == "saved"

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            r = await c.get(f"/api/{slug}/changes")
            return r.status, await r.json()
    status, j = asyncio.run(go())
    assert status == 200 and j["available"] and j["first"] and j["since"] is None


def test_index_groups_dashboards_by_category():
    idx = topics.index()
    names = [c["name"] for c in idx["categories"]]
    assert names[:4] == ["Signals", "Money & markets", "AI & technology", "People & planet"]
    assert sorted(d["slug"] for d in idx["dashboards"]) == sorted(topics.public())      # every dashboard exactly once
    assert topics.category("housing") == "Money & markets" and topics.category("zz-unknown") == "More"
    assert topics.meta("ai")["category"] == "AI & technology"
