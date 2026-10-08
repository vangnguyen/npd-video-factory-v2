"""Explicit nonplayable account/metrics/media fixtures; never Hub acceptance."""
import copy,json,unittest,threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests.test_qualified_learning_feedback import FeedbackFixture
from services.windows_native.bridge import NativeBridge
from services.windows_native.qualified_bridge_sources import VERSION,CONTRACT
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.bridge_transport import FixtureWebhookTransport,BridgeResponse
from app.bridge_auth import SigningKeyring,canonical_json_bytes

KEY=b'explicit-qualified-bridge-fixture-only-001'
class QualifiedBridgeTests(FeedbackFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.bridge=NativeBridge(self.store,workspace_id=self.workspace)
        self.bridge.attach_intelligence(self.intelligence.store)
        self.bridge.bind_qualified_sources(analytics=self.analytics,winner=self.winners,learning=self.learning,projection=self.feedback)
    def events(self):return [e for e in self.bridge.page(limit=100)['items'] if e['envelope']['payload'].get('payload_schema_version')==VERSION]
    def sparse(self):
        assessment=self.assess(request_key='explicit-qualified-bridge-assessment');self.anchor_assessment=assessment
        self.saved=self.learn(request_key='explicit-qualified-bridge-learning');record,replay=self.project_feedback();return assessment,self.saved,record
    def test_binding_and_existing_history_do_not_backfill_or_dispatch(self):
        wire=self.read_wire.copy();before=self.store.get(self.anchor_project)
        self.assertEqual(self.events(),[]);self.assertEqual(self.bridge.harvest(),0);self.assertIsNone(self.bridge.process())
        self.assertEqual(self.read_wire,wire);self.assertEqual(self.store.get(self.anchor_project),before)
    def test_sparse_assessment_and_learning_projection_preserve_nulls_without_winner_claim(self):
        wire=self.read_wire.copy();assessment,learned,record=self.sparse();self.assertEqual(self.bridge.harvest(),1)
        events=self.events();self.assertEqual(len(events),3);types=[e['envelope']['event_type'] for e in events]
        self.assertEqual(types.count('video.winner.assessed'),1);self.assertEqual(types.count('video.learning.updated'),2);self.assertNotIn('video.winner.detected',types)
        for e in events:
            p=e['envelope']['payload'];self.assertTrue(p['mock']);self.assertFalse(p['real_audience_observation']);self.assertFalse(p['automatic_application']);self.assertFalse(p['publishing_enabled'])
            self.assertEqual(e['envelope']['contract_version'],CONTRACT)
            self.assertIsNone(p['assessment_score']);self.assertEqual(p['provider_calls'],0);self.assertEqual(e['delivery']['status'],'disabled')
        self.assertEqual(self.read_wire,wire);self.assertEqual(self.bridge.harvest(),0)
    def test_same_request_replays_only_one_assessment_learning_projection_event(self):
        self.sparse();self.bridge.harvest();original=self.events();self.sparse();self.bridge.harvest();self.assertEqual(self.events(),original)
    def test_analytics_collected_event_has_original_source_response_cost_and_nullable_report_binding(self):
        original=self.store.get(self.project['id']);self.run_collection(request_key='explicit-qualified-bridge-new-observation')
        events=self.events();self.assertEqual(len(events),1);p=events[0]['envelope']['payload'];self.assertEqual(p['source_type'],'analytics');self.assertEqual(p['state'],'succeeded')
        self.assertEqual(p['observation_count'],1);self.assertIsNone(p['assessment_score']);self.assertIsNone(p['peer_count']);self.assertFalse(p['source_external_call']);self.assertEqual(self.store.get(self.project['id']),original)
    def test_rehashed_envelope_hash_flags_counts_scope_source_and_timestamp_cannot_override_original(self):
        self.sparse();self.bridge.harvest();event=self.events()[0];identity=event['envelope']['event_id']
        with self.store.transaction() as con:original=tuple(con.execute('SELECT envelope_json,envelope_sha256 FROM native_bridge_events WHERE event_id=?',(identity,)).fetchone())
        for change in (lambda v:v['payload'].update(mock=1),lambda v:v['payload'].update(automatic_application=0),lambda v:v['payload'].update(real_audience_observation=True),lambda v:v['payload'].update(source_sha256='f'*64),lambda v:v['payload'].update(scope_sha256='f'*64),lambda v:v.update(occurred_at='2026-10-01T00:00:00+00:00')):
            value=json.loads(original[0]);change(value)
            with self.store.transaction() as con:con.execute('UPDATE native_bridge_events SET envelope_json=?,envelope_sha256=? WHERE event_id=?',(json.dumps(value),digest(value),identity))
            with self.assertRaises(WorkflowError):self.bridge.page(limit=100)
        with self.store.transaction() as con:con.execute('UPDATE native_bridge_events SET envelope_json=?,envelope_sha256=? WHERE event_id=?',(*original,identity))
        self.assertEqual(self.events()[0],event)
    def test_changed_original_response_cost_refuses_event_read_and_signed_dispatch(self):
        self.run_collection(request_key='explicit-qualified-bridge-cost-proof');event=self.events()[0];wire=[]
        self.bridge.configure_delivery(transport=FixtureWebhookTransport(lambda body,headers:wire.append(body) or BridgeResponse(200)),signing=SigningKeyring('fixture-v1',{'fixture-v1':KEY}),enabled=True)
        self.bridge.enqueue(event['envelope']['event_id'])
        with self.store.transaction() as con:con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        with self.assertRaises(WorkflowError):self.bridge.process()
        self.assertEqual(wire,[])
    def test_projection_source_event_is_atomic_and_failed_capture_rolls_back_record_and_outbox(self):
        with patch.object(self.bridge,'capture_projection',side_effect=WorkflowError('EXPLICIT ATOMIC CAPTURE FAILURE')):
            with self.assertRaisesRegex(WorkflowError,'EXPLICIT'):self.project_feedback()
        with self.intelligence.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM records').fetchone()[0],0);self.assertEqual(con.execute('SELECT count(*) FROM native_bridge_source_events').fetchone()[0],0)
    def test_original_history_after_expiry_archiving_provider_removal_remains_readable_without_current_grant(self):
        self.sparse();self.bridge.harvest();events=self.events();wire=self.read_wire.copy();self.accounts.factories.clear();self.service.factories.clear();self.clock[0]+=timedelta(days=2)
        current=self.store.get(self.anchor_project);self.store.archive(self.anchor_project,current['revision'],True)
        self.assertEqual(self.events(),events);self.assertEqual(wire,self.read_wire)
    def test_lost_fixture_delivery_response_reuses_same_signed_event_and_idempotency_key(self):
        self.sparse();self.bridge.harvest();event=self.events()[0];wire=[];stamp=[1791410400.0];self.bridge.clock=lambda:stamp[0]
        def send(body,headers):
            wire.append((body,headers))
            if len(wire)==1:raise TimeoutError('EXPLICIT RECEIVER REPLY LOSS')
            return BridgeResponse(200)
        self.bridge.configure_delivery(transport=FixtureWebhookTransport(send),signing=SigningKeyring('fixture-v1',{'fixture-v1':KEY}),enabled=True)
        self.bridge.enqueue(event['envelope']['event_id']);self.bridge.process();stamp[0]+=10;self.bridge.process()
        self.assertEqual(wire[0][0],wire[1][0]);self.assertEqual(wire[0][1]['Idempotency-Key'],wire[1][1]['Idempotency-Key']);self.assertEqual(len(wire),2)
    def test_mock_positive_cohort_assessment_retains_false_audience_and_baseline_labels(self):
        self.cohort_learning();self.saved=self.learn(request_key='explicit-qualified-bridge-positive-learning');record,_=self.project_feedback();self.bridge.harvest()
        events=self.events();detected=[e['envelope']['payload'] for e in events if e['envelope']['event_type']=='video.winner.detected']
        self.assertTrue(detected)
        for p in detected:self.assertTrue(p['mock']);self.assertFalse(p['real_audience_observation']);self.assertFalse(p['real_provider_acceptance']);self.assertFalse(p['channel_baseline_verified']);self.assertIsInstance(p['assessment_score'],(int,float))
        projection=next(e['envelope']['payload'] for e in events if e['envelope']['payload']['source_type']=='projection');self.assertEqual(projection['observation_count'],6);self.assertEqual(projection['state'],'recommendations_available')
    def test_wrong_source_registry_workspace_and_mutated_runtime_reject_before_events(self):
        with self.assertRaises(WorkflowError):self.bridge.bind_qualified_sources(analytics=object())
        self.analytics.workspace='wsp_foreign';wire=self.read_wire.copy()
        with self.assertRaises(WorkflowError):self.bridge.sources.read('analytics',self.anchor_project,self.anchor['sync_id'])
        self.assertEqual(wire,self.read_wire)
    def test_original_projection_reader_does_not_take_intelligence_writer_lock_inside_workflow(self):
        self.sparse();self.bridge.harvest();entered=threading.Event();release=threading.Event()
        def hold_writer():
            with self.intelligence.store.transaction() as con:
                entered.set();release.wait(5)
                with self.store.transaction() as source:source.execute('SELECT 1')
        with ThreadPoolExecutor(2) as pool:
            holder=pool.submit(hold_writer);self.assertTrue(entered.wait(3));reader=pool.submit(self.events)
            try:self.assertEqual(len(reader.result(timeout=3)),3)
            finally:release.set()
            holder.result(timeout=3)
    def test_failed_qualified_winner_capture_rolls_back_assessment_and_its_source_event(self):
        with self.store.transaction() as con:before=con.execute('SELECT count(*) FROM native_official_winner_assessments').fetchone()[0]
        with patch.object(self.bridge,'capture_qualified',side_effect=WorkflowError('EXPLICIT ATOMIC WINNER CAPTURE FAILURE')):
            with self.assertRaisesRegex(WorkflowError,'EXPLICIT'):self.assess(request_key='explicit-qualified-bridge-rollback-assessment')
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_winner_assessments').fetchone()[0],before)
        self.assertEqual(self.events(),[])
