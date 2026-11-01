"""The Actions & Roadmap dashboard (app/topics/status.py): the committed items.json, its shape, and the readings."""
import json
from datetime import date

from app import topics
from app.topics import status as M


def smoke_patch():
    """Used by scripts/smoke.py. Nothing to patch: the dashboard reads a committed file."""


def test_topic_is_registered():
    t = topics.REGISTRY["status"]
    assert [k for k, _ in t.tabs] == ["actions", "pending", "roadmap", "log"] and set(t.slow) <= set(M.ENDPOINTS)
    assert topics.category("status") == "About this site"


def test_items_shape_and_ages():
    d = M.items()
    assert d["updated"] and d["actions"] and d["pending"] and d["roadmap"] and d["log"]
    for a in d["actions"]:
        assert a["priority"] in ("high", "medium", "low") and a["status"] in ("open", "done") and a["title"] and a["detail"]
        assert a["age_days"] is not None and a["age_days"] >= 0
    assert all(p["owner"] and p["status"] in ("in_progress", "waiting", "blocked", "done") for p in d["pending"])
    assert all(r["horizon"] in ("now", "next", "later", "done") and r["status"] in ("planned", "in_progress", "done") for r in d["roadmap"])
    assert all(l["result"] in ("ok", "problems", "did_not_run") and l["date"] for l in d["log"])
    ids = [x["id"] for k in ("actions", "pending", "roadmap") for x in d[k]]
    assert len(ids) == len(set(ids)), "ids must be unique"
    json.dumps(M.ENDPOINTS["actions"]())


def test_readings(monkeypatch, tmp_path):
    f = tmp_path / "items.json"
    f.write_text(json.dumps({"updated": "2026-11-01", "actions": [{"id": "a", "title": "t", "detail": "d", "priority": "high", "status": "open", "since": "2026-10-01", "area": "x"}],
                             "pending": [{"id": "p", "title": "t", "detail": "d", "owner": "parent", "status": "waiting", "since": "2026-10-01"}],
                             "roadmap": [{"id": "r", "title": "t", "horizon": "done", "status": "done"}], "log": [{"date": "2026-10-30", "run": "scheduled", "result": "ok", "summary": "s"}]}))
    monkeypatch.setattr(M, "FILE", f)
    r = {x["key"]: x for x in M.READINGS()}
    assert r["open_actions"]["value"] == 1 and r["open_actions"]["lean"] == -1 and r["last_check"]["lean"] == 1 and r["roadmap_done"]["value"] == 1
    assert M.items()["actions"][0]["age_days"] == (date.today() - date(2026, 10, 1)).days
