"""Integrated source Studio controller over isolated HTTP; no browser acceptance."""
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'apps/api'))
from services.windows_native.tests.test_google_oauth_callback import GoogleOAuthCallbackTests
from services.windows_native.tests.test_google_oauth_protocol import TOKEN, REFRESH, SECRET, CODE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or out == ROOT or ROOT in out.parents:
        raise ValueError('Fresh external evidence path required')
    fixture = GoogleOAuthCallbackTests(); fixture.setUp()
    try:
        served = {}
        for name in ('native.html', 'native.mjs', 'native-google-oauth.mjs'):
            status, body, headers = fixture.request('GET', '/' + name)
            assert status == 200 and body == (ROOT / 'apps/studio-web' / name).read_bytes()
            assert headers['Cache-Control'] == 'no-store' and headers['Referrer-Policy'] == 'no-referrer'
            assert headers['X-Content-Type-Options'] == 'nosniff' and "script-src 'self'" in headers['Content-Security-Policy']
            served[name] = hashlib.sha256(body).hexdigest()
        parent = (ROOT / 'apps/studio-web/native.mjs').read_text(encoding='utf-8')
        html = (ROOT / 'apps/studio-web/native.html').read_text(encoding='utf-8')
        assert "session.access?.mode==='registry'&&session.capabilities?.native_official_account_review===true" in parent
        assert "import('./native-google-oauth.mjs')" in parent and 'googleOAuthUI?.controls()' in parent and 'googleOAuthUI?.sync()' in parent
        assert html.count('id="native-google-oauth-card"') == 1 and 'id="native-google-oauth-card" hidden' in html
        fixture.purpose = 'analytics'
        request = {'origin': 'http://127.0.0.1:' + str(fixture.server.server_port), 'cookie': fixture.cookie,
            'csrf': fixture.csrf, 'project_id': fixture.project['id'], 'analytics_slot': 'ngos_' + 'a' * 32,
            'stamp': fixture.clock[0].timestamp() * 1000, 'synthetic_code': CODE}
        helper = ROOT / 'scripts/north_star_google_oauth_ui.mjs'
        result = subprocess.run(['C:/Program Files/nodejs/node.exe', str(helper)], input=json.dumps(request),
            text=True, encoding='utf-8', capture_output=True, timeout=60)
        if result.returncode:
            diagnostic = result.stderr
            for secret in (TOKEN, REFRESH, SECRET, CODE, fixture.raw, fixture.cookie, fixture.csrf):
                diagnostic = diagnostic.replace(secret, '<private>')
            diagnostic = re.sub(r'https?://[^\s\"\']+', '<private-url>', diagnostic)
            diagnostic = re.sub(r'[A-Za-z0-9_-]{50,}', '<opaque>', diagnostic)
            print(diagnostic[-3000:]); raise RuntimeError('Integrated source controller/HTTP rehearsal failed')
        value = json.loads(result.stdout)
        assert len(fixture.calls) == 2 and not fixture.server.runner.run_one()
        assert all(s not in result.stdout for s in (TOKEN, REFRESH, SECRET, CODE, fixture.raw, fixture.cookie, fixture.csrf))
        sources = ('apps/studio-web/native-google-oauth.mjs', 'apps/studio-web/native.html', 'apps/studio-web/native.mjs',
            'services/windows_native/server.py', 'services/windows_native/tests/test_google_oauth_ui_http.py',
            'apps/studio-web/tests/native-google-oauth.test.mjs', 'apps/studio-web/tests/fixtures/native-google-oauth-v1.json',
            'scripts/north_star_google_oauth_ui.py', 'scripts/north_star_google_oauth_ui.mjs')
        value.update({'mock_token_requests': 2, 'external_provider_calls': 0, 'real_secret_reads': 0, 'paid_operations': 0,
            'real_publications': 0, 'real_audience_observations': 0, 'new_media_operations': 0,
            'native_studio_parent_integrated': True, 'parent_verified_by_served_source_not_browser_execution': True,
            'browser_owner_real_provider_acceptance': False, 'served_file_requests': 3, 'served_sha256': served,
            'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}})
        with out.open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')
        print(json.dumps({'status': 'PASS', 'controller_http_requests': value['http_requests'], 'served_file_requests': 3,
            'mock_token_requests': 2, 'studio_parent_integrated': True, 'browser_owner_acceptance': False}))
    finally:
        fixture.tearDown()


if __name__ == '__main__':
    main()
