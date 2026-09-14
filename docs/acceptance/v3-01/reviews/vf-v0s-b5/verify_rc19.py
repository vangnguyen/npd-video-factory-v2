"""VF-V0S-B5 offline RC source qualification: no ledger, operation ID, bundle or authority."""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess
from pathlib import Path
from app.provider_ci_provenance import EXECUTABLE_TREE_PATHS, ProviderCiRunEvidence, executable_tree_sha256
from app.provider_runtime_bootstrap import _git_argv, ledger_database_name
from app.provider_safety import derive_acceptance_lineage_id, validate_acceptance_lineage_id
from app.asr_prompt_profile import prompt_profile_sha256, w1_prompt_profile

MAIN="dc8ff55322267dfe54674fa6c4003a899bf235ab"
TREE="432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502"
RC="vf-v3-01-rc19"
RC18="03e18c1f0c56fff8a13f167af74f34894c2db811"
TAG18="30ca09c4201cd6aea5e733c26ba4dfa1f30d5021"
JOBS={"Python unit and contract tests","Renderer tests and bundle","Studio tests","Safety and compose contract","Docker deterministic E2E"}
MINIO="quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"
B4_PROOF_SHA="f08e979daba7d4049d5840a71c2aa99d7f3c9f165dc3b60df9e83ee61ddc6246"

def git(repo,*args,raw=False):
    p=subprocess.run(_git_argv(repo,*args),capture_output=True)
    assert p.returncode==0,"SAFE_GIT_LOOKUP_FAILED"
    return p.stdout if raw else p.stdout.decode("utf-8").strip()

def ci_run(raw,jobs,role):
    assert raw["head_sha"]==MAIN and raw["name"]=="Video Factory V2 CI"
    assert raw["path"]==".github/workflows/ci.yml"
    assert raw["status"]=="completed" and raw["conclusion"]=="success"
    assert len(jobs)==5 and {j["name"] for j in jobs}==JOBS
    assert all(j["head_sha"]==MAIN and j["status"]=="completed" and j["conclusion"]=="success" for j in jobs)
    return ProviderCiRunEvidence.model_validate({
      "role":role,"workflow_name":raw["name"],"run_id":raw["id"],"commit_sha":raw["head_sha"],
      "status":raw["status"],"conclusion":raw["conclusion"],"jobs_total":5,"jobs_succeeded":5,
      "completed_at_utc":raw["updated_at"]}).model_dump(mode="json")

def audit(repo,second,metadata,b4proof,after_tag=False):
    assert git(repo,"rev-parse","HEAD")==git(second,"rev-parse","HEAD")==MAIN
    assert not git(repo,"status","--porcelain") and not git(second,"status","--porcelain")
    assert metadata["remote_main"]==MAIN
    assert metadata["main_ci"]["id"]==34869652973
    assert metadata["main_ci"]["head_branch"]=="main" and metadata["main_ci"]["event"]=="push"
    normalized=ci_run(metadata["main_ci"],metadata["main_jobs"],"governance_main")
    prior=b4proof.read_bytes()
    assert hashlib.sha256(prior).hexdigest()==B4_PROOF_SHA
    proof=json.loads(prior)
    assert proof["main_sha"]==MAIN and proof["main_provenance"]==proof["verdict"]=="PASS"
    assert proof["approved_head"]=="40d8de37e8fb4294a478422ed4f5f546e815ef55"
    objects={name:git(repo,"rev-parse",MAIN+":"+name) for name in EXECUTABLE_TREE_PATHS}
    objects2={name:git(second,"rev-parse",MAIN+":"+name) for name in EXECUTABLE_TREE_PATHS}
    first,second_hash=executable_tree_sha256(objects),executable_tree_sha256(objects2)
    assert first==second_hash==TREE
    assert objects==objects2==proof["canonical_input_local"]==proof["canonical_input_github"]
    assert objects==metadata["remote_executable_objects"]
    assert git(repo,"rev-parse",MAIN+"^{tree}")==git(repo,"rev-parse",proof["approved_head"]+"^{tree}")
    assert git(repo,"rev-parse","vf-v3-01-rc18^{}")==RC18
    assert git(repo,"rev-parse","vf-v3-01-rc18")==TAG18
    assert metadata["remote_rc18_commit"]==RC18 and metadata["remote_rc18_object"]==TAG18
    assert metadata["remote_rc17_commit"]=="d08ffc005d7f3ad517d355977b0bc3cc8d686906"
    assert metadata["remote_rc17_object"]=="ea67843635dddf94ee25d38111fc06782ad9fd74"
    assert git(repo,"rev-parse","vf-v3-01-rc17^{}")==metadata["remote_rc17_commit"]
    assert git(repo,"rev-parse","vf-v3-01-rc17")==metadata["remote_rc17_object"]
    remote_numbers=sorted(int(re.fullmatch(r"refs/tags/vf-v3-01-rc([1-9][0-9]*)",r).group(1)) for r in metadata["remote_refs"] if re.fullmatch(r"refs/tags/vf-v3-01-rc([1-9][0-9]*)",r))
    local_numbers=sorted(int(t.rsplit("rc",1)[1]) for t in git(repo,"tag","--list","vf-v3-01-rc*").splitlines())
    assert local_numbers==remote_numbers==list(range(1,20 if after_tag else 19))
    if after_tag:
        assert git(repo,"rev-parse",RC+"^{}")==MAIN
        assert git(repo,"cat-file","-t",RC)=="tag"
        assert metadata["remote_refs"]["refs/tags/"+RC+"^{}"]==MAIN
        assert git(repo,"rev-parse",RC)==metadata["remote_refs"]["refs/tags/"+RC]
    else:
        assert max(remote_numbers)+1==19
        assert "refs/tags/"+RC not in metadata["remote_refs"]
    paths=[
      "apps/api/app/provider_runtime_bootstrap.py","apps/api/app/provider_ci_provenance.py",
      "apps/api/app/provider_safety.py","apps/api/app/provider_safety_durable.py","apps/api/app/provider_safety_repository.py",
      "apps/api/app/provider_safety_db.py","apps/api/app/provider_gate_loader.py",
      "apps/api/app/asr_prompt_profile.py","apps/api/app/openai_transcription_provider.py",
      "apps/api/app/auto_edit_models.py","apps/api/app/evidence_serialization.py",
      "apps/api/migrations/versions/0014_v3_01_27_acceptance_lineage_identity.py",
      "docs/acceptance/v3-01/contracts/V3-01-27-ACCEPTANCE-LINEAGE-IDENTITY.v2.json",
      "docs/acceptance/v3-01/contracts/V3-01-25-W1-PROMPT-PROFILE.v1.json",
      "docs/acceptance/v3-01/assets/g03-asr-vi-owned-01.wav","docs/acceptance/v3-01/assets/g03-asr-vi-owned-02.wav",
      "docs/acceptance/v3-01/transcripts/g03-asr-vi-owned-01.txt","docs/acceptance/v3-01/transcripts/g03-asr-vi-owned-02.txt",
      "docs/acceptance/v3-01/rights/V3-01-RIGHTS-ASR-001.json","docs/acceptance/v3-01/rights/V3-01-RIGHTS-ASR-002.json",
      "scripts/v3_01_acceptance.py","docker-compose.yml"]
    components={}
    for name in paths:
        raw=git(repo,"show",MAIN+":"+name,raw=True)
        components[name]={"git_object":git(repo,"rev-parse",MAIN+":"+name),"git_blob_bytes_sha256":hashlib.sha256(raw).hexdigest()}
    import app.provider_runtime_bootstrap as bootstrap
    assert Path(bootstrap.__file__).resolve()==(repo/"apps/api/app/provider_runtime_bootstrap.py").resolve()
    assert git(repo,"hash-object","--path","apps/api/app/provider_runtime_bootstrap.py",str(Path(bootstrap.__file__).resolve()))==components["apps/api/app/provider_runtime_bootstrap.py"]["git_object"]
    assert MINIO in git(repo,"show",MAIN+":docker-compose.yml")
    profile=w1_prompt_profile()
    profile_hash=prompt_profile_sha256(profile)
    assert profile_hash=="9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1"
    assert profile.prompt_sha256=="6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48"
    defaults=dict(line.split("=",1) for line in git(repo,"show",MAIN+":.env.example").splitlines() if "=" in line and not line.startswith("#"))
    for name,wanted in {"PROVIDER_GLOBAL_KILL_SWITCH_ENGAGED":"true","PROVIDER_EXTERNAL_EXECUTION_ENABLED":"false",
      "PROVIDER_PAID_EXECUTION_ENABLED":"false","PROVIDER_PER_OPERATION_LIMIT_VND":"0","PROVIDER_DAILY_LIMIT_VND":"0",
      "TRANSCRIPTION_PROVIDER":"fixture","OPENAI_TRANSCRIPTION_MODEL":""}.items():
        assert defaults[name]==wanted,name
    # A pure naming preview only: does NOT call derive_rc_bound_operation_key, construct a binding, or connect.
    lineage=derive_acceptance_lineage_id(rc_tag=RC,rc_commit=MAIN,provider_key="openai-transcription",model="whisper-1",capability="asr",sequence=1)
    validate_acceptance_lineage_id(lineage,rc_tag=RC,rc_commit=MAIN,provider_key="openai-transcription",model="whisper-1",capability="asr",sequence=1)
    future_db=ledger_database_name(RC,lineage)
    assert future_db!="vf_vf_v3_01_rc18_466d54d9ede1b6f7f3179ddd52b7e251" and len(future_db)<=63
    return {"task_id":"VF-V0S-B5","phase":"POST_TAG_SOURCE" if after_tag else "PRE_TAG_PREFLIGHT",
      "verdict":"PASS","main_sha":MAIN,"main_provenance":"PASS","main_ci":normalized,
      "rc_sequencing":{"remote_valid_rc_numbers":remote_numbers,"local_valid_rc_numbers":local_numbers,
        "next_verified_before_tag":"vf-v3-01-rc19","rule":"max valid immutable RC number + 1",
        "prior_contract_evidence":"evidence/v3-01/vf-v0h-20260913T071310Z-rc18-materialization/pre-tag-preflight.json"},
      "canonical_executable_tree_sha256":TREE,"recompute_1":first,"recompute_2":second_hash,
      "canonical_git_objects":objects,"component_bindings":components,"bootstrap":"PRESENT_EXACT_IMPORTED_SOURCE",
      "main_full_git_tree":git(repo,"rev-parse",MAIN+"^{tree}"),"source_mutation":"NONE",
      "w1_profile_id":profile.profile_id,"w1_profile_sha256":profile_hash,"prompt_sha256":profile.prompt_sha256,
      "minio_image":MINIO,"acceptance_lineage_contract_version":2,"provenance_schema_version":1,
      "ledger_naming_preview":{"status":"PLAN_ONLY_NOT_CREATED_OR_APPROVED","sequence_assumption":1,
        "acceptance_lineage_id_preview":lineage,"expected_database_name":future_db,
        "namespace":"database-isolated/public schema; instance/socket/system ID/OID/role must be pinned later",
        "actual_instance_binding":"NOT_CREATED","operation_id_generated":False},
      "rc18_status":"IMMUTABLE_HISTORICAL","old_authority_reused":False,
      "operation_1_rebind_required":True,"fresh_authority_required":True,"fresh_execution_window_required":True,
      "fresh_ledger_binding_required":True,"kill_switch":"ENGAGED","bundle_mounted":False,
      "provider_credential_reads":0,"real_provider_calls":0,"ledger_runtime_writes":0,"budget_reserved_vnd":"0",
      "production_business_writes":0,"actual_provider_cost_vnd":"0",
      "dual_ci_limitation":"Existing canonical contract requires distinct governance main commit and nonempty allowlisted diff; tag/current main equality cannot satisfy it."}

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo",type=Path,required=True);ap.add_argument("--second-clean-repo",type=Path,required=True)
    ap.add_argument("--metadata",type=Path,required=True);ap.add_argument("--b4proof",type=Path,required=True)
    ap.add_argument("--after-tag",action="store_true")
    args=ap.parse_args()
    print(json.dumps(audit(args.repo.resolve(),args.second_clean_repo.resolve(),json.loads(args.metadata.read_text()),args.b4proof,args.after_tag),ensure_ascii=False,sort_keys=True,indent=2))
