"""Atomic linked source decisions over fixture evidence; no provider/UAT claim."""
import copy
import json
import unittest

from services.windows_native import source_linked_edit as linked
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native.tests import test_auto_edit_timeline as fixture
from services.windows_native.contracts import WorkflowError


class SourceLinkedEditTests(unittest.TestCase):
    setUp=fixture.NativeSourceTimelineTests.setUp
    tearDown=fixture.NativeSourceTimelineTests.tearDown
    save_analysis=fixture.NativeSourceTimelineTests.save_analysis
    create=fixture.NativeSourceTimelineTests.create
    source_clip=fixture.NativeSourceTimelineTests.source_clip

    def mutation(self,operation):
        self.project=linked.edit(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'operation':operation})
        return self.project

    def tracks(self):
        tracks=self.project['shot_timeline']['snapshot']['tracks']
        return (next(track for track in tracks if track['kind']=='source'),
            next(track for track in tracks if track['kind']=='original_audio'),
            next(track for track in tracks if track['kind']=='subtitles'))

    def assert_audio_matches(self):
        main,audio,_=self.tracks()
        fields=('source_start','source_end','timeline_start','duration','speed','disabled')
        self.assertEqual([tuple(clip[key] for key in fields) for clip in main['clips']],
            [tuple(clip[key] for key in fields) for clip in audio['clips']])

    def test_trim_extends_complete_word_and_preserves_gain_mute_text_and_raw(self):
        self.create();main,audio,captions=self.tracks();raw=copy.deepcopy(self.project['document']['media_analysis'])
        self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{'expected_version':1,'operations':[
            {'type':'set_clip_properties','clip_id':audio['clips'][0]['clip_id'],'volume':.4},
            {'type':'set_track_state','track_id':audio['track_id'],'muted':True}]})
        self.mutation({'type':'trim','clip_id':main['clips'][0]['clip_id'],'source_start':.3,'source_end':1.1})
        main,audio,captions=self.tracks();clip=main['clips'][0]
        self.assertEqual((clip['source_start'],clip['source_end']),(.2,1.2));self.assert_audio_matches()
        self.assertEqual(audio['clips'][0]['volume'],.4);self.assertTrue(audio['muted'])
        self.assertEqual(captions['clips'][0]['label'],'Xin chào.')
        self.assertEqual(len(captions['clips'][0]['metadata']['measured_source_words']),2)
        self.assertEqual(self.project['document']['media_analysis'],raw);self.assertIsNone(self.project['approval'])

    def test_split_reorder_duplicate_disable_delete_keep_av_and_caption_time(self):
        self.create();clip=self.source_clip()
        self.mutation({'type':'split','clip_id':clip['clip_id'],'at_seconds':1.3});self.assert_audio_matches()
        main,_,_=self.tracks();self.assertEqual(len(main['clips']),3)
        self.mutation({'type':'reorder','clip_id':main['clips'][-1]['clip_id'],'target_index':0});self.assert_audio_matches()
        main,_,captions=self.tracks();self.assertEqual(main['clips'][0]['source_start'],1.5)
        self.assertEqual(captions['clips'][0]['timeline_start'],.5)
        self.mutation({'type':'duplicate','clip_id':main['clips'][0]['clip_id']});self.assert_audio_matches()
        main,_,_=self.tracks();duplicate=main['clips'][-1]
        self.mutation({'type':'disable','clip_id':duplicate['clip_id'],'disabled':True});self.assert_audio_matches()
        self.mutation({'type':'delete','clip_id':duplicate['clip_id']});self.assert_audio_matches()
        self.assertFalse(self.project['document']['canonical_timeline']['snapshot']['source_media_mutated'])

    def test_split_inside_word_or_locked_linked_track_rolls_back(self):
        self.create();before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_SPLIT_TOUCHES_SPOKEN_WORD'):
            self.mutation({'type':'split','clip_id':self.source_clip()['clip_id'],'at_seconds':.4})
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        _,_,captions=self.tracks()
        self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{
            'expected_version':1,'operations':[{'type':'set_track_state','track_id':captions['track_id'],'locked':True}]})
        before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_LINKED_TRACK_LOCKED'):
            self.mutation({'type':'trim','clip_id':self.source_clip()['clip_id'],'source_end':1.3})
        self.assertEqual(timeline.view(self.store,self.project['id']),before)

    def test_independent_audio_edit_is_never_silently_reset(self):
        self.create();main,audio,_=self.tracks()
        self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{'expected_version':1,
            'operations':[{'type':'move','clip_id':audio['clips'][0]['clip_id'],'timeline_start':.1}]})
        before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_LINKED_AUDIO_DIVERGED'):
            self.mutation({'type':'trim','clip_id':main['clips'][0]['clip_id'],'source_end':1.3})
        self.assertEqual(timeline.view(self.store,self.project['id']),before)

    def test_move_ripples_without_gaps_and_speed_preserves_original_audio(self):
        self.create();main,_,_=self.tracks();first=main['clips'][0]['clip_id']
        self.mutation({'type':'move','clip_id':first,'timeline_start':99})
        main,_,captions=self.tracks();self.assertEqual(main['clips'][-1]['clip_id'],first)
        self.assertEqual(main['clips'][0]['timeline_start'],0);self.assert_audio_matches()
        self.assertEqual(captions['clips'][0]['timeline_start'],.5)
        self.mutation({'type':'set_clip_properties','clip_id':first,'speed':2})
        main,_,_=self.tracks();self.assert_audio_matches()
        self.assertEqual(main['clips'][-1]['duration'],.75)
        self.assertEqual(self.project['shot_timeline']['snapshot']['duration_seconds'],2.25)

    def test_no_audio_source_keeps_no_audio_and_allows_word_safe_trim(self):
        self.metadata=self.metadata.model_copy(update={'audio_codec':None})
        with self.store.transaction() as con:
            project=self.store.editable(con,self.project['id'],self.project['revision'])
            project['document']['assets'][0]['has_audio']=False
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',
                (json.dumps(project['document']),project['id']))
            self.store.version(con,project['id'])
        self.project=self.store.get(self.project['id']);self.create()
        self.mutation({'type':'trim','clip_id':self.source_clip()['clip_id'],'source_start':.3,'source_end':1.1})
        _,audio,_=self.tracks();self.assertEqual(audio['clips'],[])
        self.assertFalse(self.project['shot_timeline']['snapshot']['metadata']['linked_source_edit']['source_audio_synchronized'])

    def test_revision_version_and_unknown_client_identity_do_not_mutate(self):
        self.create();body={'expected_version':999,'operation':{'type':'delete','clip_id':self.source_clip()['clip_id']}}
        before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_TIMELINE_VERSION_CHANGED'):
            linked.edit(self.store,self.project['id'],self.project['revision'],body)
        body['expected_version']=1;body['actor_ref']='forged'
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_TIMELINE_REQUEST_INVALID'):
            linked.edit(self.store,self.project['id'],self.project['revision'],body)
        self.assertEqual(timeline.view(self.store,self.project['id']),before)


if __name__=='__main__':unittest.main()
