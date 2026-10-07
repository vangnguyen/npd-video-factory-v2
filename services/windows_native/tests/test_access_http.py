"""Actual isolated per-user HTTP guards; fixture credentials, no live providers."""
import http.client
from http.cookies import SimpleCookie
import json
import threading
import unittest
from unittest.mock import patch

from services.windows_native.access import NativeAccess
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from services.windows_native.server import Handler, LocalServer
from services.windows_native.tests import test_phase10_http as phase_http
from services.windows_native.tests.test_human_identity import fixture


class NativeAccessHTTPTests(unittest.TestCase):
    setUp = phase_http.Phase10HTTPTests.setUp
    tearDown = phase_http.Phase10HTTPTests.tearDown
    stop_server = phase_http.Phase10HTTPTests.stop_server

    def start_server(self):
        self.raw, data = fixture('owner')
        access = NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data), max_token_ttl_seconds=86400), 'wsp_native_fixture')
        self.server = LocalServer(0, self.config, pipeline=self.pipeline, start_worker=False, access=access)
        self.cookie, session = access.login(self.raw); self.csrf = session.csrf
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def account(self, role):
        self.raw, data = fixture(role)
        access = NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data), max_token_ttl_seconds=86400), 'wsp_native_fixture')
        access.bind_root(self.config.data_root)
        self.server.access = access
        self.cookie, session = access.login(self.raw); self.csrf = session.csrf

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path, body=json.dumps(body) if body is not None else None,
            headers={'Content-Type': 'application/json', 'Cookie': 'vf_native_session=' + self.cookie,
                'X-VF-CSRF': self.csrf, **(headers or {})})
        response = connection.getresponse(); metadata = dict(response.getheaders()); raw = response.read(); connection.close()
        value = json.loads(raw) if metadata.get('Content-Type', '').startswith('application/json') else raw
        return response.status, value, metadata

    def test_session_does_not_bootstrap_owner_and_returns_only_own_csrf_access(self):
        self.assertEqual(self.request('GET', '/api/session', headers={'Cookie': ''})[0], 401)
        self.account('viewer')
        status, value, headers = self.request('GET', '/api/session')
        self.assertEqual(status, 200); self.assertEqual(value['access']['role'], 'viewer')
        self.assertEqual(value['access']['permissions'], ['read']); self.assertEqual(value['csrf'], self.csrf)
        self.assertNotIn('Set-Cookie', headers); self.assertNotIn(self.raw, json.dumps(value))
        self.assertNotEqual(value['csrf'], self.server.csrf)

    def test_viewer_can_read_but_cannot_write_before_body_processing_or_spoof_role(self):
        self.account('viewer')
        before = self.server.store.get(self.project['id'])
        self.assertEqual(self.request('GET', '/api/projects/' + self.project['id'])[0], 200)
        with patch.object(Handler, 'read_body', side_effect=AssertionError('Unauthorized body must not be consumed')):
            status, value, _ = self.request('POST', '/api/projects', {'name': 'PRIVATE', 'prompt': 'PRIVATE'}, {'X-VF-Role': 'owner'})
        self.assertEqual(status, 403); self.assertEqual(value['code'], 'NATIVE_AUTH_FORBIDDEN')
        self.assertEqual(self.server.store.get(self.project['id']), before)

    def test_editor_changes_canonical_shot_but_cannot_approve_or_change_credentials_budget(self):
        self.account('editor')
        current = self.server.store.shot_view(self.project['id'])
        shot = current['shot_timeline']['shots'][0]
        status, edited, _ = self.request('POST', '/api/projects/' + self.project['id'] + '/shots', {
            'revision': current['revision'], 'operation': {'type': 'update', 'shot_id': shot['shot_id'], 'values': {'on_screen_text': 'Explicit editor fixture'}}})
        self.assertEqual(status, 200); self.assertIsNone(edited['approval'])
        self.assertEqual(edited['revision'], current['revision'] + 1)
        for path in ['/api/projects/' + self.project['id'] + '/approve', '/api/projects/' + self.project['id'] + '/cost-policy', '/api/connections/assemblyai']:
            self.assertEqual(self.request('POST', path, {'revision': edited['revision'], 'key': 'PRIVATE FIXTURE'})[0], 403)
        self.assertEqual(self.request('GET', '/api/connections/assemblyai')[0], 403)

    def test_reviewer_actor_is_bound_to_identity_and_cannot_edit_or_change_credentials(self):
        self.account('reviewer')
        with patch.object(self.server.store, 'approve', return_value={'explicit_mock_approval': True}) as approve:
            status, _, _ = self.request('POST', '/api/projects/' + self.project['id'] + '/approve', {
                'revision': self.project['revision'], 'reviewer': 'FORGED OWNER', 'acknowledged': True})
        self.assertEqual(status, 200); self.assertEqual(approve.call_args.args[2], 'explicit-fixture')
        for path in ['/api/projects/' + self.project['id'] + '/shots', '/api/connections/assemblyai']:
            self.assertEqual(self.request('POST', path, {})[0], 403)
        self.assertEqual(self.request('GET', '/api/runtime-status')[0], 403)

    def test_owner_configuration_still_requires_own_csrf_and_existing_body_guards(self):
        self.assertEqual(self.request('POST', '/api/projects/' + self.project['id'] + '/cost-policy', {
            'revision': self.project['revision'], 'max_ai_cost_vnd': '100'}, {'X-VF-CSRF': self.server.csrf})[0], 403)
        status, value, _ = self.request('POST', '/api/projects/' + self.project['id'] + '/cost-policy', {
            'revision': self.project['revision'], 'max_ai_cost_vnd': '100'})
        self.assertEqual(status, 200); self.assertEqual(value['document']['cost_policy']['max_ai_cost_vnd'], '100')
        self.assertIsNone(value['approval'])
        self.assertEqual(self.request('POST', '/api/projects/' + self.project['id'] + '/cost-policy', {
            'revision': value['revision'], 'max_ai_cost_vnd': '100', 'publish_enabled': True})[0], 400)

    def test_login_logout_cookie_flags_host_cross_site_and_service_identity_guards(self):
        self.assertEqual(self.request('POST', '/api/login', {'token': self.raw}, {'Host': 'hostile.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/login', {'token': self.raw}, {'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.request('POST', '/api/login', {'token': 'vf-service.fixture.' + 'x' * 48})[0], 401)
        status, value, headers = self.request('POST', '/api/login', {'token': self.raw}, {'Cookie': '', 'X-VF-CSRF': ''})
        self.assertEqual(status, 200); cookie = SimpleCookie(); cookie.load(headers['Set-Cookie'])
        self.assertTrue(cookie['vf_native_session']['httponly']); self.assertEqual(cookie['vf_native_session']['samesite'], 'Strict')
        self.cookie = cookie['vf_native_session'].value; self.csrf = value['csrf']
        self.assertEqual(self.request('POST', '/api/logout', {})[0], 200)
        self.assertEqual(self.request('GET', '/api/projects')[0], 401)

    def test_stale_global_cookie_unknown_routes_and_cross_root_controller_are_closed(self):
        self.assertEqual(self.request('GET', '/api/projects', headers={'Cookie': 'vf_native_session=' + self.server.session})[0], 401)
        self.assertEqual(self.request('POST', '/api/not-registered', {})[0], 403)
        from services.windows_native.contracts import WorkflowError
        with self.assertRaises(WorkflowError) as refused:
            LocalServer(0, self.config.__class__(data_root=self.config.data_root.parent / 'foreign'), pipeline=self.pipeline,
                start_worker=False, access=self.server.access)
        self.assertEqual(refused.exception.code, 'NATIVE_AUTH_STATE_SCOPE_MISMATCH')
        with self.assertRaises(WorkflowError) as refused:
            LocalServer(0, self.config, pipeline=self.pipeline, start_worker=False)
        self.assertEqual(refused.exception.code, 'NATIVE_AUTH_REGISTRY_REQUIRED_FOR_BOUND_STATE')

    def test_html_requires_session_without_exposing_registry_or_accepting_return_url(self):
        for path in ('/?new=1', '/native.html', '/production?view=library', '/intelligence', '/settings/assemblyai'):
            status, value, headers = self.request('GET', path, headers={'Cookie': ''})
            self.assertEqual(status, 303); self.assertEqual(headers['Location'], '/login')
            self.assertNotIn(self.raw, json.dumps(value))
        for path in ('/login?next=https://hostile.example', '/native-login.mjs', '/native-access.mjs', '/native-access.css'):
            self.assertEqual(self.request('GET', path, headers={'Cookie': ''})[0], 200)
        self.account('viewer')
        for path in ('/', '/native.html', '/production', '/intelligence'):
            self.assertEqual(self.request('GET', path)[0], 200)
        self.assertEqual(self.request('GET', '/settings/assemblyai')[0], 403)
        self.account('owner'); self.assertEqual(self.request('GET', '/settings/assemblyai')[0], 200)

    def test_profile_failure_invalidates_http_sessions_and_exposes_only_readiness_boolean(self):
        profile = self.config.data_root.parent / ('fixture-auth-' + self.project['id'] + '.json')
        _raw, data = fixture('owner'); profile.write_text(json.dumps(data), encoding='utf-8')
        self.addCleanup(lambda: profile.unlink(missing_ok=True))
        access = NativeAccess.from_file(profile, 'wsp_native_fixture', self.config.data_root)
        access.bind_root(self.config.data_root); self.server.access = access
        self.cookie, session = access.login(self.raw); self.csrf = session.csrf
        self.assertTrue(self.request('GET', '/readyz')[1]['checks']['auth_configuration'])
        profile.write_text('invalid registry', encoding='utf-8')
        status, value, _ = self.request('GET', '/readyz')
        self.assertEqual(status, 503); self.assertFalse(value['checks']['auth_configuration'])
        self.assertNotIn(str(profile), json.dumps(value)); self.assertNotIn(self.raw, json.dumps(value))
        self.assertEqual(self.request('GET', '/healthz')[0], 200)
        self.assertEqual(self.request('GET', '/api/projects')[0], 503)
        profile.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.request('GET', '/api/projects')[0], 401)
