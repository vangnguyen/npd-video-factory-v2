"""Signed HTTP/protected synthetic tokens/mock-wire recovery, never real publishing.

Media, full QC, rights, platform verification, identity and provider replies are
explicit nonplayable fixtures. Private mounts stay outside source/state/archive.
"""
import argparse,json,re,sys,zipfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,write
from scripts.north_star_native_official_publish_lifecycle import TABLES,rows
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import file_sha,digest
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_registry import PublishingFactory,Binding,Registry,load
from services.windows_native import official_publication_tokens as tokens
from services.windows_native.tests import test_official_publications_http as fixture_module

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-publish-controls-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned HTTP controls restore required')
    return path

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);fixture=fixture_module.OfficialPublicationsHTTPTests()
    private={}
    def protected_factory(profile,root,workspace,**options):
        token_path=fixture.folder/'protected-publishing'/'synthetic.dpapi';registry_path=fixture.folder/'protected-publishing'/'registry.json'
        value=tokens.AccessToken(target=fixture.target,credential_alias='youtube-explicit-signed-fixture',expires_at=fixture.credential.expires_at,scopes=list(fixture.credential.scopes),token=fixture.credential.token)
        tokens.save(token_path,root,value);binding=Binding(profile=profile,credential_alias=value.credential_alias,token_file=str(token_path),gates=options['gates'])
        write(registry_path,Registry(version=1,workspace_id=workspace,bindings=[binding]).model_dump(mode='json'));private.update(token_path=token_path,registry_path=registry_path)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Startup/status must not decrypt')):
            disabled=load(registry_path,root,workspace)[profile.target.profile_id].public()
            assert disabled['status']=='NOT_CONFIGURED' and not disabled['external_actions_enabled']
        write(out/'default-disabled-config.json',disabled)
        return PublishingFactory(profile,root,workspace,binding=binding,gates=binding.gates,client=options['client'],registry_file=registry_path,registry_sha256=file_sha(registry_path))
    with patch.object(fixture_module,'PublishingFactory',side_effect=protected_factory):fixture.setUp()
    try:
        before=fixture.server.store.get(fixture.project['id']);http=[]
        def request(method,path,body=None,expected=200):
            status,value,headers=fixture.request(method,path,body)
            http.append({'method':method,'path':path,'status':status,'request_sha256':digest(body),'response_sha256':digest(value) if isinstance(value,(dict,list)) else None,
                'cache_control':headers.get('Cache-Control')})
            assert status==expected,(path,status,value)
            return value
        session=request('GET','/api/session');assert session['capabilities']['native_official_publication_review'] and not session['capabilities']['native_live_publishing']
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Public config must not decrypt')):
            config=request('GET','/api/connections/official-publishing')
            assert config['profiles'][0]['mock'] and not config['profiles'][0]['credential_verified'] and config['session_vault']['status']=='CONFIGURED'
        write(out/'public-config.json',config);write(out/'source-dry-run-page.json',request('GET','/api/projects/'+fixture.project['id']+'/publications?limit=25'))
        write(out/'source-account-check-page.json',request('GET','/api/projects/'+fixture.project['id']+'/account-checks?limit=25'))
        body=fixture.body().model_dump(mode='json');value=request('POST',fixture.base,body);replay=request('POST',fixture.base,body);assert replay['idempotent_replay']
        write(out/'separate-unsent-review.json',value);identity=value['publication_id'];base=fixture.base+'/'+identity
        write(out/'unsent-history.json',request('GET',fixture.base+'?limit=25'));assert fixture.wire==[]
        approved=request('POST',base+'/approve',{'expected_snapshot_sha256':value['snapshot_sha256'],'acknowledged_official_publication':True,'valid_for_seconds':60})
        initial_approval=approved['approval_id'];write(out/'initial-consent.json',approved)
        from services.windows_native.assemblyai_connection import _dpapi
        counts={'publishing_token_decryptions':0,'session_decryptions':0}
        def counted(raw,**kwargs):
            if kwargs.get('decrypt'):
                counts['publishing_token_decryptions' if kwargs.get('entropy')==tokens.ENTROPY else 'session_decryptions']+=1
            return _dpapi(raw,**kwargs)
        def state():return request('GET',base+'/state')
        def step(current,action='step',expected=200):return request('POST',base+'/'+action,{'expected_snapshot_sha256':value['snapshot_sha256'],'expected_dispatch_version':current['dispatch']['version']},expected)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=counted):
            current=state();step(current);step(current,expected=409)
            current=state();reference=current['dispatch']['private_session_ref'];fixture.mode='chunk-timeout';step(current,expected=409)
            current=state();assert current['dispatch']['phase']=='reconciliation_required' and current['dispatch']['acknowledged_bytes']==0
            fixture.clock[0]+=timedelta(seconds=61);before_calls=len(fixture.wire);step(current,expected=409);assert len(fixture.wire)==before_calls
            renewal={'expected_snapshot_sha256':value['snapshot_sha256'],'expected_dispatch_version':current['dispatch']['version'],'acknowledged_official_publication':True,
                'valid_for_seconds':900,'request_key':'explicit-signed-renewal-fixture-key'}
            renewed=request('POST',base+'/renew',renewal);assert renewed['approval_id']!=initial_approval
            assert request('POST',base+'/renew',renewal)['renewal']['replayed'];write(out/'renewed-consent.json',renewed)
            current=state();assert current['dispatch']['private_session_ref']==reference;step(current)
            current=state();assert current['dispatch']['acknowledged_bytes']==262144 and current['dispatch']['private_session_ref']==reference
            step(current);step(state());uploaded=request('GET',base);assert uploaded['receipt'] is None and not uploaded['published']
            write(out/'uploaded-processing-not-confirmed.json',uploaded);completed=step(state(),'poll')
        assert completed['mock_publication_complete'] and not completed['published'] and completed['receipt']['mock'] and not completed['receipt']['external_action']
        assert request('GET',base)==completed;write(out/'terminal-history.json',request('GET',fixture.base+'?limit=25'));write(out/'terminal-dispatch.json',state())
        module=request('GET','/native-official-publications.mjs');assert isinstance(module,bytes) and module== (ROOT/'apps/studio-web/native-official-publications.mjs').read_bytes()
        assert sum(row['method']=='POST' for row in fixture.wire)==1 and len(fixture.wire)==12
        assert fixture.server.store.get(fixture.project['id'])==before and fixture.pipeline.calls==0
        write(out/'completed-review.json',completed);write(out/'expected-project.json',before);write(out/'expected-journals.json',rows(fixture.server.store))
        write(out/'http-summary.json',http);write(out/'mock-wire-summary.json',fixture.wire);write(out/'protected-use-summary.json',counts);write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        summary=fixture.server.official_publish_worker.costs.summary(fixture.project['id']);write(out/'cost-summary.json',summary)
        assert all(row['actual_cost'] is None and not row['paid'] and not row['external_call'] for row in summary['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-publish-controls.zip');write(out/'backup.json',backup)
        forbidden=[str(private['token_path']).encode(),str(private['registry_path']).encode(),fixture.credential.token.encode(),b'upload_id=EXPLICIT-PRIVATE-FIXTURE']
        with zipfile.ZipFile(out/'owned-official-publish-controls.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(all(raw not in archive.read(name) for raw in forbidden) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-publish-controls.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        sources=['services/windows_native/'+name for name in ('server.py','access.py','official_publication_models.py','official_publications.py','official_publication_routes.py','tests/test_official_publications_http.py','tests/test_phase10_http.py')]
        sources+=['apps/studio-web/'+name for name in ('native.html','native.mjs','shot-studio.mjs','native-official-publications.mjs','tests/native-official-publications.test.mjs')]+['scripts/north_star_native_official_publish_controls.py']
        write(out/'evidence.json',{'schema_version':'native-official-publish-controls-rehearsal-v1','explicit_nonplayable_qc_rights_identity_account_capability_and_oauth_fixtures':True,
            'signed_http_requests':len(http),'mock_wire_requests':len(fixture.wire),'one_init_three_exact_data_chunks_one_same_session_reconcile':True,**counts,
            'current_owner_grant_renewal_expired_grant_blocks_before_wire':True,'exact_review_and_renewal_replay_no_extra_calls':True,'stale_step_no_duplicate_init':True,
            'no_startup_status_or_history_decryption_or_sends':True,'protected_tokens_registry_private_paths_and_sessions_excluded_from_archive':True,
            'workflow_recovery_all_twelve_journals_exact':True,'original_fixture_project_jobs_artifacts_unchanged':True,'real_publications':0,'external_provider_calls':0,'paid_operations':0,
            'new_render_or_inference_calls':0,'accepted_runtime_publishing_enabled':False,'signed_native_http_worker_integrated':True,'studio_asset_served_exactly':True,
            'real_oauth_account_media_qc_legal_owner_or_provider_acceptance':False,'source_sha256':{name:file_sha(ROOT/name) for name in sources},
            'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_PUBLISH_CONTROLS_RECOVERY_PASS','signed_http_requests':len(http),'mock_wire_requests':len(fixture.wire),**counts,'external_calls':0,'explicit_nonplayable_fixture':True}))
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
