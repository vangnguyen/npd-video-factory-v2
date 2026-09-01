#!/usr/bin/env python3
"""Verify dual CI provenance for a locked RC and a governance-only main merge.

This utility is intentionally unable to read credentials, reserve budget, call
providers, deploy, publish or enable ingress. It collects Git/GitHub metadata
and validates it through the canonical executable contract.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.provider_ci_provenance import (  # noqa: E402
    EXECUTABLE_TREE_PATHS,
    ProviderCiProvenanceError,
    executable_tree_sha256,
    provider_ci_provenance_sha256,
    validate_provider_acceptance_ci_provenance,
)


class CiProvenanceCollectionError(RuntimeError):
    pass


def _run(command: list[str], *, cwd: Path) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise CiProvenanceCollectionError(
            f"command is unavailable for provenance collection: {command[0]}"
        ) from exc
    if result.returncode != 0:
        raise CiProvenanceCollectionError(
            f"command failed without trusted provenance: {command[0]}"
        )
    return result.stdout.strip()


def _git_object_map(repo: Path, commit: str) -> dict[str, str]:
    return {
        path: _run(["git", "rev-parse", f"{commit}:{path}"], cwd=repo)
        for path in EXECUTABLE_TREE_PATHS
    }


def _observe_ci_run(
    *,
    repo: Path,
    repository_slug: str,
    run_id: int,
    role: str,
) -> dict[str, object]:
    raw = _run(
        [
            "gh",
            "run",
            "view",
            str(run_id),
            "--repo",
            repository_slug,
            "--json",
            "databaseId,headSha,status,conclusion,name,jobs,updatedAt",
        ],
        cwd=repo,
    )
    try:
        observed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CiProvenanceCollectionError(
            "GitHub CI response is not valid JSON"
        ) from exc
    if not isinstance(observed, dict):
        raise CiProvenanceCollectionError("GitHub CI response is not an object")
    jobs = observed.get("jobs")
    if not isinstance(jobs, list):
        raise CiProvenanceCollectionError("GitHub CI jobs are unavailable")
    if any(not isinstance(job, dict) for job in jobs):
        raise CiProvenanceCollectionError("GitHub CI job evidence is invalid")
    return {
        "role": role,
        "workflow_name": observed.get("name"),
        "run_id": observed.get("databaseId"),
        "commit_sha": observed.get("headSha"),
        "status": observed.get("status"),
        "conclusion": observed.get("conclusion"),
        "jobs_total": len(jobs),
        "jobs_succeeded": sum(
            1 for job in jobs if job.get("conclusion") == "success"
        ),
        "completed_at_utc": observed.get("updatedAt"),
    }


def collect_and_validate(
    *,
    repo: Path,
    repository_slug: str,
    executable_rc_commit: str,
    governance_main_commit: str,
    executable_rc_ci_run_id: int,
    governance_main_ci_run_id: int,
) -> dict[str, object]:
    repo = repo.resolve()
    observed_rc_commit = _run(
        ["git", "rev-parse", f"{executable_rc_commit}^{{commit}}"],
        cwd=repo,
    )
    observed_governance_commit = _run(
        ["git", "rev-parse", f"{governance_main_commit}^{{commit}}"],
        cwd=repo,
    )
    if observed_rc_commit != executable_rc_commit:
        raise CiProvenanceCollectionError(
            "executable RC commit cannot be resolved exactly"
        )
    if observed_governance_commit != governance_main_commit:
        raise CiProvenanceCollectionError(
            "governance main commit cannot be resolved exactly"
        )

    changed_paths = sorted(
        {
            line
            for line in _run(
                [
                    "git",
                    "diff",
                    "--name-only",
                    "--no-renames",
                    f"{executable_rc_commit}..{governance_main_commit}",
                ],
                cwd=repo,
            ).splitlines()
            if line
        }
    )
    rc_tree = executable_tree_sha256(
        _git_object_map(repo, executable_rc_commit)
    )
    governance_tree = executable_tree_sha256(
        _git_object_map(repo, governance_main_commit)
    )
    payload = {
        "version": 1,
        "executable_rc_commit": executable_rc_commit,
        "governance_main_commit": governance_main_commit,
        "executable_rc_ci": _observe_ci_run(
            repo=repo,
            repository_slug=repository_slug,
            run_id=executable_rc_ci_run_id,
            role="executable_rc",
        ),
        "governance_main_ci": _observe_ci_run(
            repo=repo,
            repository_slug=repository_slug,
            run_id=governance_main_ci_run_id,
            role="governance_main",
        ),
        "executable_tree_sha256": rc_tree,
        "governance_executable_tree_sha256": governance_tree,
        "governance_changed_paths": changed_paths,
    }
    provenance = validate_provider_acceptance_ci_provenance(
        payload,
        expected_executable_rc_commit=executable_rc_commit,
        expected_governance_main_commit=governance_main_commit,
        expected_executable_rc_ci_run_id=executable_rc_ci_run_id,
        expected_governance_main_ci_run_id=governance_main_ci_run_id,
    )
    return {
        "verdict": "PASS",
        "contract": provenance.model_dump(mode="json"),
        "provenance_sha256": provider_ci_provenance_sha256(provenance),
        "credential_reads": 0,
        "provider_calls": 0,
        "reservation_vnd": "0",
        "production_verdict": "NO-GO",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--repository-slug",
        default="vangnguyen/npd-video-factory-v2",
    )
    parser.add_argument("--executable-rc-commit", required=True)
    parser.add_argument("--governance-main-commit", required=True)
    parser.add_argument("--executable-rc-ci-run-id", required=True, type=int)
    parser.add_argument("--governance-main-ci-run-id", required=True, type=int)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = collect_and_validate(
            repo=args.repo,
            repository_slug=args.repository_slug,
            executable_rc_commit=args.executable_rc_commit,
            governance_main_commit=args.governance_main_commit,
            executable_rc_ci_run_id=args.executable_rc_ci_run_id,
            governance_main_ci_run_id=args.governance_main_ci_run_id,
        )
    except (CiProvenanceCollectionError, ProviderCiProvenanceError) as exc:
        code = getattr(exc, "code", "CI_PROVENANCE_COLLECTION_FAILED")
        print(
            json.dumps(
                {
                    "verdict": "BLOCKED_0_CALL",
                    "code": code,
                    "credential_reads": 0,
                    "provider_calls": 0,
                    "reservation_vnd": "0",
                    "production_verdict": "NO-GO",
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
