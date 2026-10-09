"""Storyboard planning contracts; do not invent an uploaded-video analysis ID."""
from typing import Literal
from pydantic import Field,model_validator
from . import ingestion
from app.models import StrictModel
from app.media_intelligence_models import MediaStrategy,PlatformTarget
from .official_vision_evidence import ReviewedVision

HASH=r'^[a-f0-9]{64}$'
PLAN=r'^nmp_[a-f0-9]{32}$'
SHOT=r'^shot_[a-f0-9]{32}$'
ASSET=r'^[a-f0-9]{32}\.(jpg|png|mp4|mov)$'
Tier=Literal['user_asset','licensed_stock','internal_library','ai_image','ai_video','motion_graphic']


class Options(StrictModel):
    platform:PlatformTarget='youtube_shorts'
    aspect_ratio:Literal['9:16','16:9','1:1','4:5']|None=None
    preferred_media_type:Literal['image','video']='video'
    resolver_priority:list[Tier]=Field(default_factory=lambda:['user_asset','licensed_stock','internal_library','ai_image','ai_video','motion_graphic'],min_length=1,max_length=6)
    allow_stock:bool=Field(default=True,strict=True)
    allow_ai_image:bool=Field(default=True,strict=True)
    allow_ai_video:bool=Field(default=True,strict=True)
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.resolver_priority))!=len(self.resolver_priority):raise ValueError('Duplicate resolver tier')
        return self


class Create(StrictModel):
    revision:int=Field(ge=1,strict=True)
    expected_timeline_version:int=Field(ge=0,strict=True)
    options:Options=Field(default_factory=Options)
    reviewed_vision:list[ReviewedVision]=Field(default_factory=list,max_length=50)


class Action(StrictModel):
    revision:int=Field(ge=1,strict=True)
    expected_plan_version:int=Field(ge=1,strict=True)
    expected_plan_sha256:str=Field(pattern=HASH)


class Select(Action):
    shot_id:str=Field(pattern=SHOT)
    asset_id:str=Field(pattern=ASSET)
    expected_asset_sha256:str=Field(pattern=HASH)


class Revise(Action):
    shot_id:str=Field(pattern=SHOT)
    strategy:MediaStrategy
    query:str=Field(min_length=1,max_length=500)
    generation_prompt:str=Field(min_length=1,max_length=4000)


class Apply(Action):
    acknowledged:Literal[True]
    shot_ids:list[str]=Field(min_length=1,max_length=20)
    @model_validator(mode='after')
    def unique(self):
        import re
        if len(set(self.shot_ids))!=len(self.shot_ids) or any(not re.fullmatch(SHOT,value) for value in self.shot_ids):raise ValueError('Invalid selected shots')
        return self


class Candidate(StrictModel):
    asset_id:str=Field(pattern=ASSET)
    sha256:str=Field(pattern=HASH)
    filename:str
    kind:Literal['image','video']
    strategy:MediaStrategy
    resolver_tier:Tier
    relevance_score:float=Field(ge=0,le=1,allow_inf_nan=False)
    quality_score:float|None=Field(default=None,ge=0,le=1,allow_inf_nan=False)
    confidence:None=None
    score_basis:Literal['saved_filename_description_tags_and_uncalibrated_pixel_tiebreak','reviewed_provider_labels_and_uncalibrated_predicted_sample_quality']
    selectable:bool
    fixture:bool
    provenance:dict


class Item(StrictModel):
    shot_id:str=Field(pattern=SHOT)
    ordinal:int=Field(ge=1,le=20)
    visual_brief:str
    narration:str
    on_screen_text:str
    duration_seconds:float=Field(gt=0,le=180,allow_inf_nan=False)
    duration_basis:Literal['draft_shot_duration_requires_measured_voice_fit']
    target_aspect_ratio:Literal['9:16','16:9','1:1','4:5']
    strategy:MediaStrategy
    fallback:list[MediaStrategy]
    query:str=Field(min_length=1,max_length=500)
    generation_prompt:str=Field(min_length=1,max_length=4000)
    candidates:list[Candidate]=Field(max_length=50)
    selected_asset_id:str|None=None
    selected_asset_sha256:str|None=Field(default=None,pattern=HASH)
    status:Literal['planned','selected','requires_asset','requires_provider','requires_implementation','requires_approval']
    new_generation_budget_blocked:list[Literal['ai_image','ai_video']]=Field(default_factory=list,max_length=2)
    estimated_cost_vnd:None=None
    needs_approval:bool
    needs_attention:Literal[True]=True
    decision_basis:str
    @model_validator(mode='after')
    def selection(self):
        selected=next((value for value in self.candidates if value.asset_id==self.selected_asset_id),None)
        if self.selected_asset_id is None:
            if self.selected_asset_sha256 is not None or self.status=='selected':raise ValueError('Missing selection')
        elif selected is None or not selected.selectable or selected.sha256!=self.selected_asset_sha256 or selected.strategy!=self.strategy or self.status!='selected':raise ValueError('Invalid selection')
        return self


class Plan(StrictModel):
    schema_version:Literal['native-storyboard-media-plan-v1','native-storyboard-media-plan-v2']
    algorithm:Literal['native-storyboard-media-planner-v1','native-storyboard-media-planner-v2','native-storyboard-media-planner-v3']
    workspace_id:str
    project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    media_plan_id:str=Field(pattern=PLAN)
    version:int=Field(ge=1,strict=True)
    fingerprint:str=Field(pattern=HASH)
    input_sha256:str=Field(pattern=HASH)
    input:dict
    options:Options
    items:list[Item]=Field(min_length=1,max_length=20)
    application:dict|None=None
    created_at:str
    updated_at:str
    external_dispatches:Literal[0]=0
    paid_operations:Literal[0]=0
    publishing_enabled:Literal[False]=False
    recommendation_only:Literal[True]=True
    semantic_vision_used:bool=Field(default=False,strict=True)
    real_provider_tested:Literal[False]=False
    @model_validator(mode='after')
    def unique(self):
        if len({value.shot_id for value in self.items})!=len(self.items) or [value.ordinal for value in self.items]!=list(range(1,len(self.items)+1)):raise ValueError('Invalid scene sequence')
        if self.schema_version=='native-storyboard-media-plan-v2':
            reviewed=self.input.get('reviewed_vision')
            if (self.algorithm!='native-storyboard-media-planner-v3' or not isinstance(reviewed,dict)
                or self.input.get('schema_version')!='native-storyboard-media-input-v2'
                or type(reviewed.get('semantic_vision_used')) is not bool or self.semantic_vision_used is not reviewed['semantic_vision_used']):raise ValueError('Invalid reviewed Vision plan')
        elif self.algorithm=='native-storyboard-media-planner-v3' or self.semantic_vision_used or 'reviewed_vision' in self.input:raise ValueError('Legacy plan cannot claim reviewed Vision')
        return self
