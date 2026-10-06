"""Actual local synthetic proxy DSP; no ASR/TTS/speech/Owner acceptance."""
import copy
import unittest
from services.windows_native.tests import test_source_music as fixture
from services.windows_native import source_settings
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.contracts import file_sha


class SourceAudioProcessingTests(unittest.TestCase):
    setUp=fixture.SourceMusicTests.setUp
    tearDown=fixture.SourceMusicTests.tearDown
    save_analysis=fixture.SourceMusicTests.save_analysis
    real_source=fixture.SourceMusicTests.real_source
    wait=fixture.SourceMusicTests.wait
    music=fixture.SourceMusicTests.music

    def test_real_proxy_uses_saved_dsp_and_muted_music_does_not_claim_ducking(self):
        source=self.real_source();music=self.music()
        self.project=self.store.set_music(self.project['id'],self.project['revision'],music)
        before=copy.deepcopy(self.project['shot_timeline']['snapshot']['tracks']);source_hash=file_sha(source)
        self.project=source_settings.configure(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],
            'audio_processing':{'normalize_original_audio':True,'normalize_music':True,'duck_music':True}})
        self.assertEqual(self.project['shot_timeline']['snapshot']['tracks'],before)
        manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
            receipt=value['manifest']['audio_processing'];self.assertTrue(receipt['music_ducking'])
            self.assertTrue(receipt['normalization_original_audio_clip_ids']);self.assertTrue(receipt['normalization_music_clip_ids'])
            self.assertFalse(receipt['speech_detection_performed']);self.assertIsNone(receipt['measured_integrated_loudness'])
            track=next(item for item in self.project['shot_timeline']['snapshot']['tracks'] if item['kind']=='music')
            self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{
                'expected_version':self.project['shot_timeline']['version'],
                'operations':[{'type':'set_track_state','track_id':track['track_id'],'muted':True}]})
            self.assertEqual(manager.status(self.project['id'])['status'],'STALE')
            manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
            self.assertFalse(value['manifest']['music_ducking'])
            self.assertFalse(value['manifest']['audio_processing']['normalization_music_clip_ids'])
        finally:manager.close()
        self.assertEqual(file_sha(source),source_hash);self.assertIsNone(self.store.get(self.project['id'])['approval'])


if __name__=='__main__':unittest.main()
