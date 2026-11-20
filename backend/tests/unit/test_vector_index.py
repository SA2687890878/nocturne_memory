import pytest

from backend.vector_index import VectorIndex, VectorIndexError


DIMS = 8


def document(uri, vector, **extra):
    return {
        "memory_id": 1,
        "uri": uri,
        "content_hash": f"hash-{uri}",
        "vector": vector,
        "namespace": "personal",
        "domain": "project",
        "path": "/nocturne",
        "lifecycle_status": "active",
        **extra,
    }


def test_index_upsert_search_health_and_delete(tmp_path):
    db = tmp_path / "vectors.db"
    with VectorIndex(db, dimensions=DIMS, model_name="test-model") as index:
        assert index.upsert_many([
            document("memory://a", [1.0] + [0.0] * 7),
            document("memory://b", [0.0, 1.0] + [0.0] * 6, namespace="shared", domain="other"),
        ]) == 2
        results = index.search([1.0] + [0.0] * 7, limit=2)
        assert [row["uri"] for row in results][0] == "memory://a"
        assert results[0]["distance"] == pytest.approx(0.0)
        filtered = index.search([1.0] + [0.0] * 7, limit=1, namespace="shared", domain="other")
        assert [row["uri"] for row in filtered] == ["memory://b"]
        health = index.health_check()
        assert health["ok"] is True
        assert health["metadata_count"] == health["vector_count"] == 2
        assert health["dimensions"] == DIMS
        assert index.delete_uris(["memory://b", "memory://missing"]) == 1
        assert index.health_check()["metadata_count"] == 1


def test_upsert_updates_existing_uri_without_duplicate(tmp_path):
    with VectorIndex(tmp_path / "vectors.db", dimensions=DIMS, model_name="test-model") as index:
        index.upsert_many([document("memory://a", [1.0] + [0.0] * 7)])
        index.upsert_many([document("memory://a", [0.0, 1.0] + [0.0] * 6, content_hash="new-hash")])
        health = index.health_check()
        assert health["metadata_count"] == health["vector_count"] == 1
        result = index.search([0.0, 1.0] + [0.0] * 6, limit=1)
        assert result[0]["content_hash"] == "new-hash"


def test_invalid_vector_does_not_write_anything(tmp_path):
    with VectorIndex(tmp_path / "vectors.db", dimensions=DIMS, model_name="test-model") as index:
        with pytest.raises(ValueError, match="expected 8 dimensions"):
            index.upsert_many([document("memory://bad", [1.0, 2.0])])
        assert index.health_check()["metadata_count"] == 0


def test_model_mismatch_requires_fresh_index(tmp_path):
    db = tmp_path / "vectors.db"
    with VectorIndex(db, dimensions=DIMS, model_name="model-a") as index:
        index.upsert_many([document("memory://a", [1.0] + [0.0] * 7)])
    with pytest.raises(VectorIndexError, match="identity mismatch"):
        VectorIndex(db, dimensions=DIMS, model_name="model-b").open()


def test_dimension_mismatch_requires_fresh_index(tmp_path):
    db = tmp_path / "vectors.db"
    with VectorIndex(db, dimensions=DIMS, model_name="model-a"):
        pass
    with pytest.raises(VectorIndexError, match="dimension mismatch"):
        VectorIndex(db, dimensions=DIMS + 1, model_name="model-a").open()


def test_index_must_be_open_before_operations(tmp_path):
    index = VectorIndex(tmp_path / "vectors.db", dimensions=DIMS, model_name="test-model")
    with pytest.raises(VectorIndexError, match="not open"):
        index.health_check()


def test_apply_changes_commits_upserts_and_deletes_atomically(tmp_path):
    with VectorIndex(tmp_path / "atomic.db", dimensions=DIMS, model_name="test-model") as index:
        index.upsert_many([document("memory://keep", [1.0] + [0.0] * 7), document("memory://drop", [0.0, 1.0] + [0.0] * 6)])
        before = index.list_documents()
        with pytest.raises(ValueError, match="expected 8 dimensions"):
            index.apply_changes([document("memory://new", [1.0, 2.0])], ["memory://drop"])
        assert index.list_documents() == before
        assert index.health_check()["metadata_count"] == 2


def test_apply_changes_rolls_back_database_failure(tmp_path, monkeypatch):
    from backend import vector_index as module
    with VectorIndex(tmp_path / "rollback.db", dimensions=DIMS, model_name="test-model") as index:
        index.upsert_many([document("memory://old", [1.0] + [0.0] * 7)])
        before = index.list_documents()
        original = module._serialize_float32
        def failing_serialize(vector):
            raise RuntimeError("injected write failure")
        monkeypatch.setattr(module, "_serialize_float32", failing_serialize)
        with pytest.raises(RuntimeError, match="injected write failure"):
            index.apply_changes([document("memory://new", [0.0, 1.0] + [0.0] * 6)], ["memory://old"])
        monkeypatch.setattr(module, "_serialize_float32", original)
        assert index.list_documents() == before
        assert index.health_check()["metadata_count"] == index.health_check()["vector_count"] == 1


def test_read_only_index_can_search_without_mutating(tmp_path):
    db = tmp_path / "readonly.db"
    vector = [1.0] + [0.0] * 7
    with VectorIndex(db, dimensions=DIMS, model_name="test-model") as writable:
        writable.upsert_many([document("memory://readonly", vector)])
    before = db.stat().st_size
    with VectorIndex(db, dimensions=DIMS, model_name="test-model", read_only=True) as readonly:
        assert readonly.health_check()["ok"]
        assert readonly.search(vector, limit=1)[0]["uri"] == "memory://readonly"
    assert db.stat().st_size == before


def test_read_only_index_does_not_create_missing_file(tmp_path):
    db = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        VectorIndex(db, dimensions=DIMS, model_name="test-model", read_only=True).open()
    assert not db.exists()


def test_vector_index_never_imports_numpy_or_sqlite_vec_package(tmp_path, monkeypatch):
    import builtins

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "sqlite_vec" or name == "numpy" or name.startswith("numpy."):
            raise AssertionError("Vector operations must not initialize optional NumPy")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with VectorIndex(tmp_path / "no_numpy.db", dimensions=DIMS, model_name="test-model") as index:
        index.upsert_many([document("memory://no_numpy", [1.0] + [0.0] * 7)])
        assert index.search([1.0] + [0.0] * 7, limit=1)[0]["uri"] == "memory://no_numpy"
