"""Canonical FPS/quality settings, actual local render, no paid/TTS dispatch."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch
from services.windows_native.tests import test_manual_delivery as fixture
from services.windows_native.source_settings import configure
from services.windows_native.export_encoder import selection
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner
from services.windows_native.manual_delivery import DeliveryCreate


class ExportEncoderTests(unittest.TestCase):
    setUpClass=classmethod(fixture.ManualDeliveryTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.ManualDeliveryTests.tearDownClass.__func__)
    setUp=fixture.ManualDeliveryTests.setUp
    tearDown=fixture.ManualDeliveryTests.tearDown

    def apply(self,**options):
        state=self.store.get(self.project['id'])
        return configure(self.store,state['id'],state['revision'],{'expected_version':state['document']['canonical_timeline']['version'],**options})

    def test_invalid_fps_or_preset_preserves_project_and_approval(self):
        original=self.store.get(self.project['id'])
        for changes in [{'fps':True},{'fps':29},{'fps':120},{'fps':30.0},{'quality_preset':'arbitrary'}]:
            with self.subTest(changes=changes),self.assertRaisesRegex(WorkflowError,'REQUEST_INVALID'):self.apply(**changes)
        self.assertEqual(self.store.get(self.project['id']),original)

    def test_canonical_setting_invalidates_approval_keeps_source_and_clips_and_history(self):
        original=self.store.get(self.project['id']);before=original['document']['canonical_timeline']
        changed=self.apply(fps=25,quality_preset='small');after=changed['document']['canonical_timeline']
        self.assertIsNone(changed['approval']);self.assertGreater(after['version'],before['version'])
        self.assertEqual(after['snapshot']['tracks'],before['snapshot']['tracks']);self.assertEqual(after['snapshot']['fps'],25)
        self.assertEqual(selection(changed['document'])['crf'],27)
        self.assertEqual(file_sha(self.root/'jobs'/self.job_id/'final.mp4'),self.video_hash)
        with self.assertRaisesRegex(WorkflowError,'APPROVAL|PREVIEW'):self.store.enqueue(changed['id'],changed['revision'],'render',uuid.uuid4().hex)

    def test_malformed_saved_encoder_metadata_is_not_executable(self):
        self.assertIsNone(selection(self.project['document']))
        for raw in [{'schema_version':'native-export-encoder.v1','quality_preset':'high','crf':0},{'schema_version':'bad','quality_preset':'high'}]:
            doc=copy.deepcopy(self.project['document']);doc['canonical_timeline']['snapshot']['metadata']['native_export_encoder']=raw
            with self.assertRaisesRegex(WorkflowError,'ENCODER_OPTIONS_INVALID'):selection(doc)

    def test_actual_24fps_high_quality_preview_approval_render_and_full_qc(self):
        changed=self.apply(fps=24,quality_preset='high');manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(changed['id'],changed['revision'])
            preview=fixture.fixture.NativeSourceRenderTests.wait(self,manager)
            self.assertEqual(preview['status'],'READY',preview)
        finally:manager.close()
        approved=self.store.approve(changed['id'],changed['revision'],'AUTOMATED ENCODER PREVIEW FIXTURE — NOT OWNER UAT',True)
        job=self.store.enqueue(approved['id'],approved['revision'],'render',uuid.uuid4().hex)
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No TTS for footage export settings')):
            self.assertTrue(Runner(self.store,Pipeline(self.config)).run_one())
        done=self.store.get_job(job['id']);self.assertEqual(done['status'],'succeeded',done.get('error'))
        self.assertEqual(done['result']['qc']['fps'],24);self.assertTrue(done['result']['qc']['square_pixels_verified'])
        directory=self.root/'jobs'/job['id'];options=json.loads((directory/'native-export-options.json').read_bytes())
        self.assertEqual(options['crf'],18);self.assertEqual(options['quality_preset'],'high')
        self.assertEqual(file_sha(self.root/'jobs'/self.job_id/'final.mp4'),self.video_hash)

    def test_explicit_silent_nonburned_variant_keeps_separate_srt_and_original_tracks(self):
        tracks=copy.deepcopy(self.project['document']['canonical_timeline']['snapshot']['tracks'])
        changed=self.apply(fps=25,quality_preset='small',burn_subtitles=False,audio_included=False,preview_mode='final_effects')
        self.assertEqual(changed['document']['canonical_timeline']['snapshot']['tracks'],tracks)
        manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(changed['id'],changed['revision']);preview=fixture.fixture.NativeSourceRenderTests.wait(self,manager)
            self.assertEqual(preview['status'],'READY',preview)
        finally:manager.close()
        approved=self.store.approve(changed['id'],changed['revision'],'AUTOMATED SILENT EXPORT PREVIEW FIXTURE — NOT OWNER UAT',True)
        job=self.store.enqueue(approved['id'],approved['revision'],'render',uuid.uuid4().hex)
        self.assertTrue(Runner(self.store,Pipeline(self.config)).run_one());done=self.store.get_job(job['id'])
        self.assertEqual(done['status'],'succeeded',done.get('error'));self.assertTrue(done['result']['qc']['intentional_audio_silence'])
        peak=done['result']['qc']['audio_peak_db'];self.assertTrue(peak is None or peak<-80,peak)
        self.assertEqual(done['result']['qc']['fps'],25)
        directory=self.root/'jobs'/job['id'];captions=json.loads((directory/'subtitles.json').read_bytes())
        self.assertFalse(captions['burned_in']);self.assertGreater(len(captions['cues']),0)
        self.store.review_render(job['id'],approved['revision'],'AUTOMATED SILENT FINAL FIXTURE — NOT OWNER UAT',True,'approve')
        export=self.service.create(approved['id'],DeliveryCreate(revision=approved['revision'],render_job_id=job['id'],expected_video_sha256=done['result']['qc']['final_sha256'],
            cover=False,separate_subtitle=True,request_key='explicit-silent-separate-srt-key'))
        self.assertIn('subtitle.srt',export['files']);self.assertEqual(file_sha(self.root/'jobs'/self.job_id/'final.mp4'),self.video_hash)
