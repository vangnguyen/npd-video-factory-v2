"""Promotion contract fixtures are never actual host/security qualification."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import executor_execution as execution, executor_qualification as q


@pytest.fixture
def artifacts(monkeypatch):
    host = SimpleNamespace(source_commit="a" * 40, runner_name="dedicated", executor_executable_tree_sha256="f" * 64)
    receipt = {"status": "SELF_HOSTED_EXECUTION_PLANE_QUALIFIED", "source_commit": host.source_commit,
        "runner_id": 21, "runner_name": host.runner_name, "gates": {g: "PASS" for g in q.GATES},
        "kill_switch": "ENGAGED", "executor_executable_tree_sha256": host.executor_executable_tree_sha256,
        "probe_receipt": "/probe", "probe_receipt_sha256": "b" * 64,
        "probe_manifest": "/manifest", "probe_manifest_sha256": "c" * 64,
        "security_review": "/security", "security_review_sha256": "d" * 64, **q.ZERO}
    probe = {"verdict": "CAPABILITY_PROBES_PASS", "execution_plane_qualified": False,
        "runner_id": 21, "runner_name": host.runner_name, "source_commit": host.source_commit,
        "executor_executable_tree_sha256": host.executor_executable_tree_sha256,
        "gates": {g: {"status": "PASS"} for g in q.GATES}, **q.ZERO}
    probe["gates"]["E10"].update(KILL_SWITCH="ENGAGED", ledger_unchanged=True)
    security = {"status": "RUNNER_SECURITY_PASS", "source_commit": host.source_commit, "runner_id": 21,
        "executor_executable_tree_sha256": host.executor_executable_tree_sha256,
        "quarantine": "CLEARED_BY_VALIDATED_POLICY", "hostile_job_tests": {g: "PASS" for g in (
            "malicious_pr", "modified_workflow", "command_injection", "secret_exfiltration", "concurrent_job",
            "stale_rc", "altered_authority", "admission_launch_failure")}}
    files = {"/promotion": receipt, "/probe": probe, "/manifest": {"qualification.json": "b" * 64}, "/security": security}
    hashes = {"/promotion": "e" * 64, "/probe": "b" * 64, "/manifest": "c" * 64, "/security": "d" * 64}
    def trusted(path, digest=None):
        assert hashes[path.as_posix()] == digest
        return files[path.as_posix()]
    monkeypatch.setattr(execution, "_trusted_json", trusted)
    return host, files, {"qualification_receipt": "/promotion", "qualification_sha256": "e" * 64}


def test_explicit_promotion_binds_actual_report_shape(artifacts):
    host, files, catalog = artifacts
    execution.verify_qualification(catalog, host)
    assert files["/probe"]["execution_plane_qualified"] is False


@pytest.mark.parametrize("change", ["probe", "manifest", "security", "gate", "tree", "hostile", "ledger", "calls"])
def test_promotion_cannot_skip_prerequisites(artifacts, change):
    host, files, catalog = artifacts
    if change == "probe": files["/probe"]["verdict"] = "BLOCKED"
    elif change == "manifest": files["/manifest"]["qualification.json"] = "0" * 64
    elif change == "security": files["/security"]["status"] = "DESIGN_ONLY"
    elif change == "gate": files["/probe"]["gates"]["E3"]["status"] = "NOT_TESTED"
    elif change == "tree": files["/promotion"]["executor_executable_tree_sha256"] = "0" * 64
    elif change == "hostile": files["/security"]["hostile_job_tests"]["admission_launch_failure"] = "NOT_TESTED"
    elif change == "ledger": files["/probe"]["gates"]["E10"]["ledger_unchanged"] = False
    elif change == "calls": files["/probe"]["provider_calls"] = 1
    with pytest.raises(q.Blocked):
        execution.verify_qualification(catalog, host)
