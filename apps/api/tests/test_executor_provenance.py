from types import SimpleNamespace

import pytest
from app import executor_provenance
from app.executor_provenance import collect_executor_tree, executor_tree_sha256


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


def test_collector_trusts_only_the_bound_root_owned_source(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout="a" * 40 + "\n")

    monkeypatch.setattr(executor_provenance.subprocess, "run", fake_run)
    collect_executor_tree(tmp_path, "b" * 40)
    assert calls
    assert all(
        command[:5] == [
            "git", "-c", f"safe.directory={tmp_path}", "-C", str(tmp_path),
        ]
        for command in calls
    )
