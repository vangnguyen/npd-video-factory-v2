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
import uuid

from .contracts import WorkflowError, file_sha
from .pipeline import Config, LOCKS, Pipeline, REPO, verify_runtime
from .store import Store


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
        try:
            result = self.pipeline.run(job, lambda stage: self.store.stage(job["id"], stage))
            self.store.finish(job, result=result)
        except Exception as error:
            safe = {"code": error.code if isinstance(error, WorkflowError) else type(error).__name__, "automatic_retry": False}
            if isinstance(error, WorkflowError) and error.http_status:
                safe["http_status"] = error.http_status
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
        static = {"/": "native.html", "/native.html": "native.html", "/native.css": "native.css", "/native.mjs": "native.mjs"}
        if path in static:
            return self.file(REPO / "apps/studio-web" / static[path])
        raise WorkflowError("ROUTE_NOT_FOUND", 404)

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise WorkflowError("INVALID_BODY_LENGTH", 400) from None
        if not 1 <= length <= 22 * 1024 * 1024 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
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
        body = self.read_body()
        if self.path == "/api/projects":
            return self.reply(self.server.store.create(body.get("name"), body.get("prompt")), 201)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{32})/(draft|image|approve|jobs)", self.path)
        if not match:
            raise WorkflowError("ROUTE_NOT_FOUND", 404)
        identifier, action = match[1], match[2]
        revision = body.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise WorkflowError("REVISION_REQUIRED", 400)
        if action == "draft":
            result = self.server.store.save(identifier, revision, prompt=body.get("prompt"), proposal=body.get("proposal"))
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
            result = self.server.store.enqueue(identifier, revision, body.get("kind"), body.get("request_key"))
            self.server.runner.wake.set()
        return self.reply(result)

    def handle_request(self, method):
        try:
            self.connection.settimeout(30)
            if method == "GET":
                self.dispatch_get()
            else:
                self.dispatch_post()
        except WorkflowError as error:
            self.close_connection = True
            self.reply({"code": error.code}, error.status)
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
