"""Scoped shot edits use temporary data and explicit fixture decisions only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.shot_adapter import shots, validate_document
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal


class ShotAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        p = self.store.create("Explicit shot fixture", "Not a provider integration")
        self.assets = [{"id": f"fixture_{i}.jpg", "kind": "image", "sha256": str(i) * 64,
            "rights_confirmed": True, "filename": f"Fixture {i}", "illustration": False} for i in range(4)]
        self.project = self.store.save(p["id"], p["revision"], proposal=proposal(), asset=self.assets[0])
        for asset in self.assets[1:]:
            self.project = self.store.append_media(self.project["id"], self.project["revision"], asset)

    def tearDown(self):
        self.temp.cleanup()

    def edit(self, operation):
        self.project = self.store.mutate_shots(self.project["id"], self.project["revision"], operation)
        return self.project

    def cards(self):
        return self.store.shot_view(self.project["id"])["shot_timeline"]["shots"]

    def start(self):
        card = self.cards()[0]
        return self.edit({"type": "update", "shot_id": card["id"], "values": {"visual": card["visual"]}})

    def database_state(self):
        with self.store.transaction() as con:
            return {name: [tuple(r) for r in con.execute("SELECT * FROM " + name + " ORDER BY rowid")]
                for name in ("projects", "project_versions", "events", "jobs")}

    def test_legacy_read_is_nonwriting_and_durations_are_estimates(self):
        before = self.database_state()
        view = self.store.shot_view(self.project["id"])
        self.assertEqual(self.database_state(), before)
        self.assertFalse(view["shot_timeline"]["persisted"])
        self.assertEqual(view["shot_timeline"]["version"], 0)
        self.assertEqual(len(view["shot_timeline"]["shots"]), 3)
        self.assertTrue(all(s["requested_duration"] is None for s in view["shot_timeline"]["shots"]))
        self.assertNotIn("canonical_timeline", view["document"])

    def test_asset_edit_is_scoped_and_keeps_other_shots_and_script_decision(self):
        self.start()
        self.store.review_script(self.project["id"], self.project["revision"], "TEST FIXTURE", True,
            __import__("hashlib").sha256(self.project["document"]["proposal"]["narration"].encode()).hexdigest())
        self.project = self.store.approve(self.project["id"], self.project["revision"], "TEST FIXTURE", True)
        before = self.cards()
        result = self.edit({"type": "update", "shot_id": before[0]["id"], "values": {"asset_id": self.assets[1]["id"]}})
        after = self.cards()
        self.assertEqual(before[1:], after[1:])
        self.assertEqual(result["shot_timeline"]["scope"]["voice_dependency_shot_ids"], [])
        self.assertEqual(result["shot_timeline"]["scope"]["visual_dependency_shot_ids"], [before[0]["id"]])
        self.assertIsNone(result["approval"])
        with self.store.transaction() as con:
            self.assertTrue(self.store.current_script_review(con, result)["current"])
        self.assertEqual(result["jobs"], [])

    def test_narration_changes_only_target_and_following_warm_context(self):
        self.start()
        before = self.cards()
        result = self.edit({"type": "update", "shot_id": before[0]["id"], "values": {"narration": "Lời đọc mới."}})
        self.assertEqual(result["shot_timeline"]["scope"]["voice_dependency_shot_ids"], [before[0]["id"], before[1]["id"]])
        self.assertEqual(before[1:], self.cards()[1:])
        self.assertTrue(result["document"]["proposal"]["narration"].startswith("Lời đọc mới."))

    def test_default_subtitles_follow_narration_and_custom_or_explicit_captions_remain_authoritative(self):
        self.start()
        identifier = self.cards()[0]["id"]
        self.edit({"type": "update", "shot_id": identifier, "values": {"narration": "Lời đọc thay đổi."}})
        self.assertEqual(self.cards()[0]["subtitle"], "Lời đọc thay đổi.")
        self.edit({"type": "update", "shot_id": identifier, "values": {"narration": "Lời đọc lần hai.", "subtitle": "Phụ đề riêng."}})
        self.edit({"type": "update", "shot_id": identifier, "values": {"narration": "Lời đọc lần ba."}})
        self.assertEqual(self.cards()[0]["subtitle"], "Phụ đề riêng.")
        following = self.cards()[1]
        modified = copy.deepcopy(self.project["document"]["proposal"])
        modified["visual_brief"][1]["narration_excerpt"] = "Đoạn mới qua API cũ."
        modified["narration"] = " ".join(s["narration_excerpt"] for s in modified["visual_brief"])
        self.project = self.store.save(self.project["id"], self.project["revision"], proposal=modified)
        self.assertEqual(self.cards()[1]["id"], following["id"])
        self.assertEqual(self.cards()[1]["subtitle"], "Đoạn mới qua API cũ.")
        self.assertEqual(self.cards()[0]["subtitle"], "Phụ đề riêng.")

    def test_duration_is_explicit_and_retimes_successors_without_voice_regeneration(self):
        self.start()
        before = self.cards()
        result = self.edit({"type": "update", "shot_id": before[0]["id"], "values": {"duration": 4.5}})
        self.assertEqual(self.cards()[0]["requested_duration"], 4.5)
        self.assertEqual(result["shot_timeline"]["scope"]["voice_dependency_shot_ids"], [])
        self.assertEqual(result["shot_timeline"]["scope"]["retimed_shot_ids"], [s["id"] for s in before[1:]])
        self.assertEqual(result["shot_timeline"]["version"], 2)

    def test_reorder_moves_narration_media_and_options_together_with_stable_ids(self):
        self.start()
        before = self.cards()
        reverse = [s["id"] for s in reversed(before)]
        result = self.edit({"type": "reorder", "shot_ids": reverse})
        self.assertEqual([s["id"] for s in self.cards()], reverse)
        self.assertEqual([s["narration"] for s in self.cards()], [s["narration"] for s in reversed(before)])
        self.assertTrue(result["shot_timeline"]["scope"]["order_changed"])
        self.assertEqual([s["scene"] for s in result["document"]["proposal"]["visual_brief"]], [1, 2, 3])
        clips = result["shot_timeline"]["snapshot"]["tracks"][0]["clips"]
        self.assertEqual(clips[1]["timeline_start"], clips[0]["duration"])

    def test_duplicate_and_delete_support_more_than_five_then_enforce_twenty_limit(self):
        self.start()
        identifier = self.cards()[0]["id"]
        for _ in range(17):
            self.edit({"type": "duplicate", "shot_id": identifier})
        cards = self.cards()
        self.assertEqual(len(cards), 20)
        self.assertEqual(len({s["id"] for s in cards}), 20)
        before = self.database_state()
        with self.assertRaisesRegex(WorkflowError, "SHOT_COUNT_LIMIT"):
            self.edit({"type": "duplicate", "shot_id": identifier})
        self.assertEqual(self.database_state(), before)
        self.edit({"type": "delete", "shot_id": cards[1]["id"]})
        self.assertEqual(len(self.cards()), 19)

    def test_disabled_narration_preserves_editable_text_and_project_coverage(self):
        self.start()
        before = self.cards()
        result = self.edit({"type": "update", "shot_id": before[1]["id"], "values": {"narration_enabled": False}})
        self.assertEqual(self.cards()[1]["narration"], before[1]["narration"])
        self.assertEqual(result["document"]["proposal"]["visual_brief"][1]["narration_excerpt"], "")
        self.assertNotIn(before[1]["narration"], result["document"]["proposal"]["narration"])
        self.edit({"type": "update", "shot_id": before[1]["id"], "values": {"narration_enabled": True}})
        self.assertEqual(self.cards()[1]["narration"], before[1]["narration"])

    def test_invalid_edits_rollback_without_events_or_provider_jobs(self):
        self.start()
        identifier = self.cards()[0]["id"]
        operations = [{"type": "update", "shot_id": identifier, "values": values} for values in
            ({"duration": -1}, {"duration": True}, {"duration": float("nan")}, {"narration_enabled": 1},
             {"asset_id": "other-project.jpg"}, {"source_start": .2}, {"unexpected": "field"})]
        operations += [{"type": "reorder", "shot_ids": [{"bad": "id"}]}, {"type": "reorder", "shot_ids": [identifier]},
            {"type": "delete", "shot_id": "shot_" + "f" * 32}, {"type": "update", "shot_id": identifier, "values": {"visual": "OK"}, "approve": True},
            {"type": []}, {"type": "update", "shot_id": identifier, "values": {"visual": "A", "prompt": "B"}},
            {"type": "update", "shot_id": identifier, "values": {"duration": 3, "duration_requested": 4}}]
        for op in operations:
            before = self.database_state()
            with self.subTest(op=op), self.assertRaises(WorkflowError):
                self.edit(op)
            self.assertEqual(self.database_state(), before)

    def test_stale_busy_archived_mutations_are_rejected(self):
        self.start()
        operation = {"type": "update", "shot_id": self.cards()[0]["id"], "values": {"visual": "Changed"}}
        with self.assertRaisesRegex(WorkflowError, "STALE_VERSION"):
            self.store.mutate_shots(self.project["id"], 1, operation)
        self.store.archive(self.project["id"], self.project["revision"], True)
        with self.assertRaisesRegex(WorkflowError, "ARCHIVED"):
            self.edit(operation)
        self.store.archive(self.project["id"], self.project["revision"], False)
        self.store.enqueue(self.project["id"], self.project["revision"], "content", "fixture-only-busy")
        with self.assertRaisesRegex(WorkflowError, "PROJECT_BUSY"):
            self.edit(operation)

    def test_canonical_and_legacy_projection_tampering_fail_closed(self):
        self.start()
        for field in ("canonical", "proposal", "binding"):
            doc = copy.deepcopy(self.project["document"])
            if field == "canonical":
                doc["canonical_timeline"]["snapshot"]["tracks"][0]["clips"][0]["duration"] += .5
                doc["canonical_timeline"]["sha256"] = digest(doc["canonical_timeline"]["snapshot"])
            elif field == "proposal":
                doc["proposal"]["visual_brief"][0]["visual"] = "Unsynchronized"
            else:
                doc["scene_media"][0]["asset_id"] = self.assets[1]["id"]
            with self.subTest(field=field), self.assertRaises(WorkflowError):
                validate_document(doc)

    def test_missing_canonical_fields_and_boolean_revision_are_rejected(self):
        self.start()
        doc = copy.deepcopy(self.project["document"])
        del doc["canonical_timeline"]["snapshot"]["tracks"][0]["clips"][0]["metadata"]["shot"]["narration_enabled"]
        doc["canonical_timeline"]["sha256"] = digest(doc["canonical_timeline"]["snapshot"])
        with self.assertRaises(WorkflowError):
            validate_document(doc)
        before = self.database_state()
        with self.assertRaisesRegex(WorkflowError, "REVISION_REQUIRED"):
            self.store.mutate_shots(self.project["id"], True, {"type": "duplicate", "shot_id": self.cards()[0]["id"]})
        self.assertEqual(self.database_state(), before)

    def test_silent_shots_require_opt_in_and_last_enabled_narration_cannot_be_removed(self):
        silent = copy.deepcopy(self.project["document"]["proposal"])
        silent["visual_brief"][1]["narration_excerpt"] = ""
        silent["narration"] = " ".join(s["narration_excerpt"] for s in silent["visual_brief"] if s["narration_excerpt"])
        before = self.database_state()
        with self.assertRaisesRegex(WorkflowError, "SILENT_SHOTS_REQUIRE_CANONICAL_TIMELINE"):
            self.store.save(self.project["id"], self.project["revision"], proposal=silent)
        self.assertEqual(self.database_state(), before)
        self.start()
        self.project = self.store.save(self.project["id"], self.project["revision"], proposal=silent)
        self.assertFalse(self.cards()[1]["narration_enabled"])
        self.edit({"type": "update", "shot_id": self.cards()[0]["id"], "values": {"narration_enabled": False}})
        before = self.database_state()
        with self.assertRaisesRegex(WorkflowError, "SHOT_AT_LEAST_ONE_NARRATION_REQUIRED"):
            self.edit({"type": "update", "shot_id": self.cards()[2]["id"], "values": {"narration_enabled": False}})
        self.assertEqual(self.database_state(), before)

    def test_narration_edit_invalidates_exact_script_review(self):
        self.start()
        script_hash = __import__("hashlib").sha256(self.project["document"]["proposal"]["narration"].encode()).hexdigest()
        self.store.review_script(self.project["id"], self.project["revision"], "TEST FIXTURE", True, script_hash)
        result = self.edit({"type": "update", "shot_id": self.cards()[0]["id"], "values": {"narration": "Khác lời đọc đã duyệt."}})
        with self.store.transaction() as con:
            self.assertFalse(self.store.current_script_review(con, result)["current"])

    def test_real_restart_history_revert_and_noop_are_durable(self):
        self.start()
        original = self.cards()
        revision = self.project["revision"]
        self.edit({"type": "update", "shot_id": original[0]["id"], "values": {"visual": "New visual"}})
        self.store = Store(self.root)
        self.project = self.store.get(self.project["id"])
        self.assertEqual(self.cards()[0]["visual"], "New visual")
        self.edit({"type": "revert", "restore_revision": revision, "shot_id": original[0]["id"]})
        self.assertEqual(self.cards(), original)
        before = self.database_state()
        self.edit({"type": "update", "shot_id": original[0]["id"], "values": {"visual": original[0]["visual"]}})
        self.assertEqual(self.database_state(), before)

    def test_existing_media_regeneration_is_truthfully_scoped_and_not_ai_generation(self):
        self.start()
        before = self.cards()
        result = self.edit({"type": "regenerate", "shot_id": before[0]["id"]})
        self.assertNotEqual(self.cards()[0]["asset_id"], before[0]["asset_id"])
        self.assertEqual(self.cards()[1:], before[1:])
        self.assertEqual(result["shot_timeline"]["scope"]["provider_calls"], 0)
        with self.store.transaction() as con:
            event = json.loads(con.execute("SELECT payload FROM events WHERE action='shot_timeline_saved_approval_invalidated' ORDER BY id DESC LIMIT 1").fetchone()[0])
        self.assertEqual(event["regeneration_kind"], "deterministic_existing_media_candidate")

    def test_legacy_save_music_assets_voice_and_auto_plan_synchronize_canonical_state(self):
        self.start()
        old_ids = [s["id"] for s in self.cards()]
        modified = copy.deepcopy(self.project["document"]["proposal"])
        modified["visual_brief"][0]["on_screen_text"] = "Legacy route"
        self.project = self.store.save(self.project["id"], self.project["revision"], proposal=modified, music_enabled=False)
        self.assertEqual(self.cards()[0]["on_screen_text"], "Legacy route")
        self.project = self.store.append_media(self.project["id"], self.project["revision"],
            {**self.assets[0], "id": "another-fixture.jpg"})
        self.project = self.store.set_music(self.project["id"], self.project["revision"],
            {"id": "fixture.wav", "source_sha256": "a" * 64, "sha256": "b" * 64, "duration_seconds": 5, "rights_confirmed": True})
        self.project = self.store.set_voice_quality(self.project["id"], self.project["revision"], "scene-context-v1")
        self.project = self.store.auto_plan(self.project["id"], self.project["revision"])
        self.assertEqual([s["id"] for s in self.cards()], old_ids)
        self.assertEqual(len(shots(self.project["document"])), 3)
        self.assertTrue(validate_document(self.project["document"]))

    def test_short_video_uses_bounded_canonical_loops_and_source_start(self):
        self.project = self.store.append_media(self.project["id"], self.project["revision"],
            {"id": "fixture-video.mp4", "kind": "video", "sha256": "c" * 64,
             "duration_seconds": 2.5, "rights_confirmed": True, "filename": "Fixture"})
        identifier = self.cards()[0]["id"]
        result = self.edit({"type": "update", "shot_id": identifier,
            "values": {"asset_id": "fixture-video.mp4", "source_start": .5, "duration": 6}})
        clips = [c for c in result["shot_timeline"]["snapshot"]["tracks"][0]["clips"] if c["metadata"]["shot_id"] == identifier]
        self.assertEqual(len(clips), 3)
        self.assertEqual(clips[0]["source_start"], .5)
        self.assertAlmostEqual(sum(c["duration"] for c in clips), 6)
        self.assertTrue(all(c["source_end"] <= 2.5 for c in clips))

    def test_brand_landscape_and_document_append_keep_single_timeline(self):
        self.start()
        identifiers = [s["id"] for s in self.cards()]
        from services.windows_native.branding import catalog
        choice = next(t for t in catalog(include_landscape=True)["templates"] if t["aspect_ratio"] == "16:9")
        self.project = self.store.set_brand(self.project["id"], self.project["revision"], "vf-reference", choice["id"])
        snapshot = self.project["document"]["canonical_timeline"]["snapshot"]
        self.assertEqual((snapshot["width"], snapshot["height"], snapshot["aspect_ratio"]), (1920, 1080, "16:9"))
        self.project = self.store.append_document(self.project["id"], self.project["revision"],
            {"id": "explicit-fixture.txt", "sha256": "e" * 64, "text": "Temporary fixture; not retrieved research."})
        self.assertEqual([s["id"] for s in self.cards()], identifiers)
        self.assertTrue(validate_document(self.project["document"]))

    def test_fixture_provider_results_synchronize_without_actual_provider_dispatch(self):
        self.start()
        ids = [s["id"] for s in self.cards()]
        self.store.enqueue(self.project["id"], self.project["revision"], "content", "fixture-content-result")
        claimed = self.store.claim()
        changed = proposal()
        changed["visual_brief"][0]["visual"] = "New explicit fixture visual"
        self.store.finish(claimed, result={"proposal": changed, "provider": "explicit_test_fixture"})
        self.project = self.store.get(self.project["id"])
        self.assertEqual([s["id"] for s in self.cards()], ids)
        self.assertTrue(all(s["asset_id"] is None for s in self.cards()))
        self.assertEqual(self.cards()[0]["visual"], "New explicit fixture visual")
        self.assertIsNone(self.project["approval"])
        self.assertTrue(validate_document(self.project["document"]))
        self.store.enqueue(self.project["id"], self.project["revision"], "asr", "fixture-asr-result")
        claimed = self.store.claim()
        body = {"asset_id": self.assets[0]["id"], "source_sha256": self.assets[0]["sha256"], "transcript": None}
        self.store.finish(claimed, result={"media_analysis": [{**body, "analysis_sha256": digest(body)}]})
        self.project = self.store.get(self.project["id"])
        self.assertTrue(validate_document(self.project["document"]))
        self.assertEqual(len(self.project["document"]["media_analysis"]), 1)

    def test_legacy_writer_refuses_corrupt_previous_canonical_state(self):
        self.start()
        doc = copy.deepcopy(self.project["document"])
        doc["canonical_timeline"]["snapshot"]["tracks"][0]["clips"][0]["duration"] += .3
        doc["canonical_timeline"]["sha256"] = digest(doc["canonical_timeline"]["snapshot"])
        with self.assertRaises(WorkflowError):
            self.store.sync_shot_document(copy.deepcopy(doc), doc, self.project["id"])

    def test_new_legacy_scene_after_delete_gets_fresh_noncolliding_identity(self):
        self.start()
        old = self.cards()
        self.edit({"type": "delete", "shot_id": old[1]["id"]})
        self.project = self.store.save(self.project["id"], self.project["revision"], proposal=proposal())
        cards = self.cards()
        self.assertEqual([s["id"] for s in cards[:2]], [old[0]["id"], old[2]["id"]])
        self.assertEqual(len(set(s["id"] for s in cards)), 3)
        self.assertNotIn(cards[2]["id"], [s["id"] for s in old])
        self.assertTrue(validate_document(self.project["document"]))


if __name__ == "__main__":
    unittest.main()
