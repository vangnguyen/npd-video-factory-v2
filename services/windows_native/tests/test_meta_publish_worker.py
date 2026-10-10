"""Explicit Meta/Owner/platform/nonplayable-media mocks with local DPAPI/SQLite."""
import copy,json,unittest
from datetime import timedelta
from urllib.parse import parse_qs
from unittest.mock import patch
import httpx
from services.windows_native.tests import test_meta_distribution as admission_fixture
from services.windows_native.tests.media_delivery_fixture import FixtureStore
from services.windows_native.meta_distribution import NativeMetaPublishingFactory,ExecutionCapability
from services.windows_native.official_publication_models import MetaExecutionCreate,Gates,Action,Renew
from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue,QueueCreate,QueueCancel
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.publishing_media_delivery import NativeMediaDeliveryFactory,NativePublishingMediaDelivery,Create
from services.windows_native import meta_publishing as execution
from services.windows_native.contracts import WorkflowError,digest
from app.publishing_media_delivery import StorageProfile


def fixture(platform):
    class Case(admission_fixture.MetaAdmissionTests):
        PLATFORM=platform
        def response(self,request):
            self.calls.append((request.method,request.url.path));body=parse_qs(request.content.decode()) if request.content else {};path=request.url.path
            if not hasattr(self,'mutations'):self.mutations=[];self.finish_sent=False;self.container_status='FINISHED';self.lose=None;self.after=None;self.status_override=None
            if request.method=='POST':
                self.mutations.append((path,body))
                if path.endswith('/media'):data={'id':'34567'};name='init'
                elif path.endswith('/media_publish'):data={'id':'45678'};name='finish'
                elif request.url.host=='rupload.facebook.com':data={'success':True};name='transfer'
                elif body.get('upload_phase')==['start']:data={'video_id':'34567','upload_url':'https://rupload.facebook.com/video-upload/v24.0/34567'};name='init'
                else:self.finish_sent=True;data={'success':True};name='finish'
                if self.after:self.after(name)
                if self.lose==name:raise httpx.ReadTimeout('EXPLICIT PRIVATE RESPONSE LOSS FIXTURE',request=request)
            elif path.endswith('/me'):data={'id':'12345','instagram_business_account':{'id':'23456'}}
            elif path.endswith('/23456'):data={'id':'23456'}
            elif self.PLATFORM=='instagram_reels':data={'id':'34567','status_code':self.container_status}
            else:
                data={'id':'34567','status':{'video_status':'ready' if self.finish_sent else 'processing','uploading_phase':{'status':'complete'},
                    'processing_phase':{'status':'complete' if self.finish_sent else 'not_started'},'publishing_phase':{'status':'complete' if self.finish_sent else 'not_started'}}}
            if self.status_override is not None and request.method=='GET' and path.endswith('/34567'):return self.status_override(request)
            return httpx.Response(200,json=data)
    value=Case('test_separate_owner_grant_binds_current_account_dry_run_final_and_metadata_without_wire');value.setUp();return value


class MetaPublishWorkerTests(unittest.TestCase):
    PLATFORM='instagram_reels'
    def setUp(self):
        self.c=fixture(self.PLATFORM);self.profile=StorageProfile('https://storage-fixture.invalid','vf-media-fixture','us-east-1','publishing-media-fixture')
        self.storage=FixtureStore(self.profile,lambda:self.c.clock[0]);self.media_factory=NativeMediaDeliveryFactory(self.profile,self.c.root,self.c.workspace,enabled=True,
            directory=self.c.folder/'private'/'media',wire=self.storage.wire,clock=lambda:self.c.clock[0])
        self.factory=NativeMetaPublishingFactory(self.c.connection,owner_enabled=True,gates=Gates(publish_enabled=True,external_execution_enabled=True,owner_gate_enabled=True),
            execution=ExecutionCapability(media_configuration_sha256=self.media_factory.sha256))
        self.service=self.c.journal(self.factory);self.media=NativePublishingMediaDelivery(self.service,factory=self.media_factory)
        self.worker=NativeOfficialPublicationWorker(self.service,SessionVault(self.service,self.c.folder/'private'/'sessions'),media_delivery=self.media)
        body={**self.c.body().model_dump(mode='json'),'schema_version':'native-official-meta-publication-request-v2',
            'expected_configuration_sha256':self.factory.sha256,'expected_media_configuration_sha256':self.media_factory.sha256}
        self.publication=self.service.create(self.c.project['id'],MetaExecutionCreate.model_validate(body),principal=self.c.principal)[0]
        self.c.service=self.service;self.c.approve(self.publication)
        request=Create(publication_id=self.publication['publication_id'],expected_publication_snapshot_sha256=self.publication['snapshot_sha256'],
            expected_configuration_sha256=self.media_factory.sha256,acknowledged_external_media_delivery=True,request_key='explicit-meta-worker-media-delivery')
        self.delivery=self.media.create(self.c.project['id'],request,principal=self.c.principal)[0]
        self.delivery=self.media.process(self.c.project['id'],self.delivery['delivery_id']);self.assertEqual(self.delivery['status'],'succeeded',self.delivery['failure_code'])
        self.binding=execution.bind_media(self.service,self.media,self.c.project['id'],self.publication['publication_id'],execution.MediaBind(
            expected_snapshot_sha256=self.publication['snapshot_sha256'],expected_dispatch_version=1,media_delivery_id=self.delivery['delivery_id'],
            expected_media_snapshot_sha256=self.delivery['snapshot_sha256'],acknowledged_exact_media_selection=True,request_key='explicit-meta-worker-exact-media-selection'),principal=self.c.principal)[0]
    def tearDown(self):self.c.tearDown()
    def state(self):return self.service.state(self.c.project['id'],self.publication['publication_id'])
    def step(self):return self.worker.step(self.c.project['id'],self.publication['publication_id'],self.state()['dispatch']['version'])
    def complete(self):
        for _ in range(8):
            value=self.step()
            if value['receipt'] is not None:return value
        self.fail('Explicit fixture flow did not complete')
    def test_exact_original_video_one_async_job_phase_order_nullable_costs_and_private_history(self):
        before=self.c.store.get(self.c.project['id']);result=self.complete();self.assertFalse(result['published']);self.assertTrue(result['mock_publication_complete'])
        self.assertEqual(result['receipt']['remote_post_id'],'34567' if self.PLATFORM=='facebook' else '45678');self.assertEqual(self.storage.puts,1)
        self.assertEqual(result['provider_job']['provider_job_id'],'34567');self.assertEqual(self.c.store.get(self.c.project['id']),before)
        self.assertEqual(len(self.c.mutations),3 if self.PLATFORM=='facebook' else 2);self.assertNotIn('X-Amz-',json.dumps(result));self.assertNotIn(self.c.token,json.dumps(result))
        with self.assertRaises(WorkflowError):self.step()
        costs=[v for v in self.worker.costs.summary(self.c.project['id'])['records'] if v['provider']=='official-'+self.PLATFORM]
        self.assertTrue(costs);self.assertTrue(all(v['actual_cost'] is None and not v['external_call'] for v in costs))
    def test_unknown_init_cannot_make_second_provider_job_even_with_same_worker(self):
        self.c.lose='init';result=self.step();self.assertEqual(result['dispatch']['phase'],'meta_init_unconfirmed');calls=list(self.c.calls)
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(self.c.calls,calls);self.assertEqual(len(self.c.mutations),1);self.assertIsNone(result['provider_job'])
    def test_unknown_finish_is_never_repeated_or_given_a_fabricated_post_id(self):
        self.c.lose='finish'
        for _ in range(6):
            result=self.step()
            if result['dispatch']['phase']=='meta_finish_unconfirmed':break
        self.assertEqual(result['dispatch']['phase'],'meta_finish_unconfirmed');self.assertIsNone(result['receipt'])
        result=self.step();self.assertEqual(sum(1 for _,b in self.c.mutations if b.get('creation_id') or b.get('upload_phase')==['finish']),1)
        if self.PLATFORM=='instagram_reels':self.assertIsNone(result['receipt'])
        else:self.assertEqual(result['receipt']['remote_post_id'],'34567')
    def test_finish_known_after_consent_expires_preserves_response_without_more_requests(self):
        self.c.after=lambda name:self.c.clock.__setitem__(0,self.c.clock[0]+timedelta(seconds=901)) if name=='finish' else None
        for _ in range(6):
            result=self.step()
            if result['dispatch']['phase'] in {'uploaded','meta_processing'} and self.c.finish_sent or result['receipt']:break
        calls=list(self.c.calls)
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(self.c.calls,calls)
        self.assertTrue(result['receipt'] is not None if self.PLATFORM=='instagram_reels' else result['receipt'] is None)
    def test_revocation_blocks_credentials_and_network_before_next_step(self):
        self.step();self.service.revoke(self.c.project['id'],self.publication['publication_id'],Action(expected_snapshot_sha256=self.publication['snapshot_sha256']),principal=self.c.principal)
        calls=list(self.c.calls)
        with patch('services.windows_native.meta_connection.load_token',side_effect=AssertionError('Reject before credential decrypt')):
            with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(self.c.calls,calls)
    def test_existing_job_status_and_finish_keep_original_video_after_later_project_edit(self):
        self.step()
        if self.PLATFORM=='facebook':self.step()
        with self.c.store.transaction() as con:
            document=copy.deepcopy(self.c.project['document']);document['prompt']='Explicit later edit of unrelated current timeline'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document),self.c.project['id']));self.c.store.version(con,self.c.project['id'])
        result=self.complete();self.assertEqual(result['provider_job']['provider_job_id'],'34567');self.assertEqual(len(self.c.mutations),3 if self.PLATFORM=='facebook' else 2)
    def test_current_media_mode_and_publication_source_are_required(self):
        self.worker.meta.media.factory.enabled=False
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(self.c.mutations,[])
    def test_status_rate_limit_wait_is_durable_and_never_becomes_a_mutation_retry(self):
        self.step()
        if self.PLATFORM=='facebook':self.step()
        self.c.status_override=lambda request:httpx.Response(429,headers={'Retry-After':'60'},json={'error':{'message':'explicit private provider fixture'}})
        result=self.step();self.assertIsNotNone(result['retry_not_before']);calls=list(self.c.calls)
        with self.assertRaisesRegex(WorkflowError,'BACKOFF_ACTIVE'):self.step()
        self.assertEqual(self.c.calls,calls);self.c.status_override=None;self.c.clock[0]+=timedelta(seconds=61)
        self.assertEqual(self.complete()['provider_job']['provider_job_id'],'34567')
    def submitted(self):
        self.step()
        if self.PLATFORM=='facebook':self.step()
    def queue(self,**changes):
        queue=NativeOfficialPublicationQueue(self.worker,enabled=True)
        body=QueueCreate(expected_snapshot_sha256=self.publication['snapshot_sha256'],expected_dispatch_version=self.state()['dispatch']['version'],
            acknowledged_background_steps=True,max_steps=10,interval_seconds=30,start_at=self.c.clock[0],deadline=self.c.clock[0]+timedelta(seconds=600),
            request_key='explicit-meta-shared-background-queue',**changes)
        return queue,queue.create(self.c.project['id'],self.publication['publication_id'],body,principal=self.c.principal)
    def test_recovery_before_wire_keeps_unknown_init_without_keys_or_second_job(self):
        send=self.worker.send
        def crash(*args,**kwargs):
            if args[6]=='meta_init':raise SystemExit('Explicit crash before dispatch')
            return send(*args,**kwargs)
        with patch.object(self.worker,'send',side_effect=crash):
            with self.assertRaises(SystemExit):self.step()
        calls=list(self.c.calls)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No recovery keys')):
            self.assertEqual(self.worker.recover()['recovered_meta_intents'],1)
            self.assertEqual(self.worker.recover()['recovered_meta_intents'],0)
        result=self.state();self.assertEqual(result['dispatch']['phase'],'meta_init_unconfirmed');self.assertIsNone(result['provider_job'])
        self.assertEqual(self.c.calls,calls);self.assertEqual(self.c.mutations,[])
        with self.assertRaises(WorkflowError):self.step()
    def test_recovery_of_cost_intent_and_known_response_never_fabricates_job_or_replays_init(self):
        settle=self.worker.costs.settle
        def crash(identity,**kwargs):
            with self.c.store.transaction() as con:operation=con.execute('SELECT operation FROM native_cost_operations WHERE id=?',(identity,)).fetchone()[0]
            if operation.startswith('meta_init.'):raise SystemExit('Explicit crash before cost settlement')
            return settle(identity,**kwargs)
        with patch.object(self.worker.costs,'settle',side_effect=crash):
            with self.assertRaises(SystemExit):self.step()
        calls=list(self.c.calls)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No recovery keys')):
            self.assertEqual(self.worker.recover()['recovered_meta_intents'],1)
        result=self.state();self.assertEqual(result['dispatch']['phase'],'meta_init_unconfirmed');self.assertIsNone(result['provider_job'])
        self.assertEqual(self.c.calls,calls);self.assertEqual(len(self.c.mutations),1)
        costs=self.worker.costs.summary(self.c.project['id'])['records'];self.assertEqual(next(c['status'] for c in costs if c['operation'].startswith('meta_init.')),'outcome_unknown')
    def test_recovery_of_settled_finish_preserves_original_job_and_cannot_invent_instagram_post(self):
        self.submitted();self.step();self.assertEqual(self.state()['dispatch']['phase'],'meta_finish_ready')
        with patch.object(execution,'finish',side_effect=SystemExit('Explicit crash after provider reply and cost settlement')):
            with self.assertRaises(SystemExit):self.step()
        calls=list(self.c.calls)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No recovery keys')):
            self.assertEqual(self.worker.recover()['recovered_meta_intents'],1)
        result=self.state();self.assertEqual(result['dispatch']['phase'],'meta_finish_unconfirmed');self.assertIsNone(result['receipt'])
        self.assertEqual(result['provider_job']['provider_job_id'],'34567');self.assertEqual(self.c.calls,calls)
        result=self.step()
        if self.PLATFORM=='facebook':self.assertEqual(result['receipt']['remote_post_id'],'34567')
        else:self.assertIsNone(result['receipt'])
        self.assertEqual(sum(1 for _,b in self.c.mutations if b.get('creation_id') or b.get('upload_phase')==['finish']),1)
    def test_same_job_explicit_finite_consent_renewal_after_expiry_and_project_edits(self):
        self.submitted();original=self.state()['provider_job'];self.c.clock[0]+=timedelta(seconds=901)
        with self.c.store.transaction() as con:con.execute('UPDATE projects SET revision=revision+1 WHERE id=?',(self.c.project['id'],))
        with self.assertRaises(WorkflowError):self.step()
        payload=Renew(expected_snapshot_sha256=self.publication['snapshot_sha256'],expected_dispatch_version=self.state()['dispatch']['version'],
            acknowledged_official_publication=True,valid_for_seconds=600,request_key='explicit-meta-original-job-renewal')
        calls=list(self.c.calls);renewed=self.service.renew(self.c.project['id'],self.publication['publication_id'],payload,principal=self.c.principal)
        self.assertTrue(self.service.renew(self.c.project['id'],self.publication['publication_id'],payload,principal=self.c.principal)['replayed']);self.assertEqual(calls,self.c.calls)
        self.assertEqual(self.state()['provider_job'],original);self.assertFalse(renewed['automatic_renewal'])
        self.assertEqual(self.complete()['provider_job'],original);self.assertEqual(sum(1 for _,b in self.c.mutations if b.get('upload_phase')==['start'] or b.get('media_type')==['REELS']),1)
    def test_submitted_job_status_and_finish_do_not_require_private_media_files_or_storage_wire(self):
        self.submitted();calls=list(self.storage.calls)
        (self.media_factory.directory/(self.delivery['lease_ref']+'.dpapi')).unlink()
        with patch.object(self.media_factory,'check',side_effect=AssertionError('No storage key/file checks for submitted job')):
            with patch.object(self.media,'resolve_for_consumer',side_effect=AssertionError('No lease load for submitted job')):
                self.assertIsNotNone(self.complete()['receipt'])
        self.assertEqual(self.storage.calls,calls)
    def test_media_selection_race_during_identity_preflight_rejects_before_mutation(self):
        preflight=self.worker.meta.preflight
        def change(*args,**kwargs):
            proof=preflight(*args,**kwargs)
            payload=execution.MediaBind(**self.binding['binding']['request'],request_key='explicit-different-media-selection')
            execution.bind_media(self.service,self.media,self.c.project['id'],self.publication['publication_id'],payload,principal=self.c.principal)
            return proof
        with patch.object(self.worker.meta,'preflight',side_effect=change):
            with self.assertRaisesRegex(WorkflowError,'SELECTION_CHANGED'):self.step()
        self.assertEqual(self.state()['dispatch']['phase'],'prepared');self.assertEqual(self.c.mutations,[])
    def test_cost_bound_to_wrong_final_job_cannot_certify_history_or_receipt(self):
        self.step()
        with self.c.store.transaction() as con:con.execute("UPDATE native_cost_operations SET job_id='foreign-final-fixture' WHERE operation LIKE 'meta_init.%'")
        with self.assertRaisesRegex(WorkflowError,'COST_EVIDENCE_CHANGED'):self.state()
    def test_shared_finite_queue_completes_one_job_without_default_activation(self):
        self.assertIsNone(NativeOfficialPublicationQueue(self.worker).process());queue,plan=self.queue()
        for _ in range(8):
            result=queue.process();self.c.clock[0]+=timedelta(seconds=30)
            if result is not None and result['status']=='completed':break
        result=queue.get(self.c.project['id'],plan['plan_id']);self.assertEqual(result['status'],'completed')
        self.assertTrue(result['steps'][-1]['result']['mock_publication_complete']);self.assertFalse(result['steps'][-1]['result']['published'])
        self.assertEqual(len(self.c.mutations),3 if self.PLATFORM=='facebook' else 2);self.assertIsNone(queue.process())
    def test_shared_queue_respects_status_backoff_without_consuming_an_early_step(self):
        self.submitted();queue,plan=self.queue();self.c.status_override=lambda request:httpx.Response(429,headers={'Retry-After':'60'},json={'error':{'message':'Explicit private fixture'}})
        result=queue.process();self.assertEqual(result['status'],'queued');calls=list(self.c.calls)
        self.c.clock[0]+=timedelta(seconds=30);self.assertIsNone(queue.process());self.assertEqual(self.c.calls,calls)
        self.assertEqual(queue.get(self.c.project['id'],plan['plan_id'])['step_count'],1)
        self.c.status_override=None;self.c.clock[0]+=timedelta(seconds=31)
        for _ in range(5):
            result=queue.process();self.c.clock[0]+=timedelta(seconds=30)
            if result is not None and result['status']=='completed':break
        self.assertEqual(queue.get(self.c.project['id'],plan['plan_id'])['status'],'completed')
    def test_background_cancel_during_known_init_keeps_original_result_without_later_requests(self):
        queue,plan=self.queue();self.c.after=lambda name:queue.cancel(self.c.project['id'],plan['plan_id'],QueueCancel(expected_policy_sha256=plan['policy_sha256']),principal=self.c.principal) if name=='init' else None
        result=queue.process();self.assertEqual(result['status'],'cancelled');self.assertEqual(self.state()['provider_job']['provider_job_id'],'34567')
        calls=list(self.c.calls);self.c.clock[0]+=timedelta(seconds=31);self.assertIsNone(queue.process());self.assertEqual(self.c.calls,calls)

class FacebookMetaPublishWorkerTests(MetaPublishWorkerTests):
    PLATFORM='facebook'
    def test_unknown_transfer_uses_status_without_sending_file_url_again(self):
        self.step();self.c.lose='transfer';result=self.step();self.assertEqual(result['dispatch']['phase'],'meta_transfer_unconfirmed')
        self.c.lose=None;self.assertEqual(self.complete()['receipt']['remote_post_id'],'34567')
        self.assertEqual(sum(1 for path,_ in self.c.mutations if '/video-upload/' in path),1)
    def test_renewed_transfer_requires_new_separate_media_consent_and_readonly_delivery(self):
        self.step();self.c.clock[0]+=timedelta(seconds=901)
        payload=Renew(expected_snapshot_sha256=self.publication['snapshot_sha256'],expected_dispatch_version=self.state()['dispatch']['version'],
            acknowledged_official_publication=True,request_key='explicit-facebook-created-job-renew')
        self.service.renew(self.c.project['id'],self.publication['publication_id'],payload,principal=self.c.principal)
        calls=list(self.c.calls)
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(self.c.calls,calls)
        delivery=self.media.create(self.c.project['id'],Create(publication_id=self.publication['publication_id'],expected_publication_snapshot_sha256=self.publication['snapshot_sha256'],
            expected_configuration_sha256=self.media_factory.sha256,acknowledged_external_media_delivery=True,reconcile_delivery_id=self.delivery['delivery_id'],
            request_key='explicit-facebook-renewed-readonly-media'),principal=self.c.principal)[0]
        delivery=self.media.process(self.c.project['id'],delivery['delivery_id']);self.assertEqual(delivery['status'],'succeeded')
        execution.bind_media(self.service,self.media,self.c.project['id'],self.publication['publication_id'],execution.MediaBind(expected_snapshot_sha256=self.publication['snapshot_sha256'],
            expected_dispatch_version=self.state()['dispatch']['version'],media_delivery_id=delivery['delivery_id'],expected_media_snapshot_sha256=delivery['snapshot_sha256'],
            acknowledged_exact_media_selection=True,request_key='explicit-facebook-renewed-exact-media'),principal=self.c.principal)
        self.assertEqual(self.complete()['receipt']['remote_post_id'],'34567');self.assertEqual(self.storage.puts,1)


if __name__=='__main__':unittest.main()
