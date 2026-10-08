"""Retain and restore explicit nonplayable publication-review contract fixtures.

This is a local infrastructure rehearsal, not a media/HTTP/provider/Owner E2E.
No upload worker or external request is activated by this script.
"""
import argparse,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,write
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import file_sha,WorkflowError
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_models import Action
from services.windows_native.tests.test_official_publications import OfficialPublicationReviewTests

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-publish-review-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Exact fresh owned review recovery root required')
    return path

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external fixture evidence required')
    out.mkdir(parents=True);fixture=OfficialPublicationReviewTests();fixture.setUp()
    try:
        initial=fixture.store.get(fixture.project['id']);value=fixture.create();write(out/'review-created.json',value)
        assert value['approval_id'] is None and value['status']=='awaiting_publish_approval';approved=fixture.approve(value);write(out/'review-approved.json',approved)
        admitted,_,path,dispatch=fixture.service.admission(fixture.project['id'],value['publication_id']);assert dispatch['phase']=='prepared' and dispatch['acknowledged_bytes']==0
        write(out/'prepared-dispatch.json',dispatch)
        try:create_backup(settings(fixture.root),out/'rejected-active-review.zip')
        except WorkflowError as error:assert error.code=='BACKUP_SOURCE_HAS_ACTIVE_OPERATIONS'
        else:raise AssertionError('Pending official consent must prevent offline snapshot')
        cancelled=fixture.service.cancel(fixture.project['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=fixture.principal)
        write(out/'review-cancelled.json',cancelled);assert fixture.store.get(fixture.project['id'])==initial
        assert fixture.calls==['GET'] and not (out/'rejected-active-review.zip').exists()
        write(out/'project-expected.json',initial);write(out/'expected-review.json',cancelled)
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        with fixture.store.transaction() as con:
            grants=[dict(row) for row in con.execute('SELECT * FROM native_official_publish_approvals')]
            events=[dict(row) for row in con.execute('SELECT * FROM native_official_publish_events')]
            assert len(grants)==1 and grants[0]['status']=='revoked' and len(events)==3
            write(out/'expected-grants.json',grants);write(out/'expected-events.json',events)
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        backup=create_backup(settings(fixture.root),out/'owned-official-publish-review.zip');write(out/'backup.json',backup)
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-publish-review.zip',restored,expected_sha256=backup['sha256']))
        args.restore_root=restored;reopen(args)
        names=['services/windows_native/'+n for n in ('official_publications.py','official_publication_models.py','official_publication_registry.py','backup.py','tests/test_official_publications.py')]+['scripts/north_star_native_official_publish_review.py']
        write(out/'evidence.json',{'schema_version':'native-official-publish-review-rehearsal-v1','explicit_nonplayable_render_qc_rights_account_identity_capability_fixtures':True,
            'actual_sqlite_checkpoint_checksums_owner_registry_and_offline_recovery':True,'official_review_rows':1,'separate_grants':1,'revoked_grants':1,'audit_events':3,
            'fixture_account_reads':1,'official_upload_requests':0,'production_media_jobs_created':0,'external_provider_calls':0,'paid_operations':0,
            'pending_backup_rejected':True,'original_fixture_project_jobs_artifacts_unchanged':True,'real_media_qc':False,'real_account_or_platform_verified':False,
            'owner_uat_accepted':False,'publishing_enabled_in_accepted_runtime':False,'http_studio_upload_worker_integrated':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in names},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_PUBLISH_REVIEW_RECOVERY_PASS','official_upload_requests':0,'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();expected=json.loads((out/'expected-review.json').read_bytes());workspace=expected['workspace_id']
    store=Store(root);publications=NativePublications(store,out/'fixture-capabilities.json',workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace)
    service=NativeOfficialPublications(store,publications,accounts);assert service.get(expected['project_id'],expected['publication_id'])==expected
    assert store.get(expected['project_id'])==json.loads((out/'project-expected.json').read_bytes())
    physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    with store.transaction() as con:
        assert [dict(row) for row in con.execute('SELECT * FROM native_official_publish_approvals')]==json.loads((out/'expected-grants.json').read_bytes())
        assert [dict(row) for row in con.execute('SELECT * FROM native_official_publish_events')]==json.loads((out/'expected-events.json').read_bytes())
    assert database_status(store.db)['active_operations']==0 and service.states()['profiles']==[]
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'exact_review_grant_events_project_jobs_artifacts':True,'credentials_or_dispatchers_configured':False,
        'workflow_database_restore':True,'new_media_or_provider_operations':0,'publishing_enabled':False,'explicit_nonplayable_fixture':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true');args=p.parse_args();reopen(args) if args.reopen else run(args)
