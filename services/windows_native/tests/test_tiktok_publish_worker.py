"""Local DPAPI/SQLite with actual byte transfer through explicit protocol mocks."""
import copy,json,re,unittest
from datetime import timedelta
from unittest.mock import patch
import httpx
from services.windows_native.tests import test_tiktok_distribution as admission_fixture
from services.windows_native.tests import test_tiktok_creators as creator_fixture
from services.windows_native.tests import test_publications as publication_fixture
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native import tiktok_connection as connection
from services.windows_native import tiktok_publishing as records
from services.windows_native.tiktok_publish_sessions import PREFIX
PUBLISH_ID='v_pub_file~v2-1.123456789'
UPLOAD_TOKEN='EXPLICIT_UPLOAD_URL_SECRET_FIXTURE_0123456'
URI='https://open-upload.tiktokapis.com/video/?upload_id=123456&upload_token='+UPLOAD_TOKEN
class TikTokPublishWorkerTests(unittest.TestCase):
    def setUp(self):
        self.c=admission_fixture.TikTokDistributionAdmissionTests('test_draft_and_dry_run_require_separate_owner_publication_approval');self.c.response=self.response
        if self._testMethodName=='test_original_uploaded_status_after_upload_url_expiry_and_missing_local_file':self.c.token_ttl_hours=2;self.c.owner_ttl_hours=2
        if self._testMethodName.startswith('test_public'):
            self.c.profile_options={'api_client_audited':True};self.c.draft_options={'metadata':{'title':'Explicit public protocol fixture','privacy':'public'},'choices':{'privacy_level':'PUBLIC_TO_EVERYONE','disable_comment':True,'disable_duet':True,'disable_stitch':True,'brand_content_toggle':False,'brand_organic_toggle':False,'is_aigc':True,'music_usage_confirmed':True}}
        if self._testMethodName.startswith('test_merged'):
            self.c.profile_options={'chunk_size':5000000}
            with patch.object(creator_fixture,'render_fixture',side_effect=lambda store:publication_fixture.render_fixture(store,final_bytes=b'F'*10000123)):self.c.setUp()
        else:self.c.setUp()
        self.publish_wires=[];self.mode=None;self.status='PROCESSING_UPLOAD';self.uploaded=None;self.ids=[]
        self.value=self.c.publication();self.c.approve_publication(self.value);self.vault=SessionVault(self.c.official,directory=self.c.folder/'private'/'sessions');self.worker=NativeOfficialPublicationWorker(self.c.official,self.vault)
    def tearDown(self):self.c.tearDown()
    def response(self,request):
        if request.url.path in {'/v2/user/info/','/v2/post/publish/creator_info/query/'}:
            response=creator_fixture.TikTokCreatorFixture.response(self.c,request)
            if getattr(self,'mode',None)=='short-limit' and request.url.path.endswith('/creator_info/query/'):
                data=response.json();data['data']['max_video_post_duration_sec']=2;return httpx.Response(200,json=data)
            if getattr(self,'mode',None)=='rate-creator' and request.url.path.endswith('/creator_info/query/'):
                return httpx.Response(429,headers={'retry-after':'60'},json={'error':{'code':'rate_limit_exceeded'}})
            return response
        self.publish_wires.append({'method':request.method,'path':request.url.path,'body':request.content,'authorization':request.headers.get('authorization')})
        if self.mode=='timeout-init' and request.url.path=='/v2/post/publish/video/init/':raise httpx.ReadTimeout('EXPLICIT UNKNOWN INITIALIZATION',request=request)
        if self.mode=='timeout-chunk' and request.method=='PUT':raise httpx.ReadTimeout(UPLOAD_TOKEN,request=request)
        if request.url.path=='/v2/post/publish/video/init/':
            if self.mode=='expire-init':self.c.clock[0]+=timedelta(seconds=901)
            if self.mode=='revoke-init':self.revoke()
            return httpx.Response(200,json={'error':{'code':'ok'},'data':{'publish_id':PUBLISH_ID,'upload_url':URI}})
        if request.method=='PUT':
            self.assertIsNone(request.headers.get('authorization'));start,end,total=map(int,re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',request.headers['content-range']).groups())
            self.assertEqual(len(request.content),end-start+1);return httpx.Response(201 if end+1==total else 206)
        self.assertEqual(request.url.path,'/v2/post/publish/status/fetch/');self.assertEqual(json.loads(request.content),{'publish_id':PUBLISH_ID})
        if self.mode=='rate-status':return httpx.Response(429,headers={'retry-after':'60'},json={'error':{'code':'rate_limit_exceeded'}})
        data={'status':self.status,'publicaly_available_post_id':self.ids}
        if self.mode=='revoke-status':self.revoke()
        if self.mode=='expire-status':self.c.clock[0]+=timedelta(seconds=901)
        if self.uploaded is not None:data['uploaded_bytes']=self.uploaded
        return httpx.Response(200,json={'error':{'code':'ok'},'data':data})
    def state(self):return self.c.official.state(self.c.project['id'],self.value['publication_id'])
    def step(self):return self.worker.step(self.c.project['id'],self.value['publication_id'],self.state()['dispatch']['version'])
    def poll(self):return self.worker.poll_processing(self.c.project['id'],self.value['publication_id'],self.state()['dispatch']['version'])
    def revoke(self):
        from services.windows_native.official_publication_models import Action
        self.c.official.revoke(self.c.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256']),principal=self.c.principal)
    def renew(self):
        from services.windows_native.official_publication_models import Renew
        return self.c.official.renew(self.c.project['id'],self.value['publication_id'],Renew(expected_snapshot_sha256=self.value['snapshot_sha256'],expected_dispatch_version=self.state()['dispatch']['version'],
            acknowledged_official_publication=True,request_key='explicit-tiktok-status-renewal-fixture-key'),principal=self.c.principal)
    def queue(self):
        from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue,QueueCreate
        queue=NativeOfficialPublicationQueue(self.worker,enabled=True)
        plan=queue.create(self.c.project['id'],self.value['publication_id'],QueueCreate(expected_snapshot_sha256=self.value['snapshot_sha256'],expected_dispatch_version=self.state()['dispatch']['version'],
            acknowledged_background_steps=True,max_steps=6,interval_seconds=30,start_at=self.c.clock[0],deadline=self.c.clock[0]+timedelta(seconds=600),request_key='explicit-tiktok-bounded-queue-fixture-key'),principal=self.c.principal)
        return queue,plan
    def test_actual_session_chunk_processing_private_receipt_and_no_fake_post_id(self):
        first=self.step();self.assertEqual(first['dispatch']['phase'],'uploading');self.assertEqual(first['provider_job']['provider_job_id'],PUBLISH_ID);self.assertIsNone(first['dispatch']['remote_post_id'])
        path=self.vault.path(first['dispatch']['private_session_ref']);self.assertTrue(path.read_bytes().startswith(PREFIX));self.assertNotIn(UPLOAD_TOKEN,path.read_bytes().decode('latin1'))
        upload=self.vault.load(self.c.project['id'],self.value['publication_id']);self.assertEqual(upload.publish_id,PUBLISH_ID)
        second=self.step();self.assertEqual(second['dispatch']['phase'],'uploaded');self.assertIsNone(second['receipt']);self.assertIsNone(second['dispatch']['remote_post_id'])
        self.assertEqual(self.poll()['status'],'queued');self.status='PUBLISH_COMPLETE';done=self.poll();self.assertEqual(done['status'],'completed');self.assertTrue(done['mock_publication_complete']);self.assertFalse(done['published'])
        receipt=done['receipt'];self.assertIsNone(receipt['remote_post_id']);self.assertEqual(receipt['public_post_ids'],[]);self.assertFalse(receipt['public_visibility_confirmed']);self.assertEqual(receipt['provider_job_id'],PUBLISH_ID)
        self.assertNotIn(UPLOAD_TOKEN,json.dumps(done));self.assertEqual(len([x for x in self.publish_wires if x['path'].endswith('/init/')]),1)
    def test_unknown_initialization_never_replays_or_makes_a_second_provider_job(self):
        self.mode='timeout-init'
        with self.assertRaises(WorkflowError):self.step()
        state=self.state();self.assertEqual(state['dispatch']['phase'],'init_unconfirmed');self.assertIsNone(state['provider_job'])
        before=len(self.publish_wires)
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(len(self.publish_wires),before)
    def test_unknown_chunk_reconciles_nullable_progress_without_resending_bytes(self):
        self.step();self.mode='timeout-chunk'
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(self.state()['dispatch']['phase'],'reconciliation_required');self.mode=None;state=self.step()
        self.assertEqual(state['dispatch']['phase'],'reconciliation_required');self.assertEqual(state['dispatch']['acknowledged_bytes'],0)
        self.assertEqual(len([x for x in self.publish_wires if x['method']=='PUT']),1)
        self.assertIsNotNone(state['retry_not_before'])
    def test_wrong_private_prefix_and_original_cost_tamper_cannot_authorize_more_bytes(self):
        state=self.step();path=self.vault.path(state['dispatch']['private_session_ref']);raw=path.read_bytes();path.write_bytes(raw.replace(PREFIX,b'VF-NATIVE-YOUTUBE-UPLOAD-SESSION-1\n',1))
        with self.assertRaises(WorkflowError):self.vault.load(self.c.project['id'],self.value['publication_id'])
        path.write_bytes(raw)
        with self.c.store.transaction() as con:con.execute("UPDATE native_cost_operations SET status='outcome_unknown' WHERE id=?",(state['provider_job']['init_cost_operation_id'],))
        with self.assertRaises(WorkflowError):self.state()
    def test_original_snapshot_and_namespace_mix_are_rejected(self):
        state=self.step()
        with self.c.store.transaction() as con:
            row=con.execute('SELECT * FROM '+records.JOBS).fetchone();data=json.loads(row['job_json']);data['target_binding_sha256']='f'*64
            con.execute('UPDATE '+records.JOBS+' SET job_json=?,job_sha256=?',(json.dumps(data),digest(data)))
        with self.assertRaises(WorkflowError):self.state()
    def test_public_moderation_wait_then_single_actual_post_id(self):
        self.step();self.step();self.status='PUBLISH_COMPLETE';waiting=self.poll();self.assertEqual(waiting['status'],'queued');self.assertIsNone(waiting['receipt'])
        self.ids=[7391000000000000001];done=self.poll();self.assertEqual(done['status'],'completed');self.assertEqual(done['receipt']['remote_post_id'],str(self.ids[0]));self.assertNotEqual(done['receipt']['remote_post_id'],PUBLISH_ID)
        self.assertTrue(done['receipt']['public_visibility_confirmed']);self.assertIsNone(done['receipt']['remote_url'])
    def test_public_multiple_actual_ids_are_retained_without_choosing_one(self):
        self.step();self.step();self.status='PUBLISH_COMPLETE';self.ids=[7391000000000000001,7391000000000000002];done=self.poll()
        self.assertEqual(done['receipt']['public_post_ids'],list(map(str,self.ids)));self.assertIsNone(done['receipt']['remote_post_id']);self.assertIsNone(self.state()['dispatch']['remote_post_id'])
    def test_merged_final_chunk_uses_floor_plan_and_original_exact_bytes(self):
        self.step();first=self.step();self.assertEqual(first['dispatch']['phase'],'uploading');self.assertEqual(first['dispatch']['acknowledged_bytes'],5000000)
        last=self.step();self.assertEqual(last['dispatch']['phase'],'uploaded');chunks=[x for x in self.publish_wires if x['method']=='PUT'];self.assertEqual([len(x['body']) for x in chunks],[5000000,5000123])
        self.assertEqual(b''.join(x['body'] for x in chunks),b'F'*10000123)
    def test_known_initialization_is_retained_after_consent_expires_without_more_bytes(self):
        self.mode='expire-init';state=self.step();self.assertEqual(state['dispatch']['phase'],'uploading');self.assertIsNotNone(state['provider_job'])
        self.assertEqual(self.c.official.get(self.c.project['id'],self.value['publication_id'])['status'],'review_required');before=len(self.publish_wires)
        with patch.object(connection,'load_token',side_effect=AssertionError('No expired-grant decrypt')):
            with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(len(self.publish_wires),before)
    def test_rehashed_job_id_cannot_replace_original_registered_provider_result(self):
        self.step()
        with self.c.store.transaction() as con:
            row=con.execute('SELECT * FROM '+records.JOBS).fetchone();data=json.loads(row['job_json']);data['provider_job_id']='foreign_other_job_123'
            con.execute('UPDATE '+records.JOBS+' SET job_json=?,job_sha256=?',(json.dumps(data),digest(data)))
        with self.assertRaises(WorkflowError):self.state()
    def test_current_creator_duration_is_checked_again_before_initialization(self):
        self.mode='short-limit'
        with self.assertRaisesRegex(WorkflowError,'TIKTOK'):self.step()
        self.assertEqual(self.publish_wires,[]);self.assertEqual(self.state()['dispatch']['phase'],'prepared')
    def test_revocation_during_known_init_keeps_job_and_blocks_subsequent_bytes(self):
        self.mode='revoke-init';state=self.step();self.assertIsNotNone(state['provider_job']);before=len(self.publish_wires)
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(len(self.publish_wires),before);self.assertEqual(self.c.official.get(self.c.project['id'],self.value['publication_id'])['failure_code'],'NATIVE_OFFICIAL_PUBLISH_CONSENT_REVOKED')
    def test_completed_status_received_after_revocation_is_fact_without_more_requests(self):
        self.step();self.step();self.mode='revoke-status';self.status='PUBLISH_COMPLETE';done=self.poll();self.assertEqual(done['status'],'completed');self.assertIsNotNone(done['receipt'])
        before=len(self.publish_wires)
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.publish_wires),before)
    def test_completed_status_received_after_expiry_keeps_original_requested_consent_time(self):
        self.step();self.step();self.mode='expire-status';self.status='PUBLISH_COMPLETE';done=self.poll();self.assertEqual(done['status'],'completed')
        evidence=self.state()['processing_observations'][-1];self.assertNotEqual(evidence['requested_at'],evidence['observed_at']);self.assertTrue(evidence['publish_complete_confirmed'])
    def test_original_uploaded_job_status_and_explicit_renewal_survive_timeline_edit(self):
        self.step();self.step();self.c.fixture_document_drift();self.c.clock[0]+=timedelta(seconds=901)
        with self.assertRaises(WorkflowError):self.poll()
        renewal=self.renew();self.assertFalse(renewal['replayed']);self.status='PUBLISH_COMPLETE';done=self.poll();self.assertEqual(done['status'],'completed')
        self.assertEqual(done['snapshot']['project_revision'],self.value['snapshot']['project_revision']);self.assertNotEqual(self.c.store.get(self.c.project['id'])['revision'],done['snapshot']['project_revision'])
    def test_partial_chunk_reconciliation_requires_review_and_never_sends_another_chunk(self):
        self.step();self.mode='timeout-chunk'
        with self.assertRaises(WorkflowError):self.step()
        self.mode=None;self.uploaded=10;state=self.step();self.assertEqual(state['dispatch']['phase'],'review_required');self.assertEqual(state['dispatch']['failure_code'],'TIKTOK_PARTIAL_CHUNK_REVIEW_REQUIRED')
        before=len(self.publish_wires)
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(len(self.publish_wires),before)
    def test_current_creator_read_backoff_persists_before_init_and_requires_wait(self):
        self.mode='rate-creator'
        with self.assertRaisesRegex(Exception,'NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF'):self.step()
        self.assertEqual(self.state()['dispatch']['phase'],'prepared');self.assertIsNotNone(self.state()['retry_not_before']);self.assertEqual(self.publish_wires,[])
        self.mode=None
        with self.assertRaisesRegex(WorkflowError,'BACKOFF_ACTIVE'):self.step()
        self.c.clock[0]+=timedelta(seconds=61);self.assertEqual(self.step()['dispatch']['phase'],'uploading')
    def test_original_job_status_backoff_after_edit_waits_without_upload_or_private_load(self):
        self.step();self.step();self.c.fixture_document_drift();self.mode='rate-status'
        with patch.object(self.vault,'load',side_effect=AssertionError('Status must not load upload URL')):
            with self.assertRaisesRegex(Exception,'NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF'):self.poll()
            before=len(self.publish_wires);self.mode=None
            with self.assertRaisesRegex(WorkflowError,'BACKOFF_ACTIVE'):self.poll()
            self.assertEqual(len(self.publish_wires),before);self.c.clock[0]+=timedelta(seconds=61);self.status='PUBLISH_COMPLETE';self.assertEqual(self.poll()['status'],'completed')
        self.assertEqual(sum(x['method']=='PUT' for x in self.publish_wires),1)
    def test_unknown_chunk_reconcile_throttle_retains_actual_response_and_no_duplicate_bytes(self):
        self.step();self.mode='timeout-chunk'
        with self.assertRaises(WorkflowError):self.step()
        self.mode='rate-status'
        with patch.object(self.vault,'load',side_effect=AssertionError('Reconcile must not load upload URL')):
            with self.assertRaisesRegex(WorkflowError,'NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF'):self.step()
            self.assertEqual(self.state()['dispatch']['phase'],'reconciliation_required');self.assertIsNotNone(self.state()['retry_not_before']);before=len(self.publish_wires)
            with self.assertRaisesRegex(WorkflowError,'BACKOFF_ACTIVE'):self.step()
            self.assertEqual(len(self.publish_wires),before);self.c.clock[0]+=timedelta(seconds=61);self.mode=None;self.uploaded=self.state()['dispatch']['total_bytes']
            self.assertEqual(self.step()['dispatch']['phase'],'uploaded')
        self.assertEqual(sum(x['method']=='PUT' for x in self.publish_wires),1)
    def test_bounded_queue_completes_original_job_after_project_edit(self):
        original=self.c.store.get(self.c.project['id']);queue,plan=self.queue();self.assertEqual(queue.process()['step_count'],1);self.c.clock[0]+=timedelta(seconds=30)
        self.assertEqual(queue.process()['step_count'],2);self.c.fixture_document_drift();edited=self.c.store.get(self.c.project['id']);self.c.clock[0]+=timedelta(seconds=30);self.status='PUBLISH_COMPLETE'
        done=queue.process();self.assertEqual(done['status'],'completed');self.assertEqual(done['step_count'],3);self.assertIsNone(queue.process());self.assertEqual(self.c.store.get(self.c.project['id']),edited)
        self.assertNotEqual(original['revision'],edited['revision']);self.assertEqual(queue.get(self.c.project['id'],plan['plan_id']),done)
        self.assertEqual(sum(x['path'].endswith('/init/') for x in self.publish_wires),1);self.assertEqual(sum(x['method']=='PUT' for x in self.publish_wires),1)
    def test_queue_cancel_during_known_init_keeps_job_without_more_requests(self):
        from services.windows_native.official_publication_queue import QueueCancel
        queue,plan=self.queue();original=self.response
        def response(request):
            result=original(request)
            if request.url.path.endswith('/video/init/'):queue.cancel(self.c.project['id'],plan['plan_id'],QueueCancel(expected_policy_sha256=plan['policy_sha256']),principal=self.c.principal)
            return result
        self.c.factory.client.transport.handler=response;done=queue.process();self.assertEqual(done['status'],'cancelled');self.assertIsNotNone(self.state()['provider_job']);before=len(self.publish_wires)
        self.c.clock[0]+=timedelta(seconds=30);self.assertIsNone(queue.process());self.assertEqual(len(self.publish_wires),before)
    def test_queue_recovery_of_claimed_step_never_decrypts_or_sends(self):
        queue,plan=self.queue();self.assertIsNotNone(queue.claim())
        with patch.object(connection,'load_token',side_effect=AssertionError('Recovery must not decrypt')):
            self.assertEqual(queue.recover()['recovered_steps'],1);self.assertIsNone(queue.process());self.assertEqual(queue.get(self.c.project['id'],plan['plan_id'])['status'],'needs_attention')
        self.assertEqual(self.publish_wires,[])
    def test_cold_keyless_receipt_preserves_original_job_costs_and_observations(self):
        from services.windows_native.official_publications import NativeOfficialPublications
        self.step();self.step();self.status='PUBLISH_COMPLETE';self.poll();expected=self.state()
        with patch.object(connection,'load_token',side_effect=AssertionError('Historical reads never decrypt')):
            cold=NativeOfficialPublications(self.c.store,self.c.publications,self.c.accounts)
            self.assertEqual(cold.state(self.c.project['id'],self.value['publication_id']),expected);self.assertEqual(cold.recover()['external_calls'],0)
        self.assertIsNone(expected['receipt']['remote_post_id']);self.assertEqual(expected['receipt']['public_post_ids'],[])
    def test_original_uploaded_status_after_upload_url_expiry_and_missing_local_file(self):
        self.step();self.step();self.c.fixture_document_drift();self.c.clock[0]+=timedelta(seconds=3601);self.renew()
        (self.c.store.root/'jobs'/self.c.job['id']/'final.mp4').unlink();self.status='PUBLISH_COMPLETE'
        with patch.object(self.vault,'load',side_effect=AssertionError('Expired upload URL is irrelevant to status')):done=self.poll()
        self.assertEqual(done['status'],'completed');self.assertEqual(sum(x['path'].endswith('/init/') for x in self.publish_wires),1);self.assertEqual(sum(x['method']=='PUT' for x in self.publish_wires),1)
    def test_edit_during_upload_blocks_new_bytes_before_credentials(self):
        self.step();self.c.fixture_document_drift();before=len(self.publish_wires)
        with patch.object(connection,'load_token',side_effect=AssertionError('Changed source must fail before decrypt')):
            with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(len(self.publish_wires),before)
if __name__=='__main__':unittest.main()
