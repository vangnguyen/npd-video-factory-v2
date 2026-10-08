"""Actual FFmpeg/libass/PNG/MP4/PCM; synthetic local content is not Owner UAT."""
import copy,json,subprocess,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from services.windows_native.contracts import WorkflowError,digest,file_sha,write_json
from services.windows_native.pipeline import Pipeline,render,ass_time
from services.windows_native.storyboard_qc import subtitle_evidence,timeline_evidence
from services.windows_native.north_star_quality import policy_reference
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.hardening import Artifacts
from services.windows_native.tests.test_shot_production import prepared,voice


class StoryboardQCTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.config,self.store,self.project=prepared(self.root)
        self.project=self.store.set_brand(self.project['id'],self.project['revision'],'vang-nguyen','personal-30',duration_mode=FIT_NARRATION_POLICY)
        for shot in list(self.store.shot_view(self.project['id'])['shot_timeline']['shots']):
            self.project=self.store.mutate_shots(self.project['id'],self.project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'requested_duration':None}})
        self.document=copy.deepcopy(self.project['document']);self.document['production_quality']=policy_reference()
        self.snapshot={'document':self.document,'approval':{'snapshot_sha256':digest(self.document),'revision':self.project['revision'],'reviewer':'EXPLICIT SYNTHETIC FIXTURE ONLY'}}
    def tearDown(self):self.temp.cleanup()
    def output(self,name='render'):
        directory=self.root/name;voice(directory);return directory
    def mask(self,*,x=495,y=1435,start=.1,end=.9,text='Vang Nguyễn – Cần Giờ'):
        folder=self.root/'mask';folder.mkdir();source=folder/'subtitles.ass'
        template='''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,Segoe UI,46,&H00F1F9FC,&H00FFFFFF,&H00101D1B,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,80,80,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
        source.write_text(template+f'Dialogue: 0,{ass_time(start)},{ass_time(end)},Subtitle,,0,0,0,,{{\\pos({x},{y})}}{text}\n',encoding='utf-8')
        manifest={'captions':[{'start':start,'end':end,'text':text}],'subtitle_layout':{'schema_version':'native-ass-render-layout-v1','width':1080,'height':1920,
            'safe_rectangle':[90,160,900,1560],'ass_sha256':file_sha(source)}}
        return folder,manifest

    def test_actual_vietnamese_glyph_masks_prove_bounds_and_hash_scoped_evidence(self):
        folder,manifest=self.mask();report=subtitle_evidence(self.config,folder,manifest,1,1080,1920);self.assertEqual(report['status'],'passed')
        sample=report['samples'][0];self.assertTrue(sample['actual_libass_pixels']);self.assertTrue(sample['inside_safe_area']);self.assertEqual(sample['sha256'],file_sha(folder/sample['evidence_frame_reference']))
        self.assertGreater(sample['bounds'][2]-sample['bounds'][0],100);self.assertFalse(report['word_alignment_claimed']);self.assertIsNone(report['confidence']);self.assertEqual(report['external_provider_calls'],0)

    def test_actual_visible_pixels_outside_safe_area_fail(self):
        folder,manifest=self.mask(x=970);report=subtitle_evidence(self.config,folder,manifest,1,1080,1920)
        self.assertEqual(report['status'],'failed');self.assertFalse(report['samples'][0]['inside_safe_area']);self.assertTrue(report['failures'])

    def test_caption_without_an_output_frame_is_not_asserted_visible(self):
        folder,manifest=self.mask(start=.01,end=.02);report=subtitle_evidence(self.config,folder,manifest,1,1080,1920)
        self.assertEqual(report['status'],'failed');self.assertEqual(report['sample_count'],0);self.assertEqual(report['failures'][0]['reason'],'caption_has_no_visible_output_frame')

    def test_actual_ass_digest_dialogue_coverage_and_quantized_time_must_match(self):
        folder,manifest=self.mask();manifest['captions'][0]['end']=.8
        with self.assertRaisesRegex(WorkflowError,'SUBTITLE_BINDING_INVALID'):subtitle_evidence(self.config,folder,manifest,1,1080,1920)
        manifest['subtitle_layout']['ass_sha256']='0'*64
        with self.assertRaisesRegex(WorkflowError,'SUBTITLE_BINDING_INVALID'):subtitle_evidence(self.config,folder,manifest,1,1080,1920)

    def test_full_quality_render_keeps_pcm_and_records_measured_freeze_pixels_decode_audio_and_source_bindings(self):
        out=self.output();raw_sha=file_sha(out/'voice.wav');report=render(self.config,self.snapshot,out);full=report['full_quality'];detail=full['full_production_qc']
        self.assertTrue(report['passed']);self.assertTrue(report['checks']['full_production_qc']);self.assertEqual(full['status'],'passed')
        self.assertEqual(detail['measured_audio_loudness']['measurement_state'],'measured')
        self.assertEqual(detail['measured_audio_loudness']['input_sha256'],file_sha(out/'final.mp4'))
        self.assertFalse(detail['measured_audio_loudness']['voice_music_balance_accepted'])
        self.assertGreater(detail['freeze_frame_ratio'],.5);self.assertGreater(detail['intentional_still_seconds'],0);self.assertLessEqual(detail['unexplained_freeze_ratio'],.15)
        self.assertEqual(detail['broken_frames'],0);self.assertEqual(detail['sampled_vision_qc']['provider'],'ffmpeg-signalstats');self.assertFalse(full['semantic_vision_used'])
        self.assertEqual(full['final_sha256'],file_sha(out/'final.mp4'));self.assertEqual(full['document_sha256'],digest(self.document));self.assertEqual(file_sha(out/'voice.wav'),raw_sha)
        self.assertEqual(full['subtitle_bounds']['sample_count'],2);self.assertFalse(full['human_final_video_accepted']);self.assertFalse(full['published']);self.assertFalse(full['rights_independently_verified'])
        self.assertTrue((out/'transport-qc-report.json').is_file());self.assertTrue((out/'full-qc-report.json').is_file())

    def test_real_frozen_video_is_not_exempted_as_an_image_hold(self):
        path=self.root/'assets'/(uuid.uuid4().hex+'.mp4')
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','error','-f','lavfi','-i','color=c=0x346278:s=640x360:r=30:d=3.3',
            '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],capture_output=True,check=True,timeout=20)
        asset={'id':path.name,'kind':'video','filename':'EXPLICIT STATIC VIDEO FIXTURE.mp4','sha256':file_sha(path),'rights_confirmed':True,'illustration':False,'duration_seconds':3.3}
        current=self.store.append_media(self.project['id'],self.project['revision'],asset);shot=self.store.shot_view(current['id'])['shot_timeline']['shots'][0]
        current=self.store.mutate_shots(current['id'],current['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'asset_id':asset['id'],'motion':'none'}})
        doc=copy.deepcopy(current['document']);doc['production_quality']=policy_reference();snapshot={'document':doc,'approval':{'snapshot_sha256':digest(doc),'revision':current['revision'],'reviewer':'EXPLICIT FROZEN VIDEO FIXTURE'}}
        out=self.output()
        with self.assertRaisesRegex(WorkflowError,'STORYBOARD_FULL_MEDIA_QC_FAILED'):render(self.config,snapshot,out)
        report=json.loads((out/'qc-report.json').read_bytes());self.assertFalse(report['passed']);self.assertEqual(report['full_quality']['status'],'failed_qc')
        self.assertIn('freeze-frame ratio exceeds 15 percent',report['full_quality']['full_production_qc']['failures'])
        self.assertTrue(json.loads((out/'transport-qc-report.json').read_bytes())['passed'])
        self.assertTrue(all(interval['asset_id']!=asset['id'] for interval in report['full_quality']['timeline']['intentional_still_intervals']))

    def test_layout_gaps_frame_counts_and_changed_source_hashes_cannot_claim_renderability(self):
        out=self.output();render(self.config,self.snapshot,out);manifest=json.loads((out/'render-manifest.json').read_bytes())
        for mutate in [lambda v:v['scenes'][0].update(frames=1),lambda v:v['scenes'][0].update(start=.1),lambda v:v['scenes'][0].update(source_sha256='0'*64)]:
            changed=copy.deepcopy(manifest);mutate(changed)
            with self.assertRaisesRegex(WorkflowError,'SCENE_LAYOUT_INVALID'):timeline_evidence(self.config,self.document,changed,manifest['duration_seconds'])

    def test_worker_checkpoint_publishes_masks_and_rejects_tampered_evidence_without_resynthesis(self):
        job={'id':uuid.uuid4().hex,'project_id':self.project['id'],'revision':self.project['revision'],'kind':'render','snapshot':self.snapshot}
        out=self.root/'jobs'/job['id'];out.parent.mkdir(exist_ok=True);voice(out);write_json(out/'tts-plan.json',{'explicit_fixture':True});artifacts=Artifacts(out,job)
        artifacts.commit('tts',[out/'voice.wav',out/'voice.json',out/'tts-plan.json'],{'explicit_cached_pcm_fixture':True})
        with patch('services.windows_native.pipeline.verify_runtime'),patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No synthesis allowed')):
            result=Pipeline(self.config).run(job,lambda _:None);self.assertTrue(result['qc']['full_quality']['status']=='passed')
            self.assertEqual(Pipeline(self.config).run(job,lambda _:None),result)
            checkpoint=artifacts.load('render');names={item['path'] for item in checkpoint['artifacts']};self.assertIn('full-qc-report.json',names);self.assertIn('subtitle-qc/000.png',names)
            (out/'subtitle-qc/000.png').write_bytes(b'EXPLICIT EVIDENCE CORRUPTION FIXTURE')
            with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):Pipeline(self.config).run(job,lambda _:None)

    def test_legacy_render_report_does_not_claim_unperformed_full_quality(self):
        doc=copy.deepcopy(self.document);doc.pop('production_quality');out=self.output()
        report=render(self.config,{'document':doc,'approval':{'snapshot_sha256':digest(doc),'reviewer':'EXPLICIT LEGACY FIXTURE'}},out)
        self.assertTrue(report['passed']);self.assertNotIn('full_quality',report);self.assertFalse((out/'full-qc-report.json').exists())

    def test_measurement_failure_cannot_admit_storyboard_quality_success(self):
        out=self.output()
        with patch('services.windows_native.audio_loudness.measure',side_effect=WorkflowError('NATIVE_AUDIO_LOUDNESS_SCAN_FAILED')):
            with self.assertRaisesRegex(WorkflowError,'STORYBOARD_FULL_MEDIA_QC_FAILED'):render(self.config,self.snapshot,out)
        report=json.loads((out/'qc-report.json').read_bytes());self.assertFalse(report['passed'])
        self.assertEqual(report['full_quality']['failure_code'],'NATIVE_AUDIO_LOUDNESS_SCAN_FAILED')

    def test_storyboard_quality_failure_has_the_same_failed_qc_job_state_as_source_mode(self):
        self.store.approve(self.project['id'],self.project['revision'],'EXPLICIT STATE FIXTURE',True)
        queued=self.store.enqueue(self.project['id'],self.project['revision'],'render','explicit-full-qc-state-fixture')
        job=self.store.claim();self.assertEqual(job['id'],queued['id'])
        self.store.finish(job,error={'code':'STORYBOARD_FULL_MEDIA_QC_FAILED','automatic_retry':False})
        with self.store.transaction() as con:row=con.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone();result=self.store.job(row,con)
        self.assertEqual(result['status'],'failed_qc');self.assertIsNone(result['result'])
