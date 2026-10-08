"""Owned signed local assessment/served Studio/recovery; source data is synthetic."""
import argparse,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_winners import rows,owned,services,settings,write
from services.windows_native.tests.test_official_winner_http import OfficialWinnerHTTPTests
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status

def reopen(args):
    out=args.output.resolve();root=owned(args.restore_root);store,journal,queue,analytics,winners=services(root,out)
    assert rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    for key,service,idfield in [('publications',journal,'publication_id'),('analytics-history',analytics,'sync_id'),('winner-history',winners,'assessment_id')]:
        for value in json.loads((out/('expected-'+key+'.json')).read_bytes()):assert service.get(value['project_id'],value[idfield])==value
    for value in json.loads((out/'expected-projects.json').read_bytes()):assert store.get(value['id'])==value
    for value in json.loads((out/'expected-jobs.json').read_bytes()):assert store.get_job(value['id'])==value
    physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and not queue.configured() and queue.process() is None
    assert not analytics.states()['enabled'] and analytics.states()['accounts']==[] and analytics.process() is None and journal.states()['profiles']==[]
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),
        {'one_receipt_two_observations_three_assessments_twenty_two_journals_projects_jobs_artifacts_exact':True,
         'credential_registry_vault_publish_queue_or_analytics_enabled':False,'new_media_or_provider_operations':0,'real_audience_observations':0,'explicit_nonplayable_fixture':True})

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external winner controls evidence required')
    out.mkdir(parents=True);fixture=OfficialWinnerHTTPTests();original=fixture.request;http=[]
    def request(method,path,body=None,headers=None):
        status,value,metadata=original(method,path,body,headers)
        http.append({'method':method,'path':path,'status':status,'request_sha256':digest(body),'response_sha256':digest(value) if isinstance(value,(dict,list)) else None,'cache_control':metadata.get('Cache-Control')})
        return status,value,metadata
    fixture.request=request;fixture.setUp()
    try:
        store=fixture.server.store;project=fixture.project['id'];runner=fixture.server.runner;winners=fixture.winners
        before=store.get(project);job=store.get_job(fixture.job['id']);receipt=fixture.completed;parent=fixture.server.publications.get(project,fixture.parent['publication_id'])
        assert len(fixture.read_wire)==3 and not runner.run_one()
        runtime=request('GET','/api/connections/official-winners')[1];assert runtime['automatic_assessment'] is False and runtime['provider_calls_enabled'] is False
        write(out/'explicit-runtime-status.json',runtime)
        binding=request('GET',fixture.winner_base+'/source/'+fixture.observation['sync_id'])[1]
        assert binding['result_sha256']==digest(fixture.observation['result']) and binding['mock'] and not binding['real_audience_observation'];write(out/'server-result-binding.json',binding)
        first_body=fixture.winner_body();runner.wake.clear();first=fixture.create_winner();assert not first.pop('idempotent_replay');assert not runner.wake.is_set() and not runner.run_one()
        replay=request('POST',fixture.winner_base,first_body)[1];assert replay.pop('idempotent_replay') and replay==first and len(fixture.read_wire)==3
        assert request('GET',fixture.winner_base+'/'+first['assessment_id'])[1]==first
        fixture.metric_values[0]=100;second=fixture.create_http(request_key='explicit-signed-winner-controls-second-observation');assert runner.run_one()
        fixture.observation=request('GET',fixture.base+'/'+second['sync_id'])[1];second=fixture.create_winner(request_key='explicit-signed-winner-controls-second-assessment');second.pop('idempotent_replay')
        third=fixture.create_winner(policy={'minimum_views':1},request_key='explicit-signed-winner-controls-policy-assessment');third.pop('idempotent_replay')
        assert len(fixture.read_wire)==6 and not runner.run_one() and request('GET',fixture.winner_base+'/'+first['assessment_id'])[1]==first
        assessments=[first,second,third]
        assert all(v['assessment']['state']=='insufficient_data' and v['assessment']['score'] is None and v['mock'] is True
            and not v['real_audience_observation'] and not v['assessment']['channel_baseline_verified'] and not v['automatic_action'] and not v['external_call'] for v in assessments)
        page=request('GET',fixture.winner_base+'?limit=2&publication='+receipt['publication_id'])[1];assert page['truncated'] and len(page['items'])==2
        assert len(request('GET',fixture.winner_base+'?limit=2&publication='+receipt['publication_id']+'&cursor='+page['next_cursor'])[1]['items'])==1
        history=request('GET',fixture.winner_base+'?limit=25&publication='+receipt['publication_id'])[1];assert len(history['items'])==3;write(out/'bounded-history.json',history)
        served={}
        for name in ('native.html','native.mjs','shot-studio.mjs','native-official-analytics.mjs','native-official-winners.mjs'):
            status,value,_=request('GET','/'+name);assert status==200 and value==(ROOT/'apps/studio-web'/name).read_bytes();served[name]={'sha256':file_sha(ROOT/'apps/studio-web'/name),'bytes':len(value)}
        write(out/'served-studio-files.json',served)
        assert store.get(project)==before and store.get_job(job['id'])==job and fixture.server.official_publications.get(project,receipt['publication_id'])==receipt
        assert fixture.server.publications.get(project,parent['publication_id'])==parent
        with store.transaction() as con:syncs=[dict(row) for row in con.execute("SELECT project_id,sync_id FROM native_official_analytics_syncs WHERE status='succeeded' ORDER BY rowid")]
        observations=[fixture.analytics.get(v['project_id'],v['sync_id']) for v in syncs];assert len(observations)==2
        write(out/'expected-publications.json',[receipt]);write(out/'expected-analytics-history.json',observations);write(out/'expected-winner-history.json',assessments)
        write(out/'expected-projects.json',[before]);write(out/'expected-jobs.json',[job]);write(out/'expected-journals.json',rows(store));write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire)
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.analytics.costs.summary(project);write(out/'cost-summary.json',costs)
        assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-winner-controls.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-winner-controls.zip') as archive:
            assert all(not n.endswith(('.dpapi','.part')) for n in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(n) and fixture.read_credential.token.encode() not in archive.read(n)
                and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(n) for n in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-winner-controls.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-winner-kernel-flow-n1')
        old_store,old_journal,_,old_analytics,old_winners=services(Path('C:/vf-native-fixture-official-winner-restore-01'),prior)
        assert rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        for name,service,idfield in [('publications',old_journal,'publication_id'),('analytics-history',old_analytics,'sync_id'),('winner-history',old_winners,'assessment_id')]:
            for value in json.loads((prior/('expected-'+name+'.json')).read_bytes()):assert service.get(value['project_id'],value[idfield])==value
        write(out/'legacy-winner-kernel-replay.json',{'prior_six_receipts_ten_histories_four_assessments_twenty_two_journals_exact':True,'external_calls':0})
        write(out/'signed-http-summary.json',http);write(out/'sanitized-operation-logs.json',[json.loads(v) for v in fixture.operation_logs])
        sources=['services/windows_native/'+name for name in ('server.py','access.py','official_winner_routes.py','tests/test_official_winner_http.py','tests/test_official_analytics_http.py')]
        sources+=['apps/studio-web/'+name for name in (*served,'tests/native-official-winners.test.mjs')]+['scripts/north_star_native_official_winner_controls.py']
        write(out/'evidence.json',{'schema_version':'native-official-winner-controls-rehearsal-v1','signed_http_requests':len(http),
            'mock_analytics_read_requests':len(fixture.read_wire),'mock_publication_wire_requests':len(fixture.wire),'mock_initial_account_lookup_requests':len(fixture.calls),
            'explicit_nonplayable_qc_rights_identity_account_platform_oauth_provider_and_clock_fixtures':True,
            'assessment_has_no_provider_cost_media_or_runner_operation':True,'server_canonical_observation_hash_binding':True,
            'two_observations_three_insufficient_assessments_exact_key_replay_and_immutable_history':True,'five_studio_files_served_exactly':True,
            'all_twenty_two_journals_history_projects_jobs_artifacts_exact_restore':True,'prior_winner_kernel_history_exact':True,'archive_excludes_tokens_session_uris':True,
            'real_publications':0,'real_audience_observations':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,
            'accepted_runtime_publishing_or_analytics_enabled':False,'real_oauth_account_media_qc_legal_browser_owner_or_provider_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_WINNER_CONTROLS_RECOVERY_PASS','signed_http_requests':len(http),'mock_analytics_read_requests':len(fixture.read_wire),'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
