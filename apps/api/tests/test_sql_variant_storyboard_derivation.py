"""Actual isolated SQL children/first-party bytes. No model/provider/network/UAT."""
import asyncio
import copy
import hashlib
import os
import wave
from datetime import timedelta
from pathlib import Path
import pytest
from sqlalchemy import select, func
from app.db import AssetORM, ProjectVersionORM, VideoProjectORM, utc_now
from app.production_db import ProductionPackageORM, ProductionApprovalORM, ProductionRenderJobORM
from app.auto_edit_db import UploadSessionORM
from app.content_models import ContentDocument, ContentSaveRequest
from app.timeline_db import TimelineVersionORM, TimelineORM
from app.timeline_models import TimelineMutationRequest, TimelineOperation
from app.sql_variant_db import SqlVariantArtifactReceiptORM, SqlVariantFamilyORM
from app.sql_variant_models import FamilyVersionRequest, digest, canonical
from app.sql_variant_repository import SqlVariantError, record_value
from app.sql_variant_derivation_models import DeriveStoryboardRequest
from app.sql_variant_derivation_repository import SqlStoryboardDerivationRepository, target_key
from app.sql_variant_derivation_service import SqlStoryboardDerivationService
from app.sql_variant_storyboard_copy import LocalStoryboardCopier
from test_sql_variant_family import env, ready


async def setup(env):
    families, request, _, _, _ = await ready(env)
    family, _ = await families.reserve(env.workspace.workspace_id, env.project.project_id, request, actor_ref='fixture-editor')
    repo = SqlStoryboardDerivationRepository(families)
    service = SqlStoryboardDerivationService(repo, LocalStoryboardCopier(env.storage))
    return families, family, repo, service


def request(family, member=None, key='explicit-storyboard-derivation-fixture'):
    return DeriveStoryboardRequest(expected_version=family.version, expected_snapshot_sha256=family.snapshot_sha256,
        member_id=(member or family.members[0]).member_id, request_key=key, acknowledge_unapproved_child=True)


async def master_rows(env):
    async with env.factory() as session:
        result = {}
        for model in (VideoProjectORM, ProjectVersionORM, AssetORM, TimelineORM, TimelineVersionORM):
            rows = (await session.scalars(select(model).where(model.project_id == env.project.project_id)
                .order_by(*model.__table__.primary_key.columns))).all()
            result[model.__tablename__] = canonical([record_value(row) for row in rows])
        return result


async def run(env, service, family, payload):
    return await service.derive(env.workspace.workspace_id, env.project.project_id, family.family_id, payload, actor_ref='fixture-editor')


@pytest.mark.asyncio
async def test_real_six_children_have_independent_bytes_content_and_four_geometry_without_authority(env):
    families, family, repo, service = await setup(env)
    original = await master_rows(env)
    frozen_snapshot, frozen_result = family.snapshot.model_dump(mode='json'), copy.deepcopy(family.result)
    assets, children = [], []
    for index, member in enumerate(family.members):
        current = await families.get(env.workspace.workspace_id, env.project.project_id, family.family_id)
        payload = request(current, member, key=f'explicit-storyboard-derivation-{index:02d}')
        receipt, replayed = await run(env, service, current, payload)
        assert not replayed and receipt.state == 'ready'
        assert receipt.safety.child_projects_created == 1 and receipt.safety.source_bytes_verified
        assert receipt.safety.provider_calls == 0 and not receipt.safety.approval_inherited
        child_id = receipt.result['child_project_id']; children.append(child_id)
        version = await env.platform.get_version(receipt.result['content_version_id'])
        assert version.project_id == child_id and version.workspace_id == env.workspace.workspace_id
        assert version.snapshot['content']['approved'] is False
        master_content = await env.platform.get_version(family.snapshot.binding.source_content_version_id)
        assert version.snapshot['content']['original_text'] == master_content.snapshot['content']['original_text']
        timeline = await env.timeline.get_timeline(child_id)
        assert timeline.source_analysis_id is None and timeline.source_content_version_id == version.project_version_id
        assert timeline.approval_status == 'draft' and timeline.approved_timeline_version is None and timeline.latest_preview_id is None
        assert (timeline.snapshot.width, timeline.snapshot.height, timeline.snapshot.aspect_ratio) == (
            member.profile.width, member.profile.height, member.profile.aspect_ratio)
        assert timeline.snapshot.metadata['reframe']['needs_attention'] and timeline.snapshot.metadata['reframe']['confidence'] is None
        for old, new in receipt.result['asset_map'].items():
            source = await env.assets.get_asset(old); child = await env.assets.get_asset(new)
            assert child.project_id == child_id and child.asset_id != source.asset_id and child.object_key != source.object_key
            assert child.project_version_id == version.project_version_id and child.provenance['rights_status'] == 'unknown'
            a, b = env.storage._path(source.object_key), env.storage._path(child.object_key)
            assert a.read_bytes() == b.read_bytes() and a.stat().st_ino != b.stat().st_ino
            assert b.stat().st_nlink == 1 and child.checksum_sha256 == hashlib.sha256(b.read_bytes()).hexdigest()
            assets.append(new)
        replay, repeated = await run(env, service, current, payload)
        assert repeated and replay == receipt
    assert len(set(children)) == 6 and len(set(assets)) == 6
    current = await families.get(env.workspace.workspace_id, env.project.project_id, family.family_id)
    assert current.version == 13 and current.safety.child_projects_created == 6 and current.safety.source_bytes_verified
    assert current.snapshot.model_dump(mode='json') == frozen_snapshot and current.result == frozen_result
    assert await master_rows(env) == original
    async with env.factory() as session:
        for model in (ProductionPackageORM, ProductionApprovalORM, ProductionRenderJobORM, UploadSessionORM):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
async def test_child_edits_use_existing_canonical_and_content_engine_independently(env):
    families, family, repo, service = await setup(env)
    before = await master_rows(env)
    receipt, _ = await run(env, service, family, request(family))
    child_id = receipt.result['child_project_id']
    child = await env.timeline.get_timeline(child_id)
    clip = child.snapshot.tracks[0].clips[0]
    edited = await env.service.mutate(child_id, TimelineMutationRequest(expected_version=1,
        operations=[TimelineOperation(type='set_clip_properties', clip_id=clip.clip_id, opacity=.7)]))
    assert edited.current_version == 2 and edited.snapshot.tracks[0].clips[0].opacity == .7
    version = await env.platform.get_version(receipt.result['content_version_id'])
    document = ContentDocument.model_validate(version.snapshot['content']).model_copy(update={'creative_instructions': 'Child only'})
    saved = await env.content.save(child_id, ContentSaveRequest(document=document,
        expected_content_version_id=version.project_version_id), actor_ref='fixture-editor')
    assert saved.project_id == child_id and not saved.snapshot['content']['approved']
    assert await master_rows(env) == before
    current = await families.get(env.workspace.workspace_id, env.project.project_id, family.family_id)
    assert current.members[0].child_project_id == child_id and current.source_current
    assert (await repo.get(env.workspace.workspace_id, env.project.project_id, family.family_id, receipt.receipt_id)).state == 'ready'


@pytest.mark.asyncio
async def test_preserves_track_locks_effects_subtitle_windows_and_audio_trim(env):
    families, payload, _, _, built = await ready(env)
    path = env.tmp/'owned-tone.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b'\x00\x00'*16000)
    stored = await env.storage.put_file(object_key=f'workspaces/{env.workspace.workspace_id}/projects/{env.project.project_id}/inputs/owned-tone.wav', path=path, content_type='audio/wav')
    from app.platform_models import AssetRegister
    sound = await env.platform.register_asset(env.project.project_id, AssetRegister(asset_class='source', kind='music', filename='owned-tone.wav',
        object_key=stored.object_key, content_type=stored.content_type, size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256, storage_provider='local', provenance={'rights_status':'owned'}))
    async with env.factory() as session, session.begin():
        row = await session.get(TimelineVersionORM, built.current_version_id)
        snapshot = copy.deepcopy(row.snapshot_json)
        snapshot['tracks'][0].update(locked=True, muted=True)
        snapshot['tracks'][0]['clips'][0].update(effects=[{'type':'brightness','value':1.1}], opacity=.75,
            metadata={**snapshot['tracks'][0]['clips'][0]['metadata'], 'clip_style_schema':'clip-style-v1'})
        from app.timeline_models import TimelineClip
        snapshot['tracks'][2]['clips'] = [TimelineClip(clip_id='clip_owned_music', kind='music', label='Owned audio fixture',
            asset_id=sound.asset_id, source_start=.2, source_end=1.2, timeline_start=.3, duration=1., volume=.4, disabled=True).model_dump(mode='json')]
        row.snapshot_json = snapshot  # explicit manual fixture, no provider output
    available = await families.availability(env.workspace.workspace_id, env.project.project_id)
    payload = payload.model_copy(update={'expected_binding_sha256':available.binding_sha256})
    family, _ = await families.reserve(env.workspace.workspace_id, env.project.project_id, payload, actor_ref='fixture-editor')
    repo = SqlStoryboardDerivationRepository(families)
    receipt, _ = await run(env, SqlStoryboardDerivationService(repo, LocalStoryboardCopier(env.storage)), family, request(family))
    child = await env.timeline.get_timeline(receipt.result['child_project_id'])
    assert child.snapshot.tracks[0].locked and child.snapshot.tracks[0].muted
    assert child.snapshot.tracks[0].clips[0].effects == [{'type':'brightness','value':1.1}]
    old = snapshot['tracks'][2]['clips'][0]; new = child.snapshot.tracks[2].clips[0].model_dump(mode='json')
    for field in ('source_start','source_end','timeline_start','duration','volume','disabled','speed'):
        assert new[field] == old[field]
    captions = child.snapshot.tracks[1].clips
    assert [(c.label,c.source_start,c.source_end,c.timeline_start,c.duration) for c in captions] == [
        (c['label'],c['source_start'],c['source_end'],c['timeline_start'],c['duration']) for c in snapshot['tracks'][1]['clips']]
    assert child.snapshot.metadata['narration_plan']['scenes'][0]['scene_id'] == child.snapshot.tracks[0].clips[0].metadata['scene_id']


class PausedCopier:
    def __init__(self, wrapped):
        self.wrapped=wrapped; self.entered=asyncio.Event(); self.release=asyncio.Event(); self.calls=0
    async def copy(self, items):
        self.calls+=1; self.entered.set(); await self.release.wait()
        return await self.wrapped.copy(items)
    async def verify_all(self, copies, **kwargs):
        await self.wrapped.verify_all(copies, **kwargs)


@pytest.mark.asyncio
async def test_two_concurrent_requests_do_one_copy_and_replay_pending_without_reexecution(env):
    families, family, repo, _ = await setup(env)
    pause=PausedCopier(LocalStoryboardCopier(env.storage)); service=SqlStoryboardDerivationService(repo,pause)
    payload=request(family)
    task=asyncio.create_task(run(env,service,family,payload)); await pause.entered.wait()
    pending,replayed=await run(env,SqlStoryboardDerivationService(SqlStoryboardDerivationRepository(families),pause),family,payload)
    assert pending.state=='pending' and replayed and pause.calls==1
    pause.release.set(); done,_=await task
    assert done.state=='ready' and pause.calls==1


@pytest.mark.asyncio
async def test_content_source_mutates_during_copy_blocks_child_without_holding_sql_transaction(env):
    families,family,repo,_=await setup(env)
    pause=PausedCopier(LocalStoryboardCopier(env.storage)); service=SqlStoryboardDerivationService(repo,pause)
    task=asyncio.create_task(run(env,service,family,request(family))); await pause.entered.wait()
    source=await env.content.latest(env.project.project_id)
    document=ContentDocument.model_validate(source.snapshot['content']).model_copy(update={'creative_instructions':'source changed'})
    await asyncio.wait_for(env.content.save(env.project.project_id,ContentSaveRequest(document=document,
        expected_content_version_id=source.project_version_id)),5)
    pause.release.set()
    with pytest.raises(SqlVariantError,match='MASTER_BINDING_CHANGED'):await task
    current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    assert current.state=='recovery_required' and current.members[0].child_project_id is None and not current.source_current
    observed,replayed=await run(env,service,family,request(family))
    assert replayed and observed.state=='unknown' and pause.calls==1


@pytest.mark.asyncio
async def test_explicit_cancel_during_copy_preserves_history_no_late_child(env):
    families,family,repo,_=await setup(env)
    pause=PausedCopier(LocalStoryboardCopier(env.storage)); service=SqlStoryboardDerivationService(repo,pause)
    task=asyncio.create_task(run(env,service,family,request(family))); await pause.entered.wait()
    current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    cancelled,_=await families.cancel(env.workspace.workspace_id,env.project.project_id,family.family_id,
        FamilyVersionRequest(expected_version=current.version,expected_snapshot_sha256=current.snapshot_sha256,
            request_key='explicit-derivation-cancellation'),actor_ref='fixture-editor')
    assert cancelled.state=='cancelled'
    pause.release.set()
    with pytest.raises(SqlVariantError,match='DERIVATION_CONFLICT'):await task
    replay,replayed=await run(env,service,family,request(family))
    assert replayed and replay.state=='cancelled'
    assert await env.platform.get_project(family.members[0].planned_project_id) is None


@pytest.mark.asyncio
async def test_task_cancellation_retains_unknown_receipt_and_never_replays_copy(env):
    families,family,repo,_=await setup(env)
    pause=PausedCopier(LocalStoryboardCopier(env.storage)); service=SqlStoryboardDerivationService(repo,pause)
    payload=request(family); task=asyncio.create_task(run(env,service,family,payload)); await pause.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    replay,replayed=await run(env,service,family,payload)
    assert replayed and replay.state=='unknown' and replay.error_code=='SQL_VARIANT_COPY_CANCELLED' and pause.calls==1
    assert await env.platform.get_project(family.members[0].planned_project_id) is None


@pytest.mark.asyncio
async def test_crash_pending_and_expired_claim_do_not_automatically_repeat_io(env):
    families,family,repo,service=await setup(env)
    payload=request(family)
    receipt,claim,_=await repo.claim(env.workspace.workspace_id,env.project.project_id,family.family_id,payload,actor_ref='fixture-editor')
    async with env.factory() as session,session.begin():
        row=await session.get(SqlVariantArtifactReceiptORM,receipt.receipt_id); row.lease_until=utc_now()-timedelta(seconds=1)
    restart=SqlStoryboardDerivationService(SqlStoryboardDerivationRepository(families),LocalStoryboardCopier(env.storage))
    replay,repeated=await run(env,restart,family,payload)
    assert repeated and replay.state=='pending'
    with pytest.raises(SqlVariantError,match='LEASE_EXPIRED'):
        await repo.guard(env.workspace.workspace_id,env.project.project_id,family.family_id,receipt.receipt_id,claim['claim_id'])
    assert await env.platform.get_project(family.members[0].planned_project_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('stage',['child_flush','terminal_flush','terminal_history'])
async def test_lease_expiry_after_real_sql_await_rolls_back_children_and_ready_event(env,monkeypatch,stage):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.sql_variant_db import SqlVariantEventORM
    families,family,repo,service=await setup(env);repo.lease_seconds=1
    original=await master_rows(env)
    original_flush=AsyncSession.flush;original_read=families._read
    paused=False
    async def slow_flush(session,*args,**kwargs):
        nonlocal paused
        delay=not paused and (
            stage=='child_flush' and any(isinstance(row,VideoProjectORM) and row.provenance.get('source_type')=='storyboard_variant_derivative' for row in session.new)
            or stage=='terminal_flush' and any(isinstance(row,SqlVariantEventORM) and row.event_type=='family.derivation.completed' for row in session.new))
        result=await original_flush(session,*args,**kwargs)
        if delay:paused=True;await asyncio.sleep(1.6)
        return result
    async def slow_read(session,row):
        nonlocal paused
        result=await original_read(session,row)
        if stage=='terminal_history' and not paused and row.state=='needs_attention':
            paused=True;await asyncio.sleep(1.6)
        return result
    monkeypatch.setattr(AsyncSession,'flush',slow_flush)
    monkeypatch.setattr(families,'_read',slow_read)
    payload=request(family)
    with pytest.raises(SqlVariantError,match='LEASE_EXPIRED'):await run(env,service,family,payload)
    assert paused and await master_rows(env)==original
    assert await env.platform.get_project(family.members[0].planned_project_id) is None
    async with env.factory() as session:
        for model in (ProjectVersionORM,AssetORM,TimelineORM,TimelineVersionORM):
            assert await session.scalar(select(func.count()).select_from(model).where(model.project_id==family.members[0].planned_project_id))==0
        events=(await session.scalars(select(SqlVariantEventORM).where(SqlVariantEventORM.family_id==family.family_id).order_by(SqlVariantEventORM.version))).all()
        assert [row.event_type for row in events]==['family.reserved','family.derivation.claimed','family.derivation.unknown']
    observed,replayed=await run(env,service,family,payload)
    assert replayed and observed.state=='unknown' and observed.error_code=='SQL_VARIANT_DERIVATION_LEASE_EXPIRED'
    source=family.snapshot.binding.assets[0]
    # Independent copies remain held, never automatically overwritten/replayed.
    target=target_key(env.workspace.workspace_id,family.members[0].planned_project_id,family.members[0].member_id,source.asset_id,source.content_type)
    assert env.storage._path(target).is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('claim_id','vfc_foreign_claim'),('state','cancelled')])
async def test_terminal_durable_claim_cas_rejects_mutation_during_child_flush(env,monkeypatch,field,value):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import update
    families,family,repo,service=await setup(env)
    original_flush=AsyncSession.flush;changed=False
    async def mutate_after_flush(session,*args,**kwargs):
        nonlocal changed
        child=not changed and any(isinstance(row,VideoProjectORM) and row.provenance.get('source_type')=='storyboard_variant_derivative' for row in session.new)
        result=await original_flush(session,*args,**kwargs)
        if child:
            changed=True
            await session.execute(update(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.family_id==family.family_id,
                SqlVariantArtifactReceiptORM.kind=='storyboard_derivation').values(**{field:value}).execution_options(synchronize_session=False))
        return result
    monkeypatch.setattr(AsyncSession,'flush',mutate_after_flush)
    with pytest.raises(SqlVariantError,match='DERIVATION_CONFLICT'):await run(env,service,family,request(family))
    assert changed and await env.platform.get_project(family.members[0].planned_project_id) is None
    observed,replayed=await run(env,service,family,request(family))
    assert replayed and observed.state=='unknown'


@pytest.mark.asyncio
@pytest.mark.parametrize('target,stage',[('copy','child_flush'),('source','child_flush'),('copy','terminal_flush'),('source','terminal_history')])
async def test_late_physical_byte_mutation_rolls_back_all_child_rows_and_ready_history(env,monkeypatch,target,stage):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.sql_variant_db import SqlVariantEventORM
    families,family,repo,service=await setup(env)
    original=await master_rows(env)
    source=family.snapshot.binding.assets[0];member=family.members[0]
    old=await env.assets.get_asset(source.asset_id)
    path=env.storage._path(old.object_key if target=='source' else target_key(env.workspace.workspace_id,
        member.planned_project_id,member.member_id,source.asset_id,source.content_type))
    original_flush=AsyncSession.flush;original_read=families._read;changed=False
    def mutate():
        nonlocal changed
        changed=True;path.write_bytes(b'owned bytes changed after first completed verification')
    async def change_flush(session,*args,**kwargs):
        trigger=not changed and (
            stage=='child_flush' and any(isinstance(row,VideoProjectORM) and row.provenance.get('source_type')=='storyboard_variant_derivative' for row in session.new)
            or stage=='terminal_flush' and any(isinstance(row,SqlVariantEventORM) and row.event_type=='family.derivation.completed' for row in session.new))
        value=await original_flush(session,*args,**kwargs)
        if trigger:mutate()
        return value
    async def change_read(session,row):
        value=await original_read(session,row)
        if stage=='terminal_history' and not changed and row.state=='needs_attention':mutate()
        return value
    monkeypatch.setattr(AsyncSession,'flush',change_flush);monkeypatch.setattr(families,'_read',change_read)
    payload=request(family)
    with pytest.raises(SqlVariantError,match='COPY_RESULT_CHANGED'):await run(env,service,family,payload)
    assert changed and await env.platform.get_project(member.planned_project_id) is None
    assert await master_rows(env)==original
    async with env.factory() as session:
        for model in (ProjectVersionORM,AssetORM,TimelineORM,TimelineVersionORM):
            assert await session.scalar(select(func.count()).select_from(model).where(model.project_id==member.planned_project_id))==0
        events=(await session.scalars(select(SqlVariantEventORM).where(SqlVariantEventORM.family_id==family.family_id))).all()
        assert all(row.event_type!='family.derivation.completed' for row in events)
    observed,replayed=await run(env,service,family,payload)
    assert replayed and observed.state=='unknown' and observed.error_code=='SQL_VARIANT_COPY_RESULT_CHANGED'
    assert path.read_bytes()==b'owned bytes changed after first completed verification'


@pytest.mark.asyncio
async def test_final_read_actual_canonical_currentness_false_is_not_ignored(env,monkeypatch):
    families,family,repo,service=await setup(env)
    original=await master_rows(env);read=families._read;changed=False;observed_false=False
    async def change_before_terminal_read(session,row):
        nonlocal changed,observed_false
        if not changed and row.state=='needs_attention':
            changed=True
            source=await session.scalar(select(TimelineORM).where(TimelineORM.project_id==env.project.project_id))
            parent=await session.get(TimelineVersionORM,source.current_version_id)
            snapshot=copy.deepcopy(parent.snapshot_json);snapshot['tracks'][0]['clips'][0]['opacity']=.8
            from app.timeline_models import TimelineSnapshot
            # Actual existing canonical writer in this isolated transaction, not
            # a mocked boolean or fabricated provider result.
            await env.timeline.commit_mutation_in_session(session=session,project_id=env.project.project_id,
                expected_version=source.current_version,snapshot=TimelineSnapshot.model_validate(snapshot),
                mutation={'type':'fixture-canonical-race'},actor_ref='fixture-editor')
            await session.flush()
        value=await read(session,row)
        if row.state=='needs_attention':observed_false=not value.source_current
        return value
    monkeypatch.setattr(families,'_read',change_before_terminal_read)
    payload=request(family)
    with pytest.raises(SqlVariantError,match='MASTER_BINDING_CHANGED'):await run(env,service,family,payload)
    assert changed and observed_false and await master_rows(env)==original
    assert await env.platform.get_project(family.members[0].planned_project_id) is None
    observed,replayed=await run(env,service,family,payload)
    assert replayed and observed.state=='unknown'


@pytest.mark.asyncio
async def test_source_timeline_lock_uses_existing_writer_scope_after_project_before_family(env,monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.dml import Update
    from sqlalchemy.sql.selectable import Select
    from sqlalchemy.dialects.postgresql import dialect
    families,family,repo,_=await setup(env)
    execute=AsyncSession.execute;scalar=AsyncSession.scalar;sequence=[]
    def capture(statement):
        if isinstance(statement,Update) and statement.table.name=='video_projects':sequence.append('project-writer')
        if isinstance(statement,Select) and statement._for_update_arg is not None:
            sql=str(statement.compile(dialect=dialect()))
            if 'FROM timelines' in sql:sequence.append('timeline-lock')
            if 'FROM sql_variant_families' in sql:sequence.append('family-lock')
    async def checked_execute(session,statement,*args,**kwargs):capture(statement);return await execute(session,statement,*args,**kwargs)
    async def checked_scalar(session,statement,*args,**kwargs):capture(statement);return await scalar(session,statement,*args,**kwargs)
    monkeypatch.setattr(AsyncSession,'execute',checked_execute);monkeypatch.setattr(AsyncSession,'scalar',checked_scalar)
    await repo.claim(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    assert sequence.index('project-writer')<sequence.index('timeline-lock')<sequence.index('family-lock')
    # Actual SQLite invocation + emitted PG statement contract only. PostgreSQL
    # runtime contention/deadlock and other package-only writers NOT_VERIFIED.


@pytest.mark.asyncio
async def test_sql_collision_rolls_back_all_child_records_but_retains_unknown_copy_custody(env):
    families,family,repo,service=await setup(env)
    async with env.factory() as session,session.begin():
        session.add(VideoProjectORM(project_id=family.members[0].planned_project_id,workspace_id=env.workspace.workspace_id,
            slug='existing-collision',name='Actual collision fixture',niche='technology'))
    with pytest.raises(SqlVariantError,match='DERIVATION_CONFLICT'):await run(env,service,family,request(family))
    async with env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(AssetORM).where(AssetORM.project_id==family.members[0].planned_project_id))==0
        assert await session.scalar(select(func.count()).select_from(ProjectVersionORM).where(ProjectVersionORM.project_id==family.members[0].planned_project_id))==0
    current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    assert current.state=='recovery_required' and current.members[0].child_project_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['source_bytes','destination_bytes','receipt_input'])
async def test_tampered_source_destination_or_rehashed_input_fails_closed(env,mutation):
    families,family,repo,_=await setup(env)
    wrapped=LocalStoryboardCopier(env.storage)
    class Tamper:
        async def copy(self,items):
            if mutation=='source_bytes':
                env.storage._path(next(iter(items.values()))['object_key']).write_bytes(b'fake PNG')
            copies=await wrapped.copy(items)
            if mutation=='destination_bytes':env.storage._path(next(iter(copies.values()))['object_key']).write_bytes(b'fake PNG')
            if mutation=='receipt_input':
                async with env.factory() as session,session.begin():
                    row=await session.scalar(select(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.kind=='storyboard_derivation'))
                    value=copy.deepcopy(row.input_json);value['source_content']['snapshot']['content']['original_text']='forged'
                    row.input_json=value;row.input_sha256=digest(value)
            return copies
        async def verify_all(self,copies,**kwargs):await wrapped.verify_all(copies,**kwargs)
    with pytest.raises(SqlVariantError):await run(env,SqlStoryboardDerivationService(repo,Tamper()),family,request(family))
    assert await env.platform.get_project(family.members[0].planned_project_id) is None


@pytest.mark.asyncio
async def test_scope_actor_and_exact_request_replay_binding_before_any_copy(env):
    families,family,repo,service=await setup(env)
    payload=request(family);receipt,_=await run(env,service,family,payload)
    with pytest.raises(SqlVariantError,match='IDEMPOTENCY_CONFLICT'):
        await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,payload,actor_ref='different-editor')
    with pytest.raises(SqlVariantError,match='IDEMPOTENCY_CONFLICT'):
        await run(env,service,family,payload.model_copy(update={'member_id':family.members[1].member_id}))
    with pytest.raises(KeyError):
        await service.derive('foreign-workspace',env.project.project_id,family.family_id,payload,actor_ref='fixture-editor')


@pytest.mark.asyncio
async def test_cancel_after_completed_child_does_not_delete_child_or_grant_approval(env):
    families,family,repo,service=await setup(env)
    receipt,_=await run(env,service,family,request(family))
    current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    cancelled,_=await families.cancel(env.workspace.workspace_id,env.project.project_id,family.family_id,
        FamilyVersionRequest(expected_version=current.version,expected_snapshot_sha256=current.snapshot_sha256,
            request_key='explicit-family-cancel-after-child'),actor_ref='fixture-editor')
    assert cancelled.state=='cancelled' and cancelled.members[0].child_project_id==receipt.result['child_project_id']
    assert cancelled.members[0].state=='needs_attention' and cancelled.members[1].state=='cancelled'
    assert (await env.timeline.get_timeline(receipt.result['child_project_id'])).approval_status=='draft'


@pytest.mark.asyncio
async def test_immutable_child_initial_content_or_timeline_rehash_cannot_launder_receipt(env):
    families,family,repo,service=await setup(env)
    receipt,_=await run(env,service,family,request(family))
    async with env.factory() as session,session.begin():
        row=await session.get(TimelineVersionORM,receipt.result['timeline_version_id'])
        value=copy.deepcopy(row.snapshot_json);value['tracks'][0]['clips'][0]['label']='forged';row.snapshot_json=value
        saved=await session.get(SqlVariantArtifactReceiptORM,receipt.receipt_id)
        result=copy.deepcopy(saved.result_json);result['timeline_sha256']=digest(value)
        saved.result_json=result;saved.result_sha256=digest(result)
    with pytest.raises(SqlVariantError,match='FAMILY_EVIDENCE_CHANGED'):
        await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)


@pytest.mark.asyncio
async def test_ready_receipt_replay_verifies_actual_bytes_without_copy_or_regeneration(env):
    families,family,repo,service=await setup(env)
    payload=request(family);receipt,_=await run(env,service,family,payload)
    copied=next(iter(receipt.result['copies'].values()))
    env.storage._path(copied['object_key']).write_bytes(b'changed child bytes')
    with pytest.raises(SqlVariantError,match='COPY_RESULT_CHANGED'):
        await run(env,service,family,payload)
    current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    assert current.version==3 and current.members[0].child_project_id==receipt.result['child_project_id']
    assert env.storage._path(copied['object_key']).read_bytes()==b'changed child bytes'


@pytest.mark.asyncio
async def test_source_file_changes_after_copy_is_rechecked_before_child_commit(env):
    families,family,repo,_=await setup(env)
    wrapped=LocalStoryboardCopier(env.storage)
    class SourceTamper:
        async def copy(self,items):
            copied=await wrapped.copy(items)
            env.storage._path(next(iter(items.values()))['object_key']).write_bytes(b'changed original bytes')
            return copied
        async def verify_all(self,copies,**kwargs):await wrapped.verify_all(copies,**kwargs)
    with pytest.raises(SqlVariantError,match='COPY_RESULT_CHANGED'):
        await run(env,SqlStoryboardDerivationService(repo,SourceTamper()),family,request(family))
    assert await env.platform.get_project(family.members[0].planned_project_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('asset_class','render'),('project_version_id',None),('kind','unknown')])
async def test_child_asset_lineage_metadata_cannot_be_rebound_after_verified_copy(env,field,value):
    families,family,repo,service=await setup(env)
    receipt,_=await run(env,service,family,request(family))
    async with env.factory() as session,session.begin():
        row=await session.get(AssetORM,next(iter(receipt.result['asset_map'].values())))
        setattr(row,field,value)
    with pytest.raises(SqlVariantError,match='FAMILY_EVIDENCE_CHANGED'):
        await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('binding',['uploaded_audio_bindings_v1','transcript_revision'])
async def test_s3_audio_transcript_sources_are_explicitly_unsupported_before_any_derivation_write(env,binding):
    families,payload,_,_,built=await ready(env)
    if binding=='uploaded_audio_bindings_v1':
        # A valid bound audio-version fixture belongs in S3. This synthetic marker is
        # deliberately NOT a successful ASR record and must never authorize copying.
        # S1 rejects malformed bindings first; the semantic S2 guard is tested with
        # transcript_revision while retaining the malformed marker safety check.
        async with env.factory() as session,session.begin():
            row=await session.get(TimelineVersionORM,built.current_version_id)
            value=copy.deepcopy(row.snapshot_json);value['metadata'][binding]={'upl_not_provider_output':{'fixture':'not-provider-output'}};row.snapshot_json=value
        with pytest.raises((SqlVariantError,ValueError,KeyError)):
            await families.availability(env.workspace.workspace_id,env.project.project_id)
        return
    async with env.factory() as session,session.begin():
        row=await session.get(TimelineVersionORM,built.current_version_id)
        value=copy.deepcopy(row.snapshot_json);value['metadata'][binding]={'transcript_id':'trn_fixture_not_approved'};row.snapshot_json=value
    # Existing S1 already rejects a storyboard pretending to have video ASR.
    with pytest.raises(SqlVariantError,match='TRANSCRIPT_SELECTION_CHANGED'):
        await families.availability(env.workspace.workspace_id,env.project.project_id)
    async with env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(SqlVariantArtifactReceiptORM))==0


@pytest.mark.asyncio
async def test_explicit_mixed_mode_contract_defers_to_s3_without_claim_or_copy(env):
    families,payload,_,_,built=await ready(env)
    async with env.factory() as session,session.begin():
        row=await session.get(TimelineVersionORM,built.current_version_id)
        value=copy.deepcopy(row.snapshot_json);value['metadata']['source_kind']='mixed';row.snapshot_json=value
    # Explicit mode fixture only; no fake video/ASR/upload or provider success.
    available=await families.availability(env.workspace.workspace_id,env.project.project_id)
    assert available.binding.source_mode=='mixed'
    payload=payload.model_copy(update={'expected_binding_sha256':available.binding_sha256})
    family,_=await families.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    service=SqlStoryboardDerivationService(SqlStoryboardDerivationRepository(families),LocalStoryboardCopier(env.storage))
    with pytest.raises(SqlVariantError,match='S3_SOURCE_UNSUPPORTED'):await run(env,service,family,request(family))
    current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    assert current.version==1 and current.state=='reserved'
    async with env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(SqlVariantArtifactReceiptORM))==0


@pytest.mark.asyncio
async def test_unknown_derivative_rights_remain_blocked_by_existing_publishing_gate(env):
    families,family,repo,service=await setup(env)
    receipt,_=await run(env,service,family,request(family))
    from app.publishing_logic import validate_rights
    child=await env.assets.get_asset(next(iter(receipt.result['asset_map'].values())))
    validation=validate_rights([child])
    assert validation.status=='failed' and validation.checks[0].code=='RIGHTS_NOT_VERIFIED'
    assert validation.checks[0].passed is False
    assert validation.checks[0].evidence['rights_status']=='unknown'


def test_center_crop_exact_geometry_is_bounded_and_request_ack_is_explicit():
    from app.sql_variant_identity import center_crop
    from pydantic import ValidationError
    for target in [(1920,1080),(1080,1920),(1080,1080),(1080,1350)]:
        crop=center_crop(270,480,*target)
        assert abs(270*crop['width']/(480*crop['height'])-target[0]/target[1])<1e-9
        assert crop['x']+crop['width']<=1 and crop['y']+crop['height']<=1
    with pytest.raises(ValidationError):DeriveStoryboardRequest(expected_version=1,expected_snapshot_sha256='a'*64,
        member_id='vfm_'+'a'*32,request_key='explicit-draft-ack-fixture',acknowledge_unapproved_child=1)
