"""Retained RC-15 receipts are immutable; new outputs are diagnostic comparisons."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "docs/acceptance/v3-01/tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("v3_01_23_review", TOOLS / "v3_01_23_evidence_review.py")
assert SPEC and SPEC.loader
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


def test_diagnostic_artifacts_reproduce_without_changing_originals():
    before = {name: (REPO / REVIEW.EVIDENCE / name).read_bytes() for name in REVIEW.ORIGINAL_HASHES}
    artifacts = REVIEW.build_artifacts(REPO)
    assert artifacts == REVIEW.build_artifacts(REPO)
    for name, raw in artifacts.items():
        assert (REPO / REVIEW.EVIDENCE / name).read_bytes() == raw
    for name, raw in before.items():
        assert (REPO / REVIEW.EVIDENCE / name).read_bytes() == raw
        assert hashlib.sha256(raw).hexdigest() == REVIEW.ORIGINAL_HASHES[name]


def test_official_failure_and_critical_terms_unchanged():
    artifact = json.loads(REVIEW.build_artifacts(REPO)["diagnostic-evaluator-comparison.json"])
    new = artifact["new_evaluator"]
    assert artifact["official_historical_verdict"] == new["verdict"] == "FAIL"
    assert artifact["official_historical_verdict_immutable"] is True
    assert new["critical_terms"]["normalized_recall"] == 0.625
    assert new["wer"]["wer"] == 0.096618
    assert new["timestamps"]["zero_duration_words"] == 27
    assert new["timestamps"]["downstream_positive_duration_ready"] is False
    assert new["numeric_reconciliation"]["passed"] is True
    assert new["evidence_completeness"]["passed"] is True
    assert new["reasons"]["fail"] == ["CRITICAL_TERM_RECALL_BELOW_1_0"]
    assert new["reasons"]["review_required"] == []
    ledger = artifact["retained_ledger_diagnostic_reconciliation"]
    assert ledger["verdict"] == "PASS"
    assert ledger["provider_actual_cost_vnd"] == "326.294996"
    assert ledger["numeric_20_4_projected_actual_cost_vnd"] == "326.2950"
    assert artifact["interpretation"]["operation_2"] == "NOT_APPROVED_LOCKED"
    assert artifact["safety"]["provider_calls"] == artifact["safety"]["credential_reads"] == 0
    schema = json.loads((TOOLS.parent / "schemas/asr-post-run-evaluation.schema.json").read_text())
    Draft202012Validator(schema).validate(new)


def test_manifest_and_canonical_comparison_hashes():
    artifacts = REVIEW.build_artifacts(REPO)
    manifest = json.loads(artifacts["manifest.json"])
    for item in manifest["files"]:
        raw = artifacts.get(item["path"])
        if raw is None:
            raw = (REPO / REVIEW.EVIDENCE / item["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    comparison = json.loads(artifacts["diagnostic-evaluator-comparison.json"])
    digest = comparison.pop("comparison_sha256")
    assert hashlib.sha256(REVIEW.canonical_json_bytes(comparison)).hexdigest() == digest


def test_changed_historical_receipt_fails_before_evaluation(tmp_path):
    target = tmp_path / REVIEW.EVIDENCE
    target.mkdir(parents=True)
    (target / "operation-1-result.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="HISTORICAL_EVIDENCE_HASH_MISMATCH"):
        REVIEW.build_artifacts(tmp_path)
