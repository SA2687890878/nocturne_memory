import sqlite3

from backend import system_diagnostics


def test_write_probe_is_rolled_back_without_persistent_table(monkeypatch, tmp_path):
    db = tmp_path / "memory.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    monkeypatch.setattr(system_diagnostics.config, "get", lambda key: {
        "database_url": f"sqlite+aiosqlite:///{db.as_posix()}"
    }[key])
    result = system_diagnostics.diagnose_memory_database()
    assert result["database_readable"] is True
    assert result["database_writable"] is True
    assert result["write_probe"] == "passed_and_rolled_back"
    con = sqlite3.connect(db)
    names = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    con.close()
    assert names == ["memories"]


def test_missing_database_reports_without_creating_file(monkeypatch, tmp_path):
    db = tmp_path / "missing.db"
    monkeypatch.setattr(system_diagnostics.config, "get", lambda key: {
        "database_url": f"sqlite+aiosqlite:///{db.as_posix()}"
    }[key])
    result = system_diagnostics.diagnose_memory_database()
    assert result["database_file_exists"] is False
    assert result["database_readable"] is False
    assert result["database_writable"] is False
    assert not db.exists()
