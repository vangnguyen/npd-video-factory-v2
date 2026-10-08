"""Qualified synthetic learning cohort/recovery; no real audience or media UAT."""
import argparse,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_winners import TABLES as SOURCE_TABLES,services as source_services,settings,write
from services.windows_native.tests.test_official_learning import OfficialLearningTests
from services.windows_native.official_learning import NativeOfficialLearning,TABLES as LEARNING_TABLES
from services.windows_native.official_winner_models import Create as WinnerCreate
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
TABLES=(*SOURCE_TABLES,*LEARNING_TABLES)

def rows(store):
    with store.transaction() as con:return {name:[dict(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in TABLES}
def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-learning-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned learning restore required')
    return path
def services(root,out):
    store,journal,queue,analytics,winners=source_services(root,out)
    return store,journal,queue,analytics,winners,NativeOfficialLearning(winners)
def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();store,journal,queue,analytics,winners,learning=services(root,out)
    assert rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    for name,service,field in [('publications',journal,'publication_id'),('analytics-history',analytics,'sync_id'),('winner-history',winners,'assessment_id'),('learning-history',learning,'learning_id')]:
        for value in json.loads((out/('expected-'+name+'.json')).read_bytes()):assert service.get(value['project_id'],value[field])==value
    for value in json.loads((out/'expected-projects.json').read_bytes()):assert store.get(value['id'])==value
    for value in json.loads((out/'expected-jobs.json').read_bytes()):assert store.get_job(value['id'])==value
    physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and not queue.configured() and queue.process() is None
    assert not analytics.states()['enabled'] and analytics.states()['accounts']==[] and analytics.process() is None and journal.states()['profiles']==[]
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),
        {'seven_receipts_eleven_observations_eight_assessments_two_learning_snapshots_twenty_four_journals_projects_jobs_artifacts_exact':True,
         'credential_registry_vault_publish_queue_or_analytics_enabled':False,'new_media_or_provider_operations':0,'real_audience_observations':0,'explicit_nonplayable_fixture':True})
def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external learning evidence required')
    out.mkdir(parents=True);fixture=OfficialLearningTests();fixture.setUp()
    try:
        from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue
        from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
        NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(fixture.service,fixture.vault));fixture.cohort_learning()
        projects=[fixture.store.get(p['id']) for p in fixture.store.list()];jobs=[j for p in projects for j in p['jobs']]
        body=fixture.learning_body();first=fixture.learn();assert first['observation_count']==6 and first['status']=='recommendations_available'
        positive=next(g for d in first['dimensions'] if d['dimension']=='hook' for g in d['groups'] if g['value']=='explicit-question-hook')
        assert positive['state']=='recommendation_candidate' and positive['sample_count']==positive['control_count']==3
        replay,exact=fixture.learning.create(first['project_id'],body,principal=fixture.principal);assert exact and replay==first
        target=fixture.learning_sources[1];candidate=target['snapshot']['candidate'];fixture.project=fixture.store.get(target['project_id'])
        fixture.job=fixture.store.get_job(candidate['features']['evidence']['render_job_id']);fixture.completed=fixture.service.get(target['project_id'],target['publication_id']);fixture.rows=False
        observation=fixture.run_collection(request_key='explicit-retained-later-insufficient-learning-read')
        winner=WinnerCreate(sync_id=observation['sync_id'],expected_result_sha256=digest(observation['result']),acknowledged_recommendation_only=True,
            acknowledged_protocol_mock=True,request_key='explicit-retained-later-insufficient-winner-source')
        newest=fixture.winners.create(target['project_id'],winner,principal=fixture.principal)[0];assert newest['assessment']['state']=='insufficient_data'
        second=fixture.learn(request_key='explicit-retained-learning-after-insufficient-source');assert second['observation_count']==5
        assert all(d['state']=='insufficient_data' for d in second['dimensions']) and second['snapshot']['excluded_rows']['duplicate_remote_post']>=1
        assert fixture.learning.get(first['project_id'],first['learning_id'])==first
        assert all(v['mock'] and not v['real_audience_observation'] and not v['automatic_action'] and not v['external_call'] for v in (first,second))
        assert all(o['features']['publishing_window'] is None for v in (first,second) for o in v['snapshot']['observations'])
        with fixture.store.transaction() as con:
            pubs=[dict(r) for r in con.execute("SELECT project_id,publication_id FROM native_official_publications WHERE status='completed' ORDER BY rowid")]
            syncs=[dict(r) for r in con.execute("SELECT project_id,sync_id FROM native_official_analytics_syncs WHERE status='succeeded' ORDER BY rowid")]
            assessed=[dict(r) for r in con.execute('SELECT project_id,assessment_id FROM native_official_winner_assessments ORDER BY rowid')]
        publications=[fixture.service.get(v['project_id'],v['publication_id']) for v in pubs];analytics=[fixture.analytics.get(v['project_id'],v['sync_id']) for v in syncs]
        winners=[fixture.winners.get(v['project_id'],v['assessment_id']) for v in assessed]
        assert len(publications)==7 and len(analytics)==11 and len(winners)==8 and len(fixture.wire)==70 and len(fixture.read_wire)==39 and len(fixture.calls)==1
        assert [fixture.store.get(p['id']) for p in projects]==projects
        fixture.accounts.factories.clear();fixture.service.factories.clear()
        for value in (first,second):assert fixture.learning.get(value['project_id'],value['learning_id'])==value
        write(out/'expected-publications.json',publications);write(out/'expected-analytics-history.json',analytics);write(out/'expected-winner-history.json',winners);write(out/'expected-learning-history.json',[first,second])
        write(out/'expected-projects.json',projects);write(out/'expected-jobs.json',jobs);write(out/'expected-journals.json',rows(fixture.store));write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire)
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs={p['id']:fixture.analytics.costs.summary(p['id']) for p in projects};write(out/'cost-summary.json',costs)
        assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for s in costs.values() for r in s['records'])
        assert sum(r['provider']=='official-youtube-analytics' for s in costs.values() for r in s['records'])==33
        backup=create_backup(settings(fixture.root),out/'owned-official-learning.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-learning.zip') as archive:
            assert all(not n.endswith(('.dpapi','.part')) for n in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(n) and fixture.read_credential.token.encode() not in archive.read(n)
                and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(n) for n in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-learning.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-winner-controls-flow-n2')
        old_store,old_journal,_,old_analytics,old_winners=source_services(Path('C:/vf-native-fixture-official-winner-controls-restore-02'),prior)
        from scripts.north_star_native_official_winners import rows as old_rows
        assert old_rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        for name,service,field in [('publications',old_journal,'publication_id'),('analytics-history',old_analytics,'sync_id'),('winner-history',old_winners,'assessment_id')]:
            for value in json.loads((prior/('expected-'+name+'.json')).read_bytes()):assert service.get(value['project_id'],value[field])==value
        write(out/'legacy-signed-winner-controls-replay.json',{'prior_one_receipt_two_histories_three_assessments_twenty_two_journals_exact':True,'external_calls':0})
        sources=['services/windows_native/'+name for name in ('official_learning.py','official_learning_models.py','tests/test_official_learning.py','backup.py')]+['scripts/north_star_native_official_learning.py']
        write(out/'evidence.json',{'schema_version':'native-official-learning-kernel-rehearsal-v1',
            'explicit_nonplayable_qc_rights_identity_account_platform_oauth_provider_and_clock_fixtures':True,
            'mock_analytics_read_requests':33,'mock_peer_account_lookup_requests':6,'mock_publication_wire_requests':70,'mock_initial_account_lookup_requests':1,'signed_http_requests':0,
            'six_distinct_qualified_posts_three_group_three_controls_descriptive_mock_hook_association':True,'later_insufficient_post_never_revives_old_score_and_keeps_original_learning_exact':True,
            'learning_has_no_provider_cost_media_budget_or_automatic_action':True,'publishing_windows_missing_features_and_unknown_costs_not_invented':True,
            'all_twenty_four_journals_seven_receipts_eleven_histories_eight_assessments_two_learning_snapshots_restore_exact':True,'prior_signed_winner_controls_history_exact':True,'archive_excludes_tokens_session_uris':True,
            'real_publications':0,'real_audience_observations':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,
            'accepted_runtime_publishing_or_analytics_enabled':False,'real_oauth_account_media_qc_legal_browser_owner_or_provider_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_LEARNING_KERNEL_RECOVERY_PASS','mock_analytics_read_requests':33,'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
