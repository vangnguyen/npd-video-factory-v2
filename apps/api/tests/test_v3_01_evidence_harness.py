from __future__ import annotations

import hashlib
import importlib.util
import csv
import json
from collections import Counter
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "v3_01_acceptance.py"
SPEC = importlib.util.spec_from_file_location("v3_01_acceptance", SCRIPT_PATH)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


def test_redaction_preserves_identifiers_and_removes_credentials() -> None:
    payload = {
        "key_id": "v3",
        "object_key": "workspace/project/final.mp4",
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz012345",
        "nested": {"client_secret": "secret-value-that-must-not-remain"},
    }

    redacted = HARNESS.redact_payload(payload)

    assert redacted["key_id"] == "v3"
    assert redacted["object_key"] == "workspace/project/final.mp4"
    assert redacted["authorization"] == "<REDACTED>"
    assert redacted["nested"]["client_secret"] == "<REDACTED>"


def test_hash_manifest_is_bounded_and_deterministic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run = repo / "evidence" / "v3-01" / "run-001"
    run.mkdir(parents=True)
    (run / "run-manifest.json").write_text('{"result":"BLOCKED"}\n', encoding="utf-8")
    private = run / "private"
    private.mkdir()
    (private / "credential.txt").write_text("do-not-hash", encoding="utf-8")

    HARNESS.write_hashes(repo, run)
    first = (run / "SHA256SUMS.txt").read_text(encoding="utf-8")
    HARNESS.write_hashes(repo, run)
    second = (run / "SHA256SUMS.txt").read_text(encoding="utf-8")

    assert first == second
    assert "run-manifest.json" in first
    assert "credential.txt" not in first
    assert HARNESS.validate_hashes(run) == 1


def test_hash_manifest_detects_tampering(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run = repo / "evidence" / "v3-01" / "run-001"
    run.mkdir(parents=True)
    artifact = run / "artifact.json"
    artifact.write_text('{"state":"initial"}\n', encoding="utf-8")
    HARNESS.write_hashes(repo, run)
    artifact.write_text('{"state":"changed"}\n', encoding="utf-8")

    with pytest.raises(HARNESS.ValidationFailure, match="SHA256 mismatch"):
        HARNESS.validate_hashes(run)


def test_matrix_validation_rejects_pass_without_evidence(tmp_path: Path) -> None:
    path = tmp_path / "matrix.csv"
    headers = [
        "id", "module", "implemented", "mock_tested", "real_provider_tested",
        "production_path_tested", "quality_accepted", "critical", "evidence_ids", "gap_ids", "notes",
    ]
    rows = []
    for matrix_id in HARNESS.EXPECTED_MATRIX_IDS:
        rows.append(
            {
                "id": matrix_id,
                "module": matrix_id,
                "implemented": "NOT_TESTED",
                "mock_tested": "NOT_TESTED",
                "real_provider_tested": "NOT_TESTED",
                "production_path_tested": "NOT_TESTED",
                "quality_accepted": "NOT_TESTED",
                "critical": "Yes",
                "evidence_ids": "",
                "gap_ids": "",
                "notes": "initial",
            }
        )
    rows[0]["implemented"] = "PASS"
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(HARNESS.ValidationFailure, match="PASS without evidence"):
        HARNESS.validate_matrix(path)


def test_approval_validation_rejects_filename_mismatch(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    schemas = docs / "schemas"
    approvals = docs / "approvals"
    schemas.mkdir(parents=True)
    approvals.mkdir()
    source_schema = REPO_ROOT / "docs" / "acceptance" / "v3-01" / "schemas" / "approval-record.schema.json"
    (schemas / source_schema.name).write_text(source_schema.read_text(encoding="utf-8"), encoding="utf-8")
    record = {
        "approval_id": "V3-01-APP-999",
        "gate_id": "G-00",
        "decision": "APPROVED",
        "scope": "local tests only",
        "artifact_or_commit_hashes": [],
        "target_account_or_environment": "LOCAL",
        "limits": ["no merge"],
        "approved_by": "owner",
        "approved_at_utc": "2026-08-27T13:29:26Z",
        "expires_at_utc": None,
        "notes": "fixture",
    }
    (approvals / "V3-01-APP-998.json").write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(HARNESS.ValidationFailure, match="filename does not match"):
        HARNESS.validate_approval_records(docs)


def test_rights_validation_rejects_filename_mismatch(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    schemas = docs / "schemas"
    rights = docs / "rights"
    schemas.mkdir(parents=True)
    rights.mkdir()
    source_schema = (
        REPO_ROOT
        / "docs"
        / "acceptance"
        / "v3-01"
        / "schemas"
        / "rights-record.schema.json"
    )
    (schemas / source_schema.name).write_text(
        source_schema.read_text(encoding="utf-8"), encoding="utf-8"
    )
    record = json.loads(
        (
            REPO_ROOT
            / "docs"
            / "acceptance"
            / "v3-01"
            / "rights"
            / "V3-01-RIGHTS-G03A-001.json"
        ).read_text(encoding="utf-8")
    )
    (rights / "WRONG-ID.json").write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(HARNESS.ValidationFailure, match="filename does not match"):
        HARNESS.validate_rights_records(docs)


def test_checked_in_v3_01_register_is_complete() -> None:
    HARNESS.validate_repo(REPO_ROOT)


def test_v3_01_08_snapshot_and_latest_gap_deltas_are_consistent() -> None:
    docs = REPO_ROOT / "docs" / "acceptance" / "v3-01"
    contract_path = (
        REPO_ROOT
        / "evidence"
        / "v3-01"
        / "vf-v3-01-20260828T081742Z-b132e83"
        / "consolidation"
        / "rc-gate.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    with (docs / "02_ACCEPTANCE_MATRIX.csv").open(encoding="utf-8", newline="") as handle:
        matrix = list(csv.DictReader(handle))
    with (docs / "13_GAP_REGISTER.csv").open(encoding="utf-8", newline="") as handle:
        gaps = list(csv.DictReader(handle))

    assert contract["matrix"]["rows"] == len(matrix) == 60
    for axis in (
        "implemented",
        "mock_tested",
        "real_provider_tested",
        "production_path_tested",
        "quality_accepted",
    ):
        actual = dict(Counter(row[axis] for row in matrix))
        assert contract["matrix"][axis] == actual

    assert contract["gaps"]["total"] == len(gaps) == 16
    assert contract["gaps"]["by_status"] == {
        "OPEN": 5,
        "IN_PROGRESS": 10,
        "REMEDIATED": 1,
    }
    assert dict(Counter(row["status"] for row in gaps)) == {
        "OPEN": 4,
        "IN_PROGRESS": 11,
        "REMEDIATED": 1,
    }
    gap_003 = next(row for row in gaps if row["gap_id"] == "V3-01-GAP-003")
    assert gap_003["status"] == "IN_PROGRESS"
    assert "EV-V3-OPENAI-VISION-ADAPTER-001" in gap_003["evidence_ids"]
    assert "EV-V3-VERIFIED-GATE-LOADER-001" in gap_003["evidence_ids"]
    assert "EV-V3-STRUCTURED-ERROR-EVIDENCE-001" in gap_003["evidence_ids"]
    assert "EV-V3-RC-BOUND-ALLOWLIST-001" in gap_003["evidence_ids"]
    assert "EV-V3-RC5-VISION-REBIND-001" in gap_003["evidence_ids"]
    assert "EV-V3-RC5-VISION-OP1-REVIEW-001" in gap_003["evidence_ids"]
    assert "EV-V3-EVIDENCE-SERIALIZATION-001" in gap_003["evidence_ids"]
    assert "EV-V3-RC6-VISION-REBIND-001" in gap_003["evidence_ids"]
    assert "EV-V3-RC7-VISION-REBIND-001" in gap_003["evidence_ids"]
    assert "EV-V3-RC9-VISION-REBIND-001" in gap_003["evidence_ids"]
    assert gap_003["verified_on_commit"] == "256bda59eed028ddd642cdb0988c409c489fd655"

    gap_010 = next(row for row in gaps if row["gap_id"] == "V3-01-GAP-010")
    assert gap_010["status"] == "IN_PROGRESS"
    assert "EV-V3-VERIFIED-GATE-LOADER-001" in gap_010["evidence_ids"]
    assert "EV-V3-STRUCTURED-ERROR-EVIDENCE-001" in gap_010["evidence_ids"]
    assert "EV-V3-RC-BOUND-ALLOWLIST-001" in gap_010["evidence_ids"]
    assert "EV-V3-RC5-VISION-REBIND-001" in gap_010["evidence_ids"]
    assert "EV-V3-RC5-VISION-OP1-REVIEW-001" in gap_010["evidence_ids"]
    assert "EV-V3-EVIDENCE-SERIALIZATION-001" in gap_010["evidence_ids"]
    assert "EV-V3-RC6-VISION-REBIND-001" in gap_010["evidence_ids"]
    assert "EV-V3-RC7-VISION-REBIND-001" in gap_010["evidence_ids"]
    assert "EV-V3-RC9-VISION-REBIND-001" in gap_010["evidence_ids"]
    assert gap_010["verified_on_commit"] == "256bda59eed028ddd642cdb0988c409c489fd655"

    gap_013 = next(row for row in gaps if row["gap_id"] == "V3-01-GAP-013")
    assert gap_013["status"] == "IN_PROGRESS"
    assert "EV-V3-VERIFIED-GATE-LOADER-001" in gap_013["evidence_ids"]
    assert "EV-V3-RC5-VISION-REBIND-001" in gap_013["evidence_ids"]
    assert "EV-V3-RC5-VISION-OP1-REVIEW-001" in gap_013["evidence_ids"]
    assert "EV-V3-RC6-VISION-REBIND-001" in gap_013["evidence_ids"]
    assert "EV-V3-RC7-VISION-REBIND-001" in gap_013["evidence_ids"]
    assert "EV-V3-RC9-VISION-REBIND-001" in gap_013["evidence_ids"]
    assert gap_013["verified_on_commit"] == "256bda59eed028ddd642cdb0988c409c489fd655"
    assert contract["gaps"]["by_severity"] == dict(Counter(row["severity"] for row in gaps))
    assert contract["production_verdict"] == "NO-GO"
    assert contract["rc_candidate"]["status"] == "CONDITIONAL-RC"
    assert contract["rc_candidate"]["locked"] is False
    assert contract["safety"] == {
        "external_execution": False,
        "paid_execution": False,
        "budget_vnd": 0,
        "currency": "VND",
        "global_kill_switch_engaged": True,
        "external_notifications_enabled": False,
        "credentials_used": False,
        "deploy_performed": False,
        "public_ingress_enabled": False,
        "publish_performed": False,
        "production_analytics_enabled": False,
    }


def test_rc5_operation_1_review_record_is_permanently_fail_closed() -> None:
    record_path = (
        REPO_ROOT
        / "evidence"
        / "v3-01"
        / "vf-v3-01-20260829T145447Z-f04bffc"
        / "provider"
        / "rc5-operation-1-review.json"
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))

    assert record["provider_execution"] == "SUCCESS"
    assert record["acceptance_evidence"] == "INCOMPLETE"
    assert record["verdict"] == "REVIEW_REQUIRED"
    assert record["production_verdict"] == "NO-GO"
    assert record["operation"]["consumed"] is True
    assert record["operation"]["attempt_count"] == 1
    assert record["operation"]["retry_count"] == 0
    assert record["operation"]["fallback_count"] == 0
    assert record["operation_2"] == {
        "operation_key": "v3-01-rc5-openai-vision-call-02",
        "authorized": False,
        "executed": False,
        "ledger_rows": 0,
    }
    assert record["usage_and_cost"]["actual_cost_vnd"] == "137.6287"
    missing = record["missing_request_level_evidence"]
    assert missing["structured_output_payload"] is None
    assert missing["provider_request_id"] is None
    assert missing["client_request_id"] is None
    assert missing["request_sha256"] is None
    assert missing["response_sha256"] is None
    assert missing["provider_response_receipt"] is None
    assert missing["reconstructed"] is False
    assert record["acceptance_impact"]["real_provider_axis_promoted"] is False
    historical_runner = record["historical_runner"]
    runner_path = REPO_ROOT / historical_runner["path"]
    assert historical_runner["modified_for_remediation"] is False
    assert hashlib.sha256(runner_path.read_bytes()).hexdigest() == historical_runner["sha256"]
