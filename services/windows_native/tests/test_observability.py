"""Actual local HTTP/SQLite/worker telemetry; no provider calls or acceptance."""
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from services.windows_native.observability import Observer, configure_logging, database_ready, route_context
from services.windows_native.pipeline import Config
from services.windows_native.server import Runner
from services.windows_native.store import Store
from services.windows_native.tests import test_phase10_http as phase_http
from services.windows_native.tests import test_workflow as workflow
from services.windows_native.tests.test_multi_niche import ExplicitAIResearchFixture
from services.windows_native.intelligence_service import IntelligenceService


FFMPEG_BIN = Path('C:/Users/PC/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin')


class ObserverTests(unittest.TestCase):
    def test_only_fixed_fields_and_safe_identifiers_reach_sink(self):
        records = []
        observer = Observer(records.append)
        observer.emit('http_request', request_id='private-upload-name', job_id='Bearer private-token',
            project_id='b' * 32, stage='my-private-step', provider='secret-provider-key',
            duration=float('nan'), status=500, method='private-method', route='private-url')
        record = json.loads(records[0])
        self.assertEqual(record['project_id'], 'b' * 32)
        for field in ('request_id', 'job_id', 'provider', 'duration', 'method'):
            self.assertIsNone(record[field])
        self.assertEqual(record['route'], 'other')
        self.assertEqual(record['stage'], 'worker')
        self.assertNotIn('private', records[0]); self.assertNotIn('secret', records[0])
        observer.emit('unregistered-private-event')
        self.assertEqual(len(records), 1)

    def test_sink_failure_never_changes_operation(self):
        def failed(_record):
            raise OSError('synthetic sink failure')
        Observer(failed).emit('worker_step', duration=.2)

    def test_official_worker_ids_stages_and_providers_are_fixed_and_content_free(self):
        records=[];observer=Observer(records.append)
        for prefix,stage,provider in [('noas_','official_analytics_read','youtube-analytics-api'),
            ('nack_','official_account_read','youtube-data-api-publishing'),('nopq_','official_publish_queue','youtube-data-api-publishing')]:
            observer.emit('worker_step',job_id=prefix+'a'*32,project_id='b'*32,stage=stage,provider=provider,duration=.1)
            value=json.loads(records[-1]);self.assertEqual(value['job_id'],prefix+'a'*32);self.assertEqual(value['stage'],stage);self.assertEqual(value['provider'],provider)
        self.assertNotIn('token',json.dumps(records));self.assertNotIn('upload_id',json.dumps(records))

    def test_official_prefix_does_not_admit_arbitrary_private_identifiers(self):
        records=[];observer=Observer(records.append)
        for identity in ('noas_Bearer-private-token','nack_'+'a'*33,'nopq_'+('a'*32)+'/private','untrusted_'+'a'*32):
            observer.emit('worker_step',job_id=identity,provider='private-provider',stage='private-stage')
            value=json.loads(records[-1]);self.assertIsNone(value['job_id']);self.assertIsNone(value['provider']);self.assertEqual(value['stage'],'worker')
        self.assertNotIn('private',json.dumps(records))

    def test_cli_logging_does_not_enable_sdk_or_global_logging(self):
        logger = logging.getLogger('video_factory.native')
        prior = (list(logger.handlers), logger.level, logger.propagate)
        root_level = logging.getLogger().level
        sdk_level = logging.getLogger('httpx').level
        try:
            configure_logging(); configure_logging()
            self.assertEqual(logging.getLogger().level, root_level)
            self.assertEqual(logging.getLogger('httpx').level, sdk_level)
            self.assertFalse(logger.propagate)
            self.assertEqual(len(logger.handlers), len(prior[0]) or 1)
        finally:
            for handler in logger.handlers:
                if handler not in prior[0]:
                    handler.close()
            logger.handlers, logger.level, logger.propagate = prior

    def test_routes_discard_query_tokens_paths_and_unbounded_private_ids(self):
        self.assertEqual(route_context('/api/projects/' + 'a' * 32 + '/draft?access_token=secret'), ('project', 'a' * 32, None))
        self.assertEqual(route_context('/api/jobs/' + 'b' * 32 + '/logs?filename=private'), ('job', None, 'b' * 32))
        self.assertEqual(route_context('/api/projects/' + 'a' * 33 + '/private'), ('other', None, None))
        self.assertEqual(route_context('/private-uploads/customer-name.mp4'), ('other', None, None))

    def test_missing_corrupt_or_linked_database_fails_without_creation_or_following(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            missing = base / 'missing.sqlite3'
            self.assertFalse(database_ready(missing, {'projects'})); self.assertFalse(missing.exists())
            bad = base / 'corrupt.sqlite3'; bad.write_bytes(b'not SQLite')
            self.assertFalse(database_ready(bad, {'projects'}))
            store = Store(base / 'owned')
            self.assertTrue(database_ready(store.db, {'projects', 'jobs'}))
            self.assertFalse(database_ready(store.db, {'unknown_table'}))
            linked = base / 'linked'
            if os.name == 'nt':
                assert linked.absolute().parent == base.absolute() and store.root.absolute().parent == base.absolute()
                subprocess.run(['cmd', '/c', 'mklink', '/J', str(linked), str(store.root)], check=True, capture_output=True)
            else:
                linked.symlink_to(store.root, target_is_directory=True)
            try:
                with patch('services.windows_native.observability.sqlite3.connect', side_effect=AssertionError('Must not follow linked database')):
                    self.assertFalse(database_ready(linked / 'workflow.sqlite3', {'projects'}))
            finally:
                linked.rmdir() if os.name == 'nt' else linked.unlink()

    def test_actual_intelligence_operations_keep_null_provider_and_content_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Config(data_root=root)
            records = []
            class FailedIdeas:
                def generate(self, *args):
                    raise ValueError('PRIVATE PROVIDER KEY AND RESPONSE')
            service = IntelligenceService(config, Store(root),
                research_provider=ExplicitAIResearchFixture(root / 'research-sources'),
                idea_provider=FailedIdeas(), observer=Observer(records.append))
            bundle = service.create('PRIVATE editorial query', 'ai-education', ['https://example.com/explicit-fixture'])
            for action in ('research', 'ideas'):
                operation = service.enqueue(bundle['run']['id'], bundle['run']['version'], action, uuid.uuid4().hex)
                self.assertTrue(service.run_one())
                bundle = service.bundle(bundle['run']['id'])
                record = json.loads(records[-1])
                self.assertEqual(record['job_id'], operation['id']); self.assertEqual(record['run_id'], bundle['run']['id'])
                self.assertIsNone(record['project_id']); self.assertIsNone(record['provider'])
                self.assertEqual(record['stage'], action)
            self.assertEqual(json.loads(records[0])['event'], 'intelligence_completed')
            self.assertEqual(json.loads(records[1])['event'], 'intelligence_failed')
            self.assertEqual(bundle['operations'][0]['status'], 'FAILED')
            self.assertNotIn('PRIVATE', ''.join(records)); self.assertNotIn('example.com', ''.join(records))

    def test_actual_worker_success_and_failure_logs_no_prompt_or_raw_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary)); project = store.create('Private customer name', 'PRIVATE UPLOADED CONTENT')
            records = []
            class FixturePipeline:
                def run(self, job, stage):
                    stage('content_attempt_private_suffix')
                    return {'proposal': workflow.proposal(), 'provider_calls': 0, 'retries': 0}
            first = store.enqueue(project['id'], 1, 'content', uuid.uuid4().hex)
            self.assertTrue(Runner(store, FixturePipeline(), observer=Observer(records.append)).run_one())
            self.assertEqual(store.get_job(first['id'])['status'], 'awaiting_review')
            class FailingFixture:
                def run(self, job, stage):
                    stage('PRIVATE SECRET STEP')
                    raise ValueError('PRIVATE TOKEN AND PROVIDER BODY')
            refreshed = store.get(project['id'])
            second = store.enqueue(project['id'], refreshed['revision'], 'content', uuid.uuid4().hex)
            self.assertTrue(Runner(store, FailingFixture(), observer=Observer(records.append)).run_one())
            self.assertEqual(store.get_job(second['id'])['status'], 'failed')
            parsed = [json.loads(row) for row in records]
            self.assertTrue(any(row['event'] == 'worker_failed' for row in parsed))
            self.assertTrue(all(row['project_id'] == project['id'] and row['job_id'] in {first['id'], second['id']} for row in parsed))
            self.assertTrue(all(row['request_id'] == row['job_id'] and row['duration'] >= 0 for row in parsed))
            self.assertNotIn('PRIVATE', ''.join(records)); self.assertNotIn('private_suffix', ''.join(records))


class ObservabilityHTTPTests(unittest.TestCase):
    setUp = phase_http.Phase10HTTPTests.setUp
    tearDown = phase_http.Phase10HTTPTests.tearDown
    start_server = phase_http.Phase10HTTPTests.start_server
    stop_server = phase_http.Phase10HTTPTests.stop_server
    request = phase_http.Phase10HTTPTests.request

    def capture(self):
        records = []
        self.server.observer = Observer(records.append)
        return records

    def test_liveness_without_session_preserves_database_and_host_boundary(self):
        records = self.capture()
        before = self.server.store.get(self.project['id'])
        status, value, headers = self.request('GET', '/healthz', headers={'Cookie': '', 'X-Request-ID': 'private-token'})
        self.assertEqual(status, 200); self.assertEqual(value['status'], 'alive')
        self.assertRegex(headers['X-Request-ID'], '^[a-f0-9]{32}$')
        self.assertEqual(self.server.store.get(self.project['id']), before)
        self.assertEqual(self.request('GET', '/healthz', headers={'Host': 'hostile.example'})[0], 403)
        deadline = time.monotonic() + 1
        while len(records) < 2 and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertEqual(len(records), 2)
        self.assertNotIn('private-token', ''.join(records)); self.assertNotIn(self.server.session, ''.join(records))
        self.assertEqual(json.loads(records[0])['request_id'], headers['X-Request-ID'])

    def test_disabled_workers_missing_tools_and_database_are_not_ready(self):
        status, value, _ = self.request('GET', '/readyz', headers={'Cookie': ''})
        self.assertEqual(status, 503); self.assertEqual(value['status'], 'not_ready')
        self.assertTrue(value['checks']['workflow_database']); self.assertTrue(value['checks']['intelligence_database'])
        self.assertFalse(value['checks']['production_worker']); self.assertFalse(value['checks']['ffmpeg_tools_present'])
        self.assertNotIn(str(self.config.data_root), json.dumps(value))
        self.assertIs(value['optional_providers_checked'], False); self.assertEqual(value['provider_calls'], 0)

    def test_actual_idle_core_is_ready_without_secrets_gpu_or_optional_provider(self):
        self.assertTrue((FFMPEG_BIN / 'ffmpeg.exe').is_file())
        self.server.config = replace(self.server.config, ffmpeg_bin=FFMPEG_BIN)
        self.server.workers_enabled = True
        self.server.runner.start(); self.server.intelligence.start()
        try:
            status, value, _ = self.request('GET', '/readyz', headers={'Cookie': ''})
            self.assertEqual(status, 200); self.assertTrue(all(value['checks'].values()))
            self.assertFalse(self.config.secret_file.exists()); self.assertFalse(self.config.assemblyai_secret_file.exists())
            self.server.runner.stop.set(); self.server.runner.wake.set(); self.server.runner.thread.join(timeout=2)
            self.assertEqual(self.request('GET', '/readyz')[0], 503)
            self.assertEqual(self.request('GET', '/healthz')[0], 200)
        finally:
            self.server.runner.stop.set(); self.server.runner.wake.set(); self.server.runner.thread.join(timeout=2)

    def test_failed_private_request_has_safe_correlated_log_and_no_body(self):
        records = self.capture()
        path = '/api/projects/' + self.project['id'] + '/draft?access_token=PRIVATEQUERY'
        status, _, headers = self.request('POST', path, {'prompt': 'PRIVATE UPLOAD', 'secret': 'PRIVATE TOKEN'})
        self.assertGreaterEqual(status, 400)
        deadline = time.monotonic() + 1
        while not records and time.monotonic() < deadline:
            time.sleep(.005)
        record = json.loads(records[0])
        self.assertEqual(record['request_id'], headers['X-Request-ID'])
        self.assertEqual(record['project_id'], self.project['id']); self.assertEqual(record['status'], status)
        self.assertIsNone(record['job_id']); self.assertIsNone(record['provider'])
        self.assertNotIn('PRIVATE', ''.join(records)); self.assertNotIn(self.server.csrf, ''.join(records))
