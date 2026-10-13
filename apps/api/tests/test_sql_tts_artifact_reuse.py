"""Owned SQL + synthetic PCM/MockTransport. No model, provider or Owner acceptance."""
import asyncio
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import wave
from datetime import timedelta
import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.db import Base, ProviderUsageORM, utc_now
from app.production_audio import AudioMixEngine
from app.production_db import ProductionRenderJobORM
from app.production_logic import TimelineRenderContractValidator, PROFILE_DIMENSIONS
from app.production_models import (ProductionPackageCreateRequest, RenderCreateRequest, FinalRenderCreateRequest,
    ApprovalRequest, ApprovalDecisionRequest)
from app.production_qc import DeterministicProductionQC
from app.production_service import ProductionRenderProcessor, DeterministicTimelineRenderEngine
from app.production_repository import ProductionRepository
from app.sql_tts_artifact_reuse import TTSArtifactReuseRepository, digest
from app.sql_tts_artifact_reuse_db import TTSArtifactReuseORM
from app.vieneu_contracts import VieNeuTTSProfile, VieNeuLicenseProvenance
from app.vieneu_tts_provider import VieNeuTTSProvider
from test_mvp1_multi_input import env, author, timeline, ROOT


def raw_pcm(amplitude=4096):
    data=io.BytesIO()
    with wave.open(data,'wb') as sound:
        sound.setnchannels(1);sound.setsampwidth(2);sound.setframerate(48000)
        sound.writeframes(int(amplitude).to_bytes(2,'little',signed=True)*24000)
    return data.getvalue()


def transport(state):
    async def wire(request):
        state['calls'].append(json.loads(request.content))
        if state.get('entered') is not None:
            state['entered'].set();await state['resume'].wait()
        if state.get('failure'):
            raise RuntimeError('EXPLICIT SYNTHETIC UNKNOWN TRANSPORT OUTCOME')
        selected=VieNeuTTSProfile.model_validate(state['calls'][-1]['profile'])
        provider=state['provider']
        return httpx.Response(200,content=raw_pcm(4096 if len(state['calls'])==1 else 8192),headers={
            'x-vieneu-profile-sha256':selected.sha256,'x-vieneu-server-sha256':provider.server_sha,
            'x-vieneu-normalization-sha256':'2'*64})
    return httpx.MockTransport(wire)


class OwnedPCMFixtureEngine(AudioMixEngine):
    """Exercise real scheduling/PCM/cache custody, with explicit fixture DSP.

    This isn't normalization/ducking/renderer/media quality acceptance. Linux
    CI has no FFmpeg; no package install or real provider is required here.
    """
    async def _normalize_chunk(self, source, destination, *, speed):
        assert speed==1
        shutil.copyfile(source,destination)

    async def mix(self, *, narration_path, music_path, cues, config, duration_seconds, output_path):
        assert music_path is None
        shutil.copyfile(narration_path,output_path)
        return {'engine':'explicit-synthetic-identity-mix','fixture':True,'configured':False,
            'sample_rate':48000,'duration_seconds':duration_seconds,'ducking_applied':False}


def processor(env, provider):
    return ProductionRenderProcessor(repository=ProductionRepository(env.factory),platform=env.platform,
        asset_repository=env.assets,object_storage=env.storage,renderer=DeterministicTimelineRenderEngine(),
        qc=DeterministicProductionQC(),tts_provider=provider,audio_engine=OwnedPCMFixtureEngine(),
        manifest_validator=TimelineRenderContractValidator(ROOT/'packages/contracts/timeline-render.schema.json'),
        staging_root=env.tmp/'render-reuse',brand_name='EXPLICIT MOCK FIXTURE')


async def ready(env, state=None):
    version=await author(env,original='Xin chào.')
    built=await timeline(env,version)
    await env.platform.seed_providers([{'provider_key':'vieneu-tts','display_name':'EXPLICIT MOCK TTS',
        'capability':'tts','adapter':'mock','routing_mode':'primary','status':'healthy','enabled':True,
        'supports_dry_run':True,'metadata':{'fixture':True,'real_provider_tested':False}}])
    state=state or {'calls':[]}
    state['provider']=VieNeuTTSProvider(VieNeuTTSProfile(voice_id='Mai Anh',rights=VieNeuLicenseProvenance()),
        local_execution_enabled=True,transport=transport(state))
    job=processor(env,state['provider'])
    package=await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    review=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(expected_timeline_version=built.current_version,
        expected_subtitle_version=package.subtitle.version,expected_audio_version=package.audio_mix.version))
    return state,job,version,review


async def final(env, review):
    approval=await env.package.request_approval(env.project.project_id,ApprovalRequest(review_render_id=review.render_id))
    approval=await env.package.decide_approval(env.project.project_id,approval.approval_id,
        ApprovalDecisionRequest(decision='approved',reviewer_ref='explicit-synthetic-reviewer',comment='Fixture only; no Owner UAT'))
    return await env.package.enqueue_final(env.project.project_id,FinalRenderCreateRequest(
        expected_timeline_version=review.timeline_version,expected_subtitle_version=review.subtitle_version,
        expected_audio_version=review.audio_version,approval_id=approval.approval_id))


async def entries(env):
    async with env.factory() as session:
        return (await session.scalars(select(TTSArtifactReuseORM))).all()


@pytest.mark.asyncio
async def test_actual_sql_review_final_cold_processor_reuses_immutable_pcm_without_billing_again(env):
    state,job,version,review=await ready(env)
    reviewed=await job.process(review.render_id)
    assert reviewed.status=='awaiting_review',reviewed.failure_reason
    assert len(state['calls'])==1
    row=(await entries(env))[0];original=copy.deepcopy(row.result_json)
    prior_costs=await env.platform.list_cost_records(env.project.project_id)
    assert any(cost.actual_cost is None for cost in prior_costs)
    target=await final(env,reviewed)
    def denied(_):raise AssertionError('DeniedWire: cache hit must not call a provider')
    fresh=VieNeuTTSProvider(state['provider'].profile,local_execution_enabled=True,transport=httpx.MockTransport(denied))
    rendered=await processor(env,fresh).process(target.render_id)
    assert rendered.status=='ready',rendered.failure_reason
    assert len(state['calls'])==1 and (await entries(env))[0].result_json==original
    unit=rendered.manifest['narration']['timing'][0]
    assert unit['provider_evidence']==original['original_evidence']
    assert unit['prepared_audio_reused'] is True
    receipt=rendered.manifest['narration']['prepared_audio_reuse']
    assert receipt['source_review_render_id']==reviewed.render_id and receipt['target_render_id']==target.render_id
    assert receipt['provider_calls']==receipt['credential_reads']==0
    assert receipt['approval_transferred_to_assets'] is False and receipt['rights_authority_transferred'] is False
    after=await env.platform.list_cost_records(env.project.project_id)
    assert after[:len(prior_costs)]==prior_costs
    async with env.factory() as session:
        usage=await session.scalar(select(ProviderUsageORM).where(
            ProviderUsageORM.operation=='tts-artifact-reuse.v1.'+target.render_id))
        assert usage.metadata_json['provider_call_performed'] is False
        assert usage.metadata_json['additional_provider_billed_cost_vnd']==0
        assert usage.metadata_json['past_provider_billing_rewritten'] is False
    assert rendered.publishing_allowed is False


@pytest.mark.asyncio
async def test_four_canvases_keep_same_units_but_require_fresh_review_and_target_receipts(env):
    state,job,version,review=await ready(env)
    first=await job.process(review.render_id)
    assert first.status=='awaiting_review',first.failure_reason
    original=(await entries(env))[0].result_json
    profiles={'16:9':'review-960x540','9:16':'review-540x960','1:1':'review-540x540','4:5':'review-432x540'}
    for ratio,profile in profiles.items():
        previous=await env.timeline.get_timeline(env.project.project_id)
        shape=previous.snapshot.model_copy(deep=True)
        shape.width,shape.height={'16:9':(1920,1080),'9:16':(1080,1920),'1:1':(1080,1080),'4:5':(1080,1350)}[ratio]
        shape.aspect_ratio=ratio;shape.metadata['reframe']={'aspect_ratio':ratio,'needs_attention':True}
        changed=await env.timeline.commit_mutation(project_id=env.project.project_id,expected_version=previous.current_version,
            snapshot=shape,mutation={'type':'explicit-fixture-canvas'},actor_ref='fixture-editor')
        package=await env.package.create_or_refresh(env.project.project_id,
            ProductionPackageCreateRequest(expected_timeline_version=changed.current_version))
        assert package.approval is None
        request=RenderCreateRequest(expected_timeline_version=changed.current_version,expected_subtitle_version=package.subtitle.version,
            expected_audio_version=package.audio_mix.version,profile=profile)
        draft=await env.package.enqueue_review(env.project.project_id,request)
        complete=await job.process(draft.render_id)
        assert complete.status=='awaiting_review',complete.failure_reason
        reuse=complete.manifest['narration']['timing'][0]['raw_audio_reuse']
        assert reuse['audio_sha256']==original['original_evidence']['audio_sha256']
        assert reuse['target_timeline_version_id']==changed.current_version_id
        assert reuse['target_canonical_binding_sha256'] and reuse['owner_uat_accepted'] is False
    assert len(state['calls'])==1 and len(await entries(env))==1


@pytest.mark.asyncio
@pytest.mark.parametrize('drift',['bytes','metadata','evidence'])
async def test_corrupt_cache_is_not_a_miss_and_never_regenerates(env,drift):
    state,job,version,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    row=(await entries(env))[0];asset=await env.assets.get_asset(row.result_json['asset_id'])
    if drift=='bytes':(env.storage.root/asset.object_key).write_bytes(b'EXPLICIT OWNED PCM CORRUPTION')
    elif drift=='metadata':
        from app.db import AssetORM
        async with env.factory() as session,session.begin():
            await session.execute(update(AssetORM).where(AssetORM.asset_id==asset.asset_id).values(checksum_sha256='b'*64))
    else:
        async with env.factory() as session,session.begin():
            await session.execute(update(TTSArtifactReuseORM).where(TTSArtifactReuseORM.reuse_id==row.reuse_id).values(result_sha256='b'*64))
    # A corrupt raw-unit cache isn't repaired/regenerated in a new review.
    target=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(expected_timeline_version=1,
        expected_subtitle_version=1,expected_audio_version=1,profile='review-960x540'))
    result=await job.process(target.render_id)
    assert result.status=='failed' and 'TTS_REUSE_' in result.failure_reason
    assert len(state['calls'])==1 and (await entries(env))[0].result_json==row.result_json


@pytest.mark.asyncio
async def test_unknown_outcome_survives_restart_and_never_replays_wire(env):
    state={'calls':[],'failure':True}
    state,job,version,review=await ready(env,state)
    first=await job.process(review.render_id)
    assert first.status=='failed' and len(state['calls'])==1
    assert (await entries(env))[0].state=='unknown'
    state['failure']=False
    again=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(expected_timeline_version=1,
        expected_subtitle_version=1,expected_audio_version=1))
    result=await processor(env,state['provider']).process(again.render_id)
    assert result.status=='failed' and 'TTS_REUSE_UNKNOWN_MANUAL_REVIEW' in result.failure_reason
    assert len(state['calls'])==1


@pytest.mark.asyncio
async def test_second_sql_instance_cannot_dispatch_same_pending_unit_or_steal_expired_claim(env):
    state={'calls':[],'entered':asyncio.Event(),'resume':asyncio.Event()}
    state,job,version,review=await ready(env,state)
    task=asyncio.create_task(job.process(review.render_id))
    second_engine=create_async_engine(env.engine.url)
    other=TTSArtifactReuseRepository(async_sessionmaker(second_engine,expire_on_commit=False))
    try:
        await asyncio.wait_for(state['entered'].wait(),10)
        row=(await entries(env))[0]
        observed=await other.claim(row.binding_json,review.render_id)
        assert observed['state']=='pending' and len(state['calls'])==1
        async with env.factory() as session,session.begin():
            await session.execute(update(TTSArtifactReuseORM).where(TTSArtifactReuseORM.reuse_id==row.reuse_id)
                .values(lease_until=utc_now()-timedelta(seconds=1)))
        assert (await other.claim(row.binding_json,review.render_id))['state']=='unknown'
        state['resume'].set();result=await task
        assert result.status=='failed' and len(state['calls'])==1
        assert (await entries(env))[0].state=='unknown' and (await entries(env))[0].result_json is None
    finally:
        state['resume'].set()
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_cancel_during_pcm_download_prevents_a_late_reuse_receipt_and_no_wire(env):
    state,job,version,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    target=await final(env,reviewed)
    actual=env.storage.download_file;entered=asyncio.Event();resume=asyncio.Event()
    async def paused(*,object_key,destination,max_bytes=None,expected_size_bytes=None,expected_sha256=None,expected_prefix=None):
        await actual(object_key=object_key,destination=destination,max_bytes=max_bytes,
            expected_size_bytes=expected_size_bytes,expected_sha256=expected_sha256,expected_prefix=expected_prefix)
        if destination.name=='narration.wav':entered.set();await resume.wait()
    env.storage.download_file=paused
    task=asyncio.create_task(job.process(target.render_id))
    try:
        await asyncio.wait_for(entered.wait(),10)
        await env.production.cancel_render(env.project.project_id,target.render_id,'explicit-fixture-cancel')
        resume.set();result=await task
        assert result.status=='cancelled' and len(state['calls'])==1
        assert 'narration' not in result.manifest
    finally:
        resume.set()
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
        env.storage.download_file=actual


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['unsupported','governed_fixture','configured_optin_offline'])
async def test_final_uses_approved_prepared_audio_without_any_provider_or_secret_admission(env,lane):
    state,job,version,review=await ready(env)
    if lane!='configured_optin_offline':
        # Explicit local fixture with the actual production audio scheduler;
        # it has no cache opt-in, readiness, controller or credential handler.
        from app.providers import VoiceResult
        from app.tts_evidence import ProductionTTSProfile,TTSArtifactEvidence,SpeechTimingEvidence
        class UnsupportedProvider:
            model='explicit-governed-protocol-fixture' if lane=='governed_fixture' else 'explicit-legacy-fixture'
            voice='fixture-vi'
            async def synthesize(self, *, text,language,output_path):
                state['calls'].append({'fixture':True,'text_sha256':hashlib.sha256(text.encode()).hexdigest()})
                raw=raw_pcm();output_path.write_bytes(raw)
                evidence=None
                if lane=='governed_fixture':
                    selected=ProductionTTSProfile(provider_key='openai-tts',model='explicit-governed-protocol-fixture',voice_id='fixture-voice')
                    evidence=TTSArtifactEvidence(profile=selected,profile_sha256=selected.sha256,
                        text_sha256=hashlib.sha256(text.encode()).hexdigest(),audio_sha256=hashlib.sha256(raw).hexdigest(),
                        request_sha256='3'*64,decoded_duration_seconds=.5,latency_seconds=0,
                        timing=SpeechTimingEvidence(source='ESTIMATED_SEGMENT',reference_text=text,
                            audio_sha256=hashlib.sha256(raw).hexdigest(),duration_seconds=.5),
                        usage={'fixture':True,'model_inferences':0,'provider_calls':0})
                return VoiceResult(path=output_path,duration_seconds=.5,provider='fixture-vi',voice='fixture-vi',evidence=evidence)
        job=processor(env,UnsupportedProvider())
        if lane=='governed_fixture':
            await env.platform.seed_providers([{'provider_key':'openai-tts','display_name':'EXPLICIT GOVERNED PROTOCOL FIXTURE',
                'capability':'tts','adapter':'fixture','routing_mode':'primary','status':'disabled','enabled':False,
                'supports_dry_run':True,'metadata':{'fixture':True,'real_provider_tested':False}}])
    reviewed=await job.process(review.render_id)
    assert reviewed.status=='awaiting_review',reviewed.failure_reason
    baseline=copy.deepcopy(reviewed.manifest)
    target=await final(env,reviewed)
    class DeniedProvider:
        def __getattr__(self,name):
            raise AssertionError('No provider profile, readiness, secret, preflight or wire at final: '+name)
    final_provider=DeniedProvider()
    if lane=='governed_fixture':
        from app.tts_provider_execution import GovernedVietnameseTTSProvider
        from app.tts_evidence import ProductionTTSProfile
        selected=ProductionTTSProfile(provider_key='openai-tts',model='explicit-governed-protocol-fixture',voice_id='fixture-voice')
        final_provider=GovernedVietnameseTTSProvider(selected,controller=DeniedProvider(),
            credential_resolver=DeniedProvider(),approved_units={})
    completed=await processor(env,final_provider).process(target.render_id)
    assert completed.status=='ready',completed.failure_reason
    assert len(state['calls'])==1
    assert (await env.production.get_render(reviewed.render_id)).manifest==baseline
    source=reviewed.manifest['supporting_asset_ids']['audio-mix']
    final_asset=completed.manifest['supporting_asset_ids']['audio-mix']
    assert (await env.assets.get_asset(source)).checksum_sha256==(await env.assets.get_asset(final_asset)).checksum_sha256
    assert completed.manifest['narration'].get('caption_schedule')==baseline['narration'].get('caption_schedule')
    assert completed.manifest['narration']['prepared_audio_reuse']['fresh_provider_measurement'] is False
    assert completed.manifest['narration']['prepared_audio_reuse']['owner_uat_accepted'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('proof',['missing_binding','missing_asset','damaged_mix','raw_provider_corruption'])
async def test_approved_audio_missing_or_corrupt_fails_closed_without_final_synthesis(env,proof):
    state,job,version,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    target=await final(env,reviewed)
    if proof in {'missing_binding','missing_asset'}:
        value=copy.deepcopy(reviewed.manifest)
        if proof=='missing_binding':value['narration'].pop('canonical_audio_binding')
        else:value['supporting_asset_ids'].pop('audio-mix')
        async with env.factory() as session,session.begin():
            await session.execute(update(ProductionRenderJobORM).where(ProductionRenderJobORM.render_id==reviewed.render_id)
                .values(manifest_json=value))
    else:
        identity=reviewed.manifest['supporting_asset_ids']['audio-mix'] if proof=='damaged_mix' else reviewed.manifest['narration']['timing'][0]['provider_audio_asset_id']
        asset=await env.assets.get_asset(identity)
        (env.storage.root/asset.object_key).write_bytes(b'EXPLICIT OWNED DAMAGED APPROVED AUDIO')
    result=await job.process(target.render_id)
    assert result.status=='failed' and 'TTS_REUSE_' in result.failure_reason
    assert len(state['calls'])==1


def test_additive_migration_only_appends_custody_table_without_rewriting_old_schema(tmp_path):
    import importlib.util
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path=ROOT/'apps/api/migrations/versions/0030_sql_tts_artifact_reuse.py'
    spec=importlib.util.spec_from_file_location('owned_tts_reuse_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine=sa.create_engine('sqlite:///'+str(tmp_path/'additive.db'))
    with engine.begin() as con:
        con.execute(sa.text('CREATE TABLE preserved_evidence(id INTEGER PRIMARY KEY,payload TEXT NOT NULL)'))
        con.execute(sa.text("INSERT INTO preserved_evidence VALUES(1,'EXPLICIT RETAINED FIXTURE')"))
        prior=con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='preserved_evidence'")).scalar()
        module.op=Operations(MigrationContext.configure(con));module.upgrade()
        assert con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='preserved_evidence'")).scalar()==prior
        assert con.execute(sa.text('SELECT payload FROM preserved_evidence')).scalar()=='EXPLICIT RETAINED FIXTURE'
        assert 'sql_tts_artifact_reuse' in sa.inspect(con).get_table_names()
        with pytest.raises(RuntimeError,match='Owner approval'):module.downgrade()
    engine.dispose()
