"""Human operator selection/cancellation/recovery on a fresh owned playable clone."""
import argparse,http.client,json,re,subprocess,sys,threading,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.bridge_transport import FixtureWebhookTransport,BridgeResponse
from services.windows_native.contracts import file_sha
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_human_identity import fixture
from app.bridge_auth import SigningKeyring
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from north_star_native_bridge import read_state,config,WORKSPACE,KEY

class NoProvider:
    def run(self,*_):raise AssertionError('No media/provider dispatch in operator rehearsal')

def run(args):
    root=args.data_root.resolve();destination=args.restore_root.resolve();out=args.output.resolve();parent=args.parent_evidence.resolve()
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-bridge-operator-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned operator roots required')
    if root==destination:raise ValueError('Distinct roots required')
    proof=json.loads((parent/'evidence.json').read_bytes());recovery=json.loads((parent/'recovery.json').read_bytes())
    assert proof['actual_hub_calls']==0 and proof['local_real_full_qc'] and proof['explicit_synthetic_owned_provenance_seed'] and not proof['owner_uat']
    out.mkdir(parents=True,exist_ok=False)
    source_restore=restore_backup(parent/'native-bridge-backup.zip',root,expected_sha256=recovery['backup']['sha256'])
    before=read_state(root);artifacts={p.relative_to(root).as_posix():file_sha(p) for name in ['assets','originals','jobs','shot-previews'] for p in (root/name).rglob('*') if p.is_file()}
    raw,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,config(root),pipeline=NoProvider(),start_worker=False,access=access);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();calls=[];wire=[];signing=SigningKeyring('fixture-v1',{'fixture-v1':KEY})
    def receiver(body,headers):
        value=json.loads(body);assert signing.verify(body,key_id=headers['X-NPD-Key-Id'],timestamp=int(headers['X-NPD-Timestamp']),event_id=value['event_id'],signature=headers['X-NPD-Signature'])
        assert headers['Idempotency-Key']==value['event_id'];wire.append({'event_id':value['event_id'],'signed_fixture_verified':True,'actual_hub_call':False});return BridgeResponse(204)
    def account(role):
        nonlocal cookie,session
        token,data=fixture(role,workspace=WORKSPACE);controller=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),WORKSPACE)
        controller.bind_root(root);server.access=controller;cookie,session=controller.login(token)
    def request(method,path,body=None,*,status=200):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();value=json.loads(response.read());headers=dict(response.getheaders());connection.close()
        calls.append({'method':method,'path':path,'status':response.status});assert response.status==status,(response.status,value);assert headers['Cache-Control']=='no-store';return value
    try:
        initial=request('GET','/api/bridge/state');assert not initial['webhook_delivery_enabled'] and not initial['http_enablement_from_ui']
        first=request('POST','/api/projects',{'name':'EXPLICIT OPERATOR CANCELLATION FIXTURE','prompt':'Private owned fixture draft'},status=201)
        page=request('GET','/api/bridge/events?limit=100');selected=next(row for row in page['items'] if row['envelope']['payload'].get('project_id')==first['id'])
        assert selected['delivery']['status']=='disabled'
        server.bridge.configure_delivery(transport=FixtureWebhookTransport(receiver),signing=signing,enabled=True)
        enabled=request('GET','/api/bridge/state');body={'expected_envelope_sha256':selected['envelope_sha256'],'expected_destination_sha256':enabled['destination_sha256'],
            'expected_mode':'fixture','fixture_acknowledged':True,'http_acknowledged':False,'request_key':'native-operator-playable-select-key'}
        base='/api/bridge/events/'+selected['envelope']['event_id'];account('viewer')
        request('POST',base+'/enqueue',body,status=403);request('GET','/api/bridge/events?limit=1');account('owner')
        receipt=request('POST',base+'/enqueue',body);assert receipt['selected_status']=='queued' and not receipt['external_call_performed']
        replay=request('POST',base+'/enqueue',body);assert replay['idempotent_replay']
        server.bridge.delivery_enabled=False
        cancellation=request('POST',base+'/cancel',{**body,'fixture_acknowledged':False,'request_key':'native-operator-playable-cancel-key'})
        assert cancellation['selected_status']=='cancelled';assert server.bridge.process() is None
        stopped=request('GET',base+'/delivery');assert stopped['delivery']['status']=='cancelled' and not stopped['attempts']
        server.bridge.configure_delivery(transport=FixtureWebhookTransport(receiver),signing=signing,enabled=True)
        request('POST','/api/projects',{'name':'EXPLICIT ENABLED PRODUCER FIXTURE','prompt':'Private fresh fixture'},status=201)
        assert server.bridge.process() is not None and server.bridge.process() is None
        final_page=request('GET','/api/bridge/events?limit=100');assert len(wire)==1
        succeeded=next(row for row in final_page['items'] if row['envelope']['event_id']==wire[0]['event_id'])
        audit=request('GET','/api/bridge/events/'+wire[0]['event_id']+'/delivery');assert audit['fixture'] and not audit['real_hub_receipt_verified'] and succeeded['delivery']['status']=='succeeded'
        for old in before['projects']:
            assert server.store.get(old['id'])==old and server.store.versions(old['id'])==before['versions'][old['id']]
        assert all(file_sha(root/name)==sha for name,sha in artifacts.items())
        results={'schema_version':'native-bridge-operator-contract-v1','parent_project_id':proof['project_id'],'parent_final_sha256':proof['final_sha256'],
            'parent_preview_sha256':proof['preview_sha256'],'cancelled_event_id':selected['envelope']['event_id'],'delivered_fixture_event_id':wire[0]['event_id'],
            'authenticated_http_requests':len(calls),'owner_mock_selection':True,'viewer_blocked':True,'cancel_after_disable':True,'fixture_signed_deliveries':1,
            'parent_documents_histories_media_unchanged':True,'actual_hub_calls':0,'actual_provider_calls':0,'real_credentials_read':0,
            'actual_media_rerendered':False,'owner_uat':False,'browser_real_tested':False,'production_deployed':False}
        for name,value in [('contract.json',results),('http-requests.json',calls),('operator-state.json',enabled),('selection.json',receipt),
            ('cancellation.json',cancellation),('cancelled-audit.json',stopped),('delivered-audit.json',audit),('wire-audit.json',wire),
            ('events.json',final_page),('source-restore.json',source_restore)]:
            (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    before_restore=read_state(root)
    # The default-disabled restarted instance retains cancellation and audit; it
    # does not load signing keys or resume external delivery after a restore.
    restart=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root)],timeout=60));assert restart==before_restore
    backup=create_backup(config(root),out/'native-operator-backup.zip');restore=restore_backup(out/'native-operator-backup.zip',destination,expected_sha256=backup['sha256'])
    after=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(destination)],timeout=60));assert after==before_restore
    assert all(file_sha(destination/name)==sha for name,sha in artifacts.items())
    (out/'recovery.json').write_text(json.dumps({'backup':backup,'restore':restore,'new_process_exact':True,'fresh_root_restore_exact':True,
        'default_disabled_on_restore':True,'parent_media_unchanged':True},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'operator':'PASS','native_http_requests':len(calls),'cancelled_events':1,'signed_fixture_deliveries':1,'restart_restore':'PASS','actual_hub_calls':0}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path);parser.add_argument('--restore-root',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--parent-evidence',type=Path);parser.add_argument('--read-root',type=Path);args=parser.parse_args()
    if args.read_root:print(json.dumps(read_state(args.read_root),ensure_ascii=True))
    else:run(args)
