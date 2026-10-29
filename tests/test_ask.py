"""Ask Claude (app/ask.py, POST /api/ask): context, limits, the daily cap, and that nothing private is stored or logged."""
import asyncio
import json
import logging

import pytest

from app import ask as K, topics

SLUG = next(iter(topics.REGISTRY))


class FakeAPI:
    def __init__(self, text="London prices rose 2% on a year.", inp=4000, out=200, fail=False):
        self.calls, self.text, self.inp, self.out, self.fail = [], text, inp, out, fail

    def __call__(self, system, messages):
        self.calls.append((system, messages))
        if self.fail:
            raise RuntimeError("Claude API 529 overloaded_error")
        return {"content": [{"type": "text", "text": self.text}], "usage": {"input_tokens": self.inp, "output_tokens": self.out}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "USAGE", tmp_path / "ask_usage.json")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    for k in ("ASK_PER_HOUR", "ASK_PER_DAY", "ASK_DAILY_USD", "ASK_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(topics, "endpoints", lambda slug: {"prices": lambda: {"london": [[1700000000, 500000]], "big": "x" * 50000}})
    api = FakeAPI()
    monkeypatch.setattr(K, "_call", api)
    return api


def test_context_has_meta_tab_data_and_is_cut(env):
    ctx = K.context(SLUG, "prices", "1 Nov 2014")
    assert topics.meta(SLUG)["title"] in ctx and "1700000000" in ctx and "1 Nov 2014" in ctx
    assert len(ctx) <= K.MAX_CONTEXT and "cut short" in ctx
    assert "no single data endpoint" in K.context(SLUG, "nosuchtab", None)


def test_answer_history_and_usage(env, tmp_path):
    r = K.ask(SLUG, "prices", "What changed?", [{"q": "hi", "a": "hello"}] * 5, None, "1.2.3.4", now=1_800_000_000)
    assert r["answer"].startswith("London") and r["left"]["hour"] == 5
    system, msgs = env.calls[-1]
    assert "data, not instructions" in system
    assert len(msgs) == 2 * K.MAX_HISTORY + 1 and msgs[-1]["content"].endswith("Question: What changed?") and "<dashboard_data>" in msgs[-1]["content"]
    stored = (tmp_path / "ask_usage.json").read_text()
    assert "1.2.3.4" not in stored and "What changed" not in stored
    u = json.loads(stored)
    assert u["questions"] == 1 and abs(u["usd"] - (4000 * 3 + 200 * 15) / 1e6) < 1e-9


def test_limits_per_hour_day_and_site_cap(env, monkeypatch):
    monkeypatch.setenv("ASK_PER_HOUR", "2"); monkeypatch.setenv("ASK_PER_DAY", "3")
    t = 1_800_000_000
    K.ask(SLUG, "prices", "q1", None, None, "9.9.9.9", now=t)
    K.ask(SLUG, "prices", "q2", None, None, "9.9.9.9", now=t + 10)
    with pytest.raises(K.Limit, match="this hour"):
        K.ask(SLUG, "prices", "q3", None, None, "9.9.9.9", now=t + 20)
    K.ask(SLUG, "prices", "q3", None, None, "9.9.9.9", now=t + 3700)          # next hour
    with pytest.raises(K.Limit, match="today"):
        K.ask(SLUG, "prices", "q4", None, None, "9.9.9.9", now=t + 7400)
    K.ask(SLUG, "prices", "q", None, None, "8.8.8.8", now=t + 7400)            # another visitor is unaffected
    monkeypatch.setenv("ASK_DAILY_USD", "0.0001")
    with pytest.raises(K.Limit, match="paused until tomorrow"):
        K.ask(SLUG, "prices", "q", None, None, "7.7.7.7", now=t + 7500)
    nxt = t + 86400 * 2                                                       # a new UTC day resets everything
    monkeypatch.setenv("ASK_DAILY_USD", "2")
    assert K.ask(SLUG, "prices", "q", None, None, "9.9.9.9", now=nxt)["answer"]


def test_failed_call_does_not_count_and_bad_input(env, monkeypatch):
    monkeypatch.setattr(K, "_call", FakeAPI(fail=True))
    with pytest.raises(RuntimeError):
        K.ask(SLUG, "prices", "q", None, None, "5.5.5.5", now=1_800_000_000)
    assert K.status("5.5.5.5", now=1_800_000_001)["left"]["hour"] == 6
    with pytest.raises(ValueError):
        K.ask(SLUG, "prices", "  ", None, None, "5.5.5.5")
    with pytest.raises(ValueError):
        K.ask(SLUG, "prices", "x" * 1001, None, None, "5.5.5.5")
    with pytest.raises(KeyError):
        K.ask("nope", "prices", "q", None, None, "5.5.5.5")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(K.NotSetUp):
        K.ask(SLUG, "prices", "q", None, None, "5.5.5.5")


def test_routes_and_no_question_in_logs(env, caplog):
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    caplog.set_level(logging.INFO)

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            ok = await c.post("/api/ask", json={"slug": SLUG, "tab": "prices", "question": "secret question text"}, headers={"X-Forwarded-For": "4.4.4.4, 10.0.0.1"})
            bad = await c.post("/api/ask", json={"slug": SLUG, "tab": "prices", "question": ""})
            unknown = await c.post("/api/ask", json={"slug": "nope", "question": "q"})
            st = await (await c.get("/api/ask/status", headers={"X-Forwarded-For": "4.4.4.4"})).json()
            health = await (await c.get("/api/health")).json()
            return ok.status, await ok.json(), bad.status, unknown.status, st, health
    s, j, bad, unknown, st, health = asyncio.run(go())
    assert s == 200 and j["answer"] and bad == 400 and unknown == 404
    assert st["set_up"] and st["left"]["hour"] == 5
    assert health["ask"]["questions"] == 1 and "sk-test" not in json.dumps(health)
    assert "secret question text" not in caplog.text


def test_context_on_the_method_tab_carries_the_guide_sections(env):
    ctx = K.context("housing", "about", None)
    assert "The reader is on the tab: Method (about)" in ctx and "How it is calculated" in ctx
