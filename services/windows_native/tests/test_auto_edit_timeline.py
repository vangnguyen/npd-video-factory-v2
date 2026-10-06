"""Source-footage canonical persistence/CAS; no provider, render or human UAT."""
from copy import deepcopy
import json
import unittest
import uuid
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native import auto_edit_analysis as analysis
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.tests import test_auto_edit_analysis as fixture
from services.windows_native.store import Store
from services.windows_native.pipeline import Pipeline
from services.windows_native.shot_preview import PreviewManager


class NativeSourceTimelineTests(unittest.TestCase):
    setUp=fixture.NativeAutoEditTests.setUp
    tearDown=fixture.NativeAutoEditTests.tearDown
    save_analysis=fixture.NativeAutoEditTests.save_analysis

    def create(self, **values):
        bundle=self.save_analysis()
        item=bundle['analyses'][0]['analysis']
        self.project=timeline.create(self.store,self.project['id'],bundle['revision'],{
            'analysis_id':item['analysis_id'],'transcript_id':item['transcript']['transcript_id'],**values})
        return self.project

    def source_clip(self):
        return next(clip for track in self.project['shot_timeline']['snapshot']['tracks']
            if track['type']=='video' and track['kind']=='source' for clip in track['clips'])

    def edit(self, operations, **values):
        self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'operations':operations,**values})
        return self.project

    def test_canonical_draft_has_source_audio_aligned_captions_and_no_narrated_projection(self):
        original=deepcopy(self.project['document']['media_analysis'])
        project=self.create()
        snapshot=project['shot_timeline']['snapshot']
        self.assertEqual(project['shot_timeline']['editing_mode'],'source_footage')
        self.assertTrue(all(shot['timing_measured'] for shot in project['shot_timeline']['shots']))
        self.assertFalse(any(shot['narration_enabled'] for shot in project['shot_timeline']['shots']))
        self.assertEqual(snapshot['duration_seconds'],3.)
        source=[clip for track in snapshot['tracks'] if track['kind']=='source' for clip in track['clips']]
        audio=[clip for track in snapshot['tracks'] if track['type']=='audio' for clip in track['clips']]
        self.assertEqual([(clip['source_start'],clip['source_end'],clip['timeline_start']) for clip in source],
            [(clip['source_start'],clip['source_end'],clip['timeline_start']) for clip in audio])
        captions=[clip for track in snapshot['tracks'] if track['kind']=='subtitles' for clip in track['clips']]
        self.assertEqual(len(captions),2); self.assertEqual(len(captions[0]['metadata']['measured_source_words']),2)
        self.assertIsNone(project['document']['proposal']); self.assertIsNone(project['approval'])
        self.assertEqual(project['document']['media_analysis'],original)
        self.assertEqual(self.store.shot_view(project['id']),project)
        self.assertEqual(timeline.view(Store(self.root),project['id']),project)

    def test_reviewed_silence_cuts_are_non_destructive_and_preserve_padding(self):
        self.signals=self.signals.__class__(self.signals.shot_boundaries,
            ((.55,.9,None),(1.25,1.99,None)),self.signals.provenance)
        bundle=self.save_analysis(); item=bundle['analyses'][0]['analysis']
        decision=next(value for value in item['silence_decisions'] if value['enabled'])
        project=timeline.create(self.store,self.project['id'],bundle['revision'],{
            'analysis_id':item['analysis_id'],'transcript_id':item['transcript']['transcript_id'],
            'silence_decision_ids':[decision['decision_id']]})
        snapshot=project['shot_timeline']['snapshot']
        self.assertEqual(snapshot['metadata']['silence_decisions_applied'],1)
        self.assertAlmostEqual(snapshot['duration_seconds'],3-(decision['end_seconds']-decision['start_seconds']))
        self.assertFalse(snapshot['source_media_mutated'])
        unsafe=next(value for value in item['silence_decisions'] if not value['enabled'])
        with self.assertRaises(WorkflowError) as failed:
            timeline.create(self.store,project['id'],project['revision'],{
                'analysis_id':item['analysis_id'],'transcript_id':item['transcript']['transcript_id'],
                'expected_version':1,'silence_decision_ids':[unsafe['decision_id']]})
        self.assertEqual(failed.exception.code,'AUTO_EDIT_TIMELINE_SELECTION_INVALID')

    def test_highlight_window_extends_to_whole_word_and_four_canvas_shapes(self):
        self.create(source_window=(.3,1.1),aspect_ratio='4:5')
        snapshot=self.project['shot_timeline']['snapshot']
        self.assertEqual(snapshot['metadata']['source_selection']['word_safe_window'],[.2,1.2])
        self.assertAlmostEqual(snapshot['duration_seconds'],1.)
        self.assertEqual((snapshot['width'],snapshot['height']), (1080,1350))
        bundle=analysis.view(self.store,self.project['id']); item=bundle['analyses'][0]['analysis']
        for ratio,shape in [('9:16',(1080,1920)),('16:9',(1920,1080)),('1:1',(1080,1080))]:
            self.project=timeline.create(self.store,self.project['id'],self.project['revision'],{
                'analysis_id':item['analysis_id'],'transcript_id':item['transcript']['transcript_id'],
                'expected_version':self.project['shot_timeline']['version'],'aspect_ratio':ratio})
            self.assertEqual((self.project['shot_timeline']['snapshot']['width'],self.project['shot_timeline']['snapshot']['height']),shape)
        with self.assertRaises(WorkflowError):
            timeline.create(self.store,self.project['id'],self.project['revision'],{
                'analysis_id':item['analysis_id'],'transcript_id':item['transcript']['transcript_id'],
                'expected_version':self.project['shot_timeline']['version'],'source_window':(1.,1.01)})

    def test_shared_operations_lock_mute_source_bounds_cas_and_restore_new_version(self):
        self.create(); prior=deepcopy(self.project)
        clip=self.source_clip()
        self.edit([{'type':'split','clip_id':clip['clip_id'],'at_seconds':.8}])
        self.assertEqual(len(self.project['shot_timeline']['shots']),3)
        current=self.project
        with self.assertRaises(WorkflowError) as failed:
            timeline.edit(self.store,current['id'],current['revision'],{'expected_version':1,'operations':[{'type':'delete','clip_id':clip['clip_id']}]})
        self.assertEqual(failed.exception.code,'AUTO_EDIT_TIMELINE_VERSION_CHANGED')
        snapshot=self.project['shot_timeline']['snapshot']; track=next(value for value in snapshot['tracks'] if value['kind']=='source')
        self.edit([{'type':'set_track_state','track_id':track['track_id'],'locked':True}])
        with self.assertRaises(WorkflowError) as failed:
            self.edit([{'type':'move','clip_id':clip['clip_id'],'timeline_start':1.}])
        self.assertEqual(failed.exception.code,'AUTO_EDIT_TIMELINE_OPERATION_INVALID')
        self.edit([{'type':'set_track_state','track_id':track['track_id'],'locked':False}])
        with self.assertRaises(WorkflowError) as failed:
            self.edit([{'type':'trim','clip_id':clip['clip_id'],'source_end':4.}])
        self.assertEqual(failed.exception.code,'AUTO_EDIT_TIMELINE_SOURCE_WINDOW_INVALID')
        audio=next(value for value in snapshot['tracks'] if value['type']=='audio')
        self.edit([{'type':'set_track_state','track_id':audio['track_id'],'muted':True}])
        restored=timeline.restore(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'restore_revision':prior['revision']})
        self.assertEqual(restored['shot_timeline']['snapshot'],prior['shot_timeline']['snapshot'])
        self.assertGreater(restored['shot_timeline']['version'],prior['shot_timeline']['version'])
        self.assertIsNone(restored['approval'])

    def test_transcript_edit_updates_same_canonical_version_atomically(self):
        self.create(); before=deepcopy(self.project['shot_timeline']['snapshot'])
        bundle=analysis.view(self.store,self.project['id']); item=bundle['analyses'][0]['analysis']
        body={'expected_version':1,'expected_timeline_version':1,
            'segments':[{'segment_id':item['transcript']['segments'][0]['segment_id'],'text':'Vang Nguyễn.'}]}
        result=analysis.edit_transcript(self.store,self.project['id'],self.project['revision'],item['analysis_id'],body)
        self.project=timeline.view(self.store,self.project['id'])
        self.assertEqual(self.project['shot_timeline']['version'],2)
        self.assertEqual(result['source_timeline_version'],2)
        cues=[clip for track in self.project['shot_timeline']['snapshot']['tracks'] if track['kind']=='subtitles' for clip in track['clips']]
        self.assertEqual(cues[0]['metadata']['subtitle_text'],'Vang Nguyễn.')
        self.assertEqual(cues[0]['metadata']['measured_source_words'],[])
        for track in before['tracks']:
            if track['type']!='text':
                self.assertEqual(track,next(value for value in self.project['shot_timeline']['snapshot']['tracks'] if value['track_id']==track['track_id']))

    def test_locked_captions_roll_back_transcript_and_timeline_together(self):
        self.create()
        subtitles=next(value for value in self.project['shot_timeline']['snapshot']['tracks'] if value['kind']=='subtitles')
        self.edit([{'type':'set_track_state','track_id':subtitles['track_id'],'locked':True}])
        bundle=analysis.view(self.store,self.project['id']); item=bundle['analyses'][0]['analysis']
        before=self.store.versions(self.project['id'])
        with self.assertRaises(WorkflowError) as failed:
            analysis.edit_transcript(self.store,self.project['id'],self.project['revision'],item['analysis_id'],{
                'expected_version':1,'expected_timeline_version':2,
                'segments':[{'segment_id':item['transcript']['segments'][0]['segment_id'],'text':'Edited.'}]})
        self.assertEqual(failed.exception.code,'AUTO_EDIT_SUBTITLE_TRACK_LOCKED')
        self.assertEqual(self.store.versions(self.project['id']),before)
        self.assertEqual(analysis.view(self.store,self.project['id']),bundle)

    def test_legacy_tts_dispatch_and_projections_cannot_overwrite_source_timeline(self):
        self.create(); before=deepcopy(self.project['document'])
        for kind in ('content','render'):
            with self.assertRaises(WorkflowError) as failed:
                self.store.enqueue(self.project['id'],self.project['revision'],kind,uuid.uuid4().hex)
            self.assertEqual(failed.exception.code,'AUTO_EDIT_SOURCE_RENDER_PATH_REQUIRED')
        with self.assertRaises(WorkflowError):
            self.store.mutate_shots(self.project['id'],self.project['revision'],{'type':'delete','shot_id':self.source_clip()['clip_id']})
        self.assertEqual(self.store.get(self.project['id'])['document'],before)
        asset={**self.asset,'id':uuid.uuid4().hex+'.mp4','sha256':'b'*64}
        project=self.store.append_media(self.project['id'],self.project['revision'],asset)
        self.assertEqual(project['document']['canonical_timeline'],before['canonical_timeline'])
        self.assertEqual(len(project['document']['assets']),2)
        with self.assertRaises(WorkflowError) as failed:
            Pipeline(self.config).run({'id':uuid.uuid4().hex,'kind':'render','snapshot':{'document':project['document']}},lambda value:None)
        self.assertEqual(failed.exception.code,'AUTO_EDIT_SOURCE_RENDER_PATH_REQUIRED')
        previews=PreviewManager(self.config,self.store)
        try:
            with self.assertRaises(WorkflowError) as failed:
                previews.generate(project['id'],project['revision'])
            self.assertEqual(failed.exception.code,'AUTO_EDIT_SOURCE_PREVIEW_PATH_REQUIRED')
        finally:previews.close()


if __name__=='__main__':
    unittest.main()
