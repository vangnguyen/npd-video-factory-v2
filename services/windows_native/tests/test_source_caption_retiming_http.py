"""Signed Source caption controller/API, real owned media with ASR/human fixtures."""
import json,os,subprocess,unittest
from pathlib import Path
from services.windows_native.tests import test_source_media_tracks as fixture,test_source_media_tracks_http as http_fixture

class SourceCaptionRetimingHTTPTests(unittest.TestCase):
    setUp=http_fixture.SourceMediaTracksHTTPTests.setUp;tearDown=http_fixture.SourceMediaTracksHTTPTests.tearDown
    start_server=http_fixture.SourceMediaTracksHTTPTests.start_server;stop_server=http_fixture.SourceMediaTracksHTTPTests.stop_server
    request=http_fixture.SourceMediaTracksHTTPTests.request;account=http_fixture.SourceMediaTracksHTTPTests.account
    binding=fixture.SourceMediaTracksTests.binding;page=fixture.SourceMediaTracksTests.page;audio_body=fixture.SourceMediaTracksTests.audio_body;subtitle_body=fixture.SourceMediaTracksTests.subtitle_body;captions_body=fixture.SourceMediaTracksTests.captions_body
    test_reviewer_viewer_and_missing_CSRF_never_consume_forbidden_body=http_fixture.SourceMediaTracksHTTPTests.test_reviewer_viewer_and_missing_CSRF_never_consume_forbidden_body
    def test_explicit_Source_mapping_rejects_foreign_video_SHA_and_incomplete_pair_without_write(self):
        before=self.store.get(self.project['id']);body=self.subtitle_body(timebase='source',source_video_asset_id=self.video['id'],source_video_asset_sha256=self.video['sha256'])
        for bad in [{**body,'source_video_asset_sha256':'a'*64},{k:v for k,v in body.items() if k!='source_video_asset_id'},{**body,'timebase':'timeline'}]:
            status,response,_=self.request('POST',self.base+'/subtitles',bad);self.assertIn(status,(400,409),response);self.assertEqual(self.store.get(self.project['id']),before)
    def test_actual_Studio_source_selection_and_API_video_edits_preserve_then_explicitly_reset_caption_layout(self):
        current=self.store.get(self.project['id']);context=self.owned/'source-caption-retiming-context.json';context.write_text(json.dumps({'fixture_human':True,
            'origin':'http://127.0.0.1:'+str(self.server.server_port),'workspace_id':self.workspace,'project':{'id':current['id'],'revision':current['revision']},
            'cookie':self.cookie,'csrf':self.csrf,'source_video_asset_id':self.video['id'],'source_video_asset_sha256':self.video['sha256']}),encoding='utf-8')
        repo=Path(__file__).resolve().parents[3];run=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(repo/'scripts/native_source_caption_retiming_http_ui.mjs'),str(context)],capture_output=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'));proof=json.loads(run.stdout)
        self.assertEqual(proof['remapped']['duration_seconds'],3.75);self.assertEqual(proof['manual']['captions'],proof['edited']['captions'])
        self.assertTrue(proof['caption_mutations_use_shipped_Studio_controller']);self.assertFalse(proof['browser_rendered']);self.assertFalse(proof['owner_UAT'])
        self.stop_server();self.start_server();status,page,_=self.request('GET',self.base);self.assertEqual(status,200);self.assertEqual(page,proof['reopened'])
        path=os.environ.get('VF_SOURCE_CAPTION_RETIMING_CONTROLLER_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as h:json.dump(proof,h,ensure_ascii=False,indent=2);h.write('\n')
