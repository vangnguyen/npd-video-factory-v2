"""Actual VFR decoding and independent FFprobe clocks; no semantic/ASR provider."""
import copy,json,subprocess,unittest,uuid,os
from fractions import Fraction
from pathlib import Path
from PIL import Image

from services.windows_native import media_frame_analysis as frames
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.media import ingest_media,media_path
from services.windows_native.vision import NativeVision
from services.windows_native.vision_models import NativeVisionRequest
from services.windows_native.vision_frame_bridge import NativeEvidenceFrameExtractor
from services.windows_native.tests import test_media_frame_analysis as fixture
from services.windows_native.tests import test_source_preview as source_fixture


class DecodedFrameSamplingTests(unittest.TestCase):
    setUp=source_fixture.NativeSourcePreviewTests.setUp
    tearDown=source_fixture.NativeSourcePreviewTests.tearDown
    save_analysis=source_fixture.NativeSourcePreviewTests.save_analysis
    measure=fixture.MediaFrameTests.measure
    real_source=source_fixture.NativeSourcePreviewTests.real_source

    def vfr(self):
        entries=[]
        for i,span in enumerate((.08,.35,.69,.72,.20)):
            path=self.root/f'known-vfr-{i}.png'
            image=Image.new('RGB',(320,240),(30+i*35,130-i*15,50+i*30));image.save(path)
            entries += [f"file '{path.as_posix()}'",f'duration {span}']
        entries.append(f"file '{path.as_posix()}'")
        spec=self.root/'known-vfr.ffconcat';spec.write_text('ffconcat version 1.0\n'+'\n'.join(entries)+'\n',encoding='utf-8')
        output=self.root/'known-vfr.mp4'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','concat','-safe','0','-i',str(spec),
            '-fps_mode','vfr','-c:v','libx264','-crf','0','-pix_fmt','yuv420p',str(output)],check=True,capture_output=True,timeout=30)
        asset=ingest_media(self.config,output,'video/mp4','VFR explicit local fixture',rights_confirmed=True,illustration=True)
        self.project=self.store.create('VFR independent clock fixture','','media');self.project=self.store.append_media(self.project['id'],1,asset)
        self.asset=asset;return media_path(self.config,asset['id'])

    def test_variable_rate_keeps_actual_decoded_pts_and_fewer_samples_without_fps_duplication(self):
        source=self.vfr();original=file_sha(source);before=copy.deepcopy(self.project['document']);job,result=self.measure()
        observation=frames.view(self.store,self.project['id'])['observations'][0]
        probe=json.loads(subprocess.check_output([str(self.config.ffmpeg_bin/'ffprobe.exe'),'-v','error','-protocol_whitelist','file,pipe',
            '-select_streams','v:0','-show_frames','-show_streams','-show_format','-show_entries','frame=pts:stream=time_base:format=start_time','-of','json',str(source)]))
        tb=Fraction(probe['streams'][0]['time_base']);origin=float(probe['format']['start_time'])
        actual=[float(int(f['pts'])*tb)-origin for f in probe['frames']]
        self.assertLess(len(observation['frames']),8);self.assertGreater(len(observation['frames']),1)
        for f in observation['frames']:
            self.assertTrue(any(abs(f['timestamp_seconds']-t)<1e-9 for t in actual))
            self.assertEqual(f['decoded_pts_seconds'],f['timestamp_seconds']);self.assertEqual(f['decoded_clock']['time_base_denominator'],tb.denominator)
        self.assertNotEqual([f['timestamp_seconds'] for f in observation['frames']],observation['decoded_clock_evidence']['requested_times'])
        self.assertEqual(self.project['document'].get('canonical_timeline'),before.get('canonical_timeline'))
        self.assertEqual(file_sha(source),original);self.assertEqual(result['provider_calls'],0);self.assertIsNone(observation['confidence'])
        service=NativeVision(self.store,self.config);request=NativeVisionRequest(revision=self.project['revision'],observation_ids=[observation['observation_id']],request_key='independent-clock-fixture')
        source_binding=service.sources(self.project,request)[0];bridge=NativeEvidenceFrameExtractor(self.root,self.config,self.project['id'],source_binding)
        self.assertTrue(bridge.binding()['decoded_pts_verified']);self.assertEqual(bridge.binding()['source_frame_evidence'],observation['frames'])

    def test_rehashed_wrong_timestamp_and_changed_decoder_log_cannot_become_verified(self):
        self.vfr();self.measure();record=self.project['document']['media_frame_analyses'][0]
        changed=copy.deepcopy(record);frame=changed['observation']['frames'][0];frame['decoded_clock']['pts']+=1
        frame['timestamp_seconds']=frame['decoded_pts_seconds']=frame['decoded_clock']['timestamp_seconds']=frame['decoded_clock']['pts']*frame['decoded_clock']['time_base_numerator']/frame['decoded_clock']['time_base_denominator']
        changed['sha256']=digest(changed['observation']);frames.validate(changed,self.project['id'],self.asset)
        with self.assertRaisesRegex(WorkflowError,'CLOCK_EVIDENCE_CHANGED'):frames.verify_clock(self.root,changed['observation'])
        evidence=record['observation']['decoded_clock_evidence'];name=evidence['log_reference'].split('/')[-1]
        log=self.root/'jobs'/record['observation']['job_id']/name;log.write_bytes(log.read_bytes()+b'\nEXPLICIT OWNED TEST ALTERATION\n')
        with self.assertRaisesRegex(WorkflowError,'CLOCK_EVIDENCE_CHANGED'):frames.verify_clock(self.root,record['observation'])

    def test_nonzero_container_start_normalizes_actual_pts_without_claiming_the_seek_grid(self):
        source=self.root/'nonzero-start.mp4'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=10:d=2',
            '-c:v','libx264','-pix_fmt','yuv420p','-output_ts_offset','4',str(source)],check=True,capture_output=True,timeout=30)
        asset=ingest_media(self.config,source,'video/mp4','Offset local fixture',rights_confirmed=True,illustration=True)
        self.project=self.store.create('Nonzero-start decoded-clock fixture','','media');self.project=self.store.append_media(self.project['id'],1,asset)
        self.asset=asset;path=media_path(self.config,asset['id']);self.measure();value=frames.view(self.store,self.project['id'])['observations'][0]
        probe=json.loads(subprocess.check_output([str(self.config.ffmpeg_bin/'ffprobe.exe'),'-v','error','-show_frames','-show_format','-show_streams',
            '-select_streams','v:0','-show_entries','frame=pts:stream=time_base:format=start_time','-of','json',str(path)]))
        origin=float(probe['format']['start_time']);tb=Fraction(probe['streams'][0]['time_base']);self.assertGreaterEqual(origin,3.9)
        measured=[float(int(f['pts'])*tb)-origin for f in probe['frames']]
        self.assertEqual(value['frames'][0]['timestamp_seconds'],0.)
        for frame in value['frames']:self.assertTrue(any(abs(frame['timestamp_seconds']-v)<1e-9 for v in measured))

    def test_historical_v1_fixture_is_unchanged_and_cannot_claim_decoded_clock(self):
        path=Path(__file__).resolve().parents[3]/'apps/studio-web/tests/fixtures/native-official-vision-v1.json'
        data=json.loads(path.read_text(encoding='utf-8'))
        def find(value):
            if isinstance(value,dict):
                if 'source_observation' in value and 'asset' in value:return value
                for child in value.values():
                    found=find(child)
                    if found:return found
            elif isinstance(value,list):
                for child in value:
                    found=find(child)
                    if found:return found
        source=find(data);self.assertIsNotNone(source)
        record=source['source_observation'];before=copy.deepcopy(record);value=frames.validate(record,record['observation']['project_id'],source['asset'])
        self.assertEqual(record,before);self.assertEqual(value['schema'],frames.LEGACY_SCHEMA)
        self.assertTrue(all(f['decoded_pts_seconds'] is None for f in value['frames']))
        altered=copy.deepcopy(record);altered['observation']['decoded_clock_evidence']={'algorithm':'single-decode-threshold-sampling-v1'};altered['sha256']=digest(altered['observation'])
        with self.assertRaises(WorkflowError):frames.validate(altered,value['project_id'],source['asset'])

    def test_hardlinked_database_is_not_a_valid_measurement_authority(self):
        self.vfr();self.measure();observation=self.project['document']['media_frame_analyses'][0]['observation']
        alias=self.root/'untrusted-workflow-alias.sqlite3'
        os.link(self.store.db,alias)
        try:
            with self.assertRaisesRegex(WorkflowError,'CLOCK_EVIDENCE_CHANGED'):frames.verify_clock(self.root,observation)
        finally:alias.unlink()
