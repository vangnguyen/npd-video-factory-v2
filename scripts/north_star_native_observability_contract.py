"""Fresh local HTTP/SQLite/idle-worker proof; all content providers are fixtures."""
from __future__ import annotations

import argparse
import http.client
import json
from pathlib import Path
import threading
import time
import uuid

from services.windows_native.contracts import file_sha
from services.windows_native.observability import Observer
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_multi_niche import ExplicitAIResearchFixture, ExplicitAIIdeasFixture
from services.windows_native.tests.test_workflow import proposal


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


def run(root, output, ffmpeg):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    config = Config(data_root=root / 'data', runtime_root=root / 'unused-runtime', ffmpeg_bin=ffmpeg.parent,
        secret_file=root / 'secrets' / 'absent-openai.env', assemblyai_secret_file=root / 'secrets' / 'absent-assemblyai.dpapi')
    records = []
    class ExplicitContentFixture:
        calls = 0
        def run(self, job, stage):
            self.calls += 1
            stage('content_explicit_fixture')
            return {'proposal': proposal(), 'provider_calls': 0, 'retries': 0}
    fixture = ExplicitContentFixture()
    server = LocalServer(0, config, pipeline=fixture, start_worker=False, observer=Observer(records.append))
    server.intelligence.research_provider = ExplicitAIResearchFixture(config.data_root / 'research-sources')
    server.intelligence.idea_provider = ExplicitAIIdeasFixture()
    http_thread = threading.Thread(target=server.serve_forever, daemon=True)
    http_thread.start()
    def request(method, path, body=None, authenticated=False, csrf=True):
        headers = {'Content-Type': 'application/json', 'X-Request-ID': 'PRIVATE_UNTRUSTED_REQUEST_ID'}
        if authenticated:
            headers['Cookie'] = 'vf_native_session=' + server.session
            if csrf:
                headers['X-VF-CSRF'] = server.csrf
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        response = connection.getresponse()
        value = json.loads(response.read())
        request_id = response.getheader('X-Request-ID')
        status = response.status
        connection.close()
        return {'status': status, 'body': value, 'request_id': request_id}
    def wait_for(check):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            value = check()
            if value:
                return value
            time.sleep(.01)
        raise AssertionError('Owned fixture operation did not finish')
    try:
        health = request('GET', '/healthz')
        initial = request('GET', '/readyz')
        assert health['status'] == 200 and initial['status'] == 503
        server.workers_enabled = True
        server.runner.start(); server.intelligence.start()
        ready = request('GET', '/readyz')
        assert ready['status'] == 200 and all(ready['body']['checks'].values())
        assert not config.secret_file.exists() and not config.assemblyai_secret_file.exists()
        created = request('POST', '/api/projects', {'name': 'Explicit private telemetry fixture',
            'prompt': 'PRIVATE_UPLOAD_TELEMETRY_SENTINEL'}, authenticated=True)
        assert created['status'] == 201
        project = created['body']
        no_session = request('GET', '/api/projects/' + project['id'])
        assert no_session['status'] == 401
        no_csrf = request('POST', '/api/projects/' + project['id'] + '/draft?access_token=PRIVATE_QUERY_SENTINEL',
            {'prompt': 'PRIVATE_BODY_SENTINEL'}, authenticated=True, csrf=False)
        assert no_csrf['status'] == 403
        job = server.store.enqueue(project['id'], project['revision'], 'content', uuid.uuid4().hex)
        server.runner.wake.set()
        wait_for(lambda: server.store.get_job(job['id'])['status'] == 'awaiting_review')
        assert fixture.calls == 1 and server.store.get(project['id'])['approval'] is None
        research = server.intelligence.create('AI education source checking', 'ai-education', ['https://example.com/explicit-fixture'])
        operation = server.intelligence.enqueue(research['run']['id'], research['run']['version'], 'research', uuid.uuid4().hex)
        observed = wait_for(lambda: next((op for op in server.intelligence.bundle(research['run']['id'])['operations'] if op['id'] == operation['id'] and op['status'] in {'SUCCEEDED', 'FAILED'}), None))
        assert observed['status'] == 'SUCCEEDED', 'Explicit research fixture must satisfy source relevance'
        server.runner.stop.set(); server.runner.wake.set(); server.runner.thread.join(timeout=2)
        stopped = request('GET', '/readyz')
        alive = request('GET', '/healthz')
        assert stopped['status'] == 503 and alive['status'] == 200
    finally:
        server.shutdown(); server.server_close(); http_thread.join(timeout=2)
        server.runner.thread.join(timeout=2) if server.runner.thread.ident else None
        assert not http_thread.is_alive() and not server.runner.thread.is_alive() and not server.intelligence.thread.is_alive()
    parsed = [json.loads(row) for row in records]
    http_records = [row for row in parsed if row['event'] == 'http_request']
    worker_records = [row for row in parsed if row['event'] in {'worker_step', 'worker_failed'}]
    intelligence_records = [row for row in parsed if row['event'].startswith('intelligence_')]
    assert len(http_records) == 8 and worker_records and len(intelligence_records) == 1
    assert all(row['request_id'] and row['duration'] is not None for row in parsed)
    serialized = json.dumps(parsed)
    assert 'PRIVATE_' not in serialized and server.session not in serialized and server.csrf not in serialized
    assert str(root) not in serialized and 'example.com' not in serialized
    assert all(not {'url', 'path', 'body', 'headers', 'token', 'exception'} & row.keys() for row in parsed)
    assert all(row['project_id'] == project['id'] and row['job_id'] == job['id'] for row in worker_records)
    assert intelligence_records[0]['job_id'] == operation['id'] and intelligence_records[0]['run_id'] == research['run']['id']
    write(output / 'health.json', {'before': health, 'after_worker_stop': alive})
    write(output / 'readiness.json', {'disabled_workers': initial, 'idle_core': ready, 'stopped_worker': stopped})
    write(output / 'request-logs.json', http_records)
    write(output / 'worker-logs.json', worker_records)
    write(output / 'intelligence-logs.json', intelligence_records)
    write(output / 'privacy.json', {'private_inputs_excluded': True, 'session_csrf_excluded': True,
        'untrusted_request_id_ignored': True, 'urls_paths_provider_errors_excluded': True,
        'http_request_count': len(http_records), 'all_owned_threads_closed': True})
    receipt = {'schema': 'north-star-native-observability-contract-v1', 'status': 'PASS',
        'local_real_http_sqlite_threads': True, 'readiness_scope': ready['body']['scope'],
        'fixture_content_research_ideas': True, 'external_provider_calls': 0, 'paid_operations': 0,
        'optional_providers_checked': False, 'runtime_integrity_acceptance_checked': False,
        'full_qc_acceptance': False, 'owner_uat_accepted': False, 'production_deployed': False,
        'exports_sha256': {path.name: file_sha(path) for path in output.glob('*.json')}}
    write(output / 'receipt.json', receipt)
    print(json.dumps({'status': 'PASS', 'exports': 7, 'http_requests': len(http_records), 'provider_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    args = parser.parse_args()
    run(args.fixture_root.resolve(), args.output_root.resolve(), args.ffmpeg.resolve())
