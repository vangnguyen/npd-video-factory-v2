"""Offline executor integration, using SQLite and a fake transport exclusively."""
from contextlib import contextmanager
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import executor_execution as executor
from app import executor_qualification as q
from app import provider_single_dispatch as canonical
from test_provider_single_dispatch import FakeAdapter, NOW, _setup
from test_rc17_asr_w1_lineage_gate_bundle import _active_policy, _asr_context


def test_catalog_is_separate_from_authority_and_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "CATALOG", tmp_path / "absent")
    with pytest.raises(q.Blocked, match="EXECUTOR_NOT_QUALIFIED_DISPATCH_DISABLED"):
        executor.load_catalog()
    (tmp_path / "absent").write_text("{}")
    monkeypatch.setattr(executor, "_trusted_json", lambda *a: {"version": 1, "dispatch_enabled": False})
    with pytest.raises(q.Blocked, match="DISPATCH_DISABLED"):
        executor.load_catalog()


@pytest.mark.parametrize("change", [
    {"source_commit": "wrong"}, {"runner_id": 22}, {"runner_name": "untrusted"},
    {"status": "CI_PASS"}, {"gates": {"E1": "PASS"}}, {"provider_calls": 1},
    {"budget_reserved_vnd": "1"}, {"operation_consumption": 1}, {"kill_switch": "DISENGAGED"},
])
def test_o2_cannot_replace_independent_qualification(monkeypatch, change):
    host = SimpleNamespace(source_commit="a" * 40, runner_name="dedicated")
    receipt = {"status": "SELF_HOSTED_EXECUTION_PLANE_QUALIFIED", "source_commit": host.source_commit,
               "runner_id": 21, "runner_name": host.runner_name,
               "gates": {gate: "PASS" for gate in q.GATES}, **q.ZERO, "kill_switch": "ENGAGED"}
    monkeypatch.setattr(executor, "_trusted_json", lambda *a: {**receipt, **change})
    with pytest.raises(q.Blocked):
        executor.verify_qualification({"qualification_receipt": "/fake", "qualification_sha256": "a" * 64}, host)


@pytest.mark.parametrize("field", ["operation_id", "bundle_sha256", "loaded_scope_sha256", "authority_receipt_sha256"])
def test_request_cannot_select_other_approved_operation(field):
    with pytest.raises(q.Blocked, match="REQUEST_NOT_EXACTLY_APPROVED"):
        executor.bind_request({field: "changed"}, {"request": {field: "approved"}}, None)


async def _canonical_setup(tmp_path, monkeypatch):
    engine, sessions, repository = await _setup(tmp_path)
    policy = _active_policy().model_copy(update={"global_kill_switch_engaged": True})
    scope = policy.execution_gate
    context = _asr_context(1)
    provider = FakeAdapter(scope, "success")
    paths = canonical.SingleDispatchPaths(
        rc_source=tmp_path / "rc", binding=tmp_path / "binding", binding_sha256="a" * 64,
        bundle=tmp_path / "bundle", authority=tmp_path / "authority", authority_sha256="b" * 64,
        provenance=tmp_path / "provenance", provenance_sha256="c" * 64,
        operation_manifest=tmp_path / "operation", asset=tmp_path / "asset",
        reference_transcript=tmp_path / "reference", rights_record=tmp_path / "rights",
        evidence_directory=tmp_path / "evidence")
    binding = SimpleNamespace(operation_key=context.operation_key)
    monkeypatch.setattr(canonical, "_validate_non_secret_bindings", lambda *a, **k: SimpleNamespace(
        binding=binding, scope=scope, context=context, metadata=None))
    monkeypatch.setattr(canonical, "load_binding", lambda *a: binding)
    async def custody(*a, **k):
        return {"safe": True}
    monkeypatch.setattr(canonical, "bootstrap_custody", custody)
    monkeypatch.setattr(canonical, "_verify_virgin_custody", lambda *a: None)
    monkeypatch.setattr(canonical, "ledger_url", lambda *a: "fixture")
    monkeypatch.setattr(canonical, "create_async_engine", lambda *a, **k: engine)
    monkeypatch.setattr(canonical, "ProviderSafetyRepository", lambda *a: repository)
    monkeypatch.setattr(canonical, "OpenAITranscriptionProvider", lambda **k: provider)
    return paths, policy, provider, repository, sessions


async def test_canonical_observer_order_evidence_precedes_secret_and_reservation(tmp_path, monkeypatch):
    paths, policy, provider, repository, sessions = await _canonical_setup(tmp_path, monkeypatch)
    seen = ["INIT", "ENVIRONMENT_PREFLIGHT"]
    reads = []
    recorder = canonical._EvidenceRecorder(paths.evidence_directory, _asr_context(1).operation_key)
    def resolve(alias):
        assert seen[-1] == "EVIDENCE_ARMED"
        assert json.loads((recorder.folder / "armed.json").read_bytes())["events"][-1]["reserved_vnd"] == "0"
        reads.append(alias)
        return "synthetic-fixture-credential"
    result = await canonical.run_single_dispatch(paths, runtime_policy=policy,
        credential_resolver=resolve, clock=lambda: NOW, transition=seen.append)
    assert tuple([*seen, "TERMINAL_EVIDENCE"]) == executor.STATES
    assert result.state == "QUALITY_REVIEW_REQUIRED" and provider.invocations == 1 and len(reads) == 1


async def test_final_host_guard_failure_releases_reservation_without_transport(tmp_path, monkeypatch):
    paths, policy, provider, repository, sessions = await _canonical_setup(tmp_path, monkeypatch)
    def deny():
        raise canonical.SingleDispatchBlocked("HOST_EXECUTION_POLICY_CHANGED")
    result = await canonical.run_single_dispatch(paths, runtime_policy=policy,
        credential_resolver=lambda alias: "synthetic-fixture-credential", clock=lambda: NOW,
        final_preflight=deny)
    assert result.state == "BLOCKED_PRE_CALL" and result.operation_consumed is False
    assert result.charged_vnd == Decimal("0") and provider.invocations == 0
    assert result.evidence_sha256 is not None


async def test_missing_secret_seals_precall_evidence_and_never_reserves(tmp_path, monkeypatch):
    paths, policy, provider, repository, sessions = await _canonical_setup(tmp_path, monkeypatch)
    from unittest.mock import AsyncMock
    reserve = AsyncMock(side_effect=AssertionError("reservation forbidden"))
    monkeypatch.setattr(repository, "reserve_operation", reserve)
    with pytest.raises(canonical.SingleDispatchBlocked, match="CREDENTIAL_UNAVAILABLE"):
        await canonical.run_single_dispatch(paths, runtime_policy=policy,
            credential_resolver=lambda alias: "", clock=lambda: NOW)
    recorder = canonical._EvidenceRecorder(paths.evidence_directory, _asr_context(1).operation_key)
    terminal = json.loads((recorder.folder / "terminal.json").read_bytes())
    assert terminal["provider_call_state"] == "NOT_SENT" and terminal["operation_consumed"] is False
    assert (recorder.folder / "manifest.json").exists()
    reserve.assert_not_called()
    assert provider.invocations == 0


async def test_transition_failure_precedes_durable_dispatch_marker(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    paths, policy, provider, repository, sessions = await _canonical_setup(tmp_path, monkeypatch)
    marker = AsyncMock(wraps=repository.mark_dispatch_started)
    release = AsyncMock(wraps=repository.release_pre_dispatch)
    monkeypatch.setattr(repository, "mark_dispatch_started", marker)
    monkeypatch.setattr(repository, "release_pre_dispatch", release)
    def observe(state):
        if state == "SINGLE_DISPATCH":
            raise canonical.SingleDispatchBlocked("OBSERVER_FAILED")
    result = await canonical.run_single_dispatch(paths, runtime_policy=policy,
        credential_resolver=lambda alias: "synthetic-fixture-credential", clock=lambda: NOW,
        transition=observe)
    assert result.state == "BLOCKED_PRE_CALL" and result.operation_consumed is False
    assert result.charged_vnd == 0 and result.evidence_sha256 is not None
    marker.assert_not_called()
    release.assert_awaited_once()


@pytest.mark.parametrize("failure", ["commit_then_raise", "read_unavailable", "release_unavailable"])
async def test_reservation_acknowledgement_failure_bounded_reconciliation(tmp_path, monkeypatch, failure):
    from unittest.mock import AsyncMock
    paths, policy, provider, repository, sessions = await _canonical_setup(tmp_path, monkeypatch)
    reserve_original = repository.reserve_operation
    state_original = repository.dispatch_state
    committed = False
    async def reserve(*args, **kwargs):
        nonlocal committed
        await reserve_original(*args, **kwargs)
        committed = True
        raise RuntimeError("synthetic lost acknowledgement")
    async def state(*args, **kwargs):
        if committed and failure == "read_unavailable":
            raise RuntimeError("synthetic unavailable custody")
        return await state_original(*args, **kwargs)
    reserve_mock = AsyncMock(side_effect=reserve)
    release = AsyncMock(wraps=repository.release_pre_dispatch)
    if failure == "release_unavailable":
        release.side_effect = RuntimeError("synthetic unavailable release")
    monkeypatch.setattr(repository, "reserve_operation", reserve_mock)
    monkeypatch.setattr(repository, "dispatch_state", state)
    monkeypatch.setattr(repository, "release_pre_dispatch", release)
    result = await canonical.run_single_dispatch(paths, runtime_policy=policy,
        credential_resolver=lambda alias: "synthetic-fixture-credential", clock=lambda: NOW)
    reserve_mock.assert_awaited_once()
    assert provider.invocations == 0 and result.evidence_sha256 is not None
    if failure == "commit_then_raise":
        assert result.state == "BLOCKED_PRE_CALL" and result.operation_consumed is False
        assert result.charged_vnd == 0 and result.dispatch_started is False
        release.assert_awaited_once()
    else:
        assert result.state == "REVIEW_REQUIRED" and result.operation_consumed is None
        assert result.charged_vnd is None and result.dispatch_started is None
        assert release.await_count == (0 if failure == "read_unavailable" else 1)


async def test_competing_job_never_writes_evidence_outside_plane_lock(tmp_path, monkeypatch):
    host = SimpleNamespace(lock_path=str(tmp_path / "lock"))
    monkeypatch.setattr(executor, "load_catalog", lambda: {})
    monkeypatch.setattr(q.Host, "load", lambda: host)
    @contextmanager
    def denied(*a):
        raise q.Blocked("CONCURRENT_EXECUTION_BLOCKED")
        yield
    monkeypatch.setattr(q, "plane_lock", denied)
    monkeypatch.setattr(q, "persist", lambda *a: pytest.fail("evidence write without lock"))
    monkeypatch.setattr(q, "runtime", lambda *a: pytest.fail("runtime after denied lock"))
    monkeypatch.setattr(executor, "read_kill_switch", lambda *a: pytest.fail("custody after denied lock"))
    result = await executor.execute({})
    assert result["state"] == "BLOCKED_PRE_CALL" and result["code"] == "CONCURRENT_EXECUTION_BLOCKED"
    assert result["provider_calls"] == result["credential_reads"] == 0


@pytest.mark.parametrize("interrupted", [False, "pre", "post", "cleanup", "kill"])
async def test_host_delegates_once_unmounts_and_seals_under_exclusive_lock(tmp_path, monkeypatch, interrupted):
    import hashlib
    from unittest.mock import AsyncMock
    source = Path(executor.__file__).resolve().parents[3]
    host = SimpleNamespace(source=str(source), evidence_root=str(tmp_path), lock_path=str(tmp_path / "lock"))
    raw = b'{"synthetic":true}'
    bundle = tmp_path / "source-bundle.json"
    bundle.write_bytes(raw)
    paths = canonical.SingleDispatchPaths(source, tmp_path / "binding", "a" * 64, bundle,
        tmp_path / "authority", "b" * 64, tmp_path / "provenance", "c" * 64,
        tmp_path / "operation", tmp_path / "asset", tmp_path / "reference", tmp_path / "rights",
        tmp_path / "operations")
    monkeypatch.setattr(executor, "load_catalog", lambda: {"operations": {"fixture": {}}})
    monkeypatch.setattr(q.Host, "load", lambda: host)
    monkeypatch.setattr(q, "runtime", lambda *a: None)
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    monkeypatch.setattr(executor, "verify_qualification", lambda *a: None)
    finished = [False]
    def kill_read(*a):
        if finished[0] and interrupted == "kill":
            raise q.Blocked("KILL_SWITCH_NOT_ENGAGED")
    monkeypatch.setattr(executor, "read_kill_switch", kill_read)
    if interrupted == "cleanup":
        @contextmanager
        def cleanup_fails(**kwargs):
            folder = tmp_path / "runtime-bundle-synthetic-leak"
            folder.mkdir()
            yield str(folder)
            raise RuntimeError("synthetic bundle cleanup failure")
        monkeypatch.setattr(executor.tempfile, "TemporaryDirectory", cleanup_fails)
    monkeypatch.setattr(executor, "bind_request", lambda *a: (paths, None))
    lock = []
    @contextmanager
    def locked(*a):
        lock.append(True)
        try:
            yield
        finally:
            lock.pop()
    monkeypatch.setattr(q, "plane_lock", locked)
    def persist(*a):
        assert lock == [True]
        if interrupted != "cleanup":
            assert not list(tmp_path.glob("runtime-bundle-*"))
        return "d" * 64
    monkeypatch.setattr(q, "persist", persist)
    checked = SimpleNamespace(ready_for_execution_preflight=True, ready_for_provider_dispatch=False,
                              credential_read_performed=False, provider_call_performed=False)
    validator = AsyncMock(return_value=checked)
    monkeypatch.setattr(canonical, "validate_single_dispatch", validator)
    async def synthetic_run(mounted_paths, **kwargs):
        assert mounted_paths.bundle.read_bytes() == raw and lock == [True]
        if interrupted in {"pre", "post"}:
            for state in executor.STATES[2:(7 if interrupted == "post" else 3)]:
                kwargs["transition"](state)
            raise RuntimeError("sensitive details must not reach output")
        for state in executor.STATES[2:-1]:
            kwargs["transition"](state)
        finished[0] = True
        return canonical.SingleDispatchOutcome("QUALITY_REVIEW_REQUIRED", "QUALITY_REVIEW_REQUIRED",
            True, True, Decimal("1"), Decimal("1"), "e" * 64, ())
    dispatch = AsyncMock(side_effect=synthetic_run)
    monkeypatch.setattr(canonical, "run_single_dispatch", dispatch)
    result = await executor.execute({"bundle_id": "fixture", "bundle_sha256": hashlib.sha256(raw).hexdigest()})
    assert not lock and result["bundle_mounted"] is (interrupted == "cleanup")
    if interrupted != "kill":
        assert result["wrapper_evidence_sha256"] == "d" * 64
    assert result["credential_reads"] == 0
    assert "sensitive" not in json.dumps(result)
    assert result["provider_calls"] == (None if interrupted == "post" else 0 if interrupted == "pre" else 1)
    if interrupted == "pre":
        assert result["state"] == "BLOCKED_PRE_CALL" and result["budget_reserved_vnd"] == "0"
    if interrupted in {"cleanup", "kill"}:
        assert result["state"] == "REVIEW_REQUIRED"
        assert result["operation_consumption"] is True and result["actual_cost_vnd"] == "1"
        assert result["canonical_evidence_sha256"] == "e" * 64
    validator.assert_awaited_once()
    dispatch.assert_awaited_once()
