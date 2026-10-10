"""Real libass font/animation pixels with explicit word fixtures, not ASR/UAT."""
import copy,json,subprocess,unittest
from unittest.mock import patch
from PIL import Image
from services.windows_native.tests import test_narrated_media_tracks as fixture
from services.windows_native import source_media_tracks as media,narrated_media_timeline as tracks,narrated_media_captions as captions
from services.windows_native.contracts import WorkflowError,digest,file_sha
from app.subtitle_templates import load_templates

class NarratedMediaCaptionTests(unittest.TestCase):
    start=fixture.NarratedMediaTracksTests.start;finish=fixture.NarratedMediaTracksTests.finish;body=fixture.NarratedMediaTracksTests.body
    binding=fixture.NarratedMediaTracksTests.binding;audio_body=fixture.NarratedMediaTracksTests.audio_body
    def setUp(self):
        fixture.prepare(self);media.add_audio(self.store,self.project['id'],self.audio_body(),actor_ref='explicit-editor-fixture')
        self.document=self.store.get(self.project['id'])['document']
    tearDown=fixture.NarratedMediaTracksTests.tearDown
    def cue(self,template,word_timing=True,text='Vang Nguyễn'):
        doc=copy.deepcopy(self.document);snapshot=doc['canonical_timeline']['snapshot'];track=next(t for t in snapshot['tracks'] if t['track_id']==tracks.CAPTION_TRACK)
        clip=copy.deepcopy(track['clips'][0]);clip.update(label=text,timeline_start=.1,duration=1,source_start=0,source_end=1)
        clip['metadata']={'explicit_test_fixture':True,'human_caption_edit':True,'timing_source':'provided_WORD_FIXTURE_not_provider',
            'measured_source_words':[{'text':'Vang','start_seconds':0,'end_seconds':.45},{'text':'Nguyễn','start_seconds':.5,'end_seconds':1}] if word_timing else []}
        track['clips']=[clip];snapshot['metadata']['subtitle_style']=copy.deepcopy(template['style']);snapshot['metadata']['subtitle_template_ref']=template['template_ref']
        if template['style']['animation']=='keyword_highlight':snapshot['metadata']['subtitle_style']['keywords']=['Vang']
        doc['canonical_timeline']['sha256']=digest(snapshot);return doc
    def pixels(self,out,time):
        target=out/('frame-'+str(time)+'.png')
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','color=c=black:s=1080x1920:r=30:d=1.2',
            '-vf','ass=subtitles.ass:fontsdir=fonts','-ss',str(time),'-frames:v','1',target.name],cwd=out,capture_output=True,check=True,timeout=30)
        with Image.open(target) as image:
            pixels=np.asarray(image.convert('RGB'));visible=np.any(pixels!=0,axis=2)
            self.assertGreater(np.count_nonzero(visible),500)
            rows,cols=np.where(visible);self.assertGreaterEqual(int(cols.min()),70);self.assertLess(int(cols.max()),1010)
            self.assertGreaterEqual(int(rows.min()),90);self.assertLess(int(rows.max()),1740)
        return file_sha(target)
    def test_actual_libass_catalog_templates_render_Vietnamese_with_word_fixtures_and_visible_animations(self):
        for i,template in enumerate(load_templates()):
            with self.subTest(template=template['template_ref']):
                doc=self.cue(template);out=self.owned/('caption-'+str(i));out.mkdir();result=captions.render(doc,out,1080,1920,[70,90,1010,1740])
                self.assertEqual(len(result),1);a=self.pixels(out,.3);b=self.pixels(out,.8)
                if template['style']['animation'] in {'word_by_word','word_highlight','karaoke'}:self.assertNotEqual(a,b)
                meta=json.loads((out/'subtitles.json').read_bytes());self.assertFalse(meta['word_alignment_inferred']);self.assertEqual(meta['font_sha256'],captions.FONT_SHA)
    def test_missing_word_timing_or_mismatched_text_is_rejected_before_output(self):
        template=next(t for t in load_templates() if t['style']['animation']=='karaoke')
        for doc in [self.cue(template,False),self.cue(template,True,'Chữ khác nguồn')]:
            out=self.owned/'invalid-caption'
            with self.assertRaisesRegex(WorkflowError,'WORD_ALIGNMENT'):
                if not out.exists():out.mkdir()
                captions.render(doc,out,1080,1920,[70,90,1010,1740])
            self.assertFalse((out/'subtitles.ass').exists())
    def test_human_ASS_syntax_is_plain_text_and_font_drift_is_rejected(self):
        template=next(t for t in load_templates() if not t['requires_word_timestamps']);doc=self.cue(template,False,'Vang {\\pos(0,0)} Nguyễn')
        out=self.owned/'plain-caption';out.mkdir();captions.render(doc,out,1080,1920,[70,90,1010,1740])
        body=(out/'subtitles.ass').read_text(encoding='utf-8');self.assertNotIn('{\\pos(0,0)}',body);self.assertIn('Nguyễn',body)
        bad=self.owned/'drift-caption';bad.mkdir()
        with patch.object(captions,'FONT_SHA',{'NotoSans.ttf':'0'*64}),self.assertRaisesRegex(WorkflowError,'FONT_CHANGED'):captions.render(doc,bad,1080,1920,[70,90,1010,1740])

import numpy as np
