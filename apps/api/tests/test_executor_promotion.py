from pathlib import Path
from types import SimpleNamespace

import pytest

from app import executor_promotion as promotion
from app import executor_qualification as q
from app.executor_security import HOSTILE_JOB_TESTS


@pytest.fixture
def promotion_inputs(tmp_path, monkeypatch):
    host = SimpleNamespace(
        runner_id=6, runner_name="npd-vf-executor-ubuntu-02",
        execution_organization=q.EXECUTION_ORGANIZATION, runner_group=q.RUNNER_GROUP,
        execution_repository=q.REPOSITORY, source_commit="a" * 40,
        executor_executable_tree_sha256="b" * 64,
        execution_workflow_commit="c" * 40, binding_sha256="d" * 64,
        kill_switch=str(tmp_path / "kill"),
    )
    Path(host.kill_switch).write_bytes(b"ENGAGED\n")
    identity = q.expected_runner_identity(host)
    probe = {"verdict": "CAPABILITY_PROBES_PASS", "execution_plane_qualified": False,
        "runner_identity": dict(identity),
        "gates": {gate: {"status": "PASS"} for gate in q.GATES}, **q.ZERO}
    secret_binding_sha256 = "5" * 64
    probe["gates"]["E7"].update(
        result="PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED",
        binding_sha256=secret_binding_sha256,
        PROVIDER_CREDENTIAL_READS=0,
    )
    probe["gates"]["E10"].update(KILL_SWITCH="ENGAGED", ledger_unchanged=True)
    security = {"status": "RUNNER_SECURITY_PASS",
        "quarantine": "CLEARED_BY_VALIDATED_POLICY", "runner_identity": dict(identity),
        "hostile_job_tests": {name: "PASS" for name in HOSTILE_JOB_TESTS},
        "kill_switch": "ENGAGED", "provider_execution_allowlist": "EMPTY",
        "execution_workflow_commit": host.execution_workflow_commit, **q.ZERO}
    values = {"/probe": probe, "/manifest": {"qualification.json": "1" * 64},
              "/security": security}
    monkeypatch.setattr(promotion, "_trusted_json", lambda path, digest: values[path.as_posix()])
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    monkeypatch.setattr(q, "admission_manifest", lambda *a: {"mode": "ZERO_CALL_QUALIFICATION"})
    monkeypatch.setattr(q, "secret_presence", lambda *a: {
        "result": "PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED",
        "binding_sha256": secret_binding_sha256,
        "PROVIDER_CREDENTIAL_READS": 0,
    })
    root = tmp_path / "promotion"
    root.mkdir(mode=0o700)
    config = {"probe_receipt": "/probe", "probe_receipt_sha256": "1" * 64,
        "probe_manifest": "/manifest", "probe_manifest_sha256": "2" * 64,
        "security_review": "/security", "security_review_sha256": "3" * 64,
        "promotion_root": str(root)}
    return host, config, values


def test_promotion_is_separate_non_authority_artifact(promotion_inputs):
    host, config, values = promotion_inputs
    result = promotion.promote(host, config)
    assert result["receipt"]["status"] == "SELF_HOSTED_EXECUTION_PLANE_QUALIFIED"
    assert result["receipt"]["authority_granted"] is False
    assert result["receipt"]["o2"] == "NO"
    assert result["receipt"]["custody_binding_sha256"] == host.binding_sha256
    assert result["receipt"]["secret_binding_sha256"] == "5" * 64
    assert len(result["promotion_sha256"]) == len(result["evidence_manifest_sha256"]) == 64


def test_promotion_fails_when_any_hostile_case_is_missing(promotion_inputs):
    host, config, values = promotion_inputs
    values["/security"]["hostile_job_tests"]["unapproved_repository"] = "NOT_TESTED"
    with pytest.raises(q.Blocked, match="QUALIFICATION_SECURITY_REVIEW_FAILED"):
        promotion.promote(host, config)


def test_promotion_fails_when_secret_binding_differs_from_probe(promotion_inputs, monkeypatch):
    host, config, values = promotion_inputs
    monkeypatch.setattr(q, "secret_presence", lambda *a: {
        "result": "PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED",
        "binding_sha256": "6" * 64,
        "PROVIDER_CREDENTIAL_READS": 0,
    })
    with pytest.raises(q.Blocked, match="QUALIFICATION_SECRET_BINDING_FAILED"):
        promotion.promote(host, config)
