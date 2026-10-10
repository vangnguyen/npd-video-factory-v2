"""Retained actual loopback/DPAPI/SQLite rehearsal with explicit Meta/Owner mocks."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'apps/api'),str(ROOT)]
LOG=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007')


def cold_check(data):
    from services.windows_native.access import NativeAccess
    from services.windows_native.server import LocalServer
    from services.windows_native.tests.test_human_identity import fixture
    from services.windows_native.tests.test_phase10_http import NoProviderPipeline
    from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
    from scripts.north_star_native_official_analytics import settings
    raw,registry=fixture('owner');auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),'wsp_native_fixture')
    server=LocalServer(0,settings(Path(data['root'])),pipeline=NoProviderPipeline(),start_worker=False,access=auth)
    try:
        server.official_accounts.recover()
        actual=[server.official_accounts.get(data['project_id'],row['check_id']) for row in data['rows']]
        assert actual==data['rows'] and server.store.get(data['project_id'])==data['project']
        assert server.official_accounts.factories=={} and server.official_publications.factories=={} and not server.official_publish_queue.enabled
        assert server.official_accounts.process() is None and server.runner.pipeline.calls==0
        return {'status':'PASS','scope':'public_meta_account_history_restored_in_separate_default_off_keyless_local_server',
            'checks':len(actual),'observations':sum(len(x['result']['meta']['observations']) for x in actual),
            'project_unchanged':True,'private_credentials_loaded':False,'network_calls':0,'replay':False,'production_deployed':False}
    finally:server.server_close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--export-fixture',action='store_true');parser.add_argument('--restore-check',action='store_true');args=parser.parse_args()
    if args.restore_check:
        print(json.dumps(cold_check(json.load(sys.stdin))));return
    from services.windows_native.tests.test_meta_accounts_http import MetaAccountsHTTPTests
    from services.windows_native.backup import create_backup,restore_backup
    if args.output is None:raise ValueError('Fresh evidence path required')
    out=args.output.resolve()
    if out.parent!=LOG or not out.name.startswith('meta-account-flow-n') or out.exists():raise ValueError('Fresh owned output required')
    out.mkdir();case=MetaAccountsHTTPTests('test_signed_owner_intents_share_history_worker_costs_without_media_or_publication');case.setUp()
    try:
        before=case.server.store.get(case.project['id']);calls=[];rows=[];queued=[]
        def request(method,path,body=None):
            status,value,_=case.request(method,path,body);assert status==200,(path,status)
            calls.append({'method':method,'path':path,'status':status,'schema_version':value.get('schema_version')});return value
        states=request('GET','/api/connections/official-accounts')
        for account_ref in case.factories:
            payload=case.body(account_ref,request_key='explicit-retained-'+account_ref)
            pending=request('POST',case.url(account_ref),payload);assert pending['status']=='queued';queued.append(pending)
            result=case.server.official_accounts.process(project=case.project['id'],identity=pending['check_id'],fingerprint=pending['request_fingerprint'])
            assert result['status']=='succeeded'
            row=request('GET','/api/projects/'+case.project['id']+'/account-checks/'+pending['check_id']);assert row==result;rows.append(row)
            replay=request('POST',case.url(account_ref),payload);assert replay['idempotent_replay'] and replay['check_id']==row['check_id']
        history=request('GET','/api/projects/'+case.project['id']+'/account-checks?limit=25')
        assert {r['check_id'] for r in history['items']}=={r['check_id'] for r in rows}
        assert case.server.store.get(case.project['id'])==before and case.pipeline.calls==0 and len(case.calls)==3
        costs=case.server.official_accounts.costs.summary(case.project['id'])['records']
        assert len(costs)==3 and all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs)
        flow={'schema_version':'north-star-meta-account-flow-v1','status':'PASS','scope':'actual_owned_cookie_csrf_http_dpapi_sqlite_with_explicit_provider_owner_platform_mocks',
            'http_requests':calls,'provider_protocol_requests':[{'method':m,'path':p} for m,p in case.calls],
            'states':states,'queued':queued,'rows':rows,'costs':costs,'project':before,'project_unchanged':True,
            'genuine_provider_calls':0,'paid_operations':0,'permissions_provider_verified':False,'app_eligibility_verified':False,
            'browser_rendered':False,'owner_uat':False,'published':False,'production_deployed':False,'manual_data_deleted':False}
        text=json.dumps(flow,ensure_ascii=False,indent=2)
        assert all(secret not in text for secret in [case.mock_token,case.raw,case.cookie,case.csrf,*map(str,case.secret_paths)])
        with (out/'flow.json').open('x',encoding='utf8') as h:h.write(text+'\n')
        if args.export_fixture:
            path=ROOT/'apps/studio-web/tests/fixtures/native-meta-account-v1.json'
            with path.open('x',encoding='utf8') as h:json.dump({'schema_version':'native-meta-account-fixture-v1','explicit_mocks':True,
                'provider_owner_browser_acceptance':False,'workspace_id':case.auth.workspace_id,'project':before,'states':states,'queued':queued,'rows':rows},h,ensure_ascii=False,indent=2);h.write('\n')
        case.stop_server();backup=create_backup(case.config,out/'public-state.zip')
        with (out/'backup.json').open('x',encoding='utf8') as h:json.dump(backup,h,indent=2);h.write('\n')
        recovered=case.config.data_root.parent/'meta-recovered';assert not recovered.exists()
        restore=restore_backup(out/'public-state.zip',recovered,expected_sha256=backup['sha256'])
        data={'root':str(recovered),'project_id':before['id'],'project':before,'rows':rows}
        process=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--restore-check'],input=json.dumps(data),capture_output=True,text=True,encoding='utf8',timeout=60,cwd=ROOT)
        if process.returncode:raise AssertionError(process.stderr)
        result=json.loads(process.stdout);assert result['status']=='PASS'
        with (out/'cold-recovery.json').open('x',encoding='utf8') as h:json.dump({'restore':restore,**result},h,indent=2);h.write('\n')
        print(json.dumps({'status':'PASS','http_requests':len(calls),'protocol_requests':len(case.calls),'costs':len(costs),
            'cold_restore':result,'backup_sha256':backup['sha256'],'evidence':str(out)},ensure_ascii=False))
    finally:
        if case.thread.is_alive():case.stop_server()
        case.live_ai.stop();case.temp.cleanup()


if __name__=='__main__':main()
