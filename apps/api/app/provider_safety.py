from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import Field, field_validator, model_validator

from .models import StrictModel


CircuitState = Literal["closed", "open", "half_open"]
ExecutionClass = Literal["local", "fixture", "contract", "external"]
RightsDecision = Literal["APPROVED", "REJECTED", "BLOCKED"]
RightsBoolean = bool | Literal["unknown"]
T = TypeVar("T")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProviderRetryPolicy(StrictModel):
    max_attempts: int = Field(default=3, ge=1, le=10)
    per_request_timeout_seconds: float = Field(default=60.0, gt=0, le=3600)
    base_delay_seconds: float = Field(default=1.0, ge=0, le=300)
    max_delay_seconds: float = Field(default=30.0, ge=0, le=900)
    max_elapsed_seconds: float = Field(default=120.0, gt=0, le=3600)
    max_poll_attempts: int = Field(default=20, ge=1, le=200)
    poll_interval_seconds: float = Field(default=2.0, ge=0, le=300)
    max_concurrent_calls: int = Field(default=2, ge=1, le=100)

    @model_validator(mode="after")
    def validate_delays(self) -> "ProviderRetryPolicy":
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("retry maximum delay cannot be lower than the base delay")
        return self

    def delay_for_retry(self, retry_number: int) -> float:
        if retry_number < 1:
            return 0.0
        return min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (retry_number - 1)))


class ProviderCircuitPolicy(StrictModel):
    failure_threshold: int = Field(default=3, ge=1, le=20)
    cooldown_seconds: int = Field(default=60, ge=1, le=86_400)
    half_open_max_calls: Literal[1] = 1


class ProviderBudgetPolicy(StrictModel):
    currency: Literal["VND"] = "VND"
    approved: bool = False
    owner_approval_id: str | None = Field(
        default=None,
        pattern=r"^V3-01-APP-[0-9]{3,}$",
    )
    per_operation_limit_vnd: Decimal = Field(default=Decimal("0"), ge=0)
    daily_limit_vnd: Decimal = Field(default=Decimal("0"), ge=0)
    warning_threshold_percent: tuple[Literal[50, 80, 100], ...] = (50, 80, 100)
    expires_at: datetime | None = None

    @field_validator("warning_threshold_percent")
    @classmethod
    def validate_thresholds(
        cls, value: tuple[Literal[50, 80, 100], ...]
    ) -> tuple[Literal[50, 80, 100], ...]:
        if value != (50, 80, 100):
            raise ValueError("provider budget warning thresholds must be exactly 50, 80 and 100 percent")
        return value

    @model_validator(mode="after")
    def validate_approval(self) -> "ProviderBudgetPolicy":
        if self.approved and not self.owner_approval_id:
            raise ValueError("an approved provider budget requires an owner approval ID")
        if self.approved and (self.per_operation_limit_vnd <= 0 or self.daily_limit_vnd <= 0):
            raise ValueError("an approved provider budget requires positive VND hard limits")
        if self.daily_limit_vnd and self.daily_limit_vnd < self.per_operation_limit_vnd:
            raise ValueError("daily provider budget cannot be lower than the per-operation limit")
        return self

    def active(self, now: datetime) -> bool:
        if not self.approved:
            return False
        if self.expires_at is None:
            return True
        expiry = self.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return now < expiry.astimezone(timezone.utc)


class ProviderSafetyPolicy(StrictModel):
    version: Literal[1] = 1
    external_execution_enabled: bool = False
    paid_execution_enabled: bool = False
    global_kill_switch_engaged: bool = True
    credential_gate_approved: bool = False
    rights_gate_approved: bool = False
    budget: ProviderBudgetPolicy = Field(default_factory=ProviderBudgetPolicy)
    retry: ProviderRetryPolicy = Field(default_factory=ProviderRetryPolicy)
    circuit: ProviderCircuitPolicy = Field(default_factory=ProviderCircuitPolicy)

    @model_validator(mode="after")
    def validate_execution_gates(self) -> "ProviderSafetyPolicy":
        if self.paid_execution_enabled and not self.external_execution_enabled:
            raise ValueError("paid provider execution requires external provider execution")
        if self.external_execution_enabled and not self.credential_gate_approved:
            raise ValueError("external provider execution requires the credential owner gate")
        if self.paid_execution_enabled and not self.budget.approved:
            raise ValueError("paid provider execution requires an approved VND budget")
        return self


class ProviderRightsEvidence(StrictModel):
    rights_record_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    asset_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    asset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_type: Literal["user_owned", "stock", "ai_generated", "licensed_library", "internal"]
    provider: str = Field(min_length=1, max_length=160)
    provider_asset_or_job_id: str = Field(min_length=1, max_length=240)
    source_url_or_reference: str = Field(min_length=1, max_length=1000)
    acquired_at_utc: datetime
    license_name: str = Field(min_length=1, max_length=240)
    license_version_or_terms_date: str = Field(min_length=1, max_length=160)
    commercial_use: RightsBoolean
    derivative_use: RightsBoolean
    social_platform_use: list[str] = Field(default_factory=list, max_length=50)
    territory: list[str] = Field(default_factory=list, max_length=50)
    expiry: datetime | None = None
    attribution_required: bool
    attribution_text: str = Field(default="", max_length=1000)
    model_or_voice_rights: str = Field(default="", max_length=1000)
    person_likeness_consent: str = Field(default="", max_length=1000)
    trademark_review: str = Field(default="", max_length=1000)
    evidence_reference: str = Field(min_length=1, max_length=1000)
    reviewer: str = Field(min_length=1, max_length=240)
    decision: RightsDecision

    @model_validator(mode="after")
    def validate_approval(self) -> "ProviderRightsEvidence":
        if self.attribution_required and not self.attribution_text.strip():
            raise ValueError("approved rights with attribution require attribution text")
        return self


class ProviderRightsDecision(StrictModel):
    allowed: bool
    code: str
    checked_records: int = Field(ge=0)
    blocked_record_ids: list[str] = Field(default_factory=list)


class ProviderCallContext(StrictModel):
    operation_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,199}$")
    workspace_id: str = Field(min_length=3, max_length=80)
    project_id: str | None = Field(default=None, max_length=80)
    job_id: str | None = Field(default=None, max_length=80)
    provider_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    capability: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    operation: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,159}$")
    external_call: bool
    paid: bool
    estimated_cost_vnd: Decimal | None = Field(default=None, ge=0)
    credential_alias: str | None = Field(default=None, max_length=240)
    rights_required: bool = False
    rights: list[ProviderRightsEvidence] = Field(default_factory=list, max_length=100)

    @field_validator("credential_alias")
    @classmethod
    def validate_credential_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("secret://", "vault://", "external://")):
            raise ValueError("provider credentials must be referenced by alias, never stored as values")
        return value

    @model_validator(mode="after")
    def validate_call_class(self) -> "ProviderCallContext":
        if self.paid and not self.external_call:
            raise ValueError("a paid provider call must be classified as external")
        return self


class ProviderSafetyDecision(StrictModel):
    allowed: bool
    code: str
    external_call: bool
    paid: bool
    reserved_vnd: Decimal = Field(default=Decimal("0"), ge=0)
    circuit_state: CircuitState = "closed"
    rights: ProviderRightsDecision


class ProviderAttemptRecord(StrictModel):
    usage_id: str
    operation_key: str
    provider_key: str
    capability: str
    attempt: int = Field(ge=1)
    status: Literal["succeeded", "failed", "rate_limited", "timed_out"]
    estimated_cost_vnd: Decimal | None = Field(default=None, ge=0)
    actual_cost_vnd: Decimal | None = Field(default=None, ge=0)
    charged_cost_vnd: Decimal = Field(ge=0)
    cost_status: Literal["actual", "estimated", "pending"]
    retryable: bool
    error_code: str | None
    created_at: datetime
    completed_at: datetime


class ProviderArtifactEvidence(StrictModel):
    evidence_id: str
    operation_key: str
    provider_key: str
    capability: str
    provider_job_id: str | None
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_reference_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    content_type: str
    size_bytes: int = Field(gt=0)
    payload_verified: Literal[True] = True
    storage_receipt_verified: bool = False
    real_provider_tested: bool
    rights_record_id: str | None = None
    secret_recorded: Literal[False] = False
    captured_at: datetime


class ProviderExecutionReceipt(StrictModel):
    operation_key: str
    provider_key: str
    capability: str
    status: Literal["succeeded", "failed"]
    attempts: int = Field(ge=1)
    retries: int = Field(ge=0)
    charged_cost_vnd: Decimal = Field(ge=0)
    currency: Literal["VND"] = "VND"
    budget_alerts: list[Literal[50, 80, 100]] = Field(default_factory=list)
    circuit_state: CircuitState
    external_call: bool
    paid: bool
    rights_allowed: bool


class ProviderCapabilitySafetyRead(StrictModel):
    provider_key: str
    capability: str
    status: str
    enabled: bool
    execution_class: ExecutionClass
    external_execution_allowed: bool
    paid: bool | None
    supports_dry_run: bool
    rights_required: bool
    production_eligible: bool
    circuit_state: CircuitState


class ProviderSafetySnapshot(StrictModel):
    mode: Literal["enforced"] = "enforced"
    currency: Literal["VND"] = "VND"
    external_execution_enabled: bool
    paid_execution_enabled: bool
    global_kill_switch_engaged: bool
    credential_gate_approved: bool
    budget_gate_approved: bool
    rights_gate_approved: bool
    daily_limit_vnd: Decimal = Field(ge=0)
    committed_today_vnd: Decimal = Field(ge=0)
    reserved_today_vnd: Decimal = Field(ge=0)
    warning_threshold_percent: tuple[Literal[50, 80, 100], ...]
    retry: ProviderRetryPolicy
    circuit: ProviderCircuitPolicy
    providers: list[ProviderCapabilitySafetyRead]
    external_calls_recorded: int = Field(ge=0)
    paid_calls_recorded: int = Field(ge=0)


@dataclass(frozen=True)
class ProviderExecutionResult(Generic[T]):
    value: T
    receipt: ProviderExecutionReceipt


class ProviderSafetyBlocked(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ProviderTransientError(RuntimeError):
    def __init__(self, code: str = "PROVIDER_TRANSIENT_ERROR"):
        super().__init__(code)
        self.code = code


class ProviderRateLimitError(ProviderTransientError):
    def __init__(self):
        super().__init__("PROVIDER_RATE_LIMITED")


class ProviderTimeoutError(ProviderTransientError):
    def __init__(self):
        super().__init__("PROVIDER_TIMEOUT")


@dataclass
class _CircuitRuntime:
    state: CircuitState = "closed"
    consecutive_failures: int = 0
    opened_at: datetime | None = None
    half_open_in_flight: bool = False


class ProviderSafetyController:
    """Fail-closed provider gate for V3-01-02 contract and mock execution.

    The controller deliberately stores no credential values, request payloads or provider response
    bodies. Application configuration keeps real execution disabled in V3-01-02; enabled policies
    are used only by deterministic unit tests until G-01/G-02/G-03 are separately recorded.
    """

    def __init__(
        self,
        policy: ProviderSafetyPolicy,
        *,
        provider_definitions: Sequence[dict[str, Any]] = (),
        clock: Callable[[], datetime] = utc_now,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.policy = policy
        self._provider_definitions = [dict(value) for value in provider_definitions]
        self._clock = clock
        self._sleeper = sleeper
        self._lock = asyncio.Lock()
        self._circuits: dict[tuple[str, str], _CircuitRuntime] = {}
        self._active_operations: set[str] = set()
        self._completed_operations: set[str] = set()
        self._attempts: list[ProviderAttemptRecord] = []
        self._operation_budget_day: dict[str, date] = {}
        self._committed_vnd: dict[date, Decimal] = {}
        self._reserved_vnd: dict[date, Decimal] = {}
        self._alerts_emitted: set[tuple[date, int]] = set()

    @classmethod
    def fail_closed(
        cls, provider_definitions: Sequence[dict[str, Any]] = ()
    ) -> "ProviderSafetyController":
        return cls(ProviderSafetyPolicy(), provider_definitions=provider_definitions)

    @staticmethod
    def evaluate_rights(
        records: Sequence[ProviderRightsEvidence],
        *,
        required: bool,
        now: datetime | None = None,
    ) -> ProviderRightsDecision:
        current = now or utc_now()
        if required and not records:
            return ProviderRightsDecision(
                allowed=False,
                code="RIGHTS_EVIDENCE_REQUIRED",
                checked_records=0,
            )
        blocked: list[str] = []
        for record in records:
            expiry = record.expiry
            if expiry is not None:
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                expired = current >= expiry.astimezone(timezone.utc)
            else:
                expired = False
            if (
                record.decision != "APPROVED"
                or record.commercial_use is not True
                or record.derivative_use is not True
                or expired
                or not record.evidence_reference.strip()
                or not record.reviewer.strip()
            ):
                blocked.append(record.rights_record_id)
        return ProviderRightsDecision(
            allowed=not blocked,
            code="RIGHTS_OK" if not blocked else "RIGHTS_BLOCKED",
            checked_records=len(records),
            blocked_record_ids=blocked,
        )

    async def preflight(self, context: ProviderCallContext) -> ProviderSafetyDecision:
        now = self._clock()
        rights = self.evaluate_rights(context.rights, required=context.rights_required, now=now)
        if not context.external_call:
            if not rights.allowed:
                return self._denied(context, rights.code, rights)
            return ProviderSafetyDecision(
                allowed=True,
                code="LOCAL_OR_FIXTURE_ALLOWED",
                external_call=False,
                paid=False,
                circuit_state="closed",
                rights=rights,
            )
        if self.policy.global_kill_switch_engaged:
            return self._denied(context, "GLOBAL_KILL_SWITCH_ENGAGED", rights)
        if not self.policy.external_execution_enabled:
            return self._denied(context, "EXTERNAL_EXECUTION_DISABLED", rights)
        if not self.policy.credential_gate_approved:
            return self._denied(context, "CREDENTIAL_OWNER_GATE_REQUIRED", rights)
        if not context.credential_alias:
            return self._denied(context, "CREDENTIAL_ALIAS_REQUIRED", rights)
        if not rights.allowed:
            return self._denied(context, rights.code, rights)
        if context.rights_required and not self.policy.rights_gate_approved:
            return self._denied(context, "RIGHTS_OWNER_GATE_REQUIRED", rights)
        if context.paid and not self.policy.paid_execution_enabled:
            return self._denied(context, "PAID_EXECUTION_DISABLED", rights)
        if context.paid and not self.policy.budget.active(now):
            return self._denied(context, "BUDGET_OWNER_GATE_REQUIRED", rights)
        if context.paid and context.estimated_cost_vnd is None:
            return self._denied(context, "COST_ESTIMATE_REQUIRED", rights)

        async with self._lock:
            if context.operation_key in self._active_operations or context.operation_key in self._completed_operations:
                return self._denied(context, "DUPLICATE_OPERATION_BLOCKED", rights)
            if len(self._active_operations) >= self.policy.retry.max_concurrent_calls:
                return self._denied(context, "PROVIDER_CONCURRENCY_LIMIT", rights)
            circuit = self._circuit(context)
            if circuit.state == "open":
                assert circuit.opened_at is not None
                if now < circuit.opened_at + timedelta(seconds=self.policy.circuit.cooldown_seconds):
                    return self._denied(context, "CIRCUIT_OPEN", rights, circuit.state)
                circuit.state = "half_open"
                circuit.half_open_in_flight = False
            if circuit.state == "half_open" and circuit.half_open_in_flight:
                return self._denied(context, "CIRCUIT_HALF_OPEN_BUSY", rights, circuit.state)

            estimate = context.estimated_cost_vnd or Decimal("0")
            reservation = estimate * self.policy.retry.max_attempts if context.paid else Decimal("0")
            budget = self.policy.budget
            budget_day = now.date()
            committed_today = self._committed_vnd.get(budget_day, Decimal("0"))
            reserved_today = self._reserved_vnd.get(budget_day, Decimal("0"))
            if context.paid and reservation > budget.per_operation_limit_vnd:
                return self._denied(context, "PER_OPERATION_BUDGET_EXCEEDED", rights, circuit.state)
            if context.paid and committed_today + reserved_today + reservation > budget.daily_limit_vnd:
                return self._denied(context, "DAILY_BUDGET_EXCEEDED", rights, circuit.state)

            self._active_operations.add(context.operation_key)
            self._operation_budget_day[context.operation_key] = budget_day
            self._reserved_vnd[budget_day] = reserved_today + reservation
            if circuit.state == "half_open":
                circuit.half_open_in_flight = True
            return ProviderSafetyDecision(
                allowed=True,
                code="PROVIDER_CALL_RESERVED",
                external_call=True,
                paid=context.paid,
                reserved_vnd=reservation,
                circuit_state=circuit.state,
                rights=rights,
            )

    async def execute(
        self,
        context: ProviderCallContext,
        operation: Callable[[], Awaitable[T]],
        *,
        actual_cost: Callable[[T], Decimal | None] | None = None,
    ) -> ProviderExecutionResult[T]:
        decision = await self.preflight(context)
        if not decision.allowed:
            raise ProviderSafetyBlocked(decision.code, "provider call blocked by safety policy")
        if not context.external_call:
            value = await operation()
            return ProviderExecutionResult(
                value=value,
                receipt=ProviderExecutionReceipt(
                    operation_key=context.operation_key,
                    provider_key=context.provider_key,
                    capability=context.capability,
                    status="succeeded",
                    attempts=1,
                    retries=0,
                    charged_cost_vnd=Decimal("0"),
                    circuit_state="closed",
                    external_call=False,
                    paid=False,
                    rights_allowed=decision.rights.allowed,
                ),
            )

        started_at = self._clock()
        charged = Decimal("0")
        last_error_code = "PROVIDER_EXECUTION_FAILED"
        for attempt in range(1, self.policy.retry.max_attempts + 1):
            attempt_started = self._clock()
            try:
                value = await asyncio.wait_for(
                    operation(),
                    timeout=self.policy.retry.per_request_timeout_seconds,
                )
                actual = actual_cost(value) if actual_cost else None
                charge = self._charge_for_attempt(context, actual)
                charged += charge
                await self._record_attempt(
                    context,
                    attempt=attempt,
                    status="succeeded",
                    retryable=False,
                    error_code=None,
                    actual_cost_vnd=actual,
                    charged_cost_vnd=charge,
                    started_at=attempt_started,
                )
                receipt = await self._finish(
                    context,
                    decision,
                    attempts=attempt,
                    charged=charged,
                    succeeded=True,
                )
                return ProviderExecutionResult(value=value, receipt=receipt)
            except (ProviderTransientError, TimeoutError) as exc:
                if isinstance(exc, TimeoutError):
                    exc = ProviderTimeoutError()
                last_error_code = exc.code
                status: Literal["rate_limited", "timed_out", "failed"]
                if isinstance(exc, ProviderRateLimitError):
                    status = "rate_limited"
                elif isinstance(exc, ProviderTimeoutError):
                    status = "timed_out"
                else:
                    status = "failed"
                charge = self._charge_for_attempt(context, None)
                charged += charge
                await self._record_attempt(
                    context,
                    attempt=attempt,
                    status=status,
                    retryable=True,
                    error_code=exc.code,
                    actual_cost_vnd=None,
                    charged_cost_vnd=charge,
                    started_at=attempt_started,
                )
                elapsed = (self._clock() - started_at).total_seconds()
                delay = self.policy.retry.delay_for_retry(attempt)
                if attempt >= self.policy.retry.max_attempts or elapsed + delay > self.policy.retry.max_elapsed_seconds:
                    break
                await self._sleeper(delay)
            except Exception as exc:
                last_error_code = type(exc).__name__
                charge = self._charge_for_attempt(context, None)
                charged += charge
                await self._record_attempt(
                    context,
                    attempt=attempt,
                    status="failed",
                    retryable=False,
                    error_code="PROVIDER_NON_RETRYABLE_ERROR",
                    actual_cost_vnd=None,
                    charged_cost_vnd=charge,
                    started_at=attempt_started,
                )
                break

        receipt = await self._finish(
            context,
            decision,
            attempts=max(1, len([item for item in self._attempts if item.operation_key == context.operation_key])),
            charged=charged,
            succeeded=False,
        )
        raise ProviderSafetyBlocked(last_error_code, f"provider execution failed after {receipt.attempts} attempt(s)")

    async def bounded_poll(
        self,
        context_factory: Callable[[int], ProviderCallContext],
        poll: Callable[[], Awaitable[T]],
        is_complete: Callable[[T], bool],
    ) -> list[ProviderExecutionResult[T]]:
        results: list[ProviderExecutionResult[T]] = []
        started_at = self._clock()
        for poll_number in range(1, self.policy.retry.max_poll_attempts + 1):
            result = await self.execute(context_factory(poll_number), poll)
            results.append(result)
            if is_complete(result.value):
                return results
            elapsed = (self._clock() - started_at).total_seconds()
            if elapsed + self.policy.retry.poll_interval_seconds > self.policy.retry.max_elapsed_seconds:
                break
            await self._sleeper(self.policy.retry.poll_interval_seconds)
        raise ProviderSafetyBlocked("POLL_LIMIT_EXCEEDED", "provider polling ended at the configured hard limit")

    async def snapshot(self) -> ProviderSafetySnapshot:
        async with self._lock:
            budget_day = self._clock().date()
            providers = [self._capability_snapshot(value) for value in self._provider_definitions]
            external_calls = sum(1 for item in self._attempts if self._definition_external(item.provider_key, item.capability))
            paid_calls = sum(1 for item in self._attempts if item.charged_cost_vnd > 0)
            return ProviderSafetySnapshot(
                external_execution_enabled=self.policy.external_execution_enabled,
                paid_execution_enabled=self.policy.paid_execution_enabled,
                global_kill_switch_engaged=self.policy.global_kill_switch_engaged,
                credential_gate_approved=self.policy.credential_gate_approved,
                budget_gate_approved=self.policy.budget.approved,
                rights_gate_approved=self.policy.rights_gate_approved,
                daily_limit_vnd=self.policy.budget.daily_limit_vnd,
                committed_today_vnd=self._committed_vnd.get(budget_day, Decimal("0")),
                reserved_today_vnd=self._reserved_vnd.get(budget_day, Decimal("0")),
                warning_threshold_percent=self.policy.budget.warning_threshold_percent,
                retry=self.policy.retry,
                circuit=self.policy.circuit,
                providers=providers,
                external_calls_recorded=external_calls,
                paid_calls_recorded=paid_calls,
            )

    @property
    def attempts(self) -> tuple[ProviderAttemptRecord, ...]:
        return tuple(self._attempts)

    def _denied(
        self,
        context: ProviderCallContext,
        code: str,
        rights: ProviderRightsDecision,
        circuit_state: CircuitState = "closed",
    ) -> ProviderSafetyDecision:
        return ProviderSafetyDecision(
            allowed=False,
            code=code,
            external_call=context.external_call,
            paid=context.paid,
            circuit_state=circuit_state,
            rights=rights,
        )

    def _circuit(self, context: ProviderCallContext) -> _CircuitRuntime:
        return self._circuits.setdefault((context.provider_key, context.capability), _CircuitRuntime())

    def _charge_for_attempt(
        self, context: ProviderCallContext, actual_cost_vnd: Decimal | None
    ) -> Decimal:
        if not context.paid:
            return Decimal("0")
        return actual_cost_vnd if actual_cost_vnd is not None else (context.estimated_cost_vnd or Decimal("0"))

    async def _record_attempt(
        self,
        context: ProviderCallContext,
        *,
        attempt: int,
        status: Literal["succeeded", "failed", "rate_limited", "timed_out"],
        retryable: bool,
        error_code: str | None,
        actual_cost_vnd: Decimal | None,
        charged_cost_vnd: Decimal,
        started_at: datetime,
    ) -> None:
        usage_id = "pus_" + hashlib.sha256(
            f"{context.operation_key}|{attempt}".encode("utf-8")
        ).hexdigest()[:24]
        self._attempts.append(
            ProviderAttemptRecord(
                usage_id=usage_id,
                operation_key=context.operation_key,
                provider_key=context.provider_key,
                capability=context.capability,
                attempt=attempt,
                status=status,
                estimated_cost_vnd=context.estimated_cost_vnd,
                actual_cost_vnd=actual_cost_vnd,
                charged_cost_vnd=charged_cost_vnd,
                cost_status=(
                    "actual"
                    if actual_cost_vnd is not None
                    else "estimated"
                    if context.estimated_cost_vnd is not None
                    else "pending"
                ),
                retryable=retryable,
                error_code=error_code,
                created_at=started_at,
                completed_at=self._clock(),
            )
        )

    async def _finish(
        self,
        context: ProviderCallContext,
        decision: ProviderSafetyDecision,
        *,
        attempts: int,
        charged: Decimal,
        succeeded: bool,
    ) -> ProviderExecutionReceipt:
        async with self._lock:
            estimate = context.estimated_cost_vnd or Decimal("0")
            reservation = estimate * self.policy.retry.max_attempts if context.paid else Decimal("0")
            budget_day = self._operation_budget_day.pop(context.operation_key, self._clock().date())
            self._reserved_vnd[budget_day] = max(
                Decimal("0"),
                self._reserved_vnd.get(budget_day, Decimal("0")) - reservation,
            )
            self._committed_vnd[budget_day] = (
                self._committed_vnd.get(budget_day, Decimal("0")) + charged
            )
            self._active_operations.discard(context.operation_key)
            self._completed_operations.add(context.operation_key)
            circuit = self._circuit(context)
            circuit.half_open_in_flight = False
            if succeeded:
                circuit.state = "closed"
                circuit.consecutive_failures = 0
                circuit.opened_at = None
            else:
                circuit.consecutive_failures += 1
                if circuit.state == "half_open" or circuit.consecutive_failures >= self.policy.circuit.failure_threshold:
                    circuit.state = "open"
                    circuit.opened_at = self._clock()
            alerts = self._budget_alerts(budget_day)
            return ProviderExecutionReceipt(
                operation_key=context.operation_key,
                provider_key=context.provider_key,
                capability=context.capability,
                status="succeeded" if succeeded else "failed",
                attempts=attempts,
                retries=max(0, attempts - 1),
                charged_cost_vnd=charged,
                budget_alerts=alerts,
                circuit_state=circuit.state,
                external_call=context.external_call,
                paid=context.paid,
                rights_allowed=decision.rights.allowed,
            )

    def _budget_alerts(self, budget_day: date) -> list[Literal[50, 80, 100]]:
        limit = self.policy.budget.daily_limit_vnd
        if limit <= 0:
            return []
        percent = (self._committed_vnd.get(budget_day, Decimal("0")) / limit) * 100
        new_alerts: list[Literal[50, 80, 100]] = []
        for threshold in self.policy.budget.warning_threshold_percent:
            alert_key = (budget_day, threshold)
            if percent >= threshold and alert_key not in self._alerts_emitted:
                self._alerts_emitted.add(alert_key)
                new_alerts.append(threshold)
        return new_alerts

    def _definition_external(self, provider_key: str, capability: str) -> bool:
        for definition in self._provider_definitions:
            if definition.get("provider_key") == provider_key and definition.get("capability") == capability:
                metadata = definition.get("metadata") or {}
                return bool(metadata.get("external_call") or metadata.get("contract_only"))
        return True

    def _capability_snapshot(self, definition: dict[str, Any]) -> ProviderCapabilitySafetyRead:
        metadata = definition.get("metadata") or {}
        fixture = bool(metadata.get("fixture") or metadata.get("mock"))
        contract = bool(metadata.get("contract_only"))
        adapter = str(definition.get("adapter") or "")
        config_ref = str(definition.get("config_ref") or "")
        external = bool(
            metadata.get("external_call")
            or contract
            or metadata.get("paid") is True
            or config_ref.startswith("external-secret-ref:")
            or any(marker in adapter for marker in ("Official", "OpenAI", "ComfyUI", "S3ObjectStorage"))
        )
        declared_class = metadata.get("execution_class")
        if declared_class in {"local", "fixture", "contract", "external"}:
            execution_class: ExecutionClass = declared_class
        elif fixture:
            execution_class = "fixture"
        elif contract:
            execution_class = "contract"
        elif external:
            execution_class = "external"
        else:
            execution_class = "local"
        capability = str(definition.get("capability") or "unknown")
        provider_key = str(definition.get("provider_key") or "unknown")
        rights_required = bool(
            metadata.get("rights_evidence_required")
            or capability in {"stock_media", "image_generation", "video_generation", "tts", "music"}
        )
        circuit = self._circuits.get((provider_key, capability), _CircuitRuntime())
        enabled = bool(definition.get("enabled"))
        execution_allowed = bool(
            not external
            or (
                self.policy.external_execution_enabled
                and not self.policy.global_kill_switch_engaged
            )
        )
        production_eligible = bool(
            enabled
            and not fixture
            and not contract
            and execution_allowed
            and (not rights_required or self.policy.rights_gate_approved)
        )
        return ProviderCapabilitySafetyRead(
            provider_key=provider_key,
            capability=capability,
            status=str(definition.get("status") or "not_configured"),
            enabled=enabled,
            execution_class=execution_class,
            external_execution_allowed=bool(
                external
                and self.policy.external_execution_enabled
                and not self.policy.global_kill_switch_engaged
            ),
            paid=metadata.get("paid") if isinstance(metadata.get("paid"), bool) else None,
            supports_dry_run=bool(definition.get("supports_dry_run")),
            rights_required=rights_required,
            production_eligible=production_eligible,
            circuit_state=circuit.state,
        )


def normalize_provider_definitions(
    definitions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach one secret-free safety vocabulary to every durable provider definition."""

    normalized: list[dict[str, Any]] = []
    for source in definitions:
        definition = dict(source)
        metadata = dict(definition.get("metadata") or {})
        adapter = str(definition.get("adapter") or "")
        config_ref = str(definition.get("config_ref") or "")
        fixture = bool(metadata.get("fixture") or metadata.get("mock"))
        contract = bool(metadata.get("contract_only"))
        external = bool(
            metadata.get("external_call")
            or contract
            or metadata.get("paid") is True
            or config_ref.startswith("external-secret-ref:")
            or any(
                marker in adapter
                for marker in ("Official", "OpenAI", "ComfyUI", "S3ObjectStorage")
            )
        )
        if fixture:
            execution_class: ExecutionClass = "fixture"
        elif contract:
            execution_class = "contract"
        elif external:
            execution_class = "external"
        else:
            execution_class = "local"
        capability = str(definition.get("capability") or "unknown")
        rights_required = bool(
            metadata.get("rights_evidence_required")
            or capability
            in {"internal_media", "stock_media", "image_generation", "video_generation", "tts", "music"}
        )
        metadata.update(
            {
                "safety_contract_version": 1,
                "execution_class": execution_class,
                "external_call": external,
                "requires_approval": external,
                "rights_evidence_required": rights_required,
                "cost_currency": "VND",
                "credential_reference_only": external,
            }
        )
        definition["metadata"] = metadata
        normalized.append(definition)
    return normalized


def verify_provider_artifact(
    *,
    operation_key: str,
    provider_key: str,
    capability: str,
    request_payload: Any,
    payload: bytes,
    content_type: str,
    provider_job_id: str | None = None,
    source_reference: str | None = None,
    expected_sha256: str | None = None,
    max_size_bytes: int = 250 * 1024 * 1024,
    real_provider_tested: bool = False,
    rights_record_id: str | None = None,
    now: datetime | None = None,
) -> ProviderArtifactEvidence:
    """Verify a materialized provider artifact without retaining request/body/URL values."""

    if not payload:
        raise ProviderSafetyBlocked("ARTIFACT_EMPTY", "provider artifact is empty")
    if len(payload) > max_size_bytes:
        raise ProviderSafetyBlocked("ARTIFACT_TOO_LARGE", "provider artifact exceeds the hard limit")
    normalized_content_type = content_type.split(";", 1)[0].strip().lower()
    if not _payload_matches_content_type(payload, normalized_content_type):
        raise ProviderSafetyBlocked(
            "ARTIFACT_DECODE_FAILED",
            "provider artifact does not match its declared content type",
        )
    artifact_sha256 = hashlib.sha256(payload).hexdigest()
    if expected_sha256 and not hmac.compare_digest(artifact_sha256, expected_sha256.lower()):
        raise ProviderSafetyBlocked(
            "ARTIFACT_CHECKSUM_MISMATCH",
            "provider artifact checksum does not match the expected digest",
        )
    request_bytes = json.dumps(
        request_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    token = hashlib.sha256(
        f"{operation_key}|{provider_key}|{capability}|{artifact_sha256}".encode("utf-8")
    ).hexdigest()[:24]
    return ProviderArtifactEvidence(
        evidence_id=f"pae_{token}",
        operation_key=operation_key,
        provider_key=provider_key,
        capability=capability,
        provider_job_id=provider_job_id,
        request_sha256=hashlib.sha256(request_bytes).hexdigest(),
        artifact_sha256=artifact_sha256,
        source_reference_sha256=(
            hashlib.sha256(source_reference.encode("utf-8")).hexdigest()
            if source_reference
            else None
        ),
        content_type=normalized_content_type,
        size_bytes=len(payload),
        real_provider_tested=real_provider_tested,
        rights_record_id=rights_record_id,
        captured_at=now or utc_now(),
    )


def verify_provider_artifact_storage(
    evidence: ProviderArtifactEvidence,
    *,
    checksum_sha256: str,
    size_bytes: int,
    content_type: str,
) -> ProviderArtifactEvidence:
    matches = (
        hmac.compare_digest(evidence.artifact_sha256, checksum_sha256.lower())
        and evidence.size_bytes == size_bytes
        and evidence.content_type == content_type.split(";", 1)[0].strip().lower()
    )
    if not matches:
        raise ProviderSafetyBlocked(
            "ARTIFACT_STORAGE_MISMATCH",
            "stored artifact receipt does not match verified provider bytes",
        )
    return evidence.model_copy(update={"storage_receipt_verified": True})


def _payload_matches_content_type(payload: bytes, content_type: str) -> bool:
    stripped = payload.lstrip()
    if content_type == "image/svg+xml":
        head = stripped[:1024].lower()
        tail = stripped[-1024:].lower()
        return (head.startswith(b"<svg") or b"<svg" in head) and b"</svg>" in tail
    if content_type in {
        "application/json",
        "application/vnd.npd.video-fixture+json",
        "application/vnd.npd.video-generation-fixture+json",
        "application/vnd.npd.comfyui-result+json",
    }:
        try:
            json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return True
    if content_type == "image/png":
        return payload.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type in {"image/jpeg", "image/jpg"}:
        return payload.startswith(b"\xff\xd8") and payload.endswith(b"\xff\xd9")
    if content_type == "image/webp":
        return len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
    if content_type in {"video/mp4", "audio/mp4"}:
        return len(payload) >= 12 and payload[4:8] == b"ftyp"
    if content_type in {"video/webm", "audio/webm"}:
        return payload.startswith(b"\x1aE\xdf\xa3")
    if content_type in {"audio/wav", "audio/x-wav"}:
        return len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WAVE"
    if content_type in {"audio/mpeg", "audio/mp3"}:
        return payload.startswith(b"ID3") or payload.startswith((b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"))
    return False


def provider_safety_policy_from_settings(settings: Any) -> ProviderSafetyPolicy:
    """Build the active policy without reading credential values or external approval files."""

    return ProviderSafetyPolicy(
        external_execution_enabled=bool(settings.provider_external_execution_enabled),
        paid_execution_enabled=bool(settings.provider_paid_execution_enabled),
        global_kill_switch_engaged=bool(settings.provider_global_kill_switch_engaged),
        # G-01/G-02/G-03 are intentionally not inferred from environment values. A later,
        # separately owner-gated PR must introduce verified approval-record loading.
        credential_gate_approved=False,
        rights_gate_approved=False,
        budget=ProviderBudgetPolicy(
            currency=settings.provider_budget_currency,
            approved=False,
            per_operation_limit_vnd=settings.provider_per_operation_limit_vnd,
            daily_limit_vnd=settings.provider_daily_limit_vnd,
        ),
        retry=ProviderRetryPolicy(
            max_attempts=settings.provider_retry_max_attempts,
            per_request_timeout_seconds=settings.provider_request_timeout_seconds,
            base_delay_seconds=settings.provider_retry_base_seconds,
            max_delay_seconds=settings.provider_retry_max_seconds,
            max_elapsed_seconds=settings.provider_retry_max_elapsed_seconds,
            max_poll_attempts=settings.provider_poll_max_attempts,
            poll_interval_seconds=settings.provider_poll_interval_seconds,
            max_concurrent_calls=settings.provider_max_concurrent_calls,
        ),
        circuit=ProviderCircuitPolicy(
            failure_threshold=settings.provider_circuit_failure_threshold,
            cooldown_seconds=settings.provider_circuit_cooldown_seconds,
        ),
    )
