import copy
import unittest
from services.windows_native import source_settings as settings
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native import auto_edit_analysis as analysis
from services.windows_native.tests import test_auto_edit_timeline as fixture
from services.windows_native.contracts import WorkflowError
from app.subtitle_templates import load_templates


class SourceSettingsTests(unittest.TestCase):
    setUp=fixture.NativeSourceTimelineTests.setUp
    tearDown=fixture.NativeSourceTimelineTests.tearDown
    save_analysis=fixture.NativeSourceTimelineTests.save_analysis
    create=fixture.NativeSourceTimelineTests.create

    def configure(self,**values):
        self.project=settings.configure(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],**values})
        return self.project

    def test_four_canvases_and_seven_full_versioned_styles_use_same_snapshot(self):
        self.create();clips=copy.deepcopy(self.project['shot_timeline']['snapshot']['tracks'])
        for ratio,shape in [('9:16',(1080,1920)),('16:9',(1920,1080)),('1:1',(1080,1080)),('4:5',(1080,1350))]:
            self.configure(aspect_ratio=ratio);snapshot=self.project['shot_timeline']['snapshot']
            self.assertEqual((snapshot['width'],snapshot['height']),shape);self.assertEqual(snapshot['tracks'],clips)
        for template in load_templates():
            self.configure(subtitle_template_ref=template['template_ref'],keywords=['Cơ hội'])
            style=self.project['shot_timeline']['snapshot']['metadata']['subtitle_style']
            self.assertEqual(style['template_ref'],template['template_ref']);self.assertEqual(style['keywords'],['Cơ hội'])
        self.assertIsNone(self.project['approval'])

    def test_edited_words_cannot_acquire_invented_timed_effects(self):
        self.create();bundle=analysis.view(self.store,self.project['id']);transcript=bundle['analyses'][0]['analysis']['transcript']
        analysis.edit_transcript(self.store,self.project['id'],bundle['revision'],transcript['analysis_id'],{
            'expected_version':1,'expected_timeline_version':1,'segments':[{'segment_id':transcript['segments'][0]['segment_id'],'text':'Vang Nguyễn.'}]})
        self.project=timeline.view(self.store,self.project['id']);before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'WORD_ALIGNMENT_UNAVAILABLE'):
            self.configure(subtitle_template_ref='karaoke-gold@v1')
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        self.configure(subtitle_template_ref='sentence-clean@v1')

    def test_unknown_template_and_locked_captions_do_not_mutate(self):
        self.create();before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'SUBTITLE_TEMPLATE_UNKNOWN'):self.configure(subtitle_template_ref='arbitrary-graph')
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        captions=next(track for track in self.project['shot_timeline']['snapshot']['tracks'] if track['kind']=='subtitles')
        self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{
            'expected_version':1,'operations':[{'type':'set_track_state','track_id':captions['track_id'],'locked':True}]})
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_SUBTITLE_TRACK_LOCKED'):self.configure(subtitle_template_ref='sentence-clean@v1')


if __name__=='__main__':unittest.main()
