"""Actual signed local HTTP upload-to-track decisions; no Owner/provider acceptance."""
import json,os,subprocess,threading,unittest
from pathlib import Path
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests import test_source_media_tracks as media_fixture,test_access_http as access_fixture

class SourceMediaTracksHTTPTests(unittest.TestCase):
    binding=media_fixture.SourceMediaTracksTests.binding
    page=media_fixture.SourceMediaTracksTests.page
    audio_body=media_fixture.SourceMediaTracksTests.audio_body
    subtitle_body=media_fixture.SourceMediaTracksTests.subtitle_body
    captions_body=media_fixture.SourceMediaTracksTests.captions_body
    request=access_fixture.NativeAccessHTTPTests.request
    def setUp(self):
        media_fixture.prepare(self);self.base='/api/projects/'+self.project['id']+'/auto-edit/media-tracks';self.start_server()
    def start_server(self):
        raw,data=human_fixture('editor',workspace=self.workspace);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        self.server=LocalServer(0,self.config,start_worker=False,access=access);self.cookie,session=access.login(raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def stop_server(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def tearDown(self):self.stop_server();self.temp.cleanup()
    def account(self,role):
        raw,data=human_fixture(role,workspace=self.workspace);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        access.bind_root(self.root);self.server.access=access;self.cookie,session=access.login(raw);self.csrf=session.csrf
    def test_actual_signed_read_audio_subtitle_caption_edit_and_restart(self):
        status,initial,headers=self.request('GET',self.base);self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        status,audio,_=self.request('POST',self.base+'/audio',self.audio_body(timeline_start=.5));self.assertEqual(status,200,audio)
        self.assertEqual(audio['timeline_version'],initial['timeline_version']+1);self.assertEqual(audio['mutation']['asset_id'],self.voice['id'])
        status,subtitles,_=self.request('POST',self.base+'/subtitles',self.subtitle_body());self.assertEqual(status,200,subtitles);self.assertEqual(subtitles['captions_total'],2)
        body=self.captions_body();status,edited,_=self.request('POST',self.base+'/captions',body);self.assertEqual(status,200,edited);self.assertTrue(edited['mutation']['changed'])
        self.stop_server();self.start_server();status,reopened,_=self.request('GET',self.base);self.assertEqual(status,200);self.assertEqual(reopened,{k:v for k,v in edited.items() if k!='mutation'})
        path=os.environ.get('VF_SOURCE_MEDIA_TRACKS_HTTP_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as h:json.dump({'schema_version':'native-source-media-tracks-signed-fixture-v1',
                'fixture_human':True,'saved_ASR_fixture':True,'actual_local_media_waveform':True,'actual_HTTP':True,'real_provider_calls':0,
                'browser_rendered':False,'owner_UAT':False,'initial':initial,'audio':audio,'subtitles':subtitles,'edited':edited,'reopened':reopened},h,ensure_ascii=False,indent=2);h.write('\n')
    def test_reviewer_viewer_and_missing_CSRF_never_consume_forbidden_body(self):
        before=self.store.get(self.project['id'])
        for role in ['viewer','reviewer']:
            self.account(role)
            for action in ['audio','subtitles','captions']:
                with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body consumed')):self.assertEqual(self.request('POST',self.base+'/'+action,{})[0],403)
            self.assertEqual(self.request('GET',self.base)[0],200)
        self.account('editor')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body consumed')):self.assertEqual(self.request('POST',self.base+'/audio',{}, {'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_page_and_mutation_routes_reject_unbounded_or_provider_input(self):
        before=self.store.get(self.project['id']);body=self.audio_body()
        for change in [{'provider':'unapproved'},{'role':'owner'},{'asset_sha256':'a'*64},{'timeline_sha256':'a'*64},{'revision':body['revision']-1}]:
            self.assertIn(self.request('POST',self.base+'/audio',{**body,**change})[0],(400,409))
        for query in ['?token=NEVER','?caption_page=0','?caption_page=2&caption_page=3','?caption_page=no']:
            self.assertEqual(self.request('GET',self.base+query)[0],400)
        self.assertEqual(self.request('POST',self.base+'/audio?token=NEVER',body)[0],400)
        self.assertEqual(self.request('GET',self.base+'/audio')[0],400);self.assertEqual(self.store.get(self.project['id']),before)
        status,page,_=self.request('GET',self.base+'?caption_page=2');self.assertEqual(status,200);self.assertEqual(page['captions'],[]);self.assertEqual(page['caption_page'],2)
    def test_new_capability_and_static_controller_are_additive_and_inert(self):
        before=self.store.get(self.project['id']);status,session,_=self.request('GET','/api/session');self.assertEqual(status,200);self.assertTrue(session['capabilities']['native_source_media_tracks'])
        status,module,_=self.request('GET','/native-source-media-tracks.mjs');self.assertEqual(status,200);self.assertIn(b'initializeSourceMediaTracks',module)
        self.assertEqual(self.store.get(self.project['id']),before)

    def test_actual_Studio_controller_places_voice_music_cues_and_edits_via_signed_HTTP(self):
        current=self.page();context=self.owned/'controller-context.json';context.write_text(json.dumps({'fixture_human':True,
            'origin':'http://127.0.0.1:'+str(self.server.server_port),'workspace_id':self.workspace,
            'project':{'id':self.project['id'],'revision':current['revision']},'cookie':self.cookie,'csrf':self.csrf}),encoding='utf-8')
        repo=Path(__file__).resolve().parents[3]
        p=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(repo/'scripts/native_source_media_tracks_http_ui.mjs'),str(context)],capture_output=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'));proof=json.loads(p.stdout)
        self.assertEqual(len(proof['requests']),6);self.assertEqual(len(proof['imports']),3);self.assertFalse(proof['owner_UAT'])
        current=self.store.get(self.project['id']);self.assertEqual(current['document']['canonical_timeline']['version'],5);self.assertIsNone(current['approval'])
        from services.windows_native.source_preview import resolve_assets
        resolve_assets(self.config,current)
        path=os.environ.get('VF_SOURCE_MEDIA_TRACKS_CONTROLLER_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as h:json.dump(proof,h,ensure_ascii=False,indent=2);h.write('\n')
