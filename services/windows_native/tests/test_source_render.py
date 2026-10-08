"""Temporary synthetic media/ASR + mock human review; no Owner/provider acceptance."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch

from services.windows_native import auto_edit_timeline as timeline
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner
from services.windows_native.shot_preview import PreviewManager
from services.windows_native import source_render
from services.windows_native.tests import test_source_preview as preview_fixture
from app.production_qc import ProductionQCError


class NativeSourceRenderTests(unittest.TestCase):
    setUp=preview_fixture.NativeSourcePreviewTests.setUp
    tearDown=preview_fixture.NativeSourcePreviewTests.tearDown
    save_analysis=preview_fixture.NativeSourcePreviewTests.save_analysis
    real_source=preview_fixture.NativeSourcePreviewTests.real_source
    wait=preview_fixture.NativeSourcePreviewTests.wait

    def review_fixture(self):
        self.real_source()
        manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
        finally:manager.close()
        self.project=self.store.approve(self.project['id'],self.project['revision'],
            'AUTOMATED SYNTHETIC REVIEW FIXTURE — NOT OWNER UAT',True)
        self.assertEqual(self.project['approval']['render_mode'],'source_footage')
        self.assertEqual(self.project['approval']['reviewed_preview']['sha256'],value['sha256'])
        return value

    def test_approval_requires_actual_current_proxy_and_enforces_binding_again_at_enqueue(self):
        self.real_source()
        with self.assertRaisesRegex(WorkflowError,'HUMAN_REVIEW_REQUIRED'):
            self.store.approve(self.project['id'],self.project['revision'],'Explicit fixture',False)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_CURRENT_PREVIEW_REVIEW_REQUIRED'):
            self.store.approve(self.project['id'],self.project['revision'],'Explicit fixture',True)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_HUMAN_APPROVAL_REQUIRED_BEFORE_RENDER'):
            self.store.enqueue(self.project['id'],self.project['revision'],'render',uuid.uuid4().hex)
        self.assertIsNone(self.store.get(self.project['id'])['approval'])
        manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.project=self.store.approve(self.project['id'],self.project['revision'],'SYNTHETIC REVIEW FIXTURE',True)
            jobs_before=self.store.get(self.project['id'])['jobs']
            folder=manager.video_path(self.project['id'],value['timeline_version']).parent
            (folder/'preview.mp4').write_bytes(b'explicit isolated corrupt preview')
            with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_CURRENT_PREVIEW_REVIEW_REQUIRED'):
                self.store.enqueue(self.project['id'],self.project['revision'],'render',uuid.uuid4().hex)
            self.assertEqual(self.store.get(self.project['id'])['jobs'],jobs_before)
        finally:manager.close()

    def test_real_source_worker_qc_checkpoint_keeps_media_immutable_and_requires_final_review(self):
        self.review_fixture();source=self.root/'assets'/self.asset['id'];original=file_sha(source)
        before=copy.deepcopy(self.project['document']);calls=[];original_command=source_render.command_run
        def local(command,*args,**kwargs):
            calls.append(command);return original_command(command,*args,**kwargs)
        job=self.store.enqueue(self.project['id'],self.project['revision'],'render',uuid.uuid4().hex)
        with patch.object(source_render,'command_run',side_effect=local),patch(
                'services.windows_native.pipeline.verify_runtime',side_effect=AssertionError('No locked TTS runtime dispatch')):
            self.assertTrue(Runner(self.store,Pipeline(self.config)).run_one())
        result=self.store.get_job(job['id'])
        self.assertEqual(result['status'],'succeeded',result['error'])
        self.assertTrue(result['result']['qc']['passed']);self.assertFalse(result['result']['qc']['human_final_video_accepted'])
        measured=result['result']['qc']['measured_audio_loudness']
        self.assertEqual(measured['measurement_state'],'measured');self.assertLess(measured['integrated_lufs'],0)
        self.assertFalse(measured['normalization_target_achieved_claimed']);self.assertFalse(measured['speech_detection_performed'])
        self.assertEqual(result['result']['tts_calls'],0);self.assertEqual(result['result']['provider_calls'],0)
        self.assertFalse(any('tts_child' in str(argument) for command in calls for argument in command))
        self.assertEqual(self.store.get(self.project['id'])['document'],before);self.assertEqual(file_sha(source),original)
        with self.assertRaisesRegex(WorkflowError,'HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED'):self.store.final_video(job['id'])
        with self.assertRaisesRegex(WorkflowError,'HUMAN_FINAL_WATCH_LISTEN_REVIEW_REQUIRED'):
            self.store.review_render(job['id'],job['revision'],'Explicit mock reviewer',False,'approve')
        self.store.review_render(job['id'],job['revision'],'EXPLICIT MOCK FINAL REVIEW — NOT OWNER UAT',True,'approve')
        self.assertEqual(self.store.final_video(job['id'])['id'],job['id'])
        with patch.object(source_render,'command_run',side_effect=AssertionError('No replay for valid checkpoint')):
            cached=Pipeline(self.config).run(result,lambda value:None)
        self.assertEqual(cached,result['result'])
        folder=self.root/'jobs'/job['id']
        self.assertTrue((folder/'checkpoint-render.json').is_file())
        self.assertTrue((folder/'subtitles.json').is_file());self.assertTrue((folder/'cost.json').is_file())
        manifest=json.loads((folder/'render-manifest.json').read_bytes())
        self.assertEqual(manifest['canonical_timeline'],before['canonical_timeline'])
        self.assertFalse(manifest['publishing_allowed'])
        (folder/'final.mp4').write_bytes(b'explicit isolated damaged final')
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):
            Pipeline(self.config).run(result,lambda value:None)
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):
            self.store.final_video(job['id'])

    def test_qc_failure_is_failed_qc_and_never_publishes_ready_output(self):
        self.review_fixture()
        job=self.store.enqueue(self.project['id'],self.project['revision'],'render',uuid.uuid4().hex)
        async def reject(*args,**kwargs):raise ProductionQCError('Explicit QC fixture',{'status':'failed','failures':['synthetic QC rejection']})
        with patch.object(source_render.FullProductionQC,'inspect',side_effect=reject):
            Runner(self.store,Pipeline(self.config)).run_one()
        finished=self.store.get_job(job['id']);self.assertEqual(finished['status'],'failed_qc',finished['error'])
        self.assertEqual(finished['lifecycle'],'FAILED_QC');self.assertIsNone(finished['result'])
        folder=self.root/'jobs'/job['id'];self.assertFalse((folder/'final.mp4').exists())
        self.assertFalse((folder/'checkpoint-render.json').exists())
        self.assertTrue(list((folder/'attempts').glob('*/qc-report.json')))
        with self.assertRaises(WorkflowError):self.store.final_video(job['id'])

    def test_edit_invalidates_source_approval_and_stale_approval_cannot_reach_render_tools(self):
        self.review_fixture();prior=copy.deepcopy(self.project)
        track=self.project['document']['canonical_timeline']['snapshot']['tracks'][0]
        changed=timeline.edit(self.store,self.project['id'],self.project['revision'],{
            'expected_version':1,'operations':[{'type':'set_track_state','track_id':track['track_id'],'locked':True}]})
        self.assertIsNone(changed['approval'])
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_HUMAN_APPROVAL_REQUIRED_BEFORE_RENDER'):
            self.store.enqueue(changed['id'],changed['revision'],'render',uuid.uuid4().hex)
        fake={'id':uuid.uuid4().hex,'kind':'render','project_id':changed['id'],'revision':changed['revision'],
            'snapshot':{'document':changed['document'],'approval':prior['approval']}}
        with patch.object(source_render,'command_run',side_effect=AssertionError('No media tools before human boundary')):
            with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_HUMAN_APPROVAL_REQUIRED_BEFORE_RENDER'):
                Pipeline(self.config).run(fake,lambda value:None)

    def test_loudness_failure_is_failed_qc_with_report_and_no_ready_final(self):
        self.review_fixture();job=self.store.enqueue(self.project['id'],self.project['revision'],'render',uuid.uuid4().hex)
        with patch('services.windows_native.audio_loudness.measure',side_effect=WorkflowError('NATIVE_AUDIO_LOUDNESS_SCAN_FAILED')):
            Runner(self.store,Pipeline(self.config)).run_one()
        finished=self.store.get_job(job['id']);self.assertEqual(finished['status'],'failed_qc',finished['error'])
        folder=self.root/'jobs'/job['id'];self.assertIsNone(finished['result']);self.assertFalse((folder/'final.mp4').exists())
        reports=list((folder/'attempts').glob('*/qc-report.json'));self.assertTrue(reports)
        self.assertEqual(json.loads(reports[0].read_bytes())['failures'],['NATIVE_AUDIO_LOUDNESS_SCAN_FAILED'])


if __name__=='__main__':unittest.main()
