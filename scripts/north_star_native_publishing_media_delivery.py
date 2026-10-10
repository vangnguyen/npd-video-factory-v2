"""Retained media delivery/recovery: real local DPAPI/SQLite, explicit protocol mocks."""
import argparse,json,subprocess,sys,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'apps/api'),str(ROOT)]
LOG=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007')


def write(path,value):
    with path.open('x',encoding='utf8') as h:json.dump(value,h,ensure_ascii=False,indent=2);h.write('\n')


def cold_check(data):
    from services.windows_native.store import Store
    from services.windows_native.publications import NativePublications
    from services.windows_native.official_accounts import NativeOfficialAccounts
    from services.windows_native.official_publications import NativeOfficialPublications
    from services.windows_native.publishing_media_delivery import NativePublishingMediaDelivery
    from services.windows_native.backup import database_status
    store=Store(Path(data['root']));accounts=NativeOfficialAccounts(store,workspace_id=data['workspace_id'])
    reviews=NativePublications(store,Path(data['capabilities_file']),workspace_id=data['workspace_id'])
    journal=NativeOfficialPublications(store,reviews,accounts);media=NativePublishingMediaDelivery(journal)
    with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No cold private decrypt')):
        assert media.recover()==0
        actual=[media.get(data['project']['id'],v['delivery_id']) for v in data['history']]
        assert actual==data['history'] and store.get(data['project']['id'])==data['project']
        assert journal.page(data['project']['id'])==data['publication_history'] and media.costs.summary(data['project']['id'])==data['costs']
        database=database_status(store.db);assert database['active_operations']==0 and database['counts']==data['database_counts']
    assert media.factory is None and accounts.factories=={} and journal.factories=={}
    return {'status':'PASS','scope':'separate_process_default_off_keyless_native_media_journal_and_original_publication_history',
        'delivery_count':len(actual),'database_counts':database['counts'],'current_project_unchanged':True,
        'private_files_loaded':False,'provider_calls':0,'replay':False,'published':False,'production_deployed':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--restore-check',action='store_true');args=parser.parse_args()
    if args.restore_check:print(json.dumps(cold_check(json.load(sys.stdin))));return
    from services.windows_native.tests import test_publishing_media_delivery as fixture
    from services.windows_native.official_publication_models import Action
    from services.windows_native.backup import create_backup,restore_backup,database_status
    from services.windows_native.contracts import WorkflowError
    from scripts.north_star_native_analytics_refresh import settings
    if args.output is None:raise ValueError('Fresh owned evidence path required')
    out=args.output.resolve()
    if out.parent!=LOG or not out.name.startswith('publishing-media-flow-n') or out.exists():raise ValueError('Fresh owned evidence path required')
    out.mkdir();case=fixture.NativeMediaDeliveryTests('test_exact_approved_final_is_readback_verified_private_and_every_wire_has_nullable_cost');case.setUp()
    try:
        before=case.c.store.get(case.c.project['id']);factory=case.factory.public();initial=case.create()
        case.storage.lose_reply=True;unknown=case.process(initial)
        assert unknown['status']=='outcome_unknown' and case.storage.puts==1
        calls=list(case.storage.calls)
        try:case.process(initial)
        except WorkflowError as error:assert error.code=='NATIVE_MEDIA_DELIVERY_NO_AUTOMATIC_REPLAY'
        else:raise AssertionError('No automatic replay allowed')
        assert case.storage.calls==calls
        case.storage.lose_reply=False;recovery_body=case.body(reconcile_delivery_id=unknown['delivery_id'],request_key='retained-explicit-read-only-media-recovery')
        recovered=case.process(case.create(recovery_body));assert recovered['status']=='succeeded' and case.storage.puts==1
        assert all(v['operation']!='put_object' for v in recovered['operations'])
        replay,exact=case.service.create(before['id'],recovery_body,principal=case.c.principal);assert exact and replay==recovered
        calls=list(case.storage.calls)
        private=case.service.resolve_for_consumer(before['id'],recovered['delivery_id'],publication_snapshot_sha256=case.publication['snapshot_sha256'],consumer_mock=True)
        assert private.object.scope.final_sha256==case.publication['snapshot']['final_sha256'] and case.storage.calls==calls
        case.c.service.cancel(before['id'],case.publication['publication_id'],Action(expected_snapshot_sha256=case.publication['snapshot_sha256']),principal=case.c.principal)
        try:case.service.resolve_for_consumer(before['id'],recovered['delivery_id'],publication_snapshot_sha256=case.publication['snapshot_sha256'],consumer_mock=True)
        except WorkflowError:pass
        else:raise AssertionError('Revoked publication grant cannot resolve media URL')
        history=[case.service.get(before['id'],v['delivery_id']) for v in (unknown,recovered)]
        assert history==[unknown,recovered] and case.c.store.get(before['id'])==before
        costs=case.service.costs.summary(before['id']);records=[r for r in costs['records'] if r['provider']=='s3-publishing-media']
        assert len(records)==6 and all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in records)
        publication_history=case.c.service.page(before['id']);database=database_status(case.c.store.db)
        assert database['active_operations']==0
        flow={'schema_version':'north-star-native-publishing-media-delivery-flow-v1','status':'PASS','factory':factory,
            'scope':'direct_component_dpapi_sqlite_and_actual_local_byte_reads_with_explicit_s3_meta_owner_platform_nonplayable_media_fixtures',
            'initial':initial,'unknown':unknown,'recovered':recovered,'history':history,'publication_history':publication_history,'costs':costs,
            'storage_protocol_operations':[{'operation':op,'object_key':key} for op,key in case.storage.calls],
            'writes':case.storage.puts,'readonly_reconciliation':True,'same_request_exact_replay':True,'private_consumer_locally_verified':True,
            'private_url_returned':False,'current_owner_revoke_blocks_consumer':True,'canonical_project_unchanged':True,
            'native_http_cli_studio_wired':False,'meta_executor_implemented':False,'real_provider_calls':0,'paid_operations':0,
            'browser_rendered':False,'owner_uat':False,'publishing_authority':False,'published':False,'production_deployed':False}
        serialized=json.dumps(flow,ensure_ascii=False)
        assert all(secret not in serialized for secret in ('X-Amz-',case.c.token,str(case.directory)))
        write(out/'flow.json',flow);caps=out/'fixture-capabilities.json'
        with caps.open('xb') as h:h.write(case.c.caps.read_bytes())
        backup=create_backup(settings(case.c.root),out/'public-state.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'public-state.zip') as archive:
            assert all(not n.endswith('.dpapi') for n in archive.namelist())
            assert all(b'X-Amz-' not in archive.read(n) for n in archive.namelist() if not n.endswith('/'))
        restored=case.c.folder/'media-delivery-restored';restore=restore_backup(out/'public-state.zip',restored,expected_sha256=backup['sha256'])
        data={'root':str(restored),'workspace_id':case.c.workspace,'project':before,'history':history,'publication_history':publication_history,
            'costs':costs,'database_counts':database['counts'],'capabilities_file':str(caps)}
        process=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--restore-check'],input=json.dumps(data),
            capture_output=True,text=True,encoding='utf8',timeout=60,cwd=ROOT)
        if process.returncode:raise AssertionError(process.stderr)
        cold=json.loads(process.stdout);assert cold['status']=='PASS';write(out/'cold-recovery.json',{'restore':restore,**cold})
        summary={'status':'PASS','delivery_requests':2,'storage_protocol_operations':len(case.storage.calls),'conditional_puts':case.storage.puts,
            'storage_nullable_cost_records':len(records),'database_journal_counts':database['counts'],'backup_sha256':backup['sha256'],
            'separate_default_off_recovery':'PASS','private_url_in_public_backup':False,'real_provider_calls':0,'paid_operations':0,
            'published':False,'production_deployed':False,'manual_old_data_deleted':False}
        write(out/'summary.json',summary);print(json.dumps({'status':'PASS','evidence':str(out),'storage_operations':len(case.storage.calls),'backup_sha256':backup['sha256']}))
    finally:case.tearDown()


if __name__=='__main__':main()
