from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import struct
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.auto_edit_models import MediaMetadata
from app.config import Settings
from app.db import create_engine, create_session_factory
from app.openai_vision_provider import FFmpegVisionFrameExtractor, OpenAIVisionProvider
from app.provider_gate_loader import (
    ProviderGateBundle,
    execution_scope_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_safety import ProviderCallContext, ProviderSafetyBlocked, provider_safety_policy_from_settings
from app.provider_safety_db import (
    ProviderSafetyAttemptORM,
    ProviderSafetyBudgetDayORM,
    ProviderSafetyCircuitORM,
    ProviderSafetyOperationORM,
)
from app.provider_safety_durable import DurableProviderSafetyController
from app.provider_safety_repository import ProviderSafetyRepository


RC_TAG = "vf-v3-01-rc3"
RC_COMMIT = "adde8d9c5a7f608db80cbd9d21aecd45f721065e"
GOVERNANCE_MAIN_COMMIT = "a73bad37f1f3aa7c2347e6a76503246a46d3c112"
OPERATION_KEY = "v3-01-g03a-openai-vision-call-01"
OPERATION_TWO = "v3-01-g03a-openai-vision-call-02"
PROVIDER_KEY = "openai-vision"
MODEL = "gpt-5-mini"
CAPABILITY = "vision"
CREDENTIAL_ALIAS = "secret://openai/codex-video"
ASSET_ID = "asset-g03-a-owned-vision-test"
ASSET_SHA256 = "a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e"
EXECUTION_SCOPE_SHA256 = "a5ba3e0e1e39384cb1d6beb892b3c85a2266ea30be436faed529d6fdfe8aa9a0"
BUNDLE_SHA256 = "da4450ce9f3c6f2015d2fbea3af8ca2ffb108c13dd53daafdad294570ecf4d83"
VALID_FROM = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)
EXPIRES_AT = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


class GateConditionError(RuntimeError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise GateConditionError(code)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    require(payload.startswith(b"\x89PNG\r\n\x1a\n"), "ASSET_NOT_PNG")
    require(len(payload) >= 24 and payload[12:16] == b"IHDR", "PNG_IHDR_MISSING")
    width, height = struct.unpack(">II", payload[16:24])
    require(width > 0 and height > 0, "PNG_DIMENSIONS_INVALID")
    return width, height


def decimal_text(value: object) -> str | None:
    if value is None:
        return None
    return str(Decimal(value))


def timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    current = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def operation_row(row: ProviderSafetyOperationORM | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "operation_key": row.operation_key,
        "provider_key": row.provider_key,
        "capability": row.capability,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "operation": row.operation,
        "status": row.status,
        "external_call": row.external_call,
        "paid": row.paid,
        "currency": row.currency,
        "estimated_cost_vnd": decimal_text(row.estimated_cost_vnd),
        "reserved_vnd": decimal_text(row.reserved_vnd),
        "charged_vnd": decimal_text(row.charged_vnd),
        "budget_day": row.budget_day.isoformat(),
        "attempt_count": row.attempt_count,
        "failure_code": row.failure_code,
        "created_at": timestamp(row.created_at),
        "updated_at": timestamp(row.updated_at),
        "completed_at": timestamp(row.completed_at),
    }


def attempt_row(row: ProviderSafetyAttemptORM) -> dict[str, object]:
    return {
        "usage_id": row.usage_id,
        "operation_key": row.operation_key,
        "attempt": row.attempt,
        "status": row.status,
        "currency": row.currency,
        "estimated_cost_vnd": decimal_text(row.estimated_cost_vnd),
        "actual_cost_vnd": decimal_text(row.actual_cost_vnd),
        "charged_cost_vnd": decimal_text(row.charged_cost_vnd),
        "cost_status": row.cost_status,
        "retryable": row.retryable,
        "error_code": row.error_code,
        "created_at": timestamp(row.created_at),
        "completed_at": timestamp(row.completed_at),
    }


async def read_ledger(session_factory, budget_day: date) -> dict[str, object]:
    async with session_factory() as session:
        first = await session.get(ProviderSafetyOperationORM, OPERATION_KEY)
        second = await session.get(ProviderSafetyOperationORM, OPERATION_TWO)
        attempts = list(
            (
                await session.scalars(
                    select(ProviderSafetyAttemptORM)
                    .where(ProviderSafetyAttemptORM.operation_key == OPERATION_KEY)
                    .order_by(ProviderSafetyAttemptORM.attempt)
                )
            ).all()
        )
        budget = await session.get(ProviderSafetyBudgetDayORM, budget_day)
        circuit = await session.get(ProviderSafetyCircuitORM, (PROVIDER_KEY, CAPABILITY))
    return {
        "operation_1": operation_row(first),
        "operation_2": operation_row(second),
        "attempts": [attempt_row(item) for item in attempts],
        "budget": (
            {
                "budget_day": budget.budget_day.isoformat(),
                "currency": budget.currency,
                "daily_limit_vnd": decimal_text(budget.daily_limit_vnd),
                "committed_vnd": decimal_text(budget.committed_vnd),
                "reserved_vnd": decimal_text(budget.reserved_vnd),
                "updated_at": timestamp(budget.updated_at),
            }
            if budget is not None
            else None
        ),
        "circuit": (
            {
                "provider_key": circuit.provider_key,
                "capability": circuit.capability,
                "state": circuit.state,
                "consecutive_failures": circuit.consecutive_failures,
                "opened_at": timestamp(circuit.opened_at),
                "updated_at": timestamp(circuit.updated_at),
            }
            if circuit is not None
            else None
        ),
    }


def verify_authority(path: Path) -> dict[str, object]:
    expected_hash = os.environ["EXPECTED_OPERATION_AUTHORITY_SHA256"]
    raw = path.read_bytes()
    require(hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_hash), "OPERATION_AUTHORITY_HASH_MISMATCH")
    payload = json.loads(raw.decode("utf-8"))
    exact = {
        "decision": "APPROVED",
        "operation_key": OPERATION_KEY,
        "rc_tag": RC_TAG,
        "rc_commit": RC_COMMIT,
        "governance_main_commit": GOVERNANCE_MAIN_COMMIT,
        "provider_key": PROVIDER_KEY,
        "model": MODEL,
        "capability": CAPABILITY,
        "credential_alias": CREDENTIAL_ALIAS,
        "asset_sha256": ASSET_SHA256,
        "execution_scope_sha256": EXECUTION_SCOPE_SHA256,
        "valid_from_utc": "2026-08-28T14:00:00Z",
        "expires_at_utc": "2026-08-28T18:00:00Z",
        "operation_2_authorized": False,
        "deployment_authorized": False,
        "public_ingress_authorized": False,
        "publishing_authorized": False,
        "production_analytics_authorized": False,
    }
    for key, value in exact.items():
        require(payload.get(key) == value, f"OPERATION_AUTHORITY_SCOPE_MISMATCH:{key}")
    limits = payload.get("limits")
    require(isinstance(limits, dict), "OPERATION_AUTHORITY_LIMITS_MISSING")
    expected_limits = {
        "images": 1,
        "max_dimension_pixels": 2048,
        "image_detail": "high",
        "input_token_ceiling": 16384,
        "max_output_tokens": 4096,
        "reservation_vnd": "500",
        "timeout_seconds": 60,
        "max_concurrent_calls": 1,
        "max_attempts": 1,
        "automatic_retry": False,
        "model_fallback": False,
    }
    require(limits == expected_limits, "OPERATION_AUTHORITY_LIMITS_MISMATCH")
    return payload


async def main() -> int:
    bundle_path = Path(os.environ["GATE_BUNDLE_PATH"])
    authority_path = Path(os.environ["OPERATION_AUTHORITY_PATH"])
    asset_path = Path(os.environ["ASSET_PATH"])
    evidence_path = Path(os.environ["EVIDENCE_PATH"])
    database_url = os.environ["DATABASE_URL"]
    runtime_image_id = os.environ["RUNTIME_IMAGE_ID"]
    exact_main_ci_run_id = os.environ["EXACT_MAIN_CI_RUN_ID"]
    exact_main_ci_conclusion = os.environ["EXACT_MAIN_CI_CONCLUSION"]

    require(not evidence_path.exists(), "EVIDENCE_ALREADY_EXISTS")
    require(os.environ.get("EXPECTED_RUNTIME_COMMIT") == RC_COMMIT, "RUNTIME_COMMIT_MISMATCH")
    require(os.environ.get("EXPECTED_RUNTIME_TAG") == RC_TAG, "RUNTIME_TAG_MISMATCH")
    require(os.environ.get("EXPECTED_GOVERNANCE_MAIN_COMMIT") == GOVERNANCE_MAIN_COMMIT, "GOVERNANCE_MAIN_MISMATCH")
    require(exact_main_ci_run_id == "33175813324", "EXACT_MAIN_CI_RUN_MISMATCH")
    require(exact_main_ci_conclusion == "success", "EXACT_MAIN_CI_NOT_GREEN")
    require(sha256_file(bundle_path) == BUNDLE_SHA256, "GATE_BUNDLE_HASH_MISMATCH")
    require(sha256_file(asset_path) == ASSET_SHA256, "ASSET_HASH_MISMATCH")
    authority = verify_authority(authority_path)

    bundle = ProviderGateBundle.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    scope_hash = execution_scope_sha256(
        rc_tag=bundle.rc_tag,
        rc_commit=bundle.rc_commit,
        provider_key=bundle.provider_key,
        model=bundle.model,
        capability=bundle.capability,
        credential_alias=bundle.credential_alias,
        valid_from_utc=bundle.valid_from_utc,
        expires_at_utc=bundle.expires_at_utc,
        budget=bundle.budget,
        rights_record_sha256=bundle.rights_record.record_sha256,
        allowed_operations=bundle.allowed_operations,
    )
    require(hmac.compare_digest(scope_hash, EXECUTION_SCOPE_SHA256), "EXECUTION_SCOPE_HASH_MISMATCH")
    gate_scope = load_verified_provider_gate_bundle(
        bundle_path,
        expected_bundle_sha256=BUNDLE_SHA256,
        expected_rc_commit=RC_COMMIT,
        expected_rc_tag=RC_TAG,
    )
    require(gate_scope.operation_for(OPERATION_KEY) is not None, "OPERATION_1_NOT_ALLOWLISTED")
    require(gate_scope.operation_for(OPERATION_TWO) is not None, "OPERATION_2_NOT_PREDECLARED")

    width, height = png_dimensions(asset_path)
    require(max(width, height) <= 2048, "ASSET_DIMENSION_LIMIT_EXCEEDED")
    now = datetime.now(timezone.utc)
    require(VALID_FROM <= now < EXPIRES_AT, "ACCEPTANCE_WINDOW_INACTIVE")

    api_key = sys.stdin.readline().strip()
    require(bool(api_key), "CREDENTIAL_ALIAS_UNRESOLVED")

    settings = Settings(
        _env_file=None,
        app_env="acceptance",
        vision_fixture_enabled=False,
        vision_provider="openai",
        openai_vision_model=MODEL,
        openai_vision_credential_alias=CREDENTIAL_ALIAS,
        openai_vision_image_detail="high",
        openai_vision_max_frames=1,
        openai_vision_max_dimension_pixels=2048,
        openai_vision_input_token_ceiling=16_384,
        openai_vision_max_output_tokens=4_096,
        openai_vision_estimated_cost_vnd=Decimal("500"),
        openai_vision_input_vnd_per_million_tokens=Decimal("6565"),
        openai_vision_cached_input_vnd_per_million_tokens=Decimal("656.5"),
        openai_vision_output_vnd_per_million_tokens=Decimal("52520"),
        provider_verified_gate_bundle_enabled=True,
        provider_verified_gate_bundle_file=bundle_path,
        provider_verified_gate_bundle_sha256=BUNDLE_SHA256,
        provider_gate_expected_rc_commit=RC_COMMIT,
        provider_gate_expected_rc_tag=RC_TAG,
        provider_external_execution_enabled=True,
        provider_paid_execution_enabled=True,
        provider_global_kill_switch_engaged=False,
        provider_budget_currency="VND",
        provider_per_operation_limit_vnd=Decimal("500"),
        provider_daily_limit_vnd=Decimal("1250"),
        provider_retry_max_attempts=1,
        provider_request_timeout_seconds=60,
        provider_retry_max_elapsed_seconds=60,
        provider_max_concurrent_calls=1,
        openai_base_url="https://api.openai.com",
        openai_api_key="",
    )
    policy = provider_safety_policy_from_settings(settings)
    require(policy.execution_gate is not None, "VERIFIED_GATE_NOT_LOADED")
    require(policy.external_execution_enabled, "EXTERNAL_EXECUTION_NOT_ENABLED")
    require(policy.paid_execution_enabled, "PAID_EXECUTION_NOT_ENABLED")
    require(not policy.global_kill_switch_engaged, "KILL_SWITCH_STILL_ENGAGED")
    require(policy.retry.max_attempts == 1, "RETRY_LIMIT_MISMATCH")
    require(policy.retry.max_concurrent_calls == 1, "CONCURRENCY_LIMIT_MISMATCH")

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    repository = ProviderSafetyRepository(session_factory)
    await repository.ensure_state()
    before = await read_ledger(session_factory, gate_scope.budget_day_utc)
    require(before["operation_1"] is None, "OPERATION_1_PREEXISTS")
    require(before["operation_2"] is None, "OPERATION_2_PREEXISTS")
    require(before["budget"] is None, "ACCEPTANCE_BUDGET_PREEXISTS")

    controller = DurableProviderSafetyController(policy, repository=repository)
    adapter = OpenAIVisionProvider(
        credential_alias=CREDENTIAL_ALIAS,
        credential_resolver=lambda alias: api_key if alias == CREDENTIAL_ALIAS else "",
        frame_extractor=FFmpegVisionFrameExtractor(max_frames=1),
        model=MODEL,
        base_url="https://api.openai.com",
        timeout_seconds=60,
        image_detail="high",
        max_dimension_pixels=2048,
        input_token_ceiling=16_384,
        max_output_tokens=4_096,
        estimated_cost_vnd=Decimal("500"),
        input_vnd_per_million_tokens=Decimal("6565"),
        cached_input_vnd_per_million_tokens=Decimal("656.5"),
        output_vnd_per_million_tokens=Decimal("52520"),
    )
    metadata = MediaMetadata(
        media_kind="image",
        detected_content_type="image/png",
        format_name="png",
        width=width,
        height=height,
    )
    context = ProviderCallContext(
        operation_key=OPERATION_KEY,
        workspace_id="wsp_v3_01_rc3_acceptance",
        project_id="prj_v3_01_rc3_acceptance",
        provider_key=PROVIDER_KEY,
        model=MODEL,
        capability=CAPABILITY,
        operation="vision_analysis",
        external_call=True,
        paid=True,
        estimated_cost_vnd=Decimal("500"),
        credential_alias=CREDENTIAL_ALIAS,
        asset_id=ASSET_ID,
        asset_hash=ASSET_SHA256,
        input_media_kind="image",
        input_width=width,
        input_height=height,
        requested_frames=1,
        image_detail="high",
        input_token_ceiling=16_384,
        max_output_tokens=4_096,
        rights_required=True,
        rights=[],
    )

    started_at = datetime.now(timezone.utc)
    result = None
    receipt = None
    execution_error_code = None
    try:
        execution = await controller.execute(
            context,
            lambda: adapter.analyze(
                asset_path,
                metadata=metadata,
                scenes=[],
                asset_id=ASSET_ID,
                checksum_sha256=ASSET_SHA256,
                sample_interval_seconds=4,
            ),
            actual_cost=lambda value: value.actual_cost_vnd,
        )
        result = execution.value
        receipt = execution.receipt
    except ProviderSafetyBlocked as exc:
        execution_error_code = exc.code
    completed_at = datetime.now(timezone.utc)

    duplicate_decision = await controller.preflight(context)
    after = await read_ledger(session_factory, gate_scope.budget_day_utc)
    snapshot = await controller.snapshot()
    await engine.dispose()

    operation = after["operation_1"]
    attempts = after["attempts"]
    provider_provenance = result.provenance if result is not None else None
    cost_receipt = provider_provenance.get("cost_receipt") if provider_provenance else None
    frames = [frame.model_dump(mode="json") for frame in result.frames] if result is not None else []

    checks = {
        "exact_rc3_runtime": True,
        "exact_main_governance_ci_pass": True,
        "bundle_hash_match": True,
        "execution_scope_hash_match": True,
        "operation_authority_hash_match": True,
        "window_active_at_dispatch": VALID_FROM <= started_at < EXPIRES_AT,
        "one_owned_image": sha256_file(asset_path) == ASSET_SHA256,
        "dimensions_within_limit": max(width, height) <= 2048,
        "single_attempt": len(attempts) == 1 and attempts[0]["attempt"] == 1,
        "no_retry": receipt is not None and receipt.retries == 0,
        "no_model_fallback": provider_provenance is not None
        and provider_provenance.get("model_requested") == MODEL,
        "structured_schema_pass": result is not None and len(frames) == 1,
        "request_hash_present": provider_provenance is not None
        and bool(provider_provenance.get("request_sha256")),
        "response_hash_present": provider_provenance is not None
        and bool(provider_provenance.get("response_sha256")),
        "usage_receipt_actual": isinstance(cost_receipt, dict)
        and cost_receipt.get("status") == "actual"
        and cost_receipt.get("actual_cost_vnd") is not None,
        "actual_cost_within_reservation": receipt is not None
        and receipt.charged_cost_vnd <= Decimal("500"),
        "rights_bound": receipt is not None and receipt.rights_allowed,
        "durable_operation_succeeded": operation is not None
        and operation["status"] == "succeeded",
        "reservation_exactly_500_vnd": operation is not None
        and Decimal(str(operation["reserved_vnd"])) == Decimal("500"),
        "duplicate_blocked": duplicate_decision.code == "DUPLICATE_OPERATION_BLOCKED",
        "operation_2_absent": after["operation_2"] is None,
        "circuit_closed": after["circuit"] is not None
        and after["circuit"]["state"] == "closed",
        "secret_recorded_false": provider_provenance is not None
        and provider_provenance.get("secret_recorded") is False,
    }
    verdict = "PASS" if result is not None and all(checks.values()) else "REVIEW_REQUIRED"
    evidence = {
        "evidence_version": 1,
        "evidence_class": "real-provider acceptance candidate; not production-path acceptance",
        "verdict": verdict,
        "production_verdict": "NO-GO",
        "runtime": {
            "rc_tag": RC_TAG,
            "rc_commit": RC_COMMIT,
            "runtime_image_id": runtime_image_id,
            "governance_main_commit": GOVERNANCE_MAIN_COMMIT,
            "exact_main_ci_run_id": exact_main_ci_run_id,
            "exact_main_ci_conclusion": exact_main_ci_conclusion,
            "public_ingress": False,
            "production_deploy": False,
            "publishing": False,
            "production_analytics": False,
        },
        "authority": {
            "operation_authority_sha256": os.environ["EXPECTED_OPERATION_AUTHORITY_SHA256"],
            "approved_by": authority["approved_by"],
            "operation_key": OPERATION_KEY,
            "operation_2_authorized": False,
            "gate_bundle_sha256": BUNDLE_SHA256,
            "execution_scope_sha256": EXECUTION_SCOPE_SHA256,
            "approval_ids": {
                "G-01": gate_scope.credential_approval_id,
                "G-02": gate_scope.budget_approval_id,
                "G-03": gate_scope.rights_approval_id,
            },
            "rights_record_sha256": gate_scope.rights_record_sha256,
        },
        "input": {
            "asset_id": ASSET_ID,
            "asset_sha256": ASSET_SHA256,
            "media_kind": "image",
            "content_type": "image/png",
            "width": width,
            "height": height,
            "frames": 1,
            "detail": "high",
        },
        "execution": {
            "started_at_utc": started_at.isoformat(),
            "completed_at_utc": completed_at.isoformat(),
            "provider_key": PROVIDER_KEY,
            "model_requested": MODEL,
            "capability": CAPABILITY,
            "timeout_seconds": 60,
            "max_attempts": 1,
            "max_concurrent_calls": 1,
            "reservation_vnd": "500",
            "error_code": execution_error_code,
            "provider_receipt": receipt.model_dump(mode="json") if receipt is not None else None,
            "provider_provenance": provider_provenance,
            "structured_frames": frames,
        },
        "durable_safety": {
            "backend": "postgresql",
            "ledger": after,
            "duplicate_preflight": duplicate_decision.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
        },
        "checks": checks,
        "secret_leakage_detected": False,
    }
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2)
    require(api_key not in serialized, "SECRET_VALUE_LEAKED_TO_EVIDENCE")
    require(re.search(r"sk-[A-Za-z0-9_-]{20,}", serialized) is None, "SECRET_PATTERN_LEAKED_TO_EVIDENCE")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(serialized + "\n", encoding="utf-8")
    evidence_sha256 = sha256_file(evidence_path)
    print(
        json.dumps(
            {
                "verdict": verdict,
                "operation_key": OPERATION_KEY,
                "attempts": len(attempts),
                "charged_cost_vnd": receipt.model_dump(mode="json")["charged_cost_vnd"]
                if receipt is not None
                else None,
                "duplicate_code": duplicate_decision.code,
                "operation_2_absent": after["operation_2"] is None,
                "evidence_sha256": evidence_sha256,
            },
            sort_keys=True,
        )
    )
    return 0 if verdict == "PASS" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except GateConditionError as exc:
        print(json.dumps({"verdict": "BLOCKED_0_CALL", "code": str(exc)}, sort_keys=True))
        raise SystemExit(2)
