"""Qualified mock cohorts/immutable winner recovery; no real audience or media UAT."""
import argparse,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_analytics import TABLES as ANALYTICS_TABLES,settings,write,rows as analytics_rows
from services.windows_native.tests.test_official_winners import OfficialWinnersTests
from services.windows_native.official_winners import NativeOfficialWinners,TABLES as WINNER_TABLES
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.publications import NativePublications
from services.windows_native.store import Store
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
TABLES=(*ANALYTICS_TABLES,*WINNER_TABLES)

def rows(store):
    with store.transaction() as con:return {name:[dict(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in TABLES}

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-winner-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned winner restore required')
    return path

def services(root,out):
    expected=json.loads((out/'expected-publications.json').read_bytes());store=Store(root);workspace=expected[0]['workspace_id']
    publication=NativePublications(store,out/'fixture-capabilities.json',workspace_id=workspace)
    journal=NativeOfficialPublications(store,publication,NativeOfficialAccounts(store,workspace_id=workspace))
    queue=NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(journal,SessionVault(journal)))
    analytics=NativeOfficialAnalytics(journal);winners=NativeOfficialWinners(analytics)
    return store,journal,queue,analytics,winners

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();store,journal,queue,analytics,winners=services(root,out)
    assert rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    for value in json.loads((out/'expected-publications.json').read_bytes()):assert journal.get(value['project_id'],value['publication_id'])==value
    for value in json.loads((out/'expected-analytics-history.json').read_bytes()):assert analytics.get(value['project_id'],value['sync_id'])==value
    for value in json.loads((out/'expected-winner-history.json').read_bytes()):assert winners.get(value['project_id'],value['assessment_id'])==value
    for value in json.loads((out/'expected-projects.json').read_bytes()):assert store.get(value['id'])==value
    for value in json.loads((out/'expected-jobs.json').read_bytes()):assert store.get_job(value['id'])==value
    physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and not queue.configured() and queue.process() is None
    assert not analytics.states()['enabled'] and analytics.states()['accounts']==[] and analytics.process() is None and journal.states()['profiles']==[]
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),
        {'six_receipts_ten_analytics_histories_four_assessments_twenty_two_journals_projects_jobs_artifacts_exact':True,
         'credential_registry_vault_publish_queue_or_analytics_enabled':False,'new_media_or_provider_operations':0,'real_audience_observations':0,'explicit_nonplayable_fixture':True})

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external winner evidence required')
    out.mkdir(parents=True);fixture=OfficialWinnersTests();fixture.setUp()
    try:
        NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(fixture.service,fixture.vault));fixture.cohort()
        project_ids=[row['id'] for row in fixture.store.list()];before=[fixture.store.get(identifier) for identifier in project_ids]
        jobs=[job for project in before for job in project['jobs']];first_body=fixture.winner_body();first=fixture.assess();assert first['assessment']['state']=='winner_candidate' and first['peer_count']==5
        assessments=[first]
        for i,(metrics,state) in enumerate((([1000,20,1.2,25,2,5,5],'normal'),([1000,10,.6,12,1,2,2],'underperforming'),(None,'insufficient_data'))):
            fixture.rows=metrics is not None
            if metrics is not None:fixture.metric_values=metrics
            fixture.anchor=fixture.run_collection(request_key='explicit-retained-winner-classification-read-'+str(i))
            value=fixture.assess(request_key='explicit-retained-winner-classification-assessment-'+str(i));assert value['assessment']['state']==state and value['peer_count']==5
            assessments.append(value);assert fixture.winners.get(fixture.anchor_project,first['assessment_id'])==first
        replay,exact=fixture.winners.create(fixture.anchor_project,first_body,principal=fixture.principal);assert exact and replay==first
        assert all(value['mock'] and not value['real_audience_observation'] and not value['assessment']['channel_baseline_verified']
            and not value['assessment']['view_velocity_supported'] and not value['automatic_action'] and not value['external_call'] for value in assessments)
        assert len(fixture.wire)==60 and len(fixture.read_wire)==35 and len(fixture.calls)==1
        with fixture.store.transaction() as con:
            syncs=[dict(row) for row in con.execute("SELECT project_id,sync_id FROM native_official_analytics_syncs WHERE status='succeeded' ORDER BY rowid")]
            pubs=[dict(row) for row in con.execute("SELECT project_id,publication_id FROM native_official_publications WHERE status='completed' ORDER BY rowid")]
        history=[fixture.analytics.get(row['project_id'],row['sync_id']) for row in syncs];publications=[fixture.service.get(row['project_id'],row['publication_id']) for row in pubs]
        assert len(history)==10 and len(publications)==6 and [fixture.store.get(identifier) for identifier in project_ids]==before
        fixture.accounts.factories.clear();fixture.service.factories.clear()
        for value in assessments:assert fixture.winners.get(value['project_id'],value['assessment_id'])==value
        write(out/'expected-publications.json',publications);write(out/'expected-analytics-history.json',history);write(out/'expected-winner-history.json',assessments)
        write(out/'expected-projects.json',before);write(out/'expected-jobs.json',jobs);write(out/'expected-journals.json',rows(fixture.store))
        write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire)
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs={identifier:fixture.analytics.costs.summary(identifier) for identifier in project_ids};write(out/'cost-summary.json',costs)
        assert all(record['actual_cost'] is None and not record['paid'] and not record['external_call'] for summary in costs.values() for record in summary['records'])
        assert sum(record['provider']=='official-youtube-analytics' for summary in costs.values() for record in summary['records'])==30
        backup=create_backup(settings(fixture.root),out/'owned-official-winners.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-winners.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(name) and fixture.read_credential.token.encode() not in archive.read(name)
                and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(name) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-winners.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-analytics-controls-flow-n1');old_root=Path('C:/vf-native-fixture-official-analytics-controls-restore-01')
        expected=json.loads((prior/'completed-review.json').read_bytes());old_store=Store(old_root)
        old=NativeOfficialPublications(old_store,NativePublications(old_store,prior/'fixture-capabilities.json',workspace_id=expected['workspace_id']),NativeOfficialAccounts(old_store,workspace_id=expected['workspace_id']))
        old_analytics=NativeOfficialAnalytics(old);assert old.get(expected['project_id'],expected['publication_id'])==expected and analytics_rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        for value in json.loads((prior/'expected-analytics-history.json').read_bytes()):assert old_analytics.get(value['project_id'],value['sync_id'])==value
        write(out/'legacy-signed-controls-replay.json',{'prior_receipt_three_analytics_histories_twenty_journals_exact':True,'external_calls':0})
        sources=['apps/api/app/analytics_channel_policy.py','apps/api/app/analytics_cohort.py']+['services/windows_native/'+name for name in
            ('official_winners.py','official_winner_models.py','official_analytics.py','official_publications.py','backup.py','tests/test_official_winners.py')]+['scripts/north_star_native_official_winners.py']
        write(out/'evidence.json',{'schema_version':'native-official-winner-kernel-rehearsal-v1',
            'explicit_nonplayable_qc_rights_identity_account_platform_oauth_provider_and_clock_fixtures':True,
            'mock_publication_wire_requests':60,'mock_analytics_read_requests':30,'mock_peer_account_lookup_requests':5,'mock_initial_account_lookup_requests':1,'fixture_read_wire_total':35,'signed_http_requests':0,
            'five_distinct_qualified_same_account_query_niche_format_peers':True,'all_four_relative_assessment_states_and_exact_original_replay':True,
            'report_velocity_publishing_time_and_unknown_cost_remain_unavailable':True,'qualified_protocol_mocks_never_real_audience_or_baseline':True,
            'zero_provider_calls_or_paid_media_actions_by_winner_assessment':True,'history_valid_without_factories_credentials_or_runtime_enablement':True,
            'six_receipts_ten_observations_four_assessments_twenty_two_journals_exact_restore':True,'prior_signed_controls_receipt_histories_twenty_journals_exact':True,
            'original_projects_jobs_artifacts_unchanged':True,'archive_excludes_tokens_session_uris':True,
            'real_publications':0,'real_audience_observations':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,
            'accepted_runtime_publishing_or_analytics_enabled':False,'real_oauth_account_media_qc_legal_browser_owner_or_provider_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_WINNER_KERNEL_RECOVERY_PASS','mock_publication_wire_requests':60,'mock_analytics_read_requests':30,'relative_states':4,'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
