"""OneDrive through rclone (app/cloud.py, ported from the trading bot) and the month-end archive run (app/archive.py)."""
import json
import types
from datetime import datetime, timezone

import pytest

from app import archive as A
from app import cloud as C

GOOD = ('[onedrive]\ntype = onedrive\ntoken = {"access_token":"a b","token_type":"Bearer","refresh_token":"r","expiry":"2026-10-25T16:11:18Z"}\n'
        'drive_id = 6DC1\ndrive_type = personal\n')


def at(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_normalize_repairs_the_paste():
    assert C.normalize(GOOD) == GOOD
    one_line = '"[onedrive] type = onedrive token = {"access_token":"a b","token_type":"Bearer","refresh_token":"r","expiry":"2026-10-25T16:11:18Z"} drive_id = 6DC1 drive_type = personal"'
    assert C.normalize(one_line) == GOOD
    assert C.normalize(GOOD.replace("\n", "\\n")) == GOOD
    assert C.normalize(GOOD.replace('"token_type"', '\n"token_type"')) == GOOD
    assert C.normalize("type = onedrive\ndrive_type = personal") == "[onedrive]\ntype = onedrive\ndrive_type = personal\n"


def test_conf_written_once_and_rewritten_on_a_new_paste(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CONF", tmp_path / "rclone.conf"); monkeypatch.setattr(C, "CONF_SRC", tmp_path / "rclone.conf.src")
    assert C.ensure_conf({}) is False
    env = {"ONEDRIVE_RCLONE_CONF": GOOD}
    assert C.ensure_conf(env) and oct((tmp_path / "rclone.conf").stat().st_mode)[-3:] == "600"
    (tmp_path / "rclone.conf").write_text(GOOD.replace('"r"', '"rotated"'))          # rclone refreshed the token
    C.ensure_conf(env)
    assert '"rotated"' in (tmp_path / "rclone.conf").read_text()                     # same variable: left alone
    C.ensure_conf({"ONEDRIVE_RCLONE_CONF": GOOD.replace('"r"', '"new"')})
    assert '"new"' in (tmp_path / "rclone.conf").read_text()                         # new paste: replaced
    assert C.folder({}) == "Dashboards"
    shape = C.conf_shape(env)
    assert "a b" not in json.dumps(shape) and "6DC1" not in json.dumps(shape)


def test_scrub_hides_tokens():
    s = C._scrub('error {"access_token":"EwBYabc","refresh_token":"M.C1_xyz"} 0x' + "a" * 64)
    assert "EwBYabc" not in s and "M.C1_xyz" not in s and "a" * 64 not in s


def test_due_month_end_first_copy_and_catch_up():
    assert A.due(at("2026-10-26T12:00"), {}) is True                                  # never copied: first copy now
    st = {"ok": True, "first": "2026-10-26", "months_done": []}
    assert A.due(at("2026-10-27T12:00"), st) is False
    assert A.due(at("2026-10-31T23:00"), st) is True                                  # last day of the month
    assert A.due(at("2026-10-31T23:10"), {**st, "months_done": ["2026-10"]}) is False
    assert A.due(at("2026-11-02T08:00"), st) is True                                  # server was down on the 31st: catch up
    assert A.due(at("2026-11-02T08:00"), {**st, "months_done": ["2026-10"]}) is False
    failed = {**st, "ok": False, "last_try": at("2026-10-31T23:00").timestamp()}
    assert A.due(at("2026-10-31T23:30"), failed) is False and A.due(at("2026-10-31T23:59"), {**failed, "last_try": 0}) is True


def test_run_uploads_and_records(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "STATUS", tmp_path / "status.json")
    monkeypatch.setattr(A, "build", lambda include_private=False: b"zipbytes")
    monkeypatch.setattr(C, "configured", lambda env=None: True)
    sent = []
    monkeypatch.setattr(C, "upload_bytes", lambda data, d, name: sent.append((d, name, data)) or f"{d}/{name}")
    st = A.run(at("2026-10-26T12:00"))
    assert st["ok"] and st["first"] == "2026-10-26" and sent[-1][:2] == ("Archive/2026-10", "dashboards-2026-10-26.zip")
    st = A.run(at("2026-11-01T09:00"))                                                # catch-up of October, filed under October
    assert st["months_done"] == ["2026-10"] and sent[-1][0] == "Archive/2026-10" and st["path"] == "Dashboards/Archive/2026-10/dashboards-2026-11-01.zip"
    monkeypatch.setattr(C, "upload_bytes", lambda *a: (_ for _ in ()).throw(RuntimeError('rclone failed {"access_token":"secret"}')))
    st = A.run(at("2026-11-30T23:00"))
    assert st["ok"] is False and "secret" not in st["error"] and st["months_done"] == ["2026-10"]


def test_upload_checks_the_size(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CONF", tmp_path / "rclone.conf")
    (tmp_path / "rclone.conf").write_text("[onedrive]\ntype = onedrive\n")
    monkeypatch.setattr(C, "binary", lambda: "/usr/bin/rclone")
    sizes = {"n": 8}

    def run(args, capture_output, text, timeout):
        if args[7] == "lsjson":
            return types.SimpleNamespace(returncode=0, stdout=json.dumps({"Name": "x.zip", "Size": sizes["n"]}), stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(C.subprocess, "run", run)
    assert C.upload_bytes(b"zipbytes", "Archive/2026-10", "x.zip") == "Archive/2026-10/x.zip"
    sizes["n"] = 3
    with pytest.raises(RuntimeError, match="did not verify"):
        C.upload_bytes(b"zipbytes", "Archive/2026-10", "x.zip")


def test_health_shows_archive_without_secrets(tmp_path, monkeypatch):
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    monkeypatch.setattr(A, "STATUS", tmp_path / "status.json")
    monkeypatch.setattr(C, "CONF", tmp_path / "rclone.conf"); monkeypatch.setattr(C, "CONF_SRC", tmp_path / "rclone.conf.src")
    monkeypatch.setenv("ONEDRIVE_RCLONE_CONF", GOOD)
    monkeypatch.setattr(C, "binary", lambda: None)

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            return await (await c.get("/api/health")).text()
    text = asyncio.run(go())
    assert '"archive"' in text and "6DC1" not in text and '"r"' not in text
