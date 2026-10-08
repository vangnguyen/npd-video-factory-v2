"""Owned signed analytics/Runner/served Studio/recovery; provider inputs are fixtures."""
import argparse,json,sys,zipfile
from datetime import timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_analytics import rows,owned,reopen,settings,write
from services.windows_native.tests.test_official_analytics_http import OfficialAnalyticsHTTPTests
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.publications import NativePublications
from services.windows_native.store import Store
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup,restore_backup

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external controls evidence required')
    out.mkdir(parents=True);fixture=OfficialAnalyticsHTTPTests();original_request=fixture.request;http=[]
    def request(method,path,body=None,headers=None):
        status,value,metadata=original_request(method,path,body,headers)
        http.append({'method':method,'path':path,'status':status,'request_sha256':digest(body),'response_sha256':digest(value) if isinstance(value,(dict,list)) else None,'cache_control':metadata.get('Cache-Control')})
        return status,value,metadata
    fixture.request=request;fixture.setUp()
    try:
        store=fixture.server.store;analytics=fixture.server.official_analytics;runner=fixture.server.runner;project=fixture.project['id']
        before=store.get(project);job=store.get_job(fixture.job['id']);receipt=fixture.completed;parent=fixture.server.publications.get(project,fixture.parent['publication_id'])
        assert runner.run_one() is False and fixture.read_wire==[]
        runtime=request('GET','/api/connections/official-analytics')[1];assert runtime['enabled'] and runtime['default_enabled'] is False and runtime['fixture_fallback'] is False
        write(out/'explicit-runtime-status.json',runtime)
        binding=request('GET',fixture.base+'/source/'+receipt['publication_id'])[1];assert binding['receipt_sha256']==digest(receipt['receipt'])
        assert binding['mock'] and not binding['published'] and not binding['publishing_enabled'];write(out/'server-receipt-binding.json',binding)
        body=fixture.collection(max_attempts=2,acknowledged_bounded_retries=True).model_dump(mode='json')
        first=fixture.create_http(max_attempts=2,acknowledged_bounded_retries=True);assert fixture.read_wire==[] and first['result'] is None
        assert request('POST',fixture.base,body)[1]['idempotent_replay'];fixture.read_mode='rate-limit';assert runner.run_one()
        delayed=request('GET',fixture.base+'/'+first['sync_id'])[1];assert delayed['status']=='retry_scheduled' and not runner.run_one() and len(fixture.read_wire)==1
        write(out/'first-known-backoff.json',delayed);fixture.clock[0]+=timedelta(seconds=45);fixture.read_mode=None;assert runner.run_one() and not runner.run_one()
        first=request('GET',fixture.base+'/'+first['sync_id'])[1];replay=request('POST',fixture.base,body)[1];assert replay.pop('idempotent_replay') and replay==first and len(fixture.read_wire)==4
        fixture.metric_values[0]=100;second=fixture.create_http(request_key='explicit-signed-controls-second-read-key');assert len(fixture.read_wire)==4
        assert runner.run_one();second=request('GET',fixture.base+'/'+second['sync_id'])[1];assert second['result']['metrics']['views']==100 and len(fixture.read_wire)==7
        assert request('GET',fixture.base+'/'+first['sync_id'])[1]==first
        third=fixture.create_http(request_key='explicit-signed-controls-cancelled-read-key');payload={'expected_snapshot_sha256':third['snapshot_sha256']}
        path=fixture.base+'/'+third['sync_id']+'/cancel';third=request('POST',path,payload)[1];assert third['status']=='cancelled' and request('POST',path,payload)[1]==third
        assert not runner.run_one() and len(fixture.read_wire)==7
        for value in (first,second):
            result=value['result'];assert result['mock'] is True and result['external_call'] is False and result['real_audience_observation'] is False
            assert result['metrics']['completion_rate'] is None and result['metrics']['observation_window_hours'] is None and result['metrics']['rpm'] is None
            assert result['publishing_time'] is None and result['evidence']['coverage_end_date'] is None and result['metrics']['watch_time']==150
        page=request('GET',fixture.base+'?limit=1&publication='+receipt['publication_id'])[1];assert page['truncated'] and len(page['items'])==1
        next_page=request('GET',fixture.base+'?limit=1&publication='+receipt['publication_id']+'&cursor='+page['next_cursor'])[1];assert len(next_page['items'])==1
        history=request('GET',fixture.base+'?limit=25&publication='+receipt['publication_id'])[1];assert len(history['items'])==3
        write(out/'bounded-history.json',history);served={}
        for name in ('native.html','native.mjs','shot-studio.mjs','native-official-publications.mjs','native-official-analytics.mjs','native-analytics.mjs'):
            status,value,headers=request('GET','/'+name);assert status==200
            assert isinstance(value,bytes) and value==(ROOT/'apps/studio-web'/name).read_bytes();served[name]={'sha256':file_sha(ROOT/'apps/studio-web'/name),'bytes':len(value)}
        write(out/'served-studio-files.json',served)
        assert store.get(project)==before and store.get_job(job['id'])==job and fixture.server.official_publications.get(project,receipt['publication_id'])==receipt
        assert fixture.server.publications.get(project,parent['publication_id'])==parent
        write(out/'expected-analytics-history.json',[analytics.get(project,value['sync_id']) for value in (first,second,third)])
        write(out/'completed-review.json',receipt);write(out/'expected-project.json',before);write(out/'expected-jobs.json',[job]);write(out/'expected-journals.json',rows(store))
        write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire)
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=analytics.costs.summary(project);write(out/'cost-summary.json',costs)
        assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-analytics-controls.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-analytics-controls.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(name) and fixture.read_credential.token.encode() not in archive.read(name)
                and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(name) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-analytics-controls.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-read-registry-fences-flow-n1')
        expected=json.loads((prior/'completed-review.json').read_bytes());old_store=Store(Path('C:/vf-native-fixture-official-analytics-read-registry-restore-01'))
        old=NativeOfficialPublications(old_store,NativePublications(old_store,prior/'fixture-capabilities.json',workspace_id=expected['workspace_id']),NativeOfficialAccounts(old_store,workspace_id=expected['workspace_id']))
        old_analytics=NativeOfficialAnalytics(old);assert old.get(expected['project_id'],expected['publication_id'])==expected and rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        for value in json.loads((prior/'expected-analytics-history.json').read_bytes()):assert old_analytics.get(value['project_id'],value['sync_id'])==value
        write(out/'legacy-read-registry-replay.json',{'prior_receipt_three_analytics_histories_twenty_journals_exact':True,'external_calls':0})
        write(out/'signed-http-summary.json',http);write(out/'sanitized-operation-logs.json',[json.loads(line) for line in fixture.operation_logs])
        sources=['services/windows_native/'+name for name in ('server.py','access.py','observability.py','official_analytics_routes.py','tests/test_official_analytics_http.py','tests/test_observability.py')]
        sources +=['apps/studio-web/'+name for name in (*served,'tests/native-official-analytics.test.mjs')]+['scripts/north_star_native_official_analytics_controls.py']
        write(out/'evidence.json',{'schema_version':'native-official-analytics-controls-rehearsal-v1',
            'explicit_nonplayable_qc_rights_identity_account_platform_oauth_provider_and_clock_fixtures':True,
            'signed_http_requests':len(http),'mock_analytics_read_requests':len(fixture.read_wire),'mock_publication_wire_requests':len(fixture.wire),'mock_initial_account_lookup_requests':len(fixture.calls),
            'default_off_and_http_creation_replay_only_store_no_wire':True,'separate_finite_scoped_owner_read_consent':True,'known_backoff_no_early_runner_read':True,
            'two_immutable_qualified_mock_observations_and_local_cancelled_third_request':True,'completed_exact_key_replay_returns_same_result_no_extra_read':True,
            'all_six_studio_files_served_exactly':True,'missing_metrics_window_and_publishing_time_remain_null':True,
            'original_project_dry_run_receipt_job_artifacts_unchanged':True,'all_twenty_journals_three_histories_exact_restore':True,
            'prior_read_registry_receipt_three_histories_twenty_journals_exact':True,'archive_excludes_tokens_session_uris':True,
            'real_publications':0,'real_audience_observations':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,
            'accepted_runtime_publishing_or_analytics_enabled':False,'real_oauth_account_media_qc_legal_browser_owner_or_provider_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_ANALYTICS_CONTROLS_RECOVERY_PASS','signed_http_requests':len(http),'mock_analytics_read_requests':len(fixture.read_wire),'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
