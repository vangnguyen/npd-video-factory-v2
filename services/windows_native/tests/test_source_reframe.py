"""Actual local synthetic source geometry; manual crops are not Vision acceptance."""
import copy
import subprocess
import sys
import unittest
from services.windows_native import source_reframe,source_settings,source_linked_edit
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.tests import test_source_preview as fixture


class SourceReframeTests(unittest.TestCase):
    setUp=fixture.NativeSourcePreviewTests.setUp
    tearDown=fixture.NativeSourcePreviewTests.tearDown
    save_analysis=fixture.NativeSourcePreviewTests.save_analysis
    real_source=fixture.NativeSourcePreviewTests.real_source

    def apply(self,**values):
        self.project=source_reframe.apply(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'aspect_ratio':'9:16',**values})
        return self.project

    def test_four_ratios_preserve_audio_captions_source_and_mark_unknown_tracking(self):
        path=self.real_source();original=file_sha(path);before=copy.deepcopy(self.project)
        audio=[t for t in before['shot_timeline']['snapshot']['tracks'] if t['type']!='video']
        for ratio,width,height in [('9:16',1080,1920),('16:9',1920,1080),('1:1',1080,1080),('4:5',1080,1350)]:
            self.apply(aspect_ratio=ratio);snapshot=self.project['shot_timeline']['snapshot']
            self.assertEqual((snapshot['width'],snapshot['height'],snapshot['aspect_ratio']),(width,height,ratio))
            self.assertEqual([t for t in snapshot['tracks'] if t['type']!='video'],audio)
            saved=snapshot['metadata']['source_reframe_plan'];self.assertIsNone(saved['tracking_confidence'])
            self.assertEqual(saved['provider_status'],'NOT_CONFIGURED');self.assertEqual(saved['provider_dispatches'],0)
            self.assertTrue(saved['plan']['needs_attention']);self.assertEqual(saved['plan']['fallback'],'center_crop')
            for track in snapshot['tracks']:
                for clip in track['clips']:
                    if track['kind']!='source':continue
                    for point in clip['metadata']['reframe']['keyframes']:
                        self.assertAlmostEqual(320/240*point['width']/point['height'],width/height,places=6)
                        self.assertLessEqual(point['x']+point['width'],1.000001)
                        self.assertLessEqual(point['y']+point['height'],1.000001)
            self.assertIsNone(self.project['approval']);self.assertEqual(file_sha(path),original)

    def test_manual_path_remains_source_relative_after_linked_trim_split_speed_restore_and_duplicate(self):
        self.real_source();prior=copy.deepcopy(self.project)
        self.apply(mode='manual_override',aspect_ratio='4:5',points=[{'time':2.9,'x':.8,'y':.5,'zoom':1.1},
            {'time':0,'x':.2,'y':.5,'zoom':1}])
        saved=self.project['shot_timeline']['snapshot']['metadata']['source_reframe_plan']
        self.assertEqual(saved['plan']['strategy'],'manual_override');self.assertEqual(saved['plan']['fallback'],'none')
        self.assertEqual(saved['confidence_basis'],'explicit_human_crop_coordinates')
        self.assertIsNone(saved['tracking_confidence']);self.assertFalse(saved['fresh_provider_measurement'])
        clip=self.project['shot_timeline']['shots'][0]['shot_id']
        points=next(c['metadata']['reframe']['keyframes'] for t in self.project['shot_timeline']['snapshot']['tracks'] if t['kind']=='source' for c in t['clips'])
        self.assertEqual([point['time'] for point in points],[0,2.9])
        for operation in [{'type':'trim','clip_id':clip,'source_start':.3,'source_end':2.5},
                {'type':'split','clip_id':clip,'at_seconds':1.1},{'type':'set_clip_properties','clip_id':clip,'speed':1.25}]:
            self.project=source_linked_edit.edit(self.store,self.project['id'],self.project['revision'],{
                'expected_version':self.project['shot_timeline']['version'],'operation':operation})
        snapshot=self.project['shot_timeline']['snapshot']
        for track in snapshot['tracks']:
            if track['kind']=='source':
                for item in track['clips']:
                    self.assertEqual(item['metadata']['reframe']['time_space'],'source_seconds')
                    self.assertEqual(item['metadata']['reframe']['keyframes'],points)
        child=self.store.duplicate(self.project['id'],self.project['revision'])
        child_meta=child['shot_timeline']['snapshot']['metadata'];self.assertEqual(child_meta['source_reframe_plan']['source_analysis_id'],child_meta['source_analysis_id'])
        self.project=timeline.restore(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'restore_revision':prior['revision']})
        self.assertEqual(self.project['shot_timeline']['snapshot'],prior['shot_timeline']['snapshot'])

    def test_invalid_request_locks_drift_and_format_change_never_mutate_saved_plan(self):
        path=self.real_source();before=copy.deepcopy(self.project)
        for values,code in [({'mode':'manual_override'},'REQUEST_INVALID'),
                ({'mode':'center_crop','points':[{'time':0,'x':.5,'y':.5}]},'REQUEST_INVALID'),
                ({'mode':'manual_override','points':[{'time':3.1,'x':.5,'y':.5}]},'SOURCE_TIME_INVALID'),
                ({'mode':'manual_override','points':[{'time':0,'x':1.2,'y':.5}]},'REQUEST_INVALID'),
                ({'mode':'manual_override','points':[{'time':0,'x':.5,'y':.5}]*2},'REQUEST_INVALID'),
                ({'expected_version':99},'VERSION_CHANGED'),({'tracking_confidence':.9},'REQUEST_INVALID')]:
            with self.assertRaisesRegex(WorkflowError,code):self.apply(**values)
            self.assertEqual(timeline.view(self.store,self.project['id']),before)
        self.apply();before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'REFRAME_REAPPLY_FOR_FORMAT_REQUIRED'):
            source_settings.configure(self.store,self.project['id'],self.project['revision'],{
                'expected_version':self.project['shot_timeline']['version'],'aspect_ratio':'1:1'})
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        track=next(t for t in self.project['shot_timeline']['snapshot']['tracks'] if t['kind']=='source')
        self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'operations':[{'type':'set_track_state','track_id':track['track_id'],'locked':True}]})
        before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'PLAN_INVALID_OR_LOCKED'):self.apply()
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        path.write_bytes(b'Explicit isolated corrupt source')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED_OR_MISSING'):self.apply()
        self.assertEqual(timeline.view(self.store,self.project['id']),before)

    def test_pure_shared_geometry_import_does_not_load_api_database_or_repository(self):
        subprocess.run([sys.executable,'-c',"import services.windows_native.source_reframe;import sys;"
            "assert not any(n.startswith('sqlalchemy') or n in {'app.timeline_repository','app.repositories'} for n in sys.modules)"],
            check=True,capture_output=True,timeout=15)


if __name__=='__main__':unittest.main()
