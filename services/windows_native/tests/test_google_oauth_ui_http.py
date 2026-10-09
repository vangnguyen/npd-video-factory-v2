"""Actual signed local Studio assets; synthetic identity, no browser acceptance."""
import unittest
from pathlib import Path
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_google_oauth_http import OAuthHTTPFixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline

ROOT = Path(__file__).resolve().parents[3]


class GoogleOAuthStudioHTTPTests(OAuthHTTPFixture, unittest.TestCase):
    def test_signed_parent_module_card_headers_and_session_remain_exact(self):
        before = self.request('GET', '/api/session')[1]
        original = self.store.get(self.project['id'])
        for name in ('native.html', 'native.mjs', 'native-google-oauth.mjs'):
            status, body, headers = self.request('GET', '/' + name)
            self.assertEqual(status, 200)
            self.assertEqual(body, (ROOT / 'apps/studio-web' / name).read_bytes())
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
            self.assertNotIn('Set-Cookie', headers)
        html = (ROOT / 'apps/studio-web/native.html').read_text(encoding='utf-8')
        parent = (ROOT / 'apps/studio-web/native.mjs').read_text(encoding='utf-8')
        self.assertEqual(html.count('id="native-google-oauth-card"'), 1)
        self.assertIn('id="native-google-oauth-card" hidden', html)
        self.assertIn("session.access?.mode==='registry'&&session.capabilities?.native_official_account_review===true", parent)
        self.assertIn("import('./native-google-oauth.mjs')", parent)
        self.assertIn('googleOAuthUI?.controls()', parent)
        self.assertIn('googleOAuthUI?.sync()', parent)
        self.assertEqual(self.request('GET', '/api/session')[1], before)
        self.assertEqual(self.store.get(self.project['id']), original)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.server.runner.run_one())

    def test_viewer_module_is_public_source_but_actions_retain_server_permission(self):
        self.account('viewer')
        session = self.request('GET', '/api/session')[1]
        self.assertEqual(session['access']['permissions'], ['read'])
        self.assertEqual(self.request('GET', '/native-google-oauth.mjs')[0], 200)
        self.assertEqual(self.request('GET', '/native.html', headers={'Cookie': ''})[0], 303)
        self.assertEqual(self.request('GET', '/api/connections/google-oauth')[0], 403)
        self.assertEqual(self.request('POST', self.base + '/authorizations', {})[0], 403)
        self.assertEqual(self.request('GET', self.base + '/authorizations')[0], 200)
        for headers in ({'Host': 'untrusted.invalid'}, {'Sec-Fetch-Site': 'cross-site'}, {'Origin': 'https://untrusted.invalid'}):
            self.assertEqual(self.request('GET', '/native-google-oauth.mjs', headers=headers)[0], 403)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.request('GET', '/api/session')[1], session)

    def test_legacy_default_session_cannot_initialize_signed_oauth_controls(self):
        # An unrelated clean root is required; signed fixture roots retain auth binding.
        from dataclasses import replace
        config = replace(self.config, data_root=self.folder / 'fresh-legacy-ui-state')
        import http.client, json, threading
        with LocalServer(0, config, pipeline=NoProviderPipeline(), start_worker=False) as legacy:
            thread = threading.Thread(target=legacy.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection('127.0.0.1', legacy.server_port, timeout=5)
                connection.request('GET', '/api/session')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                session = json.loads(response.read())
                connection.close()
                self.assertNotEqual(session.get('access', {}).get('mode'), 'registry')
                self.assertNotIn('native_google_oauth', session['capabilities'])
                self.assertFalse(session['capabilities']['native_live_publishing'])
                self.assertIsNone(legacy.google_oauth)
                self.assertFalse(legacy.runner.run_one())
            finally:
                legacy.shutdown()
                thread.join()
        self.assertEqual(self.calls, [])
