"""One-operation V3-01 ASR dispatch path; no authority is embedded here.

This module is executable only from a newly locked RC containing this source,
with a separately approved bundle/authority and canonical PostgreSQL custody.
The historical generic controller is deliberately not used to execute: it
cannot distinguish a failure before HTTP send from one after dispatch begins.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import wave
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .asr_prompt_profile import prompt_profile_sha256
from .auto_edit_models import MediaMetadata
from .auto_edit_providers import ProviderTranscript
from .provider_ci_provenance import (
    provider_ci_provenance_sha256,
    validate_provider_acceptance_ci_provenance,
)
from .provider_gate_loader import (
    asr_execution_scope_sha256,
    canonical_sha256,
    load_verified_provider_gate_bundle,
)
from .provider_runtime_bootstrap import (
    BootstrapBlocked,
    BootstrapLedgerBinding,
    _git,
    bootstrap_custody,
    ledger_url,
    load_binding,
)
from .provider_safety import (
    ProviderCallContext,
    ProviderErrorEvidence,
    ProviderExecutionGateScope,
    ProviderSafetyController,
    ProviderSafetyPolicy,
    ProviderTimeoutError,
    utc_now,
)
from .provider_safety_repository import ProviderSafetyRepository
from .openai_transcription_provider import OpenAITranscriptionProvider


MODULE_PATH = "apps/api/app/provider_single_dispatch.py"
_SECRET_PATTERN = re.compile(r"(?i)(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+|OPENAI_API_KEY\s*[:=])")


class SingleDispatchBlocked(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SingleDispatchPaths:
    rc_source: Path
    binding: Path
    binding_sha256: str
    bundle: Path
    authority: Path
    authority_sha256: str
    provenance: Path
    provenance_sha256: str
    operation_manifest: Path
    asset: Path
    reference_transcript: Path
    rights_record: Path
    evidence_directory: Path


@dataclass(frozen=True)
class SingleDispatchOutcome:
    state: str
    code: str
    dispatch_started: bool
    operation_consumed: bool | None
    charged_vnd: Decimal | None
    actual_cost_vnd: Decimal | None
    evidence_sha256: str | None
    transitions: tuple[str, ...]


@dataclass(frozen=True)
class SingleDispatchQualification:
    """Read-only attestation, never authority to cross the provider boundary."""

    code: str
    binding_valid: bool
    authority_valid: bool
    bundle_valid: bool
    ledger_valid: bool
    window_policy_valid: bool
    budget_policy_valid: bool
    kill_switch_valid: bool
    duplicate_check_valid: bool
    operation_unconsumed: bool
    provider_receipt_absent: bool
    reservation_absent: bool
    credential_read_performed: bool
    provider_call_performed: bool
    ready_for_execution_preflight: bool
    ready_for_provider_dispatch: bool
    evidence: dict[str, object]
    evidence_manifest_sha256: str


@dataclass(frozen=True)
class _ValidatedDispatch:
    binding: BootstrapLedgerBinding
    scope: ProviderExecutionGateScope
    context: ProviderCallContext
    metadata: MediaMetadata
    authority: dict[str, object]
    operation_manifest_sha256: str


@dataclass
class _ScopedKillSwitch:
    operation_key: str
    engaged: bool = True
    transition_count: int = 0

    def allow_one_dispatch(self, operation_key: str) -> None:
        if not self.engaged or self.transition_count != 0 or operation_key != self.operation_key:
            raise SingleDispatchBlocked("KILL_SWITCH_DISPATCH_DENIED")
        self.engaged = False
        self.transition_count = 1

    def reengage(self) -> None:
        self.engaged = True


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _write_once(path: Path, payload: dict[str, object]) -> str:
    raw = _canonical_bytes(payload)
    if _SECRET_PATTERN.search(raw.decode("utf-8")):
        raise SingleDispatchBlocked("EVIDENCE_SECRET_SCAN_FAILED")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        raise SingleDispatchBlocked("EVIDENCE_PATH_ALREADY_EXISTS")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(raw).hexdigest()


@dataclass
class _EvidenceRecorder:
    root: Path
    operation_key: str
    events: list[dict[str, object]] = field(default_factory=list)
    armed: bool = False

    @property
    def folder(self) -> Path:
        return self.root / hashlib.sha256(self.operation_key.encode("utf-8")).hexdigest()

    def arm(self, *, reserved_vnd: Decimal, ledger_before: str) -> None:
        if self.armed:
            raise SingleDispatchBlocked("EVIDENCE_ALREADY_ARMED")
        if self.root.is_symlink() or self.folder.is_symlink():
            raise SingleDispatchBlocked("EVIDENCE_PATH_SYMLINK_BLOCKED")
        event = {
            "state": "EVIDENCE_ARMED", "reserved_vnd": str(reserved_vnd),
            "ledger_before": ledger_before, "kill_switch_before": "ENGAGED",
            "duplicate_before": "NONE",
        }
        _write_once(self.folder / "armed.json", {
            "operation_key": self.operation_key,
            "provider_calls": 0,
            "events": [*self.events, event],
        })
        self.events.append(event)
        self.armed = True

    def mark_dispatch(self, *, request_sha256: str, client_request_id: str) -> None:
        if not self.armed:
            raise SingleDispatchBlocked("EVIDENCE_NOT_ARMED")
        if self.root.is_symlink() or self.folder.is_symlink():
            raise SingleDispatchBlocked("EVIDENCE_PATH_SYMLINK_BLOCKED")
        event = {
            "state": "DISPATCH_INTENT", "request_sha256": request_sha256,
            "client_request_id": client_request_id,
        }
        _write_once(self.folder / "dispatch-intent.json", {
            "operation_key": self.operation_key,
            "dispatch_state": "NOT_YET_SENT", "events": [*self.events, event],
        })
        self.events.append(event)

    def seal(self, payload: dict[str, object]) -> str:
        if self.root.is_symlink() or self.folder.is_symlink():
            raise SingleDispatchBlocked("EVIDENCE_PATH_SYMLINK_BLOCKED")
        event = {"state": "EVIDENCE_SEALED"}
        _write_once(self.folder / "terminal.json", {
            "operation_key": self.operation_key,
            "events": [*self.events, event],
            **payload,
            "secret_recorded": False,
        })
        self.events.append(event)
        allowed = {"armed.json", "dispatch-intent.json", "terminal.json"}
        names = {path.name for path in self.folder.iterdir()}
        if not names.issubset(allowed) or "terminal.json" not in names:
            raise SingleDispatchBlocked("EVIDENCE_ARTIFACT_SET_INVALID")
        files = {
            name: _sha256_file(self.folder / name)
            for name in sorted(names)
        }
        return _write_once(self.folder / "manifest.json", {
            "version": 1,
            "operation_key": self.operation_key,
            "algorithm": "SHA-256",
            "files": files,
        })


def _exact(value: object, expected: object, code: str) -> None:
    if value != expected:
        raise SingleDispatchBlocked(code)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_authority(path: Path, expected_sha256: str) -> dict[str, object]:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256) or _sha256_file(path) != expected_sha256:
        raise SingleDispatchBlocked("AUTHORITY_RECEIPT_HASH_MISMATCH")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise SingleDispatchBlocked("AUTHORITY_RECEIPT_INVALID")
    return payload


def _verify_authority(
    authority: dict[str, object],
    binding: BootstrapLedgerBinding,
    scope: ProviderExecutionGateScope,
    *,
    provenance_sha256: str,
    operation_manifest_sha256: str,
) -> None:
    values = {
        "decision": "APPROVED", "status": "GRANTED_NOT_CONSUMED",
        "main_provenance": "PASS",
        "rc_tag": binding.rc_tag, "rc_commit": binding.rc_commit,
        "governance_main_commit": binding.governance_main_commit,
        "executable_tree_sha256": binding.executable_tree_sha256,
        "dual_ci_provenance_sha256": provenance_sha256,
        "operation_key": binding.operation_key,
        "acceptance_lineage_id": binding.acceptance_lineage_id,
        "execution_scope_sha256": binding.execution_scope_sha256,
        "loaded_runtime_scope_sha256": binding.scope_sha256,
        "gate_bundle_sha256": binding.bundle_sha256,
        "operation_manifest_sha256": operation_manifest_sha256,
        "asset_sha256": binding.asset_sha256,
        "reference_transcript_sha256": binding.reference_transcript_sha256,
        "rights_record_sha256": binding.rights_record_sha256,
        "asr_prompt_profile_sha256": binding.w1_profile_sha256,
        "prompt_sha256": binding.prompt_sha256,
        "provider_key": "openai-transcription", "model": "whisper-1",
        "capability": "asr", "language": "vi", "slot": 1,
        "operation_1_consumed": False, "operation_2_authorized": False,
        "budget_reserved_vnd": "0", "bundle_mounted": False,
        "dispatch_requires_separate_execution_task": True,
    }
    for key, expected in values.items():
        _exact(authority.get(key), expected, "AUTHORITY_" + key.upper() + "_MISMATCH")
    ledger = authority.get("ledger")
    if not isinstance(ledger, dict):
        raise SingleDispatchBlocked("AUTHORITY_LEDGER_MISSING")
    _exact(ledger.get("identity"), binding.database_name, "AUTHORITY_LEDGER_MISMATCH")
    _exact(ledger.get("system_identifier"), binding.system_identifier, "AUTHORITY_LEDGER_INSTANCE_MISMATCH")
    _exact(ledger.get("database_oid"), binding.database_oid, "AUTHORITY_LEDGER_OID_MISMATCH")
    approvals = authority.get("approval_records")
    if not isinstance(approvals, dict) or set(approvals) != {"G-01", "G-02", "G-03"}:
        raise SingleDispatchBlocked("AUTHORITY_APPROVAL_SET_MISMATCH")
    for gate, expected_hash in scope.approval_record_sha256.items():
        item = approvals[gate]
        if not isinstance(item, dict):
            raise SingleDispatchBlocked("AUTHORITY_APPROVAL_INVALID")
        _exact(item.get("record_sha256"), expected_hash, "AUTHORITY_APPROVAL_HASH_MISMATCH")
    limits = authority.get("limits")
    if not isinstance(limits, dict):
        raise SingleDispatchBlocked("AUTHORITY_LIMITS_MISSING")
    expected_limits = {
        "per_operation_limit_vnd": scope.per_operation_limit_vnd,
        "acceptance_window_limit_vnd": scope.acceptance_window_limit_vnd,
    }
    for key, expected in expected_limits.items():
        _exact(Decimal(str(limits.get(key))), expected, "AUTHORITY_BUDGET_MISMATCH")
    for key, expected in {
        "max_attempts": 1, "max_concurrent_calls": 1,
        "automatic_retry": False, "model_fallback": False,
        "provider_http_timeout_seconds": scope.provider_http_timeout_seconds,
        "controller_hard_timeout_seconds": scope.controller_hard_timeout_seconds,
    }.items():
        _exact(limits.get(key), expected, "AUTHORITY_LIMITS_MISMATCH")
    _exact(authority.get("valid_from_utc"), scope.valid_from_utc.isoformat().replace("+00:00", "Z"), "AUTHORITY_WINDOW_MISMATCH")
    _exact(authority.get("expires_at_utc"), scope.expires_at_utc.isoformat().replace("+00:00", "Z"), "AUTHORITY_WINDOW_MISMATCH")


def _wav_metadata(path: Path) -> MediaMetadata:
    with wave.open(str(path), "rb") as source:
        duration = source.getnframes() / source.getframerate()
        channels = source.getnchannels()
        rate = source.getframerate()
    return MediaMetadata(
        media_kind="audio", detected_content_type="audio/wav", format_name="wav",
        duration_seconds=duration, audio_channels=channels, audio_sample_rate=rate,
    )


def _verify_runtime_policy(policy: ProviderSafetyPolicy, scope: ProviderExecutionGateScope) -> None:
    """Never synthesize enabled external/paid flags from an approval receipt."""
    if not all((
        policy.external_execution_enabled,
        policy.paid_execution_enabled,
        policy.global_kill_switch_engaged,
        policy.credential_gate_approved,
        policy.rights_gate_approved,
        policy.verified_gate_required,
        policy.budget.approved,
    )):
        raise SingleDispatchBlocked("RUNTIME_SAFETY_POLICY_NOT_AUTHORIZED")
    if policy.execution_gate != scope or (
        policy.budget.owner_approval_id != scope.budget_approval_id
        or policy.budget.per_operation_limit_vnd != scope.per_operation_limit_vnd
        or policy.budget.daily_limit_vnd != scope.acceptance_window_limit_vnd
        or policy.budget.expires_at != scope.expires_at_utc
        or policy.retry.max_attempts != 1
        or policy.retry.max_concurrent_calls != 1
        or policy.retry.provider_http_timeout_seconds != scope.provider_http_timeout_seconds
        or policy.retry.controller_hard_timeout_seconds != scope.controller_hard_timeout_seconds
    ):
        raise SingleDispatchBlocked("RUNTIME_SAFETY_POLICY_SCOPE_MISMATCH")


def _context(binding: BootstrapLedgerBinding, scope: ProviderExecutionGateScope, metadata: MediaMetadata, asset_bytes: int) -> ProviderCallContext:
    operation = scope.operation_for(binding.operation_key)
    if operation is None or operation.slot != 1:
        raise SingleDispatchBlocked("OPERATION_1_NOT_ALLOWLISTED")
    return ProviderCallContext(
        operation_key=binding.operation_key, acceptance_lineage_id=binding.acceptance_lineage_id,
        workspace_id="wsp_" + binding.acceptance_lineage_id[-32:],
        provider_key=scope.provider_key, model=scope.model, capability=scope.capability,
        operation=operation.operation, external_call=True, paid=True,
        estimated_cost_vnd=scope.per_operation_limit_vnd,
        credential_alias=scope.credential_alias,
        asset_id=operation.asset_id, asset_hash=binding.asset_sha256,
        input_media_kind="audio", input_file_bytes=asset_bytes,
        input_duration_seconds=metadata.duration_seconds,
        requested_language=scope.requested_language,
        response_format=scope.response_format,
        timestamp_granularities=scope.timestamp_granularities,
        asr_prompt_profile=scope.asr_prompt_profile,
        rights_required=True,
        rights=list(scope.all_rights_records()),
    )


def _validate_non_secret_bindings(
    paths: SingleDispatchPaths,
    *,
    runtime_policy: ProviderSafetyPolicy,
    now: datetime,
    require_active_window: bool,
) -> _ValidatedDispatch:
    """One source of truth for both qualification and live pre-secret checks."""
    binding = load_binding(paths.binding, paths.binding_sha256)
    if binding.slot != 1:
        raise SingleDispatchBlocked("OPERATION_2_NOT_AUTHORIZED")
    if paths.evidence_directory.resolve().is_relative_to(paths.rc_source.resolve()):
        raise SingleDispatchBlocked("EVIDENCE_MUST_BE_OUTSIDE_RC_SOURCE")
    if paths.authority_sha256 != binding.authority_receipt_sha256:
        raise SingleDispatchBlocked("AUTHORITY_BOOTSTRAP_HASH_MISMATCH")
    # Source check is first, before custody access, reservation or adapter use.
    from .provider_runtime_bootstrap import verify_bound_source
    verify_bound_source(paths.rc_source, binding)
    remote_main = _git(paths.rc_source, "ls-remote", "--heads", "origin", "main").split()
    if len(remote_main) != 2 or remote_main[0] != binding.governance_main_commit:
        raise SingleDispatchBlocked("GOVERNANCE_MAIN_DRIFT")
    expected_blob = _git(paths.rc_source, "rev-parse", binding.rc_commit + ":" + MODULE_PATH)
    actual_blob = _git(paths.rc_source, "hash-object", "--path", MODULE_PATH, str(Path(__file__).resolve()))
    if expected_blob != actual_blob or Path(__file__).resolve() != (paths.rc_source / MODULE_PATH).resolve():
        raise SingleDispatchBlocked("DISPATCH_IMPLEMENTATION_NOT_IN_BOUND_RC")
    try:
        scope = load_verified_provider_gate_bundle(
            paths.bundle, expected_bundle_sha256=binding.bundle_sha256,
            expected_rc_commit=binding.rc_commit, expected_rc_tag=binding.rc_tag,
            expected_acceptance_lineage_id=binding.acceptance_lineage_id,
        )
    except Exception:
        raise SingleDispatchBlocked("BUNDLE_VALIDATION_FAILED") from None
    if require_active_window:
        if not scope.active(now):
            raise SingleDispatchBlocked("BLOCKED_OUTSIDE_WINDOW")
    elif now >= scope.expires_at_utc:
        raise SingleDispatchBlocked("WINDOW_EXPIRED")
    if scope.execution_scope_sha256 != binding.execution_scope_sha256 or asr_execution_scope_sha256(scope) != binding.execution_scope_sha256:
        raise SingleDispatchBlocked("EXECUTION_SCOPE_MISMATCH")
    if canonical_sha256(scope) != binding.scope_sha256:
        raise SingleDispatchBlocked("LOADED_SCOPE_MISMATCH")
    _verify_runtime_policy(runtime_policy, scope)
    if scope.asr_prompt_profile_sha256 != binding.w1_profile_sha256 or prompt_profile_sha256(scope.asr_prompt_profile) != binding.w1_profile_sha256:
        raise SingleDispatchBlocked("PROMPT_PROFILE_MISMATCH")
    if scope.asr_prompt_profile is None or scope.asr_prompt_profile.prompt_sha256 != binding.prompt_sha256:
        raise SingleDispatchBlocked("PROMPT_MISMATCH")
    if _sha256_file(paths.asset) != binding.asset_sha256 or _sha256_file(paths.reference_transcript) != binding.reference_transcript_sha256:
        raise SingleDispatchBlocked("ASR_INPUT_HASH_MISMATCH")
    rights = json.loads(paths.rights_record.read_bytes())
    if canonical_sha256(rights) != binding.rights_record_sha256:
        raise SingleDispatchBlocked("RIGHTS_RECORD_HASH_MISMATCH")
    provenance_raw = json.loads(paths.provenance.read_bytes())
    authority = _load_authority(paths.authority, paths.authority_sha256)
    try:
        provenance = validate_provider_acceptance_ci_provenance(
            provenance_raw,
            expected_executable_rc_commit=binding.rc_commit,
            expected_governance_main_commit=binding.governance_main_commit,
            expected_executable_rc_ci_run_id=authority["executable_rc_ci_run_id"],
            expected_governance_main_ci_run_id=authority["governance_main_ci_run_id"],
        )
    except Exception:
        raise SingleDispatchBlocked("DUAL_CI_PROVENANCE_INVALID") from None
    if provider_ci_provenance_sha256(provenance) != paths.provenance_sha256:
        raise SingleDispatchBlocked("DUAL_CI_PROVENANCE_MISMATCH")
    operation_manifest = json.loads(paths.operation_manifest.read_bytes())
    if not isinstance(operation_manifest, dict):
        raise SingleDispatchBlocked("OPERATION_MANIFEST_INVALID")
    for key, expected in {
        "operation_id": binding.operation_key,
        "ledger_operation_key": binding.operation_key,
        "ledger_identity": binding.database_name,
        "acceptance_lineage_id": binding.acceptance_lineage_id,
        "execution_scope_sha256": binding.execution_scope_sha256,
        "prompt_sha256": binding.prompt_sha256,
        "w1_profile_sha256": binding.w1_profile_sha256,
        "slot": 1,
    }.items():
        _exact(operation_manifest.get(key), expected, "OPERATION_MANIFEST_BINDING_MISMATCH")
    operation_manifest_sha256 = canonical_sha256(operation_manifest)
    _verify_authority(
        authority, binding, scope, provenance_sha256=paths.provenance_sha256,
        operation_manifest_sha256=operation_manifest_sha256,
    )
    metadata = _wav_metadata(paths.asset)
    asset_bytes = paths.asset.stat().st_size
    if asset_bytes != authority.get("asset_bytes") or abs(float(metadata.duration_seconds or 0) - float(authority.get("asset_duration_seconds", -1))) > 0.001:
        raise SingleDispatchBlocked("ASR_MEDIA_METADATA_MISMATCH")
    context = _context(binding, scope, metadata, asset_bytes)
    return _ValidatedDispatch(
        binding=binding, scope=scope, context=context, metadata=metadata,
        authority=authority, operation_manifest_sha256=operation_manifest_sha256,
    )


def _verify_pre_dispatch_contract(
    *, scope: ProviderExecutionGateScope, policy: ProviderSafetyPolicy,
    context: ProviderCallContext, now: datetime, require_active_window: bool,
) -> None:
    """Shared safety preconditions; qualification evaluates a future window at its start."""
    _verify_runtime_policy(policy, scope)
    if require_active_window:
        if not scope.active(now) or not policy.budget.active(now):
            raise SingleDispatchBlocked("BLOCKED_OUTSIDE_WINDOW")
        evaluation_time = now
    else:
        if now >= scope.expires_at_utc:
            raise SingleDispatchBlocked("WINDOW_EXPIRED")
        evaluation_time = max(now, scope.valid_from_utc)
        if not scope.active(evaluation_time) or not policy.budget.active(evaluation_time):
            raise SingleDispatchBlocked("WINDOW_POLICY_INVALID")
    if not policy.global_kill_switch_engaged:
        raise SingleDispatchBlocked("KILL_SWITCH_NOT_ENGAGED")
    if policy.retry.max_attempts != 1 or policy.retry.max_concurrent_calls != 1:
        raise SingleDispatchBlocked("SINGLE_CALL_POLICY_MISMATCH")
    controller = ProviderSafetyController(policy, clock=lambda: evaluation_time)
    prompt_denial = controller._prompt_profile_denial(context)
    scope_denial = controller._verified_scope_denial(scope, context=context, now=evaluation_time)
    rights_records = controller._verified_rights_records(scope, context=context)
    rights = controller.evaluate_rights(rights_records, required=True, now=evaluation_time)
    if prompt_denial or scope_denial or not rights.allowed:
        raise SingleDispatchBlocked(prompt_denial or scope_denial or rights.code)


def _verify_virgin_custody(custody: dict[str, object]) -> None:
    """Require an exact virgin namespace, never infer absence from a missing row alone."""
    counts = custody.get("counts")
    bootstrap_write = custody.get("ledger_bootstrap_write")
    try:
        reserved_vnd = Decimal(str(custody.get("reserved_vnd")))
    except Exception:
        raise SingleDispatchBlocked("LEDGER_RESERVED_AMOUNT_INVALID") from None
    if (
        custody.get("result") != "CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED"
        or custody.get("operation_state") != "VIRGIN_NOT_REGISTERED / NOT_CONSUMED"
        or custody.get("control_present") is not True
        or type(custody.get("active_operations")) is not int
        or custody.get("active_operations") != 0
        or type(custody.get("exact_operation_attempts")) is not int
        or custody.get("exact_operation_attempts") != 0
        or not reserved_vnd.is_finite() or reserved_vnd != 0
        or not isinstance(counts, dict)
        or set(counts) != {"operations", "attempts", "budget_days", "circuits", "budget_alerts"}
        or any(type(value) is not int or value != 0 for value in counts.values())
        or custody.get("provider_request_receipt_mapping") != "NO_OPERATION_OR_ATTEMPT_IN_THIS_BOUND_NAMESPACE"
        or custody.get("active_reservation") != "NONE_IN_THIS_BOUND_NAMESPACE"
        or not isinstance(bootstrap_write, dict)
        or bootstrap_write.get("ensure_state_invoked") is not False
    ):
        raise SingleDispatchBlocked("CHECK_ONLY_LEDGER_NOT_VIRGIN")


def _qualification_result(
    *, code: str, now: datetime, validated: _ValidatedDispatch | None = None,
    custody: dict[str, object] | None = None,
) -> SingleDispatchQualification:
    passed = code == "READY_FOR_EXECUTION_PREFLIGHT"
    checked: dict[str, object] = {}
    if validated is not None:
        binding, scope, authority = validated.binding, validated.scope, validated.authority
        checked = {
            "rc_tag": binding.rc_tag, "rc_commit": binding.rc_commit,
            "executable_tree_sha256": binding.executable_tree_sha256,
            "governance_main_commit": binding.governance_main_commit,
            "ledger_identity": binding.database_name,
            "operation_key": binding.operation_key,
            "executable_rc_ci_run_id": authority["executable_rc_ci_run_id"],
            "governance_main_ci_run_id": authority["governance_main_ci_run_id"],
            "dual_ci_provenance_sha256": authority["dual_ci_provenance_sha256"],
            "authority_receipt_sha256": binding.authority_receipt_sha256,
            "approval_record_sha256": scope.approval_record_sha256,
            "bundle_sha256": binding.bundle_sha256,
            "execution_scope_sha256": binding.execution_scope_sha256,
            "loaded_scope_sha256": binding.scope_sha256,
            "operation_manifest_sha256": validated.operation_manifest_sha256,
            "w1_profile_sha256": binding.w1_profile_sha256,
            "prompt_sha256": binding.prompt_sha256,
            "asset_sha256": binding.asset_sha256,
            "reference_transcript_sha256": binding.reference_transcript_sha256,
            "rights_record_sha256": binding.rights_record_sha256,
            "provider_key": scope.provider_key, "model": scope.model,
            "capability": scope.capability,
            "valid_from_utc": scope.valid_from_utc.isoformat(),
            "expires_at_utc": scope.expires_at_utc.isoformat(),
            "per_operation_limit_vnd": str(scope.per_operation_limit_vnd),
            "window_limit_vnd": str(scope.acceptance_window_limit_vnd),
            "max_attempts": 1, "max_concurrent_calls": 1,
            "retry": 0, "fallback": 0,
        }
    evidence: dict[str, object] = {
        "version": 1, "mode": "CHECK_ONLY", "code": code,
        "checked_at_utc": now.isoformat(), "checked_bindings": checked,
        "ledger_readback": None if custody is None else {
            "operation_state": custody.get("operation_state"),
            "exact_operation_attempts": custody.get("exact_operation_attempts"),
            "active_operations": custody.get("active_operations"),
            "reserved_vnd": custody.get("reserved_vnd"),
            "counts": custody.get("counts"),
        },
        "credential_read_performed": False, "reservation_invoked": False,
        "provider_adapter_invoked": False, "provider_call_performed": False,
        "dispatch_marker_written": False, "bundle_mounted": False,
        "operation_consumed_by_check_only": False,
        "kill_switch_transitioned": False,
        "ready_for_execution_preflight": passed,
        "ready_for_provider_dispatch": False,
    }
    return SingleDispatchQualification(
        code=code, binding_valid=passed, authority_valid=passed,
        bundle_valid=passed, ledger_valid=passed,
        window_policy_valid=passed, budget_policy_valid=passed,
        kill_switch_valid=passed, duplicate_check_valid=passed,
        operation_unconsumed=passed, provider_receipt_absent=passed,
        reservation_absent=passed, credential_read_performed=False,
        provider_call_performed=False, ready_for_execution_preflight=passed,
        ready_for_provider_dispatch=False, evidence=evidence,
        evidence_manifest_sha256=hashlib.sha256(_canonical_bytes(evidence)).hexdigest(),
    )


async def validate_single_dispatch(
    paths: SingleDispatchPaths, *, runtime_policy: ProviderSafetyPolicy,
    clock: Callable[[], datetime] = utc_now,
) -> SingleDispatchQualification:
    """Read-only check of the real runner's bindings; never dispatch authority.

    The candidate implementation cannot qualify a historical RC: the shared
    source-blob check requires this module to be part of the bound RC tree.
    """
    now = clock().astimezone(timezone.utc)
    validated: _ValidatedDispatch | None = None
    custody: dict[str, object] | None = None
    try:
        validated = _validate_non_secret_bindings(
            paths, runtime_policy=runtime_policy, now=now,
            require_active_window=False,
        )
        _verify_pre_dispatch_contract(
            scope=validated.scope, policy=runtime_policy,
            context=validated.context, now=now, require_active_window=False,
        )
        if _EvidenceRecorder(paths.evidence_directory, validated.context.operation_key).folder.exists():
            raise SingleDispatchBlocked("EVIDENCE_PATH_ALREADY_EXISTS")
        custody = await bootstrap_custody(
            paths.rc_source, validated.binding, require_virgin_namespace=True,
        )
        _verify_virgin_custody(custody)
        return _qualification_result(
            code="READY_FOR_EXECUTION_PREFLIGHT", now=now,
            validated=validated, custody=custody,
        )
    except (SingleDispatchBlocked, BootstrapBlocked) as exc:
        code = exc.code if isinstance(exc, SingleDispatchBlocked) else str(exc)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*(?::[A-Za-z0-9_]+)?", code):
            code = "CHECK_ONLY_VALIDATION_FAILED"
        return _qualification_result(
            code=code, now=now, validated=validated,
        )
    except Exception:
        # Never serialize exception text: it may contain paths or sensitive data.
        return _qualification_result(
            code="CHECK_ONLY_VALIDATION_FAILED", now=now,
            validated=validated,
        )


async def run_single_dispatch(
    paths: SingleDispatchPaths,
    *,
    runtime_policy: ProviderSafetyPolicy,
    credential_resolver: Callable[[str], str],
    clock: Callable[[], datetime] = utc_now,
) -> SingleDispatchOutcome:
    """Canonical future execution entrypoint. Never valid for an older RC tree."""
    now = clock().astimezone(timezone.utc)
    validated = _validate_non_secret_bindings(
        paths, runtime_policy=runtime_policy, now=now,
        require_active_window=True,
    )
    binding, scope, context, metadata = (
        validated.binding, validated.scope, validated.context, validated.metadata,
    )
    _verify_pre_dispatch_contract(
        scope=scope, policy=runtime_policy, context=context, now=now,
        require_active_window=True,
    )
    custody = await bootstrap_custody(
        paths.rc_source, binding, require_virgin_namespace=True,
    )
    _verify_virgin_custody(custody)
    # Only a future, explicitly authorized execution invokes this callable.
    # Resolve once after every public/non-secret binding and custody check,
    # before reserving; the value is never serialized or logged.
    try:
        resolved_credential = credential_resolver(scope.credential_alias).strip()
    except Exception:
        raise SingleDispatchBlocked("CREDENTIAL_UNAVAILABLE") from None
    if not resolved_credential:
        raise SingleDispatchBlocked("CREDENTIAL_UNAVAILABLE")

    def frozen_credential(alias: str) -> str:
        if alias != scope.credential_alias:
            raise SingleDispatchBlocked("CREDENTIAL_ALIAS_MISMATCH")
        return resolved_credential

    provider = OpenAITranscriptionProvider(
        model="whisper-1", credential_alias=scope.credential_alias,
        credential_resolver=frozen_credential,
        language="vi", provider_http_timeout_seconds=scope.provider_http_timeout_seconds,
        controller_hard_timeout_seconds=scope.controller_hard_timeout_seconds,
        max_file_bytes=scope.max_file_bytes or 0,
        max_duration_seconds=scope.max_duration_seconds or 0,
        estimated_cost_vnd=scope.per_operation_limit_vnd,
        vnd_per_minute=scope.vnd_per_minute or Decimal("0"),
        asr_prompt_profile=scope.asr_prompt_profile,
    )
    # Bootstrap above verified private peer-auth custody before the secret
    # boundary. This engine uses the same pinned database and no password.
    engine = create_async_engine(
        ledger_url(binding), echo=False, pool_pre_ping=True,
        connect_args={"password": ""},
    )
    try:
        repository = ProviderSafetyRepository(async_sessionmaker(engine, expire_on_commit=False))
        return await _run_protocol(
            scope=scope, context=context, repository=repository, provider=provider,
            policy=runtime_policy,
            asset=paths.asset, metadata=metadata,
            evidence=_EvidenceRecorder(paths.evidence_directory, context.operation_key),
            clock=clock,
        )
    finally:
        await engine.dispose()


async def _run_protocol(
    *,
    scope: ProviderExecutionGateScope,
    policy: ProviderSafetyPolicy,
    context: ProviderCallContext,
    repository: ProviderSafetyRepository,
    provider: OpenAITranscriptionProvider,
    asset: Path,
    metadata: MediaMetadata,
    evidence: _EvidenceRecorder,
    clock: Callable[[], datetime],
) -> SingleDispatchOutcome:
    """Testable state machine. Only run_single_dispatch establishes live trust."""
    states = ["INIT"]
    switch = _ScopedKillSwitch(context.operation_key)
    actual_cost: Decimal | None = None
    charged: Decimal | None = None
    transcript: ProviderTranscript | None = None
    error_evidence: ProviderErrorEvidence | None = None
    error_kind: str | None = None
    code = "UNSET"
    reserved = False
    started = False
    attempt_recorded = False
    consumed: bool | None = False
    now = clock().astimezone(timezone.utc)
    _verify_pre_dispatch_contract(
        scope=scope, policy=policy, context=context, now=now,
        require_active_window=True,
    )
    controller = ProviderSafetyController(policy, clock=clock)
    if not switch.engaged:
        raise SingleDispatchBlocked("KILL_SWITCH_NOT_ENGAGED")
    if (provider.key, provider.model, provider.capability) != (scope.provider_key, scope.model, scope.capability):
        raise SingleDispatchBlocked("PROVIDER_ADAPTER_MISMATCH")
    if (
        provider.provider_http_timeout_seconds != scope.provider_http_timeout_seconds
        or provider.controller_hard_timeout_seconds != scope.controller_hard_timeout_seconds
        or provider.asr_prompt_profile != scope.asr_prompt_profile
        or provider.credential_alias != scope.credential_alias
        or provider.language != scope.requested_language
        or provider.response_format != scope.response_format
        or provider.timestamp_granularities != scope.timestamp_granularities
        or provider.max_file_bytes != scope.max_file_bytes
        or provider.max_duration_seconds != scope.max_duration_seconds
        or provider.estimated_cost_vnd != scope.per_operation_limit_vnd
        or provider._vnd_per_minute != scope.vnd_per_minute
    ):
        raise SingleDispatchBlocked("PROVIDER_REQUEST_ENVELOPE_MISMATCH")
    states.append("PREFLIGHT_VALIDATED")
    # The evidence destination must be fresh before creating a reservation.
    if evidence.folder.exists():
        raise SingleDispatchBlocked("EVIDENCE_PATH_ALREADY_EXISTS")
    before = await repository.dispatch_state(context)
    if before.status is not None:
        raise SingleDispatchBlocked("DUPLICATE_OPERATION_BLOCKED")
    reservation = await repository.reserve_operation(
        context, now=now, max_attempts=1, max_concurrent_calls=1,
        per_operation_limit_vnd=scope.per_operation_limit_vnd,
        daily_limit_vnd=scope.acceptance_window_limit_vnd,
        circuit_failure_threshold=policy.circuit.failure_threshold,
        circuit_cooldown_seconds=policy.circuit.cooldown_seconds,
        retention_days=400, single_dispatch_protocol=True,
    )
    if not reservation.allowed:
        raise SingleDispatchBlocked(reservation.code)
    reserved = True
    states.append("RESERVED")
    started_at = clock().astimezone(timezone.utc)
    try:
        evidence.arm(reserved_vnd=reservation.reserved_vnd, ledger_before="VIRGIN_NOT_CONSUMED")
        states.append("EVIDENCE_ARMED")
        states.append("READY_TO_DISPATCH")

        async def before_send(request_sha256: str, client_request_id: str) -> None:
            nonlocal started
            if started or not scope.active(clock().astimezone(timezone.utc)):
                raise SingleDispatchBlocked("SINGLE_DISPATCH_WINDOW_OR_REENTRY_BLOCKED")
            switch.allow_one_dispatch(context.operation_key)
            # All fallible evidence I/O precedes the durable dispatch marker.
            # Once that marker commits the adapter enters transport send with
            # no intervening file operation.
            evidence.mark_dispatch(request_sha256=request_sha256, client_request_id=client_request_id)
            await repository.mark_dispatch_started(
                context, now=clock().astimezone(timezone.utc),
                request_sha256=request_sha256, client_request_id=client_request_id,
            )
            started = True
            states.append("DISPATCH_STARTED")

        transcript = await asyncio.wait_for(
            provider.transcribe(
                asset, metadata=metadata, checksum_sha256=context.asset_hash or "",
                expected_asr_prompt_profile=scope.asr_prompt_profile,
                on_http_dispatch=before_send,
            ),
            timeout=scope.controller_hard_timeout_seconds,
        )
        if not started:
            raise SingleDispatchBlocked("PROVIDER_RETURNED_WITHOUT_DISPATCH_MARKER")
        actual_cost = transcript.actual_cost_vnd
        charged = actual_cost if actual_cost is not None else context.estimated_cost_vnd
        code = "QUALITY_REVIEW_REQUIRED"
    except (Exception, asyncio.CancelledError) as exc:
        error_kind = type(exc).__name__
        if isinstance(exc, asyncio.CancelledError):
            code = "CONTROLLER_CANCELLED"
        elif isinstance(exc, (asyncio.TimeoutError, ProviderTimeoutError)):
            code = "PROVIDER_TIMEOUT"
        elif isinstance(exc, SingleDispatchBlocked):
            code = exc.code
        else:
            code = getattr(exc, "code", type(exc).__name__)
        candidate = getattr(exc, "error_evidence", None)
        error_evidence = candidate if isinstance(candidate, ProviderErrorEvidence) else None
    finally:
        switch.reengage()

    # The database marker, not an in-memory flag or transport exception class,
    # decides whether this operation is consumed. Unknown custody fails closed.
    marker = await repository.dispatch_state(context)
    if marker.protocol_version != 1 or marker.status != "reserved":
        raise SingleDispatchBlocked("DISPATCH_LEDGER_STATE_AMBIGUOUS")
    started = marker.started
    if not started:
        released = await repository.release_pre_dispatch(context, now=clock().astimezone(timezone.utc))
        if not released:
            raise SingleDispatchBlocked("PRE_DISPATCH_RELEASE_FAILED")
        reserved = False
        states.append("BLOCKED_PRE_CALL")
        consumed = False
        charged = Decimal("0")
    else:
        consumed = True
        status: Literal["succeeded", "failed", "rate_limited", "timed_out"]
        if transcript is not None:
            status = "succeeded"
        elif code == "PROVIDER_TIMEOUT":
            status = "timed_out"
        elif error_kind == "ProviderRateLimitError" or (
            isinstance(error_evidence, ProviderErrorEvidence) and error_evidence.http_status == 429
        ):
            status = "rate_limited"
        else:
            status = "failed"
        charged = charged if charged is not None else (context.estimated_cost_vnd or Decimal("0"))
        attempt = controller._build_attempt_record(
            context, attempt=1, status=status, retryable=False,
            error_code=None if transcript is not None else code,
            error_evidence=(error_evidence.model_copy(update={"retryable": False}) if error_evidence else None),
            actual_cost_vnd=actual_cost, charged_cost_vnd=charged, started_at=started_at,
        )
        try:
            await repository.record_attempt(attempt)
            attempt_recorded = True
        except Exception:
            code = "LEDGER_ATTEMPT_REVIEW_REQUIRED"
        try:
            # Reconcile even when recording the separate attempt row failed.
            # A retained terminal row plus sealed review evidence is safer than
            # leaving an active reservation behind.
            await repository.finish_operation(
                context, now=clock().astimezone(timezone.utc), attempts=1,
                charged_vnd=charged, succeeded=transcript is not None and attempt_recorded,
                failure_code=None if transcript is not None and attempt_recorded else code,
                circuit_failure_threshold=policy.circuit.failure_threshold,
                warning_thresholds=tuple(policy.budget.warning_threshold_percent),
            )
            reserved = False
            states.append(
                ("QUALITY_REVIEW_REQUIRED" if transcript is not None else
                 "PROVIDER_TIMEOUT" if status == "timed_out" else "PROVIDER_ERROR")
                if attempt_recorded else "REVIEW_REQUIRED"
            )
        except Exception:
            # This is ledger cleanup, never another provider attempt. It is
            # idempotent if the first commit succeeded but its acknowledgement
            # was lost. If custody remains unavailable, stale recovery owns it.
            code = "LEDGER_TERMINAL_REVIEW_REQUIRED"
            try:
                await repository.finish_operation(
                    context, now=clock().astimezone(timezone.utc), attempts=1,
                    charged_vnd=charged, succeeded=False, failure_code=code,
                    circuit_failure_threshold=policy.circuit.failure_threshold,
                    warning_thresholds=tuple(policy.budget.warning_threshold_percent),
                )
                reserved = False
            except Exception:
                reserved = True
            states.append("REVIEW_REQUIRED")

    final_marker = await repository.dispatch_state(context)
    snapshot = await repository.snapshot(now=clock().astimezone(timezone.utc), stale_after_seconds=900)
    rights_record = scope.rights_for_asset(context.asset_id, context.asset_hash)
    if rights_record is None:
        raise SingleDispatchBlocked("RIGHTS_RECORD_MISSING_AFTER_DISPATCH")
    provider_metadata = transcript.provenance if transcript is not None else {}
    error_metadata = error_evidence.model_dump(mode="json") if error_evidence else {}
    evidence_sha: str | None = None
    try:
        evidence_sha = evidence.seal({
            "code": code, "transitions": states,
            "dispatch_started": started,
            "provider_call_state": "POSSIBLY_SENT" if started else "NOT_SENT",
            "operation_consumed": consumed,
            "actual_cost_vnd": None if actual_cost is None else str(actual_cost),
            "safety_charge_vnd": None if charged is None else str(charged),
            "reservation_active": reserved,
            "reservation_reconciled": not reserved,
            "initial_reservation_vnd": str(reservation.reserved_vnd),
            "window_reserved_after_vnd": str(snapshot.reserved_today_vnd),
            "window_committed_after_vnd": str(snapshot.committed_today_vnd),
            "circuit_state": snapshot.circuits.get((context.provider_key, context.capability), "closed"),
            "kill_switch_after": "ENGAGED" if switch.engaged else "DISENGAGED_UNSAFE",
            "attempt_recorded": attempt_recorded,
            "ledger_after": final_marker.status,
            "request_sha256": provider_metadata.get("request_sha256") or error_metadata.get("request_sha256") or marker.request_sha256,
            "response_sha256": provider_metadata.get("response_sha256") or error_metadata.get("response_sha256"),
            "provider_request_id": provider_metadata.get("provider_request_id") or error_metadata.get("provider_request_id"),
            "client_request_id": provider_metadata.get("client_request_id") or error_metadata.get("client_request_id") or marker.client_request_id,
            "latency_ms": provider_metadata.get("latency_ms") or error_metadata.get("elapsed_ms"),
            "timeout_phase": error_metadata.get("timeout_phase"),
            "transcript": asdict(transcript) if transcript is not None else None,
            "error_evidence": error_metadata or None,
            "rights_record_id": rights_record.rights_record_id,
            "rights_record_sha256": canonical_sha256(rights_record),
            "duplicate_state": "BLOCKED_ON_REENTRY_BY_OPERATION_KEY",
            "operation_2": "LOCKED",
        })
    except Exception:
        code = "EVIDENCE_SEAL_REVIEW_REQUIRED"
        states.append("REVIEW_REQUIRED")
    return SingleDispatchOutcome(
        state=states[-1], code=code, dispatch_started=started,
        operation_consumed=consumed, charged_vnd=charged,
        actual_cost_vnd=actual_cost, evidence_sha256=evidence_sha,
        transitions=tuple(states),
    )
