"""Reviewable source-seconds crop plans. Unconfigured tracking is never inferred."""
from types import SimpleNamespace
from typing import Literal
from pydantic import Field,model_validator
from .auto_edit_timeline import _cas,_save,view
from .auto_edit_analysis import asset_reference
from .contracts import WorkflowError,digest
from .source_preview import resolve_assets
from app.models import StrictModel
from app.auto_edit_models import MediaMetadata
from app.timeline_logic import TimelineEditError
from app.timeline_reframe import bind_reframe
from app.vision_models import ManualCropOverride
from app.vision_logic import build_reframe_plans


class ManualPoint(StrictModel):
    time:float=Field(ge=0)
    x:float=Field(ge=0,le=1)
    y:float=Field(ge=0,le=1)
    zoom:float=Field(default=1,ge=1,le=4)


class Request(StrictModel):
    expected_version:int=Field(ge=1,strict=True)
    aspect_ratio:Literal['9:16','16:9','1:1','4:5']
    mode:Literal['center_crop','manual_override']='center_crop'
    points:list[ManualPoint]=Field(default_factory=list,max_length=200)
    @model_validator(mode='after')
    def valid_mode(self):
        if bool(self.points)!=(self.mode=='manual_override'):raise ValueError('manual points required only for manual mode')
        if len({point.time for point in self.points})!=len(self.points):raise ValueError('duplicate times')
        return self


def apply(store,project_id,revision,body):
    try:payload=Request.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_EDIT_REFRAME_REQUEST_INVALID',400) from None
    with store.transaction() as con:
        project=store.editable(con,project_id,revision);state=_cas(project,payload.expected_version)
        snapshot,assets=resolve_assets(SimpleNamespace(data_root=store.root),project)
        root=next(record for record in project['document']['auto_edit_analyses']
            if record['analysis']['analysis_id']==snapshot.metadata['source_analysis_id'])
        source=MediaMetadata.model_validate(root['analysis']['source_media'])
        if not source.width or not source.height or not source.duration_seconds:
            raise WorkflowError('AUTO_EDIT_REFRAME_SOURCE_GEOMETRY_REQUIRED',400)
        if any(point.time>source.duration_seconds for point in payload.points):
            raise WorkflowError('AUTO_EDIT_REFRAME_SOURCE_TIME_INVALID',400)
        asset=next(item for item in project['document']['assets'] if item['id']==root['native_asset_id'])
        identifier=asset_reference(asset)
        if identifier not in assets:raise WorkflowError('AUTO_EDIT_REFRAME_ENABLED_SOURCE_REQUIRED',400)
        target_ratio={'9:16':9/16,'16:9':16/9,'1:1':1,'4:5':4/5}[payload.aspect_ratio]
        relative=(source.width/source.height)/target_ratio;minimum_scale=max(relative,1/relative)
        try:
            overrides=[ManualCropOverride(aspect_ratio=payload.aspect_ratio,time=point.time,x=point.x,y=point.y,
                scale=round(minimum_scale*point.zoom,6)) for point in sorted(payload.points,key=lambda point:point.time)]
            fingerprint=digest({'project_id':project_id,'timeline_sha256':state['sha256'],
                'source_checksum':asset['sha256'],'request':payload.model_dump(mode='json')})
            plan=build_reframe_plans(frames=[],tracks=[],metadata=source,aspect_ratios=[payload.aspect_ratio],
                manual_overrides=overrides,minimum_tracking_confidence=.6,subtitle_safe_area_bottom=.18,
                maximum_jump=.12,fingerprint=fingerprint)[0]
            result=bind_reframe(snapshot,asset_id=identifier,metadata=source,plan=plan,vision_analysis_id=None)
        except (ValueError,TimelineEditError):raise WorkflowError('AUTO_EDIT_REFRAME_PLAN_INVALID_OR_LOCKED',400) from None
        result.metadata['source_reframe_plan']={'schema':'native-source-reframe-v1','plan':plan.model_dump(mode='json'),
            'source_analysis_id':snapshot.metadata['source_analysis_id'],'native_asset_id':asset['id'],
            'source_checksum_sha256':asset['sha256'],'source_width':source.width,'source_height':source.height,
            'source_duration_seconds':source.duration_seconds,'manual_points':[p.model_dump(mode='json') for p in payload.points],
            'provider_status':'NOT_CONFIGURED','tracking_confidence':None,'provider_dispatches':0,
            'confidence_basis':'explicit_human_crop_coordinates' if payload.points else 'unmeasured_subject_center_fallback',
            'human_review_required':True,'fresh_provider_measurement':False}
        result.metadata['reframe_review']={'needs_attention':plan.needs_attention,'fallback':plan.fallback,
            'tracking_confidence':None,'human_review_required':True,
            'confidence_basis':result.metadata['source_reframe_plan']['confidence_basis']}
        _save(store,con,project,result,'auto_edit_source_reframe_saved')
    return view(store,project_id)
