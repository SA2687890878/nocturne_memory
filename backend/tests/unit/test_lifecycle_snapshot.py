from db.snapshot import ChangesetStore, _rows_equal


def test_node_comparison_ignores_access_only_without_discarding_snapshots(tmp_path):
    store = ChangesetStore(snapshot_dir=str(tmp_path))
    before = {"uuid": "n", "lifecycle_status": "active", "last_accessed_at": None}
    after = {**before, "lifecycle_status": "obsolete", "last_accessed_at": "latest"}
    store.record("nodes", before, after)
    assert store.get_snapshot_view()[0]["nodes:n"]["after"]["last_accessed_at"] == "latest"
    store.record("nodes", after, {**after, "lifecycle_status": "active"})
    assert store.get_change_count() == 0


def test_node_comparison_preserves_creation_deletion_and_other_fields():
    row = {"uuid": "n", "lifecycle_status": "active", "last_accessed_at": None}
    assert not _rows_equal("nodes", None, row)
    assert not _rows_equal("nodes", row, None)
    assert _rows_equal("nodes", None, None)
    assert not _rows_equal("nodes", row, {**row, "lifecycle_status": "completed"})
    assert not _rows_equal("nodes", row, {**row, "uuid": "other"})
    assert not _rows_equal("edges", row, {**row, "last_accessed_at": "different"})
