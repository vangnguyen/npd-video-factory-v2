"""Canonical style decisions preserve source/media; fixtures never accept UAT."""
import copy,unittest
from services.windows_native.tests import test_source_linked_edit as source,test_narrated_video_timeline as narrated
from services.windows_native import auto_edit_timeline as timeline,narrated_timeline_editor as editor
from services.windows_native.contracts import WorkflowError

class SourceClipStyleTests(unittest.TestCase):
    setUp=source.SourceLinkedEditTests.setUp
    tearDown=source.SourceLinkedEditTests.tearDown
    save_analysis=source.SourceLinkedEditTests.save_analysis
    create=source.SourceLinkedEditTests.create
    source_clip=source.SourceLinkedEditTests.source_clip
    mutation=source.SourceLinkedEditTests.mutation
    tracks=source.SourceLinkedEditTests.tracks
    def test_visual_style_changes_only_the_selected_clip_and_preserves_other_tracks_and_sources(self):
        self.create();before=copy.deepcopy(self.project);clip=self.source_clip()
        self.mutation({'type':'set_clip_properties','clip_id':clip['clip_id'],'effects':[{'type':'brightness','value':.8},{'type':'saturation','value':.5}],
            'transition_in':{'kind':'slide','duration_seconds':.25},'transition_out':{'kind':'fade','duration_seconds':.25}})
        after=self.source_clip();self.assertEqual(after['effects'][0],{'type':'brightness','value':.8});self.assertEqual(after['metadata']['clip_style_schema'],'clip-style-v1')
        for key in ('source_start','source_end','timeline_start','duration','speed','crop','transform','opacity'):self.assertEqual(after[key],clip[key],key)
        self.assertEqual(self.project['shot_timeline']['snapshot']['tracks'][1:],before['shot_timeline']['snapshot']['tracks'][1:])
        self.assertEqual(self.project['document']['media_analysis'],before['document']['media_analysis']);self.assertIsNone(self.project['approval'])
    def test_invalid_catalog_duration_role_and_boolean_values_are_atomic(self):
        self.create();before=copy.deepcopy(self.project);clip=self.source_clip()
        for extra in [{'effects':[{'type':'script','value':1}]},{'effects':[{'type':'blur','value':.1}]},{'effects':[{'type':'brightness','value':True}]},
            {'transition_out':{'kind':'fade','duration_seconds':5}},{'transition_in':{'kind':'cut','duration_seconds':.1}}]:
            with self.assertRaises(WorkflowError):self.mutation({'type':'set_clip_properties','clip_id':clip['clip_id'],**extra})
            self.assertEqual(timeline.view(self.store,self.project['id']),before)
        audio=self.tracks()[1]['clips'][0]
        with self.assertRaises(WorkflowError):timeline.edit(self.store,self.project['id'],self.project['revision'],{'expected_version':self.project['shot_timeline']['version'],
            'operations':[{'type':'set_clip_properties','clip_id':audio['clip_id'],'effects':[]}]})
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
    def test_outgoing_crossfade_requires_contiguous_peer_and_restore_preserves_snapshot(self):
        self.create();before=copy.deepcopy(self.project);main=self.tracks()[0]
        self.mutation({'type':'set_clip_properties','clip_id':main['clips'][0]['clip_id'],'transition_out':{'kind':'crossfade','duration_seconds':.25}})
        saved=copy.deepcopy(self.project)
        with self.assertRaises(WorkflowError):self.mutation({'type':'set_clip_properties','clip_id':main['clips'][-1]['clip_id'],'transition_out':{'kind':'crossfade','duration_seconds':.25}})
        self.assertEqual(timeline.view(self.store,self.project['id']),saved)
        restored=timeline.restore(self.store,self.project['id'],self.project['revision'],{'expected_version':self.project['shot_timeline']['version'],'restore_revision':before['revision']})
        self.assertEqual(restored['document']['canonical_timeline']['sha256'],before['document']['canonical_timeline']['sha256']);self.assertIsNone(restored['approval'])

class NarratedClipStyleTests(unittest.TestCase):
    setUp=narrated.NarratedVideoTimelineTests.setUp
    tearDown=narrated.NarratedVideoTimelineTests.tearDown
    start=narrated.NarratedVideoTimelineTests.start
    finish=narrated.NarratedVideoTimelineTests.finish
    body=narrated.NarratedVideoTimelineTests.body
    binding=narrated.NarratedVideoTimelineTests.binding
    page=narrated.NarratedVideoTimelineTests.page
    subtitle_body=narrated.NarratedVideoTimelineTests.subtitle_body
    current=narrated.NarratedVideoTimelineTests.current
    edit=narrated.NarratedVideoTimelineTests.edit
    def test_visual_style_uses_canonical_video_engine_without_changing_measured_voice(self):
        initial=self.current();clip=initial['snapshot']['tracks'][0]['clips'][0]
        out=self.edit([{'type':'set_clip_properties','clip_id':clip['clip_id'],'effects':[{'type':'contrast','value':1.2}],
            'transition_out':{'kind':'fade','duration_seconds':.25}}])
        self.assertEqual(out['snapshot']['tracks'][0]['clips'][0]['effects'],[{'type':'contrast','value':1.2}])
        for kind in ('voice','subtitles'):self.assertEqual([t for t in out['snapshot']['tracks'] if t['kind']==kind],[t for t in initial['snapshot']['tracks'] if t['kind']==kind])
    def test_measured_voice_cannot_bypass_protection_by_combining_gain_with_effect_or_transition(self):
        page=self.current();voice=next(c for t in page['snapshot']['tracks'] if t['kind']=='voice' for c in t['clips'] if c['metadata'].get('narrated_generated_voice'))
        before=self.store.get(self.project['id'])
        for extra in [{'effects':[]},{'transition_out':{'kind':'fade','duration_seconds':.25}}]:
            with self.assertRaises(WorkflowError):self.edit([{'type':'set_clip_properties','clip_id':voice['clip_id'],'volume':.8,**extra}])
            self.assertEqual(self.store.get(self.project['id']),before)
