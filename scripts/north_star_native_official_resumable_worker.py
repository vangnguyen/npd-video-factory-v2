"""Retained mock-wire/DPAPI/SQLite recovery; deliberately nonplayable media.

No signed HTTP/Studio/live runtime, real account, rights, QC or Owner acceptance.
Private session vaults remain outside source/state/archives and are not exported.
"""
import argparse,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,write
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import file_sha,WorkflowError
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.tests.test_official_publication_worker import OfficialWorkerTests

TABLES=('native_official_publications','native_official_publish_approvals','native_official_publish_events','native_official_publish_dispatches',
    'native_official_publish_intents','native_official_publish_responses','native_official_publish_sessions','native_official_publish_processing','native_official_publish_receipts','native_cost_operations')

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-resumable-worker-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Exact fresh owned worker restore root required')
    return path

def rows(store):
    with store.transaction() as con:return {name:[dict(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in TABLES}

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);fixture=OfficialWorkerTests();fixture.setUp()
    try:
        before=fixture.store.get(fixture.project['id']);write(out/'created-review.json',fixture.service.get(fixture.project['id'],fixture.value['publication_id']))
        try:create_backup(settings(fixture.root),out/'rejected-active-upload.zip')
        except WorkflowError as error:assert error.code=='BACKUP_SOURCE_HAS_ACTIVE_OPERATIONS'
        else:raise AssertionError('Active official upload must block offline snapshot')
        states=[fixture.step()];reference=fixture.state()['private_session_ref'];fixture.mode='chunk-timeout'
        try:fixture.step()
        except WorkflowError as error:assert error.code=='PUBLISHING_NETWORK_OUTCOME_UNKNOWN'
        else:raise AssertionError('Expected explicit mock chunk timeout')
        states.append(fixture.service.state(fixture.project['id'],fixture.value['publication_id']));assert states[-1]['dispatch']['phase']=='reconciliation_required'
        assert states[-1]['dispatch']['acknowledged_bytes']==0;states.append(fixture.step());assert fixture.state()['acknowledged_bytes']==262144
        states.extend([fixture.step(),fixture.step()]);assert fixture.state()['phase']=='uploaded' and fixture.state()['private_session_ref']==reference
        write(out/'dispatch-states.json',states);assert fixture.service.get(fixture.project['id'],fixture.value['publication_id'])['receipt'] is None
        completed=fixture.poll();assert completed['mock_publication_complete'] and not completed['published'] and completed['receipt']['remote_url'] is None
        write(out/'completed-review.json',completed);write(out/'expected-project.json',before);write(out/'expected-journals.json',rows(fixture.store))
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()));write(out/'mock-wire-summary.json',fixture.wire)
        assert fixture.store.get(fixture.project['id'])==before;assert sum(v['method']=='POST' for v in fixture.wire)==1
        assert sum(v['range']=='bytes 0-262143/524305' for v in fixture.wire)==1 and sum(v['range']=='bytes */524305' for v in fixture.wire)==1
        costs=fixture.worker.costs.summary(fixture.project['id']);write(out/'cost-summary.json',costs)
        assert all(v['actual_cost'] is None and not v['paid'] and not v['external_call'] for v in costs['records'])
        assert sum(v['status']=='outcome_unknown' for v in costs['records'])==1
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        private=list(fixture.vault.directory.glob('*.dpapi'));assert len(private)==1
        write(out/'protected-session-summary.json',{'protected_files':1,'ciphertext_bytes':private[0].stat().st_size,'ciphertext_sha256':file_sha(private[0]),'uri_returned':False,'token_stored':False,'private_path_exported':False})
        backup=create_backup(settings(fixture.root),out/'owned-official-resumable-worker.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-resumable-worker.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(name) and fixture.credential.token.encode() not in archive.read(name) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-resumable-worker.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        sources=['services/windows_native/'+name for name in ('official_publications.py','official_publication_dispatch.py','official_publication_sessions.py','official_publication_worker.py','backup.py',
            'tests/test_official_publication_dispatch.py','tests/test_official_publication_sessions.py','tests/test_official_publication_worker.py','tests/test_publications.py')]+['scripts/north_star_native_official_resumable_worker.py']
        write(out/'evidence.json',{'schema_version':'native-official-resumable-worker-rehearsal-v1','explicit_nonplayable_render_qc_rights_account_identity_platform_fixtures':True,
            'actual_sqlite_dpapi_private_acl_checksum_and_workflow_recovery':True,'mock_wire_requests':len(fixture.wire),'initializations':1,'reconciliations':1,'data_chunks':3,'chunk_not_resent_after_timeout':True,
            'mock_processing_confirmed_receipts':1,'real_publications':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,
            'pending_backup_rejected':True,'private_session_and_tokens_excluded_from_backup':True,'original_fixture_project_jobs_artifacts_unchanged':True,'unknown_costs_null':True,
            'accepted_runtime_publishing_enabled':False,'http_studio_worker_integrated':False,'real_media_qc_or_legal_or_owner_or_account_verified':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_RESUMABLE_WORKER_RECOVERY_PASS','mock_wire_requests':len(fixture.wire),'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();expected=json.loads((out/'completed-review.json').read_bytes());workspace=expected['workspace_id'];store=Store(root)
    publications=NativePublications(store,out/'fixture-capabilities.json',workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace)
    journal=NativeOfficialPublications(store,publications,accounts);vault=SessionVault(journal)
    assert journal.get(expected['project_id'],expected['publication_id'])==expected and rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    assert store.get(expected['project_id'])==json.loads((out/'expected-project.json').read_bytes())
    physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and vault.public()['status']=='NOT_CONFIGURED' and journal.states()['profiles']==[]
    assert journal.recover()['recovered_intents']==0
    try:vault.load(expected['project_id'],expected['publication_id'])
    except WorkflowError as error:assert error.code=='NATIVE_OFFICIAL_SESSION_UNAVAILABLE'
    else:raise AssertionError('Offline history cannot supply private URI or current upload authority')
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'exact_official_receipt_all_journals_costs_project_jobs_artifacts':True,'restored_private_files':0,
        'credentials_or_dispatchers_configured':False,'workflow_database_restore':True,'new_media_or_provider_operations':0,'publishing_enabled':False,'explicit_nonplayable_fixture':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true');args=p.parse_args();reopen(args) if args.reopen else run(args)
