"""Two explicit signed read checks on a recovered genuine media/fixture-account bundle."""
import argparse,http.client,json,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_accounts import owned,factories,media
from scripts.north_star_native_analytics_refresh import access,settings,write
from services.windows_native.server import LocalServer
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha

def run(args):
    root,restored=owned(args.data_root,fresh=True),owned(args.restore_root,fresh=True);out=args.output.resolve();secrets=owned(args.secret_root)
    if root==restored or out.exists() or out==ROOT or ROOT in out.parents or any(p==out or p in out.parents for p in (root,restored,secrets)):raise ValueError('Separate fresh owned recheck roots and evidence required')
    out.mkdir(parents=True);write(out/'initial-restore.json',restore_backup(args.backup,root,expected_sha256=args.expected_sha256))
    calls=[];auth,cookie,session=access();server=LocalServer(0,settings(root),start_worker=False,access=auth,official_account_factories=factories(secrets/'explicit-fixture-registry.json',root,calls))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[];base='/api/projects/'+args.project_id
    def send(method,path,body=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        conn.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=conn.getresponse();value=json.loads(response.read());conn.close();requests.append({'method':method,'path':path,'status':response.status});assert response.status==200,(response.status,value);return value
    try:
        project=server.store.get(args.project_id);physical=media(root);before=send('GET',base+'/account-checks?limit=100');prior_cost=server.official_accounts.costs.summary(args.project_id)['records']
        states=send('GET','/api/connections/official-accounts');account=next(a for a in states['accounts'] if a['target']['platform']=='youtube');results=[]
        for index in range(2):
            body={'revision':project['revision'],'expected_configuration_sha256':account['configuration_sha256'],'acknowledged_read_only':True,'request_key':'owned-explicit-fresh-youtube-recheck-'+str(index)}
            path=base+'/official-accounts/'+account['account_ref']+'/verify';queued=send('POST',path,body);assert queued['status']=='queued';assert server.runner.run_one()
            result=send('GET',base+'/account-checks/'+queued['check_id']);assert result['status']=='succeeded' and result['result']['mock'] and not result['result']['external_call']
            replay=send('POST',path,body);assert replay['idempotent_replay'] and replay['check_id']==result['check_id'];assert not server.runner.run_one();assert len(calls)==index+1;results.append(result)
        after=send('GET',base+'/account-checks?limit=100');costs=server.official_accounts.costs.summary(args.project_id)['records'];old={r['id']:r for r in prior_cost};current={r['id']:r for r in costs}
        assert all(current[k]==v for k,v in old.items()) and len(current)==len(old)+2
        assert len({r['result']['cost_operation_id'] for r in results})==2
        new=[r for r in costs if r['id'] not in old];assert {r['operation'] for r in new}=={'account_lookup.'+r['check_id'] for r in results}
        assert all(r['actual_cost'] is None and r['estimated_cost'] is None and not r['external_call'] and not r['paid'] for r in new)
        previous={r['check_id']:r for r in before['items']};history={r['check_id']:r for r in after['items']};assert all(history[k]==v for k,v in previous.items()) and len(history)==len(previous)+2
        assert server.store.get(args.project_id)==project and media(root)==physical
        write(out/'expected-history.json',after);write(out/'expected-costs.json',costs);write(out/'project-expected.json',project);write(out/'physical-source-hashes.json',physical)
        write(out/'fresh-checks.json',results);write(out/'prior-costs.json',prior_cost);write(out/'wire-fixtures.json',calls);write(out/'http-requests.json',requests)
    finally:server.shutdown();server.server_close();thread.join()
    backup=create_backup(settings(root),out/'owned-official-account-rechecks.zip');write(out/'backup.json',backup)
    write(out/'recovery-restore.json',restore_backup(out/'owned-official-account-rechecks.zip',restored,expected_sha256=backup['sha256']));args.data_root=restored;reopen(args)
    names=['services/windows_native/official_accounts.py','services/windows_native/tests/test_official_accounts.py','services/windows_native/tests/test_official_accounts_http.py','scripts/north_star_native_official_account_rechecks.py']
    write(out/'evidence.json',{'schema_version':'native-official-account-rechecks-v1','signed_http_requests':len(requests),'fresh_youtube_checks':2,'fixture_account_reads':len(calls),
        'distinct_cost_intents':2,'exact_retries_without_new_read_or_cost':True,'prior_cost_and_account_history_unchanged':True,'actual_costs_unknown_null':True,
        'prior_project_jobs_media_unchanged':True,'prior_media_artifacts':len(physical),'both_database_restore':True,'actual_dpapi_fixture_tokens_reused':True,
        'token_account_wire_identity_are_explicit_fixtures':True,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'owner_uat_accepted':False,
        'source_sha256':{name:file_sha(ROOT/name) for name in names},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'NATIVE_OFFICIAL_ACCOUNT_RECHECKS_PASS','signed_http_requests':len(requests),'fixture_reads':2,'distinct_costs':2,'external_calls':0}))

def reopen(args):
    root,out=owned(args.data_root),args.output.resolve();auth,_,_=access();server=LocalServer(0,settings(root),start_worker=False,access=auth)
    try:
        assert server.official_accounts.page(args.project_id,limit=100)==json.loads((out/'expected-history.json').read_bytes())
        assert server.official_accounts.costs.summary(args.project_id)['records']==json.loads((out/'expected-costs.json').read_bytes())
        assert server.store.get(args.project_id)==json.loads((out/'project-expected.json').read_bytes());physical=json.loads((out/'physical-source-hashes.json').read_bytes());assert media(root)==physical
        assert server.official_accounts.process() is None
        write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'exact_account_cost_history_project_jobs_media':True,'credentials_configured':False,'new_reads_or_costs':0,'publishing_enabled':False})
    finally:server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backup',type=Path);p.add_argument('--expected-sha256');p.add_argument('--data-root',type=Path,required=True);p.add_argument('--restore-root',type=Path)
    p.add_argument('--secret-root',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id',required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
