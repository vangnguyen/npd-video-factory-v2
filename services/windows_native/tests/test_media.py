import http.client
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import quote

from PIL import Image

from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.media import ingest_media, project_assets, scene_bindings, verify_selected_files
from services.windows_native.pipeline import Config, Pipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal


def image_bytes(color="green", fmt="PNG"):
    out = io.BytesIO()
    Image.new("RGB", (320, 240), color).save(out, format=fmt)
    return out.getvalue()


class MediaBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config(data_root=Path(self.temp.name))
        self.store = Store(self.config.data_root)
        self.project = self.store.create("Media test", "Prompt")
        self.project = self.store.save(self.project["id"], 1, proposal=proposal())
        for kind in ("image", "video"):
            self.project = self.store.append_media(self.project["id"], self.project["revision"],
                {"id": kind+".jpg", "kind": kind, "sha256": "fixture", "rights_confirmed": True})
        self.bindings = [{"scene": i, "asset_id": "video.jpg" if i == 2 else "image.jpg"} for i in (1, 2, 3)]

    def tearDown(self):
        self.temp.cleanup()

    def save(self, bindings):
        self.project = self.store.save(self.project["id"], self.project["revision"], scene_media=bindings)
        return self.project

    def test_all_scenes_require_one_source_before_review(self):
        for bindings in ([], self.bindings[:2]):
            p = self.save(bindings)
            with self.assertRaisesRegex(WorkflowError, "EACH_SCENE_REQUIRES_ONE"):
                self.store.approve(p["id"], p["revision"], "Test reviewer", True)
        p = self.save(self.bindings)
        p = self.store.approve(p["id"], p["revision"], "Test reviewer", True)
        job = self.store.enqueue(p["id"], p["revision"], "render", uuid.uuid4().hex)
        self.assertEqual(job["snapshot"]["document"]["scene_media"], self.bindings)

    def test_reject_duplicate_unknown_scene_and_foreign_project_source(self):
        for bindings, code in (([self.bindings[0], self.bindings[0]], "INVALID_SCENE_MEDIA"),
                ([{"scene": 4, "asset_id": "image.jpg"}], "INVALID_SCENE_MEDIA"),
                ([{"scene": True, "asset_id": "image.jpg"}], "INVALID_SCENE_MEDIA"),
                ([{"scene": 1, "asset_id": "other-project.jpg"}], "SCENE_MEDIA_NOT_IN_PROJECT"),
                ([{**self.bindings[0], "extra": "bad"}], "INVALID_SCENE_MEDIA")):
            with self.assertRaisesRegex(WorkflowError, code):
                self.save(bindings)

    def test_changing_selected_source_invalidates_review_and_persists(self):
        p = self.save(self.bindings)
        p = self.store.approve(p["id"], p["revision"], "Test reviewer", True)
        old_hash = p["approval"]["snapshot_sha256"]
        p = self.save([{**b, "asset_id": "video.jpg"} for b in self.bindings])
        self.assertIsNone(p["approval"])
        reopened = Store(self.config.data_root).get(p["id"])
        self.assertEqual(reopened["document"]["scene_media"], p["document"]["scene_media"])
        self.assertNotEqual(digest(reopened["document"]), old_hash)
        with self.assertRaisesRegex(WorkflowError, "HUMAN_APPROVAL_REQUIRED"):
            self.store.enqueue(p["id"], p["revision"], "render", uuid.uuid4().hex)

    def test_missing_or_changed_media_stops_before_tts_child(self):
        p = self.save(self.bindings)
        p = self.store.approve(p["id"], p["revision"], "Test reviewer", True)
        job = self.store.enqueue(p["id"], p["revision"], "render", uuid.uuid4().hex)
        with patch("services.windows_native.pipeline.subprocess.run") as child:
            with self.assertRaisesRegex(WorkflowError, "SOURCE_MEDIA_CHANGED_OR_MISSING"):
                Pipeline(self.config).run(job, lambda _: None)
            child.assert_not_called()

    def test_legacy_snapshot_read_does_not_change_approval_digest(self):
        doc = {"proposal": proposal(), "asset": {"id": "legacy.jpg", "sha256": "old"}}
        original = digest(doc)
        self.assertEqual(len(project_assets(doc)), 1)
        self.assertEqual(scene_bindings(doc), [{"scene": i, "asset_id": "legacy.jpg"} for i in (1, 2, 3)])
        self.assertEqual(digest(doc), original)
        self.assertNotIn("assets", doc)

    def test_new_content_requires_new_deliberate_scene_choices(self):
        p = self.save(self.bindings)
        job = self.store.enqueue(p["id"], p["revision"], "content", uuid.uuid4().hex)
        self.store.claim(); self.store.finish(job, result={"proposal": proposal("Bản mới")})
        p = self.store.get(p["id"])
        self.assertEqual(p["document"]["scene_media"], [])
        self.assertEqual(len(p["document"]["assets"]), 2)
        self.assertIsNone(p["approval"])


class MediaHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config(data_root=Path(self.temp.name))
        self.server = LocalServer(0, self.config, start_worker=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.project = self.server.store.create("Upload test", "Prompt")

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def request(self, method, path, raw=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        hdr = {"Cookie": f"vf_native_session={self.server.session}", "X-VF-CSRF": self.server.csrf,
               "Content-Type": "image/png", "X-VF-Revision": str(self.project["revision"]),
               "X-VF-Rights": "confirmed", "X-VF-Illustration": "true", "X-VF-Filename": quote("Ảnh dự án.png"),
               **(headers or {})}
        conn.request(method, path, body=raw, headers=hdr)
        result = conn.getresponse(); body = result.read(); conn.close()
        return result.status, body

    def upload(self, raw=None, headers=None):
        return self.request("POST", f"/api/projects/{self.project['id']}/media", raw or image_bytes(), headers)

    def test_multiple_images_append_and_thumbnail_is_project_scoped(self):
        for color in ("red", "blue"):
            status, raw = self.upload(image_bytes(color))
            self.assertEqual(status, 201)
            self.project = json.loads(raw)
        assets = self.project["document"]["assets"]
        self.assertEqual(len(assets), 2); self.assertNotEqual(assets[0]["id"], assets[1]["id"])
        self.assertEqual(assets[0]["filename"], "Ảnh dự án.png")
        self.assertEqual(assets[0]["sha256"], file_sha(self.config.data_root/"assets"/assets[0]["id"]))
        url = f"/api/projects/{self.project['id']}/media/{assets[0]['id']}/thumbnail"
        status, raw = self.request("GET", url); self.assertEqual(status, 200)
        self.assertEqual(Image.open(io.BytesIO(raw)).format, "JPEG")
        other = self.server.store.create("Other", "Prompt")
        self.assertEqual(self.request("GET", url.replace(self.project["id"], other["id"]))[0], 404)

    def test_invalid_video_rights_stale_and_busy_upload_leave_no_files(self):
        for headers, expected in (({"X-VF-Rights": ""}, 400), ({"X-VF-Revision": "99"}, 409),
                ({"Content-Type": "video/mp4"}, 400), ({"X-VF-CSRF": "wrong"}, 403)):
            self.assertEqual(self.upload(headers=headers)[0], expected)
        self.server.store.enqueue(self.project["id"], 1, "content", uuid.uuid4().hex)
        self.assertEqual(self.upload()[0], 409)
        self.assertEqual(list((self.config.data_root/"uploads").glob("*")), [])
        self.assertEqual(list((self.config.data_root/"assets").glob("*")), [])

    def test_append_race_cleans_sanitized_files(self):
        with patch.object(self.server.store, "append_media", side_effect=WorkflowError("STALE_VERSION_RELOAD")):
            self.assertEqual(self.upload()[0], 409)
        self.assertEqual(list((self.config.data_root/"assets").glob("*")), [])
        self.assertEqual(list((self.config.data_root/"uploads").glob("*")), [])

    def test_real_mp4_intake_range_and_immutable_source(self):
        source = self.config.data_root/"fixture.mp4"
        subprocess.run([str(self.config.ffmpeg_bin/"ffmpeg.exe"), "-v", "error", "-nostdin", "-n",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=0.7", "-f", "lavfi", "-i",
            "sine=frequency=1500:duration=0.7", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)], check=True, timeout=30)
        status, raw = self.upload(source.read_bytes(), {"Content-Type": "video/mp4", "X-VF-Filename": quote("Chuyển động.mp4")})
        self.assertEqual(status, 201); self.project = json.loads(raw)
        asset = self.project["document"]["assets"][0]
        self.assertEqual(asset["sha256"], file_sha(source)); self.assertEqual(asset["original_audio"], "muted")
        self.assertEqual(asset["kind"], "video"); self.assertGreater(asset["duration_seconds"], .6)
        url = f"/api/projects/{self.project['id']}/media/{asset['id']}"
        self.assertEqual(self.request("GET", url, headers={"Range": "bytes=0-11"}), (206, source.read_bytes()[:12]))
        self.assertEqual(self.request("GET", url+"/thumbnail")[0], 200)

    def test_quicktime_mov_is_validated_by_container_and_preserves_bytes(self):
        source = self.config.data_root/"fixture.mov"
        subprocess.run([str(self.config.ffmpeg_bin/"ffmpeg.exe"), "-v", "error", "-nostdin", "-n",
            "-f", "lavfi", "-i", "testsrc2=size=240x320:rate=30:duration=0.5", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-f", "mov", str(source)], check=True, timeout=30)
        status, raw = self.upload(source.read_bytes(), {"Content-Type": "video/quicktime", "X-VF-Filename": "phone.MOV"})
        self.assertEqual(status, 201)
        asset = json.loads(raw)["document"]["assets"][0]
        self.assertEqual(asset["sha256"], file_sha(source))
        self.assertEqual(asset["filename"], "phone.MOV")
        self.assertEqual((asset["width"], asset["height"]), (240, 320))


if __name__ == "__main__":
    unittest.main()
