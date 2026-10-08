"""Finite Native queue kernel/recovery rehearsal; no real media/provider/UAT."""
import argparse,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,write
from scripts.north_star_native_official_publish_lifecycle import TABLES as PRIOR_TABLES,rows as prior_rows
from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue,TABLES as QUEUE_TABLES
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.publications import NativePublications
from services.windows_native.store import Store
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.tests.test_official_publication_queue import OfficialQueueTests
TABLES=(*PRIOR_TABLES,*QUEUE_TABLES)

def rows(store):
    with store.transaction() as con:return {name:[dict(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in TABLES}

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-publish-queue-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned queue-kernel restore required')
    return path

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();expected=json.loads((out/'completed-review.json').read_bytes());workspace=expected['workspace_id'];store=Store(root)
    pub=NativePublications(store,out/'fixture-capabilities.json',workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace);journal=NativeOfficialPublications(store,pub,accounts)
    queue=NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(journal,SessionVault(journal)))
    assert journal.get(expected['project_id'],expected['publication_id'])==expected and rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    for plan in json.loads((out/'expected-plan-history.json').read_bytes()):assert queue.get(plan['project_id'],plan['plan_id'])==plan
    assert store.get(expected['project_id'])==json.loads((out/'expected-project.json').read_bytes());physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and journal.states()['profiles']==[] and not queue.configured() and queue.process() is None
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'receipt_two_plan_histories_fifteen_journals_project_jobs_artifacts_exact':True,'credential_registry_vault_or_queue_enabled':False,'new_media_or_provider_operations':0,'publishing_enabled':False,'explicit_nonplayable_fixture':True})

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);fixture=OfficialQueueTests();fixture.setUp()
    try:
        before=fixture.store.get(fixture.project['id']);parent=fixture.publications.get(fixture.project['id'],fixture.parent['publication_id'])
        assert NativeOfficialPublicationQueue(fixture.worker).process() is None and fixture.queue.process() is None
        plan=fixture.create_queue();write(out/'explicit-first-plan.json',plan);assert fixture.create_queue()['idempotent_replay']
        fixture.queue.process();reference=fixture.state()['private_session_ref'];fixture.advance();fixture.mode='chunk-timeout'
        stopped=fixture.queue.process();assert stopped['status']=='needs_attention' and fixture.state()['phase']=='reconciliation_required' and fixture.state()['acknowledged_bytes']==0
        write(out/'uncertain-first-plan-stopped.json',stopped);wire_before=len(fixture.wire);fixture.advance();assert fixture.queue.process() is None and len(fixture.wire)==wire_before
        replacement=fixture.create_queue(fixture.body_queue(request_key='explicit-queue-rehearsal-new-owner-plan'));write(out/'separate-replacement-plan.json',replacement)
        for _ in range(4):completed_plan=fixture.queue.process();fixture.advance()
        completed=fixture.service.get(fixture.project['id'],fixture.value['publication_id']);assert completed_plan['status']=='completed' and completed['mock_publication_complete'] and not completed['published']
        assert fixture.state()['private_session_ref']==reference and sum(r['method']=='POST' for r in fixture.wire)==1 and sum(r['method']=='PUT' and r['bytes']>0 for r in fixture.wire)==3
        assert sum(r['range']=='bytes */524305' for r in fixture.wire)==1 and len(fixture.wire)==12 and fixture.queue.process() is None
        assert fixture.store.get(fixture.project['id'])==before and fixture.publications.get(fixture.project['id'],fixture.parent['publication_id'])==parent
        history=[fixture.get_queue(plan),fixture.get_queue(replacement)];write(out/'expected-plan-history.json',history);write(out/'completed-review.json',completed)
        write(out/'expected-project.json',before);write(out/'expected-journals.json',rows(fixture.store));write(out/'mock-wire-summary.json',fixture.wire)
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()));physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.worker.costs.summary(fixture.project['id']);write(out/'cost-summary.json',costs);assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-publish-queue.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-publish-queue.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(name) and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(name) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-publish-queue.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-publish-revocation-flow-n1');expected=json.loads((prior/'completed-review.json').read_bytes());old_store=Store(Path('C:/vf-native-fixture-official-publish-revocation-restore-01'))
        old=NativeOfficialPublications(old_store,NativePublications(old_store,prior/'fixture-capabilities.json',workspace_id=expected['workspace_id']),NativeOfficialAccounts(old_store,workspace_id=expected['workspace_id']))
        assert old.get(expected['project_id'],expected['publication_id'])==expected and prior_rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        write(out/'legacy-revocation-replay.json',{'prior_receipt_twelve_journals_exact':True,'credentials_factories_or_dispatchers_configured':False,'external_calls':0})
        sources=['services/windows_native/'+name for name in ('official_publication_queue.py','official_publication_worker.py','backup.py','tests/test_official_publication_queue.py')]+['scripts/north_star_native_official_publish_queue.py']
        write(out/'evidence.json',{'schema_version':'native-official-publish-queue-kernel-rehearsal-v1','explicit_nonplayable_qc_rights_identity_account_platform_oauth_provider_and_clock_fixtures':True,
            'mock_wire_requests':len(fixture.wire),'signed_http_requests':0,'queue_kernel_only_not_studio_or_runner_integration':True,
            'default_off_approval_alone_no_execution':True,'finite_scoped_separate_owner_plans':True,'uncertain_first_plan_no_automatic_retry':True,
            'fresh_explicit_plan_same_session_reconciliation_one_init_unique_chunks':True,'qualified_mock_receipt_two_histories':True,
            'original_project_dry_run_jobs_artifacts_unchanged':True,'all_fifteen_journals_exact_restore':True,'prior_revocation_receipt_twelve_journals_exact':True,'archive_excludes_tokens_session_uris':True,
            'real_publications':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'accepted_runtime_publishing_enabled':False,
            'real_oauth_account_media_qc_legal_owner_or_provider_acceptance':False,'durable_queue_studio_runtime_integration_complete':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_PUBLISH_QUEUE_KERNEL_RECOVERY_PASS','mock_wire_requests':len(fixture.wire),'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
