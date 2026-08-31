from __future__ import annotations

import json
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text

from app.human_auth import authorize_human_request
from app.provider_safety import (
    ProviderBudgetPolicy,
    ProviderCallContext,
    ProviderCircuitPolicy,
    ProviderErrorEvidence,
    ProviderExecutionTrace,
    ProviderRateLimitError,
    ProviderRetryPolicy,
    ProviderRightsEvidence,
    ProviderSafetyBlocked,
    ProviderSafetyController,
    ProviderSafetyPolicy,
    ProviderTimeoutError,
    ProviderTransientError,
    normalize_provider_definitions,
    verify_provider_artifact,
    verify_provider_artifact_storage,
)
from app.provider_safety_routes import router as provider_safety_router
from app.provider_safety_durable import DurableProviderSafetyController
from app.provider_safety_repository import ProviderSafetyRepository
from app.db import Base, create_engine, create_session_factory
import app.provider_safety_db  # noqa: F401
from app.provider_safety_db import ProviderSafetyAttemptORM
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


def approved_policy(
    *,
    max_attempts: int = 3,
    daily_limit: Decimal = Decimal("10000"),
    per_operation_limit: Decimal = Decimal("3000"),
    failure_threshold: int = 3,
    max_poll_attempts: int = 4,
    provider_http_timeout: float | None = None,
    controller_hard_timeout: float = 10,
    max_concurrent_calls: int = 2,
) -> ProviderSafetyPolicy:
    if provider_http_timeout is None:
        provider_http_timeout = controller_hard_timeout / 2
    return ProviderSafetyPolicy(
        external_execution_enabled=True,
        paid_execution_enabled=True,
        global_kill_switch_engaged=False,
        credential_gate_approved=True,
        rights_gate_approved=True,
        budget=ProviderBudgetPolicy(
            approved=True,
            owner_approval_id="V3-01-APP-999",
            per_operation_limit_vnd=per_operation_limit,
            daily_limit_vnd=daily_limit,
        ),
        retry=ProviderRetryPolicy(
            max_attempts=max_attempts,
            provider_http_timeout_seconds=provider_http_timeout,
            controller_hard_timeout_seconds=controller_hard_timeout,
            base_delay_seconds=1,
            max_delay_seconds=4,
            max_elapsed_seconds=30,
            max_poll_attempts=max_poll_attempts,
            poll_interval_seconds=1,
            max_concurrent_calls=max_concurrent_calls,
        ),
        circuit=ProviderCircuitPolicy(failure_threshold=failure_threshold, cooldown_seconds=10),
    )


def context(
    operation_key: str,
    *,
    paid: bool = True,
    estimate: Decimal | None = Decimal("100"),
    rights_required: bool = False,
    rights: list[ProviderRightsEvidence] | None = None,
) -> ProviderCallContext:
    return ProviderCallContext(
        operation_key=operation_key,
        workspace_id="wsp_test",
        project_id="prj_test",
        provider_key="mock-provider",
        capability="image_generation",
        operation="generate",
        external_call=True,
        paid=paid,
        estimated_cost_vnd=estimate,
        credential_alias="secret://provider/mock",
        rights_required=rights_required,
        rights=rights or [],
    )


def rights(
    record_id: str = "rights-valid",
    *,
    commercial: bool | str = True,
    derivative: bool | str = True,
    decision: str = "APPROVED",
    expiry: datetime | None = None,
) -> ProviderRightsEvidence:
    return ProviderRightsEvidence(
        rights_record_id=record_id,
        asset_id="asset-valid",
        asset_hash="a" * 64,
        source_type="stock",
        provider="mock-provider",
        provider_asset_or_job_id="provider-asset-valid",
        source_url_or_reference="evidence://provider/source",
        acquired_at_utc=datetime(2026, 8, 27, 11, 0, tzinfo=timezone.utc),
        license_name="Mock commercial license",
        license_version_or_terms_date="2026-08-27",
        commercial_use=commercial,
        derivative_use=derivative,
        social_platform_use=["youtube", "facebook"],
        territory=["VN"],
        expiry=expiry,
        attribution_required=False,
        attribution_text="",
        model_or_voice_rights="not-applicable",
        person_likeness_consent="not-applicable",
        trademark_review="reviewed",
        evidence_reference="evidence://rights/mock",
        reviewer="test-reviewer",
        decision=decision,
    )


@pytest.mark.asyncio
async def test_default_policy_is_vnd_only_and_fail_closed() -> None:
    controller = ProviderSafetyController.fail_closed(
        [
            {
                "provider_key": "remote-image",
                "capability": "image_generation",
                "status": "not_configured",
                "enabled": False,
                "supports_dry_run": True,
                "adapter": "app.providers.ContractOnlyImage",
                "metadata": {"contract_only": True, "paid": True},
            }
        ]
    )
    decision = await controller.preflight(context("operation-default"))
    snapshot = await controller.snapshot()

    assert decision.allowed is False
    assert decision.code == "GLOBAL_KILL_SWITCH_ENGAGED"
    assert snapshot.currency == "VND"
    assert snapshot.daily_limit_vnd == 0
    assert snapshot.external_calls_recorded == 0
    assert snapshot.providers[0].execution_class == "contract"
    assert snapshot.providers[0].external_execution_allowed is False
    assert snapshot.providers[0].production_eligible is False


def test_policy_rejects_unapproved_budget_and_raw_credentials() -> None:
    with pytest.raises(ValidationError, match="owner approval ID"):
        ProviderBudgetPolicy(
            approved=True,
            per_operation_limit_vnd=Decimal("100"),
            daily_limit_vnd=Decimal("1000"),
        )
    with pytest.raises(ValidationError, match="referenced by alias"):
        ProviderCallContext.model_validate(
            {**context("operation-credential").model_dump(), "credential_alias": "plain-token"}
        )


def test_rights_hook_blocks_missing_unknown_revoked_and_expired_records() -> None:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    assert ProviderSafetyController.evaluate_rights([], required=True, now=now).code == "RIGHTS_EVIDENCE_REQUIRED"
    for record in (
        rights("rights-unknown", commercial="unknown"),
        rights("rights-blocked", decision="BLOCKED"),
        rights("rights-expired", expiry=now - timedelta(seconds=1)),
        rights("rights-no-commercial", commercial=False),
        rights("rights-no-derivative", derivative=False),
    ):
        decision = ProviderSafetyController.evaluate_rights([record], required=True, now=now)
        assert decision.allowed is False
        assert decision.blocked_record_ids == [record.rights_record_id]
    assert ProviderSafetyController.evaluate_rights([rights()], required=True, now=now).allowed is True


@pytest.mark.asyncio
async def test_fixture_execution_never_consumes_external_budget() -> None:
    controller = ProviderSafetyController.fail_closed()
    local = ProviderCallContext(
        operation_key="fixture-operation",
        workspace_id="wsp_test",
        provider_key="fixture-image",
        capability="image_generation",
        operation="generate",
        external_call=False,
        paid=False,
    )
    result = await controller.execute(local, lambda: _return("fixture"))
    snapshot = await controller.snapshot()
    assert result.value == "fixture"
    assert result.receipt.external_call is False
    assert result.receipt.charged_cost_vnd == 0
    assert snapshot.committed_today_vnd == 0
    assert controller.attempts == ()


@pytest.mark.asyncio
async def test_transient_retry_is_bounded_and_every_attempt_is_costed() -> None:
    clock = MutableClock()
    controller = ProviderSafetyController(
        approved_policy(max_attempts=3), clock=clock.now, sleeper=clock.sleep
    )
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ProviderRateLimitError()
        return "asset"

    result = await controller.execute(context("retry-operation"), operation)
    assert result.value == "asset"
    assert result.receipt.attempts == 3
    assert result.receipt.retries == 2
    assert result.receipt.charged_cost_vnd == Decimal("300")
    assert [item.status for item in controller.attempts] == ["rate_limited", "rate_limited", "succeeded"]
    assert all(item.cost_status == "estimated" for item in controller.attempts)
    assert (await controller.snapshot()).reserved_today_vnd == 0


@pytest.mark.asyncio
async def test_non_retryable_error_runs_once_and_duplicate_operation_is_blocked() -> None:
    controller = ProviderSafetyController(approved_policy())
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("provider body is invalid")

    with pytest.raises(ProviderSafetyBlocked, match="after 1 attempt"):
        await controller.execute(context("non-retryable-operation"), operation)
    assert calls == 1
    duplicate = await controller.preflight(context("non-retryable-operation"))
    assert duplicate.allowed is False
    assert duplicate.code == "DUPLICATE_OPERATION_BLOCKED"


@pytest.mark.asyncio
async def test_circuit_opens_then_allows_one_half_open_probe_after_cooldown() -> None:
    clock = MutableClock()
    controller = ProviderSafetyController(
        approved_policy(max_attempts=1, failure_threshold=2),
        clock=clock.now,
        sleeper=clock.sleep,
    )

    async def fail() -> str:
        raise ProviderTransientError()

    for suffix in ("one", "two"):
        with pytest.raises(ProviderSafetyBlocked):
            await controller.execute(context(f"circuit-{suffix}", paid=False, estimate=Decimal("0")), fail)
    blocked = await controller.preflight(context("circuit-three", paid=False, estimate=Decimal("0")))
    assert blocked.code == "CIRCUIT_OPEN"

    await clock.sleep(10)
    recovered = await controller.execute(
        context("circuit-recovery", paid=False, estimate=Decimal("0")),
        lambda: _return("healthy"),
    )
    assert recovered.receipt.circuit_state == "closed"


@pytest.mark.asyncio
async def test_budget_reservation_alerts_and_hard_stop() -> None:
    controller = ProviderSafetyController(
        approved_policy(
            max_attempts=1,
            daily_limit=Decimal("1000"),
            per_operation_limit=Decimal("600"),
        )
    )
    first = await controller.execute(
        context("budget-50", estimate=Decimal("500")),
        lambda: _return(Decimal("500")),
        actual_cost=lambda value: value,
    )
    second = await controller.execute(
        context("budget-80", estimate=Decimal("300")),
        lambda: _return(Decimal("300")),
        actual_cost=lambda value: value,
    )
    third = await controller.execute(
        context("budget-100", estimate=Decimal("200")),
        lambda: _return(Decimal("200")),
        actual_cost=lambda value: value,
    )
    assert first.receipt.budget_alerts == [50]
    assert second.receipt.budget_alerts == [80]
    assert third.receipt.budget_alerts == [100]
    denied = await controller.preflight(context("budget-over", estimate=Decimal("1")))
    assert denied.code == "DAILY_BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_daily_budget_window_resets_without_losing_historical_attempts() -> None:
    clock = MutableClock()
    controller = ProviderSafetyController(
        approved_policy(
            max_attempts=1,
            daily_limit=Decimal("100"),
            per_operation_limit=Decimal("100"),
        ),
        clock=clock.now,
        sleeper=clock.sleep,
    )
    await controller.execute(
        context("day-one", estimate=Decimal("100")),
        lambda: _return(Decimal("100")),
        actual_cost=lambda value: value,
    )
    assert (await controller.snapshot()).committed_today_vnd == Decimal("100")
    clock.value += timedelta(days=1)
    assert (await controller.snapshot()).committed_today_vnd == Decimal("0")
    result = await controller.execute(
        context("day-two", estimate=Decimal("100")),
        lambda: _return(Decimal("100")),
        actual_cost=lambda value: value,
    )
    assert result.receipt.budget_alerts == [50, 80, 100]
    assert len(controller.attempts) == 2


@pytest.mark.asyncio
async def test_polling_has_a_deterministic_hard_limit() -> None:
    clock = MutableClock()
    controller = ProviderSafetyController(
        approved_policy(max_attempts=1, max_poll_attempts=2),
        clock=clock.now,
        sleeper=clock.sleep,
    )
    polls = 0

    async def poll() -> str:
        nonlocal polls
        polls += 1
        return "pending"

    with pytest.raises(ProviderSafetyBlocked, match="hard limit"):
        await controller.bounded_poll(
            lambda number: context(f"poll-{number}", paid=False, estimate=Decimal("0")),
            poll,
            lambda value: value == "complete",
        )
    assert polls == 2


@pytest.mark.asyncio
async def test_timeout_and_concurrency_are_hard_limits() -> None:
    timeout_controller = ProviderSafetyController(
        approved_policy(max_attempts=1, controller_hard_timeout=0.01)
    )

    async def never_returns() -> str:
        await asyncio.Event().wait()
        return "unreachable"

    with pytest.raises(ProviderSafetyBlocked) as timeout_error:
        await timeout_controller.execute(
            context("timeout-operation", paid=False, estimate=Decimal("0")),
            never_returns,
        )
    assert timeout_error.value.code == "CONTROLLER_ENVELOPE_TIMEOUT"
    assert timeout_controller.attempts[0].status == "timed_out"

    controller = ProviderSafetyController(
        approved_policy(max_attempts=1, max_concurrent_calls=1)
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def held_call() -> str:
        started.set()
        await release.wait()
        return "done"

    first = asyncio.create_task(
        controller.execute(
            context("concurrency-one", paid=False, estimate=Decimal("0")),
            held_call,
        )
    )
    await started.wait()
    denied = await controller.preflight(
        context("concurrency-two", paid=False, estimate=Decimal("0"))
    )
    assert denied.allowed is False
    assert denied.code == "PROVIDER_CONCURRENCY_LIMIT"
    release.set()
    assert (await first).value == "done"


def test_provider_metadata_and_artifact_evidence_are_structured_and_secret_free() -> None:
    definitions = normalize_provider_definitions(
        [
            {
                "provider_key": "fixture-image",
                "capability": "image_generation",
                "adapter": "app.DeterministicImage",
                "enabled": True,
                "status": "healthy",
                "supports_dry_run": True,
                "metadata": {"fixture": True, "paid": False},
            },
            {
                "provider_key": "official-image",
                "capability": "image_generation",
                "adapter": "app.OfficialImage",
                "enabled": False,
                "status": "not_configured",
                "supports_dry_run": False,
                "config_ref": "external-secret-ref:image",
                "metadata": {"paid": True},
            },
        ]
    )
    assert definitions[0]["metadata"]["execution_class"] == "fixture"
    assert definitions[1]["metadata"]["execution_class"] == "external"
    assert definitions[1]["metadata"]["credential_reference_only"] is True
    assert all(item["metadata"]["cost_currency"] == "VND" for item in definitions)

    payload = b'{"fixture":true,"asset":"verified"}'
    evidence = verify_provider_artifact(
        operation_key="artifact-operation",
        provider_key="fixture-image",
        capability="image_generation",
        request_payload={"prompt": "sensitive request is hashed, not retained"},
        payload=payload,
        content_type="application/json",
        source_reference="https://provider.invalid/signed?secret=not-retained",
    )
    assert evidence.artifact_sha256 == __import__("hashlib").sha256(payload).hexdigest()
    serialized = evidence.model_dump_json()
    assert "sensitive request" not in serialized
    assert "secret=not-retained" not in serialized
    stored = verify_provider_artifact_storage(
        evidence,
        checksum_sha256=evidence.artifact_sha256,
        size_bytes=len(payload),
        content_type="application/json",
    )
    assert stored.storage_receipt_verified is True
    with pytest.raises(ProviderSafetyBlocked) as mismatch:
        verify_provider_artifact_storage(
            evidence,
            checksum_sha256="0" * 64,
            size_bytes=len(payload),
            content_type="application/json",
        )
    assert mismatch.value.code == "ARTIFACT_STORAGE_MISMATCH"
    with pytest.raises(ProviderSafetyBlocked) as decode_error:
        verify_provider_artifact(
            operation_key="artifact-invalid",
            provider_key="fixture-image",
            capability="image_generation",
            request_payload={},
            payload=b"not-json",
            content_type="application/json",
        )
    assert decode_error.value.code == "ARTIFACT_DECODE_FAILED"


@pytest.mark.asyncio
async def test_provider_safety_endpoint_is_authenticated_and_secret_free() -> None:
    app = FastAPI()
    app.include_router(provider_safety_router, dependencies=[Depends(authorize_human_request)])
    install_test_human_auth(app)
    app.state.provider_safety_controller = ProviderSafetyController.fail_closed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/provider-safety")).status_code == 401
        response = await client.get("/api/v1/provider-safety", headers=TEST_HUMAN_HEADERS)
    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload).lower()
    assert payload["currency"] == "VND"
    assert payload["global_kill_switch_engaged"] is True
    assert "credential_alias" not in serialized
    assert "token" not in serialized


async def _return(value):
    return value


async def durable_components(tmp_path, policy: ProviderSafetyPolicy, clock: MutableClock):
    database = tmp_path / "provider-safety.db"
    engine = create_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    first_repository = ProviderSafetyRepository(session_factory)
    second_repository = ProviderSafetyRepository(session_factory)
    await first_repository.ensure_state()
    first = DurableProviderSafetyController(
        policy,
        repository=first_repository,
        clock=clock.now,
        sleeper=clock.sleep,
        operation_lease_seconds=120,
        operation_retention_days=400,
    )
    second = DurableProviderSafetyController(
        policy,
        repository=second_repository,
        clock=clock.now,
        sleeper=clock.sleep,
        operation_lease_seconds=120,
        operation_retention_days=400,
    )
    return engine, first_repository, second_repository, first, second


@pytest.mark.asyncio
async def test_durable_multi_instance_duplicate_concurrency_and_snapshot(tmp_path) -> None:
    clock = MutableClock()
    policy = approved_policy(max_attempts=1, max_concurrent_calls=1)
    engine, _, _, first, second = await durable_components(tmp_path, policy, clock)
    first_context = context("durable-first", paid=False, estimate=Decimal("0"))
    first_decision = await first.preflight(first_context)
    assert first_decision.allowed is True
    assert (await second.preflight(context("durable-second", paid=False, estimate=Decimal("0")))).code == (
        "PROVIDER_CONCURRENCY_LIMIT"
    )
    assert (await second.preflight(first_context)).code == "DUPLICATE_OPERATION_BLOCKED"
    await first._finish(
        first_context,
        first_decision,
        attempts=1,
        charged=Decimal("0"),
        succeeded=True,
    )
    snapshot = await second.snapshot()
    assert snapshot.state_backend == "postgresql"
    assert snapshot.durable_operations_recorded == 1
    assert snapshot.active_operations == 0
    assert snapshot.attempts_recorded == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_durable_budget_reservation_is_atomic_across_controllers(tmp_path) -> None:
    clock = MutableClock()
    policy = approved_policy(
        max_attempts=1,
        max_concurrent_calls=2,
        daily_limit=Decimal("100"),
        per_operation_limit=Decimal("100"),
    )
    engine, _, _, first, second = await durable_components(tmp_path, policy, clock)
    first_context = context("durable-budget-a", estimate=Decimal("60"))
    second_context = context("durable-budget-b", estimate=Decimal("60"))
    decisions = await asyncio.gather(
        first.preflight(first_context),
        second.preflight(second_context),
    )
    assert sum(item.allowed for item in decisions) == 1
    assert {item.code for item in decisions} == {
        "PROVIDER_CALL_RESERVED",
        "DAILY_BUDGET_EXCEEDED",
    }
    allowed_index = 0 if decisions[0].allowed else 1
    allowed_controller = first if allowed_index == 0 else second
    allowed_context = first_context if allowed_index == 0 else second_context
    await allowed_controller._finish(
        allowed_context,
        decisions[allowed_index],
        attempts=1,
        charged=Decimal("60"),
        succeeded=True,
    )
    snapshot = await first.snapshot()
    assert snapshot.committed_today_vnd == Decimal("60")
    assert snapshot.reserved_today_vnd == Decimal("0")
    assert snapshot.paid_calls_recorded == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_durable_execute_persists_bounded_attempts_without_memory_ledger(tmp_path) -> None:
    clock = MutableClock()
    policy = approved_policy(max_attempts=3)
    engine, _, _, first, second = await durable_components(tmp_path, policy, clock)
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ProviderRateLimitError()
        return "durable-asset"

    result = await first.execute(context("durable-retry-operation"), operation)
    assert result.value == "durable-asset"
    assert result.receipt.attempts == 3
    assert result.receipt.retries == 2
    assert result.receipt.charged_cost_vnd == Decimal("300")
    snapshot = await second.snapshot()
    assert snapshot.attempts_recorded == 3
    assert snapshot.committed_today_vnd == Decimal("300")
    assert snapshot.reserved_today_vnd == Decimal("0")
    assert first.attempts == ()
    await engine.dispose()


@pytest.mark.asyncio
async def test_durable_attempt_persists_only_structured_secret_free_error_evidence(tmp_path) -> None:
    clock = MutableClock()
    policy = approved_policy(max_attempts=1)
    engine, repository, _, controller, _ = await durable_components(tmp_path, policy, clock)
    evidence = ProviderErrorEvidence(
        category="http_provider_error",
        code="OPENAI_VISION_TRANSIENT_HTTP",
        http_status=503,
        provider_error_type="server_error",
        provider_error_code="temporarily_unavailable",
        provider_error_parameter="text.format.schema",
        provider_error_message="Provider temporarily unavailable",
        provider_request_id="req_durable_error",
        client_request_id="vf-durable-error",
        response_sha256="b" * 64,
        retryable=True,
        secret_recorded=False,
    )

    async def operation() -> str:
        raise ProviderTransientError(
            "OPENAI_VISION_TRANSIENT_HTTP",
            error_evidence=evidence,
        )

    with pytest.raises(ProviderSafetyBlocked) as blocked:
        await controller.execute(
            context("durable-error-evidence", paid=False, estimate=Decimal("0")),
            operation,
        )

    terminal_evidence = evidence.model_copy(update={"retryable": False})
    assert blocked.value.error_evidence == terminal_evidence
    async with repository.session_factory() as session:
        row = await session.scalar(
            select(ProviderSafetyAttemptORM).where(
                ProviderSafetyAttemptORM.operation_key == "durable-error-evidence"
            )
        )
    assert row is not None
    assert row.error_code == "OPENAI_VISION_TRANSIENT_HTTP"
    assert row.retryable is False
    assert row.error_evidence == terminal_evidence.model_dump(mode="json")
    assert "credential" not in json.dumps(row.error_evidence).lower()
    await engine.dispose()


@pytest.mark.asyncio
async def test_durable_controller_timeout_preserves_phase_ledger_and_duplicate_guard(tmp_path) -> None:
    clock = MutableClock()
    policy = approved_policy(max_attempts=1, controller_hard_timeout=0.01)
    engine, repository, _, controller, _ = await durable_components(tmp_path, policy, clock)
    trace = ProviderExecutionTrace()
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        trace.begin()
        trace.mark(
            "http_response_wait",
            dispatch_state="possibly_sent",
            client_request_id="vf-durable-timeout",
        )
        await asyncio.Event().wait()
        return "unreachable"

    timeout_context = context("durable-controller-timeout", estimate=Decimal("100"))
    with pytest.raises(ProviderSafetyBlocked) as blocked:
        await controller.execute(
            timeout_context,
            operation,
            timeout_evidence_factory=lambda timeout_envelope, error: trace.timeout_evidence(
                code="CONTROLLER_ENVELOPE_TIMEOUT",
                timeout_kind="controller_envelope",
                timeout_envelope=timeout_envelope,
                error=error,
                retryable=True,
                provider_error_message="Provider operation exceeded controller deadline",
            ),
        )

    assert blocked.value.code == "CONTROLLER_ENVELOPE_TIMEOUT"
    assert calls == 1
    async with repository.session_factory() as session:
        row = await session.scalar(
            select(ProviderSafetyAttemptORM).where(
                ProviderSafetyAttemptORM.operation_key == "durable-controller-timeout"
            )
        )
    assert row is not None
    assert row.status == "timed_out"
    assert row.retryable is False
    assert row.actual_cost_vnd is None
    assert row.charged_cost_vnd == Decimal("100")
    assert row.error_evidence is not None
    assert row.error_evidence["timeout_phase"] == "http_response_wait"
    assert row.error_evidence["timeout_kind"] == "controller_envelope"
    assert row.error_evidence["provider_http_timeout_seconds"] == 0.005
    assert row.error_evidence["controller_hard_timeout_seconds"] == 0.01
    assert row.error_evidence["request_dispatch_state"] == "possibly_sent"
    assert row.error_evidence["provider_request_id"] is None
    assert row.error_evidence["client_request_id"] == "vf-durable-timeout"
    assert row.error_evidence["retryable"] is False
    assert row.error_evidence["secret_recorded"] is False
    snapshot = await controller.snapshot()
    assert snapshot.attempts_recorded == 1
    assert snapshot.committed_today_vnd == Decimal("100")
    assert snapshot.reserved_today_vnd == Decimal("0")
    duplicate = await controller.preflight(timeout_context)
    assert duplicate.allowed is False
    assert duplicate.code == "DUPLICATE_OPERATION_BLOCKED"
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_90s_timeout_keeps_30s_controller_buffer_for_durable_evidence(
    tmp_path,
) -> None:
    clock = MutableClock()
    policy = approved_policy(
        max_attempts=1,
        provider_http_timeout=90,
        controller_hard_timeout=120,
    )
    engine, repository, _, controller, _ = await durable_components(tmp_path, policy, clock)
    virtual_monotonic = [0.0]
    trace = ProviderExecutionTrace(monotonic=lambda: virtual_monotonic[0])
    trace.begin()
    trace.mark(
        "http_response_wait",
        dispatch_state="possibly_sent",
        client_request_id="vf-provider-timeout-buffer",
    )
    virtual_monotonic[0] = 90.0
    provider_evidence = trace.timeout_evidence(
        code="PROVIDER_TIMEOUT",
        timeout_kind="read",
        timeout_envelope=policy.retry,
        error=TimeoutError("virtual provider deadline"),
        retryable=True,
        provider_error_message="Provider HTTP timeout expired",
    )

    async def provider_timeout() -> str:
        raise ProviderTimeoutError(error_evidence=provider_evidence)

    timeout_context = context("durable-provider-timeout", estimate=Decimal("100"))
    with pytest.raises(ProviderSafetyBlocked) as blocked:
        await controller.execute(timeout_context, provider_timeout)

    assert policy.retry.controller_hard_timeout_seconds - (
        policy.retry.provider_http_timeout_seconds
    ) == 30
    assert blocked.value.code == "PROVIDER_TIMEOUT"
    assert blocked.value.error_evidence is not None
    assert blocked.value.error_evidence.timeout_kind == "read"
    assert blocked.value.error_evidence.elapsed_ms == 90_000
    async with repository.session_factory() as session:
        row = await session.scalar(
            select(ProviderSafetyAttemptORM).where(
                ProviderSafetyAttemptORM.operation_key == "durable-provider-timeout"
            )
        )
    assert row is not None
    assert row.status == "timed_out"
    assert row.error_code == "PROVIDER_TIMEOUT"
    assert row.error_evidence is not None
    assert row.error_evidence["provider_http_timeout_seconds"] == 90
    assert row.error_evidence["controller_hard_timeout_seconds"] == 120
    assert row.error_evidence["retryable"] is False
    assert row.actual_cost_vnd is None
    assert row.charged_cost_vnd == Decimal("100")
    assert (await controller.preflight(timeout_context)).code == (
        "DUPLICATE_OPERATION_BLOCKED"
    )
    await engine.dispose()


@pytest.mark.asyncio
async def test_durable_circuit_and_stale_reservation_recover_after_restart(tmp_path) -> None:
    clock = MutableClock()
    policy = approved_policy(
        max_attempts=1,
        max_concurrent_calls=2,
        failure_threshold=1,
    )
    engine, _, second_repository, first, second = await durable_components(tmp_path, policy, clock)

    failed_context = context("durable-failure", paid=False, estimate=Decimal("0"))
    failed_decision = await first.preflight(failed_context)
    await first._finish(
        failed_context,
        failed_decision,
        attempts=1,
        charged=Decimal("0"),
        succeeded=False,
    )
    assert (
        await second.preflight(context("durable-circuit-blocked", paid=False, estimate=Decimal("0")))
    ).code == "CIRCUIT_OPEN"

    clock.value += timedelta(seconds=11)
    probe_context = context("durable-half-open", paid=False, estimate=Decimal("0"))
    probe_decision = await second.preflight(probe_context)
    assert probe_decision.allowed is True
    assert probe_decision.circuit_state == "half_open"
    assert (
        await first.preflight(context("durable-half-open-busy", paid=False, estimate=Decimal("0")))
    ).code == "CIRCUIT_HALF_OPEN_BUSY"
    await second._finish(
        probe_context,
        probe_decision,
        attempts=1,
        charged=Decimal("0"),
        succeeded=True,
    )

    stale_context = context("durable-stale", estimate=Decimal("25"))
    assert (await first.preflight(stale_context)).allowed is True
    await first._record_attempt(
        stale_context,
        attempt=1,
        status="timed_out",
        retryable=True,
        error_code="PROVIDER_TIMEOUT",
        actual_cost_vnd=None,
        charged_cost_vnd=Decimal("25"),
        started_at=clock.now(),
    )
    clock.value += timedelta(seconds=121)
    restarted = DurableProviderSafetyController(
        policy,
        repository=second_repository,
        clock=clock.now,
        sleeper=clock.sleep,
        operation_lease_seconds=120,
        operation_retention_days=400,
    )
    assert await restarted.recover_stale_operations() == ["durable-stale"]
    snapshot = await restarted.snapshot()
    assert snapshot.recovered_operations == 1
    assert snapshot.active_operations == 0
    assert snapshot.reserved_today_vnd == Decimal("0")
    assert snapshot.committed_today_vnd == Decimal("25")
    assert snapshot.attempts_recorded == 1
    assert (await restarted.preflight(stale_context)).code == "DUPLICATE_OPERATION_BLOCKED"
    await engine.dispose()


@pytest.mark.asyncio
async def test_durable_retention_purges_only_expired_terminal_operations(tmp_path) -> None:
    clock = MutableClock()
    policy = approved_policy(max_attempts=1, max_concurrent_calls=2)
    engine, first_repository, _, first, _ = await durable_components(tmp_path, policy, clock)

    completed_context = context("durable-retention-complete", paid=False, estimate=Decimal("0"))
    completed_decision = await first.preflight(completed_context)
    await first._finish(
        completed_context,
        completed_decision,
        attempts=1,
        charged=Decimal("0"),
        succeeded=True,
    )
    active_context = context("durable-retention-active", paid=False, estimate=Decimal("0"))
    assert (await first.preflight(active_context)).allowed is True

    clock.value += timedelta(days=401)
    assert await first_repository.purge_expired_operations(now=clock.now()) == 1
    snapshot = await first.snapshot()
    assert snapshot.durable_operations_recorded == 1
    assert snapshot.active_operations == 1
    assert snapshot.stale_active_operations == 1
    await engine.dispose()
