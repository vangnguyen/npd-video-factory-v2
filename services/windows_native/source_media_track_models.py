"""Typed upload-to-canonical-track decisions; no provider or arbitrary graph input."""
import math
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from app.models import StrictModel

ASSET=r'^[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}$'
TRACK=r'^trk_[A-Za-z0-9_-]{4,60}$'
SHA=r'^[a-f0-9]{64}$'

class Binding(StrictModel):
    revision:StrictInt=Field(ge=1)
    expected_version:StrictInt=Field(ge=1)
    timeline_sha256:str=Field(pattern=SHA)
    asset_id:str=Field(pattern=ASSET)
    asset_sha256:str=Field(pattern=SHA)
    request_key:str=Field(min_length=16,max_length=128)

class Captions(StrictModel):
    transcript_id:str=Field(pattern=r'^trn_[a-f0-9]{24}$')
    analysis_sha256:str=Field(pattern=SHA)
    replace_track_id:str|None=Field(default=None,pattern=TRACK)
    subtitle_template_ref:str=Field(min_length=1,max_length=100)

class Audio(Binding):
    role:Literal['voice','music']
    track_id:str|None=Field(default=None,pattern=TRACK)
    replace_existing:StrictBool=False
    source_start:float=Field(ge=0,le=600)
    source_end:float=Field(gt=0,le=600)
    timeline_start:float=Field(ge=0,le=600)
    volume:float=Field(default=1,ge=0,le=2)
    fade_in_seconds:float=Field(default=0,ge=0,le=5)
    fade_out_seconds:float=Field(default=0,ge=0,le=5)
    repeat_until:float|None=Field(default=None,gt=0,le=600)
    crossfade_seconds:float=Field(default=0,ge=0,le=1)
    captions:Captions|None=None
    @field_validator('source_start','source_end','timeline_start','volume','fade_in_seconds','fade_out_seconds','repeat_until','crossfade_seconds',mode='before')
    @classmethod
    def real_numbers(cls,v):
        if v is not None and (type(v) not in (int,float) or not math.isfinite(v)):raise ValueError('Finite numeric decision required')
        return v
    @model_validator(mode='after')
    def window(self):
        duration=self.source_end-self.source_start
        if duration<.05 or max(self.fade_in_seconds,self.fade_out_seconds)>duration:raise ValueError('Audio interval/fade invalid')
        if self.replace_existing and self.track_id is None:raise ValueError('Select the track to replace')
        if self.repeat_until is not None:
            if self.role!='music' or self.repeat_until<=self.timeline_start or self.crossfade_seconds>duration/2:raise ValueError('Only music repeats within a reviewed window')
        elif self.crossfade_seconds:raise ValueError('Crossfade requires a repeating music window')
        if self.captions is not None and self.role!='voice':raise ValueError('Transcript captions require a voice track')
        return self

class Subtitles(Binding):
    timebase:Literal['timeline','source']='timeline'
    offset_seconds:float=Field(default=0,ge=-600,le=600)
    trim_to_timeline:StrictBool=False
    replace_track_id:str|None=Field(default=None,pattern=TRACK)
    subtitle_template_ref:str=Field(min_length=1,max_length=100)
    source_video_asset_id:str|None=Field(default=None,pattern=ASSET)
    source_video_asset_sha256:str|None=Field(default=None,pattern=SHA)
    @field_validator('offset_seconds',mode='before')
    @classmethod
    def finite(cls,v):
        if type(v) not in (int,float) or not math.isfinite(v):raise ValueError('Finite offset required')
        return v
    @model_validator(mode='after')
    def source_binding(self):
        if (self.source_video_asset_id is None)!=(self.source_video_asset_sha256 is None):raise ValueError('Complete source video binding required')
        if self.source_video_asset_id is not None and self.timebase!='source':raise ValueError('Video binding requires source timebase')
        return self

class CaptionEdit(StrictModel):
    clip_id:str=Field(pattern=r'^clip_[A-Za-z0-9_-]{4,60}$')
    text:str=Field(min_length=1,max_length=4000)
    timeline_start:float=Field(ge=0,le=600)
    duration:float=Field(ge=.05,le=600)
    @field_validator('text')
    @classmethod
    def plain_text(cls,v):
        if not v.strip() or '\x00' in v or any(ord(c)<32 and c not in '\n\r\t' for c in v):raise ValueError('Plain caption text required')
        return v
    @field_validator('timeline_start','duration',mode='before')
    @classmethod
    def finite(cls,v):
        if type(v) not in (int,float) or not math.isfinite(v):raise ValueError('Finite caption timing required')
        return v

class EditCaptions(StrictModel):
    revision:StrictInt=Field(ge=1)
    expected_version:StrictInt=Field(ge=1)
    timeline_sha256:str=Field(pattern=SHA)
    edits:list[CaptionEdit]=Field(min_length=1,max_length=200)
    subtitle_template_ref:str=Field(min_length=1,max_length=100)
    @model_validator(mode='after')
    def unique(self):
        if len({v.clip_id for v in self.edits})!=len(self.edits):raise ValueError('Each caption appears once')
        return self
