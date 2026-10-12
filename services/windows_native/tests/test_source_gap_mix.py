"""Real normalized-source PCM timing; no speech/provider/Owner acceptance."""
import asyncio,array,datetime,json,math,subprocess,unittest
from unittest.mock import patch
from services.windows_native.tests import test_asr as fixture,test_source_audio_gaps as gap_fixture,test_source_audio_clock as clock_fixture
from services.windows_native.contracts import file_sha
from services.windows_native.media import media_path
from app.platform_models import AssetRead
from app.timeline_models import TimelineSnapshot,TimelineTrack,TimelineClip
from app.timeline_audio_processing import build_processed_audio_graph
from app.source_audio_clock import verify_audio_inputs,INPUT_TIMESTAMP_OPTIONS
from app.timeline_proxy import FFmpegProxyRenderer


class SourceGapMixTests(unittest.TestCase):
    setUp=fixture.AsrTests.setUp
    tearDown=fixture.AsrTests.tearDown
    gapped=gap_fixture.SourceAudioGapTests.gapped
    def snapshot(self,start=0,end=2,speed=1,placement=0,source=None):
        source=source or self.gapped();now=datetime.datetime.now(datetime.timezone.utc);self.original=file_sha(source)
        dto=AssetRead(asset_id='ast_gap_mix',workspace_id='wsp_gap_mix',project_id='prj_gap_mix',project_version_id=None,job_id=None,asset_class='source',kind='video',filename=source.name,object_key='assets/'+source.name,content_type='video/mp4',size_bytes=source.stat().st_size,checksum_sha256=self.original,storage_provider='local',version=1,provenance={'fixture':True},created_at=now,updated_at=now)
        duration=(end-start)/speed
        snapshot=TimelineSnapshot(duration_seconds=placement+duration,tracks=[TimelineTrack(track_id='trk_gap_mix',type='audio',kind='original_audio',label='Original',order=0,
            clips=[TimelineClip(clip_id='clip_gap_mix',kind='original_audio',label='Source',asset_id=dto.asset_id,source_start=start,source_end=end,speed=speed,timeline_start=placement,duration=duration)])])
        return snapshot,{dto.asset_id:(dto,source)}
    def mix(self,snapshot,assets):
        clocks=asyncio.run(verify_audio_inputs(snapshot,assets,executable=str(self.config.ffmpeg_bin/'ffmpeg.exe')))
        graph=build_processed_audio_graph(snapshot,assets,first_input_index=0);out=self.root/'mix.pcm'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n',*INPUT_TIMESTAMP_OPTIONS,*graph.inputs,'-filter_complex',';'.join(graph.filters),'-map','[outa]','-ac','1','-ar','48000','-f','s16le',str(out)],check=True,capture_output=True,timeout=30)
        samples=array.array('h');samples.frombytes(out.read_bytes());self.assertEqual(len(samples),round(snapshot.duration_seconds*48000))
        def rms(a,b):
            values=samples[round(a*48000):round(b*48000)];self.assertTrue(values)
            return math.sqrt(sum(float(v)**2 for v in values)/len(values))/32768
        self.assertEqual(file_sha(next(iter(assets.values()))[1]),self.original)
        return clocks,rms
    def test_gap_is_not_collapsed_and_late_original_audio_survives(self):
        snapshot,assets=self.snapshot();clocks,rms=self.mix(snapshot,assets)
        self.assertFalse(clocks['assets']['ast_gap_mix']['clock']['contiguous'])
        self.assertLess(rms(.8,.9),.001);self.assertGreater(rms(1.35,1.45),.02);self.assertGreater(rms(1.8,1.9),.02)
    def test_nonzero_audio_origin_stays_in_source_time_before_trim(self):
        source=clock_fixture.SourceAudioClockTests.delayed(self)
        snapshot,assets=self.snapshot(source=source);clocks,rms=self.mix(snapshot,assets)
        self.assertGreater(clocks['assets']['ast_gap_mix']['clock']['source_start_seconds'],.4)
        self.assertLess(rms(.2,.3),.001);self.assertGreater(rms(.7,.8),.02)
    def test_trim_and_placement_keep_gap_in_source_coordinates(self):
        snapshot,assets=self.snapshot(start=1,end=2,placement=.3);_,rms=self.mix(snapshot,assets)
        self.assertLess(rms(.36,.46),.001);self.assertGreater(rms(.7,.8),.02);self.assertGreater(rms(1.15,1.25),.02)
    def test_requested_speed_changes_gap_duration_without_losing_source_origin(self):
        snapshot,assets=self.snapshot(speed=2,placement=.2);_,rms=self.mix(snapshot,assets)
        self.assertLess(rms(.62,.7),.001);self.assertGreater(rms(1.0,1.1),.02)
    def test_actual_shared_proxy_preserves_the_same_missing_interval(self):
        snapshot,assets=self.snapshot();out=self.root/'proxy.mp4'
        async def cancelled():return False
        result=asyncio.run(FFmpegProxyRenderer(str(self.config.ffmpeg_bin/'ffmpeg.exe'),str(self.config.ffmpeg_bin/'ffprobe.exe')).render(snapshot=snapshot,assets=assets,output_path=out,width=432,height=768,is_cancelled=cancelled))
        self.assertFalse(result.manifest['source_audio_clocks']['assets']['ast_gap_mix']['clock']['contiguous'])
        data=subprocess.check_output([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-i',str(out),'-map','0:a:0','-ac','1','-ar','48000','-f','s16le','-'])
        samples=array.array('h');samples.frombytes(data)
        def rms(a,b):
            values=samples[round(a*48000):round(b*48000)];return math.sqrt(sum(float(v)**2 for v in values)/len(values))/32768
        self.assertLess(rms(.8,.9),.001);self.assertGreater(rms(1.8,1.9),.02)
    def test_source_change_and_cancel_refuse_before_decoder_dispatch(self):
        snapshot,assets=self.snapshot();source=next(iter(assets.values()))[1];source.write_bytes(source.read_bytes()+b'changed')
        with patch('asyncio.create_subprocess_exec',side_effect=AssertionError('No decoder dispatch')):
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):asyncio.run(verify_audio_inputs(snapshot,assets,executable='unused'))
            async def cancelled():return True
            with self.assertRaisesRegex(ValueError,'CANCELLED'):asyncio.run(verify_audio_inputs(snapshot,assets,executable='unused',is_cancelled=cancelled))
    def test_overlapping_decoder_clock_blocks_proxy_before_encoding(self):
        snapshot,assets=self.snapshot();out=self.root/'refused-proxy.mp4';calls=[];original=asyncio.create_subprocess_exec
        async def counted(*args,**kwargs):calls.append(args);return await original(*args,**kwargs)
        async def cancelled():return False
        with patch('app.source_audio_clock.parse_audio_clock',side_effect=ValueError('DECODED_AUDIO_NONCONTIGUOUS_REVIEW_REQUIRED')),patch('asyncio.create_subprocess_exec',side_effect=counted):
            with self.assertRaisesRegex(ValueError,'NONCONTIGUOUS'):
                asyncio.run(FFmpegProxyRenderer(str(self.config.ffmpeg_bin/'ffmpeg.exe'),str(self.config.ffmpeg_bin/'ffprobe.exe')).render(snapshot=snapshot,assets=assets,output_path=out,width=432,height=768,is_cancelled=cancelled))
        self.assertFalse(out.exists());self.assertEqual(len(calls),1);self.assertNotIn('-/filter_complex',calls[0])
