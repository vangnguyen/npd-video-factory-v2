"""Actual authenticated Native HTTP, synthetic media, no external provider."""
import json,os,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests import test_narrated_timeline_editor as editor_fixture,test_source_media_tracks_http as http_fixture
from services.windows_native.server import Handler
from services.windows_native import narrated_timeline_editor as editor

class NarratedTimelineHTTPTests(unittest.TestCase):
    start=editor_fixture.NarratedTimelineEditorTests.start;finish=editor_fixture.NarratedTimelineEditorTests.finish;body=editor_fixture.NarratedTimelineEditorTests.body
    binding=editor_fixture.NarratedTimelineEditorTests.binding;page=editor_fixture.NarratedTimelineEditorTests.page
    audio_body=editor_fixture.NarratedTimelineEditorTests.audio_body;subtitle_body=editor_fixture.NarratedTimelineEditorTests.subtitle_body;captions_body=editor_fixture.NarratedTimelineEditorTests.captions_body
    imported=editor_fixture.NarratedTimelineEditorTests.imported
    request=http_fixture.SourceMediaTracksHTTPTests.request;account=http_fixture.SourceMediaTracksHTTPTests.account
    start_server=http_fixture.SourceMediaTracksHTTPTests.start_server;stop_server=http_fixture.SourceMediaTracksHTTPTests.stop_server;tearDown=http_fixture.SourceMediaTracksHTTPTests.tearDown
    def setUp(self):
        editor_fixture.fixture.prepare(self);self.imported();self.base='/api/projects/'+self.project['id']+'/narrated-timeline';self.start_server()
    def test_roles_CSRF_and_closed_reads_before_forbidden_body(self):
        before=self.store.get(self.project['id'])
        for role in ['viewer','reviewer']:
            self.account(role)
            for action in ['edit','configure','restore']:
                with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body read')):self.assertEqual(self.request('POST',self.base+'/'+action,{})[0],403)
            self.assertEqual(self.request('GET',self.base)[0],200)
        self.account('editor')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body read')):self.assertEqual(self.request('POST',self.base+'/edit',{}, {'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.request('GET',self.base+'?token=NEVER')[0],400);self.assertEqual(before,self.store.get(self.project['id']))
    def test_signed_read_edit_configure_restore_and_cold_exact_history(self):
        status,initial,headers=self.request('GET',self.base);self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        def binding(p):return {'revision':p['revision'],'expected_version':p['timeline_version'],'timeline_sha256':p['timeline_sha256']}
        status,settings,_=self.request('POST',self.base+'/configure',{**binding(initial),'audio_processing':{'duck_music':False}});self.assertEqual(status,200,settings)
        status,undo,_=self.request('POST',self.base+'/restore',{**binding(settings),'restore_revision':initial['revision'],'restore_timeline_sha256':initial['timeline_sha256']});self.assertEqual(status,200,undo);self.assertEqual(undo['timeline_sha256'],initial['timeline_sha256'])
        status,redo,_=self.request('POST',self.base+'/restore',{**binding(undo),'restore_revision':settings['revision'],'restore_timeline_sha256':settings['timeline_sha256']});self.assertEqual(status,200,redo);self.assertEqual(redo['timeline_sha256'],settings['timeline_sha256'])
        self.stop_server();self.start_server();status,reopened,_=self.request('GET',self.base);self.assertEqual(status,200);self.assertEqual(reopened,redo)
        path=os.environ.get('VF_NARRATED_TIMELINE_HTTP_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as h:json.dump({'fixture_human':True,'synthetic_tones_not_speech':True,'actual_HTTP':True,'provider_calls':0,'owner_UAT':False,'browser_rendered':False,'initial':initial,'settings':settings,'undo':undo,'redo':redo,'reopened':reopened},h,ensure_ascii=False,indent=2);h.write('\n')
    def test_actual_controller_undo_redo_track_mix_and_split_via_signed_HTTP(self):
        context=self.owned/'narrated-timeline-controller.json';context.write_text(json.dumps({'fixture_human':True,'origin':'http://127.0.0.1:'+str(self.server.server_port),'workspace_id':self.workspace,
            'project':self.store.get(self.project['id']),'cookie':self.cookie,'csrf':self.csrf}),encoding='utf-8')
        repo=Path(__file__).resolve().parents[3];p=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(repo/'scripts/native_narrated_timeline_http_ui.mjs'),str(context)],capture_output=True,timeout=90)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'));proof=json.loads(p.stdout)
        self.assertEqual(len(proof['requests']),9);self.assertEqual(proof['provider_calls'],0);self.assertTrue(proof['undo_redo_exact_snapshot']);self.assertTrue(proof['imported_voice_split'])
        self.assertIsNone(self.store.get(self.project['id'])['approval'])
        path=os.environ.get('VF_NARRATED_TIMELINE_CONTROLLER_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as h:json.dump(proof,h,ensure_ascii=False,indent=2);h.write('\n')
    def test_request_rejects_foreign_SHA_provider_and_stale_versions_atomically(self):
        page=editor.view(self.store,self.project['id'],self.workspace);before=self.store.get(self.project['id']);body={'revision':page['revision'],'expected_version':page['timeline_version'],'timeline_sha256':page['timeline_sha256'],
            'operations':[{'type':'set_track_state','track_id':'trk_narrated_measured_voice','muted':True}]}
        for change in [{'provider':'NEVER'},{'revision':True},{'expected_version':page['timeline_version']-1},{'timeline_sha256':'0'*64}]:self.assertIn(self.request('POST',self.base+'/edit',{**body,**change})[0],(400,409))
        self.assertEqual(before,self.store.get(self.project['id']))

if __name__=='__main__':unittest.main()
