"""Owned signed account-read/DPAPI/recovery rehearsal; every wire result is a fixture.

No real OAuth token, external account, publication, render or paid operation is used.
"""
import argparse,http.client,json,re,sys,threading,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import httpx
from scripts.north_star_native_analytics_refresh import settings,access,write,WORKSPACE
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha,WorkflowError
from services.windows_native.server import LocalServer
from services.windows_native.official_account_tokens import save as save_token
from services.windows_native.official_account_registry import AccountFactory,Registry,load as load_registry
from app.analytics_official import YT_READ,YT_ANALYTICS

def owned(path,*,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-accounts-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Exact owned account fixture root required')
    return path

def factories(registry,root,calls):
    registered=load_registry(registry,root,WORKSPACE)
    def response(request):
        calls.append({'method':request.method,'host':request.url.host,'path':request.url.path,'query':str(request.url.query,'ascii'),
            'explicit_fixture':True,'token_logged':False,'external_call':False})
        assert request.method=='GET' and not request.content
        if request.url.host=='www.googleapis.com':return httpx.Response(200,json={'items':[{'id':'UC_EXPLICIT_ACCOUNT_REHEARSAL'}]})
        assert request.url.host=='open.tiktokapis.com' and request.url.path=='/v2/user/info/'
        return httpx.Response(200,json={'data':{'user':{'open_id':'EXPLICIT_TIKTOK_OPEN_ID_REHEARSAL'}},'error':{'code':'ok'}})
    return {key:AccountFactory(value.account,root,WORKSPACE,owner_read_enabled=True,transport=httpx.MockTransport(response)) for key,value in registered.items()}

def media(root):
    return {p.relative_to(root).as_posix():file_sha(p) for name in ('assets','originals','jobs','shot-previews') for p in (root/name).rglob('*') if p.is_file()}

def run(args):
    root,restored,secrets=owned(args.data_root,fresh=True),owned(args.restore_root,fresh=True),owned(args.secret_root,fresh=True)
    if len({root,restored,secrets})!=3:raise ValueError('Separate fresh owned state, restore and fixture token roots required')
    out=args.output.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents or any(p==out or p in out.parents for p in (root,restored,secrets)):raise ValueError('Fresh separate evidence folder required')
    if not re.fullmatch(r'[a-f0-9]{32}',args.project_id):raise ValueError('Exact project required')
    out.mkdir(parents=True);secrets.mkdir();write(out/'initial-restore.json',restore_backup(args.backup,root,expected_sha256=args.expected_sha256))
    accounts=[];receipts=[]
    for index,platform in enumerate(('youtube','tiktok'),1):
        token_file=secrets/(platform+'-explicit-fixture.dpapi');alias=platform+'-rehearsal-read'
        binding=str(index)*64
        token={'workspace_id':WORKSPACE,'credential_alias':alias,'credential_binding_sha256':binding,'platform':platform,
            'expires_at':(datetime.now(timezone.utc)+timedelta(hours=3)).isoformat(),
            'scopes':[YT_READ,YT_ANALYTICS] if platform=='youtube' else ['user.info.basic','video.list'],
            'token':'EXPLICIT-'+platform.upper()+'-FIXTURE-ONLY-NOT-A-REAL-ACCESS-TOKEN'}
        receipts.append(save_token(token_file,root,token));assert token['token'].encode() not in token_file.read_bytes()
        accounts.append({'account_ref':'npac_'+str(index)*32,'target':{'workspace_id':WORKSPACE,'profile_id':'ppf_'+platform+'_account_rehearsal','profile_version':1,
            'platform':platform,'provider_key':'youtube-data-api-publishing' if platform=='youtube' else 'tiktok-content-posting-api',
            'target_account_id':'UC_EXPLICIT_ACCOUNT_REHEARSAL' if platform=='youtube' else 'EXPLICIT_TIKTOK_OPEN_ID_REHEARSAL','credential_binding_sha256':binding},
            'credential_alias':alias,'token_file':str(token_file),'read_enabled':True,'publishing_enabled':False})
    registry=secrets/'explicit-fixture-registry.json';write(registry,Registry(version=1,workspace_id=WORKSPACE,accounts=accounts).model_dump(mode='json'))
    write(out/'dpapi-fixture-receipts.json',receipts)
    auth,cookie,session=access();default=LocalServer(0,settings(root),start_worker=False,access=auth,official_account_registry=registry)
    try:
        state=default.official_accounts.states();assert all(a['status']=='NOT_CONFIGURED' and not a['external_reads_enabled'] for a in state['accounts'])
        assert default.official_accounts.process() is None;write(out/'default-disabled-state.json',state)
    finally:default.server_close()
    calls=[];auth,cookie,session=access();server=LocalServer(0,settings(root),start_worker=False,access=auth,official_account_factories=factories(registry,root,calls))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[];base='/api/projects/'+args.project_id
    def send(method,path,body=None,expected=200):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        conn.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=conn.getresponse();value=json.loads(response.read());conn.close();requests.append({'method':method,'path':path,'status':response.status})
        assert response.status==expected,(response.status,value);return value
    try:
        original=server.store.get(args.project_id);physical=media(root);write(out/'project-before.json',original);write(out/'physical-source-hashes.json',physical)
        before=send('GET',base+'/account-checks?limit=100');assert before['items']==[];states=send('GET','/api/connections/official-accounts');write(out/'explicit-fixture-state.json',states)
        assert len(calls)==0 and all(a['mode']=='fixture' and a['status']=='CONFIGURED' and not a['external_reads_enabled'] for a in states['accounts'])
        bodies={};expected={}
        for index,account in enumerate(states['accounts'],1):
            body={'revision':original['revision'],'expected_configuration_sha256':account['configuration_sha256'],'acknowledged_read_only':True,'request_key':'owned-explicit-account-check-'+str(index)}
            path=base+'/official-accounts/'+account['account_ref']+'/verify';created=send('POST',path,body);assert created['status']=='queued'
            if index==1:
                try:create_backup(settings(root),out/'rejected-pending-check.zip')
                except WorkflowError as error:assert error.code=='BACKUP_SOURCE_HAS_ACTIVE_OPERATIONS'
                else:raise AssertionError('Queued account check must prevent backup')
                write(out/'queued-backup-admission.json',{'blocked':True,'code':'BACKUP_SOURCE_HAS_ACTIVE_OPERATIONS','archive_created':False})
            assert server.runner.run_one();check=send('GET',base+'/account-checks/'+created['check_id']);assert check['status']=='succeeded'
            assert check['result']['mock'] and not check['result']['external_call'] and check['result']['account_match']
            assert send('POST',path,body)['idempotent_replay'];assert len(calls)==index
            bodies[account['account_ref']]=body;expected[check['check_id']]=check
            write(out/(account['target']['platform']+'-fixture-check.json'),check)
        # Expired credentials produce no account request, cost record, authority or media job.
        server.official_accounts.clock=lambda:datetime.now(timezone.utc)+timedelta(hours=4)
        first=states['accounts'][0];path=base+'/official-accounts/'+first['account_ref']+'/verify'
        expired=send('POST',path,{**bodies[first['account_ref']],'request_key':'owned-expired-explicit-account-check'})
        assert server.runner.run_one();expired=send('GET',base+'/account-checks/'+expired['check_id'])
        assert expired['status']=='failed' and expired['failure_code']=='ANALYTICS_OAUTH_REFRESH_REQUIRED' and len(calls)==2
        expected[expired['check_id']]=expired;write(out/'expired-fixture-check.json',expired)
        server.official_accounts.clock=lambda:datetime.now(timezone.utc)
        interrupted=send('POST',path,{**bodies[first['account_ref']],'request_key':'owned-interrupted-explicit-account-check'})
        with server.store.transaction() as con:con.execute("UPDATE native_official_account_checks SET status='running',claim_id='EXPLICIT-RESTART-FIXTURE',attempts=1 WHERE check_id=?",(interrupted['check_id'],))
        server.official_accounts.recover();interrupted=send('GET',base+'/account-checks/'+interrupted['check_id']);assert interrupted['status']=='outcome_unknown'
        expected[interrupted['check_id']]=interrupted;write(out/'interrupted-fixture-check.json',interrupted)
        assert server.official_accounts.process() is None and len(calls)==2
        send('POST',path,{**bodies[first['account_ref']],'expected_configuration_sha256':'f'*64,'request_key':'owned-stale-config-explicit-account-check'},expected=409)
        send('GET',base+'/account-checks?cursor=not-a-valid-cursor',expected=400)
        page=send('GET',base+'/account-checks?limit=2');assert page['truncated'] and len(page['items'])==2
        next_page=send('GET',base+'/account-checks?limit=2&cursor='+page['next_cursor']);assert not next_page['truncated'] and len(next_page['items'])==2
        write(out/'paginated-history.json',[page,next_page])
        auth,cookie,session=access('viewer');auth.bind_root(root);server.access=auth
        send('GET',base+'/account-checks?limit=100');send('POST',path,bodies[first['account_ref']],expected=403);send('GET','/api/connections/official-accounts',expected=403)
        assert server.store.get(args.project_id)==original and media(root)==physical and len(calls)==2
        costs=server.official_accounts.costs.summary(args.project_id);assert len(costs['records'])==2 and all(r['actual_cost'] is None and not r['external_call'] and not r['paid'] for r in costs['records'])
        write(out/'cost.json',costs);write(out/'expected-checks.json',expected);write(out/'wire-fixtures.json',calls);write(out/'http-requests.json',requests)
    finally:server.shutdown();server.server_close();thread.join()
    backup=create_backup(settings(root),out/'owned-official-accounts.zip');write(out/'backup.json',backup)
    with zipfile.ZipFile(out/'owned-official-accounts.zip') as archive:
        assert all('explicit-fixture.dpapi' not in n and 'explicit-fixture-registry' not in n for n in archive.namelist())
    write(out/'recovery-restore.json',restore_backup(out/'owned-official-accounts.zip',restored,expected_sha256=backup['sha256']))
    args.data_root=restored;reopen(args)
    names=['services/windows_native/'+n for n in ('official_accounts.py','official_account_tokens.py','official_account_registry.py','official_account_routes.py','assemblyai_connection.py','server.py','access.py','backup.py')]
    names+=['services/windows_native/tests/'+n for n in ('test_official_accounts.py','test_official_account_registry.py','test_official_accounts_http.py','test_phase10_http.py')]
    names+=['apps/studio-web/'+n for n in ('native-official-accounts.mjs','native.mjs','native.html','tests/native-official-accounts.test.mjs')]+['scripts/north_star_native_official_accounts.py']
    write(out/'evidence.json',{'schema_version':'native-official-account-rehearsal-v1','explicit_account_token_wire_and_identity_fixtures':True,'actual_windows_dpapi':True,
        'signed_http_requests':len(requests),'fixture_account_requests':len(calls),'confirmed_account_checks':2,'expired_without_dispatch':True,'interrupted_without_resend':True,
        'default_disabled_no_token_or_network_read':True,'history_project_jobs_media_unchanged':True,'secrets_outside_source_state_and_backup':True,
        'actual_costs_unknown_null':True,'new_tts_render_or_paid_operations':0,'external_provider_calls':0,'real_account_verified':False,'publishing_enabled':False,'owner_uat_accepted':False,
        'source_sha256':{n:file_sha(ROOT/n) for n in names},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'NATIVE_OFFICIAL_ACCOUNT_RECOVERY_PASS','signed_http_requests':len(requests),'fixture_reads':2,'external_calls':0}))

def reopen(args):
    root,out=owned(args.data_root),args.output.resolve();secrets=owned(args.secret_root);calls=[];auth,_,_=access()
    server=LocalServer(0,settings(root),start_worker=False,access=auth,official_account_factories=factories(secrets/'explicit-fixture-registry.json',root,calls))
    try:
        expected=json.loads((out/'expected-checks.json').read_bytes())
        assert {identity:server.official_accounts.get(args.project_id,identity) for identity in expected}==expected
        assert server.store.get(args.project_id)==json.loads((out/'project-before.json').read_bytes())
        assert media(root)==json.loads((out/'physical-source-hashes.json').read_bytes())
        assert server.official_accounts.process() is None and calls==[]
        # Explicitly decrypt the synthetic tokens in the fresh process; still no wire request.
        assert all(f.credential().target==f.account.target for f in server.official_accounts.factories.values()) and calls==[]
        write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'exact_account_history_project_jobs_media':True,
            'new_account_or_media_jobs':0,'token_reads_explicit_fixture_only':2,'wire_requests':0,'publishing_enabled':False,'both_database_restore':True})
    finally:server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backup',type=Path);p.add_argument('--expected-sha256');p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--restore-root',type=Path);p.add_argument('--secret-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id',required=True)
    p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true');args=p.parse_args();reopen(args) if args.reopen else run(args)
