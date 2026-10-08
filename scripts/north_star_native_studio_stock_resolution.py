"""Actual plan/stock worker/import/restore, synthetic official-wire fixtures only."""
import argparse,hashlib,http.client,json,re,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import httpx
from services.windows_native.tests.test_stock import pixels,photo
from services.windows_native.tests.test_human_identity import fixture
from services.windows_native.access import NativeAccess
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.stock_registry import StockFactory,StockCredential
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
WORKSPACE='wsp_native_storyboard_stock_fixture'

def write(path,value):
    with path.open('xb') as handle:handle.write((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def config(root):return Config(data_root=root,runtime_root=root/'absent-runtime',secret_file=root.parent/'absent-fixture-secrets/openai.env',assemblyai_secret_file=root.parent/'absent-fixture-secrets/asr.dpapi')
def snapshot(root):
    from services.windows_native.store import Store
    from services.windows_native.stock import NativeStock
    from services.windows_native.generation_queue import NativeGenerationQueue
    from services.windows_native.generation_worker import NativeGenerationWorker
    from services.windows_native.studio_media_planner import NativeStudioMediaPlanner
    from services.windows_native.studio_media_resolution import NativeStudioMediaResolution
    store=Store(root);stock=NativeStock(store,config(root),workspace_id=WORKSPACE);generation=NativeGenerationWorker(NativeGenerationQueue(store,workspace_id=WORKSPACE),config(root))
    planner=NativeStudioMediaPlanner(store,config(root),workspace_id=WORKSPACE,providers=lambda:{'workspace_id':WORKSPACE})
    service=NativeStudioMediaResolution(planner,generation,stock);projects=[store.get(row['id']) for row in store.list(include_archived=True)]
    with store.transaction() as con:events=[dict(row) for row in con.execute('SELECT * FROM events ORDER BY id')]
    return {'projects':projects,'versions':{p['id']:store.versions(p['id']) for p in projects},'events':events,
        'resolutions':{p['id']:service.page(p['id']) for p in projects},'costs':{p['id']:stock.costs.summary(p['id']) for p in projects},
        'assets':{str(path.relative_to(root)):{'sha256':file_sha(path),'bytes':path.stat().st_size} for directory in ['assets','originals'] for path in sorted((root/directory).glob('*')) if path.is_file()},'default_execution_enabled':False}

def run(args):
    root,out,destination=args.data_root.resolve(),args.output_root.resolve(),args.restore_root.resolve()
    if args.reopen:
        actual=snapshot(root);assert actual==snapshot(destination)==json.loads((out/'offline-snapshot.json').read_bytes())
        write(out/'new-process-replay.json',{'exact_source_and_restored_replay':True,'default_execution_enabled':False,'external_requests':0,'real_provider_tested':False,'owner_uat_accepted':False});print(json.dumps({'status':'STUDIO_STOCK_RESOLUTION_RESTART_PASS'}));return
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-studio-stock-resolution-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned fixture roots required')
    if out.exists() or out==ROOT or ROOT in out.parents or out==root or root in out.parents:raise ValueError('Fresh external evidence required')
    root.mkdir();out.mkdir(parents=True);wires=[];requests=[]
    def wire(request):
        wires.append({'host':request.url.host,'path':request.url.path,'method':request.method})
        if request.url.path=='/v1/search':return httpx.Response(200,json={'photos':[photo()]})
        if request.url.path=='/v1/photos/11':return httpx.Response(200,json=photo())
        if request.url.host=='images.pexels.com':return httpx.Response(200,content=pixels(),headers={'Content-Type':'image/png'})
        raise AssertionError('Unexpected explicit stock wire fixture')
    factory=StockFactory('pexels',StockCredential(api_key='explicit-storyboard-stock-fixture-key',enabled=True),owner_enabled=True,transport=httpx.MockTransport(wire))
    raw,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    class ForbiddenCore:
        def run(self,*_):raise AssertionError('No paid/core provider in stock rehearsal')
    settings=config(root);server=LocalServer(0,settings,pipeline=ForbiddenCore(),start_worker=False,access=access,stock_factories={'pexels':factory})
    cookie,session=access.login(raw);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();server.stock.start(server.observer)
    def send(method,path,body=None,status=200,binary=None,headers=None):
        con=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10);con.request(method,path,body=binary if binary is not None else json.dumps(body) if body is not None else None,
            headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf,**(headers or {})})
        response=con.getresponse();raw=response.read();metadata=dict(response.getheaders());con.close();requests.append({'method':method,'path':path,'status':response.status})
        value=json.loads(raw) if metadata.get('Content-Type','').startswith('application/json') else {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        assert response.status==status,(response.status,value);return value
    def wait(project,identity):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            value=send('GET',f'/api/projects/{project}/media-resolutions/{identity}')
            if value['child']['status']=='succeeded':return value
            assert value['child']['status'] in {'queued','running','retry_scheduled'},value;time.sleep(.05)
        raise AssertionError('Stock fixture worker deadline')
    try:
        project=send('POST','/api/projects',{'name':'EXPLICIT STORYBOARD STOCK FIXTURE','prompt':'Explicit authored teaching fixture; no research provider','channel_profile_ref':'ai-education-reference@1'},status=201);base='/api/projects/'+project['id']
        project=send('POST',base+'/media',binary=pixels(),status=201,headers={'Content-Type':'image/png','X-VF-Revision':str(project['revision']),'X-VF-Rights':'confirmed','X-VF-Illustration':'true','X-VF-Filename':'technology-ai-explicit-owned-fixture.png'})
        proposal={'narration':'Explicit teaching fixture.','visual_brief':[{'scene':1,'visual':'Technology AI educational teaching','on_screen_text':'EXPLICIT STOCK FIXTURE','narration_excerpt':'Explicit teaching fixture.'}],
            'facts_needing_source':['Explicit authored fixture; no researched claims']}
        project=send('POST',base+'/draft',{'revision':project['revision'],'proposal':proposal,'scene_media':[]});view=send('GET',base+'/shots')
        page=send('POST',base+'/media-plans',{'revision':view['revision'],'expected_timeline_version':view['shot_timeline']['version'],'options':{'resolver_priority':['licensed_stock','user_asset'],'preferred_media_type':'image'}})
        record=page['items'][-1];project=server.store.get(project['id']);item=record['plan']['items'][0];assert item['strategy']=='stock_image';before=server.store.shot_view(project['id'])
        common={'revision':project['revision'],'expected_plan_version':record['plan']['version'],'expected_plan_sha256':record['sha256'],'fixture_acknowledged':True}
        search_body={**common,'shot_id':item['shot_id'],'provider':'pexels','request_key':'explicit-storyboard-search-key-01'};path=base+'/media-plans/'+record['plan']['media_plan_id']+'/resolve/search'
        initial=send('POST',path,search_body);search=wait(project['id'],initial['binding']['resolution_id']);replay=send('POST',path,search_body);assert replay['idempotent_replay'] and replay['binding']==search['binding']
        write(out/'stock-search-resolution.json',search);candidate=search['child']['result']['candidates'][0]
        download=send('POST',base+'/media-plans/'+record['plan']['media_plan_id']+'/resolve/download',{**common,'parent_resolution_id':search['binding']['resolution_id'],
            'expected_result_sha256':search['child']['result_sha256'],'candidate_id':candidate['candidate_id'],'expected_candidate_sha256':search['child']['result']['candidate_sha256'][candidate['candidate_id']],
            'request_key':'explicit-storyboard-download-key-01'});download=wait(project['id'],download['binding']['resolution_id']);write(out/'stock-download-resolution.json',download)
        asset=download['child']['result']['asset'];assert asset['rights_status']=='unknown' and not asset['production_eligible'];media=send('GET',base+'/stock/'+download['binding']['child_id']+'/file');assert media['sha256']==asset['sha256']
        body={'revision':project['revision'],'expected_binding_sha256':download['binding_sha256'],'expected_fingerprint':download['child']['request_fingerprint'],
            'expected_asset_sha256':asset['sha256'],'acknowledged':True,'request_key':'explicit-storyboard-import-key-01'}
        imported=send('POST',base+'/media-resolutions/'+download['binding']['resolution_id']+'/import',body);assert imported['replan_required']
        replay=send('POST',base+'/media-resolutions/'+download['binding']['resolution_id']+'/import',body);assert replay['import_receipt']['idempotent_replay'];write(out/'stock-import-resolution.json',imported)
        view=send('GET',base+'/shots');assert view['shot_timeline']['snapshot']==before['shot_timeline']['snapshot'] and view['approval'] is None
        new=send('POST',base+'/media-plans',{'revision':view['revision'],'expected_timeline_version':view['shot_timeline']['version'],'options':{'resolver_priority':['licensed_stock','user_asset'],'preferred_media_type':'image'}})
        candidates=[c for i in new['items'][-1]['plan']['items'] for c in i['candidates'] if c['asset_id']==asset['id']];assert candidates and all(not c['selectable'] for c in candidates);write(out/'stock-replan-rights-blocked.json',new)
        costs=server.stock.costs.summary(project['id']);assert len(wires)==3 and len(costs['records'])==2 and all(not r['paid'] and r['actual_cost'] is None for r in costs['records']);write(out/'cost.json',costs)
        write(out/'stock-mock-wires.json',wires);write(out/'human-http-wires.json',requests)
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
    backup=create_backup(settings,out/'native-storyboard-stock-backup.zip');counts=backup['database_status']['workflow.sqlite3']['counts'];assert counts['native_media_resolutions']==2 and counts['native_stock_imports']==1
    restore=restore_backup(out/'native-storyboard-stock-backup.zip',destination,expected_sha256=backup['sha256']);actual=snapshot(root);assert snapshot(destination)==actual
    write(out/'backup-restore.json',{'backup':backup,'restore':restore,'exact_resolution_restore':True});write(out/'offline-snapshot.json',actual)
    source=['services/windows_native/studio_media_resolution.py','services/windows_native/studio_media_resolution_routes.py','services/windows_native/generation_queue.py','services/windows_native/stock.py',
        'services/windows_native/server.py','services/windows_native/access.py','services/windows_native/backup.py','apps/studio-web/native-media-planner.mjs','apps/studio-web/native-media-resolution.mjs','scripts/north_star_native_studio_stock_resolution.py']
    write(out/'evidence.json',{'schema_version':'north-star-native-storyboard-stock-resolution-v1','explicit_fixture':True,'project_id':project['id'],'workspace_id':WORKSPACE,
        'actual_native_worker':True,'manually_injected_provider_result':False,'resolution_bindings':2,'actual_human_http_requests':len(requests),'mock_stock_wire_requests':3,
        'explicit_imports':1,'replan_rights_gate_verified':True,'timeline_placement_unchanged':True,'actual_backup_restore':True,'paid_operations':0,'actual_cost_vnd':None,'rights_independently_verified':False,
        'real_provider_tested':False,'owner_uat_accepted':False,'production_deployed':False,'source_sha256':{p:file_sha(ROOT/p) for p in source},
        'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}});print(json.dumps({'status':'STUDIO_STOCK_RESOLUTION_LOCAL_REAL_MOCK_PROVIDER_PASS','bindings':2,'mock_wires':3}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True);parser.add_argument('--restore-root',type=Path,required=True);parser.add_argument('--reopen',action='store_true');run(parser.parse_args())
