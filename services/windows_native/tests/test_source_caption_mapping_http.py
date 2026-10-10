"""Actual signed source-video caption UI against owned synthetic media, fake DOM."""
import json,os,subprocess,unittest
from pathlib import Path
from services.windows_native.tests import test_source_caption_mapping as mapping_fixture,test_narrated_media_tracks as media_fixture,test_source_media_tracks_http as http_fixture

class SourceCaptionMappingHTTPTests(unittest.TestCase):
    binding=media_fixture.NarratedMediaTracksTests.binding;page=media_fixture.NarratedMediaTracksTests.page
    audio_body=media_fixture.NarratedMediaTracksTests.audio_body;subtitle_body=media_fixture.NarratedMediaTracksTests.subtitle_body;captions_body=media_fixture.NarratedMediaTracksTests.captions_body
    start=media_fixture.NarratedMediaTracksTests.start;finish=media_fixture.NarratedMediaTracksTests.finish;body=media_fixture.NarratedMediaTracksTests.body
    mapped_body=mapping_fixture.SourceCaptionMappingTests.mapped_body
    request=http_fixture.SourceMediaTracksHTTPTests.request;account=http_fixture.SourceMediaTracksHTTPTests.account
    start_server=http_fixture.SourceMediaTracksHTTPTests.start_server;stop_server=http_fixture.SourceMediaTracksHTTPTests.stop_server
    tearDown=http_fixture.SourceMediaTracksHTTPTests.tearDown
    def setUp(self):
        mapping_fixture.prepare(self);self.base='/api/projects/'+self.project['id']+'/auto-edit/media-tracks';self.start_server()
    test_reviewer_viewer_and_missing_CSRF_never_consume_forbidden_body=http_fixture.SourceMediaTracksHTTPTests.test_reviewer_viewer_and_missing_CSRF_never_consume_forbidden_body
    def test_foreign_video_and_missing_explicit_binding_are_rejected_without_mutation(self):
        before=self.store.get(self.project['id']);body=self.mapped_body()
        for bad in [{**body,'source_video_asset_sha256':'0'*64},{**body,'source_video_asset_id':'0'*32+'.mp4'},
            {k:v for k,v in body.items() if k not in {'source_video_asset_id','source_video_asset_sha256'}},{**body,'source_mapping_graph':{}}]:
            status,response,_=self.request('POST',self.base+'/subtitles',bad);self.assertIn(status,(400,409),response)
            self.assertEqual(self.store.get(self.project['id']),before)
    def test_actual_shipped_Studio_controller_maps_selected_video_and_retains_human_layout_via_signed_HTTP(self):
        current=self.page();context=self.owned/'source-caption-controller-context.json';context.write_text(json.dumps({'fixture_human':True,
            'origin':'http://127.0.0.1:'+str(self.server.server_port),'workspace_id':self.workspace,
            'project':{'id':self.project['id'],'revision':current['revision']},'cookie':self.cookie,'csrf':self.csrf,
            'source_video_asset_id':self.video['id'],'source_video_asset_sha256':self.video['sha256']}),encoding='utf-8')
        repo=Path(__file__).resolve().parents[3]
        p=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(repo/'scripts/native_source_media_tracks_http_ui.mjs'),str(context)],capture_output=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'));proof=json.loads(p.stdout)
        self.assertEqual(len(proof['requests']),6);self.assertTrue(proof['source_video_mapping']);self.assertEqual(proof['subtitles']['mutation']['caption_count'],4)
        self.assertTrue(all(c['source_video_mapping_mode']=='follow_video' for c in proof['subtitles']['captions']))
        self.assertTrue(all(c['source_video_mapping_mode']=='human_layout' for c in proof['reopened']['captions']))
        self.assertFalse(proof['saved_ASR_fixture']);self.assertFalse(proof['browser_rendered']);self.assertFalse(proof['owner_UAT'])
        from services.windows_native.narrated_media_mix import verify
        verify(self.config,self.store.get(self.project['id'])['document'])
        self.stop_server();self.start_server();status,reopened,_=self.request('GET',self.base)
        self.assertEqual(status,200);self.assertEqual(reopened,proof['reopened'])
        path=os.environ.get('VF_SOURCE_CAPTION_MAPPING_CONTROLLER_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as h:json.dump(proof,h,ensure_ascii=False,indent=2);h.write('\n')
