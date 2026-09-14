"""Read-only candidate evidence audit; not runtime/dual-CI authority tooling."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

from app.provider_ci_provenance import EXECUTABLE_TREE_PATHS, executable_tree_sha256
from app.provider_runtime_bootstrap import _git_argv


BASE = "4507fa593fd8cf5484eb1245f788e9ee54eede39"
OLD_TREE = "ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5"
NEW_TREE = "432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502"
EVIDENCE = "evidence/v3-01/vf-v0s-b3-20260914-bootstrap-candidate"
DOCS = "docs/acceptance/v3-01/reviews/vf-v0s-b3"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(_git_argv(repo, *args), capture_output=True, text=True)
    if result.returncode:
        raise AssertionError("CANDIDATE_GIT_LOOKUP_FAILED")
    return result.stdout.strip()


def audit(repo: Path, ref: str, manifest: bool) -> dict:
    objects = {p: git(repo, "rev-parse", ref + ":" + p) for p in EXECUTABLE_TREE_PATHS}
    base_objects = {p: git(repo, "rev-parse", BASE + ":" + p) for p in EXECUTABLE_TREE_PATHS}
    first = executable_tree_sha256(objects)
    second = executable_tree_sha256(objects)
    assert first == second == NEW_TREE
    assert executable_tree_sha256(base_objects) == OLD_TREE
    changed_components = [p for p in EXECUTABLE_TREE_PATHS if objects[p] != base_objects[p]]
    assert changed_components == ["apps/api/app"]
    names = git(repo, "diff", "--name-only", BASE, ref).splitlines()
    allowed_exact = {
        "apps/api/app/provider_runtime_bootstrap.py",
        "apps/api/tests/test_provider_runtime_bootstrap.py",
        "docs/acceptance/v3-01/HANDOFF.md", "docs/acceptance/v3-01/handoff.json",
    }
    classifications = []
    for name in names:
        assert name in allowed_exact or name.startswith(DOCS + "/") or name.startswith(EVIDENCE + "/")
        kind = "bootstrap/runtime" if name.startswith("apps/api/app/") else (
            "tests" if name.startswith("apps/api/tests/") else (
                "handoff" if name.endswith("HANDOFF.md") or name.endswith("handoff.json") else "governance/evidence"
            )
        )
        classifications.append({"path": name, "class": kind})
    source = (repo / "apps/api/app/provider_runtime_bootstrap.py").read_text()
    assert "vf_vf_v3_01_rc18_" not in source and "vf-v3-01-rc18" not in source
    parsed_json = []
    links = 0
    for name in names:
        path = repo / name
        if name.endswith(".json"):
            json.loads(path.read_text(encoding="utf-8"))
            parsed_json.append(name)
        if name.endswith(".md"):
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                target = target.strip("<>").split("#")[0]
                if not target or re.match(r"^[a-zA-Z]+://", target):
                    continue
                assert (path.parent / unquote(target)).resolve().is_file(), (name, target)
                links += 1
    # Reuse the repository scanner; never examine .env/secret custody files.
    sys.path.insert(0, str(repo / "scripts"))
    from v3_01_acceptance import scan_for_secrets
    scan_for_secrets([repo / name for name in names])
    handoff = json.loads((repo / "docs/acceptance/v3-01/handoff.json").read_text())
    md = (repo / "docs/acceptance/v3-01/HANDOFF.md").read_text()
    assert handoff["candidate"]["executable_tree_sha256"] == NEW_TREE and NEW_TREE in md
    assert handoff["baseline"]["main_sha"] == BASE and BASE in md
    assert handoff["authority"]["candidate_authority"] == "NOT_CREATED" and "NOT_CREATED" in md
    assert handoff["authority"]["kill_switch"] == "ENGAGED" and "ENGAGED" in md
    assert handoff["authority"]["operation_2"] == "NOT_APPROVED / LOCKED / NOT_TRANSFERRED"
    assert "NOT_APPROVED / LOCKED / NOT_TRANSFERRED" in md
    assert handoff["acceptance"]["asr_consecutive_pass"] == 0 and "ASR: 0/2 PASS" in md
    assert handoff["acceptance"]["vision_consecutive_pass"] == 2 and "Vision: 2/2 PASS" in md
    assert handoff["acceptance"]["production"] == "NO-GO" and "Production: NO-GO" in md
    for key in ("provider_credential_reads", "real_provider_calls", "live_budget_reservations", "production_business_writes"):
        assert handoff["safety"][key] == 0
    assert git(repo, "rev-parse", "vf-v3-01-rc18^{}") == "03e18c1f0c56fff8a13f167af74f34894c2db811"
    assert git(repo, "rev-parse", "vf-v3-01-rc17^{}") == "d08ffc005d7f3ad517d355977b0bc3cc8d686906"
    git(repo, "diff", "--check", BASE, ref)
    checked = 0
    if manifest:
        for row in (repo / EVIDENCE / "SHA256SUMS.txt").read_text().splitlines():
            expected, name = row.split("  ", 1)
            assert re.fullmatch(r"[a-f0-9]{64}", expected)
            assert hashlib.sha256((repo / name).read_bytes()).hexdigest() == expected, name
            checked += 1
    return {
        "result": "PASS", "base_main": BASE, "tree_ref": ref,
        "canonical_input": objects, "recompute_1": first, "recompute_2": second,
        "old_tree": OLD_TREE, "changed_executable_components": changed_components,
        "files": classifications, "json_files": len(parsed_json), "markdown_links": links,
        "secret_scan": "PASS_ZERO_MATCHES", "diff_check": "PASS", "checksums_verified": checked,
        "handoff_md_json_parity": "PASS", "rc17_rc18": "IMMUTABLE",
        "provider_calls": 0, "provider_credential_reads": 0, "live_reservations": 0,
        "candidate_authority": "NOT_CREATED", "new_rc_created": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--tree-ref", required=True)
    parser.add_argument("--verify-manifest", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.repo, args.tree_ref, args.verify_manifest), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
