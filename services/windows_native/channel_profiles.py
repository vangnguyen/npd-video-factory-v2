"""Versioned channel/niche configuration frozen into new Native projects."""
import copy,json,re
from pathlib import Path
from typing import Literal
from pydantic import Field,model_validator
from .contracts import WorkflowError,PROFILE_SHA,digest
from .ingestion import validate_text
from .branding import choose,Selection,FIT_NARRATION_POLICY
from .idea_scoring import configuration
from app.models import StrictModel
from app.timeline_audio_processing import AudioProcessing
from app.subtitle_templates import load_templates
from app.production_models import SubtitleStyle
from app.production_logic import derive_subtitle_cues,validate_subtitles

CATALOG=Path(__file__).parent/'profiles/channels.json'
REF=r'^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$'

class NicheProfile(StrictModel):
    profile_ref:str=Field(pattern=REF)
    niche:str=Field(pattern=r'^[a-z][a-z0-9_-]{1,79}$')
    name:str=Field(min_length=1,max_length=100)
    language:Literal['vi','en']
    locale:str=Field(pattern=r'^[a-z]{2}-[A-Z]{2}$')
    country:str=Field(pattern=r'^[A-Z]{2}$')
    target_audience:str=Field(min_length=1,max_length=500)
    tone:str=Field(min_length=1,max_length=500)
    keywords:list[str]=Field(min_length=1,max_length=30)
    @model_validator(mode='after')
    def bounded(self):
        if self.locale.split('-')!=[self.language,self.country] or any(not 1<=len(word.strip())<=100 for word in self.keywords):raise ValueError('Niche locale/keywords invalid')
        return self

class PublishingProfile(StrictModel):
    profile_ref:str=Field(pattern=REF)
    platforms:list[Literal['youtube','tiktok','instagram','facebook']]=Field(min_length=1,max_length=4)
    enabled:Literal[False]=False
    human_publish_approval_required:Literal[True]=True
    rights_unknown_policy:Literal['block']='block'
    official_account_ref:None=None
    credentials_configured:Literal[False]=False
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.platforms))!=len(self.platforms):raise ValueError('Duplicate platform')
        return self

class AnalyticsProfile(StrictModel):
    profile_ref:str=Field(pattern=REF)
    enabled:Literal[False]=False
    provider_mode:Literal['official']='official'
    provider_status:Literal['NOT_CONFIGURED']='NOT_CONFIGURED'
    official_account_ref:None=None
    missing_metric_policy:Literal['null']='null'
    learning_mode:Literal['recommendation_only']='recommendation_only'

class SourcePreferences(StrictModel):
    subtitle_template_ref:str=Field(max_length=100)
    preview_mode:Literal['final_effects']='final_effects'
    audio_processing:AudioProcessing=Field(default_factory=AudioProcessing)

class ChannelProfile(StrictModel):
    profile_ref:str=Field(pattern=REF)
    name:str=Field(min_length=1,max_length=100)
    content_profile_id:str=Field(pattern=r'^[a-z][a-z0-9-]{2,60}$')
    niche_profile:NicheProfile
    brand_id:str=Field(pattern=r'^[a-z][a-z0-9-]{2,49}$')
    video_template_id:str=Field(pattern=r'^[a-z][a-z0-9-]{2,59}$')
    duration_mode:Literal['fit_narration_preserve_voice_speed']=FIT_NARRATION_POLICY
    voice_profile_sha256:Literal[PROFILE_SHA]=PROFILE_SHA
    source_preferences:SourcePreferences
    publishing_profile:PublishingProfile
    analytics_profile:AnalyticsProfile

class Catalog(StrictModel):
    schema_version:Literal['native-channel-profile-catalog-v1']
    catalog_ref:str=Field(pattern=REF)
    profiles:list[ChannelProfile]=Field(min_length=1,max_length=50)
    @model_validator(mode='after')
    def unique(self):
        if len({value.profile_ref for value in self.profiles})!=len(self.profiles):raise ValueError('Duplicate channel')
        return self

class FrozenSelection(StrictModel):
    schema_version:Literal['native-channel-selection-v1']
    profile:ChannelProfile
    profile_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    content_profile:dict
    content_profile_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    brand_template:Selection
    source_subtitle_style:SubtitleStyle
    external_dispatches:Literal[0]
    paid_operations:Literal[0]
    publishing_enabled:Literal[False]
    catalog_ref:str=Field(pattern=REF)
    catalog_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    selection_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

def resolve_profile(profile):
    data=profile.model_dump(mode='json');content=next((value for value in configuration()['profiles'] if value['id']==profile.content_profile_id),None)
    template=next((value for value in load_templates() if value['template_ref']==profile.source_preferences.subtitle_template_ref),None)
    if content is None or template is None:raise ValueError('Configured content/subtitle reference missing')
    if content['target_audience']!=profile.niche_profile.target_audience or content['tone']!=profile.niche_profile.tone:raise ValueError('Configured audience/tone mismatch')
    brand=choose(profile.brand_id,profile.video_template_id,duration_mode=profile.duration_mode)
    return {'schema_version':'native-channel-selection-v1','profile':data,'profile_sha256':digest(data),
        'content_profile':copy.deepcopy(content),'content_profile_sha256':digest(content),'brand_template':brand,
        'source_subtitle_style':copy.deepcopy(template['style']),'external_dispatches':0,'paid_operations':0,'publishing_enabled':False}

def catalog():
    try:
        parsed=Catalog.model_validate_json(CATALOG.read_bytes()).model_dump(mode='json')
        profiles=[resolve_profile(ChannelProfile.model_validate(value)) for value in parsed['profiles']]
    except (ValueError,OSError,WorkflowError):raise WorkflowError('CHANNEL_PROFILE_CATALOG_INVALID',503) from None
    return {**parsed,'sha256':digest(parsed),'selections':profiles,'external_dispatches':0,'publishing_enabled':False}

def select(reference):
    if not isinstance(reference,str) or not re.fullmatch(REF,reference):raise WorkflowError('CHANNEL_PROFILE_NOT_FOUND',400)
    available=catalog();selection=next((value for value in available['selections'] if value['profile']['profile_ref']==reference),None)
    if selection is None:raise WorkflowError('CHANNEL_PROFILE_NOT_FOUND',400)
    selection={**selection,'catalog_ref':available['catalog_ref'],'catalog_sha256':available['sha256']}
    return {**selection,'selection_sha256':digest(selection)}

def resolve(document):
    value=document.get('channel_profile')
    if value is None:return None
    try:
        FrozenSelection.model_validate(value)
        profile=ChannelProfile.model_validate(value['profile']);brand=Selection.model_validate(value['brand_template'])
        if value['schema_version']!='native-channel-selection-v1' or value['selection_sha256']!=digest({key:item for key,item in value.items() if key!='selection_sha256'}):raise ValueError()
        if value['profile_sha256']!=digest(profile.model_dump(mode='json')) or value['content_profile_sha256']!=digest(value['content_profile']):raise ValueError()
        if digest(brand.brand.model_dump())!=brand.brand_sha256 or digest(brand.template.model_dump())!=brand.template_sha256:raise ValueError()
        if brand.brand.id!=profile.brand_id or brand.template.id!=profile.video_template_id or value['content_profile']['id']!=profile.content_profile_id or document.get('niche')!=profile.niche_profile.niche:raise ValueError()
        style=SubtitleStyle.model_validate(value['source_subtitle_style'])
        if style.template_ref!=profile.source_preferences.subtitle_template_ref or brand.template.duration_policy!=profile.duration_mode:raise ValueError()
        if value['external_dispatches']!=0 or value['paid_operations']!=0 or value['publishing_enabled'] is not False:raise ValueError()
        return value
    except (KeyError,TypeError,ValueError):raise WorkflowError('CHANNEL_PROFILE_SNAPSHOT_CHANGED') from None

def bind_source(snapshot,document):
    selection=resolve(document)
    if selection is None:return snapshot
    preferences=selection['profile']['source_preferences'];style=SubtitleStyle.model_validate(selection['source_subtitle_style'])
    validate_subtitles(derive_subtitle_cues(snapshot),style,snapshot.duration_seconds)
    snapshot.metadata.update(source_preview_mode=preferences['preview_mode'],subtitle_style=style.model_dump(mode='json'),
        subtitle_template_ref=preferences['subtitle_template_ref'],source_audio_processing=preferences['audio_processing'],
        channel_profile_ref=selection['profile']['profile_ref'],channel_selection_sha256=selection['selection_sha256'])
    return snapshot
