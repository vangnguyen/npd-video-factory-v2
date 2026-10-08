"""Durable interruption fences with explicitly nonplayable publication fixtures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json,unittest
from unittest.mock import patch
from services.windows_native.tests import test_official_publications as review_fixture
from services.windows_native.official_publication_dispatch import Ticket
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.contracts import WorkflowError
from services.windows_native.backup import database_status
from app.youtube_upload import UploadProgress,UploadSession,UNIT

class OfficialDispatchFixture:
    tearDown=review_fixture.OfficialPublicationReviewTests.tearDown
    journal=review_fixture.OfficialPublicationReviewTests.journal
    body=review_fixture.OfficialPublicationReviewTests.body
    create=review_fixture.OfficialPublicationReviewTests.create
    approve=review_fixture.OfficialPublicationReviewTests.approve
    def setUp(self):
        original=review_fixture.render_fixture
        content=b'EXPLICIT NONPLAYABLE MULTICHUNK PUBLICATION FIXTURE; NO FULL QC\n'
        content+=b'X'*(2*UNIT+17-len(content))
        with patch.object(review_fixture,'render_fixture',side_effect=lambda store:original(store,final_bytes=content)):
            review_fixture.OfficialPublicationReviewTests.setUp(self)
        # Explicit configured mock profile, not a public request/body override.
        profile=self.profile.model_copy(update={'chunk_size':UNIT})
        from services.windows_native.official_publication_registry import PublishingFactory
        self.factory=PublishingFactory(profile,self.root,self.workspace,gates=self.factory.gates,client=self.client,resolver=lambda _:self.credential)
        self.service=self.journal(self.factory);self.value=self.create();self.approve(self.value)
        self.vault=SessionVault(self.service,self.folder/'private-upload-sessions')
    def state(self):return self.service.state(self.project['id'],self.value['publication_id'])['dispatch']
    def init(self):return self.service.begin_intent(self.project['id'],self.value['publication_id'],self.state()['version'],'init')
    def register(self):
        self.vault.save(self.init(),UploadSession('https://www.googleapis.com/upload/youtube/v3/videos?upload_id=EXPLICIT-PRIVATE-FIXTURE',self.value['snapshot']['final_bytes']))
    def chunk(self):
        state=self.state();start=state['acknowledged_bytes'];end=min(start+UNIT,state['total_bytes'])
        return self.service.begin_intent(self.project['id'],self.value['publication_id'],state['version'],'chunk',range_start=start,range_end=end,body_sha256='a'*64)
    def reconcile(self):return self.service.begin_intent(self.project['id'],self.value['publication_id'],self.state()['version'],'reconcile')
    def finish(self,ticket,progress):return self.service.finish_progress(ticket,progress,'b'*64)

class OfficialDispatchTests(OfficialDispatchFixture,unittest.TestCase):
    def test_one_concurrent_init_intent_is_durable_before_any_request(self):
        def attempt(_):
            try:return self.init()
            except WorkflowError as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sum(type(v) is Ticket for v in results),1);self.assertEqual(len(self.calls),1)
        with self.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM native_official_publish_intents').fetchone()[0],1)
        self.assertEqual(self.state()['phase'],'init_intent');self.assertEqual(self.service.get(self.project['id'],self.value['publication_id'])['status'],'running')
    def test_interrupted_init_is_never_reinitialized_even_after_grant_expiry_or_restart(self):
        ticket=self.init();self.clock[0]+=timedelta(seconds=901)
        restarted=self.journal(self.factory);self.assertEqual(restarted.recover()['recovered_intents'],1)
        self.assertEqual(restarted.recover()['recovered_intents'],0);self.assertEqual(self.state()['phase'],'init_unconfirmed')
        with self.assertRaises(WorkflowError):self.init()
        with self.assertRaisesRegex(WorkflowError,'DUPLICATE_REVIEW_REQUIRED'):self.create(self.body(request_key='explicit-interrupted-init-new-key'))
        self.assertEqual(len(self.calls),1)
    def test_interrupted_chunk_requires_same_session_reconcile_before_any_more_bytes(self):
        self.register();ticket=self.chunk();reference=self.state()['private_session_ref'];self.service.recover()
        self.assertEqual(self.state()['phase'],'reconciliation_required');self.assertEqual(self.state()['private_session_ref'],reference)
        with self.assertRaises(WorkflowError):self.chunk()
        reconciled=self.finish(self.reconcile(),UploadProgress('uploading',UNIT))
        self.assertEqual(reconciled['dispatch']['acknowledged_bytes'],UNIT);self.assertEqual(reconciled['dispatch']['private_session_ref'],reference)
        with self.assertRaisesRegex(WorkflowError,'TICKET_STALE'):self.finish(ticket,UploadProgress('uploading',UNIT))
        self.assertEqual(self.chunk().operation,'chunk');self.assertEqual(len(self.calls),1)
    def test_partial_acknowledgement_is_monotonic_aligned_and_never_beyond_sent_window(self):
        self.register();ticket=self.chunk()
        for offset in (True,1,2*UNIT,2*UNIT+17):
            with self.assertRaisesRegex(WorkflowError,'ACKNOWLEDGEMENT_INVALID'):self.finish(ticket,UploadProgress('uploading',offset))
        self.finish(ticket,UploadProgress('uploading',UNIT));ticket=self.chunk()
        with self.assertRaisesRegex(WorkflowError,'ACKNOWLEDGEMENT_INVALID'):self.finish(ticket,UploadProgress('uploading',0))
        self.finish(ticket,UploadProgress('uploading',2*UNIT));ticket=self.chunk()
        done=self.finish(ticket,UploadProgress('uploaded',2*UNIT+17,'FIXTURE0001'))
        self.assertEqual(done['dispatch']['phase'],'uploaded');self.assertFalse(done['published']);self.assertEqual(done['processing_acceptance'],'NOT_CHECKED')
        with self.assertRaisesRegex(WorkflowError,'ALREADY_UPLOADED'):self.reconcile()
    def test_reconcile_cannot_invent_bytes_or_completion_without_a_sent_final_window(self):
        self.register();ticket=self.reconcile()
        with self.assertRaisesRegex(WorkflowError,'ACKNOWLEDGEMENT_INVALID'):self.finish(ticket,UploadProgress('uploaded',2*UNIT+17,'FIXTURE0001'))
        self.finish(ticket,UploadProgress('uploading',0));ticket=self.chunk();self.service.uncertain(ticket)
        reconciled=self.reconcile()
        with self.assertRaisesRegex(WorkflowError,'ACKNOWLEDGEMENT_INVALID'):self.finish(reconciled,UploadProgress('uploading',2*UNIT))
        self.finish(reconciled,UploadProgress('uploading',UNIT))
    def test_expired_session_failure_retains_duplicate_guard_and_never_creates_another_init(self):
        self.register();ticket=self.reconcile();done=self.finish(ticket,UploadProgress('session_expired_requires_review',None))
        self.assertEqual(done['dispatch']['phase'],'review_required')
        with self.assertRaises(WorkflowError):self.init()
        with self.assertRaisesRegex(WorkflowError,'DUPLICATE_REVIEW_REQUIRED'):self.create(self.body(request_key='explicit-expired-session-replacement-key'))
        self.assertEqual(len(self.calls),1)
    def test_provider_backoff_blocks_early_resume_without_erasing_history(self):
        self.register();ticket=self.chunk();self.finish(ticket,UploadProgress('uploading',UNIT,retry_after=30))
        with self.assertRaisesRegex(WorkflowError,'BACKOFF_ACTIVE'):self.chunk()
        self.clock[0]+=timedelta(seconds=31);self.chunk()
        counts=database_status(self.root/'workflow.sqlite3')['counts'];self.assertEqual(counts['native_official_publish_responses'],1);self.assertEqual(counts['native_official_publish_sessions'],1)
    def test_current_owner_and_source_are_checked_before_acknowledgement_admission(self):
        self.register();ticket=self.chunk();self.clock[0]+=timedelta(seconds=901)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.finish(ticket,UploadProgress('uploading',UNIT))
        self.service.uncertain(ticket);self.assertEqual(self.state()['acknowledged_bytes'],0);self.assertEqual(self.state()['phase'],'reconciliation_required')
    def test_forged_stale_or_foreign_ticket_cannot_mutate_an_intent(self):
        ticket=self.init()
        for changes in ({'workspace_id':'wsp_foreign'},{'project_id':'f'*32},{'snapshot_sha256':'f'*64},{'approval_id':'nopa_'+'f'*32},{'intent_id':'f'*32}):
            with self.assertRaises(WorkflowError):self.service.uncertain(replace(ticket,**changes))
        self.assertEqual(self.state()['phase'],'init_intent');self.service.uncertain(ticket)
        with self.assertRaisesRegex(WorkflowError,'TICKET_STALE'):self.service.uncertain(ticket)
        for changes in ({'version':True},{'operation':'delete'},{'publication_id':'invalid'}):
            with self.assertRaises(WorkflowError):replace(ticket,**changes)
    def test_persisted_intent_tampering_and_unbounded_response_values_fail_closed(self):
        self.register();ticket=self.chunk()
        for progress in (UploadProgress('invented',0),UploadProgress('uploading',UNIT,retry_after=True),UploadProgress('reconciliation_required',UNIT),UploadProgress('uploaded',UNIT,'FIXTURE0001')):
            with self.assertRaises(WorkflowError):self.finish(ticket,progress)
        with self.store.transaction() as con:con.execute('UPDATE native_official_publish_intents SET range_end=range_end+1 WHERE intent_id=?',(ticket.intent_id,))
        with self.assertRaisesRegex(WorkflowError,'INTENT_BINDING_CHANGED'):self.service.uncertain(ticket)
        self.assertNotIn('upload_id',json.dumps(self.service.state(self.project['id'],self.value['publication_id'])))

if __name__=='__main__':unittest.main()
