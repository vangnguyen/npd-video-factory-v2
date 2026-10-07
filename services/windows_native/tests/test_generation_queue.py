"""Actual isolated SQLite/claims/cost intents; observation fixtures, no wire calls."""
from copy import deepcopy
import asyncio,concurrent.futures,json,tempfile,time,unittest
from pathlib import Path
import httpx
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_registry import GenerationCredential,GenerationFactory
from services.windows_native.generation_models import GenerationCreate,GenerationAction,GenerationRecovery,NativeImageParameters
from services.windows_native.generation_references import api_parameters
from services.windows_native.store import Store

WORKSPACE='wsp_native_generation_queue_fixture'
TOKEN='explicit-generation-queue-fixture-token-32'


class NativeGenerationQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'state';self.store=Store(self.root);self.project=self.store.create('EXPLICIT QUEUE FIXTURE','PRIVATE INPUT')
        self.clock=[time.time()];self.calls=[]
        def wire(request):self.calls.append(request.method);raise AssertionError('No external call permitted in queue suite')
        self.factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token=TOKEN,enabled=True),owner_enabled=True,transport=httpx.MockTransport(wire))
        self.service=NativeGenerationQueue(self.store,workspace_id=WORKSPACE,factory=self.factory,clock=lambda:self.clock[0])
        self.payload=GenerationCreate(revision=self.project['revision'],parameters=NativeImageParameters(prompt='EXPLICIT ORIGINAL QUEUE PROMPT'),
            fixture_acknowledged=True,request_key='explicit-native-generation-queue-key')

    def tearDown(self):self.assertEqual(self.calls,[]);self.temp.cleanup()
    def create(self,**changes):return self.service.create(self.project['id'],GenerationCreate.model_validate({**self.payload.model_dump(mode='json'),**changes}),actor='explicit-editor-fixture')[0]
    def action(self,job):return GenerationAction(expected_fingerprint=job['request_fingerprint'])
    def cost(self,job,**changes):return self.service.costs.begin(project_id=job['project_id'],provider=job['snapshot']['selection']['provider'],
        model='workflow:'+job['snapshot']['selection']['workflow_id'],operation='generation.'+job['generation_id']+'.submit',
        request_sha256=job['request_fingerprint'],estimated_cost=None,external_call=True,paid=False,**changes)
    def prepared(self):
        job=self.create();claim=self.service.claim();payload=api_parameters(self.payload.parameters,{})
        self.service.bind_input(claim,payload);operation=self.cost(job);self.service.mark_dispatch(claim,operation);return job,claim
    def observation(self,job,**changes):return {'schema_version':'comfyui-generation-observation-v1','phase':'submitted','provider_job_id':'cui_explicit_queue_fixture',
        'workspace_id':WORKSPACE,'workflow_id':job['snapshot']['selection']['workflow_id'],'workflow_version':job['snapshot']['selection']['workflow_version'],
        'status':'running','progress':15,**changes}
    def recovery(self,job,**changes):return GenerationRecovery(expected_fingerprint=job['request_fingerprint'],acknowledged=True,request_key='explicit-queue-recovery-fixture-key',**changes)

    def test_durable_frozen_idempotency_and_changed_request_rejection_preserve_project(self):
        before=self.store.get(self.project['id']);job=self.create();replay,yes=self.service.create(self.project['id'],self.payload,actor='explicit-editor-fixture')
        self.assertTrue(yes);self.assertEqual(job,replay);self.assertEqual(before,self.store.get(self.project['id']));self.assertFalse(job['worker_wired'])
        with self.assertRaises(WorkflowError):self.create(parameters={**self.payload.parameters.model_dump(mode='json'),'prompt':'CHANGED FIXTURE'})
        self.assertNotIn(TOKEN,json.dumps(job));self.assertFalse(job['publish_enabled']);self.assertFalse(job['automatic_attachment'])

    def test_default_disabled_records_not_configured_and_never_claims_or_inherits_fixture_ack(self):
        default=NativeGenerationQueue(self.store,workspace_id=WORKSPACE,clock=lambda:self.clock[0]);payload=self.payload.model_copy(update={'fixture_acknowledged':False,'external_acknowledged':True})
        job,_=default.create(self.project['id'],payload,actor='explicit-editor-fixture');self.assertEqual(job['status'],'not_configured');self.assertIsNone(default.claim())
        with self.assertRaises(WorkflowError):default.create(self.project['id'],self.payload.model_copy(update={'request_key':'different-inactive-fixture-key'}),actor='explicit-editor-fixture')
        self.assertEqual(default.costs.summary(self.project['id'])['records'],[])

    def test_atomic_concurrent_request_admission_and_single_worker_claim(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:self.create(),range(3)))
        self.assertEqual(len({job['generation_id'] for job in results}),1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:claims=list(pool.map(lambda _:self.service.claim(),range(3)))
        self.assertEqual(sum(claim is not None for claim in claims),1);self.assertEqual(self.store.get(self.project['id'])['revision'],1)

    def test_claim_expiry_requires_review_never_reclaims_or_resubmits_and_old_worker_is_fenced(self):
        job=self.create();claim=self.service.claim();self.clock[0]+=901;self.assertIsNone(self.service.claim())
        self.assertEqual(self.service.get(self.project['id'],job['generation_id'])['status'],'recovery_required')
        with self.assertRaises(WorkflowError) as error:self.service.bind_input(claim,api_parameters(self.payload.parameters,{}))
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_WORKER_FENCED')
        with self.assertRaises(WorkflowError):self.service.recover(self.project['id'],job['generation_id'],self.recovery(job),actor='explicit-editor-fixture')

    def test_provider_input_scalars_and_cost_are_frozen_before_dispatch_and_second_submission_rejected(self):
        job=self.create();claim=self.service.claim()
        with self.assertRaises(WorkflowError):self.service.bind_input(claim,api_parameters(NativeImageParameters(prompt='CHANGED PROMPT'),{}))
        self.service.bind_input(claim,api_parameters(self.payload.parameters,{}))
        with self.assertRaises(WorkflowError):self.service.mark_dispatch(claim,'0'*64)
        operation=self.cost(job);self.service.mark_dispatch(claim,operation)
        with self.assertRaises(WorkflowError):self.service.mark_dispatch(claim,operation)
        current=self.service.get(self.project['id'],job['generation_id']);self.assertTrue(current['dispatch_started']);self.assertEqual(current['cost_operation_id'],operation)
        self.assertIsNone(self.service.costs.summary(self.project['id'])['records'][0]['actual_cost'])

    def test_one_cost_intent_cannot_authorize_two_identical_generation_requests(self):
        job,claim=self.prepared();operation=self.service.get(job['project_id'],job['generation_id'])['cost_operation_id'];self.service.fail(claim,'EXPLICIT_FIXTURE_INTERRUPTION')
        other=self.create(request_key='explicit-other-identical-request-key');second=self.service.claim();self.service.bind_input(second,api_parameters(self.payload.parameters,{}))
        with self.assertRaises(WorkflowError) as error:self.service.mark_dispatch(second,operation)
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_COST_ADMISSION_INVALID');self.assertNotEqual(other['generation_id'],job['generation_id'])

    def test_observations_bind_ticket_workspace_workflow_and_version_and_deduplicate_unchanged_progress(self):
        job,claim=self.prepared();body=self.observation(job);self.assertTrue(self.service.observe(claim,body));self.assertFalse(self.service.observe(claim,body))
        for change in [{'workspace_id':'foreign'},{'provider_job_id':'cui_other'},{'workflow_id':'npd-video-generation-v1'},{'workflow_version':'other'},{'prompt':'private'},{'progress':True}]:
            with self.assertRaises(WorkflowError):self.service.observe(claim,{**body,**change})
        current=self.service.get(job['project_id'],job['generation_id']);self.assertEqual(current['provider_job_id'],body['provider_job_id'])

    def test_running_cancel_is_pending_not_false_remote_confirmation_and_bound_cancellation_can_finish(self):
        job,claim=self.prepared();self.service.observe(claim,self.observation(job));cancelled=self.service.cancel(job['project_id'],job['generation_id'],self.action(job),actor='explicit-editor-fixture')
        self.assertEqual(cancelled['status'],'running');self.assertTrue(cancelled['cancel_requested'])
        self.service.observe(claim,self.observation(job,phase='cancel_response',status='cancelled'))
        stopped=self.service.fail(claim,'EXPLICIT_CANCEL_CONFIRMED');self.assertEqual(stopped['status'],'cancelled')

    def test_unstarted_cancel_is_local_and_budget_failure_has_no_dispatch_authority(self):
        job=self.create();cancelled=self.service.cancel(job['project_id'],job['generation_id'],self.action(job),actor='explicit-editor-fixture')
        self.assertEqual(cancelled['status'],'cancelled');self.assertFalse(cancelled['dispatch_started']);self.assertIsNone(self.service.claim())
        other=self.create(request_key='explicit-cost-blocked-fixture-key');claim=self.service.claim();stopped=self.service.fail(claim,'AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH',needs_approval=True)
        self.assertEqual(stopped['status'],'needs_approval');self.assertFalse(stopped['dispatch_started']);self.assertFalse(other['dispatch_started'])

    def test_recovery_queues_only_bound_read_mode_and_frozen_replay_grants_no_submission(self):
        job,claim=self.prepared();self.service.observe(claim,self.observation(job));self.service.fail(claim,'EXPLICIT_SUBMISSION_REPLY_UNKNOWN')
        request=self.recovery(job);receipt=self.service.recover(job['project_id'],job['generation_id'],request,actor='explicit-editor-fixture')
        self.assertFalse(receipt['generation_submission_authorized']);self.assertEqual(receipt['external_calls'],0)
        self.assertTrue(self.service.recover(job['project_id'],job['generation_id'],request,actor='explicit-editor-fixture')['idempotent_replay'])
        recovered=self.service.claim();self.assertEqual(recovered['mode'],'reconcile')
        with self.assertRaises(WorkflowError) as error:self.service.mark_dispatch(recovered,recovered['job']['cost_operation_id'])
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_NO_RESUBMISSION')
        self.assertEqual(recovered['job']['provider_job_id'],'cui_explicit_queue_fixture')

    def test_reopen_defaults_inactive_preserves_frozen_job_and_workspace_mismatch_rejects(self):
        job=self.create();reopened=NativeGenerationQueue(Store(self.root),workspace_id=WORKSPACE,clock=lambda:self.clock[0])
        self.assertEqual(reopened.get(job['project_id'],job['generation_id']),job);self.assertIsNone(reopened.claim())
        with self.assertRaises(WorkflowError):NativeGenerationQueue(self.store,workspace_id='foreign')
        with self.assertRaises(WorkflowError):reopened.get(self.store.create('Other','private')['id'],job['generation_id'])

    def test_rehashed_journal_cannot_promote_fixture_provider_or_foreign_scope(self):
        job=self.create()
        with self.store.transaction() as con:
            snapshot=deepcopy(job['snapshot']);snapshot['selection']['real_provider_tested']=True
            con.execute('UPDATE native_generation_jobs SET snapshot_json=?,snapshot_sha256=? WHERE generation_id=?',(json.dumps(snapshot),digest(snapshot),job['generation_id']))
        with self.assertRaises(WorkflowError):self.service.get(job['project_id'],job['generation_id'])

    def test_last_dispatch_check_rejects_project_change_after_input_and_cost_binding(self):
        job=self.create();claim=self.service.claim();self.service.bind_input(claim,api_parameters(self.payload.parameters,{}));operation=self.cost(job)
        self.service.costs.set_budget(self.project['id'],self.project['revision'],'0')
        with self.assertRaises(WorkflowError):self.service.mark_dispatch(claim,operation)
        self.assertFalse(self.service.get(job['project_id'],job['generation_id'])['dispatch_started'])

    def test_reference_input_requires_actual_confirmed_admission_and_cannot_be_retargeted_by_rehashing(self):
        from PIL import Image
        from services.windows_native.media import ingest_media
        from services.windows_native.pipeline import Config
        path=Path(self.temp.name)/'explicit-owned-reference.png';Image.new('RGB',(320,240),(24,90,140)).save(path)
        asset=ingest_media(Config(data_root=self.root),path,'image/png',path.name,rights_confirmed=True,illustration=False)
        asset.update(rights_status='owned',license='locally_generated_synthetic_fixture',explicit_fixture=True)
        self.project=self.store.append_media(self.project['id'],self.project['revision'],asset)
        self.payload=GenerationCreate(revision=self.project['revision'],parameters=NativeImageParameters(prompt='EXPLICIT QUEUE REFERENCE FIXTURE',operation='image_to_image',
            references=[{'asset_id':asset['id'],'asset_sha256':asset['sha256']}]),fixture_acknowledged=True,request_key='explicit-reference-generation-queue-key')
        job=self.create();claim=self.service.claim()
        fake=api_parameters(self.payload.parameters,{asset['id']:'vf-reference://'+'0'*64})
        with self.assertRaises(WorkflowError) as error:self.service.bind_input(claim,fake)
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_REFERENCE_NOT_CONFIRMED')
        intake=[]
        def wire(request):
            intake.append(request.method)
            if request.method=='GET':return httpx.Response(404)
            admission=json.loads(request.headers['X-VF-Reference-Admission']);identity=digest(admission)
            return httpx.Response(201,json={'reference_id':identity,'source_reference':'vf-reference://'+identity,'filename':'reference.jpg',
                'size_bytes':len(request.content),'admission':admission,'media':{'full_decode_passed':True,'qc_passed':False,'width':320,'height':240},
                'rights_independently_verified':False,'publishing_authorized':False,'created_at':'2026-10-08T00:00:00Z'})
        self.factory.transport=httpx.MockTransport(wire)
        actual=asyncio.run(self.service.references.stage(job['generation_id'],job['snapshot']['references'],self.factory));self.assertEqual(intake,['GET','POST'])
        self.service.bind_input(claim,actual);operation=self.cost(job)
        changed=actual.model_dump(mode='json');changed['reference_images']=['vf-reference://'+'f'*64]
        with self.store.transaction() as con:con.execute('UPDATE native_generation_jobs SET provider_input_json=?,provider_input_sha256=? WHERE generation_id=?',
            (json.dumps(changed),digest(changed),job['generation_id']))
        with self.assertRaises(WorkflowError) as error:self.service.mark_dispatch(claim,operation)
        self.assertEqual(error.exception.code,'NATIVE_GENERATION_PROVIDER_INPUT_CHANGED');self.assertFalse(self.service.get(job['project_id'],job['generation_id'])['dispatch_started'])
