import errno
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.hardening import Artifacts, failure, retry_io
from services.windows_native.pipeline import Config, Pipeline, provider_request
from services.windows_native.contracts import PROFILE_SHA, file_sha
from services.windows_native.server import Runner
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.project = self.store.create("Hardening fixture", "Prompt")

    def tearDown(self):
        self.temp.cleanup()

    def job(self, kind="content"):
        return self.store.enqueue(self.project["id"], self.project["revision"], kind, uuid.uuid4().hex)

    def test_history_is_immutable_and_approval_does_not_change_content_version(self):
        first = self.project["document"]
        self.project = self.store.save(self.project["id"], 1, proposal=proposal(), asset={"id": "fixture.jpg"})
        self.project = self.store.approve(self.project["id"], 2, "FIXTURE ONLY", True)
        versions = self.store.versions(self.project["id"])
        self.assertEqual([v["revision"] for v in versions], [2, 1])
        self.assertEqual(versions[-1]["document"], first)
        self.assertNotEqual(versions[0]["components"]["script_version"], versions[1]["components"]["script_version"])
        self.assertEqual(Store(self.root).versions(self.project["id"]), versions)

    def test_additive_upgrade_preserves_legacy_rows_and_original_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.sqlite3"
            con = sqlite3.connect(path)
            try:
                con.executescript("CREATE TABLE projects(id TEXT PRIMARY KEY,revision INTEGER,document TEXT,approval TEXT,created_at TEXT,updated_at TEXT); CREATE TABLE jobs(id TEXT PRIMARY KEY,project_id TEXT,revision INTEGER,kind TEXT,status TEXT,stage TEXT,request_key TEXT UNIQUE,request_sha TEXT,snapshot TEXT,error TEXT,result TEXT,created_at TEXT,updated_at TEXT); CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT,action TEXT,payload TEXT,created_at TEXT);")
                con.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)", ("legacy", 9, json.dumps(self.project["document"]), None, "original", "original"))
                con.commit()
            finally:
                con.close()
            upgraded = Store(directory)
            self.assertEqual(upgraded.get("legacy")["document"], self.project["document"])
            self.assertEqual([v["revision"] for v in upgraded.versions("legacy")], [9])
            with upgraded.transaction() as con:
                self.assertEqual(len(con.execute("PRAGMA table_info(projects)").fetchall()), 6)
                self.assertEqual(len(con.execute("PRAGMA table_info(jobs)").fetchall()), 13)
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_retry_and_resume_keep_one_receipt_and_freeze_active_project(self):
        job = self.job(); self.store.claim()
        self.store.stage(job["id"], "retrying:content_request")
        current = self.store.get_job(job["id"])
        self.assertEqual((current["lifecycle"], current["retry_count"]), ("RETRYING", 1))
        with self.assertRaisesRegex(WorkflowError, "PROJECT_BUSY"):
            self.store.save(self.project["id"], 1, prompt="Can't edit")
        self.store.recover()
        resumed = self.store.resume(job["id"])
        self.assertEqual(resumed["id"], job["id"])
        self.assertEqual(self.store.resume(job["id"])["resume_count"], 1)
        self.assertEqual(len(self.store.get(self.project["id"])["jobs"]), 1)

    def test_changed_project_blocks_resume_without_affecting_saved_edit(self):
        job = self.job(); self.store.claim(); self.store.finish(job, error={"code": "TestFault"})
        p = self.store.save(self.project["id"], 1, prompt="New prompt")
        with self.assertRaisesRegex(WorkflowError, "STALE_VERSION"):
            self.store.resume(job["id"])
        self.assertEqual(self.store.get(p["id"])["document"]["prompt"], "New prompt")

    def test_unknown_paid_intent_blocks_resume(self):
        job = self.job(); self.store.claim(); self.store.finish(job, error={"code": "OPENAI_TIMEOUT_OUTCOME_UNKNOWN_NO_RETRY"})
        out = self.root / "jobs" / job["id"]; out.mkdir(parents=True)
        (out / "content.intent.json").write_text("{}")
        with self.assertRaisesRegex(WorkflowError, "OPENAI_OUTCOME_UNKNOWN_NO_REPLAY"):
            self.store.resume(job["id"])
        self.assertEqual(self.store.get_job(job["id"])["status"], "failed")

    def test_checkpoint_rejects_changed_bytes_and_snapshot(self):
        job = self.job(); out = self.root / "jobs" / job["id"]; out.mkdir(parents=True)
        path = out / "result.json"; path.write_text("original")
        art = Artifacts(out, job); art.commit("content", [path], {"proposal": proposal()})
        path.write_text("changed!")
        with self.assertRaisesRegex(WorkflowError, "CHECKPOINT_ARTIFACT_CHANGED"):
            art.load("content")
        path.write_text("original")
        changed = {**job, "snapshot": {**job["snapshot"], "document": {"prompt": "other"}}}
        with self.assertRaisesRegex(WorkflowError, "CHECKPOINT_BINDING_MISMATCH"):
            Artifacts(out, changed).load("content")

    def test_completed_content_checkpoint_restores_without_sdk_dispatch(self):
        job = self.job(); out = self.root / "jobs" / job["id"]; out.mkdir(parents=True)
        result = {"proposal": proposal(), "test_double": True}
        path = out / "result.json"; path.write_text(json.dumps(result))
        Artifacts(out, job).commit("content", [path], result)
        with patch("services.windows_native.pipeline.generate") as generate:
            restored = Pipeline(Config(data_root=self.root)).run(job, lambda _: None)
        self.assertEqual(restored, result); generate.assert_not_called()

    def test_provider_429_retries_once_but_timeout_and_500_never_replay(self):
        import httpx2, openai
        request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
        for code in (429, 500, "timeout"):
            with self.subTest(code=code):
                out = self.root / str(code); out.mkdir()
                job = self.job(); self.store.claim(); self.store.finish(job, error={"code": "fixture"})
                error = openai.APITimeoutError(request=request) if code == "timeout" else openai.APIStatusError("fixture", response=httpx2.Response(code, request=request), body=None)
                client = SimpleNamespace(responses=SimpleNamespace(create=None))
                calls = []
                def call(**kwargs):
                    calls.append(kwargs)
                    if len(calls) == 1: raise error
                    return "test-response"
                client.responses.create = call
                with patch("services.windows_native.pipeline.time.sleep"):
                    if code == 429:
                        self.assertEqual(provider_request(client, {}, job, out, lambda _: None, openai), ("test-response", 2))
                    else:
                        with self.assertRaises(type(error)):
                            provider_request(client, {}, job, out, lambda _: None, openai)
                        with self.assertRaisesRegex(WorkflowError, "OUTCOME_UNKNOWN"):
                            provider_request(client, {}, job, out, lambda _: None, openai)
                self.assertEqual(len(calls), 2 if code == 429 else 1)

    def test_transient_io_retries_once_and_permanent_failure_stops(self):
        calls, stages = [], []
        def operation():
            calls.append(1)
            if len(calls) == 1: raise BlockingIOError(errno.EBUSY, "fixture")
            return 123
        with patch("services.windows_native.hardening.time.sleep"):
            self.assertEqual(retry_io(operation, stages.append, "storage"), 123)
        self.assertEqual(len(calls), 2); self.assertEqual(stages[0], "retrying:storage")
        with self.assertRaises(PermissionError):
            retry_io(lambda: (_ for _ in ()).throw(PermissionError(errno.EACCES, "fixture")), stages.append, "storage")

    def test_tts_launch_io_retries_and_later_render_resume_never_reinfers(self):
        self.project = self.store.save(self.project["id"], 1, proposal=proposal(), asset={"id": "fixture.jpg"})
        self.project = self.store.approve(self.project["id"], 2, "FIXTURE ONLY", True)
        job = self.job("render"); calls = []
        def child(command, **kwargs):
            calls.append(command)
            if len(calls) == 1: raise BlockingIOError(errno.EBUSY, "injected child startup IO")
            out = Path(command[-1]); (out / "voice.wav").write_bytes(b"test audio fixture; not real TTS evidence")
            units = [{"scene": i+1, "text": text["narration_excerpt"], "start_seconds": i,
                      "activity_start_seconds": i+.1, "activity_end_seconds": i+.9, "end_seconds": i+1}
                     for i,text in enumerate(job["snapshot"]["document"]["proposal"]["visual_brief"])]
            (out / "voice.json").write_text(json.dumps({"audio_sha256": file_sha(out / "voice.wav"),
                           "profile_sha256": PROFILE_SHA, "duration_seconds": 3, "units": units}))
            (out / "tts-plan.json").write_text("{}")
            return SimpleNamespace(returncode=0)
        stages = []
        with patch("services.windows_native.pipeline.verify_selected_files"), patch("services.windows_native.pipeline.subprocess.run", child), patch("services.windows_native.pipeline.render", side_effect=WorkflowError("FFMPEG_RENDER_FAILED")), patch("services.windows_native.hardening.time.sleep"):
            for _ in range(2):
                with self.assertRaisesRegex(WorkflowError, "FFMPEG_RENDER_FAILED"):
                    Pipeline(Config(data_root=self.root)).run(job, stages.append)
        self.assertEqual(len(calls), 2)  # One launch rejection, one completed child; resume reuses audio.
        self.assertIn("retrying:locked_thuy_dung_tts", stages)
        self.assertIn("resuming_verified_tts", stages)

    def test_structured_log_has_required_fields_and_actionable_failure(self):
        job = self.job()
        class Fault:
            def run(self, job, stage):
                stage("locked_thuy_dung_tts")
                raise OSError("SENSITIVE TEST EXCEPTION BODY MUST NOT ENTER LOG")
        Runner(self.store, Fault()).run_one()
        current = self.store.get_job(job["id"])
        self.assertEqual(current["failure"]["category"], "TTS_ERROR")
        self.assertTrue(current["failure"]["action"])
        with self.store.transaction() as con:
            logs = [json.loads(r[0]) for r in con.execute("SELECT payload FROM events WHERE action='job_step'")]
        self.assertTrue(logs)
        for log in logs:
            self.assertTrue({"job_id", "project_id", "step", "provider", "duration", "retry_count", "error_code"} <= set(log))
        self.assertNotIn("SENSITIVE", json.dumps(logs))

    def test_all_required_taxonomy_categories_exist(self):
        samples = {"USER_INPUT_ERROR": "INPUT_REQUIRED", "PROVIDER_ERROR": "OPENAI_TIMEOUT", "TTS_ERROR": "TTS_CHILD_FAILED",
                   "ASR_ERROR": "ASR_UNAVAILABLE", "MEDIA_ERROR": "MEDIA_FILE_TOO_LARGE", "RENDER_ERROR": "FFMPEG_RENDER_FAILED",
                   "STORAGE_ERROR": "STORAGE_FULL", "INTERNAL_ERROR": "UnexpectedException"}
        self.assertEqual({failure(c)["category"] for c in samples.values()}, set(samples))


if __name__ == "__main__":
    unittest.main()
