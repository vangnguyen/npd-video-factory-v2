"""Offline source/CI/handoff audit for VF-V0S-B4; cannot dispatch or materialize authority."""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path
from urllib.parse import unquote
from app.provider_ci_provenance import EXECUTABLE_TREE_PATHS, ProviderCiRunEvidence, executable_tree_sha256
from app.provider_runtime_bootstrap import _git_argv

MAIN = "dc8ff55322267dfe54674fa6c4003a899bf235ab"
APPROVED = "40d8de37e8fb4294a478422ed4f5f546e815ef55"
TREE = "432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502"
OLD_TREE = "ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5"
EVIDENCE = "evidence/v3-01/vf-v0s-b4-20260914-exact-main-verification"
B3 = "evidence/v3-01/vf-v0s-b3-20260914-bootstrap-candidate"
DOCS = "docs/acceptance/v3-01/reviews/vf-v0s-b4"
EXPECTED_JOBS = {"Python unit and contract tests", "Renderer tests and bundle", "Studio tests",
                 "Safety and compose contract", "Docker deterministic E2E"}

def git(repo, *args, binary=False):
    result = subprocess.run(_git_argv(repo, *args), capture_output=True)
    assert result.returncode == 0, "SAFE_GIT_LOOKUP_FAILED"
    return result.stdout if binary else result.stdout.decode("utf-8").strip()

def audit(repo, manifest=False):
    proof = json.loads((repo / EVIDENCE / "postmerge-provenance.json").read_text())
    assert proof["main_sha"] == MAIN and proof["approved_head"] == APPROVED
    assert proof["verdict"] == proof["main_provenance"] == "PASS"
    ci = proof["exact_main_ci"]
    assert ci["id"] == 34869652973 and ci["head_sha"] == MAIN
    assert ci["name"] == "Video Factory V2 CI" and ci["event"] == "push" and ci["head_branch"] == "main"
    assert ci["status"] == "completed" and ci["conclusion"] == "success"
    normalized = ProviderCiRunEvidence.model_validate(proof["main_ci_evidence"])
    assert normalized.run_id == ci["id"] and normalized.commit_sha == MAIN
    assert normalized.jobs_total == normalized.jobs_succeeded == 5
    jobs = proof["canonical_jobs"]
    assert len(jobs) == 5 and {j["name"] for j in jobs} == EXPECTED_JOBS
    assert all(j["status"] == "completed" and j["conclusion"] == "success" for j in jobs)
    assert git(repo, "show", "-s", "--format=%P", MAIN).split() == [proof["premerge_main"], APPROVED]
    assert git(repo, "rev-parse", MAIN + "^{tree}") == git(repo, "rev-parse", APPROVED + "^{tree}")
    objects = {p: git(repo, "rev-parse", MAIN + ":" + p) for p in EXECUTABLE_TREE_PATHS}
    objects_2 = {p: git(repo, "rev-parse", MAIN + ":" + p) for p in EXECUTABLE_TREE_PATHS}
    first, second = executable_tree_sha256(objects), executable_tree_sha256(objects_2)
    assert first == second == TREE
    assert objects == proof["canonical_input_local"] == proof["canonical_input_github"]
    head_objects = {p: git(repo, "rev-parse", "HEAD:" + p) for p in EXECUTABLE_TREE_PATHS}
    assert executable_tree_sha256(head_objects) == TREE
    rc18_objects = {p: git(repo, "rev-parse", "vf-v3-01-rc18:" + p) for p in EXECUTABLE_TREE_PATHS}
    assert executable_tree_sha256(rc18_objects) == OLD_TREE != TREE
    assert git(repo, "rev-parse", "vf-v3-01-rc18^{}") == "03e18c1f0c56fff8a13f167af74f34894c2db811"
    assert git(repo, "rev-parse", "vf-v3-01-rc18") == "30ca09c4201cd6aea5e733c26ba4dfa1f30d5021"
    assert git(repo, "rev-parse", "vf-v3-01-rc17^{}") == "d08ffc005d7f3ad517d355977b0bc3cc8d686906"
    assert git(repo, "rev-parse", "vf-v3-01-rc17") == "ea67843635dddf94ee25d38111fc06782ad9fd74"
    merged_paths = git(repo, "diff", "--name-only", proof["premerge_main"], MAIN).splitlines()
    assert len(merged_paths) == 20
    premerge = json.loads((repo / EVIDENCE / "premerge-g08.json").read_text())
    assert {f["path"] for f in premerge["file_proof"]["files"]} == set(merged_paths)
    for item in premerge["file_proof"]["files"]:
        assert git(repo, "rev-parse", MAIN + ":" + item["path"]) == item["git_blob"]
    source = (repo / "apps/api/app/provider_runtime_bootstrap.py").read_text()
    assert "vf-v3-01-rc18" not in source and "vf_vf_v3_01_rc18_" not in source
    paths = set(git(repo, "diff", "--name-only", MAIN, "HEAD").splitlines())
    paths.update(git(repo, "diff", "--name-only").splitlines())
    paths.update(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    paths.update(["docs/acceptance/v3-01/HANDOFF.md", "docs/acceptance/v3-01/handoff.json"])
    paths.update(str(p.relative_to(repo)).replace("\\","/") for p in (repo / EVIDENCE).rglob("*") if p.is_file())
    paths.update(str(p.relative_to(repo)).replace("\\","/") for p in (repo / DOCS).rglob("*") if p.is_file())
    allowed = {"docs/acceptance/v3-01/HANDOFF.md", "docs/acceptance/v3-01/handoff.json"}
    assert all(p in allowed or p.startswith(EVIDENCE+"/") or p.startswith(DOCS+"/") for p in paths)
    assert not (repo/"HANDOFF.md").exists() and not (repo/"handoff.json").exists()
    parsed, links = 0, 0
    for name in sorted(paths):
        path = repo/name
        assert path.is_file()
        if name.endswith(".json"):
            json.loads(path.read_text(encoding="utf-8")); parsed += 1
        if name.endswith(".md"):
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text()):
                target = target.strip("<>").split("#")[0]
                if not target or re.match(r"^[a-zA-Z]+://",target): continue
                assert (path.parent/unquote(target)).resolve().is_file(), (name,target)
                links += 1
    sys.path.insert(0,str(repo/"scripts"))
    from v3_01_acceptance import scan_for_secrets
    scan_for_secrets([repo/p for p in paths])
    handoff = json.loads((repo/"docs/acceptance/v3-01/handoff.json").read_text())
    md = (repo/"docs/acceptance/v3-01/HANDOFF.md").read_text()
    assert handoff["task_id"] == "VF-V0S-B4" and handoff["verdict"] == "PASS"
    assert handoff["baseline"]["main_sha"] == MAIN and MAIN in md and TREE in md
    assert handoff["ci"]["run_id"] == 34869652973 and "34869652973" in md
    assert handoff["authority"]["rc18_current_main_validity"] == "HISTORICAL_REFERENCE_ONLY / INVALID_FOR_CURRENT_MAIN"
    assert "HISTORICAL_REFERENCE_ONLY / INVALID_FOR_CURRENT_MAIN" in md
    assert handoff["authority"]["operation_1_authority"] == "NOT_CREATED_FOR_CURRENT_MAIN"
    assert handoff["authority"]["operation_2"] == "NOT_APPROVED / LOCKED / NOT_TRANSFERRED"
    assert "NOT_APPROVED / LOCKED / NOT_TRANSFERRED" in md
    assert handoff["authority"]["kill_switch"] == "ENGAGED" and not handoff["authority"]["bundle_mounted"]
    assert "Kill switch: ENGAGED. Bundle: UNMOUNTED" in md
    assert handoff["current_source"]["new_rc_required"] and not handoff["current_source"]["new_rc_created"]
    assert handoff["current_source"]["fresh_ledger_binding_required"] and handoff["current_source"]["fresh_execution_window_required"]
    assert handoff["acceptance"]["asr_consecutive_pass"] == 0 and "ASR: 0/2 PASS" in md
    assert handoff["acceptance"]["vision_consecutive_pass"] == 2 and "Vision: 2/2 PASS" in md
    assert handoff["acceptance"]["production"] == "NO-GO" and "Production: NO-GO" in md
    assert all(handoff["safety"][p] == 0 for p in ("provider_credential_reads","real_provider_calls","live_budget_reservations","production_business_writes"))
    assert not handoff["safety"]["new_future_execution_ledger_namespace_created"]
    git(repo,"diff","--check",MAIN)
    historical_checksums = 0
    # Resolve the unchanged B3 manifest and its prior handoff hashes at the actual
    # merged baseline, not the later canonical handoff working tree.
    for row in git(repo,"show",MAIN+":"+B3+"/SHA256SUMS.txt").splitlines():
        expected, name = row.split("  ",1)
        assert hashlib.sha256(git(repo,"show",MAIN+":"+name,binary=True)).hexdigest() == expected
        if name not in allowed:
            assert hashlib.sha256((repo/name).read_bytes()).hexdigest() == expected
        historical_checksums += 1
    checksums = 0
    if manifest:
        for row in (repo/EVIDENCE/"SHA256SUMS.txt").read_text().splitlines():
            expected,name = row.split("  ",1)
            assert hashlib.sha256((repo/name).read_bytes()).hexdigest() == expected, name
            checksums += 1
    return {"task":"VF-V0S-B4","verdict":"PASS","main_sha":MAIN,"main_provenance":"PASS",
        "main_ci_schema":"PASS_EXISTING_ProviderCiRunEvidence","ci":"34869652973_5_OF_5_PASS",
        "recompute_1":first,"recompute_2":second,"local_remote_12_objects":"PASS",
        "merged_exact_files":len(merged_paths),"handoff_governance_only":"PASS",
        "json_files":parsed,"markdown_links":links,"diff_check":"PASS","secret_scan":"PASS_ZERO_MATCHES",
        "historical_b3_checksums_at_main":historical_checksums,"checksums":checksums,"handoff_md_json_parity":"PASS",
        "rc17_rc18":"IMMUTABLE","rc18_current_main_tree_equality":False,"mismatch":"EXPECTED_NEW_SOURCE_REQUIRES_FRESH_RC",
        "new_rc_required":True,"new_rc_created":False,"authority_created":False,"future_ledger_namespace_created":False,
        "provider_calls":0,"provider_credential_reads":0,"live_budget_reserved_vnd":"0","production_business_writes":0,
        "next_safe_action":"Owner assign VF-V0S-B5; do not execute automatically"}

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,required=True)
    parser.add_argument("--verify-manifest",action="store_true")
    args=parser.parse_args()
    print(json.dumps(audit(args.repo.resolve(),args.verify_manifest),sort_keys=True,indent=2))
