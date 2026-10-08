"""Measured native narration over actual PCM/canonical edits, explicit voice fixtures."""
import copy,json,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests.test_shot_production import prepared,voice
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.contracts import WorkflowError,digest,file_sha,write_json
from services.windows_native.hardening import Artifacts
from services.windows_native.pipeline import Pipeline
from services.windows_native.narration import identity,prepare,page,apply,reuse

class NarrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.config,self.store,self.project=prepared(self.root)
        self.project=self.store.set_brand(self.project['id'],self.project['revision'],'vang-nguyen','personal-30',duration_mode=FIT_NARRATION_POLICY)
    def tearDown(self):self.temp.cleanup()
    def start(self):
        self.project=self.store.approve(self.project['id'],self.project['revision'],'EXPLICIT NARRATION FIXTURE',True)
        job=self.store.enqueue(self.project['id'],self.project['revision'],'narration',uuid.uuid4().hex);job=self.store.claim()
        out=self.root/'jobs'/job['id'];out.parent.mkdir(exist_ok=True);voice(out);write_json(out/'tts-plan.json',{'explicit_synthetic_pcm_fixture':True})
        Artifacts(out,job).commit('tts',[out/'voice.wav',out/'voice.json',out/'tts-plan.json']);return job,out
    def finish(self):
        job,out=self.start()
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No inference allowed')):
            result=Pipeline(self.config).run(job,lambda _:None)
        self.store.finish(job,result=result);return self.store.get_job(job['id']),out,result
    def body(self,result):return {'revision':self.store.get(self.project['id'])['revision'],'expected_plan_sha256':result['plan_sha256'],'acknowledged':True}
    def audible(self,project):
        import time
        from services.windows_native.shot_preview import PreviewManager
        manager=PreviewManager(self.config,self.store);manager.generate(project['id'],project['revision']);deadline=time.monotonic()+30
        try:
            while time.monotonic()<deadline:
                status=manager.status(project['id'])
                if status['status'] not in {'QUEUED','RUNNING'}:self.assertEqual(status['status'],'READY',status);return status
                time.sleep(.05)
            self.fail('Narrated preview fixture deadline')
        finally:manager.close()

    def test_preparation_measures_scene_pcm_without_render_or_edit_and_returns_exact_checkpoint_replay(self):
        before=copy.deepcopy(self.project['document']);job,out,result=self.finish();self.assertEqual(self.store.get(self.project['id'])['document'],before)
        self.assertEqual([i['recommended_duration_seconds'] for i in result['plan']['items']],[1.7,1.6]);self.assertAlmostEqual(result['plan']['recommended_duration_seconds'],3.3)
        self.assertFalse((out/'final.mp4').exists());self.assertIsNone(result['plan']['confidence']);self.assertFalse(result['plan']['word_alignment_claimed'])
        self.assertEqual(Pipeline(self.config).run(job,lambda _:None),result);self.assertEqual(page(self.store,self.project['id'])['items'][0]['result'],result)

    def test_unapproved_preparation_is_rejected_before_queue_admission(self):
        with self.assertRaisesRegex(WorkflowError,'HUMAN_APPROVAL_REQUIRED'):self.store.enqueue(self.project['id'],self.project['revision'],'narration',uuid.uuid4().hex)
        self.assertEqual(self.store.get(self.project['id'])['jobs'],[])

    def test_apply_is_one_explicit_shared_canonical_edit_clears_approval_and_preserves_pcm(self):
        job,out,result=self.finish();raw=file_sha(out/'voice.wav');before=self.store.shot_view(self.project['id']);updated=apply(self.store,self.project['id'],job['id'],self.body(result))
        self.assertEqual(updated['revision'],before['revision']+1);self.assertEqual(updated['shot_timeline']['version'],before['shot_timeline']['version']+1);self.assertIsNone(updated['approval'])
        self.assertEqual([s['requested_duration'] for s in updated['shot_timeline']['shots']],[1.7,1.6]);self.assertEqual(file_sha(out/'voice.wav'),raw)
        self.assertEqual(updated['document']['proposal'],before['document']['proposal']);self.assertEqual(updated['document']['scene_media'],before['document']['scene_media'])
        self.assertEqual(len(updated['jobs']),1);self.assertTrue(page(self.store,self.project['id'])['items'][0]['voice_input_current']);self.assertFalse(page(self.store,self.project['id'])['items'][0]['timing_apply_current'])

    def test_changed_revision_hash_or_document_rejects_apply_without_mutation(self):
        job,out,result=self.finish();before=self.store.get(self.project['id'])
        for change in [{'expected_plan_sha256':'0'*64},{'acknowledged':False},{'revision':before['revision']-1},{'result':{'provider':'injected'}}]:
            with self.assertRaises(WorkflowError):apply(self.store,self.project['id'],job['id'],{**self.body(result),**change})
            self.assertEqual(self.store.get(self.project['id']),before)
        shot=self.store.shot_view(self.project['id'])['shot_timeline']['shots'][0]
        changed=self.store.mutate_shots(self.project['id'],before['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'on_screen_text':'Changed visual edit'}})
        with self.assertRaisesRegex(WorkflowError,'PLAN_STALE'):apply(self.store,self.project['id'],job['id'],self.body(result))
        self.assertEqual(self.store.get(self.project['id'])['document'],changed['document'])

    def test_changed_narration_invalidates_reuse_but_visual_edit_retains_exact_voice_inputs(self):
        job,out,result=self.finish();updated=apply(self.store,self.project['id'],job['id'],self.body(result));fp=identity(updated['document']);shot=updated['shot_timeline']['shots'][0]
        edited=self.store.mutate_shots(updated['id'],updated['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'on_screen_text':'Visual change'}});self.assertEqual(identity(edited['document']),fp)
        changed=self.store.mutate_shots(edited['id'],edited['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'narration':'Xin chào bạn.'}})
        self.assertNotEqual(identity(changed['document']),fp);self.assertFalse(page(self.store,changed['id'])['items'][0]['voice_input_current'])

    def test_final_render_reuses_verified_pcm_without_inference_and_keeps_original_source_approval(self):
        source,out,result=self.finish();updated=apply(self.store,self.project['id'],source['id'],self.body(result));self.audible(updated);updated=self.store.approve(updated['id'],updated['revision'],'EXPLICIT FINAL FIXTURE',True)
        job=self.store.enqueue(updated['id'],updated['revision'],'render',uuid.uuid4().hex);job=self.store.claim()
        with patch('services.windows_native.pipeline.verify_runtime'),patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No inference allowed')):
            rendered=Pipeline(self.config).run(job,lambda _:None)
        target=self.root/'jobs'/job['id'];self.assertAlmostEqual(rendered['qc']['duration_seconds'],3.3,places=1);self.assertEqual(file_sha(target/'voice.wav'),file_sha(out/'voice.wav'))
        receipt=json.loads((target/'voice-reuse.json').read_bytes());self.assertEqual(receipt['source_job_id'],source['id']);self.assertEqual(receipt['new_inference_calls'],0)
        self.assertIn('voice-reuse.json',{p['path'] for p in Artifacts(target,job).load('render')['artifacts']})
        self.assertEqual(self.store.get_job(source['id'])['snapshot']['approval'],source['snapshot']['approval'])

    def test_changed_source_pcm_or_plan_blocks_reuse_before_any_inference(self):
        source,out,result=self.finish();updated=apply(self.store,self.project['id'],source['id'],self.body(result));self.audible(updated);updated=self.store.approve(updated['id'],updated['revision'],'EXPLICIT FIXTURE',True)
        job=self.store.enqueue(updated['id'],updated['revision'],'render',uuid.uuid4().hex);target=self.root/'jobs'/job['id'];target.mkdir();(out/'voice.wav').write_bytes(b'EXPLICIT CORRUPTION FIXTURE')
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):reuse(self.config,job,Artifacts(target,job),lambda _:None)
        self.assertFalse((target/'voice.wav').exists())

    def test_foreign_project_cannot_apply_or_inherit_prepared_narration_authority(self):
        job,out,result=self.finish();other=self.store.create('Other fixture','No provider')
        with self.assertRaisesRegex(WorkflowError,'NARRATION_JOB_NOT_FOUND'):apply(self.store,other['id'],job['id'],{'revision':other['revision'],'expected_plan_sha256':result['plan_sha256'],'acknowledged':True})
        updated=apply(self.store,self.project['id'],job['id'],self.body(result));duplicate=self.store.duplicate(updated['id'],updated['revision'])
        self.assertNotIn('prepared_narration',duplicate['document']);self.assertTrue(duplicate['document']['prepared_narration_origin']['new_preparation_required'])
