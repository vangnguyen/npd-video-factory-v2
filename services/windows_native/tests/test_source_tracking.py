"""Actual local decoded source samples; fixture transcript is never real ASR."""
import copy,uuid,unittest
from services.windows_native.tests import test_source_preview as fixture
from services.windows_native import source_tracking as module,source_reframe
from services.windows_native.contracts import WorkflowError,file_sha,digest
from services.windows_native.pipeline import Pipeline


class SourceTrackingTests(unittest.TestCase):
    setUp=fixture.NativeSourcePreviewTests.setUp
    tearDown=fixture.NativeSourcePreviewTests.tearDown
    save_analysis=fixture.NativeSourcePreviewTests.save_analysis
    real_source=fixture.NativeSourcePreviewTests.real_source

    def request(self):
        state=self.project['document']['canonical_timeline']
        return {'expected_version':state['version'],'analysis_id':state['snapshot']['metadata']['source_analysis_id'],
            'configuration':{'seed_box':{'x':.2,'y':.25,'width':.2,'height':.25},'sample_interval_seconds':.2}}

    def run_tracking(self,body=None):
        queued=self.store.enqueue(self.project['id'],self.project['revision'],'source_tracking',uuid.uuid4().hex,tracking_request=body or self.request())
        job=self.store.claim();self.assertEqual(job['id'],queued['id']);stages=[]
        result=Pipeline(self.config).run(job,stages.append);self.store.finish(job,result=result)
        from services.windows_native.auto_edit_timeline import view
        self.project=view(self.store,self.project['id']);return result,stages

    def test_actual_ffmpeg_pixels_pts_job_and_saved_result_preserve_source_without_timeline_edit(self):
        path=self.real_source();original=file_sha(path);before=copy.deepcopy(self.project['document']['canonical_timeline'])
        result,stages=self.run_tracking();record=result['source_tracking_analysis'];value=record['analysis']
        self.assertGreater(value['sample_count'],8);self.assertTrue(value['decoded_pts_verified']);self.assertFalse(value['every_frame_tracking_performed'])
        self.assertFalse(value['semantic_inference_performed']);self.assertIsNone(value['confidence']);self.assertEqual(result['provider_calls'],0)
        self.assertEqual(value['frames'][0]['observation']['timestamp_seconds'],0.)
        self.assertEqual(file_sha(path),original);self.assertEqual(self.project['document']['canonical_timeline'],before);self.assertIsNone(self.project['approval'])
        with self.store.transaction() as con:self.assertEqual(module.read_saved(self.store,con,self.project,value['tracking_id'],record['sha256']),record)
        self.assertIn('local_subject_tracking_measure',stages)

    def test_exact_request_replay_changed_roi_conflict_and_invalid_source_are_atomic(self):
        self.real_source();body=self.request();key=uuid.uuid4().hex
        job=self.store.enqueue(self.project['id'],self.project['revision'],'source_tracking',key,tracking_request=body)
        self.assertEqual(job,self.store.enqueue(self.project['id'],self.project['revision'],'source_tracking',key,tracking_request=body))
        changed=copy.deepcopy(body);changed['configuration']['seed_box']['x']=.4
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_KEY_CONFLICT'):self.store.enqueue(self.project['id'],self.project['revision'],'source_tracking',key,tracking_request=changed)
        with self.assertRaisesRegex(WorkflowError,'REQUEST_KIND_INVALID'):self.store.enqueue(self.project['id'],self.project['revision'],'media_frames',uuid.uuid4().hex,tracking_request=body)

    def test_interrupted_local_job_resumes_same_request_without_changing_timeline(self):
        self.real_source();body=self.request();before=copy.deepcopy(self.project['document']['canonical_timeline'])
        queued=self.store.enqueue(self.project['id'],self.project['revision'],'source_tracking',uuid.uuid4().hex,tracking_request=body)
        job=self.store.claim();self.store.finish(job,error={'code':'EXPLICIT_LOCAL_INTERRUPTION_FIXTURE'})
        resumed=self.store.resume(queued['id']);self.assertEqual(resumed['snapshot']['tracking_request'],job['snapshot']['tracking_request'])
        job=self.store.claim();result=Pipeline(self.config).run(job,lambda _:None);self.store.finish(job,result=result)
        self.assertEqual(self.store.get_job(job['id'])['status'],'succeeded')
        self.assertEqual(self.store.get(self.project['id'])['document']['canonical_timeline'],before)

    def test_saved_analysis_can_apply_four_ratios_and_clone_preserves_only_geometry_authority(self):
        self.real_source();result,_=self.run_tracking();record=result['source_tracking_analysis'];audio=copy.deepcopy([t for t in self.project['shot_timeline']['snapshot']['tracks'] if t['type']!='video'])
        for ratio in ('9:16','16:9','1:1','4:5'):
            self.project=source_reframe.apply(self.store,self.project['id'],self.project['revision'],{'expected_version':self.project['shot_timeline']['version'],
                'aspect_ratio':ratio,'mode':'local_tracking','tracking_id':record['analysis']['tracking_id'],'tracking_sha256':record['sha256']})
            self.assertEqual([t for t in self.project['shot_timeline']['snapshot']['tracks'] if t['type']!='video'],audio)
            self.assertTrue(self.project['shot_timeline']['snapshot']['metadata']['reframe_review']['human_review_required'])
        before=self.store.get(self.project['id']);clone=self.store.duplicate(self.project['id'],self.project['revision'])
        self.assertNotIn('source_tracking_analyses',clone['document']);self.assertNotIn('local_tracking_selection',clone['document']['canonical_timeline']['snapshot']['metadata'])
        self.assertFalse(clone['document']['source_tracking_inherited_history'][0]['authority_transferred']);self.assertIsNone(clone['approval'])
        self.assertEqual(self.store.get(before['id']),before)

    def test_changed_frame_and_rehashed_record_cannot_be_applied_as_a_measured_job_result(self):
        self.real_source();result,_=self.run_tracking();record=result['source_tracking_analysis'];broken=copy.deepcopy(record)
        broken['analysis']['frames'][0]['observation']['bounding_box']={'x':.1,'y':.1,'width':.1,'height':.1};broken['sha256']=digest(broken['analysis'])
        with self.store.transaction() as con:
            self.project['document']['source_tracking_analyses']=[broken]
            with self.assertRaisesRegex(WorkflowError,'JOB_CHANGED'):module.read_saved(self.store,con,self.project,broken['analysis']['tracking_id'],broken['sha256'])
        file=module.frame_path(self.store.root,record['analysis']['frames'][0]);file.write_bytes(b'OWNED TEST CORRUPTION')
        with self.assertRaisesRegex(WorkflowError,'FRAME_CHANGED'):module.frame_path(self.store.root,record['analysis']['frames'][0])
