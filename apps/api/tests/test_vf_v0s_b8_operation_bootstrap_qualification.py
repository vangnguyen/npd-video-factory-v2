from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import provider_runtime_bootstrap as bootstrap
from app.provider_gate_loader import ProviderGateBundleError, load_verified_provider_gate_bundle


REPO = Path(__file__).resolve().parents[3]
REVIEW = REPO / "docs/acceptance/v3-01/reviews/vf-v0s-b8"
PREPARED = REPO / "docs/acceptance/v3-01/prepared/vf-v0s-b7-rc19-asr-w1"
EVIDENCE = REPO / "evidence/v3-01/vf-v0s-b8-20260915-operation-bootstrap-qualification"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_preauthority_binding_is_rejected_only_for_the_two_absent_runtime_artifacts() -> None:
    payload = _json(REVIEW / "pre-authority-bootstrap-binding.json")
    with pytest.raises(ValidationError) as captured:
        bootstrap.BootstrapLedgerBinding.model_validate(payload)
    errors = {
        (".".join(str(item) for item in error["loc"]), error["type"])
        for error in captured.value.errors(include_url=False, include_input=False)
    }
    assert errors == {
        ("authority_receipt_sha256", "string_type"),
        ("bundle_sha256", "string_type"),
    }


def test_verified_bootstrap_has_no_preauthority_qualification_mode() -> None:
    schema = bootstrap.BootstrapLedgerBinding.model_json_schema()
    assert schema["properties"]["mode"]["const"] == "ZERO_CALL_CUSTODY_ONLY"
    assert "authority_receipt_sha256" in schema["required"]
    assert "bundle_sha256" in schema["required"]
    source = Path(bootstrap.__file__).read_text(encoding="utf-8")
    assert "--qualification" not in source
    assert "READY_FOR_AUTHORITY_MATERIALIZATION" not in source
    assert "AUTHORITY_REQUIRED" not in source
    assert 'result": "CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED"' in source


def test_preparation_template_remains_non_runtime_and_unsigned() -> None:
    gate = _json(PREPARED / "gate-template.json")
    plan = _json(PREPARED / "bootstrap-binding-plan.json")
    assert gate["runtime_loadable"] is False
    assert gate["preparation_status"] == "PREPARED_NOT_AUTHORIZED"
    assert all(slot["status"] == "NOT_CREATED" for slot in gate["owner_approval_slots"].values())
    assert plan["authority_receipt_sha256"] is None
    assert plan["bundle_final_runtime_sha256"] is None
    assert plan["current_bootstrap_model_valid"] is False
    with pytest.raises(ProviderGateBundleError):
        load_verified_provider_gate_bundle(
            PREPARED / "gate-template.json",
            expected_bundle_sha256=plan["bundle_preparation_template_sha256"],
            expected_rc_commit=plan["rc_commit"],
            expected_rc_tag=plan["rc_tag"],
            expected_acceptance_lineage_id=plan["acceptance_lineage_id"],
        )


def test_b7_package_still_reproduces_without_authority_or_side_effects() -> None:
    spec = importlib.util.spec_from_file_location("vf_v0s_b7_prepare", PREPARED / "prepare_materials.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.validate_materials()
    assert result["status"] == "PASS"
    assert result["operation_authority_created"] is False
    assert result["prepared_operation_metadata_write"] is False
    assert result["credential_reads"] == result["provider_calls"] == 0
    assert result["reservation_vnd"] == "0"


def test_b8_evidence_records_fail_closed_review_boundary() -> None:
    cli = _json(EVIDENCE / "bootstrap-cli-result.json")
    ledger = _json(EVIDENCE / "ledger-readonly-audit.json")
    result = _json(EVIDENCE / "task-result.json")
    assert cli["exit_code"] == 2
    assert cli["result"] == "BLOCKED"
    assert cli["code"] == "BOOTSTRAP_BINDING_INVALID"
    assert cli["validation_error_fields"] == ["authority_receipt_sha256", "bundle_sha256"]
    assert ledger["transaction"] == "REPEATABLE_READ_READ_ONLY"
    assert all(value == 0 for value in ledger["row_counts"].values())
    assert ledger["reserved_vnd"] == "0"
    assert result["verdict"] == "REVIEW_REQUIRED"
    assert result["rc19_operation_bound_bootstrap"] == "NOT_VERIFIED"
    assert result["authority_state"] == "NOT_CREATED"
    assert result["bundle_mounted"] is False
    assert result["credential_reads"] == result["real_provider_calls"] == 0
    assert result["budget_reserved_vnd"] == result["actual_cost_vnd"] == "0"
