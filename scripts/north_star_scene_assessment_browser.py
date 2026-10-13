"""Owned loopback UI rehearsal over a checksum-verified prior Native backup.

This helper restores existing evidence. It does not run ASR, media inference,
workers, publishing, or Owner acceptance. The only auth token is an explicit
Editor fixture. Pass actual archive/checksum/project/output paths explicitly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "apps/api"), str(REPO)]

from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup, guard, restore_backup
from services.windows_native.contracts import digest, file_sha
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture

WORKSPACE = "wsp_word_browser_fixture"


def write_json(path: Path, value) -> None:
    # Every exported file is new; never overwrite accepted evidence.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


class RehearsalServer(LocalServer):
    """Drain owned request threads before creating the offline recovery copy."""

    daemon_threads = False
    block_on_close = False

    def __init__(self, *args, **kwargs):
        self.request_lock = threading.Lock()
        self.requests = {}
        self.stopping = False
        super().__init__(*args, **kwargs)

    def process_request_thread(self, request, client_address):
        with self.request_lock:
            self.requests[request] = threading.current_thread()
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.request_lock:
                self.requests.pop(request, None)

    def handle_error(self, request, client_address):
        # Closing an owned idle browser connection is expected during shutdown.
        if not self.stopping:
            super().handle_error(request, client_address)

    def stop_and_drain(self, serve_thread):
        self.stopping = True
        self.shutdown()
        serve_thread.join(timeout=10)
        if serve_thread.is_alive():
            raise RuntimeError("Owned loopback serve thread did not stop")
        with self.request_lock:
            requests = list(self.requests.items())
        for connection, _ in requests:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.server_close()
        deadline = time.monotonic() + 30
        for _, request_thread in requests:
            request_thread.join(timeout=max(0, deadline - time.monotonic()))
        with self.request_lock:
            if self.requests:
                raise RuntimeError("Owned request threads remain; state retained without cleanup")


def project_facts(project):
    document = project["document"]
    analyses = []
    for record in document.get("auto_edit_analyses", []):
        analysis = record["analysis"]
        transcript = analysis.get("transcript")
        analyses.append({
            "analysis_id": analysis["analysis_id"],
            "asset_id": analysis["asset_id"],
            "analysis_sha256": record["sha256"],
            "original_transcript_id": transcript["transcript_id"] if transcript else None,
            "original_transcript_version": transcript["version"] if transcript else None,
            "original_transcript_sha256": digest(transcript) if transcript else None,
        })
    timeline = document.get("canonical_timeline")
    return {
        "project_id": project["id"], "revision": project["revision"],
        "document_sha256": digest(document),
        "assets": [{"asset_id": asset["id"], "sha256": asset["sha256"],
            "filename": asset.get("filename"), "rights_status": asset.get("rights_status")}
            for asset in document.get("assets", [])],
        "analyses": analyses,
        "original_analysis_records_sha256": digest(document.get("auto_edit_analyses", [])),
        "original_media_analysis_sha256": digest(document.get("media_analysis", [])),
        "jobs": [{"job_id": job["id"], "kind": job["kind"], "status": job["status"]}
            for job in project.get("jobs", [])],
        "timeline_version": timeline.get("version") if timeline else None,
        "timeline_sha256": timeline.get("sha256") if timeline else None,
        "new_model_inferences": 0, "provider_calls_from_helper": 0,
        "workers_started": False, "identity_is_explicit_fixture": True,
        "owner_uat_accepted": False, "publishing_enabled": False, "production_deployed": False,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{64}", args.sha):
        parser.error("--sha must be the trusted lowercase SHA256 from the backup receipt")
    if not re.fullmatch(r"[a-f0-9]{32}", args.project_id):
        parser.error("--project-id must be an exact existing Native project ID")
    if not 1 <= args.timeout_seconds <= 900:
        parser.error("--timeout-seconds must be between 1 and 900")
    return args


def main():
    args = parse_args()
    backup = guard(args.backup.resolve(), exists=True)
    output = guard(args.output.resolve())
    guard(output.parent, exists=True)
    if output.exists():
        raise RuntimeError("Output must be a new directory")
    if file_sha(backup) != args.sha:
        raise RuntimeError("Backup bytes do not match the trusted receipt checksum")
    output.mkdir()
    # delete=False keeps recovery state if any export fails. Cleanup is attempted
    # once, only after the owned server is drained and backup export succeeds.
    temporary = tempfile.TemporaryDirectory(prefix="vf-scene-browser-", delete=False)
    root = Path(temporary.name) / "state"
    config = Config(data_root=root)
    server = None
    serve_thread = None
    exported = False
    try:
        restored = restore_backup(backup, root, expected_sha256=args.sha)
        write_json(output / "restore.json", restored)
        store = Store(root)
        before = store.get(args.project_id)
        if before["document"].get("input_kind") != "media" or before["document"].get("proposal") is not None:
            raise RuntimeError("Rehearsal requires the specified existing source-media project")
        if not before["document"].get("auto_edit_analyses"):
            raise RuntimeError("Saved source analysis is required; helper will not infer or replay ASR")
        if any(job["status"] in {"queued", "running", "retrying"} for job in before.get("jobs", [])):
            raise RuntimeError("Saved project still has active jobs; helper will not resume them")
        write_json(output / "before-project.json", before)
        write_json(output / "before-facts.json", project_facts(before))
        token, registry = fixture("editor", workspace=WORKSPACE)
        access = NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),
            max_token_ttl_seconds=86400), WORKSPACE)
        server = RehearsalServer(0, config, start_worker=False, access=access)
        serve_thread = threading.Thread(target=server.serve_forever, name="owned-scene-ui", daemon=False)
        serve_thread.start()
        control = {
            "schema_version": "native-scene-browser-rehearsal.v1",
            "base": f"http://127.0.0.1:{server.server_port}", "project_id": before["id"],
            "token": token, "workspace_id": WORKSPACE, "state_root": str(root),
            "backup_sha256": args.sha, "finish_marker": str(output / "finish"),
            "maximum_wait_seconds": args.timeout_seconds, "existing_evidence_reused": True,
            "new_model_inferences": 0, "provider_calls_from_helper": 0,
            "identity_is_explicit_fixture": True, "owner_uat_accepted": False,
            "publishing_enabled": False, "workers_started": False, "production_deployed": False,
        }
        write_json(output / "control.json", control)
        print(json.dumps({"status": "ready", "base": control["base"], "project_id": before["id"],
            "output": str(output), "prior_jobs": project_facts(before)["jobs"]}), flush=True)
        deadline = time.monotonic() + args.timeout_seconds
        while not (output / "finish").exists() and time.monotonic() < deadline:
            time.sleep(.25)
    finally:
        if server is not None:
            server.stop_and_drain(serve_thread)
        if (root / "workflow.sqlite3").is_file():
            # No Store transaction stays open across either export operation.
            store = Store(root)
            after = store.get(args.project_id)
            write_json(output / "after-project.json", after)
            after_facts = project_facts(after)
            write_json(output / "after-facts.json", after_facts)
            with store.transaction() as connection:
                events = [{"id": row["id"], "action": row["action"], "payload": json.loads(row["payload"])}
                    for row in connection.execute("SELECT id,action,payload FROM events WHERE project_id=? ORDER BY id",
                        (args.project_id,))]
            write_json(output / "job-events.json", events)
            receipt = create_backup(config, output / "scene-browser-state.zip")
            write_json(output / "backup.json", receipt)
            if file_sha(backup) != args.sha:
                raise RuntimeError("Original backup changed during owned rehearsal")
            write_json(output / "rehearsal-result.json", {
                "schema_version": "native-scene-browser-result.v1", "backup": receipt,
                "original_backup_unchanged": True, "project_id": after["id"], "revision": after["revision"],
                "original_analysis_records_unchanged": project_facts(before)["original_analysis_records_sha256"]
                    == after_facts["original_analysis_records_sha256"],
                "original_media_analysis_unchanged": project_facts(before)["original_media_analysis_sha256"]
                    == after_facts["original_media_analysis_sha256"],
                "original_asset_checksums_unchanged": project_facts(before)["assets"] == after_facts["assets"],
                "request_threads_drained": True, "provider_calls_from_helper": 0, "new_model_inferences": 0,
                "owner_uat_accepted": False, "publishing_enabled": False, "production_deployed": False,
            })
            exported = True
        print(json.dumps({"status": "exported" if exported else "retained_after_failure",
            "state_root": str(root), "output": str(output)}), flush=True)
    if exported:
        try:
            temporary.cleanup()
        except OSError as error:
            print(json.dumps({"owned_temporary_root_cleaned": False, "state_root": str(root),
                "cleanup_error": type(error).__name__, "cleanup_retried": False}), flush=True)
        else:
            print(json.dumps({"owned_temporary_root_cleaned": True}), flush=True)


if __name__ == "__main__":
    main()
