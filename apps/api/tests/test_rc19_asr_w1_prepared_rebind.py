from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
PREPARED = (
    REPO
    / "docs/acceptance/v3-01/prepared/vf-v0s-b7-rc19-asr-w1"
)
SPEC = importlib.util.spec_from_file_location(
    "vf_v0s_b7_prepare_materials", PREPARED / "prepare_materials.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _json(name: str) -> dict:
    return json.loads((PREPARED / name).read_text(encoding="utf-8"))


def test_rc19_prepared_materials_are_exact_and_unsigned() -> None:
    result = MODULE.validate_materials()
    assert result == {
        "checked_files": 12,
        "credential_reads": 0,
        "mismatches": [],
        "operation_authority_created": False,
        "prepared_operation_metadata_write": False,
        "provider_calls": 0,
        "reservation_vnd": "0",
        "status": "PASS",
        "task_id": "VF-V0S-B7",
    }


def test_rc19_generation_is_byte_deterministic() -> None:
    assert MODULE.build_materials() == MODULE.build_materials()


def test_rc19_operation_and_ledger_are_fresh() -> None:
    manifest = _json("operation-1-manifest.json")
    ledger = _json("ledger-readiness.json")
    historical = _json("historical-package-invalidation.json")
    assert manifest["operation_id"] == ledger["operation_key"]
    assert manifest["operation_id"].startswith("v3-01-rc19-")
    assert manifest["operation_id"] != historical["historical_operation_id"]
    assert ledger["exact_operation_records"] == ledger["exact_attempt_records"] == 0
    assert ledger["operation_consumed"] is False
    assert ledger["provider_request_receipt_exists"] is False
    assert ledger["active_reservation"] is False
    assert ledger["duplicate_or_idempotency_collision"] is False
    assert ledger["prepared_operation_metadata_write"] is False


def test_rc19_package_cannot_be_mistaken_for_authority() -> None:
    gate = _json("gate-template.json")
    package = _json("operation-preparation-package.json")
    bootstrap = _json("bootstrap-binding-plan.json")
    assert gate["runtime_loadable"] is False
    assert package["status"] == "PREPARED_NOT_AUTHORIZED"
    assert package["owner_gate_approvals_created"] is False
    assert bootstrap["authority_status"] == "NOT_CREATED"
    assert bootstrap["authority_receipt_sha256"] is None
    assert bootstrap["bundle_final_runtime_sha256"] is None
    assert bootstrap["current_bootstrap_model_valid"] is False
    assert package["operation_2_status"] == "NOT_APPROVED / LOCKED / NOT_TRANSFERRED"
    safety = package["safety_state"]
    assert safety["kill_switch"] == "ENGAGED"
    assert safety["bundle_mounted"] is safety["external_execution"] is safety["paid_execution"] is False
    assert safety["credential_reads"] == safety["real_provider_calls"] == 0
    assert safety["production_business_writes"] == 0
    assert safety["budget_reserved_vnd"] == safety["actual_cost_vnd"] == "0"
