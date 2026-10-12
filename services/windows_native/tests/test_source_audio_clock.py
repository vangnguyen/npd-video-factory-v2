"""Actual delayed source audio; provider speech remains an explicit transport fixture."""
import asyncio,copy,subprocess,unittest,uuid
from unittest.mock import patch
from services.windows_native.tests import test_asr as fixture
from services.windows_native import asr,auto_edit_analysis
from services.windows_native.media import ingest_media,media_path
from services.windows_native.contracts import file_sha,WorkflowError,digest
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner
from app.audio_waveform import measure_waveform


class SourceAudioClockTests(unittest.TestCase):
    setUp=fixture.AsrTests.setUp
    tearDown=fixture.AsrTests.tearDown
    def delayed(self):
        source=self.root/'delayed-tone-source.mp4'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=10:d=2',
            '-itsoffset','0.5','-f','lavfi','-i','sine=frequency=440:duration=1','-map','0:v:0','-map','1:a:0',
            '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-t','2',str(source)],check=True,capture_output=True,timeout=30)
        asset=ingest_media(self.config,source,'video/mp4','Delayed tone explicit fixture',rights_confirmed=True,illustration=True)
        self.project=self.store.create('Source clock fixture','','media');self.project=self.store.append_media(self.project['id'],1,asset);self.asset=asset
        return media_path(self.config,asset['id'])

    def test_waveform_starts_at_observed_audio_source_time_without_synthetic_leading_bins(self):
        source=self.delayed();before=file_sha(source)
        waveform=asyncio.run(measure_waveform(source,executable=str(self.config.ffmpeg_bin/'ffmpeg.exe'),duration_seconds=2.))
        self.assertEqual(waveform['method'],'ffmpeg-mono-pcm-peak-rms-v2');self.assertTrue(waveform['decoded_pts_verified'])
        self.assertGreater(waveform['bins'][0]['start_seconds'],.45)
        self.assertAlmostEqual(waveform['bins'][0]['start_seconds'],waveform['source_start_seconds'],places=6)
        self.assertFalse(waveform['decoded_source_clock']['implicit_gap_fill_performed']);self.assertEqual(file_sha(source),before)

    def test_provider_pcm_evidence_is_preserved_and_transcript_maps_to_observed_source_offset(self):
        source=self.delayed();before=file_sha(source);job=self.store.enqueue(self.project['id'],self.project['revision'],'asr',uuid.uuid4().hex)
        Runner(self.store,Pipeline(self.config)).run_one();saved=self.store.get_job(job['id']);self.assertEqual(saved['status'],'succeeded',saved.get('error'))
        record=self.store.get(self.project['id'])['document']['media_analysis'][0];offset=record['audio']['decoded_source_clock']['source_start_seconds']
        self.assertGreater(offset,.45);original=record['provider_pcm_transcript'];mapped=record['transcript']
        self.assertEqual(original['segments'][0]['words'][0]['start_seconds'],0.)
        self.assertAlmostEqual(mapped['segments'][0]['words'][0]['start_seconds'],offset,places=9)
        self.assertAlmostEqual(mapped['segments'][0]['words'][1]['start_seconds'],offset+.21,places=9)
        self.assertEqual(mapped['provenance']['source_clock_mapping']['provider_pcm_transcript_sha256'],digest(original))
        self.assertEqual(mapped['provenance']['raw_response_sha256'],original['provenance']['raw_response_sha256'])
        self.assertEqual(file_sha(source),before);self.assertEqual(len(fixture.FixtureTransport.calls),3)
        forged=copy.deepcopy(record);forged['transcript']['segments'][0]['words'][0]['start_seconds']+=.1
        forged['analysis_sha256']=digest({k:v for k,v in forged.items() if k!='analysis_sha256'})
        self.assertIsNone(asr.analysis_for_asset({'media_analysis':[forged]},self.asset))
        self.assertEqual(asr.analysis_for_asset({'media_analysis':[record]},self.asset),record)

    def test_noncontiguous_audio_clock_refuses_dispatch_before_upload_or_new_paid_creation(self):
        self.delayed()
        with patch('app.decoded_audio_clock.parse_audio_clock',side_effect=ValueError('DECODED_AUDIO_NONCONTIGUOUS_REVIEW_REQUIRED')):
            job=self.store.enqueue(self.project['id'],self.project['revision'],'asr',uuid.uuid4().hex);Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(self.store.get_job(job['id'])['status'],'failed');self.assertEqual(fixture.FixtureTransport.calls,[])
        self.assertNotIn('media_analysis',self.store.get(self.project['id'])['document'])
