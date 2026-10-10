"""Retained async Meta evidence: actual local journals/DPAPI, explicit wire mocks."""
import argparse,json,subprocess,sys,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'apps/api'),str(ROOT)]
LOG=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007')


def write(path,value):
    with path.open('x',encoding='utf8') as handle:json.dump(value,handle,ensure_ascii=False,indent=2);handle.write('\n')


def cold_check(data):
    from services.windows_native.store import Store
    from services.windows_native.publications import NativePublications
    from services.windows_native.official_accounts import NativeOfficialAccounts
    from services.windows_native.official_publications import NativeOfficialPublications
    from services.windows_native.publishing_media_delivery import NativePublishingMediaDelivery
    from services.windows_native import meta_publishing
    from services.windows_native.backup import database_status
    store=Store(Path(data['root']));accounts=NativeOfficialAccounts(store,workspace_id=data['workspace_id'])
    reviews=NativePublications(store,Path(data['capabilities_file']),workspace_id=data['workspace_id'])
    journal=NativeOfficialPublications(store,reviews,accounts);media=NativePublishingMediaDelivery(journal)
    with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No recovery credential/lease decrypt')):
        assert journal.page(data['project']['id'])==data['publication_history']
        assert media.get(data['project']['id'],data['delivery_id'])==data['media_history']
        assert journal.state(data['project']['id'],data['publication_id'])==data['final_state']
        assert store.get(data['project']['id'])==data['project'] and media.costs.summary(data['project']['id'])==data['costs']
        assert meta_publishing.recover(journal,media.costs)==0
        database=database_status(store.db);assert database['active_operations']==0 and database['counts']==data['database_counts']
        assert journal.states()['profiles']==[] and accounts.factories=={} and media.factory is None
    return {'status':'PASS','scope':'separate_process_default_off_keyless_original_meta_job_receipt_media_cost_and_project_history',
        'private_files_loaded':False,'provider_calls':0,'replay':False,'published':False,'database_counts':database['counts']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--restore-check',action='store_true');args=parser.parse_args()
    if args.restore_check:print(json.dumps(cold_check(json.load(sys.stdin))));return
    from services.windows_native.tests.test_meta_publish_worker import MetaPublishWorkerTests,FacebookMetaPublishWorkerTests
    from services.windows_native.backup import create_backup,restore_backup,database_status
    from scripts.north_star_native_analytics_refresh import settings
    if args.output is None:raise ValueError('Fresh owned evidence path required')
    out=args.output.resolve()
    if out.parent!=LOG or not out.name.startswith('meta-execution-flow-n') or out.exists():raise ValueError('Fresh owned evidence path required')
    out.mkdir();summaries=[]
    for kind in (MetaPublishWorkerTests,FacebookMetaPublishWorkerTests):
        case=kind('test_exact_original_video_one_async_job_phase_order_nullable_costs_and_private_history');case.setUp()
        try:
            folder=out/case.PLATFORM;folder.mkdir();before=case.c.store.get(case.c.project['id']);steps=[]
            for _ in range(8):
                state=case.step();steps.append(state)
                if state['receipt'] is not None:break
            assert state['mock_publication_complete'] is True and state['published'] is False
            assert state['provider_job']['provider_job_id']=='34567' and len(case.c.mutations)==(3 if case.PLATFORM=='facebook' else 2)
            assert case.c.store.get(before['id'])==before and case.storage.puts==1
            costs=case.worker.costs.summary(before['id']);platform_costs=[r for r in costs['records'] if r['provider']=='official-'+case.PLATFORM]
            assert platform_costs and all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in platform_costs)
            publication_history=case.service.page(before['id']);media_history=case.media.get(before['id'],case.delivery['delivery_id'])
            database=database_status(case.c.store.db);assert database['active_operations']==0
            flow={'schema_version':'north-star-native-meta-execution-flow-v1','status':'PASS','platform':case.PLATFORM,
                'scope':'direct_worker_real_local_dpapi_sqlite_with_explicit_provider_storage_owner_platform_and_nonplayable_media_fixtures',
                'steps':steps,'publication_history':publication_history,'media_history':media_history,'costs':costs,
                'protocol_calls':[{'method':method,'path':path} for method,path in case.c.calls],
                'one_provider_job':True,'one_storage_write':True,'canonical_project_unchanged':True,'private_url_returned':False,
                'native_http_cli_studio_wired':False,'real_provider_calls':0,'paid_operations':0,'published':False,
                'browser_rendered':False,'owner_uat':False,'accepted_media_generated':False,'production_deployed':False}
            serialized=json.dumps(flow,ensure_ascii=False)
            assert all(secret not in serialized for secret in ('X-Amz-',case.c.token,str(case.media_factory.directory)))
            write(folder/'flow.json',flow);caps=folder/'fixture-capabilities.json'
            with caps.open('xb') as handle:handle.write(case.c.caps.read_bytes())
            backup=create_backup(settings(case.c.root),folder/'public-state.zip');write(folder/'backup.json',backup)
            with zipfile.ZipFile(folder/'public-state.zip') as archive:
                assert all(not name.endswith('.dpapi') for name in archive.namelist())
                assert all(b'X-Amz-' not in archive.read(name) for name in archive.namelist() if not name.endswith('/'))
            restored=case.c.folder/('meta-restored-'+case.PLATFORM);restore=restore_backup(folder/'public-state.zip',restored,expected_sha256=backup['sha256'])
            data={'root':str(restored),'workspace_id':case.c.workspace,'project':before,'publication_history':publication_history,
                'media_history':media_history,'delivery_id':case.delivery['delivery_id'],'publication_id':case.publication['publication_id'],
                'final_state':state,'costs':costs,'database_counts':database['counts'],'capabilities_file':str(caps)}
            process=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--restore-check'],input=json.dumps(data),
                capture_output=True,text=True,encoding='utf8',timeout=60,cwd=ROOT)
            if process.returncode:raise AssertionError(process.stderr)
            cold=json.loads(process.stdout);assert cold['status']=='PASS';write(folder/'cold-recovery.json',{'restore':restore,**cold})
            summaries.append({'platform':case.PLATFORM,'worker_steps':len(steps),'meta_operations':len(platform_costs),'meta_nullable_cost_records':len(platform_costs),
                'mutations':len(case.c.mutations),'storage_writes':case.storage.puts,'provider_job_id':state['provider_job']['provider_job_id'],
                'mock_remote_post_id':state['receipt']['remote_post_id'],'backup_sha256':backup['sha256'],'keyless_cold_recovery':'PASS'})
        finally:case.tearDown()
    summary={'status':'PASS','scope':'two_direct_component_meta_protocol_mocks_with_two_separate_process_local_restores','platforms':summaries,
        'real_provider_calls':0,'paid_operations':0,'published':False,'production_deployed':False,'manual_old_data_deleted':False,
        'native_http_cli_studio_wired':False,'browser_rendered':False,'owner_uat':False,'full_north_star_acceptance':False}
    write(out/'summary.json',summary);print(json.dumps({'status':'PASS','evidence':str(out),'platforms':len(summaries)}))


if __name__=='__main__':main()
