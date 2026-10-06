"""Actual synthetic music/source audio; explicit saved ASR, no provider/UAT."""
import copy
import subprocess
import unittest
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native import source_music
from services.windows_native.source_preview import resolve_assets
from services.windows_native.music import ingest_music
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.tests import test_source_preview as fixture


class SourceMusicTests(unittest.TestCase):
    setUp=fixture.NativeSourcePreviewTests.setUp
    tearDown=fixture.NativeSourcePreviewTests.tearDown
    save_analysis=fixture.NativeSourcePreviewTests.save_analysis
    real_source=fixture.NativeSourcePreviewTests.real_source
    wait=fixture.NativeSourcePreviewTests.wait

    def music(self,frequency=220):
        path=self.root/f'music-{frequency}.wav'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n',
            '-f','lavfi','-i',f'sine=frequency={frequency}:duration=1','-c:a','pcm_s16le',str(path)],
            capture_output=True,check=True,timeout=30)
        return ingest_music(self.config,path,'audio/wav','Explicit synthetic music.wav',rights_confirmed=True)

    def test_music_repeats_on_same_timeline_and_real_proxy_keeps_sources_and_review_gate(self):
        source=self.real_source();before=copy.deepcopy(self.project['document']['canonical_timeline']['snapshot'])
        music=self.music();originals={source:file_sha(source),self.root/'assets'/music['id']:music['sha256']}
        self.project=self.store.set_music(self.project['id'],self.project['revision'],music)
        after=self.project['shot_timeline']['snapshot'];self.assertEqual(after['duration_seconds'],before['duration_seconds'])
        self.assertEqual(after['tracks'][:-1],before['tracks']);self.assertIsNone(self.project['approval'])
        track=after['tracks'][-1];self.assertEqual(track['kind'],'music');self.assertEqual(len(track['clips']),3)
        self.assertEqual([clip['timeline_start'] for clip in track['clips']],[0,1,2])
        self.assertEqual(self.project['document']['source_music_assets'][0]['bpm'],None)
        self.assertEqual(len(resolve_assets(self.config,self.project)[1]),2)
        manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
            self.assertEqual(len(value['manifest']['audio_clip_receipts']),5)
            self.assertFalse(value['manifest']['music_ducking']);self.assertFalse(self.store.get(self.project['id'])['approval'])
        finally:manager.close()
        self.assertEqual({path:file_sha(path) for path in originals},originals)

    def test_replacement_preserves_previous_music_for_exact_history_restore(self):
        self.real_source();first=self.music();self.project=self.store.set_music(self.project['id'],self.project['revision'],first)
        prior=copy.deepcopy(self.project);second=self.music(330)
        self.project=self.store.set_music(self.project['id'],self.project['revision'],second)
        self.assertEqual(len(self.project['document']['source_music_assets']),2)
        self.project=timeline.restore(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'restore_revision':prior['revision']})
        self.assertEqual(self.project['shot_timeline']['snapshot'],prior['shot_timeline']['snapshot'])
        _,assets=resolve_assets(self.config,self.project)
        self.assertTrue(any(path.name==first['id'] for _,path in assets.values()))
        self.assertFalse(any(path.name==second['id'] for _,path in assets.values()))

    def test_unknown_rights_and_locked_track_reject_without_mutation(self):
        self.real_source();music=self.music();before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'MEDIA_RIGHTS_CONFIRMATION_REQUIRED'):
            source_music.set_music(self.store,self.project['id'],self.project['revision'],{**music,'rights_confirmed':False})
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        self.project=self.store.set_music(self.project['id'],self.project['revision'],music)
        track=self.project['shot_timeline']['snapshot']['tracks'][-1]
        self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],
            'operations':[{'type':'set_track_state','track_id':track['track_id'],'locked':True}]})
        before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_MUSIC_TRACK_LOCKED'):
            self.store.set_music(self.project['id'],self.project['revision'],music)
        self.assertEqual(timeline.view(self.store,self.project['id']),before)


if __name__=='__main__':unittest.main()
