"""Actual narrated FFmpeg previews from explicitly cached synthetic PCM."""
import copy,json,threading,time,unittest,uuid
from services.windows_native.tests import test_narration as fixture
from services.windows_native.narration import apply
from services.windows_native.narration_preview import PROFILE,snapshot,validate_context,reviewed,folder_for,render
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.contracts import WorkflowError,file_sha

class NarrationPreviewTests(unittest.TestCase):
    setUp=fixture.NarrationTests.setUp;tearDown=fixture.NarrationTests.tearDown
    start=fixture.NarrationTests.start;finish=fixture.NarrationTests.finish;body=fixture.NarrationTests.body
    def fitted(self):
        source,out,result=self.finish();project=apply(self.store,self.project['id'],source['id'],self.body(result));return project,source,out
    def generate(self,project):
        manager=PreviewManager(self.config,self.store);manager.generate(project['id'],project['revision']);deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            value=manager.status(project['id'])
            if value['status'] not in {'QUEUED','RUNNING'}:return manager,value
            time.sleep(.05)
        manager.close();self.fail('Actual narrated preview deadline')

    def test_preview_authorization_requires_approved_source_pcm_but_grants_no_final_or_inference_authority(self):
        project,source,out=self.fitted();value=snapshot(self.store,project);self.assertIsNone(value['approval']);context=validate_context(self.config,value)
        self.assertEqual(context['source_narration_job_id'],source['id']);self.assertFalse(context['final_render_authorized']);self.assertFalse(context['new_inference_authorized'])
        changed=copy.deepcopy(value);changed['preview_authorization']['final_render_authorized']=True
        with self.assertRaises(WorkflowError):validate_context(self.config,changed)
        with self.assertRaisesRegex(WorkflowError,'HUMAN_APPROVAL_REQUIRED'):self.store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex)

    def test_actual_manager_generates_audible_full_effects_media_and_full_qc_without_inference_or_approval(self):
        project,source,out=self.fitted();raw=file_sha(out/'voice.wav');manager,value=self.generate(project)
        try:
            self.assertEqual(value['status'],'READY',value);self.assertEqual(value['preview_profile'],PROFILE);self.assertTrue(value['final_approval_eligible'])
            self.assertEqual(value['audio_mode'],'measured_scene_narration_full_effects_preview');manifest=value['manifest'];self.assertTrue(manifest['qc']['passed'])
            self.assertEqual(manifest['qc']['full_quality']['render_purpose'],'narration_preview');self.assertEqual(manifest['qc']['full_quality']['subtitle_bounds']['sample_count'],2)
            self.assertAlmostEqual(manifest['qc']['duration_seconds'],3.3,places=1);self.assertEqual(manifest['source_voice_sha256'],raw);self.assertEqual(manifest['new_inference_calls'],0)
            binding=reviewed(self.store,self.config,self.store.get(project['id']));self.assertEqual(binding['sha256'],file_sha(manager.video_path(project['id'],value['timeline_version'])))
            self.assertIsNone(self.store.get(project['id'])['approval']);self.assertEqual(file_sha(out/'voice.wav'),raw);self.assertEqual(len(self.store.get(project['id'])['jobs']),1)
            self.assertEqual(manager.generate(project['id'],project['revision']),manager.status(project['id']))
        finally:manager.close()

    def test_changed_subtitle_pixel_evidence_blocks_preview_review_and_serving(self):
        project,_,_=self.fitted();manager,value=self.generate(project)
        try:
            self.assertEqual(value['status'],'READY',value);folder=folder_for(self.config,project);mask=next(item for item in value['manifest']['artifacts'] if item['path'].startswith('subtitle-qc/'))
            (folder/mask['path']).write_bytes(b'EXPLICIT PIXEL EVIDENCE CORRUPTION')
            with self.assertRaisesRegex(WorkflowError,'CURRENT_AUDIBLE_PREVIEW'):reviewed(self.store,self.config,self.store.get(project['id']))
            with self.assertRaises(WorkflowError):manager.video_path(project['id'],value['timeline_version'])
        finally:manager.close()

    def test_changed_canonical_edit_stales_preview_without_changing_original_audio(self):
        project,_,out=self.fitted();manager,value=self.generate(project)
        try:
            self.assertEqual(value['status'],'READY',value);raw=file_sha(out/'voice.wav');shot=project['shot_timeline']['shots'][0]
            changed=self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'on_screen_text':'Changed visual review'}})
            self.assertEqual(manager.status(project['id'])['status'],'STALE');self.assertFalse(manager.status(project['id'])['final_approval_eligible'])
            with self.assertRaisesRegex(WorkflowError,'CURRENT_AUDIBLE_PREVIEW'):reviewed(self.store,self.config,changed)
            self.assertEqual(file_sha(out/'voice.wav'),raw)
        finally:manager.close()

    def test_precancelled_preview_produces_no_playable_output_or_authority(self):
        project,_,_=self.fitted();folder=folder_for(self.config,project);folder.mkdir(parents=True);event=threading.Event();event.set()
        with self.assertRaisesRegex(WorkflowError,'PREVIEW_CANCELLED'):render(self.config,self.store,project,folder,event)
        self.assertFalse((folder/'preview.mp4').exists());self.assertIsNone(self.store.get(project['id'])['approval'])

    def test_narration_only_approval_cannot_render_and_current_audible_preview_is_bound_to_production_approval(self):
        project,_,_=self.fitted()
        with self.assertRaisesRegex(WorkflowError,'CURRENT_AUDIBLE_PREVIEW'):self.store.approve(project['id'],project['revision'],'EXPLICIT FIXTURE',True)
        narration=self.store.approve(project['id'],project['revision'],'EXPLICIT TTS ONLY FIXTURE',True,purpose='narration')
        self.assertEqual(narration['approval']['approval_scope'],'narration_only')
        with self.assertRaisesRegex(WorkflowError,'AUDIBLE_PREVIEW_APPROVAL_REQUIRED'):self.store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex)
        manager,value=self.generate(project)
        try:
            self.assertEqual(value['status'],'READY',value);approved=self.store.approve(project['id'],project['revision'],'EXPLICIT AFTER-PREVIEW FIXTURE',True)
            self.assertEqual(approved['approval']['render_mode'],'prepared_narration');self.assertNotIn('approval_scope',approved['approval'])
            self.assertEqual(approved['approval']['reviewed_preview']['sha256'],value['sha256']);queued=self.store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex)
            self.assertEqual(queued['snapshot']['approval'],approved['approval'])
        finally:manager.close()
