"""Reproduce the unsigned RC-20 ASR W1 Operation 1 preparation materials.

This offline checker has no database connector, credential resolver, budget API,
bundle mount, authority signer, or provider adapter. It never writes files.
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
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "apps/api"))

from app.asr_prompt_profile import W1_PROMPT, prompt_profile_sha256, validate_prompt_profile  # noqa: E402
from app.provider_ci_provenance import EXECUTABLE_TREE_PATHS, executable_tree_sha256  # noqa: E402
from app.provider_gate_loader import (  # noqa: E402
    HashedRightsRecord,
    OpenAIAsrGateBudgetEnvelope,
    canonical_sha256,
    execution_scope_sha256,
)
from app.provider_runtime_bootstrap import ledger_database_name  # noqa: E402
from app.provider_safety import (  # noqa: E402
    ProviderAllowedOperation,
    ProviderRightsEvidence,
    derive_acceptance_lineage_id,
    derive_rc_bound_operation_key,
)


MAIN = "4ac4880d5627c2800eb918d24c59da5f8e047091"
MAIN_CI = 35172654970
RC_TAG = "vf-v3-01-rc20"
RC_COMMIT = "93b5441d44347c9c40b745bdfed0969880853f68"
RC_CI = 35124578033
TREE = "611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630"
PROVENANCE = "5caca534d1cfa6a4e3d9b4f9f9b6b1c33b024ec65afdfc36cf875c673bc1eb86"
LEDGER = "vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d"
PROFILE_SHA = "9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1"
PROMPT_SHA = "6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48"
ASSET_SHA = "fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef"
TRANSCRIPT_SHA = "585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e"
RIGHTS_SHA = "5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091"
RC19_OPERATION = (
    "v3-01-rc19-openai-transcription-asr-al-0001-"
    "d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd-call-01"
)
START = datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc)
END = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
ALIAS = "secret://openai/codex-video"  # Reference only; never resolved here.
RUNNER = "apps/api/app/provider_single_dispatch.py"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha(relative: str) -> str:
    return _sha((REPO / relative).read_bytes())


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _input(slot: int) -> tuple[dict[str, object], HashedRightsRecord]:
    number = f"{slot:02d}"
    asset = f"docs/acceptance/v3-01/assets/g03-asr-vi-owned-{number}.wav"
    transcript = f"docs/acceptance/v3-01/transcripts/g03-asr-vi-owned-{number}.txt"
    rights_path = f"docs/acceptance/v3-01/rights/V3-01-RIGHTS-ASR-{slot:03d}.json"
    rights = ProviderRightsEvidence.model_validate(json.loads((REPO / rights_path).read_text(encoding="utf-8")))
    with wave.open(str(REPO / asset), "rb") as wav:
        frames, rate = wav.getnframes(), wav.getframerate()
        channels, sample_width = wav.getnchannels(), wav.getsampwidth()
    record = {
        "asset_id": f"asset-g03-asr-vi-owned-{number}",
        "asset_path": asset,
        "asset_sha256": _file_sha(asset),
        "reference_transcript_path": transcript,
        "reference_transcript_sha256": _file_sha(transcript),
        "rights_record_id": rights.rights_record_id,
        "rights_record_path": rights_path,
        "rights_record_canonical_sha256": canonical_sha256(rights),
        "size_bytes": (REPO / asset).stat().st_size,
        "duration_seconds": format(Decimal(frames) / Decimal(rate), "f"),
        "frame_count": frames,
        "sample_rate_hz": rate,
        "channels": channels,
        "sample_width_bytes": sample_width,
        "slot": slot,
    }
    assert rights.asset_id == record["asset_id"] and rights.asset_hash == record["asset_sha256"]
    return record, HashedRightsRecord(record_sha256=canonical_sha256(rights), record=rights)


def _anchors() -> dict[str, object]:
    return {
        "repository": "vangnguyen/npd-video-factory-v2",
        "governance_main_commit": MAIN,
        "governance_main_ci_run_id": MAIN_CI,
        "main_provenance": "PASS",
        "dual_ci_provenance": "PASS",
        "dual_ci_provenance_sha256": PROVENANCE,
        "rc_tag": RC_TAG,
        "rc_commit": RC_COMMIT,
        "executable_rc_ci_run_id": RC_CI,
        "executable_tree_sha256": TREE,
    }


def _window() -> dict[str, object]:
    return {
        "timezone": "Asia/Ho_Chi_Minh",
        "start_ict": "2026-09-21T21:00:00+07:00",
        "end_ict": "2026-09-22T01:00:00+07:00",
        "start_utc": START.isoformat(),
        "end_utc": END.isoformat(),
        "budget_day_utc": "2026-09-21",
        "status": "PROPOSED_NOT_AUTHORIZED",
        "active": False,
    }


def build() -> dict[str, bytes]:
    assert _git("rev-parse", "HEAD") == MAIN
    assert _git("rev-parse", RC_TAG + "^{}") == RC_COMMIT
    objects = {path: _git("rev-parse", f"{MAIN}:{path}") for path in EXECUTABLE_TREE_PATHS}
    assert executable_tree_sha256(objects) == TREE
    assert _git("rev-parse", f"{RC_COMMIT}:{RUNNER}") == _git("rev-parse", f"{MAIN}:{RUNNER}")
    runner_blob = _git("rev-parse", f"{RC_COMMIT}:{RUNNER}")

    profile_payload = json.loads((REPO / "docs/acceptance/v3-01/contracts/V3-01-25-W1-PROMPT-PROFILE.v1.json").read_text(encoding="utf-8"))
    profile = validate_prompt_profile(profile_payload)
    assert profile is not None and prompt_profile_sha256(profile) == PROFILE_SHA
    assert profile.prompt_sha256 == PROMPT_SHA == _sha(W1_PROMPT.encode("utf-8"))
    asset1, rights1 = _input(1)
    asset2, rights2 = _input(2)
    assert asset1["asset_sha256"] == ASSET_SHA
    assert asset1["reference_transcript_sha256"] == TRANSCRIPT_SHA
    assert asset1["rights_record_canonical_sha256"] == RIGHTS_SHA
    assert asset1["size_bytes"] == 5_800_940 and asset1["duration_seconds"] == "120.852"

    lineage = derive_acceptance_lineage_id(
        rc_tag=RC_TAG, rc_commit=RC_COMMIT, provider_key="openai-transcription",
        model="whisper-1", capability="asr", sequence=1,
    )
    assert ledger_database_name(RC_TAG, lineage) == LEDGER
    operations = tuple(ProviderAllowedOperation.model_validate({
        "asset_hash": asset["asset_sha256"], "asset_id": asset["asset_id"],
        "operation": "flow_a_asr", "operation_key": derive_rc_bound_operation_key(
            rc_tag=RC_TAG, provider_key="openai-transcription", capability="asr",
            slot=slot, acceptance_lineage_id=lineage,
        ), "slot": slot,
    }) for slot, asset in ((1, asset1), (2, asset2)))
    op = operations[0].operation_key
    assert op != RC19_OPERATION
    operation_binding = {
        "rc_tag": RC_TAG, "rc_commit": RC_COMMIT, "executable_tree_sha256": TREE,
        "acceptance_lineage_id": lineage, "ledger_identity": LEDGER,
        "operation_key": op, "slot": 1, "provider_key": "openai-transcription",
        "model": "whisper-1", "capability": "asr",
    }
    binding_sha = canonical_sha256(operation_binding)
    budget = OpenAIAsrGateBudgetEnvelope.model_validate({
        "currency": "VND", "per_operation_limit_vnd": "500",
        "acceptance_window_limit_vnd": "1250", "vnd_per_minute": "162",
        "budget_day_utc": "2026-09-21", "files_per_operation": 1,
        "max_file_bytes": 25_000_000, "max_duration_seconds": 180.0,
        "requested_language": "vi", "response_format": "verbose_json",
        "timestamp_granularities": ["segment", "word"],
        "max_attempts": 1, "max_concurrent_calls": 1,
        "automatic_retry": False, "model_fallback": False,
        "provider_http_timeout_seconds": 90.0,
        "controller_hard_timeout_seconds": 120.0,
    })
    modeled = (Decimal(str(asset1["duration_seconds"])) * Decimal("162") / Decimal("60"))
    assert modeled == Decimal("326.3004") and modeled < Decimal("500")
    budget_payload = budget.model_dump(mode="json")
    execution_sha = execution_scope_sha256(
        rc_tag=RC_TAG, rc_commit=RC_COMMIT, provider_key="openai-transcription",
        model="whisper-1", capability="asr", credential_alias=ALIAS,
        valid_from_utc=START, expires_at_utc=END, budget=budget,
        allowed_operations=operations,
        rights_record_sha256s=(rights1.record_sha256, rights2.record_sha256),
        asr_prompt_profile=profile, acceptance_lineage_sequence=1,
        acceptance_lineage_id=lineage,
    )
    approvals = {gate: {"status": "NOT_CREATED", "record_sha256": None} for gate in ("G-01", "G-02", "G-03")}
    template = {
        "version": 2, "bundle_id": "V3-01-GATE-RC20-OPENAI-ASR-W1-LINEAGE-A-PREPARED",
        "rc_tag": RC_TAG, "rc_commit": RC_COMMIT,
        "acceptance_lineage_sequence": 1, "acceptance_lineage_id": lineage,
        "provider_key": "openai-transcription", "model": "whisper-1", "capability": "asr",
        "credential_alias": ALIAS, "valid_from_utc": START.isoformat(),
        "expires_at_utc": END.isoformat(), "budget": budget_payload,
        "allowed_operations": [item.model_dump(mode="json") for item in operations],
        "rights_records": [rights1.model_dump(mode="json"), rights2.model_dump(mode="json")],
        "asr_prompt_profile": profile.model_dump(mode="json"),
        "owner_approval_slots": approvals, "preparation_status": "PREPARED_NOT_AUTHORIZED",
        "runtime_loadable": False, "operation_2_status": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
    }
    template_raw = _json_bytes(template)
    template_sha = _sha(template_raw)
    scope = {
        "schema": "vf-v0s-b15-prepared-scope-v1", "status": "PREPARED_NOT_AUTHORIZED",
        "anchors": _anchors(), "acceptance_lineage_id": lineage,
        "ledger_identity": LEDGER, "operation_key": op,
        "ledger_operation_binding_sha256": binding_sha,
        "runner_entrypoint": "app.provider_single_dispatch.run_single_dispatch",
        "runner_git_blob": runner_blob, "execution_scope_sha256": execution_sha,
        "provider_key": "openai-transcription", "model": "whisper-1",
        "capability": "asr", "language": "vi", "credential_alias_reference_only": ALIAS,
        "w1_profile_sha256": PROFILE_SHA, "prompt_sha256": PROMPT_SHA,
        "asset": asset1, "slot_2_negative_guard_only": asset2,
        "budget": budget_payload, "modeled_cost_vnd": format(modeled, "f"),
        "window": _window(), "approval_slots": approvals,
        "kill_switch": "ENGAGED", "bundle_mounted": False,
        "operation_2_status": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
    }
    scope_sha = canonical_sha256(scope)
    manifest = {
        "schema": "vf-v0s-b15-operation-manifest-v1", "status": "PREPARED_NOT_AUTHORIZED",
        "operation_id": op, "ledger_operation_key": op, "ledger_identity": LEDGER,
        "acceptance_lineage_id": lineage, "slot": 1,
        "anchors": _anchors(), "execution_scope_sha256": execution_sha,
        "prepared_scope_sha256": scope_sha, "template_sha256": template_sha,
        "ledger_operation_binding_sha256": binding_sha,
        "runner_git_blob": runner_blob,
        "provider_key": "openai-transcription", "model": "whisper-1",
        "capability": "asr", "language": "vi", "w1_profile_sha256": PROFILE_SHA,
        "prompt_sha256": PROMPT_SHA, "asset_sha256": ASSET_SHA,
        "reference_transcript_sha256": TRANSCRIPT_SHA,
        "rights_record_sha256": RIGHTS_SHA, "budget": budget_payload,
        "window": _window(), "authority_receipt_sha256": None,
        "operation_2_status": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
    }
    manifest_sha = canonical_sha256(manifest)
    package = {
        "schema": "vf-v0s-b15-operation-preparation-package-v1",
        "task_id": "VF-V0S-B15", "status": "PREPARED_NOT_AUTHORIZED",
        "anchors": _anchors(), "acceptance_lineage_id": lineage,
        "ledger": {
            "identity": LEDGER, "system_identifier": "7686186223531422166",
            "postgres_version": "16.15", "migration_head": "0015_v3_01_dispatch",
            "custody": "VERIFIED", "operation_state": "VIRGIN_NOT_REGISTERED / NOT_CONSUMED",
            "operation_record_exists": False, "provider_request_receipt_exists": False,
            "active_reservation": False, "duplicate_or_idempotency_collision": False,
            "prepared_operation_metadata_write": False,
        },
        "operation_id": op, "ledger_operation_key": op,
        "ledger_operation_binding_sha256": binding_sha,
        "execution_scope_sha256": execution_sha, "prepared_scope_sha256": scope_sha,
        "operation_manifest_sha256": manifest_sha, "preparation_template_sha256": template_sha,
        "immutable_input": asset1, "w1_profile_sha256": PROFILE_SHA,
        "prompt_sha256": PROMPT_SHA, "provider_key": "openai-transcription",
        "model": "whisper-1", "capability": "asr", "language": "vi",
        "runner_contract": {
            "entrypoint": "app.provider_single_dispatch.run_single_dispatch",
            "git_blob": runner_blob, "attempts": 1, "concurrency": 1, "retry": 0,
            "fallback": 0, "provider_timeout_seconds": 90,
            "controller_timeout_seconds": 120,
            "pre_dispatch": "No durable dispatch marker: release reservation, NOT_CONSUMED, zero provider calls",
            "post_dispatch": "Durable dispatch marker: terminal/possibly-sent, no second call, reconcile reservation",
            "kill_switch": "ENGAGED until bounded one-call transition; always re-engage",
            "evidence": "arm before dispatch marker; seal pre-call or post-dispatch terminal evidence",
        },
        "budget": {
            "accounting_source": "https://developers.openai.com/api/docs/models/whisper-1",
            "usd_per_minute": "0.006", "fixed_accounting_vnd_per_usd": "27000",
            "vnd_per_minute": "162", "duration_seconds": asset1["duration_seconds"],
            "modeled_cost_vnd": format(modeled, "f"),
            "proposed_per_operation_ceiling_vnd": "500",
            "proposed_window_ceiling_vnd": "1250",
            "status": "PROPOSED_NOT_AUTHORIZED", "reserved_vnd": "0",
        },
        "proposed_window": _window(), "approvals": approvals,
        "authority_status": "NOT_CREATED", "authority_receipt_sha256": None,
        "final_runtime_bundle_sha256": None, "bundle_mounted": False,
        "operation_bound_bootstrap": "DEFERRED_BY_CONTRACT",
        "required_order": ["B15_PREPARATION", "B16_FINAL_APPROVALS_AUTHORITY_BUNDLE", "B17_ZERO_CALL_BOOTSTRAP"],
        "quality_gate": {
            "wer_max_percent": "15", "critical_terms_required": 8,
            "critical_terms_total": 8, "asset_02_negative_insertion_guard": True,
            "reference_transcript_mutation": False,
            "transcript_post_correction": False,
        },
        "future_evidence_required": [
            "request_hash", "dispatch_marker", "provider_request_id", "response_hash",
            "transcript", "timestamps", "w1_profile_and_prompt", "usage_and_cost",
            "latency_and_timeout_phase", "reservation_and_reconciliation",
            "ledger_and_circuit", "idempotency", "rights_record", "secret_scan",
            "wer_critical_terms_and_insertion_guard",
            "evidence_manifest_sha256",
        ],
        "operation_2_status": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
        "safety": {
            "kill_switch": "ENGAGED", "credential_reads": 0,
            "budget_reserved_vnd": "0", "real_provider_calls": 0,
            "production_business_writes": 0, "actual_cost_vnd": "0",
        },
        "historical_rc19_operation_id_reused": False,
    }
    outputs = {
        "gate-template.json": template_raw,
        "scope-candidate.json": _json_bytes(scope),
        "operation-1-manifest.json": _json_bytes(manifest),
        "operation-preparation-package.json": _json_bytes(package),
    }
    hashes = {
        "schema": "vf-v0s-b15-prepared-hashes-v1", "status": "PREPARED_NOT_AUTHORIZED",
        "operation_id": op, "acceptance_lineage_id": lineage,
        "execution_scope_sha256": execution_sha, "prepared_scope_sha256": scope_sha,
        "operation_manifest_sha256": manifest_sha,
        "preparation_template_sha256": template_sha,
        "ledger_operation_binding_sha256": binding_sha,
        "package_canonical_sha256": canonical_sha256(package),
        "canonicalization": "UTF-8 JSON, sorted keys, compact separators; file hashes cover exact pretty UTF-8 LF bytes",
        "files_sha256": {name: _sha(raw) for name, raw in sorted(outputs.items())},
    }
    outputs["prepared-material-hashes.json"] = _json_bytes(hashes)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-file", choices=(
        "gate-template.json", "scope-candidate.json", "operation-1-manifest.json",
        "operation-preparation-package.json", "prepared-material-hashes.json",
    ))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = build()
    if args.print_file:
        sys.stdout.buffer.write(outputs[args.print_file])
    elif args.check:
        assert outputs == build(), "NONDETERMINISTIC_PREPARATION_MATERIAL"
        for name, raw in outputs.items():
            assert (HERE / name).read_bytes() == raw, f"MATERIAL_REPRODUCTION_MISMATCH:{name}"
        print(json.dumps({"result": "PASS", "files": len(outputs),
                          "hashes": json.loads(outputs["prepared-material-hashes.json"])}, sort_keys=True))
    else:
        print(json.dumps(json.loads(outputs["prepared-material-hashes.json"]), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
