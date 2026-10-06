"""Small, local durability helpers; no external services or automatic paid replay."""
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import shutil
import time

from .contracts import WorkflowError, canonical, digest, file_sha

LIFECYCLE = {"queued": "CREATED", "running": "RUNNING", "retrying": "RETRYING",
             "awaiting_review": "WAITING_HUMAN", "failed": "FAILED", "interrupted": "FAILED",
             "succeeded": "SUCCEEDED"}


def failure(code, step="", http_status=None):
    """Only known identifiers enter logs, never exception text/provider bodies/secrets."""
    value = (str(code) + " " + step).upper()
    if "ASR" in value or "TRANSCRIPT" in value:
        category, action = "ASR_ERROR", "Kiểm tra kết nối và job nhận diện lời nói. Chỉ tiếp tục quan sát job đã biết; yêu cầu chưa rõ kết quả không được gửi lại."
    elif any(s in value for s in ("OPENAI", "PROVIDER", "RATELIMIT", "AUTHENTICATION", "CONTENT_REQUEST")):
        category, action = "PROVIDER_ERROR", "Kiểm tra kết nối, hạn mức và quyền truy cập provider. Kết quả chưa rõ sẽ không tự chạy lại."
    elif any(s in value for s in ("TTS", "SYNTHESIS", "VOICE", "THUY_DUNG")):
        category, action = "TTS_ERROR", "Kiểm tra runtime giọng đọc và log TTS. Không đổi preset hoặc tự lặp inference lỗi."
    elif any(s in value for s in ("FFMPEG", "RENDER", "QC")):
        category, action = "RENDER_ERROR", "Kiểm tra FFmpeg, dung lượng đĩa và log render; có thể tiếp tục từ audio đã kiểm chứng."
    elif any(s in value for s in ("STORAGE", "ARTIFACT", "CHECKPOINT", "OSERROR", "PERMISSION", "SQLITE", "FILEEXISTS")):
        category, action = "STORAGE_ERROR", "Kiểm tra quyền truy cập, dung lượng đĩa và hash artifact trước khi tiếp tục."
    elif any(s in value for s in ("MEDIA", "IMAGE", "VIDEO", "MUSIC")):
        category, action = "MEDIA_ERROR", "Kiểm tra file nguồn, định dạng và lựa chọn media từng cảnh."
    elif any(s in value for s in ("REQUIRED", "INVALID", "STALE", "APPROVAL", "PROJECT", "INPUT", "PROPOSAL", "EDITOR")):
        category, action = "USER_INPUT_ERROR", "Mở lại dự án, kiểm tra nội dung/nguồn và lưu đúng phiên bản trước khi duyệt."
    else:
        category, action = "INTERNAL_ERROR", "Giữ nguyên dự án và xem log của job để xử lý lỗi."
    return {"category": category, "error_code": code, "step": step, "http_status": http_status,
            "action": action, "automatic_paid_replay": False}


def retry_io(operation, stage, step, attempts=2):
    for attempt in range(attempts):
        try:
            return operation()
        except OSError as error:
            transient = error.errno in {errno.EAGAIN, errno.EINTR, errno.EBUSY, errno.ETIMEDOUT} or getattr(error, "winerror", None) in {32, 33}
            if not transient or attempt + 1 == attempts:
                raise
            stage("retrying:" + step)
            time.sleep(.1)
            stage(step)


def durable_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as handle:
        handle.write(canonical(value)); handle.flush(); os.fsync(handle.fileno())
    os.replace(temp, path)


class Artifacts:
    def __init__(self, out, job):
        self.out, self.job = Path(out), job
        self.binding = digest(job["snapshot"])

    def path(self, relative):
        path = (self.out / relative).resolve()
        if self.out.resolve() not in path.parents or path.is_symlink():
            raise WorkflowError("ARTIFACT_PATH_INVALID")
        return path

    def metadata(self, path):
        path = Path(path)
        return {"path": path.relative_to(self.out).as_posix(), "sha256": file_sha(path), "bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}

    def load(self, step):
        file = self.out / ("checkpoint-" + step + ".json")
        if not file.exists():
            return None
        value = json.loads(file.read_bytes())
        if value.get("snapshot_sha256") != self.binding or value.get("job_id") != self.job["id"]:
            raise WorkflowError("CHECKPOINT_BINDING_MISMATCH")
        for artifact in value["artifacts"]:
            path = self.path(artifact["path"])
            if not path.is_file() or path.stat().st_size != artifact["bytes"] or file_sha(path) != artifact["sha256"]:
                raise WorkflowError("CHECKPOINT_ARTIFACT_CHANGED")
        return value

    def commit(self, step, paths, result=None):
        value = {"schema_version": 1, "job_id": self.job["id"], "project_id": self.job["project_id"],
                 "revision": self.job["revision"], "snapshot_sha256": self.binding, "step": step,
                 "created_at": datetime.now(timezone.utc).isoformat(),
                 "artifacts": [self.metadata(path) for path in paths], "result": result,
                 "lineage": {"input_version": digest(self.job["snapshot"]["document"]),
                             "approval": self.job["snapshot"].get("approval")}}
        durable_json(self.out / ("checkpoint-" + step + ".json"), value)
        return value

    def publish(self, source, name):
        target = self.path(name)
        source = Path(source)
        if target.exists():
            if file_sha(target) != file_sha(source):
                raise WorkflowError("ARTIFACT_EXISTS_WITH_DIFFERENT_BYTES")
            return target
        # Copy to a new sibling first; interrupted copies are not checkpointed.
        temp = target.with_suffix(target.suffix + ".publishing")
        with source.open("rb") as src, temp.open("wb") as dst:
            shutil.copyfileobj(src, dst); dst.flush(); os.fsync(dst.fileno())
        os.replace(temp, target)
        return target


def resume_boundary(root, job):
    out = Path(root) / "jobs" / job["id"]
    artifacts = Artifacts(out, job)
    for step in ("content", "tts", "render", "asr", "auto_edit_analysis"):
        artifacts.load(step)  # Refuse changed checkpoint bytes before enqueueing.
    if job["kind"] == "asr":
        from .asr import validate_resume
        validate_resume(root, job)
    if job["kind"] == "content" and not artifacts.load("content"):
        for intent in out.glob("content*.intent.json"):
            receipt = intent.with_name(intent.name.replace(".intent.json", ".rejected.json"))
            if not receipt.exists() or json.loads(receipt.read_bytes()).get("http_status") != 429:
                raise WorkflowError("OPENAI_OUTCOME_UNKNOWN_NO_REPLAY")


def version_components(doc):
    return {"input_version": digest({"prompt": doc.get("prompt"), "inputs": doc.get("inputs"),
                                     "input_kind": doc.get("input_kind", "prompt"), "documents": doc.get("documents", []),
                                     "assets": doc.get("assets", doc.get("asset"))}),
            "script_version": digest(doc.get("proposal")),
            "storyboard_version": digest({"scenes": (doc.get("proposal") or {}).get("visual_brief"),
                                          "scene_media": doc.get("scene_media"), "edit_plan": doc.get("edit_plan"),
                                          "music": doc.get("music"), "music_enabled": doc.get("music_enabled", True),
                                          "brand_template": doc.get("brand_template")})}
