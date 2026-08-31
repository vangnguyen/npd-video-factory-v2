from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import Field, field_validator, model_validator

from .models import StrictModel


CircuitState = Literal["closed", "open", "half_open"]
ExecutionClass = Literal["local", "fixture", "contract", "external"]
RightsDecision = Literal["APPROVED", "REJECTED", "BLOCKED"]
RightsBoolean = bool | Literal["unknown"]
ProviderErrorCategory = Literal[
    "http_provider_error",
    "transport_timeout",
    "transport_error",
    "response_parse_failure",
    "structured_output_refusal",
    "structured_output_incomplete",
    "structured_output_validation",
    "usage_receipt_missing",
    "usage_receipt_invalid",
]
ProviderTimeoutPhase = Literal[
    "service_dispatch",
    "credential_resolution",
    "frame_extraction",
    "request_build",
    "http_connection_pool",
    "http_connect",
    "http_request_write",
    "http_request_dispatch",
    "http_response_wait",
    "http_response_read",
    "response_parse",
    "controller_envelope",
    "unknown",
]
ProviderTimeoutKind = Literal[
    "connect",
    "write",
    "read",
    "pool",
    "transport",
    "controller_envelope",
    "unknown",
]
ProviderRequestDispatchState = Literal[
    "not_started",
    "not_sent",
    "possibly_sent",
    "response_headers_received",
    "unknown",
]
T = TypeVar("T")


_SECRET_EVIDENCE_PATTERN = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9_-]{8,}|bearer\s+\S+|(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+)"
)
_V3_RC_TAG_PATTERN = re.compile(r"^vf-v3-01-(rc[1-9][0-9]*)$")
RC_BOUND_OPERATION_SLOTS = (1, 2)


def derive_rc_bound_operation_key(
    *,
    rc_tag: str,
    provider_key: str,
    capability: str,
    slot: int,
) -> str:
    """Derive one immutable acceptance operation ID from its exact RC scope."""

    rc_match = _V3_RC_TAG_PATTERN.fullmatch(rc_tag)
    if rc_match is None:
        raise ValueError("operation ID requires an exact V3-01 RC tag")
    if slot not in RC_BOUND_OPERATION_SLOTS:
        raise ValueError("operation slot is outside the two-operation acceptance allowlist")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,119}", provider_key):
        raise ValueError("operation ID requires a canonical provider key")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,119}", capability):
        raise ValueError("operation ID requires a canonical capability")

    provider_capability = (
        provider_key
        if provider_key.endswith(f"-{capability}")
        else f"{provider_key}-{capability}"
    )
    return f"v3-01-{rc_match.group(1)}-{provider_capability}-call-{slot:02d}"


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
    secret_recorded: Literal[False] = False

    @model_validator(mode="after")
    def validate_approval(self) -> "ProviderRightsEvidence":
        if self.attribution_required and not self.attribution_text.strip():
            raise ValueError("approved rights with attribution require attribution text")
        return self


class ProviderAllowedOperation(StrictModel):
    operation_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,199}$")
    slot: Literal[1, 2]
    operation: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,159}$")
    asset_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    asset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ProviderExecutionGateScope(StrictModel):
    bundle_id: str = Field(pattern=r"^V3-01-GATE-[A-Za-z0-9._-]{3,120}$")
    bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rc_tag: str = Field(pattern=r"^vf-v3-01-rc[0-9]+$")
    rc_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    provider_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    model: str = Field(min_length=1, max_length=160)
    capability: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    credential_alias: str = Field(min_length=1, max_length=240)
    valid_from_utc: datetime
    expires_at_utc: datetime
    budget_day_utc: date
    per_operation_limit_vnd: Decimal = Field(gt=0)
    acceptance_window_limit_vnd: Decimal = Field(gt=0)
    input_vnd_per_million_tokens: Decimal = Field(gt=0)
    cached_input_vnd_per_million_tokens: Decimal = Field(gt=0)
    output_vnd_per_million_tokens: Decimal = Field(gt=0)
    max_frames: int = Field(ge=1, le=32)
    max_dimension_pixels: int = Field(ge=32, le=65_535)
    image_detail: Literal["low", "high", "auto"]
    input_token_ceiling: int = Field(ge=1)
    max_output_tokens: int = Field(ge=256, le=32_768)
    timeout_seconds: float = Field(gt=0, le=3600)
    max_attempts: Literal[1] = 1
    max_concurrent_calls: Literal[1] = 1
    credential_approval_id: str = Field(pattern=r"^V3-01-APP-[0-9]{3,}$")
    budget_approval_id: str = Field(pattern=r"^V3-01-APP-[0-9]{3,}$")
    rights_approval_id: str = Field(pattern=r"^V3-01-APP-[0-9]{3,}$")
    approval_record_sha256: dict[str, str]
    rights_record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    allowed_operations: tuple[ProviderAllowedOperation, ProviderAllowedOperation]
    rights_record: ProviderRightsEvidence

    @field_validator("credential_alias")
    @classmethod
    def validate_credential_alias(cls, value: str) -> str:
        if not value.startswith(("secret://", "vault://", "external://")):
            raise ValueError("verified provider gates may reference credentials only by alias")
        return value

    @field_validator("approval_record_sha256")
    @classmethod
    def validate_approval_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != {"G-01", "G-02", "G-03"}:
            raise ValueError("verified gate scope requires G-01, G-02 and G-03 approval hashes")
        if any(len(item) != 64 or any(char not in "0123456789abcdef" for char in item) for item in value.values()):
            raise ValueError("verified approval hashes must be lowercase SHA-256 values")
        return value

    @model_validator(mode="after")
    def validate_window_and_operations(self) -> "ProviderExecutionGateScope":
        start = self.valid_from_utc
        expiry = self.expires_at_utc
        if start.tzinfo is None or expiry.tzinfo is None:
            raise ValueError("verified gate window timestamps must be timezone aware")
        start = start.astimezone(timezone.utc)
        expiry = expiry.astimezone(timezone.utc)
        if expiry <= start or expiry - start > timedelta(hours=4):
            raise ValueError("verified gate window must be positive and at most four hours")
        if start.date() != expiry.date() or self.budget_day_utc != start.date():
            raise ValueError("verified gate window cannot cross the UTC budget day")
        if self.acceptance_window_limit_vnd < self.per_operation_limit_vnd * 2:
            raise ValueError("acceptance budget must cover both allowlisted operations")
        operation_keys = tuple(item.operation_key for item in self.allowed_operations)
        operation_slots = tuple(item.slot for item in self.allowed_operations)
        if operation_slots != RC_BOUND_OPERATION_SLOTS:
            raise ValueError("verified gate scope requires ordered operation slots 1 and 2")
        expected_keys = tuple(
            derive_rc_bound_operation_key(
                rc_tag=self.rc_tag,
                provider_key=self.provider_key,
                capability=self.capability,
                slot=slot,
            )
            for slot in RC_BOUND_OPERATION_SLOTS
        )
        if operation_keys != expected_keys:
            raise ValueError("verified gate scope operation IDs do not match the exact RC scope")
        for item in self.allowed_operations:
            if item.asset_id != self.rights_record.asset_id or item.asset_hash != self.rights_record.asset_hash:
                raise ValueError("every allowlisted operation must bind the approved rights asset")
        if self.rights_record.decision != "APPROVED":
            raise ValueError("verified gate scope requires an approved RightsRecord")
        return self

    def active(self, now: datetime) -> bool:
        current = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)
        return (
            self.valid_from_utc.astimezone(timezone.utc)
            <= current
            < self.expires_at_utc.astimezone(timezone.utc)
            and current.date() == self.budget_day_utc
        )

    def operation_for(self, operation_key: str) -> ProviderAllowedOperation | None:
        return next(
            (item for item in self.allowed_operations if item.operation_key == operation_key),
            None,
        )


class ProviderSafetyPolicy(StrictModel):
    version: Literal[1] = 1
    external_execution_enabled: bool = False
    paid_execution_enabled: bool = False
    global_kill_switch_engaged: bool = True
    credential_gate_approved: bool = False
    rights_gate_approved: bool = False
    verified_gate_required: bool = False
    execution_gate: ProviderExecutionGateScope | None = None
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
        if self.external_execution_enabled and self.verified_gate_required and self.execution_gate is None:
            raise ValueError("external provider execution requires a verified gate bundle")
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
    model: str | None = Field(default=None, max_length=160)
    capability: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    operation: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,159}$")
    external_call: bool
    paid: bool
    estimated_cost_vnd: Decimal | None = Field(default=None, ge=0)
    credential_alias: str | None = Field(default=None, max_length=240)
    asset_id: str | None = Field(default=None, max_length=160)
    asset_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    input_media_kind: Literal["image", "video", "audio", "document"] | None = None
    input_width: int | None = Field(default=None, ge=1)
    input_height: int | None = Field(default=None, ge=1)
    requested_frames: int | None = Field(default=None, ge=1, le=32)
    image_detail: Literal["low", "high", "auto"] | None = None
    input_token_ceiling: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=256, le=32_768)
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


class ProviderErrorEvidence(StrictModel):
    """Bounded, secret-free provider failure metadata safe for durable persistence."""

    category: ProviderErrorCategory
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_]{2,119}$")
    http_status: int | None = Field(default=None, ge=100, le=599)
    provider_error_type: str | None = Field(default=None, max_length=160)
    provider_error_code: str | None = Field(default=None, max_length=160)
    provider_error_parameter: str | None = Field(default=None, max_length=160)
    provider_error_message: str | None = Field(default=None, max_length=1000)
    provider_request_id: str | None = Field(
        default=None,
        pattern=r"^(?:[A-Za-z0-9._:-]{1,200}|sha256:[a-f0-9]{64})$",
    )
    client_request_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9._:-]{1,200}$",
    )
    response_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    timeout_phase: ProviderTimeoutPhase | None = None
    timeout_kind: ProviderTimeoutKind | None = None
    configured_timeout_seconds: float | None = Field(default=None, gt=0, le=3600)
    elapsed_ms: float | None = Field(default=None, ge=0)
    request_dispatch_state: ProviderRequestDispatchState | None = None
    exception_chain: tuple[str, ...] = Field(default=(), max_length=8)
    retryable: bool
    secret_recorded: Literal[False] = False

    @field_validator(
        "provider_error_type",
        "provider_error_code",
        "provider_error_parameter",
        "provider_error_message",
        "provider_request_id",
        "client_request_id",
    )
    @classmethod
    def reject_secret_material(cls, value: str | None) -> str | None:
        if value is not None and _SECRET_EVIDENCE_PATTERN.search(value):
            raise ValueError("provider error evidence cannot contain credential material")
        return value

    @field_validator("exception_chain")
    @classmethod
    def validate_exception_chain(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,159}", item) for item in value):
            raise ValueError("provider exception chain must contain type names only")
        return value


def _exception_type_chain(error: BaseException) -> tuple[str, ...]:
    """Return bounded exception type lineage without persisting messages or payloads."""

    chain: list[str] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and len(chain) < 8 and id(current) not in seen:
        seen.add(id(current))
        chain.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return tuple(chain)


@dataclass
class ProviderExecutionTrace:
    """Per-operation, secret-free phase trace used when a deadline cancels the adapter."""

    monotonic: Callable[[], float] = time.perf_counter
    phase: ProviderTimeoutPhase = "service_dispatch"
    request_dispatch_state: ProviderRequestDispatchState = "not_started"
    client_request_id: str | None = None
    provider_request_id: str | None = None
    _started_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._started_at = self.monotonic()

    def begin(self) -> None:
        self._started_at = self.monotonic()
        self.phase = "service_dispatch"
        self.request_dispatch_state = "not_started"
        self.client_request_id = None
        self.provider_request_id = None

    def mark(
        self,
        phase: ProviderTimeoutPhase,
        *,
        dispatch_state: ProviderRequestDispatchState | None = None,
        client_request_id: str | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        self.phase = phase
        if dispatch_state is not None:
            self.request_dispatch_state = dispatch_state
        if client_request_id is not None:
            self.client_request_id = client_request_id
        if provider_request_id is not None:
            self.provider_request_id = provider_request_id

    def elapsed_ms(self) -> float:
        return round(max(0.0, self.monotonic() - self._started_at) * 1000, 3)

    def timeout_evidence(
        self,
        *,
        code: str,
        timeout_kind: ProviderTimeoutKind,
        configured_timeout_seconds: float,
        error: BaseException,
        retryable: bool,
        provider_error_message: str,
    ) -> ProviderErrorEvidence:
        return ProviderErrorEvidence(
            category="transport_timeout",
            code=code,
            provider_error_type=type(error).__name__,
            provider_error_message=provider_error_message,
            provider_request_id=self.provider_request_id,
            client_request_id=self.client_request_id,
            timeout_phase=self.phase,
            timeout_kind=timeout_kind,
            configured_timeout_seconds=configured_timeout_seconds,
            elapsed_ms=self.elapsed_ms(),
            request_dispatch_state=self.request_dispatch_state,
            exception_chain=_exception_type_chain(error),
            retryable=retryable,
            secret_recorded=False,
        )


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
    error_evidence: ProviderErrorEvidence | None = None
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
    state_backend: Literal["memory", "postgresql"] = "memory"
    durable_operations_recorded: int = Field(default=0, ge=0)
    active_operations: int = Field(default=0, ge=0)
    recovered_operations: int = Field(default=0, ge=0)
    attempts_recorded: int = Field(default=0, ge=0)
    stale_active_operations: int = Field(default=0, ge=0)
    oldest_active_age_seconds: float | None = Field(default=None, ge=0)
    operation_retention_days: int | None = Field(default=None, ge=1)


@dataclass(frozen=True)
class ProviderExecutionResult(Generic[T]):
    value: T
    receipt: ProviderExecutionReceipt


class ProviderSafetyBlocked(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        error_evidence: ProviderErrorEvidence | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.error_evidence = error_evidence


class ProviderTransientError(RuntimeError):
    def __init__(
        self,
        code: str = "PROVIDER_TRANSIENT_ERROR",
        *,
        error_evidence: ProviderErrorEvidence | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.error_evidence = error_evidence


class ProviderRateLimitError(ProviderTransientError):
    def __init__(self, *, error_evidence: ProviderErrorEvidence | None = None):
        super().__init__("PROVIDER_RATE_LIMITED", error_evidence=error_evidence)


class ProviderTimeoutError(ProviderTransientError):
    def __init__(self, *, error_evidence: ProviderErrorEvidence | None = None):
        super().__init__("PROVIDER_TIMEOUT", error_evidence=error_evidence)


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
        monotonic: Callable[[], float] = time.perf_counter,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.policy = policy
        self._provider_definitions = [dict(value) for value in provider_definitions]
        self._clock = clock
        self._monotonic = monotonic
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
        rights_records: Sequence[ProviderRightsEvidence] = context.rights
        if context.external_call and self.policy.verified_gate_required:
            scope = self.policy.execution_gate
            if scope is None:
                rights = self.evaluate_rights(
                    rights_records,
                    required=context.rights_required,
                    now=now,
                )
                return self._denied(context, "VERIFIED_GATE_BUNDLE_REQUIRED", rights)
            rights_records = (scope.rights_record,)
            rights = self.evaluate_rights(
                rights_records,
                required=context.rights_required,
                now=now,
            )
            scope_denial = self._verified_scope_denial(scope, context=context, now=now)
            if scope_denial is not None:
                return self._denied(context, scope_denial, rights)
        else:
            rights = self.evaluate_rights(
                rights_records,
                required=context.rights_required,
                now=now,
            )
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

    @staticmethod
    def _verified_scope_denial(
        scope: ProviderExecutionGateScope,
        *,
        context: ProviderCallContext,
        now: datetime,
    ) -> str | None:
        current = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)
        if current < scope.valid_from_utc.astimezone(timezone.utc):
            return "VERIFIED_GATE_NOT_ACTIVE"
        if current >= scope.expires_at_utc.astimezone(timezone.utc):
            return "VERIFIED_GATE_EXPIRED"
        if current.date() != scope.budget_day_utc:
            return "VERIFIED_GATE_BUDGET_DAY_MISMATCH"
        if context.provider_key != scope.provider_key:
            return "PROVIDER_NOT_AUTHORIZED"
        if context.model != scope.model:
            return "MODEL_NOT_AUTHORIZED"
        if context.capability != scope.capability:
            return "CAPABILITY_NOT_AUTHORIZED"
        if context.credential_alias != scope.credential_alias:
            return "CREDENTIAL_ALIAS_NOT_AUTHORIZED"
        operation = scope.operation_for(context.operation_key)
        if operation is None:
            return "OPERATION_NOT_ALLOWLISTED"
        if context.operation != operation.operation:
            return "OPERATION_SCOPE_MISMATCH"
        if context.asset_id != operation.asset_id or context.asset_hash != operation.asset_hash:
            return "RIGHTS_ASSET_BINDING_MISMATCH"
        if context.input_media_kind != "image":
            return "INPUT_MEDIA_KIND_NOT_AUTHORIZED"
        if context.input_width is None or context.input_height is None:
            return "INPUT_DIMENSIONS_REQUIRED"
        if max(context.input_width, context.input_height) > scope.max_dimension_pixels:
            return "INPUT_DIMENSION_LIMIT_EXCEEDED"
        if context.requested_frames != scope.max_frames:
            return "FRAME_LIMIT_MISMATCH"
        if context.image_detail != scope.image_detail:
            return "IMAGE_DETAIL_MISMATCH"
        if context.input_token_ceiling != scope.input_token_ceiling:
            return "INPUT_TOKEN_CEILING_MISMATCH"
        if context.max_output_tokens != scope.max_output_tokens:
            return "OUTPUT_TOKEN_LIMIT_MISMATCH"
        if context.estimated_cost_vnd is None:
            return "COST_ESTIMATE_REQUIRED"
        if context.estimated_cost_vnd != scope.per_operation_limit_vnd:
            return "COST_RESERVATION_MISMATCH"
        return None

    async def execute(
        self,
        context: ProviderCallContext,
        operation: Callable[[], Awaitable[T]],
        *,
        actual_cost: Callable[[T], Decimal | None] | None = None,
        timeout_evidence_factory: Callable[
            [float, BaseException], ProviderErrorEvidence
        ]
        | None = None,
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
        last_error_evidence: ProviderErrorEvidence | None = None
        last_exception: Exception | None = None
        attempts_made = 0
        for attempt in range(1, self.policy.retry.max_attempts + 1):
            attempts_made = attempt
            attempt_started = self._clock()
            attempt_started_monotonic = self._monotonic()
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
                    error_evidence=None,
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
                    try:
                        evidence = (
                            timeout_evidence_factory(
                                self.policy.retry.per_request_timeout_seconds,
                                exc,
                            )
                            if timeout_evidence_factory is not None
                            else ProviderErrorEvidence(
                                category="transport_timeout",
                                code="PROVIDER_TIMEOUT",
                                provider_error_type=type(exc).__name__,
                                provider_error_message=(
                                    "Provider operation exceeded the controller deadline"
                                ),
                                timeout_phase="controller_envelope",
                                timeout_kind="controller_envelope",
                                configured_timeout_seconds=(
                                    self.policy.retry.per_request_timeout_seconds
                                ),
                                elapsed_ms=round(
                                    max(0.0, self._monotonic() - attempt_started_monotonic)
                                    * 1000,
                                    3,
                                ),
                                request_dispatch_state="unknown",
                                exception_chain=_exception_type_chain(exc),
                                retryable=True,
                                secret_recorded=False,
                            )
                        )
                    except Exception:
                        evidence = ProviderErrorEvidence(
                            category="transport_timeout",
                            code="PROVIDER_TIMEOUT",
                            provider_error_type=type(exc).__name__,
                            provider_error_message=(
                                "Provider operation exceeded the controller deadline; "
                                "phase evidence fallback was used"
                            ),
                            timeout_phase="controller_envelope",
                            timeout_kind="controller_envelope",
                            configured_timeout_seconds=(
                                self.policy.retry.per_request_timeout_seconds
                            ),
                            elapsed_ms=round(
                                max(0.0, self._monotonic() - attempt_started_monotonic)
                                * 1000,
                                3,
                            ),
                            request_dispatch_state="unknown",
                            exception_chain=_exception_type_chain(exc),
                            retryable=True,
                            secret_recorded=False,
                        )
                    exc = ProviderTimeoutError(error_evidence=evidence)
                last_error_code = exc.code
                last_exception = exc
                status: Literal["rate_limited", "timed_out", "failed"]
                if isinstance(exc, ProviderRateLimitError):
                    status = "rate_limited"
                elif isinstance(exc, ProviderTimeoutError):
                    status = "timed_out"
                else:
                    status = "failed"
                elapsed = (self._clock() - started_at).total_seconds()
                delay = self.policy.retry.delay_for_retry(attempt)
                retry_authorized = not (
                    attempt >= self.policy.retry.max_attempts
                    or elapsed + delay > self.policy.retry.max_elapsed_seconds
                )
                error_evidence = exc.error_evidence
                if (
                    error_evidence is not None
                    and error_evidence.retryable != retry_authorized
                ):
                    error_evidence = error_evidence.model_copy(
                        update={"retryable": retry_authorized}
                    )
                last_error_evidence = error_evidence
                charge = self._charge_for_attempt(context, None)
                charged += charge
                await self._record_attempt(
                    context,
                    attempt=attempt,
                    status=status,
                    retryable=retry_authorized,
                    error_code=exc.code,
                    error_evidence=error_evidence,
                    actual_cost_vnd=None,
                    charged_cost_vnd=charge,
                    started_at=attempt_started,
                )
                if not retry_authorized:
                    break
                await self._sleeper(delay)
            except Exception as exc:
                evidence = getattr(exc, "error_evidence", None)
                if not isinstance(evidence, ProviderErrorEvidence):
                    evidence = None
                last_error_evidence = evidence
                last_error_code = evidence.code if evidence is not None else type(exc).__name__
                last_exception = exc
                charge = self._charge_for_attempt(context, None)
                charged += charge
                await self._record_attempt(
                    context,
                    attempt=attempt,
                    status="failed",
                    retryable=False,
                    error_code=last_error_code,
                    error_evidence=evidence,
                    actual_cost_vnd=None,
                    charged_cost_vnd=charge,
                    started_at=attempt_started,
                )
                break

        receipt = await self._finish(
            context,
            decision,
            attempts=max(1, attempts_made),
            charged=charged,
            succeeded=False,
        )
        blocked = ProviderSafetyBlocked(
            last_error_code,
            f"provider execution failed after {receipt.attempts} attempt(s)",
            error_evidence=last_error_evidence,
        )
        if last_exception is not None:
            raise blocked from last_exception
        raise blocked

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

    def _build_attempt_record(
        self,
        context: ProviderCallContext,
        *,
        attempt: int,
        status: Literal["succeeded", "failed", "rate_limited", "timed_out"],
        retryable: bool,
        error_code: str | None,
        error_evidence: ProviderErrorEvidence | None,
        actual_cost_vnd: Decimal | None,
        charged_cost_vnd: Decimal,
        started_at: datetime,
    ) -> ProviderAttemptRecord:
        usage_id = "pus_" + hashlib.sha256(
            f"{context.operation_key}|{attempt}".encode("utf-8")
        ).hexdigest()[:24]
        return ProviderAttemptRecord(
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
            error_evidence=error_evidence,
            created_at=started_at,
            completed_at=self._clock(),
        )

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
        error_evidence: ProviderErrorEvidence | None = None,
    ) -> None:
        self._attempts.append(
            self._build_attempt_record(
                context,
                attempt=attempt,
                status=status,
                retryable=retryable,
                error_code=error_code,
                error_evidence=error_evidence,
                actual_cost_vnd=actual_cost_vnd,
                charged_cost_vnd=charged_cost_vnd,
                started_at=started_at,
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
    """Build the active policy without reading credential values.

    A verified gate bundle contains approval metadata and hashes only. It is read from a protected
    file, hash-pinned by deployment configuration, and never contains provider credential values.
    """

    execution_gate: ProviderExecutionGateScope | None = None
    if settings.provider_verified_gate_bundle_enabled:
        from .provider_gate_loader import load_verified_provider_gate_bundle

        execution_gate = load_verified_provider_gate_bundle(
            settings.provider_verified_gate_bundle_file,
            expected_bundle_sha256=settings.provider_verified_gate_bundle_sha256,
            expected_rc_commit=settings.provider_gate_expected_rc_commit,
            expected_rc_tag=settings.provider_gate_expected_rc_tag,
        )
    gate_loaded = execution_gate is not None

    return ProviderSafetyPolicy(
        external_execution_enabled=bool(settings.provider_external_execution_enabled),
        paid_execution_enabled=bool(settings.provider_paid_execution_enabled),
        global_kill_switch_engaged=bool(settings.provider_global_kill_switch_engaged),
        credential_gate_approved=gate_loaded,
        rights_gate_approved=gate_loaded,
        verified_gate_required=True,
        execution_gate=execution_gate,
        budget=ProviderBudgetPolicy(
            currency=settings.provider_budget_currency,
            approved=gate_loaded,
            owner_approval_id=(execution_gate.budget_approval_id if execution_gate else None),
            per_operation_limit_vnd=(
                execution_gate.per_operation_limit_vnd
                if execution_gate
                else settings.provider_per_operation_limit_vnd
            ),
            daily_limit_vnd=(
                execution_gate.acceptance_window_limit_vnd
                if execution_gate
                else settings.provider_daily_limit_vnd
            ),
            expires_at=(execution_gate.expires_at_utc if execution_gate else None),
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
