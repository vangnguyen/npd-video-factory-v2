"""Explicit pacing choices with synthetic PCM; never provider or Owner acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np
from services.windows_native import branding
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.pipeline import render
from services.windows_native.shot_render_timing import retime_voice, voice_placement_diagnostics
from services.windows_native.tests.test_shot_production import prepared, voice


class VoiceDurationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.cfg,self.store,self.project=prepared(self.root)

    def tearDown(self): self.temp.cleanup()

    def automatic_shots(self):
        project=self.project
        for shot in project['shot_timeline']['shots']:
            project=self.store.mutate_shots(project['id'],project['revision'],{
                'type':'update','shot_id':shot['shot_id'],'values':{'requested_duration':None}})
        return project

    def test_omitted_mode_preserves_frozen_selection_hash_and_explicit_fixed_choice(self):
        original=branding.choose('ngoc-phuong-dong','property-45')
        self.assertEqual(digest(original),'10776dc7dfdc0bae092f3cf4c2ffb2edd6860db431a37b3d8b9fc2f374a5f46b')
        self.assertEqual(original,branding.choose('ngoc-phuong-dong','property-45',branding.FIXED_DURATION_POLICY))
        fit=branding.choose('ngoc-phuong-dong','property-45',branding.FIT_NARRATION_POLICY)
        self.assertEqual(original['brand'],fit['brand'])
        self.assertNotEqual(original['template_sha256'],fit['template_sha256'])
        self.assertEqual(branding.resolve({'brand_template':fit})[1].duration_policy,branding.FIT_NARRATION_POLICY)
        changed=copy.deepcopy(fit); changed['template']['duration_policy']=branding.FIXED_DURATION_POLICY
        with self.assertRaisesRegex(WorkflowError,'SNAPSHOT_CHANGED'): branding.resolve({'brand_template':changed})
        for invalid in ('automatic',True,{}):
            with self.subTest(invalid=invalid),self.assertRaisesRegex(WorkflowError,'MODE_INVALID'):
                branding.choose('ngoc-phuong-dong','property-45',invalid)

    def test_fit_uses_measured_voice_and_bounded_intro_outro_without_nominal_target_cap(self):
        fixed={'brand_template':branding.choose('ngoc-phuong-dong','property-30')}
        fit={'brand_template':branding.choose('ngoc-phuong-dong','property-30',branding.FIT_NARRATION_POLICY)}
        self.assertEqual(branding.measured_duration(fixed,20.86),30.)
        self.assertAlmostEqual(branding.measured_duration(fit,20.86),22.96)
        self.assertAlmostEqual(branding.measured_duration(fit,50),52.1)
        with self.assertRaisesRegex(WorkflowError,'NARRATION_TOO_LONG'): branding.measured_duration(fixed,50)
        with self.assertRaisesRegex(WorkflowError,'EXCEEDS_180'): branding.measured_duration(fit,179)
        for bad in (float('nan'),float('inf'),-1):
            with self.subTest(bad=bad),self.assertRaisesRegex(WorkflowError,'DURATION_INVALID'):
                branding.measured_duration(fit,bad)

    def test_fit_keeps_every_source_sample_and_measured_caption_times_without_long_tail(self):
        project=self.automatic_shots(); out=self.root/'fit'; meta,samples=voice(out)
        doc=project['document']; before=digest(doc); original=file_sha(out/'voice.wav')
        brand,template=branding.resolve({'brand_template':branding.choose('vang-nguyen','personal-45',branding.FIT_NARRATION_POLICY)})
        result=retime_voice(doc,meta,out,brand,template)
        self.assertAlmostEqual(result['duration_seconds'],3.3)
        self.assertAlmostEqual(result['units'][0]['activity_start_seconds'],1.11)
        self.assertAlmostEqual(result['units'][-1]['activity_end_seconds'],2.29)
        with wave.open(str(out/'render-voice.wav'),'rb') as wav:
            actual=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
        self.assertTrue(np.array_equal(actual[52800:110400],samples))
        self.assertFalse(actual[:52800].any()); self.assertFalse(actual[110400:].any())
        self.assertEqual(file_sha(out/'voice.wav'),original); self.assertEqual(digest(doc),before)
        self.assertEqual((result['speed'],result['pitch_changed']),(1,False))
        self.assertAlmostEqual(result['voice_placement']['tail_after_source_voice_seconds'],1.)
        self.assertAlmostEqual(result['voice_placement']['tail_after_narration_activity_seconds'],1.01)
        self.assertEqual(json.loads((out/'render-voice.json').read_bytes()),result)

    def test_fixed_template_keeps_identical_pcm_placement_and_reports_real_hold(self):
        doc=self.automatic_shots()['document']; out=self.root/'fixed'; meta,samples=voice(out)
        brand,template=branding.resolve({'brand_template':branding.choose('vang-nguyen','personal-45')})
        result=retime_voice(doc,meta,out,brand,template)
        self.assertEqual(result['duration_seconds'],45)
        self.assertAlmostEqual(result['voice_placement']['tail_after_source_voice_seconds'],42.7)
        self.assertAlmostEqual(result['voice_placement']['last_narration_activity_end_seconds'],2.29)
        with wave.open(str(out/'render-voice.wav'),'rb') as wav:
            actual=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
        self.assertTrue(np.array_equal(actual[52800:110400],samples)); self.assertFalse(actual[110400:].any())

    def test_fit_honors_explicit_slots_including_last_and_refuses_clipped_narration(self):
        out=self.root/'requested'; meta,samples=voice(out)
        brand,template=branding.resolve({'brand_template':branding.choose('vang-nguyen','personal-45',branding.FIT_NARRATION_POLICY)})
        result=retime_voice(self.project['document'],meta,out,brand,template)
        self.assertEqual(result['duration_seconds'],8)
        self.assertEqual([r['end']-r['start'] for r in result['scene_layout']],[4,4])
        self.assertAlmostEqual(result['voice_placement']['between_unit_activity_gaps_seconds'][0],2.32)
        with wave.open(str(out/'render-voice.wav'),'rb') as wav:
            actual=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
        self.assertTrue(np.array_equal(actual[52800:81600],samples[:28800]))
        self.assertTrue(np.array_equal(actual[192000:220800],samples[28800:]))
        short=self.store.mutate_shots(self.project['id'],self.project['revision'],{
            'type':'update','shot_id':self.project['shot_timeline']['shots'][0]['shot_id'],'values':{'duration':.5}})
        with self.assertRaisesRegex(WorkflowError,'NARRATION_OVERFLOW'):
            retime_voice(short['document'],meta,out,brand,template)

    def test_legacy_activity_diagnostics_account_for_intro_without_claiming_word_alignment(self):
        out=self.root/'legacy'; meta,_=voice(out)
        value=voice_placement_diagnostics(meta,25,intro=1.1)
        self.assertAlmostEqual(value['source_voice_end_seconds'],2.3)
        self.assertAlmostEqual(value['last_narration_activity_end_seconds'],2.29)
        self.assertAlmostEqual(value['tail_after_source_voice_seconds'],22.7)
        self.assertAlmostEqual(value['between_unit_activity_gaps_seconds'][0],.02)
        self.assertEqual(value['timing_source'],'measured_waveform_activity_not_word_alignment')

    def test_actual_synthetic_portrait_export_fits_voice_and_reports_final_scene_hold(self):
        project=self.automatic_shots()
        project=self.store.set_brand(project['id'],project['revision'],'vang-nguyen','personal-45',
                                     duration_mode=branding.FIT_NARRATION_POLICY)
        out=self.root/'synthetic-fit-export'; meta,_=voice(out)
        report=render(self.cfg,{'document':project['document'],'approval':{
            'snapshot_sha256':digest(project['document']),'reviewer':'AUTOMATED SYNTHETIC FIXTURE ONLY'}},out)
        self.assertTrue(report['passed']); self.assertAlmostEqual(report['duration_seconds'],3.3,places=1)
        self.assertFalse(report['human_final_video_accepted'])
        manifest=json.loads((out/'render-manifest.json').read_bytes())
        self.assertEqual(manifest['duration_policy'],branding.FIT_NARRATION_POLICY)
        self.assertAlmostEqual(manifest['cta_hold_after_voice_seconds'],1.)
        self.assertAlmostEqual(manifest['voice_placement']['last_narration_activity_end_seconds'],2.29)
        self.assertAlmostEqual(manifest['scenes'][-1]['end'],3.3)
        self.assertEqual(manifest['source_voice_sha256'],meta['audio_sha256'])
        timeline=json.loads((out/'timeline.json').read_bytes())
        self.assertAlmostEqual(timeline['duration_seconds'],3.3)
        captions=[clip for track in timeline['tracks'] if track['track_id']=='trk_native_captions' for clip in track['clips']]
        self.assertTrue(all(clip['timeline_start']+clip['duration']<=2.29+.001 for clip in captions))


if __name__=='__main__': unittest.main()
