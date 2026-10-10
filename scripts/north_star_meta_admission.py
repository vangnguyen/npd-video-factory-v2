"""Retain scoped Meta admission/cold recovery; every provider/Owner/media result is mocked."""
import argparse, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'apps/api'),str(ROOT)]
LOG=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007')


def write(path,value):
    with path.open('x',encoding='utf8') as h:json.dump(value,h,ensure_ascii=False,indent=2);h.write('\n')


def cold_check(data):
    from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
    from services.windows_native.access import NativeAccess
    from services.windows_native.server import LocalServer
    from services.windows_native.tests.test_phase10_http import NoProviderPipeline
    from services.windows_native.tests.test_human_identity import fixture
    from scripts.north_star_native_analytics_refresh import settings
    _,registry=fixture('owner',workspace=data['workspace_id']);auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),data['workspace_id'])
    server=LocalServer(0,settings(Path(data['root'])),pipeline=NoProviderPipeline(),start_worker=False,access=auth,publishing_capabilities_file=Path(data['capabilities_file']))
    try:
        actual=server.official_publications.page(data['project']['id'])
        assert actual==data['history'] and server.store.get(data['project']['id'])==data['project']
        assert server.official_accounts.factories=={} and server.official_publications.factories=={} and not server.official_publish_queue.enabled
        assert server.official_accounts.process() is None and server.official_publish_queue.process() is None and server.runner.pipeline.calls==0
        return {'status':'PASS','scope':'separate_default_off_keyless_local_server_meta_admission_history',
            'publication_count':len(actual['items']),'project_unchanged':True,'private_credentials_loaded':False,'provider_calls':0,'replay':False,
            'published':False,'production_deployed':False}
    finally:server.server_close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--restore-check',action='store_true');args=parser.parse_args()
    if args.restore_check:print(json.dumps(cold_check(json.load(sys.stdin))));return
    from services.windows_native.tests import test_meta_distribution_http as fixture
    from services.windows_native.backup import create_backup, restore_backup
    if args.output is None:raise ValueError('Fresh owned evidence path required')
    out=args.output.resolve()
    if out.parent!=LOG or not out.name.startswith('meta-admission-flow-n') or out.exists():raise ValueError('Fresh owned evidence path required')
    out.mkdir();platforms=[]
    for kind in (fixture.FacebookAdmissionHTTPTests,fixture.MetaAdmissionHTTPTests):
        case=kind('test_existing_signed_review_approval_status_is_inert_and_cannot_send');case.setUp();stopped=False
        try:
            calls=[];before=case.server.store.get(case.c.project['id'])
            def request(method,path,body=None,expected=200):
                status,value,_=case.request(method,path,body);assert status==expected,(path,status)
                calls.append({'method':method,'path':path,'status':status,'schema_version':value.get('schema_version'),'code':value.get('code')});return value
            states=request('GET','/api/connections/official-publishing')
            value=request('POST',case.base,case.c.body().model_dump(mode='json'));identity=value['publication_id'];path=case.base+'/'+identity
            approved=request('POST',path+'/approve',{'expected_snapshot_sha256':value['snapshot_sha256'],'acknowledged_official_publication':True})
            state=request('GET',path+'/state');assert state['dispatch']['phase']=='prepared' and approved['status']=='queued'
            blocked=request('POST',path+'/step',{'expected_snapshot_sha256':value['snapshot_sha256'],'expected_dispatch_version':1},expected=409)
            assert blocked['code']=='NATIVE_OFFICIAL_PUBLISH_EXECUTION_NOT_IMPLEMENTED'
            replay=request('POST',case.base,case.c.body().model_dump(mode='json'));assert replay['idempotent_replay']
            cancelled=request('POST',path+'/cancel',{'expected_snapshot_sha256':value['snapshot_sha256']});assert cancelled['status']=='cancelled'
            history=request('GET',case.base);assert len(history['items'])==1 and history['items'][0]==cancelled
            costs=case.server.official_accounts.costs.summary(before['id'])['records']
            assert case.server.store.get(before['id'])==before and len(costs)==(1 if case.PLATFORM=='facebook' else 2)
            assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs)
            flow={'schema_version':'north-star-meta-admission-flow-v1','status':'PASS','platform':case.PLATFORM,
                'scope':'existing_signed_loopback_api_dpapi_sqlite_explicitly_bound_inert_meta_factory_with_owner_platform_provider_nonplayable_media_mocks',
                'http_requests':calls,'states':states,'initial':value,'approved':approved,'prepared':state,'cancelled':cancelled,'history':history,'costs':costs,
                'provider_protocol_requests':[{'method':m,'path':p} for m,p in case.c.calls],
                'current_project_unchanged':True,'genuine_provider_calls':0,'paid_operations':0,'meta_publish_dispatch_implemented':False,
                'native_startup_registry_wired':False,'studio_meta_publication_wired':False,'browser_rendered':False,'owner_uat':False,'published':False,'production_deployed':False}
            text=json.dumps(flow,ensure_ascii=False)
            assert all(secret not in text for secret in (case.c.token,case.raw,case.cookie,case.csrf,str(case.c.path)))
            write(out/(case.PLATFORM+'-flow.json'),flow)
            caps=out/(case.PLATFORM+'-fixture-capabilities.json')
            with caps.open('xb') as h:h.write(case.c.caps.read_bytes())
            case.stop_server();stopped=True
            backup=create_backup(case.config,out/(case.PLATFORM+'-public-state.zip'));write(out/(case.PLATFORM+'-backup.json'),backup)
            recovered=case.folder/'meta-admission-restored';assert not recovered.exists()
            restore=restore_backup(Path(backup['backup_path']),recovered,expected_sha256=backup['sha256'])
            data={'root':str(recovered),'workspace_id':case.workspace,'project':before,'history':history,'capabilities_file':str(caps)}
            process=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--restore-check'],input=json.dumps(data),
                capture_output=True,text=True,encoding='utf8',timeout=60,cwd=ROOT)
            if process.returncode:raise AssertionError(process.stderr)
            result=json.loads(process.stdout);assert result['status']=='PASS';write(out/(case.PLATFORM+'-cold-recovery.json'),{'restore':restore,**result})
            platforms.append({'platform':case.PLATFORM,'http_requests':len(calls),'protocol_reads':len(case.c.calls),'costs':len(costs),'backup_sha256':backup['sha256'],'cold_restore':'PASS'})
        finally:
            if not stopped:case.stop_server()
            case.c.tearDown()
    write(out/'summary.json',{'status':'PASS','platforms':platforms,'published':False,'real_provider_calls':0,'paid_operations':0,'manual_data_deleted':False})
    print(json.dumps({'status':'PASS','platforms':platforms,'evidence':str(out)}))


if __name__=='__main__':main()
