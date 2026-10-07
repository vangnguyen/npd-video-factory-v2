"""Official endpoint wire contracts only; HTTP/media payloads are explicit mocks."""
import hashlib
import json
import logging
import pytest
import httpx
from app.config import Settings
from app.media_intelligence_logic import rank_stock_candidates
from app.media_intelligence_providers import MediaProviderNotConfigured
from app.media_intelligence_service import create_media_provider_bundle,_asset_kind
from app.stock_media_providers import PexelsStockMediaProvider,PixabayStockMediaProvider,StockProviderFailure,stock_request_scope,SCOPE

PNG=b'\x89PNG\r\n\x1a\n'+b'explicit mocked media; not decoded acceptance'
MP4=b'\x00\x00\x00\x18ftypisom'+b'explicit mocked video; not playable acceptance'


def photo(identifier=11):
    return {'id':identifier,'width':640,'height':360,'url':f'https://www.pexels.com/photo/fixture-{identifier}/',
        'photographer':'Mock creator','alt':'Educational technology fixture','src':{'original':f'https://images.pexels.com/photos/{identifier}/mock.png'}}


def video(identifier=21):
    return {'id':identifier,'width':1920,'height':1080,'duration':3.,'url':f'https://www.pexels.com/video/mock-{identifier}/',
        'user':{'name':'Mock filmmaker'},'video_files':[{'width':1920,'height':1080,'file_type':'video/mp4',
            'link':f'https://videos.pexels.com/video-files/{identifier}/mock.mp4'}]}


def pix_image():
    return {'id':31,'user':'Mock photographer','pageURL':'https://pixabay.com/photos/mock-31/',
        'webformatURL':'https://cdn.pixabay.com/photo/mock_640.png','webformatWidth':640,'webformatHeight':360,
        'imageWidth':4096,'imageHeight':2304,'tags':'education, technology'}


def pix_video():
    return {'id':41,'user':'Mock filmmaker','pageURL':'https://pixabay.com/videos/mock-41/','duration':3.,
        'videos':{'medium':{'url':'https://cdn.pixabay.com/video/mock.mp4','width':1080,'height':1920}}}


@pytest.mark.asyncio
@pytest.mark.parametrize('provider',[PexelsStockMediaProvider,PixabayStockMediaProvider])
async def test_disabled_and_missing_scope_never_dispatch(provider,tmp_path):
    def forbidden(request):raise AssertionError('External dispatch forbidden')
    adapter=provider(api_key='explicit-mock-secret',cache_root=tmp_path,transport=httpx.MockTransport(forbidden))
    with pytest.raises(MediaProviderNotConfigured):await adapter.search_images('technology',orientation='portrait',limit=3)
    enabled=provider(api_key='explicit-mock-secret',enabled=True,cache_root=tmp_path,transport=httpx.MockTransport(forbidden))
    with pytest.raises(ValueError,match='WORKSPACE_SCOPE'):await enabled.search_images('technology',orientation='portrait',limit=3)
    assert not list(tmp_path.rglob('*.json'));await enabled.aclose()


@pytest.mark.asyncio
async def test_pexels_official_new_paths_scoped_cache_license_and_bounded_download(tmp_path,caplog):
    calls=[];secret='explicit-pexels-contract-secret'
    def handler(request):
        calls.append(request)
        if request.url.host=='api.pexels.com':assert request.headers['Authorization']==secret
        else:assert 'Authorization' not in request.headers
        if request.url.path=='/v1/search':return httpx.Response(200,json={'photos':[photo(),photo(12)]})
        if request.url.path=='/v1/videos/search':return httpx.Response(200,json={'videos':[video()]})
        if request.url.path=='/v1/photos/11':return httpx.Response(200,json=photo())
        if request.url.path=='/v1/videos/videos/21':return httpx.Response(200,json=video())
        if request.url.host=='images.pexels.com':return httpx.Response(200,content=PNG,headers={'Content-Type':'image/png'})
        if request.url.host=='videos.pexels.com':return httpx.Response(200,content=MP4,headers={'Content-Type':'video/mp4'})
        raise AssertionError('Unexpected official mock endpoint')
    adapter=PexelsStockMediaProvider(api_key=secret,enabled=True,cache_root=tmp_path,transport=httpx.MockTransport(handler))
    caplog.set_level(logging.INFO,logger='httpx')
    try:
        with stock_request_scope('workspace-A'):
            found=await adapter.search_images('AI education',orientation='portrait',limit=2)
            assert len(found)==2 and found[0].provider_asset_id=='image:11'
            repeat=await adapter.search_images('AI education',orientation='portrait',limit=2)
            assert repeat[0].candidate_id==found[0].candidate_id and len(calls)==1
            ranked=rank_stock_candidates(found,query='AI education',vision_description='')
            assert [c.provider_asset_id for c in ranked]==['image:11','image:12']
            assert all(c.semantic_score is None and c.vision_rerank_score is None for c in ranked)
            malicious=found[0].model_copy(update={'provenance':{'download_url':'https://private.invalid/steal'},'license':'forged'})
            image=await adapter.download_asset(malicious)
            assert image.payload==PNG and image.license=='Pexels License'
            assert not image.production_eligible and not image.real_provider_tested
            assert image.generation_provenance['complete_decode_required']
            assert image.generation_provenance['payload_sha256']==hashlib.sha256(PNG).hexdigest()
            movies=await adapter.search_videos('technology',orientation='landscape',limit=1)
            movie=await adapter.download_asset(movies[0]);assert movie.payload==MP4 and movie.duration_seconds==3.
        count=len(calls)
        with stock_request_scope('workspace-B'):await adapter.search_images('AI education',orientation='portrait',limit=2)
        assert len(calls)==count+1
        assert secret not in caplog.text
        assert all(secret not in p.read_text() for p in tmp_path.rglob('*.json'))
    finally:await adapter.aclose()


@pytest.mark.asyncio
async def test_pixabay_secret_is_only_at_wire_and_videos_filter_orientation_locally(tmp_path,caplog):
    calls=[];secret='explicit-pixabay-contract-secret'
    def handler(request):
        calls.append(request)
        if request.url.host=='pixabay.com':
            assert request.url.params['key']==secret
            if request.url.path=='/api/':return httpx.Response(200,json={'hits':[pix_image()]})
            assert request.url.path=='/api/videos/' and 'orientation' not in request.url.params
            return httpx.Response(200,json={'hits':[pix_video()]})
        assert 'key' not in request.url.params and 'Authorization' not in request.headers
        return httpx.Response(200,content=PNG if request.url.path.endswith('.png') else MP4,
            headers={'Content-Type':'image/png' if request.url.path.endswith('.png') else 'video/mp4'})
    adapter=PixabayStockMediaProvider(api_key=secret,enabled=True,cache_root=tmp_path,cache_scope='workspace-A',transport=httpx.MockTransport(handler))
    caplog.set_level(logging.INFO,logger='httpx')
    try:
        photos=await adapter.search_images('education',orientation='landscape',limit=1)
        assert calls[0].url.params['per_page']=='3' and calls[0].url.params['orientation']=='horizontal'
        assert photos[0].width==640 and photos[0].height==360 # Selected URL, not original 4096px dimensions.
        assert photos[0].license=='Pixabay Content License' and photos[0].semantic_score is None
        assert (await adapter.download_asset(photos[0])).payload==PNG
        movies=await adapter.search_videos('education',orientation='portrait',limit=1);assert len(movies)==1
        assert (await adapter.download_asset(movies[0])).payload==MP4
        assert secret not in caplog.text
        assert all(secret not in p.read_text() for p in tmp_path.rglob('*.json'))
    finally:await adapter.aclose()


@pytest.mark.asyncio
async def test_cache_survives_restart_requires_24h_and_rejects_corrupt_binding(tmp_path,monkeypatch):
    calls=[]
    def handler(request):calls.append(request);return httpx.Response(200,json={'photos':[photo()]})
    kwargs=dict(api_key='explicit-mock-key',enabled=True,cache_root=tmp_path,cache_scope='workspace-A')
    first=PexelsStockMediaProvider(**kwargs,transport=httpx.MockTransport(handler))
    await first.search_images('technology',orientation='unknown',limit=1);await first.aclose()
    restarted=PexelsStockMediaProvider(**kwargs,transport=httpx.MockTransport(handler))
    try:
        await restarted.search_images('technology',orientation='unknown',limit=1);assert len(calls)==1
        file=next(tmp_path.rglob('*.json'));cached=json.loads(file.read_bytes())
        monkeypatch.setattr('app.stock_media_providers.time.time',lambda:cached['created_at']+86401)
        await restarted.search_images('technology',orientation='unknown',limit=1);assert len(calls)==2
        changed=json.loads(file.read_bytes());changed['response']['photos'][0]['src']['original']='https://evil.invalid/image.png'
        file.write_text(json.dumps(changed))
        with pytest.raises(StockProviderFailure,match='STOCK_CACHE_INVALID'):
            await restarted.search_images('technology',orientation='unknown',limit=1)
        assert len(calls)==2
    finally:await restarted.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('url',['http://images.pexels.com/a.png','https://127.0.0.1/a.png',
    'https://images.pexels.com.evil.invalid/a.png','https://user:secret@images.pexels.com/a.png',
    'https://images.pexels.com:8443/a.png','https://images.pexels.com/a.png?api_key=secret'])
async def test_unapproved_media_urls_never_download(tmp_path,url):
    calls=[];item=photo();item['src']['original']=url
    def handler(request):calls.append(request);return httpx.Response(200,json={'photos':[item]})
    adapter=PexelsStockMediaProvider(api_key='explicit-mock-key',enabled=True,cache_root=tmp_path,cache_scope='workspace-A',transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(StockProviderFailure,match='STOCK_URL_INVALID'):
            await adapter.search_images('technology',orientation='unknown',limit=1)
        assert len(calls)==1
    finally:await adapter.aclose()


@pytest.mark.asyncio
async def test_rate_limit_redirect_size_mime_and_id_binding_errors_are_safe_and_do_not_auto_retry(tmp_path):
    mode={'status':429};calls=[]
    def handler(request):
        calls.append(request)
        if mode['status']==200:return httpx.Response(200,json=photo(99))
        return httpx.Response(mode['status'],headers={'Retry-After':'30','Location':'http://127.0.0.1/private'},text='Do not persist provider error body')
    adapter=PexelsStockMediaProvider(api_key='explicit-mock-key',enabled=True,cache_root=tmp_path,cache_scope='workspace-A',transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(StockProviderFailure) as rate:await adapter.search_images('technology',orientation='unknown',limit=1)
        assert rate.value.code=='STOCK_RATE_LIMITED' and rate.value.retry_after_seconds==30 and rate.value.retryable
        assert len(calls)==1 and not list(tmp_path.rglob('*.json'))
        mode['status']=302
        with pytest.raises(StockProviderFailure,match='STOCK_HTTP_FAILED'):await adapter.get_asset('image:11')
        mode['status']=200
        with pytest.raises(StockProviderFailure,match='STOCK_ASSET_BINDING_MISMATCH'):await adapter.get_asset('image:11')
    finally:await adapter.aclose()


def test_factory_configuration_keeps_secrets_out_of_settings_exports_and_default_dispatch_off(tmp_path):
    defaults=Settings(_env_file=None)
    assert not create_media_provider_bundle(defaults).stock.configured
    for name in ['pexels','pixabay']:
        kwargs={'stock_media_provider':name,name+'_api_key':'explicit-secret-key','stock_cache_root':tmp_path}
        settings=Settings(_env_file=None,**kwargs)
        provider=create_media_provider_bundle(settings).stock;assert not provider.configured
        assert 'explicit-secret-key' not in repr(settings) and 'explicit-secret-key' not in settings.model_dump_json()
        with pytest.raises(ValueError,match='global provider safety gate') as denied:
            Settings(_env_file=None,media_external_execution_enabled=True,**kwargs)
        assert 'explicit-secret-key' not in str(denied.value)
        # Factory mechanics only: an explicitly unvalidated fixture never dispatches.
        enabled=settings.model_copy(update={'media_external_execution_enabled':True})
        assert create_media_provider_bundle(enabled).stock.configured


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,expected',[('mime','STOCK_MIME_MAGIC_MISMATCH'),('size','STOCK_RESPONSE_TOO_LARGE'),('timeout','STOCK_NETWORK_FAILED')])
async def test_download_failure_never_promotes_invalid_bytes_and_errors_do_not_expose_key(tmp_path,mode,expected):
    secret='explicit-unique-contract-secret'
    def handler(request):
        if request.url.host=='api.pexels.com':return httpx.Response(200,json=photo())
        if mode=='timeout':raise httpx.ReadTimeout('Sensitive wire URL '+secret,request=request)
        if mode=='size':return httpx.Response(200,content=PNG,headers={'Content-Type':'image/png','Content-Length':'99999'})
        return httpx.Response(200,content=b'<html>not an image</html>',headers={'Content-Type':'image/png'})
    adapter=PexelsStockMediaProvider(api_key=secret,enabled=True,cache_root=tmp_path,cache_scope='workspace-A',
        max_download_bytes=100,transport=httpx.MockTransport(handler))
    try:
        candidate=await adapter.get_asset('image:11')
        with pytest.raises(StockProviderFailure,match=expected) as failed:await adapter.download_asset(candidate)
        assert secret not in str(failed.value)
    finally:await adapter.aclose()


@pytest.mark.asyncio
async def test_official_mock_candidates_persist_in_media_plan_and_worker_materialization_uses_same_scope(tmp_path):
    from types import SimpleNamespace
    from test_media_intelligence import setup_media_stack,plan_request
    from app.media_intelligence_service import MediaProviderBundle
    from app.media_intelligence_providers import DeterministicImageGenerationProvider,DeterministicVideoGenerationProvider
    calls=[]
    def handler(request):
        calls.append(request)
        if request.url.host in {'images.pexels.com','videos.pexels.com'}:
            return httpx.Response(200,content=PNG if request.url.host=='images.pexels.com' else MP4,
                headers={'Content-Type':'image/png' if request.url.host=='images.pexels.com' else 'video/mp4'})
        if request.url.path=='/v1/search':return httpx.Response(200,json={'photos':[photo()]})
        if request.url.path=='/v1/videos/search':return httpx.Response(200,json={'videos':[video()]})
        if request.url.path=='/v1/photos/11':return httpx.Response(200,json=photo())
        if request.url.path=='/v1/videos/videos/21':return httpx.Response(200,json=video())
        raise AssertionError('Unexpected official contract URL')
    adapter=PexelsStockMediaProvider(api_key='explicit-mocked-planning-key',enabled=True,cache_root=tmp_path/'cache',transport=httpx.MockTransport(handler))
    env=await setup_media_stack(tmp_path/'stack',MediaProviderBundle(stock=adapter,
        image=DeterministicImageGenerationProvider(),video=DeterministicVideoGenerationProvider()))
    try:
        await env['platform'].seed_providers([{'provider_key':'pexels','display_name':'Explicit HTTP contract mock',
            'capability':'stock_media','adapter':'explicit-mock-http','routing_mode':'primary','status':'healthy',
            'enabled':True,'supports_dry_run':True,'metadata':{'fixture':True,'real_provider_tested':False}}])
        env['planner'].allow_external_execution=True # MockTransport only; no live scope is enabled.
        payload=plan_request(env).model_copy(update={'selection_policy':'priority','resolver_priority':['licensed_stock']})
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=payload)
        saved=await env['planner'].get(plan.media_plan_id)
        assert saved==plan and all(item.candidates for item in plan.items)
        assert all(candidate.semantic_score is None and candidate.vision_rerank_score is None for item in plan.items for candidate in item.candidates)
        item=plan.items[0];candidate=item.candidates[0]
        env['resolver'].allow_external_execution=True # This resolver uses only the injected MockTransport.
        materialized,source=await env['resolver']._materialize(SimpleNamespace(
            selected_candidate_id=candidate.candidate_id,capability='stock_media',external_call=True,paid=False),plan,item)
        assert source is None and materialized.source_type=='stock' and materialized.license=='Pexels License'
        assert materialized.payload in {PNG,MP4} and not materialized.production_eligible and not materialized.real_provider_tested
        assert materialized.generation_provenance['mock_transport_used']
        assert (await env['planner'].get(plan.media_plan_id))==saved
        assert SCOPE.get() is None
        from app.media_intelligence_models import MediaResolutionRequest
        job=await env['resolver'].enqueue(project_id=plan.project_id,media_plan_id=plan.media_plan_id,
            media_plan_item_id=item.media_plan_item_id,payload=MediaResolutionRequest(candidate_id=candidate.candidate_id))
        count=len(calls)
        blocked=await env['resolver'].process(job.resolution_job_id)
        assert blocked.status=='failed' and len(calls)==count # Global safety controller still refuses dispatch.
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_concurrent_workspace_contexts_do_not_reuse_or_mix_cached_responses(tmp_path):
    import asyncio
    calls=[]
    async def handler(request):
        scope=SCOPE.get();calls.append(scope);await asyncio.sleep(0)
        value=photo();value['photographer']=scope
        return httpx.Response(200,json={'photos':[value]})
    adapter=PexelsStockMediaProvider(api_key='explicit-mock-key',enabled=True,cache_root=tmp_path,transport=httpx.MockTransport(handler))
    async def search(scope):
        with stock_request_scope(scope):
            return await adapter.search_images('same public query',orientation='unknown',limit=1)
    try:
        first,second=await asyncio.gather(search('workspace-A'),search('workspace-B'))
        assert first[0].creator=='workspace-A' and second[0].creator=='workspace-B'
        assert sorted(calls)==['workspace-A','workspace-B'] and len(list(tmp_path.rglob('*.json')))==2
        assert SCOPE.get() is None
    finally:await adapter.aclose()


@pytest.mark.parametrize('strategy,mime,expected',[
    ('stock_image','image/png','stock_image'),('stock_image','image/jpeg','stock_image'),
    ('ai_image','image/png','generated_image'),('stock_video','video/mp4','stock_video'),
    ('ai_video','video/mp4','generated_video'),('ai_video','application/vnd.fixture+json','media_contract_fixture')])
def test_materialized_asset_kind_matches_decoded_media_contract(strategy,mime,expected):
    assert _asset_kind(strategy,mime)==expected
