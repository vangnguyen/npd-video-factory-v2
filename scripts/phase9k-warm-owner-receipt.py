"""Bind the real Owner B-onset approval and preserve a read-only repair baseline.

This one-shot evidence helper writes a receipt and two new external SQLite
backups. It never initializes Store, edits live databases, approves a final
render, dispatches work, or invokes a provider.
"""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "evidence/post-mvp-roadmap/phase-9/9k"
PREVIOUS = EVIDENCE / "audio-repair-02"
NEXT = EVIDENCE / "audio-repair-03"
DATA = Path("C:/NPD-Video-Factory/phase2")
BACKUPS = Path("C:/NPD-Video-Factory/post-mvp-validation")
GIT = Path("C:/Users/PC/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe")
WORDS = "Giọng B đạt"
EXPECTED_AUDIO_SHA256 = "18eca083913bc7e26247f521ae48f658422a0f4a54d40583c00f43fded6ec37f"
EXPECTED_MANIFEST_SHA256 = "5dc941c11bd3f92d80a4c4cff54bf9f95edb9cb3f3128043586540e6e7130bad"
EXPECTED_BUNDLE_SHA256 = "91d2239c2f64fe9df366e341b568fcb30767455f71517489a2078fd31028d735"
MUTABLE_REPORTS = {
    REPO / "POST_INTERNAL_PRODUCTION_PHASE9_REPORT.md",
    EVIDENCE / "phase9k-final-review.md",
    EVIDENCE / "phase9k-handoff-matrix.md",
    EVIDENCE / "real-production-checkpoint.md",
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def open_read_only(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def table_snapshot(connection):
    snapshots = {}
    for table in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"):
        quoted = '"' + table["name"].replace('"', '""') + '"'
        rows = [dict(row) for row in connection.execute("SELECT * FROM " + quoted)]
        rows.sort(key=canonical)
        snapshots[table["name"]] = {
            "ddl": table["sql"], "row_count": len(rows), "rows_sha256": digest(rows),
            "ordering": "canonical row bytes, ascending",
        }
    return snapshots


def preserve_backups(recorded_at, suffix):
    preserved = []
    for name in ("workflow", "intelligence"):
        live = DATA / (name + ".sqlite3")
        target = BACKUPS / ("owner-before-phase9k-warm-03-" + name + "-" +
                            recorded_at.strftime("%Y%m%dT%H%M%SZ") + "-" + suffix + ".sqlite3")
        # Reserve a fresh exact path before sqlite can create its backup file.
        with target.open("xb"):
            pass
        with open_read_only(live) as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        with open_read_only(target) as saved, open_read_only(live) as source:
            assert saved.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            before = table_snapshot(saved)
            assert before == table_snapshot(source), "Live database changed during receipt capture"
        preserved.append({"database": name, "source_path": str(live), "path": str(target),
                          "sha256": file_sha(target), "consistent_sqlite_backup": True,
                          "source_opened_read_only": True, "table_snapshots": before})
    return preserved


def main():
    target = NEXT / "owner-B-approval.json"
    assert not target.exists(), "Existing Owner receipt is immutable; inspect it before continuing"
    recorded = datetime.now(timezone.utc)
    manifest = read(PREVIOUS / "onset-review-manifest.json")
    assert file_sha(PREVIOUS / "onset-review-manifest.json") == EXPECTED_MANIFEST_SHA256
    assert file_sha(PREVIOUS / "onset-listening-bundle.md") == EXPECTED_BUNDLE_SHA256
    assert file_sha(manifest["audio"]) == manifest["audio_sha256"] == EXPECTED_AUDIO_SHA256
    assert len(manifest["pairs"]) == 8
    assert manifest["human_accepted_final_videos"] == manifest["native_video_jobs_created"] == 0
    samples = []
    for pair in manifest["pairs"]:
        folder = PREVIOUS / f'case-{pair["case"]:02}/scene-{pair["scene"]:02}'
        for name, key in (("A-current-onset.wav", "A_wave_sha256"),
                          ("B-warm-onset.wav", "B_wave_sha256"),
                          ("B-target-trial.wav", "B_target_wave_sha256")):
            assert file_sha(folder / name) == pair[key]
        boundary = read(folder / "boundary.json")
        samples.append({
            "case": pair["case"], "scene": pair["scene"], "owner_phrase": pair["owner_phrase"],
            "B_start_seconds": pair["B_start_seconds"],
            "excerpt_duration_seconds": pair["excerpt_duration_seconds"],
            "B_onset_path": str(folder / "B-warm-onset.wav"),
            "B_onset_sha256": pair["B_wave_sha256"],
            "B_target_path": str(folder / "B-target-trial.wav"),
            "B_target_sha256": pair["B_target_wave_sha256"],
            "B_context_source_sha256": pair["B_source_voice_sha256"],
            "boundary_sha256": file_sha(folder / "boundary.json"),
            "cut_seconds": boundary["cut_seconds"], "cut_method": boundary["method"],
            "provider_native_timestamps_are_approximate": True,
            "human_onset_audio_accepted": True, "full_script_word_accuracy_approved": False,
        })
    frozen = {path.relative_to(REPO).as_posix(): file_sha(path)
              for path in sorted((REPO / "evidence").rglob("*"))
              if path.is_file() and path not in MUTABLE_REPORTS and NEXT not in path.parents}
    baseline = read(EVIDENCE.parent / "release-baseline.json")
    for video in baseline["final_videos"]:
        assert file_sha(video["path"]) == video["sha256"]
    for name, sha in baseline["accepted_evidence"].items():
        assert file_sha(EVIDENCE.parent.parent / "phase-8" / name) == sha
    for package in baseline["dependencies"]:
        assert importlib.metadata.version(package["name"]) == package["version"]
    assert subprocess.check_output([str(GIT), "rev-parse", "internal-production-v1^{}"],
                                   cwd=REPO, text=True).strip() == baseline["head_sha"]
    backups = preserve_backups(recorded, uuid.uuid4().hex[:12])
    sys.path.insert(0, str(REPO))
    from services.windows_native.intelligence_lineage import projection
    cases = []
    previous = read(PREVIOUS / "owner-onset-feedback.json")
    with open_read_only(backups[0]["path"]) as workflow:
        assert workflow.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0] == 0
        for item in previous["cases"]:
            project = workflow.execute("SELECT * FROM projects WHERE id=?", (item["project_id"],)).fetchone()
            job = workflow.execute("SELECT * FROM jobs WHERE id=?", (item["job_id"],)).fetchone()
            document = json.loads(project["document"])
            snapshot = json.loads(job["snapshot"])
            approval = json.loads(project["approval"]) if project["approval"] else None
            review_row = workflow.execute("SELECT * FROM render_reviews WHERE job_id=? ORDER BY id DESC LIMIT 1",
                                          (job["id"],)).fetchone()
            final_review = dict(review_row) if review_row else None
            script_event = workflow.execute("SELECT payload FROM events WHERE project_id=? AND action='human_script_approved' ORDER BY id DESC LIMIT 1",
                                            (project["id"],)).fetchone()
            script_review = json.loads(script_event["payload"])
            lineage = projection(document)
            script_sha = hashlib.sha256(document["proposal"]["narration"].encode("utf-8")).hexdigest()
            assert script_review["script_sha256"] == script_sha
            assert script_review["lineage_sha256"] == digest(lineage)
            assert document == snapshot["document"] and digest(snapshot) == item["snapshot_sha256"]
            assert job["status"] == "succeeded" and job["revision"] == item["job_revision"] == 11
            assert project["revision"] == (12 if item["named_onsets"] else 11)
            assert (final_review["decision"] if final_review else "PENDING") == ("reject" if item["named_onsets"] else "PENDING")
            assert file_sha(DATA / "jobs" / job["id"] / "final.mp4") == item["final_sha256"]
            assert file_sha(DATA / "jobs" / job["id"] / "voice.wav") == item["voice_sha256"]
            cases.append({
                "case": item["case"], "project_id": project["id"],
                "current_revision": project["revision"], "current_document_sha256": digest(document),
                "current_approval_sha256": digest(approval) if approval else None,
                "proposal_sha256": digest(document["proposal"]),
                "prior_job_id": job["id"], "prior_job_revision": job["revision"],
                "prior_snapshot_sha256": digest(snapshot), "prior_final_sha256": item["final_sha256"],
                "prior_voice_sha256": item["voice_sha256"], "prior_final_review": final_review,
                "script_review_id": script_review["review_id"], "script_sha256": script_sha,
                "current_script_review": {**script_review, "current": True}, "research_lineage": lineage,
                "prior_job_row_sha256": digest(dict(job)), "prior_project_row_sha256": digest(dict(project)),
            })
    for name, sha in frozen.items():
        assert file_sha(REPO / name) == sha, "Historical evidence changed during receipt capture: " + name
    receipt = {
        "recorded_at": recorded.isoformat(), "received_timestamp_claimed": False,
        "source": "Direct human user message in this Codex chat", "owner_message": WORDS,
        "owner_message_sha256": hashlib.sha256(WORDS.encode("utf-8")).hexdigest(),
        "reviewer": "Owner — giọng B đạt qua Codex", "scope": "EIGHT_NAMED_B_ONSET_SAMPLES_AUDIO_QUALITY_ONLY",
        "classification": "OWNER_B_ONSET_AUDIO_APPROVED_ORDINARY_REPAIR_CONTINUES",
        "reviewed_audio_path": manifest["audio"], "reviewed_audio_sha256": EXPECTED_AUDIO_SHA256,
        "reviewed_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "reviewed_bundle_sha256": EXPECTED_BUNDLE_SHA256,
        "audio_duration_seconds": manifest["duration_seconds"], "accepted_samples": samples,
        "human_onset_audio_accepted": True, "full_script_word_accuracy_approved": False,
        "full_video_watch_listen_claimed": False, "final_video_approved": False,
        "human_accepted_final_videos": 0, "publishing_approved": False,
        "ordinary_audio_repair_and_internal_render_authorized": True,
        "authorization_basis": "Existing Phase9 execution authority, all-five repair scope, unchanged approved v2 scripts/media/internal-production approvals, and this B-onset response",
        "original_script_authorization_sha256": file_sha(EVIDENCE / "owner-script-authorization-v2.json"),
        "original_script_approval_manifest_sha256": file_sha(EVIDENCE / "script-approval-manifest.json"),
        "original_media_authorization_sha256": file_sha(EVIDENCE / "owner-media-authorization.json"),
        "earlier_all_five_repair_receipt_sha256": file_sha(EVIDENCE / "audio-repair-01/owner-feedback.json"),
        "prior_onset_rejection_receipt_sha256": file_sha(PREVIOUS / "owner-onset-feedback.json"),
        "final_acceptance_requirement": "Owner watches/listens to the exact new complete MP4s and explicitly accepts their final results; this response must not approve render jobs or mark opportunities PRODUCED",
        "cases": cases, "backups": backups,
        "table_snapshots": {item["database"]: item["table_snapshots"] for item in backups},
        "frozen_prior_evidence_base": str(REPO), "frozen_prior_evidence": frozen,
        "frozen_prior_file_count": len(frozen), "frozen_prior_evidence_unchanged": True,
        "excluded_mutable_reports": [path.relative_to(REPO).as_posix() for path in sorted(MUTABLE_REPORTS)],
        "baseline_head_sha": subprocess.check_output([str(GIT), "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "accepted_release_sha": baseline["head_sha"], "accepted_phase8_videos_unchanged": 10,
        "accepted_phase8_evidence_unchanged": True, "release_marker_unchanged": True,
        "runtime_dependencies_unchanged": True, "live_databases_mutated": False,
        "native_jobs_dispatched": 0, "provider_requests": 0, "CONTENT_INTELLIGENCE_READY": "NO",
    }
    NEXT.mkdir(exist_ok=True)
    with target.open("xb") as destination:
        destination.write(canonical(receipt))
    assert read(target) == receipt
    print(json.dumps({"receipt": str(target), "receipt_sha256": file_sha(target),
                      "B_onset_samples_accepted": len(samples), "cases_snapshotted": len(cases),
                      "backups": [{"database": item["database"], "path": item["path"], "sha256": item["sha256"]} for item in backups],
                      "frozen_prior_file_count": len(frozen), "live_databases_mutated": False,
                      "human_accepted_final_videos": 0}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
