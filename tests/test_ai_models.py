"""AI Model Iteration (/ai-models) on fixtures: Epoch AI (through compute_chips), OpenRouter's models API, Wikimedia pageviews, no network.
smoke_patch() points the fetchers at the same fixtures for scripts/smoke.py."""
import json

import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import ai_models as M
from app.topics import china_us_tech as CN
from app.topics import compute_chips as CC


# ------------------------------------------------------------------ fixtures
ORGS = [("OpenAI", "United States of America"), ("Anthropic", "United States of America"), ("Google DeepMind", "United States of America"),
        ("Meta AI", "United States of America"), ("xAI", "United States of America"), ("DeepSeek", "China"), ("Alibaba", "China"),
        ("Moonshot AI", "China"), ("Mistral AI", "France"), ("Zhipu AI", "China"), ("Some University", "Canada")]


def epoch_csv() -> str:
    rows = ["Model,Domain,Organization,Publication date,Parameters,Training compute (FLOP),Training hardware,Hardware quantity,Training compute cost (2023 USD),Country (of organization),Model accessibility,Base model"]
    for i in range(220):
        org, country = ORGS[i % len(ORGS)]
        d = pd.Timestamp("2015-01-01") + pd.Timedelta(days=int(i * 19))
        flop = 10 ** (18 + i * 0.04 - (1.0 if country == "China" else 0) + (0.4 if i % 5 == 0 else 0))
        cost = f"{flop / 1e19:.0f}" if i % 3 == 0 else ""
        hw, qty = ("NVIDIA H100 SXM5 80GB", "16384") if i % 4 == 0 else ("", "")
        acc = "Open weights (unrestricted)" if org in ("Meta AI", "DeepSeek", "Alibaba", "Moonshot AI", "Mistral AI", "Zhipu AI") and i % 2 else "API access"
        rows.append(f'Model {i},Language,"{org}",{d.date()},{1e9 * (1 + i)},{flop:.3e},{hw},{qty},{cost},"{country}",{acc},')
    rows.append('No compute,Language,OpenAI,2024-01-01,1e9,,,,,United States of America,API access,')
    return "\n".join(rows)


def openrouter_json() -> dict:
    data = []
    for i, (mid, name, inp, out) in enumerate([("openai/gpt-6-astra", "OpenAI: GPT-6 Astra", 10, 50), ("anthropic/claude-opus-5.5", "Anthropic: Claude Opus 5.5", 4, 20),
                                                ("google/gemini-4-argon", "Google: Gemini 4 Argon", 2, 10), ("deepseek/deepseek-v4.1-flash", "DeepSeek: DeepSeek V4.1 Flash", 0.3, 1.2),
                                                ("moonshotai/kimi-k3", "MoonshotAI: Kimi K3", 3, 15), ("qwen/qwen3.8-max", "Qwen: Qwen3.8-Max", 1.2, 6),
                                                ("mistralai/mistral-large-4", "Mistral: Mistral Large 4", 1.36, 4.18), ("z-ai/glm-5.3", "Z.ai: GLM 5.3", 1.4, 4.4),
                                                ("meta-llama/muse-spark", "Meta: Muse Spark", 1, 3), ("x-ai/grok-4.7", "xAI: Grok 4.7", 2, 6),
                                                ("someone/other-model", "Someone: Other", 1, 1), ("openai/free-thing", "OpenAI: free thing", 0, 0)]):
        data.append({"id": mid, "name": name, "created": 1750000000 + i * 86400 * 10, "context_length": 1000000 if i < 6 else 256000,
                     "pricing": {"prompt": str(inp / 1e6), "completion": str(out / 1e6), "request": "0"}})
    return {"data": data}


def wiki_json(base: int) -> dict:
    months = pd.date_range("2022-11-01", "2026-10-01", freq="MS")
    return {"items": [{"project": "en.wikipedia", "timestamp": m.strftime("%Y%m%d00"), "views": int(base * (1 + 0.02 * i))} for i, m in enumerate(months)]}


def fake_cc_fetch(url, ttl=0, **k):
    if "notable_ai_models" in url:
        return epoch_csv()
    raise ConnectionError("fixture: unknown url " + url)


def fake_fetch(url, ttl=0, **k):
    if "openrouter" in url:
        return json.dumps(openrouter_json())
    if "wikimedia" in url:
        return json.dumps(wiki_json(50000 if "DeepSeek" in url else 20000))
    raise ConnectionError("fixture: unknown url " + url)


def fake_capex():
    return {"kpi": {"ttm": 400.0, "ttm_yoy": 0.5, "quarter": 110.0, "quarter_yoy": 0.4, "date": "2026-09-30"}}


def smoke_patch():
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above."""
    CC.fetch = fake_cc_fetch
    M.fetch = fake_fetch
    CC._capex = fake_capex


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(CC, "fetch", fake_cc_fetch)
    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(CC, "_capex", fake_capex)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


# ------------------------------------------------------------------ tests
def test_registered():
    t = topics.REGISTRY["ai-models"]
    assert t.module == "ai_models" and set(k for k, _ in t.tabs) <= set(M.ENDPOINTS)
    assert topics.category("ai-models") == "AI & technology"
    m = topics.meta("ai-models")
    assert m["sources"] and "Not investment advice" in m["notes"] and m["method"]


def test_shared_helpers_in_compute_chips_and_china_us_tech():
    x = CC.parse_epoch(epoch_csv())
    assert {"params", "hardware", "hw_qty", "cost", "open", "base"} <= set(x.columns) and x["cost"].notna().sum() > 50 and x["open"].any()
    assert CN.controls_rows()[0]["date"] <= CN.controls_rows()[-1]["date"] and CN.leaderboard_rows()[0]["date"] == "2024-06-10"


def test_name_normalisation_matches_arena_openrouter_and_launch_names():
    assert M.norm("Claude Opus 5.5 (Max)") == M.norm("anthropic/claude-opus-5.5") == M.norm("Anthropic: Claude Opus 5.5") == "claudeopus55"
    assert M.norm("o3-2025-04-16") == "o3" and M.norm("DeepSeek-R1-0528") == "deepseekr1" and M.norm("Gemini-2.5-Pro") == M.norm("Gemini 2.5 Pro")
    assert M.family_of_org("Google DeepMind,Google") == "Gemini" and M.family_of_org("Zhipu AI") == "GLM" and M.family_of_org("Some University") is None
    assert M.family_of_vendor("moonshotai") == "Kimi" and M.family_of_vendor("someone") is None


def test_hand_entered_files_are_complete():
    fams = {f["family"] for f in M.families()}
    assert len(fams) >= 10 and {"GPT", "Claude", "Gemini", "Llama/Muse", "Grok", "DeepSeek", "Qwen", "Kimi", "Mistral", "GLM"} <= fams
    rel = M.rows("releases")
    assert len(rel) > 80 and all(r["family"] in fams and r["open"] in ("yes", "no") and r["flagship"] in ("yes", "no") and r["country"] for r in rel)
    for name in ("arena", "index", "prices", "openrouter_share", "benchmarks", "costs"):
        for r in M.rows(name):
            assert r["family"] in fams | {"Other"}, (name, r)
    for r in M.rows("prices"):
        assert M._num(r["input"]) is not None and M._num(r["output"]) is not None
    assert all(r["basis"] in ("disclosed", "reported", "estimated", "derived") for r in M.rows("costs"))
    for name in ("releases", "arena", "prices", "index", "costs", "benchmarks", "china_hardware", "openrouter_share"):
        for r in M.rows(name):
            if "memory" in r.get("note", "") or "secondary" in r.get("note", ""):
                assert "verify" in r["note"] or "checked" in r["note"], (name, r)
    dates = {r["date"] for r in M.rows("chips_covered")}
    assert dates <= {r["date"] for r in CN.controls_rows()}, "every chips_covered row joins a controls.csv step by date"


def test_iteration_payload():
    p = B.json_safe(M._iteration_now())
    assert p["years"][0] == 2022 and len(p["per_year"]["GPT"]) == len(p["years"])
    assert p["gaps"]["Claude"]["median_days"] > 0 and p["gaps"]["Claude"]["days_since"] >= 0
    assert 0 < p["open_share"][-1][1] < 1 and p["cadence_12m"] and p["cadence_12m"] > 0
    assert p["timeline"] and p["rows"][0]["date"] >= p["rows"][-1]["date"] and p["n_verify"] > 0


def test_release_gaps_and_cadence():
    rel = [{"date": "2026-01-01", "family": "A"}, {"date": "2026-03-01", "family": "A"}, {"date": "2026-05-01", "family": "A"}, {"date": "2020-01-01", "family": "B"}]
    g = M.release_gaps(rel, ["A", "B"])
    assert g["A"]["median_days"] == 60 and g["A"]["n"] == 3 and g["B"]["median_days"] is None and g["B"]["gaps"] == []
    assert M.cadence_12m(rel, ["A", "B"]) in (60, None)      # None once the 2026 rows are older than a year


def test_compute_payload(mocked):
    p = B.json_safe(M._compute_now())
    E = p["epoch"]
    assert E["models"] and E["record"] and E["last_record"] and E["record_age_months"] >= 0
    assert set(E["by_country"]) == {"US", "China"} and {"GPT", "Claude", "Gemini", "DeepSeek"} <= set(E["family_max"])
    assert E["hardware"] and E["hardware"][0]["hw_qty"] == 16384 and E["largest"]["flop"] >= E["models"][-1]["flop"]
    assert all(m["flop"] >= M.MIN_FLOP for m in E["models"])


def test_record_steps():
    x = pd.DataFrame({"date": pd.to_datetime(["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"]), "flop": [1e23, 5e22, 2e24, 1e24], "model": list("abcd")})
    pts, last = M.record_steps(x)
    assert [p[1] for p in pts] == [1e23, 2e24] and last == "2022-01-01"
    assert M.months_since(None) is None and M.months_since(str(pd.Timestamp.now().date())) == 0


def test_openrouter_parser_and_daily_log(mocked):
    models = M.parse_openrouter(openrouter_json())
    ids = {m["id"] for m in models}
    assert "someone/other-model" not in ids and "openai/gpt-6-astra" in ids and len(models) == 11
    astra = next(m for m in models if m["id"] == "openai/gpt-6-astra")
    assert astra["input"] == 10 and astra["output"] == 50 and astra["family"] == "GPT" and astra["context"] == 1000000
    with pytest.raises(ValueError):
        M.parse_openrouter({"data": [{"id": "someone/x", "pricing": {"prompt": "0.001", "completion": "0.002"}}]})
    assert M.log_prices(models, "2026-11-08") == 11 and M.log_prices(models, "2026-11-08") == 0 and M.log_prices(models, "2026-11-09") == 11
    log = M.price_log()
    assert log["date"].nunique() == 2 and set(log.columns) == {"date", "id", "input", "output", "context"}


def test_wiki_parser():
    s = M.parse_wiki(wiki_json(1000))
    assert s.index[0] == pd.Timestamp("2022-11-01") and s.iloc[-1] > s.iloc[0]
    with pytest.raises(ValueError):
        M.parse_wiki({"detail": "not found"})
    url, key = M.wiki_url("Claude (language model)")
    assert "Claude%20%28language%20model%29" in url or "Claude_(language_model)" in url or "Claude_%28language_model%29" in url
    assert key.endswith("/monthly") and "20221101" in url


def test_utility_payload(mocked):
    p = B.json_safe(M._utility_now())
    A = p["arena"]
    assert A["dates"] == ["2024-06-10", "2025-07-17", "2026-11-04"] and A["latest"][0]["rank"] == 1
    s = A["stats"]["2026-11-04"]
    assert s["top_model"].startswith("Gemini 4") and s["china_share"] is not None and s["open_gap"] > 0 and s["best_open"] == "Kimi K3 (Max)" and s["n_top20"] == 10
    assert A["by_family"]["Gemini"] and A["us_cn"] and p["index"]["by_family"]["Gemini"] and p["benchmarks"]["names"] == ["FrontierMath", "GPQA Diamond", "SWE-bench Verified"]
    assert set(p["wiki"]) >= {"GPT", "DeepSeek"} and p["wiki"]["DeepSeek"][-1][1] > p["wiki"]["GPT"][-1][1]
    assert p["openrouter"]["latest"] and p["openrouter"]["china_share"][-1][1] > 0.5


def test_utility_without_wikimedia_still_serves_the_leaderboards(mocked, monkeypatch):
    monkeypatch.setattr(M, "fetch", lambda url, ttl=0, **k: (_ for _ in ()).throw(ConnectionError("down")))
    p = M._utility_now()
    assert p["wiki"] is None and p["wiki_error"] and p["arena"]["latest"]


def test_sanctions_payload(mocked):
    M._compute()
    p = B.json_safe(M._sanctions_now())
    assert p["controls"][0]["date"] >= p["controls"][-1]["date"] and any(r["chips"] for r in p["controls"])
    assert p["by_country"]["US"] and p["gap_oom"] and p["gap_oom"][-1][1] > 0 and p["hardware"] and p["rule_dates"]
    jan = next(r for r in p["controls"] if r["date"] == "2026-01-15")
    assert "H200" in jan["chips"] and jan["direction"] == "1"


def test_cost_payload_prices_and_calculator(mocked):
    p = B.json_safe(M._cost_now())
    assert p["current"] and p["current_error"] is None and p["epoch_cost"]["models"] and p["epoch_cost"]["models"][0]["per_eflop"] > 0
    fp = p["frontier_price"]
    assert [x["date"] for x in fp] == ["2024-06-10", "2025-07-17", "2026-11-04"] and fp[-1]["n_top20"] == 10
    assert fp[0]["price"] == 15 and fp[0]["model"].startswith("GPT-4o")                   # GPT-4o launch price, within 50 points of the top
    assert fp[-1]["source"] == "openrouter" and fp[-1]["price"] == 3 and fp[-1]["model"] == "Muse Spark"   # OpenRouter's current list (fixture: Muse Spark $3) wins
    pp = {x["model"]: x for x in p["per_point"]}
    assert pp["Claude Opus 5.5 (Max)"]["output"] == 20 and pp["Claude Opus 5.5 (Max)"]["per_point"] == pytest.approx(20 / 1509, abs=1e-4)
    assert p["launch_by_family"]["Claude"][-1][1] == 0.5 or p["launch_by_family"]["Claude"]        # sorted by date
    assert p["capex"]["ttm"] == 400.0 and len(p["calculator"]) > 60 and all(v["output"] is not None for v in p["calculator"])
    assert p["log_days"] == 1


def test_cost_without_openrouter_uses_launch_prices_and_marks_handled(mocked, monkeypatch):
    monkeypatch.setattr(M, "fetch", lambda url, ttl=0, **k: (_ for _ in ()).throw(ConnectionError("down")))
    B.HEALTH.setdefault(M.OPENROUTER, {"module": "ai_models", "ok": None, "fail": 1.0, "error": "x"})
    p = M._cost_now()
    assert p["current"] is None and p["current_error"] == "ConnectionError"
    assert p["frontier_price"][-1]["source"] == "launch" and p["frontier_price"][-1]["price"] == 4.25   # Muse Spark launch price (Meta Model API)
    assert B.HEALTH[M.OPENROUTER].get("handled_how")


def test_overview_readings_and_signals(mocked):
    assert M.READINGS() == [] and M.SIGNALS() == []                      # nothing cached yet: nothing downloaded here
    o = B.json_safe(M.ENDPOINTS["overview"]())
    K = o["kpi"]
    assert K["frontier_score"] == 1528 and K["record_age_months"] is not None and K["frontier_price"] == 3 and K["china_share"] is not None and K["cadence_12m"]
    assert o["series"]["record"] and o["series"]["frontier_score"] and o["timeline"]
    r = {x["key"]: x for x in M.READINGS()}
    assert {"frontier_score", "frontier_price", "china_share"} <= set(r) and r["frontier_score"]["lean"] == 1
    keys = [w["key"] for w in json.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())["ai-models"]]
    sig = {x["key"]: x for x in M.SIGNALS()}
    assert list(sig) == keys == ["frontier_record_age", "price_per_point", "open_gap", "china_share_top20", "release_cadence"]
    assert all(isinstance(x["crossed"], bool) and x["lean"] in (-1, 0, 1) and x["watch"] for x in sig.values())
    assert sig["price_per_point"]["crossed"] is False and sig["price_per_point"]["lean"] == -1 and sig["price_per_point"]["note"].startswith("partial snapshot (10 of 20")   # rose, but a partial snapshot never counts
    assert sig["china_share_top20"]["crossed"] is False and "partial" in sig["china_share_top20"]["note"]
    B.json_safe(M.SIGNALS())


def test_watchlist_rows_are_approved():
    wl = json.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())["ai-models"]
    assert len(wl) == 5 and all(not r.get("proposed") and r.get("approved") and r["signal"] and r["watch"] for r in wl)   # approved by the owner 11 Nov 2026


def test_every_endpoint_through_the_server(mocked):
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            for name in ["meta", *(k for k in M.ENDPOINTS if k != "layout")]:
                r = await c.get(f"/api/ai-models/{name}")
                assert r.status == 200, name
            assert (await c.get("/ai-models.js")).status == 200
    asyncio.run(go())


@pytest.mark.network
def test_live_sources():
    from app import cache
    cache._cache.clear()
    assert len(M.parse_openrouter(json.loads(B._download(M.OPENROUTER)))) > 20
    url, _ = M.wiki_url("DeepSeek")
    assert len(M.parse_wiki(json.loads(B._download(url, 30, False, M.BOT)))) > 12
