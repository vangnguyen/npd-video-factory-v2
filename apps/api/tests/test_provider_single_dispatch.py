"""Disposable SQLite and fake-adapter tests; no credential or provider transport."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.auto_edit_providers import ProviderTranscript
from app.db import Base, create_engine, create_session_factory
from app.openai_transcription_provider import OpenAITranscriptionProvider
from app.provider_safety_db import (
    ProviderSafetyAttemptORM,
    ProviderSafetyBudgetDayORM,
    ProviderSafetyOperationORM,
)
from app.provider_safety_repository import ProviderSafetyRepository
from app.provider_safety import ProviderSafetyController, ProviderSafetyPolicy
from app.provider_single_dispatch import (
    _EvidenceRecorder,
    _ScopedKillSwitch,
    _run_protocol,
    _verify_runtime_policy,
)
from test_rc17_asr_w1_lineage_gate_bundle import ACTIVE_AT, _active_policy, _asr_context


NOW = ACTIVE_AT + timedelta(minutes=5)
REQUEST_SHA = "a" * 64


def test_checked_in_policy_cannot_be_promoted_by_runner():
    scope = _active_policy().execution_gate
    assert scope is not None
    with pytest.raises(Exception, match="RUNTIME_SAFETY_POLICY_NOT_AUTHORIZED"):
        _verify_runtime_policy(ProviderSafetyPolicy(), scope)
    active = _active_policy().model_copy(update={"global_kill_switch_engaged": True})
    _verify_runtime_policy(active, scope)
    with pytest.raises(Exception, match="RUNTIME_SAFETY_POLICY_SCOPE_MISMATCH"):
        _verify_runtime_policy(active.model_copy(update={"execution_gate": None}), scope)


def test_operation_scoped_kill_switch_is_single_use_and_reengages():
    switch = _ScopedKillSwitch("synthetic-op-1")
    assert switch.engaged and switch.transition_count == 0
    with pytest.raises(Exception, match="KILL_SWITCH_DISPATCH_DENIED"):
        switch.allow_one_dispatch("synthetic-op-2")
    switch.allow_one_dispatch("synthetic-op-1")
    assert not switch.engaged and switch.transition_count == 1
    with pytest.raises(Exception, match="KILL_SWITCH_DISPATCH_DENIED"):
        switch.allow_one_dispatch("synthetic-op-1")
    switch.reengage()
    assert switch.engaged
    with pytest.raises(Exception, match="KILL_SWITCH_DISPATCH_DENIED"):
        switch.allow_one_dispatch("synthetic-op-1")


class FakeAdapter(OpenAITranscriptionProvider):
    def __init__(self, scope, behavior: str):
        super().__init__(
            model="whisper-1", credential_alias=scope.credential_alias,
            credential_resolver=lambda alias: (_ for _ in ()).throw(
                AssertionError("credential resolver must not be called in fake tests")
            ),
            language="vi", provider_http_timeout_seconds=scope.provider_http_timeout_seconds,
            controller_hard_timeout_seconds=scope.controller_hard_timeout_seconds,
            max_file_bytes=scope.max_file_bytes,
            max_duration_seconds=scope.max_duration_seconds,
            estimated_cost_vnd=scope.per_operation_limit_vnd,
            vnd_per_minute=scope.vnd_per_minute,
            asr_prompt_profile=scope.asr_prompt_profile,
        )
        self.behavior = behavior
        self.invocations = 0
        self.boundary_invocations = 0

    async def transcribe(self, path, *, metadata, checksum_sha256, expected_asr_prompt_profile, on_http_dispatch):
        self.invocations += 1
        if self.behavior == "pre":
            raise ValueError("synthetic pre-send failure")
        self.boundary_invocations += 1
        await on_http_dispatch(REQUEST_SHA, "vf-synthetic-request")
        if self.behavior == "twice":
            self.boundary_invocations += 1
            await on_http_dispatch(REQUEST_SHA, "vf-synthetic-request")
        if self.behavior == "post":
            raise RuntimeError("synthetic post-send failure")
        if self.behavior == "timeout":
            raise asyncio.TimeoutError()
        return ProviderTranscript(
            language="vi", confidence=None, segments=(), actual_cost_vnd=Decimal("100"),
            provenance={
                "request_sha256": REQUEST_SHA, "response_sha256": "b" * 64,
                "provider_request_id": "req_synthetic", "latency_ms": 1.0,
                "secret_recorded": False,
            },
        )


async def _setup(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'ledger.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = create_session_factory(engine)
    repository = ProviderSafetyRepository(sessions)
    await repository.ensure_state()
    return engine, sessions, repository


async def _counts(sessions, operation_key):
    async with sessions() as session:
        operation = await session.get(ProviderSafetyOperationORM, operation_key)
        attempts = int(await session.scalar(select(func.count()).select_from(ProviderSafetyAttemptORM)) or 0)
        budget = await session.get(ProviderSafetyBudgetDayORM, NOW.date())
        return operation, attempts, budget


@pytest.mark.parametrize("behavior,terminal,consumed,attempts", [
    ("success", "QUALITY_REVIEW_REQUIRED", True, 1),
    ("pre", "BLOCKED_PRE_CALL", False, 0),
    ("post", "PROVIDER_ERROR", True, 1),
    ("timeout", "PROVIDER_TIMEOUT", True, 1),
    ("twice", "PROVIDER_ERROR", True, 1),
])
async def test_single_dispatch_boundaries_and_evidence(tmp_path, behavior, terminal, consumed, attempts):
    scope = _active_policy().execution_gate
    assert scope is not None
    context = _asr_context(1)
    engine, sessions, repository = await _setup(tmp_path)
    provider = FakeAdapter(scope, behavior)
    evidence = _EvidenceRecorder(tmp_path / "evidence", context.operation_key)
    try:
        result = await _run_protocol(
            scope=scope, context=context, repository=repository, provider=provider,
            policy=_active_policy().model_copy(update={"global_kill_switch_engaged": True}),
            asset=tmp_path / "synthetic.wav", metadata=None,
            evidence=evidence, clock=lambda: NOW,
        )
        assert result.state == terminal
        assert result.dispatch_started is consumed
        assert result.operation_consumed is consumed
        assert provider.invocations == 1
        operation, count, budget = await _counts(sessions, context.operation_key)
        assert count == attempts
        assert budget.reserved_vnd == 0
        if consumed:
            assert operation is not None
            assert operation.dispatch_protocol_version == 1
            assert operation.dispatch_started_at is not None
            assert operation.status == ("succeeded" if behavior == "success" else "failed")
            assert result.charged_vnd == (Decimal("100") if behavior == "success" else Decimal("500"))
        else:
            assert operation is None
            assert result.charged_vnd == 0
        terminal_evidence = json.loads((evidence.folder / "terminal.json").read_bytes())
        assert terminal_evidence["dispatch_started"] is consumed
        assert terminal_evidence["provider_call_state"] == ("POSSIBLY_SENT" if consumed else "NOT_SENT")
        assert terminal_evidence["kill_switch_after"] == "ENGAGED"
        assert terminal_evidence["operation_2"] == "LOCKED"
        assert terminal_evidence["secret_recorded"] is False
        manifest = json.loads((evidence.folder / "manifest.json").read_bytes())
        assert hashlib.sha256((evidence.folder / "manifest.json").read_bytes()).hexdigest() == result.evidence_sha256
        assert manifest["files"]["terminal.json"] == hashlib.sha256(
            (evidence.folder / "terminal.json").read_bytes()
        ).hexdigest()
        if consumed:
            assert (evidence.folder / "dispatch-intent.json").is_file()
        else:
            assert not (evidence.folder / "dispatch-intent.json").exists()
    finally:
        await engine.dispose()


async def test_reentry_after_dispatch_is_blocked_without_second_adapter_invocation(tmp_path):
    scope = _active_policy().execution_gate
    assert scope is not None
    context = _asr_context(1)
    engine, sessions, repository = await _setup(tmp_path)
    first = FakeAdapter(scope, "success")
    second = FakeAdapter(scope, "success")
    try:
        await _run_protocol(
            scope=scope, context=context, repository=repository, provider=first,
            policy=_active_policy().model_copy(update={"global_kill_switch_engaged": True}),
            asset=tmp_path / "synthetic.wav", metadata=None,
            evidence=_EvidenceRecorder(tmp_path / "evidence1", context.operation_key), clock=lambda: NOW,
        )
        with pytest.raises(Exception, match="DUPLICATE_OPERATION_BLOCKED"):
            await _run_protocol(
                scope=scope, context=context, repository=repository, provider=second,
                policy=_active_policy().model_copy(update={"global_kill_switch_engaged": True}),
                asset=tmp_path / "synthetic.wav", metadata=None,
                evidence=_EvidenceRecorder(tmp_path / "evidence2", context.operation_key), clock=lambda: NOW,
            )
        assert first.invocations == 1 and second.invocations == 0
        operation, count, budget = await _counts(sessions, context.operation_key)
        assert operation.status == "succeeded" and count == 1 and budget.reserved_vnd == 0
    finally:
        await engine.dispose()


async def test_stale_unstarted_protocol_releases_without_consumption(tmp_path):
    scope = _active_policy().execution_gate
    assert scope is not None
    context = _asr_context(1)
    engine, sessions, repository = await _setup(tmp_path)
    try:
        reservation = await repository.reserve_operation(
            context, now=NOW, max_attempts=1, max_concurrent_calls=1,
            per_operation_limit_vnd=scope.per_operation_limit_vnd,
            daily_limit_vnd=scope.acceptance_window_limit_vnd,
            circuit_failure_threshold=3, circuit_cooldown_seconds=60,
            retention_days=400, single_dispatch_protocol=True,
        )
        assert reservation.allowed
        recovered = await repository.recover_stale_operations(
            stale_before=NOW + timedelta(seconds=1), now=NOW + timedelta(seconds=2),
            warning_thresholds=(50, 80, 100),
        )
        assert recovered == [context.operation_key]
        operation, count, budget = await _counts(sessions, context.operation_key)
        assert operation is None and count == 0 and budget.reserved_vnd == 0
    finally:
        await engine.dispose()


async def test_protocol_forbids_attempt_or_terminal_before_dispatch_marker(tmp_path):
    scope = _active_policy().execution_gate
    assert scope is not None
    context = _asr_context(1)
    engine, sessions, repository = await _setup(tmp_path)
    try:
        reservation = await repository.reserve_operation(
            context, now=NOW, max_attempts=1, max_concurrent_calls=1,
            per_operation_limit_vnd=scope.per_operation_limit_vnd,
            daily_limit_vnd=scope.acceptance_window_limit_vnd,
            circuit_failure_threshold=3, circuit_cooldown_seconds=60,
            retention_days=400, single_dispatch_protocol=True,
        )
        assert reservation.allowed
        attempt = ProviderSafetyController(
            _active_policy().model_copy(update={"global_kill_switch_engaged": True}),
            clock=lambda: NOW,
        )._build_attempt_record(
            context, attempt=1, status="failed", retryable=False,
            error_code="SYNTHETIC", error_evidence=None,
            actual_cost_vnd=None, charged_cost_vnd=Decimal("500"), started_at=NOW,
        )
        with pytest.raises(RuntimeError, match="requires a committed dispatch marker"):
            await repository.record_attempt(attempt)
        with pytest.raises(RuntimeError, match="cannot finish before dispatch"):
            await repository.finish_operation(
                context, now=NOW, attempts=1, charged_vnd=Decimal("500"),
                succeeded=False, failure_code="SYNTHETIC", circuit_failure_threshold=3,
                warning_thresholds=(50, 80, 100),
            )
        assert await repository.release_pre_dispatch(context, now=NOW)
        operation, attempts, budget = await _counts(sessions, context.operation_key)
        assert operation is None and attempts == 0 and budget.reserved_vnd == 0
    finally:
        await engine.dispose()


async def test_marker_is_single_use_and_blocks_pre_call_release(tmp_path):
    scope = _active_policy().execution_gate
    assert scope is not None
    context = _asr_context(1)
    engine, sessions, repository = await _setup(tmp_path)
    try:
        reservation = await repository.reserve_operation(
            context, now=NOW, max_attempts=1, max_concurrent_calls=1,
            per_operation_limit_vnd=scope.per_operation_limit_vnd,
            daily_limit_vnd=scope.acceptance_window_limit_vnd,
            circuit_failure_threshold=3, circuit_cooldown_seconds=60,
            retention_days=400, single_dispatch_protocol=True,
        )
        assert reservation.allowed
        await repository.mark_dispatch_started(
            context, now=NOW, request_sha256=REQUEST_SHA,
            client_request_id="vf-synthetic-request",
        )
        with pytest.raises(RuntimeError, match="not virgin and reserved"):
            await repository.mark_dispatch_started(
                context, now=NOW, request_sha256=REQUEST_SHA,
                client_request_id="vf-synthetic-request",
            )
        assert not await repository.release_pre_dispatch(context, now=NOW)
        operation, attempts, budget = await _counts(sessions, context.operation_key)
        assert operation.status == "reserved" and attempts == 0
        assert budget.reserved_vnd == Decimal("500")
    finally:
        await engine.dispose()


async def test_stale_marked_protocol_is_terminal_with_unknown_actual_cost(tmp_path):
    scope = _active_policy().execution_gate
    assert scope is not None
    context = _asr_context(1)
    engine, sessions, repository = await _setup(tmp_path)
    try:
        reservation = await repository.reserve_operation(
            context, now=NOW, max_attempts=1, max_concurrent_calls=1,
            per_operation_limit_vnd=scope.per_operation_limit_vnd,
            daily_limit_vnd=scope.acceptance_window_limit_vnd,
            circuit_failure_threshold=3, circuit_cooldown_seconds=60,
            retention_days=400, single_dispatch_protocol=True,
        )
        assert reservation.allowed
        await repository.mark_dispatch_started(
            context, now=NOW, request_sha256=REQUEST_SHA,
            client_request_id="vf-synthetic-request",
        )
        assert not await repository.release_pre_dispatch(context, now=NOW)
        recovered = await repository.recover_stale_operations(
            stale_before=NOW + timedelta(seconds=1), now=NOW + timedelta(seconds=2),
            warning_thresholds=(50, 80, 100),
        )
        assert recovered == [context.operation_key]
        operation, count, budget = await _counts(sessions, context.operation_key)
        assert operation.status == "recovered"
        assert operation.failure_code == "STALE_DISPATCH_RECOVERED_COST_UNKNOWN"
        assert operation.charged_vnd == Decimal("500")
        assert count == 0 and budget.reserved_vnd == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize("failure_point,consumed", [
    ("arm", False),
    ("dispatch_evidence", False),
    ("dispatch_marker", False),
    ("attempt_record", True),
    ("finish_once", True),
])
async def test_exception_boundaries_reconcile_and_keep_single_call(tmp_path, monkeypatch, failure_point, consumed):
    scope = _active_policy().execution_gate
    assert scope is not None
    context = _asr_context(1)
    engine, sessions, repository = await _setup(tmp_path)
    provider = FakeAdapter(scope, "success")
    evidence = _EvidenceRecorder(tmp_path / "evidence", context.operation_key)
    if failure_point == "arm":
        monkeypatch.setattr(evidence, "arm", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic arm failure")))
    elif failure_point == "dispatch_evidence":
        monkeypatch.setattr(evidence, "mark_dispatch", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic dispatch evidence failure")))
    elif failure_point == "dispatch_marker":
        monkeypatch.setattr(repository, "mark_dispatch_started", AsyncMock(side_effect=RuntimeError("synthetic marker failure")))
    elif failure_point == "attempt_record":
        monkeypatch.setattr(repository, "record_attempt", AsyncMock(side_effect=RuntimeError("synthetic attempt write failure")))
    else:
        original_finish = repository.finish_operation
        calls = 0

        async def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("synthetic finish acknowledgement failure")
            return await original_finish(*args, **kwargs)

        monkeypatch.setattr(repository, "finish_operation", fail_once)
    try:
        result = await _run_protocol(
            scope=scope, context=context, repository=repository, provider=provider,
            policy=_active_policy().model_copy(update={"global_kill_switch_engaged": True}),
            asset=tmp_path / "synthetic.wav", metadata=None,
            evidence=evidence, clock=lambda: NOW,
        )
        assert result.dispatch_started is consumed
        assert result.operation_consumed is consumed
        assert provider.invocations == (0 if failure_point == "arm" else 1)
        operation, attempts, budget = await _counts(sessions, context.operation_key)
        assert budget.reserved_vnd == 0
        if consumed:
            assert operation is not None and operation.status in {"failed", "succeeded"}
        else:
            assert operation is None and attempts == 0
        if failure_point in {"attempt_record", "finish_once"}:
            assert result.state == "REVIEW_REQUIRED"
        assert result.evidence_sha256 is not None
    finally:
        await engine.dispose()
