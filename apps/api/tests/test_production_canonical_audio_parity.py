"""Owned PCM/SQLite proof. Visual render, QC and approvals are explicit fixtures."""
import asyncio
import array
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Depends
from sqlalchemy import select, update

from app.db import AssetORM, CostRecordORM, ProviderUsageORM
from app.production_audio import (AudioMixEngine, active_canonical_audio, canonical_audio_graph,
    canonical_audio_input, validate_canonical_audio_receipt, _run_canonical_audio)
from app.production_models import (AudioMixReplaceRequest, MixConfig, VoiceConfig,
    MusicConfig,
    ProductionPackageCreateRequest, RenderCreateRequest, ApprovalRequest, ApprovalDecisionRequest,
    FinalRenderCreateRequest)
from app.production_logic import ProductionContractError, TimelineRenderContractValidator
from app.production_service import ProductionRenderProcessor, DeterministicTimelineRenderEngine
from app.production_qc import DeterministicProductionQC
from app.platform_models import AssetRegister, ProjectCreate
from app.timeline_models import TimelineSnapshot, TimelineTrack, TimelineClip, TransitionSpec
from app.timeline_proxy import FFmpegProxyRenderer
from app.production_repository import ApprovalBoundaryError
from app.production_db import ProductionEventORM, ProductionRenderJobORM
from test_mvp1_multi_input import env, image, author
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS

ROOT = Path(__file__).resolve().parents[3]


def require_ffmpeg():
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Owned local FFmpeg/FFprobe not configured')


async def tone(env, name='voice', *, frequency=880, gated=False, switch=False, rights='owned', project=None,
               amplitude=.12, channels=1):
    project = project or env.project
    path = env.tmp / (name + '.wav')
    samples = array.array('h', (round(amplitude * 32767 * math.sin(2 * math.pi *
        (frequency/2 if switch and n < 48000 else frequency) * n / 48000))
        if not gated or 48000 <= n < 96000 else 0 for n in range(192000)))
    if channels==2:
        samples=array.array('h',(value for value in samples for _ in range(2)))
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((channels, 2, 48000, 0, 'NONE', 'not compressed'))
        wav.writeframes(samples.tobytes())
    stored = await env.storage.put_file(object_key=f'workspaces/{project.workspace_id}/projects/{project.project_id}/inputs/{name}.wav',
        path=path, content_type='audio/wav')
    asset = await env.platform.register_asset(project.project_id, AssetRegister(asset_class='source', kind='audio',
        filename=path.name, object_key=stored.object_key, content_type='audio/wav', size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256, storage_provider='local',
        provenance={'fixture': True, 'rights_status': rights, 'source': 'first-party-mathematical-tone'}))
    return asset, path


def audio_track(asset, kind, order, *, start=0, end=4, speed=1, placement=0, volume=1, fades=False):
    return TimelineTrack(track_id='trk_' + kind + '_audio', type='audio', kind=kind, label=kind, order=order,
        clips=[TimelineClip(clip_id='clip_' + kind + '_audio', kind=kind, label=kind, asset_id=asset.asset_id,
            source_start=start, source_end=end, speed=speed, timeline_start=placement,
            duration=(end-start)/speed, volume=volume,
            transition_in=TransitionSpec(kind='fade', duration_seconds=.15) if fades else TransitionSpec(),
            transition_out=TransitionSpec(kind='fade', duration_seconds=.15) if fades else TransitionSpec())])


async def source_project(env, *, kind='voice', processing=None):
    still = await image(env)
    content = await author(env)
    source, path = await tone(env)
    snapshot = TimelineSnapshot(schema_version='1.1', width=270, height=480, duration_seconds=4,
        tracks=[TimelineTrack(track_id='trk_image', type='video', kind='source', label='Owned template fixture', order=0,
            clips=[TimelineClip(clip_id='clip_image', kind='image', label='Fixture visual', asset_id=still.asset_id,
                timeline_start=0, duration=4)]), audio_track(source, kind, 1),
            TimelineTrack(track_id='trk_subtitles', type='text', kind='subtitles', label='CI fixture caption', order=2,
                clips=[TimelineClip(clip_id='clip_subtitle', kind='subtitle', label='Fixture audio',
                    source_start=0, source_end=4, timeline_start=0, duration=4)])],
        metadata={'content_version_id': content.project_version_id,
            **({'source_audio_processing': processing} if processing is not None else {})})
    await env.timeline.create_timeline(project_id=env.project.project_id, source_analysis_id=None,
        source_media_plan_id=None, source_content_version_id=content.project_version_id,
        snapshot=snapshot, actor_ref='explicit-fixture-editor')
    package = await env.package.create_or_refresh(env.project.project_id, ProductionPackageCreateRequest())
    return SimpleNamespace(source=source, path=path, snapshot=snapshot, package=package)


async def disabled_package(env, value):
    return await env.package.replace_audio_mix(env.project.project_id, AudioMixReplaceRequest(
        expected_timeline_version=1, expected_audio_version=value.package.audio_mix.version,
        config=MixConfig(voice=VoiceConfig(enabled=False))))


class PoisonTTS:
    calls = 0
    async def synthesize(self, **kwargs):
        self.calls += 1
        raise AssertionError('Canonical Source-mode must not synthesize')


def processor(env, *, audio=None):
    return ProductionRenderProcessor(repository=env.production, platform=env.platform,
        asset_repository=env.assets, object_storage=env.storage,
        renderer=DeterministicTimelineRenderEngine(), qc=DeterministicProductionQC(),
        tts_provider=PoisonTTS(), audio_engine=audio or AudioMixEngine(),
        manifest_validator=TimelineRenderContractValidator(ROOT/'packages/contracts/timeline-render.schema.json'),
        staging_root=env.tmp/'renders', brand_name='Explicit nonplayable visual/QC fixture')


async def queue_review(env, package):
    return await env.package.enqueue_review(env.project.project_id, RenderCreateRequest(
        expected_timeline_version=1, expected_subtitle_version=package.subtitle.version,
        expected_audio_version=package.audio_mix.version))


async def fixture_final(env, reviewed):
    approval = await env.package.request_approval(env.project.project_id,
        ApprovalRequest(review_render_id=reviewed.render_id, requester_ref='explicit-fixture-reviewer'))
    await env.package.decide_approval(env.project.project_id, approval.approval_id,
        ApprovalDecisionRequest(decision='approved', reviewer_ref='explicit-fixture-reviewer',
            comment='CI fixture decision, never Owner UAT'))
    return await env.package.enqueue_final(env.project.project_id, FinalRenderCreateRequest(
        expected_timeline_version=reviewed.timeline_version, expected_subtitle_version=reviewed.subtitle_version,
        expected_audio_version=reviewed.audio_version, approval_id=approval.approval_id))


@pytest.mark.parametrize('kind', ['voice', 'music', 'sfx'])
async def test_voice_disabled_accepts_active_canonical_sources_without_tts(env, kind):
    value = await source_project(env, kind=kind)
    package = await disabled_package(env, value)
    assert package.audio_mix.config.voice.enabled is False
    assert (await env.timeline.get_timeline(env.project.project_id)).snapshot == value.snapshot
    assert await env.platform.list_cost_records(env.project.project_id) == []


async def test_actual_asgi_audio_mix_auth_and_sql_accept_canonical_voice(env):
    from app.production_routes import router
    from app.human_auth import authorize_human_request
    value = await source_project(env)
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(authorize_human_request)])
    app.state.production_package_service = env.package
    install_test_human_auth(app, platform_repository=env.platform, platform_role=None,
        workspace_roles={env.workspace.workspace_id:'viewer'})
    body = AudioMixReplaceRequest(expected_timeline_version=1, expected_audio_version=1,
        config=MixConfig(voice=VoiceConfig(enabled=False))).model_dump(mode='json')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://isolated-canonical-fixture') as client:
        denied=await client.put(f'/api/v1/projects/{env.project.project_id}/audio-mix',json=body,headers=TEST_HUMAN_HEADERS)
        assert denied.status_code==403
        install_test_human_auth(app, platform_repository=env.platform, platform_role=None,
            workspace_roles={env.workspace.workspace_id:'editor'})
        accepted=await client.put(f'/api/v1/projects/{env.project.project_id}/audio-mix',json=body,headers=TEST_HUMAN_HEADERS)
        assert accepted.status_code==200,accepted.text
        assert accepted.json()['audio_mix']['config']['voice']['enabled'] is False
    assert (await env.timeline.get_timeline(env.project.project_id)).snapshot==value.snapshot
    assert await env.platform.list_cost_records(env.project.project_id)==[]


@pytest.mark.parametrize('state', ['muted', 'disabled', 'zero'])
async def test_inaudible_canonical_sources_do_not_authorize_a_silent_mix(env, state):
    value = await source_project(env)
    changed = value.snapshot.model_copy(deep=True)
    if state == 'zero':
        changed.tracks[1].clips[0].volume = 0
    else:
        setattr(changed.tracks[1], state, True)
    await env.timeline.commit_mutation(project_id=env.project.project_id, expected_version=1,
        snapshot=changed, mutation={'type':'explicit-fixture'}, actor_ref='explicit-fixture-editor')
    with pytest.raises(ProductionContractError, match='audio mix must'):
        await env.package.replace_audio_mix(env.project.project_id, AudioMixReplaceRequest(
            expected_timeline_version=2, expected_audio_version=1, config=MixConfig(voice=VoiceConfig(enabled=False))))


async def test_canonical_music_cannot_bypass_existing_rights_validation(env):
    value = await source_project(env, kind='music')
    async with env.factory() as session, session.begin():
        await session.execute(update(AssetORM).where(AssetORM.asset_id == value.source.asset_id)
            .values(provenance={'rights_status':'unknown','fixture':True}))
    with pytest.raises(ProductionContractError, match='rights metadata'):
        await disabled_package(env, value)


async def test_worker_rejects_foreign_canonical_audio_before_synthesis(env):
    value = await source_project(env)
    package = await disabled_package(env, value)
    foreign = await env.platform.create_project(env.workspace.workspace_id,
        ProjectCreate(slug='foreign-canonical-fixture', name='Owned foreign fixture'))
    async with env.factory() as session, session.begin():
        await session.execute(update(AssetORM).where(AssetORM.asset_id == value.source.asset_id)
            .values(project_id=foreign.project_id))
    job = await queue_review(env, package)
    p = processor(env)
    failed = await p.process(job.render_id)
    assert failed.status == 'failed' and 'unavailable' in failed.failure_reason
    assert p.tts_provider.calls == 0 and await env.platform.list_cost_records(env.project.project_id) == []


def pcm(path):
    with wave.open(str(path), 'rb') as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (2,2,48000)
        count = wav.getnframes()
        return count, wav.readframes(count)


async def test_actual_pcm_matches_canonical_trim_tempo_gain_fades_and_source_receipt(env, monkeypatch):
    require_ffmpeg()
    voice, voice_path = await tone(env, switch=True)
    music, music_path = await tone(env, 'music', frequency=220)
    sfx, sfx_path = await tone(env, 'sfx', frequency=1320)
    snapshot = TimelineSnapshot(duration_seconds=4, tracks=[
        audio_track(voice,'voice',0,start=1,end=3,speed=2,placement=.5,volume=.5,fades=True),
        audio_track(music,'music',1,volume=.25),
        audio_track(sfx,'sfx',2,start=.2,end=.4,placement=3,volume=.2)])
    assets={a.asset_id:(a,p) for a,p in [(voice,voice_path),(music,music_path),(sfx,sfx_path)]}
    before={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,(_,path) in assets.items()}
    config=MixConfig(voice=VoiceConfig(enabled=False))
    output=env.tmp/'canonical.wav'
    from app import production_audio
    run=production_audio._run_canonical_audio
    async def captured(command, **kwargs):
        (env.tmp/'canonical-argv.json').write_text(json.dumps(command, indent=2))
        return await run(command, **kwargs)
    monkeypatch.setattr(production_audio,'_run_canonical_audio',captured)
    result=await AudioMixEngine().mix_canonical_timeline(snapshot=snapshot,assets=assets,config=config,
        base_audio_path=None,output_path=output,is_cancelled=lambda:asyncio.sleep(0,result=False))
    graph=canonical_audio_graph(snapshot,assets,config,first_input_index=0)
    filters=env.tmp/'reference.filters';filters.write_text(';'.join(graph.filters))
    reference=env.tmp/'reference.wav'
    completed=subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-copyts','-start_at_zero',
        *graph.inputs,'-filter_complex_threads','1','-/filter_complex',str(filters),'-map','[outa]',
        '-ar','48000','-ac','2','-c:a','pcm_s16le','-t','4','-fs',str(192001*4+65536),
        str(reference)],capture_output=True,timeout=15)
    assert completed.returncode==0,completed.stderr[-300:]
    assert pcm(output)==pcm(reference) and pcm(output)[0]==192000
    # FFmpeg's canonical mono -> stereo matrix applies -3 dB per channel.
    channel_gain=1/math.sqrt(2)
    assert amplitude(output,880,1.0,1.2)==pytest.approx(.06*channel_gain,rel=.04)
    assert amplitude(output,440,.8,1.0)<.001  # The first source second was trimmed away.
    assert amplitude(output,880,.2,.4)<.001 and amplitude(output,880,1.7,1.9)<.001
    assert amplitude(output,880,.52,.57)<amplitude(output,880,1.0,1.2)*.5
    assert amplitude(output,220,2.0,2.2)==pytest.approx(.03*channel_gain,rel=.04)
    assert amplitude(output,1320,3.0,3.2)==pytest.approx(.024*channel_gain,rel=.08)
    proof=validate_canonical_audio_receipt(result['canonical_timeline_audio'],snapshot,assets,config)
    assert len(proof.audio_clip_receipts)==3 and proof.external_provider_calls==0
    assert {key:hashlib.sha256(path.read_bytes()).hexdigest() for key,(_,path) in assets.items()}==before


def amplitude(path, frequency, start, end):
    count,data=pcm(path);values=array.array('h');values.frombytes(data)
    if sys.byteorder!='little':values.byteswap()
    samples=[v/32768 for v in values[::2]][int(start*48000):int(end*48000)]
    real=sum(v*math.cos(2*math.pi*frequency*n/48000) for n,v in enumerate(samples))
    imag=sum(v*math.sin(2*math.pi*frequency*n/48000) for n,v in enumerate(samples))
    return 2*math.hypot(real,imag)/len(samples)


async def test_actual_normalization_keeps_gain_and_ducking_uses_voice_energy(env):
    require_ffmpeg()
    voice,vp=await tone(env,gated=True);music,mp=await tone(env,'music',frequency=220)
    assets={voice.asset_id:(voice,vp),music.asset_id:(music,mp)}
    snapshot=TimelineSnapshot(duration_seconds=4,tracks=[audio_track(voice,'voice',0),audio_track(music,'music',1,volume=.3)],
        metadata={'source_audio_processing':{'normalize_original_audio':True,'normalize_music':True,'duck_music':True}})
    engine=AudioMixEngine();config=MixConfig(voice=VoiceConfig(enabled=False))
    first=env.tmp/'normalized.wav';half=env.tmp/'half.wav'
    result=await engine.mix_canonical_timeline(snapshot=snapshot,assets=assets,config=config,base_audio_path=None,
        output_path=first,is_cancelled=lambda:asyncio.sleep(0,result=False))
    snapshot.tracks[0].clips[0].volume=.5
    await engine.mix_canonical_timeline(snapshot=snapshot,assets=assets,config=config,base_audio_path=None,
        output_path=half,is_cancelled=lambda:asyncio.sleep(0,result=False))
    assert amplitude(half,880,1.2,1.6)==pytest.approx(amplitude(first,880,1.2,1.6)*.5,rel=.03)
    assert amplitude(first,220,1.2,1.6)<amplitude(first,220,.3,.7)*.65
    proof=result['canonical_timeline_audio']
    assert proof['audio_processing']['music_ducking'] and not proof['audio_processing']['speech_detection_performed']
    assert proof['audio_processing']['measured_integrated_loudness'] is None


async def test_sql_proxy_reads_processing_metadata_at_real_graph_boundary(env,monkeypatch):
    from app import timeline_proxy
    source,path=await tone(env)
    snapshot=TimelineSnapshot(duration_seconds=4,tracks=[audio_track(source,'voice',0)],
        metadata={'source_audio_processing':{'normalize_original_audio':True}})
    actual=timeline_proxy.build_processed_audio_graph;seen=[]
    def boundary(*args,**kwargs):
        graph=actual(*args,**kwargs);seen.append(graph.processing)
        raise RuntimeError('EXPLICIT_STOP_BEFORE_VIDEO_ENCODER')
    monkeypatch.setattr(timeline_proxy,'build_processed_audio_graph',boundary)
    with pytest.raises(RuntimeError,match='EXPLICIT_STOP'):
        await FFmpegProxyRenderer().render(snapshot=snapshot,assets={source.asset_id:(source,path)},
            output_path=env.tmp/'never-rendered.mp4',width=270,height=480,
            is_cancelled=lambda:asyncio.sleep(0,result=False))
    assert seen[0]['configuration']['normalize_original_audio'] is True
    assert not (env.tmp/'never-rendered.mp4').exists()


@pytest.mark.parametrize('processing',[False,[],{'duck_music':1},{'filter':'arbitrary'}])
async def test_untyped_processing_is_rejected_before_provider_or_source_io(env,processing,monkeypatch):
    value=await source_project(env,processing=processing)
    package=await disabled_package(env,value);job=await queue_review(env,package);p=processor(env)
    async def denied(*args,**kwargs):raise AssertionError('Invalid processing must not stage or synthesize')
    monkeypatch.setattr(p,'_download_render_asset',denied)
    failed=await p.process(job.render_id)
    assert failed.status=='failed' and p.tts_provider.calls==0
    assert 'Invalid processing must not' not in failed.failure_reason


async def test_review_final_reuses_approved_canonical_pcm_without_tts_dsp_or_phantom_cost(env):
    require_ffmpeg()
    value=await source_project(env);package=await disabled_package(env,value)
    p=processor(env);reviewed=await p.process((await queue_review(env,package)).render_id)
    assert reviewed.status=='awaiting_review',reviewed.failure_reason
    target=await fixture_final(env,reviewed)
    class PoisonAudio:
        def __getattr__(self,name):raise AssertionError('Final must only copy approved prepared PCM')
    final=await processor(env,audio=PoisonAudio()).process(target.render_id)
    assert final.status=='ready',final.failure_reason
    assert final.manifest['mix']['canonical_timeline_audio']==reviewed.manifest['mix']['canonical_timeline_audio']
    for job in (reviewed,final):
        asset=await env.assets.get_asset(job.manifest['supporting_asset_ids']['audio-mix'])
        assert asset.checksum_sha256==reviewed.manifest['mix']['canonical_timeline_audio']['output_sha256']
    async with env.factory() as session:
        usage=(await session.scalars(select(ProviderUsageORM))).all()
        assert usage and all(row.capability!='tts' for row in usage)
    assert p.tts_provider.calls==0 and final.publishing_allowed is False


async def test_canonical_voice_preserves_explicit_legacy_music_mix_and_separate_narration(env):
    require_ffmpeg()
    value=await source_project(env)
    music,_=await tone(env,'explicit-legacy-bed',frequency=220)
    package=await env.package.replace_audio_mix(env.project.project_id,AudioMixReplaceRequest(
        expected_timeline_version=1,expected_audio_version=1,
        config=MixConfig(voice=VoiceConfig(enabled=False),music=MusicConfig(asset_id=music.asset_id,
            gain_db=-3,ducking_db=-3,fade_in_seconds=0,fade_out_seconds=0))))
    p=processor(env);reviewed=await p.process((await queue_review(env,package)).render_id)
    assert reviewed.status=='awaiting_review',reviewed.failure_reason
    assert reviewed.manifest['mix']['legacy_base_mix']['configured'] is True
    assert reviewed.manifest['mix']['legacy_base_mix']['ducking_applied'] is True
    assert reviewed.manifest['mix']['ducking_applied'] is True
    assert reviewed.manifest['mix']['canonical_timeline_audio']['legacy_base_sha256']
    raw=await env.assets.get_asset(reviewed.manifest['supporting_asset_ids']['narration-track'])
    mixed=await env.assets.get_asset(reviewed.manifest['supporting_asset_ids']['audio-mix'])
    raw_path=env.tmp/'raw-narration.wav'
    await env.storage.download_file(object_key=raw.object_key,destination=raw_path,
        max_bytes=raw.size_bytes,expected_size_bytes=raw.size_bytes,expected_sha256=raw.checksum_sha256)
    with wave.open(str(raw_path),'rb') as wav:
        assert wav.getnchannels()==1 and not any(wav.readframes(wav.getnframes()))
    assert raw.checksum_sha256!=mixed.checksum_sha256 and p.tts_provider.calls==0


@pytest.mark.parametrize('change',['missing_receipt','source_custody'])
async def test_old_or_changed_canonical_proof_requires_fresh_review_without_final_dsp(env,change):
    require_ffmpeg()
    value=await source_project(env);package=await disabled_package(env,value)
    reviewed=await processor(env).process((await queue_review(env,package)).render_id)
    assert reviewed.status=='awaiting_review',reviewed.failure_reason
    if change=='missing_receipt':
        async with env.factory() as session,session.begin():
            row=await session.get(ProductionRenderJobORM,reviewed.render_id)
            manifest=copy.deepcopy(row.manifest_json);manifest['mix'].pop('canonical_timeline_audio');row.manifest_json=manifest
    target=await fixture_final(env,await env.production.get_render(reviewed.render_id))
    if change=='source_custody':
        async with env.factory() as session,session.begin():
            row=await session.get(AssetORM,value.source.asset_id)
            row.provenance={**row.provenance,'changed_after_review':True}
    class PoisonAudio:
        def __getattr__(self,name):raise AssertionError('Do not remaster a stale final')
    failed=await processor(env,audio=PoisonAudio()).process(target.render_id)
    assert failed.status=='failed' and 'FRESH_REVIEW_REQUIRED' in failed.failure_reason


async def test_second_cancel_drains_owned_child_before_output_cleanup(env,monkeypatch):
    from app import production_audio
    real_spawn=asyncio.create_subprocess_exec;entered=asyncio.Event();gate=asyncio.Event();held=[]
    async def spawn(*args,**kwargs):
        process=await real_spawn(*args,**kwargs);stream=process.stderr
        class Reader:
            first=True
            async def read(self,size):
                if not self.first:await gate.wait()
                data=await stream.read(size);self.first=False;entered.set();return data
        process.stderr=Reader();held.append(process);return process
    monkeypatch.setattr(production_audio.asyncio,'create_subprocess_exec',spawn)
    output=env.tmp/'unfinished.wav';output.write_bytes(b'explicit-owned-output')
    # Direct base interpreter avoids the Windows venv launcher redirector.
    task=asyncio.create_task(_run_canonical_audio([sys._base_executable,'-c',
        'import sys,time;sys.stderr.write("READY");sys.stderr.flush();time.sleep(10)'],
        output_path=output,is_cancelled=lambda:asyncio.sleep(0,result=False),timeout_seconds=20))
    await asyncio.wait_for(entered.wait(),5);task.cancel();await asyncio.sleep(.05);task.cancel();await asyncio.sleep(.05)
    assert not task.done() and output.exists()
    gate.set()
    with pytest.raises(asyncio.CancelledError):await asyncio.wait_for(task,5)
    assert held[0].returncode is not None and not output.exists()


@pytest.mark.parametrize('change',['source','cancel','legacy_music'])
async def test_terminal_writer_rechecks_after_flush_and_rolls_back_completion(env,monkeypatch,change):
    require_ffmpeg()
    value=await source_project(env);package=await disabled_package(env,value)
    target_source=value.source
    if change=='legacy_music':
        target_source,_=await tone(env,'terminal-legacy-bed',frequency=220)
        package=await env.package.replace_audio_mix(env.project.project_id,AudioMixReplaceRequest(
            expected_timeline_version=1,expected_audio_version=package.audio_mix.version,
            config=MixConfig(voice=VoiceConfig(enabled=False),music=MusicConfig(asset_id=target_source.asset_id,
                gain_db=-3,ducking_db=-3,fade_in_seconds=0,fade_out_seconds=0))))
    original=env.production._event;injected=[]
    async def boundary(session,**kwargs):
        await original(session,**kwargs)
        if kwargs.get('event_type')=='render.review_completed':
            await session.flush()
            if change in {'source','legacy_music'}:
                await session.execute(update(AssetORM).where(AssetORM.asset_id==target_source.asset_id)
                    .values(version=AssetORM.version+1))
            else:
                await session.execute(update(ProductionRenderJobORM).where(ProductionRenderJobORM.render_id==kwargs['entity_id'])
                    .values(cancellation_requested=True))
            injected.append(change)
    monkeypatch.setattr(env.production,'_event',boundary)
    queued=await queue_review(env,package);failed=await processor(env).process(queued.render_id)
    assert injected==[change] and failed.status=='failed'
    async with env.factory() as session:
        row=await session.get(ProductionRenderJobORM,queued.render_id)
        assert row.output_asset_id is None and row.qc_status!='passed'
        events=(await session.scalars(select(ProductionEventORM).where(ProductionEventORM.entity_id==queued.render_id))).all()
        assert not any(event.event_type=='render.review_completed' for event in events)
        assert (await session.get(AssetORM,target_source.asset_id)).version==target_source.version
        assert (await session.scalars(select(CostRecordORM))).all()==[]


@pytest.mark.parametrize('change',['source','cancel'])
async def test_other_sql_instance_wins_after_service_check_before_writer_lock(env,monkeypatch,change):
    """Independent committed SQL mutation after all service IO; no fake lock."""
    from app.production_repository import ProductionRepository
    require_ffmpeg()
    value=await source_project(env);package=await disabled_package(env,value)
    original=env.production._canonical_audio_terminal_fence
    entered,resume=asyncio.Event(),asyncio.Event()
    async def paused(session,row,manifest,**kwargs):
        if kwargs.get('lock'):
            entered.set();await resume.wait()
        return await original(session,row,manifest,**kwargs)
    monkeypatch.setattr(env.production,'_canonical_audio_terminal_fence',paused)
    queued=await queue_review(env,package)
    task=asyncio.create_task(processor(env).process(queued.render_id))
    try:
        await asyncio.wait_for(entered.wait(),20)
        if change=='source':
            async with env.factory() as session,session.begin():
                await session.execute(update(AssetORM).where(AssetORM.asset_id==value.source.asset_id)
                    .values(version=AssetORM.version+1))
        else:
            await ProductionRepository(env.factory).cancel_render(env.project.project_id,queued.render_id,
                actor_ref='other-explicit-fixture-editor')
        resume.set();result=await asyncio.wait_for(task,20)
        assert result.status==('failed' if change=='source' else 'cancelled')
        async with env.factory() as session:
            row=await session.get(ProductionRenderJobORM,queued.render_id)
            assert row.output_asset_id is None and row.qc_status!='passed'
            events=(await session.scalars(select(ProductionEventORM).where(
                ProductionEventORM.entity_id==queued.render_id))).all()
            assert not any(event.event_type=='render.review_completed' for event in events)
            assert (await session.get(AssetORM,value.source.asset_id)).version==value.source.version+(change=='source')
            assert (await session.scalars(select(CostRecordORM))).all()==[]
    finally:
        resume.set()
        if not task.done():
            task.cancel();await asyncio.gather(task,return_exceptions=True)


async def test_late_qc_exception_preserves_other_worker_terminal_decision(env,monkeypatch):
    from app.production_qc import ProductionQCError
    from test_render_terminal_observation import rows
    require_ffmpeg()
    value=await source_project(env);package=await disabled_package(env,value)
    queued=await queue_review(env,package);p=processor(env);captured=[]
    async def rejected(*args,**kwargs):
        await env.production.fail_render(queued.render_id,code='FIRST_WORKER_FIXTURE_FAILURE',
            reason='Separate terminal worker fixture decision; no Owner/QC acceptance')
        captured.append(await rows(env))
        raise ProductionQCError('LATE_SECOND_WORKER_QC_FIXTURE',{'status':'failed','fixture':True})
    monkeypatch.setattr(p.qc,'inspect',rejected)
    result=await p.process(queued.render_id)
    assert result.error_code=='FIRST_WORKER_FIXTURE_FAILURE'
    assert await rows(env)==captured[0]


async def test_canonical_writer_cannot_bypass_receipt_by_omitting_manifest_field(env):
    value=await source_project(env);package=await disabled_package(env,value)
    queued=await queue_review(env,package);await env.production.start_render(queued.render_id)
    with pytest.raises(ApprovalBoundaryError,match='CANONICAL_AUDIO_COMPLETION_PROOF_REQUIRED'):
        await env.production.complete_render(queued.render_id,output_asset_id=None,
            qc_report={'fixture':True,'not_real_render_qc':True},manifest={'fixture':True})
    row=await env.production.get_render(queued.render_id)
    assert row.status=='running' and row.qc_status!='passed' and row.output_asset_id is None
    assert await env.platform.list_cost_records(env.project.project_id)==[]


@pytest.mark.parametrize('limit',[-3,-.1])
@pytest.mark.parametrize('base',[False,True])
async def test_actual_pcm_terminal_limiter_matches_saved_config_and_receipt(env,limit,base):
    require_ffmpeg()
    source,path=await tone(env,amplitude=.97,channels=2)
    snapshot=TimelineSnapshot(duration_seconds=4,tracks=[audio_track(source,'voice',0,volume=2)])
    assets={source.asset_id:(source,path)}
    config=MixConfig(voice=VoiceConfig(enabled=False),limiter_peak_db=limit)
    base_path=None
    if base:
        _,base_path=await tone(env,'explicit-base',frequency=220,amplitude=.6,channels=2)
    output=env.tmp/'limited.wav'
    result=await AudioMixEngine().mix_canonical_timeline(snapshot=snapshot,assets=assets,config=config,
        base_audio_path=base_path,output_path=output,is_cancelled=lambda:asyncio.sleep(0,result=False))
    count,data=pcm(output);samples=array.array('h');samples.frombytes(data)
    if sys.byteorder!='little':samples.byteswap()
    peak=max(map(abs,samples))/32768;ceiling=math.pow(10,limit/20)
    assert count==192000 and output.stat().st_size<=833540
    assert ceiling-3/32768<=peak<=ceiling+2/32768
    receipt=validate_canonical_audio_receipt(result['canonical_timeline_audio'],snapshot,assets,config)
    assert receipt.audio_processing['limiter_peak_db']==result['limiter_peak_db']==limit
    assert bool(receipt.legacy_base_sha256)==base
    # Shared proxy defaults retain their original limiter even when production
    # has explicitly selected a different ceiling.
    from app.timeline_audio_processing import build_processed_audio_graph
    proxy=build_processed_audio_graph(snapshot,assets,first_input_index=0)
    assert proxy.processing['limiter_peak_db']==-1
