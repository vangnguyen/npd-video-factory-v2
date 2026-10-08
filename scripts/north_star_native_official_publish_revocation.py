"""Signed local stop/race/reconciliation/recovery; provider/media are fixtures."""
import argparse,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,write
from scripts.north_star_native_official_publish_lifecycle import rows
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import file_sha,digest
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications,CONSENT_REVOKED
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.tests.test_official_publications_http import OfficialPublicationsHTTPTests

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-publish-revocation-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned revocation restore required')
    return path

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();expected=json.loads((out/'completed-review.json').read_bytes());workspace=expected['workspace_id'];store=Store(root)
    pub=NativePublications(store,out/'fixture-capabilities.json',workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace);journal=NativeOfficialPublications(store,pub,accounts)
    assert journal.get(expected['project_id'],expected['publication_id'])==expected and rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    assert store.get(expected['project_id'])==json.loads((out/'expected-project.json').read_bytes());physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and journal.states()['profiles']==[] and SessionVault(journal).public()['status']=='NOT_CONFIGURED'
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'receipt_all_twelve_journals_project_jobs_artifacts_exact':True,'credential_registry_vault_dispatcher_configured':False,'new_media_or_provider_operations':0,'publishing_enabled':False,'explicit_nonplayable_fixture':True})

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);fixture=OfficialPublicationsHTTPTests();fixture.setUp()
    try:
        before=fixture.server.store.get(fixture.project['id']);parent=fixture.server.publications.get(fixture.project['id'],fixture.parent['publication_id']);http=[]
        def request(method,path,body=None,expected=200):
            status,value,headers=fixture.request(method,path,body);assert status==expected,(path,status,value)
            http.append({'method':method,'path':path,'status':status,'request_sha256':digest(body),'response_sha256':digest(value) if isinstance(value,(dict,list)) else None,'cache_control':headers.get('Cache-Control')});return value
        write(out/'public-config.json',request('GET','/api/connections/official-publishing'))
        value=request('POST',fixture.base,fixture.body().model_dump(mode='json'));base=fixture.base+'/'+value['publication_id'];body={'expected_snapshot_sha256':value['snapshot_sha256']}
        write(out/'frozen-review.json',value);write(out/'separate-consent.json',request('POST',base+'/approve',{**body,'acknowledged_official_publication':True}))
        def state():return request('GET',base+'/state')
        def step(expected=200):return request('POST',base+'/step',{**body,'expected_dispatch_version':state()['dispatch']['version']},expected)
        def renew(key):return request('POST',base+'/renew',{**body,'expected_dispatch_version':state()['dispatch']['version'],'acknowledged_official_publication':True,'request_key':key})
        step();step();first=state();wire_before=len(fixture.wire)
        stopped=request('POST',base+'/revoke',body);assert stopped['failure_code']==CONSENT_REVOKED and stopped['status']=='review_required'
        assert request('POST',base+'/revoke',body)==stopped and state()==first
        step(409);assert len(fixture.wire)==wire_before;write(out/'first-local-stop.json',stopped)
        renew('explicit-revocation-rehearsal-renewal-1');original=fixture.response;raced=[False]
        def response(provider_request):
            result=original(provider_request)
            if provider_request.method=='PUT' and provider_request.content and not raced[0]:
                raced[0]=True;request('POST',base+'/revoke',body)
            return result
        fixture.client.transport.handler=response;step(409);unknown=state()
        assert unknown['dispatch']['phase']=='reconciliation_required' and unknown['dispatch']['acknowledged_bytes']==first['dispatch']['acknowledged_bytes']
        stopped=request('GET',base);assert stopped['failure_code']==CONSENT_REVOKED and stopped['status']=='review_required';write(out/'response-time-stop.json',stopped);write(out/'same-session-unknown-chunk.json',unknown)
        wire_before=len(fixture.wire);step(409);assert len(fixture.wire)==wire_before
        fixture.client.transport.handler=original;renew('explicit-revocation-rehearsal-renewal-2');step();reconciled=state()
        assert reconciled['dispatch']['private_session_ref']==first['dispatch']['private_session_ref'] and reconciled['dispatch']['acknowledged_bytes']==2*fixture.profile.chunk_size
        write(out/'explicit-renewal-existing-session-reconciled.json',reconciled);step()
        completed=request('POST',base+'/poll',{**body,'expected_dispatch_version':state()['dispatch']['version']})
        assert completed['mock_publication_complete'] and not completed['published'] and not completed['receipt']['external_action']
        wire_before=len(fixture.wire);request('POST',base+'/revoke',body,409);assert len(fixture.wire)==wire_before and request('GET',base)==completed
        write(out/'terminal-history.json',request('GET',fixture.base+'?limit=25'));write(out/'terminal-dispatch.json',state())
        assert request('GET','/native-official-publications.mjs')==(ROOT/'apps/studio-web/native-official-publications.mjs').read_bytes()
        assert fixture.server.store.get(fixture.project['id'])==before and fixture.server.publications.get(fixture.project['id'],parent['publication_id'])==parent and fixture.pipeline.calls==0
        assert sum(r['method']=='POST' for r in fixture.wire)==1 and sum(r['bytes']>0 and r['method']=='PUT' for r in fixture.wire)==3 and sum(r['range']=='bytes */524305' for r in fixture.wire)==1
        journals=rows(fixture.server.store);assert sum(r['action']=='official.publication.consent.revoked' for r in journals['native_official_publish_events'])==2
        assert sum(r['status']=='revoked' for r in journals['native_official_publish_approvals'])==2
        write(out/'completed-review.json',completed);write(out/'expected-project.json',before);write(out/'expected-journals.json',journals)
        write(out/'http-summary.json',http);write(out/'mock-wire-summary.json',fixture.wire);write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.server.official_publish_worker.costs.summary(fixture.project['id']);write(out/'cost-summary.json',costs);assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-publish-revocation.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-publish-revocation.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(name) and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(name) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-publish-revocation.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-publish-metadata-flow-n1');expected=json.loads((prior/'completed-review.json').read_bytes());old_store=Store(Path('C:/vf-native-fixture-official-publish-metadata-restore-01'))
        old=NativeOfficialPublications(old_store,NativePublications(old_store,prior/'fixture-capabilities.json',workspace_id=expected['workspace_id']),NativeOfficialAccounts(old_store,workspace_id=expected['workspace_id']))
        assert old.get(expected['project_id'],expected['publication_id'])==expected and rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        write(out/'legacy-metadata-replay.json',{'prior_receipt_and_twelve_journals_exact':True,'credentials_factories_or_dispatchers_configured':False,'external_calls':0})
        sources=['services/windows_native/'+name for name in ('official_publications.py','official_publication_routes.py','access.py','server.py','tests/test_official_publication_revocation.py','tests/test_official_publications_http.py')]
        sources+=['apps/studio-web/native-official-publications.mjs','apps/studio-web/tests/native-official-publications.test.mjs','scripts/north_star_native_official_publish_revocation.py']
        write(out/'evidence.json',{'schema_version':'native-official-publish-revocation-rehearsal-v1','explicit_nonplayable_qc_rights_identity_account_platform_oauth_and_provider_fixtures':True,
            'signed_http_requests':len(http),'mock_wire_requests':len(fixture.wire),'local_stop_and_exact_replay_without_wire':True,'response_time_revocation_sticky_no_invented_ack':True,
            'explicit_renewal_one_init_same_session_reconcile':True,'completed_mock_receipt_preserved_no_remote_delete':True,'original_project_dry_run_jobs_artifacts_unchanged':True,
            'all_twelve_journals_exact_restore':True,'prior_metadata_receipt_twelve_journals_exact':True,'archive_excludes_tokens_session_uris':True,'studio_asset_served_exactly':True,
            'real_publications':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'accepted_runtime_publishing_enabled':False,
            'durable_upload_queue_scheduling_complete':False,'real_oauth_account_media_qc_legal_owner_or_provider_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_PUBLISH_REVOCATION_RECOVERY_PASS','signed_http_requests':len(http),'mock_wire_requests':len(fixture.wire),'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
