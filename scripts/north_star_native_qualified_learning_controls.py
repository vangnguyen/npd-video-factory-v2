"""Signed qualified feedback controls/recovery; synthetic source, no media UAT."""
import argparse,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_learning import rows,settings,write
from scripts.north_star_native_qualified_learning import services,intelligence_rows
from services.windows_native.tests.test_qualified_learning_feedback_http import QualifiedFeedbackHTTPTests
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-qualified-learning-controls-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned qualified controls root required')
    return path

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve()
    store,journal,queue,analytics,winners,learning,intelligence,radar,feedback,planner=services(root,out)
    try:
        assert rows(store)==json.loads((out/'expected-journals.json').read_bytes())
        assert intelligence_rows(intelligence.store)==json.loads((out/'expected-intelligence-journals.json').read_bytes())
        for name,service,field in [('publications',journal,'publication_id'),('analytics-history',analytics,'sync_id'),('winner-history',winners,'assessment_id'),('learning-history',learning,'learning_id')]:
            values=json.loads((out/('expected-'+name+'.json')).read_bytes());assert len(values)==1
            for value in values:assert service.get(value['project_id'],value[field])==value
        projections=json.loads((out/'expected-projections.json').read_bytes());assert len(projections)==1
        assert feedback.get(projections[0]['id'])==projections[0]
        assert feedback.suggestions(projections[0]['id'])==json.loads((out/'expected-template-suggestions.json').read_bytes())
        for value in json.loads((out/'expected-projects.json').read_bytes()):assert store.get(value['id'])==value
        for value in json.loads((out/'expected-jobs.json').read_bytes()):assert store.get_job(value['id'])==value
        physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
        assert database_status(store.db)['active_operations']==0 and not queue.configured() and queue.process() is None
        assert not analytics.states()['enabled'] and analytics.states()['accounts']==[] and analytics.process() is None and journal.states()['profiles']==[]
        write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
            'one_receipt_observation_assessment_learning_projection_24_workflow_four_intelligence_journals_original_projects_jobs_files_templates_exact':True,
            'credential_registry_publish_queue_analytics_or_trend_providers_enabled':False,'new_media_or_provider_operations':0,'real_audience_observations':0,'explicit_nonplayable_fixture':True})
    finally:radar.close()

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external qualified controls evidence required')
    out.mkdir(parents=True);fixture=QualifiedFeedbackHTTPTests();original=fixture.request;http=[]
    def request(method,path,body=None,headers=None):
        status,value,metadata=original(method,path,body,headers)
        http.append({'method':method,'path':path,'status':status,'request_sha256':digest(body),'response_sha256':digest(value) if isinstance(value,(dict,list)) else None,'cache_control':metadata.get('Cache-Control')})
        return status,value,metadata
    fixture.request=request;fixture.setUp()
    try:
        store=fixture.server.store;project=fixture.project['id'];runner=fixture.server.runner;before=store.get(project);job=store.get_job(fixture.job['id']);receipt=fixture.completed
        assert len(fixture.read_wire)==3 and len(fixture.wire)==10 and not runner.run_one();runner.wake.clear()
        body=fixture.qualified_body();first=fixture.project_feedback();record=first['record'];replay=request('POST','/api/trends/learning/qualified',body)[1]
        assert replay['idempotent_replay'] and replay['record']==record and first['record_sha256']==digest(record)
        assert request('POST','/api/trends/learning/qualified',{**body,'expected_learning_sha256':'f'*64})[0]==409
        history=request('GET','/api/trends/learning')[1];assert history['items']==[record]
        assert request('GET','/api/trends/records/'+record['id'])[1]['record']==record
        templates=request('GET','/api/trends/learning/qualified/'+record['id']+'/templates')[1]
        assert templates['suggestions']==[] and templates['projection_sha256']==digest(record) and not templates['automatic_application']
        assert record['payload']['observation_count']==0 and record['payload']['status']=='insufficient_data' and record['payload']['mock'] and not record['payload']['real_audience_observation']
        fixture.account('viewer');assert request('POST','/api/trends/learning/qualified',body)[0]==403
        assert request('GET','/api/trends/learning/qualified/'+record['id']+'/templates')[1]==templates
        assert request('GET',fixture.learning_base+'/'+fixture.learned['learning_id'])[1]==fixture.learned
        served={}
        for name in ('native.html','native.mjs','shot-studio.mjs','native-qualified-learning.mjs','native-official-learning.mjs','trend-radar.mjs'):
            status,value,_=request('GET','/'+name);assert status==200 and value==(ROOT/'apps/studio-web'/name).read_bytes();served[name]={'sha256':file_sha(ROOT/'apps/studio-web'/name),'bytes':len(value)}
        write(out/'served-studio-files.json',served);write(out/'bounded-history.json',history);write(out/'projection-response.json',first)
        assert not runner.wake.is_set() and not runner.run_one() and len(fixture.read_wire)==3 and len(fixture.wire)==10
        assert store.get(project)==before and store.get_job(job['id'])==job and fixture.server.official_publications.get(project,receipt['publication_id'])==receipt
        with store.transaction() as con:
            syncs=[dict(r) for r in con.execute("SELECT project_id,sync_id FROM native_official_analytics_syncs WHERE status='succeeded' ORDER BY rowid")]
            assessed=[dict(r) for r in con.execute('SELECT project_id,assessment_id FROM native_official_winner_assessments ORDER BY rowid')]
        observations=[fixture.analytics.get(v['project_id'],v['sync_id']) for v in syncs];assessments=[fixture.winners.get(v['project_id'],v['assessment_id']) for v in assessed]
        assert len(observations)==len(assessments)==1
        for name,value in [('publications',[receipt]),('analytics-history',observations),('winner-history',assessments),('learning-history',[fixture.learned]),('projections',[record]),('template-suggestions',templates),('projects',[before]),('jobs',[job])]:write(out/('expected-'+name+'.json'),value)
        write(out/'expected-journals.json',rows(store));write(out/'expected-intelligence-journals.json',intelligence_rows(fixture.server.intelligence.store))
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()));write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire)
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.analytics.costs.summary(project);write(out/'cost-summary.json',costs);assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-qualified-learning-controls.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-qualified-learning-controls.zip') as archive:
            assert all(not n.endswith(('.dpapi','.part')) for n in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(n) and fixture.read_credential.token.encode() not in archive.read(n) and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(n) for n in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-qualified-learning-controls.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-qualified-learning-feedback-flow-n2')
        old=services(Path('C:/vf-native-fixture-qualified-learning-feedback-restore-02'),prior)
        try:
            assert rows(old[0])==json.loads((prior/'expected-journals.json').read_bytes()) and intelligence_rows(old[6].store)==json.loads((prior/'expected-intelligence-journals.json').read_bytes())
            for value in json.loads((prior/'expected-projections.json').read_bytes()):assert old[8].get(value['id'])==value
            assert old[8].suggestions(json.loads((prior/'expected-projections.json').read_bytes())[0]['id'])==json.loads((prior/'expected-template-suggestions.json').read_bytes())
        finally:old[7].close()
        write(out/'legacy-qualified-feedback-replay.json',{'prior_24_workflow_four_intelligence_journals_two_projections_templates_original_sources_exact':True,'external_calls':0})
        write(out/'signed-http-summary.json',http);write(out/'sanitized-operation-logs.json',[json.loads(v) for v in fixture.operation_logs])
        sources=['services/windows_native/server.py','services/windows_native/tests/test_qualified_learning_feedback_http.py','scripts/north_star_native_qualified_learning_controls.py']+['apps/studio-web/'+name for name in (*served,'tests/native-qualified-learning.test.mjs','tests/native-official-learning.test.mjs','tests/native-trend-radar.test.mjs')]
        write(out/'evidence.json',{'schema_version':'native-qualified-learning-controls-rehearsal-v1','signed_http_requests':len(http),'mock_analytics_read_requests':3,'mock_publication_wire_requests':10,'mock_initial_account_lookup_requests':1,
            'explicit_nonplayable_qc_rights_identity_account_platform_oauth_provider_and_clock_fixtures':True,'no_provider_cost_media_budget_or_runner_operation_for_projection':True,'six_studio_files_served_exactly':True,
            'one_sparse_learning_projection_24_workflow_four_intelligence_journals_projects_jobs_files_templates_restore_exact':True,'prior_qualified_feedback_history_exact':True,'archive_excludes_tokens_session_uris':True,
            'real_publications':0,'real_audience_observations':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'accepted_runtime_publishing_or_analytics_enabled':False,'real_oauth_account_media_qc_legal_browser_owner_or_provider_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_QUALIFIED_LEARNING_CONTROLS_RECOVERY_PASS','signed_http_requests':len(http),'mock_analytics_read_requests':3,'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
