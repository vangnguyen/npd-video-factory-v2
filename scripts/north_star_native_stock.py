"""Official-wire mocks, real local image/video intake and offline recovery.

Fresh playable clone only; no provider account, external media, publication or UAT.
"""
import argparse,hashlib,http.client,io,json,re,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import httpx
from PIL import Image
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha
from services.windows_native.server import LocalServer
from services.windows_native.stock import NativeStock
from services.windows_native.stock_registry import StockFactory,StockCredential
from services.windows_native.source_broll import shared_assets
from services.windows_native.source_assets import canonical_assets
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from north_star_native_bridge import read_state,config,WORKSPACE


class NoProvider:
    def run(self,*_):raise AssertionError('No existing media/provider dispatch in stock intake rehearsal')


def state(root):
    result=read_state(root)
    from services.windows_native.store import Store
    store=Store(root);service=NativeStock(store,config(root),workspace_id=WORKSPACE)
    result['stock']={row['id']:service.page(row['id'],limit=100) for row in result['projects']}
    result['costs']={row['id']:service.costs.summary(row['id']) for row in result['projects']}
    with store.transaction() as con:
        result['stock_imports']=[dict(row) for row in con.execute('SELECT * FROM native_stock_imports ORDER BY stock_id')]
        result['stock_events']=[dict(row) for row in con.execute('SELECT * FROM native_stock_events ORDER BY sequence')]
    result['default_provider_configuration']=service.providers();return result


def run(args):
    root=args.data_root.resolve();destination=args.restore_root.resolve();out=args.output.resolve();parent=args.parent_evidence.resolve()
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-stock-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned stock roots required')
    if root==destination:raise ValueError('Distinct roots required')
    proof=json.loads((parent/'evidence.json').read_bytes());recovery=json.loads((parent/'recovery.json').read_bytes())
    assert proof['local_real_full_qc'] and proof['explicit_synthetic_owned_provenance_seed'] and not proof['owner_uat']
    out.mkdir(parents=True,exist_ok=False);restored=restore_backup(parent/'native-bridge-backup.zip',root,expected_sha256=recovery['backup']['sha256'])
    raw,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,config(root),pipeline=NoProvider(),start_worker=False,access=access);cookie,session=access.login(raw)
    project=server.store.get(proof['project_id']);source=next(row for row in canonical_assets(project['document']) if row['kind']=='video');movie=(root/'assets'/source['id']).read_bytes()
    buffer=io.BytesIO();Image.new('RGB',(320,240),(35,105,165)).save(buffer,format='PNG');png=buffer.getvalue();wire=[]
    def receiver(request):
        wire.append({'host':request.url.host,'path':request.url.path,'fixture':True,'actual_provider_call':False})
        if request.url.host=='api.pexels.com':assert request.headers['Authorization']=='explicit-fixture-stock-key'
        if request.url.host=='pixabay.com':assert request.url.params['key']=='explicit-fixture-stock-key'
        if request.url.host in ('images.pexels.com','cdn.pixabay.com'):assert 'Authorization' not in request.headers and 'key' not in request.url.params
        photo={'id':11,'width':640,'height':360,'url':'https://www.pexels.com/photo/explicit-fixture-11/',
            'photographer':'EXPLICIT SYNTHETIC PIXELS · NOT A REAL CREATOR RESULT','alt':'EXPLICIT TECHNOLOGY FIXTURE',
            'src':{'original':'https://images.pexels.com/photos/11/explicit-fixture.png'}}
        video={'id':41,'user':'EXPLICIT LOCAL SYNTHETIC VIDEO · NOT PROVIDER MEDIA','pageURL':'https://pixabay.com/videos/explicit-fixture-41/','duration':3.,
            'videos':{'medium':{'url':'https://cdn.pixabay.com/video/explicit-fixture.mp4','width':320,'height':240}}}
        if request.url.path=='/v1/search':return httpx.Response(200,json={'photos':[photo]})
        if request.url.path=='/v1/photos/11':return httpx.Response(200,json=photo)
        if request.url.host=='images.pexels.com':return httpx.Response(200,content=png,headers={'Content-Type':'image/png'})
        if request.url.host=='pixabay.com':return httpx.Response(200,json={'hits':[video]})
        if request.url.host=='cdn.pixabay.com':return httpx.Response(200,content=movie,headers={'Content-Type':'video/mp4'})
        raise AssertionError('Unexpected explicit official wire fixture')
    factories={key:StockFactory(key,StockCredential(api_key='explicit-fixture-stock-key',enabled=True),owner_enabled=True,
        transport=httpx.MockTransport(receiver)) for key in ['pexels','pixabay']}
    server.stock=NativeStock(server.store,config(root),workspace_id=WORKSPACE,factories=factories)
    server.stock.start(server.observer);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();calls=[];before=state(root)
    artifacts={p.relative_to(root).as_posix():file_sha(p) for name in ['assets','originals','jobs','shot-previews'] for p in (root/name).rglob('*') if p.is_file()}
    def account(role):
        nonlocal cookie,session
        token,data=fixture(role,workspace=WORKSPACE);controller=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),WORKSPACE)
        controller.bind_root(root);server.access=controller;cookie,session=controller.login(token)
    def request(method,path,body=None,*,status=200):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();payload=response.read();headers=dict(response.getheaders());connection.close()
        value=json.loads(payload) if headers.get('Content-Type','').startswith('application/json') else {'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
        calls.append({'method':method,'path':path,'status':response.status});assert response.status==status,(response.status,value);assert headers['Cache-Control']=='no-store';return value
    def wait(identity):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            value=request('GET',base+'/'+identity)
            if value['status']=='succeeded':return value
            if value['status'] in ('failed','not_configured','cancelled'):raise AssertionError(value['failure_code'])
            time.sleep(.1)
        raise AssertionError('Bounded owned stock worker deadline')
    base='/api/projects/'+project['id']+'/stock';bundles=[]
    try:
        configured=request('GET','/api/stock/providers');assert all(row['mode']=='fixture' for row in configured['items']) and not configured['ui_enablement_supported']
        for provider,kind in [('pexels','image'),('pixabay','video')]:
            account('owner');current=server.store.get(project['id']);body={'revision':current['revision'],'provider':provider,'query':'EXPLICIT SYNTHETIC TECHNOLOGY FIXTURE',
                'media_type':kind,'orientation':'landscape','limit':3,'fixture_acknowledged':True,'request_key':'native-stock-playable-search-'+provider}
            if provider=='pexels':
                account('viewer');request('POST',base+'/search',body,status=403);request('GET',base+'?limit=1');account('owner')
                request('POST',base+'/search',{**body,'download_url':'https://untrusted.example/file'},status=400)
            search=request('POST',base+'/search',body);search=wait(search['stock_id']);candidate=search['result']['candidates'][0]
            assert search['result']['mock'] and search['result']['actual_provider_calls']==0 and candidate['semantic_score'] is None
            download={'revision':current['revision'],'search_id':search['stock_id'],'candidate_id':candidate['candidate_id'],
                'expected_result_sha256':search['result_sha256'],'expected_candidate_sha256':search['result']['candidate_sha256'][candidate['candidate_id']],
                'fixture_acknowledged':True,'request_key':'native-stock-playable-download-'+provider}
            ready=request('POST',base+'/download',download);ready=wait(ready['stock_id']);asset=ready['result']['asset']
            assert asset['rights_status']=='unknown' and not asset['production_eligible'] and asset['needs_attention'] and ready['result']['full_native_media_validation_passed']
            assert server.store.get(project['id'])['document']==current['document'] and server.store.get(project['id'])['revision']==current['revision']
            local=request('GET',base+'/'+ready['stock_id']+'/file');assert local['sha256']==asset['sha256']
            attach={'revision':current['revision'],'expected_fingerprint':ready['request_fingerprint'],'expected_asset_sha256':asset['sha256'],
                'acknowledged':True,'request_key':'native-stock-playable-attachment-'+provider}
            account('viewer');request('POST',base+'/'+ready['stock_id']+'/import',attach,status=403);account('editor')
            receipt=request('POST',base+'/'+ready['stock_id']+'/import',attach);replay=request('POST',base+'/'+ready['stock_id']+'/import',attach)
            assert replay['idempotent_replay'] and not receipt['rights_independently_verified'] and receipt['approval_invalidated']
            assert request('GET',base+'/'+ready['stock_id'])['attachment']==receipt
            (out/(provider+'-registered'+Path(asset['id']).suffix)).write_bytes((root/'assets'/asset['id']).read_bytes())
            bundles.append({'search':search,'download':ready,'attachment':receipt,'local_file':local})
        after=state(root);current=server.store.get(project['id']);projected=shared_assets(current,config(root))
        stock=[value.model_dump(mode='json') for value in projected.values() if value.provenance['source_type']=='stock']
        assert len(stock)==2 and all(value['provenance']['rights_status']=='unknown' and value['provenance']['fixture'] for value in stock)
        assert current['approval'] is None and current['jobs']==project['jobs'];assert after['versions'][project['id']][2:]==before['versions'][project['id']]
        assert all(file_sha(root/name)==sha for name,sha in artifacts.items());assert all(row['result']['mock'] for row in after['stock'][project['id']]['items'])
        assert len(after['costs'][project['id']]['records'])-len(before['costs'][project['id']]['records'])==4
        proof_out={'schema_version':'native-stock-contract-v1','project_id':project['id'],'parent_final_sha256':proof['final_sha256'],'parent_preview_sha256':proof['preview_sha256'],
            'authenticated_http_requests':len(calls),'fixture_wire_attempts':len(wire),'actual_provider_calls':0,'stock_searches':2,'stock_downloads':2,'explicit_attachments':2,
            'independent_worker_executed':True,'real_local_image_decode':True,'real_local_video_full_decode':True,'source_metadata_and_actual_dimensions_separate':True,
            'fixture_rights_remain_unknown':True,'no_automatic_attachment':True,'old_jobs_versions_and_media_unchanged':True,'core_approval_invalidated':True,
            'source_broll_projection_preserves_stock_and_unknown_rights':True,'actual_media_rerendered':False,'real_credentials_read':0,'actual_publications':0,'paid_operations':0,
            'actual_hub_calls':0,'owner_uat':False,'browser_real_tested':False,'production_deployed':False}
        for name,value in [('contract.json',proof_out),('http-requests.json',calls),('stock-bundles.json',bundles),('wire-audit.json',wire),('source-projections.json',stock),
            ('stock-history.json',after['stock'][project['id']]),('cost.json',after['costs'][project['id']]),('stock-events.json',after['stock_events']),('source-restore.json',restored)]:
            (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    frozen=state(root);restart=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root)],timeout=60));assert restart==frozen
    backup=create_backup(config(root),out/'native-stock-backup.zip');restored=restore_backup(out/'native-stock-backup.zip',destination,expected_sha256=backup['sha256'])
    fresh=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(destination)],timeout=60));assert fresh==frozen
    assert all(file_sha(destination/name)==sha for name,sha in artifacts.items())
    (out/'recovery.json').write_text(json.dumps({'backup':backup,'restore':restored,'new_process_exact':True,'fresh_root_restore_exact':True,
        'stock_adapters_default_not_configured_on_restore':True,'parent_media_unchanged':True},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'stock':'PASS','stock_searches':2,'stock_downloads':2,'attachments':2,'fixture_wire_attempts':len(wire),'authenticated_http_requests':len(calls),
        'real_local_image_video_decode':True,'restart_restore':'PASS','actual_provider_calls':0,'owner_uat':False}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path);parser.add_argument('--restore-root',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--parent-evidence',type=Path);parser.add_argument('--read-root',type=Path);args=parser.parse_args()
    if args.read_root:print(json.dumps(state(args.read_root),ensure_ascii=True))
    else:run(args)
