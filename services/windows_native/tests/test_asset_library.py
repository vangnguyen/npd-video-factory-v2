"""Disposable media/history/HTTP contracts; no live data or production acceptance."""
import concurrent.futures
import copy
import http.client
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
import unittest

from PIL import Image

from services.windows_native.asset_association import mutate
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.media import ingest_media, library_assets, library_file
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.shot_adapter import validate_document
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal


def tables(store):
    con = sqlite3.connect(store.db.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        return {name: digest(con.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall())
                for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    finally:
        con.close()


class AssetLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.cfg = Config(data_root=self.root / 'data')
        self.store = Store(self.cfg.data_root)
        self.source = self.store.create('Library source fixture', 'No provider or real-world facts')
        self.target = self.store.create('New project fixture', 'Assets workspace starts empty')
        self.assets = []
        for name, color in [('Alpha garden.png', 'green'), ('Beta diagram.png', 'blue'), ('Gamma plan.png', 'red')]:
            path = self.root / name; Image.new('RGB', (320, 240), color).save(path)
            asset = ingest_media(self.cfg, path, 'image/png', name, rights_confirmed=True, illustration=True)
            self.source = self.store.append_media(self.source['id'], self.source['revision'], asset)
            self.assets.append(asset)

    def tearDown(self):
        self.temp.cleanup()

    def attach(self, ids, target=None):
        p = target or self.target
        return mutate(self.store, p['id'], p['revision'], None, 'attach', asset_ids=ids)

    def test_library_search_filter_pagination_deduplicates_history_without_db_writes(self):
        before = tables(self.store)
        self.assertEqual(library_assets(self.store)['total'], 3)
        result = library_assets(self.store, kind='image', query='GARDEN', page_size=1)
        self.assertEqual(result['total'], 1); self.assertEqual(result['items'][0]['id'], self.assets[0]['id'])
        pages = [library_assets(self.store, page=i, page_size=1)['items'][0]['id'] for i in range(1, 4)]
        self.assertEqual(len(set(pages)), 3)
        self.assertEqual(library_assets(self.store, page=4, page_size=1)['items'], [])
        self.assertEqual(library_assets(self.store, kind='video')['total'], 0)
        self.assertEqual(before, tables(self.store))

    def test_batch_attach_is_one_revision_and_preserves_source_metadata_bytes_restart(self):
        self.assertEqual(self.target['document']['assets'], [])
        files = {str(p): file_sha(p) for p in (self.store.root / 'assets').iterdir()}
        originals = {str(p): file_sha(p) for p in (self.store.root / 'originals').iterdir()}
        old_source = copy.deepcopy(self.source)
        result = self.attach([a['id'] for a in self.assets[:2]])
        self.assertEqual(result['revision'], self.target['revision'] + 1)
        self.assertEqual(result['document']['assets'], self.assets[:2])
        self.assertEqual(result['document']['scene_media'], [])
        self.assertIsNone(result['approval'])
        restored = Store(self.store.root).get(result['id'])
        self.assertEqual(restored['document'], result['document'])
        self.assertEqual(restored['document']['asset_library_associations'][self.assets[0]['id']]['source_project_ids'], [self.source['id']])
        self.assertEqual(files, {str(p): file_sha(p) for p in (self.store.root / 'assets').iterdir()})
        self.assertEqual(originals, {str(p): file_sha(p) for p in (self.store.root / 'originals').iterdir()})
        self.assertEqual(self.store.get(self.source['id']), old_source)
        self.assertEqual(library_assets(self.store)['total'], 3)

    def test_already_attached_batch_is_true_noop_with_full_project_view(self):
        result = self.attach([self.assets[0]['id']]); before = tables(self.store)
        repeated = self.attach([self.assets[0]['id']], result)
        self.assertEqual(repeated, result); self.assertIn('jobs', repeated)
        self.assertEqual(before, tables(self.store))

    def test_removed_project_association_retains_original_and_library_after_restart(self):
        identifier = self.assets[0]['id']
        target = self.attach([identifier])
        target = mutate(self.store, target['id'], target['revision'], identifier, 'remove')
        self.source = mutate(self.store, self.source['id'], self.source['revision'], identifier, 'remove')
        self.assertFalse(target['document']['assets'])
        restarted = Store(self.store.root)
        record = next(a for a in library_assets(restarted)['items'] if a['id'] == identifier)
        self.assertTrue(record['available']); self.assertFalse(record['used'])
        self.assertEqual(file_sha(self.store.root / 'assets' / identifier), self.assets[0]['sha256'])
        self.assertEqual(file_sha(self.store.root / 'originals' / self.assets[0]['original_id']), self.assets[0]['source_sha256'])
        self.assertEqual(mutate(restarted, target['id'], target['revision'], None, 'attach', asset_ids=[identifier])['document']['assets'][0], self.assets[0])

    def test_used_media_cannot_be_removed_canonical_attach_preserves_stable_shots(self):
        target = self.attach([self.assets[0]['id']])
        target = self.store.save(target['id'], target['revision'], proposal=proposal())
        target = self.store.auto_plan(target['id'], target['revision'])
        shot = self.store.shot_view(target['id'])['shot_timeline']['shots'][0]
        target = self.store.mutate_shots(target['id'], target['revision'], {'type': 'update', 'shot_id': shot['shot_id'], 'values': {'on_screen_text': 'Canonical fixture'}})
        target = self.store.approve(target['id'], target['revision'], 'CONTRACT FIXTURE, NOT OWNER ACCEPTANCE', True)
        old_state = copy.deepcopy(target['document']['canonical_timeline']); old_shots = self.store.shot_view(target['id'])['shot_timeline']['shots']
        before = tables(self.store)
        with self.assertRaisesRegex(WorkflowError, 'ASSET_USED_REPLACE_BEFORE_REMOVING'):
            mutate(self.store, target['id'], target['revision'], self.assets[0]['id'], 'remove')
        self.assertEqual(before, tables(self.store))
        updated = self.attach([self.assets[1]['id']], target)
        validate_document(updated['document'])
        self.assertIsNone(updated['approval'])
        self.assertEqual(updated['document']['canonical_timeline']['version'], old_state['version'] + 1)
        self.assertEqual(self.store.shot_view(updated['id'])['shot_timeline']['shots'], old_shots)
        self.assertEqual(updated['document']['scene_media'], target['document']['scene_media'])
        self.assertEqual(updated['document']['proposal'], target['document']['proposal'])
        # Replacement consumes the newly attached asset through the existing shot API.
        replaced = self.store.mutate_shots(updated['id'], updated['revision'], {'type': 'update', 'shot_id': shot['shot_id'], 'values': {'asset_id': self.assets[1]['id']}})
        self.assertEqual(self.store.shot_view(replaced['id'])['shot_timeline']['shots'][0]['asset_id'], self.assets[1]['id'])

    def test_tampered_second_selection_rolls_back_entire_attach(self):
        (self.store.root / 'assets' / self.assets[1]['id']).write_bytes(b'tampered fixture')
        before = tables(self.store)
        with self.assertRaisesRegex(WorkflowError, 'LIBRARY_SOURCE_CHANGED_OR_MISSING'):
            self.attach([a['id'] for a in self.assets[:2]])
        self.assertEqual(before, tables(self.store))
        self.assertEqual(self.store.get(self.target['id'])['document']['assets'], [])

    def test_original_hash_is_required_and_unavailable_records_are_explicit(self):
        (self.store.root / 'originals' / self.assets[0]['original_id']).write_bytes(b'changed original fixture')
        record = next(a for a in library_assets(self.store)['items'] if a['id'] == self.assets[0]['id'])
        self.assertFalse(record['available']); self.assertEqual(record['availability_issue'], 'LIBRARY_ORIGINAL_CHANGED_OR_MISSING')
        with self.assertRaisesRegex(WorkflowError, 'LIBRARY_ORIGINAL_CHANGED_OR_MISSING'):
            self.attach([self.assets[0]['id']])

    def test_metadata_conflict_is_not_silently_resolved(self):
        conflicting = {**self.assets[0], 'sha256': '0' * 64}
        self.store.append_media(self.target['id'], self.target['revision'], conflicting)
        record = next(a for a in library_assets(self.store)['items'] if a['id'] == self.assets[0]['id'])
        self.assertFalse(record['available']); self.assertEqual(record['availability_issue'], 'LIBRARY_SOURCE_METADATA_CONFLICT')

    def test_invalid_stale_busy_archived_and_concurrent_selections_are_guarded(self):
        for ids in ([], [self.assets[0]['id']] * 2, [None]):
            with self.assertRaisesRegex(WorkflowError, 'LIBRARY_ASSET_IDS_INVALID'):
                self.attach(ids)
        with self.assertRaisesRegex(WorkflowError, 'LIBRARY_ASSET_NOT_FOUND'):
            self.attach(['unknown.jpg'])
        updated = self.attach([self.assets[0]['id']])
        with self.assertRaisesRegex(WorkflowError, 'STALE_VERSION_RELOAD'):
            self.attach([self.assets[1]['id']])
        job = self.store.enqueue(updated['id'], updated['revision'], 'content', 'library-busy-fixture')
        with self.assertRaisesRegex(WorkflowError, 'PROJECT_BUSY'):
            self.attach([self.assets[1]['id']], updated)
        self.store.claim(); self.store.finish(job, error={'code': 'INTENTIONAL_CONTRACT_FIXTURE'})
        archived = self.store.archive(updated['id'], updated['revision'], True)
        with self.assertRaisesRegex(WorkflowError, 'PROJECT_ARCHIVED'):
            self.attach([self.assets[1]['id']], archived)
        target = self.store.create('Concurrent fixture', 'No live providers')
        def attempt(asset):
            try:
                return self.attach([asset['id']], target)['revision']
            except WorkflowError as error:
                return error.code
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            result = list(pool.map(attempt, self.assets[:2]))
        self.assertCountEqual(result, [2, 'STALE_VERSION_RELOAD'])

    def test_library_safe_files_thumbnail_and_legacy_image_fallback(self):
        path, video = library_file(self.store, self.assets[0]['id'], thumbnail=True)
        self.assertEqual(path.name, self.assets[0]['thumbnail_id']); self.assertFalse(video)
        legacy = self.store.create('Legacy fixture', 'No providers')
        raw = copy.deepcopy(self.assets[1]); raw.pop('thumbnail_id'); raw.pop('original_id'); raw.pop('source_sha256'); raw.pop('source_bytes')
        self.store.append_media(legacy['id'], legacy['revision'], raw)
        # The first trusted metadata still retains the original thumbnail for this shared ID.
        self.assertTrue(library_file(self.store, raw['id'], thumbnail=True)[0].is_file())
        with self.assertRaisesRegex(WorkflowError, 'LIBRARY_ASSET_NOT_FOUND'):
            library_file(self.store, '../secret')

    def test_unconfirmed_rights_and_project_limit_refuse_atomic_attach(self):
        restricted = {**self.assets[0], 'id': 'restricted-fixture.jpg', 'rights_confirmed': False}
        (self.store.root / 'assets' / restricted['id']).write_bytes((self.store.root / 'assets' / self.assets[0]['id']).read_bytes())
        self.source = self.store.append_media(self.source['id'], self.source['revision'], restricted)
        before = tables(self.store)
        with self.assertRaisesRegex(WorkflowError, 'MEDIA_RIGHTS_CONFIRMATION_REQUIRED'):
            self.attach([restricted['id']])
        self.assertEqual(before, tables(self.store))
        target = self.target
        for i in range(49):
            copied = {**self.assets[0], 'id': f'limit-fixture-{i}.jpg'}
            (self.store.root / 'assets' / copied['id']).write_bytes((self.store.root / 'assets' / self.assets[0]['id']).read_bytes())
            target = self.store.append_media(target['id'], target['revision'], copied)
        before = tables(self.store)
        with self.assertRaisesRegex(WorkflowError, 'PROJECT_MEDIA_LIMIT_50'):
            self.attach([a['id'] for a in self.assets[:2]], target)
        self.assertEqual(before, tables(self.store))


class NoProviderPipeline:
    def run(self, job, stage):
        raise AssertionError('Provider/render execution forbidden in library HTTP fixtures')


class AssetLibraryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); base = Path(self.temp.name)
        self.cfg = Config(data_root=base / 'data', runtime_root=base / 'runtime',
            secret_file=base / 'secrets' / 'absent-openai.env', assemblyai_secret_file=base / 'secrets' / 'absent-assemblyai.dpapi')
        self.start()

    def start(self):
        self.server = LocalServer(0, self.cfg, pipeline=NoProviderPipeline(), start_worker=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def tearDown(self):
        self.stop(); self.temp.cleanup()

    def request(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        conn.request(method, path, body=raw if raw is not None else json.dumps(body) if body is not None else None,
            headers={'Content-Type': 'application/json', 'Cookie': 'vf_native_session=' + self.server.session,
                     'X-VF-CSRF': self.server.csrf, **(headers or {})})
        response = conn.getresponse(); data = response.read(); metadata = dict(response.getheaders()); conn.close()
        value = json.loads(data) if metadata.get('Content-Type', '').startswith('application/json') else data
        return response.status, value, metadata

    def create(self, **extra):
        status, project, _ = self.request('POST', '/api/projects', {'name': 'HTTP library fixture', 'prompt': 'No live providers', **extra})
        self.assertEqual(status, 201); return project

    def test_actual_http_upload_library_attach_restart_remove_preserves_bytes(self):
        source, target = self.create(), self.create()
        self.assertEqual(target['document']['assets'], [])
        image = io.BytesIO(); Image.new('RGB', (320, 480), 'navy').save(image, format='PNG')
        status, source, _ = self.request('POST', '/api/projects/' + source['id'] + '/media', raw=image.getvalue(),
            headers={'Content-Type': 'image/png', 'X-VF-Revision': str(source['revision']),
                     'X-VF-Rights': 'confirmed', 'X-VF-Illustration': 'true', 'X-VF-Filename': 'Uploaded-library-fixture.png'})
        self.assertEqual(status, 201)
        asset = source['document']['assets'][0]; original = self.cfg.data_root / 'originals' / asset['original_id']
        original_hash = file_sha(original)
        status, library, _ = self.request('GET', '/api/assets?kind=image&q=Uploaded&page=1&page_size=24')
        self.assertEqual(status, 200); self.assertEqual(library['total'], 1)
        item = library['items'][0]; self.assertEqual(item['id'], asset['id'])
        self.assertEqual(self.request('GET', item['thumbnail_url'])[0], 200)
        status, content, _ = self.request('GET', item['file_url'])
        self.assertEqual(status, 200); self.assertEqual(content, (self.cfg.data_root / 'assets' / asset['id']).read_bytes())
        status, target, _ = self.request('POST', '/api/projects/' + target['id'] + '/asset-association',
            {'revision': target['revision'], 'action': 'attach', 'asset_ids': [asset['id']]})
        self.assertEqual(status, 200); self.assertEqual(target['document']['assets'][0], asset)
        before = tables(self.server.store); self.stop(); self.start(); self.assertEqual(before, tables(self.server.store))
        restored = self.request('GET', '/api/projects/' + target['id'])[1]
        self.assertEqual(restored['document'], target['document'])
        status, target, _ = self.request('POST', '/api/projects/' + target['id'] + '/asset-association',
            {'revision': target['revision'], 'action': 'remove', 'asset_id': asset['id']})
        self.assertEqual(status, 200); self.assertEqual(target['document']['assets'], [])
        self.assertEqual(self.request('GET', '/api/assets')[1]['total'], 1)
        self.assertEqual(file_sha(original), original_hash)

    def test_session_capabilities_auth_csrf_origin_and_query_validation(self):
        status, session, headers = self.request('GET', '/api/session', headers={'Cookie': ''})
        self.assertEqual(status, 200)
        self.assertIs(session['capabilities']['native_studio_ux'], True)
        self.assertIs(session['capabilities']['asset_library'], True)
        self.assertIn('HttpOnly', headers['Set-Cookie']); self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        for route in ['/api/assets', '/api/assets/unknown.jpg/file']:
            self.assertEqual(self.request('GET', route, headers={'Cookie': ''})[0], 401)
        for query in ['kind=audio', 'page=zero', 'page=0', 'page_size=101', 'page=1&page=2', 'path=../secret']:
            self.assertEqual(self.request('GET', '/api/assets?' + query)[0], 400)
        project = self.create(); body = {'revision': project['revision'], 'action': 'attach', 'asset_ids': ['unknown.jpg']}
        route = '/api/projects/' + project['id'] + '/asset-association'
        self.assertEqual(self.request('POST', route, body, headers={'X-VF-CSRF': 'wrong'})[0], 403)
        self.assertEqual(self.request('POST', route, body, headers={'Origin': 'https://untrusted.invalid'})[0], 403)
        self.assertEqual(self.request('GET', '/api/assets/../secret/file')[0], 404)

    def test_optional_profile_is_config_validated_persisted_legacy_create_exact(self):
        legacy = self.create()
        self.assertEqual(set(legacy['document']), {'name', 'prompt', 'input_kind', 'proposal', 'asset', 'assets', 'scene_media', 'documents'})
        selected = self.server.intelligence.catalog['profiles'][0]
        profiled = self.create(content_profile_id=selected['id'])
        context = profiled['document']['content_profile']
        self.assertEqual(context['id'], selected['id']); self.assertEqual(context['name'], selected['name'])
        self.assertEqual(context['configuration_sha256'], digest(selected))
        self.assertNotIn('brand_template', profiled['document'])
        self.stop(); self.start()
        self.assertEqual(self.request('GET', '/api/projects/' + profiled['id'])[1]['document']['content_profile'], context)
        before = tables(self.server.store)
        for invalid in [None, True, 'not-configured']:
            self.assertEqual(self.request('POST', '/api/projects', {'name': 'Invalid fixture', 'prompt': 'No providers', 'content_profile_id': invalid})[0], 400)
        self.assertEqual(before, tables(self.server.store))

    def test_actual_video_library_range_thumbnail_and_atomic_reuse(self):
        source, target = self.create(), self.create()
        path = self.cfg.data_root / 'library-video-fixture.mp4'
        subprocess.run([str(self.cfg.ffmpeg_bin / 'ffmpeg.exe'), '-v', 'error', '-nostdin', '-n',
            '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30:duration=0.7', '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p', str(path)], check=True, timeout=30)
        original = path.read_bytes()
        status, source, _ = self.request('POST', '/api/projects/' + source['id'] + '/media', raw=original,
            headers={'Content-Type': 'video/mp4', 'X-VF-Revision': str(source['revision']),
                'X-VF-Rights': 'confirmed', 'X-VF-Illustration': 'true', 'X-VF-Filename': 'Library-video-fixture.mp4'})
        self.assertEqual(status, 201)
        status, library, _ = self.request('GET', '/api/assets?kind=video&q=Library-video')
        self.assertEqual(status, 200); self.assertEqual(library['total'], 1)
        item = library['items'][0]
        self.assertEqual((item['width'], item['height']), (320, 240))
        self.assertGreater(item['duration_seconds'], .6)
        status, data, headers = self.request('GET', item['file_url'], headers={'Range': 'bytes=0-15'})
        self.assertEqual(status, 206); self.assertEqual(data, original[:16]); self.assertIn('Content-Range', headers)
        self.assertEqual(self.request('GET', item['thumbnail_url'])[0], 200)
        status, target, _ = self.request('POST', '/api/projects/' + target['id'] + '/asset-association',
            {'revision': target['revision'], 'action': 'attach', 'asset_ids': [item['id']]})
        self.assertEqual(status, 200); self.assertEqual(target['document']['assets'][0]['sha256'], file_sha(path))
        self.assertEqual(self.request('GET', item['file_url'])[1], original)

    def test_explicit_duration_mode_is_persisted_without_changing_legacy_default(self):
        from services.windows_native.branding import choose, catalog, FIT_NARRATION_POLICY
        values = catalog(); brand, template = values['brands'][0]['id'], values['templates'][0]['id']
        project = self.create(); route = '/api/projects/' + project['id'] + '/brand-template'
        status, project, _ = self.request('POST', route, {'revision': project['revision'], 'brand_id': brand, 'template_id': template})
        self.assertEqual(status, 200); self.assertEqual(project['document']['brand_template'], choose(brand, template))
        fixed = project['document']['brand_template']; before = tables(self.server.store)
        self.assertEqual(self.request('POST', route, {'revision': project['revision'], 'brand_id': brand, 'template_id': template,
            'duration_mode': 'invalid-mode'})[0], 400)
        self.assertEqual(before, tables(self.server.store))
        status, project, _ = self.request('POST', route, {'revision': project['revision'], 'brand_id': brand, 'template_id': template,
            'duration_mode': FIT_NARRATION_POLICY})
        self.assertEqual(status, 200); self.assertIsNone(project['approval'])
        selected = project['document']['brand_template']
        self.assertEqual(selected, choose(brand, template, duration_mode=FIT_NARRATION_POLICY))
        self.assertEqual(selected['template']['duration_seconds'], fixed['template']['duration_seconds'])
        self.assertNotEqual(selected['template_sha256'], fixed['template_sha256']); self.assertEqual(selected['brand'], fixed['brand'])
        self.stop(); self.start()
        self.assertEqual(self.request('GET', '/api/projects/' + project['id'])[1]['document']['brand_template'], selected)
        self.assertEqual(self.server.store.get(project['id'])['jobs'], [])


if __name__ == '__main__':
    unittest.main()
