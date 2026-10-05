from __future__ import annotations

import argparse
import base64
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
from pathlib import Path
import re
import secrets
import threading
import time
import uuid
from urllib.parse import unquote

from .contracts import WorkflowError, file_sha
from .pipeline import Config, LOCKS, Pipeline, REPO, verify_runtime
from .store import Store
from .hardening import failure
from .ingestion import DOCUMENT_TYPES, DOCUMENT_MAX_BYTES, ingest_document
from . import assemblyai_connection
from .media import CONTENT_TYPES, IMAGE_MAX_BYTES, VIDEO_MAX_BYTES, discard_media, ingest_media, media_path, project_assets


class Runner:
    def __init__(self, store, pipeline):
        self.store, self.pipeline = store, pipeline
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.work, daemon=True, name="native-single-worker")

    def start(self):
        self.store.recover()
        self.thread.start()

    def run_one(self):
        job = self.store.claim()
        if not job:
            return False
        step, started = "starting", time.monotonic()
        def stage(value):
            nonlocal step, started
            self.store.log_step(job, step, time.monotonic() - started)
            self.store.stage(job["id"], value)
            step, started = value, time.monotonic()
        try:
            result = self.pipeline.run(job, stage)
            self.store.log_step(job, step, time.monotonic() - started)
            self.store.finish(job, result=result)
        except Exception as error:
            safe = {"code": error.code if isinstance(error, WorkflowError) else type(error).__name__, "automatic_retry": False}
            if isinstance(error, WorkflowError) and error.http_status:
                safe["http_status"] = error.http_status
            self.store.log_step(job, step, time.monotonic() - started, safe["code"])
            self.store.finish(job, error=safe)
        return True

    def work(self):
        while not self.stop.is_set():
            if not self.run_one():
                self.wake.wait(1)
                self.wake.clear()


def save_image(config, payload):
    from PIL import Image, ImageOps
    if payload.get("rights_confirmed") is not True or not isinstance(payload.get("illustration"), bool):
        raise WorkflowError("IMAGE_RIGHTS_CONFIRMATION_REQUIRED", 400)
    try:
        raw = base64.b64decode(payload["image_base64"], validate=True)
        if not 1 <= len(raw) <= 15 * 1024 * 1024:
            raise ValueError()
        Image.MAX_IMAGE_PIXELS = 40_000_000
        image = Image.open(io.BytesIO(raw))
        if image.format not in {"JPEG", "PNG"} or image.width * image.height > 40_000_000:
            raise ValueError()
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        if min(image.size) < 240:
            raise ValueError()
    except Exception:
        raise WorkflowError("INVALID_IMAGE_JPEG_PNG_MAX_15MB_40MP_MIN_240PX", 400) from None
    directory = config.data_root / "assets"
    directory.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex + ".jpg"
    path = directory / identifier
    image.save(path, quality=95)
    return {"id": identifier, "sha256": file_sha(path), "illustration": payload["illustration"],
            "rights_confirmed": True, "width": image.width, "height": image.height}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, config, *, pipeline=None, start_worker=True):
        config.validate_data_root()
        super().__init__(("127.0.0.1", port), Handler)
        self.config, self.store = config, Store(config.data_root)
        self.session = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.connection_lock = threading.Lock()
        self.runner = Runner(self.store, pipeline or Pipeline(config))
        if start_worker:
            self.runner.start()

    def server_close(self):
        self.runner.stop.set()
        self.runner.wake.set()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # No body, tokens, user content or provider error details in HTTP logs.

    def boundary(self, write=False, session=True):
        port = self.server.server_port
        host = self.headers.get("Host", "")
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            raise WorkflowError("LOOPBACK_HOST_REQUIRED", 403)
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise WorkflowError("CROSS_SITE_REQUEST_BLOCKED", 403)
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            raise WorkflowError("SAME_ORIGIN_REQUIRED", 403)
        if session:
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
            except Exception:
                raise WorkflowError("LOCAL_SESSION_REQUIRED", 401) from None
            token = cookies.get("vf_native_session")
            if token is None or not secrets.compare_digest(token.value, self.server.session):
                raise WorkflowError("LOCAL_SESSION_REQUIRED", 401)
        if write and not secrets.compare_digest(self.headers.get("X-VF-CSRF", ""), self.server.csrf):
            raise WorkflowError("CSRF_TOKEN_REQUIRED", 403)

    def reply(self, value, status=200, headers=None):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.common("application/json; charset=utf-8", len(raw), headers)
        self.end_headers()
        self.wfile.write(raw)

    def common(self, content_type, size, headers=None):
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; media-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for name, value in (headers or {}).items():
            self.send_header(name, value)

    def file(self, path, *, video=False):
        if not path.is_file():
            raise WorkflowError("ARTIFACT_NOT_FOUND", 404)
        size, start, end = path.stat().st_size, 0, path.stat().st_size - 1
        request_range = self.headers.get("Range") if video else None
        status, extra = 200, {}
        if video:
            extra["Accept-Ranges"] = "bytes"
        if request_range:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", request_range)
            if not match:
                raise WorkflowError("INVALID_VIDEO_RANGE", 416)
            start = int(match[1])
            end = min(int(match[2]), end) if match[2] else end
            if start > end or start >= size:
                raise WorkflowError("INVALID_VIDEO_RANGE", 416)
            status = 206
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self.send_response(status)
        self.common(mimetypes.guess_type(path)[0] or "application/octet-stream", end - start + 1, extra)
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def dispatch_get(self):
        path = self.path.split("?", 1)[0]
        self.boundary(session=path.startswith("/api/") and path not in {"/api/session", "/api/health"})
        if path == "/api/session":
            return self.reply({"csrf": self.server.csrf}, headers={"Set-Cookie": f"vf_native_session={self.server.session}; HttpOnly; SameSite=Strict; Path=/"})
        if path == "/api/health":
            return self.reply({"status": "ready", "model": "gpt-6-luna", "voice": "Thùy Dung", "resolution": "1080x1920", "human_review_required": True})
        if path == "/api/defaults":
            return self.reply({"prompt": (LOCKS / "accepted-prompt.txt").read_text(encoding="utf-8")})
        if path == "/api/projects":
            return self.reply(self.server.store.list())
        if path == "/api/connections/assemblyai":
            return self.reply(assemblyai_connection.status(self.server.config))
        versions = re.fullmatch(r"/api/projects/([0-9a-f]{32})/versions", path)
        if versions:
            return self.reply(self.server.store.versions(versions[1]))
        logs = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/logs", path)
        if logs:
            job = self.server.store.get_job(logs[1])
            with self.server.store.transaction() as con:
                rows = con.execute("SELECT payload,created_at FROM events WHERE action='job_step' AND project_id=? AND json_extract(payload,'$.job_id')=? ORDER BY id", (job["project_id"], job["id"]))
                return self.reply([{**json.loads(r["payload"]), "created_at": r["created_at"]} for r in rows])
        match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/media/([0-9a-f]{32}\.(?:jpg|mp4))(/thumbnail)?", path)
        if match:
            project = self.server.store.get(match[1])
            asset = next((a for a in project_assets(project["document"]) if a["id"] == match[2]), None)
            if asset is None:
                raise WorkflowError("MEDIA_NOT_IN_PROJECT", 404)
            identifier = asset.get("thumbnail_id", asset["id"]) if match[3] else asset["id"]
            return self.file(media_path(self.server.config, identifier), video=not match[3] and asset["kind"] == "video")
        match = re.fullmatch(r"/api/projects/([0-9a-f]{32})(/image)?", path)
        if match:
            project = self.server.store.get(match[1])
            if match[2]:
                asset = project["document"]["asset"]
                if not asset:
                    raise WorkflowError("IMAGE_NOT_FOUND", 404)
                return self.file(self.server.config.data_root / "assets" / asset["id"])
            return self.reply(project)
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/video", path)
        if match:
            job = self.server.store.get_job(match[1])
            project = self.server.store.get(job["project_id"])
            if job["status"] != "succeeded" or job["revision"] != project["revision"] or not project["approval"]:
                raise WorkflowError("VIDEO_STALE_OR_NOT_READY")
            return self.file(self.server.config.data_root / "jobs" / job["id"] / "final.mp4", video=True)
        static = {"/": "native.html", "/native.html": "native.html", "/native.css": "native.css", "/native.mjs": "native.mjs",
                  "/settings/assemblyai": "assemblyai.html", "/assemblyai.mjs": "assemblyai.mjs"}
        if path in static:
            return self.file(REPO / "apps/studio-web" / static[path])
        raise WorkflowError("ROUTE_NOT_FOUND", 404)

    def read_body(self, max_bytes=22 * 1024 * 1024):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise WorkflowError("INVALID_BODY_LENGTH", 400) from None
        if not 1 <= length <= max_bytes or self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise WorkflowError("JSON_BODY_REQUIRED_MAX_22MB", 400)
        try:
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
            return body
        except ValueError:
            raise WorkflowError("INVALID_JSON_BODY", 400) from None

    def dispatch_post(self):
        self.boundary(write=True)
        if self.path == "/api/connections/assemblyai":
            body = self.read_body(max_bytes=2048)
            if set(body) not in ({"key"}, {"verify_saved"}) or ("verify_saved" in body and body["verify_saved"] is not True):
                raise WorkflowError("ASSEMBLYAI_CONNECTION_BODY_INVALID", 400)
            if "key" in body and not isinstance(body["key"], str):
                raise WorkflowError("ASSEMBLYAI_KEY_FORMAT_INVALID", 400)
            with self.server.connection_lock:
                with self.server.store.transaction() as con:
                    if con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0]:
                        raise WorkflowError("ASSEMBLYAI_CONNECTION_WAIT_FOR_JOBS", 409)
                return self.reply(assemblyai_connection.connect(self.server.config, body.get("key")))
        upload_match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/media", self.path)
        if upload_match:
            return self.upload_media(upload_match[1])
        document_match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/documents", self.path)
        if document_match:
            return self.upload_document(document_match[1])
        body = self.read_body()
        resume = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/resume", self.path)
        if resume:
            result = self.server.store.resume(resume[1])
            self.server.runner.wake.set()
            return self.reply(result)
        if self.path == "/api/projects":
            return self.reply(self.server.store.create(body.get("name"), body.get("prompt"), body.get("input_kind", "prompt")), 201)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/(draft|image|approve|jobs)", self.path)
        if not match:
            raise WorkflowError("ROUTE_NOT_FOUND", 404)
        identifier, action = match[1], match[2]
        revision = body.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise WorkflowError("REVISION_REQUIRED", 400)
        if action == "draft":
            result = self.server.store.save(identifier, revision, prompt=body.get("prompt"), proposal=body.get("proposal"), scene_media=body.get("scene_media"), input_kind=body.get("input_kind"))
        elif action == "image":
            asset = save_image(self.server.config, body)
            try:
                result = self.server.store.save(identifier, revision, asset=asset)
            except Exception:
                (self.server.config.data_root / "assets" / asset["id"]).unlink(missing_ok=True)
                raise
        elif action == "approve":
            result = self.server.store.approve(identifier, revision, body.get("reviewer"), body.get("acknowledged"))
        else:
            if body.get("kind") == "asr":
                from .asr import pending_speech
                doc = self.server.store.get(identifier)["document"]
                if pending_speech(doc) and not assemblyai_connection.status(self.server.config)["connected"]:
                    raise WorkflowError("ASR_PROVIDER_UNAVAILABLE_NO_TRANSCRIPT", 503)
            result = self.server.store.enqueue(identifier, revision, body.get("kind"), body.get("request_key"))
            self.server.runner.wake.set()
        return self.reply(result)

    def upload_media(self, identifier):
        content_type = self.headers.get("Content-Type", "").split(";")[0]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            revision = int(self.headers.get("X-VF-Revision", "0"))
        except ValueError:
            raise WorkflowError("INVALID_MEDIA_UPLOAD_HEADERS", 400) from None
        limit = VIDEO_MAX_BYTES if content_type.startswith("video/") else IMAGE_MAX_BYTES
        if content_type not in CONTENT_TYPES or not 0 < length <= limit or self.headers.get("Transfer-Encoding"):
            raise WorkflowError("MEDIA_FILE_TOO_LARGE_OR_TYPE_UNSUPPORTED", 400)
        rights = self.headers.get("X-VF-Rights") == "confirmed"
        illustration_value = self.headers.get("X-VF-Illustration")
        if not rights or illustration_value not in {"true", "false"}:
            raise WorkflowError("MEDIA_RIGHTS_CONFIRMATION_REQUIRED", 400)
        # Early optimistic check, then recheck in the append transaction after validation.
        with self.server.store.transaction() as con:
            self.server.store.editable(con, identifier, revision)
        directory = self.server.config.data_root / "uploads"
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / (uuid.uuid4().hex + ".part")
        try:
            remaining = length
            with source.open("xb") as dest:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise WorkflowError("MEDIA_UPLOAD_INCOMPLETE", 400)
                    dest.write(chunk)
                    remaining -= len(chunk)
            asset = ingest_media(self.server.config, source, content_type, unquote(self.headers.get("X-VF-Filename", "Media")),
                                 rights_confirmed=True, illustration=illustration_value == "true")
            try:
                result = self.server.store.append_media(identifier, revision, asset)
            except Exception:
                discard_media(self.server.config, asset)
                raise
            return self.reply(result, 201)
        finally:
            source.unlink(missing_ok=True)

    def upload_document(self, identifier):
        content_type = self.headers.get("Content-Type", "").split(";")[0]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            revision = int(self.headers.get("X-VF-Revision", "0"))
        except ValueError:
            raise WorkflowError("DOCUMENT_HEADERS_INVALID", 400) from None
        if content_type not in DOCUMENT_TYPES or not 0 < length <= DOCUMENT_MAX_BYTES or self.headers.get("Transfer-Encoding"):
            raise WorkflowError("DOCUMENT_TYPE_OR_SIZE_INVALID_MAX_5MB", 400)
        with self.server.store.transaction() as con:
            self.server.store.editable(con, identifier, revision)
        directory = self.server.config.data_root / "uploads"; directory.mkdir(parents=True, exist_ok=True)
        source = directory / (uuid.uuid4().hex + ".part")
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise WorkflowError("DOCUMENT_UPLOAD_INCOMPLETE", 400)
            with source.open("xb") as handle: handle.write(raw)
            asset = ingest_document(self.server.config, source, content_type, unquote(self.headers.get("X-VF-Filename", "Document")))
            try:
                result = self.server.store.append_document(identifier, revision, asset)
            except Exception:
                (self.server.config.data_root / "documents" / asset["id"]).unlink(missing_ok=True)
                raise
            return self.reply(result, 201)
        finally:
            source.unlink(missing_ok=True)

    def handle_request(self, method):
        try:
            self.connection.settimeout(30)
            if method == "GET":
                self.dispatch_get()
            else:
                self.dispatch_post()
        except WorkflowError as error:
            self.close_connection = True
            self.reply({"code": error.code, "failure": failure(error.code, http_status=error.http_status)}, error.status)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self.close_connection = True
            self.reply({"code": "LOCAL_REQUEST_FAILED"}, 500)

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")


def main():
    parser = argparse.ArgumentParser(description="Video Factory Windows Native Studio")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--port", type=int, default=8026)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    config = Config.load(args.config)
    try:
        ready = verify_runtime(config, full=True)
        if args.preflight:
            print(json.dumps(ready, ensure_ascii=False))
            return
        from .windows_job import contain_process_tree, lock_data_root
        contain_process_tree()
        lock = lock_data_root(config.data_root)
        with LocalServer(args.port, config) as server:
            print(f"Video Factory: http://127.0.0.1:{server.server_port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        lock.close()
    except Exception as error:
        print(json.dumps({"code": error.code if isinstance(error, WorkflowError) else type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
