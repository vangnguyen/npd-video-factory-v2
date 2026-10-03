"""Isolated real-input review/final driver, reusing the existing MI-04 pipeline.

No provider credentials, ASR or production host. Finals require an explicit
artifact-bound Owner review file; selecting a voice is not reviewing a movie.
Input manifests and project media stay outside the public source repository.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "apps/api"), str(REPO / "apps/api/tests")]
from app.content_models import ContentDocument, ContentSaveRequest
from app.content_service import canonical_bytes, prepare_document
from app.production_audio import AudioMixEngine, _read_pcm16, _trim_activity
from app.production_models import (ProductionPackageCreateRequest, RenderCreateRequest,
    ApprovalRequest, ApprovalDecisionRequest, FinalRenderCreateRequest)
from app.production_service import (ProductionRenderProcessor, RemotionTimelineRenderEngine,
    ProductionPackageService)
from app.production_logic import TimelineRenderContractValidator
from app.production_qc import FullProductionQC
from app.narration_pacing import reflow_snapshot
from app.providers import VoiceResult
from app.vieneu_contracts import selected_vieneu_profile, VieNeuVoiceSelection
from app.vieneu_tts_provider import VieNeuTTSProvider
from app.tts_evidence import TTSArtifactEvidence
from app.platform_models import AssetRegister
from app.media_validation import sniff_media
from app.auto_edit_providers import FFprobeMediaProbe, FFmpegMediaSignalProvider
from app.auto_edit_service import AutoEditAnalysisService
from app.auto_edit_models import AutoEditAnalysisRequest
from test_mvp1_multi_input import env as isolated_env, timeline, Queue

PROTECTED = ["Ngọc Phương Đông", "Vinhomes Green Paradise Cần Giờ", "Vinhomes Saigon Park",
    "chính sách bán hàng", "thanh toán sớm", "chiết khấu", "phối cảnh", "sa bàn"]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_bound_file(item, parent, *, max_bytes):
    """Only local, declared files; no URLs, shell evaluation or implicit rights."""
    if set(item) != {"path", "sha256", "permission_reference"} or not item["permission_reference"]:
        raise ValueError("EXPLICIT_INPUT_PERMISSION_REQUIRED")
    path = Path(item["path"])
    path = path if path.is_absolute() else parent / path
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("INPUT_CUSTODY_OR_SIZE_INVALID")
    if sha(path) != item["sha256"]:
        raise ValueError("INPUT_HASH_MISMATCH")
    return path


def load_inputs(path):
    doc = json.loads(path.read_bytes())
    if set(doc) != {"cases"} or len(doc["cases"]) != 3:
        raise ValueError("THREE_REPRESENTATIVE_CASES_REQUIRED")
    if [c["case"] for c in doc["cases"]] != ["image_script", "script_only", "mixed_no_audio"]:
        raise ValueError("CASE_ORDER_INVALID")
    for case in doc["cases"]:
        if set(case) != {"case", "script", "image", "video", "script_approval_reference"}:
            raise ValueError("INPUT_FIELDS_INVALID")
        if not isinstance(case["script_approval_reference"], str) or not case["script_approval_reference"].strip():
            raise ValueError("EXPLICIT_SCRIPT_REVIEW_REQUIRED")
        read_bound_file(case["script"], path.parent, max_bytes=80000)
        if bool(case["image"]) != (case["case"] != "script_only"):
            raise ValueError("IMAGE_CASE_MISMATCH")
        if bool(case["video"]) != (case["case"] == "mixed_no_audio"):
            raise ValueError("VIDEO_CASE_MISMATCH")
        for kind in ("image", "video"):
            if case[kind]:
                read_bound_file(case[kind], path.parent, max_bytes=100000000)
    return doc


@asynccontextmanager
async def environment(root, *, reopen):
    if not reopen:
        generator = isolated_env.__wrapped__(root)
        env = await anext(generator)
        (root / "identity.json").write_bytes(canonical_bytes({
            "workspace_id": env.workspace.workspace_id, "project_id": env.project.project_id}))
        try:
            yield env
        finally:
            await generator.aclose()
        return
    from app.db import create_engine, create_session_factory
    from app.repositories import PlatformRepository
    from app.auto_edit_repository import AutoEditRepository
    from app.timeline_repository import TimelineRepository
    from app.production_repository import ProductionRepository
    from app.object_storage import LocalObjectStorageProvider
    identity = json.loads((root / "identity.json").read_bytes())
    engine = create_engine(f"sqlite+aiosqlite:///{root}/dev.db")
    factory = create_session_factory(engine)
    platform = PlatformRepository(factory)
    assets, timelines, production = AutoEditRepository(factory), TimelineRepository(factory), ProductionRepository(factory)
    storage = LocalObjectStorageProvider(root / "objects")
    env = SimpleNamespace(engine=engine, platform=platform, assets=assets, timeline=timelines,
        production=production, storage=storage, project=await platform.get_project(identity["project_id"]), tmp=root)
    env.package = ProductionPackageService(repository=production, timeline_repository=timelines,
        asset_repository=assets, queue=Queue(), settings=SimpleNamespace(audio_tts_provider="vieneu",
            vieneu_voice_id="Thùy Dung", vieneu_local_execution_enabled=True))
    try:
        yield env
    finally:
        await engine.dispose()


async def add_media(env, item, parent, kind, args):
    path = read_bound_file(item, parent, max_bytes=100000000)
    content_type = "video/mp4" if kind == "video" else ("image/png" if path.suffix.lower() == ".png" else "image/jpeg")
    detected_kind, mime = sniff_media(path, content_type)
    if detected_kind != kind:
        raise ValueError("INPUT_MEDIA_KIND_MISMATCH")
    metadata = await FFprobeMediaProbe(args.ffprobe).probe(path, detected_content_type=mime, media_kind=kind)
    if kind == "video" and metadata.audio_codec is not None:
        raise ValueError("SPOKEN_VIDEO_ASR_REQUIRED_NO_MUTING_ALLOWED")
    stored = await env.storage.put_file(object_key=f"projects/{env.project.project_id}/inputs/{item['sha256']}{path.suffix}",
        path=path, content_type=mime)
    asset = await env.platform.register_asset(env.project.project_id, AssetRegister(asset_class="source",
        kind=kind, filename=path.name, object_key=stored.object_key, content_type=mime,
        size_bytes=stored.size_bytes, checksum_sha256=stored.checksum_sha256, storage_provider="local",
        provenance={"rights_status":"licensed", "rights_basis":"Owner-declared bounded internal review permission",
            "permission_reference":item["permission_reference"], "media_metadata":metadata.model_dump(mode="json")}))
    if kind == "image":
        return asset, None
    poison = AsyncMock(side_effect=AssertionError("ASR/resolver/budget forbidden in selected TTS review"))
    analysis = await AutoEditAnalysisService(repository=env.assets, platform=env.platform, object_storage=env.storage,
        transcription_provider=SimpleNamespace(key="contract", model="none", transcribe=poison),
        provider_safety=SimpleNamespace(execute=poison), signal_provider=FFmpegMediaSignalProvider(args.ffmpeg),
        staging_root=env.tmp / "analysis").analyze(env.project.project_id, AutoEditAnalysisRequest(asset_id=asset.asset_id))
    poison.assert_not_called()
    if analysis.status != "succeeded" or analysis.transcript is not None or analysis.provenance.get("asr_state") != "no_audio_stream":
        raise ValueError("NO_AUDIO_ANALYSIS_NOT_PROVEN")
    return asset, analysis


class ExactLocalAudio:
    def __init__(self, outputs):
        self.outputs = outputs

    async def synthesize(self, *, text, language, output_path):
        result = self.outputs[text]
        if language != "vi" or result.evidence.text_sha256 != hashlib.sha256(text.encode()).hexdigest() or sha(result.path) != result.evidence.audio_sha256:
            raise ValueError("PERSISTED_SELECTED_AUDIO_MISMATCH")
        shutil.copyfile(result.path, output_path)
        return VoiceResult(path=output_path, duration_seconds=result.duration_seconds,
            provider=result.provider, voice=result.voice, evidence=result.evidence)


def processor(env, outputs, args):
    return ProductionRenderProcessor(repository=env.production, platform=env.platform, asset_repository=env.assets,
        object_storage=env.storage, renderer=RemotionTimelineRenderEngine(renderer_url="http://127.0.0.1:3017", timeout_seconds=600),
        qc=FullProductionQC(ffmpeg_path=args.ffmpeg, ffprobe_path=args.ffprobe), tts_provider=ExactLocalAudio(outputs),
        audio_engine=AudioMixEngine(ffmpeg_path=args.ffmpeg),
        manifest_validator=TimelineRenderContractValidator(REPO / "packages/contracts/timeline-render.schema.json"),
        staging_root=env.tmp / "renders", brand_name="Internal real-input review — not published")


async def export_render(env, done, target, args):
    if done.qc_status != "passed" or done.status not in {"awaiting_review", "ready"}:
        raise ValueError("SELECTED_RENDER_QC_FAILED: " + str(done.failure_reason))
    assets = await env.platform.list_assets(env.project.project_id)
    asset = next(a for a in assets if a.asset_id == done.output_asset_id)
    if target.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    shutil.copyfile(env.tmp / "objects" / asset.object_key, target)
    subprocess.run([args.ffmpeg, "-hide_banner", "-v", "error", "-i", str(target), "-f", "null", "-"], check=True)
    return sha(target)


async def review_case(args, case, root, commit):
    root.mkdir(mode=0o700)
    async with environment(root, reopen=False) as env:
        await env.platform.seed_providers([{"provider_key":"vieneu-tts", "display_name":"Selected Thùy Dung local",
            "capability":"tts", "adapter":"vieneu-local", "routing_mode":"primary", "status":"healthy",
            "enabled":True, "supports_dry_run":True, "metadata":{"paid":False, "dev_only":True}}])
        env.package.settings = SimpleNamespace(audio_tts_provider="vieneu", vieneu_voice_id="Thùy Dung", vieneu_local_execution_enabled=True)
        script_path = read_bound_file(case["script"], args.inputs.parent, max_bytes=80000)
        script = script_path.read_bytes().decode("utf-8")
        shutil.copyfile(script_path, root / "original-script.txt")
        document = prepare_document(ContentDocument(input_kind="script", original_text=script, protected_terms=PROTECTED))
        photo = (await add_media(env, case["image"], args.inputs.parent, "image", args))[0] if case["image"] else None
        video, analysis = await add_media(env, case["video"], args.inputs.parent, "video", args) if case["video"] else (None, None)
        if video and len(document.scenes) < 2:
            raise ValueError("MIXED_REVIEW_NEEDS_AT_LEAST_TWO_SCENES")
        for index, scene in enumerate(document.scenes):
            scene.pause_after_seconds = .25
            if photo:
                scene.asset_id = photo.asset_id
                scene.media_strategy = "user_asset"
            if video and index == 0:
                scene.asset_id, scene.analysis_id = video.asset_id, analysis.analysis_id
                scene.duration_seconds = min(scene.duration_seconds, analysis.source_media.duration_seconds)
        # Verbatim script with explicit editorial approval reference; not voice-quality acceptance.
        version = await env.content.save(env.project.project_id, ContentSaveRequest(document=document.model_copy(update={"approved":True})))
        built = await timeline(env, version, "mixed" if video else "storyboard_media")
        plan = built.snapshot.metadata["narration_plan"]
        if " ".join(script.split()) != " ".join(" ".join(u["text"].split()) for u in plan["units"]):
            raise ValueError("NARRATION_SOURCE_COVERAGE_MISMATCH")
        provider = VieNeuTTSProvider(selected_vieneu_profile(), local_execution_enabled=True, selected_voice_only=True)
        audio, outputs, timing = AudioMixEngine(ffmpeg_path=args.ffmpeg), {}, []
        for index, unit in enumerate(plan["units"]):
            result = outputs.get(unit["text"])
            if result is None:
                result = await provider.synthesize(text=unit["text"], language="vi", output_path=root / f"raw-unit-{index:03d}.wav")
            normalized = root / f"decoded-unit-{index:03d}.wav"
            await audio._normalize_chunk(result.path, normalized, speed=1)
            frames, rate = _read_pcm16(normalized)
            timing.append({"text_sha256":unit["text_sha256"], "rendered_audio_duration_seconds":len(_trim_activity(frames))/rate,
                "audio_duration_source":"decoded_pcm_sample_count", "applied_timing_speedup":1})
            outputs[unit["text"]] = result
        changed = await env.timeline.commit_mutation(project_id=env.project.project_id, expected_version=1,
            snapshot=reflow_snapshot(built.snapshot, {"plan_sha256":hashlib.sha256(canonical_bytes(plan)).hexdigest(), "timing":timing}),
            mutation={"type":"decoded-selected-narration-reflow"}, actor_ref="isolated-real-input-review")
        await env.package.create_or_refresh(env.project.project_id, ProductionPackageCreateRequest())
        render = await env.package.enqueue_review(env.project.project_id, RenderCreateRequest(
            expected_timeline_version=changed.current_version, expected_subtitle_version=1, expected_audio_version=1))
        done = await processor(env, outputs, args).process(render.render_id)
        movie_sha = await export_render(env, done, root / "review.mp4", args)
        assets = await env.platform.list_assets(env.project.project_id)
        narration = next(a for a in assets if a.asset_id == done.manifest["supporting_asset_ids"]["narration-track"])
        shutil.copyfile(root / "objects" / narration.object_key, root / "narration.wav")
        narration_frames, narration_rate = _read_pcm16(root / "narration.wav")
        for name, value in [("render", done), ("storyboard", version), ("timeline", changed)]:
            (root / f"{name}.json").write_bytes(canonical_bytes(value.model_dump(mode="json")))
        metadata = {"case":case["case"], "source_commit":commit, "source_inputs":case,
            "profile":provider.profile.model_dump(mode="json"), "profile_sha256":provider.profile.sha256,
            "selection":VieNeuVoiceSelection().model_dump(mode="json"), "review_sha256":movie_sha,
            "original_script_file_sha256":sha(script_path), "source_text_sha256":hashlib.sha256(script.encode()).hexdigest(),
            "audio_sha256":sha(root / "narration.wav"), "qc":done.qc_report, "review_render_id":done.render_id,
            "decoded_actual_duration_seconds":len(narration_frames)/narration_rate,
            "trimmed_speech_duration_seconds":sum(t["rendered_audio_duration_seconds"] for t in timing),
            "timing_source":"ESTIMATED_SEGMENT", "word_alignment":"WORD_ALIGNMENT_OPEN",
            "human_quality_acceptance":"PENDING_EXACT_OUTPUT_REVIEW", "final_status":"NOT_RENDERED_REVIEW_REQUIRED",
            "local_service_requests":len(outputs), "narration_unit_count":len(plan["units"]),
            "external_provider_calls":0, "external_credential_reads":0,
            "production_writes":0, "paid_spend_vnd":0, "local_compute_cost":"NOT_METERED"}
        (root / "metadata.json").write_bytes(canonical_bytes(metadata))
        print(json.dumps({"case":case["case"], "review":str(root / "review.mp4"), "sha256":movie_sha}, ensure_ascii=False), flush=True)


async def finalize_case(args, root, owner_review, commit):
    metadata = json.loads((root / "metadata.json").read_bytes())
    if metadata["source_commit"] != commit or sha(root / "review.mp4") != metadata["review_sha256"]:
        raise ValueError("REVIEW_SOURCE_OR_BYTES_CHANGED")
    if owner_review != {"review_sha256":metadata["review_sha256"], "decision":"APPROVED_FOR_FINAL_RENDER", "reviewer":"Owner"}:
        raise ValueError("EXACT_OWNER_REVIEW_REQUIRED")
    outputs = {}
    for path in sorted(root.glob("raw-unit-*.wav")):
        evidence = TTSArtifactEvidence.model_validate_json(path.with_suffix(".wav.vieneu.json").read_bytes())
        if evidence.profile_sha256 != selected_vieneu_profile().sha256:
            raise ValueError("FINAL_SELECTED_PROFILE_MISMATCH")
        outputs[evidence.timing.reference_text] = VoiceResult(path=path, duration_seconds=evidence.decoded_duration_seconds,
            provider="vieneu-tts", voice="Thùy Dung", evidence=evidence)
    async with environment(root, reopen=True) as env:
        review = await env.package.get_render(env.project.project_id, metadata["review_render_id"])
        approval = await env.package.request_approval(env.project.project_id, ApprovalRequest(review_render_id=review.render_id,
            requester_ref="Owner", note="Exact artifact-bound review; not deployment/publication authority"))
        approval = await env.package.decide_approval(env.project.project_id, approval.approval_id,
            ApprovalDecisionRequest(decision="approved", reviewer_ref="Owner", comment="Bound to review MP4 SHA " + metadata["review_sha256"]))
        final = await env.package.enqueue_final(env.project.project_id, FinalRenderCreateRequest(
            expected_timeline_version=review.timeline_version, expected_subtitle_version=review.subtitle_version,
            expected_audio_version=review.audio_version, approval_id=approval.approval_id))
        done = await processor(env, outputs, args).process(final.render_id)
        movie_sha = await export_render(env, done, root / "final.mp4", args)
        (root / "final-render.json").write_bytes(canonical_bytes(done.model_dump(mode="json")))
        (root / "owner-review.json").write_bytes(canonical_bytes(owner_review))
        (root / "final-metadata.json").write_bytes(canonical_bytes({"source_commit":commit, "final_sha256":movie_sha,
            "qc":done.qc_report, "approval":approval.model_dump(mode="json"), "human_quality_acceptance":"REQUIRES_FINAL_OUTPUT_REVIEW"}))
        print(json.dumps({"final":str(root / "final.mp4"), "sha256":movie_sha}), flush=True)


async def run(args):
    git = (shutil.which("git.exe") if str(REPO).startswith("/mnt/") else None) or "git"
    commit = subprocess.check_output([git, "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    if subprocess.check_output([git, "status", "--porcelain"], cwd=REPO, text=True).strip():
        raise ValueError("CLEAN_COMMITTED_CANDIDATE_REQUIRED")
    if args.owner_review:
        reviews = json.loads(args.owner_review.read_bytes())
        for case in ("image_script", "script_only", "mixed_no_audio"):
            if case in reviews:
                await finalize_case(args, args.output / case, reviews[case], commit)
        return
    if args.output.exists():
        raise ValueError("FRESH_REVIEW_OUTPUT_REQUIRED")
    inputs = load_inputs(args.inputs)
    args.output.mkdir(mode=0o700, parents=True)
    (args.output / "inputs.json").write_bytes(canonical_bytes(inputs))
    for case in inputs["cases"]:
        await review_case(args, case, args.output / case["case"], commit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--owner-review", type=Path)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    asyncio.run(run(parser.parse_args()))
