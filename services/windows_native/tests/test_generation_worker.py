"""Actual SQLite/pixels, provider execution explicitly mocked, no network calls."""
from copy import deepcopy
from dataclasses import replace
import asyncio,json,threading,time,unittest
from unittest.mock import patch
from services.windows_native.tests import test_generation_media as helpers
from services.windows_native.generation_worker import NativeGenerationWorker
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_models import GenerationAction,GenerationRecovery,GenerationImport
from services.windows_native.pipeline import Config
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.observability import Observer
from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider


class NativeGenerationWorkerTests(unittest.TestCase):
    setUp=helpers.NativeGenerationMediaTests.setUp
    tearDown=helpers.NativeGenerationMediaTests.tearDown
    create=helpers.NativeGenerationMediaTests.create
    cost=helpers.NativeGenerationMediaTests.cost
    prepared=helpers.NativeGenerationMediaTests.prepared
    observation=helpers.NativeGenerationMediaTests.observation
    pixels=helpers.NativeGenerationMediaTests.pixels
    output=helpers.NativeGenerationMediaTests.output

    def worker(self):return NativeGenerationWorker(self.service,Config(data_root=self.root))
    def recovery(self,job,key='explicit-worker-read-recovery-key'):
        return GenerationRecovery(expected_fingerprint=job['request_fingerprint'],acknowledged=True,request_key=key)
    def import_request(self,job,**changes):
        return GenerationImport.model_validate({'revision':self.store.get(self.project['id'])['revision'],'expected_fingerprint':job['request_fingerprint'],
            'expected_asset_sha256':job['result']['asset']['sha256'],'acknowledged':True,'request_key':'explicit-worker-attachment-key',**changes})
    def generate(self,worker,*,failure=False,cancel=False):
        async def call(adapter,payload):
            job=self.service.page(self.project['id'])['items'][0]
            with self.store.transaction() as con:
                row=self.service.row(con,job['project_id'],job['generation_id']);cost=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(row['cost_operation_id'],)).fetchone()
                self.assertTrue(row['dispatch_started']);self.assertEqual(cost['status'],'dispatch_intent')
            if failure:raise TimeoutError('EXPLICIT UNKNOWN PROVIDER FIXTURE')
            if cancel:
                self.service.cancel(job['project_id'],job['generation_id'],GenerationAction(expected_fingerprint=job['request_fingerprint']),actor='explicit-editor-fixture')
                self.assertTrue(adapter.cancel_requested());await adapter.on_job(self.observation(job,status='cancelled',phase='cancel_response'));raise RuntimeError('EXPLICIT CANCEL FIXTURE')
            await adapter.on_job(self.observation(job,status='succeeded',progress=100,phase='polled'));return self.output(job)
        return patch.object(ComfyUIBridgeGenerationProvider,'generate',call)

    def test_worker_dispatch_observation_actual_decode_success_and_unknown_rights_without_project_edit(self):
        before=self.store.get(self.project['id']);job=self.create();worker=self.worker()
        with self.generate(worker):self.assertEqual(worker.process(),job['generation_id'])
        result=worker.get(job['project_id'],job['generation_id']);self.assertEqual(result['status'],'succeeded');self.assertTrue(result['worker_wired'])
        self.assertEqual(result['result']['mode'],'create');self.assertEqual(result['result']['asset']['rights_status'],'unknown');self.assertFalse(result['result']['production_eligible'])
        self.assertIsNone(result['result']['actual_cost_vnd']);self.assertEqual(self.store.get(self.project['id']),before);self.assertIsNone(worker.process())
        self.assertEqual(self.service.costs.summary(job['project_id'])['records'][0]['status'],'response_received')

    def test_timeout_never_retries_submission_and_explicit_recovery_uses_only_read_adapter(self):
        job=self.create();worker=self.worker()
        with self.generate(worker,failure=True):worker.process()
        self.assertEqual(worker.get(job['project_id'],job['generation_id'])['status'],'recovery_required');self.assertIsNone(worker.process())
        self.service.recover(job['project_id'],job['generation_id'],self.recovery(job),actor='explicit-editor-fixture');calls=[]
        async def reconcile(adapter,payload,*,provider_job_id=None):
            calls.append(provider_job_id);await adapter.on_job(self.observation(job,status='succeeded',phase='reconciled',progress=100));return self.output(job)
        with patch.object(ComfyUIBridgeGenerationProvider,'generate',side_effect=AssertionError('No second submission')),patch.object(ComfyUIBridgeGenerationProvider,'reconcile',reconcile):worker.process()
        result=worker.get(job['project_id'],job['generation_id']);self.assertEqual(result['status'],'succeeded');self.assertEqual(result['result']['mode'],'reconcile');self.assertEqual(calls,[None])
        records=self.service.costs.summary(job['project_id'])['records'];self.assertEqual(len(records),2);self.assertCountEqual([r['status'] for r in records],['outcome_unknown','response_received'])
        self.assertTrue(all(r['actual_cost'] is None and not r['paid'] for r in records))

    def test_persisted_stage_recovers_without_provider_calls_or_new_cost_intent(self):
        job=self.create();worker=self.worker()
        with self.generate(worker),patch.object(worker,'finish',side_effect=WorkflowError('EXPLICIT_CRASH_AFTER_STAGE')):worker.process()
        self.assertEqual(worker.get(job['project_id'],job['generation_id'])['status'],'recovery_required')
        self.service.recover(job['project_id'],job['generation_id'],self.recovery(job),actor='explicit-editor-fixture')
        with patch.object(ComfyUIBridgeGenerationProvider,'generate',side_effect=AssertionError()),patch.object(ComfyUIBridgeGenerationProvider,'reconcile',side_effect=AssertionError()):worker.process()
        result=worker.get(job['project_id'],job['generation_id']);self.assertEqual(result['result']['mode'],'local_stage_recovery');self.assertEqual(len(self.service.costs.summary(job['project_id'])['records']),1)

    def test_pending_cancel_requires_observed_bound_confirmation_and_does_not_materialize(self):
        job=self.create();worker=self.worker()
        with self.generate(worker,cancel=True):worker.process()
        self.assertEqual(worker.get(job['project_id'],job['generation_id'])['status'],'cancelled');self.assertFalse((self.root/'assets').exists())

    def test_explicit_import_atomic_revision_approval_invalidation_and_frozen_idempotency(self):
        job=self.create();worker=self.worker()
        with self.generate(worker):worker.process()
        result=worker.get(job['project_id'],job['generation_id']);before=self.store.get(self.project['id']);request=self.import_request(result)
        receipt=worker.attach(self.project['id'],job['generation_id'],request,actor='explicit-editor-fixture');current=self.store.get(self.project['id'])
        self.assertEqual(current['revision'],before['revision']+1);self.assertIsNone(current['approval']);self.assertEqual(current['document']['assets'][-1],result['result']['asset'])
        self.assertEqual(current['document'].get('canonical_timeline'),before['document'].get('canonical_timeline'));self.assertTrue(receipt['approval_invalidated'])
        self.store.save(current['id'],current['revision'],prompt='LATER PROJECT EDIT')
        replay=worker.attach(self.project['id'],job['generation_id'],request,actor='explicit-editor-fixture');self.assertTrue(replay['idempotent_replay']);self.assertEqual(replay['revision'],receipt['revision'])
        with self.assertRaises(WorkflowError):worker.attach(self.project['id'],job['generation_id'],request.model_copy(update={'expected_fingerprint':'0'*64}),actor='explicit-editor-fixture')
        with self.assertRaises(WorkflowError):worker.attach(self.project['id'],job['generation_id'],request.model_copy(update={'request_key':'explicit-other-attachment-key'}),actor='explicit-editor-fixture')

    def test_import_missing_ack_stale_revision_foreign_project_or_corrupt_physical_asset_rejects(self):
        job=self.create();worker=self.worker()
        with self.generate(worker):worker.process()
        result=worker.get(job['project_id'],job['generation_id']);request=self.import_request(result);before=self.store.get(self.project['id'])
        for changes in [{'acknowledged':False},{'revision':2},{'expected_asset_sha256':'0'*64}]:
            with self.assertRaises(WorkflowError):worker.attach(self.project['id'],job['generation_id'],request.model_copy(update=changes),actor='explicit-editor-fixture')
        with self.assertRaises(WorkflowError):worker.get(self.store.create('OTHER','PRIVATE')['id'],job['generation_id'])
        self.assertEqual(self.store.get(self.project['id']),before)
        asset=result['result']['asset'];(self.root/'originals'/asset['original_id']).write_bytes(b'corrupt')
        with self.assertRaises(WorkflowError):worker.asset_file(self.project['id'],job['generation_id'])
        with self.assertRaises(WorkflowError):worker.attach(self.project['id'],job['generation_id'],request,actor='explicit-editor-fixture')

    def test_rehashed_result_cannot_promote_rights_change_cost_scope_or_recovery_mode(self):
        job=self.create();worker=self.worker()
        with self.generate(worker):worker.process()
        with self.store.transaction() as con:original=json.loads(con.execute('SELECT result_json FROM native_generation_results').fetchone()[0])
        for key,value in [('rights_status','owned'),('real_provider_tested',True),('project_id','0'*32),('stage_receipt_sha256','0'*64),('mode','reconcile'),('recovery_count',1),('original_cost_operation_id','foreign')]:
            changed={**original,key:value}
            with self.store.transaction() as con:con.execute('UPDATE native_generation_results SET result_json=?,result_sha256=?',(json.dumps(changed),digest(changed)))
            with self.assertRaises(WorkflowError):worker.get(self.project['id'],job['generation_id'])

    def test_default_inactive_daemon_and_reopen_preserve_results_without_execution(self):
        job=self.create();worker=self.worker()
        with self.generate(worker):worker.process()
        before=worker.get(self.project['id'],job['generation_id']);default=NativeGenerationQueue(self.store,workspace_id=self.service.workspace)
        reopened=NativeGenerationWorker(default,Config(data_root=self.root));self.assertEqual(reopened.get(self.project['id'],job['generation_id']),before)
        events=[];reopened.start(Observer(events.append));time.sleep(.05);reopened.close();self.assertFalse(reopened.worker.is_alive());self.assertEqual(events,[])

    def test_expired_worker_cannot_finish_or_recover_automatically(self):
        job,claim=self.prepared();worker=self.worker();self.service.observe(claim,self.observation(job,status='succeeded',progress=100));stage=worker.media.register(claim,self.output(job))
        self.service.costs.settle(job_id:=self.service.get(job['project_id'],job['generation_id'])['cost_operation_id'],status='response_received',response_sha256=digest(stage))
        self.clock[0]+=901
        with self.assertRaises(WorkflowError):worker.finish(claim,job_id,mode='create')
        self.assertIsNone(worker.process());self.assertEqual(worker.get(job['project_id'],job['generation_id'])['status'],'recovery_required')

    def test_unknown_official_price_with_budget_blocks_before_submission_or_paid_authority(self):
        import httpx
        from scripts.north_star_comfyui_http_backend import fixture_manifest
        from services.windows_native.generation_registry import GenerationFactory,GenerationCredential
        from services.windows_native.generation_models import GenerationCreate
        manifest=fixture_manifest(self.root);document=json.loads(manifest.read_bytes())
        for workflow in document['workflows']:
            workflow['execution']['approval_kind']='owner_approved'
            workflow['execution']['approval_reference']='EXPLICIT CONFIGURATION UNIT FIXTURE, NOT OWNER UAT'
        manifest.write_text(json.dumps(document),encoding='utf-8')
        calls=[]
        class ForbiddenOfficialTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self,request):calls.append(request.method);raise AssertionError('No official request authorized in unit fixture')
        self.factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token='explicit-budget-unit-fixture-token-32',enabled=True),
            owner_enabled=True,transport=ForbiddenOfficialTransport(),manifest_path=manifest)
        self.service=NativeGenerationQueue(self.store,workspace_id=self.service.workspace,factory=self.factory,clock=lambda:self.clock[0])
        self.project=self.service.costs.set_budget(self.project['id'],1,'0');self.payload=GenerationCreate.model_validate({**self.payload.model_dump(mode='json'),
            'revision':self.project['revision'],'external_acknowledged':True,'fixture_acknowledged':False})
        job=self.create();worker=self.worker()
        with patch.object(ComfyUIBridgeGenerationProvider,'generate',side_effect=AssertionError('Submission forbidden')):worker.process()
        current=worker.get(job['project_id'],job['generation_id']);self.assertEqual(current['status'],'needs_approval');self.assertFalse(current['dispatch_started']);self.assertEqual(calls,[])
        records=self.service.costs.summary(job['project_id'])['records'];self.assertEqual(len(records),1);self.assertTrue(records[0]['paid']);self.assertEqual(records[0]['status'],'needs_approval')

    def test_provider_configuration_drift_fails_queue_head_without_repeated_execution(self):
        job=self.create();worker=self.worker();self.factory.credential.service_token='changed-explicit-fixture-token-with-32-characters'
        self.assertIsNone(worker.process());current=worker.get(job['project_id'],job['generation_id']);self.assertEqual(current['status'],'failed')
        self.assertEqual(current['failure_code'],'NATIVE_GENERATION_PROVIDER_CONFIGURATION_CHANGED');self.assertIsNone(worker.process());self.assertEqual(self.service.costs.summary(job['project_id'])['records'],[])
