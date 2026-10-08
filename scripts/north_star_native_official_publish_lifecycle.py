"""Nonplayable mock consent/backoff/restart recovery; no real publication."""
import argparse,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,write
from scripts.north_star_native_official_resumable_worker import TABLES as PRIOR_TABLES
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import file_sha,WorkflowError
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.tests.test_official_publication_lifecycle import OfficialLifecycleTests
from app.publishing_wire import PublishingWireError
from datetime import timedelta
TABLES=(*PRIOR_TABLES,'native_official_publish_renewals','native_official_publish_read_backoffs')

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-publish-lifecycle-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned lifecycle restore required')
    return path
def rows(store):
    with store.transaction() as con:return {name:[dict(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in TABLES}

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);fixture=OfficialLifecycleTests();fixture.setUp()
    try:
        before=fixture.store.get(fixture.project['id']);fixture.step();fixture.step();reference=fixture.state()['private_session_ref'];initial_approval=fixture.service.get(fixture.project['id'],fixture.value['publication_id'])['approval_id']
        fixture.client.transport.handler=fixture.limited
        try:fixture.step()
        except PublishingWireError as error:assert error.code=='NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF'
        else:raise AssertionError('Expected explicit mock rate limit')
        wire_count=len(fixture.wire)
        try:fixture.step()
        except WorkflowError as error:assert error.code=='NATIVE_OFFICIAL_PUBLISH_BACKOFF_ACTIVE'
        else:raise AssertionError('Early reads must be blocked')
        assert len(fixture.wire)==wire_count;write(out/'rate-limit-state.json',fixture.service.state(fixture.project['id'],fixture.value['publication_id']))
        fixture.clock[0]+=timedelta(seconds=901);body=fixture.body_renew();renewed=fixture.renew(body);replayed=fixture.renew(body)
        assert replayed['replayed'] and replayed['approval_id']==renewed['approval_id'] and renewed['prior_approval_id']==initial_approval and len(fixture.wire)==wire_count
        assert fixture.state()['private_session_ref']==reference and fixture.state()['acknowledged_bytes']==262144
        write(out/'explicit-consent-renewal.json',renewed);write(out/'renewal-exact-replay.json',replayed)
        fixture.client.transport.handler=fixture.response;fixture.step()
        ticket=fixture.chunk();cost=fixture.worker.costs.begin(project_id=fixture.project['id'],provider='official-youtube',model=None,operation='upload_chunk.'+ticket.intent_id,
            request_sha256='c'*64,external_call=False,paid=False)
        # Explicit unsent interruption fixture. Recovery conservatively calls it
        # unknown; no provider acknowledgement or actual third chunk is invented.
        recovered=fixture.worker.recover();assert recovered['recovered_intents']==recovered['unfinished_costs_marked_unknown']==1
        assert fixture.worker.recover()['unfinished_costs_marked_unknown']==0;write(out/'local-restart-recovery.json',recovered)
        assert fixture.state()['phase']=='reconciliation_required';fixture.step();assert fixture.state()['acknowledged_bytes']==524288;fixture.step();completed=fixture.poll()
        assert completed['mock_publication_complete'] and not completed['published'] and fixture.store.get(fixture.project['id'])==before
        assert sum(row['method']=='POST' for row in fixture.wire)==1 and sum(row['range']=='bytes */524305' for row in fixture.wire)==1
        write(out/'completed-review.json',completed);write(out/'expected-project.json',before);write(out/'expected-journals.json',rows(fixture.store));write(out/'mock-wire-summary.json',fixture.wire)
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()));summary=fixture.worker.costs.summary(fixture.project['id']);write(out/'cost-summary.json',summary)
        assert all(row['actual_cost'] is None and not row['external_call'] and not row['paid'] for row in summary['records'])
        assert sum(row['status']=='outcome_unknown' for row in summary['records'])==1
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        backup=create_backup(settings(fixture.root),out/'owned-official-publish-lifecycle.zip');write(out/'backup.json',backup)
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-publish-lifecycle.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        sources=['services/windows_native/'+name for name in ('official_publications.py','official_publication_models.py','official_publication_worker.py','backup.py','tests/test_official_publication_lifecycle.py')]+['scripts/north_star_native_official_publish_lifecycle.py']
        write(out/'evidence.json',{'schema_version':'native-official-publish-lifecycle-rehearsal-v1','explicit_nonplayable_qc_rights_identity_account_capability_fixtures':True,
            'actual_sqlite_dpapi_scoped_consent_cost_backoff_and_recovery':True,'mock_wire_requests':len(fixture.wire),'initializations':1,'reconciliations':1,'data_chunks':3,
            'read_backoff_observations':1,'early_retry_no_wire_or_credential_resolution':True,'explicit_renewals':1,'original_grant_revoked':True,'exact_renewal_replay_no_new_grant':True,
            'same_session_offset_retained':True,'unsent_interruption_fixture_cost_marked_unknown':True,'new_upload_after_restart':False,
            'workflow_recovery_all_twelve_journals_exact':True,'original_fixture_project_jobs_artifacts_unchanged':True,'unknown_costs_null':True,
            'real_publications':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'http_studio_worker_integrated':False,
            'real_media_qc_legal_owner_account_or_provider_acceptance':False,'source_sha256':{name:file_sha(ROOT/name) for name in sources},
            'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_PUBLISH_LIFECYCLE_RECOVERY_PASS','mock_wire_requests':len(fixture.wire),'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();expected=json.loads((out/'completed-review.json').read_bytes());workspace=expected['workspace_id'];store=Store(root)
    publications=NativePublications(store,out/'fixture-capabilities.json',workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace);journal=NativeOfficialPublications(store,publications,accounts)
    assert journal.get(expected['project_id'],expected['publication_id'])==expected and rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    assert store.get(expected['project_id'])==json.loads((out/'expected-project.json').read_bytes());physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and journal.states()['profiles']==[]
    worker=NativeOfficialPublicationWorker(journal,SessionVault(journal));assert worker.recover()['unfinished_costs_marked_unknown']==worker.recover()['recovered_intents']==0
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'exact_receipt_all_twelve_journals_costs_project_jobs_artifacts':True,
        'history_and_costs_unchanged_by_second_recovery':rows(store)==json.loads((out/'expected-journals.json').read_bytes()),'credentials_vault_or_dispatchers_configured':False,
        'new_media_or_provider_operations':0,'publishing_enabled':False,'explicit_nonplayable_fixture':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
