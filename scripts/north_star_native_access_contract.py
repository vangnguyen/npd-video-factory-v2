"""Isolated actual Native HTTP/session/SQLite proof with four fixture identities."""
from __future__ import annotations

import argparse
import hashlib
import http.client
from http.cookies import SimpleCookie
import json
from pathlib import Path
import threading
import uuid

from services.windows_native.access import NativeAccess
from services.windows_native.contracts import file_sha
from services.windows_native.observability import Observer
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_human_identity import fixture
from services.windows_native.tests.test_multi_niche import build_tech_project


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


def run(root, output, ffmpeg):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    _config, original_store, _service, project, _bundle, unrelated = build_tech_project(root / 'data')
    config = Config(data_root=root / 'data', runtime_root=root / 'unused-runtime', ffmpeg_bin=ffmpeg.parent,
        secret_file=root / 'secrets' / 'absent-openai.env', assemblyai_secret_file=root / 'secrets' / 'absent-assemblyai.dpapi')
    registry = {'version': 1, 'tokens': {}}; tokens = {}
    for role in ('owner', 'editor', 'reviewer', 'viewer'):
        _raw, data = fixture(role); record = data['tokens']['explicit-fixture']
        identifier = 'explicit-' + role; raw = 'vf1.' + identifier + '.' + 'x' * 48
        record.update(token_id=identifier, subject='usr:' + identifier, display_name='EXPLICIT ' + role.upper() + ' FIXTURE; NOT OWNER UAT',
            token_sha256=hashlib.sha256(raw.encode()).hexdigest())
        registry['tokens'][identifier] = record; tokens[role] = raw
    profile = root / 'secrets' / 'fixture-registry.json'; profile.parent.mkdir()
    profile.write_text(json.dumps(registry), encoding='utf-8')
    access = NativeAccess.from_file(profile, 'wsp_native_fixture', config.data_root)
    logs, operations, clients, secrets_in_memory = [], [], {}, list(tokens.values())
    class NoProvider:
        def run(self, _job, _stage):
            raise AssertionError('No provider or production dispatch authorized in this contract')
    server = LocalServer(0, config, pipeline=NoProvider(), start_worker=False, access=access, observer=Observer(logs.append))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    def request(method, path, body=None, *, role=None, expected=200, headers=None):
        request_headers = {'Content-Type': 'application/json'}
        if role in clients:
            cookie, csrf = clients[role]; request_headers.update(Cookie='vf_native_session=' + cookie, **{'X-VF-CSRF': csrf})
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        connection.request(method, path, json.dumps(body) if body is not None else None, request_headers)
        response = connection.getresponse(); metadata = dict(response.getheaders()); raw = response.read(); connection.close()
        value = json.loads(raw) if metadata.get('Content-Type', '').startswith('application/json') else raw
        operations.append({'method': method, 'path': path.split('?', 1)[0], 'role': role, 'status': response.status,
            'request_id': metadata['X-Request-ID']})
        assert response.status == expected, (method, path, response.status, value.get('code') if isinstance(value, dict) else 'static')
        return value, metadata
    try:
        _value, headers = request('GET', '/?new=1', expected=303)
        assert headers['Location'] == '/login'
        request('GET', '/login'); request('GET', '/api/session', expected=401)
        public = {}
        for role in tokens:
            value, metadata = request('POST', '/api/login', {'token': tokens[role]}, role=role)
            cookies = SimpleCookie(); cookies.load(metadata['Set-Cookie']); cookie = cookies['vf_native_session']
            assert cookie['httponly'] and cookie['samesite'] == 'Strict'
            clients[role] = cookie.value, value['csrf']; secrets_in_memory.extend(clients[role])
            value, metadata = request('GET', '/api/session', role=role)
            assert 'Set-Cookie' not in metadata and value['access']['role'] == role
            public[role] = value['access']
            request('GET', '/production', role=role)
            request('GET', '/api/projects/' + project['id'], role=role)
        request('GET', '/settings/assemblyai', role='viewer', expected=403)
        request('GET', '/settings/assemblyai', role='owner')
        request('POST', '/api/projects', {'name': 'UNAUTHORIZED PRIVATE INPUT'}, role='viewer', expected=403)
        request('POST', '/api/projects', {'name': 'UNAUTHORIZED PRIVATE INPUT'}, role='reviewer', expected=403)
        before = server.store.shot_view(project['id']); shot = before['shot_timeline']['shots'][0]
        edited, _metadata = request('POST', '/api/projects/' + project['id'] + '/shots', {
            'revision': before['revision'], 'operation': {'type': 'update', 'shot_id': shot['shot_id'],
                'values': {'on_screen_text': 'Explicit editor capability acceptance'}}}, role='editor')
        assert edited['revision'] == before['revision'] + 1 and edited['approval'] is None
        request('POST', '/api/projects/' + project['id'] + '/approve', {}, role='editor', expected=403)
        request('POST', '/api/projects/' + project['id'] + '/cost-policy', {}, role='editor', expected=403)
        request('POST', '/api/projects/' + project['id'] + '/script-review', {
            'revision': edited['revision'], 'reviewer': 'FORGED OWNER', 'acknowledged': False,
            'script_sha256': file_sha(profile)}, role='reviewer', expected=400)
        reviewed, _metadata = request('POST', '/api/projects/' + project['id'] + '/script-review', {
            'revision': edited['revision'], 'reviewer': 'FORGED OWNER', 'acknowledged': True,
            'script_sha256': hashlib.sha256(edited['document']['proposal']['narration'].encode()).hexdigest()}, role='reviewer')
        with server.store.transaction() as con:
            review = server.store.current_script_review(con, reviewed)
        assert review['reviewer'] == 'explicit-reviewer' and review['media_approved'] is False and review['production_approved'] is False
        assert reviewed['approval'] is None and reviewed['jobs'] == []
        request('POST', '/api/projects/' + project['id'] + '/jobs', {
            'revision': edited['revision'], 'kind': 'render', 'request_key': uuid.uuid4().hex}, role='editor', expected=409)
        request('POST', '/api/projects/' + project['id'] + '/cost-policy', {
            'revision': edited['revision'], 'max_ai_cost_vnd': '100'}, role='owner', expected=403,
            headers={'X-VF-CSRF': clients['editor'][1]})
        final, _metadata = request('POST', '/api/projects/' + project['id'] + '/cost-policy', {
            'revision': edited['revision'], 'max_ai_cost_vnd': '100'}, role='owner')
        assert final['document']['cost_policy']['max_ai_cost_vnd'] == '100' and final['approval'] is None
        request('POST', '/api/logout', {}, role='viewer'); request('GET', '/api/projects', role='viewer', expected=401)
        registry['tokens']['explicit-editor']['enabled'] = False
        profile.write_text(json.dumps(registry), encoding='utf-8')
        for role in ('owner', 'editor', 'reviewer'):
            request('GET', '/api/projects', role=role, expected=401)
        request('POST', '/api/login', {'token': tokens['editor']}, expected=401)
        assert server.store.get(unrelated['id']) == unrelated
        assert not config.secret_file.exists() and not config.assemblyai_secret_file.exists()
        assert server.store.get(project['id'])['jobs'] == []
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
        assert not thread.is_alive() and not server.runner.thread.is_alive() and not server.intelligence.thread.is_alive()
    parsed = [json.loads(value) for value in logs]
    log_text = json.dumps(parsed)
    assert len(parsed) == len(operations) and all(secret not in log_text for secret in secrets_in_memory)
    assert 'UNAUTHORIZED PRIVATE INPUT' not in log_text and 'FORGED OWNER' not in log_text
    write(output / 'request-contracts.json', operations)
    write(output / 'session-permissions.json', public)
    write(output / 'canonical-before.json', before)
    write(output / 'canonical-after.json', server.store.shot_view(project['id']))
    write(output / 'explicit-fixture-script-review.json', {**review, 'explicit_mock_human_decision': True, 'owner_uat_accepted': False})
    write(output / 'request-logs.json', parsed)
    write(output / 'privacy-and-gates.json', {'credentials_sessions_csrf_not_exported': True, 'no_provider_calls': True,
        'unrelated_project_unchanged': True, 'canonical_editor_revision_incremented': True, 'script_review_actor_bound': True,
        'script_only_review_cannot_approve_media_or_production': True, 'cross_session_csrf_rejected': True,
        'registry_change_revokes_all_sessions': True, 'disabled_identity_cannot_login': True,
        'no_global_owner_bootstrap': True, 'all_owned_threads_closed': True})
    serialized = ''.join(path.read_text(encoding='utf-8') for path in output.glob('*.json'))
    assert all(secret not in serialized for secret in secrets_in_memory)
    write(output / 'receipt.json', {'schema': 'north-star-native-access-contract-v1', 'status': 'PASS',
        'local_real_http_sqlite': True, 'explicit_fixture_credentials_only': True, 'http_requests': len(operations),
        'all_four_roles': True, 'external_provider_calls': 0, 'paid_operations': 0, 'actual_human_owner_approval': False,
        'browser_uat_verified': False, 'production_deployed': False,
        'exports_sha256': {path.name: file_sha(path) for path in output.glob('*.json')}})
    print(json.dumps({'status': 'PASS', 'exports': 8, 'http_requests': len(operations), 'actual_provider_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True); parser.add_argument('--ffmpeg', type=Path, required=True)
    args = parser.parse_args(); run(args.fixture_root.resolve(), args.output_root.resolve(), args.ffmpeg.resolve())
