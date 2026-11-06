"""The Graphify Map dashboard (app/topics/graphify_map.py): served from the committed export in data/graphify/."""
import json

from app import topics
from app.topics import graphify_map as M


def smoke_patch():
    """Used by scripts/smoke.py. Nothing to patch: the dashboard reads committed files only."""


def test_topic_is_registered():
    t = topics.REGISTRY["graphify"]
    assert t.module == "graphify_map" and t.tabs[0][0] == "map" and topics.category("graphify") == "About this site"
    assert set(t.slow) <= set(M.ENDPOINTS)


def test_map_export_shape():
    m = M.map_data()
    assert m["stats"]["nodes"] > 1000 and m["stats"]["edges"] > m["stats"]["nodes"] and m["stats"]["communities"] > 20
    assert m["communities"][0]["size"] >= m["communities"][-1]["size"] and m["gods"][0]["deg"] >= m["gods"][1]["deg"]
    ids = {n["id"] for n in m["nodes"]}
    assert all(a in ids and b in ids for a, b, _, _ in m["edges"][:500])
    assert all(s["fa"] != s["fb"] and s["conf"] != "EXTRACTED" for s in m["surprises"])
    json.dumps(m)


def test_savings_export_and_readings():
    s = M.savings()
    assert len(s["tasks"]) >= 5 and all(t["graph_tokens"] < t["naive_tokens"] for t in s["tasks"])
    assert s["graphify_benchmark"]["reduction_x"] > 10
    r = {x["key"]: x for x in M.READINGS()}
    assert r["avg_saving"]["value"] > 80 and r["avg_saving"]["lean"] == 1 and r["nodes"]["lean"] == 0


def test_missing_export_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "DIR", tmp_path)
    try:
        M.map_data()
    except FileNotFoundError as e:
        assert "graphify_export" in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_daily_usage_from_transcript_and_totals(monkeypatch, tmp_path):
    """scripts/graphify_usage.py: a transcript gives measured tokens and lookups per day (a response split over lines counted once);
    running totals give the change since the previous snapshot; the usage tab adds them up and estimates the other sessions' savings."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("gu", Path(__file__).resolve().parents[1] / "scripts" / "graphify_usage.py")
    gu = importlib.util.module_from_spec(spec); spec.loader.exec_module(gu)
    monkeypatch.setattr(gu, "OUT", tmp_path / "usage.json")
    u = {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 5}
    lines = [{"type": "assistant", "timestamp": "2026-11-01T10:00:00Z", "message": {"id": "m1", "usage": u, "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "graphify query \"x\"; graphify path \"a\" \"b\""}}]}},
             {"type": "assistant", "timestamp": "2026-11-01T10:00:01Z", "message": {"id": "m1", "usage": u, "content": [{"type": "text", "text": "hi"}]}},
             {"type": "assistant", "timestamp": "2026-11-02T09:00:00Z", "message": {"id": "m2", "usage": u, "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "grep -r graphify ."}}]}},
             {"type": "user", "timestamp": "2026-11-02T09:00:00Z", "message": {}}]
    tr = tmp_path / "t.jsonl"; tr.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    d = gu.load(); assert gu.from_transcript(d, tr, "dev-agent") == 2
    day1 = next(r for r in d["days"] if r["date"] == "2026-11-01")
    assert day1["cache_read"] == 1000 and day1["lookups"] == 2                     # m1 once; query and path both count
    assert next(r for r in d["days"] if r["date"] == "2026-11-02")["lookups"] == 0  # "grep graphify" is not a lookup
    gu.from_transcript(d, tr, "dev-agent"); assert len(d["days"]) == 2              # idempotent
    snap = tmp_path / "s.json"
    snap.write_text(json.dumps({"sessions": {"housing": {"as_of": "2026-11-01T12:00:00Z", "input": 1, "cache_write": 10, "cache_read": 100, "output": 1, "cost_usd": 1.0}, "space": None}}))
    assert gu.from_totals(d, snap) == 0                                            # the first snapshot is only a starting point
    snap.write_text(json.dumps({"sessions": {"housing": {"as_of": "2026-11-02T12:00:00Z", "input": 3, "cache_write": 30, "cache_read": 600, "output": 5, "cost_usd": 3.5}}}))
    assert gu.from_totals(d, snap) == 1
    h = next(r for r in d["days"] if r["session"] == "housing")
    assert h["date"] == "2026-11-02" and h["cache_read"] == 500 and h["cost_usd"] == 2.5 and "lookups" not in h
    gu.save(d)
    monkeypatch.setattr(M, "DIR", tmp_path); monkeypatch.setattr(M, "INSTALLED", "2026-11-01")
    out = M.usage()
    per = out["saving_per_lookup"]
    assert per > 0 and [x["date"] for x in out["days"]] == ["2026-11-01", "2026-11-02"]
    d1, d2 = out["days"]
    assert d1["lookups"] == 2 and d1["saved"] == 2 * per and d1["total"] == 1115
    assert d2["sessions"] == 2 and d2["lookups"] == 0 and d2["saved_est"] > 0          # housing's lookups estimated at the dev agent's rate
    assert {s["session"] for s in out["sessions"]} == {"dev-agent", "housing"}
    assert "tokens_last_day" in {r["key"] for r in M.READINGS()}
