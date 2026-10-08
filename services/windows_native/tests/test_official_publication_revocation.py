"""Revocable publication grants; all media/provider responses are explicit fixtures."""
import json,unittest
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests.test_official_publication_dispatch import OfficialDispatchFixture
from services.windows_native.tests import test_official_publication_worker as worker_fixture
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_models import Action,Renew
from services.windows_native.official_publications import CONSENT_REVOKED
from services.windows_native.contracts import WorkflowError
from services.windows_native.backup import database_status
from app.youtube_upload import UNIT

class PublicationRevocationTests(OfficialDispatchFixture,unittest.TestCase):
    response=worker_fixture.OfficialWorkerTests.response
    step=worker_fixture.OfficialWorkerTests.step
    poll=worker_fixture.OfficialWorkerTests.poll
    upload=worker_fixture.OfficialWorkerTests.upload
    def setUp(self):
        super().setUp();self.wire=[];self.ack=0;self.processing='processed';self.privacy='private';self.mode=None
        self.client.transport.handler=self.response;self.worker=NativeOfficialPublicationWorker(self.service,self.vault)
    def revoke(self,**changes):
        return self.service.revoke(self.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256'],**changes),principal=self.principal)
    def renew(self):
        return self.service.renew(self.project['id'],self.value['publication_id'],Renew(expected_snapshot_sha256=self.value['snapshot_sha256'],expected_dispatch_version=self.state()['version'],
            acknowledged_official_publication=True,request_key='explicit-after-revocation-renewal'),principal=self.principal)
    def events(self):
        with self.store.transaction() as con:return [dict(r) for r in con.execute("SELECT * FROM native_official_publish_events WHERE action='official.publication.consent.revoked'").fetchall()]
    def test_stop_retains_known_session_offset_version_and_replays_without_more_events_or_wire(self):
        self.step();self.step();before=self.state();source=self.store.get(self.project['id']);calls=len(self.wire)
        first=self.revoke();self.assertEqual(first['status'],'review_required');self.assertEqual(first['failure_code'],CONSENT_REVOKED)
        self.assertEqual(self.state(),before);self.assertEqual(self.revoke(),first);self.assertEqual(len(self.events()),1)
        with patch.object(self.factory,'credential',side_effect=AssertionError('Revocation precedes credentials')):
            with self.assertRaises(WorkflowError):self.step()
            with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.wire),calls);self.assertEqual(self.store.get(self.project['id']),source)
        with self.store.transaction() as con:self.assertEqual(con.execute("SELECT count(*) FROM native_official_publish_approvals WHERE status='active'").fetchone()[0],0)
    def test_source_revision_artifact_configuration_changes_and_expiry_cannot_prevent_local_stop(self):
        self.register();self.clock[0]+=timedelta(seconds=901)
        (self.root/'jobs'/self.job['id']/'final.mp4').write_bytes(b'EXPLICIT CHANGED FIXTURE')
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET revision=revision+1 WHERE id=?',(self.project['id'],))
            con.execute('UPDATE project_dashboard SET archived=1 WHERE project_id=?',(self.project['id'],))
        self.service.factories.clear()
        with patch.object(self.service,'revalidate',side_effect=AssertionError('Stop requires no production preflight')):
            self.assertEqual(self.revoke()['failure_code'],CONSENT_REVOKED)
        self.assertEqual(self.wire,[]);self.assertIsNotNone(self.state()['private_session_ref'])
    def test_wrong_snapshot_scope_role_and_unchecked_payload_cannot_revoke(self):
        bad=Action(expected_snapshot_sha256='f'*64)
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):self.service.revoke(self.project['id'],self.value['publication_id'],bad,principal=self.principal)
        other=self.store.create('Other fixture','No providers')
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.service.revoke(other['id'],self.value['publication_id'],bad,principal=self.principal)
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.service.revoke(self.project['id'],self.value['publication_id'],bad.model_copy(update={'expected_snapshot_sha256':True}),principal=self.principal)
        object.__setattr__(self.verifier.registry.tokens[self.principal.token_id],'enabled',False)
        with self.assertRaisesRegex(WorkflowError,'HUMAN_OWNER'):self.revoke()
        self.assertEqual(self.events(),[]);self.assertEqual(self.state()['phase'],'prepared')
    def test_known_init_response_after_revocation_is_protected_without_any_more_upload_bytes(self):
        original=self.response
        def response(request):
            result=original(request)
            if request.method=='POST':self.revoke()
            return result
        self.client.transport.handler=response;self.step()
        value=self.service.get(self.project['id'],self.value['publication_id']);self.assertEqual(value['failure_code'],CONSENT_REVOKED)
        self.assertEqual(value['status'],'review_required');self.assertEqual(self.state()['phase'],'uploading');self.assertIsNotNone(self.state()['private_session_ref'])
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(len(self.wire),2);self.assertEqual(sum(r['method']=='PUT' for r in self.wire),0)
    def test_chunk_reply_after_stop_is_unknown_then_explicit_renewal_reconciles_same_session(self):
        self.step();reference=self.state()['private_session_ref'];original=self.response
        def response(request):
            result=original(request)
            if request.method=='PUT' and request.content:self.revoke()
            return result
        self.client.transport.handler=response
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(self.state()['phase'],'reconciliation_required');self.assertEqual(self.state()['acknowledged_bytes'],0)
        self.assertEqual(self.service.get(self.project['id'],self.value['publication_id'])['failure_code'],CONSENT_REVOKED)
        calls=len(self.wire)
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(len(self.wire),calls);self.client.transport.handler=original;self.renew();self.step()
        self.assertEqual(self.state()['acknowledged_bytes'],UNIT);self.assertEqual(self.state()['private_session_ref'],reference)
        self.step();self.step();self.assertTrue(self.poll()['mock_publication_complete'])
        self.assertEqual(sum(r['method']=='POST' for r in self.wire),1)
        self.assertEqual(sum(r['range']=='bytes 0-262143/524305' for r in self.wire),1)
    def test_processing_reply_after_stop_cannot_issue_receipt(self):
        self.upload();original=self.response
        def response(request):
            result=original(request)
            if request.url.path=='/youtube/v3/videos':self.revoke()
            return result
        self.client.transport.handler=response
        with self.assertRaises(WorkflowError):self.poll()
        value=self.service.get(self.project['id'],self.value['publication_id']);self.assertIsNone(value['receipt']);self.assertEqual(value['failure_code'],CONSENT_REVOKED)
        calls=len(self.wire)
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.wire),calls)
    def test_restart_retains_revocation_and_never_resends_unfinished_intent(self):
        self.register();self.chunk();self.revoke();result=self.worker.recover();self.assertEqual(result['recovered_intents'],1)
        self.assertEqual(self.service.get(self.project['id'],self.value['publication_id'])['failure_code'],CONSENT_REVOKED)
        self.assertEqual(self.state()['phase'],'reconciliation_required');self.assertEqual(self.wire,[])
        self.assertEqual(database_status(self.root/'workflow.sqlite3')['counts']['native_official_publish_approvals'],1)
        with self.assertRaises(WorkflowError):self.step()
    def test_completed_receipt_is_preserved_without_remote_delete(self):
        self.upload();done=self.poll();before=self.state();calls=len(self.wire)
        with self.assertRaisesRegex(WorkflowError,'ALREADY_COMPLETED'):self.revoke()
        self.assertEqual(self.service.get(self.project['id'],self.value['publication_id']),done);self.assertEqual(self.state(),before);self.assertEqual(len(self.wire),calls)
        self.assertEqual(self.events(),[])
    def test_unapproved_review_cannot_be_relabelled_as_a_revoked_grant(self):
        self.service.cancel(self.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256']),principal=self.principal)
        self.value=self.create(self.body(request_key='explicit-unapproved-revocation-fixture'))
        with self.assertRaisesRegex(WorkflowError,'NO_GRANT_TO_REVOKE'):self.revoke()
        self.assertEqual(self.events(),[]);self.assertEqual(self.wire,[])
