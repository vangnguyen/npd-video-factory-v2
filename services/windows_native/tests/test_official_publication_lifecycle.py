"""Explicit consent renewal/backoff/restart fixtures; no real publishing authority."""
import json,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
import httpx
from services.windows_native.tests.test_official_publication_dispatch import OfficialDispatchFixture
from services.windows_native.tests import test_official_publication_worker as worker_fixture
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_models import Renew
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.backup import database_status
from app.youtube_upload import UploadProgress,UploadSession,UNIT
from app.publishing_wire import PublishingWireError

class OfficialLifecycleTests(OfficialDispatchFixture,unittest.TestCase):
    response=worker_fixture.OfficialWorkerTests.response
    step=worker_fixture.OfficialWorkerTests.step
    poll=worker_fixture.OfficialWorkerTests.poll
    upload=worker_fixture.OfficialWorkerTests.upload
    def setUp(self):
        OfficialDispatchFixture.setUp(self);self.wire=[];self.ack=0;self.processing='processed';self.privacy='private';self.mode=None
        self.client.transport.handler=self.response;self.worker=NativeOfficialPublicationWorker(self.service,self.vault)
    def body_renew(self,**changes):
        return Renew.model_validate({'expected_snapshot_sha256':self.value['snapshot_sha256'],'expected_dispatch_version':self.state()['version'],
            'acknowledged_official_publication':True,'valid_for_seconds':900,'request_key':'explicit-owner-consent-renewal-key',**changes})
    def renew(self,body=None):return self.service.renew(self.project['id'],self.value['publication_id'],body or self.body_renew(),principal=self.principal)
    def test_owner_renewal_preserves_session_offset_and_revokes_prior_grant(self):
        self.step();self.step();before=self.state();old=self.service.get(self.project['id'],self.value['publication_id'])['approval_id'];self.clock[0]+=timedelta(seconds=901)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.step()
        wire_before=len(self.wire);renewed=self.renew();self.assertEqual(len(self.wire),wire_before);after=self.state()
        self.assertEqual(after['private_session_ref'],before['private_session_ref']);self.assertEqual(after['acknowledged_bytes'],UNIT);self.assertNotEqual(renewed['approval_id'],old)
        with self.store.transaction() as con:
            self.assertEqual(con.execute('SELECT status FROM native_official_publish_approvals WHERE approval_id=?',(old,)).fetchone()[0],'revoked')
            self.assertEqual(con.execute("SELECT count(*) FROM native_official_publish_approvals WHERE status='active'").fetchone()[0],1)
        self.step();self.step();self.assertTrue(self.poll()['mock_publication_complete']);self.assertEqual(sum(row['method']=='POST' for row in self.wire),1)
    def test_exact_renewal_replay_and_concurrent_requests_issue_one_new_grant(self):
        self.register();body=self.body_renew()
        with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(lambda _:self.renew(body),range(2)))
        self.assertEqual(sum(not v['replayed'] for v in values),1);self.assertEqual(values[0]['approval_id'],values[1]['approval_id'])
        self.assertEqual({k:v for k,v in values[0].items() if k!='replayed'},{k:v for k,v in values[1].items() if k!='replayed'})
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_publish_renewals').fetchone()[0],1)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.renew(body.model_copy(update={'valid_for_seconds':60}))
        self.assertEqual(self.wire,[])
    def test_uncertain_init_active_ticket_and_expired_session_cannot_renew_a_restart_path(self):
        ticket=self.init()
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):self.renew()
        self.service.uncertain(ticket)
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):self.renew()
        self.assertEqual(self.wire,[])
    def test_expired_known_session_cannot_receive_a_grant_for_more_upload_bytes(self):
        ticket=self.init();self.vault.save(ticket,UploadSession('https://www.googleapis.com/upload/youtube/v3/videos?upload_id=EXPLICIT-EXPIRED-FIXTURE',2*UNIT+17),ttl_seconds=60)
        self.clock[0]+=timedelta(seconds=61)
        with self.assertRaisesRegex(WorkflowError,'SESSION_EXPIRED_REVIEW_REQUIRED'):self.renew()
        self.assertEqual(self.wire,[])
    def test_uploaded_video_can_renew_processing_consent_after_private_session_expiry(self):
        self.upload();self.clock[0]+=timedelta(seconds=3601)
        with self.assertRaises(WorkflowError):self.poll()
        # Explicit fresh login and refreshed OAuth fixtures, not automatic renewal.
        from services.windows_native.tests.test_human_identity import fixture
        from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
        from app.publishing_credentials import PublishingOAuthCredential
        raw,registry=fixture('owner',workspace=self.workspace,issued=self.clock[0]-timedelta(seconds=1),expires=self.clock[0]+timedelta(hours=1))
        self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400);self.principal=self.verifier.verify('Bearer '+raw,now=self.clock[0])
        self.credential=PublishingOAuthCredential(self.target,self.clock[0]+timedelta(hours=1),self.credential.scopes,'EXPLICIT-REFRESHED-UPLOAD-FIXTURE-1234567890')
        self.renew();self.assertTrue(self.poll()['mock_publication_complete']);self.assertEqual(sum(row['method']=='POST' for row in self.wire),1)
    def test_owner_revocation_wrong_snapshot_stale_source_and_numeric_ack_cannot_renew(self):
        self.register()
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):self.renew(self.body_renew(expected_snapshot_sha256='f'*64))
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):self.renew(self.body_renew(expected_dispatch_version=self.state()['version']+1))
        with self.assertRaisesRegex(WorkflowError,'RENEWAL_INVALID'):self.renew(self.body_renew().model_copy(update={'acknowledged_official_publication':1}))
        object.__setattr__(self.verifier.registry.tokens[self.principal.token_id],'enabled',False)
        with self.assertRaisesRegex(WorkflowError,'HUMAN_OWNER'):self.renew()
        object.__setattr__(self.verifier.registry.tokens[self.principal.token_id],'enabled',True)
        (self.root/'jobs'/self.job['id']/'final.mp4').write_bytes(b'EXPLICIT CORRUPTED FINAL FIXTURE')
        with self.assertRaises(WorkflowError):self.renew()
        self.assertEqual(self.wire,[])
    def test_rehashed_renewal_flag_cannot_create_initialization_authority(self):
        self.register();renewed=self.renew()
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_official_publish_approvals WHERE approval_id=?',(renewed['approval_id'],)).fetchone();grant=json.loads(row['grant_json']);grant['restart_initialization_authorized']=0
            con.execute('UPDATE native_official_publish_approvals SET grant_json=?,grant_sha256=? WHERE approval_id=?',(json.dumps(grant),digest(grant),renewed['approval_id']))
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.service.admission(self.project['id'],self.value['publication_id'])
    def test_read_rate_limit_is_durable_and_prevents_any_early_secret_read_or_wire_request(self):
        self.client.transport.handler=lambda request:self.limited(request)
        with self.assertRaisesRegex(PublishingWireError,'READ_BACKOFF'):self.step()
        self.assertEqual(self.state()['phase'],'prepared');self.assertEqual(len(self.wire),1)
        self.assertIsNotNone(self.service.state(self.project['id'],self.value['publication_id'])['retry_not_before'])
        with patch.object(self.factory,'credential',side_effect=AssertionError('Backoff must precede secret reads')):
            with self.assertRaisesRegex(WorkflowError,'BACKOFF_ACTIVE'):self.step()
            journal=self.journal(self.factory);restarted=NativeOfficialPublicationWorker(journal,SessionVault(journal,self.vault.directory))
            with self.assertRaisesRegex(WorkflowError,'BACKOFF_ACTIVE'):restarted.step(self.project['id'],self.value['publication_id'],self.state()['version'])
        self.assertEqual(len(self.wire),1);self.clock[0]+=timedelta(seconds=31);self.client.transport.handler=self.response;self.step()
        self.assertEqual(sum(row['method']=='POST' for row in self.wire),1);counts=database_status(self.root/'workflow.sqlite3')['counts'];self.assertEqual(counts['native_official_publish_read_backoffs'],1)
    def limited(self,request):
        self.wire.append({'method':request.method,'path':request.url.path,'range':None,'bytes':0});return httpx.Response(429,headers={'Retry-After':'30'},json={'error':{'reason':'EXPLICIT-LIMIT-FIXTURE'}})
    def test_chunk_retry_after_blocks_account_read_and_cannot_be_bypassed_by_renewal(self):
        self.register();ticket=self.chunk();self.finish(ticket,UploadProgress('uploading',UNIT,retry_after=30));self.ack=UNIT
        self.renew()
        with self.assertRaisesRegex(WorkflowError,'BACKOFF_ACTIVE'):self.step()
        self.assertEqual(self.wire,[]);self.clock[0]+=timedelta(seconds=31);self.step();self.assertEqual(self.state()['acknowledged_bytes'],2*UNIT)
    def test_processing_read_backoff_prevents_early_polls_and_retains_history(self):
        self.upload();original=self.response
        def response(request):return self.limited(request) if request.url.path=='/youtube/v3/videos' else original(request)
        self.client.transport.handler=response
        with self.assertRaisesRegex(PublishingWireError,'READ_BACKOFF'):self.poll()
        before=len(self.wire)
        with self.assertRaisesRegex(WorkflowError,'BACKOFF_ACTIVE'):self.poll()
        self.assertEqual(len(self.wire),before);self.clock[0]+=timedelta(seconds=31);self.client.transport.handler=self.response;self.assertTrue(self.poll()['mock_publication_complete'])
    def test_restart_marks_only_unfinished_owned_costs_unknown_without_decrypt_or_resend(self):
        self.register();ticket=self.chunk();cost=self.worker.costs.begin(project_id=self.project['id'],provider='official-youtube',model=None,operation='upload_chunk.'+ticket.intent_id,request_sha256='c'*64,paid=False,external_call=False)
        foreign=self.worker.costs.begin(project_id=self.project['id'],provider='official-youtube',model=None,operation='unrelated.operation',request_sha256='d'*64,paid=False,external_call=False)
        absent=NativeOfficialPublicationWorker(self.service,SessionVault(self.service));self.clock[0]+=timedelta(seconds=901)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Recovery cannot decrypt')):result=absent.recover()
        self.assertEqual(result['recovered_intents'],1);self.assertEqual(result['unfinished_costs_marked_unknown'],1);self.assertEqual(absent.recover()['unfinished_costs_marked_unknown'],0)
        with self.store.transaction() as con:
            self.assertEqual(con.execute('SELECT status FROM native_cost_operations WHERE id=?',(cost,)).fetchone()[0],'outcome_unknown')
            self.assertEqual(con.execute('SELECT status FROM native_cost_operations WHERE id=?',(foreign,)).fetchone()[0],'dispatch_intent')
        self.assertEqual(self.wire,[]);self.assertEqual(self.state()['phase'],'reconciliation_required')
    def test_source_scope_size_and_backoff_evidence_corruption_fail_closed(self):
        self.register();ticket=self.chunk()
        with self.store.transaction() as con:con.execute('UPDATE native_official_publish_dispatches SET total_bytes=total_bytes+1 WHERE publication_id=?',(self.value['publication_id'],))
        with self.assertRaisesRegex(WorkflowError,'DISPATCH_BINDING_CHANGED'):self.service.uncertain(ticket)

if __name__=='__main__':unittest.main()
