"""Native receipt-to-analytics protocol/recovery rehearsal; no real audience/media/UAT."""
import argparse,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,write
from scripts.north_star_native_official_publish_queue import TABLES as PRIOR_TABLES
from services.windows_native.official_analytics import NativeOfficialAnalytics,TABLES as ANALYTICS_TABLES
from services.windows_native.official_analytics_models import Cancel
from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.publications import NativePublications
from services.windows_native.store import Store
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.tests.test_official_analytics import OfficialAnalyticsTests
from datetime import timedelta
TABLES=(*PRIOR_TABLES,*ANALYTICS_TABLES)

def rows(store):
    with store.transaction() as con:return {name:[dict(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in TABLES}

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-analytics-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned official-analytics restore required')
    return path

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();expected=json.loads((out/'completed-review.json').read_bytes());workspace=expected['workspace_id'];store=Store(root)
    pub=NativePublications(store,out/'fixture-capabilities.json',workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace)
    journal=NativeOfficialPublications(store,pub,accounts);queue=NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(journal,SessionVault(journal)))
    analytics=NativeOfficialAnalytics(journal)
    assert journal.get(expected['project_id'],expected['publication_id'])==expected and rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    for sync in json.loads((out/'expected-analytics-history.json').read_bytes()):assert analytics.get(sync['project_id'],sync['sync_id'])==sync
    assert store.get(expected['project_id'])==json.loads((out/'expected-project.json').read_bytes())
    for job in json.loads((out/'expected-jobs.json').read_bytes()):assert store.get_job(job['id'])==job
    physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and journal.states()['profiles']==[] and not queue.configured() and queue.process() is None
    assert analytics.states()['accounts']==[] and not analytics.states()['enabled'] and analytics.process() is None
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),
        {'receipt_three_analytics_histories_twenty_journals_project_jobs_artifacts_exact':True,'credential_registry_vault_publish_queue_or_analytics_enabled':False,
         'new_media_or_provider_operations':0,'real_audience_observation':False,'explicit_nonplayable_fixture':True})

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);fixture=OfficialAnalyticsTests();fixture.setUp()
    try:
        NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(fixture.service,fixture.vault))
        before=fixture.store.get(fixture.project['id']);before_job=fixture.store.get_job(fixture.job['id']);parent=fixture.publications.get(fixture.project['id'],fixture.parent['publication_id'])
        receipt=fixture.service.get(fixture.project['id'],fixture.value['publication_id'])
        assert NativeOfficialAnalytics(fixture.service).process() is None
        fixture.read_mode='rate-limit';first=fixture.run_collection(max_attempts=2,acknowledged_bounded_retries=True)
        assert first['status']=='retry_scheduled' and len(fixture.read_wire)==1 and fixture.analytics.process() is None
        write(out/'first-known-backoff.json',first);fixture.clock[0]+=timedelta(seconds=45);fixture.read_mode=None
        first=fixture.analytics.process();assert first['status']=='succeeded' and first['attempts']==2 and len(fixture.read_wire)==4
        fixture.metric_values[0]=100;second=fixture.run_collection(request_key='explicit-rehearsal-second-analytics-key')
        assert second['status']=='succeeded' and second['result']['metrics']['views']==100 and len(fixture.read_wire)==7
        assert fixture.analytics.get(fixture.project['id'],first['sync_id'])['result']==first['result']
        third=fixture.collect(request_key='explicit-rehearsal-cancelled-analytics-key')
        third=fixture.analytics.cancel(fixture.project['id'],third['sync_id'],Cancel(expected_snapshot_sha256=third['snapshot_sha256']),principal=fixture.principal)
        assert third['status']=='cancelled' and fixture.analytics.process() is None and len(fixture.read_wire)==7
        for value in (first,second):
            result=value['result'];assert result['mock'] is True and result['external_call'] is False and result['real_audience_observation'] is False
            assert result['metrics']['completion_rate'] is None and result['metrics']['observation_window_hours'] is None and result['metrics']['rpm'] is None
            assert result['publishing_time'] is None and result['evidence']['coverage_end_date'] is None and result['metrics']['watch_time']==150
        assert all(row['method']=='GET' for row in fixture.read_wire)
        assert fixture.store.get(fixture.project['id'])==before and fixture.store.get_job(fixture.job['id'])==before_job
        assert fixture.service.get(fixture.project['id'],fixture.value['publication_id'])==receipt and fixture.publications.get(fixture.project['id'],fixture.parent['publication_id'])==parent
        history=[fixture.analytics.get(fixture.project['id'],value['sync_id']) for value in (first,second,third)]
        write(out/'expected-analytics-history.json',history);write(out/'completed-review.json',receipt)
        write(out/'expected-project.json',before);write(out/'expected-jobs.json',[before_job]);write(out/'expected-journals.json',rows(fixture.store))
        write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire)
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.analytics.costs.summary(fixture.project['id']);write(out/'cost-summary.json',costs)
        assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        read_costs=[r for r in costs['records'] if r['provider']=='official-youtube-analytics'];assert len(read_costs)==7 and len({r['operation'] for r in read_costs})==7
        backup=create_backup(settings(fixture.root),out/'owned-official-analytics.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-analytics.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(name) and fixture.read_credential.token.encode() not in archive.read(name)
                and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(name) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-analytics.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-publish-queue-controls-flow-n1')
        expected=json.loads((prior/'completed-review.json').read_bytes());old_store=Store(Path('C:/vf-native-fixture-official-publish-queue-controls-restore-01'))
        old=NativeOfficialPublications(old_store,NativePublications(old_store,prior/'fixture-capabilities.json',workspace_id=expected['workspace_id']),NativeOfficialAccounts(old_store,workspace_id=expected['workspace_id']))
        old_queue=NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(old,SessionVault(old)))
        assert old.get(expected['project_id'],expected['publication_id'])==expected
        with old_store.transaction() as con:assert {name:[dict(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in PRIOR_TABLES}==json.loads((prior/'expected-journals.json').read_bytes())
        for plan in json.loads((prior/'expected-plan-history.json').read_bytes()):assert old_queue.get(plan['project_id'],plan['plan_id'])==plan
        write(out/'legacy-queue-controls-replay.json',{'prior_receipt_two_plan_histories_fifteen_journals_exact':True,'external_calls':0})
        sources=['services/windows_native/'+name for name in ('official_analytics.py','official_analytics_models.py','backup.py','tests/test_official_analytics.py')]+['scripts/north_star_native_official_analytics.py']
        write(out/'evidence.json',{'schema_version':'native-official-analytics-kernel-rehearsal-v1',
            'explicit_nonplayable_qc_rights_identity_account_platform_oauth_provider_and_clock_fixtures':True,
            'mock_publication_wire_requests':len(fixture.wire),'mock_initial_account_lookup_requests':len(fixture.calls),'mock_analytics_read_requests':len(fixture.read_wire),
            'signed_http_requests':0,'analytics_kernel_only_not_studio_or_runner_integration':True,
            'default_off_no_decryption_or_read_on_initialization':True,'separate_finite_receipt_and_current_account_bound_read_consent':True,
            'every_attempt_fresh_authenticated_account_video_ownership_report':True,'known_backoff_distinct_attempt_costs':True,
            'two_immutable_mock_observations_and_local_cancelled_third_request':True,'missing_metrics_and_unknown_window_publishing_time_remain_null':True,
            'original_project_dry_run_receipt_job_artifacts_unchanged':True,'all_twenty_journals_exact_restore':True,
            'prior_queue_controls_receipt_two_histories_fifteen_journals_exact':True,'archive_excludes_tokens_session_uris':True,
            'real_publications':0,'real_audience_observations':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,
            'accepted_runtime_publishing_or_analytics_enabled':False,'real_oauth_account_media_qc_legal_owner_or_provider_acceptance':False,
            'native_analytics_studio_runtime_integration_complete':False,'source_sha256':{name:file_sha(ROOT/name) for name in sources},
            'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_ANALYTICS_KERNEL_RECOVERY_PASS','mock_analytics_read_requests':len(fixture.read_wire),'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
