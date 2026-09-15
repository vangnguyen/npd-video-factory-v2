"""Offline audit for VF-V0S-B5G RC-19 governance provenance closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from app.provider_ci_provenance import (
    ALLOWED_GOVERNANCE_PATH_PREFIXES,
    EXECUTABLE_TREE_PATHS,
    ProviderCiRunEvidence,
    executable_tree_sha256,
    provider_ci_provenance_sha256,
    validate_provider_acceptance_ci_provenance,
)


RC_COMMIT = "dc8ff55322267dfe54674fa6c4003a899bf235ab"
MAIN_COMMIT = "d13c57bf480ed3b6b8b56f46370fef58b291810b"
APPROVED_HEAD = "cd866a03445eff1df0f489b2b6050f22939a363f"
TREE_SHA = "432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502"
DUAL_SHA = "12128084c7fff1397b2476e5360b45e13232eef0bbf161f962c3c6de38d43228"
PACK = Path("evidence/v3-01/vf-v0s-b5g-20260915-rc19-provenance-closure")


def run(repo: Path, *argv: str) -> str:
    result = subprocess.run(
        ["git", *argv], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def object_map(repo: Path, commit: str) -> dict[str, str]:
    return {
        path: run(repo, "rev-parse", f"{commit}:{path}")
        for path in EXECUTABLE_TREE_PATHS
    }


def load(repo: Path, name: str) -> dict[str, object]:
    value = json.loads((repo / PACK / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def audit(repo: Path, *, verify_manifest: bool) -> dict[str, object]:
    repo = repo.resolve()
    g08 = load(repo, "g08-review.json")
    merge = load(repo, "merge-observation.json")
    ci = load(repo, "exact-main-ci.json")
    main = load(repo, "main-provenance.json")
    dual = load(repo, "dual-ci-provenance.json")
    live = load(repo, "live-state.json")
    hand = json.loads(
        (repo / "docs/acceptance/v3-01/handoff.json").read_text(encoding="utf-8")
    )

    assert g08["verdict"] == "PASS" and g08["approved_head_sha"] == APPROVED_HEAD
    assert len(g08["changed_files"]) == 18 and g08["executable_runtime_changes"] == 0
    assert all(
        item["path"].startswith(ALLOWED_GOVERNANCE_PATH_PREFIXES)
        for item in g08["changed_files"]
    )
    assert merge["merge_commit"] == MAIN_COMMIT
    assert merge["merge_commit_parents"] == [RC_COMMIT, APPROVED_HEAD]
    assert merge["tree_equality"] == "PASS"
    assert merge["approved_exact_head_merged"] is True

    ProviderCiRunEvidence.model_validate(main["ci"])
    assert ci["run_id"] == 34916352282
    assert ci["jobs_total"] == ci["jobs_succeeded"] == 5
    assert len(ci["jobs"]) == 5
    assert all(job["conclusion"] == "success" for job in ci["jobs"])
    assert main["verdict"] == "PASS" and main["main_sha"] == MAIN_COMMIT
    assert main["full_git_tree"] == run(repo, "rev-parse", f"{MAIN_COMMIT}^{{tree}}")
    assert main["executable_git_objects"] == object_map(repo, MAIN_COMMIT)
    assert executable_tree_sha256(main["executable_git_objects"]) == TREE_SHA

    provenance = validate_provider_acceptance_ci_provenance(
        dual["contract"],
        expected_executable_rc_commit=RC_COMMIT,
        expected_governance_main_commit=MAIN_COMMIT,
        expected_executable_rc_ci_run_id=34875483864,
        expected_governance_main_ci_run_id=34916352282,
    )
    assert provider_ci_provenance_sha256(provenance) == dual["provenance_sha256"] == DUAL_SHA
    assert executable_tree_sha256(object_map(repo, RC_COMMIT)) == TREE_SHA
    assert executable_tree_sha256(object_map(repo, MAIN_COMMIT)) == TREE_SHA

    assert hand["task_id"] == "VF-V0S-B5G" and hand["verdict"] == "PASS"
    assert hand["rc"]["governance_lineage"] == "CLOSED / PASS"
    assert hand["future_ledger_plan"]["ledger_created"] is False
    assert hand["authority"]["operation_1_id"] == "NOT_GENERATED"
    assert hand["authority"]["operation_1_authority"] == "NOT_CREATED"
    assert hand["authority"]["operation_2"] == "NOT_APPROVED / LOCKED / NOT_TRANSFERRED"
    assert hand["authority"]["kill_switch"] == "ENGAGED"
    assert hand["authority"]["bundle_mounted"] is False
    assert hand["safety"] == {
        "ledger_created": False,
        "ledger_runtime_writes": 0,
        "provider_credential_reads": 0,
        "real_provider_calls": 0,
        "live_budget_reserved_vnd": "0",
        "production_business_writes": 0,
        "actual_provider_cost_vnd": "0",
    }
    assert live["ledger_created"] is False and live["real_provider_calls"] == 0
    assert live["pr66"]["disposition"] == "SUPERSEDED_HISTORICAL_DRAFT"

    markdown = (repo / "docs/acceptance/v3-01/HANDOFF.md").read_text(encoding="utf-8")
    for token in (
        "TASK: VF-V0S-B5G",
        "VERDICT: PASS",
        "RC19_GOVERNANCE_LINEAGE: CLOSED / PASS",
        "ASR: 0/2 PASS",
        "Vision: 2/2 PASS",
        "Production: NO-GO",
    ):
        assert token in markdown

    checksum_count = 0
    if verify_manifest:
        lines = (repo / PACK / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line:
                continue
            expected, rel = line.split("  ", 1)
            payload = (repo / PACK / rel).read_bytes()
            assert hashlib.sha256(payload).hexdigest() == expected
            checksum_count += 1

    json_count = 0
    json_paths = [
        repo / "docs/acceptance/v3-01/handoff.json",
        *(repo / PACK).glob("*.json"),
    ]
    for path in json_paths:
        json.loads(path.read_text(encoding="utf-8"))
        json_count += 1

    link_count = 0
    markdown_paths = [
        repo / PACK / "README.md",
        repo / "docs/acceptance/v3-01/HANDOFF.md",
    ]
    for md in markdown_paths:
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", md.read_text(encoding="utf-8")):
            if target.startswith("https://"):
                link_count += 1
                continue
            assert (md.parent / target).resolve().exists(), target
            link_count += 1

    changed = [
        line
        for line in run(repo, "diff", "--name-only", f"{MAIN_COMMIT}..HEAD").splitlines()
        if line
    ]
    assert changed
    assert all(path.startswith(ALLOWED_GOVERNANCE_PATH_PREFIXES) for path in changed)
    assert executable_tree_sha256(object_map(repo, "HEAD")) == TREE_SHA
    assert run(repo, "diff", "--check", f"{MAIN_COMMIT}..HEAD") == ""

    secret_patterns = (
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{16,}"),
        re.compile(r"(?i)(api[_-]?key|token|password)\s*[:=]\s*['\"][^'\"]{8,}"),
    )
    for rel in changed:
        path = repo / rel
        if path.suffix.lower() in {".wav", ".png", ".jpg", ".jpeg", ".pdf"}:
            continue
        content = path.read_text(encoding="utf-8")
        assert not any(pattern.search(content) for pattern in secret_patterns), rel

    return {
        "task_id": "VF-V0S-B5G",
        "verdict": "PASS",
        "g08": "PASS",
        "exact_main_ci": "34916352282_5_OF_5_PASS",
        "main_provenance": "PASS",
        "dual_ci_provenance": "PASS",
        "dual_ci_provenance_sha256": DUAL_SHA,
        "rc19_governance_lineage": "CLOSED_PASS",
        "canonical_tree": TREE_SHA,
        "tree_equality": "PASS",
        "json_parse": json_count,
        "markdown_links": link_count,
        "checksums": checksum_count,
        "secret_scan": "PASS_ZERO_MATCHES",
        "diff_check": "PASS",
        "scope_drift": "PASS",
        "credential_reads": 0,
        "budget_reserved_vnd": "0",
        "provider_calls": 0,
        "production_business_writes": 0,
        "actual_cost_vnd": "0",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--verify-manifest", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            audit(args.repo, verify_manifest=args.verify_manifest),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
