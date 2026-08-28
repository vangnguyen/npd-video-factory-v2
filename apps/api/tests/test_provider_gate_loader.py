from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.db import Base, create_engine, create_session_factory
from app.provider_gate_loader import (
    G02_A_OPERATION_KEYS,
    HashedApprovalRecord,
    HashedRightsRecord,
    ProviderApprovalRecord,
    ProviderGateBudgetEnvelope,
    ProviderGateBundle,
    ProviderGateBundleError,
    canonical_sha256,
    execution_scope_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_safety import (
    ProviderAllowedOperation,
    ProviderCallContext,
    ProviderRightsEvidence,
    ProviderSafetyController,
    provider_safety_policy_from_settings,
)
from app.provider_safety_durable import DurableProviderSafetyController
from app.provider_safety_repository import ProviderSafetyRepository
import app.provider_safety_db  # noqa: F401


RC_COMMIT = "c" * 40
RC_TAG = "vf-v3-01-rc3"
ASSET_ID = "asset-g03-a-owned-vision-test"
ASSET_HASH = "a" * 64
OPERATION_ONE, OPERATION_TWO = G02_A_OPERATION_KEYS
ACTIVATES_AT = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
EXPIRES_AT = ACTIVATES_AT + timedelta(hours=3)
REPO_ROOT = Path(__file__).resolve().parents[3]


def _rights_record() -> ProviderRightsEvidence:
    return ProviderRightsEvidence(
        rights_record_id="V3-01-RIGHTS-G03A-001",
        asset_id=ASSET_ID,
        asset_hash=ASSET_HASH,
        source_type="internal",
        provider="Ngoc Phuong Dong",
        provider_asset_or_job_id="g03-owned-test-card-v1",
        source_url_or_reference=(
            "repo://docs/acceptance/v3-01/assets/g03-a-owned-vision-test.png"
        ),
        acquired_at_utc=datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc),
        license_name="NPD internally created acceptance asset",
        license_version_or_terms_date="2026-08-28",
        commercial_use=True,
        derivative_use=True,
        social_platform_use=[],
        territory=["VN"],
        expiry=None,
        attribution_required=False,
        attribution_text="",
        model_or_voice_rights="not-applicable",
        person_likeness_consent="not-applicable-no-person",
        trademark_review="no-third-party-trademark",
        evidence_reference=(
            "repo://docs/acceptance/v3-01/rights/V3-01-RIGHTS-G03A-001.json"
        ),
        reviewer="NPD owner",
        decision="APPROVED",
        secret_recorded=False,
    )


def _budget() -> ProviderGateBudgetEnvelope:
    return ProviderGateBudgetEnvelope(
        per_operation_limit_vnd=Decimal("500"),
        acceptance_window_limit_vnd=Decimal("1250"),
        input_vnd_per_million_tokens=Decimal("6565"),
        cached_input_vnd_per_million_tokens=Decimal("656.5"),
        output_vnd_per_million_tokens=Decimal("52520"),
        budget_day_utc=ACTIVATES_AT.date(),
        max_frames=1,
        max_dimension_pixels=2048,
        image_detail="high",
        input_token_ceiling=16_384,
        max_output_tokens=4_096,
        timeout_seconds=60,
        max_attempts=1,
        max_concurrent_calls=1,
    )


def _approval(
    approval_id: str,
    gate_id: str,
    *,
    artifact_hashes: list[str],
) -> HashedApprovalRecord:
    record = ProviderApprovalRecord(
        approval_id=approval_id,
        gate_id=gate_id,
        decision="APPROVED",
        scope=f"bounded {gate_id} OpenAI Vision acceptance",
        artifact_or_commit_hashes=artifact_hashes,
        target_account_or_environment="isolated local acceptance runner",
        limits=["no deploy", "no publish", "no fallback"],
        approved_by="NPD owner",
        approved_at_utc=ACTIVATES_AT - timedelta(hours=1),
        expires_at_utc=EXPIRES_AT,
        notes="Secret-free deterministic test approval.",
    )
    return HashedApprovalRecord(
        record_sha256=canonical_sha256(record),
        record=record,
    )


def _valid_bundle() -> ProviderGateBundle:
    budget = _budget()
    rights = _rights_record()
    rights_hash = canonical_sha256(rights)
    provider_scope_hash = canonical_sha256(
        {
            "provider_key": "openai-vision",
            "model": "gpt-5-mini",
            "capability": "vision",
            "credential_alias": "secret://openai/codex-video",
        }
    )
    allowed_operations = (
        ProviderAllowedOperation(
            operation_key=OPERATION_ONE,
            operation="vision_analysis",
            asset_id=ASSET_ID,
            asset_hash=ASSET_HASH,
        ),
        ProviderAllowedOperation(
            operation_key=OPERATION_TWO,
            operation="vision_analysis",
            asset_id=ASSET_ID,
            asset_hash=ASSET_HASH,
        ),
    )
    scope_hash = execution_scope_sha256(
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-vision",
        model="gpt-5-mini",
        capability="vision",
        credential_alias="secret://openai/codex-video",
        valid_from_utc=ACTIVATES_AT,
        expires_at_utc=EXPIRES_AT,
        budget=budget,
        rights_record_sha256=rights_hash,
        allowed_operations=allowed_operations,
    )
    return ProviderGateBundle(
        bundle_id="V3-01-GATE-RC3-OPENAI-VISION-A",
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-vision",
        model="gpt-5-mini",
        capability="vision",
        credential_alias="secret://openai/codex-video",
        valid_from_utc=ACTIVATES_AT,
        expires_at_utc=EXPIRES_AT,
        budget=budget,
        credential_approval=_approval(
            "V3-01-APP-101",
            "G-01",
            artifact_hashes=[RC_COMMIT, provider_scope_hash, scope_hash],
        ),
        budget_approval=_approval(
            "V3-01-APP-102",
            "G-02",
            artifact_hashes=[RC_COMMIT, canonical_sha256(budget), scope_hash],
        ),
        rights_approval=_approval(
            "V3-01-APP-103",
            "G-03",
            artifact_hashes=[RC_COMMIT, rights_hash, scope_hash],
        ),
        rights_record=HashedRightsRecord(
            record_sha256=rights_hash,
            record=rights,
        ),
        allowed_operations=allowed_operations,
    )


def _write_bundle(tmp_path, *, payload: dict[str, object] | None = None):
    bundle_payload = payload or _valid_bundle().model_dump(mode="json")
    raw = json.dumps(
        bundle_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path = tmp_path / "provider-gates.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def _settings(
    path,
    bundle_sha256: str,
    *,
    execution: bool = False,
    **updates: object,
) -> Settings:
    payload: dict[str, object] = {
        "vision_provider": "openai",
        "openai_vision_max_frames": 1,
        "openai_vision_max_dimension_pixels": 2048,
        "openai_vision_input_token_ceiling": 16_384,
        "openai_vision_max_output_tokens": 4_096,
        "openai_vision_estimated_cost_vnd": Decimal("500"),
        "openai_vision_input_vnd_per_million_tokens": Decimal("6565"),
        "openai_vision_cached_input_vnd_per_million_tokens": Decimal("656.5"),
        "openai_vision_output_vnd_per_million_tokens": Decimal("52520"),
        "provider_verified_gate_bundle_enabled": True,
        "provider_verified_gate_bundle_file": path,
        "provider_verified_gate_bundle_sha256": bundle_sha256,
        "provider_gate_expected_rc_commit": RC_COMMIT,
        "provider_gate_expected_rc_tag": RC_TAG,
        "provider_per_operation_limit_vnd": Decimal("500"),
        "provider_daily_limit_vnd": Decimal("1250"),
        "provider_retry_max_attempts": 1,
        "provider_request_timeout_seconds": 60,
        "provider_retry_max_elapsed_seconds": 60,
        "provider_max_concurrent_calls": 1,
        "provider_external_execution_enabled": execution,
        "provider_paid_execution_enabled": execution,
        "provider_global_kill_switch_engaged": not execution,
    }
    payload.update(updates)
    return Settings(
        _env_file=None,
        **payload,
    )


def _context(operation_key: str, **updates: object) -> ProviderCallContext:
    payload: dict[str, object] = {
        "operation_key": operation_key,
        "workspace_id": "wsp_acceptance",
        "project_id": "prj_acceptance",
        "provider_key": "openai-vision",
        "model": "gpt-5-mini",
        "capability": "vision",
        "operation": "vision_analysis",
        "external_call": True,
        "paid": True,
        "estimated_cost_vnd": Decimal("500"),
        "credential_alias": "secret://openai/codex-video",
        "asset_id": ASSET_ID,
        "asset_hash": ASSET_HASH,
        "input_media_kind": "image",
        "input_width": 1024,
        "input_height": 1024,
        "requested_frames": 1,
        "image_detail": "high",
        "input_token_ceiling": 16_384,
        "max_output_tokens": 4_096,
        "rights_required": True,
        "rights": [],
    }
    payload.update(updates)
    return ProviderCallContext.model_validate(payload)


def test_valid_bundle_is_hash_pinned_and_loads_without_enabling_calls(tmp_path) -> None:
    path, bundle_sha256 = _write_bundle(tmp_path)
    settings = _settings(path, bundle_sha256)
    policy = provider_safety_policy_from_settings(settings)

    assert policy.execution_gate is not None
    assert policy.execution_gate.bundle_sha256 == bundle_sha256
    assert policy.execution_gate.allowed_operations[0].operation_key == OPERATION_ONE
    assert policy.external_execution_enabled is False
    assert policy.paid_execution_enabled is False
    assert policy.global_kill_switch_engaged is True
    assert policy.budget.per_operation_limit_vnd == Decimal("500")
    assert policy.budget.daily_limit_vnd == Decimal("1250")


def test_checked_in_g03_asset_is_hash_bound_and_narrowly_owner_approved() -> None:
    rights_path = (
        REPO_ROOT
        / "docs"
        / "acceptance"
        / "v3-01"
        / "rights"
        / "V3-01-RIGHTS-G03A-001.json"
    )
    asset_path = (
        REPO_ROOT
        / "docs"
        / "acceptance"
        / "v3-01"
        / "assets"
        / "g03-a-owned-vision-test.png"
    )
    record = ProviderRightsEvidence.model_validate_json(rights_path.read_text(encoding="utf-8"))

    assert hashlib.sha256(asset_path.read_bytes()).hexdigest() == record.asset_hash
    assert record.source_type == "internal"
    assert record.commercial_use is True
    assert record.derivative_use is True
    assert record.secret_recorded is False
    assert record.decision == "APPROVED"
    assert record.reviewer == "Owner (GitHub: vangnguyen)"
    assert record.social_platform_use == []
    assert record.license_name == (
        "NPD owner-approved Vision acceptance only; no publishing, training, resale or other use"
    )


def test_loader_rejects_file_tampering_internal_hash_drift_and_wrong_rc(tmp_path) -> None:
    path, bundle_sha256 = _write_bundle(tmp_path)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ProviderGateBundleError, match="SHA-256 mismatch"):
        load_verified_provider_gate_bundle(
            path,
            expected_bundle_sha256=bundle_sha256,
            expected_rc_commit=RC_COMMIT,
            expected_rc_tag=RC_TAG,
        )

    payload = _valid_bundle().model_dump(mode="json")
    payload["credential_approval"]["record"]["notes"] = "tampered"
    path, tampered_sha256 = _write_bundle(tmp_path, payload=payload)
    with pytest.raises(ProviderGateBundleError, match="invalid"):
        load_verified_provider_gate_bundle(
            path,
            expected_bundle_sha256=tampered_sha256,
            expected_rc_commit=RC_COMMIT,
            expected_rc_tag=RC_TAG,
        )

    path, bundle_sha256 = _write_bundle(tmp_path)
    with pytest.raises(ProviderGateBundleError, match="exact RC"):
        load_verified_provider_gate_bundle(
            path,
            expected_bundle_sha256=bundle_sha256,
            expected_rc_commit="d" * 40,
            expected_rc_tag=RC_TAG,
        )


def test_loader_rejects_unapproved_operation_ids_and_scope_drift() -> None:
    payload = _valid_bundle().model_dump(mode="json")
    payload["allowed_operations"][1]["operation_key"] = "unexpected-operation"
    with pytest.raises(ValidationError, match="predeclared G-02-A operation IDs"):
        ProviderGateBundle.model_validate(payload)

    payload = _valid_bundle().model_dump(mode="json")
    payload["expires_at_utc"] = (
        EXPIRES_AT - timedelta(minutes=1)
    ).isoformat()
    with pytest.raises(ValidationError, match="execution scope hash"):
        ProviderGateBundle.model_validate(payload)


def test_g02_config_drift_and_execution_without_bundle_fail_closed(tmp_path) -> None:
    path, bundle_sha256 = _write_bundle(tmp_path)
    with pytest.raises(ValidationError, match="G-02-A envelope"):
        _settings(path, bundle_sha256, provider_retry_max_attempts=2)
    with pytest.raises(ValidationError, match="verified owner-gate bundle"):
        Settings(
            _env_file=None,
            provider_external_execution_enabled=True,
            provider_paid_execution_enabled=True,
            provider_global_kill_switch_engaged=False,
        )


@pytest.mark.asyncio
async def test_verified_scope_enforces_operation_asset_limits_expiry_and_no_fallback(
    tmp_path,
) -> None:
    path, bundle_sha256 = _write_bundle(tmp_path)
    policy = provider_safety_policy_from_settings(
        _settings(path, bundle_sha256, execution=True)
    )
    clock = lambda: ACTIVATES_AT + timedelta(minutes=5)
    controller = ProviderSafetyController(policy, clock=clock)

    first = await controller.execute(
        _context(OPERATION_ONE),
        lambda: _return(Decimal("100")),
        actual_cost=lambda result: result,
    )
    second = await controller.execute(
        _context(OPERATION_TWO),
        lambda: _return(Decimal("100")),
        actual_cost=lambda result: result,
    )
    assert first.receipt.charged_cost_vnd == Decimal("100")
    assert second.receipt.charged_cost_vnd == Decimal("100")
    assert (await controller.preflight(_context(OPERATION_ONE))).code == (
        "DUPLICATE_OPERATION_BLOCKED"
    )
    assert (await controller.preflight(_context("unlisted-operation"))).code == (
        "OPERATION_NOT_ALLOWLISTED"
    )

    fresh = ProviderSafetyController(policy, clock=clock)
    assert (
        await fresh.preflight(_context(OPERATION_ONE, asset_hash="b" * 64))
    ).code == "RIGHTS_ASSET_BINDING_MISMATCH"
    assert (
        await fresh.preflight(_context(OPERATION_ONE, estimated_cost_vnd=Decimal("499")))
    ).code == "COST_RESERVATION_MISMATCH"
    assert (
        await fresh.preflight(_context(OPERATION_ONE, model="automatic-fallback-model"))
    ).code == "MODEL_NOT_AUTHORIZED"
    assert (
        await fresh.preflight(_context(OPERATION_ONE, input_width=2049))
    ).code == "INPUT_DIMENSION_LIMIT_EXCEEDED"

    expired = ProviderSafetyController(policy, clock=lambda: EXPIRES_AT)
    assert (
        await expired.preflight(_context(OPERATION_ONE))
    ).code == "VERIFIED_GATE_EXPIRED"


@pytest.mark.asyncio
async def test_durable_gate_reservation_is_atomic_and_survives_restart(tmp_path) -> None:
    path, bundle_sha256 = _write_bundle(tmp_path)
    policy = provider_safety_policy_from_settings(
        _settings(path, bundle_sha256, execution=True)
    )
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'gate.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    first_repository = ProviderSafetyRepository(session_factory)
    second_repository = ProviderSafetyRepository(session_factory)
    await first_repository.ensure_state()
    clock = lambda: ACTIVATES_AT + timedelta(minutes=10)
    first = DurableProviderSafetyController(
        policy,
        repository=first_repository,
        clock=clock,
    )
    second = DurableProviderSafetyController(
        policy,
        repository=second_repository,
        clock=clock,
    )

    first_result = await first.execute(
        _context(OPERATION_ONE),
        lambda: _return(Decimal("100")),
        actual_cost=lambda result: result,
    )
    assert first_result.receipt.charged_cost_vnd == Decimal("100")
    second_result = await second.execute(
        _context(OPERATION_TWO),
        lambda: _return(Decimal("100")),
        actual_cost=lambda result: result,
    )
    assert second_result.receipt.charged_cost_vnd == Decimal("100")

    restarted = DurableProviderSafetyController(
        policy,
        repository=ProviderSafetyRepository(session_factory),
        clock=clock,
    )
    assert (await restarted.preflight(_context(OPERATION_ONE))).code == (
        "DUPLICATE_OPERATION_BLOCKED"
    )
    assert (await restarted.preflight(_context("third-operation"))).code == (
        "OPERATION_NOT_ALLOWLISTED"
    )
    snapshot = await restarted.snapshot()
    assert snapshot.committed_today_vnd == Decimal("200")
    assert snapshot.reserved_today_vnd == Decimal("0")
    assert snapshot.paid_calls_recorded == 2
    await engine.dispose()


async def _return(value):
    return value
