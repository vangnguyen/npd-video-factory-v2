"""Reproduce an offline diagnostic comparison; never replace historical receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from v3_01_23_asr_critical_term_forensic import build_report
from v3_01_asr_post_run_evaluator import (
    canonical_json_bytes,
    evaluate,
    reconcile_single_operation_ledger,
)

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path("docs/acceptance/v3-01/evidence/rc15-asr-operation-1")
ORIGINAL_HASHES = {
    "operation-1-result.json": "ef06ffc48495e207ae7e827207ff67ee7b345b3323c702c1852b39a27a2d5099",
    "operation-1-evaluator-input.json": "80dfdbe7b8afe38eda7086d452e393d8893fdcca2c562174c055abe91a889474",
    "operation-1-post-run-evaluation.json": "08d71d294dc602e219d09d824c9d66e834a6c713f36f4a94368f5034598ffda9",
}


def rendered(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def build_artifacts(repo: Path = ROOT) -> dict[str, bytes]:
    source = {}
    for name, expected in ORIGINAL_HASHES.items():
        raw = (repo / EVIDENCE / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("HISTORICAL_EVIDENCE_HASH_MISMATCH")
        source[name] = json.loads(raw)
    payload = source["operation-1-evaluator-input.json"]
    receipt = source["operation-1-result.json"]
    old = source["operation-1-post-run-evaluation.json"]
    new = evaluate(payload)
    ledger = reconcile_single_operation_ledger(payload, receipt["ledger"])
    if not (
        old["verdict"] == new["verdict"] == "FAIL"
        and old["critical_terms"] == new["critical_terms"]
        and old["wer"] == new["wer"]
        and old["timestamps"] == new["timestamps"]
        and old["evidence_completeness"]["checks"]["reservation_reconciled"] is False
        and new["evidence_completeness"]["passed"] is True
        and new["numeric_reconciliation"]["passed"] is True
        and ledger["verdict"] == "PASS"
    ):
        raise ValueError("DIAGNOSTIC_COMPARISON_INVARIANT_FAILED")
    comparison = {
        "schema_version": 1,
        "record_kind": "diagnostic_evaluator_comparison_not_historical_reassessment",
        "checkpoint": "V3-01-23",
        "operation_id": payload["operation"]["operation_id"],
        "source_receipt_raw_sha256": ORIGINAL_HASHES,
        "official_historical_verdict": "FAIL",
        "official_historical_verdict_immutable": True,
        "old_evaluator": {
            "source_commit": "07e276f2ec69b2e0247899077537374f3d94f4b4",
            "evaluation_sha256": old["evaluation_sha256"],
            "reservation_comparison": '"0.0000" == "0" is false',
            "verdict": old["verdict"],
            "reasons": old["reasons"],
            "evidence_completeness": old["evidence_completeness"],
        },
        "new_evaluator": new,
        "retained_ledger_diagnostic_reconciliation": ledger,
        "interpretation": {
            "critical_term_failures": "Content differences against owner-confirmed reference; matcher unchanged; no new acoustic review.",
            "numeric_bug": "Decimal equality replaces raw-string zero comparison; receipt and retained ledger reconcile.",
            "actual_cost_vnd": "326.294996",
            "ledger_numeric_20_4_vnd": "326.2950",
            "rounding_policy": "Only the explicit storage projection rounds; original provider cost is not rewritten.",
            "asr_consecutive": "0/2 PASS",
            "vision_consecutive": "2/2 PASS",
            "operation_1": "CONSUMED_SUCCEEDED_ACCEPTANCE_FAIL",
            "operation_2": "NOT_APPROVED_LOCKED",
            "downstream_positive_duration_ready": False,
        },
        "safety": {
            "provider_calls": 0, "credential_reads": 0, "live_reservations": 0,
            "spend_vnd": "0", "production_verdict": "NO-GO", "authority_granted": False,
        },
    }
    comparison["comparison_sha256"] = hashlib.sha256(canonical_json_bytes(comparison)).hexdigest()
    output = {
        "critical-term-forensic.json": rendered(build_report(repo)),
        "diagnostic-evaluator-comparison.json": rendered(comparison),
    }
    manifest = {
        "schema_version": 1,
        "record_kind": "v3_01_23_local_evidence_checksum_manifest",
        "hash_semantics": "SHA-256 over exact file bytes; canonical internal hashes are separate fields",
        "originals_immutable": True,
        "official_acceptance": "FAIL",
        "files": [
            {"path": name, "sha256": digest, "role": "original_immutable"}
            for name, digest in ORIGINAL_HASHES.items()
        ] + [
            {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "role": "derived_diagnostic_only"}
            for name, raw in output.items()
        ],
    }
    output["manifest.json"] = rendered(manifest)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write ONLY the three derived artifacts")
    args = parser.parse_args()
    output = build_artifacts()
    for name, raw in output.items():
        path = ROOT / EVIDENCE / name
        if args.write:
            path.write_bytes(raw)
        elif path.read_bytes() != raw:
            raise ValueError("DERIVED_EVIDENCE_NOT_REPRODUCIBLE")
    print(json.dumps({"result": "PASS", "original_files_verified": 3, "derived_files_verified": len(output),
                      "historical_verdict": "FAIL", "provider_calls": 0, "credential_reads": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
