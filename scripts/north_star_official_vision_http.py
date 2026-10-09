"""Retained signed loopback Vision rehearsal; no real credentials, spend or inference."""
import argparse,http.client,json,re,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer
from services.windows_native.vision import NativeVision
from services.windows_native.vision_credentials import NativeVisionKeyVault
from services.windows_native.vision_registry import VisionProfile,NativeVisionFactory
from services.windows_native.media_frame_analysis import view
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.observability import Observer
from scripts.north_star_official_vision import config_for,write,WORKSPACE
from scripts.north_star_vision_registry import journals


def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-vision-http-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():
        raise ValueError('Fresh owned official Vision HTTP fixture required')
    return path


def access():
    raw,data=human_fixture('owner',workspace=WORKSPACE)
    return raw,NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),WORKSPACE)


def reopen(args):
    root=owned(args.restore_root,'restore');out=args.output.resolve();raw,identity=access();before=None
    with LocalServer(0,config_for(root),pipeline=NoProviderPipeline(),start_worker=False,access=identity) as server:
        expected=json.loads((out/'expected-all-official-history.json').read_bytes())
        for row in expected:assert server.official_vision.get(row['project_id'],row['vision_id'])==row
        for project in json.loads((out/'expected-projects.json').read_bytes()):assert server.store.get(project['id'])==project
        legacy=NativeVision(server.store,server.config)
        for row in json.loads((out/'expected-legacy-history.json').read_bytes()):assert legacy.get(row['project_id'],row['vision_id'])==row
        before=journals(server.store);assert before==json.loads((out/'expected-all-journals.json').read_bytes())
        assert server.official_vision.recover()==0 and not server.runner.run_one()
        assert journals(server.store)==before and database_status(server.store.db)['active_operations']==0
        assert not server.official_vision.states()['enabled'] and server.official_vision.states()['profiles']==[]
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
        'all_current_journals_exact':True,'journal_count':len(before),'all_official_histories_exact':len(expected),
        'original_projects_and_legacy_history_exact':True,'current_credentials_config_identity_required_for_history':False,
        'startup_decryption':False,'dispatch_retry_or_consent_renewal':False,'real_provider_tested':False,'owner_uat_accepted':False})


def run(args):
    state=owned(args.state_root,'state',True);restored=owned(args.restore_root,'restore',True);out=args.output.resolve();prior=args.kernel_input.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);archive=prior/'public-official-vision.zip'
    write(out/'prior-restore.json',restore_backup(archive,state,expected_sha256=file_sha(archive)))
    projects=json.loads((prior/'expected-budgeted-projects.json').read_bytes());old_history=json.loads((prior/'expected-runtime-history.json').read_bytes())
    old_legacy=json.loads((prior/'expected-legacy-history.json').read_bytes());old_journals=json.loads((prior/'expected-journals.json').read_bytes())
    raw,identity=access();config=config_for(state);private=Path('C:/vf-native-fixture-vision-registry-secrets-01')
    vault=NativeVisionKeyVault(private,state,WORKSPACE);profile=VisionProfile.model_validate(json.loads((private/'public-vision-registry.json').read_bytes())['profiles'][0])
    private_hashes={p.name:file_sha(p) for p in private.glob('*.dpapi')};files={p.relative_to(state).as_posix():file_sha(p) for p in state.rglob('*')
        if p.is_file() and p.suffix!='.sqlite3' and not p.name.endswith(('-wal','-shm'))}
    wire=[];mode=[None];logs=[]
    def response(request):
        body=json.loads(request.content);count=sum(v['type']=='input_image' for v in body['input'][0]['content'])
        assert str(request.url)=='https://api.openai.com/v1/responses' and request.method=='POST' and body['store'] is False
        wire.append({'kind':mode[0],'frame_count':count,'fixed_endpoint':True,'mock':True})
        if mode[0]=='timeout':raise httpx.ReadTimeout('EXPLICIT SYNTHETIC HTTP VISION TIMEOUT',request=request)
        payload=response_payload(count)
        if mode[0]=='invalid':payload['output'][0]['content'][0]['text']='INVALID EXPLICIT STRUCTURED MOCK'
        return httpx.Response(200,json=payload)
    factory=NativeVisionFactory(profile,vault,operator_enabled=True,transport=httpx.MockTransport(response));pipeline=NoProviderPipeline()
    server=LocalServer(0,config,pipeline=pipeline,start_worker=False,access=identity,observer=Observer(logs.append),
        official_vision_directory=private,official_vision_enabled=True,official_vision_factories={profile.profile_id:factory})
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();cookie,session=identity.login(raw);http_calls=[]
    def request(method,path,body=None,expected=200):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        conn.request(method,path,body=json.dumps(body) if body is not None else None,
            headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        reply=conn.getresponse();value=json.loads(reply.read());conn.close();assert reply.status==expected,(path,value)
        assert all(v.strip()=='no-store' for v in reply.getheader('Cache-Control','').split(','));http_calls.append({'method':method,'route':path.partition('?')[0],'status':reply.status});return value
    try:
        session_before=request('GET','/api/session');states=request('GET','/api/connections/official-vision')
        assert states['enabled'] and states['profiles'][0]['mock'] and not session_before['capabilities']['native_official_vision']
        expected=[]
        for index,kind in enumerate(('image-success','video-success','invalid','timeout','cancel')):
            mode[0]=kind;project=projects[index%2];frames=view(server.store,project['id']);base='/api/projects/'+project['id']+'/official-vision'
            body={'revision':project['revision'],'profile_id':profile.profile_id,'expected_configuration_sha256':factory.sha256,
                'observation_id':frames['observations'][0]['observation_id'],'acknowledged_external_image_analysis':True,
                'acknowledged_protocol_mock':True,'max_operation_cost_vnd':'500','valid_for_seconds':600,'request_key':'retained-signed-official-vision-'+kind}
            row=request('POST',base,body);assert row['status']=='approved';assert not server.runner.run_one()
            action={'expected_snapshot_sha256':row['snapshot_sha256']};route=base+'/'+row['vision_id']
            if kind=='cancel':request('POST',route+'/cancel',action)
            done=request('POST',route+'/process',action)
            assert done['status']==('succeeded' if index<2 else 'review_required' if kind=='invalid' else 'outcome_unknown' if kind=='timeout' else 'cancelled')
            assert request('GET',route)==done and request('POST',route+'/process',action)==done
            assert request('POST',base,body)['idempotent_replay'];assert server.store.get(project['id'])==project;expected.append(done)
        assert len(wire)==4 and sum(v['response'] is not None for v in expected)==3 and sum(v['result'] is not None for v in expected)==2
        for row in old_history:assert request('GET','/api/projects/'+row['project_id']+'/official-vision/'+row['vision_id'])==row
        assert request('GET','/api/session')==session_before and not server.runner.run_one() and pipeline.calls==0
        for project in projects:
            page=request('GET','/api/projects/'+project['id']+'/official-vision?limit=1');seen=[page['items'][0]['vision_id']]
            while page['next_cursor']:
                page=request('GET','/api/projects/'+project['id']+'/official-vision?limit=1&cursor='+page['next_cursor']);seen.extend(v['vision_id'] for v in page['items'])
            assert set(seen)=={v['vision_id'] for v in old_history+expected if v['project_id']==project['id']}
        legacy=NativeVision(server.store,config)
        for row in old_legacy:assert legacy.get(row['project_id'],row['vision_id'])==row
        current=journals(server.store)
        for table,rows in old_journals.items():
            assert all(row in current[table] for row in rows),table
        assert all(file_sha(state/name)==value for name,value in files.items()) and all(file_sha(private/name)==value for name,value in private_hashes.items())
        costs=[server.official_vision.costs.summary(p['id']) for p in projects]
        assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for p in costs for r in p['records'])
        write(out/'expected-all-official-history.json',old_history+expected);write(out/'new-signed-history.json',expected);write(out/'expected-projects.json',projects)
        write(out/'expected-legacy-history.json',old_legacy);write(out/'expected-all-journals.json',current);write(out/'mock-wire-summary.json',wire)
        write(out/'signed-http-summary.json',http_calls);write(out/'observer-events.json',logs);write(out/'cost-summary.json',costs)
    finally:server.shutdown();server.server_close();thread.join()
    backup=create_backup(config,out/'public-official-vision-http.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-official-vision-http.zip',restored,expected_sha256=backup['sha256']));reopen(args)
    names=('services/windows_native/server.py','services/windows_native/access.py','services/windows_native/official_vision.py',
        'services/windows_native/official_vision_routes.py','services/windows_native/tests/test_official_vision_http.py','scripts/north_star_official_vision_http.py')
    write(out/'evidence.json',{'schema_version':'native-official-vision-http-rehearsal-v1','source_sha256':{n:file_sha(ROOT/n) for n in names},
        'signed_http_requests':len(http_calls),'new_finite_intents':5,'new_mock_requests':4,'new_complete_responses':3,'new_mock_results':2,
        'all_current_journals':len(current),'all_official_histories':len(old_history+expected),'reused_unique_pngs':9,'new_cpu_jobs':0,
        'original_projects_old_histories_original_files_private_generations_exact':True,'session_shape_and_default_false_flag_exact':True,
        'startup_recovery_only_no_dispatch_retry_or_consent_renewal':True,'paid_costs_known':False,'real_credentials':False,'external_provider_calls':0,
        'paid_operations':0,'semantic_inference_performed':False,'publishing_enabled':False,'owner_uat_accepted':False,'real_provider_tested':False,
        'studio_integrated':False,'production_deployed':False,'public_backup_sha256':backup['sha256'],
        'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','signed_http_requests':len(http_calls),'new_mock_requests':4,'all_current_journals':len(current),'all_official_histories':13}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--kernel-input',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--state-root',type=Path);p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--new-process',action='store_true');args=p.parse_args()
    reopen(args) if args.new_process else run(args)
