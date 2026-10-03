"""Real local audio + EXISTING storyboard/timeline/production/QC dev proof.

The existing synthetic-media SQLite harness supplies isolated repositories,
never production state or authority. Cached audio below is real VieNeu output,
not a successful-response fixture. No model/voice is automatically accepted.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/"apps/api"),str(REPO/"apps/api/tests")]
from app.content_service import canonical_bytes, prepare_document
from app.content_models import ContentDocument, ContentSaveRequest
from app.production_audio import AudioMixEngine, _read_pcm16, _trim_activity
from app.production_models import MixConfig, ProductionPackageCreateRequest, RenderCreateRequest
from app.production_service import ProductionRenderProcessor, RemotionTimelineRenderEngine
from app.production_logic import TimelineRenderContractValidator
from app.production_qc import FullProductionQC
from app.narration_pacing import reflow_snapshot
from app.providers import VoiceResult
from app.vieneu_contracts import VieNeuTTSProfile, VieNeuLicenseProvenance, VOICE_IDS
from app.vieneu_tts_provider import VieNeuTTSProvider
from test_mvp1_multi_input import env as isolated_env, image, timeline


def sha(path):
    with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


async def run(args):
    git=(shutil.which("git.exe") if str(REPO).startswith("/mnt/") else None) or "git"
    commit=subprocess.check_output([git,"rev-parse","HEAD"],cwd=REPO,text=True).strip()
    if subprocess.check_output([git,"status","--porcelain"],cwd=REPO,text=True).strip():
        raise ValueError("clean committed source required for audition")
    if args.output.exists():raise ValueError("fresh audition directory required")
    args.output.mkdir(parents=True,mode=0o700)
    script_path=REPO/"docs/acceptance/mvp1/vieneu-tts-01/AUDITION_SCRIPT.txt"
    script=script_path.read_text(encoding="utf-8")
    shutil.copyfile(script_path,args.output/"AUDITION_SCRIPT.txt")
    counts=[]
    for number,voice in enumerate(VOICE_IDS,1):
        root=args.output/f"voice-{number}"
        root.mkdir(mode=0o700)
        generator=isolated_env.__wrapped__(root)
        env=await anext(generator)
        try:
            await env.platform.seed_providers([{"provider_key":"vieneu-tts","display_name":"VieNeu local audition",
                "capability":"tts","adapter":"vieneu-local","routing_mode":"primary","status":"healthy",
                "enabled":True,"supports_dry_run":True,"metadata":{"paid":False,"dev_only":True}}])
            asset=await image(env)
            doc=prepare_document(ContentDocument(input_kind="script",original_text=script,
                protected_terms=["Ngọc Phương Đông","Vinhomes Green Paradise Cần Giờ","Vinhomes Saigon Park","chính sách bán hàng"]))
            for scene in doc.scenes:
                scene.asset_id=asset.asset_id;scene.media_strategy="user_asset"
                scene.pause_after_seconds=.25
            # Synthetic harness editorial approval ONLY, not voice/production acceptance.
            version=await env.content.save(env.project.project_id,ContentSaveRequest(document=doc.model_copy(update={"approved":True})))
            built=await timeline(env,version)
            plan=built.snapshot.metadata["narration_plan"]
            provider=VieNeuTTSProvider(VieNeuTTSProfile(voice_id=voice,rights=VieNeuLicenseProvenance()),local_execution_enabled=True)
            audio=AudioMixEngine(ffmpeg_path=args.ffmpeg)
            outputs={};timing=[]
            for index,unit in enumerate(plan["units"]):
                result=await provider.synthesize(text=unit["text"],language="vi",output_path=root/f"raw-unit-{index:03d}.wav")
                normalized=root/f"decoded-unit-{index:03d}.wav"
                await audio._normalize_chunk(result.path,normalized,speed=1)
                frames,rate=_read_pcm16(normalized)
                measured=len(_trim_activity(frames))/rate
                timing.append({"text_sha256":unit["text_sha256"],"rendered_audio_duration_seconds":measured,
                    "audio_duration_source":"decoded_pcm_sample_count","applied_timing_speedup":1})
                outputs[unit["text"]]=result
            observation={"plan_sha256":hashlib.sha256(canonical_bytes(plan)).hexdigest(),"timing":timing}
            changed=await env.timeline.commit_mutation(project_id=env.project.project_id,expected_version=1,
                snapshot=reflow_snapshot(built.snapshot,observation),mutation={"type":"measured-narration-reflow"},actor_ref="synthetic-dev")
            class PersistedRealAuditionAudio:
                """Exact local-result replay; no extra inference for the review render."""
                async def synthesize(self,*,text,language,output_path):
                    result=outputs[text]
                    if language!="vi" or result.evidence.text_sha256!=hashlib.sha256(text.encode()).hexdigest() or sha(result.path)!=result.evidence.audio_sha256:
                        raise ValueError("persisted audition identity mismatch")
                    shutil.copyfile(result.path,output_path)
                    return VoiceResult(path=output_path,duration_seconds=result.duration_seconds,
                        provider=result.provider,voice=result.voice,evidence=result.evidence)
            await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
            render=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(
                expected_timeline_version=changed.current_version,expected_subtitle_version=1,expected_audio_version=1))
            processor=ProductionRenderProcessor(repository=env.production,platform=env.platform,asset_repository=env.assets,
                object_storage=env.storage,renderer=RemotionTimelineRenderEngine(renderer_url="http://127.0.0.1:3017",timeout_seconds=600),
                qc=FullProductionQC(ffmpeg_path=args.ffmpeg,ffprobe_path=args.ffprobe),tts_provider=PersistedRealAuditionAudio(),
                audio_engine=audio,manifest_validator=TimelineRenderContractValidator(REPO/"packages/contracts/timeline-render.schema.json"),
                staging_root=root/"renders",brand_name="Local voice audition — not production acceptance")
            done=await processor.process(render.render_id)
            (root/"render.json").write_bytes(canonical_bytes(done.model_dump(mode="json")))
            (root/"storyboard.json").write_bytes(canonical_bytes(version.model_dump(mode="json")))
            (root/"timeline.json").write_bytes(canonical_bytes(changed.model_dump(mode="json")))
            if done.status!="awaiting_review" or done.qc_status!="passed":
                raise ValueError("audition review render failed: "+str(done.failure_reason))
            assets=await env.platform.list_assets(env.project.project_id)
            movie_asset=next(a for a in assets if a.asset_id==done.output_asset_id)
            movie=root/"review.mp4";shutil.copyfile(root/"objects"/movie_asset.object_key,movie)
            narration=done.manifest["supporting_asset_ids"]["narration-track"]
            narration_asset=next(a for a in assets if a.asset_id==narration)
            shutil.copyfile(root/"objects"/narration_asset.object_key,root/"audition.wav")
            subprocess.run([args.ffmpeg,"-hide_banner","-v","error","-i",str(movie),"-f","null","-"],check=True)
            report={"provider":"vieneu-tts","voice":voice,"source_commit":commit,
                "profile":provider.profile.model_dump(mode="json"),"profile_sha256":provider.profile.sha256,
                "script_sha256":hashlib.sha256(script.encode()).hexdigest(),"review_mp4_sha256":sha(movie),
                "audition_audio_sha256":sha(root/"audition.wav"),"local_service_requests":len(outputs),
                "qc":done.qc_report,"timing_source":"ESTIMATED_SEGMENT","word_alignment":"WORD_ALIGNMENT_OPEN",
                "human_quality_accepted":False,"external_provider_calls":0,"provider_credential_reads":0,
                "cached_real_results_used_by_review":True,"fixture_audio_used":False,
                "rights":"self-authored audition narration and image; Apache-2.0 pinned preset assets"}
            (root/"metadata.json").write_bytes(canonical_bytes(report))
            counts.append(report)
            print(json.dumps({"voice":voice,"review":str(movie),"qc":done.qc_status},ensure_ascii=False),flush=True)
        finally:
            await generator.aclose()
    (args.output/"RUN_REPORT.json").write_bytes(canonical_bytes({"source_commit":commit,"voices":counts,
        "human_acceptance":"NOT_RUN","openai_comparator":"NOT_RUN / SEPARATE_AUTHORITY_REQUIRED",
        "provider_credentials_read":0,"external_provider_calls":0,"out_of_pocket_spend_vnd":0,"production_writes":0}))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--ffmpeg",required=True)
    parser.add_argument("--ffprobe",required=True)
    asyncio.run(run(parser.parse_args()))
