"""Actual in-memory sessions/file invalidation and pure permission contracts."""
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest

from services.windows_native.access import NativeAccess, permission_for
from services.windows_native.contracts import WorkflowError
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier


class NativeAccessTests(unittest.TestCase):
    def create(self, role='viewer', **options):
        raw, data = fixture(role)
        verifier = HumanAuthVerifier(HumanAuthRegistry.model_validate(data), max_token_ttl_seconds=86400)
        access = NativeAccess(verifier, 'wsp_native_fixture', **options)
        return raw, data, access

    def rejected(self, code, operation):
        with self.assertRaises(WorkflowError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def test_session_cookie_is_new_hashed_private_and_bound_to_one_controller(self):
        raw, _data, access = self.create('editor')
        first, session = access.login(raw)
        second, _other = access.login(raw)
        self.assertNotEqual(first, second); self.assertNotEqual(first, raw)
        self.assertNotIn(first, access.sessions); self.assertNotIn(raw, repr(access.sessions))
        self.assertIs(access.authenticate(first), session)
        self.assertNotIn(raw, json.dumps(access.public(session)))
        foreign = self.create('owner')[2]
        self.rejected('NATIVE_AUTH_SESSION_REQUIRED', lambda: foreign.authenticate(first))
        self.rejected('NATIVE_AUTH_SESSION_REQUIRED', lambda: access.authorize(replace(session, role='owner'), 'POST', '/api/connections/assemblyai'))

    def test_four_roles_enforce_read_edit_review_manage_and_unknown_write_closed(self):
        identifier = 'a' * 32
        routes = [('GET', '/api/projects', 'read'), ('POST', '/api/projects/' + identifier + '/shots', 'edit'),
            ('POST', '/api/projects/' + identifier + '/approve', 'review'),
            ('POST', '/api/connections/assemblyai', 'manage')]
        allowed = {'owner': {'read', 'edit', 'review', 'manage'}, 'editor': {'read', 'edit'},
            'reviewer': {'read', 'review'}, 'viewer': {'read'}}
        for role, grants in allowed.items():
            raw, _data, access = self.create(role)
            cookie, session = access.login(raw)
            for method, path, permission in routes:
                with self.subTest(role=role, action=permission):
                    if permission in grants:
                        self.assertEqual(access.authorize(session, method, path), permission)
                    else:
                        self.rejected('NATIVE_AUTH_FORBIDDEN', lambda: access.authorize(session, method, path))
            self.assertEqual(access.authorize(session, 'POST', '/api/logout'), 'read')
            self.rejected('NATIVE_AUTH_FORBIDDEN', lambda: access.authorize(session, 'POST', '/api/unknown-write'))

    def test_explicit_review_and_owner_only_configuration_routes(self):
        identifier = 'b' * 32
        for path in ['/api/projects/' + identifier + '/' + suffix for suffix in ('approve', 'reject', 'script-review')]:
            self.assertEqual(permission_for('POST', path), 'review')
        for path in ['/api/jobs/' + identifier + '/review', '/api/intelligence/briefs/' + identifier + '/approve',
            '/api/intelligence/opportunities/' + identifier + '/reject', '/api/production/briefs/' + identifier + '/approve']:
            self.assertEqual(permission_for('POST', path), 'review')
        for method, path in [('GET', '/api/runtime-status'), ('GET', '/api/connections/assemblyai'),
            ('POST', '/api/projects/' + identifier + '/cost-policy'), ('POST', '/api/jobs/' + identifier + '/open-folder')]:
            self.assertEqual(permission_for(method, path), 'manage')
        self.assertIsNone(permission_for('DELETE', '/api/projects/' + identifier))

    def test_csrf_is_per_session_writes_require_exact_binding_and_logout_revokes(self):
        raw, _data, access = self.create('owner')
        cookie, session = access.login(raw)
        _second_cookie, second = access.login(raw)
        self.rejected('CSRF_TOKEN_REQUIRED', lambda: access.authenticate(cookie, write=True))
        self.rejected('CSRF_TOKEN_REQUIRED', lambda: access.authenticate(cookie, write=True, csrf=second.csrf))
        self.rejected('CSRF_TOKEN_REQUIRED', lambda: access.authenticate(cookie, write=True, csrf='é' * 43))
        self.assertIs(access.authenticate(cookie, write=True, csrf=session.csrf), session)
        access.logout(cookie); access.logout(cookie)
        self.rejected('NATIVE_AUTH_SESSION_REQUIRED', lambda: access.authenticate(cookie))

    def test_expiry_capacity_and_bounded_rate_limits(self):
        now = [0.0]
        raw, _data, access = self.create('viewer', clock=lambda: now[0], session_ttl=60,
            max_sessions=1, login_per_minute=2, requests_per_minute=2)
        cookie, session = access.login(raw)
        self.rejected('NATIVE_AUTH_SESSION_CAPACITY', lambda: access.login(raw))
        self.rejected('NATIVE_AUTH_LOGIN_RATE_LIMITED', lambda: access.login(raw))
        access.authenticate(cookie); access.authenticate(cookie)
        self.rejected('NATIVE_AUTH_REQUEST_RATE_LIMITED', lambda: access.authenticate(cookie))
        now[0] = 61
        self.rejected('NATIVE_AUTH_SESSION_REQUIRED', lambda: access.authenticate(cookie))
        self.rejected('NATIVE_AUTH_SESSION_REQUIRED', lambda: access.authorize(session, 'GET', '/api/projects'))
        replacement, _new = access.login(raw)
        self.assertNotEqual(cookie, replacement)

    def test_invalid_cross_workspace_and_service_credentials_cannot_create_session(self):
        raw, _data, access = self.create('viewer')
        self.rejected('NATIVE_AUTH_CREDENTIAL_REQUIRED', lambda: access.login('vf-service.fixture.' + 'x' * 48))
        self.rejected('NATIVE_AUTH_CREDENTIAL_REQUIRED', lambda: access.login(raw + 'tampered'))
        foreign = NativeAccess(access.verifier, 'wsp_other_fixture')
        self.rejected('NATIVE_AUTH_WORKSPACE_NOT_FOUND', lambda: foreign.login(raw))
        self.assertEqual(foreign.sessions, {})

    def test_real_profile_changes_revoke_sessions_and_malformed_profile_fails_closed(self):
        raw, data, _access = self.create('owner')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / 'secrets' / 'fixture-registry.json'; profile.parent.mkdir()
            profile.write_text(json.dumps(data), encoding='utf-8')
            access = NativeAccess.from_file(profile, 'wsp_native_fixture', root / 'data')
            cookie, session = access.login(raw)
            data['tokens']['explicit-fixture']['workspace_roles']['wsp_native_fixture'] = 'viewer'
            profile.write_text(json.dumps(data), encoding='utf-8')
            self.rejected('NATIVE_AUTH_SESSION_REQUIRED', lambda: access.authenticate(cookie))
            cookie, session = access.login(raw)
            self.assertEqual(session.role, 'viewer')
            profile.write_text('not a valid registry', encoding='utf-8')
            self.rejected('NATIVE_AUTH_PROFILE_UNAVAILABLE', lambda: access.authenticate(cookie))
            self.assertEqual(access.sessions, {})

    def test_profiles_embedded_in_state_oversize_or_invalid_config_are_refused(self):
        raw, data, access = self.create('owner')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / 'fixture-registry.json'; profile.write_text(json.dumps(data), encoding='utf-8')
            self.rejected('NATIVE_AUTH_PROFILE_MUST_BE_OUTSIDE_STATE', lambda: NativeAccess.from_file(profile, 'wsp_native_fixture', root))
            profile.write_bytes(b' ' * (256 * 1024 + 1))
            self.rejected('NATIVE_AUTH_PROFILE_UNAVAILABLE', lambda: NativeAccess.from_file(profile, 'wsp_native_fixture', root / 'data'))
        for value in ('foreign-workspace', None):
            self.rejected('NATIVE_AUTH_CONFIGURATION_INVALID', lambda: NativeAccess(access.verifier, value))
        self.rejected('NATIVE_AUTH_CONFIGURATION_INVALID', lambda: self.create(session_ttl=True))

    def test_state_binding_rejects_linked_database_and_readiness_fails_closed_on_profile_loss(self):
        raw, data, access = self.create('owner')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); state = root / 'state'; state.mkdir()
            original = root / 'original.sqlite3'; original.write_bytes(b'not opened by binding')
            os.link(original, state / 'workflow.sqlite3')
            self.rejected('BACKUP_LINKED_PATH_REJECTED', lambda: access.bind_root(state))
            self.assertIsNone(access.data_root)
            profile = root / 'fixture-registry.json'; profile.write_text(json.dumps(data), encoding='utf-8')
            configured = NativeAccess.from_file(profile, 'wsp_native_fixture', root / 'other-state')
            cookie, _session = configured.login(raw)
            self.assertTrue(configured.ready())
            profile.unlink()
            self.assertFalse(configured.ready()); self.assertEqual(configured.sessions, {})
            self.rejected('NATIVE_AUTH_PROFILE_UNAVAILABLE', lambda: configured.authenticate(cookie))

    def test_workspace_binding_is_durable_and_cannot_be_relabelled_or_removed(self):
        raw, _data, access = self.create('owner')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'new-state'; access.bind_root(root)
            marker = root / '.vf-auth-workspace.json'; original = marker.read_bytes()
            _raw, _data, same = self.create('owner'); same.bind_root(root)
            self.assertEqual(marker.read_bytes(), original)
            foreign = NativeAccess(access.verifier, 'wsp_other_fixture')
            self.rejected('NATIVE_AUTH_STATE_BINDING_UNAVAILABLE', lambda: foreign.bind_root(root))
            self.assertEqual(marker.read_bytes(), original); self.assertFalse(foreign.root_bound)
            cookie, _session = access.login(raw); marker.unlink()
            self.assertFalse(access.ready()); self.assertEqual(access.sessions, {})
            self.rejected('NATIVE_AUTH_STATE_BINDING_UNAVAILABLE', lambda: access.authenticate(cookie))
