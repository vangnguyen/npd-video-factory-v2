from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator

from app.provider_gate_loader import canonical_sha256, load_verified_provider_gate_bundle
from app.provider_runtime_bootstrap import BootstrapLedgerBinding


REPO = Path(__file__).resolve().parents[3]
AUTHORITY_DIR = REPO / "docs/acceptance/v3-01/authority/vf-v0s-b9-rc19-asr-w1-op1"
EVIDENCE = REPO / "evidence/v3-01/vf-v0s-b10-20260915-final-bootstrap-qualification"
HANDOFF_JSON = REPO / "docs/acceptance/v3-01/handoff.json"
HANDOFF_MD = REPO / "docs/acceptance/v3-01/HANDOFF.md"

spec = importlib.util.spec_from_file_location(
    "vf_v0s_b9_materializer", AUTHORITY_DIR / "materialize_and_validate.py"
)
assert spec is not None and spec.loader is not None
materializer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(materializer)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_bundle_reproduces_and_real_loader_accepts_without_mount() -> None:
    result = materializer.validate_materials()
    assert result["status"] == "PASS"
    assert result["gate_loader"] == "PASS / VALID_IN_MEMORY_NOT_MOUNTED"
    assert result["bundle_mounted"] is False

    manifest = _json(AUTHORITY_DIR / "manifest.json")
    bundle = REPO / manifest["final_bundle_path"]
    assert _sha(bundle) == "9dc8b99a8c10fbb1e8e2ba1a6f4a908b8322bca45c6a09d34d14f32a15cf5cdc"
    scope = load_verified_provider_gate_bundle(
        bundle,
        expected_bundle_sha256=manifest["final_runtime_bundle_sha256"],
        expected_rc_commit=materializer.RC_COMMIT,
        expected_rc_tag=materializer.RC_TAG,
        expected_acceptance_lineage_id=materializer.LINEAGE,
    )
    assert canonical_sha256(scope) == "10df8f6da5418c74511692368aaa27084950379e6695b9a4f92aefe0358313b1"


def test_real_bootstrap_binding_is_schema_valid_and_final_authority_bound() -> None:
    binding = _json(AUTHORITY_DIR / "bootstrap-binding.json")
    Draft202012Validator(BootstrapLedgerBinding.model_json_schema()).validate(binding)
    if os.name != "nt":
        BootstrapLedgerBinding.model_validate(binding)
    assert _sha(AUTHORITY_DIR / "bootstrap-binding.json") == (
        "0387f6a8c432e609b01b398fea739438160c3b8ccb975afe59c643fc39760779"
    )
    assert binding["bundle_sha256"] == "9dc8b99a8c10fbb1e8e2ba1a6f4a908b8322bca45c6a09d34d14f32a15cf5cdc"
    assert binding["authority_receipt_sha256"] == (
        "2f4a322a5d3e97861a08412336ccbf0a0fdcc0e0e4c75b75901ec0c38d3bf8e0"
    )
    assert binding["scope_sha256"] == "10df8f6da5418c74511692368aaa27084950379e6695b9a4f92aefe0358313b1"
    assert binding["kill_switch_engaged"] is True
    assert binding["external_execution_enabled"] is binding["paid_execution_enabled"] is False
    assert binding["budget_reserved_vnd"] == "0"


def test_actual_bootstrap_cli_result_is_zero_call_read_only_and_ready_for_preflight() -> None:
    result = _json(EVIDENCE / "bootstrap-cli-result.json")
    assert result["exit_code"] == 0
    assert result["bootstrap_mode"] == "ZERO_CALL_CUSTODY_ONLY / --require-virgin-namespace"
    assert result["command_constraints"] == {
        "initialize_control_flag_present": False,
        "rc_source": "exact detached vf-v3-01-rc19 worktree",
        "require_virgin_namespace": True,
    }
    output = result["output"]
    assert output["result"] == "CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED"
    assert output["operation_state"] == "VIRGIN_NOT_REGISTERED / NOT_CONSUMED"
    assert output["counts"] == {
        "attempts": 0,
        "budget_alerts": 0,
        "budget_days": 0,
        "circuits": 0,
        "operations": 0,
    }
    assert output["ledger_bootstrap_write"]["ensure_state_invoked"] is False
    assert output["ledger_bootstrap_write"]["observed_control_presence_change"] == 0
    assert output["credential_reads"] == output["provider_calls"] == 0
    assert output["reserved_vnd"] == "0"
    assert output["bundle_mounted"] is output["authority_created_or_changed"] is False
    assert output["dispatch_entrypoint"] is None
    assert output["kill_switch"] == "ENGAGED"
    assert result["contract_classification"] == {
        "bootstrap_result": "BOOTSTRAP_BINDING_VALID",
        "provider_dispatch_ready": False,
        "rc19_operation_bound_bootstrap": "VERIFIED",
        "ready_state": "READY_FOR_EXECUTION_PREFLIGHT",
    }


def test_ledger_readback_remains_virgin_and_lineage_isolated() -> None:
    ledger = _json(EVIDENCE / "ledger-readback.json")
    assert ledger["readback_result"] == "PASS / VIRGIN / READ_ONLY"
    assert ledger["transaction"] == "REPEATABLE READ / READ ONLY"
    assert ledger["identity"]["database_name"] == (
        "vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed"
    )
    assert ledger["operation_record_exists"] is ledger["operation_consumed"] is False
    assert ledger["provider_request_receipt"] == "NONE"
    assert ledger["active_reservation"] is ledger["duplicate_or_idempotency_collision"] is False
    assert ledger["bootstrap_metadata_write"] is False
    assert ledger["execution_table_counts"] == {
        "attempts": 0,
        "budget_alerts": 0,
        "budget_days": 0,
        "circuits": 0,
        "operations": 0,
    }


def test_authority_and_approvals_remain_exact_and_unconsumed() -> None:
    bundle = _json(EVIDENCE / "final-bundle-validation.json")
    assert bundle["authority_status"] == "GRANTED_NOT_CONSUMED"
    assert bundle["authority_receipt_sha256"] == (
        "2f4a322a5d3e97861a08412336ccbf0a0fdcc0e0e4c75b75901ec0c38d3bf8e0"
    )
    assert {key: value["approval_id"] for key, value in bundle["approvals"].items()} == {
        "G-01": "V3-01-APP-075",
        "G-02": "V3-01-APP-076",
        "G-03": "V3-01-APP-077",
    }
    assert all(value["status"] == "PASS" for value in bundle["approvals"].values())
    assert bundle["bundle_mounted"] is False
    assert bundle["budget_policy"]["reserved_vnd"] == "0"


def test_window_and_budget_are_structural_not_execution_side_effects() -> None:
    bundle = _json(EVIDENCE / "final-bundle-validation.json")
    assert bundle["window_policy"] == {
        "end_ict": "2026-09-17T01:00:00+07:00",
        "end_utc": "2026-09-16T18:00:00Z",
        "status": "BOUND_NOT_EVALUATED_FOR_DISPATCH",
        "start_ict": "2026-09-16T21:00:00+07:00",
        "start_utc": "2026-09-16T14:00:00Z",
    }
    assert bundle["budget_policy"] == {
        "modeled_cost_vnd": "326.3004",
        "per_operation_ceiling_vnd": "500",
        "reserved_vnd": "0",
        "window_ceiling_vnd": "1250",
    }


def test_terminal_task_result_is_preflight_ready_not_dispatch_ready() -> None:
    result = _json(EVIDENCE / "task-result.json")
    assert result["verdict"] == "PASS"
    assert result["rc19_operation_bound_bootstrap"] == "VERIFIED"
    assert result["ready_state"] == "READY_FOR_EXECUTION_PREFLIGHT"
    assert result["provider_dispatch_ready"] is False
    assert result["operation_1_consumed"] is result["bundle_mounted"] is False
    assert result["provider_request_receipt"] == "NONE"
    assert result["active_reservation"] is result["duplicate_or_idempotency_collision"] is False
    assert result["credential_reads"] == result["provider_calls"] == 0
    assert result["budget_reserved_vnd"] == result["actual_cost_vnd"] == "0"
    assert result["production_business_writes"] == 0
    assert result["kill_switch"] == "ENGAGED"


def test_canonical_handoff_matches_b10_terminal_state() -> None:
    handoff = _json(HANDOFF_JSON)
    markdown = HANDOFF_MD.read_text(encoding="utf-8")
    assert handoff["task_id"] == "VF-V0S-B10"
    assert handoff["verdict"] == "PASS"
    assert handoff["bootstrap"]["result"] == "BOOTSTRAP_BINDING_VALID"
    assert handoff["bootstrap"]["rc19_operation_bound_bootstrap"] == "VERIFIED"
    assert handoff["bootstrap"]["ready_state"] == "READY_FOR_EXECUTION_PREFLIGHT"
    assert handoff["bootstrap"]["provider_dispatch_ready"] is False
    assert handoff["ledger"]["mutations"] == 0
    assert handoff["safety"] == {
        "actual_cost_vnd": "0",
        "budget_reserved_vnd": "0",
        "bundle_mounted": False,
        "credential_reads": 0,
        "kill_switch": "ENGAGED",
        "production_business_writes": 0,
        "real_provider_calls": 0,
    }
    for value in (
        handoff["operation"]["id"],
        handoff["gate"]["final_runtime_bundle_sha256"],
        handoff["gate"]["loaded_runtime_scope_sha256"],
        handoff["authority"]["receipt_sha256"],
        handoff["ledger"]["identity"],
        handoff["bootstrap"]["ready_state"],
    ):
        assert str(value) in markdown
