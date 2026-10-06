"""Deterministic native scene choices projected into the existing timeline contract."""
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from .contracts import Proposal, Scene, WorkflowError, digest
from .media import project_assets, scene_bindings
from .asr import analysis_for_asset
from app.timeline_models import TimelineClip, TimelineTrack, TimelineSnapshot, TransitionSpec


class SceneOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene: int = Field(ge=1, le=20)
    crop_strategy: Literal["contain", "cover"] = "contain"
    motion: Literal["none", "zoom_in", "pan_left", "pan_right"] = "none"
    source_start: float = Field(default=0, ge=0, le=600, allow_inf_nan=False)
    transition: Literal["cut", "fade"] = "cut"


class PlannedScene(Scene):
    id: str
    start_target: float
    end_target: float
    asset_candidates: list[dict]
    selected_asset: str
    crop_strategy: Literal["contain", "cover"]
    motion: Literal["none", "zoom_in", "pan_left", "pan_right"]
    source_start: float
    subtitle: str
    transition: Literal["cut", "fade"]
    music_ducking: bool
    cta_marker: bool


def tokens(text):
    stop = {"và", "của", "với", "cho", "trong", "để", "là", "có", "một", "các", "bạn", "này", "đến", "từ", "khi"}
    return set(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold())) - stop


def candidates(doc, scene, index):
    assets = project_assets(doc)
    wanted = tokens(scene.narration_excerpt + " " + scene.visual)
    ranked = []
    for ordinal, asset in enumerate(assets):
        record = analysis_for_asset(doc, asset)
        transcript = (record or {}).get("transcript")
        text = " ".join(s["text"] for s in transcript["segments"]) if transcript else ""
        overlap = len(wanted & tokens(text))
        preferred = ordinal == index % len(assets)
        score = overlap * 10 + int(preferred)
        source_start = 0
        if transcript and overlap:
            matching = [w["start_seconds"] for s in transcript["segments"] for w in s["words"] if wanted & tokens(w["text"])]
            source_start = min(matching) if matching else 0
        ranked.append({"asset_id": asset["id"], "source_sha256": asset["sha256"], "score": score,
            "reason": "transcript_token_overlap" if overlap else "library_rotation_requires_human_visual_check",
            "semantic_image_claim": False, "transcript_overlap_tokens": overlap, "source_start": source_start,
            "analysis_sha256": record["analysis_sha256"] if record else None})
    return sorted(ranked, key=lambda c: (-c["score"], c["asset_id"]))


def build_plan(doc, options=None, *, auto_select=False):
    from .branding import resolve
    brand,template=resolve(doc)
    if not doc.get("proposal"):
        raise WorkflowError("EDITOR_SCRIPT_REQUIRED", 400)
    proposal = Proposal.model_validate(doc["proposal"])
    assets = {a["id"]: a for a in project_assets(doc)}
    if not assets or any(a.get("rights_confirmed") is not True for a in assets.values()):
        raise WorkflowError("EDITOR_MEDIA_AND_RIGHTS_REQUIRED", 400)
    try:
        parsed = [SceneOptions.model_validate(o) for o in (options or [])]
    except ValueError:
        raise WorkflowError("EDITOR_OPTIONS_INVALID", 400) from None
    if len({o.scene for o in parsed}) != len(parsed) or any(o.scene > len(proposal.visual_brief) for o in parsed):
        raise WorkflowError("EDITOR_OPTIONS_INVALID", 400)
    selected = {b["scene"]: b["asset_id"] for b in scene_bindings(doc)}
    old = {s["scene"]: s for s in (doc.get("edit_plan") or {}).get("scenes", [])}
    overrides = {o.scene: o for o in parsed}
    total = float(template.duration_seconds) if template else max(25., len(proposal.narration.split())/2.5 + 2.)
    weights = [max(1,len(s.narration_excerpt)) for s in proposal.visual_brief]
    cursor, scenes = 0., []
    for index, scene in enumerate(proposal.visual_brief):
        ranked = candidates(doc, scene, index)
        asset_id = ranked[0]["asset_id"] if auto_select else selected.get(scene.scene, ranked[0]["asset_id"])
        if asset_id not in assets:
            raise WorkflowError("SCENE_MEDIA_NOT_IN_PROJECT", 400)
        asset = assets[asset_id]
        previous = old.get(scene.scene)
        base = {"scene": scene.scene, "crop_strategy": "contain", "motion": "zoom_in" if asset["kind"] == "image" else "none",
                "source_start": next(r["source_start"] for r in ranked if r["asset_id"] == asset_id) if asset["kind"] == "video" else 0,
                "transition": "fade"}
        if previous and previous["selected_asset"] == asset_id:
            base.update({k: previous[k] for k in ("crop_strategy", "motion", "source_start", "transition")})
        choice = overrides.get(scene.scene) or SceneOptions.model_validate(base)
        if asset["kind"] == "video" and (choice.motion != "none" or choice.source_start >= asset.get("duration_seconds", 0)):
            raise WorkflowError("EDITOR_VIDEO_TRIM_OR_MOTION_INVALID", 400)
        if asset["kind"] == "image" and choice.source_start:
            raise WorkflowError("EDITOR_IMAGE_HAS_NO_SOURCE_TIME", 400)
        end = cursor + total * weights[index]/sum(weights)
        scenes.append(PlannedScene(**scene.model_dump(), id=f"scene_{scene.scene:02}", start_target=cursor, end_target=end,
            asset_candidates=ranked, selected_asset=asset_id, crop_strategy=choice.crop_strategy, motion=choice.motion,
            source_start=choice.source_start, subtitle=scene.narration_excerpt, transition=choice.transition,
            music_ducking=bool(doc.get("music")) and doc.get("music_enabled",True), cta_marker=index==len(proposal.visual_brief)-1).model_dump())
        cursor=end
    return {"schema_version":"native-editor-v1", "proposal_sha256":digest(doc["proposal"]), "scenes":scenes,
            "timing_source":"text_estimate_replaced_by_measured_voice_before_render", "human_visual_review_required":True,
            "safe_area":brand.safe_areas.model_dump(), "cta":brand.primary_cta,
            **({"brand_template_sha256":digest(doc["brand_template"])} if doc.get("brand_template") else {})}


def validate_plan(doc):
    plan = doc.get("edit_plan")
    if not plan:
        if doc.get("brand_template"): raise WorkflowError("BRANDED_RENDER_SCENE_PLAN_REQUIRED")
        return None
    if plan.get("schema_version") != "native-editor-v1" or plan.get("proposal_sha256") != digest(doc["proposal"]):
        raise WorkflowError("EDITOR_PLAN_STALE")
    checked = build_plan(doc, [{k:s[k] for k in SceneOptions.model_fields} for s in plan["scenes"]])
    if digest(checked) != digest(plan):
        raise WorkflowError("EDITOR_PLAN_CHANGED_OR_STALE")
    return plan


def timeline(doc, frames, captions, voice=None):
    """Reuse canonical timeline DTOs, with explicit native media identifier mapping."""
    visual, text = [], []
    plan = validate_plan(doc)
    from .branding import resolve
    brand,template=resolve(doc)
    by_scene = {s["scene"]:s for s in plan["scenes"]} if plan else {}
    assets = {a["id"]: a for a in project_assets(doc)}
    for frame in frames:
        options=by_scene.get(frame["scene"], {})
        identifier="ast_"+digest(frame["asset_id"])[:32]
        start, remaining, offset, loop = frame["start"], frame["end"]-frame["start"], options.get("source_start",0), 0
        while remaining>1e-7:
            length=remaining if frame["kind"]=="image" else min(remaining,assets[frame["asset_id"]]["duration_seconds"]-offset)
            if length<=0:
                raise WorkflowError("EDITOR_SOURCE_WINDOW_INVALID")
            visual.append(TimelineClip(clip_id=f"clip_native_{frame['scene']:02}_{loop:04}", kind="image" if frame["kind"]=="image" else "source",
                label=f"Cảnh {frame['scene']}", asset_id=identifier, timeline_start=start, duration=length,
                source_start=offset, source_end=None if frame["kind"]=="image" else offset+length,
                transition_in=TransitionSpec(kind=options.get("transition","cut") if loop==0 else "cut",duration_seconds=min(.15,length) if loop==0 and options.get("transition")=="fade" else 0),
                metadata={"native_asset_id":frame["asset_id"],"source_sha256":frame["source_sha256"],"fit":options.get("crop_strategy","contain"),
                          "motion":options.get("motion","none"),"short_source_policy":frame.get("short_video_policy"),"source_audio":"muted","loop_index":loop}))
            start+=length; remaining-=length; offset=0; loop+=1
    for index,cue in enumerate(captions):
        text.append(TimelineClip(clip_id=f"clip_caption_{index:04}",kind="subtitle",label=cue["text"][:240],source_end=cue["end"]-cue["start"],
            timeline_start=cue["start"],duration=cue["end"]-cue["start"],metadata={"text":cue["text"],"timing_source":cue.get('timing_source',"measured_sentence_activity_weighted_phrase_estimate")}))
    tracks=[
        TimelineTrack(track_id="trk_native_video",type="video",kind="source",label="Cảnh",order=0,clips=visual),
        TimelineTrack(track_id="trk_native_captions",type="text",kind="subtitles",label="Lời đọc",order=1,clips=text)]
    if voice:
        tracks.append(TimelineTrack(track_id="trk_native_voice",type="audio",kind="voice",label="Thùy Dung",order=len(tracks),clips=[
            TimelineClip(clip_id="clip_native_voice",kind="voice",label="Giọng đọc đã đo",source_end=voice["duration_seconds"],
                timeline_start=0 if doc.get('canonical_timeline') else brand.intro_seconds,duration=voice["duration_seconds"],metadata={"sha256":voice["audio_sha256"],"profile_sha256":voice["profile_sha256"],"speed":1})]))
    music=doc.get("music") if doc.get("music_enabled",True) else None
    if music:
        clips=[]; start=0.; total=frames[-1]["end"]
        while start<total-1e-7:
            length=min(music["duration_seconds"],total-start)
            clips.append(TimelineClip(clip_id=f"clip_native_music_{len(clips):04}",kind="music",label="Nhạc nền",timeline_start=start,source_end=length,duration=length,
                volume=brand.music_profile.nominal_gain,asset_id="ast_"+digest(music["id"])[:32],metadata={"native_asset_id":music["id"],"sha256":music["sha256"],"ducking":brand.music_profile.ducking}))
            start+=length
        tracks.append(TimelineTrack(track_id="trk_native_music",type="audio",kind="music",label="Nhạc nền",order=len(tracks),clips=clips))
    lineage={}
    if doc.get("content_intelligence"):
        from .intelligence_lineage import projection
        lineage={"content_intelligence":projection(doc)}
    shape={'width':template.width,'height':template.height,'aspect_ratio':template.aspect_ratio} if template else {}
    canonical=doc.get('canonical_timeline')
    if canonical:
        from .shot_adapter import validate_document,shots
        validate_document(doc)
        mapping={i+1:s['shot_id'] for i,s in enumerate(shots(doc))}
        for clip in visual:
            clip.metadata['shot_id']=mapping[int(clip.clip_id.split('_')[2])]
        lineage['canonical_timeline']={'version':canonical['version'],'sha256':canonical['sha256']}
    return TimelineSnapshot(schema_version="1.1",duration_seconds=frames[-1]["end"],tracks=tracks,**shape,
        metadata={"timing_source":"measured_narration_audio", "edit_plan_sha256":digest(plan), "human_review_required":True,
                  **lineage}).model_dump(mode="json")
