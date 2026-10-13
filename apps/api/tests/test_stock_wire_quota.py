"""SQL-owned wire scheduling across adapters/process state; mocked HTTP only."""
import asyncio
from dataclasses import replace
import json
import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.stock_media_providers import PexelsStockMediaProvider, StockProviderFailure, stock_request_scope
from app.stock_wire_context import stock_wire_operation
from app.stock_wire_quota import (StockWireDeferred, StockWireQuotaGuard, StockWireQuotaRepository, digest)
from app.stock_wire_quota_db import StockWireControlORM, StockWireEventORM, StockWireScopeORM

NOW = 1_800_000_000.0
PNG = b'\x89PNG\r\n\x1a\nexplicit wire fixture; not decoded acceptance'


def photo():
    return {'id':11,'width':640,'height':360,'url':'https://www.pexels.com/photo/explicit-fixture-11/',
        'photographer':'EXPLICIT MOCK CREATOR','alt':'EXPLICIT MOCK QUOTA FIXTURE',
        'src':{'original':'https://images.pexels.com/photos/11/explicit-fixture.png'}}


async def stack(tmp_path, clock):
    engine = create_async_engine('sqlite+aiosqlite:///'+str(tmp_path/'stock.sqlite3'))
    async with engine.begin() as connection:
        for model in (StockWireControlORM, StockWireScopeORM, StockWireEventORM):
            await connection.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = StockWireQuotaRepository(factory)
    await repository.ensure_state()
    return engine, factory, repository, StockWireQuotaGuard(repository, clock=lambda:clock[0])


def operation(source='explicit-plan-fixture', project='prj_explicit_fixture', budget='a'*64, workspace='wsp_explicit_fixture'):
    return stock_wire_operation(workspace_id=workspace, project_id=project, source_ref=source, budget_sha256=budget)


def adapter(tmp_path, guard, handler, **overrides):
    return PexelsStockMediaProvider(api_key='explicit-noncredential', enabled=True, cache_root=tmp_path/'cache',
        wire_guard=guard, require_wire_guard=True, transport=httpx.MockTransport(handler), **overrides)


@pytest.mark.asyncio
async def test_429_persists_across_fresh_repository_adapter_and_job_without_wire_or_retry_budget(tmp_path):
    clock=[NOW];engine,factory,repository,guard=await stack(tmp_path,clock);calls=[]
    def response(request):calls.append(request);return httpx.Response(429,headers={'Retry-After':'600'})
    first=adapter(tmp_path,guard,response)
    try:
        with stock_request_scope('wsp_explicit_fixture'), operation('plan-first') as context:
            with pytest.raises(StockProviderFailure):await first.search_images('PRIVATE QUERY MUST NOT PERSIST',orientation='any',limit=1)
            assert context.wire_attempts==1
            scope=guard.scope(first,'wsp_explicit_fixture','api')
        restarted=adapter(tmp_path,StockWireQuotaGuard(StockWireQuotaRepository(factory),clock=lambda:clock[0]),response)
        with stock_request_scope('wsp_explicit_fixture'), operation('different-job',budget='b'*64) as context:
            with pytest.raises(StockWireDeferred) as waiting:await restarted.search_images('second',orientation='any',limit=1)
            assert waiting.value.next_at==NOW+600 and context.wire_attempts==0
        assert len(calls)==1
        history=await repository.history(scope)
        assert any(row['action']=='cooldown_observed' for row in history)
        assert any(row['action']=='deferred_before_wire' and row['evidence']['wire_attempts']==0 for row in history)
        assert 'explicit-noncredential' not in json.dumps(history)
        assert 'PRIVATE QUERY MUST NOT PERSIST' not in json.dumps(history)
        await restarted.aclose()
    finally:await first.aclose();await engine.dispose()


@pytest.mark.asyncio
async def test_success_remaining_zero_preserves_month_reset_but_cached_search_bypasses_wire_lease(tmp_path):
    clock=[NOW];engine,factory,repository,guard=await stack(tmp_path,clock);calls=[];reset=int(NOW)+31*86400
    def response(request):calls.append(request);return httpx.Response(200,json={'photos':[photo()]},
        headers={'X-RateLimit-Remaining':'0','X-RateLimit-Reset':str(reset)})
    first=adapter(tmp_path,guard,response)
    try:
        with stock_request_scope('wsp_explicit_fixture'),operation() as context:
            seeded=await first.search_images('cached',orientation='any',limit=1);assert context.wire_attempts==1
        restarted=adapter(tmp_path,StockWireQuotaGuard(StockWireQuotaRepository(factory),clock=lambda:clock[0]),response)
        with stock_request_scope('wsp_explicit_fixture'),operation('new-cached-job') as context:
            hit=await restarted.search_images('cached',orientation='any',limit=1)
            assert context.wire_attempts==0 and hit[0].candidate_id==seeded[0].candidate_id and hit[0].provenance['fixture']
            with pytest.raises(StockWireDeferred) as pending:await restarted.search_images('notcached',orientation='any',limit=1)
            assert pending.value.next_at==reset
        assert len(calls)==1
        clock[0]=reset+1
        with stock_request_scope('wsp_explicit_fixture'),operation('due-job'):
            await restarted.search_images('notcached',orientation='any',limit=1)
        assert len(calls)==2
        await restarted.aclose()
    finally:await first.aclose();await engine.dispose()


@pytest.mark.asyncio
async def test_api_exhaustion_allows_prepared_cached_metadata_and_cdn_without_repeating_api(tmp_path):
    clock=[NOW];engine,factory,repository,guard=await stack(tmp_path,clock);calls=[]
    def response(request):
        calls.append(request.url.host)
        if request.url.host=='api.pexels.com':return httpx.Response(200,json=photo(),
            headers={'X-RateLimit-Remaining':'0','X-RateLimit-Reset':str(int(NOW)+600)})
        return httpx.Response(200,content=PNG,headers={'Content-Type':'image/png'})
    current=adapter(tmp_path,guard,response)
    try:
        with stock_request_scope('wsp_explicit_fixture'),operation('metadata-seed'):
            await current.get_asset('image:11')
        with stock_request_scope('wsp_explicit_fixture'),operation('download-job') as context:
            metadata=await current.cached_metadata('image:11')
            assert metadata is not None
            async with guard.prepare_download(current,'wsp_explicit_fixture',metadata):
                candidate=await current.get_asset('image:11')
                result=await current.download_asset(candidate)
            assert context.wire_attempts==1 and result.payload==PNG and result.generation_provenance['fixture']
            assert context.permits=={} and context.cached_inputs=={}
        assert calls==['api.pexels.com','images.pexels.com']
    finally:await current.aclose();await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_sql_instances_claim_only_one_wire_lease_and_expired_owner_is_fenced(tmp_path):
    clock=[NOW];engine,factory,repository,guard=await stack(tmp_path,clock)
    scope={'schema_version':'sql-stock-wire-scope.v1','workspace_id':'wsp_fixture','root_sha256':'a'*64,
        'provider':'pexels','mode':'fixture','configuration_sha256':'b'*64,'request_class':'api'}
    bound={'workspace_id':'wsp_fixture','project_id':'prj_fixture','source_ref':'explicit-job','budget_sha256':'c'*64}
    other=StockWireQuotaRepository(factory)
    try:
        results=await asyncio.gather(repository.admit(scope,bound,NOW),other.admit(scope,bound,NOW),return_exceptions=True)
        permits=[value for value in results if not isinstance(value,Exception)]
        assert len(permits)==1 and sum(isinstance(value,StockWireDeferred) for value in results)==1
        old=permits[0];new=await other.admit(scope,bound,NOW+181)
        assert old.lease_id!=new.lease_id
        assert await repository.release(old,stamp=NOW+182,status=429,headers={'Retry-After':'600'},wire_attempted=True) is False
        with pytest.raises(StockWireDeferred):await repository.check_permit(old,NOW+182)
        assert await other.release(new,stamp=NOW+182,wire_attempted=False)
        history=await repository.history(scope)
        assert any(value['action']=='expired_lease_recovered' and value['evidence']['paid_replay_authorized'] is False for value in history)
        assert not any(value['action']=='cooldown_observed' for value in history)
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_workspace_config_root_and_api_cdn_boundaries_never_reuse_blocked_state(tmp_path):
    clock=[NOW];engine,factory,repository,guard=await stack(tmp_path,clock)
    scope={'schema_version':'sql-stock-wire-scope.v1','workspace_id':'wsp_fixture','root_sha256':'a'*64,
        'provider':'pexels','mode':'fixture','configuration_sha256':'b'*64,'request_class':'api'}
    bound={'workspace_id':'wsp_fixture','project_id':'prj_fixture','source_ref':'explicit-job','budget_sha256':'c'*64}
    try:
        first=await repository.admit(scope,bound,NOW)
        await repository.release(first,stamp=NOW,status=429,headers={'Retry-After':'600'},wire_attempted=True)
        for key,value in [('workspace_id','wsp_other'),('root_sha256','d'*64),('configuration_sha256','e'*64),
                ('mode','official'),('request_class','cdn')]:
            changed={**scope,key:value};operation={**bound,'workspace_id':changed['workspace_id']}
            permit=await repository.admit(changed,operation,NOW+1)
            await repository.release(permit,stamp=NOW+1,wire_attempted=False)
        with pytest.raises(StockWireDeferred):await repository.admit(scope,bound,NOW+1)
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_rehashed_but_invalid_quota_evidence_and_foreign_context_refuse_before_wire(tmp_path):
    clock=[NOW];engine,factory,repository,guard=await stack(tmp_path,clock);calls=[]
    def response(request):calls.append(request);return httpx.Response(429,headers={'Retry-After':'60'})
    current=adapter(tmp_path,guard,response)
    try:
        with stock_request_scope('wsp_explicit_fixture'),operation() as context:
            with pytest.raises(StockProviderFailure):await current.search_images('seed',orientation='any',limit=1)
            scope=guard.scope(current,'wsp_explicit_fixture','api')
        async with factory() as session:
            row=await session.get(StockWireScopeORM,digest(scope));evidence=dict(row.evidence_json)
            evidence['backoff']={**evidence['backoff'],'basis':'successful_api_quota_exhaustion','remaining':False}
            row.evidence_json=evidence;row.evidence_sha256=digest(evidence);await session.commit()
        with stock_request_scope('wsp_explicit_fixture'),operation('corruption-test'):
            with pytest.raises(ValueError,match='STOCK_WIRE_STATE_INVALID'):
                await current.search_images('new',orientation='any',limit=1)
        with stock_request_scope('different-workspace'),operation():
            with pytest.raises(ValueError,match='STOCK_WIRE_OPERATION_SCOPE_REQUIRED'):
                await current.search_images('foreign',orientation='any',limit=1)
        assert len(calls)==1
    finally:await current.aclose();await engine.dispose()
