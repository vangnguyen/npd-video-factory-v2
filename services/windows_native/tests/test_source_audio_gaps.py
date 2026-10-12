"""Real gapped AAC media; words/ASR remain explicit protocol fixtures."""
import asyncio,copy,subprocess,unittest,uuid,wave
from unittest.mock import patch
from services.windows_native.tests import test_asr as fixture
from services.windows_native import asr,auto_edit_analysis
from services.windows_native.media import ingest_media,media_path
from services.windows_native.contracts import file_sha,WorkflowError,digest
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner
from app.audio_waveform import measure_waveform


class GapTransport(fixture.FixtureTransport):
    cross_gap=False
    async def request(self,method,path,credential,timeout,**kwargs):
        value=await super().request(method,path,credential,timeout,**kwargs)
        if method=='GET':
            value.update(text='Trước sau.',words=[{'text':'Trước','start':100,'end':200,'confidence':.9},
                {'text':'sau.','start':600 if self.cross_gap else 1300,'end':1500,'confidence':.8}])
        return value


class SourceAudioGapTests(unittest.TestCase):
    setUp=fixture.AsrTests.setUp
    tearDown=fixture.AsrTests.tearDown
    def gapped(self):
        source=self.root/'gapped-tone.mp4'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=10:d=2',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=2','-af',"aselect='not(between(t,0.6,1.2))'",
            '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,capture_output=True,timeout=30)
        self.asset=ingest_media(self.config,source,'video/mp4','Gap tone explicit fixture',rights_confirmed=True,illustration=True)
        self.project=self.store.create('Gap clock fixture','','media');self.project=self.store.append_media(self.project['id'],1,self.asset)
        return media_path(self.config,self.asset['id'])

    def run_asr(self,cross_gap=False):
        GapTransport.cross_gap=cross_gap;GapTransport.calls=[];GapTransport.fail_observe_once=False
        with patch.object(asr,'analyze',side_effect=lambda c,j,o,s:self.analyze_original(c,j,o,s,transport_factory=GapTransport)):
            job=self.store.enqueue(self.project['id'],self.project['revision'],'asr',uuid.uuid4().hex);Runner(self.store,Pipeline(self.config)).run_one()
        return self.store.get_job(job['id'])

    def test_waveform_preserves_missing_interval_without_invented_amplitude(self):
        source=self.gapped();before=file_sha(source)
        waveform=asyncio.run(measure_waveform(source,executable=str(self.config.ffmpeg_bin/'ffmpeg.exe'),duration_seconds=2))
        self.assertEqual(waveform['method'],'ffmpeg-mono-pcm-peak-rms-v3');self.assertFalse(waveform['decoded_source_clock']['contiguous'])
        gap=waveform['missing_audio_intervals'][0];self.assertGreater(gap['end_seconds']-gap['start_seconds'],.5)
        self.assertTrue(all(b['end_seconds']<=gap['start_seconds'] or b['start_seconds']>=gap['end_seconds'] for b in waveform['bins']))
        self.assertFalse(waveform['decoded_source_clock']['implicit_gap_fill_performed']);self.assertEqual(file_sha(source),before)

    def test_actual_derived_wav_pads_exact_gap_and_preserves_every_decoded_sample(self):
        source=self.gapped();before=file_sha(source);job=self.run_asr();self.assertEqual(job['status'],'succeeded',job.get('error'))
        record=self.store.get(self.project['id'])['document']['media_analysis'][0];metadata=record['audio'];plan=metadata['explicit_gap_padding']['plan']
        directory=self.root/'jobs'/job['id']/'analysis'/self.asset['id']
        with wave.open(str(directory/'decoded-speech.wav'),'rb') as raw,wave.open(str(directory/'speech.wav'),'rb') as padded:
            self.assertEqual(padded.getnframes(),plan['normalized_pcm_samples']);self.assertEqual(raw.getnframes(),plan['decoded_pcm_samples'])
            self.assertGreater(plan['inserted_silence_samples'],8000)
            for gap in plan['gaps']:
                padded.setpos(gap['pcm_start_sample']);self.assertEqual(padded.readframes(gap['pcm_end_sample']-gap['pcm_start_sample']),b'\0'*2*(gap['pcm_end_sample']-gap['pcm_start_sample']))
            for segment in plan['segments']:
                raw.setpos(segment['pcm_start_sample']);padded.setpos(segment['normalized_pcm_start_sample']);count=segment['pcm_end_sample']-segment['pcm_start_sample']
                self.assertEqual(raw.readframes(count),padded.readframes(count))
        self.assertEqual(record['transcript']['segments'][0]['words'][1]['start_seconds'],1.3)
        self.assertEqual(record['provider_pcm_transcript']['segments'][0]['words'][1]['start_seconds'],1.3)
        self.assertEqual(file_sha(source),before);self.assertIsNone(self.store.get(self.project['id'])['approval'])
        self.assertEqual(asr.analysis_for_asset(self.store.get(self.project['id'])['document'],self.asset),record)
        forged=copy.deepcopy(record);forged['audio']['explicit_gap_padding']['plan']['inserted_silence_samples']+=1
        forged['analysis_sha256']=digest({k:v for k,v in forged.items() if k!='analysis_sha256'})
        self.assertIsNone(asr.analysis_for_asset({'media_analysis':[forged]},self.asset))
        forged=copy.deepcopy(record);forged['audio']['decoded_source_clock']['source_start_seconds']=.1
        forged['audio']['explicit_gap_padding']['decoded_audio_clock_sha256']=digest(forged['audio']['decoded_source_clock'])
        forged['analysis_sha256']=digest({k:v for k,v in forged.items() if k!='analysis_sha256'})
        self.assertIsNone(asr.analysis_for_asset({'media_analysis':[forged]},self.asset))

    def test_word_crossing_missing_audio_requires_review_without_word_split_or_paid_replay(self):
        self.gapped();job=self.run_asr(cross_gap=True);self.assertEqual(job['status'],'failed')
        self.assertEqual(job['error']['code'],'ASR_WORD_OVER_SOURCE_AUDIO_GAP_REVIEW_REQUIRED');self.assertNotIn('media_analysis',self.store.get(self.project['id'])['document'])
        with patch.object(asr,'analyze',side_effect=lambda c,j,o,s:self.analyze_original(c,j,o,s,transport_factory=GapTransport)):
            self.store.resume(job['id']);Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(self.store.get_job(job['id'])['status'],'failed');self.assertEqual(len(GapTransport.calls),3)

    def test_decoded_pcm_tamper_blocks_known_job_resume_before_another_provider_operation(self):
        self.gapped();GapTransport.cross_gap=False;GapTransport.calls=[];GapTransport.fail_observe_once=True
        with patch.object(asr,'analyze',side_effect=lambda c,j,o,s:self.analyze_original(c,j,o,s,transport_factory=GapTransport)):
            job=self.store.enqueue(self.project['id'],self.project['revision'],'asr',uuid.uuid4().hex);Runner(self.store,Pipeline(self.config)).run_one()
        raw=self.root/'jobs'/job['id']/'analysis'/self.asset['id']/'decoded-speech.wav';raw.write_bytes(raw.read_bytes()+b'changed')
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):self.store.resume(job['id'])
        self.assertEqual(len(GapTransport.calls),3)
