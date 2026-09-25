import pytest
from app.executor_provenance import executor_tree_sha256


def test_workflow_changes_invalidate_executor_hash_without_mutating_old_contract():
    baseline = executor_tree_sha256("a" * 64, "b" * 40)
    assert baseline != executor_tree_sha256("a" * 64, "c" * 40)
    assert baseline != executor_tree_sha256("d" * 64, "b" * 40)
    assert baseline == executor_tree_sha256("a" * 64, "b" * 40)


@pytest.mark.parametrize("canonical,workflow", [("main", "a" * 40), ("a" * 64, "main"),
                                                ("A" * 64, "a" * 40), ("a" * 64, "")])
def test_invalid_object_pins_block(canonical, workflow):
    with pytest.raises(ValueError, match="EXECUTOR_TREE_OBJECT_INVALID"):
        executor_tree_sha256(canonical, workflow)
