"""Owned SQLite queue/history/cost integration; synthetic Meta receipts/responses."""
from datetime import timedelta
import json

import httpx
import pytest
from sqlalchemy import select

from app import analytics_meta as meta
from app.analytics_models import AnalyticsSyncRequest
from app.analytics_official import AnalyticsOfficialError
from app.analytics_repository import AnalyticsRepository
from app.analytics_runtime import OfficialAnalyticsRuntime
from app.analytics_service import AnalyticsBoundaryError
from app.db import ProviderRegistryORM, ProviderUsageORM, CostRecordORM, utc_now
from app.publishing_db import PublicationORM
from app.publishing_models import PublicationReceipt, PublishingTargetBinding
from app.publishing_profiles import PROVIDER_KEYS
from test_analytics_learning import analytics_stack
from test_analytics_meta import ig_table,fb_table,REMOTE


@pytest.fixture(params=['instagram_reels','facebook'])
async def meta_stack(tmp_path,request):
    stack=await analytics_stack(tmp_path);platform=request.param;parent=stack.publication
    target=PublishingTargetBinding(workspace_id=parent.workspace_id,profile_id='ppf_meta_read_fixture',profile_version=1,
        platform=platform,provider_key=PROVIDER_KEYS[platform],target_account_id='17890000000000001' if platform=='instagram_reels' else '100000000000001',
        credential_binding_sha256='a'*64)
    current=[target];calls=[];mode=[None];views=[123];profile=['100000000000001','v26.0']
    official_key=stack.providers.OFFICIAL_KEYS[platform]
    async with stack.production.repository.session_factory() as session:
        async with session.begin():
            row=await session.get(PublicationORM,parent.publication_id)
            row.platform=platform;row.provider_key=target.provider_key;row.mode='live';row.dry_run=False
            row.status='published';row.mock=True;row.external_action=False
            row.provider_validation_json={**row.provider_validation_json,'provider_key':target.provider_key,
                'target_binding':target.model_dump(mode='json')}
            row.receipt_json=PublicationReceipt(receipt_id='receipt_EXPLICIT_META_ANALYTICS_FIXTURE',provider_key=target.provider_key,
                platform=platform,mode='live',request_fingerprint=parent.request_fingerprint,remote_post_id=REMOTE,
                remote_url=None,mock=True,external_action=False,created_at=utc_now()).model_dump(mode='json')
            session.add(ProviderRegistryORM(provider_id='pvr_meta_analytics_'+platform,provider_key=official_key,display_name='EXPLICIT META READ FIXTURE',capability='analytics',
                adapter='explicit.fixture',routing_mode='disabled',status='fixture',enabled=False,supports_dry_run=True,
                config_ref=None,metadata_json={'fixture_only':True}))
    def receive(request):
        calls.append({'method':request.method,'path':request.url.path,'query':str(request.url.query)})
        if mode[0]=='rate-limit':return httpx.Response(429,headers={'Retry-After':'40'},json={'error':{'message':'PRIVATE'}})
        if request.url.path.endswith('/me'):
            value={'id':profile[0]}
            if platform=='instagram_reels':value['instagram_business_account']={'id':target.target_account_id}
            if mode[0]=='foreign-account':value['id']='222'
            if mode[0]=='profile-change':profile[0]='333'
        elif dict(request.url.params).get('fields') in ('id,owner,media_product_type','id,from'):
            value={'id':REMOTE,'owner':{'id':target.target_account_id},'media_product_type':'REELS'} if platform=='instagram_reels' else {'id':REMOTE,'from':{'id':target.target_account_id}}
            if mode[0]=='foreign-media':value['id']='222'
        else:
            value=ig_table({'views':views[0],'likes':4}) if platform=='instagram_reels' else fb_table(views=views[0])
        return httpx.Response(200,json=value)
    stack.settings.analytics_external_execution_enabled=True;stack.settings.provider_external_execution_enabled=True
    runtime=OfficialAnalyticsRuntime(repository=stack.repository,publishing_repository=stack.service.publishing_repository,
        settings=stack.settings,target_provider=lambda *_:current[0],
        credential_resolver=lambda selected:meta.MetaAnalyticsCredential(selected,profile[1],profile[0],utc_now()+timedelta(hours=1),
            meta.SCOPES[platform],'EXPLICIT-META-READ-FIXTURE-NOT-A-SECRET'),
        clients={platform:meta.MetaAnalyticsHTTPClient(platform,api_version='v26.0',transport=httpx.MockTransport(receive))})
    runtime.install(stack.providers)
    try:yield stack,runtime,current,calls,mode,views,platform
    finally:await stack.production.engine.dispose()


async def reserve(stack,suffix='initial',query=None):
    return await stack.service.create_sync(project_id=stack.production.project.project_id,
        payload=AnalyticsSyncRequest(publication_id=stack.publication.publication_id,provider_mode='official',query=query),
        idempotency_key='meta-analytics-runtime-fixture-'+suffix)


@pytest.mark.asyncio
async def test_meta_queue_persists_mock_metrics_history_costs_and_reopens_without_provider(meta_stack):
    stack,runtime,current,calls,mode,views,platform=meta_stack
    sync,replay=await reserve(stack);assert not replay
    done=await stack.processor.process(sync.sync_id)
    assert done.status=='succeeded' and done.mock and not done.external_call
    assert len(calls)==3 and all(call['method']=='GET' for call in calls)
    first=(await stack.repository.list_snapshots(sync.project_id))[0]
    assert first.metrics.views==123 and first.metrics.watch_time is None and first.metrics.revenue is None
    assert first.evidence['publication_time'] is None and first.evidence['query'] is None
    assert first.evidence['account_match'] and first.evidence['api_version']=='v26.0'
    first_json=first.model_dump(mode='json')
    old,replay=await reserve(stack);assert replay and old.sync_id==sync.sync_id and len(calls)==3
    views[0]=250;refresh,_=await reserve(stack,'refresh');await stack.processor.process(refresh.sync_id)
    reopened=AnalyticsRepository(stack.repository.session_factory)
    snapshots=await reopened.list_snapshots(sync.project_id)
    assert len(snapshots)==2 and snapshots[1].model_dump(mode='json')==first_json and snapshots[0].metrics.views==250
    async with stack.repository.session_factory() as session:
        usages=(await session.scalars(select(ProviderUsageORM).where(ProviderUsageORM.capability=='analytics'))).all()
        costs=(await session.scalars(select(CostRecordORM).where(CostRecordORM.provider_usage_id.in_([u.usage_id for u in usages])))).all()
    assert len(usages)==len(costs)==6 and all(u.status=='confirmed' for u in usages)
    assert all(c.actual_cost is None and c.estimated_cost is None for c in costs)
    assert 'EXPLICIT-META-READ-FIXTURE' not in json.dumps([s.model_dump(mode='json') for s in snapshots])
    runtime.clients.clear()
    assert (await reopened.list_snapshots(sync.project_id))[1].model_dump(mode='json')==first_json


@pytest.mark.asyncio
@pytest.mark.parametrize('mode_value,maximum_calls',[('foreign-account',1),('foreign-media',2)])
async def test_meta_foreign_account_or_media_stops_before_metrics(meta_stack,mode_value,maximum_calls):
    stack,_,_,calls,mode,_,_=meta_stack;mode[0]=mode_value
    sync,_=await reserve(stack);done=await stack.processor.process(sync.sync_id)
    assert done.status=='failed' and len(calls)==maximum_calls
    assert await stack.repository.list_snapshots(sync.project_id)==[]


@pytest.mark.asyncio
async def test_meta_account_configuration_change_and_default_gate_stop_before_any_read(meta_stack):
    stack,runtime,current,calls,_,_,_=meta_stack
    sync,_=await reserve(stack);current[0]=current[0].model_copy(update={'profile_version':2})
    done=await stack.processor.process(sync.sync_id)
    assert done.status=='failed' and calls==[]
    current[0]=current[0].model_copy(update={'profile_version':1})
    runtime.settings.analytics_external_execution_enabled=False
    assert not runtime.provider(sync.platform,sync.workspace_id).state(sync.platform).supports_sync
    pending,_=await reserve(stack,'disabled');disabled=await stack.processor.process(pending.sync_id)
    assert disabled.status=='not_configured' and calls==[]


@pytest.mark.asyncio
async def test_meta_lifetime_profiles_refuse_calendar_ranges_before_queue_dispatch(meta_stack):
    stack,_,_,calls,_,_,_=meta_stack
    with pytest.raises(AnalyticsBoundaryError,match='date-range report'):
        await reserve(stack,query={'start_date':'2026-10-01','end_date':'2026-10-06'})
    assert calls==[]


@pytest.mark.asyncio
async def test_meta_rate_limit_schedules_backoff_without_fabricating_a_snapshot(meta_stack):
    stack,_,_,calls,mode,_,_=meta_stack;mode[0]='rate-limit'
    sync,_=await reserve(stack);done=await stack.processor.process(sync.sync_id)
    assert done.status=='retry_scheduled' and done.next_retry_at is not None and len(calls)==1
    assert await stack.repository.list_snapshots(sync.project_id)==[]


@pytest.mark.asyncio
async def test_changed_meta_page_profile_during_read_cannot_reach_metrics(meta_stack):
    stack,_,_,calls,mode,_,_=meta_stack;mode[0]='profile-change'
    sync,_=await reserve(stack);done=await stack.processor.process(sync.sync_id)
    assert done.status=='failed' and len(calls)==1
    assert await stack.repository.list_snapshots(sync.project_id)==[]
