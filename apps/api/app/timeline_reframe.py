"""Bind existing structured Vision plans to canonical, source-relative crop paths."""
from __future__ import annotations
from typing import Literal
from pydantic import Field
from .models import StrictModel
from .timeline_logic import TimelineEditError
from .timeline_models import CropSpec,TimelineSnapshot
from .vision_models import ReframePlanRead
from .vision_logic import build_reframe_plans

ASPECT_DIMENSIONS={'9:16':(1080,1920),'16:9':(1920,1080),'1:1':(1080,1080),'4:5':(1080,1350)}


class ReframeApplyRequest(StrictModel):
    expected_version: int = Field(ge=1,strict=True)
    aspect_ratio: Literal['9:16','16:9','1:1','4:5']
    vision_analysis_id: str | None = Field(default=None,pattern=r'^vis_[A-Za-z0-9_-]{4,60}$')


def crop_keyframes(plan: ReframePlanRead,metadata):
    if not metadata.width or not metadata.height:raise TimelineEditError('measured source dimensions required for reframe')
    target_width,target_height=ASPECT_DIMENSIONS[plan.aspect_ratio]
    relative=(metadata.width/metadata.height)/(target_width/target_height)
    minimum_scale=max(relative,1/relative)
    previous=-1.;result=[]
    if len(plan.keyframes)>2000:raise TimelineEditError('reframe plan exceeds the supported keyframe limit')
    for keyframe in plan.keyframes:
        if keyframe.time<=previous:raise TimelineEditError('reframe keyframe times must strictly increase')
        if keyframe.time>float(metadata.duration_seconds or 0)+.001:raise TimelineEditError('reframe keyframe exceeds measured source duration')
        previous=keyframe.time
        if keyframe.scale<minimum_scale-1e-6:raise TimelineEditError('reframe scale cannot fit the requested aspect ratio')
        # Scale is relative to the full source frame along the cropped axis.
        width=min(1.,1/keyframe.scale if relative>=1 else (1/relative)/keyframe.scale)
        height=min(1.,relative/keyframe.scale if relative>=1 else 1/keyframe.scale)
        crop=CropSpec(x=max(0.,min(1-width,keyframe.x-width/2)),y=max(0.,min(1-height,keyframe.y-height/2)),width=width,height=height)
        result.append({'time':keyframe.time,**crop.model_dump(mode='json')})
    if not result:raise TimelineEditError('reframe plan has no keyframes')
    return result


def bind_reframe(snapshot:TimelineSnapshot,*,asset_id:str,metadata,plan:ReframePlanRead,vision_analysis_id:str|None):
    result=snapshot.model_copy(deep=True)
    keyframes=crop_keyframes(plan,metadata)
    affected=[]
    for track in result.tracks:
        if track.type!='video' or track.disabled:continue
        for clip in track.clips:
            if clip.asset_id!=asset_id or clip.disabled:continue
            if track.locked:raise TimelineEditError('unlock the source video track before reframing')
            clip.crop=CropSpec.model_validate({key:value for key,value in keyframes[0].items() if key!='time'})
            clip.metadata={**clip.metadata,'reframe':{'schema_version':1,'plan_id':plan.reframe_id,
                'vision_analysis_id':vision_analysis_id,'aspect_ratio':plan.aspect_ratio,'strategy':plan.strategy,
                'confidence':plan.confidence,'fallback':plan.fallback,'needs_attention':plan.needs_attention,
                'source_width':metadata.width,'source_height':metadata.height,'time_space':'source_seconds','keyframes':keyframes}}
            affected.append(clip.clip_id)
    if not affected:raise TimelineEditError('active timeline has no enabled footage from this source')
    result.width,result.height=ASPECT_DIMENSIONS[plan.aspect_ratio]
    result.aspect_ratio=plan.aspect_ratio
    result.metadata={**result.metadata,'reframe':{'aspect_ratio':plan.aspect_ratio,'vision_analysis_id':vision_analysis_id,
        'plan_id':plan.reframe_id,'strategy':plan.strategy,'confidence':plan.confidence,'fallback':plan.fallback,
        'needs_attention':plan.needs_attention,'affected_clip_ids':affected,'human_review_required':True,'provider_dispatches':0}}
    return result


async def apply_reframe(service,vision_repository,project_id,payload,actor_ref):
    timeline=await service.repository.get_timeline(project_id)
    if timeline is None:raise KeyError(project_id)
    if not timeline.source_analysis_id:raise TimelineEditError('source-footage reframe requires a video analysis timeline')
    analysis=await service.auto_edit_repository.get_analysis(timeline.source_analysis_id)
    if analysis is None or analysis.project_id!=project_id:raise KeyError(timeline.source_analysis_id)
    if payload.vision_analysis_id:
        if vision_repository is None:raise TimelineEditError('Vision repository is not configured')
        vision=await vision_repository.get_analysis(payload.vision_analysis_id)
        if vision is None or vision.project_id!=project_id or vision.analysis_id!=analysis.analysis_id or vision.asset_id!=analysis.asset_id:
            raise KeyError(payload.vision_analysis_id)
        if vision.status!='succeeded':raise TimelineEditError('Vision analysis is not ready')
        if (vision.provenance.get('source_asset_checksum')!=analysis.provenance.get('source_asset_checksum')
            or vision.source_media.width!=analysis.source_media.width or vision.source_media.height!=analysis.source_media.height):
            raise TimelineEditError('Vision evidence does not match the measured source')
        plan=next((plan for plan in vision.reframe_plans if plan.aspect_ratio==payload.aspect_ratio),None)
        if plan is None:raise TimelineEditError('saved Vision analysis has no requested aspect ratio')
    else:
        plan=build_reframe_plans(frames=[],tracks=[],metadata=analysis.source_media,aspect_ratios=[payload.aspect_ratio],
            manual_overrides=[],minimum_tracking_confidence=.6,subtitle_safe_area_bottom=.18,maximum_jump=.12,
            fingerprint=analysis.fingerprint)[0]
    snapshot=bind_reframe(timeline.snapshot,asset_id=analysis.asset_id,metadata=analysis.source_media,plan=plan,
                          vision_analysis_id=payload.vision_analysis_id)
    service.validator.validate(snapshot)
    return await service.repository.commit_mutation(project_id=project_id,expected_version=payload.expected_version,snapshot=snapshot,
        mutation={'type':'smart-reframe','aspect_ratio':payload.aspect_ratio,'vision_analysis_id':payload.vision_analysis_id,
                  'fallback':plan.fallback,'needs_attention':plan.needs_attention,'provider_dispatches':0},actor_ref=actor_ref)
