"""Native job/approval/media tests. Distinct tones stand for voices; no Owner UAT."""
import copy,json,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests import test_dialogue_audio as fixtures
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.dialogue_binding import NativeDialogueCompiler,validate
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.pipeline import Pipeline
from services.windows_native.narration import apply
from services.windows_native.voice_library import NativeVoiceLibrary

class DialogueRuntimeTests(unittest.TestCase):
    cast=fixtures.DialogueAudioTests.cast
    save_cast=fixtures.DialogueAudioTests.save_cast
    def setUp(self):
        fixtures.DialogueAudioTests.setUp(self)
        project=self.store.get(self.project['id']);self.store.set_brand(project['id'],project['revision'],'vang-nguyen','personal-30',duration_mode=FIT_NARRATION_POLICY)
        self.provider_patch=patch('services.windows_native.dialogue_runtime.providers_for',return_value=self.providers);self.provider_patch.start()
        self.legacy_patch=patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('Drama must never use legacy single voice'));self.legacy_patch.start()
        self.compile()
    def tearDown(self):
        self.legacy_patch.stop();self.provider_patch.stop();fixtures.DialogueAudioTests.tearDown(self)
    def compile(self):
        project=self.store.get(self.project['id']);previous=project['document'].get('compiled_dialogue')
        return NativeDialogueCompiler(self.store,self.library,self.providers).compile(project['id'],{'revision':project['revision'],
            'expected_version':previous['version'] if previous else 0,'request_key':'explicit-runtime-compile-'+str(project['revision'])},actor_ref='AUTOMATED RUNTIME FIXTURE — NOT UAT')
    def approved_job(self):
        project=self.store.get(self.project['id']);project=self.store.approve(project['id'],project['revision'],'AUTOMATED DIALOGUE FIXTURE — NOT OWNER',True,purpose='narration')
        self.store.enqueue(project['id'],project['revision'],'narration',uuid.uuid4().hex);return self.store.claim()
    def prepare(self):
        job=self.approved_job();result=Pipeline(self.config).run(job,lambda _:None);self.store.finish(job,result=result)
        return job,result,self.root/'jobs'/job['id']
    def apply(self,job,result):
        return apply(self.store,self.project['id'],job['id'],{'revision':self.store.get(self.project['id'])['revision'],
            'expected_plan_sha256':result['plan_sha256'],'acknowledged':True})

    def test_narration_approval_only_and_measured_canonical_apply_preserve_two_speakers(self):
        job,result,out=self.prepare();self.assertEqual(len(self.adapter.calls),2);self.assertFalse((out/'final.mp4').exists())
        self.assertEqual(job['snapshot']['approval']['approval_scope'],'narration_only')
        with self.assertRaisesRegex(WorkflowError,'AUDIBLE_PREVIEW_APPROVAL_REQUIRED'):
            self.store.enqueue(job['project_id'],job['revision'],'render',uuid.uuid4().hex)
        before=file_sha(out/'voice.wav');updated=self.apply(job,result);self.assertIsNone(updated['approval']);self.assertEqual(file_sha(out/'voice.wav'),before)
        self.assertLess(sum(v['duration'] for v in updated['shot_timeline']['shots']),10)
        tracks=updated['document']['canonical_timeline']['snapshot']['tracks'];captions=[c for t in tracks if t['kind']=='subtitles' for c in t['clips']]
        self.assertEqual([v['metadata']['speaker_name'] for v in captions],['An','Bình'])
        self.assertEqual([v['metadata']['dialogue_line_id'] for v in captions],[fixtures.LINE_A,fixtures.LINE_B])
        self.assertNotEqual(result['plan']['profile_sha256'],__import__('services.windows_native.contracts',fromlist=['PROFILE_SHA']).PROFILE_SHA)

    def test_targeted_character_reselection_reuses_other_actor_through_real_job_path(self):
        first,result,out=self.prepare();original=file_sha(out/'voice.wav');self.apply(first,result)
        configuration=copy.deepcopy(self.configuration);configuration['casting'][0]=self.cast(fixtures.CHAR_A,self.voices[2]);self.save_cast(configuration)
        project=self.store.get(self.project['id'])
        with self.assertRaisesRegex(WorkflowError,'SPECIFICATION_STALE'):self.store.approve(project['id'],project['revision'],'FIXTURE',True,purpose='narration')
        self.compile();second,result2,out2=self.prepare();meta=json.loads((out2/'voice.json').read_bytes())
        self.assertEqual(len(self.adapter.calls),3);self.assertEqual(meta['reused_line_clips'],1);self.assertEqual(self.adapter.calls[-1]['line_id'],fixtures.LINE_A)
        self.assertEqual(file_sha(out/'voice.wav'),original);self.apply(second,result2)

    def test_worker_rejects_provider_change_and_revoked_project_approval_before_io(self):
        job=self.approved_job();self.adapter.configuration_sha256='2'*64
        with self.assertRaisesRegex(WorkflowError,'PROVIDER_CONFIGURATION_CHANGED'):Pipeline(self.config).run(job,lambda _:None)
        self.adapter.configuration_sha256='1'*64
        # The real Runner records the failed attempt before an editor can mutate
        # the project. Preserve that busy-project guard in this direct-worker test.
        self.store.finish(job,error={'code':'DRAMA_PROVIDER_CONFIGURATION_CHANGED'})
        project=self.store.shot_view(self.project['id']);self.store.mutate_shots(project['id'],project['revision'],
            {'type':'update','shot_id':project['shot_timeline']['shots'][0]['shot_id'],'values':{'on_screen_text':'Later edit invalidates approval'}})
        with self.assertRaisesRegex(WorkflowError,'CURRENT_HUMAN_APPROVAL_REQUIRED'):Pipeline(self.config).run(job,lambda _:None)
        self.assertEqual(self.adapter.calls,[]);self.assertFalse((self.root/'jobs'/job['id']).exists())

    def test_library_version_change_rejects_queue_admission_after_approval(self):
        project=self.store.get(self.project['id']);project=self.store.approve(project['id'],project['revision'],'FIXTURE',True,purpose='narration')
        voice=self.voices[0];self.library.update(voice['voice_id'],{'expected_version':1,'request_key':'explicit-runtime-rights-revoke',
            'definition':{**voice['definition'],'rights_status':'blocked'}},actor_ref='EXPLICIT FIXTURE')
        with self.assertRaisesRegex(WorkflowError,'VOICE_BINDING_CHANGED'):self.store.enqueue(project['id'],project['revision'],'narration',uuid.uuid4().hex)
        self.assertEqual(self.adapter.calls,[]);self.assertEqual(self.store.get(project['id'])['jobs'],[])

    def test_complete_attempt_recovery_does_not_repeat_inference_after_lost_checkpoint(self):
        job=self.approved_job();original=Pipeline.publish_voice
        with patch.object(Pipeline,'publish_voice',side_effect=WorkflowError('EXPLICIT_PARENT_STOP_BEFORE_TTS_CHECKPOINT')):
            with self.assertRaisesRegex(WorkflowError,'EXPLICIT_PARENT_STOP'):Pipeline(self.config).run(job,lambda _:None)
        self.assertEqual(len(self.adapter.calls),2)
        result=Pipeline(self.config).run(job,lambda _:None);self.assertEqual(result['status'],'ready_for_timing_review');self.assertEqual(len(self.adapter.calls),2)
        self.assertEqual(len(list((self.root/'jobs'/job['id']/'attempts').glob('dialogue-*'))),1)

    def test_forged_self_consistent_compiler_manifest_has_no_db_authority(self):
        document=copy.deepcopy(self.store.get(self.project['id'])['document']);spec=document['compiled_dialogue'];spec['version']+=1
        spec['sha256']=digest({k:v for k,v in spec.items() if k!='sha256'})
        with self.assertRaisesRegex(WorkflowError,'COMPILATION_RECEIPT_CHANGED'):validate(document,self.library,providers=self.providers)
        self.assertEqual(self.adapter.calls,[])

    def test_two_mock_actors_no_narrator_preview_final_qc_and_manual_package_use_same_pcm(self):
        from services.windows_native.shot_preview import PreviewManager
        from services.windows_native.manual_delivery import NativeManualDelivery,DeliveryCreate
        source,result,out=self.prepare();original=file_sha(out/'voice.wav');project=self.apply(source,result)
        manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(project['id'],project['revision']);deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                status=manager.status(project['id'])
                if status['status'] not in {'QUEUED','RUNNING'}:break
                time.sleep(.1)
            self.assertEqual(status['status'],'READY',status)
        finally:manager.close()
        project=self.store.approve(project['id'],project['revision'],'AUTOMATED FINAL FIXTURE — NOT OWNER ACCEPTANCE',True)
        self.store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex);job=self.store.claim()
        rendered=Pipeline(self.config).run(job,lambda _:None);self.store.finish(job,result=rendered)
        self.assertTrue(rendered['qc']['passed']);target=self.root/'jobs'/job['id'];self.assertEqual(file_sha(target/'voice.wav'),original)
        self.assertEqual(len(self.adapter.calls),2);self.assertFalse(rendered['qc']['human_final_video_accepted'])
        captions=json.loads((target/'subtitles.json').read_bytes());self.assertEqual([v['speaker_name'] for v in captions['speaker_mapping']],['An','Bình'])
        self.assertIn('An: Xin chào.',(target/'subtitles.ass').read_text(encoding='utf-8'));self.assertIn('Bình: Cảm ơn.',(target/'subtitles.ass').read_text(encoding='utf-8'))
        self.store.review_render(job['id'],job['revision'],'AUTOMATED MEDIA FIXTURE — NOT OWNER',True,'approve')
        service=NativeManualDelivery(self.store,self.config);delivery=service.create(project['id'],DeliveryCreate(revision=project['revision'],render_job_id=job['id'],
            expected_video_sha256=rendered['qc']['final_sha256'],request_key='explicit-drama-export-fixture'))
        self.assertEqual(delivery['status'],'ready');directory=Path(delivery['output_location']);self.assertFalse(delivery['externally_posted'])
        self.assertIn('An: Xin chào.',(directory/'subtitle.srt').read_text(encoding='utf-8'));self.assertIn('Bình: Cảm ơn.',(directory/'subtitle.srt').read_text(encoding='utf-8'))
        rights=json.loads((directory/'rights-summary.json').read_bytes());self.assertEqual(len([v for v in rights['items'] if v['kind']=='dialogue_voice']),2)
        self.assertFalse(rights['independently_verified']);self.assertEqual(file_sha(directory/'final-video.mp4'),rendered['qc']['final_sha256'])
        from services.windows_native.manual_delivery import RecreatePackage
        qp=json.loads((directory/'dialogue-qc.json').read_bytes());self.assertEqual(qp['status'],'passed')
        self.assertEqual(json.loads((directory/'qc-report.json').read_bytes())['dialogue_caption_qc'],qp)
        old_zip=file_sha(directory/'delivery-package.zip');recreated=service.recreate(project['id'],delivery['export_id'],RecreatePackage(
            expected_manifest_sha256=delivery['manifest_sha256'],request_key='explicit-drama-recreate-qp-fixture'))
        recreated_dir=Path(recreated['output_location']);self.assertEqual(json.loads((recreated_dir/'dialogue-qc.json').read_bytes()),qp)
        self.assertEqual(json.loads((recreated_dir/'qc-report.json').read_bytes())['dialogue_caption_qc'],qp);self.assertEqual(file_sha(directory/'delivery-package.zip'),old_zip)
        # A library revocation closes fresh/current delivery even though the
        # document revision is unchanged. Historical approved bytes remain usable.
        voice=self.voices[0];self.library.update(voice['voice_id'],{'expected_version':1,'request_key':'explicit-post-export-voice-revoke',
            'definition':{**voice['definition'],'rights_status':'blocked'}},actor_ref='EXPLICIT FIXTURE')
        current=self.store.get(project['id']);self.assertFalse(current['drama_voice_binding']['current'])
        old=service.get(project['id'],delivery['export_id']);self.assertEqual(old['approval_state'],'approved_at_export');self.assertFalse(old['current_for_project'])
        self.assertEqual(file_sha(service.file(project['id'],delivery['export_id'],'final-video.mp4')),rendered['qc']['final_sha256'])
        with self.assertRaisesRegex(WorkflowError,'VOICE_BINDING_CHANGED'):service.create(project['id'],DeliveryCreate(revision=project['revision'],render_job_id=job['id'],
            expected_video_sha256=rendered['qc']['final_sha256'],request_key='explicit-new-export-after-revoke'))
        self.assertEqual(len(service.page(project['id'])['items']),2)
