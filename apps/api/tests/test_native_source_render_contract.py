"""Shared JSON contract must match native/source renderer capabilities and legacy guards."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import copy

import pytest
from app.production_logic import build_timeline_render_manifest, TimelineRenderContractValidator, ProductionContractError
from app.production_models import MixConfig, SubtitleStyle, SubtitleVersionRead
from app.timeline_models import TimelineSnapshot, TimelineTrack, TimelineClip


def manifest(language='en',duration=600,styling=False):
    snapshot=TimelineSnapshot(schema_version='1.1',duration_seconds=duration,tracks=[
        TimelineTrack(track_id='trk_source',type='video',kind='source',label='Source',order=0,clips=[
            TimelineClip(clip_id='clip_source',kind='source',label='Source',asset_id='ast_source',
                source_start=0,source_end=duration,timeline_start=0,duration=duration,
                effects=[{'type':'brightness','value':.8},{'type':'saturation','value':.5}] if styling else [],
                metadata={'clip_style_schema':'clip-style-v1'} if styling else {})])])
    subtitles=SubtitleVersionRead(subtitle_version_id='sub_version',package_id='pkg_source',
        project_id='prj_source',timeline_version_id='tlv_source',timeline_version=1,version=1,
        cues=[],style=SubtitleStyle(animation='none'),actor_ref='explicit-test-fixture',created_at=datetime.now(timezone.utc))
    return build_timeline_render_manifest(snapshot=snapshot,subtitles=subtitles,mix_config=MixConfig(),
        mixed_audio_path=Path('/fixture/mix.wav'),asset_paths={'ast_source':(SimpleNamespace(
            content_type='video/mp4',provenance={}),Path('/fixture/source.mp4'))},profile='vertical-1080x1920',
        project_name='Source edit',project_slug='source',niche='technology',brand_name='Fixture',language=language)


def test_canonical_effects_emit_closed_v24_contract_and_old_versions_refuse_extensions():
    value=manifest(styling=True);validator=TimelineRenderContractValidator(Path(__file__).resolve().parents[3]/'packages/contracts/timeline-render.schema.json')
    assert value['version']=='2.4';assert value['visual_clips'][0]['effects']==[{'type':'brightness','value':.8},{'type':'saturation','value':.5}]
    validator.validate(value)
    for version in ('2.0','2.1','2.2','2.3'):
        old=copy.deepcopy(value);old['version']=version
        with pytest.raises(ProductionContractError):validator.validate(old)
    for effect in ({'type':'script','value':1},{'type':'blur','value':.1},{'type':'brightness','value':True}):
        bad=copy.deepcopy(value);bad['visual_clips'][0]['effects']=[effect]
        with pytest.raises(ProductionContractError):validator.validate(bad)


def test_render_crossfade_pair_and_duration_are_validated_before_dispatch():
    value=manifest(styling=True,duration=3);validator=TimelineRenderContractValidator(Path(__file__).resolve().parents[3]/'packages/contracts/timeline-render.schema.json')
    value['visual_clips'][0]['transition_out']={'kind':'fade','duration_seconds':4}
    with pytest.raises(ProductionContractError,match='duration'):validator.validate(value)
    value['visual_clips'][0]['transition_out']={'kind':'crossfade','duration_seconds':.25}
    with pytest.raises(ProductionContractError,match='contiguous'):validator.validate(value)


def test_source_language_duration_and_optional_caption_changes_are_versioned():
    value=manifest();validator=TimelineRenderContractValidator(Path(__file__).resolve().parents[3]/'packages/contracts/timeline-render.schema.json')
    validator.validate(value)
    assert value['version']=='2.3' and value['metadata']['language']=='en' and value['subtitles']==[]
    for version in ('2.0','2.1','2.2'):
        legacy=copy.deepcopy(value);legacy['version']=version
        with pytest.raises(ProductionContractError):validator.validate(legacy)
    invalid=copy.deepcopy(value);invalid['metadata']['duration_seconds']=601
    with pytest.raises(ProductionContractError):validator.validate(invalid)
    with pytest.raises(ProductionContractError,match='Vietnamese or English'):manifest(language='invented')

def test_narrated_visual_viewport_uses_v23_and_cannot_escape_the_canvas():
    value=manifest();validator=TimelineRenderContractValidator(Path(__file__).resolve().parents[3]/'packages/contracts/timeline-render.schema.json')
    value['visual_clips'][0]['viewport']={'x':0,'y':.2,'width':1,'height':.6};validator.validate(value)
    for viewport in ({'x':0,'y':.2,'width':1,'height':.9},{'x':-.1,'y':.2,'width':1,'height':.6},
                     {'x':0,'y':.2,'width':True,'height':.6},{'x':0,'y':.2,'width':1,'height':float('nan')}):
        changed=copy.deepcopy(value);changed['visual_clips'][0]['viewport']=viewport
        with pytest.raises(ProductionContractError):validator.validate(changed)
    legacy=manifest(language='vi',duration=1);legacy['version']='2.2';legacy['visual_clips'][0]['viewport']=value['visual_clips'][0]['viewport']
    with pytest.raises(ProductionContractError,match='viewport'):validator.validate(legacy)
