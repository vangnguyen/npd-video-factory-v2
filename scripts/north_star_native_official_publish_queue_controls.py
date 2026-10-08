"""Signed finite queue/Runner/Studio/recovery; real publishing remains disabled."""
import argparse,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_publish_queue import rows,owned,reopen,write,settings
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue
from services.windows_native.tests.test_official_publication_queue_http import OfficialQueueHTTPTests

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);fixture=OfficialQueueHTTPTests();original_request=fixture.request;http=[]
    def request(method,path,body=None,headers=None):
        status,value,metadata=original_request(method,path,body,headers)
        http.append({'method':method,'path':path,'status':status,'request_sha256':digest(body),'response_sha256':digest(value) if isinstance(value,(dict,list)) else None,'cache_control':metadata.get('Cache-Control')})
        return status,value,metadata
    fixture.request=request;fixture.setUp()
    try:
        before=fixture.server.store.get(fixture.project['id']);parent=fixture.server.publications.get(fixture.project['id'],fixture.parent['publication_id']);queue=fixture.server.official_publish_queue
        assert fixture.server.runner.run_one() is False and fixture.wire==[]
        runtime=request('GET','/api/connections/official-publish-queue')[1];assert runtime['enabled'] and runtime['default_enabled'] is False;write(out/'explicit-runtime-status.json',runtime)
        body=fixture.queue_body();plan=fixture.create_queue(body);assert fixture.wire==[];assert request('POST',fixture.queue_base,body)[1]['idempotent_replay'];write(out/'separate-first-plan.json',plan)
        assert fixture.server.runner.run_one() and not fixture.server.runner.run_one();first=request('GET',fixture.queue_base+'/'+plan['plan_id'])[1]
        assert first['step_count']==1 and len(fixture.wire)==2;write(out/'first-one-due-step.json',first)
        cancel={'expected_policy_sha256':plan['policy_sha256']};path=fixture.queue_base+'/'+plan['plan_id']+'/cancel';stopped=request('POST',path,cancel)[1]
        assert stopped['status']=='cancelled' and request('POST',path,cancel)[1]==stopped;write(out/'cancelled-first-plan.json',stopped)
        fixture.clock[0]+=__import__('datetime').timedelta(seconds=31);assert fixture.server.runner.run_one() is False and len(fixture.wire)==2
        reference=fixture.state_http(fixture.value)['dispatch']['private_session_ref'];replacement=fixture.create_queue(fixture.queue_body(request_key='explicit-signed-queue-replacement-plan'))
        write(out/'separate-replacement-plan.json',replacement)
        for _ in range(4):assert fixture.server.runner.run_one();fixture.clock[0]+=__import__('datetime').timedelta(seconds=30)
        history=request('GET',fixture.queue_base+'?limit=25')[1];assert len(history['items'])==2;completed_plan=request('GET',fixture.queue_base+'/'+replacement['plan_id'])[1]
        assert completed_plan['status']=='completed' and completed_plan['step_count']==4 and fixture.server.runner.run_one() is False
        completed=request('GET',fixture.base+'/'+fixture.value['publication_id'])[1];assert completed['mock_publication_complete'] and not completed['published'] and completed['receipt']['external_action'] is False
        assert fixture.state_http(fixture.value)['dispatch']['private_session_ref']==reference and sum(r['method']=='POST' for r in fixture.wire)==1 and sum(r['method']=='PUT' for r in fixture.wire)==3 and len(fixture.wire)==10
        assert request('POST',fixture.queue_base+'/'+replacement['plan_id']+'/cancel',{'expected_policy_sha256':replacement['policy_sha256']})[1]['status']=='completed'
        for name in ('native-official-publication-queue.mjs','native-official-publications.mjs','native.mjs','native.html','shot-studio.mjs'):
            status,value,_=request('GET','/'+name);assert status==200 and value==(ROOT/'apps/studio-web'/name).read_bytes()
        assert fixture.server.store.get(fixture.project['id'])==before and fixture.server.publications.get(fixture.project['id'],fixture.parent['publication_id'])==parent and fixture.pipeline.calls==0
        write(out/'expected-plan-history.json',history['items']);write(out/'completed-plan.json',completed_plan);write(out/'completed-review.json',completed);write(out/'expected-project.json',before)
        write(out/'expected-journals.json',rows(fixture.server.store));write(out/'http-summary.json',http);write(out/'mock-wire-summary.json',fixture.wire);write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()))
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.server.official_publish_worker.costs.summary(fixture.project['id']);write(out/'cost-summary.json',costs);assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-official-publish-queue-controls.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-official-publish-queue-controls.zip') as archive:
            assert all(not name.endswith(('.dpapi','.part')) for name in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(name) and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(name) for name in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-official-publish-queue-controls.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-publish-queue-kernel-flow-n1');expected=json.loads((prior/'completed-review.json').read_bytes());old_store=Store(Path('C:/vf-native-fixture-official-publish-queue-restore-01'))
        old=NativeOfficialPublications(old_store,NativePublications(old_store,prior/'fixture-capabilities.json',workspace_id=expected['workspace_id']),NativeOfficialAccounts(old_store,workspace_id=expected['workspace_id']))
        old_queue=NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(old,SessionVault(old)))
        assert old.get(expected['project_id'],expected['publication_id'])==expected and rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        for previous in json.loads((prior/'expected-plan-history.json').read_bytes()):assert old_queue.get(previous['project_id'],previous['plan_id'])==previous
        write(out/'legacy-kernel-replay.json',{'preceding_receipt_two_histories_fifteen_journals_exact':True,'credentials_factories_vault_or_queue_configured':False,'external_calls':0})
        sources=['services/windows_native/'+name for name in ('official_publication_queue.py','official_publication_queue_routes.py','server.py','access.py','tests/test_official_publication_queue.py','tests/test_official_publication_queue_http.py')]
        sources+=['apps/studio-web/'+name for name in ('native-official-publication-queue.mjs','native-official-publications.mjs','native.mjs','native.html','shot-studio.mjs','tests/native-official-publication-queue.test.mjs')]+['scripts/north_star_native_official_publish_queue_controls.py']
        write(out/'evidence.json',{'schema_version':'native-official-publish-queue-controls-rehearsal-v1','explicit_nonplayable_qc_rights_identity_account_platform_oauth_provider_and_clock_fixtures':True,
            'signed_http_requests':len(http),'mock_wire_requests':len(fixture.wire),'default_off_and_approval_alone_no_execution':True,'separate_runtime_gate_and_scoped_owner_plan':True,
            'one_step_per_due_runner_call_no_early_retry':True,'cancel_exact_replay_no_future_queue_send_grant_kept':True,'new_separate_plan_same_session_one_init_three_unique_chunks':True,
            'qualified_mock_receipt_two_histories_completed_noop_cancel':True,'all_five_studio_files_served_exactly':True,'original_project_dry_run_jobs_artifacts_unchanged':True,
            'all_fifteen_journals_and_two_histories_exact_restore':True,'prior_kernel_receipt_two_histories_fifteen_journals_exact':True,'archive_excludes_tokens_session_uris':True,
            'real_publications':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'accepted_runtime_publishing_enabled':False,
            'real_oauth_account_media_qc_legal_browser_schedule_owner_or_provider_acceptance':False,'source_sha256':{name:file_sha(ROOT/name) for name in sources},
            'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_OFFICIAL_PUBLISH_QUEUE_CONTROLS_RECOVERY_PASS','signed_http_requests':len(http),'mock_wire_requests':len(fixture.wire),'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
