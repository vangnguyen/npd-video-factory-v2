"""Measured local media and conservative speech-boundary safety; no real ASR claim."""
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import pytest
from app.auto_edit_logic import build_silence_decisions
from app.auto_edit_models import AutoEditAnalysisRequest,MediaMetadata
from app.auto_edit_providers import MediaSignals,ProviderTranscript,ProviderSegment,ProviderWord,require_positive_duration_transcript,FFmpegMediaSignalProvider
from app.timeline_logic import build_initial_timeline
from app.timeline_logic import TimelineEditError
from test_auto_edit_studio import analysis_fixture
from app.platform_models import AssetRead
from datetime import datetime,timezone


def transcript(words):
    return require_positive_duration_transcript(ProviderTranscript(language='vi',confidence=.9,segments=(
        ProviderSegment(start_seconds=1,end_seconds=3,text='Lời nói tiếng Việt.',confidence=.9,speaker=None,words=tuple(words)),),
        provenance={'fixture':True}))


@pytest.mark.parametrize('words',[[],[ProviderWord(start_seconds=1,end_seconds=3,text='Lời nói',confidence=.9)]])
def test_silence_inside_speech_is_blocked_even_without_word_timestamps(words):
    signals=MediaSignals(shot_boundaries=(),silence_intervals=((1.2,2.8,None),(3.2,4.8,None)),provenance={'fixture':True})
    decisions=build_silence_decisions(signals=signals,transcript=transcript(words),config=AutoEditAnalysisRequest(asset_id='ast_safety_fixture'))
    assert not decisions[0]['enabled'] and decisions[0]['conflicts_with_speech']
    assert decisions[1]['enabled'] and not decisions[1]['conflicts_with_speech']
    assert decisions[0]['evidence']['measured_db'] is None and not decisions[0]['evidence']['measured_db_available']
    if not words:assert decisions[0]['evidence']['speech_protection']==['segment_without_word_timestamps']


def asset():
    now=datetime.now(timezone.utc)
    return AssetRead(asset_id='ast_safety_fixture',workspace_id='wsp_safety_fixture',project_id='prj_safety_fixture',
        project_version_id=None,job_id=None,asset_class='uploaded',kind='video',filename='local-fixture.mp4',object_key='workspaces/safety/local-fixture.mp4',
        content_type='video/mp4',size_bytes=100,checksum_sha256='a'*64,storage_provider='local',version=1,provenance={'fixture':True},created_at=now,updated_at=now)


def test_canonical_source_windows_keep_padding_and_revalidate_missing_words():
    source=asset();analysis=analysis_fixture(source.project_id,source.asset_id)
    decision=analysis.silence_decisions[0]
    decision.start_seconds=3.8;decision.end_seconds=4.8;decision.padding_before_seconds=.8;decision.padding_after_seconds=.8
    snap=build_initial_timeline(analysis=analysis,source_asset=source,media_plan=None,media_assets={})
    windows=[(c.source_start,c.source_end) for t in snap.tracks if t.kind=='source' for c in t.clips]
    assert windows==[(0.,3.8),(4.8,5.),(5.,10.)]
    assert snap.metadata['silence_speech_padding_preserved']
    # A stale/provider decision marked safe still cannot override known speech.
    decision.start_seconds=1;decision.end_seconds=2
    snap=build_initial_timeline(analysis=analysis,source_asset=source,media_plan=None,media_assets={})
    assert snap.metadata['silence_decisions_applied']==0
    assert snap.duration_seconds==10


def test_selected_cuts_are_reversible_and_cannot_remove_speech_or_all_footage():
    source=asset();analysis=analysis_fixture(source.project_id,source.asset_id)
    selected=build_initial_timeline(analysis=analysis,source_asset=source,media_plan=None,media_assets={},silence_decision_ids=[])
    assert selected.duration_seconds==10
    assert selected.metadata['silence_review']['selected_ids']==[]
    assert selected.metadata['silence_review']['source_media_mutated'] is False
    for ids in [['sil_foreign_fixture'],['sil_timeline_001']]:
        if ids[0]=='sil_timeline_001':
            analysis.silence_decisions[0].start_seconds=1;analysis.silence_decisions[0].end_seconds=2
        with pytest.raises(TimelineEditError,match='unknown, overlaps speech'):
            build_initial_timeline(analysis=analysis,source_asset=source,media_plan=None,media_assets={},silence_decision_ids=ids)
    analysis.transcript=None
    analysis.silence_decisions[0].start_seconds=0;analysis.silence_decisions[0].end_seconds=10
    with pytest.raises(TimelineEditError,match='no usable source'):
        build_initial_timeline(analysis=analysis,source_asset=source,media_plan=None,media_assets={},silence_decision_ids=['sil_timeline_001'])


@pytest.mark.asyncio
async def test_saved_silence_review_preserves_old_versions_and_requires_fresh_approval(tmp_path):
    from test_transcript_editing import stack,edit
    from app.transcript_editing import edit_transcript
    from app.timeline_service import TimelineService,TimelineContractValidator
    from app.timeline_models import TimelineCreateRequest,TimelineRestoreRequest
    from app.timeline_repository import TimelineConflictError
    from app.repositories import PlatformRepository
    from test_auto_edit_studio import SCHEMA
    engine,sessions,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        service=TimelineService(repository=timelines,platform=PlatformRepository(sessions),auto_edit_repository=repo,
                                media_repository=None,validator=TimelineContractValidator(SCHEMA))
        old=timeline.snapshot.model_dump(mode='json')
        revised=await edit_transcript(repo,project.project_id,analysis.analysis_id,edit(analysis,timeline),'editor')
        latest=await timelines.get_timeline(project.project_id)
        restored=await service.restore(project.project_id,TimelineRestoreRequest(expected_version=latest.current_version,
                                                                               restore_version=timeline.current_version))
        request=TimelineCreateRequest(analysis_id=analysis.analysis_id,silence_decision_ids=[],expected_timeline_version=restored.current_version)
        result=await service.create(project.project_id,request)
        assert result.current_version==restored.current_version+1 and result.approval_status=='draft'
        assert result.snapshot.metadata['transcript_revision']['transcript_id']==analysis.transcript.transcript_id
        assert result.snapshot.metadata['transcript_revision']['transcript_id']!=revised.transcript.transcript_id
        assert (await timelines.get_version_by_id(timeline.current_version_id)).snapshot.model_dump(mode='json')==old
        with pytest.raises(TimelineConflictError):await service.create(project.project_id,request)
        locked=result.snapshot.model_copy(deep=True);locked.tracks[0].locked=True
        saved=await timelines.commit_mutation(project_id=project.project_id,expected_version=result.current_version,
                snapshot=locked,mutation={'type':'fixture-lock'},actor_ref='fixture')
        request.expected_timeline_version=saved.current_version
        with pytest.raises(TimelineEditError,match='unlock'):await service.create(project.project_id,request)
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_real_ffmpeg_detector_does_not_report_threshold_as_measured_energy(tmp_path):
    executable=shutil.which('ffmpeg')
    if not executable:pytest.skip('FFmpeg absent; real local test remains required')
    media=tmp_path/'tone-with-silence.mp4'
    subprocess.run([executable,'-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x240:r=30:d=4',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1.1','-af','adelay=1000,apad=whole_dur=4',
        '-c:v','libx264','-preset','ultrafast','-c:a','aac','-t','4',str(media)],check=True,capture_output=True,timeout=30)
    metadata=MediaMetadata(media_kind='video',detected_content_type='video/mp4',format_name='mp4',duration_seconds=4,
        width=320,height=240,fps=30,video_codec='h264',audio_codec='aac',audio_channels=1,audio_sample_rate=48000)
    signals=await FFmpegMediaSignalProvider(executable).analyze(media,metadata=metadata,silence_threshold_db=-35,minimum_silence_duration=.5)
    assert len(signals.silence_intervals)==2
    assert all(level is None for _,_,level in signals.silence_intervals)
    assert signals.silence_intervals[0][1]==pytest.approx(1,abs=.02)
    assert signals.silence_intervals[1][0]==pytest.approx(2.1,abs=.02)
    assert signals.provenance['fixture'] is False
    waveform=signals.waveform
    assert waveform['measured'] and waveform['duration_seconds']==pytest.approx(4,abs=.05)
    assert len(waveform['bins'])<=1600
    quiet=[b['peak'] for b in waveform['bins'] if .2<b['start_seconds']<.8]
    tone=[b['peak'] for b in waveform['bins'] if 1.2<b['start_seconds']<1.8]
    assert max(quiet)<.001 and min(tone)>.05


@pytest.mark.asyncio
async def test_http_silence_review_is_editor_scoped_with_identity_and_conflict(tmp_path):
    from test_transcript_editing import stack
    from app.main import app
    from app.timeline_service import TimelineService,TimelineContractValidator
    from app.repositories import PlatformRepository
    from test_auto_edit_studio import SCHEMA
    from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
    from httpx import ASGITransport,AsyncClient
    engine,sessions,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        platform=PlatformRepository(sessions)
        app.state.timeline_service=TimelineService(repository=timelines,platform=platform,auto_edit_repository=repo,
                                                    media_repository=None,validator=TimelineContractValidator(SCHEMA))
        body={'analysis_id':analysis.analysis_id,'silence_decision_ids':[],
              'expected_timeline_version':timeline.current_version,'actor_ref':'forged-owner'}
        url=f'/api/v1/projects/{project.project_id}/timeline'
        install_test_human_auth(app,platform_repository=platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post(url,json=body)).status_code==401
            assert (await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)).status_code==403
            install_test_human_auth(app,platform_repository=platform,platform_role='editor',workspace_roles={'*':'editor'})
            changed=await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)
            assert changed.status_code==201
            versions=await timelines.list_versions(project.project_id)
            assert max(versions,key=lambda version:version.version).actor_ref=='usr:test-owner'
            assert (await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)).status_code==409
    finally:await engine.dispose()
