"""Retained actual loopback Meta/media runtime with explicit provider/Owner mocks."""
import argparse,json,subprocess,sys,threading,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'apps/api'),str(ROOT)]
LOG=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007')


def write(path,value):
    with path.open('x',encoding='utf8') as handle:json.dump(value,handle,ensure_ascii=False,indent=2);handle.write('\n')


def cold_check(data):
    from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
    from services.windows_native.access import NativeAccess
    from services.windows_native.server import LocalServer
    from services.windows_native.tests.test_phase10_http import NoProviderPipeline
    from services.windows_native.tests.test_access_http import NativeAccessHTTPTests
    from services.windows_native.backup import database_status
    from scripts.north_star_native_analytics_refresh import settings
    from types import SimpleNamespace
    config=settings(Path(data['root']));auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data['registry']),max_token_ttl_seconds=86400),data['workspace_id'])
    with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No cold private key/lease decrypt')):
        server=LocalServer(0,config,pipeline=NoProviderPipeline(),start_worker=False,access=auth,publishing_capabilities_file=Path(data['capabilities_file']))
        cookie,session=auth.login(data['raw_human_fixture']);client=SimpleNamespace(server=server,cookie=cookie,csrf=session.csrf)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for path,expected in data['history'].items():
                status,actual,_=NativeAccessHTTPTests.request(client,'GET',path)
                assert status==200 and actual==expected,path
            assert server.official_publications.factories=={} and server.publishing_media.factory is None
            assert not server.official_publish_queue.enabled and server.runner.run_one() is False
            database=database_status(server.store.db);assert database['active_operations']==0 and database['counts']==data['database_counts']
        finally:server.shutdown();server.server_close();thread.join()
    return {'status':'PASS','scope':'separate_process_default_off_actual_signed_http_original_meta_media_cost_project_history',
        'http_reads':len(data['history']),'private_keys_loaded':False,'provider_calls':0,'automatic_replay':False,'published':False,'database_counts':database['counts']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--restore-check',action='store_true');args=parser.parse_args()
    if args.restore_check:print(json.dumps(cold_check(json.load(sys.stdin))));return
    from services.windows_native.tests.test_meta_runtime_http import MetaRuntimeHTTPTests,FacebookMetaRuntimeHTTPTests
    from services.windows_native.backup import create_backup,restore_backup,database_status
    from scripts.north_star_native_analytics_refresh import settings
    if args.output is None:raise ValueError('Fresh owned evidence directory required')
    out=args.output.resolve()
    if out.parent!=LOG or not out.name.startswith('meta-runtime-flow-n') or out.exists():raise ValueError('Fresh owned evidence directory required')
    out.mkdir();summaries=[]
    for kind in (MetaRuntimeHTTPTests,FacebookMetaRuntimeHTTPTests):
        case=kind('test_runtime_signed_review_separate_media_selection_and_async_receipt_use_one_worker');case.setUp()
        try:
            folder=out/case.PLATFORM;folder.mkdir();samples=[];request=case.request
            def record(method,path,body=None,**kwargs):
                result=request(method,path,body,**kwargs);samples.append({'method':method,'path':path,'status':result[0],'response':result[1]});return result
            case.request=record;project=case.server.store.get(case.c.project['id'])
            runtime=case.request('GET','/api/connections/official-publishing')[1];media_runtime=case.request('GET','/api/connections/publishing-media')[1]
            dry_page=case.request('GET','/api/projects/'+project['id']+'/publications?limit=25')[1]
            account_page=case.request('GET','/api/projects/'+project['id']+'/account-checks?limit=25')[1]
            case.review();media=case.deliver();binding=case.bind(media);stages=[]
            for _ in range(8):
                state=case.step();publication=case.request('GET',case.path)[1];stages.append({'publication':publication,'dispatch':state})
                if state['receipt'] is not None:break
            assert state['published'] is False and state['mock_publication_complete'] is True
            assert case.server.store.get(project['id'])==project and case.storage.puts==1
            history={case.base:case.request('GET',case.base)[1],case.path+'/media-deliveries':case.request('GET',case.path+'/media-deliveries')[1],
                case.path+'/state':case.request('GET',case.path+'/state')[1]}
            costs=case.server.official_publish_worker.costs.summary(project['id']);database=database_status(case.server.store.db)
            assert database['active_operations']==0 and all(r['actual_cost'] is None and not r['external_call'] for r in costs['records'])
            value={'schema_version':'north-star-native-meta-runtime-flow-v1','status':'PASS','platform':case.PLATFORM,
                'scope':'actual_signed_loopback_runtime_http_with_explicit_meta_s3_owner_platform_nonplayable_media_fixtures',
                'project':project,'runtime':runtime,'media_runtime':media_runtime,'dry_run_page':dry_page,'account_page':account_page,
                'media':media,'binding':binding,'stages':stages,'history':history,'costs':costs,'http_samples':samples,
                'native_runtime_cli_http_connected':True,'studio_connected':False,'one_provider_job':True,'one_storage_write':True,
                'canonical_project_unchanged':True,'real_provider_calls':0,'paid_operations':0,'published':False,'browser_rendered':False,
                'owner_uat':False,'accepted_media_generated':False,'production_deployed':False}
            serialized=json.dumps(value,ensure_ascii=False)
            assert all(secret not in serialized for secret in ('X-Amz-',case.c.token,case.raw,case.cookie,str(case.media.directory)))
            write(folder/'flow.json',value);caps=folder/'fixture-capabilities.json'
            with caps.open('xb') as handle:handle.write(case.c.caps.read_bytes())
            backup=create_backup(settings(case.root),folder/'public-state.zip');write(folder/'backup.json',backup)
            with zipfile.ZipFile(folder/'public-state.zip') as archive:
                assert all(not name.endswith('.dpapi') for name in archive.namelist())
                assert all(b'X-Amz-' not in archive.read(name) for name in archive.namelist() if not name.endswith('/'))
            restored=case.folder/('meta-runtime-restored-'+case.PLATFORM);restore=restore_backup(folder/'public-state.zip',restored,expected_sha256=backup['sha256'])
            payload={'root':str(restored),'workspace_id':case.workspace,'registry':case.auth.verifier.registry.model_dump(mode='json'),'raw_human_fixture':case.raw,
                'capabilities_file':str(caps),'history':history,'database_counts':database['counts']}
            process=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--restore-check'],input=json.dumps(payload),
                capture_output=True,text=True,encoding='utf8',timeout=60,cwd=ROOT)
            if process.returncode:raise AssertionError(process.stderr)
            cold=json.loads(process.stdout);assert cold['status']=='PASS';write(folder/'cold-recovery.json',{'restore':restore,**cold})
            summaries.append({'platform':case.PLATFORM,'http_requests':len(samples),'worker_steps':len(stages),'mutations':len(case.c.mutations),
                'storage_writes':case.storage.puts,'cost_records':len(costs['records']),'backup_sha256':backup['sha256'],'keyless_signed_http_restore':'PASS'})
        finally:case.tearDown()
    summary={'status':'PASS','platforms':summaries,'scope':'two_actual_local_signed_http_runtime_flows_and_two_separate_process_keyless_http_restores',
        'real_provider_calls':0,'paid_operations':0,'studio_connected':False,'browser_rendered':False,'owner_uat':False,'full_north_star_acceptance':False,
        'published':False,'production_deployed':False,'manual_old_data_deleted':False}
    write(out/'summary.json',summary);print(json.dumps({'status':'PASS','evidence':str(out),'platforms':len(summaries)}))


if __name__=='__main__':main()
