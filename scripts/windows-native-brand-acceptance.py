"""Actual template renders using explicit reference fixtures and accepted speech."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid

REPO=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(REPO))
from services.windows_native.contracts import file_sha, digest
from services.windows_native.hardening import Artifacts, durable_json
from services.windows_native.pipeline import Config, Pipeline
from services.windows_native.server import Runner
from services.windows_native.store import Store


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--data-root",type=Path,required=True); parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args(); config=Config(data_root=args.data_root.resolve()); config.validate_data_root()
    if config.data_root.exists() or args.report.exists(): raise ValueError("FRESH_BRAND_ACCEPTANCE_ROOT_REQUIRED")
    root=Path(r"C:\NPD-Video-Factory\post-mvp-validation\phase5-editor-20261005")
    reference=Store(root).get("ea61e12275614826bf654cfdfafd5550")["document"]
    store=Store(config.data_root)
    for folder in ("assets","originals"): shutil.copytree(root/folder,config.data_root/folder)
    source=Path(r"C:\NPD-Video-Factory\outputs\MVP1")
    receipt=json.loads((source/"owner-final-video-approval.json").read_bytes())
    assert file_sha(source/"voice.wav")==receipt["voice_sha256"]
    proposal=json.loads((source/"content-proposal.json").read_bytes())
    timing=Path(r"C:\NPD-Video-Factory\phase2-validation\single-media-regression\voice.json")
    results=[]
    for brand_id,template_id in [("ngoc-phuong-dong","property-30"),("vang-nguyen","personal-45"),("ngoc-phuong-dong","news-60"),("vang-nguyen","event-30")]:
        p=store.create(f"Brand reference {brand_id} {template_id}","Accepted speech; reference media; no new provider")
        p=store.save(p["id"],1,proposal=proposal)
        for asset in reference["assets"]: p=store.append_media(p["id"],p["revision"],asset)
        p=store.set_music(p["id"],p["revision"],reference["music"])
        p=store.auto_plan(p["id"],p["revision"]); p=store.set_brand(p["id"],p["revision"],brand_id,template_id)
        p=store.approve(p["id"],p["revision"],"INTEGRATION FIXTURE — NOT OWNER ACCEPTANCE",True)
        identity=digest(p["document"])
        job=store.enqueue(p["id"],p["revision"],"render","brand-fixture-"+uuid.uuid4().hex)
        out=config.data_root/"jobs"/job["id"]; out.mkdir(parents=True); artifacts=Artifacts(out,job)
        wav=artifacts.publish(source/"voice.wav","voice.wav"); meta=artifacts.publish(timing,"voice.json")
        artifacts.commit("tts",[wav,meta],{"explicit_fixture":True,"reused_existing_real_accepted_WAV":True,"new_inference":False})
        Runner(store,Pipeline(config)).run_one(); current=store.get_job(job["id"])
        assert current["status"]=="succeeded",current
        manifest=json.loads((out/"render-manifest.json").read_bytes())
        target=p["document"]["brand_template"]["template"]["duration_seconds"]
        assert abs(current["result"]["qc"]["duration_seconds"]-target)<.12
        assert current["result"]["qc"]["passed"] and Artifacts(out,job).load("render")
        assert manifest["brand_template"]==p["document"]["brand_template"] and manifest["voice_speed"]==1
        assert file_sha(out/"voice.wav")==receipt["voice_sha256"] and not manifest["official_brand_assets_claimed"]
        assert digest(Store(config.data_root).get(p["id"])["document"])==identity
        results.append({"project_id":p["id"],"job_id":job["id"],"brand_id":brand_id,"template_id":template_id,"target_duration":target,
            "final_mp4":str(out/"final.mp4"),"qc":current["result"]["qc"],"brand_sha256":p["document"]["brand_template"]["brand_sha256"],
            "template_sha256":p["document"]["brand_template"]["template_sha256"],"source_voice_sha256":receipt["voice_sha256"],"voice_speed":1,
            "cta_hold_after_voice_seconds":manifest["cta_hold_after_voice_seconds"],"human_final_accepted":False})
        print(json.dumps({"completed":len(results),"template":template_id,"qc":"PASS"}),flush=True)
    report={"status":"PASS","scope":"technical brand/template/reference renders; fixture approvals, not human production acceptance","data_root":str(config.data_root),"outputs":results,
        "actual_durations":[30,45,60],"actual_purposes":["property","personal","news","event"],"new_provider_calls":0,"new_tts_inferences":0,
        "official_logos_or_assets_fabricated":False,"human_final_accepted":False}
    args.report.parent.mkdir(parents=True,exist_ok=True); durable_json(args.report,report)
    print(json.dumps({"status":"PASS","report":str(args.report)}),flush=True)


if __name__=="__main__": main()
