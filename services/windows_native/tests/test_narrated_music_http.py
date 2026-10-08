"""Signed actual WAV intake for narrated canonical timelines; explicit fixtures."""
import unittest
from unittest.mock import patch
from services.windows_native.tests import test_music_http as fixture
from services.windows_native.tests.test_shot_production import prepared
from services.windows_native.server import Handler
from services.windows_native.contracts import file_sha

class NarratedMusicHTTPTests(unittest.TestCase):
    setUp=fixture.MusicHTTPTests.setUp;tearDown=fixture.MusicHTTPTests.tearDown
    setUp_parent=fixture.MusicHTTPTests.setUp_parent;tearDown_parent=fixture.MusicHTTPTests.tearDown_parent
    real_source=fixture.MusicHTTPTests.real_source;save_analysis=fixture.MusicHTTPTests.save_analysis;music=fixture.MusicHTTPTests.music
    request=fixture.MusicHTTPTests.request;account=fixture.MusicHTTPTests.account;upload=fixture.MusicHTTPTests.upload
    def test_editor_can_upload_measured_narrated_overlap_without_source_or_approval_transfer(self):
        _,_,master=prepared(self.root);self.account('editor');status,updated=self.upload(project=master)
        self.assertEqual(status,201,updated);self.assertEqual(updated['document']['music']['narrated_loop']['crossfade_frames'],12000)
        self.assertEqual(updated['document']['canonical_timeline']['snapshot']['tracks'][-1]['track_id'],'trk_native_music')
        self.assertIsNone(updated['approval']);self.assertEqual(updated['jobs'],[])
        self.assertTrue(self.request('GET','/api/session')[1]['capabilities']['native_narrated_music_loop'])
    def test_invalid_and_stale_narrated_header_or_viewer_never_leave_new_assets(self):
        _,_,master=prepared(self.root);before={p.name:file_sha(p) for d in ('assets','originals') for p in (self.root/d).iterdir() if p.is_file()}
        for fade in ['NaN','1.1','0.1234','0.75']:self.assertEqual(self.upload(fade,project=master)[0],400)
        self.assertEqual(self.upload(project=master,extra={'X-VF-Revision':str(master['revision']-1)})[0],409)
        self.assertEqual({p.name:file_sha(p) for d in ('assets','originals') for p in (self.root/d).iterdir() if p.is_file()},before)
        self.account('viewer')
        with patch.object(Handler,'upload_music',side_effect=AssertionError('Viewer must not enter music intake')):self.assertEqual(self.upload(project=master)[0],403)
