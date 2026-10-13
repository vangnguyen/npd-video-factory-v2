"""Signed full orchestration over existing engines and explicit offline fixtures."""
import hashlib,json,shutil,os
from pathlib import Path
from types import SimpleNamespace
import pytest,httpx
from app.service_api_contract import CAPABILITIES
from app.db import AssetORM
from app.auto_edit_repository import AutoEditRepository
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.timeline_repository import TimelineRepository
from app.timeline_service import TimelineService,TimelineContractValidator,PreviewService,DeterministicProxyRenderer
from app.content_service import ContentService
from app.content_models import ContentDocument
from app.content_generation import ContentGenerationService,content_provider_definition
from app.repositories import PostgresJobStore
from app.production_repository import ProductionRepository
from app.production_service import ProductionPackageService,ProductionRenderProcessor,DeterministicTimelineRenderEngine
from app.production_qc import DeterministicProductionQC
from app.production_logic import TimelineRenderContractValidator
from app.publishing_repository import PublishingRepository
from app.publishing_service import PublishingService
from app.publishing_logic import PublishingCapabilityRegistry
from app.publishing_providers import PublishingProviderRegistry
from app.analytics_repository import AnalyticsRepository
from app.analytics_providers import AnalyticsProviderRegistry
from app.analytics_service import AnalyticsService
from app.trend_repository import TrendRepository
from app.trend_service import TrendIntelligenceService
from app.trend_providers import create_trend_provider_registry
from test_service_api import application,signed
from test_agent_hub_bridge import FakeRedis
from test_auto_edit_analysis import setup_services,synthetic_mp4
from test_audio_subtitle_render_qc import DeterministicAudioEngine
from test_publishing import publishing_settings,CAPABILITIES as PUBLISH_CAPABILITIES
from test_analytics_learning import analytics_settings
from test_trend_intelligence import FIXTURE_PATH
from auth_test_support import TEST_HUMAN_HEADERS,install_test_human_auth

ROOT=Path(__file__).resolve().parents[3]

class ExplicitServiceAudioFixture(DeterministicAudioEngine):
    async def mix_original(self,*,narration_path,clips,duration_seconds,gain_db,output_path):
        # Protocol-only audio fixture; it does not establish actual mixing/QC.
        shutil.copyfile(narration_path,output_path)
        return {'fixture':True,'original_audio_clips':len(clips),'duration_seconds':duration_seconds,'gain_db':gain_db}

@pytest.fixture
async def flow(tmp_path):
    engine,factory,platform,assets,uploads,analyses,project,version=await setup_services(tmp_path)
    workspace=await platform.get_workspace(project.workspace_id);redis=FakeRedis()
    app=application(SimpleNamespace(platform=platform,workspace=workspace,redis=redis))
    app.state.upload_service=uploads;app.state.auto_edit_analysis_service=analyses
    timeline_repo=TimelineRepository(factory);storage=uploads.object_storage
    app.state.auto_edit_repository=assets;app.state.object_storage=storage
    app.state.preview_download_root=tmp_path/'preview-downloads';app.state.production_render_download_root=tmp_path/'render-downloads'
    app.state.timeline_service=TimelineService(repository=timeline_repo,platform=platform,auto_edit_repository=assets,
        media_repository=MediaIntelligenceRepository(factory),validator=TimelineContractValidator(ROOT/'packages/contracts/timeline.schema.json'),
        object_storage=storage)
    app.state.preview_service=PreviewService(repository=timeline_repo,platform=platform,auto_edit_repository=assets,object_storage=storage,
        queue=redis,renderer=DeterministicProxyRenderer(),staging_root=tmp_path/'previews')
    await platform.seed_providers([content_provider_definition('fixture'),
        {'provider_key':'espeak','display_name':'Explicit speech fixture','capability':'tts','adapter':'fixture','routing_mode':'primary',
         'status':'healthy','enabled':True,'supports_dry_run':True,'metadata':{'paid':False}},
        {'provider_key':'remotion','display_name':'Explicit render fixture','capability':'rendering','adapter':'fixture','routing_mode':'primary',
         'status':'healthy','enabled':True,'supports_dry_run':True,'metadata':{'paid':False}}])
    app.state.content_service=ContentService(platform)
    app.state.content_generation_service=ContentGenerationService(platform=platform,store=PostgresJobStore(factory,redis,platform=platform),
        queue=redis,mode='fixture')
    production=ProductionRepository(factory)
    app.state.production_package_service=ProductionPackageService(repository=production,timeline_repository=timeline_repo,
        asset_repository=assets,queue=redis,settings=SimpleNamespace(audio_tts_provider='espeak'))
    processor=ProductionRenderProcessor(repository=production,platform=platform,asset_repository=assets,object_storage=storage,
        renderer=DeterministicTimelineRenderEngine(),qc=DeterministicProductionQC(),tts_provider=object(),audio_engine=ExplicitServiceAudioFixture(),
        manifest_validator=TimelineRenderContractValidator(ROOT/'packages/contracts/timeline-render.schema.json'),staging_root=tmp_path/'renders',
        brand_name='Explicit service API fixture')
    psettings=publishing_settings()
    app.state.publishing_service=PublishingService(repository=PublishingRepository(factory),
        production_repository=production,asset_repository=assets,capabilities=PublishingCapabilityRegistry(PUBLISH_CAPABILITIES),
        providers=PublishingProviderRegistry(psettings),settings=psettings)
    asettings=analytics_settings()
    app.state.analytics_service=AnalyticsService(repository=AnalyticsRepository(factory),publishing_repository=PublishingRepository(factory),
        platform_repository=platform,providers=AnalyticsProviderRegistry(asettings),queue=redis,settings=asettings)
    providers=create_trend_provider_registry(FIXTURE_PATH);trend=TrendRepository(factory);await trend.seed_sources(providers.definitions())
    app.state.trend_intelligence_service=TrendIntelligenceService(trend,providers,platform)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://explicit-full-service-fixture') as client:
            yield SimpleNamespace(app=app,client=client,platform=platform,project=project,workspace=workspace,version=version,
                factory=factory,processor=processor,production=production,trace=[])
    finally:await engine.dispose()

async def call(flow,method,path,payload=None,key='step',human=False,extra=None):
    headers={**(TEST_HUMAN_HEADERS if human else {}),**(extra or {})}
    response=await signed(flow.client,method,path,payload,key='service-full-flow-fixture-'+key,extra=headers)
    data=response.json() if response.headers.get('Content-Type','').startswith('application/json') else None
    flow.trace.append({'method':method,'path':path,'status':response.status_code,'response':data,
        'content_sha256':hashlib.sha256(response.content).hexdigest(),'operation_id':response.headers.get('X-NPD-Service-Operation')})
    return response

def record(flow,name,extra=None):
    if not os.environ.get('VF_SERVICE_API_EVIDENCE_DIR'):return
    folder=Path(os.environ['VF_SERVICE_API_EVIDENCE_DIR']);folder.mkdir(parents=True,exist_ok=True)
    path=folder/(name+'.json');assert not path.exists()
    value={'schema_version':'service-api-signed-flow-fixture-v1','scenario':name,'workspace_id':flow.workspace.workspace_id,
        'project_id':flow.project.project_id,'trace':flow.trace,'provider_media_identity_clock_are_fixtures':True,
        'real_provider_calls':0,'paid_calls':0,'Owner_UAT':False,'full_Mode_A_B_accepted':False,
        'production_deployed':False,**(extra or {})}
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

@pytest.mark.asyncio
async def test_upload_analysis_canonical_edit_preview_human_approval_render_and_dry_run_publication(flow):
    pid=flow.project.project_id;base='/v1/projects/'+pid
    data=synthetic_mp4();sha=hashlib.sha256(data).hexdigest()
    upload=await call(flow,'POST','/v1/uploads/init',{'project_id':pid,'filename':'explicit-service-fixture.mp4','media_kind':'video',
        'content_type':'video/mp4','size_bytes':len(data),'checksum_sha256':sha},key='upload')
    assert upload.status_code==201,upload.text
    uid=upload.json()['upload_id']
    part_size=upload.json()['part_size_bytes']
    for offset in range(0,len(data),part_size):
        number=offset//part_size+1;chunk=data[offset:offset+part_size]
        part=await signed(flow.client,'PUT',f'/v1/uploads/{uid}/parts/{number}',raw=chunk,
            key='service-full-flow-upload-part-fixture-'+str(number),
            extra={'Content-Type':'application/octet-stream','X-Part-SHA256':hashlib.sha256(chunk).hexdigest()})
        assert part.status_code==200,part.text
    completed=await call(flow,'POST','/v1/uploads/complete',{'upload_id':uid,'checksum_sha256':sha},key='complete')
    assert completed.status_code==200,completed.text
    analyzed=await call(flow,'POST',base+'/analyze',{'asset_id':completed.json()['asset_id']},key='analyze')
    assert analyzed.status_code==201,analyzed.text
    aid=analyzed.json()['analysis_id']
    assert (await call(flow,'GET',base+'/analyses/'+aid)).json()==analyzed.json()
    timeline=await call(flow,'POST',base+'/timeline',{'analysis_id':aid},key='timeline')
    assert timeline.status_code==201,timeline.text
    tv=timeline.json()['current_version'];head=await call(flow,'GET',base+'/timeline')
    # SQLite drops timezone metadata on domain re-read; canonical edit content
    # and version remain the same. This is not a PostgreSQL timestamp claim.
    assert {k:v for k,v in head.json().items() if k not in ('created_at','updated_at')}=={
        k:v for k,v in timeline.json().items() if k not in ('created_at','updated_at')}
    clip=next(c for t in timeline.json()['snapshot']['tracks'] for c in t['clips'] if c.get('asset_id'))
    edited=await call(flow,'PUT',base+'/timeline',{'expected_version':tv,'operations':[
        {'type':'set_clip_properties','clip_id':clip['clip_id'],'volume':.7}],'actor_ref':'forged-client-editor'},key='edit')
    assert edited.status_code==200,edited.text
    tv=edited.json()['current_version'];assert tv==timeline.json()['current_version']+1
    preview=await call(flow,'POST',base+'/preview',{'timeline_version':tv},key='preview')
    assert preview.status_code==202,preview.text
    ready=await flow.app.state.preview_service.process(preview.json()['preview_id'])
    assert ready.status=='ready'
    view=await call(flow,'GET',base+'/previews/'+ready.preview_id)
    assert view.json()['playback_url'].startswith('/v1/')
    proxy=await call(flow,'GET',view.json()['playback_url'])
    assert proxy.status_code==200 and proxy.headers['Cache-Control']=='no-store' and proxy.content
    package=await call(flow,'POST',base+'/production-package',{'expected_timeline_version':tv},key='package')
    assert package.status_code==201,package.text
    versions={'expected_timeline_version':tv,'expected_subtitle_version':package.json()['subtitle']['version'],
        'expected_audio_version':package.json()['audio_mix']['version']}
    denied=await call(flow,'POST',base+'/render',{**versions,'approval_id':'apr_missing_service_fixture'},key='early-final')
    assert denied.status_code==409
    review=await call(flow,'POST',base+'/review-render',versions,key='review');assert review.status_code==202,review.text
    done=await flow.processor.process(review.json()['render_id']);assert done.status=='awaiting_review',(done.error_code,done.failure_reason,done.qc_report)
    approval=await call(flow,'POST',base+'/approval-requests',{'review_render_id':done.render_id},key='approval-request')
    assert approval.status_code==201,approval.text
    decision={'approval_id':approval.json()['approval_id'],'decision':'approved','reviewer_ref':'forged-client-reviewer'}
    assert (await call(flow,'POST',base+'/approve',decision,key='decision')).status_code==401
    accepted=await call(flow,'POST',base+'/approve',decision,key='decision',human=True)
    assert accepted.status_code==200 and accepted.json()['reviewer_ref']=='usr:test-owner',accepted.text
    final=await call(flow,'POST',base+'/render',{**versions,'approval_id':approval.json()['approval_id']},key='final')
    assert final.status_code==202,final.text
    render=await flow.processor.process(final.json()['render_id']);assert render.status=='ready' and render.qc_status=='passed'
    view=await call(flow,'GET',base+'/renders/'+render.render_id)
    assert view.json()['status']=='ready' and view.json()['playback_url'].startswith('/v1/')
    binary=await call(flow,'GET',view.json()['playback_url'])
    assert binary.status_code==200 and binary.headers['Cache-Control']=='no-store' and binary.content
    publication={'platform':'youtube','final_render_id':render.render_id,'mode':'dry_run',
        'metadata':{'title':'Explicit AI educational service fixture','description':'Synthetic acceptance only','privacy':'private'},
        'actor_ref':'forged-client-owner'}
    assert (await call(flow,'POST',base+'/publish',publication,key='publish')).status_code==401
    published=await call(flow,'POST',base+'/publish',publication,key='publish',human=True)
    assert published.status_code==201,published.text
    assert published.json()['external_action'] is False and published.json()['mock'] is True
    assert (await call(flow,'GET',base+'/publications')).json()[0]['publication_id']==published.json()['publication_id']
    analytics=await call(flow,'GET',base+'/analytics');assert analytics.status_code==200
    assert (await call(flow,'POST',base+'/render',{**versions,'approval_id':approval.json()['approval_id']},key='final')).json()==final.json()
    record(flow,'uploaded-media-orchestration',{'canonical_timeline_version':tv,'source_media_mutated':False,
        'preview_media_sha256':hashlib.sha256(proxy.content).hexdigest(),'render_media_sha256':hashlib.sha256(binary.content).hexdigest(),
        'media_are_nonplayable_protocol_fixtures':True,'real_audio_mix_or_QC_acceptance':False})

@pytest.mark.asyncio
async def test_trend_to_idea_and_content_proposal_uses_existing_engines_and_stays_unapproved(flow):
    ws=flow.workspace.workspace_id
    refreshed=await call(flow,'POST','/v1/trends/refresh',{'workspace_id':ws,'context':{'niche':'technology'}},key='trend')
    assert refreshed.status_code==201,refreshed.text
    trends=await call(flow,'GET','/v1/trends?workspace_id='+ws);assert trends.status_code==200 and trends.json()
    ideas=await call(flow,'POST','/v1/ideas/generate',{'cluster_id':trends.json()[0]['cluster_id'],'niche':'technology'},key='ideas')
    assert ideas.status_code==200 and ideas.json(),ideas.text
    assert (await call(flow,'GET','/v1/opportunities?workspace_id='+ws)).json()
    pid=flow.project.project_id;base='/v1/projects/'+pid
    saved=await call(flow,'PUT',base+'/content',{'document':{'input_kind':'idea','original_text':'Một video giáo dục về AI.'}},key='content')
    assert saved.status_code==200,saved.text
    version=saved.json()['project_version_id'];payload={'expected_content_version_id':version,'idempotency_key':'explicit_inner_generation_fixture'}
    generated=await call(flow,'POST',base+'/generate',payload,key='generate');assert generated.status_code==202,generated.text
    identity=generated.json()['job']['job_id'];await flow.app.state.content_generation_service.process(identity)
    proposal=await call(flow,'GET',base+'/generations/'+identity);assert proposal.status_code==200,proposal.text
    assert proposal.json()['job']['status']=='awaiting_review'
    applied=await call(flow,'POST',base+'/generations/'+identity+'/apply',{'expected_content_version_id':version},key='apply')
    assert applied.status_code==200 and applied.json()['snapshot']['content']['approved'] is False,applied.text
    assert (await call(flow,'POST',base+'/generate',payload,key='generate')).json()==generated.json()
    record(flow,'trend-content-orchestration',{'content_remains_unapproved':True,'creative_provider_is_fixture':True})

@pytest.mark.asyncio
async def test_approval_requires_reviewer_and_publication_requires_owner_even_with_every_service_capability(flow):
    base='/v1/projects/'+flow.project.project_id
    install_test_human_auth(flow.app,platform_repository=flow.platform,platform_role=None,
        workspace_roles={flow.workspace.workspace_id:'editor'})
    approve=await call(flow,'POST',base+'/approve',{'approval_id':'apr_missing_fixture','decision':'approved','reviewer_ref':'owner'},human=True)
    assert approve.status_code==403
    publication={'platform':'youtube','final_render_id':'rnd_missing_fixture','metadata':{'title':'Explicit fixture'}}
    assert (await call(flow,'POST',base+'/publish',publication,human=True)).status_code==403
    record(flow,'human-boundary-denials',{'service_signature_does_not_confer_human_roles':True})
