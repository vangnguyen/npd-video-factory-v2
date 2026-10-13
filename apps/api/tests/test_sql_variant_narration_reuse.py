"""Actual isolated SQLite lineage/PCM; manually seeded synthetic review, no renderer/model."""
import asyncio
import copy
from datetime import timedelta
import hashlib
import io
from types import SimpleNamespace
import wave
import threading
import pytest
from sqlalchemy import select,func
from app.db import AssetORM,utc_now
from app.production_db import ProductionApprovalORM,ProductionPackageORM,ProductionRenderJobORM
from app.platform_models import AssetRegister
from app.content_models import StoryboardScene
from app.production_models import ProductionPackageCreateRequest,RenderCreateRequest,ApprovalRequest,ApprovalDecisionRequest
from app.tts_evidence import TTSArtifactEvidence,ProductionTTSProfile,SpeechTimingEvidence
from app.sql_tts_artifact_reuse import asset_proof
from app.sql_variant_models import FamilyReserveRequest,digest
from app.sql_variant_repository import SqlVariantFamilyRepository,SqlVariantError,record_value
from app.sql_variant_db import SqlVariantArtifactReceiptORM
from app.sql_variant_derivation_repository import SqlStoryboardDerivationRepository
from app.sql_variant_derivation_service import SqlStoryboardDerivationService
from app.sql_variant_derivation_models import DeriveStoryboardRequest
from app.sql_variant_storyboard_copy import LocalStoryboardCopier
from app.sql_variant_narration_repository import SqlVariantNarrationRepository
from app.sql_variant_narration_service import SqlVariantNarrationService
from app.sql_variant_narration_copy import LocalNarrationCopier
from app.sql_variant_narration_models import NarrationReuseRequest
from app.sql_variant_narration_projection import narration_projection,child_cues
from test_mvp1_multi_input import env,author,timeline,image


def wav(seconds):
    out=io.BytesIO()
    with wave.open(out,'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000)
        f.writeframes(b'\x00\x08'*round(seconds*48000))
    return out.getvalue()


async def asset(env,name,kind,raw):
    path=env.tmp/name;path.write_bytes(raw)
    saved=await env.storage.put_file(object_key=f'workspaces/{env.workspace.workspace_id}/projects/{env.project.project_id}/fixture-review/{name}',path=path)
    return await env.platform.register_asset(env.project.project_id,AssetRegister(asset_class='render',kind=kind,
        filename=name,object_key=saved.object_key,content_type='audio/wav' if name.endswith('.wav') else 'video/mp4',
        size_bytes=saved.size_bytes,checksum_sha256=saved.checksum_sha256,storage_provider='local',
        provenance={'fixture':True,'human_accepted':False,'rights_status':'unknown'}))


@pytest.fixture
async def narration_env(env):
    photo=await image(env)
    text='Lời đọc fixture giữ nguyên tên Hà Nội.'
    content=await author(env,scenes=[StoryboardScene(scene_id='scene_01',narration=text,media_strategy='user_asset',asset_id=photo.asset_id)],original=text)
    built=await timeline(env,content)
    package=await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    reviewed=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(
        expected_timeline_version=1,expected_subtitle_version=1,expected_audio_version=1))
    raw=await asset(env,'unit-000-raw.wav','tts-provider-source',wav(.5))
    prepared=await asset(env,'narration.wav','narration-track',wav(built.snapshot.duration_seconds))
    video=await asset(env,'review.mp4','av-review',b'EXPLICIT UNRENDERED REVIEW BYTE FIXTURE')
    profile=ProductionTTSProfile(provider_key='explicit-fixture-tts',model='manual-pcm-fixture',voice_id='vi')
    evidence=TTSArtifactEvidence(profile=profile,profile_sha256=profile.sha256,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),audio_sha256=raw.checksum_sha256,
        request_sha256='3'*64,decoded_duration_seconds=.5,latency_seconds=0,
        timing=SpeechTimingEvidence(duration_seconds=.5),usage={'fixture':True,'normalization_record_sha256':'2'*64})
    manifest={'fixture':True,'narration':{'provider':'explicit-fixture-tts','voice':'vi','duration_seconds':built.snapshot.duration_seconds,
        'timing':[{'unit_id':'narration_0000','cue_ids':[c.cue_id for c in package.subtitle.cues],
            'start_seconds':0,'end_seconds':.5,'slot_end_seconds':built.snapshot.duration_seconds,
            'text_sha256':evidence.text_sha256,'source_audio_duration_seconds':.5,'rendered_audio_duration_seconds':.5,
            'provider_evidence':evidence.model_dump(mode='json'),'provider_audio_file':'unit-000-raw.wav',
            'provider_audio_asset_id':raw.asset_id,'provider_audio_asset_proof':asset_proof(raw),
            'audio_duration_source':'decoded_pcm_sample_count','applied_timing_speedup':1}]},
        'supporting_asset_ids':{'narration-track':prepared.asset_id},
        'supporting_audio_proofs':{'narration-track':asset_proof(prepared)}}
    completed=await env.production.complete_render(reviewed.render_id,output_asset_id=video.asset_id,
        qc_report={'fixture':True,'not_real_render_qc':True},manifest=manifest)
    manifest=completed.manifest
    approval=await env.package.request_approval(env.project.project_id,ApprovalRequest(review_render_id=reviewed.render_id))
    approval=await env.package.decide_approval(env.project.project_id,approval.approval_id,
        ApprovalDecisionRequest(decision='approved',reviewer_ref='explicit-synthetic-reviewer',comment='Contract fixture, not Owner/UAT'))
    families=SqlVariantFamilyRepository(env.factory)
    available=await families.availability(env.workspace.workspace_id,env.project.project_id)
    reserve=FamilyReserveRequest(expected_project_version=available.binding.project_version,expected_timeline_version=1,
        expected_timeline_version_id=built.current_version_id,expected_binding_sha256=available.binding_sha256,
        catalog_ref=available.catalog.catalog_ref,catalog_sha256=available.catalog_sha256,
        profile_refs=['youtube-landscape@1'],request_key='explicit-s5-family-fixture',acknowledge_draft_derivation=True)
    family,_=await families.reserve(env.workspace.workspace_id,env.project.project_id,reserve,actor_ref='fixture-editor')
    derivative=SqlStoryboardDerivationService(SqlStoryboardDerivationRepository(families),LocalStoryboardCopier(env.storage))
    inherited,_=await derivative.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,
        DeriveStoryboardRequest(expected_version=family.version,expected_snapshot_sha256=family.snapshot_sha256,
            member_id=family.members[0].member_id,request_key='explicit-s5-child-fixture',acknowledge_unapproved_child=True),actor_ref='fixture-editor')
    current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    child=await env.timeline.get_timeline(inherited.result['child_project_id'])
    projection=narration_projection(child.snapshot.model_dump(mode='json'),child_cues(child.snapshot.model_dump(mode='json')),package.audio_mix.config.voice)
    request=NarrationReuseRequest(enabled=True,expected_version=current.version,expected_snapshot_sha256=current.snapshot_sha256,
        request_key='explicit-s5-narration-fixture',member_id=current.members[0].member_id,
        child_project_id=child.project_id,expected_child_content_version_id=inherited.result['content_version_id'],
        expected_child_timeline_version_id=child.current_version_id,expected_child_timeline_version=child.current_version,
        source_review_render_id=reviewed.render_id,source_approval_id=approval.approval_id,
        expected_source_manifest_sha256=digest(manifest),expected_semantic_sha256=digest(projection),
        expected_profile_sha256s=[profile.sha256],expected_normalization_sha256s=['2'*64],
        voice_config=package.audio_mix.config.voice,acknowledge_fresh_child_review=True)
    repo=SqlVariantNarrationRepository(families)
    copier=LocalNarrationCopier(env.storage)
    service=SqlVariantNarrationService(repo,copier,enabled=True)
    yield SimpleNamespace(env=env,families=families,family=current,child=child,request=request,
        repo=repo,copier=copier,service=service,raw=raw,prepared=prepared,evidence=evidence,manifest=manifest)


async def run(f,request=None,actor='fixture-editor'):
    return await f.service.reuse(f.env.workspace.workspace_id,f.env.project.project_id,f.family.family_id,
        request or f.request,actor_ref=actor)


async def master_records(f):
    async with f.env.factory() as s:
        return {m.__tablename__:[record_value(r) for r in (await s.scalars(select(m).where(m.project_id==f.env.project.project_id))).all()]
            for m in [AssetORM,ProductionApprovalORM,ProductionPackageORM,ProductionRenderJobORM]}


async def test_real_sql_import_keeps_bytes_original_evidence_and_child_review_independent(narration_env):
    f=narration_env;before=await master_records(f)
    result,replay=await run(f)
    assert not replay and result.state=='ready' and result.provider_calls==0 and result.new_inferences==0
    assert result.approval_transferred is False and result.human_review_required and not result.publishing_enabled
    assert len(result.result['copies'])==2
    for old,item in result.result['copies'].items():
        original=await f.env.assets.get_asset(old);target=await f.env.assets.get_asset(item['asset_id'])
        assert target.project_id==f.child.project_id and target.asset_class=='generated'
        assert target.provenance['rights_status']=='unknown' and not target.provenance['production_eligible']
        a,b=f.env.storage._path(original.object_key),f.env.storage._path(target.object_key)
        assert a.read_bytes()==b.read_bytes() and a.stat().st_ino!=b.stat().st_ino and b.stat().st_nlink==1
    assert await master_records(f)==before
    child=await f.env.timeline.get_timeline(f.child.project_id)
    assert child.approval_status=='draft' and child.approved_timeline_version is None
    assert (await f.env.platform.get_version(f.request.expected_child_content_version_id)).snapshot['content']['approved'] is False
    with pytest.raises(AssertionError):
        assert result.owner_uat_accepted
    replay_result,replay=await run(f)
    assert replay and replay_result==result
    value=await f.repo.input(f.env.workspace.workspace_id,f.env.project.project_id,f.family.family_id,result.receipt_id)
    assert value['original_narration']==f.manifest['narration']


async def test_default_disabled_has_no_sql_copy_or_provider_attempt(narration_env):
    f=narration_env
    async def denied(*a,**kw):raise AssertionError('disabled IO')
    f.repo.claim=denied;f.copier.copy=denied
    service=SqlVariantNarrationService(f.repo,f.copier)
    result,replay=await service.reuse(f.env.workspace.workspace_id,f.env.project.project_id,f.family.family_id,f.request,actor_ref='fixture-editor')
    assert result.state=='disabled' and result.receipt_id is None and not replay


@pytest.mark.parametrize('change',['text','voice','profile','normalization','foreign','manifest','actor'])
async def test_drift_foreign_and_actor_never_become_provider_or_copy_miss(narration_env,change):
    f=narration_env;request=f.request
    if change=='text':request=request.model_copy(update={'expected_semantic_sha256':'9'*64})
    elif change=='voice':request=request.model_copy(update={'voice_config':request.voice_config.model_copy(update={'speed':1.1})})
    elif change=='profile':request=request.model_copy(update={'expected_profile_sha256s':['9'*64]})
    elif change=='normalization':request=request.model_copy(update={'expected_normalization_sha256s':['9'*64]})
    elif change=='foreign':request=request.model_copy(update={'child_project_id':f.env.project.project_id})
    elif change=='manifest':request=request.model_copy(update={'expected_source_manifest_sha256':'9'*64})
    else:
        await run(f)
    called=[]
    async def denied(*a,**kw):called.append(True);raise AssertionError('drift copy')
    f.copier.copy=denied
    with pytest.raises((SqlVariantError,RuntimeError)):
        await run(f,request,actor='other-editor' if change=='actor' else 'fixture-editor')
    assert not called


async def test_pending_expiry_is_unknown_and_replay_never_copies(narration_env):
    f=narration_env
    receipt,claim,replayed=await f.repo.claim(f.env.workspace.workspace_id,f.env.project.project_id,f.family.family_id,f.request,actor_ref='fixture-editor')
    async with f.env.factory() as s,s.begin():
        (await s.get(SqlVariantArtifactReceiptORM,receipt.receipt_id)).lease_until=utc_now()-timedelta(seconds=1)
    async def denied(*a,**kw):raise AssertionError('expired receipt copied')
    f.copier.copy=denied
    result,replay=await run(f)
    assert replay and result.state=='unknown' and result.result is None


async def test_approval_revoked_after_copy_rolls_back_assets_and_keeps_unknown(narration_env):
    f=narration_env;original=f.copier.copy
    async def revoked(*a,**kw):
        copies=await original(*a,**kw)
        async with f.env.factory() as s,s.begin():
            (await s.get(ProductionApprovalORM,f.request.source_approval_id)).status='changes_requested'
        return copies
    f.copier.copy=revoked
    with pytest.raises(SqlVariantError):await run(f)
    async with f.env.factory() as s:
        receipts=(await s.scalars(select(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.kind=='approved_narration_reuse'))).all()
        assert len(receipts)==1 and receipts[0].state=='unknown'
        assert await s.scalar(select(func.count()).select_from(AssetORM).where(AssetORM.kind.in_(['variant-narration-source','variant-tts-source'])))==0


async def test_double_cancel_drains_local_writer_and_unknown_is_not_replayed(narration_env):
    f=narration_env;entered=threading.Event();release=threading.Event();original=f.copier.copier._copy
    def paused(items,stop):
        entered.set();assert release.wait(5);return original(items,stop)
    f.copier.copier._copy=paused
    task=asyncio.create_task(run(f))
    assert await asyncio.to_thread(entered.wait,3)
    task.cancel();await asyncio.sleep(.02);task.cancel();await asyncio.sleep(.02)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):await task
    result,replay=await run(f)
    assert replay and result.state=='unknown' and result.error_code=='SQL_VARIANT_NARRATION_CANCELLED'


async def test_same_size_copy_mutation_during_last_sql_guard_rolls_back_all_assets(narration_env):
    f=narration_env;held_ready=False;saved={};hold=f.copier.hold;capture=f.repo._capture
    async def held(copies,value):
        nonlocal held_ready
        result=await hold(copies,value);saved.update(copies);held_ready=True;return result
    async def late(*a,**kw):
        value=await capture(*a,**kw)
        if held_ready:
            item=next(iter(saved.values()))
            f.env.storage._path(item['object_key']).write_bytes(b'X'*item['size_bytes'])
        return value
    f.copier.hold=held;f.repo._capture=late
    with pytest.raises(SqlVariantError,match='OUTCOME_UNKNOWN'):await run(f)
    async with f.env.factory() as s:
        assert await s.scalar(select(func.count()).select_from(AssetORM).where(AssetORM.kind.in_(['variant-narration-source','variant-tts-source'])))==0
        receipt=await s.scalar(select(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.kind=='approved_narration_reuse'))
        assert receipt.state=='unknown' and receipt.result_json is None


@pytest.mark.parametrize('field,value',[('approval_transferred',True),('publishing_enabled',True),('provider_calls',1)])
async def test_rehashed_result_does_not_grant_authority_or_fake_provider_counts(narration_env,field,value):
    f=narration_env;result,_=await run(f)
    async with f.env.factory() as s,s.begin():
        receipt=await s.get(SqlVariantArtifactReceiptORM,result.receipt_id)
        changed={**receipt.result_json,field:value};receipt.result_json=changed;receipt.result_sha256=digest(changed)
    with pytest.raises(SqlVariantError):
        await f.repo.get(f.env.workspace.workspace_id,f.env.project.project_id,f.family.family_id,result.receipt_id,require_current=True)
