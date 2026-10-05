"""Explicit provider fixtures test safety; real speech acceptance is separate."""
import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

from PIL import Image
from services.windows_native import asr
from services.windows_native.contracts import WorkflowError, file_sha
from services.windows_native.hardening import Artifacts, failure
from services.windows_native.ingestion import provider_context, transcript_script
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Config, Pipeline, verify_runtime
from services.windows_native.server import Runner
from services.windows_native.store import Store

KEY = "EXPLICIT_FIXTURE_ASR_KEY_NOT_REAL"


class FixtureTransport(asr.DurableTransport):
    calls = []
    fail_upload = False
    fail_observe_once = False
    invalid_timing = False

    async def request(self, method, path, credential, timeout, **kwargs):
        self.calls.append((method, path))
        if path == "/v2/upload":
            if self.fail_upload: raise TimeoutError()
            return {"upload_url": "https://cdn.assemblyai.com/fixture.wav"}
        if path == "/v2/transcript":
            return {"id": "fixture-transcript-1"}
        if self.fail_observe_once:
            type(self).fail_observe_once = False
            raise TimeoutError()
        return {"id":"fixture-transcript-1","status":"completed","language_code":"vi",
                "speech_model_used":"universal-3-5-pro","text":"Xin chào.",
                "words":[{"text":"Xin","start":0,"end":200,"confidence":.9},
                         {"text":"chào.","start":100 if self.invalid_timing else 210,"end":500,"confidence":.8}],
                "explicit_test_fixture":True}


class AsrTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.config=Config(data_root=self.root); self.store=Store(self.root)
        self.project=self.store.create("ASR fixture", "", "media")
        source=self.root/"fixture-sine-not-speech.mp4"
        subprocess.run([str(self.config.ffmpeg_bin/"ffmpeg.exe"),"-v","error","-nostdin","-n",
            "-f","lavfi","-i","color=c=green:s=320x240:r=30:d=1","-f","lavfi","-i","sine=frequency=440:duration=1",
            "-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-t","1",str(source)],check=True,capture_output=True,timeout=20)
        self.source=source; self.original_sha=file_sha(source)
        asset=ingest_media(self.config,source,"video/mp4","unrelated-name.jpg",rights_confirmed=True,illustration=False)
        self.project=self.store.append_media(self.project["id"],1,asset); self.asset=asset
        FixtureTransport.calls=[]; FixtureTransport.fail_upload=False; FixtureTransport.fail_observe_once=False; FixtureTransport.invalid_timing=False
        self.patches=[patch.object(asr.connection,"status",return_value={"connected":True}),
                      patch.object(asr.connection,"load_credential",return_value=KEY),
                      patch.object(asr,"analyze",side_effect=lambda c,j,o,s: self.analyze_original(c,j,o,s,transport_factory=FixtureTransport))]
        self.analyze_original=asr.analyze
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def run_job(self):
        job=self.store.enqueue(self.project["id"],self.project["revision"],"asr",uuid.uuid4().hex)
        Runner(self.store,Pipeline(self.config)).run_one()
        return self.store.get_job(job["id"])

    def test_extract_persist_timestamps_lineage_restart_and_script_without_generation(self):
        job=self.run_job(); self.assertEqual(job["status"],"succeeded")
        project=Store(self.root).get(self.project["id"])
        record=project["document"]["media_analysis"][0]
        self.assertEqual(record["transcript"]["segments"][0]["text"],"Xin chào.")
        self.assertEqual(record["transcript"]["segments"][0]["words"][1]["start_seconds"],.21)
        self.assertEqual(record["media"]["shots"],[{"start_seconds":0.,"end_seconds":1.}])
        self.assertEqual(project["input"]["metadata"]["workflow"],"REVIEW_TRANSCRIPT")
        self.assertFalse(project["input"]["metadata"]["untranscribed_video_audio"])
        self.assertEqual(transcript_script(project["document"]),"Xin chào.")
        self.assertIn("Xin chào.",provider_context(project["document"]))
        self.assertIsNone(project["approval"])
        self.assertEqual(file_sha(self.source),self.original_sha)
        self.assertEqual(file_sha(self.root/"originals"/self.asset["original_id"]),self.original_sha)
        self.assertEqual(len(FixtureTransport.calls),3)
        self.store.enqueue(project["id"],project["revision"],"content",uuid.uuid4().hex)
        with patch("services.windows_native.pipeline.generate") as provider:
            Runner(self.store,Pipeline(self.config)).run_one(); provider.assert_not_called()
        result=self.store.get(project["id"])
        self.assertEqual(result["document"]["proposal"]["narration"],"Xin chào.")
        self.assertEqual(result["jobs"][0]["result"]["provider_calls"],0)
        self.assertIn("AssemblyAI",result["document"]["proposal"]["facts_needing_source"][0])
        self.assertNotIn(KEY,(self.root/"jobs"/job["id"]/"analysis-result.json").read_text(encoding="utf-8"))

    def test_known_job_observation_resume_never_uploads_or_creates_twice(self):
        FixtureTransport.fail_observe_once=True
        job=self.run_job(); self.assertEqual(job["status"],"failed")
        self.assertNotIn("media_analysis",self.store.get(self.project["id"])["document"])
        self.assertEqual(self.store.get(self.project["id"])["revision"],self.project["revision"])
        self.assertEqual(job["failure"]["category"],"ASR_ERROR")
        with self.assertRaisesRegex(WorkflowError,"ASR_EXISTING_JOB_RESUME_REQUIRED"):
            self.store.enqueue(self.project["id"],self.project["revision"],"asr",uuid.uuid4().hex)
        self.store.resume(job["id"]); Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(self.store.get_job(job["id"])["status"],"succeeded")
        self.assertEqual(sum(m=="POST" and p=="/v2/upload" for m,p in FixtureTransport.calls),1)
        self.assertEqual(sum(m=="POST" and p=="/v2/transcript" for m,p in FixtureTransport.calls),1)
        self.assertEqual(sum(m=="GET" for m,p in FixtureTransport.calls),2)

    def test_unknown_upload_blocks_resume_and_leaves_original_project_unchanged(self):
        before=self.store.get(self.project["id"])["document"]
        FixtureTransport.fail_upload=True
        job=self.run_job(); self.assertEqual(job["status"],"failed")
        with self.assertRaisesRegex(WorkflowError,"ASR_OUTCOME_UNKNOWN_NO_REPLAY"):
            self.store.resume(job["id"])
        self.assertEqual(self.store.get(self.project["id"])["document"],before)
        self.assertEqual(len(FixtureTransport.calls),1)

    def test_bad_word_timing_no_fake_result_and_complete_receipt_not_reposted(self):
        FixtureTransport.invalid_timing=True
        job=self.run_job(); self.assertEqual(job["status"],"failed")
        self.assertIn("WORD_TIMING_NON_MONOTONIC",job["error"]["code"])
        self.assertNotIn("media_analysis",self.store.get(self.project["id"])["document"])
        self.store.resume(job["id"]); Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(len(FixtureTransport.calls),3)
        self.assertEqual(self.store.get_job(job["id"])["status"],"failed")

    def test_unavailable_credential_explicit_error_zero_uploads(self):
        with patch.object(asr.connection,"status",return_value={"connected":False}):
            job=self.run_job()
        self.assertEqual(job["error"]["code"],"ASR_PROVIDER_UNAVAILABLE_NO_TRANSCRIPT")
        self.assertEqual(FixtureTransport.calls,[])
        self.assertNotIn("media_analysis",self.store.get(self.project["id"])["document"])

    def test_changed_source_and_audio_checkpoint_refuse_before_external_dispatch(self):
        FixtureTransport.fail_observe_once=True
        job=self.run_job()
        audio=self.root/"jobs"/job["id"]/"analysis"/self.asset["id"]/"speech.wav"
        audio.write_bytes(audio.read_bytes()+b"corruption")
        with self.assertRaisesRegex(WorkflowError,"CHECKPOINT_ARTIFACT_CHANGED"):
            self.store.resume(job["id"])
        self.assertEqual(len(FixtureTransport.calls),3)

    def test_images_local_only_and_measured_descriptors_no_filename_guess(self):
        p=self.store.create("Image", "", "media")
        image=self.root/"photo.png"; Image.new("RGB",(320,240),(10,100,20)).save(image)
        asset=ingest_media(self.config,image,"image/png","official-luxury-resort.jpg",rights_confirmed=True,illustration=False)
        p=self.store.append_media(p["id"],1,asset)
        self.store.enqueue(p["id"],p["revision"],"asr",uuid.uuid4().hex)
        with patch.object(asr.connection,"status",return_value={"connected":False}):
            Runner(self.store,Pipeline(self.config)).run_one()
        result=self.store.get(p["id"])
        self.assertEqual(result["jobs"][0]["status"],"succeeded")
        record=result["document"]["media_analysis"][0]
        self.assertIsNone(record["transcript"])
        self.assertEqual(record["media"]["semantic_content"],"not_analyzed")
        self.assertEqual(FixtureTransport.calls,[])

    def test_no_duplicate_job_same_request_and_preserved_voice_runtime(self):
        key=uuid.uuid4().hex
        a=self.store.enqueue(self.project["id"],self.project["revision"],"asr",key)
        b=self.store.enqueue(self.project["id"],self.project["revision"],"asr",key)
        self.assertEqual(a["id"],b["id"])
        self.assertEqual(verify_runtime(self.config,False)["voice"],"Thùy Dung")
        self.assertEqual(failure("ASR_PROVIDER_ERROR")["category"],"ASR_ERROR")

    def test_complete_checkpoint_corruption_rejected_before_any_additional_calls(self):
        job=self.run_job(); self.assertEqual(job["status"],"succeeded")
        out=self.root/"jobs"/job["id"]
        receipt=out/"analysis"/self.asset["id"]/"provider"/"provider-completed.json"
        receipt.write_bytes(receipt.read_bytes()+b" ")
        with self.assertRaisesRegex(WorkflowError,"CHECKPOINT_ARTIFACT_CHANGED"):
            Pipeline(self.config).run(job,lambda _:None)
        self.assertEqual(len(FixtureTransport.calls),3)


class TransportBoundaryTests(unittest.TestCase):
    def test_fixed_tls_origin_no_redirect_proxy_or_body_secret_retention(self):
        import httpx2
        with tempfile.TemporaryDirectory() as folder:
            options=[]; requests=[]
            def handler(request):
                requests.append((request.method,str(request.url)))
                self.assertEqual(request.headers["authorization"],KEY)
                return httpx2.Response(200,json={"ok":True})
            def factory(**kwargs):
                options.append(kwargs)
                return httpx2.AsyncClient(transport=httpx2.MockTransport(handler),**kwargs)
            transport=asr.DurableTransport(Path(folder),"fixture-binding",lambda _:None,client_factory=factory)
            result=asyncio.run(transport.request("GET","/v2/transcript/fixture",KEY,5))
            self.assertEqual(result,{"ok":True})
            self.assertEqual(requests,[("GET","https://api.assemblyai.com/v2/transcript/fixture")])
            self.assertFalse(options[0]["trust_env"]); self.assertFalse(options[0]["follow_redirects"])
            def redirect(request):return httpx2.Response(302,headers={"location":"https://unrelated.example"})
            transport.client_factory=lambda **kw:httpx2.AsyncClient(transport=httpx2.MockTransport(redirect),**kw)
            with self.assertRaisesRegex(WorkflowError,"ASR_HTTP_REQUEST_FAILED"):
                asyncio.run(transport.request("GET","/v2/transcript/fixture",KEY,5))
            def echo(request):return httpx2.Response(200,json={"echo":KEY})
            transport.client_factory=lambda **kw:httpx2.AsyncClient(transport=httpx2.MockTransport(echo),**kw)
            with self.assertRaisesRegex(WorkflowError,"ASR_RESPONSE_CONTAINS_CREDENTIAL_REJECTED"):
                asyncio.run(transport.request("GET","/v2/transcript/fixture",KEY,5))
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_language_model_and_id_mismatch_rejected_without_completed_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            transport=asr.DurableTransport(Path(folder),"fixture-binding",lambda _:None)
            for extra,code in (({"language_code":"en"},"ASR_LANGUAGE_MISMATCH"),
                               ({"speech_model_used":"universal-2"},"ASR_MODEL_MISMATCH_NO_FALLBACK"),
                               ({"speech_model_used":None},"ASR_MODEL_MISMATCH_NO_FALLBACK"),
                               ({"id":"other"},"ASR_TRANSCRIPT_ID_CHANGED")):
                async def request(*args,**kwargs):
                    return {"id":"fixture","status":"completed","language_code":"vi","speech_model_used":"universal-3-5-pro",**extra}
                transport.request=request
                with self.assertRaisesRegex(WorkflowError,code):
                    asyncio.run(transport.get_transcript("fixture",KEY,5))
                self.assertFalse((Path(folder)/"provider-completed.json").exists())


if __name__=="__main__":unittest.main()
