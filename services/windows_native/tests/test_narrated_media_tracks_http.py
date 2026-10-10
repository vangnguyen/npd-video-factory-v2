"""Actual signed HTTP/controller against saved measured synthetic Mode A PCM."""
import json,os,subprocess,unittest
from pathlib import Path
from services.windows_native.tests import test_narrated_media_tracks as media_fixture,test_source_media_tracks_http as http_fixture

class NarratedMediaTracksHTTPTests(unittest.TestCase):
    binding=media_fixture.NarratedMediaTracksTests.binding;page=media_fixture.NarratedMediaTracksTests.page
    audio_body=media_fixture.NarratedMediaTracksTests.audio_body;subtitle_body=media_fixture.NarratedMediaTracksTests.subtitle_body;captions_body=media_fixture.NarratedMediaTracksTests.captions_body
    start=media_fixture.NarratedMediaTracksTests.start;finish=media_fixture.NarratedMediaTracksTests.finish;body=media_fixture.NarratedMediaTracksTests.body
    request=http_fixture.SourceMediaTracksHTTPTests.request;account=http_fixture.SourceMediaTracksHTTPTests.account
    start_server=http_fixture.SourceMediaTracksHTTPTests.start_server;stop_server=http_fixture.SourceMediaTracksHTTPTests.stop_server
    tearDown=http_fixture.SourceMediaTracksHTTPTests.tearDown
    def setUp(self):
        media_fixture.prepare(self);self.base='/api/projects/'+self.project['id']+'/auto-edit/media-tracks';self.start_server()
    test_reviewer_viewer_and_missing_CSRF_never_consume_forbidden_body=http_fixture.SourceMediaTracksHTTPTests.test_reviewer_viewer_and_missing_CSRF_never_consume_forbidden_body
    test_page_and_mutation_routes_reject_unbounded_or_provider_input=http_fixture.SourceMediaTracksHTTPTests.test_page_and_mutation_routes_reject_unbounded_or_provider_input
    def test_actual_signed_read_caption_seed_audio_SRT_edit_and_restart(self):
        before=self.store.get(self.project['id']);status,initial,headers=self.request('GET',self.base)
        self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(initial['timeline_mode'],'narrated');self.assertTrue(initial['pending_generated_tracks'])
        self.assertEqual(before,self.store.get(self.project['id']))
        status,audio,_=self.request('POST',self.base+'/audio',self.audio_body(timeline_start=.5));self.assertEqual(status,200,audio);self.assertFalse(audio['pending_generated_tracks'])
        status,subtitles,_=self.request('POST',self.base+'/subtitles',self.subtitle_body());self.assertEqual(status,200,subtitles)
        status,edited,_=self.request('POST',self.base+'/captions',self.captions_body());self.assertEqual(status,200,edited)
        self.stop_server();self.start_server();status,reopened,_=self.request('GET',self.base);self.assertEqual(status,200);self.assertEqual(reopened,{k:v for k,v in edited.items() if k!='mutation'})
        path=os.environ.get('VF_NARRATED_MEDIA_TRACKS_HTTP_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as h:json.dump({'schema_version':'native-narrated-media-tracks-signed-fixture-v1',
                'fixture_human':True,'synthetic_measured_narration_fixture':True,'saved_ASR_fixture':False,'actual_local_media_waveform':True,'actual_HTTP':True,
                'real_provider_calls':0,'browser_rendered':False,'owner_UAT':False,'initial':initial,'audio':audio,'subtitles':subtitles,'edited':edited,'reopened':reopened},h,ensure_ascii=False,indent=2);h.write('\n')
    def test_actual_Studio_controller_measured_projection_to_media_tracks_via_signed_HTTP(self):
        current=self.page();context=self.owned/'narrated-controller-context.json';context.write_text(json.dumps({'fixture_human':True,
            'origin':'http://127.0.0.1:'+str(self.server.server_port),'workspace_id':self.workspace,
            'project':{'id':self.project['id'],'revision':current['revision']},'cookie':self.cookie,'csrf':self.csrf}),encoding='utf-8')
        repo=Path(__file__).resolve().parents[3]
        p=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(repo/'scripts/native_source_media_tracks_http_ui.mjs'),str(context)],capture_output=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'));proof=json.loads(p.stdout)
        self.assertEqual(len(proof['requests']),6);self.assertEqual(len(proof['imports']),3);self.assertFalse(proof['saved_ASR_fixture']);self.assertTrue(proof['synthetic_measured_narration_fixture'])
        from services.windows_native.narrated_media_mix import verify
        verify(self.config,self.store.get(self.project['id'])['document'])
        path=os.environ.get('VF_NARRATED_MEDIA_TRACKS_CONTROLLER_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as h:json.dump(proof,h,ensure_ascii=False,indent=2);h.write('\n')
