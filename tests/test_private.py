"""Private dashboards (app/auth.py): off the index, data/script/Ask behind the PRIVATE_PASSCODE cookie, wrong guesses limited."""
import asyncio
import io
import sys
import types
import zipfile

import pytest

from app import auth as A, topics

PRIV = topics.Topic("zz-private", "Private test", "x", "zz_private", (("today", "Today"),), private=True)


@pytest.fixture
def priv(monkeypatch, tmp_path):
    mod = types.ModuleType("app.topics.zz_private")
    mod.TOPIC = PRIV
    mod.ENDPOINTS = {"today": lambda: {"secret_pick": "Lakers +4.5"}}
    mod.SOURCES = [{"name": "The Odds API", "url": "https://api.the-odds-api.com/v4/?apiKey=SECRET"}]
    monkeypatch.setitem(sys.modules, "app.topics.zz_private", mod)
    monkeypatch.setitem(topics.REGISTRY, "zz-private", PRIV)
    monkeypatch.setenv("PRIVATE_PASSCODE", "open sesame")
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    A._fails.clear()
    (tmp_path / "static").mkdir()
    return mod


def test_tokens_and_rate_limit(priv, monkeypatch):
    t = A.token(now=1_800_000_000)
    assert A.valid(t, now=1_800_000_001) and not A.valid(t, now=1_800_000_000 + 31 * 86400)        # expires after 30 days
    assert not A.valid("123.abc") and not A.valid(None) and not A.valid("garbage")
    monkeypatch.setenv("PRIVATE_PASSCODE", "a new passcode")
    assert not A.valid(t, now=1_800_000_001)                                                         # changing it signs everyone out
    monkeypatch.setenv("PRIVATE_PASSCODE", "open sesame")
    for _ in range(A.TRIES):
        assert A.unlock("wrong", "1.1.1.1", now=1_800_000_000) is None
    with pytest.raises(A.TooMany):
        A.unlock("open sesame", "1.1.1.1", now=1_800_000_100)
    assert A.unlock("open sesame", "2.2.2.2", now=1_800_000_100)                                   # someone else is not blocked
    assert A.unlock("open sesame", "1.1.1.1", now=1_800_000_000 + A.WINDOW + 1)                      # the window passes
    assert A.allowed("housing", None) and not A.allowed("zz-private", None)


def test_hidden_from_index_health_and_public_archive(priv, monkeypatch):
    assert "zz-private" not in [d["slug"] for d in topics.index()["dashboards"]]
    from app import archive
    monkeypatch.setattr(topics, "endpoints", lambda slug: priv.ENDPOINTS if slug == "zz-private" else {})
    names = zipfile.ZipFile(io.BytesIO(archive.build())).namelist()
    assert not any("zz-private" in n for n in names)
    assert any("zz-private/today.json" in n for n in zipfile.ZipFile(io.BytesIO(archive.build(include_private=True))).namelist())


def test_routes(priv, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            out = {}
            out["meta"] = (await c.get("/api/zz-private/meta")).status
            r = await c.get("/api/zz-private/today")
            out["data"], out["data_body"] = r.status, await r.text()
            out["ask"] = (await c.post("/api/ask", json={"slug": "zz-private", "tab": "today", "question": "best bet?"})).status
            out["page"] = (await c.get("/zz-private")).status                        # the shell loads; it asks for the passcode
            out["index"] = await (await c.get("/api/index")).text()
            out["health"] = await (await c.get("/api/health")).text()
            out["wrong"] = (await c.post("/api/unlock", json={"passcode": "nope"})).status
            r = await c.post("/api/unlock", json={"passcode": "open sesame"})
            out["unlock"], out["cookie"] = r.status, r.cookies.get("dash_auth")
            out["data_after"] = await (await c.get("/api/zz-private/today")).json()
            out["meta_after"] = await (await c.get("/api/zz-private/meta")).json()
            await c.post("/api/lock")
            out["after_lock"] = (await c.get("/api/zz-private/today")).status
            out["public"] = (await c.get("/api/housing/meta")).status
            return out
    o = asyncio.run(go())
    assert o["meta"] == o["data"] == 401 and "Lakers" not in o["data_body"] and o["ask"] == 401
    assert o["page"] == 200 and "zz-private" not in o["index"] and "SECRET" not in o["health"]
    assert o["wrong"] == 401 and o["unlock"] == 200 and o["cookie"]["httponly"] and o["cookie"]["samesite"] == "Strict"
    assert o["data_after"] == {"secret_pick": "Lakers +4.5"} and o["meta_after"]["private"] is True
    assert o["after_lock"] == 401 and o["public"] == 200


def test_not_set_up(priv, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    monkeypatch.delenv("PRIVATE_PASSCODE")

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            r = await c.get("/api/zz-private/meta")
            u = await c.post("/api/unlock", json={"passcode": ""})
            return r.status, await r.json(), u.status
    s, j, u = asyncio.run(go())
    assert s == 401 and j["set_up"] is False and u == 503


def test_post_actions_only_on_private_dashboards_behind_the_passcode(priv):
    """POST /api/<slug>/<name> routes to module.ACTIONS for a private dashboard once unlocked; everything else is refused."""
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    saved = []

    def save(body):
        if body.get("stake", 0) < 0:
            raise ValueError("a bet needs a stake")
        saved.append(body)
        return {"ok": True, "n": len(saved)}
    priv.ACTIONS = {"bets": save}
    priv.FOOTER = "18+. BeGambleAware.org."

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            out = {"locked": (await c.post("/api/zz-private/bets", json={"stake": 1})).status}
            await c.post("/api/unlock", json={"passcode": "open sesame"})
            ok = await c.post("/api/zz-private/bets", json={"stake": 5, "name": "Lakers"})
            out["ok"] = (ok.status, await ok.json())
            out["bad"] = (await c.post("/api/zz-private/bets", json={"stake": -1})).status
            out["not_object"] = (await c.post("/api/zz-private/bets", json=[1, 2])).status
            out["form"] = (await c.post("/api/zz-private/bets", data="stake=5", headers={"Content-Type": "application/x-www-form-urlencoded"})).status
            out["big"] = (await c.post("/api/zz-private/bets", json={"note": "x" * 20000})).status
            out["unknown"] = (await c.post("/api/zz-private/nope", json={})).status
            out["public"] = (await c.post("/api/housing/prices", json={})).status
            out["footer"] = (await (await c.get("/api/zz-private/meta")).json())["footer"]
            out["house_footer"] = (await (await c.get("/api/housing/meta")).json())["footer"]
            return out
    r = asyncio.run(go())
    assert r["locked"] == 401 and r["ok"] == (200, {"ok": True, "n": 1}) and saved == [{"stake": 5, "name": "Lakers"}]
    assert r["bad"] == 400 and r["not_object"] == 400 and r["form"] == 415 and r["big"] == 413
    assert r["unknown"] == 404 and r["public"] == 404 and len(saved) == 1
    assert r["footer"] == "18+. BeGambleAware.org." and r["house_footer"] == ""
