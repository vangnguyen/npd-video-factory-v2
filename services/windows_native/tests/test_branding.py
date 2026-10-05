"""Reference configuration fixtures, never official assets or human acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from services.windows_native import branding
from services.windows_native.contracts import WorkflowError, PROFILE_SHA, digest, file_sha
from services.windows_native.editor import validate_plan
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal


class BrandingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.store=Store(self.root); self.config=Config(data_root=self.root)
        self.p=self.store.create("Brand fixture","No provider calls")
        directory=self.root/"assets"; directory.mkdir(); self.asset_id="a"*32+".jpg"
        Image.new("RGB",(320,240),"green").save(directory/self.asset_id)
        self.p=self.store.save(self.p["id"],1,proposal=proposal(),asset={"id":self.asset_id,"kind":"image","sha256":file_sha(directory/self.asset_id),"rights_confirmed":True})
        self.p=self.store.auto_plan(self.p["id"],self.p["revision"])

    def tearDown(self): self.temp.cleanup()

    def test_two_seed_profiles_twelve_templates_reference_assets_and_locked_voice(self):
        values=branding.catalog(); self.assertEqual(len(values["templates"]),12)
        self.assertEqual({v["purpose"] for v in values["templates"]},{"property_presentation","news_update","personal_brand","event_promo"})
        self.assertEqual({v["duration_seconds"] for v in values["templates"]},{30,45,60})
        for profile in values["brands"]:
            self.assertIsNone(profile["logo"]); self.assertIsNone(profile["music_profile"]["default_track"])
            self.assertEqual(profile["voice_profile_sha256"],PROFILE_SHA)
        self.assertEqual({b["id"] for b in values["brands"] if b["asset_status"]=="reference_only_official_assets_missing"},{"ngoc-phuong-dong","vang-nguyen"})

    def test_selection_frozen_despite_later_catalog_changes_and_restart(self):
        p=self.store.set_brand(self.p["id"],self.p["revision"],"ngoc-phuong-dong","property-30")
        selected=p["document"]["brand_template"]; self.assertEqual(Store(self.root).get(p["id"])["document"]["brand_template"],selected)
        altered=json.loads(branding.CATALOG.read_bytes()); altered["brands"][1]["primary_cta"]="New later config"
        catalog_path=self.root/"later-catalog.json"; catalog_path.write_text(json.dumps(altered),encoding="utf-8")
        with patch.object(branding,"CATALOG",catalog_path):
            self.assertEqual(branding.resolve(p["document"])[0].primary_cta,selected["brand"]["primary_cta"])
        self.assertEqual(validate_plan(p["document"])["brand_template_sha256"],digest(selected))

    def test_style_change_preserves_scene_choices_and_invalidates_approval(self):
        p=self.store.approve(self.p["id"],self.p["revision"],"UNIT FIXTURE — NOT HUMAN ACCEPTANCE",True)
        choices=copy.deepcopy(p["document"]["scene_media"])
        p=self.store.set_brand(p["id"],p["revision"],"vang-nguyen","personal-45")
        self.assertIsNone(p["approval"]); self.assertEqual(p["document"]["scene_media"],choices)
        self.assertEqual(p["document"]["edit_plan"]["cta"],p["document"]["brand_template"]["brand"]["primary_cta"])
        self.assertAlmostEqual(p["document"]["edit_plan"]["scenes"][-1]["end_target"],45)
        with self.assertRaisesRegex(WorkflowError,"STALE"): self.store.set_brand(p["id"],p["revision"]-1,"vang-nguyen","personal-45")

    def test_bad_ids_mutated_style_voice_font_and_hash_refused_without_fallback(self):
        with self.assertRaisesRegex(WorkflowError,"CHOICE_REQUIRED"): branding.choose("missing","property-30")
        value=branding.choose("vang-nguyen","personal-45")
        for key,bad in [("voice_profile_sha256","other-voice"),("palette",{**value["brand"]["palette"],"background":"bad-filter-expression"}),("fonts",{**value["brand"]["fonts"],"body":"../secret"})]:
            changed=copy.deepcopy(value); changed["brand"][key]=bad
            with self.assertRaisesRegex(WorkflowError,"CHANGED_OR_INVALID"): branding.resolve({"brand_template":changed})
        changed=copy.deepcopy(value); changed["brand"]["primary_cta"]="Changed but unhashed"
        with self.assertRaisesRegex(WorkflowError,"CHANGED_OR_INVALID"): branding.resolve({"brand_template":changed})

    def test_target_durations_voice_speed_preserved_and_overflow_explicit(self):
        for target in (30,45,60):
            doc={"brand_template":branding.choose("ngoc-phuong-dong",f"property-{target}")}
            self.assertEqual(branding.measured_duration(doc,20.86),target)
            with self.assertRaisesRegex(WorkflowError,"NARRATION_TOO_LONG"): branding.measured_duration(doc,target)
            with self.assertRaisesRegex(WorkflowError,"DURATION_INVALID"): branding.measured_duration(doc,float("nan"))

    def test_logo_rights_and_source_hash_are_checked(self):
        choice=branding.choose("ngoc-phuong-dong","property-30"); choice["brand"]["logo"]=self.asset_id
        choice["brand_sha256"]=digest(choice["brand"]); doc={**self.p["document"],"brand_template":choice}
        self.assertEqual(branding.validate_assets(self.config,doc).logo,self.asset_id)
        (self.root/"assets"/self.asset_id).write_bytes(b"changed")
        with self.assertRaisesRegex(WorkflowError,"LOGO_SOURCE_CHANGED"): branding.validate_assets(self.config,doc)

    def test_legacy_document_projection_does_not_rewrite_or_add_brand(self):
        doc=self.p["document"]; before=digest(doc); _,template=branding.resolve(doc)
        self.assertIsNone(template); self.assertEqual(digest(doc),before); self.assertNotIn("brand_template",doc)

