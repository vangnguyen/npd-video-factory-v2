"""Signed finite refresh Studio bytes/original responses and offline exact recovery."""
import argparse,json,re,sys,zipfile
from pathlib import Path
from datetime import timedelta
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_learning import rows,settings,write
from scripts.north_star_native_qualified_learning import services
from scripts.north_star_native_qualified_bridge import bridge_rows,source_rows
from services.windows_native.tests.test_official_analytics_refresh_http import OfficialRefreshHTTPTests
from services.windows_native.official_analytics_refresh import NativeOfficialAnalyticsRefresh,TABLES
from services.windows_native.bridge import NativeBridge
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status

def journals(store):
    value=rows(store)
    with store.transaction() as con:value.update({name:[dict(r) for r in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in TABLES})
    return value
def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-refresh-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned official refresh root required')
    return path
def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();parts=services(root,out)
    store,journal,queue,analytics,winners,learning,intelligence,radar,feedback,planner=parts
    try:
        refresh=NativeOfficialAnalyticsRefresh(analytics);bridge=NativeBridge(store,workspace_id=learning.workspace);bridge.attach_intelligence(intelligence.store)
        bridge.bind_qualified_sources(analytics=analytics,winner=winners,learning=learning,projection=feedback)
        assert journals(store)==json.loads((out/'expected-journals.json').read_bytes()) and bridge_rows(store)==json.loads((out/'expected-bridge-journals.json').read_bytes())
        assert source_rows(intelligence.store)==json.loads((out/'expected-intelligence-journals.json').read_bytes())
        value=json.loads((out/'expected-refresh-plan.json').read_bytes());assert refresh.get(value['project_id'],value['plan_id'])==value and len(value['occurrences'])==2 and value['status']=='completed'
        for item in json.loads((out/'expected-analytics-history.json').read_bytes()):assert analytics.get(item['project_id'],item['sync_id'])==item
        publication=json.loads((out/'expected-publications.json').read_bytes())[0];assert journal.get(publication['project_id'],publication['publication_id'])==publication
        assert bridge.page(limit=100)==json.loads((out/'expected-bridge-page.json').read_bytes())
        for value in json.loads((out/'expected-projects.json').read_bytes()):assert store.get(value['id'])==value
        for value in json.loads((out/'expected-jobs.json').read_bytes()):assert store.get_job(value['id'])==value
        physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
        assert database_status(store.db)['active_operations']==0 and not refresh.configured() and refresh.tick() is None
        assert refresh.recover()['plans_needing_attention']==0 and not analytics.enabled and analytics.process() is None
        assert not queue.configured() and queue.process() is None and journal.states()['profiles']==[] and analytics.states()['accounts']==[]
        assert not bridge.delivery_enabled and bridge.verifier is None and bridge.process() is None and bridge.harvest()==0
        write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
            'one_receipt_one_completed_finite_plan_two_occurrences_observations_source_events_27_workflow_eight_bridge_five_intelligence_journals_exact':True,
            'original_project_job_files_hashes_and_null_metric_history_exact':True,'credentials_providers_refresh_publication_queue_service_auth_webhook_enabled':False,
            'external_or_new_media_operations':0,'real_audience_observations':0,'explicit_nonplayable_fixture':True})
    finally:radar.close()
def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external official refresh evidence required')
    out.mkdir(parents=True);fixture=OfficialRefreshHTTPTests();original=fixture.request;http=[]
    def request(method,path,body=None,headers=None):
        status,value,metadata=original(method,path,body,headers)
        http.append({'method':method,'path':path,'status':status,'request_sha256':digest(body),'response_sha256':digest(value) if isinstance(value,(dict,list)) else None,'cache_control':metadata.get('Cache-Control')})
        return status,value,metadata
    fixture.request=request;fixture.setUp()
    try:
        store=fixture.server.store;project=fixture.project['id'];before=store.get(project);job=store.get_job(fixture.job['id'])
        assert len(fixture.wire)==10 and len(fixture.calls)==1 and fixture.read_wire==[]
        runtime=request('GET','/api/connections/official-analytics-refresh')[1];assert runtime['enabled'] and not runtime['default_enabled'] and not runtime['publishing_enabled']
        source=request('GET',fixture.base+'/source/'+fixture.completed['publication_id'])[1];assert source['receipt_qualified'] and source['mock']
        body=fixture.refresh_payload(max_runs=2).model_dump(mode='json');status,created,_=request('POST',fixture.refresh_base,body)
        assert status==200 and created['run_count']==0 and fixture.read_wire==[]
        assert fixture.server.runner.run_one();first=request('GET',fixture.refresh_base+'/'+created['plan_id'])[1];assert first['run_count']==1 and first['occurrences'][0]['sync']['status']=='succeeded'
        assert not fixture.server.runner.run_one();fixture.clock[0]+=timedelta(seconds=60);fixture.rows=False
        assert fixture.server.runner.run_one() and fixture.server.runner.run_one() and not fixture.server.runner.run_one()
        saved=request('GET',fixture.refresh_base+'/'+created['plan_id'])[1];assert saved['status']=='completed' and len(saved['occurrences'])==2
        observations=[v['sync'] for v in saved['occurrences']];assert observations[0]==first['occurrences'][0]['sync'] and observations[0]['result']['metrics']['views']==0
        assert all(v is None for v in observations[1]['result']['metrics'].values()) and observations[1]['result']['evidence']['row_count']==0
        assert all(v['mock'] and not v['result']['real_audience_observation'] and v['result']['publishing_time'] is None for v in observations)
        replay=request('POST',fixture.refresh_base,body)[1];assert replay.pop('idempotent_replay') and replay==saved and len(fixture.read_wire)==6
        page=request('GET',fixture.refresh_base+'?publication='+created['publication_id']+'&limit=25')[1];assert page['items']==[saved]
        fixture.account('viewer');assert request('GET',fixture.refresh_base+'/'+created['plan_id'])[1]==saved
        served={}
        for name in ('native-official-refresh.mjs','native-official-analytics.mjs','native.html','native.mjs'):
            status,value,_=request('GET','/'+name);assert status==200 and value==(ROOT/'apps/studio-web'/name).read_bytes();served[name]={'sha256':file_sha(ROOT/'apps/studio-web'/name),'bytes':len(value)}
        assert len(fixture.read_wire)==6 and len(fixture.wire)==10 and store.get(project)==before and store.get_job(job['id'])==job
        bridge=fixture.server.bridge;assert bridge.harvest()==0;bridge_page=bridge.page(limit=100);assert len(bridge_page['items'])==2
        assert all(v['envelope']['payload']['source_type']=='analytics' and v['envelope']['payload']['mock'] and not v['envelope']['payload']['real_audience_observation'] and v['delivery']['status']=='disabled' for v in bridge_page['items'])
        write(out/'expected-refresh-plan.json',saved);write(out/'expected-analytics-history.json',observations);write(out/'expected-publications.json',[fixture.completed])
        write(out/'expected-projects.json',[before]);write(out/'expected-jobs.json',[job]);write(out/'expected-journals.json',journals(store))
        write(out/'expected-bridge-journals.json',bridge_rows(store));write(out/'expected-intelligence-journals.json',source_rows(fixture.server.intelligence.store));write(out/'expected-bridge-page.json',bridge_page)
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()));write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire);write(out/'served-studio-files.json',served)
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.analytics.costs.summary(project);write(out/'cost-summary.json',costs);assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-refresh.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-refresh.zip') as archive:
            assert all(not n.endswith(('.dpapi','.part')) for n in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(n) and fixture.read_credential.token.encode() not in archive.read(n) and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(n) for n in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-refresh.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-qualified-bridge-flow-n1');old=services(Path('C:/vf-native-fixture-qualified-bridge-restore-01'),prior)
        try:
            old_bridge=NativeBridge(old[0],workspace_id=old[5].workspace);old_bridge.attach_intelligence(old[6].store);old_bridge.bind_qualified_sources(analytics=old[3],winner=old[4],learning=old[5],projection=old[8])
            assert rows(old[0])==json.loads((prior/'expected-journals.json').read_bytes()) and bridge_rows(old[0])==json.loads((prior/'expected-bridge-journals.json').read_bytes())
            assert source_rows(old[6].store)==json.loads((prior/'expected-intelligence-journals.json').read_bytes()) and old_bridge.page(limit=100)==json.loads((prior/'expected-bridge-page.json').read_bytes())
            record=json.loads((prior/'expected-projection.json').read_bytes());assert old[8].get(record['id'])==record
        finally:old[7].close()
        write(out/'legacy-qualified-bridge-replay.json',{'prior_24_workflow_eight_bridge_five_intelligence_journals_four_original_qualified_events_and_projection_exact':True,'external_calls':0})
        prior_refresh=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-refresh-flow-n2');old=services(Path('C:/vf-native-fixture-official-refresh-restore-02'),prior_refresh)
        try:
            old_refresh=NativeOfficialAnalyticsRefresh(old[3]);old_bridge=NativeBridge(old[0],workspace_id=old[5].workspace);old_bridge.attach_intelligence(old[6].store)
            old_bridge.bind_qualified_sources(analytics=old[3],winner=old[4],learning=old[5],projection=old[8])
            assert journals(old[0])==json.loads((prior_refresh/'expected-journals.json').read_bytes()) and bridge_rows(old[0])==json.loads((prior_refresh/'expected-bridge-journals.json').read_bytes())
            assert source_rows(old[6].store)==json.loads((prior_refresh/'expected-intelligence-journals.json').read_bytes()) and old_bridge.page(limit=100)==json.loads((prior_refresh/'expected-bridge-page.json').read_bytes())
            original=json.loads((prior_refresh/'expected-refresh-plan.json').read_bytes());assert old_refresh.get(original['project_id'],original['plan_id'])==original
            for observation in json.loads((prior_refresh/'expected-analytics-history.json').read_bytes()):assert old[3].get(observation['project_id'],observation['sync_id'])==observation
            assert not old_refresh.configured() and old_refresh.tick() is None and not old_bridge.delivery_enabled and old_bridge.process() is None
        finally:old[7].close()
        write(out/'legacy-official-refresh-replay.json',{'prior_27_workflow_eight_bridge_five_intelligence_journals_original_finite_plan_two_occurrences_observations_events_exact':True,'external_calls':0})
        write(out/'signed-http-summary.json',http);write(out/'sanitized-operation-logs.json',[json.loads(v) for v in fixture.operation_logs])
        sources=['services/windows_native/'+name for name in ('official_analytics.py','official_analytics_refresh.py','official_analytics_refresh_routes.py','server.py','access.py','backup.py','tests/test_official_analytics_refresh.py','tests/test_official_analytics_refresh_http.py')]+['scripts/north_star_native_official_refresh_controls.py']+['apps/studio-web/'+name for name in ('native-official-refresh.mjs','native.mjs','native.html','tests/native-official-refresh.test.mjs','tests/fixtures/native-official-refresh-v1.json')]
        write(out/'evidence.json',{'schema_version':'native-official-refresh-controls-rehearsal-v1','signed_http_requests':len(http),'mock_analytics_read_requests':6,'mock_publication_wire_requests':10,'mock_initial_account_lookup_requests':1,
            'finite_completed_plan':1,'occurrences':2,'qualified_analytics_source_events':2,'zero_and_empty_report_nulls_fixed_query_old_snapshots_preserved':True,
            '27_workflow_eight_bridge_five_intelligence_journals_original_project_job_files_fresh_restore_exact':True,'prior_qualified_bridge_original_history_exact':True,'prior_finite_official_refresh_original_history_exact':True,'studio_controls_integrated':True,'automatic_ui_provider_reads':False,
            'explicit_nonplayable_qc_rights_oauth_account_identity_and_clock_fixtures':True,'real_publications':0,'real_audience_observations':0,'actual_hub_calls':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'browser_owner_provider_or_production_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_REFRESH_RECOVERY_PASS','signed_http_requests':len(http),'occurrences':2,'mock_read_requests':6,'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
