"""Host adapter for the canonical single-dispatch runner; no transport here.

The root-owned catalog is deployment policy, not Owner authority. Both its
independent qualification binding and canonical O2 validation must pass. No
catalog enabling dispatch is installed during VF-EXECUTOR-02.
"""
from __future__ import annotations

from dataclasses import replace
from contextlib import ExitStack, nullcontext
import hashlib
import json
from pathlib import Path
import re
import tempfile
import uuid

from . import executor_qualification as q
from . import provider_single_dispatch as canonical
from .provider_custody import CANONICAL_CUSTODY_BINDING_SHA256, load_custody_binding
from .provider_runtime_bootstrap import load_operation_binding
from .provider_safety import ProviderSafetyPolicy

CATALOG = Path("/etc/npd-video-factory/execution-catalog.json")
STATES = (
    "INIT", "ENVIRONMENT_PREFLIGHT", "BINDING_PREFLIGHT", "LEDGER_PREFLIGHT",
    "BUNDLE_VALIDATED", "EVIDENCE_ARMED", "SECRET_AVAILABLE", "BUDGET_RESERVED",
    "FINAL_TIME_CHECK", "READY_TO_DISPATCH", "SINGLE_DISPATCH", "TERMINAL_EVIDENCE",
)


def _trusted_json(path: Path, expected_sha256: str | None = None) -> dict:
    q.private_path(path, root_owned=True)
    raw = path.read_bytes()
    q.secret_scan(raw)
    if expected_sha256 is not None:
        q.require(hashlib.sha256(raw).hexdigest() == expected_sha256, "HOST_ARTIFACT_HASH_MISMATCH")
    value = json.loads(raw)
    q.require(isinstance(value, dict), "HOST_ARTIFACT_INVALID")
    return value


def load_catalog() -> dict:
    if not CATALOG.exists():
        raise q.Blocked("EXECUTOR_NOT_QUALIFIED_DISPATCH_DISABLED")
    value = _trusted_json(CATALOG)
    q.require(value.get("version") == 1 and value.get("dispatch_enabled") is True,
              "EXECUTOR_NOT_QUALIFIED_DISPATCH_DISABLED")
    return value


def verify_qualification(catalog: dict, host: q.Host) -> None:
    """Qualification is an independently pinned deployment prerequisite.

    This is a separate root-owned promotion artifact, not a renamed capability
    probe receipt. It binds the raw probe receipt/manifest and independent
    hostile-job security evidence. None of these artifacts authorizes O2.
    """
    receipt = _trusted_json(Path(catalog["qualification_receipt"]), catalog["qualification_sha256"])
    q.require(receipt.get("status") == "SELF_HOSTED_EXECUTION_PLANE_QUALIFIED",
              "EXECUTOR_NOT_QUALIFIED_DISPATCH_DISABLED")
    q.require_runner_identity(receipt, host, "QUALIFICATION_IDENTITY_MISMATCH")
    q.require(receipt.get("gates") == {gate: "PASS" for gate in q.GATES}, "QUALIFICATION_GATES_FAILED")
    q.require(all(receipt.get(name) == value for name, value in q.ZERO.items()),
              "QUALIFICATION_ZERO_INVARIANTS_FAILED")
    q.require(receipt.get("kill_switch") == "ENGAGED", "QUALIFICATION_KILL_SWITCH_INVALID")
    q.require(receipt.get("custody_binding_sha256") == host.binding_sha256,
              "QUALIFICATION_CUSTODY_BINDING_MISMATCH")
    secret_binding = q.secret_presence(host)
    q.require(receipt.get("secret_binding_sha256")
              == secret_binding.get("binding_sha256")
              and secret_binding.get("result")
              == "PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED"
              and secret_binding.get("PROVIDER_CREDENTIAL_READS") == 0,
              "QUALIFICATION_SECRET_BINDING_MISMATCH")
    q.require(receipt.get("execution_workflow_commit") == host.execution_workflow_commit,
              "QUALIFICATION_WORKFLOW_PROVENANCE_MISMATCH")
    probes = _trusted_json(Path(receipt["probe_receipt"]), receipt["probe_receipt_sha256"])
    manifest = _trusted_json(Path(receipt["probe_manifest"]), receipt["probe_manifest_sha256"])
    q.require(manifest.get("qualification.json") == receipt["probe_receipt_sha256"],
              "QUALIFICATION_MANIFEST_MISMATCH")
    q.require(probes.get("verdict") == "CAPABILITY_PROBES_PASS"
              and probes.get("execution_plane_qualified") is False,
              "QUALIFICATION_PROBE_IDENTITY_MISMATCH")
    q.require_runner_identity(probes, host, "QUALIFICATION_PROBE_IDENTITY_MISMATCH")
    q.require(all(probes.get("gates", {}).get(gate, {}).get("status") == "PASS" for gate in q.GATES)
              and all(probes.get(name) == value for name, value in q.ZERO.items())
              and probes["gates"]["E10"].get("KILL_SWITCH") == "ENGAGED"
              and probes["gates"]["E10"].get("ledger_unchanged") is True,
              "QUALIFICATION_PROBES_FAILED")
    security = _trusted_json(Path(receipt["security_review"]), receipt["security_review_sha256"])
    q.require(security.get("status") == "RUNNER_SECURITY_PASS"
              and security.get("quarantine") == "CLEARED_BY_VALIDATED_POLICY",
              "QUALIFICATION_SECURITY_REVIEW_FAILED")
    q.require_runner_identity(security, host, "QUALIFICATION_SECURITY_IDENTITY_MISMATCH")
    from .executor_security import HOSTILE_JOB_TESTS
    threats = HOSTILE_JOB_TESTS
    q.require(all(security.get("hostile_job_tests", {}).get(threat) == "PASS" for threat in threats),
              "QUALIFICATION_SECURITY_TESTS_FAILED")
    q.require(all(security.get(name) == value for name, value in q.ZERO.items())
              and security.get("kill_switch") == "ENGAGED"
              and security.get("provider_execution_allowlist") == "EMPTY",
              "QUALIFICATION_SECURITY_ZERO_INVARIANTS_FAILED")
    evidence = _trusted_json(Path(receipt["evidence_manifest"]),
                             receipt["evidence_manifest_sha256"])
    q.require_runner_identity(evidence, host, "QUALIFICATION_EVIDENCE_IDENTITY_MISMATCH")
    q.require(evidence.get("custody_binding_sha256") == host.binding_sha256
              and evidence.get("secret_binding_sha256")
              == secret_binding.get("binding_sha256")
              and evidence.get("execution_workflow_commit") == host.execution_workflow_commit
              and evidence.get("kill_switch") == "ENGAGED"
              and all(evidence.get(name) == value for name, value in q.ZERO.items())
              and evidence.get("artifacts") == {
                  "probe_receipt": receipt["probe_receipt_sha256"],
                  "probe_manifest": receipt["probe_manifest_sha256"],
                  "security_review": receipt["security_review_sha256"],
              }, "QUALIFICATION_EVIDENCE_MANIFEST_INVALID")


def bind_request(
    request: dict,
    entry: dict,
    host: q.Host,
    *,
    qualification_sha256: str,
) -> tuple[canonical.SingleDispatchPaths, ProviderSafetyPolicy]:
    caller_identity_fields = {*q.RUNNER_IDENTITY_FIELDS, "runner_identity"}
    q.require(not caller_identity_fields.intersection(request), "CALLER_RUNNER_IDENTITY_FORBIDDEN")
    q.require(entry.get("request") == request, "REQUEST_NOT_EXACTLY_APPROVED")
    data = dict(entry["paths"])
    q.require(not {"custody_binding", "custody_binding_sha256"}.intersection(data),
              "OPERATION_CUSTODY_OVERRIDE_FORBIDDEN")
    data.update(
        custody_binding=host.binding,
        custody_binding_sha256=host.binding_sha256,
    )
    paths = canonical.SingleDispatchPaths(**{
        name: value if name.endswith("sha256") else Path(value)
        for name, value in data.items()
    })
    q.require(paths.rc_source == Path(host.source) and request["rc_commit"] == host.source_commit,
              "EXECUTABLE_SOURCE_MISMATCH")
    q.require(paths.evidence_directory == Path(host.evidence_root) / "operations",
              "EVIDENCE_ROOT_MISMATCH")
    for name in ("operation_binding", "custody_binding", "bundle", "authority",
                 "provenance", "operation_manifest", "asset", "reference_transcript",
                 "rights_record"):
        q.private_path(getattr(paths, name), root_owned=True)
    operation = load_operation_binding(
        paths.operation_binding,
        paths.operation_binding_sha256,
    )
    custody = load_custody_binding(
        paths.custody_binding,
        paths.custody_binding_sha256,
    )
    q.require(paths.custody_binding_sha256 == host.binding_sha256,
              "CUSTODY_BINDING_MISMATCH")
    q.require(host.binding_sha256 == CANONICAL_CUSTODY_BINDING_SHA256,
              "CUSTODY_BINDING_NOT_CANONICAL")
    q.require(operation.executor_executable_tree_sha256
              == host.executor_executable_tree_sha256,
              "EXECUTOR_TREE_MISMATCH")
    q.require(operation.execution_plane_promotion_sha256 == qualification_sha256,
              "EXECUTION_PLANE_PROMOTION_MISMATCH")
    q.require(custody.database_name == "vf_provider_custody_v3_01",
              "CUSTODY_DATABASE_MISMATCH")
    expected = {
        "operation_id": operation.operation_key, "bundle_sha256": operation.bundle_sha256,
        "loaded_scope_sha256": operation.loaded_scope_sha256,
        "authority_receipt_sha256": operation.authority_receipt_sha256,
        "rc_tag": operation.rc_tag, "rc_commit": operation.rc_commit,
        "governance_main_sha": operation.governance_main_commit,
        "provider_capability": operation.capability,
    }
    q.require(all(request[key] == value for key, value in expected.items()), "REQUEST_BINDING_MISMATCH")
    policy = ProviderSafetyPolicy.model_validate(
        _trusted_json(Path(entry["runtime_policy"]), entry["runtime_policy_sha256"]))
    return paths, policy


def read_kill_switch(host: q.Host) -> None:
    path = Path(host.kill_switch)
    q.private_path(path, root_owned=True)
    q.require(path.read_bytes() == b"ENGAGED\n", "KILL_SWITCH_NOT_ENGAGED")


async def execute(request: dict) -> dict:
    """One host invocation, no retries. All output consists of fixed safe codes.

    Only run_single_dispatch may reserve, consume or call a provider. The
    wrapper stages a private bundle and always removes it. Global kill-switch
    state stays ENGAGED; the canonical runner owns its one-shot scoped switch.
    """
    states = ["INIT"]
    output = {"state": "BLOCKED_PRE_CALL", "code": "EXECUTOR_PREFLIGHT_FAILED", **q.ZERO}
    host = None
    outcome = None
    invoked = False
    credential_reads = 0
    mounted_folder = None
    lifetime = ExitStack()
    locked = False

    def transition(state: str) -> None:
        q.require(state == STATES[len(states)], "EXECUTION_STATE_ORDER_INVALID")
        states.append(state)

    try:
        catalog = load_catalog()
        host = q.Host.load()
        # Keep the lock through the finally block, including terminal evidence.
        lifetime.enter_context(q.plane_lock(Path(host.lock_path)))
        locked = True
        with nullcontext():
            transition("ENVIRONMENT_PREFLIGHT")
            q.runtime(host, workflow_kind="execution")
            q.require(Path(__file__).resolve() == Path(host.source) / "apps/api/app/executor_execution.py",
                      "EXECUTION_ADAPTER_SOURCE_MISMATCH")
            verify_qualification(catalog, host)
            read_kill_switch(host)
            entry = catalog["operations"].get(request["bundle_id"])
            q.require(isinstance(entry, dict), "OPERATION_NOT_ALLOWLISTED")
            paths, policy = bind_request(
                request,
                entry,
                host,
                qualification_sha256=catalog["qualification_sha256"],
            )
            checked = await canonical.validate_single_dispatch(paths, runtime_policy=policy)
            q.require(checked.ready_for_execution_preflight and not checked.ready_for_provider_dispatch
                      and not checked.credential_read_performed and not checked.provider_call_performed,
                      "CANONICAL_CHECK_ONLY_BLOCKED")
            root = Path(host.evidence_root)
            q.private_path(root, directory=True)
            with tempfile.TemporaryDirectory(prefix="runtime-bundle-", dir=root) as folder:
                mounted_folder = Path(folder)
                mounted = Path(folder) / "bundle.json"
                raw = paths.bundle.read_bytes()
                q.require(hashlib.sha256(raw).hexdigest() == request["bundle_sha256"], "BUNDLE_HASH_MISMATCH")
                mounted.write_bytes(raw)
                mounted.chmod(0o600)
                mounted_paths = replace(paths, bundle=mounted)

                def resolve_credential(alias: str) -> str:
                    q.require(credential_reads == 0 and policy.execution_gate is not None
                              and alias == policy.execution_gate.credential_alias,
                              "CREDENTIAL_ALIAS_OR_REENTRY_BLOCKED")
                    q.require(alias == q.CANONICAL_CREDENTIAL_ALIAS,
                              "CREDENTIAL_ALIAS_OR_REENTRY_BLOCKED")
                    # The executor is deliberately not a plaintext resolver. A later
                    # Owner-approved task must install a privileged resolver for the
                    # selected backend. Until then this remains pre-call fail-closed.
                    q.secret_presence(host)
                    raise q.Blocked("PRIVILEGED_SECRET_RESOLVER_NOT_INSTALLED")

                def final_preflight() -> None:
                    read_kill_switch(host)
                    # Qualification revocation or host disable is checked again
                    # immediately before the canonical provider boundary.
                    q.require(load_catalog() == catalog, "HOST_EXECUTION_POLICY_CHANGED")
                    verify_qualification(catalog, host)

                invoked = True
                outcome = await canonical.run_single_dispatch(
                    mounted_paths, runtime_policy=policy, credential_resolver=resolve_credential,
                    transition=transition, final_preflight=final_preflight,
                )
                # Capture the authoritative outcome before any fallible mount
                # cleanup or kill-switch read; neither may restore initial zeros.
                output = {
                    "state": outcome.state, "code": outcome.code,
                    "provider_calls": None if outcome.dispatch_started is None else 1 if outcome.dispatch_started else 0,
                    "operation_consumption": outcome.operation_consumed,
                    "actual_cost_vnd": None if outcome.actual_cost_vnd is None else str(outcome.actual_cost_vnd),
                    "canonical_evidence_sha256": outcome.evidence_sha256,
                }
                if outcome.state == "BLOCKED_PRE_CALL":
                    output.update(budget_reserved_vnd="0", actual_cost_vnd="0")
            read_kill_switch(host)
    except q.Blocked as exc:
        output["code"] = str(exc)
        if outcome is not None:
            output["state"] = "REVIEW_REQUIRED"
    except canonical.SingleDispatchBlocked as exc:
        output["code"] = exc.code
    except BaseException:
        output["code"] = "EXECUTOR_RUNTIME_REVIEW_REQUIRED" if invoked else "EXECUTOR_PREFLIGHT_FAILED"
        if outcome is not None:
            output["state"] = "REVIEW_REQUIRED"
    finally:
        if invoked and outcome is None and STATES.index(states[-1]) >= STATES.index("SECRET_AVAILABLE"):
            # Do not claim zero if canonical execution was interrupted: its
            # durable ledger and terminal evidence must decide consumption.
            output.update(state="REVIEW_REQUIRED", provider_calls=None,
                          operation_consumption=None, budget_reserved_vnd=None, actual_cost_vnd=None)
        still_mounted = mounted_folder is not None and mounted_folder.exists()
        output.update(credential_reads=credential_reads, transitions=[*states, "TERMINAL_EVIDENCE"],
                      bundle_mounted=still_mounted, authority_inferred=False)
        if still_mounted:
            output.update(state="REVIEW_REQUIRED", code="BUNDLE_CLEANUP_FAILED")
        if host is not None and locked:
            try:
                read_kill_switch(host)
                output["kill_switch"] = "ENGAGED"
                output["wrapper_evidence_sha256"] = q.persist(
                    Path(host.evidence_root), "execution-" + uuid.uuid4().hex + ".json", output)
            except Exception:
                output.update(state="REVIEW_REQUIRED", code="EXECUTOR_TERMINAL_EVIDENCE_FAILED")
        lifetime.close()
    if not isinstance(output.get("code"), str) or re.fullmatch(r"[A-Z][A-Z0-9_]*", output["code"]) is None:
        output["code"] = "EXECUTOR_RUNTIME_REVIEW_REQUIRED"
    return output
