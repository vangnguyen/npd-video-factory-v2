"""Owned signed HTTP and UI rehearsal; provider/Owner/media are explicit mocks."""
import argparse,json,subprocess,sys,threading
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests.test_meta_runtime_http import MetaRuntimeHTTPTests,FacebookMetaRuntimeHTTPTests
from services.windows_native.meta_distribution import NativeMetaPublishingFactory
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_native_analytics_refresh import settings

ROOT=Path(r'C:\vfns01');LOG=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007')
def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def node_runtime(server,cookie,csrf,workspace,project,platform,**options):
    data={'origin':'http://127.0.0.1:'+str(server.server_port),'cookie':cookie,'csrf':csrf,'workspace_id':workspace,'project':project,'platform':platform,**options}
    result=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(ROOT/'scripts/north_star_meta_studio.mjs')],input=json.dumps(data),capture_output=True,text=True,encoding='utf-8',timeout=90,cwd=ROOT)
    if result.returncode:raise AssertionError(result.stderr)
    value=json.loads(result.stdout);assert value['status']=='PASS';raw=json.dumps(value);assert all(secret not in raw for secret in (cookie,csrf,'X-Amz-'))
    return value
def node(case,**options):
    value=node_runtime(case.server,case.cookie,case.csrf,case.workspace,case.server.store.get(case.c.project['id']),case.PLATFORM,**options)
    assert all(secret not in json.dumps(value) for secret in (case.raw,case.c.token));return value
def cold_check(data):
    from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
    from services.windows_native.access import NativeAccess
    from services.windows_native.server import LocalServer
    from services.windows_native.tests.test_phase10_http import NoProviderPipeline
    auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data['registry']),max_token_ttl_seconds=86400),data['workspace_id'])
    with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No cold private credential or lease read')):
        server=LocalServer(0,settings(Path(data['root'])),pipeline=NoProviderPipeline(),start_worker=False,access=auth,publishing_capabilities_file=Path(data['capabilities_file']))
        cookie,session=auth.login(data['raw_human_fixture']);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            value=node_runtime(server,cookie,session.csrf,data['workspace_id'],server.store.get(data['project_id']),data['platform'],read_only=True)
            assert value['publication']==data['publication'] and value['dispatch']==data['dispatch']
            assert server.official_publications.factories=={} and server.publishing_media.factory is None and not server.official_publish_queue.enabled and not server.runner.run_one()
            database=database_status(server.store.db);assert database['active_operations']==0 and database['counts']==data['database_counts']
            return {'status':'PASS','scope':'separate_process_default_off_keyless_Studio_controllers_actual_signed_HTTP_fake_DOM_history','ui':value,
                'private_keys_loaded':False,'provider_calls':0,'automatic_replay':False,'database_counts':database['counts']}
        finally:server.shutdown();server.server_close();thread.join()
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--restore-check',action='store_true');args=p.parse_args()
    if args.restore_check:print(json.dumps(cold_check(json.load(sys.stdin))));return
    if args.output is None:raise ValueError('Fresh output required')
    out=args.output.absolute()
    if out.parent!=LOG or not out.name.startswith('meta-studio-flow-n') or out.exists():raise ValueError('Fresh owned evidence output required')
    out.mkdir();summaries=[]
    for cls in [MetaRuntimeHTTPTests,FacebookMetaRuntimeHTTPTests]:
        case=cls('test_runtime_signed_review_separate_media_selection_and_async_receipt_use_one_worker');case.setUp();folder=out/case.PLATFORM;folder.mkdir()
        try:
            original=case.server.store.get(case.c.project['id']);value=node(case,queue=case.PLATFORM=='facebook');write(folder/'ui-initial.json',value)
            identity=value['publication']['publication_id'];plan=value['queue_plan']
            if plan is not None:
                case.c.clock[0]=datetime.fromisoformat(plan['policy']['request']['start_at']);case.server.official_publish_queue.clock=lambda:case.c.clock[0]
                for _ in range(8):
                    if case.server.official_publications.get(original['id'],identity)['receipt'] is not None:break
                    assert case.server.runner.run_one();case.c.clock[0]+=timedelta(seconds=31)
                value=node(case,read_only=True);write(folder/'ui-final-read.json',value)
                assert all(call['method']=='GET' for call in value['calls'])
            final=case.server.official_publications.get(original['id'],identity);state=case.server.official_publications.state(original['id'],identity)
            assert final['mock_publication_complete'] is True and final['published'] is False and final==value['publication'] and state==value['dispatch']
            assert case.server.store.get(original['id'])==original and case.pipeline.calls==0 and case.storage.puts==1
            with case.server.store.transaction() as con:costs=[dict(row) for row in con.execute('SELECT * FROM native_cost_operations')]
            assert not any(row['paid'] or row['external_call'] for row in costs)
            write(folder/'costs.json',costs);backup=create_backup(settings(case.root),folder/'public-state.zip');write(folder/'backup.json',backup)
            destination=case.folder/('meta-studio-restored-'+case.PLATFORM);restore=restore_backup(folder/'public-state.zip',destination,expected_sha256=backup['sha256'])
            payload={'root':str(destination),'workspace_id':case.workspace,'platform':case.PLATFORM,'project_id':original['id'],'publication':final,'dispatch':state,
                'registry':case.auth.verifier.registry.model_dump(mode='json'),'raw_human_fixture':case.raw,'capabilities_file':str(case.c.caps),'database_counts':database_status(case.server.store.db)['counts']}
            checked=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).absolute()),'--restore-check'],input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8',timeout=90,cwd=ROOT)
            if checked.returncode:raise AssertionError(checked.stderr)
            cold=json.loads(checked.stdout);assert cold['status']=='PASS';write(folder/'cold-ui-history.json',{'restore':restore,'verification':cold})
            summaries.append({'platform':case.PLATFORM,'ui_http_requests':len(json.loads((folder/'ui-initial.json').read_text(encoding='utf-8'))['calls'])+len(value['calls']) if plan is not None else len(value['calls']),
                'shared_queue':plan is not None,'one_storage_write':True,'nullable_cost_records':len(costs),'backup_sha256':backup['sha256'],'canonical_project_unchanged':True,'final_receipt_observed_by_ui':True,'separate_process_keyless_Studio_history':'PASS'})
        finally:case.tearDown()
    case=MetaRuntimeHTTPTests('test_runtime_signed_review_separate_media_selection_and_async_receipt_use_one_worker');case.setUp()
    try:
        legacy=NativeMetaPublishingFactory(case.c.connection,owner_enabled=True,gates=case.c.factory.gates)
        case.stop_server();case.meta=legacy;case.start_server(configured=True)
        original=list(case.c.calls);value=node(case,legacy=True);assert case.c.calls==original and case.storage.calls==[];write(out/'legacy-v1-ui.json',value)
    finally:case.tearDown()
    summary={'status':'PASS','platforms':summaries,'legacy_v1_UI_execution_disabled':True,'real_provider_calls':0,'paid_operations':0,'browser_rendered':False,'owner_uat':False,'accepted_media_generated':False,'main_merged':False,'production_deployed':False,'manual_old_data_deleted':False}
    write(out/'summary.json',summary);print(json.dumps({'status':'PASS','evidence':str(out),'platforms':2,'legacy':True}))
if __name__=='__main__':main()
