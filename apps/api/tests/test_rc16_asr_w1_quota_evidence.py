from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = (
    REPO_ROOT
    / "docs"
    / "acceptance"
    / "v3-01"
    / "evidence"
    / "rc16-asr-w1-operation-1"
)
REVIEW_PATH = EVIDENCE_DIR / "operation-1-quota-review.json"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
REVIEW_SHA256 = "173e8c37b144491610a3c58651fd0fb35c0f722eadb494b9ef26f4a3fb05da49"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_rc16_quota_review_hash_and_manifest_are_exact() -> None:
    assert hashlib.sha256(REVIEW_PATH.read_bytes()).hexdigest() == REVIEW_SHA256
    manifest = _load(MANIFEST_PATH)
    assert manifest["evidence_id"] == "EV-V3-RC16-ASR-W1-OP1-QUOTA-001"
    assert manifest["files"] == [
        {
            "path": "operation-1-quota-review.json",
            "sha256": REVIEW_SHA256,
            "role": "secret_free_evidence_projection",
        }
    ]
    assert manifest["source_receipts_rewritten"] is False


def test_rc16_quota_failure_preserves_provider_and_cost_semantics() -> None:
    review = _load(REVIEW_PATH)
    outcome = review["outcome"]
    safety = review["durable_safety_state"]

    assert outcome["provider_dispatched"] is True
    assert outcome["provider_execution"] == "FAILED"
    assert outcome["http_status"] == 429
    assert outcome["provider_error_code"] == "credit_balance_exhausted"
    assert outcome["acceptance_verdict"] == "REVIEW_REQUIRED"
    assert outcome["structured_transcript"] is None
    assert outcome["usage_receipt"] is None
    assert outcome["actual_provider_cost_vnd"] is None
    assert outcome["actual_provider_cost_status"] == "UNKNOWN"
    assert outcome["operation_consumed"] is True
    assert safety["safety_charge_vnd"] == "500.0000"
    assert safety["safety_charge_is_actual_provider_cost"] is False
    assert safety["reserved_vnd_after_reconciliation"] == "0.0000"


def test_credit_follow_up_does_not_create_or_revive_authority() -> None:
    review = _load(REVIEW_PATH)
    follow_up = review["owner_follow_up"]
    post_run = review["post_run"]
    boundary = review["audit_boundary"]

    assert follow_up["evidence_class"] == "OWNER_REPORTED_NOT_LIVE_VERIFIED"
    assert follow_up["revives_consumed_operation"] is False
    assert follow_up["grants_operation_2_authority"] is False
    assert follow_up["grants_new_operation_authority"] is False
    assert post_run["operation_2"] == "NOT_APPROVED_LOCKED"
    assert post_run["asr_consecutive_pass"] == "0/2"
    assert post_run["production_verdict"] == "NO-GO"
    assert boundary["provider_calls_in_this_evidence_package"] == 0
    assert boundary["credential_reads_in_this_evidence_package"] == 0
    assert boundary["spend_in_this_evidence_package_vnd"] == "0"
