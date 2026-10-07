"""Isolated real SQLite plus explicit provider/billing fixtures, never a paid call."""
import asyncio
import concurrent.futures
from decimal import Decimal
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import uuid

from services.windows_native.asr import DurableTransport
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.costs import CostLedger, amount, token_usage
from services.windows_native.pipeline import provider_request
from services.windows_native.store import Store
from services.windows_native.tests import test_phase10_http as phase_http


class CostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.project = self.store.create('Explicit cost fixture', 'No actual external provider')
        self.other = self.store.create('Unrelated fixture', 'Unchanged')
        self.ledger = CostLedger(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def begin(self, operation='fixture', **overrides):
        return self.ledger.begin(**{
            'project_id': self.project['id'], 'provider': 'explicit-fixture', 'model': 'fixture-model',
            'operation': operation, 'request_sha256': 'a' * 64, **overrides})

    def budget(self, limit):
        self.project = self.ledger.set_budget(self.project['id'], self.project['revision'], limit)

    def test_amount_validation_and_usage_are_bounded_without_content(self):
        for value in [True, False, 1.2, 'NaN', 'Infinity', '-1', '1e50', '0.0000001', {}, ['1']]:
            with self.subTest(value=value), self.assertRaisesRegex(WorkflowError, 'COST_AMOUNT_INVALID'):
                amount(value)
        self.assertEqual(amount('0.000001'), Decimal('0.000001'))
        self.assertIsNone(amount(None))
        self.assertEqual(token_usage({'input_tokens': 2, 'output_tokens': 3, 'total_tokens': 5,
            'secret': 'must not persist', 'prompt': 'must not persist'}),
            {'input_tokens': 2, 'output_tokens': 3, 'total_tokens': 5})

    def test_exact_restart_and_unknown_billing_not_zero(self):
        original = self.store.get(self.other['id'])
        identifier = self.begin(estimated_cost='100')
        self.ledger.settle(identifier, status='response_received', usage={'total_tokens': 20})
        value = self.ledger.summary(self.project['id'])
        self.assertEqual(value['estimated_cost_total'], '100')
        self.assertIsNone(value['actual_cost_total'])
        self.assertEqual(value['known_actual_cost_subtotal'], '0')
        self.assertEqual(value['unknown_actual_cost_operations'], 1)
        self.assertFalse(value['actual_cost_complete'])
        self.assertFalse(value['full_project_cost_capture_verified'])
        self.assertFalse(value['provider_authorized'])
        self.assertIsNone(value['local_compute_cost'])
        self.assertEqual(value, CostLedger(Store(self.root)).summary(self.project['id']))
        self.assertEqual(original, self.store.get(self.other['id']))
        self.assertEqual(self.ledger.summary(self.other['id'])['records'], [])

    def test_billed_fixture_requires_hash_and_receipt_is_immutable(self):
        identifier = self.begin(estimated_cost='100')
        with self.assertRaisesRegex(WorkflowError, 'COST_BILLING_RECEIPT_REQUIRED'):
            self.ledger.settle(identifier, status='response_received', actual_cost='70')
        expected = self.ledger.settle(identifier, status='response_received', actual_cost='70',
            billing_receipt_sha256='b' * 64)
        replay = self.ledger.settle(identifier, status='response_received', actual_cost='70',
            billing_receipt_sha256='b' * 64)
        self.assertEqual(expected, replay)
        with self.assertRaisesRegex(WorkflowError, 'COST_IMMUTABLE_RECEIPT_CONFLICT'):
            self.ledger.settle(identifier, status='response_received', actual_cost='75', billing_receipt_sha256='c' * 64)
        self.assertEqual(self.ledger.summary(self.project['id'])['actual_cost_total'], '70')

    def test_unknown_intent_never_replays_and_request_drift_rejects(self):
        identifier = self.begin()
        self.assertTrue(self.ledger.pending(identifier))
        for record in [self.ledger, CostLedger(Store(self.root))]:
            with self.assertRaisesRegex(WorkflowError, 'ALREADY_DISPATCHED_NO_REPLAY'):
                record.begin(project_id=self.project['id'], provider='explicit-fixture', model='fixture-model',
                    operation='fixture', request_sha256='a' * 64)
        with self.assertRaisesRegex(WorkflowError, 'COST_OPERATION_CONFLICT'):
            self.begin(request_sha256='b' * 64)
        value = self.ledger.summary(self.project['id'])
        self.assertTrue(value['needs_attention'])
        self.assertIsNone(value['actual_cost_total'])
        self.assertIsNone(value['estimated_cost_total'])

    def test_budget_unknown_estimate_blocks_and_persists_refusal(self):
        self.budget('100')
        with self.assertRaisesRegex(WorkflowError, 'AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH'):
            self.begin()
        summary = self.ledger.summary(self.project['id'])
        self.assertEqual(summary['attempted_operations'], 0)
        self.assertEqual(summary['records'][0]['status'], 'needs_approval')
        self.assertTrue(summary['needs_approval'])
        self.assertFalse(summary['provider_authorized'])

    def test_budget_admission_is_atomic_under_two_concurrent_candidates(self):
        self.budget('100')
        def candidate(number):
            try:
                self.begin(f'candidate-{number}', estimated_cost='100')
                return 'admitted'
            except WorkflowError as error:
                return error.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            values = list(executor.map(candidate, range(2)))
        self.assertCountEqual(values, ['admitted', 'AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH'])
        self.assertEqual(self.ledger.summary(self.project['id'])['known_budget_exposure_vnd'], '100')

    def test_job_scope_and_frozen_budget(self):
        self.budget('10')
        job = self.store.enqueue(self.project['id'], self.project['revision'], 'content', uuid.uuid4().hex)
        for project, identifier in [(self.other['id'], job['id']), (self.project['id'], 'missing')]:
            with self.assertRaisesRegex(WorkflowError, 'COST_JOB_SCOPE_MISMATCH'):
                self.begin(project_id=project, job_id=identifier)
        with self.assertRaisesRegex(WorkflowError, 'AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH'):
            self.begin(job_id=job['id'], estimated_cost='11')
        with self.assertRaisesRegex(WorkflowError, 'PROJECT_BUSY'):
            self.budget(None)

    def test_budget_revision_invalidation_and_stale_write(self):
        before = self.store.get(self.project['id'])
        self.budget('0')
        self.assertEqual(self.project['revision'], before['revision'] + 1)
        self.assertIsNone(self.project['approval'])
        self.assertEqual(self.project['document']['cost_policy']['max_ai_cost_vnd'], '0')
        with self.assertRaisesRegex(WorkflowError, 'STALE_VERSION_RELOAD'):
            self.ledger.set_budget(self.project['id'], before['revision'], '5')
        self.assertEqual(len(self.store.versions(self.project['id'])), 2)

    def content_call(self, response=None, error=None):
        class StatusError(Exception): pass
        calls = []
        def create(**request):
            calls.append(request)
            if error:
                raise error
            return response or SimpleNamespace(usage={'input_tokens': 2, 'output_tokens': 3, 'total_tokens': 5})
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        openai = SimpleNamespace(APIStatusError=StatusError)
        job = self.store.enqueue(self.project['id'], self.project['revision'], 'content', uuid.uuid4().hex)
        out = self.root / 'provider-fixture'; out.mkdir()
        return client, openai, job, out, calls

    def test_content_budget_refuses_before_mock_dispatch(self):
        self.budget('0')
        client, sdk, job, out, calls = self.content_call()
        with self.assertRaisesRegex(WorkflowError, 'AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH'):
            provider_request(client, {'model': 'explicit-fixture'}, job, out, lambda _: None, sdk, cost_ledger=self.ledger)
        self.assertEqual(calls, [])
        self.assertFalse((out / 'content.intent.json').exists())

    def test_mock_response_usage_does_not_become_price_and_timeout_cannot_replay(self):
        client, sdk, job, out, calls = self.content_call(error=TimeoutError('private detail must not enter ledger'))
        with self.assertRaises(TimeoutError):
            provider_request(client, {'model': 'explicit-fixture'}, job, out, lambda _: None, sdk, cost_ledger=self.ledger)
        self.assertEqual(len(calls), 1)
        with self.assertRaisesRegex(WorkflowError, 'OPENAI_OUTCOME_UNKNOWN_NO_REPLAY'):
            provider_request(client, {'model': 'explicit-fixture'}, job, out, lambda _: None, sdk, cost_ledger=self.ledger)
        self.assertEqual(len(calls), 1)
        summary = self.ledger.summary(self.project['id'])
        self.assertEqual(summary['records'][0]['status'], 'outcome_unknown')
        self.assertNotIn('private detail', json.dumps(summary))
        self.assertIsNone(summary['actual_cost_total'])

    def test_mock_asr_wire_records_once_and_scope_distinguishes_assets(self):
        import httpx2
        job = self.store.enqueue(self.project['id'], self.project['revision'], 'content', uuid.uuid4().hex)
        observed = []
        def handler(request):
            observed.append(request.url.path)
            return httpx2.Response(200, json={'fixture': True})
        def factory(**kwargs):
            return httpx2.AsyncClient(transport=httpx2.MockTransport(handler), **kwargs)
        for binding in ['a' * 64, 'b' * 64]:
            transport = DurableTransport(self.root / binding[:4], binding, lambda _: None, client_factory=factory)
            transport.cost_ledger = self.ledger
            transport.cost_context = {'project_id': self.project['id'], 'job_id': job['id']}
            asyncio.run(transport.request('POST', '/v2/upload', 'fixture-secret', 5, content=b'synthetic'))
        summary = self.ledger.summary(self.project['id'])
        self.assertEqual(len(observed), 2)
        self.assertEqual(len(summary['records']), 2)
        self.assertNotEqual(summary['records'][0]['id'], summary['records'][1]['id'])
        self.assertTrue(all(row['status'] == 'response_received' for row in summary['records']))
        self.assertNotIn('fixture-secret', json.dumps(summary))


class CostHTTPTests(unittest.TestCase):
    # Reuse the isolated server/credential-free setup without inheriting its tests.
    setUp = phase_http.Phase10HTTPTests.setUp
    tearDown = phase_http.Phase10HTTPTests.tearDown
    start_server = phase_http.Phase10HTTPTests.start_server
    stop_server = phase_http.Phase10HTTPTests.stop_server
    request = phase_http.Phase10HTTPTests.request

    def test_summary_is_session_protected_and_nulls_preserved(self):
        self.assertIs(self.request('GET','/api/session')[1]['capabilities']['native_cost_ledger'], True)
        ledger = CostLedger(self.server.store)
        identifier = ledger.begin(project_id=self.project['id'], provider='explicit-fixture', model=None,
            operation='unknown-billing', request_sha256='a' * 64)
        ledger.settle(identifier, status='response_received')
        route = '/api/projects/' + self.project['id'] + '/cost-summary'
        status, value, _ = self.request('GET', route)
        self.assertEqual(status, 200)
        self.assertIsNone(value['actual_cost_total'])
        self.assertIsNone(value['estimated_cost_total'])
        status, _, _ = self.request('GET', route, headers={'Cookie': ''})
        self.assertEqual(status, 401)
        status, _, _ = self.request('GET', '/api/projects/' + '0' * 32 + '/cost-summary')
        self.assertEqual(status, 404)

    def test_budget_requires_csrf_exact_fields_and_revision(self):
        route = '/api/projects/' + self.project['id'] + '/cost-policy'
        payload = {'revision': self.project['revision'], 'max_ai_cost_vnd': '100'}
        self.assertEqual(self.request('POST', route, payload, {'X-VF-CSRF': ''})[0], 403)
        self.assertEqual(self.request('POST', route, {**payload, 'publish_enabled': True})[0], 400)
        status, value, _ = self.request('POST', route, payload)
        self.assertEqual(status, 200)
        self.assertIsNone(value['approval'])
        self.assertEqual(value['document']['proposal'], self.project['document']['proposal'])
        self.assertEqual(value['document']['cost_policy']['max_ai_cost_vnd'], '100')
        self.assertNotEqual(self.request('POST', route, payload)[0], 200)
        self.assertEqual(self.pipeline.calls, 0)
