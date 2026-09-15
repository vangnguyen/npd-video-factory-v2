from __future__ import annotations

import copy
import importlib.util
import json
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.provider_gate_loader import (
    OpenAIAsrGateBundle,
    ProviderApprovalRecord,
    canonical_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_runtime_bootstrap import BootstrapLedgerBinding


REPO = Path(__file__).resolve().parents[3]
HERE = REPO / "docs/acceptance/v3-01/authority/vf-v0s-b9-rc19-asr-w1-op1"
spec = importlib.util.spec_from_file_location("vf_v0s_b9", HERE / "materialize_and_validate.py")
assert spec is not None and spec.loader is not None
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def forbid_provider_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "create_connection", review.no_network)
    monkeypatch.setattr(socket.socket, "connect", review.no_network)


def test_full_b9_offline_materialization_audit() -> None:
    result = review.validate_materials()
    assert result["status"] == "PASS"
    assert result["gate_loader"] == "PASS / VALID_IN_MEMORY_NOT_MOUNTED"
    assert result["authority_status"] == "GRANTED_NOT_CONSUMED"
    assert result["operation_1_consumed"] is result["bundle_mounted"] is False
    assert result["kill_switch"] == "ENGAGED"
    assert result["credential_reads"] == result["provider_calls"] == 0
    assert result["production_business_writes"] == 0
    assert result["budget_reserved_vnd"] == result["actual_cost_vnd"] == "0"


def test_final_bundle_reproduces_twice_and_real_loader_passes() -> None:
    one = review.build_materials()[review.BUNDLE_PATH]
    two = review.build_materials()[review.BUNDLE_PATH]
    assert one == two == review.BUNDLE_PATH.read_bytes()
    manifest = _json(HERE / "manifest.json")
    scope = load_verified_provider_gate_bundle(
        review.BUNDLE_PATH,
        expected_bundle_sha256=manifest["final_runtime_bundle_sha256"],
        expected_rc_commit=review.RC_COMMIT,
        expected_rc_tag=review.RC_TAG,
        expected_acceptance_lineage_id=review.LINEAGE,
    )
    assert canonical_sha256(scope) == manifest["final_scope_sha256"]
    assert scope.rc_commit == review.RC_COMMIT


def test_three_fresh_distinct_owner_records_are_schema_valid() -> None:
    manifest = _json(HERE / "manifest.json")
    schema = _json(REPO / "docs/acceptance/v3-01/schemas/approval-record.schema.json")
    validator = Draft202012Validator(schema)
    ids = set()
    for gate in ("G-01", "G-02", "G-03"):
        item = manifest["approval_records"][gate]
        record = _json(REPO / item["record_path"])
        validator.validate(record)
        model = ProviderApprovalRecord.model_validate(record)
        assert model.gate_id == gate and model.decision == "APPROVED"
        assert model.approval_id == review.APPROVAL_IDS[gate]
        assert canonical_sha256(model) == item["canonical_record_sha256"]
        assert review.RC_COMMIT in model.artifact_or_commit_hashes
        assert review.EXECUTION_SCOPE in model.artifact_or_commit_hashes
        assert review.PREPARATION_TEMPLATE in model.artifact_or_commit_hashes
        assert review.LEDGER_OPERATION_BINDING in model.artifact_or_commit_hashes
        ids.add(model.approval_id)
    assert ids == {"V3-01-APP-075", "V3-01-APP-076", "V3-01-APP-077"}


@pytest.mark.parametrize("field", ["credential_approval", "budget_approval", "rights_approval"])
@pytest.mark.parametrize(
    "mode",
    ["missing", "null", "wrong_role", "wrong_hash", "stale_rc", "stale_scope", "rejected", "expired", "late", "extra"],
)
def test_real_gate_schema_fails_closed_for_approval_drift(field: str, mode: str) -> None:
    payload = _json(review.BUNDLE_PATH)
    if mode == "missing":
        del payload[field]
    elif mode == "null":
        payload[field] = None
    elif mode == "wrong_hash":
        payload[field]["record_sha256"] = "0" * 64
    else:
        record = payload[field]["record"]
        if mode == "wrong_role":
            record["gate_id"] = "G-02" if record["gate_id"] != "G-02" else "G-01"
        elif mode == "stale_rc":
            record["artifact_or_commit_hashes"].remove(review.RC_COMMIT)
        elif mode == "stale_scope":
            record["artifact_or_commit_hashes"].remove(review.EXECUTION_SCOPE)
        elif mode == "rejected":
            record["decision"] = "REJECTED"
        elif mode == "expired":
            record["expires_at_utc"] = "2026-09-16T17:59:59Z"
        elif mode == "late":
            record["approved_at_utc"] = "2026-09-16T14:00:01Z"
        elif mode == "extra":
            record["unbound_execution_override"] = True
        payload[field]["record_sha256"] = canonical_sha256(record)
    with pytest.raises(ValidationError):
        OpenAIAsrGateBundle.model_validate(payload)


@pytest.mark.parametrize(
    "key",
    [
        "operation_key",
        "slot",
        "rc_tag",
        "rc_commit",
        "governance_main_commit",
        "dual_ci_provenance_sha256",
        "executable_tree_sha256",
        "execution_scope_sha256",
        "prepared_scope_sha256",
        "operation_manifest_sha256",
        "gate_bundle_sha256",
        "loaded_runtime_scope_sha256",
        "asr_prompt_profile_sha256",
        "prompt_sha256",
        "asset_sha256",
        "reference_transcript_sha256",
        "rights_record_sha256",
        "valid_from_utc",
        "expires_at_utc",
        "status",
        "operation_1_consumed",
        "operation_2_authorized",
        "bundle_mounted",
        "kill_switch",
    ],
)
def test_outer_authority_denies_any_exact_binding_mutation(key: str) -> None:
    payload = _json(HERE / "operation-1-authority.json")
    payload[key] = "tampered"
    with pytest.raises(ValueError, match="OP1_AUTHORITY_BINDING_MISMATCH"):
        review.require_exact_authority(payload)


@pytest.mark.parametrize(
    "key,value",
    [
        ("per_operation_limit_vnd", "501"),
        ("acceptance_window_limit_vnd", "1251"),
        ("provider_http_timeout_seconds", 91),
        ("controller_hard_timeout_seconds", 121),
        ("max_attempts", 2),
        ("max_concurrent_calls", 2),
        ("automatic_retry", True),
        ("model_fallback", True),
    ],
)
def test_outer_authority_denies_limit_mutation(key: str, value: object) -> None:
    payload = _json(HERE / "operation-1-authority.json")
    payload["limits"][key] = value
    with pytest.raises(ValueError, match="OP1_AUTHORITY_BINDING_MISMATCH"):
        review.require_exact_authority(payload)


def test_operation_two_planning_slot_is_not_authority() -> None:
    gate = _json(review.BUNDLE_PATH)
    assert len(gate["allowed_operations"]) == len(gate["rights_records"]) == 2
    assert review.require_operation_one(gate["allowed_operations"][0]["operation_key"])
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        review.require_operation_one(gate["allowed_operations"][1]["operation_key"])


@pytest.mark.parametrize(
    "delta,expected",
    [(-1, False), (0, True), (1, True), (14399, True), (14400, False), (14401, False)],
)
def test_exact_owner_window_is_start_inclusive_end_exclusive(delta: int, expected: bool) -> None:
    start = datetime(2026, 9, 16, 14, tzinfo=timezone.utc)
    assert review.authority_window_active(start + timedelta(seconds=delta)) is expected


def test_window_requires_timezone() -> None:
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED"):
        review.authority_window_active(datetime(2026, 9, 16, 14))


def test_bootstrap_binding_is_final_authority_bound_but_not_execution() -> None:
    payload = _json(HERE / "bootstrap-binding.json")
    manifest = _json(HERE / "manifest.json")
    Draft202012Validator(BootstrapLedgerBinding.model_json_schema()).validate(payload)
    if os.name != "nt":
        BootstrapLedgerBinding.model_validate(payload)
    assert payload["authority_receipt_sha256"] == manifest["authority_receipt_raw_sha256"]
    assert payload["bundle_sha256"] == manifest["final_runtime_bundle_sha256"]
    assert payload["scope_sha256"] == manifest["final_scope_sha256"]
    assert payload["database_name"] == review.LEDGER
    assert payload["kill_switch_engaged"] is True
    assert payload["external_execution_enabled"] is payload["paid_execution_enabled"] is False
    assert payload["budget_reserved_vnd"] == "0"


def test_no_execution_state_or_confirmation_token_materialized() -> None:
    authority = _json(HERE / "operation-1-authority.json")
    assert authority["status"] == "GRANTED_NOT_CONSUMED"
    assert authority["operation_1_consumed"] is authority["bundle_mounted"] is False
    assert authority["kill_switch"] == "ENGAGED"
    assert authority["budget_reserved_vnd"] == authority["actual_cost_vnd"] == "0"
    assert authority["credential_reads"] == authority["provider_calls"] == 0
    assert authority["confirmation_token_binding"] == {
        "binding_sha256": None,
        "created": False,
        "required_by_current_gate_schema": False,
        "required_by_retained_asr_authority_verifier": False,
        "status": "NOT_REQUIRED_BY_VERIFIED_ASR_CONTRACT",
    }


def test_network_is_forbidden_by_materialization_harness() -> None:
    with pytest.raises(AssertionError, match="FORBIDS_NETWORK"):
        socket.create_connection(("api.openai.com", 443))
