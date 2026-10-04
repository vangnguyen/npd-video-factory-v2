"""Hash-pinned, per-lane public admission. Not an ASR gate or a key store.

Admission-only bundles cannot authorize execute(). Resolver references contain
only identity; a protected backend must be separately admitted/injected by the
host. Loading/prepare never calls that backend or the durable reservation path.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_serializer, model_validator
from .models import StrictModel


LANES = {
    "content_generation": ("openai-storyboard-content", "secret://openai/video-factory-content-generation", "storyboard-proposal"),
    "tts": ("openai-tts", "secret://openai/video-factory-vietnamese-tts", "narration-unit"),
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class AdmissionInput(StrictModel):
    operation_key: str = Field(pattern=r"^mvp1-(content_generation|tts)-[a-f0-9]{64}$")
    operation: Literal["storyboard-proposal", "narration-unit"]
    asset_id: str = Field(pattern=r"^pver_[A-Za-z0-9_-]{1,150}$")
    asset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    narration: str | None = Field(default=None, min_length=1, max_length=4096)
    rights_record: dict[str, Any]
    rights_record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    # Optional exact UTF-8 prompt asset mode. Pin the entire request document too,
    # so a raw-text hash never permits altered instructions/facts/protected terms.
    prompt_document_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_serializer(mode="wrap")
    def preserve_legacy_representation(self, handler):
        data = handler(self)
        if self.prompt_document_sha256 is None:
            data.pop("prompt_document_sha256", None)
        return data


class Mvp1AdmissionScope(StrictModel):
    schema_name: Literal["mvp1-provider-admission-v1"] = "mvp1-provider-admission-v1"
    version: Literal[1] = 1
    capability: Literal["content_generation", "tts"]
    provider_key: str
    credential_alias: str
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    workspace_id: str = Field(min_length=3, max_length=80)
    project_id: str = Field(min_length=3, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    profile: dict[str, Any]
    profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner_approval_id: str = Field(pattern=r"^V3-01-APP-[0-9]{3,}$")
    decision: Literal["APPROVED"]
    approved_by: Literal["Owner (GitHub: vangnguyen)"]
    purpose: Literal["bounded content generation proposal only", "bounded Vietnamese narration synthesis only"]
    execution_authorized: bool = False
    resolver_reference: Literal["protected-provider-resolver-v1"] = "protected-provider-resolver-v1"
    valid_from_utc: datetime
    expires_at_utc: datetime
    budget_day_utc: date
    per_operation_limit_vnd: Decimal = Field(gt=0, allow_inf_nan=False)
    acceptance_window_limit_vnd: Decimal = Field(gt=0, allow_inf_nan=False)
    tts_vnd_per_character: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    provider_http_timeout_seconds: float = Field(default=90, gt=0, le=90)
    controller_hard_timeout_seconds: float = Field(default=120, gt=0, le=120)
    max_attempts: Literal[1] = 1
    max_concurrent_calls: Literal[1] = 1
    automatic_retry: Literal[False] = False
    model_fallback: Literal[False] = False
    allowed_operations: tuple[AdmissionInput, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def bindings(self):
        from .provider_safety import ProviderRightsEvidence
        from .storyboard_content_provider import ContentProviderProfile
        from .tts_evidence import ProductionTTSProfile
        provider, alias, operation = LANES[self.capability]
        if (self.provider_key, self.credential_alias) != (provider, alias):
            raise ValueError("MVP1_PROVIDER_CREDENTIAL_BINDING_MISMATCH")
        selected = (ContentProviderProfile if self.capability == "content_generation" else ProductionTTSProfile).model_validate(self.profile)
        if selected.provider_key != provider or selected.model != self.model or selected.sha256 != self.profile_sha256:
            raise ValueError("MVP1_PROFILE_BINDING_MISMATCH")
        expected_purpose = "bounded content generation proposal only" if self.capability == "content_generation" else "bounded Vietnamese narration synthesis only"
        if self.purpose != expected_purpose:
            raise ValueError("MVP1_PURPOSE_MISMATCH")
        if self.capability == "content_generation":
            if self.tts_vnd_per_character is not None or selected.estimated_cost_vnd != self.per_operation_limit_vnd:
                raise ValueError("MVP1_CONTENT_BUDGET_PROFILE_MISMATCH")
        elif self.tts_vnd_per_character is None or selected.alignment_capability != "none":
            raise ValueError("MVP1_TTS_RATE_OR_ALIGNMENT_UNSUPPORTED")
        start, expiry = self.valid_from_utc, self.expires_at_utc
        if start.tzinfo is None or expiry.tzinfo is None:
            raise ValueError("MVP1_WINDOW_NOT_AWARE")
        start, expiry = start.astimezone(timezone.utc), expiry.astimezone(timezone.utc)
        if not timedelta(0) < expiry-start <= timedelta(hours=4) or start.date() != expiry.date() or self.budget_day_utc != start.date():
            raise ValueError("MVP1_WINDOW_BUDGET_DAY_MISMATCH")
        if self.acceptance_window_limit_vnd < self.per_operation_limit_vnd * len(self.allowed_operations):
            raise ValueError("MVP1_WINDOW_BUDGET_INSUFFICIENT")
        if len({i.operation_key for i in self.allowed_operations}) != len(self.allowed_operations) or len({(i.asset_id, i.asset_hash) for i in self.allowed_operations}) != len(self.allowed_operations):
            raise ValueError("MVP1_DUPLICATE_INPUT_OPERATION")
        for item in self.allowed_operations:
            if item.prompt_document_sha256 is not None and self.capability != "content_generation":
                raise ValueError("MVP1_PROMPT_ASSET_CONTENT_ONLY")
            expected_key = "mvp1-" + self.capability + "-" + digest({"source_commit": self.source_commit, "profile_sha256": self.profile_sha256, "workspace_id": self.workspace_id, "project_id": self.project_id, "asset_id": item.asset_id, "asset_hash": item.asset_hash})
            if item.operation_key != expected_key or item.operation != operation:
                raise ValueError("MVP1_OPERATION_IDENTITY_MISMATCH")
            rights = ProviderRightsEvidence.model_validate(item.rights_record)
            if digest(rights.model_dump(mode="json")) != item.rights_record_sha256 or (rights.asset_id, rights.asset_hash) != (item.asset_id, item.asset_hash):
                raise ValueError("MVP1_RIGHTS_HASH_INPUT_MISMATCH")
            if rights.decision != "APPROVED" or rights.commercial_use is not True or rights.derivative_use is not True or rights.provider != provider or rights.license_name != self.purpose or rights.social_platform_use:
                raise ValueError("MVP1_RIGHTS_PURPOSE_NOT_APPROVED")
            if self.capability == "tts":
                from .tts_provider_execution import narration_input_sha256
                if item.narration is None or item.asset_hash != narration_input_sha256(selected, item.narration) or Decimal(len(item.narration)) * self.tts_vnd_per_character > self.per_operation_limit_vnd:
                    raise ValueError("MVP1_TTS_INPUT_RATE_MISMATCH")
            elif item.narration is not None:
                raise ValueError("MVP1_CONTENT_CANNOT_CONTAIN_TTS_UNIT")
        return self

    @property
    def acceptance_lineage_id(self): return None  # NOT RC28 acceptance authority.
    @property
    def asr_prompt_profile(self): return None
    @property
    def budget_approval_id(self): return self.owner_approval_id
    @property
    def input_vnd_per_million_tokens(self): return self.profile.get("input_vnd_per_million_tokens") and Decimal(self.profile["input_vnd_per_million_tokens"])
    @property
    def output_vnd_per_million_tokens(self): return self.profile.get("output_vnd_per_million_tokens") and Decimal(self.profile["output_vnd_per_million_tokens"])
    @property
    def max_output_tokens(self): return self.profile.get("max_output_tokens")
    def operation_for(self, key): return next((i for i in self.allowed_operations if i.operation_key == key), None)
    def rights_for_asset(self, asset_id, asset_hash=None):
        from .provider_safety import ProviderRightsEvidence
        item = next((i for i in self.allowed_operations if i.asset_id == asset_id and i.asset_hash == asset_hash), None)
        return ProviderRightsEvidence.model_validate(item.rights_record) if item else None

    def denial_for(self, context, now, *, require_execution=True):
        # Revalidation rejects model_copy/model_construct bypasses too.
        validated = type(self).model_validate(self.model_dump())
        if require_execution and not validated.execution_authorized: return "MVP1_EXECUTION_AUTHORITY_REQUIRED"
        if now.tzinfo is None: return "MVP1_TIME_NOT_VERIFIED"
        if not validated.valid_from_utc <= now < validated.expires_at_utc: return "MVP1_WINDOW_INACTIVE"
        item = validated.operation_for(context.operation_key)
        if item is None: return "OPERATION_NOT_ALLOWLISTED"
        if (context.provider_key, context.model, context.capability, context.credential_alias, context.workspace_id, context.project_id) != (validated.provider_key, validated.model, validated.capability, validated.credential_alias, validated.workspace_id, validated.project_id): return "MVP1_SCOPE_IDENTITY_MISMATCH"
        if context.acceptance_lineage_id is not None or not context.job_id or not context.rights_required or not context.external_call or not context.paid: return "MVP1_CONTEXT_CLASS_MISMATCH"
        if (context.asset_id, context.asset_hash, context.operation, context.input_media_kind, context.requested_language) != (item.asset_id, item.asset_hash, item.operation, "document", "vi"): return "MVP1_INPUT_VERSION_MISMATCH"
        if context.estimated_cost_vnd != validated.per_operation_limit_vnd: return "COST_RESERVATION_MISMATCH"
        if self.capability == "content_generation" and context.max_output_tokens != self.max_output_tokens: return "OUTPUT_TOKEN_LIMIT_MISMATCH"
        rights = validated.rights_for_asset(item.asset_id, item.asset_hash)
        if rights.expiry is not None and (rights.expiry.tzinfo is None or now >= rights.expiry): return "RIGHTS_BLOCKED"
        return None


def load_mvp1_admission(path: Path, *, expected_sha256: str, expected_source_commit: str, capability: str):
    # Public metadata only. No source locator/token/credential file in schema.
    if len(expected_sha256) != 64 or len(expected_source_commit) != 40:
        raise ValueError("MVP1_ADMISSION_PIN_REQUIRED")
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("MVP1_ADMISSION_PATH_UNSAFE")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 1_000_000:
        raise ValueError("MVP1_ADMISSION_ROOT_CUSTODY_REQUIRED")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino): raise ValueError("MVP1_ADMISSION_FILE_CHANGED")
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid != 0 or opened.st_mode & 0o022 or opened.st_size > 1_000_000:
            raise ValueError("MVP1_ADMISSION_ROOT_CUSTODY_REQUIRED")
        with os.fdopen(fd, "rb", closefd=False) as handle: raw = handle.read(1_000_001)
    finally: os.close(fd)
    if hashlib.sha256(raw).hexdigest() != expected_sha256: raise ValueError("MVP1_ADMISSION_RAW_HASH_MISMATCH")
    scope = Mvp1AdmissionScope.model_validate_json(raw)
    if scope.source_commit != expected_source_commit or scope.capability != capability:
        raise ValueError("MVP1_ADMISSION_SOURCE_LANE_MISMATCH")
    return scope


class ProtectedResolverReference:
    """DI reference, not a plaintext key or ambient env fallback.

    Backend transport is deliberately not selected by workflow/prompt/config.
    A future protected host injects it after separate runtime qualification.
    This source task never installs or invokes a runtime backend.
    """
    def __init__(self, scope: Mvp1AdmissionScope, *, transport=None, raw_file_sha256=None):
        self.scope, self.transport, self._claimed = scope, transport, set()
        self.raw_file_sha256 = raw_file_sha256
    @property
    def backend_admitted(self): return self.transport is not None
    def resolve_for_context(self, context):
        denial = self.scope.denial_for(context, datetime.now(timezone.utc))
        if denial or self.transport is None: raise RuntimeError("MVP1_PROTECTED_RESOLVER_NOT_ADMITTED")
        if context.operation_key in self._claimed: raise RuntimeError("MVP1_RESOLVER_HANDOFF_ALREADY_CLAIMED")
        self._claimed.add(context.operation_key)  # Ambiguity never permits a local retry.
        # The protected backend MUST atomically enforce cross-process one-shot;
        # this local guard is not a substitute for runtime spent-marker custody.
        return self.transport({"schema": "mvp1-protected-resolver-reference-v1", "provider_key": self.scope.provider_key,
            "credential_alias": self.scope.credential_alias, "scope_sha256": digest(self.scope.model_dump(mode="json")),
            "scope_raw_file_sha256": self.raw_file_sha256,
            "operation_key": context.operation_key, "workspace_id": context.workspace_id,
            "project_id": context.project_id, "job_id": context.job_id, "input_sha256": context.asset_hash,
            "profile_sha256": self.scope.profile_sha256, "max_resolutions": 1})


def create_mvp1_lane_bindings(settings, *, capability, repository, resolver_transport=None):
    from .provider_safety import ProviderSafetyPolicy, ProviderBudgetPolicy, ProviderRetryPolicy
    from .provider_safety_durable import DurableProviderSafetyController
    if capability not in LANES:
        raise ValueError("MVP1_UNKNOWN_CAPABILITY")
    prefix = "content" if capability == "content_generation" else "tts"
    if not getattr(settings, prefix + "_admission_enabled", False):
        return {"controller": None, "credential_resolver": None, "approved_units": {}}
    try:
        scope = load_mvp1_admission(getattr(settings, prefix + "_admission_file"),
            expected_sha256=getattr(settings, prefix + "_admission_sha256"),
            expected_source_commit=settings.mvp1_provider_source_commit, capability=capability)
    except (ValueError, OSError):
        # A missing/invalid public file blocks this lane, not the shared worker.
        # Never expose validation input, paths or exception contents in logs/UI.
        return {"controller": None, "credential_resolver": None, "approved_units": {},
            "admission_error": "MVP1_LANE_ADMISSION_BLOCKED"}
    live = scope.execution_authorized and settings.provider_external_execution_enabled and settings.provider_paid_execution_enabled
    policy = ProviderSafetyPolicy(execution_gate=scope, verified_gate_required=True,
        external_execution_enabled=live, paid_execution_enabled=live,
        global_kill_switch_engaged=settings.provider_global_kill_switch_engaged,
        credential_gate_approved=True, rights_gate_approved=True,
        budget=ProviderBudgetPolicy(approved=True, owner_approval_id=scope.owner_approval_id,
            per_operation_limit_vnd=scope.per_operation_limit_vnd, daily_limit_vnd=scope.acceptance_window_limit_vnd,
            expires_at=scope.expires_at_utc),
        retry=ProviderRetryPolicy(max_attempts=1, max_concurrent_calls=1,
            provider_http_timeout_seconds=scope.provider_http_timeout_seconds,
            controller_hard_timeout_seconds=scope.controller_hard_timeout_seconds))
    controller = DurableProviderSafetyController(policy, repository=repository)
    reference = ProtectedResolverReference(scope, transport=resolver_transport,
        raw_file_sha256=getattr(settings, prefix + "_admission_sha256"))
    units = {}
    if capability == "tts":
        from .provider_safety import ProviderCallContext
        for item in scope.allowed_operations:
            units[item.asset_hash] = ProviderCallContext(operation_key=item.operation_key,
                workspace_id=scope.workspace_id, project_id=scope.project_id,
                job_id="job_tts_" + item.asset_hash[:24], provider_key=scope.provider_key, model=scope.model,
                capability="tts", operation=item.operation, external_call=True, paid=True,
                credential_alias=scope.credential_alias, asset_id=item.asset_id, asset_hash=item.asset_hash,
                input_media_kind="document", requested_language="vi", rights_required=True,
                estimated_cost_vnd=scope.per_operation_limit_vnd)
    return {"controller": controller, "credential_resolver": reference, "approved_units": units}
