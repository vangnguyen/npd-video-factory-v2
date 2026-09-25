"""Offline controls are not evidence of a qualified self-hosted host."""
import asyncio
from dataclasses import replace
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
    return q.Host(q.REPOSITORY, "dedicated", sorted(q.LABELS), "Ubuntu", str(REPO), "a" * 40,
        str(tmp_path), str(tmp_path / "lock"), str(tmp_path / "binding"), "b" * 64,
        "0015", str(tmp_path / "secret"), str(tmp_path / "kill-switch"))


@pytest.fixture
def request_payload():
    return {"operation_id": "fixture-operation", "bundle_id": "fixture",
        "bundle_sha256": "a" * 64, "loaded_scope_sha256": "b" * 64,
        "authority_receipt_sha256": "c" * 64, "rc_tag": "vf-v3-01-rc23",
        "rc_commit": "d" * 40, "governance_main_sha": "e" * 40, "provider_capability": "asr"}


@pytest.mark.parametrize("field", ["command", "shell", "script", "endpoint", "secret", "retry", "fallback"])
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
    monkeypatch.setenv("VF_REQUEST_JSON", '{"secret":"sk-this-is-a-fake-secret"}')
    assert request.main() == 2
    assert "sk-this" not in capsys.readouterr().out


@pytest.fixture
def trusted_job():
    return {"GITHUB_REPOSITORY": q.REPOSITORY, "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_WORKFLOW_REF": q.REPOSITORY + "/.github/workflows/video-factory-executor-qualification.yml@refs/heads/main"}


@pytest.mark.parametrize("key,value", [
    ("GITHUB_REPOSITORY", "untrusted/repo"), ("GITHUB_EVENT_NAME", "pull_request"),
    ("GITHUB_EVENT_NAME", "pull_request_target"), ("GITHUB_REF", "refs/pull/1/merge"),
    ("GITHUB_REF", "refs/heads/candidate"), ("GITHUB_WORKFLOW_SHA", "b" * 40),
    ("GITHUB_WORKFLOW_REF", q.REPOSITORY + "/.github/workflows/ci.yml@refs/heads/main"),
])
def test_untrusted_runner_jobs_blocked(trusted_job, key, value):
    assert not hook.allowed({**trusted_job, key: value}, {"approved_workflow_commits": ["a" * 40]})


def test_quarantine_rejects_all_jobs(trusted_job):
    assert not hook.allowed(trusted_job, {"approved_workflow_commits": []})
    assert hook.allowed(trusted_job, {"approved_workflow_commits": ["a" * 40]})


def test_wrong_runner_labels(host, tmp_path, monkeypatch):
    from dataclasses import asdict
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(asdict(replace(host, labels=["self-hosted", "linux"]))))
    with pytest.raises(q.Blocked, match="RUNNER_LABELS_INVALID"):
        q.Host.load(path)


def test_runtime_unavailable(host, monkeypatch):
    monkeypatch.setattr(q.platform, "release", lambda: "generic-linux")
    with pytest.raises(q.Blocked, match="WSL_RUNTIME_UNAVAILABLE"):
        q.runtime(host)


def test_missing_secret_source_does_not_read_plaintext(host, monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("secret plaintext read"))
    with pytest.raises((FileNotFoundError, q.Blocked)):
        q.secret_presence(host)


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
    assert result["loader_probe"] == "INVALID_FIXTURE_REJECTED"
    assert list(tmp_path.iterdir()) == []


async def test_kill_switch_disengaged_blocks(host, tmp_path, monkeypatch):
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    Path(host.kill_switch).write_bytes(b"DISENGAGED\n")
    with pytest.raises(q.Blocked, match="KILL_SWITCH_NOT_ENGAGED"):
        await q.check_only(host, tmp_path)


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
        return {"identity": {}, "migration_head": "0015", "operation_state": "VIRGIN",
                "reserved_vnd": "0", "reservation_privileges": True}
    monkeypatch.setattr(q, "custody", custody)
    monkeypatch.setattr(q, "github", lambda h: {"GITHUB_ACCESS": "VERIFIED"})
    monkeypatch.setattr(q, "provider_network", lambda: {"PROVIDER_NETWORK": "VERIFIED"})
    monkeypatch.setattr(q, "secret_presence", lambda h: {"SECRET_SOURCE": "PRESENT"})
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


async def test_reservation_backend_unavailable(host, tmp_path, mock_probes, monkeypatch):
    async def custody(h):
        return {"identity": {}, "migration_head": "0015", "operation_state": "VIRGIN",
                "reserved_vnd": "0", "reservation_privileges": False}
    monkeypatch.setattr(q, "custody", custody)
    result = await q.qualify(host, tmp_path)
    assert result["gates"]["E8"]["status"] == "BLOCKED"
    assert result["budget_reserved_vnd"] == "0"


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
        for job in workflow["jobs"].values():
            assert set(job["runs-on"]) == q.LABELS
            assert "refs/heads/main" in job["if"]
            assert all("uses" not in step for step in job["steps"])
