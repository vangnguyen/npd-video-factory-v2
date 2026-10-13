"""Actual SQL optional writer fence, no renderer/DSP/model or approval transfer."""
import copy
from types import SimpleNamespace
import pytest
from sqlalchemy import select,func
from app.db import AssetORM
from app.content_models import ContentDocument,ContentSaveRequest
from app.timeline_models import TimelineCreateRequest
from app.production_models import ProductionPackageCreateRequest,RenderCreateRequest
from app.production_db import ProductionRenderJobORM,ProductionApprovalORM,ProductionEventORM
from app.production_repository import ProductionRepository,ApprovalBoundaryError
from app.sql_variant_repository import SqlVariantError
from app.sql_variant_models import digest
from app.sql_variant_narration_projection import narration_projection,child_cues
from app.sql_variant_narration_render import (VariantNarrationReviewLoader,VariantNarrationTerminalFence,VariantNarrationRenderRequest)
from test_sql_variant_narration_reuse import env,narration_env,run
from test_mvp1_multi_input import ROOT


async def child_review(f):
    # Independent test-only child rights decision; never copied from its master.
    async with f.env.factory() as s,s.begin():
        assets=(await s.scalars(select(AssetORM).where(AssetORM.project_id==f.child.project_id))).all()
        for asset in assets:
            asset.provenance={**asset.provenance,'rights_status':'owned','fixture_child_rights_decision':True}
            asset.version+=1
    version=await f.env.platform.get_version(f.request.expected_child_content_version_id)
    document=ContentDocument.model_validate(version.snapshot['content']).model_copy(update={'approved':True})
    changed=await f.env.content.save(f.child.project_id,ContentSaveRequest(expected_content_version_id=version.project_version_id,document=document))
    built=await f.env.service.create(f.child.project_id,TimelineCreateRequest(source_kind='storyboard_media',
        content_version_id=changed.project_version_id,expected_timeline_version=1))
    package=await f.env.package.create_or_refresh(f.child.project_id,ProductionPackageCreateRequest())
    render=await f.env.package.enqueue_review(f.child.project_id,RenderCreateRequest(
        expected_timeline_version=built.current_version,expected_subtitle_version=package.subtitle.version,
        expected_audio_version=package.audio_mix.version))
    projection=narration_projection(built.snapshot.model_dump(mode='json'),child_cues(built.snapshot.model_dump(mode='json')),package.audio_mix.config.voice)
    request=f.request.model_copy(update={'expected_child_content_version_id':changed.project_version_id,
        'expected_child_timeline_version_id':built.current_version_id,'expected_child_timeline_version':built.current_version,
        'expected_semantic_sha256':digest(projection)})
    receipt,_=await run(f,request)
    render=await f.env.production.start_render(render.render_id)
    loader=VariantNarrationReviewLoader(f.repo,f.copier,f.env.assets,enabled=True)
    selection=VariantNarrationRenderRequest(enabled=True,receipt_id=receipt.receipt_id,family_id=receipt.family_id,
        member_id=receipt.member_id,master_project_id=f.env.project.project_id,input_sha256=receipt.input_sha256,result_sha256=receipt.result_sha256)
    workdir=f.env.tmp/'child-loader';workdir.mkdir()
    narration=await loader.prepare(render,built.snapshot.model_dump(mode='json'),package.subtitle,
        package.audio_mix.config,workdir,selection.model_dump())
    return SimpleNamespace(render=render,narration=narration,receipt=receipt,package=package,built=built,workdir=workdir)


async def test_typed_review_loader_and_atomic_completion_have_fresh_child_review(narration_env):
    f=narration_env;child=await child_review(f)
    assert child.narration['timing'][0]['provider_evidence']==f.evidence.model_dump(mode='json')
    assert (child.workdir/'narration.wav').read_bytes()==f.env.storage._path(f.prepared.object_key).read_bytes()
    assert 'raw_audio_reuse' not in child.narration['timing'][0]
    repository=ProductionRepository(f.env.factory,variant_narration_fence=VariantNarrationTerminalFence(f.repo,f.copier))
    completed=await repository.complete_render(child.render.render_id,output_asset_id=None,
        qc_report={'fixture':True,'not_real_render_qc':True},manifest={'narration':child.narration})
    assert completed.status=='awaiting_review' and completed.approval_id is None and not completed.publishing_allowed
    assert child.narration['variant_narration_reuse']['source_approval_transferred'] is False
    async with f.env.factory() as s:
        assert await s.scalar(select(func.count()).select_from(ProductionApprovalORM).where(ProductionApprovalORM.project_id==f.child.project_id))==0


async def test_explicit_proof_without_typed_configured_fence_fails_closed(narration_env):
    f=narration_env;child=await child_review(f)
    with pytest.raises(ApprovalBoundaryError,match='NOT_CONFIGURED'):
        await f.env.production.complete_render(child.render.render_id,output_asset_id=None,
            qc_report={'fixture':True},manifest={'narration':child.narration})
    assert (await f.env.production.get_render(child.render.render_id)).status=='running'


async def test_source_change_after_terminal_flush_rolls_back_child_and_event(narration_env):
    f=narration_env;child=await child_review(f)
    fence=VariantNarrationTerminalFence(f.repo,f.copier);original=fence.guard
    async def changed(session,render,proof,*,terminal=False):
        if terminal:
            approval=await session.get(ProductionApprovalORM,f.request.source_approval_id)
            approval.status='changes_requested';await session.flush()
        return await original(session,render,proof,terminal=terminal)
    fence.guard=changed
    repository=ProductionRepository(f.env.factory,variant_narration_fence=fence)
    async with f.env.factory() as s:
        before=await s.scalar(select(func.count()).select_from(ProductionEventORM).where(ProductionEventORM.project_id==f.child.project_id))
    with pytest.raises((SqlVariantError,RuntimeError)):
        await repository.complete_render(child.render.render_id,output_asset_id=None,
            qc_report={'fixture':True},manifest={'narration':child.narration})
    current=await f.env.production.get_render(child.render.render_id)
    assert current.status=='running' and current.manifest.get('narration') is None and current.output_asset_id is None
    async with f.env.factory() as s:
        assert (await s.get(ProductionApprovalORM,f.request.source_approval_id)).status=='approved'
        assert await s.scalar(select(func.count()).select_from(ProductionEventORM).where(ProductionEventORM.project_id==f.child.project_id))==before


async def test_explicit_reuse_without_loader_cannot_fall_back_to_provider_or_renderer(narration_env):
    f=narration_env;child=await child_review(f)
    async with f.env.factory() as s,s.begin():
        row=await s.get(ProductionRenderJobORM,child.render.render_id)
        row.manifest_json={**row.manifest_json,'variant_narration_request':{
            'enabled':True,'receipt_id':child.receipt.receipt_id,'family_id':child.receipt.family_id,
            'member_id':child.receipt.member_id,'master_project_id':f.env.project.project_id,
            'input_sha256':child.receipt.input_sha256,'result_sha256':child.receipt.result_sha256}}
    called=[]
    class Denied:
        async def synthesize(self,**kw):called.append('provider');raise AssertionError('provider disabled')
        async def synthesize_narration(self,*a,**kw):called.append('DSP');raise AssertionError('DSP disabled')
        async def render(self,**kw):called.append('renderer');raise AssertionError('renderer disabled')
        async def inspect(self,*a,**kw):called.append('QC');raise AssertionError('QC disabled')
    from app.production_service import ProductionRenderProcessor
    from app.production_logic import TimelineRenderContractValidator
    processor=ProductionRenderProcessor(repository=f.env.production,platform=f.env.platform,
        asset_repository=f.env.assets,object_storage=f.env.storage,renderer=Denied(),qc=Denied(),
        tts_provider=Denied(),audio_engine=Denied(),manifest_validator=TimelineRenderContractValidator(ROOT/'packages/contracts/timeline-render.schema.json'),
        staging_root=f.env.tmp/'no-provider-or-render',brand_name='Fixture')
    result=await processor.process(child.render.render_id)
    assert result.status=='failed' and 'SQL_VARIANT_NARRATION_NOT_CONFIGURED' in result.failure_reason and not called
