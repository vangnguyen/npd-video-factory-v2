import base64
import concurrent.futures
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
import subprocess
import sys
from unittest.mock import patch

from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.pipeline import Config, Pipeline, ass_escape, measured_scene_units, sentence_units
from services.windows_native.contracts import Proposal
from services.windows_native.server import LocalServer, Runner, save_image
from services.windows_native.store import Store
from services.windows_native.pipeline import synthesize, REPO
from services.windows_native.pipeline import generate


def proposal(text="Xin chào"):
    return {"narration": f"{text}. Cần kiểm chứng. Xin cảm ơn.",
            "visual_brief": [{"scene": i+1, "visual": "Ảnh dự án", "on_screen_text": "Tìm hiểu",
                              "narration_excerpt": t} for i,t in enumerate([f"{text}.", "Cần kiểm chứng.", "Xin cảm ơn."])],
            "facts_needing_source": ["Hồ sơ chính thức"]}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config(data_root=Path(self.temp.name))
        self.store = Store(self.config.data_root)
        self.project = self.store.create("Dự án", "Yêu cầu")

    def tearDown(self):
        self.temp.cleanup()

    def ready_draft(self):
        p = self.store.save(self.project["id"], 1, proposal=proposal(),
                            asset={"id":"image.jpg","sha256":"example","rights_confirmed":True,"illustration":True})
        return self.store.approve(p["id"], p["revision"], "Owner", True)

    def test_render_blocked_before_human_review(self):
        with self.assertRaisesRegex(WorkflowError, "HUMAN_APPROVAL_REQUIRED_BEFORE_TTS"):
            self.store.enqueue(self.project["id"], 1, "render", uuid.uuid4().hex)
        self.assertEqual(self.store.get(self.project["id"])["jobs"], [])

    def test_approval_requires_name_explicit_ack_and_image(self):
        for name, ack in [("",True),("Owner",False),("Owner","true")]:
            with self.assertRaisesRegex(WorkflowError,"HUMAN_REVIEW_REQUIRED"):
                self.store.approve(self.project["id"],1,name,ack)
        with self.assertRaisesRegex(WorkflowError,"CONTENT_AND_IMAGE_REQUIRED"):
            self.store.approve(self.project["id"],1,"Owner",True)

    def test_edit_invalidates_approval_and_blocks_stale_render(self):
        p=self.ready_draft()
        old_revision=p["revision"]
        p=self.store.save(p["id"],p["revision"],proposal=proposal("Chào bạn"))
        self.assertIsNone(p["approval"])
        with self.assertRaisesRegex(WorkflowError,"STALE_VERSION_RELOAD"):
            self.store.enqueue(p["id"],old_revision,"render",uuid.uuid4().hex)
        with self.assertRaisesRegex(WorkflowError,"HUMAN_APPROVAL_REQUIRED_BEFORE_TTS"):
            self.store.enqueue(p["id"],p["revision"],"render",uuid.uuid4().hex)

    def test_image_or_prompt_edit_invalidates_review(self):
        p=self.ready_draft()
        p=self.store.save(p["id"],p["revision"],asset={"id":"new.jpg"})
        self.assertIsNone(p["approval"])
        p=self.store.approve(p["id"],p["revision"],"Owner",True)
        p=self.store.save(p["id"],p["revision"],prompt="New prompt")
        self.assertIsNone(p["approval"])
        self.assertIsNone(p["document"]["proposal"])

    def test_schema_rejects_incomplete_or_reordered_coverage(self):
        value=proposal();value["visual_brief"][0]["narration_excerpt"]="Wrong"
        with self.assertRaisesRegex(WorkflowError,"INVALID_PROPOSAL"):
            self.store.save(self.project["id"],1,proposal=value)

    def test_concurrent_duplicate_dispatch_has_one_receipt(self):
        key=uuid.uuid4().hex
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            jobs=list(pool.map(lambda _:self.store.enqueue(self.project["id"],1,"content",key),range(10)))
        self.assertEqual(len({job["id"] for job in jobs}),1)
        self.assertEqual(len(self.store.get(self.project["id"])["jobs"]),1)
        with self.assertRaisesRegex(WorkflowError,"IDEMPOTENCY_KEY_CONFLICT"):
            self.store.enqueue(self.project["id"],2,"content",key)
        with self.assertRaisesRegex(WorkflowError,"PROJECT_BUSY"):
            self.store.enqueue(self.project["id"],1,"content",uuid.uuid4().hex)

    def test_project_cannot_change_while_queued_or_running(self):
        self.store.enqueue(self.project["id"],1,"content",uuid.uuid4().hex)
        for run in (False,True):
            if run:self.store.claim()
            with self.assertRaisesRegex(WorkflowError,"PROJECT_BUSY"):
                self.store.save(self.project["id"],1,prompt="Other")

    def test_restart_keeps_queued_and_never_replays_dispatched_job(self):
        self.store.enqueue(self.project["id"],1,"content",uuid.uuid4().hex)
        second=self.store.create("Second","Prompt")
        self.store.enqueue(second["id"],1,"content",uuid.uuid4().hex)
        running=self.store.claim()
        restarted=Store(self.config.data_root);restarted.recover()
        self.assertEqual(restarted.get_job(running["id"])["status"],"interrupted")
        self.assertEqual(restarted.claim()["project_id"],second["id"])
        self.assertIsNone(restarted.claim())

    def test_content_finishes_at_review_with_no_tts_dispatch(self):
        self.store.enqueue(self.project["id"],1,"content",uuid.uuid4().hex)
        class Fake:
            calls=0
            def run(_,job,stage):
                _.calls+=1
                return {"proposal":proposal(),"provider_calls":1,"retries":0}
        fake=Fake();runner=Runner(self.store,fake)
        self.assertTrue(runner.run_one());self.assertFalse(runner.run_one())
        p=self.store.get(self.project["id"])
        self.assertIsNone(p["approval"])
        self.assertEqual(p["revision"],2)
        self.assertEqual(p["jobs"][0]["status"],"awaiting_review")
        self.assertEqual(fake.calls,1)
        self.assertTrue(Store(self.config.data_root).get(p["id"])["document"]["proposal"])

    def test_provider_failure_exposes_category_http_only_no_retry(self):
        self.store.enqueue(self.project["id"],1,"content",uuid.uuid4().hex)
        class Fake:
            calls=0
            def run(_,job,stage):
                _.calls+=1
                raise WorkflowError("RateLimitError",http_status=429)
        fake=Fake();runner=Runner(self.store,fake)
        runner.run_one();runner.run_one()
        job=self.store.get(self.project["id"])["jobs"][0]
        self.assertEqual(job["error"],{"code":"RateLimitError","automatic_retry":False,"http_status":429})
        self.assertEqual(fake.calls,1)

    def test_pipeline_checks_approval_again_before_child(self):
        p=self.ready_draft();job=self.store.enqueue(p["id"],p["revision"],"render",uuid.uuid4().hex)
        job["snapshot"]["document"]["prompt"]="Changed outside store"
        with patch("subprocess.run") as run:
            with self.assertRaisesRegex(WorkflowError,"HUMAN_APPROVAL_REQUIRED_BEFORE_TTS"):
                Pipeline(self.config).run(job,lambda _:None)
            run.assert_not_called()

    def test_source_image_validation_and_immutable_generated_name(self):
        from PIL import Image
        data=io.BytesIO();Image.new("RGB",(320,240),"green").save(data,format="PNG")
        body={"image_base64":base64.b64encode(data.getvalue()).decode(),"rights_confirmed":True,"illustration":True}
        image=save_image(self.config,body)
        self.assertEqual(image["sha256"],file_sha(self.config.data_root/"assets"/image["id"]))
        with self.assertRaisesRegex(WorkflowError,"IMAGE_RIGHTS"):
            save_image(self.config,{**body,"rights_confirmed":False})
        with self.assertRaisesRegex(WorkflowError,"INVALID_IMAGE"):
            save_image(self.config,{**body,"image_base64":"SGVsbG8="})

    def test_ass_overrides_are_not_executed(self):
        self.assertNotIn("{",ass_escape(r"{\pos(0,0)}hello\N"))
        self.assertNotIn("\\",ass_escape(r"{\pos(0,0)}hello\N"))

    def test_data_root_cannot_write_into_accepted_mvp_or_synced_sources(self):
        for path in (Path(r"C:\NPD-Video-Factory\outputs\MVP1"),Path(r"C:\NPD-Video-Factory\runtime\new"),REPO/"data",self.config.data_root/"sources"/"new"):
            with self.assertRaisesRegex(WorkflowError,"DATA_ROOT_MUST_NOT_TOUCH"):
                Config(data_root=path).validate_data_root()

    def test_multiple_sentences_in_one_scene_keep_exact_coverage_and_order(self):
        value=proposal();value["visual_brief"][2]["narration_excerpt"]+=" Kiểm tra tiếp!"
        value["narration"]+=" Kiểm tra tiếp!"
        obj=Proposal.model_validate(value)
        units=sentence_units(obj)
        self.assertEqual([u["scene"] for u in units],[1,2,3,3])
        meta={"duration_seconds":4,"units":[{**u,"start_seconds":i,"end_seconds":i+1,
            "activity_start_seconds":i+.1,"activity_end_seconds":i+.9} for i,u in enumerate(units)]}
        self.assertEqual(len(measured_scene_units(obj,meta)[2]),2)
        meta["units"][3]["scene"]=2
        with self.assertRaisesRegex(WorkflowError,"VOICE_SCENE_BINDING"):
            measured_scene_units(obj,meta)

    def test_synthesis_preserves_parameters_network_block_and_exact_sentence_plan(self):
        import numpy as np
        import socket
        from services.windows_native.pipeline import profile
        p=self.ready_draft()
        out=self.config.data_root/"test-tts";out.mkdir()
        captured=[]
        class FakeEngine:
            def __init__(self,**kwargs):pass
            def infer(self,**kwargs):
                captured.append(kwargs)
                with socket.socket() as connection:
                    try:connection.connect(("example.com",443))
                    except WorkflowError:pass
                    else:raise AssertionError("outbound network was not blocked")
                self.observed_eos=True
                return (np.sin(np.arange(48000)*.05)*.2).astype(np.float32)
        with patch("services.windows_native.pipeline.verify_runtime"),patch("vieneu._v3_turbo_engine.onnx_runtime_lite.OnnxV3LiteEngine",FakeEngine),patch("socket.socket.connect"):
            synthesize(self.config,{"document":p["document"],"approval":p["approval"]},out)
        meta=json.loads((out/"voice.json").read_bytes())
        self.assertEqual(meta["inference_calls"],3)
        self.assertEqual(meta["retries"],0)
        self.assertEqual([u["text"] for u in meta["units"]],[s["narration_excerpt"] for s in p["document"]["proposal"]["visual_brief"]])
        for actual in captured:
            self.assertEqual({k:actual[k] for k in ("temperature","top_k","top_p","repetition_penalty","max_new_frames")},
                {k:profile()["parameters"][k] for k in ("temperature","top_k","top_p","repetition_penalty","max_new_frames")})

    def test_synthesis_frame_cap_stops_without_retry_or_final_wav(self):
        import numpy as np
        p=self.ready_draft();out=self.config.data_root/"test-cap";out.mkdir()
        class FakeEngine:
            def __init__(self,**kwargs):pass
            def infer(self,**kwargs):return np.ones(10,dtype=np.float32)
        with patch("services.windows_native.pipeline.verify_runtime"),patch("vieneu._v3_turbo_engine.onnx_runtime_lite.OnnxV3LiteEngine",FakeEngine),patch("socket.socket.connect"):
            with self.assertRaisesRegex(WorkflowError,"SYNTHESIS_FRAME_CAP_WITHOUT_EOS_STOP"):
                synthesize(self.config,{"document":p["document"],"approval":p["approval"]},out)
        self.assertFalse((out/"voice.wav").exists())

    def test_sdk_uses_exact_model_explicit_timeout_and_zero_retries(self):
        from types import SimpleNamespace
        captured={"calls":0}
        class FakeSDK:
            def __init__(self,**kwargs):captured.update(kwargs);self.responses=self
            def create(self,**kwargs):
                captured["calls"]+=1;captured["request"]=kwargs
                return SimpleNamespace(status="completed",model="gpt-6-luna",id="test-response",
                    usage=SimpleNamespace(model_dump=lambda:{"total_tokens":10}),
                    output=[SimpleNamespace(type="message",content=[SimpleNamespace(type="output_text",text=json.dumps(proposal()))])])
            def close(self):captured["http_client"].close()
        job=self.store.enqueue(self.project["id"],1,"content",uuid.uuid4().hex)
        out=self.config.data_root/"test-sdk";out.mkdir()
        with patch("services.windows_native.pipeline.load_key",return_value="sk-synthetic-test"),patch("openai.OpenAI",FakeSDK):
            result=generate(self.config,job,out)
        self.assertEqual(captured["max_retries"],0)
        self.assertEqual(captured["timeout"].connect,15)
        self.assertEqual(captured["timeout"].read,90)
        self.assertEqual(captured["request"]["model"],"gpt-6-luna")
        self.assertEqual(captured["request"]["max_output_tokens"],2048)
        self.assertFalse(captured["request"]["store"])
        self.assertTrue(result["human_review_required"])
        self.assertEqual(captured["calls"],1)
        self.assertNotIn("sk-synthetic-test",(out/"content-result.json").read_text())

    @unittest.skipUnless(os.name=="nt","Windows process containment")
    def test_one_server_lock_per_data_root(self):
        from services.windows_native.windows_job import lock_data_root
        first=lock_data_root(self.config.data_root)
        try:
            with self.assertRaisesRegex(WorkflowError,"DATA_ROOT_ALREADY_IN_USE"):
                lock_data_root(self.config.data_root)
        finally:first.close()

    @unittest.skipUnless(os.name=="nt","Windows process containment")
    def test_child_process_dies_when_parent_is_forcibly_stopped(self):
        import ctypes
        from ctypes import wintypes
        code="from services.windows_native.windows_job import contain_process_tree; import subprocess,sys,time; contain_process_tree(); child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print(child.pid,flush=True); time.sleep(30)"
        parent=subprocess.Popen([sys.executable,"-c",code],cwd=REPO,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        handle=None
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        try:
            child_pid=int(parent.stdout.readline())
            handle=kernel.OpenProcess(0x100000,False,child_pid)
            self.assertTrue(handle)
            parent.terminate();parent.wait(timeout=5)
            self.assertEqual(kernel.WaitForSingleObject(handle,5000),0)
        finally:
            if parent.poll() is None:parent.kill();parent.wait()
            parent.stdout.close();parent.stderr.close()
            if handle:kernel.CloseHandle(handle)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=LocalServer(0,Config(data_root=Path(self.temp.name)),start_worker=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_port
        self.cookie=f"vf_native_session={self.server.session}"

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=10)
        hdr={"Cookie":self.cookie,"X-VF-CSRF":self.server.csrf,"Content-Type":"application/json",**(headers or {})}
        conn.request(method,path,json.dumps(body) if body is not None else None,headers=hdr)
        response=conn.getresponse();data=response.read();conn.close()
        return response.status,data

    def test_loopback_host_origin_and_csrf(self):
        body={"name":"Test","prompt":"Prompt"}
        for headers in ({"Host":f"evil.test:{self.port}"},{"Origin":"https://evil.test"},{"Sec-Fetch-Site":"cross-site"},{"X-VF-CSRF":"wrong"}):
            self.assertEqual(self.request("POST","/api/projects",body,headers)[0],403)
        self.assertEqual(self.request("POST","/api/projects",body,{"Cookie":""})[0],401)
        self.assertEqual(self.request("POST","/api/projects",body)[0],201)

    def test_http_review_gate_and_no_path_traversal(self):
        status,raw=self.request("POST","/api/projects",{"name":"Test","prompt":"Prompt"})
        p=json.loads(raw)
        status,raw=self.request("POST",f"/api/projects/{p['id']}/jobs",{"revision":1,"kind":"render","request_key":uuid.uuid4().hex})
        self.assertEqual(status,409);self.assertEqual(json.loads(raw)["code"],"HUMAN_APPROVAL_REQUIRED_BEFORE_TTS")
        self.assertEqual(self.request("GET","/../secrets/openai.env")[0],404)
        self.assertEqual(self.request("GET","/native.html")[0],200)

    def test_early_rejection_returns_json_with_unread_upload_bytes(self):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=10)
        conn.request("POST","/api/projects",b"untrusted" * 32768,headers={
            "Cookie":self.cookie,"X-VF-CSRF":"wrong","Content-Type":"application/json"})
        response=conn.getresponse(); body=json.loads(response.read()); conn.close()
        self.assertEqual(response.status,403)
        self.assertEqual(body["code"],"CSRF_TOKEN_REQUIRED")
        self.assertEqual(self.server.store.list(),[])

    def test_range_playback_and_old_video_invalidation(self):
        p=self.server.store.create("Test","Prompt")
        p=self.server.store.save(p["id"],1,proposal=proposal(),asset={"id":"image"})
        p=self.server.store.approve(p["id"],2,"Owner",True)
        job=self.server.store.enqueue(p["id"],2,"render",uuid.uuid4().hex)
        path=self.server.config.data_root/"jobs"/job["id"];path.mkdir(parents=True);(path/"final.mp4").write_bytes(b"0123456789")
        from services.windows_native.hardening import Artifacts
        result={"qc":{"passed":True,"final_sha256":file_sha(path/"final.mp4")},"explicit_transport_fixture":True}
        Artifacts(path,job).commit("render",[path/"final.mp4"],result)
        self.server.store.claim();self.server.store.finish(job,result=result)
        url=f"/api/jobs/{job['id']}/video"
        status,raw=self.request("GET",url,headers={"Range":"bytes=2-5"})
        self.assertEqual((status,raw),(206,b"2345"))
        self.server.store.save(p["id"],2,prompt="Changed")
        self.assertEqual(self.request("GET",url)[0],409)


if __name__=="__main__":
    unittest.main()
