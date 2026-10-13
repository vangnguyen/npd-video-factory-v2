"""Durable wire gates on isolated SQLite and synthetic HTTP transports only."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from email.utils import format_datetime
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
import uuid

import httpx
from services.windows_native.contracts import WorkflowError
from services.windows_native.stock import NativeStock, COOLDOWN_FAILURE, LEASE_FAILURE, WIRE_LEASE_SECONDS, retry_delay
from services.windows_native.stock_models import StockSearch, StockDownload
from services.windows_native.stock_registry import StockFactory, StockCredential
from services.windows_native.store import Store
from services.windows_native.tests import test_stock as fixture


class StockCooldownTests(unittest.TestCase):
    setUp = fixture.StockTests.setUp
    tearDown = fixture.StockTests.tearDown
    wire = fixture.StockTests.wire

    def factory_for(self, wire, key='explicit-fixture-key', provider='pexels'):
        return StockFactory(provider, StockCredential(api_key=key, enabled=True),
            owner_enabled=True, transport=httpx.MockTransport(wire))

    def restart(self, factory=None):
        self.service.close(); self.factory = factory or self.factory
        self.service = NativeStock(Store(self.root), self.config, workspace_id='wsp_stock_fixture',
            factories={'pexels': self.factory}, clock=lambda: self.clock[0])
        return self.service

    def create(self, query, service=None, provider='pexels', project=None):
        service = service or self.service; project = project or self.project
        factory = service.factories[provider]
        job, _ = service.create(project['id'], StockSearch(revision=project['revision'], provider=provider,
            query=query, media_type='image', orientation='landscape', limit=3,
            fixture_acknowledged=factory.mode == 'fixture', external_acknowledged=factory.mode == 'official',
            request_key='stock-cooldown-' + uuid.uuid4().hex), actor='fixture-owner')
        return job

    def process_job(self, job, service=None):
        service = service or self.service
        service.process()
        return service.get(job['project_id'], job['stock_id'])

    def throttle(self, delay='600'):
        def wire(request):
            self.calls.append(request.url.path)
            return httpx.Response(429, headers={'Retry-After': delay})
        self.restart(self.factory_for(wire))
        first = self.process_job(self.create('throttle-first'))
        self.assertEqual(first['status'], 'retry_scheduled')
        self.assertEqual(first['attempts'], 1)
        return first

    def test_fresh_process_second_job_respects_first_retry_after_without_wire_or_budget_use(self):
        before = deepcopy(self.store.get(self.project['id'])); first = self.throttle()
        code = '''import json,sys,httpx
from pathlib import Path
from services.windows_native.store import Store
from services.windows_native.pipeline import Config
from services.windows_native.stock import NativeStock
from services.windows_native.stock_registry import StockFactory,StockCredential
from services.windows_native.stock_models import StockSearch
calls=[]
def forbidden(request):
 calls.append(1);raise AssertionError('COOLDOWN MUST PREVENT WIRE')
root=Path(sys.argv[1]);store=Store(root)
factory=StockFactory('pexels',StockCredential(api_key='explicit-fixture-key',enabled=True),owner_enabled=True,transport=httpx.MockTransport(forbidden))
service=NativeStock(store,Config(data_root=root),workspace_id='wsp_stock_fixture',factories={'pexels':factory},clock=lambda:float(sys.argv[3]))
project=store.get(sys.argv[2]);job,_=service.create(project['id'],StockSearch(revision=project['revision'],provider='pexels',query='fresh-process-second',media_type='image',orientation='landscape',limit=3,fixture_acknowledged=True,request_key='stock-fresh-process-second-job'),actor='fixture-owner')
service.process();saved=service.get(project['id'],job['stock_id'])
print(json.dumps({'status':saved['status'],'attempts':saved['attempts'],'next_at':saved['next_at'],'failure_code':saved['failure_code'],'calls':len(calls)}))
'''
        child = subprocess.run([sys.executable, '-X', 'utf8', '-c', code, str(self.root), self.project['id'], str(self.clock[0])],
            capture_output=True, text=True, check=True, timeout=30)
        actual = json.loads(child.stdout)
        self.assertEqual(actual, {'status': 'retry_scheduled', 'attempts': 0, 'next_at': first['next_at'],
            'failure_code': COOLDOWN_FAILURE, 'calls': 0})
        self.assertEqual(self.store.get(self.project['id']), before)

    def test_long_retry_after_is_not_truncated_and_repeated_waits_never_exhaust_wire_budget(self):
        first = self.throttle('7200')
        self.assertEqual(first['next_at'], self.clock[0] + 7200)
        self.restart(self.factory_for(lambda request: (_ for _ in ()).throw(AssertionError('No cooled wire'))))
        for index in range(4):
            job = self.create('second-' + str(index)); saved = self.process_job(job)
            self.assertEqual((saved['status'], saved['attempts'], saved['failure_code']), ('retry_scheduled', 0, COOLDOWN_FAILURE))
            self.assertEqual(saved['next_at'], first['next_at'])
        for _ in range(4): self.assertIsNone(self.service.process())
        self.assertEqual(len(self.calls), 1)

    def test_expiry_resumes_real_mock_dispatch_and_cancellation_does_not_clear_provider_cooldown(self):
        first = self.throttle()
        self.service.cancel(self.project['id'], first['stock_id'], fingerprint=first['request_fingerprint'], actor='fixture-owner')
        self.restart(self.factory_for(self.wire))
        second = self.process_job(self.create('after-cancel'))
        self.assertEqual(second['failure_code'], COOLDOWN_FAILURE); self.assertEqual(len(self.calls), 1)
        self.clock[0] = first['next_at'] + 1
        resumed = self.process_job(second)
        self.assertEqual(resumed['status'], 'succeeded'); self.assertEqual(resumed['attempts'], 1)
        self.assertEqual(resumed['result']['fixture_wire_attempts'], 1); self.assertEqual(len(self.calls), 2)

    def test_successful_trusted_cache_hit_still_succeeds_with_zero_wire_during_cooldown(self):
        warm = self.process_job(self.create('cached-query'))
        self.assertEqual(warm['status'], 'succeeded')
        self.throttle(); before = len(self.calls)
        self.restart(self.factory_for(lambda request: (_ for _ in ()).throw(AssertionError('Cache must not dispatch'))))
        cached = self.process_job(self.create('cached-query'))
        self.assertEqual(cached['status'], 'succeeded')
        self.assertEqual((cached['result']['fixture_wire_attempts'], cached['result']['actual_provider_calls']), (0, 0))
        self.assertEqual(len(self.calls), before)
        left = cached['result']['candidates'][0]; right = warm['result']['candidates'][0]
        for key in ('candidate_id', 'provider_asset_id', 'source_reference', 'license', 'rights_status', 'production_eligible'):
            self.assertEqual(left[key], right[key])

    def test_concurrent_workers_share_short_wire_lease_then_immediate_cooldown(self):
        entered = threading.Event(); release = threading.Event(); calls = []
        async def slow(request):
            calls.append(request.url.path); entered.set()
            await asyncio.to_thread(release.wait, 5)
            return httpx.Response(429, headers={'Retry-After': '600'})
        self.restart(self.factory_for(slow)); first = self.create('in-flight-first')
        thread = threading.Thread(target=self.service.process); thread.start()
        other = None
        try:
            self.assertTrue(entered.wait(3))
            other = NativeStock(Store(self.root), self.config, workspace_id='wsp_stock_fixture',
                factories={'pexels': self.factory}, clock=lambda: self.clock[0])
            second = self.create('concurrent-second', other)
            blocked = self.process_job(second, other)
            self.assertEqual((blocked['failure_code'], blocked['attempts']), (LEASE_FAILURE, 0))
            self.assertEqual(len(calls), 1)
            release.set(); thread.join(5); self.assertFalse(thread.is_alive())
            self.clock[0] += WIRE_LEASE_SECONDS + 1
            cooled = self.process_job(second, other)
            self.assertEqual((cooled['failure_code'], cooled['attempts']), (COOLDOWN_FAILURE, 0))
            self.assertEqual(cooled['next_at'], self.service.get(self.project['id'], first['stock_id'])['next_at'])
            self.assertEqual(len(calls), 1)
        finally:
            release.set(); thread.join(5)
            if other: other.close()

    def test_crashed_wire_lease_expires_and_stale_owner_cannot_release_new_claim(self):
        first = self.create('crashed-wire-fixture'); counter = {'wire_attempts': 0, 'wire_leases': {}}
        old = self.service.wire_admit(first['snapshot'], 'api', first['stock_id'], counter)
        self.service.cancel(self.project['id'], first['stock_id'], fingerprint=first['request_fingerprint'], actor='fixture-owner')
        self.restart(); second = self.process_job(self.create('restart-during-old-lease'))
        self.assertEqual((second['failure_code'], second['attempts']), (LEASE_FAILURE, 0))
        self.assertEqual(self.calls, [])
        self.clock[0] += WIRE_LEASE_SECONDS + 1
        new_counter = {'wire_attempts': 0, 'wire_leases': {}}
        new = self.service.wire_admit(second['snapshot'], 'api', second['stock_id'], new_counter)
        scope = self.service.wire_scope(first['snapshot'], 'api')
        self.service.wire_release(scope, old)
        with self.store.transaction() as con: self.assertEqual(self.service.cooldown_row(con, scope)['lease_id'], new)
        self.service.wire_release(scope, new)
        resumed = self.process_job(second)
        self.assertEqual(resumed['status'], 'succeeded'); self.assertEqual(len(self.calls), 1)

    def test_configuration_rotation_other_workspace_root_and_provider_have_separate_gates(self):
        self.throttle()
        rotated = self.factory_for(lambda request: httpx.Response(200, json={'photos': [fixture.photo()]}), key='explicit-rotated-fixture-key')
        self.restart(rotated)
        self.assertEqual(self.process_job(self.create('rotated-config'))['status'], 'succeeded')
        new_root = Path(self.temp.name) / 'other-state'; store = Store(new_root); config = replace(self.config, data_root=new_root)
        project = store.create('Independent workspace fixture', 'Explicit isolated test input')
        factory = self.factory_for(lambda request: httpx.Response(200, json={'photos': [fixture.photo()]}))
        other = NativeStock(store, config, workspace_id='wsp_other_stock_fixture', factories={'pexels': factory}, clock=lambda: self.clock[0])
        try:
            job = self.create('other-workspace-root', other, project=project)
            self.assertEqual(self.process_job(job, other)['status'], 'succeeded')
        finally: other.close()
        with self.assertRaisesRegex(WorkflowError, 'WORKSPACE_MISMATCH'):
            NativeStock(self.store, self.config, workspace_id='wsp_foreign_stock_fixture')
        pixabay = self.factory_for(lambda request: httpx.Response(200, json={'hits': []}), provider='pixabay')
        self.service.factories['pixabay'] = pixabay
        self.assertEqual(self.process_job(self.create('independent-provider', provider='pixabay'))['status'], 'succeeded')

    def test_http_date_and_absolute_reset_keep_durable_full_deadline(self):
        self.clock[0] = float(int(self.clock[0])); deadline = self.clock[0] + 7200
        date = format_datetime(datetime.fromtimestamp(deadline, timezone.utc), usegmt=True)
        first = self.throttle(date); self.assertEqual(first['next_at'], deadline)
        self.assertEqual(retry_delay(httpx.Headers({'X-RateLimit-Reset': str(int(deadline))}), self.clock[0]), 7200)
        self.assertEqual(retry_delay(httpx.Headers({'Retry-After': 'not-a-date'}), self.clock[0]), 5)

    def test_tampered_cooldown_evidence_refuses_wire_and_preserves_old_history(self):
        first = self.throttle(); before = self.service.get(self.project['id'], first['stock_id'])
        with self.store.transaction() as con: con.execute('UPDATE native_stock_provider_cooldowns SET cooldown_until=cooldown_until+1')
        self.restart(self.factory_for(lambda request: (_ for _ in ()).throw(AssertionError('No invalid-gate wire'))))
        second = self.process_job(self.create('invalid-gate'))
        self.assertEqual((second['status'], second['failure_code']), ('failed', 'NATIVE_STOCK_PROVIDER_COOLDOWN_INVALID'))
        self.assertEqual(self.service.get(self.project['id'], first['stock_id']), before)
        self.assertEqual(len(self.calls), 1)

    def test_successful_monthly_api_quota_zero_survives_restart_but_cache_and_cdn_remain_available(self):
        # Official Pexels headers can announce exhaustion on successful 2xx:
        # https://www.pexels.com/api/documentation/ (UNIX monthly reset).
        self.clock[0] = float(int(self.clock[0])); deadline = self.clock[0] + 31*86400
        wire_calls = []
        def wire(request):
            wire_calls.append((request.url.host, request.url.path))
            if request.url.path == '/v1/photos/11':
                return httpx.Response(200, json=fixture.photo(), headers={
                    'X-Ratelimit-Remaining': '0', 'X-Ratelimit-Reset': str(int(deadline))})
            if request.url.path == '/v1/search': return httpx.Response(200, json={'photos': [fixture.photo()]})
            if request.url.host == 'images.pexels.com':
                return httpx.Response(200, content=fixture.pixels(), headers={'Content-Type': 'image/png'})
            raise AssertionError('Unexpected synthetic stock request')
        self.restart(self.factory_for(wire)); search = self.process_job(self.create('quota-cached-search'))
        candidate = search['result']['candidates'][0]
        def download():
            job, _ = self.service.create(self.project['id'], StockDownload(revision=self.project['revision'],
                search_id=search['stock_id'], candidate_id=candidate['candidate_id'],
                expected_result_sha256=search['result_sha256'], expected_candidate_sha256=fixture.digest(candidate),
                fixture_acknowledged=True, request_key='quota-download-' + uuid.uuid4().hex), actor='fixture-owner')
            return self.process_job(job)
        first = download()
        self.assertEqual(first['status'], 'succeeded'); self.assertEqual(first['result']['fixture_wire_attempts'], 2)
        self.restart(self.factory_for(wire))
        cached = self.process_job(self.create('quota-cached-search'))
        self.assertEqual(cached['status'], 'succeeded'); self.assertEqual(cached['result']['fixture_wire_attempts'], 0)
        blocked = self.process_job(self.create('quota-new-uncached-search'))
        self.assertEqual((blocked['failure_code'], blocked['attempts'], blocked['next_at']), (COOLDOWN_FAILURE, 0, deadline))
        second = download()
        self.assertEqual(second['status'], 'succeeded'); self.assertEqual(second['result']['fixture_wire_attempts'], 1)
        self.assertEqual(len(wire_calls), 4)
        with self.store.transaction() as con:
            rows = con.execute('SELECT * FROM native_stock_provider_cooldowns').fetchall()
        api = next(row for row in rows if row['request_class'] == 'api')
        evidence = json.loads(api['evidence_json'])
        self.assertEqual((api['cooldown_until'], evidence['basis'], evidence['status_code'], evidence['remaining']),
            (deadline, 'successful_api_quota_exhaustion', 200, 0))
        self.assertTrue(all(row['cooldown_until'] == 0 for row in rows if row['request_class'].startswith('cdn:')))
        self.clock[0] = deadline + 1
        resumed = self.process_job(blocked)
        self.assertEqual(resumed['status'], 'succeeded'); self.assertEqual(resumed['attempts'], 1)

    def test_missing_or_malformed_successful_quota_headers_do_not_invent_exhaustion(self):
        for headers in ({}, {'X-Ratelimit-Remaining': '0'},
            {'X-Ratelimit-Remaining': 'unknown', 'X-Ratelimit-Reset': str(int(self.clock[0]+7200))},
            {'X-Ratelimit-Remaining': '0', 'X-Ratelimit-Reset': 'not-an-epoch'},
            {'X-Ratelimit-Remaining': '0', 'X-Ratelimit-Reset': str(int(self.clock[0]-1))}):
            self.restart(self.factory_for(lambda request, h=headers: httpx.Response(200, json={'photos': [fixture.photo()]}, headers=h)))
            result = self.process_job(self.create('no-valid-quota-' + uuid.uuid4().hex))
            self.assertEqual(result['status'], 'succeeded')
            with self.store.transaction() as con:
                row = con.execute("SELECT * FROM native_stock_provider_cooldowns WHERE request_class='api'").fetchone()
            self.assertEqual(row['cooldown_until'], 0)
            self.assertEqual(json.loads(row['evidence_json']), {})


if __name__ == '__main__': unittest.main()
