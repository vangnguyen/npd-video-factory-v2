"""Actual isolated HTTP contracts; all AI/research/media results are labelled fixtures.

No live credentials, provider requests, publication, or production acceptance occurs.
"""
from copy import deepcopy
import http.client
from http.cookies import SimpleCookie
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from PIL import Image

from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.pipeline import Config
from services.windows_native.production_intelligence import item_id
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.server import LocalServer
from services.windows_native.shot_ai_edit import ShotAIEdit
from services.windows_native.tests.test_intelligence_engines import receipt
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
from services.windows_native.tests.test_workflow import proposal
from services.windows_native.voice_quality import policy_reference


class NoProviderPipeline:
    def __init__(self):
        self.calls = 0

    def run(self, job, stage):
        self.calls += 1
        raise AssertionError('Production pipeline must not run in HTTP contract fixtures')


class Phase10HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.config = Config(data_root=base / 'data', runtime_root=base / 'runtime',
            secret_file=base / 'secrets' / 'absent-openai.env', assemblyai_secret_file=base / 'secrets' / 'absent-assemblyai.dpapi',
            ffmpeg_bin=base / 'deliberately-unavailable-ffmpeg')
        self.pipeline = NoProviderPipeline()
        self.live_ai = patch.object(ShotAIEdit, '_request', side_effect=AssertionError('Live AI request forbidden in contract fixture'))
        self.live_ai.start()
        self.start_server()
        self.project = self.server.store.create('Isolated HTTP shot fixture', 'No live providers or final acceptance')
        folder = self.config.data_root / 'assets'; folder.mkdir(exist_ok=True)
        path = folder / (uuid.uuid4().hex + '.jpg')
        Image.new('RGB', (320, 240), (45, 75, 95)).save(path)
        self.asset = {'id': path.name, 'kind': 'image', 'filename': 'Generated HTTP fixture image',
                      'sha256': file_sha(path), 'rights_confirmed': True, 'illustration': True}
        self.project = self.server.store.save(self.project['id'], self.project['revision'], proposal=proposal(), asset=self.asset)
        self.project = self.server.store.approve(self.project['id'], self.project['revision'], 'HTTP CONTRACT FIXTURE — NOT OWNER ACCEPTANCE', True)

    def start_server(self):
        self.server = LocalServer(0, self.config, pipeline=self.pipeline, start_worker=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        for worker in list(self.server.previews.workers.values()):
            worker.join(timeout=5)

    def tearDown(self):
        self.stop_server()
        self.live_ai.stop()
        self.assertEqual(self.pipeline.calls, 0)
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        connection.request(method, path, body=json.dumps(body) if body is not None else None,
            headers={'Content-Type': 'application/json', 'Cookie': 'vf_native_session=' + self.server.session,
                     'X-VF-CSRF': self.server.csrf, **(headers or {})})
        response = connection.getresponse(); raw = response.read(); metadata = dict(response.getheaders()); connection.close()
        value = json.loads(raw) if metadata.get('Content-Type', '').startswith('application/json') else raw
        return response.status, value, metadata

    def api(self, method, path, body=None, headers=None):
        return self.request(method, path, body, headers)[:2]

    def shots(self):
        status, value = self.api('GET', '/api/projects/' + self.project['id'] + '/shots')
        self.assertEqual(status, 200)
        return value

    def mutation(self, visual='A deliberate HTTP fixture edit'):
        current = self.shots()
        return {'revision': current['revision'], 'operation': {'type': 'update',
            'shot_id': current['shot_timeline']['shots'][0]['shot_id'], 'values': {'visual': visual}}}

    def database_state(self):
        with self.server.store.transaction() as con:
            return {table: [tuple(row) for row in con.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                    for table in ('projects', 'project_versions', 'events', 'jobs')}

    def approved_brief(self):
        ci = self.server.intelligence
        ci.research_provider = PublicWebResearchProvider(self.config.data_root / 'research-sources', fetch=lambda url: receipt())
        ci.idea_provider = FixtureIdeas()
        status, bundle = self.api('POST', '/api/intelligence/runs', {'query': 'HTTP fixture housing source review',
            'profile_id': 'vietnam-property', 'source_urls': ['https://example.com/test']})
        self.assertEqual(status, 200)
        for action in ('research', 'ideas'):
            status, _ = self.api('POST', f"/api/intelligence/runs/{bundle['run']['id']}/{action}",
                {'version': bundle['run']['version'], 'request_key': uuid.uuid4().hex})
            self.assertEqual(status, 200)
            self.assertTrue(ci.run_one())
            status, bundle = self.api('GET', '/api/intelligence/runs/' + bundle['run']['id'])
            self.assertEqual(status, 200)
        idea = bundle['ideas'][0]
        status, bundle = self.api('POST', '/api/intelligence/ideas/' + idea['id'] + '/select',
            {'version': idea['version'], 'opportunity_version': bundle['opportunity']['version'], 'reviewer': 'HTTP CONTRACT FIXTURE'})
        self.assertEqual(status, 200)
        brief = bundle['brief']
        status, preflight = self.api('GET', '/api/production/briefs/' + brief['id'] + '/preflight')
        self.assertEqual(status, 200)
        self.assertFalse(preflight['approval_performed'])
        status, bundle = self.api('POST', '/api/production/briefs/' + brief['id'] + '/approve',
            {'version': brief['version'], 'binding_sha256': preflight['binding_sha256'],
             'reviewer': 'HTTP CONTRACT FIXTURE', 'acknowledged': True})
        self.assertEqual(status, 200)
        return bundle

    def test_shots_read_only_and_native_session_origin_csrf_boundary(self):
        endpoint = '/api/projects/' + self.project['id'] + '/shots'
        before = self.database_state()
        view = self.shots()
        self.assertFalse(view['shot_timeline']['persisted'])
        self.assertEqual(view['shot_timeline']['version'], 0)
        self.assertEqual(self.shots(), view)
        self.assertEqual(self.database_state(), before)
        self.assertEqual(self.api('GET', endpoint, headers={'Cookie': ''})[0], 401)
        self.assertEqual(self.api('GET', endpoint, headers={'Host': 'untrusted.invalid'})[0], 403)
        self.assertEqual(self.api('GET', endpoint, headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        body = self.mutation()
        self.assertEqual(self.api('POST', endpoint, body, {'X-VF-CSRF': 'incorrect'})[0], 403)
        self.assertEqual(self.api('POST', endpoint, body, {'Origin': 'https://foreign.invalid'})[0], 403)
        self.assertEqual(self.api('POST', endpoint, body, {'Cookie': ''})[0], 401)
        self.assertEqual(self.database_state(), before)

    def test_session_capabilities_preserve_cookie_csrf_boundary_without_project_writes(self):
        before = self.database_state()
        status, session, headers = self.request('GET', '/api/session', headers={'Cookie': '', 'X-VF-CSRF': ''})
        self.assertEqual(status, 200)
        self.assertEqual(session['capabilities'], {'native_shot_studio': True, 'production_intelligence': True, 'voice_quality_selection': True,
            'native_studio_ux': True, 'asset_library': True, 'north_star_quality': True, 'native_auto_edit_analysis': True,
            'native_source_timeline':True,'native_media_frame_analysis':True,'native_cost_ledger':True,
            'native_publication_review':True,'native_live_publishing':False})
        for name in ('native_shot_studio', 'production_intelligence', 'voice_quality_selection', 'native_studio_ux', 'asset_library'):
            self.assertIs(type(session['capabilities'][name]), bool)
        self.assertEqual(session['csrf'], self.server.csrf)
        self.assertNotIn(self.server.session, json.dumps(session))
        cookie = SimpleCookie(); cookie.load(headers['Set-Cookie'])
        value = cookie['vf_native_session']
        self.assertEqual(value.value, self.server.session)
        self.assertTrue(value['httponly']); self.assertEqual(value['samesite'], 'Strict')
        self.assertEqual(value['path'], '/')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.request('GET', '/api/session')[1], session)
        for rejected in ({'Host': 'untrusted.invalid'}, {'Origin': 'https://foreign.invalid'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.api('GET', '/api/session', headers=rejected)[0], 403)
        endpoint = '/api/projects/' + self.project['id'] + '/shots'
        request_cookie = 'vf_native_session=' + value.value
        self.assertEqual(self.api('GET', endpoint, headers={'Cookie': ''})[0], 401)
        self.assertEqual(self.api('GET', endpoint, headers={'Cookie': 'vf_native_session=wrong'})[0], 401)
        self.assertEqual(self.api('GET', endpoint, headers={'Cookie': request_cookie})[0], 200)
        body = {'revision': self.project['revision'], 'operation': {'type': 'publish'}}
        self.assertEqual(self.api('POST', endpoint, body, {'Cookie': request_cookie, 'X-VF-CSRF': 'wrong'})[0], 403)
        self.assertEqual(self.api('POST', endpoint, body, {'Cookie': '', 'X-VF-CSRF': session['csrf']})[0], 401)
        status, failure = self.api('POST', endpoint, body, {'Cookie': request_cookie, 'X-VF-CSRF': session['csrf']})
        self.assertEqual((status, failure['code']), (400, 'SHOT_OPERATION_INVALID'))
        self.assertEqual(self.database_state(), before)

    def test_native_auto_edit_evidence_and_transcript_http_guards(self):
        from services.windows_native.auto_edit_analysis import make_analysis
        from services.windows_native.tests.test_auto_edit_analysis import saved_asr
        from app.auto_edit_models import MediaMetadata
        from app.auto_edit_providers import MediaSignals
        asset = {'id': uuid.uuid4().hex+'.mp4', 'kind': 'video', 'filename': 'Explicit HTTP source fixture',
            'sha256': 'a'*64, 'rights_confirmed': True, 'illustration': False,
            'duration_seconds': 3., 'width': 320, 'height': 240, 'has_audio': True}
        source_path=self.config.data_root/'assets'/asset['id']
        source_path.write_bytes(b'Explicit nonplayable HTTP source fixture; no decode or render')
        asset['sha256']=file_sha(source_path)
        self.project = self.server.store.append_media(self.project['id'], self.project['revision'], asset)
        job = self.server.store.enqueue(self.project['id'], self.project['revision'], 'asr', uuid.uuid4().hex)
        job = self.server.store.claim()
        self.server.store.finish(job, result={'media_analysis': [saved_asr(asset)]})
        self.project = self.server.store.get(self.project['id'])
        status, job = self.api('POST', '/api/projects/'+self.project['id']+'/jobs', {
            'revision': self.project['revision'], 'kind': 'auto_edit_analysis', 'request_key': uuid.uuid4().hex})
        self.assertEqual(status, 200)
        job = self.server.store.claim()
        record = make_analysis(self.project['id'], self.project['document'], asset,
            MediaMetadata(media_kind='video', detected_content_type='video/mp4', duration_seconds=3., audio_codec='aac'),
            MediaSignals((), ((1.3,1.95,None),), {'fixture': True}))
        self.server.store.finish(job, result={'auto_edit_analyses': [record]})
        endpoint = '/api/projects/'+self.project['id']+'/auto-edit'
        before = self.database_state()
        status, view = self.api('GET', endpoint); self.assertEqual(status, 200)
        self.assertEqual(self.api('GET', endpoint)[1], view)
        self.assertEqual(self.database_state(), before)
        self.assertEqual(self.api('GET', endpoint, headers={'Cookie':''})[0], 401)
        transcript = view['analyses'][0]['analysis']['transcript']
        path = endpoint+'/'+transcript['analysis_id']+'/transcript'
        body = {'revision': view['revision'], 'edit': {'expected_version': 1,
            'segments': [{'segment_id': transcript['segments'][0]['segment_id'], 'text':'Vang Nguyễn.'}]}}
        for headers, expected in [({'Cookie':''},401), ({'X-VF-CSRF':'invalid'},403), ({'Origin':'https://foreign.invalid'},403)]:
            self.assertEqual(self.api('POST',path,body,headers)[0],expected)
        self.assertEqual(self.database_state(), before)
        forged = deepcopy(body); forged['edit']['actor_ref'] = 'other-owner'
        self.assertEqual(self.api('POST',path,forged)[0],400)
        status, updated = self.api('POST',path,body); self.assertEqual(status,200)
        self.assertEqual(updated['analyses'][0]['analysis']['transcript']['version'],2)
        self.assertEqual(updated['analyses'][0]['analysis']['transcript']['segments'][0]['words'],[])
        self.assertEqual(self.api('POST',path,body)[0],409)
        self.assertEqual(self.api('GET','/native-auto-edit.mjs')[0],200)
        # Canonical source editing is opt-in for a separate media project;
        # the existing narrated HTTP fixture cannot be replaced by this route.
        timeline_path=endpoint+'/timeline'
        canonical_body={'revision':updated['revision'],'action':'create','payload':{
            'analysis_id':transcript['analysis_id'],
            'transcript_id':updated['analyses'][0]['analysis']['transcript']['transcript_id']}}
        self.assertEqual(self.api('POST',timeline_path,canonical_body)[0],400)
        source_project=self.server.store.create('HTTP source timeline fixture','','media')
        source_project=self.server.store.append_media(source_project['id'],source_project['revision'],asset)
        job=self.server.store.enqueue(source_project['id'],source_project['revision'],'asr',uuid.uuid4().hex)
        job=self.server.store.claim(); self.server.store.finish(job,result={'media_analysis':[saved_asr(asset)]})
        source_project=self.server.store.get(source_project['id'])
        job=self.server.store.enqueue(source_project['id'],source_project['revision'],'auto_edit_analysis',uuid.uuid4().hex)
        job=self.server.store.claim()
        record=make_analysis(source_project['id'],source_project['document'],asset,
            MediaMetadata(media_kind='video',detected_content_type='video/mp4',duration_seconds=3.,audio_codec='aac'),
            MediaSignals((),(),{'fixture':True}))
        self.server.store.finish(job,result={'auto_edit_analyses':[record]})
        source_project=self.server.store.get(source_project['id'])
        timeline_path='/api/projects/'+source_project['id']+'/auto-edit/timeline'
        canonical_body={'revision':source_project['revision'],'action':'create','payload':{
            'analysis_id':record['analysis']['analysis_id'],'transcript_id':record['analysis']['transcript']['transcript_id']}}
        for headers,expected in [({'Cookie':''},401),({'X-VF-CSRF':'invalid'},403),({'Origin':'https://foreign.invalid'},403)]:
            self.assertEqual(self.api('POST',timeline_path,canonical_body,headers)[0],expected)
        status,canonical=self.api('POST',timeline_path,canonical_body); self.assertEqual(status,200)
        self.assertEqual(canonical['shot_timeline']['editing_mode'],'source_footage')
        self.assertEqual(self.api('GET',timeline_path)[1],canonical)
        self.assertEqual(self.api('GET',timeline_path,headers={'Cookie':''})[0],401)
        track=next(value for value in canonical['shot_timeline']['snapshot']['tracks'] if value['type']=='audio')
        mutation={'revision':canonical['revision'],'action':'edit','payload':{'expected_version':1,
            'operations':[{'type':'set_track_state','track_id':track['track_id'],'muted':True}]}}
        status,edited=self.api('POST',timeline_path,mutation); self.assertEqual(status,200)
        self.assertEqual(edited['shot_timeline']['version'],2)
        self.assertEqual(self.api('POST',timeline_path,mutation)[0],409)
        forged=deepcopy(mutation); forged['revision']=edited['revision']; forged['payload']['expected_version']=2
        forged['payload']['actor_ref']='foreign-owner'
        self.assertEqual(self.api('POST',timeline_path,forged)[0],400)

        # These are authenticated local editing/catalog/static contracts, not a
        # real browser/media/provider or Owner acceptance test.
        self.assertEqual(self.api('GET','/api/auto-edit/subtitle-templates',headers={'Cookie':''})[0],401)
        status,catalog=self.api('GET','/api/auto-edit/subtitle-templates');self.assertEqual(status,200)
        self.assertEqual(len(catalog['templates']),7)
        for path in ('/native-source-editor.mjs','/native-source-editor.css','/studio-utils.mjs','/waveform.mjs','/timeline-history.mjs'):
            self.assertEqual(self.api('GET',path)[0],200)
        source=next(clip for track in edited['shot_timeline']['snapshot']['tracks'] if track['kind']=='source' for clip in track['clips'])
        linked={'revision':edited['revision'],'action':'linked_edit','payload':{'expected_version':2,
            'operation':{'type':'trim','clip_id':source['clip_id'],'source_start':.3,'source_end':1.1}}}
        self.assertEqual(self.api('POST',timeline_path,linked,{'X-VF-CSRF':'bad'})[0],403)
        status,synchronized=self.api('POST',timeline_path,linked);self.assertEqual(status,200)
        self.assertAlmostEqual(synchronized['shot_timeline']['snapshot']['duration_seconds'],1.)
        self.assertEqual(self.api('POST',timeline_path,linked)[0],409)
        configured={'revision':synchronized['revision'],'action':'configure','payload':{'expected_version':3,
            'aspect_ratio':'4:5','subtitle_template_ref':'karaoke-gold@v1'}}
        status,choice=self.api('POST',timeline_path,configured);self.assertEqual(status,200)
        self.assertEqual(choice['shot_timeline']['snapshot']['metadata']['subtitle_style']['animation'],'karaoke')
        self.assertEqual((choice['shot_timeline']['snapshot']['width'],choice['shot_timeline']['snapshot']['height']),(1080,1350))
        self.assertEqual(choice['document']['source_timeline_mutations'][-1]['version'],4)
        broll_path='/api/projects/'+source_project['id']+'/auto-edit/broll'
        body={'revision':choice['revision'],'action':'create','payload':{'expected_version':4}}
        before=self.database_state()
        for headers,expected in [({'Cookie':''},401),({'X-VF-CSRF':'bad'},403),({'Origin':'https://foreign.invalid'},403)]:
            self.assertEqual(self.api('POST',broll_path,body,headers)[0],expected)
        self.assertEqual(self.api('POST',broll_path,{**body,'provider':'forged'})[0],400)
        self.assertEqual(self.database_state(),before)
        status,planned=self.api('POST',broll_path,body);self.assertEqual(status,200)
        self.assertEqual(planned['document']['canonical_timeline'],choice['document']['canonical_timeline'])
        self.assertEqual(self.api('POST',broll_path,body)[0],409)
        self.assertEqual(self.api('GET','/native-source-broll.mjs')[0],200)
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=15)
        connection.request('POST','/api/projects/'+source_project['id']+'/media',body=(self.config.data_root/'assets'/self.asset['id']).read_bytes(),headers={
            'Content-Type':'image/jpeg','Cookie':'vf_native_session='+self.server.session,'X-VF-CSRF':self.server.csrf,
            'X-VF-Revision':str(planned['revision']),'X-VF-Rights':'confirmed','X-VF-Illustration':'true','X-VF-Filename':'Supporting fixture.jpg'})
        response=connection.getresponse();uploaded=json.loads(response.read());connection.close()
        self.assertEqual(response.status,201,uploaded)
        self.assertEqual(uploaded['shot_timeline']['version'],4)
        self.assertEqual(uploaded['document']['canonical_timeline'],choice['document']['canonical_timeline'])
        duplicate_path='/api/projects/'+source_project['id']+'/duplicate';body={'revision':uploaded['revision']}
        before=self.database_state()
        self.assertEqual(self.api('POST',duplicate_path,body,{'X-VF-CSRF':'bad'})[0],403)
        self.assertEqual(self.api('POST',duplicate_path,body,{'Cookie':''})[0],401)
        self.assertEqual(self.database_state(),before)
        status,child=self.api('POST',duplicate_path,body);self.assertEqual(status,200)
        self.assertEqual(child['shot_timeline']['version'],1);self.assertEqual(child['jobs'],[]);self.assertIsNone(child['approval'])
        self.assertEqual(child['shot_timeline']['snapshot']['metadata']['native_project_id'],child['id'])
        self.assertEqual(self.api('GET',timeline_path)[1],uploaded)

    def test_voice_quality_catalog_session_and_write_guards_preserve_accepted_default(self):
        before = self.database_state()
        self.assertNotIn('voice_quality', self.project['document'])
        status, catalog = self.api('GET', '/api/voice-quality')
        self.assertEqual(status, 200)
        self.assertEqual({c['id'] for c in catalog['choices']}, {'scene-context-v1', 'warm-scene-context-v1'})
        self.assertIsNone(catalog['default']['id'])
        self.assertTrue(catalog['selection_requires_explicit_action']); self.assertTrue(catalog['human_listening_required'])
        for choice in catalog['choices']:
            self.assertEqual({k: choice[k] for k in ('id', 'version', 'sha256')}, policy_reference(choice['id']))
            self.assertEqual(set(choice), {'id', 'version', 'sha256', 'label'})
            self.assertTrue(choice['label'].startswith('Thùy Dung'))
        self.assertEqual(self.api('GET', '/api/voice-quality', headers={'Cookie': ''})[0], 401)
        self.assertEqual(self.api('GET', '/api/voice-quality', headers={'Origin': 'https://foreign.invalid'})[0], 403)
        endpoint = '/api/projects/' + self.project['id'] + '/voice-quality'
        body = {'revision': self.project['revision'], 'policy_id': 'warm-scene-context-v1'}
        for headers, status in [({'Cookie': ''}, 401), ({'X-VF-CSRF': 'incorrect'}, 403),
                ({'Origin': 'https://foreign.invalid'}, 403), ({'Sec-Fetch-Site': 'cross-site'}, 403)]:
            self.assertEqual(self.api('POST', endpoint, body, headers)[0], status)
        for invalid in ({**body, 'policy_id': 'unknown'}, {**body, 'policy_id': None},
                {**body, 'revision': True}):
            self.assertEqual(self.api('POST', endpoint, invalid)[0], 400)
        status, failure = self.api('POST', endpoint, {**body, 'revision': self.project['revision'] - 1})
        self.assertEqual((status, failure['code']), (409, 'STALE_VERSION_RELOAD'))
        self.assertEqual(self.database_state(), before)
        self.assertEqual(self.server.store.get(self.project['id']), self.project)

    def test_voice_quality_http_persistence_noop_and_busy_without_dispatch(self):
        original = deepcopy(self.project)
        endpoint = '/api/projects/' + original['id'] + '/voice-quality'
        status, selected = self.api('POST', endpoint, {'revision': original['revision'], 'policy_id': 'warm-scene-context-v1'})
        self.assertEqual(status, 200)
        self.assertEqual(selected['revision'], original['revision'] + 1)
        self.assertEqual(selected['document'], {**original['document'], 'voice_quality': policy_reference('warm-scene-context-v1')})
        self.assertIsNone(selected['approval']); self.assertEqual(selected['jobs'], [])
        old_version = next(v for v in self.server.store.versions(original['id']) if v['revision'] == original['revision'])
        self.assertEqual(old_version['document'], original['document'])
        self.stop_server(); self.start_server()
        self.assertEqual(self.api('GET', '/api/projects/' + original['id'])[1], selected)
        _, reviewed_fixture = self.api('POST', '/api/projects/' + original['id'] + '/approve',
            {'revision': selected['revision'], 'reviewer': 'HTTP CONTRACT FIXTURE — NOT OWNER ACCEPTANCE', 'acknowledged': True})
        before = self.database_state()
        self.assertEqual(self.api('POST', endpoint, {'revision': selected['revision'], 'policy_id': 'warm-scene-context-v1'}),
            (200, reviewed_fixture))
        self.assertEqual(self.database_state(), before)
        # A selection is never a production dispatch; a deliberately queued local
        # fixture job only verifies that the existing busy guard still applies.
        self.server.store.enqueue(original['id'], selected['revision'], 'content', uuid.uuid4().hex)
        before = self.database_state()
        status, failure = self.api('POST', endpoint, {'revision': selected['revision'], 'policy_id': 'scene-context-v1'})
        self.assertEqual((status, failure['code']), (409, 'PROJECT_BUSY'))
        self.assertEqual(self.database_state(), before)

    def test_shot_http_edit_conflicts_failures_and_legacy_draft_compatibility(self):
        endpoint = '/api/projects/' + self.project['id'] + '/shots'
        old = self.shots(); cards = old['shot_timeline']['shots']; body = self.mutation()
        status, updated = self.api('POST', endpoint, body)
        self.assertEqual(status, 200)
        self.assertEqual(updated['revision'], old['revision'] + 1)
        self.assertEqual(updated['shot_timeline']['version'], 1)
        self.assertEqual(updated['shot_timeline']['shots'][1:], cards[1:])
        self.assertEqual(updated['shot_timeline']['scope']['voice_dependency_shot_ids'], [])
        self.assertIsNone(updated['approval']); self.assertEqual(updated['jobs'], [])
        before = self.database_state()
        status, failure = self.api('POST', endpoint, body)
        self.assertEqual((status, failure['code']), (409, 'STALE_VERSION_RELOAD'))
        for payload, expected in [({'revision': True, 'operation': body['operation']}, 400),
            ({'revision': updated['revision'], 'operation': {'type': 'update', 'shot_id': cards[0]['shot_id'], 'values': {'duration': -1}}}, 400),
            ({'revision': updated['revision'], 'operation': {'type': 'update', 'shot_id': 'shot_' + 'f' * 32, 'values': {'visual': 'Missing shot'}}}, 404)]:
            self.assertEqual(self.api('POST', endpoint, payload)[0], expected)
            self.assertEqual(self.database_state(), before)
        legacy = deepcopy(updated['document']['proposal'])
        legacy['visual_brief'][0]['on_screen_text'] = 'Legacy API edit'
        status, legacy_saved = self.api('POST', '/api/projects/' + self.project['id'] + '/draft',
            {'revision': updated['revision'], 'proposal': legacy})
        self.assertEqual(status, 200)
        current = self.shots()['shot_timeline']['shots']
        self.assertEqual([s['shot_id'] for s in current], [s['shot_id'] for s in cards])
        self.assertEqual(current[0]['on_screen_text'], 'Legacy API edit')
        self.assertIsNone(legacy_saved['approval']); self.assertEqual(legacy_saved['jobs'], [])

    def test_busy_and_archived_shot_mutations_are_explicitly_refused(self):
        body = self.mutation(); endpoint = '/api/projects/' + self.project['id'] + '/shots'
        self.server.store.enqueue(self.project['id'], self.project['revision'], 'content', uuid.uuid4().hex)
        before = self.database_state()
        status, failure = self.api('POST', endpoint, body)
        self.assertEqual((status, failure['code']), (409, 'PROJECT_BUSY'))
        self.assertEqual(self.database_state(), before)
        other = self.server.store.create('Archived HTTP fixture', 'No dispatch')
        other = self.server.store.save(other['id'], 1, proposal=proposal(), asset=self.asset)
        other_view = self.server.store.shot_view(other['id'])
        status, _ = self.api('POST', '/api/projects/' + other['id'] + '/archive', {'revision': other['revision'], 'archived': True})
        self.assertEqual(status, 200)
        status, failure = self.api('POST', '/api/projects/' + other['id'] + '/shots', {'revision': other['revision'],
            'operation': {'type': 'update', 'shot_id': other_view['shot_timeline']['shots'][0]['shot_id'], 'values': {'visual': 'Refused'}}})
        self.assertEqual((status, failure['code']), (409, 'PROJECT_ARCHIVED_RESTORE_FIRST'))

    def test_preview_video_is_session_version_and_hash_bound_transport_fixture(self):
        endpoint = '/api/projects/' + self.project['id'] + '/preview'
        current = self.shots(); view = current['shot_timeline']
        self.assertEqual(self.api('GET', endpoint)[1]['status'], 'EMPTY')
        manager = self.server.previews
        folder = manager._folder(current['id'], view['sha256'], current['revision']); folder.mkdir(parents=True)
        video = folder / 'preview.mp4'; contents = b'PREVIEW HTTP TRANSPORT FIXTURE; NOT REAL VIDEO QC'; video.write_bytes(contents)
        durable_json(folder / 'preview.json', {'id': folder.name, 'project_id': current['id'], 'revision': current['revision'],
            'timeline_version': view['version'], 'timeline_sha256': view['sha256'], 'status': 'READY', 'sha256': file_sha(video),
            'audio_mode': 'silent_visual_proxy', 'final_approval_eligible': False, 'provider_calls': 0, 'tts_calls': 0,
            'test_fixture': 'transport-only; no production acceptance'})
        status, ready = self.api('GET', endpoint)
        self.assertEqual(status, 200); self.assertFalse(ready['final_approval_eligible'])
        url = ready['video_url']
        self.assertEqual(self.api('GET', url, headers={'Cookie': ''})[0], 401)
        status, payload, metadata = self.request('GET', url)
        self.assertEqual(status, 200); self.assertEqual(payload, contents); self.assertEqual(metadata['Content-Type'], 'video/mp4')
        status, payload, metadata = self.request('GET', url, headers={'Range': 'bytes=2-8'})
        self.assertEqual(status, 206); self.assertEqual(payload, contents[2:9]); self.assertEqual(metadata['Content-Range'], f'bytes 2-8/{len(contents)}')
        self.assertEqual(self.api('GET', endpoint + '/video?version=999')[0], 409)
        video.write_bytes(b'tampered transport fixture')
        status, failure = self.api('GET', url)
        self.assertEqual((status, failure['code']), (409, 'PREVIEW_ARTIFACT_CHANGED'))
        video.write_bytes(contents)
        self.assertEqual(self.api('POST', '/api/projects/' + self.project['id'] + '/shots', self.mutation())[0], 200)
        self.assertEqual(self.api('GET', endpoint)[1]['status'], 'STALE')
        self.assertEqual(self.api('GET', url)[0], 409)
        self.assertEqual(self.server.store.get(current['id'])['jobs'], [])

    def test_preview_generation_guards_and_explicit_local_failure_no_provider(self):
        endpoint = '/api/projects/' + self.project['id'] + '/preview'
        body = {'revision': self.project['revision'], 'action': 'generate'}
        self.assertEqual(self.api('POST', endpoint, body, {'X-VF-CSRF': 'bad'})[0], 403)
        self.assertEqual(self.api('POST', endpoint, {**body, 'revision': 0})[0], 409)
        self.assertEqual(self.api('POST', endpoint, {**body, 'action': 'publish'})[0], 400)
        status, requested = self.api('POST', endpoint, body)
        self.assertEqual(status, 200); self.assertIn(requested['status'], {'QUEUED', 'RUNNING'})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status, result = self.api('GET', endpoint)
            if result['status'] not in {'QUEUED', 'RUNNING'}:
                break
            time.sleep(.025)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['error']['code'], 'FileNotFoundError')
        self.assertFalse(result['error']['automatic_replay'])
        self.assertEqual(result['provider_calls'], 0); self.assertEqual(result['tts_calls'], 0)
        self.assertIsNone(result['video_url']); self.assertFalse(result['final_approval_eligible'])
        self.assertEqual(self.server.store.get(self.project['id'])['revision'], self.project['revision'])
        self.assertEqual(self.server.store.get(self.project['id'])['jobs'], [])

    def test_ai_suggestion_http_fixture_cached_no_autoapply_then_explicit_shot_apply(self):
        calls = []
        def fixture(context):
            calls.append(deepcopy(context))
            return {'values': {'visual': 'Human-reviewable fixture suggestion', 'narration': None, 'on_screen_text': None,
                'subtitle': None, 'duration': None, 'asset_id': None}, 'rationale': 'HTTP test fixture suggestion',
                'uncertainty': 'No real AI provider or factual verification'}, {'provider': 'test_fixture', 'actual_provider_calls': 0, 'fixture_calls': 1}
        self.server.shot_ai = ShotAIEdit(self.config, self.server.store, provider=fixture)
        current = self.shots(); shot = current['shot_timeline']['shots'][0]['shot_id']
        endpoint = '/api/projects/' + current['id'] + '/ai-edit'
        body = {'revision': current['revision'], 'shot_id': shot, 'instruction': 'Đề xuất mô tả ngắn hơn', 'request_key': uuid.uuid4().hex}
        before = self.database_state()
        self.assertEqual(self.api('POST', endpoint, body, {'X-VF-CSRF': 'bad'})[0], 403); self.assertEqual(calls, [])
        status, suggestion = self.api('POST', endpoint, body)
        self.assertEqual(status, 200); self.assertTrue(suggestion['requires_human_apply']); self.assertFalse(suggestion['facts_verified'])
        self.assertFalse(suggestion['media_generated']); self.assertFalse(suggestion['render_dispatched'])
        self.assertEqual(suggestion['provider']['actual_provider_calls'], 0)
        self.assertEqual(self.database_state(), before)
        self.assertEqual(self.api('POST', endpoint, body), (200, suggestion)); self.assertEqual(len(calls), 1)
        self.assertEqual(self.api('POST', endpoint, {**body, 'instruction': 'Different request under same key'})[1]['code'], 'SHOT_AI_REQUEST_KEY_CONFLICT')
        status, applied = self.api('POST', '/api/projects/' + current['id'] + '/shots',
            {'revision': current['revision'], 'operation': suggestion['operation']})
        self.assertEqual(status, 200)
        self.assertEqual(applied['shot_timeline']['shots'][0]['visual'], 'Human-reviewable fixture suggestion')
        self.assertIsNone(applied['approval']); self.assertEqual(applied['jobs'], [])
        self.assertEqual(self.api('POST', endpoint, {**body, 'request_key': uuid.uuid4().hex})[1]['code'], 'STALE_VERSION_RELOAD')
        self.assertEqual(len(calls), 1)

    def test_ai_failure_has_durable_intent_no_implicit_provider_replay(self):
        calls = []
        def fail(context):
            calls.append(context)
            raise WorkflowError('EXPLICIT_HTTP_FIXTURE_PROVIDER_UNAVAILABLE', 503)
        self.server.shot_ai = ShotAIEdit(self.config, self.server.store, provider=fail)
        current = self.shots(); endpoint = '/api/projects/' + current['id'] + '/ai-edit'
        body = {'revision': current['revision'], 'shot_id': current['shot_timeline']['shots'][0]['shot_id'],
                'instruction': 'Fixture unavailable failure', 'request_key': uuid.uuid4().hex}
        before = self.database_state()
        status, failure = self.api('POST', endpoint, body)
        self.assertEqual((status, failure['code']), (503, 'EXPLICIT_HTTP_FIXTURE_PROVIDER_UNAVAILABLE'))
        status, repeated = self.api('POST', endpoint, body)
        self.assertEqual((status, repeated['code']), (409, 'SHOT_AI_OUTCOME_UNKNOWN_NO_REPLAY'))
        self.assertEqual(len(calls), 1); self.assertEqual(self.database_state(), before)
        folder = self.server.shot_ai.root / digest({'project_id': current['id'], 'request_key': body['request_key']})
        self.assertTrue((folder / 'intent.json').is_file())
        self.assertFalse((folder / 'result.json').exists())
        self.assertEqual(json.loads((folder / 'failure.json').read_bytes()), {'code': 'EXPLICIT_HTTP_FIXTURE_PROVIDER_UNAVAILABLE', 'automatic_retry': False})

    def test_production_http_planning_catalog_failures_preserve_native_project(self):
        original = self.server.store.get(self.project['id']); status, queue = self.api('GET', '/api/production/queue')
        self.assertEqual(status, 200); row = next(r for r in queue['items'] if r['project_id'] == self.project['id'])
        endpoint = '/api/production/planning/' + row['id']
        body = {'version': 0, 'reviewer': 'HTTP CONTRACT FIXTURE', 'changes': {'campaign': 'October test campaign',
             'planned_date': '2026-10-20', 'format': '16:9', 'project_priority': 90}}
        self.assertEqual(self.api('GET', '/api/production/queue', headers={'Cookie': ''})[0], 401)
        self.assertEqual(self.api('POST', endpoint, body, {'X-VF-CSRF': 'bad'})[0], 403)
        self.assertEqual(self.api('POST', endpoint, body, {'Origin': 'https://untrusted.invalid'})[0], 403)
        status, changed = self.api('POST', endpoint, body)
        self.assertEqual(status, 200); self.assertEqual(changed['planning']['version'], 1)
        self.assertEqual(self.api('POST', endpoint, body)[1]['code'], 'PLANNING_STALE_VERSION_RELOAD')
        self.assertEqual(self.api('POST', endpoint, {**body, 'version': 1, 'changes': {'planned_date': '2026-02-30'}})[0], 400)
        self.assertEqual(self.api('POST', endpoint, {**body, 'version': 1, 'changes': {'publish': True}})[0], 400)
        self.assertEqual(self.api('GET', endpoint + '/history')[1][0], changed['planning'])
        calendar = self.api('GET', '/api/production/calendar')[1]
        self.assertTrue(calendar['planning_only']); self.assertFalse(calendar['scheduler_enabled']); self.assertFalse(calendar['publish_enabled'])
        catalog = self.api('GET', '/api/production/profiles')[1]
        self.assertEqual(len(catalog['profiles']), 6); self.assertEqual(len(catalog['brand_templates']['templates']), 30)
        self.assertEqual(self.api('GET', '/api/brand-templates')[1]['templates'].__len__(), 15)
        self.assertEqual(len(self.api('GET', '/api/brand-templates?formats=all')[1]['templates']), 30)
        self.assertEqual(self.server.store.get(self.project['id']), original)
        self.assertEqual(self.api('GET', '/api/projects/' + self.project['id'])[1]['document'], original['document'])

    def test_production_explicit_batch_preflight_receipt_and_restart_no_provider(self):
        bundle = self.approved_brief()
        _, queue = self.api('GET', '/api/production/queue')
        row = next(r for r in queue['items'] if r['id'] == item_id('opportunity', bundle['opportunity']['id']))
        direct = next(r for r in queue['items'] if r['project_id'] == self.project['id'])
        def entry(value):
            return {'id': value['id'], 'planning_version': value['planning']['version'], 'binding_sha256': value['binding_sha256']}
        key = uuid.uuid4().hex; request = {'action': 'scripts', 'items': [entry(row), entry(direct)], 'request_key': key,
                                       'reviewer': 'HTTP CONTRACT FIXTURE', 'acknowledged': True}
        self.assertEqual(self.api('POST', '/api/production/batch', request, {'X-VF-CSRF': 'bad'})[0], 403)
        status, result = self.api('POST', '/api/production/batch', request)
        self.assertEqual(status, 200); self.assertEqual([r['status'] for r in result['items']], ['QUEUED', 'SKIPPED'])
        self.assertFalse(result['automatic_approval']); self.assertFalse(result['render_dispatched'])
        self.assertEqual(self.api('GET', '/api/production/batches/' + key), (200, result))
        self.assertEqual(self.api('POST', '/api/production/batch', request), (200, result))
        self.assertEqual(self.api('POST', '/api/production/batch', {**request, 'action': 'storyboards'})[1]['code'], 'BATCH_IDEMPOTENCY_KEY_CONFLICT')
        produced = self.server.store.get(result['items'][0]['project_id'])
        self.assertEqual([j['kind'] for j in produced['jobs']], ['content']); self.assertEqual(produced['jobs'][0]['status'], 'queued')
        self.assertIsNone(produced['approval']); self.assertIsNone(produced['document']['proposal'])
        old_session, old_csrf = self.server.session, self.server.csrf
        self.stop_server(); self.start_server()
        self.assertNotEqual(self.server.session, old_session); self.assertNotEqual(self.server.csrf, old_csrf)
        self.assertEqual(self.api('GET', '/api/production/batches/' + key, headers={'Cookie': 'vf_native_session=' + old_session})[0], 401)
        self.assertEqual(self.api('GET', '/api/production/batches/' + key), (200, result))
        self.assertEqual(self.api('POST', '/api/production/batch', request), (200, result))
        restarted = self.server.store.get(produced['id'])
        self.assertEqual(len(restarted['jobs']), 1); self.assertEqual(restarted['jobs'][0]['id'], produced['jobs'][0]['id'])
        self.assertEqual(restarted['jobs'][0]['status'], 'queued'); self.assertIsNone(restarted['approval'])


if __name__ == '__main__':
    unittest.main()
