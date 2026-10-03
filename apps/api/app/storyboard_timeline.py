"""Deterministic scene/media planning on the existing timeline and asset platform."""
from __future__ import annotations
import hashlib
import struct
import zlib
import tempfile
from pathlib import Path
from .content_models import ContentDocument
from .content_service import ContentService, canonical_bytes
from .platform_models import AssetRegister
from .timeline_models import TimelineClip, TimelineTrack, TimelineSnapshot, TransitionSpec
from .timeline_logic import TimelineEditError


def template_png() -> bytes:
    """First-party abstract title-card background, not an AI image or architectural render."""
    width, height = 270, 480
    rows = b"".join(b"\0" + bytes((12+y//12, 26+y//10, 48+y//8))*width for y in range(height))
    def chunk(name, value):
        return struct.pack(">I", len(value))+name+value+struct.pack(">I", zlib.crc32(name+value)&0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            +chunk(b"IDAT", zlib.compress(rows))+chunk(b"IEND", b""))


async def build_storyboard(service, project, payload):
    version = await service.platform.get_version(payload.content_version_id)
    if version is None or version.project_id != project.project_id or version.workspace_id != project.workspace_id:
        raise KeyError(payload.content_version_id)
    current = await ContentService(service.platform).latest(project.project_id)
    if current is None or current.project_version_id != version.project_version_id:
        raise TimelineEditError("CONTENT_VERSION_STALE")
    document = ContentDocument.model_validate(version.snapshot.get("content", {}))
    if not document.approved:
        raise TimelineEditError("SCRIPT_STORYBOARD_APPROVAL_REQUIRED")
    visuals, subtitles, originals, plan = [], [], [], []
    cursor = 0.0
    video_count = 0
    for index, scene in enumerate(document.scenes):
        if scene.media_strategy in {"ai_image", "ai_video"}:
            raise TimelineEditError(f"MEDIA_PROVIDER_NOT_CONFIGURED: {scene.media_strategy}; plan retained")
        if scene.media_strategy == "motion_graphic":
            if service.object_storage is None:
                raise TimelineEditError("template object storage is unavailable")
            data = template_png()
            digest = hashlib.sha256(data).hexdigest()
            key = f"workspaces/{project.workspace_id}/projects/{project.project_id}/templates/{digest}.png"
            with tempfile.TemporaryDirectory(prefix="vf-template-") as folder:
                path = Path(folder)/"title-card.png"
                path.write_bytes(data)
                stored = await service.object_storage.put_file(object_key=key, path=path, content_type="image/png")
            asset = await service.platform.register_asset(project.project_id, AssetRegister(
                project_version_id=version.project_version_id, asset_class="generated", kind="image",
                filename="title-card.png", object_key=stored.object_key, content_type="image/png",
                size_bytes=stored.size_bytes, checksum_sha256=stored.checksum_sha256,
                storage_provider=stored.storage_provider, provenance={"source_type": "first_party_template",
                    "rights_status": "owned", "license": "NPD deterministic template", "external_call": False,
                    "ai_generated": False, "production_eligible": True}))
        else:
            asset = await service.auto_edit_repository.get_asset(scene.asset_id)
            if asset is None or asset.project_id != project.project_id or asset.workspace_id != project.workspace_id:
                raise TimelineEditError("CROSS_PROJECT_ASSET_OR_MISSING_ASSET")
            rights = asset.provenance.get("rights_status")
            if rights not in {"owned", "licensed", "public_domain", "royalty_free"}:
                raise TimelineEditError("MEDIA_RIGHTS_REQUIRED")
            if asset.provenance.get("production_eligible") is False:
                raise TimelineEditError("PLANNING_FIXTURE_NOT_RENDERABLE")
        is_video = asset.content_type.startswith("video/")
        metadata = {"scene_id": scene.scene_id, "content_type": asset.content_type,
            "source_checksum_sha256": asset.checksum_sha256, "fit": scene.fit,
            "architectural_render": scene.architectural_render, "official_render": scene.official_render,
            "media_strategy": scene.media_strategy, "rights_status": asset.provenance.get("rights_status"),
            "timing_source": "user_scene_display_duration"}
        if is_video:
            video_count += 1
            analysis = await service.auto_edit_repository.get_analysis(scene.analysis_id) if scene.analysis_id else None
            if (analysis is None or analysis.status != "succeeded" or analysis.asset_id != asset.asset_id
                    or analysis.project_id != project.project_id):
                raise TimelineEditError("VIDEO_ANALYSIS_REQUIRED")
            source = analysis.source_media
            if source.audio_codec and (analysis.transcript is None or not analysis.transcript.segments):
                raise TimelineEditError("SPOKEN_VIDEO_ASR_REQUIRED")
            if source.duration_seconds is None or scene.source_start+scene.duration_seconds > source.duration_seconds+0.001:
                raise TimelineEditError("VIDEO_SOURCE_BOUNDS_EXCEEDED")
            metadata["analysis_id"] = analysis.analysis_id
        elif asset.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise TimelineEditError("UNSUPPORTED_STORYBOARD_MEDIA")
        elif scene.analysis_id or scene.source_start:
            raise TimelineEditError("IMAGE_HAS_NO_SOURCE_TIME_WINDOW")
        if scene.architectural_render and is_video:
            raise TimelineEditError("ARCHITECTURAL_RENDER_IS_IMAGE_METADATA")
        if scene.official_render and not asset.provenance.get("official_render_verified"):
            raise TimelineEditError("OFFICIAL_RENDER_PROVENANCE_REQUIRED")
        clip = TimelineClip(clip_id=f"clip_story_{index:04d}", kind="source" if is_video else "image",
            label=scene.visual_brief[:240] or f"Scene {index+1}", asset_id=asset.asset_id,
            source_start=scene.source_start if is_video else 0,
            source_end=scene.source_start+scene.duration_seconds if is_video else None,
            timeline_start=cursor, duration=scene.duration_seconds,
            transition_in=TransitionSpec(kind=scene.transition, duration_seconds=0.25 if scene.transition in {"fade","crossfade"} else 0),
            metadata=metadata)
        visuals.append(clip)
        if is_video and scene.original_audio == "keep" and source.audio_codec:
            originals.append(clip.model_copy(update={"clip_id": f"clip_audio_{index:04d}", "kind": "original_audio"}))
        if scene.narration.strip():
            subtitles.append(TimelineClip(clip_id=f"clip_text_{index:04d}", kind="subtitle", label=scene.narration,
                source_start=0, source_end=scene.duration_seconds, timeline_start=cursor, duration=scene.duration_seconds,
                metadata={"timing_source": "user_scene_cue", "scene_index": index, "measured_word_timestamps": False}))
        plan.append({"scene_id": scene.scene_id, "strategy": scene.media_strategy, "asset_id": asset.asset_id,
                     "asset_sha256": asset.checksum_sha256, "duration_seconds": scene.duration_seconds,
                     "status": "resolved", "ai_video": False, "rights_status": asset.provenance.get("rights_status")})
        cursor = round(cursor+scene.duration_seconds, 6)
    actual_kind = "mixed" if video_count else "storyboard_media"
    if payload.source_kind != actual_kind:
        raise TimelineEditError("TIMELINE_SOURCE_KIND_MISMATCH")
    from .narration_pacing import narration_plan
    return TimelineSnapshot(schema_version="1.1", duration_seconds=cursor, tracks=[
        TimelineTrack(track_id="trk_storyboard", type="video", kind="source", label="Storyboard", order=0, clips=visuals),
        TimelineTrack(track_id="trk_storytext", type="text", kind="subtitles", label="Narration cues (scene timing)", order=1, clips=subtitles),
        TimelineTrack(track_id="trk_storyaudio", type="audio", kind="original_audio", label="Original audio", order=2, clips=originals)],
        metadata={"source_kind": actual_kind, "content_version_id": version.project_version_id,
            "content_sha256": version.provenance["content_sha256"], "media_plan": plan,
            "media_plan_sha256": hashlib.sha256(canonical_bytes(plan)).hexdigest(),
            "narration_plan": narration_plan(document),
            "narration_timing": "scene_cue_schedule_not_measured_word_alignment", "ai_generated": False})
