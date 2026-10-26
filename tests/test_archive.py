"""The month-end archive zip (app/archive.py, GET /api/archive.zip)."""
import io
import zipfile

from app import archive, topics


def test_archive_has_every_dashboard(tmp_path, monkeypatch):
    def fake(slug):
        def boom():
            raise RuntimeError("source down")
        return {"a": lambda: {"x": 1}, "b": boom}
    monkeypatch.setattr(topics, "endpoints", fake)
    monkeypatch.setattr(topics, "health", lambda: {"ok": True})
    monkeypatch.setattr(archive, "SNAP_DIR", tmp_path)
    slug = next(iter(topics.REGISTRY))
    (tmp_path / "daily" / slug).mkdir(parents=True)
    (tmp_path / "daily" / slug / "2026-10-26.json").write_text('{"date": "2026-10-26", "readings": []}')
    z = zipfile.ZipFile(io.BytesIO(archive.build()))
    names = z.namelist()
    root = names[0].split("/")[0] + "/"
    assert root.startswith("archive-") and root + "index.json" in names
    for s in topics.REGISTRY:
        assert f"{root}{s}/meta.json" in names and f"{root}{s}/a.json" in names
        assert "source down" in z.read(f"{root}{s}/b.error.txt").decode()
    assert f"{root}{slug}/daily/2026-10-26.json" in names
    assert any(n.startswith(root + "data/") for n in names)
