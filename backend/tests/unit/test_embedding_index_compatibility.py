import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "experiments" / "nvidia_embedding_incremental_sync.py"
SPEC = importlib.util.spec_from_file_location("nvidia_embedding_incremental_sync", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_empty_index_does_not_force_rebuild():
    assert MODULE.should_rebuild_index(None, 0, "model-a", 2048, 2) is False


def test_legacy_index_without_state_is_rebuilt():
    assert MODULE.should_rebuild_index(None, 12, "model-a", 2048, 2) is True


def test_model_change_forces_full_rebuild():
    assert MODULE.should_rebuild_index(("model-a", 2048, 2), 12, "model-b", 2048, 2) is True


def test_document_format_change_forces_full_rebuild():
    assert MODULE.should_rebuild_index(("model-a", 2048, 1), 12, "model-a", 2048, 2) is True


def test_same_index_identity_keeps_incremental_mode():
    assert MODULE.should_rebuild_index(("model-a", 2048, 2), 12, "model-a", 2048, 2) is False


def test_dimension_change_requires_fresh_index():
    import pytest
    with pytest.raises(RuntimeError, match="create a fresh isolated index"):
        MODULE.should_rebuild_index(("model-a", 1024, 2), 12, "model-a", 2048, 2)
