"""Signed scheduled-metadata mock wire and recovery; no real media/provider/UAT."""
import argparse,json,re,sys,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,write
from scripts.north_star_native_official_publish_lifecycle import rows
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import file_sha,digest
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.tests.test_official_publications_http import OfficialPublicationsHTTPTests

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-publish-metadata-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned scheduled-metadata restore required')
    return path

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);fixture=OfficialPublicationsHTTPTests();fixture.setUp()
    try:
        before=fixture.server.store.get(fixture.project['id']);parent=fixture.server.publications.get(fixture.project['id'],fixture.parent['publication_id'])
        at=fixture.clock[0]+timedelta(seconds=120);scheduled=[at];initial=[];original=fixture.response
        def response(request):
            if request.method=='POST':initial.append(json.loads(request.content))
            result=original(request)
            if request.url.path=='/youtube/v3/videos' and scheduled[0] is not None:
                value=result.json();value['items'][0]['status']['publishAt']=scheduled[0].astimezone(timezone.utc).isoformat();return httpx.Response(200,json=value)
            return result
        fixture.client.transport.handler=response;http=[]
        def request(method,path,body=None,expected=200):
            status,value,headers=fixture.request(method,path,body);assert status==expected,(path,status,value)
            http.append({'method':method,'path':path,'status':status,'request_sha256':digest(body),'response_sha256':digest(value) if isinstance(value,(dict,list)) else None,'cache_control':headers.get('Cache-Control')})
            return value
        write(out/'public-config.json',request('GET','/api/connections/official-publishing'))
        metadata={**parent['snapshot']['request']['metadata'],'title':'Explicit scheduled educational publication fixture','scheduled_at':at.isoformat()}
        body=fixture.body(metadata=metadata).model_dump(mode='json');value=request('POST',fixture.base,body);assert request('POST',fixture.base,body)['idempotent_replay']
        assert value['snapshot']['metadata_source']=='explicit_owner_request' and datetime.fromisoformat(value['snapshot']['metadata']['scheduled_at'].replace('Z','+00:00'))==at
        write(out/'frozen-scheduled-review.json',value);base=fixture.base+'/'+value['publication_id']
        write(out/'separate-consent.json',request('POST',base+'/approve',{'expected_snapshot_sha256':value['snapshot_sha256'],'acknowledged_official_publication':True}))
        def state():return request('GET',base+'/state')
        def action(current,name='step',expected=200):return request('POST',base+'/'+name,{'expected_snapshot_sha256':value['snapshot_sha256'],'expected_dispatch_version':current['dispatch']['version']},expected)
        action(state())
        for _ in range(3):action(state())
        uploaded=request('GET',base);assert uploaded['receipt'] is None and not uploaded['published'];write(out/'uploaded-not-processing-confirmed.json',uploaded)
        current=state();pending=action(current,'poll');assert pending['status']=='queued' and pending['receipt'] is None;write(out/'private-future-schedule-pending.json',pending)
        state();before_wire=len(fixture.wire);action(current,'poll',409);assert len(fixture.wire)==before_wire
        fixture.clock[0]+=timedelta(seconds=121);fixture.privacy='public';scheduled[0]=None;completed=action(state(),'poll')
        assert completed['mock_publication_complete'] and not completed['published'] and not completed['receipt']['external_action']
        assert request('GET',base)==completed;write(out/'terminal-history.json',request('GET',fixture.base+'?limit=25'));write(out/'terminal-dispatch.json',state())
        module=request('GET','/native-official-publications.mjs');assert module==(ROOT/'apps/studio-web/native-official-publications.mjs').read_bytes()
        assert len(initial)==1 and initial[0]['status']['publishAt']==at.isoformat().replace('+00:00','Z') and len(fixture.wire)==12
        assert fixture.server.store.get(fixture.project['id'])==before and fixture.server.publications.get(fixture.project['id'],parent['publication_id'])==parent and fixture.pipeline.calls==0
        write(out/'initial-wire-metadata.json',initial[0]);write(out/'completed-review.json',completed);write(out/'expected-project.json',before);write(out/'expected-journals.json',rows(fixture.server.store))
        write(out/'http-summary.json',http);write(out/'mock-wire-summary.json',fixture.wire);write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.server.official_publish_worker.costs.summary(fixture.project['id']);write(out/'cost-summary.json',costs);assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-publish-metadata.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-publish-metadata.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(name) and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(name) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-publish-metadata.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-publish-controls-flow-n2');expected=json.loads((prior/'completed-review.json').read_bytes())
        old_store=Store(Path('C:/vf-native-fixture-official-publish-controls-restore-02'));pub=NativePublications(old_store,prior/'fixture-capabilities.json',workspace_id=expected['workspace_id']);accounts=NativeOfficialAccounts(old_store,workspace_id=expected['workspace_id'])
        old=NativeOfficialPublications(old_store,pub,accounts)
        assert old.get(expected['project_id'],expected['publication_id'])==expected and rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        write(out/'legacy-controls-replay.json',{'prior_control_receipt_and_all_twelve_journals_exact':True,'credentials_factories_or_dispatchers_configured':False,'external_calls':0})
        sources=['services/windows_native/'+name for name in ('official_publication_models.py','official_publications.py','official_publication_worker.py','tests/test_official_publication_metadata.py')]
        sources+=['apps/studio-web/native-official-publications.mjs','apps/studio-web/tests/native-official-publications.test.mjs','scripts/north_star_native_official_publish_metadata.py']
        write(out/'evidence.json',{'schema_version':'native-official-publish-metadata-rehearsal-v1','explicit_nonplayable_qc_rights_identity_account_capability_oauth_and_clock_fixtures':True,
            'signed_http_requests':len(http),'mock_wire_requests':len(fixture.wire),'one_init_three_exact_data_chunks_two_processing_observations':True,
            'explicit_metadata_frozen_in_review_and_wire':True,'private_future_schedule_not_terminal':True,'observed_post_schedule_public_release_mock_receipt':True,
            'stale_processing_read_no_extra_request':True,'original_project_dry_run_job_and_artifacts_unchanged':True,'workflow_recovery_all_twelve_journals_exact':True,
            'prior_pre_metadata_receipt_and_twelve_journals_exact':True,'credentials_and_session_uris_excluded_from_archive':True,'studio_asset_served_exactly':True,
            'real_publications':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'accepted_runtime_publishing_enabled':False,
            'durable_upload_queue_scheduling_complete':False,'real_oauth_account_media_qc_legal_owner_or_provider_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_PUBLISH_METADATA_RECOVERY_PASS','signed_http_requests':len(http),'mock_wire_requests':len(fixture.wire),'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();expected=json.loads((out/'completed-review.json').read_bytes());workspace=expected['workspace_id'];store=Store(root)
    pub=NativePublications(store,out/'fixture-capabilities.json',workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace);journal=NativeOfficialPublications(store,pub,accounts)
    assert journal.get(expected['project_id'],expected['publication_id'])==expected and rows(store)==json.loads((out/'expected-journals.json').read_bytes())
    assert store.get(expected['project_id'])==json.loads((out/'expected-project.json').read_bytes());physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
    assert database_status(store.db)['active_operations']==0 and journal.states()['profiles']==[] and SessionVault(journal).public()['status']=='NOT_CONFIGURED'
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'exact_receipt_all_twelve_journals_project_jobs_artifacts':True,'protected_credentials_registry_vault_or_dispatchers_configured':False,'new_media_or_provider_operations':0,'publishing_enabled':False,'explicit_nonplayable_fixture':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
