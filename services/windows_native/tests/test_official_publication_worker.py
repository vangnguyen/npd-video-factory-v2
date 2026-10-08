"""Bounded official wire worker with explicitly nonplayable fixtures; no real posts."""
from datetime import timedelta
import hashlib,json,unittest
from unittest.mock import patch
import httpx
from services.windows_native.tests.test_official_publication_dispatch import OfficialDispatchFixture
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.contracts import WorkflowError
from app.youtube_upload import UNIT
from app.publishing_wire import PublishingWireError

class OfficialWorkerTests(OfficialDispatchFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.wire=[];self.ack=0;self.processing='processed';self.privacy='private';self.mode=None
        self.client.transport.handler=self.response;self.worker=NativeOfficialPublicationWorker(self.service,self.vault)
    def response(self,request):
        self.wire.append({'method':request.method,'path':request.url.path,'range':request.headers.get('content-range'),'body_sha256':hashlib.sha256(request.content).hexdigest(),'bytes':len(request.content)})
        if request.url.path=='/youtube/v3/channels':
            target='FOREIGN' if self.mode=='foreign-account' else self.target.target_account_id
            return httpx.Response(200,json={'items':[{'id':target}]})
        if request.method=='POST':
            if self.mode=='init-timeout':raise httpx.ReadTimeout('EXPLICIT-SECRET-FIXTURE-MUST-NOT-LEAK',request=request)
            if self.mode=='expire-init':self.clock[0]+=timedelta(seconds=901)
            return httpx.Response(200,headers={'Location':'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=EXPLICIT-PRIVATE-FIXTURE'})
        if request.method=='PUT':
            if request.content:
                start=int(request.headers['content-range'].split(' ')[1].split('-')[0]);self.assertEqual(start,self.ack);self.ack+=len(request.content)
                if self.mode=='chunk-timeout':self.mode=None;raise httpx.ReadTimeout('EXPLICIT-CHUNK-UNCERTAINTY-FIXTURE',request=request)
            if self.ack==2*UNIT+17:return httpx.Response(200,json={'id':'FIXTURE0001'})
            return httpx.Response(308,headers={'Range':f'bytes=0-{self.ack-1}'} if self.ack else {})
        if request.url.path=='/youtube/v3/videos':
            return httpx.Response(200,json={'items':[{'id':'FIXTURE0001','status':{'uploadStatus':self.processing,'privacyStatus':self.privacy},'processingDetails':{'processingStatus':'succeeded' if self.processing=='processed' else 'processing'}}]})
        raise AssertionError('Unexpected endpoint in mock worker fixture')
    def step(self):return self.worker.step(self.project['id'],self.value['publication_id'],self.state()['version'])
    def poll(self):return self.worker.poll_processing(self.project['id'],self.value['publication_id'],self.state()['version'])
    def upload(self):
        self.step()
        for _ in range(3):self.step()
    def test_explicit_mock_upload_has_one_init_three_exact_chunks_and_no_receipt_until_processing(self):
        before=self.store.get(self.project['id']);self.upload();state=self.service.get(self.project['id'],self.value['publication_id'])
        self.assertIsNone(state['receipt']);self.assertFalse(state['published']);self.assertEqual(self.state()['phase'],'uploaded')
        mutations=[row for row in self.wire if row['method'] in ('POST','PUT')];self.assertEqual(len(mutations),4);self.assertEqual(mutations[0]['method'],'POST')
        self.assertEqual([row['range'] for row in mutations[1:]],['bytes 0-262143/524305','bytes 262144-524287/524305','bytes 524288-524304/524305'])
        done=self.poll();self.assertEqual(done['status'],'completed');self.assertFalse(done['published']);self.assertTrue(done['mock_publication_complete']);self.assertTrue(done['receipt']['mock']);self.assertFalse(done['receipt']['external_action']);self.assertIsNone(done['receipt']['remote_url'])
        self.assertEqual(self.store.get(self.project['id']),before);self.assertNotIn(self.credential.token,json.dumps(done));self.assertNotIn('upload_id',json.dumps(done))
        records=self.worker.costs.summary(self.project['id'])['records'];self.assertEqual(len(records),11)
        self.assertTrue(all(row['actual_cost'] is None and row['estimated_cost'] is None and not row['external_call'] and not row['paid'] for row in records));self.assertEqual(len({row['operation'] for row in records}),11)
        with self.assertRaises(WorkflowError):self.step()
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.wire),10)
    def test_lost_init_response_blocks_any_second_post_or_replacement_publication(self):
        self.mode='init-timeout'
        with self.assertRaisesRegex(WorkflowError,'PUBLISHING_NETWORK_OUTCOME_UNKNOWN'):self.step()
        self.assertEqual(self.state()['phase'],'init_unconfirmed')
        with self.assertRaises(WorkflowError):self.step()
        with self.assertRaisesRegex(WorkflowError,'DUPLICATE_REVIEW_REQUIRED'):self.create(self.body(request_key='explicit-lost-init-new-key'))
        self.assertEqual(sum(row['method']=='POST' for row in self.wire),1);self.assertNotIn('SECRET',json.dumps(self.service.get(self.project['id'],self.value['publication_id'])))
        costs=self.worker.costs.summary(self.project['id'])['records'];self.assertEqual(sum(row['status']=='outcome_unknown' for row in costs),1)
    def test_lost_chunk_response_reconciles_existing_session_without_repeating_bytes(self):
        self.step();reference=self.state()['private_session_ref'];self.mode='chunk-timeout'
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(self.state()['phase'],'reconciliation_required');self.assertEqual(self.state()['acknowledged_bytes'],0)
        self.step();self.assertEqual(self.state()['acknowledged_bytes'],UNIT);self.assertEqual(self.state()['private_session_ref'],reference)
        self.step();self.step();done=self.poll();self.assertTrue(done['mock_publication_complete'])
        mutations=[row for row in self.wire if row['method'] in ('POST','PUT')];self.assertEqual(sum(row['method']=='POST' for row in mutations),1);self.assertEqual(sum(row['range']=='bytes */524305' for row in mutations),1)
        self.assertEqual(sum(row['range']=='bytes 0-262143/524305' for row in mutations),1)
    def test_missing_vault_current_owner_or_stale_version_causes_no_provider_calls(self):
        absent=NativeOfficialPublicationWorker(self.service,SessionVault(self.service))
        with self.assertRaisesRegex(WorkflowError,'NOT_CONFIGURED'):absent.step(self.project['id'],self.value['publication_id'],self.state()['version'])
        with self.assertRaisesRegex(WorkflowError,'WORKER_STALE'):self.worker.step(self.project['id'],self.value['publication_id'],self.state()['version']+1)
        self.clock[0]+=timedelta(seconds=901)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.step()
        self.assertEqual(self.wire,[]);self.assertEqual(len(self.worker.costs.summary(self.project['id'])['records']),1)
    def test_foreign_authenticated_channel_prevents_upload_initialization(self):
        self.mode='foreign-account'
        with self.assertRaisesRegex(Exception,'ACCOUNT_NOT_CONFIRMED'):self.step()
        self.assertEqual(self.state()['phase'],'prepared');self.assertEqual(len(self.wire),1);self.assertEqual(self.wire[0]['method'],'GET')
    def test_known_init_response_after_grant_expiry_is_retained_without_sending_more_bytes(self):
        self.mode='expire-init';self.step();self.assertEqual(self.state()['phase'],'uploading');self.assertIsNotNone(self.state()['private_session_ref'])
        self.assertEqual(self.service.get(self.project['id'],self.value['publication_id'])['status'],'review_required')
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(len(self.wire),2);self.assertEqual(sum(row['method']=='PUT' for row in self.wire),0)
    def test_processing_in_progress_and_wrong_visibility_never_create_a_receipt(self):
        self.upload();self.processing='uploaded';pending=self.poll();self.assertEqual(pending['status'],'queued');self.assertIsNone(pending['receipt'])
        self.processing='processed';self.privacy='public';blocked=self.poll();self.assertEqual(blocked['status'],'review_required');self.assertIsNone(blocked['receipt']);self.assertFalse(blocked['published'])
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_publish_processing').fetchone()[0],2)
    def test_numeric_mock_relabelled_receipt_or_changed_remote_binding_fails_closed(self):
        self.upload();done=self.poll();receipt=done['receipt']
        from services.windows_native.contracts import digest
        for changes in ({'mock':1},{'mock':False,'external_action':True},{'remote_post_id':'OTHERID0001'}):
            changed={**receipt,**changes}
            with self.store.transaction() as con:con.execute('UPDATE native_official_publish_receipts SET receipt_json=?,receipt_sha256=?',(json.dumps(changed),digest(changed)))
            with self.assertRaisesRegex(WorkflowError,'RECEIPT_CHANGED'):self.service.get(self.project['id'],self.value['publication_id'])
    def test_artifact_change_after_init_prevents_any_chunk(self):
        self.step();(self.root/'jobs'/self.job['id']/'final.mp4').write_bytes(b'EXPLICIT ALTERED FINAL FIXTURE')
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(sum(row['method']=='PUT' for row in self.wire),0)
    def test_worker_configuration_mutation_and_raw_transport_errors_are_not_authority(self):
        self.worker.vault=SessionVault(self.service,self.folder/'another-vault')
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.step()
        self.assertEqual(self.wire,[])

if __name__=='__main__':unittest.main()
