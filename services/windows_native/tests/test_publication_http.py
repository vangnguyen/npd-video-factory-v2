"""Native loopback HTTP/session/RBAC/CSRF contracts over synthetic owned fixtures."""
import unittest
from unittest.mock import patch

from services.windows_native.server import Handler
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_publications import render_fixture


class NativePublicationHTTPTests(unittest.TestCase):
    setUp = access_fixture.NativeAccessHTTPTests.setUp
    tearDown = access_fixture.NativeAccessHTTPTests.tearDown
    stop_server = access_fixture.NativeAccessHTTPTests.stop_server
    start_server = access_fixture.NativeAccessHTTPTests.start_server
    request = access_fixture.NativeAccessHTTPTests.request
    account = access_fixture.NativeAccessHTTPTests.account

    def prepared(self):
        project, job = render_fixture(self.server.store)
        body = {'revision': project['revision'], 'final_job_id': job['id'], 'platform':'youtube',
            'mode':'dry_run', 'metadata':{'title':'EXPLICIT HTTP MOCK PUBLICATION','privacy':'private'},
            'request_key':'native-http-publication-fixture-key'}
        path = '/api/projects/' + project['id'] + '/publications'
        return project, job, body, path

    def test_authenticated_editor_prepares_but_owner_alone_approves_and_mock_receipt_has_no_post(self):
        project, job, body, path = self.prepared(); self.account('editor')
        before = self.server.store.get(project['id'])
        status, row, headers = self.request('POST', path, body)
        self.assertEqual(status, 200); self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertFalse(row['external_action']); self.assertEqual(row['status'], 'awaiting_publish_approval')
        approval = {'expected_fingerprint':row['request_fingerprint'],'expected_artifact_sha256':row['snapshot']['final_sha256'],'acknowledged':True}
        route = path + '/' + row['publication_id']
        with patch.object(Handler, 'read_body', side_effect=AssertionError('Unauthorized approval body must not be read')):
            self.assertEqual(self.request('POST', route + '/approve', approval)[0], 403)
        self.account('owner'); status, approved, _ = self.request('POST', route + '/approve', approval)
        self.assertEqual(status, 200); self.assertEqual(approved['approval']['actor_ref'], 'explicit-fixture')
        status, done, _ = self.request('POST', route + '/dry-run', {'expected_fingerprint':row['request_fingerprint']})
        self.assertEqual(status, 200); self.assertEqual(done['status'], 'dry_run_succeeded')
        self.assertIsNone(done['receipt']['remote_post_id']); self.assertFalse(done['receipt']['external_action'])
        self.assertEqual(self.request('GET', route)[1]['receipt'], done['receipt'])
        self.assertEqual(self.server.store.get(project['id']), before); self.assertEqual(self.pipeline.calls, 0)

    def test_viewer_reads_but_cannot_create_and_scope_csrf_live_guards_hold(self):
        project, job, body, path = self.prepared(); self.account('viewer')
        self.assertEqual(self.request('GET', path)[0], 200)
        with patch.object(Handler, 'read_body', side_effect=AssertionError('No unauthorized body read')):
            self.assertEqual(self.request('POST', path, body)[0], 403)
        self.account('owner')
        self.assertEqual(self.request('POST', path, body, {'X-VF-CSRF':'wrong'})[0], 403)
        self.assertEqual(self.request('POST', path, {**body,'mode':'live'})[0], 400)
        self.assertEqual(self.request('POST', path, {**body,'publish_enabled':True})[0], 400)
        status, row, _ = self.request('POST', path, body); self.assertEqual(status, 200)
        foreign = path.replace(project['id'], self.project['id']) + '/' + row['publication_id']
        self.assertEqual(self.request('GET', foreign)[0], 404)
        self.assertEqual(self.request('GET', path + '?limit=101')[0], 400)
        self.assertEqual(self.request('GET', path + '?limit=1&limit=2')[0], 400)
        self.assertEqual(self.request('GET', path + '?cursor=invalid')[0], 400)
        self.assertTrue(self.request('GET', '/api/session')[1]['capabilities']['native_publication_review'])
        self.assertFalse(self.request('GET', '/api/session')[1]['capabilities']['native_live_publishing'])


if __name__ == '__main__': unittest.main()
