"""Materialize and reproduce the VF-V0S-B9 RC-19 ASR W1 authority.

This is an offline governance generator. It uses the existing strict gate and
bootstrap models, but it has no credential resolver, reservation path, bundle
mount, kill-switch transition, or provider adapter.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
PREPARED = REPO / "docs/acceptance/v3-01/prepared/vf-v0s-b7-rc19-asr-w1"
APPROVALS_DIR = REPO / "docs/acceptance/v3-01/approvals"
BUNDLE_PATH = REPO / "docs/acceptance/v3-01/V3-01-GATE-RC19-OPENAI-ASR-W1-LINEAGE-A.json"
sys.path.insert(0, str(REPO / "apps/api"))
sys.path.insert(0, str(REPO / "scripts"))

from app.provider_ci_provenance import EXECUTABLE_TREE_PATHS, executable_tree_sha256  # noqa: E402
from app.provider_gate_loader import (  # noqa: E402
    OpenAIAsrGateBundle,
    ProviderApprovalRecord,
    asr_execution_scope_sha256,
    canonical_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_runtime_bootstrap import (  # noqa: E402
    BootstrapLedgerBinding,
    ledger_database_name,
)
from app.provider_safety import (  # noqa: E402
    derive_acceptance_lineage_id,
    derive_rc_bound_operation_key,
)
from v3_01_ci_provenance import _git_object_map  # noqa: E402


TASK = "VF-V0S-B9"
REPOSITORY = "vangnguyen/npd-video-factory-v2"
MAIN = "7ad25cb039c712d450486778d2981d9ef8175385"
MAIN_CI = 34946537685
RC_TAG = "vf-v3-01-rc19"
RC_COMMIT = "dc8ff55322267dfe54674fa6c4003a899bf235ab"
RC_CI = 34875483864
TREE = "432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502"
PROVENANCE = "77445b206e8712f4b24ddc0910ef18b41264154b26189748c60c1fdc4f632171"
LEDGER = "vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed"
LEDGER_SYSTEM_IDENTIFIER = "7685665008963764889"
LEDGER_DATABASE_OID = 16384
LEDGER_ROLE = "vang_nguyen"
LEDGER_SCHEMA = "public"
LEDGER_POSTGRES_MAJOR = 16
LEDGER_SOCKET = "/home/vang_nguyen/.local/share/npd-vf-rc19-ledger-d86a01b1a8c5/socket"
LEDGER_PORT = 55439
LINEAGE = "al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd"
OPERATION = (
    "v3-01-rc19-openai-transcription-asr-al-0001-"
    "d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd-call-01"
)
EXECUTION_SCOPE = "7d51c74c2b7c9efe3a12f99d1849997e682bdc028850e8af90db8f5497879a85"
PREPARED_SCOPE = "eeac77edc3e88309d1d3b3a883ae5b7c5618fb6a5907f7c13eb3595829fbde49"
OPERATION_MANIFEST = "d24e29259fd2cea90f539fc2e60b213f7b9522a515de18defda606607a0673ca"
PREPARATION_TEMPLATE = "30979114a9ee55fc4bec60433b565ae1473bbbc17ecaf2c2bddbb3b57195ce0f"
PROFILE = "9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1"
PROMPT = "6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48"
ASSET = "fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef"
REFERENCE = "585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e"
RIGHTS = "5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091"
RIGHTS_2 = "972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323"
PROVIDER_SCOPE = "4d88c5c59c9b5ca9e8c126f0798356eb6ef82a8db2fe16045434af1d69048349"
BUDGET_SCOPE = "10403dc5ce372e2421bae36ab28ae5ec864acafe85253b07c210c5c29053814b"
LEDGER_OPERATION_BINDING = "867ec5d9eb6b3b4756d74a051941ca3104a7c4a370832df263dea261828bcf63"
OWNER_MANIFEST = "0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0"
RECORDED_AT = "2026-09-15T10:49:19Z"
WINDOW_START_UTC = "2026-09-16T14:00:00Z"
WINDOW_END_UTC = "2026-09-16T18:00:00Z"
WINDOW_START_ICT = "2026-09-16T21:00:00+07:00"
WINDOW_END_ICT = "2026-09-17T01:00:00+07:00"
APPROVAL_IDS = {"G-01": "V3-01-APP-075", "G-02": "V3-01-APP-076", "G-03": "V3-01-APP-077"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def raw_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_numbers(value: object) -> object:
    if isinstance(value, dict):
        return {key: file_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [file_numbers(item) for item in value]
    if type(value) is float and value.is_integer():
        return int(value)
    return value


def pretty_bytes(value: object) -> bytes:
    return (
        json.dumps(file_numbers(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def git_optional(*args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=REPO, check=False, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def github_pull_request_base_attests_main() -> bool:
    """Accept an exact GitHub event anchor when checkout is intentionally shallow.

    actions/checkout does not guarantee origin/main or tag refs for pull_request
    jobs. The signed event payload still binds the repository, base ref and exact
    base SHA; any missing or malformed field fails closed.
    """

    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
        or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
        or os.environ.get("GITHUB_BASE_REF") != "main"
    ):
        return False
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return False
    try:
        payload = read_json(Path(event_path))
        pull_request = payload["pull_request"]
        return (
            pull_request["base"]["ref"] == "main"
            and pull_request["base"]["sha"] == MAIN
            and pull_request["base"]["repo"]["full_name"] == REPOSITORY
        )
    except (KeyError, OSError, TypeError, ValueError):
        return False


def no_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("VF_V0S_B9_OFFLINE_MATERIALIZATION_FORBIDS_NETWORK")


def validate_baseline() -> None:
    ci_main_attested = github_pull_request_base_attests_main()
    remote_main = git_optional(
        "rev-parse", "--verify", "refs/remotes/origin/main^{commit}"
    )
    if remote_main is None:
        if not ci_main_attested:
            raise ValueError("GOVERNANCE_MAIN_REF_UNAVAILABLE")
    elif remote_main != MAIN:
        raise ValueError("GOVERNANCE_MAIN_DRIFT")

    tag_commit = git_optional("rev-parse", "--verify", RC_TAG + "^{}")
    if tag_commit is None:
        if not ci_main_attested:
            raise ValueError("RC19_TAG_UNAVAILABLE")
    elif tag_commit != RC_COMMIT:
        raise ValueError("RC19_TAG_DRIFT")

    refs = ["HEAD"]
    for ref, unavailable_code in (
        (MAIN, "GOVERNANCE_MAIN_OBJECT_UNAVAILABLE"),
        (RC_COMMIT, "RC19_COMMIT_OBJECT_UNAVAILABLE"),
    ):
        if git_optional("rev-parse", "--verify", ref + "^{commit}") is not None:
            refs.append(ref)
        elif not ci_main_attested:
            raise ValueError(unavailable_code)
    for ref in refs:
        objects = _git_object_map(REPO, ref)
        if executable_tree_sha256(objects) != TREE:
            raise ValueError("EXECUTABLE_TREE_DRIFT:" + ref)
    spec = importlib.util.spec_from_file_location(
        "vf_v0s_b7_prepare", PREPARED / "prepare_materials.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("B7_REPRODUCER_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.validate_materials()["status"] != "PASS":
        raise ValueError("B7_PREPARATION_REPRODUCTION_FAILED")


def owner_decision() -> dict:
    package = read_json(PREPARED / "operation-preparation-package.json")
    immutable = package["immutable_input"]
    return {
        "acceptance_lineage_id": LINEAGE,
        "acceptance_lineage_sequence": 1,
        "anchors": {
            "dual_ci_provenance": "PASS",
            "dual_ci_provenance_sha256": PROVENANCE,
            "executable_rc_ci_run_id": RC_CI,
            "executable_tree_sha256": TREE,
            "governance_main_ci_run_id": MAIN_CI,
            "governance_main_commit": MAIN,
            "main_provenance": "PASS",
            "rc_commit": RC_COMMIT,
            "rc_tag": RC_TAG,
            "repository": REPOSITORY,
        },
        "approved_by": "Owner (GitHub: vangnguyen)",
        "authorized_materialization": [
            "G-01 existing ProviderApprovalRecord",
            "G-02 existing ProviderApprovalRecord",
            "G-03 existing ProviderApprovalRecord",
            "completed existing OpenAIAsrGateBundle",
            "Operation-1-only authority receipt",
        ],
        "authorized_window": {
            "budget_day_utc": "2026-09-16",
            "end_ict": WINDOW_END_ICT,
            "end_utc": WINDOW_END_UTC,
            "interval": "not_before <= now < not_after",
            "start_ict": WINDOW_START_ICT,
            "start_utc": WINDOW_START_UTC,
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "bundle_mount_in_this_task_authorized": False,
        "capability": "asr",
        "confirmation_token_contract": (
            "No confirmation-token field in the current ASR gate schema or retained "
            "ASR authority verifier; no plaintext token generated"
        ),
        "credential_access_in_this_task_authorized": False,
        "execution_in_this_task_authorized": False,
        "execution_scope_sha256": EXECUTION_SCOPE,
        "immutable_inputs": {
            **immutable,
            "prompt_sha256": PROMPT,
            "w1_profile_sha256": PROFILE,
        },
        "kill_switch_disengagement_in_this_task_authorized": False,
        "language": "vi",
        "ledger": {
            "custody": "VERIFIED / CANONICAL",
            "database_oid": LEDGER_DATABASE_OID,
            "identity": LEDGER,
            "operation_binding_sha256": LEDGER_OPERATION_BINDING,
            "operation_key": OPERATION,
            "state": "VIRGIN_NOT_REGISTERED / NOT_CONSUMED",
            "system_identifier": LEDGER_SYSTEM_IDENTIFIER,
        },
        "limits": {
            "acceptance_window_limit_vnd": "1250",
            "automatic_retry": False,
            "budget_day_utc": "2026-09-16",
            "controller_hard_timeout_seconds": 120,
            "currency": "VND",
            "files_per_operation": 1,
            "max_attempts": 1,
            "max_concurrent_calls": 1,
            "max_duration_seconds": 180,
            "max_file_bytes": 25000000,
            "model_fallback": False,
            "per_operation_limit_vnd": "500",
            "provider_http_timeout_seconds": 90,
            "requested_language": "vi",
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment", "word"],
            "vnd_per_minute": "162",
        },
        "loader_planning_slots": (
            "Two ordered operations and both RightsRecords remain in the verified loader "
            "schema; allowlist membership is not Operation 2 authority"
        ),
        "model": "whisper-1",
        "operation_2_authorized": False,
        "operation_key": OPERATION,
        "operation_manifest_sha256": OPERATION_MANIFEST,
        "prepared_review_scope_sha256": PREPARED_SCOPE,
        "preparation_template_sha256": PREPARATION_TEMPLATE,
        "production_writes_authorized": False,
        "provider_key": "openai-transcription",
        "record_type": "V3-01 current explicit Owner authority materialization source",
        "recorded_at_utc": RECORDED_AT,
        "reservation_in_this_task_authorized": False,
        "slot": 1,
        "source": "Explicit Owner decision in VF-V0S-B9; not inherited from RC-18",
        "task_id": TASK,
        "version": 1,
    }


def approval_records(decision_sha: str) -> dict[str, ProviderApprovalRecord]:
    scope = read_json(PREPARED / "scope-candidate.json")
    asset_two = scope["immutable_inputs"][1]
    common_hashes = {
        RC_COMMIT,
        MAIN,
        TREE,
        PROVENANCE,
        EXECUTION_SCOPE,
        PREPARED_SCOPE,
        OPERATION_MANIFEST,
        PREPARATION_TEMPLATE,
        decision_sha,
        LEDGER_OPERATION_BINDING,
        PROFILE,
        PROMPT,
        ASSET,
        REFERENCE,
        RIGHTS,
    }
    common_limits = [
        f"Only Operation 1: {OPERATION}",
        f"Exact {RC_TAG} commit {RC_COMMIT}; lineage {LINEAGE}; canonical ledger {LEDGER}",
        f"Window {WINDOW_START_UTC} <= dispatch time < {WINDOW_END_UTC}; Asia/Ho_Chi_Minh; UTC budget day 2026-09-16",
        "One attempt, concurrency 1, retry 0, fallback 0; provider HTTP 90 seconds < controller hard envelope 120 seconds",
        "Operation 2 NOT_APPROVED / LOCKED / NOT_TRANSFERRED; no second call or automatic unlock",
        "VF-V0S-B9 creates authority artifacts only: no mount, credential read, reservation, kill-switch disengagement or provider dispatch",
        "A separate future execution task and fresh full preflight are mandatory; authority alone bypasses no gate",
        "No deployment, public ingress, publishing, training, resale or production analytics",
    ]
    notes = (
        "Materialized from the explicit current Owner decision VF-V0S-B9, not "
        "backdated or inherited from RC-18. The structured Owner decision binds "
        "RC-19/main/tree/provenance/ledger/input constraints. The preparation template "
        "is included; the completed raw bundle is bound by the outer Op1 authority "
        "receipt to avoid a self-referential hash cycle. Loader validity is not activation."
    )
    gate_specific = {
        "G-01": {
            "hashes": {PROVIDER_SCOPE},
            "limits": [
                "openai-transcription / whisper-1 / asr / vi only; external credential alias reference only",
                "W1 profile asr-whisper-vi-w1-v1 and exact profile/prompt hashes required",
                "No transcript correction, fuzzy rescue or reference rewrite; WER <=15 percent and critical terms 8/8 unchanged",
            ],
            "scope": "exact execution/binding",
        },
        "G-02": {
            "hashes": {BUDGET_SCOPE},
            "limits": [
                "Maximum 500 VND atomic reservation for this one operation; 1250 VND total window ceiling, not permission for another call",
                "Fixed accounting basis 162 VND/minute; duration 120.852 seconds; modeled 326.3004 VND is not actual cost",
                "No reservation in VF-V0S-B9; future reservation must reconcile to numeric zero",
            ],
            "scope": "VND budget/spend ceiling",
        },
        "G-03": {
            "hashes": {
                RIGHTS_2,
                OWNER_MANIFEST,
                asset_two["asset_sha256"],
                asset_two["reference_transcript_sha256"],
            },
            "limits": [
                "Only asset-g03-asr-vi-owned-01 and V3-01-RIGHTS-ASR-001 may be dispatched under this approval",
                "Voice-processing consent is limited to OpenAI ASR acceptance; publishing/training/resale remain prohibited",
                "RightsRecord ASR-002 is retained only for the two-input planning schema; Operation 2 is not approved",
                "Provider timestamps and boundary-point semantics remain unchanged; interval consumers still require PositiveDurationTranscript",
            ],
            "scope": "asset/rights and dated interval",
        },
    }
    records = {}
    for gate_id, specific in gate_specific.items():
        records[gate_id] = ProviderApprovalRecord.model_validate(
            {
                "approval_id": APPROVAL_IDS[gate_id],
                "approved_at_utc": RECORDED_AT,
                "approved_by": "Owner (GitHub: vangnguyen)",
                "artifact_or_commit_hashes": sorted(common_hashes | specific["hashes"]),
                "decision": "APPROVED",
                "expires_at_utc": WINDOW_END_UTC,
                "gate_id": gate_id,
                "limits": common_limits + specific["limits"],
                "notes": notes,
                "scope": (
                    f"Exact RC-19 ASR W1 Operation-1-only {specific['scope']} approval "
                    f"for {OPERATION}. Owner source: VF-V0S-B9."
                ),
                "target_account_or_environment": (
                    "Isolated future Owner-gated RC-19 acceptance runtime using canonical "
                    f"ledger {LEDGER}; no production execution"
                ),
            }
        )
    return records


def final_bundle(records: dict[str, ProviderApprovalRecord]) -> tuple[bytes, dict]:
    prepared = read_json(PREPARED / "gate-template.json")
    bundle = {key: copy.deepcopy(prepared[key]) for key in OpenAIAsrGateBundle.model_fields if key in prepared}
    bundle["bundle_id"] = "V3-01-GATE-RC19-OPENAI-ASR-W1-LINEAGE-A"
    fields = {"G-01": "credential_approval", "G-02": "budget_approval", "G-03": "rights_approval"}
    for gate_id, field in fields.items():
        record = records[gate_id]
        bundle[field] = {
            "record": record.model_dump(mode="json"),
            "record_sha256": canonical_sha256(record),
        }
    model = OpenAIAsrGateBundle.model_validate(bundle)
    rendered = pretty_bytes(model.model_dump(mode="json"))
    return rendered, json.loads(rendered)


def load_scope(bundle_bytes: bytes) -> tuple[dict, str, str]:
    final_sha = hashlib.sha256(bundle_bytes).hexdigest()
    with tempfile.TemporaryDirectory(prefix="vf-v0s-b9-") as temporary:
        path = Path(temporary) / "gate.json"
        path.write_bytes(bundle_bytes)
        scope = load_verified_provider_gate_bundle(
            path,
            expected_bundle_sha256=final_sha,
            expected_rc_commit=RC_COMMIT,
            expected_rc_tag=RC_TAG,
            expected_acceptance_lineage_id=LINEAGE,
        )
    scope_sha = canonical_sha256(scope)
    if asr_execution_scope_sha256(scope) != EXECUTION_SCOPE:
        raise ValueError("FINAL_LOADED_EXECUTION_SCOPE_DRIFT")
    projection = {
        "bundle_mounted": False,
        "gate_loader": "PASS / VALID_IN_MEMORY_NOT_MOUNTED",
        "scope": scope.model_dump(mode="json"),
        "scope_canonical_sha256": scope_sha,
    }
    return projection, final_sha, scope_sha


def authority(
    decision_sha: str,
    approval_hashes: dict[str, str],
    final_bundle_sha: str,
    final_scope_sha: str,
) -> dict:
    return {
        "acceptance_lineage_id": LINEAGE,
        "acceptance_lineage_sequence": 1,
        "actual_cost_vnd": "0",
        "approval_records": {
            gate: {
                "approval_id": APPROVAL_IDS[gate],
                "record_path": f"docs/acceptance/v3-01/approvals/{APPROVAL_IDS[gate]}.json",
                "record_sha256": approval_hashes[gate],
            }
            for gate in ("G-01", "G-02", "G-03")
        },
        "approved_by": "Owner (GitHub: vangnguyen)",
        "asr_prompt_profile_id": "asr-whisper-vi-w1-v1",
        "asr_prompt_profile_sha256": PROFILE,
        "asset_bytes": 5800940,
        "asset_duration_seconds": 120.852,
        "asset_id": "asset-g03-asr-vi-owned-01",
        "asset_sha256": ASSET,
        "authorized_window": {
            "budget_day_utc": "2026-09-16",
            "end_ict": WINDOW_END_ICT,
            "end_utc": WINDOW_END_UTC,
            "interval": "not_before <= now < not_after",
            "start_ict": WINDOW_START_ICT,
            "start_utc": WINDOW_START_UTC,
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "budget_reserved_vnd": "0",
        "bundle_mounted": False,
        "capability": "asr",
        "confirmation_token_binding": {
            "binding_sha256": None,
            "created": False,
            "required_by_current_gate_schema": False,
            "required_by_retained_asr_authority_verifier": False,
            "status": "NOT_REQUIRED_BY_VERIFIED_ASR_CONTRACT",
        },
        "consumed_or_dispatched_by_this_task": False,
        "credential_alias": "secret://openai/codex-video",
        "credential_reads": 0,
        "decision": "APPROVED",
        "deployment_authorized": False,
        "dispatch_requires_separate_execution_task": True,
        "dual_ci_provenance_sha256": PROVENANCE,
        "executable_rc_ci_run_id": RC_CI,
        "executable_tree_sha256": TREE,
        "execution_scope_sha256": EXECUTION_SCOPE,
        "expires_at_utc": WINDOW_END_UTC,
        "gate_bundle_path": BUNDLE_PATH.relative_to(REPO).as_posix(),
        "gate_bundle_sha256": final_bundle_sha,
        "governance_main_ci_run_id": MAIN_CI,
        "governance_main_commit": MAIN,
        "kill_switch": "ENGAGED",
        "kill_switch_transition_executed": False,
        "language": "vi",
        "ledger": {
            "custody": "VERIFIED / CANONICAL",
            "database_oid": LEDGER_DATABASE_OID,
            "identity": LEDGER,
            "operation_binding_sha256": LEDGER_OPERATION_BINDING,
            "operation_record_exists_at_materialization": False,
            "provider_request_receipt_at_materialization": "NONE",
            "system_identifier": LEDGER_SYSTEM_IDENTIFIER,
        },
        "limits": {
            "acceptance_window_limit_vnd": "1250",
            "automatic_retry": False,
            "controller_hard_timeout_seconds": 120,
            "currency": "VND",
            "files_per_operation": 1,
            "max_attempts": 1,
            "max_concurrent_calls": 1,
            "max_duration_seconds": 180,
            "max_file_bytes": 25000000,
            "minimum_duration_seconds": 90,
            "model_fallback": False,
            "per_operation_limit_vnd": "500",
            "provider_http_timeout_seconds": 90,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment", "word"],
            "vnd_per_minute": "162",
        },
        "loaded_runtime_scope_sha256": final_scope_sha,
        "main_provenance": "PASS",
        "model": "whisper-1",
        "modeled_cost_vnd": "326.3004",
        "operation_1_consumed": False,
        "operation_2_authorized": False,
        "operation_key": OPERATION,
        "operation_manifest_sha256": OPERATION_MANIFEST,
        "owner_decision_sha256": decision_sha,
        "prepared_scope_sha256": PREPARED_SCOPE,
        "preparation_template_sha256": PREPARATION_TEMPLATE,
        "pre_execution_requirements": [
            "Revalidate exact current main/RC/tree/dual-CI provenance and unchanged workflow",
            "Verify authority receipt, final raw bundle, loaded scope, lineage, operation and immutable input hashes",
            "Run bootstrap against canonical RC-19 ledger; confirm operation unconsumed and no request/reservation/duplicate",
            "Verify not_before <= current time < not_after and UTC budget day immediately before dispatch",
            "Mount only the exact final bundle after all pre-secret checks pass; loader must pass",
            "Verify credential alias availability without exposing its value only in the separate execution task",
            "Atomically reserve at most 500 VND within the 1250 VND window",
            "Arm durable evidence before a single dispatch; retry/fallback remain zero",
        ],
        "production_analytics_authorized": False,
        "production_verdict": "NO-GO",
        "production_writes": 0,
        "prompt_sha256": PROMPT,
        "provider_calls": 0,
        "provider_key": "openai-transcription",
        "public_ingress_authorized": False,
        "publishing_authorized": False,
        "rc_commit": RC_COMMIT,
        "rc_tag": RC_TAG,
        "record_type": "V3-01 real-provider operation authority",
        "recorded_at_utc": RECORDED_AT,
        "reference_transcript_sha256": REFERENCE,
        "resale_authorized": False,
        "rights_record_id": "V3-01-RIGHTS-ASR-001",
        "rights_record_sha256": RIGHTS,
        "signature_status": (
            "No cryptographic signing contract in the verified ASR gate/authority verifier; "
            "this record attests the explicit current Owner task"
        ),
        "slot": 1,
        "source": (
            "Explicit Owner decision VF-V0S-B9; authority artifacts only; a separate "
            "bounded preflight/dispatch task is required"
        ),
        "status": "GRANTED_NOT_CONSUMED",
        "task_id": TASK,
        "terminal_contract": {
            "after_dispatch": "CONSUMED regardless of provider result; one attempt only; no retry/fallback",
            "before_dispatch_binding_mismatch": "BLOCKED_PRE_CALL / NOT_CONSUMED",
            "cleanup": "Reconcile reservation; re-engage kill switch; unmount; seal evidence; STOP for Owner review",
            "missing_post_call_evidence": "REVIEW_REQUIRED / CONSUMED; no reconstruction or retry",
            "operation_2": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
        },
        "training_authorized": False,
        "valid_from_utc": WINDOW_START_UTC,
        "version": 1,
    }


def require_exact_authority(payload: object) -> dict:
    """Offline exact-byte authority pin; it does not activate the authority."""
    path = HERE / "operation-1-authority.json"
    manifest_path = HERE / "manifest.json"
    if not path.is_file() or not manifest_path.is_file():
        raise ValueError("OP1_AUTHORITY_ARTIFACT_MISSING")
    manifest = read_json(manifest_path)
    if raw_sha(path) != manifest["authority_receipt_raw_sha256"]:
        raise ValueError("AUTHORITY_RECEIPT_SHA_MISMATCH")
    if not isinstance(payload, dict) or pretty_bytes(payload) != path.read_bytes():
        raise ValueError("OP1_AUTHORITY_BINDING_MISMATCH")
    return payload


def require_operation_one(operation_key: str, payload: object | None = None) -> bool:
    item = require_exact_authority(
        read_json(HERE / "operation-1-authority.json") if payload is None else payload
    )
    if operation_key != item["operation_key"] or item["operation_2_authorized"] is not False:
        raise ValueError("OPERATION_2_OR_OTHER_OPERATION_NOT_AUTHORIZED")
    return True


def authority_window_active(now: datetime) -> bool:
    item = require_exact_authority(read_json(HERE / "operation-1-authority.json"))
    if now.tzinfo is None:
        raise ValueError("WINDOW_TIMEZONE_REQUIRED")
    start = datetime.fromisoformat(item["valid_from_utc"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(item["expires_at_utc"].replace("Z", "+00:00"))
    utc = now.astimezone(timezone.utc)
    return start <= utc < end and utc.date() == start.date()


def bootstrap_binding(authority_sha: str, bundle_sha: str, scope_sha: str) -> dict:
    payload = {
        "acceptance_lineage_id": LINEAGE,
        "asset_sha256": ASSET,
        "authority_receipt_sha256": authority_sha,
        "budget_reserved_vnd": "0",
        "bundle_sha256": bundle_sha,
        "capability": "asr",
        "database_name": LEDGER,
        "database_oid": LEDGER_DATABASE_OID,
        "database_role": LEDGER_ROLE,
        "environment": "v3_01_acceptance_runtime",
        "executable_tree_sha256": TREE,
        "execution_scope_sha256": EXECUTION_SCOPE,
        "external_execution_enabled": False,
        "governance_main_commit": MAIN,
        "kill_switch_engaged": True,
        "language": "vi",
        "mode": "ZERO_CALL_CUSTODY_ONLY",
        "model": "whisper-1",
        "operation_key": OPERATION,
        "paid_execution_enabled": False,
        "port": LEDGER_PORT,
        "postgres_major": LEDGER_POSTGRES_MAJOR,
        "prompt_sha256": PROMPT,
        "provider_key": "openai-transcription",
        "rc_commit": RC_COMMIT,
        "rc_tag": RC_TAG,
        "reference_transcript_sha256": REFERENCE,
        "rights_record_sha256": RIGHTS,
        "schema_name": LEDGER_SCHEMA,
        "scope_sha256": scope_sha,
        "sequence": 1,
        "slot": 1,
        "socket_directory": LEDGER_SOCKET,
        "system_identifier": LEDGER_SYSTEM_IDENTIFIER,
        "version": 1,
        "w1_profile_sha256": PROFILE,
    }
    # The custody endpoint is a POSIX socket consumed by the RC source under
    # WSL. Pydantic's Path.is_absolute() is host-dependent, so on Windows we
    # validate the strict generated schema plus the model's identity rules and
    # the POSIX path explicitly. B10 must run the full model/CLI under WSL.
    Draft202012Validator(BootstrapLedgerBinding.model_json_schema()).validate(payload)
    if not PurePosixPath(payload["socket_directory"]).is_absolute():
        raise ValueError("BOOTSTRAP_SOCKET_NOT_POSIX_ABSOLUTE")
    lineage = derive_acceptance_lineage_id(
        rc_tag=payload["rc_tag"],
        rc_commit=payload["rc_commit"],
        provider_key=payload["provider_key"],
        model=payload["model"],
        capability=payload["capability"],
        sequence=payload["sequence"],
    )
    operation = derive_rc_bound_operation_key(
        rc_tag=payload["rc_tag"],
        provider_key=payload["provider_key"],
        capability=payload["capability"],
        slot=payload["slot"],
        acceptance_lineage_id=lineage,
    )
    if payload["acceptance_lineage_id"] != lineage or payload["operation_key"] != operation:
        raise ValueError("BOOTSTRAP_OPERATION_IDENTITY_MISMATCH")
    if payload["database_name"] != ledger_database_name(payload["rc_tag"], lineage):
        raise ValueError("BOOTSTRAP_DATABASE_NAMESPACE_MISMATCH")
    return payload


def build_materials() -> dict[Path, bytes]:
    validate_baseline()
    decision = owner_decision()
    decision_sha = canonical_sha256(decision)
    records = approval_records(decision_sha)
    approval_hashes = {gate: canonical_sha256(record) for gate, record in records.items()}
    validator = Draft202012Validator(
        read_json(REPO / "docs/acceptance/v3-01/schemas/approval-record.schema.json")
    )
    for record in records.values():
        validator.validate(record.model_dump(mode="json"))
    bundle_bytes, _ = final_bundle(records)
    projection, bundle_sha, scope_sha = load_scope(bundle_bytes)
    auth = authority(decision_sha, approval_hashes, bundle_sha, scope_sha)
    auth_bytes = pretty_bytes(auth)
    auth_sha = hashlib.sha256(auth_bytes).hexdigest()
    binding = bootstrap_binding(auth_sha, bundle_sha, scope_sha)
    manifest = {
        "approval_records": {
            gate: {
                "approval_id": APPROVAL_IDS[gate],
                "canonical_record_sha256": approval_hashes[gate],
                "record_path": f"docs/acceptance/v3-01/approvals/{APPROVAL_IDS[gate]}.json",
            }
            for gate in ("G-01", "G-02", "G-03")
        },
        "authority_path": (HERE / "operation-1-authority.json").relative_to(REPO).as_posix(),
        "authority_receipt_raw_sha256": auth_sha,
        "bundle_mounted": False,
        "credential_reads": 0,
        "evidence_pointer": "evidence/v3-01/vf-v0s-b9-20260915-final-authority/README.md",
        "execution_scope_sha256": EXECUTION_SCOPE,
        "final_bundle_path": BUNDLE_PATH.relative_to(REPO).as_posix(),
        "final_runtime_bundle_sha256": bundle_sha,
        "final_scope_sha256": scope_sha,
        "hash_dependency_order": [
            "immutable B7 template/inputs and current Owner decision",
            "G-01/G-02/G-03 bind template and execution scope, not final bundle hash",
            "completed bundle embeds canonical hashed approvals",
            "real loader validation yields loaded scope hash",
            "outer Op1 authority binds final raw bundle/scope/approval/ledger hashes",
            "bootstrap binding and governance checksums seal the result",
        ],
        "kill_switch": "ENGAGED",
        "ledger_identity": LEDGER,
        "ledger_mutations_by_materialization": 0,
        "operation_1_consumed": False,
        "operation_2": "NOT_APPROVED / LOCKED / NOT_TRANSFERRED",
        "owner_decision_canonical_sha256": decision_sha,
        "prepared_scope_sha256": PREPARED_SCOPE,
        "preparation_template_sha256": PREPARATION_TEMPLATE,
        "production_business_writes": 0,
        "provider_calls": 0,
        "record_role": "GOVERNANCE_INTEGRITY_MANIFEST_NOT_RUNTIME_SCHEMA",
        "serialization": {
            "canonical_models": "model_dump(mode=json), sorted compact UTF-8 JSON, no trailing LF",
            "raw_artifacts": "UTF-8 without BOM; sorted keys; indent2; ensure_ascii=False; integral numbers normalized; one LF",
        },
        "status": "GRANTED_NOT_CONSUMED",
        "task_id": TASK,
    }
    readme = f"""# RC-19 ASR W1 Operation 1 final authority

Status: **GRANTED_NOT_CONSUMED**. Owner authority source: `{TASK}`.

- RC: `{RC_TAG}` -> `{RC_COMMIT}`
- Governance main: `{MAIN}`
- Operation 1: `{OPERATION}`
- Canonical ledger: `{LEDGER}`
- Final runtime bundle SHA-256: `{bundle_sha}`
- Loaded runtime scope SHA-256: `{scope_sha}`
- Execution-scope SHA-256: `{EXECUTION_SCOPE}`
- Authority receipt SHA-256: `{auth_sha}`
- G-01/G-02/G-03: `{approval_hashes['G-01']}`, `{approval_hashes['G-02']}`, `{approval_hashes['G-03']}`

The final bundle was reproduced deterministically and accepted by the real gate
loader in memory. It is not mounted. The authority is limited to Operation 1 and
the exact 2026-09-16 14:00-18:00 UTC window (21:00-01:00 ICT), with 500 VND
per-operation and 1,250 VND window ceilings. Attempts/concurrency are 1/1;
retry/fallback are 0/0; provider/controller timeouts are 90/120 seconds.

`bootstrap-binding.json` is loader-valid zero-call custody input for the next
bounded qualification task. It is not an execution command and was not invoked
here. No operation row, provider receipt, reservation, bundle mount, credential
read, kill-switch transition, provider call, or production business write was
created. Operation 2 remains `NOT_APPROVED / LOCKED / NOT_TRANSFERRED`.

NEXT_SAFE_ACTION: **VF-V0S-B10 — zero-call operation-bound bootstrap
qualification with the exact final authority/bundle. Stop before execution.**
"""
    outputs: dict[Path, bytes] = {
        APPROVALS_DIR / f"{APPROVAL_IDS[gate]}.json": pretty_bytes(record.model_dump(mode="json"))
        for gate, record in records.items()
    }
    outputs.update(
        {
            BUNDLE_PATH: bundle_bytes,
            HERE / "README.md": readme.encode("utf-8"),
            HERE / "bootstrap-binding.json": pretty_bytes(binding),
            HERE / "loaded-scope-validation-only.json": pretty_bytes(projection),
            HERE / "manifest.json": pretty_bytes(manifest),
            HERE / "operation-1-authority.json": auth_bytes,
            HERE / "owner-decision.json": pretty_bytes(decision),
        }
    )
    return outputs


def checksum_bytes(outputs: dict[Path, bytes]) -> bytes:
    members = {path: raw for path, raw in outputs.items() if path.parent == HERE}
    for name in ("materialize_and_validate.py", "validate_governance.py"):
        path = HERE / name
        if path.is_file():
            members[path] = path.read_bytes()
    lines = [
        f"{hashlib.sha256(raw).hexdigest()}  {path.name}"
        for path, raw in sorted(members.items(), key=lambda item: item[0].name)
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def validate_materials(outputs: dict[Path, bytes] | None = None) -> dict:
    expected = build_materials() if outputs is None else outputs
    mismatches = [
        path.relative_to(REPO).as_posix()
        for path, raw in expected.items()
        if not path.is_file() or path.read_bytes() != raw
    ]
    expected_checksum = checksum_bytes(expected)
    checksum_path = HERE / "SHA256SUMS.txt"
    if not checksum_path.is_file() or checksum_path.read_bytes() != expected_checksum:
        mismatches.append(checksum_path.relative_to(REPO).as_posix())
    bundle = read_json(BUNDLE_PATH) if BUNDLE_PATH.is_file() else None
    if bundle is not None:
        restored = copy.deepcopy(bundle)
        for field in ("credential_approval", "budget_approval", "rights_approval"):
            restored.pop(field)
        prepared = read_json(PREPARED / "gate-template.json")
        expected_base = {key: prepared[key] for key in OpenAIAsrGateBundle.model_fields if key in prepared}
        expected_base["bundle_id"] = "V3-01-GATE-RC19-OPENAI-ASR-W1-LINEAGE-A"
        for timestamp_field in ("valid_from_utc", "expires_at_utc"):
            expected_base[timestamp_field] = datetime.fromisoformat(
                expected_base[timestamp_field].replace("Z", "+00:00")
            ).isoformat().replace("+00:00", "Z")
        if restored != expected_base:
            mismatches.append("FINAL_BUNDLE_NON_APPROVAL_FIELDS_DRIFT")
    return {
        "actual_cost_vnd": "0",
        "authority_status": "GRANTED_NOT_CONSUMED",
        "budget_reserved_vnd": "0",
        "bundle_mounted": False,
        "checked_files": len(expected) + 1,
        "credential_reads": 0,
        "gate_loader": "PASS / VALID_IN_MEMORY_NOT_MOUNTED" if not mismatches else "FAIL",
        "kill_switch": "ENGAGED",
        "mismatches": mismatches,
        "operation_1_consumed": False,
        "production_business_writes": 0,
        "provider_calls": 0,
        "status": "PASS" if not mismatches else "FAIL",
        "task_id": TASK,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    socket.create_connection = no_network
    socket.socket.connect = no_network
    outputs = build_materials()
    if args.write:
        for path, raw in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (HERE / "SHA256SUMS.txt").write_bytes(checksum_bytes(outputs))
    result = validate_materials(outputs)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
