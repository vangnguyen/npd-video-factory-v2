"""Shared JSON contract must match native/source renderer capabilities and legacy guards."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import copy

import pytest
from app.production_logic import build_timeline_render_manifest, TimelineRenderContractValidator, ProductionContractError
from app.production_models import MixConfig, SubtitleStyle, SubtitleVersionRead
from app.timeline_models import TimelineSnapshot, TimelineTrack, TimelineClip


def manifest(language='en',duration=600):
    snapshot=TimelineSnapshot(schema_version='1.1',duration_seconds=duration,tracks=[
        TimelineTrack(track_id='trk_source',type='video',kind='source',label='Source',order=0,clips=[
            TimelineClip(clip_id='clip_source',kind='source',label='Source',asset_id='ast_source',
                source_start=0,source_end=duration,timeline_start=0,duration=duration)])])
    subtitles=SubtitleVersionRead(subtitle_version_id='sub_version',package_id='pkg_source',
        project_id='prj_source',timeline_version_id='tlv_source',timeline_version=1,version=1,
        cues=[],style=SubtitleStyle(animation='none'),actor_ref='explicit-test-fixture',created_at=datetime.now(timezone.utc))
    return build_timeline_render_manifest(snapshot=snapshot,subtitles=subtitles,mix_config=MixConfig(),
        mixed_audio_path=Path('/fixture/mix.wav'),asset_paths={'ast_source':(SimpleNamespace(
            content_type='video/mp4',provenance={}),Path('/fixture/source.mp4'))},profile='vertical-1080x1920',
        project_name='Source edit',project_slug='source',niche='technology',brand_name='Fixture',language=language)


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
