"""Promotion contract fixtures are never actual host/security qualification."""
from types import SimpleNamespace

import pytest
from app import executor_execution as execution, executor_qualification as q


@pytest.fixture
def artifacts(monkeypatch):
    host = SimpleNamespace(
        runner_id=6,
        runner_name="npd-vf-executor-ubuntu-02",
        execution_organization=q.EXECUTION_ORGANIZATION,
        runner_group=q.RUNNER_GROUP,
        execution_repository=q.REPOSITORY,
        source_commit="a" * 40,
        executor_executable_tree_sha256="f" * 64,
    )
    identity = q.expected_runner_identity(host)
    receipt = {
        "status": "SELF_HOSTED_EXECUTION_PLANE_QUALIFIED",
        "runner_identity": dict(identity),
        "gates": {gate: "PASS" for gate in q.GATES},
        "kill_switch": "ENGAGED",
        "probe_receipt": "/probe",
        "probe_receipt_sha256": "b" * 64,
        "probe_manifest": "/manifest",
        "probe_manifest_sha256": "c" * 64,
        "security_review": "/security",
        "security_review_sha256": "d" * 64,
        **q.ZERO,
    }
    probe = {
        "verdict": "CAPABILITY_PROBES_PASS",
        "execution_plane_qualified": False,
        "runner_identity": dict(identity),
        "gates": {gate: {"status": "PASS"} for gate in q.GATES},
        **q.ZERO,
    }
    probe["gates"]["E10"].update(KILL_SWITCH="ENGAGED", ledger_unchanged=True)
    security = {
        "status": "RUNNER_SECURITY_PASS",
        "runner_identity": dict(identity),
        "quarantine": "CLEARED_BY_VALIDATED_POLICY",
        "hostile_job_tests": {threat: "PASS" for threat in (
            "malicious_pr", "modified_workflow", "command_injection", "secret_exfiltration",
            "concurrent_job", "stale_rc", "altered_authority", "admission_launch_failure",
        )},
    }
    files = {
        "/promotion": receipt,
        "/probe": probe,
        "/manifest": {"qualification.json": "b" * 64},
        "/security": security,
    }
    hashes = {
        "/promotion": "e" * 64,
        "/probe": "b" * 64,
        "/manifest": "c" * 64,
        "/security": "d" * 64,
    }

    def trusted(path, digest=None):
        assert hashes[path.as_posix()] == digest
        return files[path.as_posix()]

    monkeypatch.setattr(execution, "_trusted_json", trusted)
    return host, files, {"qualification_receipt": "/promotion", "qualification_sha256": "e" * 64}


def test_explicit_promotion_binds_actual_report_shape(artifacts):
    host, files, catalog = artifacts
    execution.verify_qualification(catalog, host)
    assert files["/probe"]["execution_plane_qualified"] is False
    assert files["/promotion"]["runner_identity"] == q.expected_runner_identity(host)
    assert files["/probe"]["runner_identity"] == files["/security"]["runner_identity"]


@pytest.mark.parametrize("change", ["probe", "manifest", "security", "gate", "hostile", "ledger", "calls"])
def test_promotion_cannot_skip_prerequisites(artifacts, change):
    host, files, catalog = artifacts
    if change == "probe":
        files["/probe"]["verdict"] = "BLOCKED"
    elif change == "manifest":
        files["/manifest"]["qualification.json"] = "0" * 64
    elif change == "security":
        files["/security"]["status"] = "DESIGN_ONLY"
    elif change == "gate":
        files["/probe"]["gates"]["E3"]["status"] = "NOT_TESTED"
    elif change == "hostile":
        files["/security"]["hostile_job_tests"]["admission_launch_failure"] = "NOT_TESTED"
    elif change == "ledger":
        files["/probe"]["gates"]["E10"]["ledger_unchanged"] = False
    elif change == "calls":
        files["/probe"]["provider_calls"] = 1
    with pytest.raises(q.Blocked):
        execution.verify_qualification(catalog, host)


ARTIFACT_CODES = (
    ("/promotion", "QUALIFICATION_IDENTITY_MISMATCH"),
    ("/probe", "QUALIFICATION_PROBE_IDENTITY_MISMATCH"),
    ("/security", "QUALIFICATION_SECURITY_IDENTITY_MISMATCH"),
)
WRONG_IDENTITY_VALUES = {
    "runner_id": 7,
    "runner_name": "wrong-runner",
    "execution_organization": "wrong-org",
    "runner_group": "Default",
    "execution_repository": "wrong-org/wrong-repo",
    "source_commit": "b" * 40,
    "executor_executable_tree_sha256": "0" * 64,
}


@pytest.mark.parametrize("artifact,code", ARTIFACT_CODES)
def test_old_runner_21_is_rejected(artifacts, artifact, code):
    host, files, catalog = artifacts
    files[artifact]["runner_identity"]["runner_id"] = 21
    with pytest.raises(q.Blocked, match=code):
        execution.verify_qualification(catalog, host)


@pytest.mark.parametrize("artifact,code", ARTIFACT_CODES)
def test_missing_runner_identity_is_rejected(artifacts, artifact, code):
    host, files, catalog = artifacts
    del files[artifact]["runner_identity"]
    with pytest.raises(q.Blocked, match=code):
        execution.verify_qualification(catalog, host)


def test_qualification_receipt_for_different_runner_is_rejected(artifacts):
    host, files, catalog = artifacts
    files["/promotion"]["runner_identity"]["runner_id"] = 7
    with pytest.raises(q.Blocked, match="QUALIFICATION_IDENTITY_MISMATCH"):
        execution.verify_qualification(catalog, host)


def test_probe_receipt_for_different_runner_is_rejected(artifacts):
    host, files, catalog = artifacts
    files["/probe"]["runner_identity"]["runner_id"] = 7
    with pytest.raises(q.Blocked, match="QUALIFICATION_PROBE_IDENTITY_MISMATCH"):
        execution.verify_qualification(catalog, host)


def test_security_review_for_different_runner_is_rejected(artifacts):
    host, files, catalog = artifacts
    files["/security"]["runner_identity"]["runner_id"] = 7
    with pytest.raises(q.Blocked, match="QUALIFICATION_SECURITY_IDENTITY_MISMATCH"):
        execution.verify_qualification(catalog, host)


@pytest.mark.parametrize("artifact,code", ARTIFACT_CODES)
@pytest.mark.parametrize("field,value", WRONG_IDENTITY_VALUES.items())
def test_identity_field_mismatch_fails_closed(artifacts, artifact, code, field, value):
    host, files, catalog = artifacts
    files[artifact]["runner_identity"][field] = value
    with pytest.raises(q.Blocked, match=code):
        execution.verify_qualification(catalog, host)


@pytest.mark.parametrize("artifact,code", ARTIFACT_CODES)
@pytest.mark.parametrize("field", q.RUNNER_IDENTITY_FIELDS)
def test_missing_identity_field_fails_closed(artifacts, artifact, code, field):
    host, files, catalog = artifacts
    del files[artifact]["runner_identity"][field]
    with pytest.raises(q.Blocked, match=code):
        execution.verify_qualification(catalog, host)


@pytest.mark.parametrize("artifact,code", ARTIFACT_CODES)
@pytest.mark.parametrize("value", [6.0, "6", True, None])
def test_runner_id_comparison_is_type_strict(artifacts, artifact, code, value):
    host, files, catalog = artifacts
    files[artifact]["runner_identity"]["runner_id"] = value
    with pytest.raises(q.Blocked, match=code):
        execution.verify_qualification(catalog, host)


@pytest.mark.parametrize("artifact,code", ARTIFACT_CODES)
def test_extra_identity_field_fails_closed(artifacts, artifact, code):
    host, files, catalog = artifacts
    files[artifact]["runner_identity"]["caller_override"] = "forbidden"
    with pytest.raises(q.Blocked, match=code):
        execution.verify_qualification(catalog, host)


@pytest.mark.parametrize("artifact,code", ARTIFACT_CODES)
@pytest.mark.parametrize("field", q.RUNNER_IDENTITY_FIELDS)
def test_legacy_top_level_identity_cannot_contradict_canonical_binding(artifacts, artifact, code, field):
    host, files, catalog = artifacts
    files[artifact][field] = WRONG_IDENTITY_VALUES[field]
    with pytest.raises(q.Blocked, match=code):
        execution.verify_qualification(catalog, host)
