"""Changed read-registry stops/fresh consent/recovery; explicit protocol fixtures only."""
import argparse,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_analytics import rows,owned,reopen,settings,write
from services.windows_native.tests.test_official_analytics import OfficialAnalyticsTests
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_account_registry import AccountFactory
from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.publications import NativePublications
from services.windows_native.store import Store
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external read-registry evidence required')
    out.mkdir(parents=True);fixture=OfficialAnalyticsTests();fixture.setUp()
    try:
        NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(fixture.service,fixture.vault))
        before=fixture.store.get(fixture.project['id']);job=fixture.store.get_job(fixture.job['id']);receipt=fixture.completed
        path=fixture.bound_registry();first=fixture.run_collection();assert first['status']=='succeeded' and len(fixture.read_wire)==3
        frozen=fixture.reader.sha256;fixture.collect(request_key='explicit-registry-blocked-read-key');path.write_bytes(path.read_bytes()+b' ')
        stopped=fixture.analytics.process();assert stopped['status']=='failed' and stopped['failure_code']=='NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_CHANGED' and len(fixture.read_wire)==3
        assert fixture.analytics.process() is None
        fixture.reader=AccountFactory(fixture.reader.account,fixture.root,fixture.workspace,owner_read_enabled=True,
            transport=fixture.reader.client.wire.transport,resolver=lambda _:fixture.read_credential,registry_file=path,registry_sha256=file_sha(path))
        fixture.accounts.factories[fixture.reader.account.account_ref]=fixture.reader;assert fixture.reader.sha256!=frozen
        last=fixture.run_collection(request_key='explicit-registry-new-configuration-consent-key');assert last['status']=='succeeded' and len(fixture.read_wire)==6
        path.unlink();fixture.accounts.factories.clear();history=[fixture.analytics.get(fixture.project['id'],r['sync_id']) for r in (first,stopped,last)]
        assert all(r['result']['real_audience_observation'] is False for r in (first,last))
        assert NativeOfficialAnalytics(fixture.service).get(fixture.project['id'],first['sync_id'])['result']==first['result']
        assert fixture.store.get(fixture.project['id'])==before and fixture.store.get_job(job['id'])==job
        assert fixture.service.get(fixture.project['id'],receipt['publication_id'])==receipt
        write(out/'expected-analytics-history.json',history);write(out/'completed-review.json',receipt)
        write(out/'expected-project.json',before);write(out/'expected-jobs.json',[job]);write(out/'expected-journals.json',rows(fixture.store))
        write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire)
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.analytics.costs.summary(fixture.project['id']);write(out/'cost-summary.json',costs)
        assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-read-registry.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-read-registry.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(name) and fixture.read_credential.token.encode() not in archive.read(name)
                and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(name) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-read-registry.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-analytics-kernel-flow-n1');expected=json.loads((prior/'completed-review.json').read_bytes())
        old_store=Store(Path('C:/vf-native-fixture-official-analytics-restore-01'))
        old=NativeOfficialPublications(old_store,NativePublications(old_store,prior/'fixture-capabilities.json',workspace_id=expected['workspace_id']),NativeOfficialAccounts(old_store,workspace_id=expected['workspace_id']))
        old_analytics=NativeOfficialAnalytics(old);assert old.get(expected['project_id'],expected['publication_id'])==expected and rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        for sync in json.loads((prior/'expected-analytics-history.json').read_bytes()):assert old_analytics.get(sync['project_id'],sync['sync_id'])==sync
        write(out/'legacy-analytics-kernel-replay.json',{'prior_receipt_three_analytics_histories_twenty_journals_exact':True,'external_calls':0})
        sources=['services/windows_native/'+name for name in ('official_account_registry.py','official_analytics.py','tests/test_official_account_registry.py','tests/test_official_analytics.py')]+['scripts/north_star_native_official_read_registry.py']
        write(out/'evidence.json',{'schema_version':'native-official-read-registry-fences-rehearsal-v1',
            'explicit_nonplayable_qc_rights_identity_account_platform_oauth_provider_and_clock_fixtures':True,'mock_analytics_read_requests':len(fixture.read_wire),
            'mock_publication_wire_requests':len(fixture.wire),'mock_initial_account_lookup_requests':len(fixture.calls),'signed_http_requests':0,
            'changed_registry_after_consent_zero_additional_reads':True,'fresh_exact_configuration_and_explicit_new_consent_required':True,
            'removed_registry_and_factories_do_not_break_history':True,'all_twenty_journals_three_histories_source_and_prior_kernel_exact_restore':True,
            'real_publications':0,'real_audience_observations':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,
            'accepted_runtime_publishing_or_analytics_enabled':False,'real_oauth_account_media_qc_legal_owner_or_provider_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_READ_REGISTRY_FENCES_RECOVERY_PASS','mock_analytics_read_requests':len(fixture.read_wire),'external_calls':0}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
