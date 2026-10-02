"""Offline controls are not evidence of a qualified self-hosted host."""
import asyncio
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

from app import executor_qualification as q, executor_request as request

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("executor_hook", REPO / "scripts/executor-job-started.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


@pytest.fixture
def host(tmp_path):
    return q.Host(
        runner_id=6,
        runner_name="npd-vf-executor-ubuntu-02",
        execution_organization=q.EXECUTION_ORGANIZATION,
        runner_group=q.RUNNER_GROUP,
        execution_repository=q.REPOSITORY,
        execution_workflow_commit="a" * 40,
        workflow_allowlist=str(tmp_path / "workflow-allowlist.json"),
        labels=sorted(q.LABELS),
        distro="Ubuntu",
        source=str(REPO),
        source_commit="a" * 40,
        evidence_root=str(tmp_path),
        lock_path=str(tmp_path / "lock"),
        binding=str(tmp_path / "binding"),
        binding_sha256="b" * 64,
        migration_head="0015",
        secret_binding=str(q.PROVIDER_SECRET_BINDING),
        kill_switch=str(tmp_path / "kill-switch"),
        executor_executable_tree_sha256="c" * 64,
    )


@pytest.fixture
def request_payload():
    return {"operation_id": "fixture-operation", "bundle_id": "fixture",
        "bundle_sha256": "a" * 64, "loaded_scope_sha256": "b" * 64,
        "authority_receipt_sha256": "c" * 64, "rc_tag": "vf-v3-01-rc23",
        "rc_commit": "d" * 40, "governance_main_sha": "e" * 40, "provider_capability": "asr"}


@pytest.mark.parametrize("field", [
    "command", "shell", "script", "endpoint", "secret", "retry", "fallback",
    *q.RUNNER_IDENTITY_FIELDS, "runner_identity",
])
def test_arbitrary_inputs_rejected(request_payload, field):
    with pytest.raises(q.Blocked, match="INPUT_FIELDS_INVALID"):
        request.validate_request({**request_payload, field: "anything"})


@pytest.mark.parametrize("field,value", [
    ("bundle_id", "../../private"), ("bundle_id", "x; echo injection"),
    ("operation_id", "$(curl invalid)"), ("rc_commit", "main"),
    ("authority_receipt_sha256", "wrong"), ("loaded_scope_sha256", "wrong"),
    ("bundle_sha256", "wrong"), ("provider_capability", "tts"),
])
def test_wrong_bindings_syntax(request_payload, field, value):
    with pytest.raises(q.Blocked):
        request.validate_request({**request_payload, field: value})


def test_rc22_is_closed(request_payload):
    with pytest.raises(q.Blocked, match="RC22_EXECUTION_CLOSED"):
        request.validate_request({**request_payload, "rc_tag": "vf-v3-01-rc22"})


def test_valid_shaped_request_never_means_authority(request_payload, monkeypatch, capsys):
    from app import provider_single_dispatch
    monkeypatch.setattr(provider_single_dispatch, "run_single_dispatch", lambda *a, **k: pytest.fail("dispatch"))
    monkeypatch.setenv("VF_REQUEST_JSON", json.dumps(request_payload))
    assert request.main() == 2
    output = json.loads(capsys.readouterr().out)
    assert output["state"] == "BLOCKED_PRE_CALL"
    assert output["code"] == "EXECUTOR_NOT_QUALIFIED_DISPATCH_DISABLED"
    assert all(output[key] == value for key, value in q.ZERO.items())


def test_request_logs_do_not_echo_secrets(monkeypatch, capsys):
    monkeypatch.setenv("VF_REQUEST_JSON", '{"secret":"sk-fake-fixture"}')
    assert request.main() == 2
    assert "sk-fake" not in capsys.readouterr().out


@pytest.fixture
def trusted_job():
    return {"GITHUB_REPOSITORY": q.REPOSITORY, "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_WORKFLOW_REF": q.REPOSITORY + "/.github/workflows/video-factory-executor-qualification.yml@refs/heads/main"}


@pytest.fixture
def qualification_manifest(trusted_job):
    return {"version": 1, "mode": "ZERO_CALL_QUALIFICATION",
        "approved_qualification_workflows": [{
            "workflow_ref": trusted_job["GITHUB_WORKFLOW_REF"],
            "workflow_sha": trusted_job["GITHUB_WORKFLOW_SHA"],
        }], "approved_execution_workflows": []}


@pytest.mark.parametrize("key,value", [
    ("GITHUB_REPOSITORY", "untrusted/repo"), ("GITHUB_EVENT_NAME", "pull_request"),
    ("GITHUB_EVENT_NAME", "pull_request_target"), ("GITHUB_REF", "refs/pull/1/merge"),
    ("GITHUB_REF", "refs/heads/candidate"), ("GITHUB_WORKFLOW_SHA", "b" * 40),
    ("GITHUB_WORKFLOW_REF", q.REPOSITORY + "/.github/workflows/ci.yml@refs/heads/main"),
])
def test_untrusted_runner_jobs_blocked(trusted_job, qualification_manifest, key, value):
    assert not hook.allowed({**trusted_job, key: value}, qualification_manifest)


def test_quarantine_rejects_all_jobs(trusted_job, qualification_manifest):
    empty = {**qualification_manifest, "approved_qualification_workflows": []}
    assert not hook.allowed(trusted_job, empty)
    assert hook.allowed(trusted_job, qualification_manifest)


def test_qualification_mode_rejects_provider_execution(trusted_job, qualification_manifest):
    execution = {**trusted_job, "GITHUB_WORKFLOW_REF": q.EXECUTION_WORKFLOW_REF}
    assert not hook.allowed(execution, qualification_manifest)


@pytest.mark.parametrize("name,value", [
    ("VF_REQUEST_JSON", "{}"), ("INPUT_COMMAND", "id"), ("INPUT_OPERATION_ID", "synthetic"),
])
def test_qualification_environment_injection_rejected(
    trusted_job, qualification_manifest, name, value,
):
    assert not hook.allowed({**trusted_job, name: value}, qualification_manifest)


def test_legacy_commit_only_allowlist_rejected(trusted_job):
    assert not hook.allowed(trusted_job, {"approved_workflow_commits": ["a" * 40]})


def test_host_admission_manifest_allows_only_exact_qualification(host, tmp_path, monkeypatch):
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    path = Path(host.workflow_allowlist)
    expected = {"workflow_ref": q.QUALIFICATION_WORKFLOW_REF,
                "workflow_sha": host.execution_workflow_commit}
    path.write_text(json.dumps({"version": 1, "mode": "ZERO_CALL_QUALIFICATION",
        "approved_qualification_workflows": [expected], "approved_execution_workflows": []}))
    assert q.admission_manifest(host, "qualification")["approved_execution_workflows"] == []
    path.write_text(json.dumps({"version": 1, "mode": "ZERO_CALL_QUALIFICATION",
        "approved_qualification_workflows": [expected],
        "approved_execution_workflows": [{"workflow_ref": q.EXECUTION_WORKFLOW_REF,
                                           "workflow_sha": host.execution_workflow_commit}]}))
    with pytest.raises(q.Blocked, match="QUALIFICATION_ADMISSION_NOT_EXACT"):
        q.admission_manifest(host, "qualification")


def test_wrong_runner_labels(host, tmp_path, monkeypatch):
    from dataclasses import asdict
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(asdict(replace(host, labels=["self-hosted", "linux"]))))
    with pytest.raises(q.Blocked, match="RUNNER_LABELS_INVALID"):
        q.Host.load(path)


@pytest.mark.parametrize("runner_id", [None, True, 6.0, "6", 0, -1])
def test_root_host_binding_requires_positive_integer_runner_id(host, tmp_path, monkeypatch, runner_id):
    from dataclasses import asdict
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**asdict(host), "runner_id": runner_id}))
    with pytest.raises(q.Blocked, match="RUNNER_ID_INVALID"):
        q.Host.load(path)


def test_root_host_binding_requires_complete_identity(host, tmp_path, monkeypatch):
    from dataclasses import asdict
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    path = tmp_path / "config.json"
    value = asdict(host)
    del value["runner_group"]
    path.write_text(json.dumps(value))
    with pytest.raises(q.Blocked, match="HOST_CONFIG_SCHEMA_INVALID"):
        q.Host.load(path)


def test_root_host_binding_requires_canonical_secret_binding_path(
    host, tmp_path, monkeypatch,
):
    from dataclasses import asdict
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        **asdict(host), "secret_binding": str(tmp_path / "caller-selected.json"),
    }))
    with pytest.raises(q.Blocked, match="SECRET_BINDING_PATH_INVALID"):
        q.Host.load(path)


@pytest.mark.parametrize("field,value,code", [
    ("runner_name", "", "RUNNER_NAME_INVALID"),
    ("execution_organization", "wrong-org", "EXECUTION_ORGANIZATION_INVALID"),
    ("runner_group", "Default", "RUNNER_GROUP_INVALID"),
    ("execution_repository", "wrong-org/wrong-repo", "REPOSITORY_SCOPE_INVALID"),
    ("source_commit", "wrong", "SOURCE_COMMIT_INVALID"),
    ("executor_executable_tree_sha256", "0" * 63, "EXECUTOR_TREE_HASH_INVALID"),
    ("execution_workflow_commit", "0" * 39, "EXECUTION_WORKFLOW_COMMIT_INVALID"),
])
def test_root_host_binding_rejects_wrong_identity_values(host, tmp_path, monkeypatch, field, value, code):
    from dataclasses import asdict
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**asdict(host), field: value}))
    with pytest.raises(q.Blocked, match=code):
        q.Host.load(path)


def test_runtime_unavailable(host, monkeypatch):
    monkeypatch.setattr(q.platform, "release", lambda: "generic-linux")
    with pytest.raises(q.Blocked, match="WSL_RUNTIME_UNAVAILABLE"):
        q.runtime(host)


@pytest.mark.parametrize("key,value,code", [
    ("RUNNER_NAME", "wrong-runner", "RUNNER_NAME_MISMATCH"),
    ("GITHUB_REPOSITORY_OWNER", "wrong-org", "EXECUTION_ORGANIZATION_MISMATCH"),
    ("GITHUB_REPOSITORY", "wrong-org/wrong-repo", "REPOSITORY_SCOPE_INVALID"),
    ("GITHUB_EVENT_NAME", "pull_request", "UNTRUSTED_EVENT"),
    ("GITHUB_REF", "refs/pull/1/merge", "UNTRUSTED_REF"),
    ("GITHUB_WORKFLOW_REF", q.EXECUTION_WORKFLOW_REF, "UNTRUSTED_WORKFLOW"),
    ("GITHUB_WORKFLOW_SHA", "0" * 40, "EXECUTION_WORKFLOW_COMMIT_MISMATCH"),
])
def test_runtime_observation_cannot_replace_root_identity(host, monkeypatch, key, value, code):
    monkeypatch.setattr(q.sys, "platform", "linux")
    monkeypatch.setattr(q.platform, "release", lambda: "microsoft-standard-WSL2")
    trusted = {
        "WSL_DISTRO_NAME": host.distro,
        "RUNNER_NAME": host.runner_name,
        "GITHUB_REPOSITORY_OWNER": host.execution_organization,
        "GITHUB_REPOSITORY": host.execution_repository,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": q.QUALIFICATION_WORKFLOW_REF,
        "GITHUB_WORKFLOW_SHA": host.execution_workflow_commit,
    }
    for name, observed in trusted.items():
        monkeypatch.setenv(name, observed)
    monkeypatch.setenv(key, value)
    with pytest.raises(q.Blocked, match=code):
        q.runtime(host)


def _secret_binding(**changes):
    value = {
        "version": 1,
        "credential_alias": q.CANONICAL_CREDENTIAL_ALIAS,
        "provider": "openai",
        "capability_scope": ["asr"],
        "source_type": "UNBOUND",
        "source_locator": None,
        "owner": "root",
        "expected_owner_uid": 0,
        "expected_owner_gid": 0,
        "expected_mode": "0400",
        "state": "UNBOUND_APPROVED_SLOT",
        "created_for": "VF-EXECUTOR-05C",
        "authority_granted": False,
        "secret_source_present": False,
        "systemd_credential_id": None,
        "encryption_key_type": None,
        "provider_runtime_reads": 0,
        "backend_qualification_receipt_sha256": None,
    }
    value.update(changes)
    return value


def _bound_secret_host(host, tmp_path, monkeypatch, value, *, receipt_changes=None):
    if value.get("state") == "BOUND_ENCRYPTED_SOURCE_PRESENT":
        receipt = {
            "version": 1, "task": "VF-SECRET-01", "status": "PASS",
            "systemd_version": "255 (255.4-1ubuntu8.17)",
            "host_key_present": True, "host_key_owner": "root:root",
            "host_key_mode": "0400", "host_key_regular_file": True,
            "host_key_symlink": False, "runner_host_key_read": False,
            "runner_host_key_write": False,
            "credential_mechanism": "LoadCredentialEncrypted",
            "systemd_credential_id": q.SYSTEMD_CREDENTIAL_ID,
            "encryption_key_type": "HOST", "synthetic_encrypt": "PASS",
            "name_binding": "PASS", "controlled_service_receive": "PASS",
            "access_isolation": "PASS", "cleanup": "PASS",
            "actual_provider_credential_decrypted": False,
            "provider_runtime_reads": 0, "provider_calls": 0,
            "encrypted_source_path": str(q.SYSTEMD_ENCRYPTED_SOURCE),
            "encrypted_source_present": True,
            "encrypted_source_owner": "root:root",
            "encrypted_source_mode": "0400",
            "encrypted_source_regular_file": True,
            "encrypted_source_symlink": False,
            "encrypted_source_nonempty": True,
            "credstore_owner": "root:root", "credstore_mode": "0700",
            "runner_source_read": False, "runner_source_write": False,
            "runner_credstore_list": False,
        }
        receipt.update(receipt_changes or {})
        receipt_path = tmp_path / "systemd-backend-receipt.json"
        receipt_raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        receipt_path.write_bytes(receipt_raw)
        value["backend_qualification_receipt_sha256"] = hashlib.sha256(receipt_raw).hexdigest()
        monkeypatch.setattr(q, "SYSTEMD_BACKEND_RECEIPT", receipt_path)
    binding = tmp_path / "provider-secret-binding.json"
    binding.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    return replace(host, secret_binding=str(binding))


def test_unbound_metadata_is_present_but_e7_stays_blocked(host, tmp_path, monkeypatch):
    bound = _bound_secret_host(host, tmp_path, monkeypatch, _secret_binding())
    with pytest.raises(q.ProbeBlocked, match="BLOCKED_SECRET_SOURCE_NOT_INSTALLED") as exc:
        q.secret_presence(bound)
    assert exc.value.evidence["SECRET_BINDING_METADATA_PRESENT"] is True
    assert exc.value.evidence["SECRET_SOURCE_PRESENT"] is False
    assert exc.value.evidence["PROVIDER_CREDENTIAL_READS"] == 0


def test_secret_binding_rejects_extra_fields(host, tmp_path, monkeypatch):
    bound = _bound_secret_host(
        host, tmp_path, monkeypatch, _secret_binding(api_key="forbidden"),
    )
    with pytest.raises(q.Blocked, match="SECRET_BINDING_SCHEMA_INVALID"):
        q.secret_presence(bound)


def test_bound_source_presence_never_reads_plaintext(host, tmp_path, monkeypatch):
    value = _secret_binding(
        source_type="SYSTEMD_ENCRYPTED_CREDENTIAL",
        source_locator=str(q.SYSTEMD_ENCRYPTED_SOURCE),
        state="BOUND_ENCRYPTED_SOURCE_PRESENT", secret_source_present=True,
        systemd_credential_id=q.SYSTEMD_CREDENTIAL_ID,
        encryption_key_type="HOST", created_for="VF-SECRET-01",
    )
    bound = _bound_secret_host(host, tmp_path, monkeypatch, value)
    original = Path.read_bytes
    def guarded_read(path):
        if path in {q.SYSTEMD_ENCRYPTED_SOURCE, q.SYSTEMD_HOST_KEY}:
            pytest.fail("provider credential plaintext read")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    result = q.secret_presence(bound)
    assert result["SECRET_SOURCE_PRESENT"] is True
    assert result["PROVIDER_CREDENTIAL_READS"] == 0
    assert result["result"] == "PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED"


@pytest.mark.parametrize("receipt_changes", [
    {"encrypted_source_nonempty": False},
    {"encrypted_source_owner": "vf-executor:vf-executor"},
    {"encrypted_source_mode": "0644"},
    {"encrypted_source_symlink": True},
    {"credstore_mode": "0711"},
    {"runner_source_read": True},
    {"runner_source_write": True},
    {"runner_credstore_list": True},
    {"host_key_owner": "vf-executor:vf-executor"},
    {"host_key_mode": "0600"},
    {"host_key_symlink": True},
    {"runner_host_key_read": True},
])
def test_root_receipt_rejects_invalid_custody_metadata(
    host, tmp_path, monkeypatch, receipt_changes,
):
    bound = _bound_secret_host(host, tmp_path, monkeypatch, _secret_binding(
        source_type="SYSTEMD_ENCRYPTED_CREDENTIAL",
        source_locator=str(q.SYSTEMD_ENCRYPTED_SOURCE),
        state="BOUND_ENCRYPTED_SOURCE_PRESENT", secret_source_present=True,
        systemd_credential_id=q.SYSTEMD_CREDENTIAL_ID,
        encryption_key_type="HOST", created_for="VF-SECRET-01",
    ), receipt_changes=receipt_changes)
    with pytest.raises(q.Blocked, match="SYSTEMD_BACKEND_RECEIPT_INVALID"):
        q.secret_presence(bound)


@pytest.mark.parametrize("field,value,code", [
    ("source_locator", "/wrong/provider-source", "SECRET_BINDING_BOUND_STATE_INVALID"),
    ("systemd_credential_id", "wrong-id", "SECRET_BINDING_BOUND_STATE_INVALID"),
    ("encryption_key_type", "NULL", "SECRET_BINDING_BOUND_STATE_INVALID"),
    ("source_type", "ROOT_FILE", "SECRET_BINDING_BOUND_STATE_INVALID"),
    ("state", "BOUND_SOURCE_INSTALLED", "SECRET_BINDING_STATE_INVALID"),
])
def test_bound_systemd_metadata_is_exact(host, tmp_path, monkeypatch, field, value, code):
    binding = tmp_path / "provider-secret-binding.json"
    payload = _secret_binding(
        source_type="SYSTEMD_ENCRYPTED_CREDENTIAL",
        source_locator=str(q.SYSTEMD_ENCRYPTED_SOURCE),
        state="BOUND_ENCRYPTED_SOURCE_PRESENT", secret_source_present=True,
        systemd_credential_id=q.SYSTEMD_CREDENTIAL_ID,
        encryption_key_type="HOST", created_for="VF-SECRET-01",
        backend_qualification_receipt_sha256="1" * 64,
    )
    payload[field] = value
    binding.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    with pytest.raises(q.Blocked, match=code):
        q.load_secret_binding(replace(host, secret_binding=str(binding)))


def test_backend_receipt_hash_is_bound(host, tmp_path, monkeypatch):
    bound = _bound_secret_host(host, tmp_path, monkeypatch, _secret_binding(
        source_type="SYSTEMD_ENCRYPTED_CREDENTIAL",
        source_locator=str(q.SYSTEMD_ENCRYPTED_SOURCE),
        state="BOUND_ENCRYPTED_SOURCE_PRESENT", secret_source_present=True,
        systemd_credential_id=q.SYSTEMD_CREDENTIAL_ID,
        encryption_key_type="HOST", created_for="VF-SECRET-01",
    ))
    q.SYSTEMD_BACKEND_RECEIPT.write_text("{}", encoding="utf-8")
    with pytest.raises(q.Blocked, match="SYSTEMD_BACKEND_RECEIPT_HASH_MISMATCH"):
        q.secret_presence(bound)


def test_backend_receipt_requires_root_owned_non_symlink_policy(
    host, tmp_path, monkeypatch,
):
    bound = _bound_secret_host(host, tmp_path, monkeypatch, _secret_binding(
        source_type="SYSTEMD_ENCRYPTED_CREDENTIAL",
        source_locator=str(q.SYSTEMD_ENCRYPTED_SOURCE),
        state="BOUND_ENCRYPTED_SOURCE_PRESENT", secret_source_present=True,
        systemd_credential_id=q.SYSTEMD_CREDENTIAL_ID,
        encryption_key_type="HOST", created_for="VF-SECRET-01",
    ))
    calls = []
    def policy(path, **kwargs):
        calls.append((path, kwargs))
        if path == q.SYSTEMD_BACKEND_RECEIPT:
            raise q.Blocked("SYMLINK_BLOCKED")
    monkeypatch.setattr(q, "private_path", policy)
    with pytest.raises(q.Blocked, match="SYMLINK_BLOCKED"):
        q.secret_presence(bound)
    assert calls[-1] == (q.SYSTEMD_BACKEND_RECEIPT, {"root_owned": True})


def test_private_execution_repo_uses_root_owned_operator_provenance(
    host, tmp_path, monkeypatch,
):
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    monkeypatch.setattr(q.subprocess, "run", lambda *a, **k: pytest.fail("network git"))
    path = tmp_path / "execution-provenance.json"
    bound = replace(host, execution_provenance=str(path))
    path.write_text(json.dumps({
        "version": 1,
        "source": "GITHUB_OPERATOR_VERIFIED",
        "execution_organization": host.execution_organization,
        "execution_repository": host.execution_repository,
        "runner_group": host.runner_group,
        "repository_access": "SELECTED_REPOSITORIES",
        "selected_repositories": [host.execution_repository],
        "selected_workflows": [q.QUALIFICATION_WORKFLOW_REF, q.EXECUTION_WORKFLOW_REF],
        "public_repositories_allowed": False,
        "execution_workflow_commit": host.execution_workflow_commit,
    }))
    result = q.github(bound)
    assert result["observed_main"] == host.execution_workflow_commit
    assert result["GITHUB_ACCESS"] == "VERIFIED_BY_ROOT_OWNED_OPERATOR_EVIDENCE"


def test_operator_provenance_mismatch_fails_closed(host, tmp_path, monkeypatch):
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    path = tmp_path / "execution-provenance.json"
    bound = replace(host, execution_provenance=str(path))
    path.write_text(json.dumps({
        "version": 1,
        "source": "GITHUB_OPERATOR_VERIFIED",
        "execution_organization": host.execution_organization,
        "execution_repository": host.execution_repository,
        "runner_group": host.runner_group,
        "repository_access": "SELECTED_REPOSITORIES",
        "selected_repositories": [host.execution_repository],
        "selected_workflows": [q.QUALIFICATION_WORKFLOW_REF, q.EXECUTION_WORKFLOW_REF],
        "public_repositories_allowed": False,
        "execution_workflow_commit": "0" * 40,
    }))
    with pytest.raises(q.Blocked, match="EXECUTION_WORKFLOW_PROVENANCE_MISMATCH"):
        q.github(bound)


@pytest.mark.skipif(os.name != "posix", reason="requires real Unix ownership/fsync/flock")
def test_evidence_persists_and_manifest_is_immutable(tmp_path):
    tmp_path.chmod(0o700)
    digest = q.persist(tmp_path, "receipt.json", q.ZERO)
    assert digest == q.sha((tmp_path / "receipt.json").read_bytes())
    with pytest.raises(FileExistsError):
        q.persist(tmp_path, "receipt.json", q.ZERO)


@pytest.mark.skipif(os.name != "posix", reason="requires Unix filesystem")
def test_read_only_evidence_blocks(tmp_path):
    if os.getuid() == 0:
        pytest.skip("root bypasses DAC")
    tmp_path.chmod(0o500)
    try:
        with pytest.raises(PermissionError):
            q.persist(tmp_path, "receipt.json", q.ZERO)
    finally:
        tmp_path.chmod(0o700)


@pytest.mark.skipif(os.name != "posix", reason="requires real flock")
def test_concurrent_attempt_blocks_and_lock_inode_survives(tmp_path):
    tmp_path.chmod(0o700)
    lock = tmp_path / "plane.lock"
    with q.plane_lock(lock):
        with pytest.raises(q.Blocked, match="CONCURRENT_EXECUTION_BLOCKED"):
            with q.plane_lock(lock):
                pytest.fail("overlapping execution")
    assert lock.exists()
    with q.plane_lock(lock):
        pass


def test_bundle_fixture_cleanup_and_rejection(tmp_path):
    result = q.fixture_mount(tmp_path)
    assert result["loader_probe"] == "VALID_EXPIRED_SYNTHETIC_FIXTURE_LOADED"
    assert list(tmp_path.iterdir()) == []


async def test_kill_switch_disengaged_blocks(host, tmp_path, monkeypatch):
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    Path(host.kill_switch).write_bytes(b"DISENGAGED\n")
    with pytest.raises(q.Blocked, match="KILL_SWITCH_NOT_ENGAGED"):
        await q.check_only(host, tmp_path)


async def test_e3_rejects_noncanonical_custody_hash_before_database_access(host):
    from app.provider_custody import CustodyBlocked

    with pytest.raises(CustodyBlocked, match="CUSTODY_BINDING_NOT_CANONICAL"):
        await q.custody(host)


async def test_check_only_calls_canonical_validator_without_dispatch(host, tmp_path, monkeypatch):
    from app import provider_single_dispatch as dispatch
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    Path(host.kill_switch).write_bytes(b"ENGAGED\n")
    monkeypatch.setattr(dispatch, "run_single_dispatch", lambda *a, **k: pytest.fail("dispatch"))
    monkeypatch.setattr(dispatch, "create_async_engine", lambda *a, **k: pytest.fail("database mutation"))
    result = await q.check_only(host, tmp_path)
    assert result["CHECK_ONLY_RUNNER"] == "VERIFIED"
    assert Path(host.kill_switch).read_bytes() == b"ENGAGED\n"


@pytest.fixture
def mock_probes(host, monkeypatch):
    writes = {}
    monkeypatch.setattr(q, "persist", lambda root, name, data: writes.setdefault(name, data) and "a" * 64)
    monkeypatch.setattr(q, "runtime", lambda h: {"WSL_RUNTIME": "VERIFIED"})
    async def custody(h):
        return {"identity": {}, "migration_head": "0015", "counts": {},
                "active_operations": 0, "reserved_vnd": "0",
                "qualification_access": "SELECT_ONLY"}
    monkeypatch.setattr(q, "custody", custody)
    monkeypatch.setattr(q, "github", lambda h: {"GITHUB_ACCESS": "VERIFIED"})
    monkeypatch.setattr(q, "load_secret_binding", lambda h: (_secret_binding(), b"synthetic-metadata"))
    monkeypatch.setattr(q, "provider_network", lambda *a: {"PROVIDER_NETWORK": "VERIFIED"})
    monkeypatch.setattr(q, "secret_presence", lambda h: {
        "SECRET_SOURCE": "PRESENT", "binding_sha256": q.sha(b"synthetic-metadata"),
    })
    monkeypatch.setattr(q, "fixture_mount", lambda r: {"BUNDLE_MOUNT_CAPABILITY": "VERIFIED"})
    async def check(h, r):
        return {"KILL_SWITCH": "ENGAGED", "CHECK_ONLY_RUNNER": "VERIFIED"}
    monkeypatch.setattr(q, "check_only", check)
    return writes


@pytest.mark.parametrize("probe,gate", [
    ("runtime", "E2"), ("custody", "E3"), ("github", "E5"),
    ("provider_network", "E6"), ("secret_presence", "E7"),
    ("fixture_mount", "E9"), ("check_only", "E10"),
])
async def test_unavailable_capability_fails_closed(host, tmp_path, mock_probes, monkeypatch, probe, gate):
    def fail(*args):
        raise RuntimeError("must-not-log-this-value")
    monkeypatch.setattr(q, probe, fail)
    result = await q.qualify(host, tmp_path)
    assert result["verdict"] == "BLOCKED"
    assert result["gates"][gate]["status"] == "BLOCKED"
    assert "must-not-log" not in json.dumps(result)
    assert all(result[k] == v for k, v in q.ZERO.items())


async def test_e7_preserves_non_secret_unbound_evidence(
    host, tmp_path, mock_probes, monkeypatch,
):
    def unbound(_host):
        raise q.ProbeBlocked("BLOCKED_SECRET_SOURCE_NOT_INSTALLED", {
            "SECRET_BINDING_METADATA_PRESENT": True,
            "SECRET_SOURCE_PRESENT": False,
            "PROVIDER_CREDENTIAL_READS": 0,
        })
    monkeypatch.setattr(q, "secret_presence", unbound)
    result = await q.qualify(host, tmp_path)
    assert result["gates"]["E7"] == {
        "status": "BLOCKED",
        "code": "BLOCKED_SECRET_SOURCE_NOT_INSTALLED",
        "SECRET_BINDING_METADATA_PRESENT": True,
        "SECRET_SOURCE_PRESENT": False,
        "PROVIDER_CREDENTIAL_READS": 0,
    }
    assert result["credential_reads"] == 0


async def test_non_select_only_qualification_access_blocks(host, tmp_path, mock_probes, monkeypatch):
    async def custody(h):
        return {"identity": {}, "migration_head": "0015", "counts": {},
                "active_operations": 0, "reserved_vnd": "0",
                "qualification_access": "MUTATING"}
    monkeypatch.setattr(q, "custody", custody)
    result = await q.qualify(host, tmp_path)
    assert result["gates"]["E8"]["status"] == "BLOCKED"
    assert result["budget_reserved_vnd"] == "0"


async def test_active_or_reserved_custody_cannot_be_qualified(
    host, tmp_path, mock_probes, monkeypatch,
):
    async def active_custody(_host):
        return {
            "identity": {},
            "migration_head": "0015",
            "counts": {"provider_safety_operations": 1},
            "active_operations": 1,
            "reserved_vnd": "500",
            "qualification_access": "SELECT_ONLY",
        }

    monkeypatch.setattr(q, "custody", active_custody)
    result = await q.qualify(host, tmp_path)
    assert result["verdict"] == "BLOCKED"
    assert result["gates"]["E3"] == {
        "status": "BLOCKED",
        "code": "CUSTODY_ACTIVE_RESERVATION_STATE_INVALID",
    }
    assert result["gates"]["E4"]["status"] == "BLOCKED"
    assert result["gates"]["E8"]["status"] == "BLOCKED"


async def test_evidence_failure_cannot_return_success(host, tmp_path, mock_probes, monkeypatch):
    def fail(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(q, "persist", fail)
    with pytest.raises(OSError):
        await q.qualify(host, tmp_path)


def test_secret_scan_blocks_plaintext():
    with pytest.raises(q.Blocked, match="SECRET_SCAN_FAILED"):
        q.secret_scan(b'{"unexpected":"sk-this-is-a-fake-test"}')


def test_workflow_boundary_and_shared_concurrency():
    import yaml
    workflows = [yaml.safe_load((REPO / ".github/workflows" / name).read_text()) for name in (
        "video-factory-executor-qualification.yml", "video-factory-provider-execution.yml")]
    assert workflows[0]["concurrency"] == workflows[1]["concurrency"]
    assert workflows[0]["concurrency"]["cancel-in-progress"] is False
    for workflow in workflows:
        triggers = workflow.get("on", workflow.get(True))
        assert set(triggers) == {"workflow_dispatch"}
        dispatch = triggers["workflow_dispatch"] or {}
        inputs = set(dispatch.get("inputs", {}))
        assert not inputs.intersection({*q.RUNNER_IDENTITY_FIELDS, "runner_identity"})
        assert workflow["permissions"] == {}
        for job in workflow["jobs"].values():
            assert job["runs-on"]["group"] == q.RUNNER_GROUP
            assert set(job["runs-on"]["labels"]) == q.LABELS
            assert job["if"] == (
                "github.repository == 'npd-ai/npd-video-factory-executor' && "
                "github.ref == 'refs/heads/main'"
            )
            assert all("uses" not in step for step in job["steps"])
