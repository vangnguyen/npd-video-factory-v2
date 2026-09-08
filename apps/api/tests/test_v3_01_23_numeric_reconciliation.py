from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs" / "acceptance" / "v3-01"
EVALUATOR = DOCS / "tools" / "v3_01_asr_post_run_evaluator.py"
INPUT_SCHEMA = DOCS / "schemas" / "asr-post-run-input.schema.json"
OUTPUT_SCHEMA = DOCS / "schemas" / "asr-post-run-evaluation.schema.json"


@pytest.fixture(scope="module")
def evaluator():
    spec = importlib.util.spec_from_file_location("asr_evaluator_numeric_v30123", EVALUATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def payload():
    return json.loads((DOCS / "fixtures" / "asr-post-run" / "pass.json").read_text(encoding="utf-8"))


def _set_amount(payload: dict, field: str, value: object) -> None:
    target = payload["provider_transcript"] if field == "actual_cost_vnd" else payload["receipts"]
    target[field] = value


def _assert_output_schema(result: dict) -> None:
    Draft202012Validator(json.loads(OUTPUT_SCHEMA.read_text(encoding="utf-8"))).validate(result)


def _cli(tmp_path: Path, payload: dict):
    source = tmp_path / "numeric-input.json"
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(EVALUATOR), str(source)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )


@pytest.mark.parametrize("zero", ["0", "0.0", "0.0000", "000.000000"])
@pytest.mark.parametrize("reservation", ["500", "500.000000"])
def test_numeric_equivalence_and_canonical_hash(evaluator, payload, zero, reservation) -> None:
    original = copy.deepcopy(payload)
    payload["receipts"]["post_reconciliation_reserved_vnd"] = zero
    payload["receipts"]["reservation_vnd"] = reservation
    payload["provider_transcript"]["actual_cost_vnd"] = "16.2"

    result = evaluator.evaluate(payload)

    assert result == evaluator.evaluate(original)
    assert result["verdict"] == "PASS"
    assert result["numeric_reconciliation"]["canonical_amounts"] == {
        "reservation_vnd": "500",
        "post_reconciliation_reserved_vnd": "0",
        "actual_cost_vnd": "16.2",
    }
    assert result["numeric_reconciliation"]["acceptance_window_aggregate_status"] == "NOT_PROVIDED"
    assert result["numeric_reconciliation"]["acceptance_window_aggregate_checked"] is False
    _assert_output_schema(result)


def test_decimal_precision_is_preserved_not_float_or_context_rounded(evaluator, payload) -> None:
    payload["provider_transcript"]["actual_cost_vnd"] = "326.294996"
    with localcontext() as context:
        context.prec = 3
        amount = evaluator.parse_vnd_amount("326.294996")
        assert amount == Decimal("326.294996")
        assert evaluator._canonical_vnd(amount) == "326.294996"
        result = evaluator.evaluate(payload)
    assert result["numeric_reconciliation"]["canonical_amounts"]["actual_cost_vnd"] == "326.294996"
    assert result["verdict"] == "PASS"


INVALID_AMOUNTS = [
    "NaN", "sNaN", "Infinity", "-Infinity", "-1", "-0", "1e2", " 0", "0 ",
    "", "0.0000001", 0, 500.0, True, False,
]
MONEY_FIELDS = ["reservation_vnd", "post_reconciliation_reserved_vnd", "actual_cost_vnd"]


@pytest.mark.parametrize("field", MONEY_FIELDS)
@pytest.mark.parametrize("invalid", INVALID_AMOUNTS)
def test_direct_evaluation_rejects_invalid_money(evaluator, payload, field, invalid) -> None:
    _set_amount(payload, field, invalid)
    result = evaluator.evaluate(payload)
    assert result["verdict"] == "FAIL"
    assert f"MONEY_AMOUNT_INVALID:{field.upper()}" in result["reasons"]["fail"]
    assert result["numeric_reconciliation"]["canonical_amounts"][field] is None
    _assert_output_schema(result)


@pytest.mark.parametrize("field", MONEY_FIELDS)
@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-1", 500.0, True])
def test_cli_schema_rejects_invalid_money(tmp_path, payload, field, invalid) -> None:
    _set_amount(payload, field, invalid)
    result = _cli(tmp_path, payload)
    assert result.returncode == 2
    assert json.loads(result.stderr)["verdict"] == "FAIL"
    assert not result.stdout


@pytest.mark.parametrize("field", MONEY_FIELDS)
def test_missing_required_money_is_never_pass_direct_or_cli(evaluator, tmp_path, payload, field) -> None:
    target = payload["provider_transcript"] if field == "actual_cost_vnd" else payload["receipts"]
    del target[field]
    result = evaluator.evaluate(payload)
    assert result["verdict"] == "REVIEW_REQUIRED"
    assert f"MONEY_AMOUNT_MISSING:{field.upper()}" in result["reasons"]["review_required"]
    assert result["numeric_reconciliation"]["passed"] is False
    command = _cli(tmp_path, payload)
    assert command.returncode == 2
    assert json.loads(command.stderr)["verdict"] == "FAIL"


@pytest.mark.parametrize("mutation", ["missing_flag", "false_flag", "unknown_actual"])
def test_missing_cost_receipt_remains_review_required(evaluator, tmp_path, payload, mutation) -> None:
    if mutation == "missing_flag":
        del payload["receipts"]["cost_receipt_present"]
    elif mutation == "false_flag":
        payload["receipts"]["cost_receipt_present"] = False
    else:
        payload["provider_transcript"]["actual_cost_vnd"] = None
    result = evaluator.evaluate(payload)
    assert result["verdict"] == "REVIEW_REQUIRED"
    assert result["evidence_completeness"]["checks"]["cost_receipt"] is False
    command = _cli(tmp_path, payload)
    if mutation == "missing_flag":
        assert command.returncode == 2
    else:
        assert command.returncode == 0
        assert json.loads(command.stdout)["verdict"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize(
    ("field", "amount", "reason"),
    [
        ("reservation_vnd", "500.000001", "PER_OPERATION_RESERVATION_LIMIT_EXCEEDED"),
        ("reservation_vnd", "1250.000001", "ACCEPTANCE_WINDOW_LIMIT_EXCEEDED"),
        ("actual_cost_vnd", "500.000001", "ACTUAL_COST_EXCEEDS_RESERVATION"),
        ("actual_cost_vnd", "1250.000001", "ACCEPTANCE_WINDOW_LIMIT_EXCEEDED"),
        ("post_reconciliation_reserved_vnd", "500.000001", "REMAINING_RESERVATION_EXCEEDS_ORIGINAL"),
    ],
)
def test_budget_and_reconciliation_violations_fail_direct_and_cli(
    evaluator, tmp_path, payload, field, amount, reason
) -> None:
    _set_amount(payload, field, amount)
    result = evaluator.evaluate(payload)
    assert result["verdict"] == "FAIL"
    assert reason in result["reasons"]["fail"]
    command = _cli(tmp_path, payload)
    assert command.returncode == 0
    assert json.loads(command.stdout)["verdict"] == "FAIL"


def test_unreleased_reservation_is_numeric_and_stays_review_required(evaluator, payload) -> None:
    payload["receipts"]["post_reconciliation_reserved_vnd"] = "0.000001"
    result = evaluator.evaluate(payload)
    assert result["verdict"] == "REVIEW_REQUIRED"
    assert result["evidence_completeness"]["checks"]["reservation_reconciled"] is False


def test_zero_variants_pass_cli_without_mutating_source(tmp_path, payload) -> None:
    payload["receipts"]["reservation_vnd"] = "500.000000"
    payload["receipts"]["post_reconciliation_reserved_vnd"] = "0.0000"
    before = copy.deepcopy(payload)
    result = _cli(tmp_path, payload)
    assert result.returncode == 0
    assert json.loads(result.stdout)["verdict"] == "PASS"
    assert payload == before


def test_pass_output_cannot_claim_failed_numeric_checks(evaluator, payload) -> None:
    result = evaluator.evaluate(payload)
    result["numeric_reconciliation"]["passed"] = False
    with pytest.raises(ValidationError):
        _assert_output_schema(result)
    result = evaluator.evaluate(payload)
    result["numeric_reconciliation"]["checks"]["actual_cost_within_reservation"] = False
    with pytest.raises(ValidationError):
        _assert_output_schema(result)


def test_historical_output_schema_does_not_require_new_numeric_record(evaluator, payload) -> None:
    result = evaluator.evaluate(payload)
    del result["numeric_reconciliation"]
    _assert_output_schema(result)


@pytest.fixture
def retained_primary():
    directory = DOCS / "evidence" / "rc15-asr-operation-1"
    record = json.loads((directory / "operation-1-result.json").read_text(encoding="utf-8"))
    # The primary receipt holds a path/hash reference, not embedded input data.
    record["diagnostic_input"] = json.loads((directory / "operation-1-evaluator-input.json").read_text(encoding="utf-8"))
    return record


def test_retained_single_operation_ledger_exact_storage_projection(evaluator, retained_primary) -> None:
    before = copy.deepcopy(retained_primary)
    result = evaluator.reconcile_single_operation_ledger(
        retained_primary["diagnostic_input"], retained_primary["ledger"]
    )
    assert result["verdict"] == "PASS"
    assert result["aggregate_checked"] is True
    assert result["provider_actual_cost_vnd"] == "326.294996"
    assert result["numeric_20_4_projected_actual_cost_vnd"] == "326.2950"
    assert result["checks"]["historical_reservation_binding"] is True
    assert result["checks"]["outstanding_reservation_reconciled"] is True
    assert retained_primary == before
    # This is a diagnostic, not a revision of the original operation verdict.
    assert retained_primary["acceptance_verdict"] != "PASS"


@pytest.mark.parametrize(
    ("amount", "projected"),
    [("326.294996", "326.2950"), ("0.000049", "0.0000"), ("0.000050", "0.0001"), ("500", "500.0000")],
)
def test_numeric_20_4_projection_is_explicit_not_fuzzy(evaluator, amount, projected) -> None:
    with localcontext() as context:
        context.prec = 3
        actual = evaluator.numeric_20_4_projection(amount)
    assert actual == Decimal(projected)
    assert format(actual, ".4f") == projected


@pytest.mark.parametrize("amount", ["NaN", "-1", 500, "10000000000000000.0000", "9999999999999999.999999"])
def test_numeric_20_4_projection_rejects_invalid_or_overflow(evaluator, amount) -> None:
    with pytest.raises(ValueError):
        evaluator.numeric_20_4_projection(amount)


@pytest.mark.parametrize(
    ("section", "field", "value", "check"),
    [
        ("operation_1", "charged_vnd", "326.2949", "storage_cost_projection"),
        ("budget", "committed_vnd", "326.2949", "committed_matches_single_operation"),
        ("budget", "reserved_vnd", "0.0001", "outstanding_reservation_reconciled"),
        ("budget", "committed_vnd", "1250.0001", "aggregate_within_budget"),
        ("budget", "daily_limit_vnd", "1250.0001", "exact_window_limit"),
        ("operation_1", "reserved_vnd", "500.0001", "operation_reservation_ceiling"),
        ("operation_1", "operation_key", "wrong-operation", "operation_identity"),
        ("operation_1", "budget_day", "2026-09-09", "budget_day_binding"),
        ("operation_1", "attempt_count", 2, "single_attempt"),
    ],
)
def test_retained_ledger_mismatch_fails_exactly(evaluator, retained_primary, section, field, value, check) -> None:
    retained_primary["ledger"][section][field] = value
    result = evaluator.reconcile_single_operation_ledger(
        retained_primary["diagnostic_input"], retained_primary["ledger"]
    )
    assert result["verdict"] == "FAIL"
    assert result["checks"][check] is False


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", 0.0, True])
def test_retained_ledger_invalid_money_fails_without_echoing_values(evaluator, retained_primary, value) -> None:
    retained_primary["ledger"]["budget"]["committed_vnd"] = value
    result = evaluator.reconcile_single_operation_ledger(
        retained_primary["diagnostic_input"], retained_primary["ledger"]
    )
    assert result["verdict"] == "FAIL"
    assert result["reasons"] == ["LEDGER_MONEY_INVALID"]


@pytest.mark.parametrize("mutation", ["absent", "missing_amount", "multiple_operations", "no_actual_receipt"])
def test_incomplete_ledger_cannot_claim_aggregate_pass(evaluator, retained_primary, mutation) -> None:
    ledger = retained_primary["ledger"]
    if mutation == "absent":
        ledger = None
    elif mutation == "missing_amount":
        del ledger["budget"]["committed_vnd"]
    elif mutation == "multiple_operations":
        ledger["counts"]["operations"] = 2
    else:
        retained_primary["diagnostic_input"]["provider_transcript"]["actual_cost_vnd"] = None
    result = evaluator.reconcile_single_operation_ledger(retained_primary["diagnostic_input"], ledger)
    assert result["verdict"] == "REVIEW_REQUIRED"
    assert result["aggregate_checked"] is False
