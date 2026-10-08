"""Nonplayable mock-wire upload with actual protected synthetic OAuth tokens."""
import argparse,json,re,sys,zipfile
from pathlib import Path
from datetime import timedelta
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,write
from scripts.north_star_native_official_publish_lifecycle import TABLES
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import file_sha
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_models import Action
from services.windows_native.official_publication_registry import PublishingFactory,Binding,Registry,load as load_registry
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native import official_publication_tokens as tokens
from services.windows_native.tests.test_official_publication_worker import OfficialWorkerTests
from unittest.mock import patch

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-publish-credentials-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned credential restore required')
    return path
def rows(store):
    with store.transaction() as con:return {name:[dict(row) for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in TABLES}

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);fixture=OfficialWorkerTests();fixture.setUp()
    try:
        before=fixture.store.get(fixture.project['id']);old=fixture.value
        cancelled=fixture.service.cancel(fixture.project['id'],old['publication_id'],Action(expected_snapshot_sha256=old['snapshot_sha256']),principal=fixture.principal)
        write(out/'original-unsent-review-cancelled.json',cancelled)
        path=fixture.folder/'protected-publishing'/'fixture.dpapi';value=tokens.AccessToken(target=fixture.target,credential_alias='fixture-youtube-upload',expires_at=fixture.clock[0]+timedelta(hours=1),
            scopes=list(fixture.credential.scopes),token='EXPLICIT-PROTECTED-UPLOAD-TOKEN-FIXTURE-0123456789')
        write(out/'protected-token-receipt.json',tokens.save(path,fixture.root,value))
        binding=Binding(profile=fixture.factory.profile,credential_alias=value.credential_alias,token_file=str(path),gates=fixture.factory.gates)
        registry_path=path.parent/'public-registry.json';registry_path.write_text(Registry(version=1,workspace_id=fixture.workspace,bindings=[binding]).model_dump_json(),encoding='utf-8')
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No default-startup decryption')):
            disabled=load_registry(registry_path,fixture.root,fixture.workspace)[fixture.target.profile_id].public()
            assert disabled['status']=='NOT_CONFIGURED' and not disabled['external_actions_enabled'] and not disabled['gates']['publish_enabled']
        write(out/'default-disabled-factory.json',disabled)
        fixture.factory=PublishingFactory(binding.profile,fixture.root,fixture.workspace,binding=binding,gates=binding.gates,client=fixture.client,registry_file=registry_path,registry_sha256=file_sha(registry_path))
        fixture.service=fixture.journal(fixture.factory);fixture.value=fixture.create(fixture.body(request_key='explicit-protected-upload-review-key'));fixture.approve(fixture.value)
        fixture.vault=SessionVault(fixture.service,fixture.folder/'protected-upload-sessions');fixture.worker=NativeOfficialPublicationWorker(fixture.service,fixture.vault)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No public status decryption')):
            configured=fixture.factory.public();assert configured['status']=='CONFIGURED' and configured['mock'] and not configured['credential_verified'] and not configured['external_actions_enabled']
        write(out/'configured-mock-factory.json',configured)
        from services.windows_native.assemblyai_connection import _dpapi
        count={'publishing_token_decryptions':0,'session_decryptions':0}
        def counted(raw,**kwargs):
            if kwargs.get('decrypt'):
                if kwargs.get('entropy')==tokens.ENTROPY:count['publishing_token_decryptions']+=1
                else:count['session_decryptions']+=1
            return _dpapi(raw,**kwargs)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=counted):fixture.upload();completed=fixture.poll()
        assert completed['mock_publication_complete'] and not completed['published'] and count['publishing_token_decryptions']>0 and count['session_decryptions']==3
        assert fixture.store.get(fixture.project['id'])==before and sum(row['method']=='POST' for row in fixture.wire)==1
        write(out/'credential-use-summary.json',count);write(out/'completed-review.json',completed);write(out/'expected-project.json',before);write(out/'expected-journals.json',rows(fixture.store))
        write(out/'mock-wire-summary.json',fixture.wire);write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        summary=fixture.worker.costs.summary(fixture.project['id']);write(out/'cost-summary.json',summary);assert all(row['actual_cost'] is None and not row['paid'] and not row['external_call'] for row in summary['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-publish-credentials.zip');write(out/'backup.json',backup)
        forbidden=[str(path).encode(),str(registry_path).encode(),value.token.encode(),b'upload_id=EXPLICIT-PRIVATE-FIXTURE']
        with zipfile.ZipFile(out/'owned-official-publish-credentials.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(all(raw not in archive.read(name) for raw in forbidden) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-publish-credentials.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        sources=['services/windows_native/'+name for name in ('official_publication_registry.py','official_publication_tokens.py','tests/test_official_publication_tokens.py')]+['scripts/north_star_native_official_publish_credentials.py']
        write(out/'evidence.json',{'schema_version':'native-official-publish-credentials-rehearsal-v1','explicit_nonplayable_qc_rights_identity_account_capability_and_oauth_fixtures':True,
            'actual_windows_dpapi_private_acl_scoped_token_reads':True,**count,'mock_wire_requests':len(fixture.wire),'initializations':1,'data_chunks':3,'mock_terminal_receipts':1,
            'read_only_and_publishing_tokens_separate':True,'registry_and_factory_public_status_no_decryption_or_wire':True,'default_disabled_before_secret_resolution':True,
            'protected_tokens_registry_private_paths_and_sessions_excluded_from_archive':True,'workflow_recovery_all_twelve_journals_exact':True,'original_fixture_project_jobs_artifacts_unchanged':True,
            'old_unsent_review_cancelled_and_preserved':True,'real_publications':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,
            'accepted_runtime_publishing_enabled':False,'http_studio_worker_integrated':False,'real_oauth_account_media_qc_legal_owner_or_provider_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_PUBLISH_CREDENTIALS_RECOVERY_PASS','mock_wire_requests':len(fixture.wire),**count,'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();expected=json.loads((out/'completed-review.json').read_bytes());workspace=expected['workspace_id'];store=Store(root)
    publications=NativePublications(store,out/'fixture-capabilities.json',workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace);journal=NativeOfficialPublications(store,publications,accounts)
    assert journal.get(expected['project_id'],expected['publication_id'])==expected and rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    assert store.get(expected['project_id'])==json.loads((out/'expected-project.json').read_bytes());physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and journal.states()['profiles']==[] and SessionVault(journal).public()['status']=='NOT_CONFIGURED'
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'exact_receipt_all_twelve_journals_project_jobs_artifacts':True,'protected_credentials_registry_vault_or_dispatchers_configured':False,
        'new_media_or_provider_operations':0,'publishing_enabled':False,'explicit_nonplayable_fixture':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
