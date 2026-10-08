"""Finite default-off queue with explicit nonplayable media/provider fixtures."""
import json,unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from services.windows_native.tests.test_official_publication_dispatch import OfficialDispatchFixture
from services.windows_native.tests import test_official_publication_worker as worker_fixture
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue,QueueCreate,QueueCancel,QueueTicket,Outcome
from services.windows_native.official_publication_models import Action,Renew
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.backup import database_status
from app.youtube_upload import UNIT

class OfficialQueueTests(OfficialDispatchFixture,unittest.TestCase):
    response=worker_fixture.OfficialWorkerTests.response
    def setUp(self):
        super().setUp();self.wire=[];self.ack=0;self.processing='processed';self.privacy='private';self.mode=None
        self.client.transport.handler=self.response;self.worker=NativeOfficialPublicationWorker(self.service,self.vault)
        self.queue=NativeOfficialPublicationQueue(self.worker,enabled=True)
    def body_queue(self,**changes):
        return QueueCreate.model_validate({'expected_snapshot_sha256':self.value['snapshot_sha256'],'expected_dispatch_version':self.state()['version'],
            'acknowledged_background_steps':True,'max_steps':10,'interval_seconds':30,'start_at':self.clock[0],'deadline':self.clock[0]+timedelta(seconds=600),
            'request_key':'explicit-bounded-queue-fixture-key',**changes})
    def create_queue(self,body=None):
        return self.queue.create(self.project['id'],self.value['publication_id'],body or self.body_queue(),principal=self.principal)
    def get_queue(self,plan):return self.queue.get(self.project['id'],plan['plan_id'])
    def cancel_queue(self,plan):return self.queue.cancel(self.project['id'],plan['plan_id'],QueueCancel(expected_policy_sha256=plan['policy_sha256']),principal=self.principal)
    def advance(self,seconds=30):self.clock[0]+=timedelta(seconds=seconds)
    def revoke(self):return self.service.revoke(self.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256']),principal=self.principal)
    def test_default_off_and_approval_alone_cannot_execute_or_read_credentials(self):
        disabled=NativeOfficialPublicationQueue(self.worker)
        self.assertIsNone(disabled.process());self.assertIsNone(self.queue.process())
        with patch.object(self.factory,'credential',side_effect=AssertionError('Disabled queue never reads credentials')):
            with self.assertRaisesRegex(WorkflowError,'NOT_ENABLED'):disabled.create(self.project['id'],self.value['publication_id'],self.body_queue(),principal=self.principal)
        self.assertEqual(self.wire,[])
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_INVALID'):NativeOfficialPublicationQueue(self.worker,enabled=1)
    def test_five_finite_steps_one_init_three_unique_chunks_and_qualified_mock_receipt(self):
        before=self.store.get(self.project['id']);plan=self.create_queue();results=[]
        for _ in range(5):results.append(self.queue.process());self.advance()
        done=self.get_queue(plan);self.assertEqual(done['status'],'completed');self.assertEqual(done['step_count'],5);self.assertEqual(len(done['steps']),5)
        self.assertTrue(done['steps'][-1]['result']['mock_publication_complete']);self.assertFalse(done['steps'][-1]['result']['published']);self.assertIsNone(self.queue.process())
        self.assertEqual(sum(r['method']=='POST' for r in self.wire),1);self.assertEqual(sum(r['method']=='PUT' for r in self.wire),3);self.assertEqual(len(self.wire),10)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertNotIn('upload_id',json.dumps(done));self.assertNotIn(self.credential.token,json.dumps(done))
    def test_future_start_and_terminal_step_exhaustion_do_not_send_extra_requests(self):
        plan=self.create_queue(self.body_queue(start_at=self.clock[0]+timedelta(seconds=60),max_steps=2));self.assertIsNone(self.queue.process());self.assertEqual(self.wire,[])
        self.advance(60);self.assertEqual(self.queue.process()['step_count'],1);self.assertIsNone(self.queue.process());self.advance();done=self.queue.process()
        self.assertEqual(done['status'],'exhausted');self.assertEqual(done['step_count'],2);self.assertEqual(self.state()['acknowledged_bytes'],UNIT);self.advance();self.assertIsNone(self.queue.process());self.assertEqual(len(self.wire),4)
    def test_aware_finite_typed_bounds_unknown_fields_and_unchecked_models_fail_closed(self):
        for change in ({'acknowledged_background_steps':1},{'max_steps':True},{'max_steps':101},{'max_steps':0},{'interval_seconds':0},
            {'start_at':1},{'deadline':False},{'start_at':'2026-10-08T12:00:00'},{'deadline':self.clock[0]},{'token':'NEVER'},{'enabled':True}):
            with self.assertRaises(ValidationError):self.body_queue(**change)
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.create_queue(self.body_queue().model_copy(update={'acknowledged_background_steps':1}))
        with self.assertRaisesRegex(WorkflowError,'WINDOW_OUTSIDE_CONSENT'):self.create_queue(self.body_queue(deadline=self.clock[0]+timedelta(seconds=901)))
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):self.create_queue(self.body_queue(expected_dispatch_version=self.state()['version']+1))
        self.assertEqual(self.wire,[])
    def test_exact_key_replay_conflict_and_one_active_plan_preserve_source_after_edits(self):
        body=self.body_queue();plan=self.create_queue(body);self.assertTrue(self.create_queue(body)['idempotent_replay'])
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.create_queue(body.model_copy(update={'max_steps':11}))
        with self.assertRaisesRegex(WorkflowError,'ALREADY_ACTIVE'):self.create_queue(body.model_copy(update={'request_key':'explicit-second-active-plan-fixture'}))
        with self.store.transaction() as con:con.execute('UPDATE projects SET revision=revision+1 WHERE id=?',(self.project['id'],))
        self.assertEqual(self.create_queue(body)['plan_id'],plan['plan_id']);self.assertTrue(self.create_queue(body)['idempotent_replay']);self.assertEqual(self.wire,[])
    def test_concurrent_claim_has_exactly_one_fenced_step_and_no_wire(self):
        plan=self.create_queue()
        with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(lambda _:self.queue.claim(),range(2)))
        self.assertEqual(sum(isinstance(v,tuple) for v in claims),1);ticket=next(v[0] for v in claims if isinstance(v,tuple));self.assertIsInstance(ticket,QueueTicket)
        self.assertEqual(self.get_queue(plan)['step_count'],1);self.assertEqual(self.wire,[])
        with self.assertRaises(WorkflowError):self.queue.guard(replace(ticket,project_id='f'*32))
    def assert_stops(self,reason):
        plan=self.create_queue()
        if reason=='deadline':self.advance(601)
        elif reason=='role':object.__setattr__(self.verifier.registry.tokens[self.principal.token_id],'enabled',False)
        elif reason=='grant':self.revoke()
        else:(self.root/'jobs'/self.job['id']/'final.mp4').write_bytes(b'EXPLICIT CHANGED QUEUE SOURCE FIXTURE')
        with patch.object(self.factory,'credential',side_effect=AssertionError('Admission precedes secret reads')):result=self.queue.process()
        self.assertIn(result['status'],('expired','needs_attention'));self.assertEqual(result['step_count'],0);self.assertEqual(self.wire,[]);self.assertIsNone(self.queue.process())
    def test_deadline_expiry_stops_before_credentials(self):self.assert_stops('deadline')
    def test_owner_revocation_stops_before_credentials(self):self.assert_stops('role')
    def test_publication_grant_revocation_stops_before_credentials(self):self.assert_stops('grant')
    def test_source_change_stops_before_credentials(self):self.assert_stops('source')
    def test_queue_cancel_after_source_changes_replays_without_revoking_manual_grant(self):
        plan=self.create_queue();self.queue.process();before=self.state();calls=len(self.wire)
        with self.store.transaction() as con:con.execute('UPDATE projects SET revision=revision+1 WHERE id=?',(self.project['id'],))
        first=self.cancel_queue(plan);self.assertEqual(first['status'],'cancelled');self.assertEqual(self.cancel_queue(plan),first);self.assertIsNone(self.queue.process());self.assertEqual(self.state(),before);self.assertEqual(len(self.wire),calls)
        with self.store.transaction() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM native_official_publish_approvals WHERE status='active'").fetchone()[0],1)
            self.assertEqual(con.execute("SELECT count(*) FROM native_official_publish_queue_events WHERE action='official.publication.queue.cancelled'").fetchone()[0],1)
    def test_cancel_during_account_read_prevents_upload_initialization(self):
        plan=self.create_queue();original=self.response
        def response(request):
            result=original(request)
            if request.url.path=='/youtube/v3/channels':self.cancel_queue(plan)
            return result
        self.client.transport.handler=response;done=self.queue.process();self.assertEqual(done['status'],'cancelled');self.assertEqual(self.state()['phase'],'prepared')
        self.assertEqual(len(self.wire),1);self.assertEqual(self.wire[0]['method'],'GET');self.assertIsNone(self.queue.process())
    def test_cancel_during_known_init_retains_session_and_never_sends_more_bytes(self):
        plan=self.create_queue();original=self.response
        def response(request):
            result=original(request)
            if request.method=='POST':self.cancel_queue(plan)
            return result
        self.client.transport.handler=response;done=self.queue.process();self.assertEqual(done['status'],'cancelled');self.assertEqual(self.state()['phase'],'uploading');self.assertIsNotNone(self.state()['private_session_ref'])
        self.advance();self.assertIsNone(self.queue.process());self.assertEqual(len(self.wire),2)
    def test_unknown_chunk_stops_plan_and_new_explicit_plan_reconciles_without_second_init(self):
        plan=self.create_queue();self.queue.process();reference=self.state()['private_session_ref'];self.advance();self.mode='chunk-timeout';unknown=self.queue.process()
        self.assertEqual(unknown['status'],'needs_attention');self.assertEqual(self.state()['phase'],'reconciliation_required');self.assertEqual(self.state()['acknowledged_bytes'],0)
        self.advance();calls=len(self.wire);self.assertIsNone(self.queue.process());self.assertEqual(len(self.wire),calls)
        replacement=self.create_queue(self.body_queue(request_key='explicit-uncertain-new-bounded-plan'))
        for _ in range(4):done=self.queue.process();self.advance()
        self.assertEqual(done['status'],'completed');self.assertEqual(done['plan_id'],replacement['plan_id']);self.assertEqual(self.state()['private_session_ref'],reference)
        self.assertEqual(sum(r['method']=='POST' for r in self.wire),1);self.assertEqual(sum(r['range']=='bytes 0-262143/524305' for r in self.wire),1)
        self.assertEqual(self.get_queue(plan)['status'],'needs_attention')
    def test_known_read_backoff_is_durable_and_no_early_secret_or_wire_is_allowed(self):
        plan=self.create_queue();original=self.response
        def limited(request):
            self.wire.append({'method':request.method,'path':request.url.path,'range':None,'bytes':0});return httpx.Response(429,headers={'Retry-After':'60'},json={'error':{'reason':'EXPLICIT FIXTURE'}})
        self.client.transport.handler=limited;first=self.queue.process();self.assertEqual(first['status'],'queued');self.assertEqual(first['step_count'],1)
        self.advance()
        with patch.object(self.factory,'credential',side_effect=AssertionError('No early retry secret reads')):self.assertIsNone(self.queue.process())
        self.assertEqual(len(self.wire),1);self.advance();self.client.transport.handler=original;self.assertEqual(self.queue.process()['step_count'],2)
        self.assertEqual(sum(r['method']=='POST' for r in self.wire),1)
    def test_explicit_grant_renewal_invalidates_old_plan_and_new_plan_keeps_session(self):
        plan=self.create_queue();self.queue.process();reference=self.state()['private_session_ref'];self.advance()
        self.service.renew(self.project['id'],self.value['publication_id'],Renew(expected_snapshot_sha256=self.value['snapshot_sha256'],expected_dispatch_version=self.state()['version'],
            acknowledged_official_publication=True,request_key='explicit-queue-new-publication-grant'),principal=self.principal)
        before=len(self.wire);stopped=self.queue.process();self.assertEqual(stopped['status'],'needs_attention');self.assertEqual(stopped['failure_code'],'NATIVE_OFFICIAL_PUBLISH_QUEUE_GRANT_CHANGED');self.assertEqual(len(self.wire),before)
        replacement=self.create_queue(self.body_queue(request_key='explicit-queue-new-grant-new-plan'));self.queue.process();self.assertEqual(self.state()['private_session_ref'],reference);self.assertEqual(sum(r['method']=='POST' for r in self.wire),1)
    def test_restart_requires_review_without_decrypt_resend_or_authority_renewal(self):
        plan=self.create_queue();ticket,_=self.queue.claim();self.init()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Startup recovery cannot decrypt')):
            self.worker.recover();result=self.queue.recover();self.assertEqual(result['recovered_steps'],1);self.assertEqual(self.queue.recover()['recovered_steps'],0)
        history=self.get_queue(plan);self.assertEqual(history['status'],'needs_attention');self.assertEqual(history['steps'][0]['status'],'outcome_unknown');self.assertEqual(self.state()['phase'],'init_unconfirmed')
        self.assertIsNone(self.queue.process());self.assertEqual(self.wire,[])
        with self.assertRaises(WorkflowError):self.queue.guard(ticket)
    def test_historical_read_and_counts_without_dispatchers_preserve_fifteen_journals(self):
        plan=self.create_queue();self.cancel_queue(plan);before=self.get_queue(plan)
        journal=self.journal(self.factory);journal.factories.clear();worker=NativeOfficialPublicationWorker(journal,SessionVault(journal));readonly=NativeOfficialPublicationQueue(worker)
        self.assertEqual(readonly.get(self.project['id'],plan['plan_id']),before);counts=database_status(self.root/'workflow.sqlite3')['counts']
        self.assertEqual(counts['native_official_publish_queue_plans'],1);self.assertEqual(counts['native_official_publish_queue_steps'],0);self.assertEqual(counts['native_official_publish_queue_events'],2);self.assertEqual(self.wire,[])
    def test_rehashed_numeric_consent_cross_scope_policy_and_relabelled_result_are_rejected(self):
        plan=self.create_queue();self.queue.process()
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_official_publish_queue_steps').fetchone();result=json.loads(row['result_json']);result['mock']=False
            con.execute('UPDATE native_official_publish_queue_steps SET result_json=?,result_sha256=?',(json.dumps(result),digest(result)))
        with self.assertRaisesRegex(WorkflowError,'STEP_CHANGED'):self.get_queue(plan)
        self.advance();calls=len(self.wire)
        with patch.object(self.factory,'credential',side_effect=AssertionError('Prior evidence integrity precedes credentials')):self.assertEqual(self.queue.process()['status'],'needs_attention')
        self.assertEqual(len(self.wire),calls)
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_official_publish_queue_plans').fetchone();policy=json.loads(row['policy_json']);policy['request']['acknowledged_background_steps']=1
            con.execute('UPDATE native_official_publish_queue_plans SET policy_json=?,policy_sha256=?,request_sha256=?',(json.dumps(policy),digest(policy),digest({'publication_id':self.value['publication_id'],'request':policy['request']})))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.get_queue(plan)
    def test_cancel_during_chunk_keeps_known_progress_and_stops_all_future_queue_steps(self):
        plan=self.create_queue();self.queue.process();reference=self.state()['private_session_ref'];self.advance();original=self.response
        def response(request):
            result=original(request)
            if request.method=='PUT' and request.content:self.cancel_queue(plan)
            return result
        self.client.transport.handler=response;done=self.queue.process();self.assertEqual(done['status'],'cancelled')
        self.assertEqual(self.state()['acknowledged_bytes'],UNIT);self.assertEqual(self.state()['private_session_ref'],reference);calls=len(self.wire)
        self.advance();self.assertIsNone(self.queue.process());self.assertEqual(len(self.wire),calls);self.assertFalse(done['steps'][-1]['result']['published'])
    def test_grant_revocation_during_chunk_cannot_invent_progress_or_continue_plan(self):
        plan=self.create_queue();self.queue.process();self.advance();original=self.response
        def response(request):
            result=original(request)
            if request.method=='PUT' and request.content:self.revoke()
            return result
        self.client.transport.handler=response;done=self.queue.process();self.assertEqual(done['status'],'needs_attention')
        self.assertEqual(self.state()['acknowledged_bytes'],0);self.assertEqual(self.state()['phase'],'reconciliation_required')
        self.assertEqual(self.service.get(self.project['id'],self.value['publication_id'])['failure_code'],'NATIVE_OFFICIAL_PUBLISH_CONSENT_REVOKED')
        self.advance();self.assertIsNone(self.queue.process());self.assertEqual(len(self.wire),4)
    def test_cancelled_claim_recovery_is_local_and_preserves_cancellation(self):
        plan=self.create_queue();self.queue.claim();self.cancel_queue(plan)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No startup secrets')):self.assertEqual(self.queue.recover()['recovered_steps'],1)
        done=self.get_queue(plan);self.assertEqual(done['status'],'cancelled');self.assertEqual(done['steps'][0]['status'],'outcome_unknown');self.assertEqual(self.wire,[])
    def test_operator_configuration_mutation_cannot_enable_disable_or_run_an_existing_plan(self):
        plan=self.create_queue();self.queue.enabled=False
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.queue.process()
        self.assertEqual(self.wire,[]);self.queue.enabled=True;self.assertEqual(self.get_queue(plan)['step_count'],0)
        disabled=NativeOfficialPublicationQueue(self.worker);disabled.enabled=True
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):disabled.process()
        self.assertEqual(self.wire,[])
    def test_wrong_scope_policy_cancel_and_unchecked_outcome_are_refused(self):
        plan=self.create_queue();other=self.store.create('Foreign queue fixture','No providers')
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.queue.get(other['id'],plan['plan_id'])
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):self.queue.cancel(self.project['id'],plan['plan_id'],QueueCancel(expected_policy_sha256='f'*64),principal=self.principal)
        ticket,_=self.queue.claim()
        with self.assertRaisesRegex(WorkflowError,'OUTCOME_INVALID'):self.queue.finish(ticket,Outcome(mock=True).model_copy(update={'published':1}))
        with self.assertRaisesRegex(WorkflowError,'TICKET_STALE'):self.queue.guard(replace(ticket,claim_id='f'*32))
        self.assertEqual(self.wire,[])
