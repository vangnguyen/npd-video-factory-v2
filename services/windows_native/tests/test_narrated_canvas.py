"""Actual compact narrated MP4/ASS masks; fixtures are not human acceptance."""
import copy
import json
import unittest
from pydantic import ValidationError
from services.windows_native.branding import catalog,choose,resolve,VideoTemplate,FIT_NARRATION_POLICY
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.narrated_layout import layout
from services.windows_native.pipeline import render
from services.windows_native.north_star_quality import policy_reference
from services.windows_native.tests import test_storyboard_qc as fixtures


class NarratedCanvasTests(unittest.TestCase):
    setUp=fixtures.StoryboardQCTests.setUp
    tearDown=fixtures.StoryboardQCTests.tearDown
    output=fixtures.StoryboardQCTests.output

    def test_opt_in_catalog_preserves_existing_templates_and_all_four_geometries(self):
        old=catalog();expanded=catalog(include_all_formats=True)
        self.assertEqual(len(old['templates']),15);self.assertEqual(len(catalog(include_landscape=True)['templates']),30)
        self.assertEqual(len(expanded['templates']),60)
        self.assertEqual(expanded['templates'][:15],old['templates']);self.assertEqual({t['aspect_ratio'] for t in expanded['templates']},{'9:16','16:9','1:1','4:5'})
        for t in expanded['templates']:
            selection=choose('vf-reference',t['id']);self.assertEqual(selection['template'],t)
            self.assertEqual(selection['template_sha256'],digest(t))

    def test_invalid_canvas_pairs_and_unreviewed_legacy_compact_path_fail(self):
        original=choose('vf-reference','personal-30-square')['template']
        for changes in [{'height':1920},{'width':1920},{'height':1024},{'aspect_ratio':'4:5'}]:
            with self.assertRaises(ValidationError):VideoTemplate.model_validate({**original,**changes})
        brand,_=resolve({'brand_template':choose('vf-reference','personal-30-square')})
        with self.assertRaisesRegex(WorkflowError,'REQUIRES_EDIT_PLAN'):layout('square',1080,1080,'1:1',brand,editable=False)
        with self.assertRaisesRegex(WorkflowError,'CANVAS_MISMATCH'):layout('vertical-short',1080,1080,'9:16',brand,editable=True)

    def test_existing_portrait_landscape_geometry_is_exact_and_new_regions_are_contained(self):
        brand,_=resolve(self.document)
        old=layout('vertical-short',1080,1920,'9:16',brand,editable=True)
        self.assertEqual((old['media_top'],old['plane_height'],old['caption_top'],old['footer_y'],old['subtitle_font_size']),(390,830,1320,1250,brand.subtitle_style.font_size))
        wide=layout('landscape',1920,1080,'16:9',brand,editable=True)
        self.assertEqual((wide['media_top'],wide['plane_height'],wide['caption_top'],wide['footer_y'],wide['subtitle_font_size']),(230,530,850,810,38))
        for profile,height,ratio in [('square',1080,'1:1'),('portrait-feed',1350,'4:5')]:
            g=layout(profile,1080,height,ratio,brand,editable=True)
            self.assertLess(g['media_top']+g['plane_height'],g['illustration_y']);self.assertLess(g['footer_y'],g['caption_top'])
            self.assertLess(g['caption_top'],height-g['safe_bottom']-10);self.assertEqual(g['plane_height']%2,0)

    def test_actual_square_and_feed_full_qc_keep_pcm_and_vietnamese_subtitle_pixels_inside(self):
        for suffix,width,height,ratio,profile in [('square',1080,1080,'1:1','square'),('feed',1080,1350,'4:5','portrait-feed')]:
            current=self.store.set_brand(self.project['id'],self.store.get(self.project['id'])['revision'],'vang-nguyen','personal-30-'+suffix,duration_mode=FIT_NARRATION_POLICY)
            doc=copy.deepcopy(current['document']);doc['production_quality']=policy_reference()
            snapshot={'document':doc,'approval':{'snapshot_sha256':digest(doc),'revision':current['revision'],'reviewer':'EXPLICIT COMPACT SYNTHETIC FIXTURE'}}
            out=self.output(suffix);source=file_sha(out/'voice.wav');report=render(self.config,snapshot,out)
            self.assertTrue(report['passed']);self.assertEqual(report['full_quality']['status'],'passed')
            self.assertTrue(report['checks']['square_1080x1080' if suffix=='square' else 'portrait_feed_1080x1350'])
            self.assertNotIn('landscape_1920x1080',report['checks'])
            self.assertEqual(file_sha(out/'voice.wav'),source)
            manifest=json.loads((out/'render-manifest.json').read_bytes());self.assertEqual(manifest['render_profile']['id'],profile)
            self.assertEqual((manifest['subtitle_layout']['width'],manifest['subtitle_layout']['height']),(width,height))
            ass=(out/'subtitles.ass').read_text(encoding='utf-8');self.assertIn(f'PlayResX: {width}',ass);self.assertIn(f'PlayResY: {height}',ass)
            self.assertTrue(all(s['inside_safe_area'] for s in report['full_quality']['subtitle_bounds']['samples']))
            self.assertFalse(report['full_quality']['human_final_video_accepted'])


if __name__=='__main__':unittest.main()
