"""Explicit fixture approvals are test-only; no provider or voice inference."""
import copy
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
import wave
from unittest.mock import patch

from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.editor import build_plan, validate_plan, timeline
from services.windows_native.hardening import version_components
from services.windows_native.music import ingest_music
from services.windows_native.pipeline import Config, Pipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal


def music_bytes():
    import numpy as np
    stream=io.BytesIO()
    with wave.open(stream,"wb") as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(48000)
        audio.writeframes((np.sin(np.arange(96000)*2*np.pi*440/48000)*8000).astype("<i2").tobytes())
    return stream.getvalue()


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.config=Config(data_root=self.root); self.store=Store(self.root)
        self.project=self.store.create("Scene fixtures", "No paid dispatch")
        self.project=self.store.save(self.project["id"],1,proposal=proposal())
        for index in range(5):
            self.project=self.store.append_media(self.project["id"],self.project["revision"],
                {"id":f"fixture_{index:04}.jpg","kind":"image" if index<4 else "video","duration_seconds":2.5,
                 "sha256":f"fixture_sha_{index}","rights_confirmed":True,"filename":"Xin chào.mp4" if index==3 else "opaque.bin"})

    def tearDown(self): self.temp.cleanup()

    def test_five_asset_plan_deterministic_no_filename_semantics(self):
        doc=self.project["document"]; before=digest(doc)
        a=build_plan(doc,auto_select=True); b=build_plan(doc,auto_select=True)
        self.assertEqual(a,b); self.assertEqual(digest(doc),before)
        self.assertEqual([s["selected_asset"] for s in a["scenes"]],[f"fixture_{i:04}.jpg" for i in range(3)])
        self.assertTrue(a["scenes"][-1]["cta_marker"])
        self.assertTrue(all(len(s["asset_candidates"])==5 for s in a["scenes"]))
        self.assertTrue(all(not c["semantic_image_claim"] for s in a["scenes"] for c in s["asset_candidates"]))

    def test_verified_transcript_match_and_tampered_analysis_is_not_used(self):
        doc=copy.deepcopy(self.project["document"])
        record={"asset_id":"fixture_0004.jpg","source_sha256":"fixture_sha_4","explicit_fixture":True,
            "transcript":{"segments":[{"text":"Xin chào.","words":[{"text":"Xin","start_seconds":.4},{"text":"chào.","start_seconds":.7}]}]}}
        record["analysis_sha256"]=digest(record); doc["media_analysis"]=[record]
        scene=build_plan(doc,auto_select=True)["scenes"][0]
        self.assertEqual(scene["selected_asset"],record["asset_id"]); self.assertEqual(scene["source_start"],.4)
        self.assertEqual(scene["asset_candidates"][0]["reason"],"transcript_token_overlap")
        doc["media_analysis"][0]["transcript"]["segments"][0]["text"]="changed"
        self.assertEqual(build_plan(doc,auto_select=True)["scenes"][0]["selected_asset"],"fixture_0000.jpg")

    def test_cas_busy_manual_source_change_restart_and_approval_invalidation(self):
        p=self.store.auto_plan(self.project["id"],self.project["revision"])
        self.assertEqual(validate_plan(p["document"]),p["document"]["edit_plan"])
        p=self.store.approve(p["id"],p["revision"],"UNIT FIXTURE — NOT HUMAN ACCEPTANCE",True)
        old=version_components(p["document"])
        bindings=copy.deepcopy(p["document"]["scene_media"]); bindings[0]["asset_id"]="fixture_0003.jpg"
        p=self.store.save(p["id"],p["revision"],scene_media=bindings,scene_options=[{"scene":1,"motion":"pan_left","crop_strategy":"cover","transition":"fade"}])
        self.assertIsNone(p["approval"]); self.assertNotEqual(old["storyboard_version"],version_components(p["document"])["storyboard_version"])
        self.assertEqual(Store(self.root).get(p["id"])["document"],p["document"])
        self.assertEqual(p["document"]["edit_plan"]["scenes"][0]["selected_asset"],"fixture_0003.jpg")
        with self.assertRaisesRegex(WorkflowError,"STALE_VERSION"): self.store.auto_plan(p["id"],p["revision"]-1)
        self.store.enqueue(p["id"],p["revision"],"content",uuid.uuid4().hex)
        with self.assertRaisesRegex(WorkflowError,"PROJECT_BUSY"): self.store.auto_plan(p["id"],p["revision"])

    def test_mutated_plan_and_script_fail_closed(self):
        p=self.store.auto_plan(self.project["id"],self.project["revision"]); doc=copy.deepcopy(p["document"])
        doc["edit_plan"]["scenes"][0]["asset_candidates"][0]["score"]+=1
        with self.assertRaisesRegex(WorkflowError,"CHANGED_OR_STALE"): validate_plan(doc)
        doc=copy.deepcopy(p["document"]); doc["proposal"]=proposal("Thay đổi")
        with self.assertRaisesRegex(WorkflowError,"EDITOR_PLAN_STALE"): validate_plan(doc)

    def test_video_bounds_image_options_and_unknown_choices(self):
        doc=copy.deepcopy(self.project["document"]); doc["scene_media"]=[{"scene":1,"asset_id":"fixture_0004.jpg"}]
        for options in ([{"scene":1,"source_start":2.5}],[{"scene":1,"motion":"zoom_in"}],[{"scene":1,"source_start":float("nan")}],[{"scene":1,"source_start":-1}],[{"scene":1,"crop_strategy":"bad"}],[{"scene":1},{"scene":1}]):
            with self.assertRaises(WorkflowError): build_plan(doc,options)
        doc["scene_media"]=[{"scene":1,"asset_id":"fixture_0000.jpg"}]
        with self.assertRaisesRegex(WorkflowError,"IMAGE_HAS_NO_SOURCE"): build_plan(doc,[{"scene":1,"source_start":.3}])

    def test_loop_projection_obeys_existing_canonical_timeline_bounds(self):
        doc=copy.deepcopy(self.project["document"]); doc["scene_media"]=[{"scene":i,"asset_id":"fixture_0004.jpg"} for i in (1,2,3)]
        doc["edit_plan"]=build_plan(doc,[{"scene":i,"source_start":.5} for i in (1,2,3)])
        frames=[{"scene":i,"asset_id":"fixture_0004.jpg","kind":"video","source_sha256":"fixture_sha_4","start":(i-1)*8,"end":i*8} for i in (1,2,3)]
        value=timeline(doc,frames,[{"text":"Caption","start":1.1,"end":3.}])
        clips=value["tracks"][0]["clips"]
        self.assertGreater(len(clips),3)
        self.assertAlmostEqual(sum(c["duration"] for c in clips),24)
        self.assertTrue(all(c["source_end"]<=2.5 for c in clips))
        self.assertTrue(all(abs(c["source_end"]-c["source_start"]-c["duration"])<1e-6 for c in clips))


class MusicHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.config=Config(data_root=Path(self.temp.name))
        self.server=LocalServer(0,self.config,start_worker=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.project=self.server.store.create("Music fixture","Prompt")

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def upload(self,raw=None,headers=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=30)
        conn.request("POST",f"/api/projects/{self.project['id']}/music",body=music_bytes() if raw is None else raw,headers={
            "Cookie":f"vf_native_session={self.server.session}","X-VF-CSRF":self.server.csrf,"Content-Type":"audio/wav",
            "X-VF-Rights":"confirmed","X-VF-Revision":str(self.project["revision"]),"X-VF-Filename":"fixture.wav",**(headers or {})})
        response=conn.getresponse(); body=json.loads(response.read()); conn.close(); return response.status,body

    def test_real_audio_intake_original_hash_and_restart(self):
        raw=music_bytes(); status,p=self.upload(raw); self.assertEqual(status,201)
        music=p["document"]["music"]
        self.assertEqual((self.config.data_root/"originals"/music["original_id"]).read_bytes(),raw)
        self.assertEqual(music["source_sha256"],file_sha(self.config.data_root/"originals"/music["original_id"]))
        self.assertEqual(music["sha256"],file_sha(self.config.data_root/"assets"/music["id"]))
        self.assertEqual(Store(self.config.data_root).get(p["id"])["document"]["music"],music)
        with wave.open(str(self.config.data_root/"assets"/music["id"]),"rb") as wav:
            self.assertEqual((wav.getframerate(),wav.getnchannels()),(48000,2))

    def test_rights_mime_csrf_stale_and_busy_refuse(self):
        for headers,code in [({"X-VF-Rights":""},400),({"Content-Type":"audio/mpeg"},400),({"X-VF-CSRF":"wrong"},403),({"X-VF-Revision":"99"},409)]:
            self.assertEqual(self.upload(headers=headers)[0],code)
        self.server.store.enqueue(self.project["id"],1,"content",uuid.uuid4().hex)
        self.assertEqual(self.upload()[0],409)
        self.assertEqual(list((self.config.data_root/"uploads").glob("*")),[])

    def test_upload_race_leaves_no_orphaned_music(self):
        with patch.object(self.server.store,"set_music",side_effect=WorkflowError("STALE_VERSION_RELOAD")):
            self.assertEqual(self.upload()[0],409)
        self.assertEqual(list((self.config.data_root/"assets").glob("*")),[])
        self.assertEqual(list((self.config.data_root/"originals").glob("*")),[])

    def test_music_tamper_stops_before_voice_inference(self):
        source=self.config.data_root/"source.wav"; source.write_bytes(music_bytes())
        music=ingest_music(self.config,source,"audio/wav","test.wav",rights_confirmed=True)
        asset_dir=self.config.data_root/"assets"; (asset_dir/"fixture.jpg").write_bytes(b"explicit fixture")
        p=self.server.store.save(self.project["id"],1,proposal=proposal(),asset={"id":"fixture.jpg","sha256":file_sha(asset_dir/"fixture.jpg"),"rights_confirmed":True})
        p=self.server.store.set_music(p["id"],p["revision"],music)
        p=self.server.store.approve(p["id"],p["revision"],"UNIT FIXTURE — NOT HUMAN ACCEPTANCE",True)
        job=self.server.store.enqueue(p["id"],p["revision"],"render",uuid.uuid4().hex)
        (asset_dir/music["id"]).write_bytes(b"changed")
        with patch("services.windows_native.pipeline.subprocess.run") as process:
            with self.assertRaisesRegex(WorkflowError,"MUSIC_ARTIFACT_CHANGED"): Pipeline(self.config).run(job,lambda _:None)
            process.assert_not_called()

