"""Build and validate the unsigned VF-V0S-B7 RC-19 ASR W1 package.

This generator is deliberately offline.  It has no credential resolver,
database connector, reservation path, gate mount, or provider adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import wave
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "apps/api"))

from app.asr_prompt_profile import prompt_profile_sha256, validate_prompt_profile  # noqa: E402
from app.provider_ci_provenance import EXECUTABLE_TREE_PATHS, executable_tree_sha256  # noqa: E402
from app.provider_gate_loader import (  # noqa: E402
    HashedRightsRecord,
    OpenAIAsrGateBudgetEnvelope,
    ProviderGateBundleError,
    canonical_sha256,
    execution_scope_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_safety import (  # noqa: E402
    ProviderAllowedOperation,
    ProviderRightsEvidence,
    derive_acceptance_lineage_id,
    derive_rc_bound_operation_key,
)
from app.provider_runtime_bootstrap import _git_argv, ledger_database_name  # noqa: E402


TASK = "VF-V0S-B7"
REPOSITORY = "vangnguyen/npd-video-factory-v2"
MAIN = "7ad25cb039c712d450486778d2981d9ef8175385"
MAIN_CI = 34946537685
RC_TAG = "vf-v3-01-rc19"
RC_COMMIT = "dc8ff55322267dfe54674fa6c4003a899bf235ab"
RC_CI = 34875483864
TREE = "432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502"
PROVENANCE = "77445b206e8712f4b24ddc0910ef18b41264154b26189748c60c1fdc4f632171"
LEDGER = "vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed"
LEDGER_SYSTEM_IDENTIFIER = "7685665008963764889"
LEDGER_DATABASE_OID = 16384
LEDGER_ROLE = "vang_nguyen"
LEDGER_SCHEMA = "public"
LEDGER_POSTGRES_VERSION = "16.15"
LEDGER_MIGRATION = "0014_v3_01_27"
PREPARED_AT = "2026-09-15T08:54:13Z"
WINDOW_START_UTC = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)
WINDOW_END_UTC = datetime(2026, 9, 16, 18, 0, tzinfo=timezone.utc)
WINDOW_START_ICT = "2026-09-16T21:00:00+07:00"
WINDOW_END_ICT = "2026-09-17T01:00:00+07:00"
PROFILE_SHA = "9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1"
PROMPT_SHA = "6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48"
PROVIDER_SCOPE_SHA = "4d88c5c59c9b5ca9e8c126f0798356eb6ef82a8db2fe16045434af1d69048349"
CREDENTIAL_ALIAS = "secret://openai/codex-video"
OLD_RC18_OPERATION = (
    "v3-01-rc18-openai-transcription-asr-al-0001-"
    "0e0aa1417c53feb79da3656eaa0d228b059db841496243f533b48607312c8518-call-01"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _git_object(path: str) -> str:
    return subprocess.check_output(
        _git_argv(REPO, "rev-parse", f"HEAD:{path}"), cwd=REPO, text=True
    ).strip()


def _asset(slot: int) -> dict[str, object]:
    suffix = f"{slot:02d}"
    asset_id = f"asset-g03-asr-vi-owned-{suffix}"
    asset_path = f"docs/acceptance/v3-01/assets/g03-asr-vi-owned-{suffix}.wav"
    transcript_path = f"docs/acceptance/v3-01/transcripts/g03-asr-vi-owned-{suffix}.txt"
    rights_path = f"docs/acceptance/v3-01/rights/V3-01-RIGHTS-ASR-{slot:03d}.json"
    absolute_asset = REPO / asset_path
    with wave.open(str(absolute_asset), "rb") as wav:
        channels = wav.getnchannels()
        frame_count = wav.getnframes()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
    duration = Decimal(frame_count) / Decimal(sample_rate)
    modeled_cost = Decimal(frame_count) * Decimal("162") / Decimal(sample_rate * 60)
    rights_payload = json.loads((REPO / rights_path).read_text(encoding="utf-8"))
    rights = ProviderRightsEvidence.model_validate(rights_payload)
    rights_sha = canonical_sha256(rights)
    expected_rights = {
        1: "5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091",
        2: "972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323",
    }[slot]
    assert rights_sha == expected_rights
    assert rights.asset_id == asset_id and rights.asset_hash == _sha256(absolute_asset)
    return {
        "asset_id": asset_id,
        "asset_path": asset_path,
        "asset_sha256": _sha256(absolute_asset),
        "channels": channels,
        "duration_seconds_exact": format(duration, "f"),
        "frame_count": frame_count,
        "modeled_cost_vnd": format(modeled_cost.quantize(Decimal("0.0001")), "f"),
        "new_execution_rights_or_approval_created": False,
        "reference_transcript_path": transcript_path,
        "reference_transcript_sha256": _sha256(REPO / transcript_path),
        "rights_record_canonical_sha256": rights_sha,
        "rights_record_file_sha256": _sha256(REPO / rights_path),
        "rights_record_id": rights.rights_record_id,
        "rights_record_path": rights_path,
        "role": "OPERATION_1_INPUT" if slot == 1 else "FUTURE_SLOT_2_NEGATIVE_INSERTION_GUARD_ONLY_LOCKED",
        "sample_rate_hz": sample_rate,
        "sample_width_bytes": sample_width,
        "size_bytes": absolute_asset.stat().st_size,
        "slot": slot,
    }


def _anchors() -> dict[str, object]:
    return {
        "dual_ci_provenance": "PASS",
        "dual_ci_provenance_sha256": PROVENANCE,
        "executable_rc_ci_run_id": RC_CI,
        "executable_tree_sha256": TREE,
        "governance_main_ci_run_id": MAIN_CI,
        "governance_main_commit": MAIN,
        "main_provenance": "PASS",
        "rc_commit": RC_COMMIT,
        "rc_tag": RC_TAG,
        "repository": REPOSITORY,
    }


def _window() -> dict[str, object]:
    return {
        "budget_day_utc": "2026-09-16",
        "end_ict": WINDOW_END_ICT,
        "end_utc": WINDOW_END_UTC.isoformat(),
        "scheduler_or_countdown_created": False,
        "start_ict": WINDOW_START_ICT,
        "start_utc": WINDOW_START_UTC.isoformat(),
        "status": "PROPOSED_NOT_AUTHORIZED",
        "timezone": "Asia/Ho_Chi_Minh",
    }


def _safety() -> dict[str, object]:
    return {
        "actual_cost_vnd": "0",
        "budget_reserved_vnd": "0",
        "bundle_mounted": False,
        "credential_reads": 0,
        "external_execution": False,
        "kill_switch": "ENGAGED",
        "paid_execution": False,
        "prepared_operation_metadata_write": False,
        "production_business_writes": 0,
        "real_provider_calls": 0,
    }


def build_materials() -> dict[str, bytes]:
    profile_payload = json.loads(
        (REPO / "docs/acceptance/v3-01/contracts/V3-01-25-W1-PROMPT-PROFILE.v1.json").read_text(
            encoding="utf-8"
        )
    )
    profile = validate_prompt_profile(profile_payload)
    assert profile is not None
    assert prompt_profile_sha256(profile) == PROFILE_SHA and profile.prompt_sha256 == PROMPT_SHA

    assets = [_asset(1), _asset(2)]
    rights_wrappers: list[HashedRightsRecord] = []
    for asset in assets:
        rights_payload = json.loads((REPO / str(asset["rights_record_path"])).read_text(encoding="utf-8"))
        rights_wrappers.append(
            HashedRightsRecord.model_validate(
                {"record_sha256": asset["rights_record_canonical_sha256"], "record": rights_payload}
            )
        )

    lineage = derive_acceptance_lineage_id(
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        sequence=1,
    )
    assert ledger_database_name(RC_TAG, lineage) == LEDGER
    operations = tuple(
        ProviderAllowedOperation.model_validate(
            {
                "asset_hash": assets[slot - 1]["asset_sha256"],
                "asset_id": assets[slot - 1]["asset_id"],
                "operation": "flow_a_asr",
                "operation_key": derive_rc_bound_operation_key(
                    rc_tag=RC_TAG,
                    provider_key="openai-transcription",
                    capability="asr",
                    slot=slot,
                    acceptance_lineage_id=lineage,
                ),
                "slot": slot,
            }
        )
        for slot in (1, 2)
    )
    operation_one = operations[0].operation_key
    operation_binding = {
        "acceptance_lineage_id": lineage,
        "capability": "asr",
        "executable_tree_sha256": TREE,
        "ledger_identity": LEDGER,
        "model": "whisper-1",
        "operation_key": operation_one,
        "provider_key": "openai-transcription",
        "rc_commit": RC_COMMIT,
        "rc_tag": RC_TAG,
        "slot": 1,
    }
    operation_binding_sha = canonical_sha256(operation_binding)

    budget = OpenAIAsrGateBudgetEnvelope.model_validate(
        {
            "acceptance_window_limit_vnd": "1250",
            "automatic_retry": False,
            "budget_day_utc": "2026-09-16",
            "controller_hard_timeout_seconds": 120.0,
            "currency": "VND",
            "files_per_operation": 1,
            "max_attempts": 1,
            "max_concurrent_calls": 1,
            "max_duration_seconds": 180.0,
            "max_file_bytes": 25000000,
            "model_fallback": False,
            "per_operation_limit_vnd": "500",
            "provider_http_timeout_seconds": 90.0,
            "requested_language": "vi",
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment", "word"],
            "vnd_per_minute": "162",
        }
    )
    budget_payload = budget.model_dump(mode="json")
    budget_sha = canonical_sha256(budget_payload)
    execution_scope = execution_scope_sha256(
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        credential_alias=CREDENTIAL_ALIAS,
        valid_from_utc=WINDOW_START_UTC,
        expires_at_utc=WINDOW_END_UTC,
        budget=budget,
        allowed_operations=operations,
        rights_record_sha256s=tuple(item.record_sha256 for item in rights_wrappers),
        asr_prompt_profile=profile,
        acceptance_lineage_sequence=1,
        acceptance_lineage_id=lineage,
    )

    approval_slots = {
        gate: {"record_sha256": None, "status": "NOT_CREATED"}
        for gate in ("G-01", "G-02", "G-03")
    }
    gate_template = {
        "acceptance_lineage_id": lineage,
        "acceptance_lineage_sequence": 1,
        "allowed_operations": [item.model_dump(mode="json") for item in operations],
        "asr_prompt_profile": profile.model_dump(mode="json"),
        "budget": budget_payload,
        "bundle_id": "V3-01-GATE-RC19-OPENAI-ASR-W1-LINEAGE-A-PREPARED",
        "capability": "asr",
        "credential_alias": CREDENTIAL_ALIAS,
        "expires_at_utc": WINDOW_END_UTC.isoformat(),
        "model": "whisper-1",
        "operation_2_status": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
        "owner_approval_slots": approval_slots,
        "preparation_status": "PREPARED_NOT_AUTHORIZED",
        "provider_key": "openai-transcription",
        "rc_commit": RC_COMMIT,
        "rc_tag": RC_TAG,
        "rights_records": [item.model_dump(mode="json") for item in rights_wrappers],
        "runtime_loadable": False,
        "valid_from_utc": WINDOW_START_UTC.isoformat(),
        "version": 2,
    }
    gate_bytes = _json_bytes(gate_template)
    preparation_bundle_sha = hashlib.sha256(gate_bytes).hexdigest()

    ledger_readiness = {
        "acceptance_lineage_id": lineage,
        "active_reservation": False,
        "control_seed": "global/revision=0",
        "database_oid": LEDGER_DATABASE_OID,
        "duplicate_or_idempotency_collision": False,
        "exact_attempt_records": 0,
        "exact_operation_records": 0,
        "ledger_custody": "VERIFIED",
        "ledger_identity": LEDGER,
        "migration_head": LEDGER_MIGRATION,
        "operation_consumed": False,
        "operation_key": operation_one,
        "operation_state": "VIRGIN_NOT_REGISTERED / NOT_CONSUMED",
        "postgres_role": LEDGER_ROLE,
        "postgres_schema": LEDGER_SCHEMA,
        "postgres_system_identifier": LEDGER_SYSTEM_IDENTIFIER,
        "postgres_version": LEDGER_POSTGRES_VERSION,
        "prepared_operation_metadata_write": False,
        "provider_request_receipt_exists": False,
        "reserved_vnd": "0",
        "row_counts": {
            "cost_records": 0,
            "idempotency_keys": 0,
            "provider_safety_attempts": 0,
            "provider_safety_budget_alerts": 0,
            "provider_safety_budget_days": 0,
            "provider_safety_circuits": 0,
            "provider_safety_operations": 0,
            "provider_usage": 0,
        },
        "schema": "vf-v0s-b7-ledger-readiness-v1",
        "source_transaction": "REPEATABLE_READ_READ_ONLY",
        "state_before": "VIRGIN_READY_FOR_OPERATION_REBIND",
        "status": "PASS",
        "task_id": TASK,
        "verified_at_utc": PREPARED_AT,
    }

    scope = {
        "acceptance_lineage_id": lineage,
        "acceptance_lineage_sequence": 1,
        "allowed_operations_planning_only": [item.model_dump(mode="json") for item in operations],
        "anchors": _anchors(),
        "budget": budget_payload,
        "budget_canonical_sha256": budget_sha,
        "capability": "asr",
        "credential_alias_reference_only": CREDENTIAL_ALIAS,
        "execution_scope_sha256": execution_scope,
        "immutable_inputs": assets,
        "language": "vi",
        "ledger": {
            "custody": "VERIFIED",
            "identity": LEDGER,
            "operation_binding_sha256": operation_binding_sha,
            "operation_key": operation_one,
            "state": "VIRGIN_NOT_REGISTERED / NOT_CONSUMED",
        },
        "model": "whisper-1",
        "operation_2_status": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
        "owner_approval_slots": approval_slots,
        "owner_manifest_path": "docs/acceptance/v3-01/assets/V3-01-RC11-ASR-ASSET-MANIFEST.json",
        "owner_manifest_sha256": _sha256(
            REPO / "docs/acceptance/v3-01/assets/V3-01-RC11-ASR-ASSET-MANIFEST.json"
        ),
        "prompt_sha256": PROMPT_SHA,
        "proposed_window": _window(),
        "provider_capability_scope_sha256": PROVIDER_SCOPE_SHA,
        "provider_key": "openai-transcription",
        "safety_state": _safety(),
        "schema": "vf-v0s-b7-prepared-scope-v1",
        "status": "PREPARED_NOT_AUTHORIZED",
        "w1_profile_sha256": PROFILE_SHA,
    }
    scope_sha = canonical_sha256(scope)

    operation_manifest = {
        "acceptance_lineage_id": lineage,
        "anchors": _anchors(),
        "budget": budget_payload,
        "capability": "asr",
        "confirmation_token_created": False,
        "execution_authority_created": False,
        "execution_scope_sha256": execution_scope,
        "input": assets[0],
        "language": "vi",
        "ledger_identity": LEDGER,
        "ledger_operation_binding_sha256": operation_binding_sha,
        "ledger_operation_key": operation_one,
        "ledger_state": "VIRGIN_NOT_REGISTERED / NOT_CONSUMED",
        "model": "whisper-1",
        "operation_2_status": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
        "operation_id": operation_one,
        "prepared_bundle_template_sha256": preparation_bundle_sha,
        "prompt_sha256": PROMPT_SHA,
        "proposed_window": _window(),
        "provider_key": "openai-transcription",
        "schema": "vf-v0s-b7-operation-manifest-v1",
        "scope_canonical_sha256": scope_sha,
        "slot": 1,
        "status": "PREPARED_NOT_AUTHORIZED",
        "w1_profile_id": "asr-whisper-vi-w1-v1",
        "w1_profile_sha256": PROFILE_SHA,
    }
    operation_manifest_sha = canonical_sha256(operation_manifest)

    package = {
        "acceptance_lineage_id": lineage,
        "anchors": _anchors(),
        "budget": budget_payload,
        "capability": "asr",
        "execution_scope_sha256": execution_scope,
        "future_execution_evidence_contract": "future-evidence-contract.json",
        "future_preflight_requirements": [
            "Exact RC/tag/tree, current governance main, completed dual-CI provenance and unchanged workflow",
            "Final Owner G-01/G-02/G-03 records, final runtime bundle and authority receipt must be separately created",
            "Durable ledger recheck proves Operation 1 not consumed, no request/attempt/reservation/idempotency collision and Operation 2 locked",
            "Current time must be inside a separately Owner-authorized future window on the same UTC budget day",
            "Only a separately authorized execution task may reserve at most 500 VND, mount, resolve credentials or dispatch",
        ],
        "immutable_input": assets[0],
        "language": "vi",
        "ledger": ledger_readiness,
        "ledger_operation_binding_sha256": operation_binding_sha,
        "model": "whisper-1",
        "modeled_cost_vnd": assets[0]["modeled_cost_vnd"],
        "operation_2_status": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
        "operation_id": operation_one,
        "operation_manifest_canonical_sha256": operation_manifest_sha,
        "owner_gate_approvals_created": False,
        "preparation_bundle_template_sha256": preparation_bundle_sha,
        "prompt_sha256": PROMPT_SHA,
        "proposed_reservation_ceiling_vnd": "500",
        "proposed_window": _window(),
        "provider_availability_precheck_plan": "No authenticated probe in B7; later authorized execution uses only the contract-approved check and no extra call.",
        "provider_key": "openai-transcription",
        "quality_gate": {
            "asset_02_negative_insertion_guard": True,
            "critical_terms_required": 8,
            "critical_terms_total": 8,
            "fuzzy_matching": False,
            "positive_duration_downstream_contract": "UNCHANGED",
            "reference_mutation": False,
            "same_w1_profile_for_both_assets": True,
            "transcript_post_correction": False,
            "wer_max_percent": "15",
        },
        "required_next_owner_decisions": [
            "G-01-ASR RC19 exact execution rebind",
            "G-02-ASR RC19 budget/window rebind",
            "G-03-ASR RC19 rights/time rebind",
            "G-08 governance review",
            "Separate RC19 Operation 1 authority",
        ],
        "safety_state": _safety(),
        "schema": "vf-v0s-b7-operation-preparation-package-v1",
        "scope_canonical_sha256": scope_sha,
        "status": "PREPARED_NOT_AUTHORIZED",
        "terminal_rules": {
            "after_dispatch": "Future execution consumes Operation 1 regardless of outcome, reconciles, re-engages/unmounts and stops for Owner review.",
            "before_dispatch": "Any unverifiable or mismatched binding is BLOCKED_PRE_CALL with zero provider call.",
            "fallback": False,
            "operation_2_automatic_unlock": False,
            "retry": False,
        },
        "w1_profile_id": "asr-whisper-vi-w1-v1",
        "w1_profile_sha256": PROFILE_SHA,
    }
    package_sha = canonical_sha256(package)

    bootstrap_plan = {
        "acceptance_lineage_id": lineage,
        "authority_receipt_sha256": None,
        "authority_status": "NOT_CREATED",
        "bundle_final_runtime_sha256": None,
        "bundle_preparation_template_sha256": preparation_bundle_sha,
        "current_bootstrap_model_valid": False,
        "current_bootstrap_model_blocker": "AWAITING_OWNER_AUTHORITY_AND_FINAL_RUNTIME_BUNDLE",
        "database_identity": LEDGER,
        "execution_scope_sha256": execution_scope,
        "operation_key": operation_one,
        "operation_preparation_package_sha256": package_sha,
        "rc_commit": RC_COMMIT,
        "rc_tag": RC_TAG,
        "schema": "vf-v0s-b7-operation-bound-bootstrap-plan-v1",
        "scope_sha256": scope_sha,
        "status": "PREPARED_NOT_AUTHORIZED",
        "zero_call_b8_inputs_ready": True,
    }

    immutable = {
        "anchors": _anchors(),
        "checked_in_safety_defaults": {
            "openai_transcription_model": "",
            "provider_daily_limit_vnd": "0",
            "provider_external_execution_enabled": False,
            "provider_gate_expected_acceptance_lineage_id": "",
            "provider_global_kill_switch_engaged": True,
            "provider_paid_execution_enabled": False,
            "provider_per_operation_limit_vnd": "0",
            "provider_verified_gate_bundle_enabled": False,
            "provider_verified_gate_bundle_sha256": "",
            "transcription_provider": "fixture",
        },
        "environment_or_credential_values_read": False,
        "inputs": assets,
        "ledger_read_only_accessed": True,
        "observed_at_utc": PREPARED_AT,
        "owner_manifest_path": "docs/acceptance/v3-01/assets/V3-01-RC11-ASR-ASSET-MANIFEST.json",
        "owner_manifest_sha256": scope["owner_manifest_sha256"],
        "owner_manifest_validation": "UNCHANGED_OWNER_CONFIRMED_RIGHTS; NO_NEW_EXECUTION_APPROVAL",
        "profile_sha256": PROFILE_SHA,
        "prompt_sha256": PROMPT_SHA,
        "status": "PASS",
        "task_id": TASK,
        "tree_recompute": [TREE, TREE],
    }

    pricing = {
        "accounting_fx_not_market_fx": True,
        "actual_provider_cost_new_task_vnd": "0",
        "asset_01_modeled_vnd": assets[0]["modeled_cost_vnd"],
        "asset_02_planning_modeled_vnd": assets[1]["modeled_cost_vnd"],
        "calculation": "duration_seconds / 60 * 0.006 USD/minute * 27000 fixed accounting VND/USD",
        "fixed_accounting_vnd_per_usd": "27000",
        "hard_180_seconds_modeled_vnd": "486",
        "model": "whisper-1",
        "observed_at_utc": PREPARED_AT,
        "official_source": "https://developers.openai.com/api/docs/models/whisper-1",
        "per_operation_ceiling_vnd": "500",
        "price_or_fx_drift_policy": "FAIL_CLOSED_OWNER_REBIND_REQUIRED",
        "price_usd_per_minute": "0.006",
        "reservation_performed": False,
        "status": "CURRENT_PUBLIC_PRICE_REVALIDATED; RC19 BUDGET NOT_AUTHORIZED",
        "task_id": TASK,
        "two_asset_planning_modeled_vnd": format(
            Decimal(str(assets[0]["modeled_cost_vnd"])) + Decimal(str(assets[1]["modeled_cost_vnd"])),
            "f",
        ),
        "vnd_per_minute": "162",
        "window_ceiling_vnd": "1250",
    }

    future_evidence = {
        "anchors": _anchors(),
        "execution_scope_sha256": execution_scope,
        "new_real_provider_receipt_present": False,
        "operation_id": operation_one,
        "preparation_bundle_template_sha256": preparation_bundle_sha,
        "prompt_sha256": PROMPT_SHA,
        "required_outputs": [
            "fresh preflight bindings, time/day, ledger virgin state, Operation 2 locked",
            "request SHA-256, provider request ID and response SHA-256",
            "actual retained transcript and raw/canonical timestamp provenance",
            "W1 profile and prompt request binding",
            "usage, latency, timeout phase, actual cost or explicit UNKNOWN",
            "durable operation/attempt/budget/circuit and reservation reconciliation",
            "duplicate/idempotency and RightsRecord/asset/reference binding",
            "WER <=15%, exact critical terms 8/8 and insertion guards",
            "secret containment and canonical evidence SHA-256 manifest",
            "post-run kill switch engaged, bundle unmounted, Operation 2 locked and STOP",
        ],
        "schema": "vf-v0s-b7-future-evidence-requirements-v1",
        "scope_canonical_sha256": scope_sha,
        "status": "REQUIREMENTS_ONLY_NO_NEW_PROVIDER_EVIDENCE",
        "w1_profile_sha256": PROFILE_SHA,
    }

    historical = {
        "historical_authority_receipt_sha256": "9a2750d2f6f8db6e5a130726f56e216873c202b59e5408bcca42a4607c87e397",
        "historical_bundle_sha256": "bb0f588c1465386e2be4caadf578dc10bb23020061a01c82ff4beab8b6fc2743",
        "historical_execution_scope_sha256": "64d69549493743774e035f04efb99d890f86799b79a9bbef06a7ee26c8b5cf77",
        "historical_files_modified": False,
        "historical_operation_id": OLD_RC18_OPERATION,
        "historical_rc": "vf-v3-01-rc18",
        "historical_scope_sha256": "bf23f78f972f319eba224b7ca4d988dfe5edf0f7bbaa1381cc80e916dfd814d5",
        "operation_identity_authority_scope_bundle_window_reservation_transferred": False,
        "schema": "vf-v0s-b7-historical-package-invalidation-v1",
        "status": "HISTORICAL_REFERENCE_ONLY / INVALID_FOR_RC19",
    }

    artifacts: dict[str, object] = {
        "bootstrap-binding-plan.json": bootstrap_plan,
        "future-evidence-contract.json": future_evidence,
        "gate-template.json": gate_template,
        "historical-package-invalidation.json": historical,
        "immutable-input-validation.json": immutable,
        "ledger-readiness.json": ledger_readiness,
        "operation-1-manifest.json": operation_manifest,
        "operation-preparation-package.json": package,
        "pricing-basis.json": pricing,
        "scope-candidate.json": scope,
    }
    rendered = {name: _json_bytes(value) for name, value in artifacts.items()}
    hashes = {
        "acceptance_lineage_id": lineage,
        "canonicalization": "UTF-8, Unicode retained, sorted keys, compact separators for canonical SHA; artifact hashes cover exact pretty UTF-8 LF bytes.",
        "execution_scope_sha256": execution_scope,
        "files_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(rendered.items())},
        "ledger_operation_binding_sha256": operation_binding_sha,
        "operation_id": operation_one,
        "operation_manifest_canonical_sha256": operation_manifest_sha,
        "operation_preparation_package_canonical_sha256": package_sha,
        "preparation_bundle_template_sha256": preparation_bundle_sha,
        "prompt_utf8_sha256": PROMPT_SHA,
        "schema": "vf-v0s-b7-prepared-hashes-v1",
        "scope_canonical_sha256": scope_sha,
        "status": "PREPARED_NOT_AUTHORIZED",
        "w1_profile_canonical_sha256": PROFILE_SHA,
    }
    rendered["prepared-material-hashes.json"] = _json_bytes(hashes)

    readme = f"""# RC-19 ASR W1 Operation 1 preparation package

Status: **PREPARED_NOT_AUTHORIZED**. This package creates no Owner gate record,
authority receipt, confirmation token, active window, mounted bundle, reservation,
credential read or provider call.

## Fresh identity

- RC: `{RC_TAG}` -> `{RC_COMMIT}`
- Governance main: `{MAIN}`
- Executable tree: `{TREE}`
- Dual-CI provenance: PASS, `{PROVENANCE}`
- Lineage: `{lineage}`
- Operation 1: `{operation_one}`
- Canonical ledger: `{LEDGER}`
- Ledger state: `VIRGIN_NOT_REGISTERED / NOT_CONSUMED`
- Ledger operation binding: `{operation_binding_sha}`

The operation name follows the existing identity-v2 contract. The scope and
manifest bind governance/provenance/tree, ledger, W1 profile/prompt, assets,
references, RightsRecords, proposed budget/window and terminal rules. RC-18
operation-specific identity, scope, bundle, authority, window and reservation
are historical only and were not transferred.

## Prepared hashes

- execution-scope SHA: `{execution_scope}`
- scope SHA: `{scope_sha}`
- operation manifest SHA: `{operation_manifest_sha}`
- preparation bundle/template SHA: `{preparation_bundle_sha}`

`gate-template.json` is intentionally not loader-valid: G-01/G-02/G-03 and
final runtime/authority material do not exist. `bootstrap-binding-plan.json`
keeps those slots unbound. A later bounded task must not substitute this
preparation hash for a final runtime bundle or authority receipt.

## Proposal only

- Window: **2026-09-16 21:00 -> 2026-09-17 01:00 ICT**
  (2026-09-16 14:00 -> 18:00 UTC), `PROPOSED_NOT_AUTHORIZED`.
- 500 VND per operation; 1,250 VND window; modeled asset-01 cost 326.3004 VND.
- One attempt, concurrency one, provider/controller timeout 90s/120s,
  retry/fallback 0/0.

Official OpenAI documentation observed on 2026-09-15 lists `whisper-1` at
$0.006 per minute. The fixed 27,000 VND/USD value is the already approved
accounting basis, not a live FX claim. Any price/FX/binding drift fails closed.

Kill switch ENGAGED; bundle UNMOUNTED; Operation 2 NOT_APPROVED / LOCKED /
NOT_TRANSFERRED. Credential reads, budget reserved, provider calls, production
business writes and actual cost are all zero.

**NEXT_SAFE_ACTION: VF-V0S-B8 — zero-call operation-bound bootstrap
qualification. Stop before Owner approvals, authority/window activation,
bundle mount, credentials, reservation or provider dispatch.**
"""
    rendered["README.md"] = readme.encode("utf-8")
    return rendered


def validate_materials(materials: dict[str, bytes] | None = None) -> dict[str, object]:
    expected = build_materials() if materials is None else materials
    mismatches = []
    for name, raw in expected.items():
        path = HERE / name
        if not path.is_file() or path.read_bytes() != raw:
            mismatches.append(name)
    hashes = json.loads(expected["prepared-material-hashes.json"])
    gate = json.loads(expected["gate-template.json"])
    scope = json.loads(expected["scope-candidate.json"])
    package = json.loads(expected["operation-preparation-package.json"])
    manifest = json.loads(expected["operation-1-manifest.json"])
    ledger = json.loads(expected["ledger-readiness.json"])
    bootstrap = json.loads(expected["bootstrap-binding-plan.json"])
    assert gate["runtime_loadable"] is False
    assert all(item["status"] == "NOT_CREATED" for item in gate["owner_approval_slots"].values())
    assert package["status"] == scope["status"] == manifest["status"] == "PREPARED_NOT_AUTHORIZED"
    assert package["owner_gate_approvals_created"] is False
    assert bootstrap["authority_receipt_sha256"] is None and bootstrap["bundle_final_runtime_sha256"] is None
    assert bootstrap["current_bootstrap_model_valid"] is False
    assert ledger["exact_operation_records"] == ledger["exact_attempt_records"] == 0
    assert ledger["operation_consumed"] is ledger["provider_request_receipt_exists"] is False
    assert ledger["active_reservation"] is ledger["duplicate_or_idempotency_collision"] is False
    assert ledger["prepared_operation_metadata_write"] is False
    assert hashes["preparation_bundle_template_sha256"] != "bb0f588c1465386e2be4caadf578dc10bb23020061a01c82ff4beab8b6fc2743"
    assert OLD_RC18_OPERATION not in expected["operation-1-manifest.json"].decode("utf-8")
    with _loader_rejection(gate):
        load_verified_provider_gate_bundle(
            HERE / "gate-template.json",
            expected_bundle_sha256=hashes["preparation_bundle_template_sha256"],
            expected_rc_commit=RC_COMMIT,
            expected_rc_tag=RC_TAG,
            expected_acceptance_lineage_id=gate["acceptance_lineage_id"],
        )
    objects = {path: _git_object(path) for path in EXECUTABLE_TREE_PATHS}
    assert executable_tree_sha256(objects) == TREE
    return {
        "checked_files": len(expected),
        "credential_reads": 0,
        "mismatches": mismatches,
        "operation_authority_created": False,
        "prepared_operation_metadata_write": False,
        "provider_calls": 0,
        "reservation_vnd": "0",
        "status": "PASS" if not mismatches else "FAIL",
        "task_id": TASK,
    }


class _loader_rejection:
    def __init__(self, gate: dict[str, object]):
        self.gate = gate

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            raise AssertionError("UNSIGNED_GATE_TEMPLATE_BECAME_RUNTIME_LOADABLE")
        if not issubclass(exc_type, ProviderGateBundleError):
            return False
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    materials = build_materials()
    if args.write:
        HERE.mkdir(parents=True, exist_ok=True)
        for name, raw in materials.items():
            (HERE / name).write_bytes(raw)
    result = validate_materials(materials)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
