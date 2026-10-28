import pytest
from db.migrations import runner


async def test_backup_cannot_create_a_missing_source_database(tmp_path):
    source = tmp_path / "missing.db"
    with pytest.raises(RuntimeError, match="backup failed"):
        await runner._backup_sqlite_online(str(source), "missing")
    assert not source.exists()
    assert not list(tmp_path.glob(source.name + "*.bak"))


async def test_backup_rejects_non_exact_integrity_ok(tmp_path, monkeypatch):
    import sqlite3
    source = tmp_path / "source.db"
    conn = sqlite3.connect(source)
    conn.close()
    monkeypatch.setattr(runner, "_sqlite_integrity_verdict", lambda path: "ok but corrupt")
    with pytest.raises(RuntimeError, match="integrity_check failed"):
        await runner._backup_sqlite_online(str(source), "bad-verdict")
    assert len(list(tmp_path.glob(source.name + "*.pending"))) == 1
    assert not list(tmp_path.glob(source.name + "*.bak"))
