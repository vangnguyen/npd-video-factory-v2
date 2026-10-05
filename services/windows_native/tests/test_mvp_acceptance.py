"""Restart and fault isolation checks. Test doubles never certify real provider/TTS output."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.pipeline import REPO
from services.windows_native.server import Runner
from services.windows_native.store import Store
from services.windows_native.tests.test_workflow import proposal


class MvpAcceptanceTests(unittest.TestCase):
    def test_separate_process_restart_keeps_exact_document_and_revision(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            project = store.create("Restart fixture", "Isolated persistence test")
            project = store.save(project["id"], 1, proposal=proposal())
            expected = {k: project[k] for k in ("document", "revision", "approval")}
            code = "import json,sys; from services.windows_native.store import Store; p=Store(sys.argv[1]).get(sys.argv[2]); print(json.dumps({k:p[k] for k in ('document','revision','approval')}))"
            for _ in range(2):
                output = subprocess.check_output([sys.executable, "-c", code, root, project["id"]],
                                                 cwd=REPO, timeout=20)
                self.assertEqual(json.loads(output), expected)

    def test_provider_tts_render_failures_preserve_snapshot_and_allow_revision(self):
        for kind, step, error_code in (("content", "content_request", "OPENAI_CONNECTION_ERROR_NO_RETRY"),
                                       ("render", "locked_thuy_dung_tts", "TTS_CHILD_FAILED"),
                                       ("render", "ffmpeg_render_and_qc", "FFMPEG_RENDER_FAILED")):
            with self.subTest(step=step), tempfile.TemporaryDirectory() as root:
                store = Store(root)
                project = store.create("Fault fixture", "No live provider dispatch")
                if kind == "render":
                    project = store.save(project["id"], 1, proposal=proposal(), asset={"id": "fixture.jpg"})
                    project = store.approve(project["id"], project["revision"], "TEST FIXTURE ONLY", True)
                before = digest({k: project[k] for k in ("document", "revision", "approval")})
                job = store.enqueue(project["id"], project["revision"], kind, "fault-" + step)

                class Fault:
                    def run(self, job, stage):
                        stage(step)
                        raise WorkflowError(error_code)

                runner = Runner(store, Fault())
                self.assertTrue(runner.run_one())
                self.assertFalse(runner.run_one())
                reopened = Store(root)
                after = reopened.get(project["id"])
                self.assertEqual(digest({k: after[k] for k in ("document", "revision", "approval")}), before)
                self.assertEqual(reopened.get_job(job["id"])["status"], "failed")
                with closing(sqlite3.connect(Path(root) / "workflow.sqlite3")) as con:
                    self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                edited = reopened.save(project["id"], project["revision"], prompt="Revised after failure")
                self.assertEqual(edited["revision"], project["revision"] + 1)
                self.assertIsNone(edited["approval"])


if __name__ == "__main__":
    unittest.main()
