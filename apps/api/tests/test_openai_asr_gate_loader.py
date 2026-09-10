from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.config import Settings
from app.db import Base, create_engine, create_session_factory
from app.provider_gate_loader import (
    HashedApprovalRecord,
    HashedRightsRecord,
    OpenAIAsrGateBudgetEnvelope,
    OpenAIAsrGateBundle,
    ProviderApprovalRecord,
    canonical_sha256,
    execution_scope_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_safety import (
    ProviderAllowedOperation,
    ProviderCallContext,
    ProviderRightsEvidence,
    ProviderSafetyController,
    derive_acceptance_lineage_id,
    derive_rc_bound_operation_key,
    provider_safety_policy_from_settings,
    validate_acceptance_lineage_id,
)
from app.provider_safety_db import ProviderSafetyAttemptORM, ProviderSafetyOperationORM
from app.provider_safety_durable import DurableProviderSafetyController
from app.provider_safety_repository import ProviderSafetyRepository
import app.provider_safety_db  # noqa: F401


RC_COMMIT = "b" * 40
RC_TAG = "vf-v3-01-rc11"
ACTIVATES_AT = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)
EXPIRES_AT = ACTIVATES_AT + timedelta(hours=3)
ASSET_BINDINGS = (
    ("asset-asr-owned-a", "a" * 64),
    ("asset-asr-owned-b", "c" * 64),
)


def _budget() -> OpenAIAsrGateBudgetEnvelope:
    return OpenAIAsrGateBudgetEnvelope(
        per_operation_limit_vnd=Decimal("400"),
        acceptance_window_limit_vnd=Decimal("900"),
        vnd_per_minute=Decimal("160"),
        budget_day_utc=ACTIVATES_AT.date(),
        files_per_operation=1,
        max_file_bytes=25_000_000,
        max_duration_seconds=600,
        requested_language="vi",
        response_format="verbose_json",
        timestamp_granularities=("segment", "word"),
        provider_http_timeout_seconds=90,
        controller_hard_timeout_seconds=120,
        max_attempts=1,
        max_concurrent_calls=1,
        automatic_retry=False,
        model_fallback=False,
    )


def _rights(slot: int, asset_id: str, asset_hash: str) -> ProviderRightsEvidence:
    return ProviderRightsEvidence(
        rights_record_id=f"V3-01-RIGHTS-ASR-{slot:03d}",
        asset_id=asset_id,
        asset_hash=asset_hash,
        source_type="user_owned",
        provider="Ngoc Phuong Dong",
        provider_asset_or_job_id=f"owned-asr-fixture-{slot}",
        source_url_or_reference=f"repo://acceptance/asr-owned-{slot}.wav",
        acquired_at_utc=ACTIVATES_AT - timedelta(days=1),
        license_name="NPD-owned ASR acceptance input only",
        license_version_or_terms_date="2026-09-03",
        commercial_use=True,
        derivative_use=True,
        social_platform_use=[],
        territory=["VN"],
        expiry=None,
        attribution_required=False,
        attribution_text="",
        model_or_voice_rights="owner-cleared test voice",
        person_likeness_consent="owner-cleared acceptance recording",
        trademark_review="no third-party trademark",
        evidence_reference=f"repo://acceptance/asr-rights-{slot}.json",
        reviewer="NPD owner",
        decision="APPROVED",
        secret_recorded=False,
    )


def _approval(
    approval_id: str,
    gate_id: str,
    hashes: list[str],
) -> HashedApprovalRecord:
    record = ProviderApprovalRecord(
        approval_id=approval_id,
        gate_id=gate_id,
        decision="APPROVED",
        scope=f"bounded {gate_id} ASR acceptance",
        artifact_or_commit_hashes=hashes,
        target_account_or_environment="isolated local acceptance runner",
        limits=["one attempt", "no retry", "no fallback", "no publish"],
        approved_by="NPD owner",
        approved_at_utc=ACTIVATES_AT - timedelta(hours=1),
        expires_at_utc=EXPIRES_AT,
        notes="Secret-free synthetic gate contract.",
    )
    return HashedApprovalRecord(
        record_sha256=canonical_sha256(record),
        record=record,
    )


def _bundle() -> OpenAIAsrGateBundle:
    budget = _budget()
    rights = tuple(
        _rights(slot, asset_id, asset_hash)
        for slot, (asset_id, asset_hash) in enumerate(ASSET_BINDINGS, start=1)
    )
    hashed_rights = tuple(
        HashedRightsRecord(record_sha256=canonical_sha256(record), record=record)
        for record in rights
    )
    operations = tuple(
        ProviderAllowedOperation(
            operation_key=derive_rc_bound_operation_key(
                rc_tag=RC_TAG,
                provider_key="openai-transcription",
                capability="asr",
                slot=slot,
            ),
            slot=slot,
            operation="flow_a_asr",
            asset_id=asset_id,
            asset_hash=asset_hash,
        )
        for slot, (asset_id, asset_hash) in enumerate(ASSET_BINDINGS, start=1)
    )
    provider_hash = canonical_sha256(
        {
            "provider_key": "openai-transcription",
            "model": "whisper-1",
            "capability": "asr",
            "credential_alias": "secret://openai/codex-video",
        }
    )
    rights_hashes = tuple(item.record_sha256 for item in hashed_rights)
    scope_hash = execution_scope_sha256(
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        credential_alias="secret://openai/codex-video",
        valid_from_utc=ACTIVATES_AT,
        expires_at_utc=EXPIRES_AT,
        budget=budget,
        rights_record_sha256s=rights_hashes,
        allowed_operations=operations,
    )
    return OpenAIAsrGateBundle(
        bundle_id="V3-01-GATE-RC11-OPENAI-ASR-A",
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        credential_alias="secret://openai/codex-video",
        valid_from_utc=ACTIVATES_AT,
        expires_at_utc=EXPIRES_AT,
        budget=budget,
        credential_approval=_approval(
            "V3-01-APP-201", "G-01", [RC_COMMIT, provider_hash, scope_hash]
        ),
        budget_approval=_approval(
            "V3-01-APP-202", "G-02", [RC_COMMIT, canonical_sha256(budget), scope_hash]
        ),
        rights_approval=_approval(
            "V3-01-APP-203", "G-03", [RC_COMMIT, *rights_hashes, scope_hash]
        ),
        rights_records=hashed_rights,
        allowed_operations=operations,
    )


def _write_bundle(tmp_path, payload: dict[str, object] | None = None):
    raw = json.dumps(
        payload or _bundle().model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path = tmp_path / "asr-provider-gate.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def _settings(path, bundle_sha: str, **updates: object) -> Settings:
    values: dict[str, object] = {
        "transcription_provider": "openai",
        "openai_transcription_model": "whisper-1",
        "openai_transcription_estimated_cost_vnd": Decimal("400"),
        "openai_transcription_vnd_per_minute": Decimal("160"),
        "provider_verified_gate_bundle_enabled": True,
        "provider_verified_gate_bundle_file": path,
        "provider_verified_gate_bundle_sha256": bundle_sha,
        "provider_gate_expected_rc_commit": RC_COMMIT,
        "provider_gate_expected_rc_tag": RC_TAG,
        "provider_per_operation_limit_vnd": Decimal("400"),
        "provider_daily_limit_vnd": Decimal("900"),
        "provider_retry_max_attempts": 1,
        "provider_http_timeout_seconds": 90,
        "controller_hard_timeout_seconds": 120,
        "provider_retry_max_elapsed_seconds": 120,
        "provider_max_concurrent_calls": 1,
    }
    values.update(updates)
    return Settings(_env_file=None, **values)


def _context(slot: int, **updates: object) -> ProviderCallContext:
    asset_id, asset_hash = ASSET_BINDINGS[slot - 1]
    values: dict[str, object] = {
        "operation_key": derive_rc_bound_operation_key(
            rc_tag=RC_TAG,
            provider_key="openai-transcription",
            capability="asr",
            slot=slot,
        ),
        "workspace_id": "wsp_asr_acceptance",
        "project_id": "prj_asr_acceptance",
        "provider_key": "openai-transcription",
        "model": "whisper-1",
        "capability": "asr",
        "operation": "flow_a_asr",
        "external_call": True,
        "paid": True,
        "estimated_cost_vnd": Decimal("400"),
        "credential_alias": "secret://openai/codex-video",
        "asset_id": asset_id,
        "asset_hash": asset_hash,
        "input_media_kind": "audio",
        "input_file_bytes": 1_000_000,
        "input_duration_seconds": 95,
        "requested_language": "vi",
        "response_format": "verbose_json",
        "timestamp_granularities": ("segment", "word"),
        "rights_required": True,
        "rights": [],
    }
    values.update(updates)
    return ProviderCallContext.model_validate(values)


def test_asr_bundle_loads_offline_but_defaults_remain_fail_closed(tmp_path) -> None:
    path, bundle_sha = _write_bundle(tmp_path)
    settings = _settings(path, bundle_sha)
    policy = provider_safety_policy_from_settings(settings)

    assert policy.execution_gate is not None
    assert policy.execution_gate.capability == "asr"
    assert policy.execution_gate.model == "whisper-1"
    assert policy.execution_gate.max_file_bytes == 25_000_000
    assert policy.execution_gate.max_duration_seconds == 600
    assert policy.execution_gate.timestamp_granularities == ("segment", "word")
    assert len(policy.execution_gate.all_rights_records()) == 2
    assert policy.external_execution_enabled is False
    assert policy.paid_execution_enabled is False
    assert policy.global_kill_switch_engaged is True


@pytest.mark.asyncio
async def test_asr_scope_enforces_asset_duration_format_and_model(tmp_path) -> None:
    path, bundle_sha = _write_bundle(tmp_path)
    settings = _settings(
        path,
        bundle_sha,
        provider_external_execution_enabled=True,
        provider_paid_execution_enabled=True,
        provider_global_kill_switch_engaged=False,
    )
    controller = ProviderSafetyController(
        provider_safety_policy_from_settings(settings),
        clock=lambda: ACTIVATES_AT + timedelta(minutes=5),
    )

    assert (await controller.preflight(_context(1))).code == "PROVIDER_CALL_RESERVED"
    fresh = ProviderSafetyController(
        provider_safety_policy_from_settings(settings),
        clock=lambda: ACTIVATES_AT + timedelta(minutes=5),
    )
    assert (await fresh.preflight(_context(1, model="gpt-transcribe"))).code == (
        "MODEL_NOT_AUTHORIZED"
    )
    assert (await fresh.preflight(_context(1, input_duration_seconds=601))).code == (
        "INPUT_DURATION_LIMIT_EXCEEDED"
    )
    assert (await fresh.preflight(_context(1, response_format=None))).code == (
        "RESPONSE_FORMAT_MISMATCH"
    )
    assert (await fresh.preflight(_context(1, asset_hash="d" * 64))).code == (
        "RIGHTS_ASSET_BINDING_MISMATCH"
    )


@pytest.mark.parametrize("model", ["gpt-transcribe", "gpt-4o-transcribe"])
def test_asr_gate_does_not_promote_incompatible_candidate(model: str) -> None:
    payload = _bundle().model_dump(mode="json")
    payload["model"] = model
    with pytest.raises(ValidationError, match="strict native timestamp contract"):
        OpenAIAsrGateBundle.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_duration_seconds", 601),
        ("openai_transcription_vnd_per_minute", Decimal("161")),
        ("provider_daily_limit_vnd", Decimal("901")),
        ("provider_retry_max_attempts", 2),
    ],
)
def test_asr_runtime_settings_must_match_hash_pinned_g02(
    tmp_path,
    field: str,
    value: object,
) -> None:
    path, bundle_sha = _write_bundle(tmp_path)
    updates = {field: value}
    if field == "max_duration_seconds":
        updates = {"openai_transcription_max_duration_seconds": value}
    with pytest.raises(ValidationError, match="verified G-02-ASR envelope"):
        _settings(path, bundle_sha, **updates)


def test_asr_bundle_rejects_one_rights_record_and_tampered_operation() -> None:
    payload = _bundle().model_dump(mode="json")
    payload["rights_records"] = payload["rights_records"][:1]
    with pytest.raises(ValidationError):
        OpenAIAsrGateBundle.model_validate(payload)

    payload = _bundle().model_dump(mode="json")
    payload["allowed_operations"][1]["operation_key"] = (
        "v3-01-rc10-openai-transcription-asr-call-02"
    )
    with pytest.raises(ValidationError, match="derive from exact RC"):
        OpenAIAsrGateBundle.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("per_operation_limit_vnd", 400),
        ("acceptance_window_limit_vnd", 900.0),
        ("vnd_per_minute", "0160"),
    ],
)
def test_asr_bundle_rejects_noncanonical_vnd_json(field: str, value: object) -> None:
    payload = _budget().model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError, match="canonical decimal strings"):
        OpenAIAsrGateBudgetEnvelope.model_validate(payload)


def test_asr_loader_rejects_hash_and_exact_rc_drift(tmp_path) -> None:
    path, bundle_sha = _write_bundle(tmp_path)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_verified_provider_gate_bundle(
            path,
            expected_bundle_sha256="0" * 64,
            expected_rc_commit=RC_COMMIT,
            expected_rc_tag=RC_TAG,
        )
    with pytest.raises(ValueError, match="exact RC"):
        load_verified_provider_gate_bundle(
            path,
            expected_bundle_sha256=bundle_sha,
            expected_rc_commit="d" * 40,
            expected_rc_tag=RC_TAG,
        )


def _lineage_bundle(sequence: int = 2) -> OpenAIAsrGateBundle:
    budget = _budget()
    rights = tuple(
        _rights(slot, asset_id, asset_hash)
        for slot, (asset_id, asset_hash) in enumerate(ASSET_BINDINGS, start=1)
    )
    hashed_rights = tuple(
        HashedRightsRecord(record_sha256=canonical_sha256(record), record=record)
        for record in rights
    )
    lineage_id = derive_acceptance_lineage_id(
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        sequence=sequence,
    )
    operations = tuple(
        ProviderAllowedOperation(
            operation_key=derive_rc_bound_operation_key(
                rc_tag=RC_TAG,
                provider_key="openai-transcription",
                capability="asr",
                slot=slot,
                acceptance_lineage_id=lineage_id,
            ),
            slot=slot,
            operation="flow_a_asr",
            asset_id=asset_id,
            asset_hash=asset_hash,
        )
        for slot, (asset_id, asset_hash) in enumerate(ASSET_BINDINGS, start=1)
    )
    provider_hash = canonical_sha256(
        {
            "provider_key": "openai-transcription",
            "model": "whisper-1",
            "capability": "asr",
            "credential_alias": "secret://openai/codex-video",
        }
    )
    rights_hashes = tuple(item.record_sha256 for item in hashed_rights)
    scope_hash = execution_scope_sha256(
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        credential_alias="secret://openai/codex-video",
        valid_from_utc=ACTIVATES_AT,
        expires_at_utc=EXPIRES_AT,
        budget=budget,
        rights_record_sha256s=rights_hashes,
        allowed_operations=operations,
        acceptance_lineage_sequence=sequence,
        acceptance_lineage_id=lineage_id,
    )
    return OpenAIAsrGateBundle(
        version=2,
        bundle_id="V3-01-GATE-RC11-OPENAI-ASR-LINEAGE-002",
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        acceptance_lineage_sequence=sequence,
        acceptance_lineage_id=lineage_id,
        credential_alias="secret://openai/codex-video",
        valid_from_utc=ACTIVATES_AT,
        expires_at_utc=EXPIRES_AT,
        budget=budget,
        credential_approval=_approval(
            "V3-01-APP-211", "G-01", [RC_COMMIT, provider_hash, scope_hash]
        ),
        budget_approval=_approval(
            "V3-01-APP-212", "G-02", [RC_COMMIT, canonical_sha256(budget), scope_hash]
        ),
        rights_approval=_approval(
            "V3-01-APP-213", "G-03", [RC_COMMIT, *rights_hashes, scope_hash]
        ),
        rights_records=hashed_rights,
        allowed_operations=operations,
    )


def _write_lineage_bundle(tmp_path, bundle: OpenAIAsrGateBundle | None = None):
    value = bundle or _lineage_bundle()
    raw = json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path = tmp_path / "asr-provider-gate-lineage-v2.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest(), value


def _lineage_context(bundle: OpenAIAsrGateBundle, slot: int, **updates: object):
    lineage_id = bundle.acceptance_lineage_id
    assert lineage_id is not None
    values: dict[str, object] = {
        "operation_key": bundle.allowed_operations[slot - 1].operation_key,
        "acceptance_lineage_id": lineage_id,
    }
    values.update(updates)
    return _context(slot, **values)


def test_lineage_id_and_operation_ids_are_canonical_and_rc_bound() -> None:
    first = _lineage_bundle(1)
    second = _lineage_bundle(2)
    assert first.acceptance_lineage_id != second.acceptance_lineage_id
    assert first.allowed_operations[0].operation_key != second.allowed_operations[0].operation_key
    assert (
        first.credential_approval.record.artifact_or_commit_hashes[-1]
        != second.credential_approval.record.artifact_or_commit_hashes[-1]
    )
    assert derive_rc_bound_operation_key(
        rc_tag=RC_TAG,
        provider_key="openai-transcription",
        capability="asr",
        slot=1,
    ) == "v3-01-rc11-openai-transcription-asr-call-01"
    with pytest.raises(ValueError, match="exact execution scope"):
        validate_acceptance_lineage_id(
            second.acceptance_lineage_id or "",
            rc_tag=RC_TAG,
            rc_commit="c" * 40,
            provider_key="openai-transcription",
            model="whisper-1",
            capability="asr",
            sequence=2,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_id",
        "missing_sequence",
        "tampered",
        "wrong_sequence",
        "wrong_type",
        "legacy_with_lineage",
        "old_operation",
    ],
)
def test_lineage_bundle_rejects_missing_tampered_and_legacy_claims(mutation: str) -> None:
    payload = _lineage_bundle().model_dump(mode="json")
    if mutation == "missing_id":
        payload.pop("acceptance_lineage_id")
    elif mutation == "missing_sequence":
        payload.pop("acceptance_lineage_sequence")
    elif mutation == "tampered":
        payload["acceptance_lineage_id"] = "al-0002-" + "0" * 64
    elif mutation == "wrong_sequence":
        payload["acceptance_lineage_sequence"] = 3
    elif mutation == "wrong_type":
        payload["acceptance_lineage_sequence"] = "2"
    elif mutation == "old_operation":
        payload["allowed_operations"][0]["operation_key"] = (
            "v3-01-rc11-openai-transcription-asr-call-01"
        )
    else:
        payload["version"] = 1
    with pytest.raises(ValidationError):
        OpenAIAsrGateBundle.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rc_commit", "c" * 40),
        ("rc_tag", "vf-v3-01-rc12"),
        ("provider_key", "other-provider"),
        ("model", "gpt-transcribe"),
        ("capability", "vision"),
    ],
)
def test_lineage_identity_rejects_cross_scope_reuse(field: str, value: str) -> None:
    lineage_id = _lineage_bundle().acceptance_lineage_id
    assert lineage_id is not None
    scope: dict[str, object] = {
        "rc_tag": RC_TAG,
        "rc_commit": RC_COMMIT,
        "provider_key": "openai-transcription",
        "model": "whisper-1",
        "capability": "asr",
        "sequence": 2,
    }
    scope[field] = value
    with pytest.raises(ValueError, match="exact execution scope"):
        validate_acceptance_lineage_id(lineage_id, **scope)


def test_lineage_loader_requires_exact_expected_identity(tmp_path) -> None:
    path, bundle_sha, bundle = _write_lineage_bundle(tmp_path)
    lineage_id = bundle.acceptance_lineage_id
    assert lineage_id is not None
    scope = load_verified_provider_gate_bundle(
        path,
        expected_bundle_sha256=bundle_sha,
        expected_rc_commit=RC_COMMIT,
        expected_rc_tag=RC_TAG,
        expected_acceptance_lineage_id=lineage_id,
    )
    assert scope.gate_bundle_version == 2
    assert scope.acceptance_lineage_id == lineage_id
    assert scope.acceptance_lineage_sequence == 2
    assert scope.execution_scope_sha256 == execution_scope_sha256(
        rc_tag=scope.rc_tag,
        rc_commit=scope.rc_commit,
        provider_key=scope.provider_key,
        model=scope.model,
        capability=scope.capability,
        credential_alias=scope.credential_alias,
        valid_from_utc=scope.valid_from_utc,
        expires_at_utc=scope.expires_at_utc,
        budget=bundle.budget,
        rights_record_sha256s=scope.rights_record_sha256s,
        allowed_operations=scope.allowed_operations,
        acceptance_lineage_sequence=2,
        acceptance_lineage_id=lineage_id,
    )
    with pytest.raises(ValueError, match="requires an expected acceptance lineage"):
        load_verified_provider_gate_bundle(
            path,
            expected_bundle_sha256=bundle_sha,
            expected_rc_commit=RC_COMMIT,
            expected_rc_tag=RC_TAG,
        )
    stale = _lineage_bundle(1).acceptance_lineage_id
    with pytest.raises(ValueError, match="expected acceptance lineage"):
        load_verified_provider_gate_bundle(
            path,
            expected_bundle_sha256=bundle_sha,
            expected_rc_commit=RC_COMMIT,
            expected_rc_tag=RC_TAG,
            expected_acceptance_lineage_id=stale,
        )


@pytest.mark.asyncio
async def test_lineage_preflight_rejects_old_and_wrong_lineage_before_reservation(
    tmp_path,
) -> None:
    path, bundle_sha, bundle = _write_lineage_bundle(tmp_path)
    lineage_id = bundle.acceptance_lineage_id
    assert lineage_id is not None
    settings = _settings(
        path,
        bundle_sha,
        provider_gate_expected_acceptance_lineage_id=lineage_id,
        provider_external_execution_enabled=True,
        provider_paid_execution_enabled=True,
        provider_global_kill_switch_engaged=False,
    )
    policy = provider_safety_policy_from_settings(settings)
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'lineage.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = create_session_factory(engine)
    repository = ProviderSafetyRepository(sessions)
    await repository.ensure_state()
    controller = DurableProviderSafetyController(
        policy,
        repository=repository,
        clock=lambda: ACTIVATES_AT + timedelta(minutes=5),
    )

    wrong_lineage = _lineage_bundle(1).acceptance_lineage_id
    decision = await controller.preflight(
        _lineage_context(bundle, 1, acceptance_lineage_id=wrong_lineage)
    )
    assert decision.code == "ACCEPTANCE_LINEAGE_MISMATCH"
    decision = await controller.preflight(
        _lineage_context(bundle, 1, acceptance_lineage_id=None)
    )
    assert decision.code == "ACCEPTANCE_LINEAGE_MISMATCH"
    old_operation = derive_rc_bound_operation_key(
        rc_tag=RC_TAG,
        provider_key="openai-transcription",
        capability="asr",
        slot=1,
    )
    decision = await controller.preflight(
        _lineage_context(bundle, 1, operation_key=old_operation)
    )
    assert decision.code == "OPERATION_NOT_ALLOWLISTED"
    async with sessions() as session:
        assert int(
            await session.scalar(select(func.count()).select_from(ProviderSafetyOperationORM))
            or 0
        ) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_lineage_is_preserved_in_durable_operation_attempt_and_receipt(tmp_path) -> None:
    path, bundle_sha, bundle = _write_lineage_bundle(tmp_path)
    lineage_id = bundle.acceptance_lineage_id
    assert lineage_id is not None
    settings = _settings(
        path,
        bundle_sha,
        provider_gate_expected_acceptance_lineage_id=lineage_id,
        provider_external_execution_enabled=True,
        provider_paid_execution_enabled=True,
        provider_global_kill_switch_engaged=False,
    )
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'lineage-evidence.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = create_session_factory(engine)
    repository = ProviderSafetyRepository(sessions)
    await repository.ensure_state()
    controller = DurableProviderSafetyController(
        provider_safety_policy_from_settings(settings),
        repository=repository,
        clock=lambda: ACTIVATES_AT + timedelta(minutes=5),
    )

    async def completed() -> Decimal:
        return Decimal("100")

    result = await controller.execute(
        _lineage_context(bundle, 1),
        completed,
        actual_cost=lambda value: value,
    )
    assert result.receipt.acceptance_lineage_id == lineage_id
    async with sessions() as session:
        operation = await session.get(
            ProviderSafetyOperationORM,
            bundle.allowed_operations[0].operation_key,
        )
        attempt = await session.scalar(select(ProviderSafetyAttemptORM))
        assert operation is not None and operation.acceptance_lineage_id == lineage_id
        assert attempt is not None and attempt.acceptance_lineage_id == lineage_id
    assert (await controller.preflight(_lineage_context(bundle, 1))).code == (
        "DUPLICATE_OPERATION_BLOCKED"
    )
    await engine.dispose()
