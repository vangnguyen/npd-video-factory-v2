"""Real streamed motion pixels/PTS plus legacy Native fingerprint compatibility."""
import asyncio,copy,json,subprocess,unittest,uuid
from fractions import Fraction
from unittest.mock import patch
from services.windows_native.tests import test_auto_edit_analysis as analysis_fixture
from services.windows_native.tests import test_decoded_frame_sampling as frame_fixture
from services.windows_native import auto_edit_analysis as native
from services.windows_native.media import media_path
from services.windows_native.pipeline import Pipeline
from services.windows_native.contracts import digest,file_sha
from app.visual_signals import measure_visual_signals
from app.auto_edit_models import AutoEditAnalysisRead
from app.auto_edit_providers import FFmpegMediaSignalProvider


class DenseVisualClockTests(unittest.TestCase):
    setUp=analysis_fixture.NativeAutoEditTests.setUp
    tearDown=analysis_fixture.NativeAutoEditTests.tearDown

    def test_legacy_v3_analysis_remains_current_without_new_job_or_json_rewrite(self):
        with patch.object(FFmpegMediaSignalProvider,'algorithm_version','scene-silence-waveform-visual-v3'):
            record=native.make_analysis(self.project['id'],self.project['document'],self.asset,self.metadata,self.signals)
        record['analysis']['provenance'].pop('signal_algorithm');record['sha256']=digest({k:v for k,v in record.items() if k!='sha256'})
        before=copy.deepcopy(record);value=AutoEditAnalysisRead.model_validate(record['analysis'])
        self.assertTrue(native.matches_saved_fingerprint(value,self.project['id'],self.project['document'],self.asset))
        self.assertNotEqual(value.fingerprint,native.fingerprint(self.project['id'],self.project['document'],self.asset))
        self.assertEqual(record,before);self.assertEqual(native.pending({'media_analysis':self.project['document']['media_analysis'],'assets':[self.asset],'auto_edit_analyses':[record]},self.project['id']),[])

    def test_actual_vfr_dense_motion_uses_source_pts_without_nominal_fps_duplicates(self):
        frame_fixture.DecodedFrameSamplingTests.vfr(self);source=media_path(self.config,self.asset['id']);before=file_sha(source)
        result=asyncio.run(measure_visual_signals(source,executable=str(self.config.ffmpeg_bin/'ffmpeg.exe'),duration_seconds=self.asset['duration_seconds']))
        probe=json.loads(subprocess.check_output([str(self.config.ffmpeg_bin/'ffprobe.exe'),'-v','error','-show_frames','-show_streams','-show_format',
            '-select_streams','v:0','-show_entries','frame=pts:stream=time_base:format=start_time','-of','json',str(source)]))
        tb=Fraction(probe['streams'][0]['time_base']);origin=float(probe['format']['start_time']);actual=[float(int(f['pts'])*tb)-origin for f in probe['frames']]
        self.assertEqual(result['schema_version'],2);self.assertTrue(result['decoded_pts_verified']);self.assertFalse(result['semantic_vision'])
        for frame in result['frames']:self.assertTrue(any(abs(frame['timestamp_seconds']-t)<1e-9 for t in actual))
        self.assertLessEqual(len(result['frames']),len(actual));self.assertNotEqual([f['timestamp_seconds'] for f in result['frames']],result['requested_sample_times'])
        self.assertNotIn(str(source),result['decoder_clock_log']);self.assertEqual(file_sha(source),before)

    def test_new_native_analysis_persists_v4_clock_and_does_not_call_asr(self):
        frame_fixture.DecodedFrameSamplingTests.vfr(self);before=copy.deepcopy(self.project['document'])
        queued=self.store.enqueue(self.project['id'],self.project['revision'],'auto_edit_analysis',uuid.uuid4().hex);job=self.store.claim()
        with patch('services.windows_native.asr.analyze',side_effect=AssertionError('No new ASR call')):
            result=Pipeline(self.config).run(job,lambda _:None)
        self.store.finish(job,result=result);bundle=native.view(self.store,self.project['id']);analysis=bundle['analyses'][0]['analysis']
        self.assertEqual(analysis['provenance']['signal_algorithm'],'scene-silence-waveform-visual-v4')
        self.assertTrue(analysis['provenance']['media_signals']['visual']['decoded_pts_verified'])
        self.assertIsNone(analysis['transcript']);self.assertEqual(result['provider_calls'],0)
        self.assertEqual(self.store.get(self.project['id'])['document'].get('canonical_timeline'),before.get('canonical_timeline'))

    def test_nonzero_start_scene_boundary_uses_actual_normalized_clock_and_matching_score(self):
        from app.auto_edit_models import MediaMetadata
        source=self.root/'offset-shot-boundary.mp4'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n',
            '-f','lavfi','-i','color=c=black:s=320x240:r=30:d=1','-f','lavfi','-i','color=c=white:s=320x240:r=30:d=1',
            '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-c:v','libx264','-pix_fmt','yuv420p','-output_ts_offset','4',str(source)],
            check=True,capture_output=True,timeout=30)
        provider=FFmpegMediaSignalProvider(str(self.config.ffmpeg_bin/'ffmpeg.exe'))
        result=asyncio.run(provider.analyze(source,metadata=MediaMetadata(media_kind='video',detected_content_type='video/mp4',duration_seconds=2.,
            width=320,height=240,fps=30,video_codec='h264'),silence_threshold_db=-35.,minimum_silence_duration=.5))
        self.assertEqual(len(result.shot_boundaries),1)
        self.assertAlmostEqual(result.shot_boundaries[0][0],1.,places=9)
        self.assertGreater(result.shot_boundaries[0][1],.35)
        self.assertTrue(result.provenance['scene_decoded_clock_verified'])
        self.assertEqual(result.provenance['scene_decoded_stamps'][0]['timestamp_seconds'],1.)
        self.assertTrue(result.visual['decoded_pts_verified']);self.assertFalse(result.visual['semantic_vision'])
