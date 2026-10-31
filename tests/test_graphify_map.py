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
