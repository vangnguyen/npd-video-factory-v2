"""Actual signed loopback current-scene workflow; explicit ASR/human fixtures."""
import copy
import threading
import unittest
import uuid
from unittest.mock import patch

from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import Handler, LocalServer
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as identity
from services.windows_native.tests import test_scene_assessments as fixture


class SceneAssessmentHTTPTests(unittest.TestCase):
    workspace = 'wsp_scene_assessment_http_fixture'
    request = access_fixture.NativeAccessHTTPTests.request
    save_analysis = fixture.SceneAssessmentTests.save_analysis
    real_source = fixture.SceneAssessmentTests.real_source

    def setUp(self):
        fixture.SceneAssessmentTests.setUp(self)
        raw, data = identity('editor', workspace=self.workspace)
        self.access = NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),
            max_token_ttl_seconds=86400), self.workspace)
        self.server = LocalServer(0, self.config, start_worker=False, access=self.access)
        self.cookie, session = self.access.login(raw); self.csrf = session.csrf
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.route = '/api/projects/' + self.project['id'] + '/auto-edit/scene-assessments'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        fixture.SceneAssessmentTests.tearDown(self)

    def account(self, role):
        raw, data = identity(role, workspace=self.workspace)
        access = NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),
            max_token_ttl_seconds=86400), self.workspace)
        access.bind_root(self.root); self.server.access = access
        self.cookie, session = access.login(raw); self.csrf = session.csrf

    def test_signed_editor_save_read_cache_and_actor_preserve_originals(self):
        before = copy.deepcopy(self.store.get(self.project['id']))
        code, session, _ = self.request('GET', '/api/session')
        self.assertEqual(code, 200); self.assertTrue(session['capabilities']['native_scene_assessments'])
        code, page, headers = self.request('GET', self.route)
        self.assertEqual(code, 200, page); self.assertEqual(headers['Cache-Control'], 'no-store')
        request = fixture.body(page)
        code, saved, headers = self.request('POST', self.route, request)
        self.assertEqual(code, 200, saved); self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(len(saved['items']), 1)
        value = saved['items'][0]['assessment']; self.assertEqual(value['actor_ref'], 'explicit-fixture')
        self.assertEqual(value['workspace_id'], self.workspace)
        self.assertFalse(value['result']['owner_uat_accepted']); self.assertFalse(value['result']['semantic_vision_used'])
        current = self.store.get(self.project['id'])
        for field in ('canonical_timeline', 'auto_edit_analyses', 'media_analysis'):
            self.assertEqual(current['document'][field], before['document'][field])
        self.assertIsNone(current['approval']); self.assertEqual(current['jobs'], before['jobs'])
        self.assertEqual(self.request('GET', self.route)[1], saved)
        code, replay, _ = self.request('POST', self.route, fixture.body(saved))
        self.assertEqual(code, 200, replay); self.assertEqual(replay, saved)
        self.assertEqual(self.store.get(self.project['id']), current)

    def test_auth_csrf_role_and_query_refuse_before_reading_mutation_body(self):
        code, page, _ = self.request('GET', self.route); self.assertEqual(code, 200)
        request = fixture.body(page); before = self.store.get(self.project['id'])
        with patch.object(Handler, 'read_body', side_effect=AssertionError('Guard before body')):
            self.assertEqual(self.request('POST', self.route, request, {'Cookie': ''})[0], 401)
            self.assertEqual(self.request('POST', self.route, request, {'X-VF-CSRF': 'wrong'})[0], 403)
            self.assertEqual(self.request('POST', self.route, request, {'Origin': 'https://invalid.example'})[0], 403)
            self.assertIn(self.request('POST', self.route + '?actor_ref=owner', request)[0], (400, 404))
        for role in ('viewer', 'reviewer'):
            self.account(role)
            with patch.object(Handler, 'read_body', side_effect=AssertionError('Role before body')):
                self.assertEqual(self.request('POST', self.route, request)[0], 403)
            self.assertEqual(self.request('GET', self.route)[0], 200)
        self.assertEqual(self.request('GET', self.route + '?refresh=1')[0], 400)
        self.assertEqual(self.store.get(self.project['id']), before)

    def test_body_forgery_stale_source_and_missing_project_do_not_write(self):
        _, page, _ = self.request('GET', self.route); request = fixture.body(page)
        before = self.store.get(self.project['id'])
        for values, expected in (({'actor_ref': 'forged-owner'}, 400), ({'revision': 99}, 409),
            ({'expected_transcript_id': 'trn_' + 'f' * 24}, 409),
            ({'acknowledged_saved_evidence': False}, 400), ({'acknowledged_saved_evidence': 1}, 400)):
            self.assertEqual(self.request('POST', self.route, {**request, **values})[0], expected)
            self.assertEqual(self.store.get(self.project['id']), before)
        foreign = '/api/projects/' + 'e' * 32 + '/auto-edit/scene-assessments'
        self.assertEqual(self.request('GET', foreign)[0], 404)
        self.path.write_bytes(b'Explicit owned corrupt-media fixture')
        self.assertEqual(self.request('POST', self.route, request)[0], 409)
        self.assertEqual(self.store.get(self.project['id']), before)

    def test_busy_project_returns_conflict_without_assessment_or_timeline_write(self):
        _, page, _ = self.request('GET', self.route); request = fixture.body(page)
        self.store.enqueue(self.project['id'], self.project['revision'], 'media_frames', uuid.uuid4().hex)
        before = self.store.get(self.project['id'])
        code, error, _ = self.request('POST', self.route, request)
        self.assertEqual(code, 409, error); self.assertEqual(error['code'], 'PROJECT_BUSY')
        self.assertEqual(self.store.get(self.project['id']), before)


if __name__ == '__main__':
    unittest.main()
