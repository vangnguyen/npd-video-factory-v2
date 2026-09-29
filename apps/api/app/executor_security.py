"""Independent hostile-job review for the zero-call executor plane."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import uuid

from . import executor_qualification as q

HOSTILE_JOB_TESTS = (
    "unapproved_repository",
    "unapproved_workflow",
    "unapproved_ref",
    "modified_workflow",
    "pr_triggered_workflow",
    "command_injection",
    "environment_injection",
    "stale_source_commit",
    "incorrect_executable_tree_sha",
    "cross_runner_receipt",
    "concurrent_execution_attempt",
)


def _load_hook(host: q.Host):
    path = Path(host.source) / "scripts/executor-job-started.py"
    q.private_path(path, root_owned=True)
    spec = importlib.util.spec_from_file_location("installed_executor_admission", path)
    q.require(spec is not None and spec.loader is not None, "ADMISSION_HOOK_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _identity_rejected(host: q.Host, field: str, value: object) -> bool:
    identity = q.expected_runner_identity(host)
    identity[field] = value
    try:
        q.require_runner_identity({"runner_identity": identity}, host, "IDENTITY_REJECTED")
    except q.Blocked:
        return True
    return False


def review(host: q.Host, root: Path, *, hook=None) -> dict:
    manifest = q.admission_manifest(host, "qualification")
    hook = hook or _load_hook(host)
    trusted = {
        "GITHUB_REPOSITORY": host.execution_repository,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_SHA": host.execution_workflow_commit,
        "GITHUB_WORKFLOW_REF": q.QUALIFICATION_WORKFLOW_REF,
    }
    q.require(hook.allowed(trusted, manifest), "APPROVED_QUALIFICATION_REJECTED")
    cases = {
        "unapproved_repository": not hook.allowed(
            {**trusted, "GITHUB_REPOSITORY": "unapproved/repository"}, manifest),
        "unapproved_workflow": not hook.allowed(
            {**trusted, "GITHUB_WORKFLOW_REF": host.execution_repository + "/.github/workflows/unapproved.yml@refs/heads/main"},
            manifest),
        "unapproved_ref": not hook.allowed(
            {**trusted, "GITHUB_REF": "refs/heads/unapproved"}, manifest),
        "modified_workflow": not hook.allowed(
            {**trusted, "GITHUB_WORKFLOW_SHA": "0" * 40}, manifest),
        "pr_triggered_workflow": not hook.allowed(
            {**trusted, "GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF": "refs/pull/1/merge"},
            manifest),
        "command_injection": not hook.allowed(
            {**trusted, "GITHUB_WORKFLOW_REF": q.QUALIFICATION_WORKFLOW_REF + ";id"}, manifest),
        "environment_injection": not hook.allowed(
            {**trusted, "VF_REQUEST_JSON": "{}"}, manifest),
        "stale_source_commit": _identity_rejected(host, "source_commit", "0" * 40),
        "incorrect_executable_tree_sha": _identity_rejected(
            host, "executor_executable_tree_sha256", "0" * 64),
        "cross_runner_receipt": _identity_rejected(host, "runner_id", 21),
    }
    try:
        with q.plane_lock(Path(host.lock_path)):
            try:
                with q.plane_lock(Path(host.lock_path)):
                    pass
            except q.Blocked as exc:
                cases["concurrent_execution_attempt"] = str(exc) == "CONCURRENT_EXECUTION_BLOCKED"
            else:
                cases["concurrent_execution_attempt"] = False
    except Exception:
        cases["concurrent_execution_attempt"] = False
    q.require(set(cases) == set(HOSTILE_JOB_TESTS) and all(cases.values()),
              "HOSTILE_JOB_SECURITY_FAILED")
    kill = Path(host.kill_switch)
    q.private_path(kill, root_owned=True)
    q.require(kill.read_bytes() == b"ENGAGED\n", "KILL_SWITCH_NOT_ENGAGED")
    report = {
        "task": "VF-SECRET-01",
        "status": "RUNNER_SECURITY_PASS",
        "quarantine": "CLEARED_BY_VALIDATED_POLICY",
        "runner_identity": q.expected_runner_identity(host),
        "execution_workflow_commit": host.execution_workflow_commit,
        "hostile_job_tests": {name: "PASS" for name in HOSTILE_JOB_TESTS},
        "kill_switch": "ENGAGED",
        "provider_execution_allowlist": "EMPTY",
        **q.ZERO,
    }
    digest = q.persist(root, "security-review.json", report)
    return {"report": report, "security_review_sha256": digest}


def main() -> int:
    argparse.ArgumentParser(description="Video Factory independent runner security review").parse_args()
    try:
        host = q.Host.load()
        evidence = Path(host.evidence_root)
        q.private_path(evidence, directory=True)
        root = evidence / ("vf-secret-01-security-" + uuid.uuid4().hex)
        root.mkdir(mode=0o700)
        result = review(host, root)
        print(json.dumps({"status": result["report"]["status"],
            "evidence_directory": root.name,
            "security_review_sha256": result["security_review_sha256"], **q.ZERO}, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "BLOCKED", "code": "RUNNER_SECURITY_REVIEW_FAILED", **q.ZERO}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
