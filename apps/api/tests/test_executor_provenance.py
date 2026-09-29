from types import SimpleNamespace
from pathlib import Path

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
    assert all(command[:3] == ["git", "-C", str(tmp_path)] for command in calls)
    assert all("safe.directory=*" not in command and "-c" not in command for command in calls)


@pytest.mark.parametrize(
    "stdout,returncode",
    [
        ("*\n", 0),
        ("/different/path\n", 0),
        ("/protected/source\n/protected/source\n", 0),
        ("", 1),
    ],
)
def test_system_safe_directory_mismatch_fails_closed(monkeypatch, stdout, returncode):
    monkeypatch.setattr(
        executor_provenance.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=stdout, returncode=returncode),
    )
    with pytest.raises(ValueError, match="GIT_SAFE_DIRECTORY_NOT_EXACT"):
        executor_provenance.verify_system_safe_directory(Path("/protected/source"))


def test_system_safe_directory_accepts_one_exact_entry(monkeypatch):
    monkeypatch.setattr(
        executor_provenance.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="/protected/source\n", returncode=0),
    )
    executor_provenance.verify_system_safe_directory(Path("/protected/source"))
