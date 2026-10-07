"""Actual local pixels in isolated media jobs; speech remains an explicit mock."""
import copy
import json
import subprocess
import unittest
import uuid
from unittest.mock import patch
from PIL import Image
from services.windows_native import media_frame_analysis as frames,auto_edit_timeline as timeline
from services.windows_native import auto_edit_analysis,source_broll
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Pipeline
from services.windows_native.tests import test_source_preview as fixture


class MediaFrameTests(unittest.TestCase):
    setUp=fixture.NativeSourcePreviewTests.setUp
    tearDown=fixture.NativeSourcePreviewTests.tearDown
    save_analysis=fixture.NativeSourcePreviewTests.save_analysis
    real_source=fixture.NativeSourcePreviewTests.real_source

    def measure(self,finish=True):
        project=self.store.get(self.project['id'])
        job=self.store.enqueue(project['id'],project['revision'],'media_frames',uuid.uuid4().hex)
        job=self.store.claim();stages=[]
        with patch('services.windows_native.asr.analyze',side_effect=AssertionError('No ASR call')), \
             patch('services.windows_native.pipeline.generate',side_effect=AssertionError('No AI call')):
            result=Pipeline(self.config).run(job,stages.append)
        self.assertIn('media_frame_local_pixel_sampling',stages)
        if finish:self.store.finish(job,result=result);self.project=self.store.get(project['id'])
        return job,result

    def test_actual_video_pixels_are_bound_and_saved_without_timeline_or_raw_asr_mutation(self):
        source=self.real_source();before=copy.deepcopy(self.project);checksum=file_sha(source)
        job,result=self.measure();bundle=frames.view(self.store,self.project['id']);value=bundle['observations'][0]
        self.assertEqual(self.project['document']['canonical_timeline'],before['document']['canonical_timeline'])
        self.assertEqual(self.project['document']['media_analysis'],before['document']['media_analysis'])
        self.assertEqual(self.project['revision'],before['revision']+1);self.assertIsNone(self.project['approval'])
        self.assertEqual((result['provider_calls'],result['paid_operations']),(0,0))
        self.assertIsNone(result['actual_local_compute_cost']);self.assertFalse(result['canonical_timeline_mutated'])
        self.assertEqual(len(value['frames']),8);self.assertEqual(value['job_id'],job['id'])
        self.assertEqual(value['semantic_provider_status'],'NOT_CONFIGURED');self.assertIsNone(value['confidence'])
        self.assertFalse(value['semantic_inference_performed']);self.assertFalse(value['frozen_video_detection_performed'])
        for frame in value['frames']:
            self.assertTrue(0<frame['timestamp_seconds']<3);self.assertIsNone(frame['decoded_pts_seconds'])
            path=frames.frame_path(self.root,frame);self.assertEqual(file_sha(path),frame['sha256'])
            with Image.open(path) as image:self.assertEqual(image.size,(frame['width'],frame['height']))
            self.assertLessEqual(max(frame['width'],frame['height']),480)
            facts=frame['pixel_facts'];self.assertIsNone(facts['ocr']);self.assertIsNone(facts['blur_score'])
        self.assertEqual(file_sha(source),checksum);self.assertFalse(bundle['pending_asset_ids'])
        self.assertIn('media_frame_evidence_version',self.store.versions(self.project['id'])[0]['components'])
        before_versions=self.store.versions(self.project['id']);self.assertEqual(frames.view(self.store,self.project['id']),bundle)
        self.assertEqual(self.store.versions(self.project['id']),before_versions)
        with self.assertRaisesRegex(WorkflowError,'MEDIA_FRAME_NO_PENDING_ASSET'):
            self.store.enqueue(self.project['id'],self.project['revision'],'media_frames',uuid.uuid4().hex)

    def test_black_image_and_static_video_report_samples_without_fabricated_semantics_or_freeze_detection(self):
        source=self.root/'static.mp4'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi',
            '-i','color=c=blue:s=320x240:r=30:d=3','-c:v','libx264','-pix_fmt','yuv420p',str(source)],
            check=True,capture_output=True,timeout=30)
        asset=ingest_media(self.config,source,'video/mp4','Static fixture',rights_confirmed=True,illustration=False)
        self.project=self.store.create('Static pixel fixture','','media')
        self.project=self.store.append_media(self.project['id'],self.project['revision'],asset)
        black=self.root/'black.png';Image.new('RGB',(320,240),(0,0,0)).save(black)
        image=ingest_media(self.config,black,'image/png','Black fixture',rights_confirmed=True,illustration=True)
        image['rights_confirmed']=False # Explicit unverified historical metadata.
        self.project=self.store.append_media(self.project['id'],self.project['revision'],image)
        self.measure();values=frames.view(self.store,self.project['id'])['observations']
        video=next(v for v in values if v['asset_id']==asset['id']);picture=next(v for v in values if v['asset_id']==image['id'])
        self.assertEqual(sum(f['duplicate_sample_of'] is not None for f in video['frames']),7)
        self.assertEqual(len(video['thumbnail_candidate_ids']),1);self.assertFalse(video['frozen_video_detection_performed'])
        self.assertTrue(picture['frames'][0]['pixel_facts']['black_sample']);self.assertEqual(picture['best_frame_ids'],[])
        self.assertEqual(picture['rights_status'],'unknown');self.assertFalse(picture['rights_independently_verified'])
        self.assertIsNone(picture['frames'][0]['pixel_facts']['watermark_or_logo_evidence'])

    def test_checkpoint_reuse_rejects_changed_source_and_changed_frame(self):
        source=self.real_source();job,result=self.measure()
        with patch('services.windows_native.source_render.command_run',side_effect=AssertionError('No second decode')):
            self.assertEqual(Pipeline(self.config).run(job,lambda stage:None),result)
        frame=result['media_frame_analyses'][0]['observation']['frames'][0];path=frames.frame_path(self.root,frame)
        original=path.read_bytes();path.write_bytes(original+b'corrupt-test')
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):Pipeline(self.config).run(job,lambda stage:None)
        with self.assertRaisesRegex(WorkflowError,'MEDIA_FRAME_ARTIFACT_CHANGED'):frames.view(self.store,self.project['id'])
        path.write_bytes(original);source.write_bytes(source.read_bytes()+b'source-drift')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED_OR_MISSING'):Pipeline(self.config).run(job,lambda stage:None)

    def test_forged_semantic_or_wrong_job_result_rolls_back_before_job_success(self):
        self.real_source();job,result=self.measure(finish=False);before=self.store.get(self.project['id'])
        changed=copy.deepcopy(result);record=changed['media_frame_analyses'][0]
        record['observation']['semantic_inference_performed']=True;record['sha256']=digest(record['observation'])
        with self.assertRaisesRegex(WorkflowError,'MEDIA_FRAME_OBSERVATIONS_INVALID'):self.store.finish(job,result=changed)
        changed=copy.deepcopy(result);record=changed['media_frame_analyses'][0]
        record['observation']['job_id']=uuid.uuid4().hex;record['sha256']=digest(record['observation'])
        with self.assertRaisesRegex(WorkflowError,'MEDIA_FRAME_RESULT_JOB_MISMATCH'):self.store.finish(job,result=changed)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.store.get_job(job['id'])['status'],'running')
        self.store.finish(job,result=result)

    def test_stale_result_and_interrupted_resume_never_write_or_automatically_replay(self):
        self.real_source();job,result=self.measure(finish=False)
        self.store.recover();self.assertEqual(self.store.get_job(job['id'])['status'],'interrupted')
        resumed=self.store.resume(job['id']);self.assertEqual(resumed['id'],job['id']);claimed=self.store.claim()
        with patch('services.windows_native.source_render.command_run',side_effect=AssertionError('Checkpoint must be reused')):
            cached=Pipeline(self.config).run(claimed,lambda stage:None)
        self.assertEqual(cached,result)
        with self.store.transaction() as con:con.execute('UPDATE projects SET revision=revision+1 WHERE id=?',(self.project['id'],))
        with self.assertRaisesRegex(WorkflowError,'MEDIA_FRAME_STALE_RESULT'):self.store.finish(claimed,result=result)
        self.assertNotIn('media_frame_analyses',self.store.get(self.project['id'])['document'])

    def test_source_duplicate_rebinds_identity_and_preserves_actual_frames_with_explicit_lineage(self):
        self.real_source();self.measure();before=copy.deepcopy(self.project);versions=self.store.versions(self.project['id'])
        child=self.store.duplicate(self.project['id'],self.project['revision'])
        old=frames.view(self.store,self.project['id'])['observations'][0];new=frames.view(self.store,child['id'])['observations'][0]
        self.assertEqual(new['project_id'],child['id']);self.assertNotEqual(old['observation_id'],new['observation_id'])
        self.assertFalse(new['identity_rebinding']['fresh_measurement']);self.assertEqual(new['identity_rebinding']['source_project_id'],self.project['id'])
        for original,reused in zip(old['frames'],new['frames'],strict=True):
            self.assertNotEqual(original['frame_id'],reused['frame_id']);self.assertEqual(original['reference'],reused['reference'])
            self.assertEqual(frames.frame_path(self.root,original),frames.image_path(self.store,child['id'],reused['frame_id']))
        self.assertFalse(frames.view(self.store,child['id'])['pending_asset_ids']);self.assertIsNone(child['approval'])
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.store.versions(self.project['id']),versions)
        unrelated=self.store.create('Unrelated','','media');unrelated=self.store.append_media(unrelated['id'],1,self.asset)
        with self.assertRaisesRegex(WorkflowError,'MEDIA_FRAME_NOT_FOUND'):frames.image_path(self.store,unrelated['id'],old['frames'][0]['frame_id'])

    def test_changed_checkpoint_blocks_manual_resume_and_history_limit_blocks_enqueue(self):
        self.real_source()
        with patch.object(frames,'MAX_RECORDS',0),self.assertRaisesRegex(WorkflowError,'MEDIA_FRAME_HISTORY_LIMIT'):
            self.store.enqueue(self.project['id'],self.project['revision'],'media_frames',uuid.uuid4().hex)
        job,result=self.measure(finish=False);self.store.recover()
        path=frames.frame_path(self.root,result['media_frame_analyses'][0]['observation']['frames'][0]);path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):self.store.resume(job['id'])
        self.assertEqual(self.store.get_job(job['id'])['status'],'interrupted')

    def test_scene_highlight_and_supporting_media_ranking_bind_saved_pixels_without_semantic_confidence(self):
        self.real_source();image=self.root/'supporting.png'
        Image.new('RGB',(320,240),(25,125,220)).save(image)
        asset=ingest_media(self.config,image,'image/png','Xin chào supporting.png',rights_confirmed=True,illustration=True)
        self.project=self.store.append_media(self.project['id'],self.project['revision'],asset)
        self.measure();bundle=auto_edit_analysis.view(self.store,self.project['id'])
        scenes=bundle['analyses'][0]['scenes'];measured=[s for s in scenes if s['evidence']['pixel_quality_facts']]
        self.assertTrue(measured);self.assertTrue(bundle['analyses'][0]['highlights'])
        for scene in measured:
            self.assertFalse(scene['evidence']['vision_used']);self.assertIsNone(scene['evidence']['pixel_quality_confidence'])
            self.assertEqual(scene['subjects'],[]);self.assertTrue(scene['needs_attention'])
            self.assertIn('uncalibrated',scene['evidence']['quality_basis'])
        self.project=source_broll.create(self.store,self.config,self.project['id'],self.project['revision'],{'expected_version':1})
        plan=self.project['document']['source_broll_plans'][-1]['plan']
        candidates=plan['items'][0]['provenance']['supporting_candidates'];candidate=next(c for c in candidates if c['filename']=='Xin chào supporting.png')
        self.assertIsNotNone(candidate['quality_score']);self.assertIsNone(candidate['confidence'])
        self.assertIsNone(candidate['pixel_quality_summary']['semantic_relevance'])
        self.assertEqual(candidate['pixel_quality_summary']['source_sha256'],asset['sha256'])
        self.assertEqual(plan['provider_status']['semantic_vision'],'NOT_CONFIGURED')
        record=next(r for r in self.project['document']['media_frame_analyses'] if r['observation']['asset_id']==asset['id'])
        frames.frame_path(self.root,record['observation']['frames'][0]).write_bytes(b'Corrupted supporting evidence')
        with self.assertRaisesRegex(WorkflowError,'MEDIA_FRAME_ARTIFACT_CHANGED'):source_broll.shared_assets(self.project,self.config)


if __name__=='__main__':unittest.main()
