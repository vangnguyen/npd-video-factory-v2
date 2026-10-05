"""20 isolated local render jobs, with real accepted WAV and real FFmpeg/QC.

Fixture script approval is synthetic and is NOT Owner final acceptance. No SDK/TTS dispatch.
"""
import argparse
import errno
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from unittest.mock import patch
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.hardening import Artifacts, durable_json
from services.windows_native.pipeline import Config, Pipeline, render
from services.windows_native.server import Runner
from services.windows_native.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=20)
    args = parser.parse_args()
    if not 20 <= args.jobs <= 30:
        raise ValueError("batch requires 20–30 local jobs")
    config = Config(data_root=args.data_root.resolve()); config.validate_data_root()
    if config.data_root.exists():
        raise ValueError("FRESH_BATCH_DIRECTORY_REQUIRED_NO_OVERWRITE")
    source = Path(r"C:\NPD-Video-Factory\outputs\MVP1")
    accepted = json.loads((source / "owner-final-video-approval.json").read_bytes())
    assert file_sha(source / "voice.wav") == accepted["voice_sha256"]
    proposal = json.loads((source / "content-proposal.json").read_bytes())
    timing = Path(r"C:\NPD-Video-Factory\phase2-validation\single-media-regression\voice.json")
    voice = json.loads(timing.read_bytes()); assert voice["audio_sha256"] == accepted["voice_sha256"]
    source_manifest = json.loads((source / "render-manifest.json").read_bytes())
    image = Path(source_manifest["source_asset"])
    assert file_sha(image) == source_manifest["source_asset_sha256"]
    store = Store(config.data_root)
    assets = config.data_root / "assets"; assets.mkdir()
    shutil.copyfile(image, assets / "accepted-image.jpg")
    asset = {"id": "accepted-image.jpg", "kind": "image", "filename": "accepted MVP source (batch fixture)",
             "sha256": file_sha(image), "rights_confirmed": True, "illustration": True}
    results = []
    for index in range(args.jobs):
        project = store.create(f"Hardening local fixture {index+1:02}", "Existing accepted script/WAV; no new provider request")
        project = store.save(project["id"], 1, proposal=proposal, asset=asset)
        project = store.approve(project["id"], project["revision"], "INTEGRATION FIXTURE — NOT OWNER ACCEPTANCE", True)
        before = digest({k: project[k] for k in ("document", "revision", "approval")})
        key = "hardening-batch-" + uuid.uuid4().hex
        job = store.enqueue(project["id"], project["revision"], "render", key)
        assert store.enqueue(project["id"], project["revision"], "render", key)["id"] == job["id"]
        out = config.data_root / "jobs" / job["id"]; out.mkdir(parents=True)
        art = Artifacts(out, job)
        wav = art.publish(source / "voice.wav", "voice.wav")
        meta = art.publish(timing, "voice.json")
        art.commit("tts", [wav, meta], {"fixture_seed": "reused_existing_real_accepted_WAV",
                   "new_inference": False, "source": str(source / "voice.wav"), "source_sha256": file_sha(wav)})
        runner = Runner(store, Pipeline(config)); fault = None
        if index == 0:
            fault = "injected_render_timeout_then_real_retry"
            calls = [0]
            def render_with_timeout(*a, **kw):
                calls[0] += 1
                if calls[0] == 1: raise subprocess.TimeoutExpired("injected fixture", .01)
                return render(*a, **kw)
            with patch("services.windows_native.pipeline.render", render_with_timeout):
                runner.run_one()
        elif index == 1:
            fault = "injected_failure_then_same_job_resume_real_render"
            with patch("services.windows_native.pipeline.render", side_effect=WorkflowError("FFMPEG_RENDER_FAILED")):
                runner.run_one()
            failed_project = store.get(project["id"])
            assert digest({k: failed_project[k] for k in ("document", "revision", "approval")}) == before
            assert store.get_job(job["id"])["failure"]["action"]
            assert store.resume(job["id"])["id"] == job["id"]
            assert store.resume(job["id"])["resume_count"] == 1
            runner.run_one()
        elif index == 2:
            fault = "interrupted_job_reopened_then_explicit_resume_from_verified_audio"
            store.claim(); reopened = Store(config.data_root); reopened.recover()
            assert reopened.get_job(job["id"])["status"] == "interrupted"
            reopened.resume(job["id"]); Runner(reopened, Pipeline(config)).run_one()
        elif index == 3:
            fault = "injected_transient_publish_io_then_retry_without_rerender"
            original = Artifacts.publish; raised = [False]
            def sharing_error(self, path, name):
                if name == "final.mp4" and not raised[0]:
                    raised[0] = True; raise BlockingIOError(errno.EBUSY, "injected sharing fixture")
                return original(self, path, name)
            with patch.object(Artifacts, "publish", sharing_error):
                runner.run_one()
        else:
            runner.run_one()
        current = store.get_job(job["id"])
        assert current["status"] == "succeeded", current
        assert current["result"]["qc"]["passed"]
        assert Artifacts(out, job).load("render")
        after = store.get(project["id"])
        assert digest({k: after[k] for k in ("document", "revision", "approval")}) == before
        assert len(after["jobs"]) == 1
        results.append({"job_id": job["id"], "project_id": project["id"], "status": current["status"],
                        "lifecycle": current["lifecycle"], "retry_count": current["retry_count"],
                        "resume_count": current["resume_count"], "fault": fault,
                        "final_mp4": str(out / "final.mp4"), "qc": current["result"]["qc"],
                        "render_version": current["result"]["render_version"],
                        "new_provider_calls": 0, "new_tts_inferences": 0, "human_final_accepted": False})
        print(json.dumps({"completed": len(results), "total": args.jobs, "job_id": job["id"],
                          "qc": "PASS", "retry_count": current["retry_count"], "resume_count": current["resume_count"]}), flush=True)
    with store.transaction() as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        logs = [{**json.loads(r["payload"]), "created_at": r["created_at"]} for r in con.execute("SELECT payload,created_at FROM events WHERE action='job_step' ORDER BY id")]
    report = {"status": "PASS", "scope": "twenty isolated real FFmpeg render/QC jobs with reused real accepted WAV; fixture approvals; not a production/human acceptance batch",
              "data_root": str(config.data_root), "sqlite_integrity": integrity, "jobs": results,
              "new_provider_calls": 0, "new_tts_inferences": 0, "owner_project_changed": False,
              "structured_logs": logs}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.report.exists(): raise ValueError("REPORT_EXISTS_NO_OVERWRITE")
    durable_json(args.report, report)
    print(json.dumps({"status": "PASS", "jobs": len(results), "integrity": integrity, "report": str(args.report)}))


if __name__ == "__main__":
    main()
