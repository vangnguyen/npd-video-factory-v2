"""Measured local quality tests; synthetic speech does not certify Owner listening."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import unicodedata
from unittest.mock import patch
import numpy as np
from services.windows_native.contracts import Proposal,WorkflowError,digest,file_sha
from services.windows_native.north_star_quality import (POLICY,policy_reference,resolve_policy,canonical_names,
    canonicalize_draft,validate_tts_names,validate_render_profile,evaluate_speech_placement,audio_activity)
from services.windows_native.pipeline import Config,Pipeline,render,qc
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.store import Store
from services.windows_native.tests.test_shot_production import prepared,voice


class NorthStarQualityTests(unittest.TestCase):
    def test_proper_names_unicode_aliases_idempotent_and_word_boundaries(self):
        text='Green Paradise Cần Giờ. Vinhomes Sài Gòn Park. Vang Nguyen.'
        expected='Vinhomes Green Paradise Cần Giờ. Vinhomes Saigon Park. Vang Nguyễn.'
        self.assertEqual(canonical_names(unicodedata.normalize('NFD',text)),expected)
        self.assertEqual(canonical_names(expected),expected)
        self.assertEqual(canonical_names('SuperGreen ParadiseX; Vang NguyenXYZ'),'SuperGreen ParadiseX; Vang NguyenXYZ')
        self.assertEqual(canonical_names('VINHOMES GREEN PARADISE CẦN GIỜ'),POLICY['proper_names'][0])

    def test_versioned_policy_does_not_migrate_legacy_and_cannot_drift(self):
        self.assertIsNone(resolve_policy({'prompt':'legacy'}))
        doc={'production_quality':policy_reference()}
        returned=resolve_policy(doc); returned['max_narration_tail_seconds']=99
        self.assertEqual(resolve_policy(doc)['max_narration_tail_seconds'],2)
        for bad in [None,{},dict(policy_reference(),version=2),dict(policy_reference(),sha256='0'*64)]:
            with self.subTest(bad=bad),self.assertRaisesRegex(WorkflowError,'POLICY_CHANGED'):
                resolve_policy({'production_quality':bad})

    def test_render_profile_hard_validation(self):
        self.assertEqual(validate_render_profile('vertical-short',1080,1920,'9:16')['id'],'vertical-short')
        for width,height,ratio in [(1920,1080,'16:9'),(720,1280,'9:16'),(1080.,1920,'9:16'),(1080,1920,'16:9')]:
            with self.subTest(width=width,height=height),self.assertRaisesRegex(WorkflowError,'CANVAS_MISMATCH'):
                validate_render_profile('vertical-short',width,height,ratio)
        for profile in [None,{},'unknown']:
            with self.assertRaisesRegex(WorkflowError,'PROFILE_UNKNOWN'):validate_render_profile(profile,1080,1920)

    def test_pcm_activity_measures_tail_without_claiming_speech(self):
        x=np.concatenate([np.ones(100)*.1,np.zeros(350)])
        analysis=audio_activity(x,100)
        self.assertAlmostEqual(analysis['trailing_silence_seconds'],3.5)
        self.assertFalse(analysis['speech_detected']);self.assertTrue(analysis['audio_activity_detected'])
        self.assertEqual(audio_activity(np.zeros(100),100)['trailing_silence_seconds'],1)
        for samples,rate,options in [([],100,{}),([float('nan')],100,{}),([[1]],100,{}),([1],True,{}),([1],100,{'window_seconds':float('nan')}),([1],100,{'threshold_db':1})]:
            with self.assertRaisesRegex(WorkflowError,'INPUT_INVALID'):audio_activity(samples,rate,**options)

    def test_music_activity_cannot_hide_narration_tail_or_gaps(self):
        placement={'last_narration_activity_end_seconds':3.,'between_unit_activity_gaps_seconds':[4.],
                   'timing_source':'measured_waveform_activity_not_word_alignment'}
        checks=evaluate_speech_placement(placement,30,POLICY)
        self.assertFalse(checks['no_narration_dead_air']);self.assertFalse(checks['no_excessive_speech_gaps'])
        self.assertFalse(checks['word_alignment_claimed'])
        for end in [None,True,float('inf'),31,-1]:
            with self.assertRaisesRegex(WorkflowError,'BINDING_INVALID'):
                evaluate_speech_placement(dict(placement,last_narration_activity_end_seconds=end),30,POLICY)

    def test_content_draft_normalizes_before_review_preserves_raw_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root)
            legacy=store.create('Legacy test','Vang Nguyen.',input_kind='script')
            self.assertNotIn('production_quality',legacy['document'])
            project=store.create('New quality test','Vang Nguyen.',input_kind='script',production_quality=True)
            self.assertEqual(project['document']['production_quality'],policy_reference())
            job=store.enqueue(project['id'],project['revision'],'content','quality-test-content')
            pipeline=Pipeline(Config(data_root=root))
            with patch('services.windows_native.pipeline.generate',side_effect=AssertionError('Paid AI forbidden')):
                result=pipeline.run(job,lambda _:None)
                self.assertEqual(pipeline.run(job,lambda _:None),result)
            out=root/'jobs'/job['id']
            raw=json.loads((out/'content-result.json').read_bytes())
            self.assertEqual(raw['proposal']['narration'],'Vang Nguyen.')
            self.assertEqual(result['proposal']['narration'],'Vang Nguyễn.')
            self.assertEqual(result['proper_name_normalization']['source_proposal_sha256'],digest(raw['proposal']))
            self.assertFalse(result['proper_name_normalization']['pronunciation_verified'])
            self.assertIsNone(store.get(project['id'])['approval'])
            self.assertEqual(store.get(project['id'])['document']['prompt'],'Vang Nguyen.')
            p=Proposal.model_validate(raw['proposal'])
            with self.assertRaisesRegex(WorkflowError,'PROPER_NAME_REVIEW_REQUIRED'):validate_tts_names(project['document'],p)
            validate_tts_names(legacy['document'],p)
            validate_tts_names(project['document'],Proposal.model_validate(result['proposal']))
            before=copy.deepcopy(raw['proposal']);canonicalize_draft(raw['proposal']);self.assertEqual(raw['proposal'],before)

    def test_approval_rejects_noncanonical_names_without_creating_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);_,store,legacy=prepared(root)
            project=store.create('Quality approval fixture','No providers',production_quality=True)
            proposal=copy.deepcopy(legacy['document']['proposal'])
            proposal['visual_brief'][0]['narration_excerpt']='Vang Nguyen.'
            proposal['narration']='Vang Nguyen. Cảm ơn.'
            project=store.save(project['id'],project['revision'],proposal=proposal,asset=legacy['document']['assets'][0])
            with self.assertRaisesRegex(WorkflowError,'PROPER_NAME_REVIEW_REQUIRED'):
                store.approve(project['id'],project['revision'],'AUTOMATED FIXTURE',True)
            self.assertIsNone(store.get(project['id'])['approval'])

    def test_fixed_requested_dead_air_fails_without_modifying_voice_or_rendering(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);config,_,project=prepared(root);out=root/'fixed';meta,_=voice(out)
            doc=copy.deepcopy(project['document']);doc['production_quality']=policy_reference()
            with patch('services.windows_native.pipeline.subprocess.run',side_effect=AssertionError('No FFmpeg render expected')):
                with self.assertRaisesRegex(WorkflowError,'DEAD_AIR_REVIEW_DURATION_REQUIRED'):
                    render(config,{'document':doc,'approval':{'snapshot_sha256':digest(doc)}},out)
            self.assertEqual(file_sha(out/'voice.wav'),meta['audio_sha256']);self.assertFalse((out/'final.mp4').exists())

    def test_actual_fit_narration_render_and_final_audio_tail_qc(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);config,store,project=prepared(root)
            project=store.set_brand(project['id'],project['revision'],'vang-nguyen','personal-30',duration_mode=FIT_NARRATION_POLICY)
            for shot in list(store.shot_view(project['id'])['shot_timeline']['shots']):
                project=store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'requested_duration':None}})
            doc=copy.deepcopy(project['document']);doc['production_quality']=policy_reference()
            out=root/'fit';meta,_=voice(out)
            report=render(config,{'document':doc,'approval':{'snapshot_sha256':digest(doc),'reviewer':'AUTOMATED SYNTHETIC FIXTURE ONLY'}},out)
            manifest=json.loads((out/'render-manifest.json').read_bytes())
            self.assertTrue(report['passed']);self.assertTrue(report['checks']['no_trailing_audio_silence'])
            self.assertTrue(manifest['speech_quality']['no_narration_dead_air'])
            self.assertLess(report['duration_seconds'],5);self.assertFalse(report['human_final_video_accepted'])
            self.assertEqual(file_sha(out/'voice.wav'),meta['audio_sha256'])
            padded=root/'padded';padded.mkdir()
            subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-y','-i',str(out/'final.mp4'),
                '-vf','tpad=stop_mode=clone:stop_duration=4','-af','apad=pad_dur=4','-c:v','libx264','-preset','ultrafast',
                '-c:a','aac',str(padded/'final.mp4')],check=True,timeout=60,capture_output=True)
            with self.assertRaisesRegex(WorkflowError,'MEDIA_QC_FAILED'):
                qc(config,padded,report['duration_seconds']+4,quality_policy=POLICY)
            failed=json.loads((padded/'qc-report.json').read_bytes())
            self.assertFalse(failed['checks']['no_trailing_audio_silence'])
            self.assertGreater(failed['decoded_audio_activity']['trailing_silence_seconds'],4)
            self.assertTrue(failed['checks']['full_decode']);self.assertTrue(failed['checks']['portrait_1080x1920'])


if __name__=='__main__':unittest.main()
