from __future__ import annotations

import json
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.human_auth import authorize_human_request
from app.provider_safety import (
    ProviderBudgetPolicy,
    ProviderCallContext,
    ProviderCircuitPolicy,
    ProviderRateLimitError,
    ProviderRetryPolicy,
    ProviderRightsEvidence,
    ProviderSafetyBlocked,
    ProviderSafetyController,
    ProviderSafetyPolicy,
    ProviderTransientError,
    normalize_provider_definitions,
    verify_provider_artifact,
    verify_provider_artifact_storage,
)
from app.provider_safety_routes import router as provider_safety_router
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
    per_request_timeout: float = 10,
    max_concurrent_calls: int = 2,
) -> ProviderSafetyPolicy:
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
            per_request_timeout_seconds=per_request_timeout,
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
        approved_policy(max_attempts=1, per_request_timeout=0.01)
    )

    async def never_returns() -> str:
        await asyncio.Event().wait()
        return "unreachable"

    with pytest.raises(ProviderSafetyBlocked) as timeout_error:
        await timeout_controller.execute(
            context("timeout-operation", paid=False, estimate=Decimal("0")),
            never_returns,
        )
    assert timeout_error.value.code == "PROVIDER_TIMEOUT"
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
