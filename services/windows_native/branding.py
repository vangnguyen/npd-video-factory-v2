"""Frozen project brand/template choices; legacy snapshots remain readable."""
import copy
import json
import math
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .contracts import PROFILE_SHA, WorkflowError, digest, file_sha
from .media import project_assets, media_path

CATALOG=Path(__file__).parent/"profiles"/"catalog.json"


class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid")


class Fonts(Strict):
    heading: Literal["seguisb.ttf","arialbd.ttf"]="seguisb.ttf"
    body: Literal["segoeui.ttf","arial.ttf"]="segoeui.ttf"
    subtitle_family: Literal["Segoe UI","Arial"]="Segoe UI"


class Palette(Strict):
    background: str=Field(pattern=r"^#[0-9a-fA-F]{6}$")
    text: str=Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str=Field(pattern=r"^#[0-9a-fA-F]{6}$")
    muted: str=Field(pattern=r"^#[0-9a-fA-F]{6}$")
    caption_background: str=Field(pattern=r"^#[0-9a-fA-F]{6}$")
    caption_border: str=Field(pattern=r"^#[0-9a-fA-F]{6}$")


class SubtitleStyle(Strict):
    font_size: int=Field(default=46,ge=24,le=64)
    color: str=Field(default="#fcf9f1",pattern=r"^#[0-9a-fA-F]{6}$")
    timing: Literal["measured_sentence_activity_weighted_phrase_estimate"]="measured_sentence_activity_weighted_phrase_estimate"


class SafeAreas(Strict):
    top: int=Field(default=160,ge=90,le=180)
    bottom: int=Field(default=360,ge=320,le=420)
    left: int=Field(default=90,ge=70,le=130)
    right: int=Field(default=180,ge=140,le=210)
    source: Literal["configurable_reference_margins"]="configurable_reference_margins"


class MusicProfile(Strict):
    nominal_gain: float=Field(default=.12,ge=.01,le=.25,allow_inf_nan=False)
    ducking: Literal["voice_sidechaincompress"]="voice_sidechaincompress"
    default_track: None=None  # No unlicensed or fabricated default music asset.


class BrandProfile(Strict):
    id: str=Field(pattern=r"^[a-z][a-z0-9-]{2,49}$")
    name: str=Field(min_length=1,max_length=100)
    logo: str|None=Field(default=None,pattern=r"^[0-9a-f]{32}\.jpg$")
    asset_status: Literal["reference_only_official_assets_missing","generic_reference","configured"]
    fonts: Fonts=Field(default_factory=Fonts)
    palette: Palette
    subtitle_style: SubtitleStyle=Field(default_factory=SubtitleStyle)
    primary_cta: str=Field(min_length=1,max_length=180)
    intro: str=Field(min_length=1,max_length=100)
    intro_seconds: float=Field(default=1.1,ge=.5,le=2,allow_inf_nan=False)
    outro_seconds: float=Field(default=1.,ge=.5,le=3,allow_inf_nan=False)
    voice_profile_sha256: str
    music_profile: MusicProfile=Field(default_factory=MusicProfile)
    safe_areas: SafeAreas=Field(default_factory=SafeAreas)
    project_disclaimers: list[str]=Field(min_length=1,max_length=3)

    @model_validator(mode="after")
    def preserve_voice(self):
        if self.voice_profile_sha256!=PROFILE_SHA or any(not 1<=len(s)<=180 for s in self.project_disclaimers):
            raise ValueError("Locked voice or disclaimer invalid")
        return self


class VideoTemplate(Strict):
    id: str=Field(pattern=r"^[a-z][a-z0-9-]{2,59}$")
    name: str=Field(min_length=1,max_length=120)
    purpose: Literal["property_presentation","news_update","personal_brand","event_promo"]
    scene_label: str=Field(min_length=1,max_length=40)
    duration_seconds: Literal[30,45,60]
    width: Literal[1080,1920]=1080
    height: Literal[1920,1080]=1920
    fps: Literal[30]=30
    aspect_ratio: Literal["9:16","16:9"]="9:16"
    duration_policy: Literal["preserve_voice_speed_hold_cta_to_target_refuse_overflow"]="preserve_voice_speed_hold_cta_to_target_refuse_overflow"

    @model_validator(mode='after')
    def canvas_pair(self):
        if (self.width,self.height,self.aspect_ratio) not in {(1080,1920,'9:16'),(1920,1080,'16:9')}:
            raise ValueError('Template canvas/aspect mismatch')
        return self


class Selection(Strict):
    schema_version: Literal["native-brand-template-v1"]="native-brand-template-v1"
    brand: BrandProfile
    template: VideoTemplate
    brand_sha256: str
    template_sha256: str


def catalog(include_landscape=False):
    raw=json.loads(CATALOG.read_bytes())
    profiles=[]
    for choice in raw["brands"]:
        value=copy.deepcopy(raw["defaults"]); value.update(choice)
        profiles.append(BrandProfile.model_validate(value).model_dump())
    templates=[VideoTemplate.model_validate({**family,"id":f"{family['id']}-{seconds}","name":f"{family['name']} · {seconds} giây","duration_seconds":seconds}).model_dump()
               for family in raw["template_families"] for seconds in raw["durations"]]
    if include_landscape:
        templates += [VideoTemplate.model_validate({**t,'id':t['id']+'-landscape','name':t['name']+' · 16:9',
                         'width':1920,'height':1080,'aspect_ratio':'16:9'}).model_dump() for t in list(templates)]
    return {"brands":profiles,"templates":templates}


def choose(brand_id, template_id):
    values=catalog(include_landscape=True)
    brand=next((b for b in values["brands"] if b["id"]==brand_id),None)
    template=next((t for t in values["templates"] if t["id"]==template_id),None)
    if not brand or not template: raise WorkflowError("BRAND_TEMPLATE_CHOICE_REQUIRED",400)
    return Selection(brand=brand,template=template,brand_sha256=digest(brand),template_sha256=digest(template)).model_dump()


def resolve(doc):
    value=doc.get("brand_template")
    if not value:
        return BrandProfile.model_validate(next(b for b in catalog()["brands"] if b["id"]=="vf-reference")),None
    try:
        selection=Selection.model_validate(value)
        if digest(selection.brand.model_dump())!=selection.brand_sha256 or digest(selection.template.model_dump())!=selection.template_sha256:
            raise ValueError()
        return selection.brand,selection.template
    except ValueError:
        raise WorkflowError("BRAND_TEMPLATE_SNAPSHOT_CHANGED_OR_INVALID") from None


def validate_assets(config, doc):
    brand,_=resolve(doc)
    fonts=Path(os.environ.get("WINDIR",r"C:\Windows"))/"Fonts"
    if any(not (fonts/name).is_file() for name in (brand.fonts.heading,brand.fonts.body)):
        raise WorkflowError("BRAND_FONT_UNAVAILABLE")
    if brand.logo:
        logo=next((a for a in project_assets(doc) if a["id"]==brand.logo and a["kind"]=="image" and a["rights_confirmed"] is True),None)
        if not logo or not media_path(config,brand.logo).is_file() or file_sha(media_path(config,brand.logo))!=logo["sha256"]:
            raise WorkflowError("BRAND_LOGO_SOURCE_CHANGED_OR_RIGHTS_MISSING")
    return brand


def measured_duration(doc, voice_seconds):
    if not isinstance(voice_seconds,(float,int)) or not math.isfinite(voice_seconds) or not 0<voice_seconds<=180:
        raise WorkflowError("VOICE_DURATION_INVALID")
    brand,template=resolve(doc)
    required=brand.intro_seconds+voice_seconds+brand.outro_seconds
    if template:
        if required>template.duration_seconds+.001:
            raise WorkflowError("TEMPLATE_NARRATION_TOO_LONG_CHOOSE_LONGER_OR_EDIT")
        return float(template.duration_seconds)
    return max(25.,required)
