"""Read-only VF-V0S-B5 evidence/handoff audit; this is not execution bootstrap."""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path
from urllib.parse import unquote
from pydantic import ValidationError
from app.provider_ci_provenance import (EXECUTABLE_TREE_PATHS, ProviderCiRunEvidence,
    ProviderAcceptanceCiProvenance, ProviderCiProvenanceError,
    validate_provider_acceptance_ci_provenance, executable_tree_sha256)
from app.provider_runtime_bootstrap import _git_argv, ledger_database_name
from app.provider_safety import derive_acceptance_lineage_id
MAIN="dc8ff55322267dfe54674fa6c4003a899bf235ab"
TREE="432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502"
RC="vf-v3-01-rc19"
TAG="09a9a51628ab2e33d4ee85a1620f7afca692d18e"
EP="evidence/v3-01/vf-v0s-b5-20260915-rc19-materialization"
DP="docs/acceptance/v3-01/reviews/vf-v0s-b5"
B3="evidence/v3-01/vf-v0s-b3-20260914-bootstrap-candidate"
HANDOFFS={"docs/acceptance/v3-01/HANDOFF.md","docs/acceptance/v3-01/handoff.json"}
def git(repo,*args,raw=False):
    p=subprocess.run(_git_argv(repo,*args),capture_output=True)
    assert p.returncode==0,"SAFE_GIT_LOOKUP_FAILED"
    return p.stdout if raw else p.stdout.decode("utf-8").strip()

def audit(repo,verify_manifest):
    proof=json.loads((repo/EP/"rc-ci.json").read_text())
    rc_ci=ProviderCiRunEvidence.model_validate(proof["normalized_rc_ci"])
    assert rc_ci.role=="executable_rc" and rc_ci.run_id==34875483864 and rc_ci.commit_sha==MAIN
    assert rc_ci.jobs_total==rc_ci.jobs_succeeded==5
    assert proof["run"]["head_branch"]==RC and proof["run"]["event"]=="workflow_dispatch"
    assert proof["run"]["status"]=="completed" and proof["run"]["conclusion"]=="success"
    names={"Python unit and contract tests","Renderer tests and bundle","Studio tests","Safety and compose contract","Docker deterministic E2E"}
    jobs=proof["jobs"]
    assert len(jobs)==5 and {j["name"] for j in jobs}==names
    assert all(j["head_sha"]==MAIN and j["status"]=="completed" and j["conclusion"]=="success" for j in jobs)
    assert git(repo,"rev-parse",RC+"^{}")==MAIN and git(repo,"rev-parse",RC)==TAG
    assert git(repo,"cat-file","-t",RC)=="tag"
    main_objects={p:git(repo,"rev-parse",MAIN+":"+p) for p in EXECUTABLE_TREE_PATHS}
    rc_objects={p:git(repo,"rev-parse",RC+":"+p) for p in EXECUTABLE_TREE_PATHS}
    head_objects={p:git(repo,"rev-parse","HEAD:"+p) for p in EXECUTABLE_TREE_PATHS}
    assert main_objects==rc_objects==head_objects
    assert executable_tree_sha256(main_objects)==executable_tree_sha256(rc_objects)==TREE
    for name,tag,commit in (
      ("vf-v3-01-rc18","30ca09c4201cd6aea5e733c26ba4dfa1f30d5021","03e18c1f0c56fff8a13f167af74f34894c2db811"),
      ("vf-v3-01-rc17","ea67843635dddf94ee25d38111fc06782ad9fd74","d08ffc005d7f3ad517d355977b0bc3cc8d686906")):
        assert git(repo,"rev-parse",name)==tag and git(repo,"rev-parse",name+"^{}")==commit
    prior=(repo/EP/"b4-main-provenance-source.json").read_bytes()
    assert hashlib.sha256(prior).hexdigest()=="f08e979daba7d4049d5840a71c2aa99d7f3c9f165dc3b60df9e83ee61ddc6246"
    assert json.loads(prior)["main_sha"]==MAIN and json.loads(prior)["main_provenance"]=="PASS"
    annotation=json.loads((repo/EP/"tag-annotation.json").read_text())
    actual_message=git(repo,"cat-file","tag",TAG,raw=True).split(b"\n\n",1)[1]
    assert json.loads(actual_message)==annotation
    for name,pin in annotation["current_safety_rights_evidence_bindings"].items():
        assert git(repo,"rev-parse",MAIN+":"+name)==pin["git_object"]
        assert hashlib.sha256(git(repo,"show",MAIN+":"+name,raw=True)).hexdigest()==pin["git_blob_bytes_sha256"]
    assert not annotation["old_execution_material_transferred"] and not annotation["operation_1_id_generated"]
    assert annotation["operation_1_authority"]=="NOT_CREATED"
    blocked=json.loads((repo/EP/"dual-ci-blocked.json").read_text())
    payload=blocked["attempted_contract"]
    main_ci=ProviderCiRunEvidence.model_validate(payload["governance_main_ci"])
    assert main_ci.run_id==34869652973 and main_ci.role=="governance_main" and main_ci.commit_sha==MAIN
    assert main_ci.jobs_total==main_ci.jobs_succeeded==5
    assert payload["executable_rc_ci"]==rc_ci.model_dump(mode="json")
    assert payload["executable_rc_commit"]==payload["governance_main_commit"]==MAIN
    assert payload["governance_changed_paths"]==[] and git(repo,"diff","--name-only",MAIN,MAIN)==""
    try:
        validate_provider_acceptance_ci_provenance(payload,expected_executable_rc_commit=MAIN,
          expected_governance_main_commit=MAIN,expected_executable_rc_ci_run_id=34875483864,
          expected_governance_main_ci_run_id=34869652973)
        raise AssertionError("FALSE_DUAL_CI_PASS")
    except ProviderCiProvenanceError as exc:
        assert exc.code=="CI_PROVENANCE_INVALID"
    try:
        ProviderAcceptanceCiProvenance.model_validate(payload)
        raise AssertionError("FALSE_DUAL_CI_PASS")
    except ValidationError as exc:
        assert any(e["loc"]==("governance_changed_paths",) and e["type"]=="too_short" for e in exc.errors())
    assert blocked["collector_exit_code"]==2 and blocked["collector_output"]["verdict"]=="BLOCKED_0_CALL"
    hand=json.loads((repo/"docs/acceptance/v3-01/handoff.json").read_text())
    md=(repo/"docs/acceptance/v3-01/HANDOFF.md").read_text()
    assert hand["task_id"]=="VF-V0S-B5" and hand["verdict"]=="REVIEW_REQUIRED"
    assert hand["baseline"]["main_sha"]==MAIN and hand["baseline"]["main_provenance"]=="PASS"
    assert hand["rc"]["tag"]==RC and hand["rc"]["commit"]==MAIN and hand["rc"]["tag_object"]==TAG
    assert hand["rc"]["rc_ci"]==34875483864 and hand["rc"]["ci_result"]=="5/5 PASS"
    assert hand["rc"]["dual_ci"]=="BLOCKED_DISTINCT_GOVERNANCE_MAIN_REQUIRED"
    assert hand["authority"]["operation_1_authority"]=="NOT_CREATED"
    assert hand["authority"]["operation_2"]=="NOT_APPROVED / LOCKED / NOT_TRANSFERRED"
    assert hand["authority"]["kill_switch"]=="ENGAGED" and not hand["authority"]["bundle_mounted"]
    assert not hand["authority"]["rc18_material_reused"] and hand["authority"]["fresh_window_required"]
    plan=hand["ledger_naming_plan"]
    lineage=derive_acceptance_lineage_id(rc_tag=RC,rc_commit=MAIN,provider_key="openai-transcription",model="whisper-1",capability="asr",sequence=1)
    assert plan["expected_database_name"]==ledger_database_name(RC,lineage)
    assert plan["status"]=="PLAN_ONLY_NOT_CREATED_OR_APPROVED" and not plan["operation_id_generated"]
    assert plan["expected_database_name"] not in {
      "vf_vf_v3_01_rc18_466d54d9ede1b6f7f3179ddd52b7e251",
      "vf_vf_v3_01_rc19_c6da26ba2a8795793f7d36051a816b7d",
      "vf_vf_v3_01_rc20_20b9045ce79c76077018d74956d89b9a"}
    for key in ("ledger_runtime_writes","provider_credential_reads","real_provider_calls","live_budget_reservations","production_business_writes"):
        assert hand["safety"][key]==0
    assert hand["safety"]["actual_provider_cost_vnd"]=="0" and not hand["safety"]["new_runtime_ledger_created"]
    assert hand["acceptance"]=={"asr_consecutive":"0/2 PASS","vision_consecutive":"2/2 PASS","production":"NO-GO"}
    for value in (MAIN,TREE,RC,TAG,"34875483864","34869652973","REVIEW_REQUIRED",
      "NOT_CREATED","NOT_APPROVED / LOCKED / NOT_TRANSFERRED","ENGAGED","UNMOUNTED",
      "ASR: 0/2 PASS","Vision: 2/2 PASS","Production: NO-GO","BLOCKED_DISTINCT_GOVERNANCE_MAIN_REQUIRED",
      plan["expected_database_name"]):
        assert value in md,value
    assert not (repo/"HANDOFF.md").exists() and not (repo/"handoff.json").exists()
    changed=set(git(repo,"diff","--name-only",MAIN,"HEAD").splitlines())
    changed.update(git(repo,"diff","--name-only",MAIN).splitlines())
    changed.update(git(repo,"ls-files","--others","--exclude-standard").splitlines())
    assert changed and all(name in HANDOFFS or name.startswith(EP+"/") or name.startswith(DP+"/") for name in changed)
    audit_files=set(HANDOFFS)
    for prefix in (EP,DP):
        audit_files.update(str(p.relative_to(repo)).replace("\\","/") for p in (repo/prefix).rglob("*") if p.is_file())
    count_json=count_links=0
    for name in sorted(audit_files):
        p=repo/name
        if p.suffix==".json":
            json.loads(p.read_text());count_json+=1
        if p.suffix==".md":
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)",p.read_text()):
                target=target.strip("<>").split("#")[0]
                if not target or re.match(r"^[a-zA-Z]+://",target):continue
                assert (p.parent/unquote(target)).resolve().is_file(),(name,target)
                count_links+=1
        if p.suffix in {".md",".json",".py",".txt",".log"}:
            content=p.read_text()
            assert all(line==line.rstrip() for line in content.splitlines()),name
    sys.path.insert(0,str(repo/"scripts"))
    from v3_01_acceptance import scan_for_secrets
    scan_for_secrets([repo/name for name in audit_files])
    git(repo,"diff","--check",MAIN)
    historical_count=0
    for row in git(repo,"show",MAIN+":"+B3+"/SHA256SUMS.txt").splitlines():
        expected,name=row.split("  ",1)
        assert hashlib.sha256(git(repo,"show",MAIN+":"+name,raw=True)).hexdigest()==expected,name
        if name not in HANDOFFS:
            assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==expected
        historical_count+=1
    checksums=0
    if verify_manifest:
        rows=(repo/EP/"SHA256SUMS.txt").read_text().splitlines()
        names=set()
        for row in rows:
            expected,name=row.split("  ",1)
            assert name not in names and name in audit_files,names
            assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==expected,name
            names.add(name);checksums+=1
        assert names==audit_files-{EP+"/SHA256SUMS.txt"}
    return {"task_id":"VF-V0S-B5","audit_verdict":"PASS_EXPECTED_REVIEW_REQUIRED_STATE",
      "task_verdict":"REVIEW_REQUIRED","rc_ci":"34875483864_5_OF_5_PASS","main_provenance":"PASS",
      "rc_commit":MAIN,"rc_tag":RC,"canonical_tree":TREE,"main_rc_tree_equality":"PASS",
      "actual_dual_ci":"BLOCKED_DISTINCT_GOVERNANCE_MAIN_REQUIRED","real_validator_rejection":"CI_PROVENANCE_INVALID",
      "source_mutation":"NONE","historical_b3_checksums_at_original_main":historical_count,
      "governance_files":len(changed),"json_parse":count_json,"markdown_links":count_links,
      "checksums":checksums,"handoff_md_json_parity":"PASS","secret_scan":"PASS_ZERO_MATCHES","diff_check":"PASS",
      "ledger_created":False,"ledger_writes":0,"operation_id_generated":False,"authority_created":False,
      "provider_credential_reads":0,"real_provider_calls":0,"live_budget_reserved_vnd":"0","production_business_writes":0,
      "next_safe_action":"Owner G-08 review of the separate B5 governance draft; no merge/ledger/rebind/authority/dispatch automatically"}

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--repo",type=Path,required=True)
    ap.add_argument("--verify-manifest",action="store_true");args=ap.parse_args()
    print(json.dumps(audit(args.repo.resolve(),args.verify_manifest),sort_keys=True,indent=2))
