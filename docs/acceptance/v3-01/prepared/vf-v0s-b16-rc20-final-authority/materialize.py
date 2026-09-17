"""Reproduce VF-V0S-B16R's correction of B16 authority CI-run bindings offline.

No database connection, credential resolver, reservation, mount or provider
client is constructed here. This script only reads canonical source material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
B15 = REPO / "docs/acceptance/v3-01/prepared/vf-v0s-b15-rc20-asr-w1"
sys.path.insert(0, str(REPO / "apps/api"))

from app.asr_prompt_profile import prompt_profile_sha256, validate_prompt_profile  # noqa: E402
from app.provider_ci_provenance import (  # noqa: E402
    EXECUTABLE_TREE_PATHS,
    executable_tree_sha256,
    provider_ci_provenance_sha256,
    validate_provider_acceptance_ci_provenance,
)
from app.provider_gate_loader import (  # noqa: E402
    OpenAIAsrGateBundle,
    ProviderApprovalRecord,
    canonical_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_runtime_bootstrap import BootstrapLedgerBinding, ledger_database_name  # noqa: E402
from app.provider_single_dispatch import _load_authority, _verify_authority  # noqa: E402
from app.provider_safety import derive_acceptance_lineage_id, derive_rc_bound_operation_key  # noqa: E402


MAIN = "4ac4880d5627c2800eb918d24c59da5f8e047091"
RC_TAG = "vf-v3-01-rc20"
RC_COMMIT = "93b5441d44347c9c40b745bdfed0969880853f68"
TREE = "611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630"
PROVENANCE = "5caca534d1cfa6a4e3d9b4f9f9b6b1c33b024ec65afdfc36cf875c673bc1eb86"
RC_CI_RUN = 35124578033
MAIN_CI_RUN = 35172654970
LEDGER = "vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d"
OPERATION = (
    "v3-01-rc20-openai-transcription-asr-al-0001-"
    "9722891b4ae68168375adea9fc53cc6ad89c20fa8f3c5d8535f056173f428624-call-01"
)
EXECUTION_SHA = "cc68432affb13d290860cb7ca71feb3efb46f0e82541c6d0d2a54fff60d00093"
PREPARED_SCOPE_SHA = "667c88a949feec343e6b37934ba4705edbb0c616ba92217124227045ad5a4be4"
MANIFEST_SHA = "a16fb870af5572e57081a3de7f8d90c789393445efa5dcaa5186bc562b13d4d2"
TEMPLATE_SHA = "6c3efc700df2c3c2163c0ff9f7ea8f71af728e5f1eec5b1c55c1ef92301057c0"
PROFILE_SHA = "9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1"
PROMPT_SHA = "6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48"
ASSET_SHA = "fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef"
TRANSCRIPT_SHA = "585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e"
RIGHTS_SHA = "5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091"
APPROVED_AT = "2026-09-17T02:56:22Z"  # Owner decision in VF-V0S-B16; not a historical claim.
START = "2026-09-21T14:00:00Z"
END = "2026-09-21T18:00:00Z"
RUNNER_PATH = "apps/api/app/provider_single_dispatch.py"
RUNNER_BLOB = "a61a035d7b8e60be61581ce5d9d59028e2715688"
APPROVAL_IDS = {"G-01": "V3-01-APP-078", "G-02": "V3-01-APP-079", "G-03": "V3-01-APP-080"}
REL = "docs/acceptance/v3-01/prepared/vf-v0s-b16-rc20-final-authority"
BASELINE_PROVENANCE = REPO / "docs/acceptance/v3-01/reviews/vf-v0s-b16r/baseline-dual-ci-provenance.json"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _load(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def _binding(payload: dict) -> BootstrapLedgerBinding:
    # The execution socket is a Linux absolute path. Windows Path.is_absolute()
    # cannot validate that Linux-only contract; the final artifact is separately
    # schema-validated under Linux before any B17 qualification.
    if sys.platform == "win32":
        assert payload["socket_directory"].startswith("/home/vang_nguyen/")
        return BootstrapLedgerBinding.model_construct(**payload)
    return BootstrapLedgerBinding.model_validate(payload)


def _check_inputs() -> tuple[dict, dict, dict, dict]:
    # This candidate is branched directly from MAIN and carries the B15 package.
    assert _git("ls-remote", "--heads", "origin", "main").split()[0] == MAIN
    assert _git("rev-parse", RC_TAG + "^{}") == RC_COMMIT
    objects = {path: _git("rev-parse", f"{MAIN}:{path}") for path in EXECUTABLE_TREE_PATHS}
    assert executable_tree_sha256(objects) == TREE
    assert _git("rev-parse", f"{RC_COMMIT}:{RUNNER_PATH}") == RUNNER_BLOB
    assert _git("rev-parse", f"{MAIN}:{RUNNER_PATH}") == RUNNER_BLOB
    template = _load(B15 / "gate-template.json")
    prepared_scope = _load(B15 / "scope-candidate.json")
    manifest = _load(B15 / "operation-1-manifest.json")
    package = _load(B15 / "operation-preparation-package.json")
    hashes = _load(B15 / "prepared-material-hashes.json")
    for name, expected in {
        "gate-template.json": TEMPLATE_SHA,
        "scope-candidate.json": hashes["files_sha256"]["scope-candidate.json"],
        "operation-1-manifest.json": hashes["files_sha256"]["operation-1-manifest.json"],
        "operation-preparation-package.json": hashes["files_sha256"]["operation-preparation-package.json"],
    }.items():
        assert _sha((B15 / name).read_bytes()) == expected == hashes["files_sha256"][name]
    assert canonical_sha256(prepared_scope) == PREPARED_SCOPE_SHA
    assert canonical_sha256(manifest) == MANIFEST_SHA
    assert package["execution_scope_sha256"] == EXECUTION_SHA
    assert package["prepared_scope_sha256"] == PREPARED_SCOPE_SHA
    assert package["operation_manifest_sha256"] == MANIFEST_SHA
    assert package["preparation_template_sha256"] == TEMPLATE_SHA
    assert package["anchors"]["dual_ci_provenance_sha256"] == PROVENANCE
    assert package["operation_id"] == OPERATION == package["ledger_operation_key"]
    assert package["ledger"]["identity"] == LEDGER
    assert package["ledger"]["system_identifier"] == "7686186223531422166"
    assert package["ledger"]["migration_head"] == "0015_v3_01_dispatch"
    assert package["status"] == "PREPARED_NOT_AUTHORIZED"
    assert package["authority_status"] == "NOT_CREATED"
    assert template["runtime_loadable"] is False
    assert template["preparation_status"] == "PREPARED_NOT_AUTHORIZED"
    assert all(v["record_sha256"] is None for v in template["owner_approval_slots"].values())
    assert template["provider_key"] == "openai-transcription" and template["model"] == "whisper-1"
    assert template["capability"] == "asr" and package["language"] == "vi"
    assert template["allowed_operations"][0]["operation_key"] == OPERATION
    assert template["valid_from_utc"] == "2026-09-21T14:00:00+00:00"
    assert template["expires_at_utc"] == "2026-09-21T18:00:00+00:00"
    assert template["budget"]["per_operation_limit_vnd"] == "500"
    assert template["budget"]["acceptance_window_limit_vnd"] == "1250"
    assert package["budget"]["modeled_cost_vnd"] == "326.3004"
    assert Decimal(package["budget"]["duration_seconds"]) * Decimal("162") / Decimal("60") == Decimal("326.3004")
    assert template["budget"]["max_attempts"] == template["budget"]["max_concurrent_calls"] == 1
    assert template["budget"]["automatic_retry"] is False and template["budget"]["model_fallback"] is False
    assert template["budget"]["provider_http_timeout_seconds"] == 90.0
    assert template["budget"]["controller_hard_timeout_seconds"] == 120.0
    lineage = derive_acceptance_lineage_id(
        rc_tag=RC_TAG, rc_commit=RC_COMMIT, provider_key="openai-transcription",
        model="whisper-1", capability="asr", sequence=1,
    )
    assert lineage == template["acceptance_lineage_id"]
    assert ledger_database_name(RC_TAG, lineage) == LEDGER
    assert derive_rc_bound_operation_key(
        rc_tag=RC_TAG, provider_key="openai-transcription", capability="asr",
        slot=1, acceptance_lineage_id=lineage,
    ) == OPERATION
    profile = validate_prompt_profile(_load(REPO / "docs/acceptance/v3-01/contracts/V3-01-25-W1-PROMPT-PROFILE.v1.json"))
    assert profile is not None and prompt_profile_sha256(profile) == PROFILE_SHA
    assert profile.prompt_sha256 == PROMPT_SHA == _sha(profile.prompt.encode("utf-8"))
    assert template["asr_prompt_profile"] == profile.model_dump(mode="json")
    assert _sha((REPO / package["immutable_input"]["asset_path"]).read_bytes()) == ASSET_SHA
    assert _sha((REPO / package["immutable_input"]["reference_transcript_path"]).read_bytes()) == TRANSCRIPT_SHA
    assert canonical_sha256(_load(REPO / package["immutable_input"]["rights_record_path"])) == RIGHTS_SHA
    assert template["rights_records"][0]["record_sha256"] == RIGHTS_SHA
    assert all(canonical_sha256(item["record"]) == item["record_sha256"]
               for item in template["rights_records"])
    assert _sha((REPO / "docs/acceptance/v3-01/assets/g03-asr-vi-owned-02.wav").read_bytes()) == template["rights_records"][1]["record"]["asset_hash"]
    return template, prepared_scope, manifest, package


def _approval(gate: str, template: dict, package: dict, provider_hash: str, budget_hash: str, window_hash: str) -> dict:
    common = [RC_COMMIT, TREE, MAIN, PROVENANCE, LEDGER, OPERATION, EXECUTION_SHA,
              MANIFEST_SHA, RUNNER_BLOB, PROFILE_SHA, PROMPT_SHA, ASSET_SHA, TRANSCRIPT_SHA,
              RIGHTS_SHA, TEMPLATE_SHA, window_hash]
    if gate == "G-01":
        scope = "VF-V0S-B16 Owner approval: exact RC-20 ASR W1 Operation 1 execution binding only."
        hashes = common + [provider_hash]
        limits = ["Operation 1 only; Operation 2 remains locked", "openai-transcription / whisper-1 / asr / vi only",
                  "Single-dispatch runner and exact lineage-bound ledger only", "Credential alias is a reference, never a plaintext secret"]
    elif gate == "G-02":
        scope = "VF-V0S-B16 Owner approval: one RC-20 Operation 1 budget envelope only; no reservation in B16."
        hashes = common + [budget_hash]
        limits = ["Modeled 326.3004 VND", "500 VND per-operation maximum", "1250 VND window maximum",
                  "One attempt and one concurrent call; retry 0; fallback 0", "90s provider and 120s controller timeouts",
                  "Reserve only during future fresh execution preflight; release before dispatch or reconcile after dispatch"]
    else:
        scope = "VF-V0S-B16 Owner approval: exact RC-20 Operation 1 asset, rights and 2026-09-21 UTC window only."
        hashes = common + [template["rights_records"][1]["record_sha256"]]
        limits = ["Operation 1 asset and RightsRecord 001 only", "Window 2026-09-21T14:00:00Z to 2026-09-21T18:00:00Z exclusively",
                  "ICT 2026-09-21 21:00 to 2026-09-22 01:00", "Expires at window end; no extension or inherited RC-19 window",
                  "RightsRecord 002 is bound only because the two-slot gate schema requires it; Operation 2 is not approved"]
    record = ProviderApprovalRecord.model_validate({
        "approval_id": APPROVAL_IDS[gate], "gate_id": gate, "decision": "APPROVED",
        "scope": scope, "artifact_or_commit_hashes": list(dict.fromkeys(hashes)),
        "target_account_or_environment": f"RC-20 isolated acceptance ledger {LEDGER}",
        "limits": limits, "approved_by": "Owner (GitHub: vangnguyen)",
        "approved_at_utc": APPROVED_AT, "expires_at_utc": END,
        "notes": "Authority source: explicit Owner VF-V0S-B16 instruction. No B16 execution, credential access, reservation, mount, kill-switch transition or provider call.",
    })
    return record.model_dump(mode="json")


def build() -> dict[str, bytes]:
    template, prepared_scope, manifest, package = _check_inputs()
    provider_hash = canonical_sha256({
        "provider_key": template["provider_key"], "model": template["model"],
        "capability": template["capability"], "credential_alias": template["credential_alias"],
    })
    budget_hash = canonical_sha256(template["budget"])
    window_hash = canonical_sha256({
        "valid_from_utc": START, "expires_at_utc": END, "timezone": "Asia/Ho_Chi_Minh",
        "operation_key": OPERATION, "slot": 1,
    })
    records = {gate: _approval(gate, template, package, provider_hash, budget_hash, window_hash)
               for gate in ("G-01", "G-02", "G-03")}
    record_hashes = {gate: canonical_sha256(record) for gate, record in records.items()}
    bundle = {key: value for key, value in template.items() if key not in {
        "owner_approval_slots", "preparation_status", "runtime_loadable", "operation_2_status"}}
    bundle["bundle_id"] = "V3-01-GATE-RC20-OPENAI-ASR-W1-LINEAGE-A"
    for gate, key in (("G-01", "credential_approval"), ("G-02", "budget_approval"), ("G-03", "rights_approval")):
        bundle[key] = {"record_sha256": record_hashes[gate], "record": records[gate]}
    validated = OpenAIAsrGateBundle.model_validate(bundle)
    assert validated.rc_tag == RC_TAG and validated.rc_commit == RC_COMMIT
    bundle_bytes = _json_bytes(bundle)
    bundle_sha = _sha(bundle_bytes)
    # The runtime loader checks raw bytes plus every strict schema and approval invariant.
    # It is called against a file only in --check after patch-created artifacts exist.
    scope = _scope_from_bundle(bundle, bundle_sha)
    loaded_scope_sha = canonical_sha256(scope)
    assert scope.execution_scope_sha256 == EXECUTION_SHA
    assert loaded_scope_sha != PREPARED_SCOPE_SHA
    assert scope.approval_record_sha256 == record_hashes
    binding = _binding({
        "version": 1, "mode": "ZERO_CALL_CUSTODY_ONLY", "environment": "v3_01_acceptance_runtime",
        "rc_tag": RC_TAG, "rc_commit": RC_COMMIT, "governance_main_commit": MAIN,
        "executable_tree_sha256": TREE, "acceptance_lineage_id": template["acceptance_lineage_id"],
        "sequence": 1, "provider_key": "openai-transcription", "model": "whisper-1",
        "capability": "asr", "language": "vi", "slot": 1, "operation_key": OPERATION,
        "authority_receipt_sha256": "0" * 64, "bundle_sha256": bundle_sha,
        "execution_scope_sha256": EXECUTION_SHA, "scope_sha256": loaded_scope_sha,
        "w1_profile_sha256": PROFILE_SHA, "prompt_sha256": PROMPT_SHA,
        "asset_sha256": ASSET_SHA, "reference_transcript_sha256": TRANSCRIPT_SHA,
        "rights_record_sha256": RIGHTS_SHA, "system_identifier": "7686186223531422166",
        "database_oid": 16384, "database_name": LEDGER, "database_role": "vang_nguyen",
        "schema_name": "public", "postgres_major": 16,
        "socket_directory": "/home/vang_nguyen/.local/share/npd-vf-rc20-ledger-9722891b4ae6/socket",
        "port": 55440, "kill_switch_engaged": True,
        "external_execution_enabled": False, "paid_execution_enabled": False,
        "budget_reserved_vnd": "0",
    })
    authority = {
        "schema": "vf-v0s-b16r-rc20-op1-authority-v1", "authority_source": "VF-V0S-B16 explicit Owner instruction; VF-V0S-B16R CI-run binding correction",
        "approved_at_utc": APPROVED_AT, "decision": "APPROVED", "status": "GRANTED_NOT_CONSUMED",
        "main_provenance": "PASS", "rc_tag": RC_TAG, "rc_commit": RC_COMMIT,
        "governance_main_commit": MAIN, "executable_tree_sha256": TREE,
        "dual_ci_provenance_sha256": PROVENANCE,
        "executable_rc_ci_run_id": RC_CI_RUN,
        "governance_main_ci_run_id": MAIN_CI_RUN,
        "operation_key": OPERATION,
        "acceptance_lineage_id": template["acceptance_lineage_id"],
        "execution_scope_sha256": EXECUTION_SHA, "prepared_scope_sha256": PREPARED_SCOPE_SHA,
        "loaded_runtime_scope_sha256": loaded_scope_sha, "gate_bundle_sha256": bundle_sha,
        "operation_manifest_sha256": MANIFEST_SHA, "preparation_template_sha256": TEMPLATE_SHA,
        "asset_sha256": ASSET_SHA, "reference_transcript_sha256": TRANSCRIPT_SHA,
        "rights_record_sha256": RIGHTS_SHA, "asr_prompt_profile_sha256": PROFILE_SHA,
        "prompt_sha256": PROMPT_SHA, "provider_key": "openai-transcription", "model": "whisper-1",
        "capability": "asr", "language": "vi", "slot": 1,
        "operation_1_consumed": False, "operation_2_authorized": False,
        "budget_reserved_vnd": "0", "bundle_mounted": False,
        "dispatch_requires_separate_execution_task": True,
        "single_dispatch_entrypoint": "app.provider_single_dispatch.run_single_dispatch",
        "single_dispatch_runner_git_blob": RUNNER_BLOB,
        "kill_switch": "ENGAGED", "ledger": {
            "identity": LEDGER, "system_identifier": "7686186223531422166", "database_oid": 16384,
            "migration_head": "0015_v3_01_dispatch", "operation_state": "VIRGIN_NOT_REGISTERED / NOT_CONSUMED",
        },
        "approval_records": {gate: {"approval_id": APPROVAL_IDS[gate], "record_sha256": record_hashes[gate]}
                             for gate in ("G-01", "G-02", "G-03")},
        "limits": {
            "per_operation_limit_vnd": "500", "acceptance_window_limit_vnd": "1250",
            "modeled_cost_vnd": "326.3004", "max_attempts": 1, "max_concurrent_calls": 1,
            "automatic_retry": False, "model_fallback": False,
            "provider_http_timeout_seconds": 90.0, "controller_hard_timeout_seconds": 120.0,
        },
        "valid_from_utc": START, "expires_at_utc": END,
        "no_execution_in_this_task": True,
    }
    _verify_authority(authority, binding, scope, provenance_sha256=PROVENANCE, operation_manifest_sha256=MANIFEST_SHA)
    assert authority["executable_rc_ci_run_id"] == RC_CI_RUN
    assert authority["governance_main_ci_run_id"] == MAIN_CI_RUN
    authority_bytes = _json_bytes(authority)
    authority_sha = _sha(authority_bytes)
    binding_payload = binding.model_dump(mode="json")
    binding_payload["authority_receipt_sha256"] = authority_sha
    binding = _binding(binding_payload)
    _verify_authority(authority, binding, scope, provenance_sha256=PROVENANCE, operation_manifest_sha256=MANIFEST_SHA)
    final = {
        "schema": "vf-v0s-b16r-final-material-hashes-v1", "task_id": "VF-V0S-B16R",
        "owner_approval_source": "VF-V0S-B16", "status": "GRANTED_NOT_CONSUMED",
        "governance_main_commit": MAIN, "rc_tag": RC_TAG, "rc_commit": RC_COMMIT,
        "executable_tree_sha256": TREE, "dual_ci_provenance_sha256": PROVENANCE,
        "executable_rc_ci_run_id": RC_CI_RUN,
        "governance_main_ci_run_id": MAIN_CI_RUN,
        "ledger_identity": LEDGER, "operation_key": OPERATION,
        "execution_scope_sha256": EXECUTION_SHA, "prepared_scope_sha256": PREPARED_SCOPE_SHA,
        "operation_manifest_sha256": MANIFEST_SHA, "preparation_template_sha256": TEMPLATE_SHA,
        "approval_record_sha256": record_hashes, "final_loaded_scope_sha256": loaded_scope_sha,
        "final_runtime_bundle_sha256": bundle_sha, "authority_receipt_sha256": authority_sha,
        "historical_b16_authority_receipt_sha256": "694693ca50001c93d5264418661bc8a25179a3791d6437e077f67653c2a3140c",
        "bootstrap_binding_sha256": _sha(_json_bytes(binding_payload)),
        "window": {"start_utc": START, "end_utc": END,
                   "start_ict": "2026-09-21T21:00:00+07:00", "end_ict": "2026-09-22T01:00:00+07:00"},
        "safety": {"kill_switch": "ENGAGED", "bundle_mounted": False,
                   "budget_reserved_vnd": "0", "credential_reads": 0,
                   "real_provider_calls": 0, "production_business_writes": 0, "actual_cost_vnd": "0"},
        "operation_bound_bootstrap": "READY_FOR_B17_NOT_RUN",
    }
    outputs = {
        f"docs/acceptance/v3-01/approvals/{APPROVAL_IDS[gate]}.json": _json_bytes(records[gate])
        for gate in ("G-01", "G-02", "G-03")
    }
    outputs.update({
        f"{REL}/final-runtime-bundle.json": bundle_bytes,
        f"{REL}/final-loaded-scope.json": _json_bytes(scope.model_dump(mode="json")),
        f"{REL}/operation-1-authority.json": authority_bytes,
        f"{REL}/bootstrap-binding-for-b17.json": _json_bytes(binding_payload),
        f"{REL}/final-material-hashes.json": _json_bytes(final),
    })
    return outputs


def _scope_from_bundle(bundle: dict, bundle_sha: str):
    # Match the verified loader's projection without creating a temporary file.
    from app.provider_gate_loader import (  # noqa: E402
        ProviderExecutionGateScope, execution_scope_sha256, prompt_profile_sha256,
    )
    parsed = OpenAIAsrGateBundle.model_validate(bundle)
    rights_hashes = tuple(item.record_sha256 for item in parsed.rights_records)
    hashes = {gate: value.record_sha256 for gate, value in (
        ("G-01", parsed.credential_approval), ("G-02", parsed.budget_approval),
        ("G-03", parsed.rights_approval))}
    scope_sha = execution_scope_sha256(
        rc_tag=parsed.rc_tag, rc_commit=parsed.rc_commit, provider_key=parsed.provider_key,
        model=parsed.model, capability=parsed.capability, credential_alias=parsed.credential_alias,
        valid_from_utc=parsed.valid_from_utc, expires_at_utc=parsed.expires_at_utc,
        budget=parsed.budget, rights_record_sha256s=rights_hashes,
        allowed_operations=parsed.allowed_operations, asr_prompt_profile=parsed.asr_prompt_profile,
        acceptance_lineage_sequence=parsed.acceptance_lineage_sequence,
        acceptance_lineage_id=parsed.acceptance_lineage_id,
    )
    return ProviderExecutionGateScope(
        gate_bundle_version=parsed.version, bundle_id=parsed.bundle_id, bundle_sha256=bundle_sha,
        rc_tag=parsed.rc_tag, rc_commit=parsed.rc_commit, provider_key=parsed.provider_key,
        model=parsed.model, capability=parsed.capability,
        acceptance_lineage_sequence=parsed.acceptance_lineage_sequence,
        acceptance_lineage_id=parsed.acceptance_lineage_id,
        credential_alias=parsed.credential_alias, valid_from_utc=parsed.valid_from_utc,
        expires_at_utc=parsed.expires_at_utc, budget_day_utc=parsed.budget.budget_day_utc,
        per_operation_limit_vnd=parsed.budget.per_operation_limit_vnd,
        acceptance_window_limit_vnd=parsed.budget.acceptance_window_limit_vnd,
        provider_http_timeout_seconds=parsed.budget.provider_http_timeout_seconds,
        controller_hard_timeout_seconds=parsed.budget.controller_hard_timeout_seconds,
        max_attempts=parsed.budget.max_attempts, max_concurrent_calls=parsed.budget.max_concurrent_calls,
        credential_approval_id=parsed.credential_approval.record.approval_id,
        budget_approval_id=parsed.budget_approval.record.approval_id,
        rights_approval_id=parsed.rights_approval.record.approval_id,
        approval_record_sha256=hashes, allowed_operations=parsed.allowed_operations,
        vnd_per_minute=parsed.budget.vnd_per_minute, max_file_bytes=parsed.budget.max_file_bytes,
        max_duration_seconds=parsed.budget.max_duration_seconds,
        requested_language=parsed.budget.requested_language, response_format=parsed.budget.response_format,
        timestamp_granularities=parsed.budget.timestamp_granularities,
        asr_prompt_profile=parsed.asr_prompt_profile,
        asr_prompt_profile_sha256=prompt_profile_sha256(parsed.asr_prompt_profile),
        rights_record_sha256s=rights_hashes, execution_scope_sha256=scope_sha,
        rights_records=tuple(item.record for item in parsed.rights_records),
    )


def check(outputs: dict[str, bytes]) -> None:
    assert outputs == build()  # second independent deterministic construction
    hashes = _load(HERE / "final-material-hashes.json")
    bundle_path = HERE / "final-runtime-bundle.json"
    assert _sha(bundle_path.read_bytes()) == hashes["final_runtime_bundle_sha256"]
    scope = load_verified_provider_gate_bundle(
        bundle_path, expected_bundle_sha256=hashes["final_runtime_bundle_sha256"],
        expected_rc_commit=RC_COMMIT, expected_rc_tag=RC_TAG,
        expected_acceptance_lineage_id=_load(B15 / "gate-template.json")["acceptance_lineage_id"],
    )
    assert canonical_sha256(scope) == hashes["final_loaded_scope_sha256"]
    assert scope.execution_scope_sha256 == EXECUTION_SHA
    authority = _load(HERE / "operation-1-authority.json")
    binding = _binding(_load(HERE / "bootstrap-binding-for-b17.json"))
    assert _sha((HERE / "operation-1-authority.json").read_bytes()) == binding.authority_receipt_sha256
    assert _load_authority(HERE / "operation-1-authority.json", binding.authority_receipt_sha256) == authority
    provenance = validate_provider_acceptance_ci_provenance(
        _load(BASELINE_PROVENANCE),
        expected_executable_rc_commit=binding.rc_commit,
        expected_governance_main_commit=binding.governance_main_commit,
        expected_executable_rc_ci_run_id=authority["executable_rc_ci_run_id"],
        expected_governance_main_ci_run_id=authority["governance_main_ci_run_id"],
    )
    assert provider_ci_provenance_sha256(provenance) == PROVENANCE
    _verify_authority(authority, binding, scope, provenance_sha256=PROVENANCE, operation_manifest_sha256=MANIFEST_SHA)
    for relative, raw in outputs.items():
        assert (REPO / relative).read_bytes() == raw, relative
    # Fail-closed negative controls for the three runtime boundaries.
    tampered_bundle = _load(bundle_path)
    tampered_bundle["budget"]["per_operation_limit_vnd"] = "501"
    try:
        OpenAIAsrGateBundle.model_validate(tampered_bundle)
    except ValueError:
        pass
    else:
        raise AssertionError("G02_BUDGET_TAMPER_WAS_ACCEPTED")
    for field, bad in (("status", "CONSUMED"), ("operation_2_authorized", True),
                       ("valid_from_utc", "2026-09-21T13:59:00Z")):
        tampered_authority = dict(authority)
        tampered_authority[field] = bad
        try:
            _verify_authority(tampered_authority, binding, scope,
                              provenance_sha256=PROVENANCE, operation_manifest_sha256=MANIFEST_SHA)
        except Exception:
            pass
        else:
            raise AssertionError(f"AUTHORITY_TAMPER_ACCEPTED_{field}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-file", choices=list(build().keys()))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    outputs = build()
    if args.print_file:
        sys.stdout.buffer.write(outputs[args.print_file])
    elif args.check:
        check(outputs)
        print("B16R_FINAL_MATERIALS_PASS REAL_GATE_LOADER_PASS AUTHORITY_CI_BINDINGS_PASS DETERMINISTIC_BYTES_PASS")
    elif args.summary:
        sys.stdout.buffer.write(outputs[f"{REL}/final-material-hashes.json"])
    else:
        parser.error("select --print-file, --check or --summary")


if __name__ == "__main__":
    main()
