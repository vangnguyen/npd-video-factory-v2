"""Actual input measurement and fail-closed receipts, no speech or balance UAT."""
import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from services.windows_native import audio_loudness as loudness
from services.windows_native.pipeline import Config
from services.windows_native.contracts import WorkflowError,file_sha

class AudioLoudnessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.config=Config(data_root=Path(self.temp.name));self.path=self.config.data_root/'tone.wav'
    def tearDown(self):self.temp.cleanup()
    def generate(self,source):
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i',source,
            '-t','3','-c:a','pcm_s16le',str(self.path)],check=True,capture_output=True,timeout=30)
    def test_actual_tone_reports_input_values_without_normalizing_bytes_or_accepting_voice(self):
        self.generate('sine=frequency=440:duration=3');sha=file_sha(self.path);value=loudness.measure(self.config,self.path)
        self.assertEqual(file_sha(self.path),sha);self.assertEqual(value['input_sha256'],sha)
        self.assertEqual(value['measurement_state'],'measured');self.assertLess(value['integrated_lufs'],-16)
        self.assertLess(value['true_peak_dbfs'],-10);self.assertFalse(value['audio_modified'])
        self.assertFalse(value['normalization_target_achieved_claimed']);self.assertFalse(value['speech_detection_performed'])
        self.assertFalse(value['voice_music_balance_accepted']);self.assertEqual(value['external_provider_calls'],0)
    def test_actual_silence_is_null_not_fabricated_loudness(self):
        self.generate('anullsrc=r=48000:cl=stereo');value=loudness.measure(self.config,self.path)
        self.assertEqual(value['measurement_state'],'silent_input');self.assertIsNone(value['integrated_lufs']);self.assertIsNone(value['true_peak_dbfs'])
    def test_malformed_nonfinite_missing_or_unbounded_measurements_fail(self):
        valid={'input_i':'-23.12','input_tp':'-7.34','input_lra':'2.1','input_thresh':'-33.2'}
        self.assertEqual(loudness.parse('Diagnostic\n'+json.dumps(valid))['integrated_lufs'],-23.12)
        for body in [{},dict(valid,input_i='nan'),dict(valid,input_tp='inf'),dict(valid,input_lra='-2'),dict(valid,input_lra='-inf'),dict(valid,input_i=0),dict(valid,input_tp='100')]:
            with self.assertRaisesRegex(WorkflowError,'NATIVE_AUDIO_LOUDNESS_RESULT_INVALID'):loudness.parse(json.dumps(body))
    def test_timeout_failure_and_oversized_result_are_redacted(self):
        self.path.write_bytes(b'explicit fixture input')
        for effect in [subprocess.TimeoutExpired('PRIVATE PATH FIXTURE',60),OSError('PRIVATE PATH FIXTURE')]:
            with patch.object(loudness.subprocess,'run',side_effect=effect):
                with self.assertRaisesRegex(WorkflowError,'^NATIVE_AUDIO_LOUDNESS_SCAN_FAILED$'):loudness.measure(self.config,self.path)
        for result in [SimpleNamespace(returncode=1,stderr=b'PRIVATE PATH FIXTURE'),SimpleNamespace(returncode=0,stderr=b'X'*(1024*1024+1))]:
            with patch.object(loudness.subprocess,'run',return_value=result):
                with self.assertRaisesRegex(WorkflowError,'^NATIVE_AUDIO_LOUDNESS_SCAN_FAILED$'):loudness.measure(self.config,self.path)
    def test_input_replacement_during_scan_is_rejected(self):
        self.path.write_bytes(b'explicit fixture original')
        def replace(*args,**kwargs):
            self.path.write_bytes(b'explicit fixture replacement')
            return SimpleNamespace(returncode=0,stderr=json.dumps({'input_i':'-20','input_tp':'-5','input_lra':'0','input_thresh':'-30'}).encode())
        with patch.object(loudness.subprocess,'run',side_effect=replace):
            with self.assertRaisesRegex(WorkflowError,'NATIVE_AUDIO_LOUDNESS_INPUT_CHANGED'):loudness.measure(self.config,self.path)

if __name__=='__main__':unittest.main()
