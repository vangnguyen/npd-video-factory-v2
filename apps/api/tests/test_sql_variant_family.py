"""Owned SQLite/manual storyboard contracts, no model/provider/network or fake upload.

First-party PNG bytes and the existing canonical builder are real local inputs;
fixture script approval is not video approval or Owner UAT.
"""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db import Base, AssetORM, VideoProjectORM
from app.auto_edit_db import UploadSessionORM
from app.content_models import ContentDocument, ContentSaveRequest
from app.content_service import prepare_document
from app.platform_models import WorkspaceCreate, ProjectCreate
from app.sql_variant_models import (NoAuthority, VariantCatalog, VariantProfile, default_catalog,
    FamilyReserveRequest, FamilyVersionRequest, AssetReceiptReserveRequest, canonical, digest)
from app.sql_variant_repository import SqlVariantFamilyRepository, SqlVariantError, record_value
from app.sql_variant_db import (SqlVariantFamilyORM, SqlVariantMemberORM,
    SqlVariantArtifactReceiptORM, SqlVariantEventORM)
from app.timeline_db import TimelineORM
from app.production_db import ProductionPackageORM
from test_mvp1_multi_input import env as original_environment, author, timeline, ROOT


@pytest.fixture
async def env(tmp_path):
    generator = original_environment.__wrapped__(tmp_path)
    value = await anext(generator)
    value.project = await value.platform.create_project(value.workspace.workspace_id,
        ProjectCreate(slug='technology-master',name='Explicit technology education fixture',niche='technology'))
    try:
        yield value
    finally:
        await value.engine.dispose()
        await generator.aclose()


async def ready(env):
    version = await author(env, original='Đây là dữ liệu kiểm thử công nghệ được cung cấp.')
    built = await timeline(env, version)
    repo = SqlVariantFamilyRepository(env.factory)
    available = await repo.availability(env.workspace.workspace_id, env.project.project_id)
    payload = FamilyReserveRequest(expected_project_version=available.binding.project_version,
        expected_timeline_version=built.current_version, expected_timeline_version_id=built.current_version_id,
        expected_binding_sha256=available.binding_sha256, catalog_ref=available.catalog.catalog_ref,
        catalog_sha256=available.catalog_sha256, profile_refs=[p.profile_ref for p in available.catalog.profiles],
        request_key='explicit-sql-variant-family-fixture', acknowledge_draft_derivation=True)
    return repo, payload, available, version, built


async def counts(env):
    async with env.factory() as session:
        return {model.__tablename__: await session.scalar(select(func.count()).select_from(model))
            for model in (VideoProjectORM, AssetORM, SqlVariantFamilyORM, SqlVariantMemberORM,
                          SqlVariantArtifactReceiptORM, SqlVariantEventORM)}


async def original_rows(env):
    async with env.factory() as session:
        result = {}
        for mapper in Base.registry.mappers:
            model = mapper.class_
            if model.__tablename__.startswith('sql_variant_'):
                continue
            rows = (await session.scalars(select(model).order_by(*model.__table__.primary_key.columns))).all()
            result[model.__tablename__] = canonical([record_value(r) for r in rows])
        return result


def test_catalog_version_data_contract_and_six_destinations_preserve_four_geometry_profiles():
    catalog = default_catalog()
    saved = VariantCatalog.model_validate_json((ROOT/'packages/contracts/sql-variant-profiles.json').read_bytes())
    assert saved == catalog
    assert len({p.target for p in catalog.profiles}) == 6
    assert len({p.aspect_ratio for p in catalog.profiles}) == 4
    vertical = [p for p in catalog.profiles if p.aspect_ratio == '9:16']
    assert len(vertical) == 3 and len({p.profile_ref for p in vertical}) == 3
    assert catalog.profiles[0].final_profile == 'landscape-1920x1080'
    assert NoAuthority().model_dump() == dict(provider_calls=0, new_inference_calls=0, child_projects_created=0,
        source_bytes_verified=False, approval_inherited=False, rights_override_inherited=False,
        automatic_render=False, publishing_enabled=False)


@pytest.mark.parametrize('field,value', [('width',1080),('platform','tiktok'),('review_profile','review-540x960'),('height',True)])
def test_profiles_cannot_be_retargeted_or_coerced(field,value):
    data=default_catalog().profiles[0].model_dump();data[field]=value
    with pytest.raises(ValidationError):VariantProfile.model_validate(data)


@pytest.mark.parametrize('field,value', [('approval_inherited',0),('approval_inherited',True),
    ('provider_calls',False),('child_projects_created',1),('source_bytes_verified',True),('publishing_enabled',True)])
def test_no_authority_uses_exact_boolean_and_integer_contract(field,value):
    with pytest.raises(ValidationError):NoAuthority.model_validate({field:value})


def test_constructor_no_io_and_later_catalog_mutation_cannot_change_frozen_configuration():
    def denied():raise AssertionError('No IO in constructor or catalog')
    configured=default_catalog();repo=SqlVariantFamilyRepository(denied,catalog=configured)
    configured.profiles.pop()
    public=repo.catalog();public.profiles.pop()
    assert len(repo.catalog().profiles)==6
    broken=default_catalog().model_copy(update={'profiles':[default_catalog().profiles[0]]*6})
    with pytest.raises(ValidationError):SqlVariantFamilyRepository(denied,catalog=broken)


@pytest.mark.asyncio
async def test_actual_source_reserves_six_members_atomically_with_no_children_assets_or_authority(env):
    repo,payload,available,_,_=await ready(env)
    before=await original_rows(env);prior=await counts(env)
    family,replayed=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    assert not replayed and family.state=='reserved' and family.version==1 and family.source_current
    assert len(family.members)==len({m.planned_project_id for m in family.members})==6
    assert all(m.child_project_id is None and m.state=='reserved' for m in family.members)
    assert family.snapshot.binding==available.binding
    assert (await counts(env))['video_projects']==prior['video_projects']
    assert (await counts(env))['assets']==prior['assets']
    assert (await counts(env))['sql_variant_members']==6
    assert await original_rows(env)==before
    assert 'object_key' not in available.binding.assets[0].model_dump()
    assert family.safety.source_bytes_verified is False and family.safety.publishing_enabled is False
    assert (await env.platform.get_project(env.project.project_id)).niche=='technology'


@pytest.mark.asyncio
async def test_tenant_foreign_master_and_foreign_family_are_hidden_before_write(env):
    repo,payload,_,_,_=await ready(env)
    family,_=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    foreign=await env.platform.create_workspace(WorkspaceCreate(slug='foreign-workspace',name='Fixture',owner_ref='fixture'))
    before=await counts(env)
    with pytest.raises(KeyError,match='MASTER_NOT_FOUND'):
        await repo.reserve(foreign.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    other=await env.platform.create_project(env.workspace.workspace_id,ProjectCreate(slug='other-family',name='Fixture'))
    assert await repo.get(env.workspace.workspace_id,other.project_id,family.family_id) is None
    assert (await counts(env))['sql_variant_families']==before['sql_variant_families']


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['project_version','timeline_version','timeline_version_id','binding','catalog','target','duplicate','ack'])
async def test_mutated_request_or_stale_expected_source_cannot_reserve(env,change):
    repo,payload,_,_,_=await ready(env)
    values={'project_version':{'expected_project_version':payload.expected_project_version+1},
        'timeline_version':{'expected_timeline_version':payload.expected_timeline_version+1},
        'timeline_version_id':{'expected_timeline_version_id':'tlv_foreign_fixture'},'binding':{'expected_binding_sha256':'a'*64},
        'catalog':{'catalog_sha256':'b'*64},'target':{'profile_refs':['unapproved-platform@1']},
        'duplicate':{'profile_refs':[payload.profile_refs[0]]*2},'ack':{'acknowledge_draft_derivation':1}}[change]
    bad=payload.model_copy(update=values)
    before=await counts(env)
    with pytest.raises((SqlVariantError,ValidationError)):
        await repo.reserve(env.workspace.workspace_id,env.project.project_id,bad,actor_ref='fixture-editor')
    assert await counts(env)==before


@pytest.mark.asyncio
async def test_idempotency_preserves_exact_original_result_and_conflicts_on_body_or_actor(env):
    repo,payload,_,_,_=await ready(env)
    first,_=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    second,replayed=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    assert replayed and second==first
    with pytest.raises(SqlVariantError,match='IDEMPOTENCY_CONFLICT'):
        await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload.model_copy(update={'profile_refs':payload.profile_refs[::-1]}),actor_ref='fixture-editor')
    with pytest.raises(SqlVariantError,match='ACTOR_CHANGED'):
        await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='another-editor')
    assert (await counts(env))['sql_variant_families']==1


@pytest.mark.asyncio
async def test_two_sql_instances_reserve_same_request_once_under_concurrency(env):
    repo,payload,_,_,_=await ready(env)
    second_engine=create_async_engine(env.engine.url)
    other=SqlVariantFamilyRepository(async_sessionmaker(second_engine,expire_on_commit=False))
    try:
        results=await asyncio.gather(*(r.reserve(env.workspace.workspace_id,env.project.project_id,payload,
            actor_ref='fixture-editor') for r in [repo,other,repo,other]),return_exceptions=True)
        assert not any(isinstance(r,BaseException) for r in results),results
        assert len({f.family_id for f,_ in results})==1
        assert sum(not replayed for _,replayed in results)==1
        assert (await counts(env))['sql_variant_members']==6
        assert (await counts(env))['sql_variant_events']==1
    finally:await second_engine.dispose()


@pytest.mark.asyncio
async def test_failure_after_member_inserts_rolls_back_whole_reservation_without_source_mutation(env,monkeypatch):
    repo,payload,_,_,_=await ready(env);before=await counts(env);original=await original_rows(env)
    def fail(*args):raise RuntimeError('EXPLICIT FIXTURE RESERVATION FAILURE')
    monkeypatch.setattr(repo,'_event',fail)
    with pytest.raises(RuntimeError,match='FIXTURE RESERVATION FAILURE'):
        await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    assert await counts(env)==before and await original_rows(env)==original


@pytest.mark.asyncio
async def test_same_version_asset_metadata_drift_invalidates_binding_and_future_receipt_without_losing_history(env):
    repo,payload,available,_,_=await ready(env)
    family,_=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    asset=available.binding.assets[0]
    async with env.factory() as session,session.begin():
        row=await session.get(AssetORM,asset.asset_id)
        await session.execute(update(AssetORM).where(AssetORM.asset_id==asset.asset_id)
            .values(provenance={**row.provenance,'fixture_metadata_changed':True}))
    loaded=await repo.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    assert loaded.snapshot==family.snapshot and loaded.source_current is False
    changed=payload.model_copy(update={'request_key':'new-source-binding-reservation-fixture'})
    with pytest.raises(SqlVariantError,match='MASTER_BINDING_CHANGED'):
        await repo.reserve(env.workspace.workspace_id,env.project.project_id,changed,actor_ref='fixture-editor')
    receipt=AssetReceiptReserveRequest(expected_version=1,expected_snapshot_sha256=family.snapshot_sha256,
        request_key='changed-source-artifact-reservation-fixture',member_id=family.members[0].member_id,
        source_asset_id=asset.asset_id,expected_source_record_sha256=asset.record_sha256)
    with pytest.raises(SqlVariantError,match='MASTER_BINDING_CHANGED'):
        await repo.reserve_asset_receipt(env.workspace.workspace_id,env.project.project_id,family.family_id,receipt,actor_ref='fixture-editor')


@pytest.mark.asyncio
async def test_new_content_invalidates_derivation_currentness_but_preserves_frozen_family_and_allows_cancel(env):
    repo,payload,_,version,_=await ready(env)
    family,_=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    changed=prepare_document(ContentDocument(input_kind='script',original_text='Đây là nội dung mới được cung cấp.'))
    await env.content.save(env.project.project_id,ContentSaveRequest(expected_content_version_id=version.project_version_id,document=changed))
    loaded=await repo.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    assert not loaded.source_current and loaded.snapshot_sha256==family.snapshot_sha256
    request=FamilyVersionRequest(expected_version=1,expected_snapshot_sha256=family.snapshot_sha256,request_key='cancel-old-family-version-fixture')
    result,replayed=await repo.cancel(env.workspace.workspace_id,env.project.project_id,family.family_id,request,actor_ref='fixture-editor')
    assert not replayed and result.state=='cancelled' and result.version==2
    assert all(m.state=='cancelled' for m in result.members)
    repeated,replayed=await repo.cancel(env.workspace.workspace_id,env.project.project_id,family.family_id,request,actor_ref='fixture-editor')
    assert replayed and repeated==result


@pytest.mark.asyncio
async def test_asset_receipt_reservation_is_atomic_scoped_and_has_no_result_claim_or_copy(env):
    repo,payload,available,_,_=await ready(env)
    family,_=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    source=available.binding.assets[0];original=await original_rows(env)
    request=AssetReceiptReserveRequest(expected_version=1,expected_snapshot_sha256=family.snapshot_sha256,
        request_key='explicit-asset-receipt-reservation-fixture',member_id=family.members[0].member_id,
        source_asset_id=source.asset_id,expected_source_record_sha256=source.record_sha256)
    results=await asyncio.gather(*(repo.reserve_asset_receipt(env.workspace.workspace_id,env.project.project_id,
        family.family_id,request,actor_ref='fixture-editor') for _ in range(3)),return_exceptions=True)
    assert not any(isinstance(r,BaseException) for r in results),results
    assert len({r.receipt_id for r,_ in results})==1 and sum(not replayed for _,replayed in results)==1
    receipt=results[0][0]
    assert receipt.state=='reserved' and receipt.target_asset_id is None and receipt.result is None and receipt.claim_id is None
    assert receipt.safety.source_bytes_verified is False and await original_rows(env)==original
    foreign=request.model_copy(update={'member_id':'vfm_'+'f'*32,'request_key':'foreign-member-reservation-fixture'})
    with pytest.raises(SqlVariantError,match='SOURCE_OR_MEMBER_CHANGED'):
        await repo.reserve_asset_receipt(env.workspace.workspace_id,env.project.project_id,family.family_id,foreign,actor_ref='fixture-editor')
    cancel=FamilyVersionRequest(expected_version=1,expected_snapshot_sha256=family.snapshot_sha256,request_key='cancel-reserved-asset-family-fixture')
    await repo.cancel(env.workspace.workspace_id,env.project.project_id,family.family_id,cancel,actor_ref='fixture-editor')
    cancelled=await repo.get_asset_receipt(env.workspace.workspace_id,env.project.project_id,family.family_id,receipt.receipt_id)
    assert cancelled.state=='cancelled' and cancelled.result is None


@pytest.mark.asyncio
@pytest.mark.parametrize('target',['profile','authority','event','receipt'])
async def test_rehashed_forged_history_is_not_execution_or_selection_authority(env,target):
    repo,payload,available,_,_=await ready(env)
    family,_=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    receipt=None
    if target=='receipt':
        asset=available.binding.assets[0]
        request=AssetReceiptReserveRequest(expected_version=1,expected_snapshot_sha256=family.snapshot_sha256,
            request_key='corrupt-asset-receipt-fixture-key',member_id=family.members[0].member_id,
            source_asset_id=asset.asset_id,expected_source_record_sha256=asset.record_sha256)
        receipt,_=await repo.reserve_asset_receipt(env.workspace.workspace_id,env.project.project_id,family.family_id,request,actor_ref='fixture-editor')
    async with env.factory() as session,session.begin():
        if target=='profile':
            row=await session.get(SqlVariantMemberORM,family.members[0].member_id)
            changed=copy.deepcopy(row.profile_json);changed['width']=1080
            await session.execute(update(SqlVariantMemberORM).where(SqlVariantMemberORM.member_id==row.member_id)
                .values(profile_json=changed,profile_sha256=digest(changed)))
        elif target=='authority':
            row=await session.get(SqlVariantFamilyORM,family.family_id)
            changed=copy.deepcopy(row.snapshot_json);changed['safety']['approval_inherited']=True
            await session.execute(update(SqlVariantFamilyORM).where(SqlVariantFamilyORM.family_id==row.family_id)
                .values(snapshot_json=changed,snapshot_sha256=digest(changed)))
        elif target=='event':
            row=await session.scalar(select(SqlVariantEventORM).where(SqlVariantEventORM.family_id==family.family_id))
            changed=copy.deepcopy(row.payload_json);changed['safety']['publishing_enabled']=True
            await session.execute(update(SqlVariantEventORM).where(SqlVariantEventORM.event_id==row.event_id)
                .values(payload_json=changed,payload_sha256=digest(changed)))
        else:
            row=await session.get(SqlVariantArtifactReceiptORM,receipt.receipt_id)
            changed=copy.deepcopy(row.input_json);changed['safety']['source_bytes_verified']=True
            await session.execute(update(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.receipt_id==row.receipt_id)
                .values(input_json=changed,input_sha256=digest(changed)))
    with pytest.raises(SqlVariantError,match='EVIDENCE_CHANGED'):
        if target=='receipt':await repo.get_asset_receipt(env.workspace.workspace_id,env.project.project_id,family.family_id,receipt.receipt_id)
        else:await repo.get(env.workspace.workspace_id,env.project.project_id,family.family_id)


@pytest.mark.asyncio
async def test_history_cursor_limit_and_restart_are_scoped_to_exact_master(env):
    repo,payload,_,_,_=await ready(env)
    first,_=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    second,_=await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload.model_copy(update={'request_key':'second-variant-reservation-fixture'}),actor_ref='fixture-editor')
    page=await repo.list(env.workspace.workspace_id,env.project.project_id,limit=1)
    assert len(page.items)==1 and page.next_cursor
    next_page=await repo.list(env.workspace.workspace_id,env.project.project_id,limit=1,cursor=page.next_cursor)
    assert len(next_page.items)==1 and next_page.items[0].family_id!=page.items[0].family_id and next_page.next_cursor is None
    other=await env.platform.create_project(env.workspace.workspace_id,ProjectCreate(slug='cursor-foreign',name='Fixture'))
    with pytest.raises(SqlVariantError,match='CURSOR_INVALID'):
        await repo.list(env.workspace.workspace_id,other.project_id,cursor=page.next_cursor)
    with pytest.raises(SqlVariantError,match='PAGE_INVALID'):
        await repo.list(env.workspace.workspace_id,env.project.project_id,limit=True)
    reopened=SqlVariantFamilyRepository(env.factory)
    assert (await reopened.get(env.workspace.workspace_id,env.project.project_id,first.family_id)).snapshot_sha256==first.snapshot_sha256
    assert (await reopened.get(env.workspace.workspace_id,env.project.project_id,second.family_id)).snapshot_sha256==second.snapshot_sha256


@pytest.mark.asyncio
async def test_family_limit_and_stale_cancel_cas_do_not_touch_existing_reservation(env):
    repo,payload,_,_,_=await ready(env)
    bounded=SqlVariantFamilyRepository(env.factory,max_families_per_master=1)
    family,_=await bounded.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    before=await counts(env)
    with pytest.raises(SqlVariantError,match='FAMILY_LIMIT'):
        await bounded.reserve(env.workspace.workspace_id,env.project.project_id,
            payload.model_copy(update={'request_key':'over-limit-family-fixture-key'}),actor_ref='fixture-editor')
    stale=FamilyVersionRequest(expected_version=2,expected_snapshot_sha256=family.snapshot_sha256,
        request_key='stale-family-cancel-fixture-key')
    with pytest.raises(SqlVariantError,match='VERSION_CHANGED'):
        await repo.cancel(env.workspace.workspace_id,env.project.project_id,family.family_id,stale,actor_ref='fixture-editor')
    assert await counts(env)==before and (await repo.get(env.workspace.workspace_id,env.project.project_id,family.family_id)).state=='reserved'


@pytest.mark.asyncio
async def test_user_upload_provenance_cannot_fake_actual_upload_reference(env):
    repo,_,available,_,_=await ready(env)
    asset=available.binding.assets[0]
    async with env.factory() as session,session.begin():
        row=await session.get(AssetORM,asset.asset_id)
        await session.execute(update(AssetORM).where(AssetORM.asset_id==row.asset_id).values(
            provenance={**row.provenance,'source_type':'user_upload','source_reference':'upl_missing_fixture'}))
    with pytest.raises(SqlVariantError,match='UPLOAD_REFERENCE_CHANGED'):
        await repo.availability(env.workspace.workspace_id,env.project.project_id)
    async with env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(UploadSessionORM))==0
        assert await session.scalar(select(func.count()).select_from(SqlVariantFamilyORM))==0


@pytest.mark.asyncio
async def test_asset_version_from_another_project_cannot_be_frozen_as_master_source(env):
    repo,_,available,_,_=await ready(env)
    other=await env.platform.create_project(env.workspace.workspace_id,ProjectCreate(slug='foreign-source-version',name='Fixture'))
    foreign=await env.platform.ensure_initial_version(other.project_id,snapshot={'fixture':True})
    async with env.factory() as session,session.begin():
        await session.execute(update(AssetORM).where(AssetORM.asset_id==available.binding.assets[0].asset_id)
            .values(project_version_id=foreign.project_version_id))
    with pytest.raises(SqlVariantError,match='ASSET_VERSION_SCOPE_CHANGED'):
        await repo.availability(env.workspace.workspace_id,env.project.project_id)


@pytest.mark.asyncio
async def test_planned_id_collision_after_other_member_inserts_rolls_back_all_family_rows(env,monkeypatch):
    repo,payload,_,_,_=await ready(env)
    existing=await env.platform.create_project(env.workspace.workspace_id,ProjectCreate(slug='existing-target-collision',name='Fixture'))
    before=await counts(env);original=await original_rows(env);actual=repo._ids
    def collide(workspace,master,key_sha,request_sha,profile_ref=None):
        result=actual(workspace,master,key_sha,request_sha,profile_ref)
        if profile_ref==payload.profile_refs[-1]:return result[0],existing.project_id
        return result
    monkeypatch.setattr(repo,'_ids',collide)
    with pytest.raises(SqlVariantError,match='PLANNED_PROJECT_COLLISION'):
        await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    assert await counts(env)==before and await original_rows(env)==original


@pytest.mark.asyncio
async def test_client_claims_and_invalid_actor_are_rejected_before_any_reservation_write(env):
    repo,payload,_,_,_=await ready(env);before=await counts(env)
    for claim in ('approval_inherited','rights_override_inherited','publishing_enabled','provider_health','max_ai_cost'):
        with pytest.raises(ValidationError):FamilyReserveRequest.model_validate({**payload.model_dump(),claim:True})
    with pytest.raises(SqlVariantError,match='ACTOR_REQUIRED'):
        await repo.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='private\nactor')
    assert await counts(env)==before


def test_additive_migration_preserves_existing_tables_and_declares_reserved_parent_without_fake_graph_acceptance(tmp_path):
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    spec=importlib.util.spec_from_file_location('owned_variant_migration',ROOT/'apps/api/migrations/versions/0032_ns_sql_variants.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.revision=='0032_ns_sql_variants' and module.down_revision=='0031_ns_video_jobs'
    engine=sa.create_engine('sqlite:///'+str(tmp_path/'additive-only.db'))
    try:
        with engine.begin() as con:
            con.execute(sa.text('CREATE TABLE preserved_source(id INTEGER PRIMARY KEY,payload TEXT NOT NULL)'))
            con.execute(sa.text("INSERT INTO preserved_source VALUES(1,'EXPLICIT ORIGINAL SOURCE')"))
            prior=con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='preserved_source'")).scalar()
            module.op=Operations(MigrationContext.configure(con));module.upgrade()
            assert con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='preserved_source'")).scalar()==prior
            assert con.execute(sa.text('SELECT payload FROM preserved_source')).scalar()=='EXPLICIT ORIGINAL SOURCE'
            inspector=sa.inspect(con)
            assert len([name for name in inspector.get_table_names() if name.startswith('sql_variant_')])==4
            for model in (SqlVariantFamilyORM,SqlVariantMemberORM,SqlVariantArtifactReceiptORM,SqlVariantEventORM):
                assert {c['name']:c['nullable'] for c in inspector.get_columns(model.__tablename__)}=={
                    c.name:c.nullable for c in model.__table__.columns}
            with pytest.raises(RuntimeError,match='Owner approval'):module.downgrade()
        for model in (TimelineORM,ProductionPackageORM):
            assert any(type(c).__name__=='UniqueConstraint' and [col.name for col in c.columns]==['project_id'] for c in model.__table__.constraints)
        print('MIGRATION_GRAPH=NOT_VERIFIED; direct additive SQLite DDL only; reserved parent0031 not supplied by this scope')
    finally:engine.dispose()
