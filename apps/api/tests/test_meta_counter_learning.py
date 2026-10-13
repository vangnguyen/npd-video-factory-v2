"""SQL/API Meta counter policy parity over explicit synthetic fixture histories."""
import hashlib,json
from dataclasses import replace
import httpx
import pytest
from sqlalchemy import select
from app import analytics_meta as meta
from app.analytics_cohort import channel_context
from app.analytics_channel_policy import META_COUNTER_VERSION,WinnerChannelPolicy,meta_counter_scope,assess_meta_counter_channel,values
from app.analytics_db import WinnerAssessmentORM,AnalyticsMetricSnapshotORM
from app.analytics_models import AnalyticsSyncRequest
from app.analytics_providers import AnalyticsCollection
from app.db import utc_now
from app.learning_models import LearningCreate
from app.learning_service import ChannelLearningService
from app.production_db import ProductionRenderJobORM
from app.production_features import RenderFeatureContext,digest as feature_digest
from app.publishing_db import PublicationORM
from app.publishing_credentials import target_digest
from app.publishing_wire import OfficialResponse
from auth_test_support import TEST_HUMAN_HEADERS
from test_channel_learning import learning_app
from test_analytics_meta_runtime import meta_stack,reserve
from test_analytics_meta import ig_table,fb_table,REMOTE


def synthetic_counts(platform,target,remote,positive):
    """Mint definition/availability from the same explicit mock counts as metrics."""
    response=ig_table({'views':1000,'likes':40 if positive else 4,'comments':0,
        'shares':20 if positive else 2,'saved':30 if positive else 3}) if platform=='instagram_reels' else fb_table(
        views=1000,likes={'data':[],'summary':{'total_count':40 if positive else 4}})
    if platform=='instagram_reels':
        for row in response['data']:row['id']=row['id'].replace(REMOTE,remote)
    else:response.update(id=remote,**{'from':{'id':target.target_account_id}})
    metrics,definition=meta.metrics(OfficialResponse(200,{},json.dumps(response).encode()),target,remote,api_version='v26.0')
    return metrics,definition,response


@pytest.mark.asyncio
async def test_processor_selects_distinct_counter_algorithm_and_keeps_unsupported_fields(meta_stack):
    stack,runtime,targets,calls,mode,views,platform=meta_stack
    sync,_=await reserve(stack,'counter-version');done=await stack.processor.process(sync.sync_id)
    assert done.status=='succeeded'
    async with stack.repository.session_factory() as session:
        row=await session.scalar(select(WinnerAssessmentORM).where(WinnerAssessmentORM.snapshot_id==done.snapshot_id))
        assert row.algorithm_version==META_COUNTER_VERSION and row.state=='insufficient_data' and row.score is None
        assert all(f['evidence']['comparison']=='matching_meta_counter_scope' for f in row.factors_json)
    assert len(calls)==3 and all(c['method']=='GET' for c in calls)


async def seed_counter_history(meta_stack):
    stack,runtime,targets,calls,mode,views,platform=meta_stack;target=targets[0];factory=stack.repository.session_factory
    first,_=await reserve(stack,'definition-seed');await stack.processor.process(first.sync_id)
    original_snapshot=(await stack.repository.list_snapshots(first.project_id))[0]
    weights={k:0.0 for k in WinnerChannelPolicy().weights};weights.update(engagement=.4,shares=.3,saves=.3)
    policy=WinnerChannelPolicy(minimum_peer_posts=3,minimum_weight_coverage=.5,weights=weights)
    last=None
    for index in range(6):
        parent_id='pub_explicit_meta_counter_seed_'+str(index)
        async with factory() as session:
            original=await session.get(PublicationORM,stack.publication.publication_id)
            render=await session.get(ProductionRenderJobORM,original.final_render_id)
            context=RenderFeatureContext.model_validate(render.manifest_json['feature_context']).model_copy(update={
                'hook_type':'explicit-question-hook' if index<3 else 'explicit-list-hook','niche':'technology'})
            fields={c.name:getattr(render,c.name) for c in ProductionRenderJobORM.__table__.columns}
            render_id='ren_explicit_meta_counter_seed_'+str(index)
            fields.update(render_id=render_id,version=2000+index,manifest_json={**render.manifest_json,
                'feature_context':context.model_dump(mode='json'),'feature_context_sha256':feature_digest(context)})
            session.add(ProductionRenderJobORM(**fields))
            fields={c.name:getattr(original,c.name) for c in PublicationORM.__table__.columns}
            fields.update(publication_id=parent_id,final_render_id=render_id,idempotency_key_hash=hashlib.sha256(parent_id.encode()).hexdigest(),
                receipt_json={**original.receipt_json,'remote_post_id':str(17890000000001000+index)})
            session.add(PublicationORM(**fields));await session.commit()
        sync,_=await stack.service.create_sync(project_id=first.project_id,payload=AnalyticsSyncRequest(publication_id=parent_id,
            provider_mode='official',query=None),idempotency_key='explicit-meta-counter-seed-'+str(index))
        claimed=await stack.repository.claim(sync.sync_id);parent=await stack.service.publishing_repository.get(sync.project_id,parent_id)
        features=await stack.processor._capture_features(claimed,parent);positive=index<3
        metrics,definition,_=synthetic_counts(platform,target,parent.receipt.remote_post_id,positive)
        baseline,_,_=synthetic_counts(platform,target,parent.receipt.remote_post_id,False)
        peers=[{'snapshot_id':'ams_explicit_counter_baseline_'+str(i),'values':values(baseline,features.duration_seconds)} for i in range(3)]
        assessment=assess_meta_counter_channel(metrics,duration=features.duration_seconds,production_cost=None,
            context={'peers':peers,'scope_verified':True,'counter_growth':None,'candidate_rows_truncated':False},policy=policy)
        evidence={**original_snapshot.evidence,**definition,'account_match':True,'target_binding_sha256':target_digest(target),'query':None,
            'explicit_synthetic_metric_seed':True,'actual_provider_calls':0}
        last=await stack.repository.complete(sync.sync_id,collection=AnalyticsCollection(provider_key=original_snapshot.provider_key,
            source='explicit-meta-counter-learning-fixture',source_kind='official_api',collected_at=utc_now(),
            metrics=metrics,mock=True,external_call=False,evidence=evidence),features=features,assessment=assessment,insights=[],expected_attempt=claimed.attempt_count)
    return first,parent_id,definition,policy


@pytest.mark.asyncio
async def test_meta_learning_freezes_metric_definition_and_never_mixes_legacy_assessments(meta_stack):
    stack,runtime,targets,calls,mode,views,platform=meta_stack;factory=stack.repository.session_factory
    first,parent_id,definition,policy=await seed_counter_history(meta_stack)
    service=ChannelLearningService(factory)
    payload=LearningCreate(publication_id=parent_id,provider_mode='official')
    learned,hit=await service.create(first.project_id,payload,actor='explicit-meta-counter-actor',key='explicit-meta-counter-learning-key')
    assert not hit and learned.scope['winner_algorithm_version']==META_COUNTER_VERSION
    assert learned.scope['api_version']=='v26.0' and learned.scope['metric_definition_sha256']==meta_counter_scope(platform,definition)['metric_definition_sha256']
    assert len(learned.observations)==(6 if platform=='instagram_reels' else 0)
    assert all(o.features['publishing_window'] is None for o in learned.observations)
    assert len(calls)==3
    assert (await service.get(learned.workspace_id,learned.learning_snapshot_id)).model_dump()==learned.model_dump()
    saved=learned.model_dump()
    replay,hit=await service.create(first.project_id,payload,actor='different-fixture-actor',key='explicit-meta-counter-learning-key')
    assert hit and replay.model_dump()==saved
    async with factory() as session:
        rows=(await session.scalars(select(AnalyticsMetricSnapshotORM).where(
            AnalyticsMetricSnapshotORM.publication_id.like('pub_explicit_meta_counter_seed_%')).order_by(AnalyticsMetricSnapshotORM.publication_id))).all()
        rows[0].evidence_json={**rows[0].evidence_json,'api_version':'v25.0'}
        rows[1].evidence_json={**rows[1].evidence_json,'normalized_units':{'views':'incompatible-fixture-unit'}}
        assessment=await session.scalar(select(WinnerAssessmentORM).where(WinnerAssessmentORM.snapshot_id==rows[2].snapshot_id))
        assessment.algorithm_version='winner-channel-assessment-v1'
        await session.commit()
    revised,hit=await service.create(first.project_id,payload,actor='explicit-meta-counter-actor',key='explicit-meta-counter-revised-key')
    assert not hit and len(revised.observations)==(3 if platform=='instagram_reels' else 0)
    # The original IG response returns only views/likes, so it is also excluded
    # from the later complete interaction-definition study.
    assert revised.excluded_rows['incompatible_scope']==(4 if platform=='instagram_reels' else 3)
    assert (await service.get(learned.workspace_id,learned.learning_snapshot_id)).model_dump()==saved
    assert len(calls)==3


@pytest.mark.asyncio
async def test_meta_actual_sql_cohort_and_processor_exclude_definition_changes(meta_stack):
    stack,runtime,targets,calls,mode,views,platform=meta_stack;factory=stack.repository.session_factory
    first,_,definition,policy=await seed_counter_history(meta_stack);stack.processor.winner_policy=policy
    async with factory() as session:
        original=await session.get(PublicationORM,stack.publication.publication_id)
        render=await session.get(ProductionRenderJobORM,original.final_render_id)
        context=RenderFeatureContext.model_validate(render.manifest_json['feature_context']).model_copy(update={'niche':'technology'})
        render.manifest_json={**render.manifest_json,'feature_context':context.model_dump(mode='json'),'feature_context_sha256':feature_digest(context)}
        await session.commit()
    metrics,definition,response=synthetic_counts(platform,targets[0],REMOTE,True)
    collection=AnalyticsCollection(provider_key=stack.providers.OFFICIAL_KEYS[platform],source='explicit-counter-cohort-fixture',
        source_kind='official_api',collected_at=utc_now(),metrics=metrics,mock=True,external_call=False,
        evidence={**definition,'account_match':True,'target_binding_sha256':target_digest(targets[0]),'query':None})
    pending,_=await reserve(stack,'actual-counter-cohort')
    parent=await stack.service.publishing_repository.get(first.project_id,stack.publication.publication_id)
    features=await stack.processor._capture_features(pending,parent)
    async def cohort():
        return await channel_context(factory,sync=pending,publication=parent,collection=collection,features=features,policy=policy)
    baseline=await cohort()
    assert baseline['scope_verified'] and len(baseline['peers'])==6 and baseline['counter_growth'] is None
    assert all(peer.get('counter_growth') is None and peer['values']['view_velocity'] is None for peer in baseline['peers'])
    async with factory() as session:
        rows=(await session.scalars(select(AnalyticsMetricSnapshotORM).where(
            AnalyticsMetricSnapshotORM.publication_id.like('pub_explicit_meta_counter_seed_%')).order_by(AnalyticsMetricSnapshotORM.publication_id))).all()
        rows[0].evidence_json={**rows[0].evidence_json,'api_version':'v25.0'}
        rows[1].evidence_json={**rows[1].evidence_json,'returned_metrics':[]}
        rows[2].evidence_json={**rows[2].evidence_json,'provider_metric_semantics_real_verified':True}
        await session.commit()
    reduced=await cohort();assert len(reduced['peers'])==3
    old=runtime.clients[platform].wire.transport
    def receive(request):
        if 'metric' in request.url.params or dict(request.url.params).get('fields')==meta.FB_FIELDS:
            calls.append({'method':request.method,'path':request.url.path,'query':str(request.url.query)})
            return httpx.Response(200,json=response)
        return old.handle_request(request)
    runtime.clients[platform].wire.transport=httpx.MockTransport(receive)
    done=await stack.processor.process(pending.sync_id);assert done.status=='succeeded'
    async with factory() as session:
        assessment=await session.scalar(select(WinnerAssessmentORM).where(WinnerAssessmentORM.snapshot_id==done.snapshot_id))
        assert assessment.algorithm_version==META_COUNTER_VERSION
        assert assessment.state==('winner_candidate' if platform=='instagram_reels' else 'insufficient_data')
        assert assessment.score==(100 if platform=='instagram_reels' else None)
        assert all(f['evidence']['peer_count']<=3 for f in assessment.factors_json)
    assert len(calls)==6 and all(c['method']=='GET' for c in calls)
    invalid=features.model_copy(update={'evidence':{**features.evidence,'feature_context_sha256':'0'*64}})
    rejected=await channel_context(factory,sync=pending,publication=parent,collection=collection,features=invalid,policy=policy)
    assert rejected['scope_verified'] is False and not rejected['peers']


@pytest.mark.parametrize('field,bad',[
    ('metric_mapping',None),('normalized_units',{'views':float('nan')}),
    ('returned_metrics',['views','views']),('unavailable_metrics',{'views':True}),('api_version','PRIVATE_BAD_VALUE')])
def test_invalid_meta_definition_returns_unverified_without_serialization_error(field,bad):
    definition={'metric_scope':'lifetime_media_insights','api_version':'v26.0','metric_mapping':{'views':'views'},
        'normalized_units':{'views':'count'},'returned_metrics':['views'],'unavailable_metrics':[],
        'provider_metric_semantics_real_verified':False}
    assert meta_counter_scope('instagram_reels',definition)
    definition[field]=bad;assert meta_counter_scope('instagram_reels',definition) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('restriction',['invalid_definition','genuine_semantics_unverified'])
async def test_meta_processor_fails_closed_and_preserves_distinct_algorithm(meta_stack,monkeypatch,restriction):
    stack,runtime,targets,calls,mode,views,platform=meta_stack
    get=stack.providers.get;provider=get(platform=platform,mode='official',workspace=stack.publication.workspace_id)
    collect=provider.collect
    async def restricted(context):
        value=await collect(context)
        # Explicit synthetic boundary injection; the HTTP transport remains mock.
        if restriction=='invalid_definition':return replace(value,evidence={**value.evidence,'api_version':'invalid'})
        return replace(value,mock=False)
    monkeypatch.setattr(provider,'collect',restricted)
    monkeypatch.setattr(stack.providers,'get',lambda **kwargs:provider)
    sync,_=await reserve(stack,'fail-closed-'+restriction);done=await stack.processor.process(sync.sync_id)
    assert done.status=='succeeded' and len(calls)==3
    async with stack.repository.session_factory() as session:
        assessment=await session.scalar(select(WinnerAssessmentORM).where(WinnerAssessmentORM.snapshot_id==done.snapshot_id))
        assert assessment.algorithm_version==META_COUNTER_VERSION and assessment.state=='insufficient_data' and assessment.score is None
        if restriction=='genuine_semantics_unverified':assert any('not real-provider verified' in value for value in assessment.evidence_json)


@pytest.mark.asyncio
async def test_meta_learning_asgi_owner_history_and_role_guard(meta_stack):
    stack,runtime,targets,calls,mode,views,platform=meta_stack
    first,parent_id,definition,_=await seed_counter_history(meta_stack)
    base=f'/api/v1/projects/{first.project_id}/analytics/learning-snapshots'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=learning_app(stack,'owner')),
        base_url='http://explicit-meta-fixture',headers=TEST_HUMAN_HEADERS) as client:
        response=await client.post(base,json={'publication_id':parent_id},headers={'Idempotency-Key':'meta-learning-asgi-fixture'})
        assert response.status_code==201 and response.headers['Cache-Control']=='no-store'
        value=response.json();assert value['scope']['winner_algorithm_version']==META_COUNTER_VERSION
        assert len(value['observations'])==(6 if platform=='instagram_reels' else 0)
        identity=value['learning_snapshot_id']
        endpoint=f'/api/v1/workspaces/{first.workspace_id}/learning-snapshots/{identity}'
        assert (await client.get(endpoint)).json()==value
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=learning_app(stack,'viewer')),
        base_url='http://explicit-meta-fixture',headers=TEST_HUMAN_HEADERS) as client:
        denied=await client.post(base,json={'publication_id':parent_id},headers={'Idempotency-Key':'meta-learning-asgi-denied'})
        assert denied.status_code==403
        assert (await client.get(endpoint)).json()==value
    assert len(calls)==3
