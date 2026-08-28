from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .models import StrictModel
from .provider_safety import (
    ProviderAllowedOperation,
    ProviderExecutionGateScope,
    ProviderRightsEvidence,
)


G02_A_OPERATION_KEYS = (
    "v3-01-g03a-openai-vision-call-01",
    "v3-01-g03a-openai-vision-call-02",
)


class ProviderGateBundleError(ValueError):
    """Raised when an owner-gate bundle cannot be trusted."""


def canonical_sha256(value: StrictModel | dict[str, object]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, StrictModel) else value
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def execution_scope_sha256(
    *,
    rc_tag: str,
    rc_commit: str,
    provider_key: str,
    model: str,
    capability: str,
    credential_alias: str,
    valid_from_utc: datetime,
    expires_at_utc: datetime,
    budget: "ProviderGateBudgetEnvelope",
    rights_record_sha256: str,
    allowed_operations: tuple[ProviderAllowedOperation, ProviderAllowedOperation],
) -> str:
    """Hash every mutable field that an owner must approve for one live window."""

    return canonical_sha256(
        {
            "rc_tag": rc_tag,
            "rc_commit": rc_commit,
            "provider_key": provider_key,
            "model": model,
            "capability": capability,
            "credential_alias": credential_alias,
            "valid_from_utc": valid_from_utc.astimezone(timezone.utc).isoformat(),
            "expires_at_utc": expires_at_utc.astimezone(timezone.utc).isoformat(),
            "budget": budget.model_dump(mode="json"),
            "rights_record_sha256": rights_record_sha256,
            "allowed_operations": [
                operation.model_dump(mode="json") for operation in allowed_operations
            ],
        }
    )


class ProviderApprovalRecord(StrictModel):
    approval_id: str = Field(pattern=r"^V3-01-APP-[0-9]{3,}$")
    gate_id: Literal["G-01", "G-02", "G-03"]
    decision: Literal["APPROVED", "REJECTED", "REVOKED"]
    scope: str = Field(min_length=1)
    artifact_or_commit_hashes: list[str] = Field(min_length=1)
    target_account_or_environment: str
    limits: list[str]
    approved_by: str = Field(min_length=1)
    approved_at_utc: datetime
    expires_at_utc: datetime | None = None
    notes: str

    @model_validator(mode="after")
    def validate_timestamp(self) -> "ProviderApprovalRecord":
        if self.approved_at_utc.tzinfo is None:
            raise ValueError("approval timestamp must be timezone aware")
        if self.expires_at_utc is not None and self.expires_at_utc.tzinfo is None:
            raise ValueError("approval expiry must be timezone aware")
        return self


class HashedApprovalRecord(StrictModel):
    record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    record: ProviderApprovalRecord

    @model_validator(mode="after")
    def verify_hash(self) -> "HashedApprovalRecord":
        if not _constant_time_hash_equal(self.record_sha256, canonical_sha256(self.record)):
            raise ValueError("approval record SHA-256 mismatch")
        return self


class HashedRightsRecord(StrictModel):
    record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    record: ProviderRightsEvidence

    @model_validator(mode="after")
    def verify_hash(self) -> "HashedRightsRecord":
        if not _constant_time_hash_equal(self.record_sha256, canonical_sha256(self.record)):
            raise ValueError("RightsRecord SHA-256 mismatch")
        return self


class ProviderGateBudgetEnvelope(StrictModel):
    currency: Literal["VND"] = "VND"
    per_operation_limit_vnd: Decimal = Field(gt=0)
    acceptance_window_limit_vnd: Decimal = Field(gt=0)
    input_vnd_per_million_tokens: Decimal = Field(gt=0)
    cached_input_vnd_per_million_tokens: Decimal = Field(gt=0)
    output_vnd_per_million_tokens: Decimal = Field(gt=0)
    budget_day_utc: date
    max_frames: int = Field(ge=1, le=32)
    max_dimension_pixels: int = Field(ge=32, le=65_535)
    image_detail: Literal["low", "high", "auto"]
    input_token_ceiling: int = Field(ge=1)
    max_output_tokens: int = Field(ge=256, le=32_768)
    timeout_seconds: float = Field(gt=0, le=3600)
    max_attempts: Literal[1] = 1
    max_concurrent_calls: Literal[1] = 1

    @model_validator(mode="after")
    def enforce_g02_a_envelope(self) -> "ProviderGateBudgetEnvelope":
        expected = {
            "per_operation_limit_vnd": Decimal("500"),
            "acceptance_window_limit_vnd": Decimal("1250"),
            "input_vnd_per_million_tokens": Decimal("6565"),
            "cached_input_vnd_per_million_tokens": Decimal("656.5"),
            "output_vnd_per_million_tokens": Decimal("52520"),
            "max_frames": 1,
            "max_dimension_pixels": 2048,
            "image_detail": "high",
            "input_token_ceiling": 16_384,
            "max_output_tokens": 4_096,
            "timeout_seconds": 60.0,
            "max_attempts": 1,
            "max_concurrent_calls": 1,
        }
        actual = {
            "per_operation_limit_vnd": self.per_operation_limit_vnd,
            "acceptance_window_limit_vnd": self.acceptance_window_limit_vnd,
            "input_vnd_per_million_tokens": self.input_vnd_per_million_tokens,
            "cached_input_vnd_per_million_tokens": self.cached_input_vnd_per_million_tokens,
            "output_vnd_per_million_tokens": self.output_vnd_per_million_tokens,
            "max_frames": self.max_frames,
            "max_dimension_pixels": self.max_dimension_pixels,
            "image_detail": self.image_detail,
            "input_token_ceiling": self.input_token_ceiling,
            "max_output_tokens": self.max_output_tokens,
            "timeout_seconds": self.timeout_seconds,
            "max_attempts": self.max_attempts,
            "max_concurrent_calls": self.max_concurrent_calls,
        }
        if actual != expected:
            raise ValueError("gate bundle exceeds or changes the owner-approved G-02-A envelope")
        return self


class ProviderGateBundle(StrictModel):
    version: Literal[1] = 1
    bundle_id: str = Field(pattern=r"^V3-01-GATE-[A-Za-z0-9._-]{3,120}$")
    rc_tag: str = Field(pattern=r"^vf-v3-01-rc[0-9]+$")
    rc_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    provider_key: Literal["openai-vision"]
    model: Literal["gpt-5-mini"]
    capability: Literal["vision"]
    credential_alias: Literal["secret://openai/codex-video"]
    valid_from_utc: datetime
    expires_at_utc: datetime
    budget: ProviderGateBudgetEnvelope
    credential_approval: HashedApprovalRecord
    budget_approval: HashedApprovalRecord
    rights_approval: HashedApprovalRecord
    rights_record: HashedRightsRecord
    allowed_operations: tuple[ProviderAllowedOperation, ProviderAllowedOperation]

    @field_validator("valid_from_utc", "expires_at_utc")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("gate bundle timestamps must be timezone aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_approval_scope(self) -> "ProviderGateBundle":
        approvals = {
            "G-01": self.credential_approval.record,
            "G-02": self.budget_approval.record,
            "G-03": self.rights_approval.record,
        }
        if any(record.gate_id != gate_id for gate_id, record in approvals.items()):
            raise ValueError("approval record is bound to the wrong owner gate")
        if any(record.decision != "APPROVED" for record in approvals.values()):
            raise ValueError("all runtime owner gates must be explicitly approved")
        if len({record.approval_id for record in approvals.values()}) != 3:
            raise ValueError("G-01, G-02 and G-03 require distinct approval record IDs")
        if any(self.rc_commit not in record.artifact_or_commit_hashes for record in approvals.values()):
            raise ValueError("every owner approval must bind the exact RC commit")
        for record in approvals.values():
            if record.approved_at_utc.astimezone(timezone.utc) > self.valid_from_utc:
                raise ValueError("owner approval was recorded after the requested gate activation")
            if record.expires_at_utc is not None and (
                record.expires_at_utc.astimezone(timezone.utc) < self.expires_at_utc
            ):
                raise ValueError("owner approval expires before the requested gate window")

        provider_scope_hash = canonical_sha256(
            {
                "provider_key": self.provider_key,
                "model": self.model,
                "capability": self.capability,
                "credential_alias": self.credential_alias,
            }
        )
        if provider_scope_hash not in self.credential_approval.record.artifact_or_commit_hashes:
            raise ValueError("G-01 approval does not bind the exact provider capability scope")
        if canonical_sha256(self.budget) not in self.budget_approval.record.artifact_or_commit_hashes:
            raise ValueError("G-02 approval does not bind the exact VND budget envelope")
        if self.rights_record.record_sha256 not in (
            self.rights_approval.record.artifact_or_commit_hashes
        ):
            raise ValueError("G-03 approval does not bind the exact RightsRecord hash")

        if self.expires_at_utc <= self.valid_from_utc:
            raise ValueError("gate expiry must follow activation")
        if self.expires_at_utc - self.valid_from_utc > timedelta(hours=4):
            raise ValueError("gate bundle window cannot exceed four hours")
        if self.valid_from_utc.date() != self.expires_at_utc.date():
            raise ValueError("gate bundle window cannot cross the UTC budget day")
        if self.budget.budget_day_utc != self.valid_from_utc.date():
            raise ValueError("gate budget day must match the activation day")

        rights = self.rights_record.record
        if rights.decision != "APPROVED" or rights.secret_recorded is not False:
            raise ValueError("G-03 requires an approved secret-free RightsRecord")
        if rights.commercial_use is not True or rights.derivative_use is not True:
            raise ValueError("G-03 asset must allow commercial and derivative use")
        if rights.expiry is not None and rights.expiry.astimezone(timezone.utc) <= self.expires_at_utc:
            raise ValueError("RightsRecord expires before the gate window closes")

        keys = [item.operation_key for item in self.allowed_operations]
        if tuple(keys) != G02_A_OPERATION_KEYS:
            raise ValueError("the two predeclared G-02-A operation IDs must match exactly")
        for operation in self.allowed_operations:
            if operation.operation != "vision_analysis":
                raise ValueError("G-02-A allows only the Vision analysis operation")
            if operation.asset_id != rights.asset_id or operation.asset_hash != rights.asset_hash:
                raise ValueError("allowlisted operation does not bind the approved G-03 asset")

        scope_hash = execution_scope_sha256(
            rc_tag=self.rc_tag,
            rc_commit=self.rc_commit,
            provider_key=self.provider_key,
            model=self.model,
            capability=self.capability,
            credential_alias=self.credential_alias,
            valid_from_utc=self.valid_from_utc,
            expires_at_utc=self.expires_at_utc,
            budget=self.budget,
            rights_record_sha256=self.rights_record.record_sha256,
            allowed_operations=self.allowed_operations,
        )
        if any(
            scope_hash not in record.artifact_or_commit_hashes
            for record in approvals.values()
        ):
            raise ValueError("every owner approval must bind the exact execution scope hash")
        return self


def load_verified_provider_gate_bundle(
    path: Path,
    *,
    expected_bundle_sha256: str,
    expected_rc_commit: str,
    expected_rc_tag: str,
) -> ProviderExecutionGateScope:
    if not expected_bundle_sha256 or len(expected_bundle_sha256) != 64:
        raise ProviderGateBundleError("a lowercase expected gate-bundle SHA-256 is required")
    if not path.is_file():
        raise ProviderGateBundleError("verified provider gate bundle is missing")
    raw = path.read_bytes()
    actual_bundle_sha256 = hashlib.sha256(raw).hexdigest()
    if not _constant_time_hash_equal(expected_bundle_sha256, actual_bundle_sha256):
        raise ProviderGateBundleError("verified provider gate bundle SHA-256 mismatch")
    try:
        payload = json.loads(raw.decode("utf-8"))
        bundle = ProviderGateBundle.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProviderGateBundleError("verified provider gate bundle is invalid") from exc
    if bundle.rc_commit != expected_rc_commit or bundle.rc_tag != expected_rc_tag:
        raise ProviderGateBundleError("verified provider gate bundle does not match the exact RC")

    approval_hashes = {
        "G-01": bundle.credential_approval.record_sha256,
        "G-02": bundle.budget_approval.record_sha256,
        "G-03": bundle.rights_approval.record_sha256,
    }
    return ProviderExecutionGateScope(
        bundle_id=bundle.bundle_id,
        bundle_sha256=actual_bundle_sha256,
        rc_tag=bundle.rc_tag,
        rc_commit=bundle.rc_commit,
        provider_key=bundle.provider_key,
        model=bundle.model,
        capability=bundle.capability,
        credential_alias=bundle.credential_alias,
        valid_from_utc=bundle.valid_from_utc,
        expires_at_utc=bundle.expires_at_utc,
        budget_day_utc=bundle.budget.budget_day_utc,
        per_operation_limit_vnd=bundle.budget.per_operation_limit_vnd,
        acceptance_window_limit_vnd=bundle.budget.acceptance_window_limit_vnd,
        input_vnd_per_million_tokens=bundle.budget.input_vnd_per_million_tokens,
        cached_input_vnd_per_million_tokens=(
            bundle.budget.cached_input_vnd_per_million_tokens
        ),
        output_vnd_per_million_tokens=bundle.budget.output_vnd_per_million_tokens,
        max_frames=bundle.budget.max_frames,
        max_dimension_pixels=bundle.budget.max_dimension_pixels,
        image_detail=bundle.budget.image_detail,
        input_token_ceiling=bundle.budget.input_token_ceiling,
        max_output_tokens=bundle.budget.max_output_tokens,
        timeout_seconds=bundle.budget.timeout_seconds,
        max_attempts=bundle.budget.max_attempts,
        max_concurrent_calls=bundle.budget.max_concurrent_calls,
        credential_approval_id=bundle.credential_approval.record.approval_id,
        budget_approval_id=bundle.budget_approval.record.approval_id,
        rights_approval_id=bundle.rights_approval.record.approval_id,
        approval_record_sha256=approval_hashes,
        rights_record_sha256=bundle.rights_record.record_sha256,
        allowed_operations=bundle.allowed_operations,
        rights_record=bundle.rights_record.record,
    )


def _constant_time_hash_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("ascii"), right.encode("ascii"))
