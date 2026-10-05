from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .contracts import Proposal, WorkflowError, digest
from .media import MAX_ASSETS, project_assets, scene_bindings, selected_media, validate_bindings
from .hardening import LIFECYCLE, failure, resume_boundary, version_components
from .ingestion import project_input, validate_text


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    """One transaction binds input, approval, idempotency receipt and dispatch intent."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "workflow.sqlite3"
        with self.transaction() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL,
                    approval TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    kind TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                    request_key TEXT UNIQUE NOT NULL, request_sha TEXT NOT NULL,
                    snapshot TEXT NOT NULL, error TEXT, result TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
                    action TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS project_versions (
                    project_id TEXT NOT NULL, revision INTEGER NOT NULL, document TEXT NOT NULL,
                    components TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(project_id,revision));
                CREATE TABLE IF NOT EXISTS job_runtime (
                    job_id TEXT PRIMARY KEY, retry_count INTEGER NOT NULL DEFAULT 0,
                    resume_count INTEGER NOT NULL DEFAULT 0);
            """)
            # Additive history starts with the current preserved document, never invented past versions.
            for row in con.execute("SELECT * FROM projects").fetchall():
                self.version(con, row["id"])

    @contextmanager
    def transaction(self):
        con = sqlite3.connect(self.db, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("BEGIN IMMEDIATE")
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def event(self, con, project_id, action, payload):
        con.execute("INSERT INTO events(project_id,action,payload,created_at) VALUES(?,?,?,?)",
                    (project_id, action, json.dumps(payload, ensure_ascii=False), now()))

    @staticmethod
    def project(row):
        if row is None:
            raise WorkflowError("PROJECT_NOT_FOUND", 404)
        doc = json.loads(row["document"])
        return {**dict(row), "document": doc, "input": project_input(doc, row["revision"]),
                "approval": json.loads(row["approval"]) if row["approval"] else None}

    def job(self, row, con=None):
        if row is None:
            raise WorkflowError("JOB_NOT_FOUND", 404)
        result = dict(row)
        for key in ("snapshot", "error", "result"):
            result[key] = json.loads(row[key]) if row[key] else None
        result["lifecycle"] = LIFECYCLE[result["status"]]
        runtime = con.execute("SELECT retry_count,resume_count FROM job_runtime WHERE job_id=?", (row["id"],)).fetchone() if con else None
        result.update(dict(runtime) if runtime else {"retry_count": 0, "resume_count": 0})
        last = con.execute("SELECT payload FROM events WHERE action='job_step' AND project_id=? AND json_extract(payload,'$.job_id')=? ORDER BY id DESC LIMIT 1", (result["project_id"], result["id"])).fetchone() if con and result["error"] else None
        step = json.loads(last[0])["step"] if last else result["stage"]
        result["failure"] = failure(result["error"]["code"], result["error"].get("last_stage", step), result["error"].get("http_status")) if result["error"] else None
        return result

    def version(self, con, identifier):
        project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
        existing = con.execute("SELECT document FROM project_versions WHERE project_id=? AND revision=?", (identifier, project["revision"])).fetchone()
        if existing and digest(json.loads(existing[0])) != digest(project["document"]):
            raise WorkflowError("IMMUTABLE_VERSION_CONFLICT")
        con.execute("INSERT OR IGNORE INTO project_versions VALUES(?,?,?,?,?)",
                    (identifier, project["revision"], json.dumps(project["document"], ensure_ascii=False),
                     json.dumps(version_components(project["document"])), now()))

    def versions(self, identifier):
        with self.transaction() as con:
            self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
            return [{**dict(r), "document": json.loads(r["document"]), "components": json.loads(r["components"])}
                    for r in con.execute("SELECT * FROM project_versions WHERE project_id=? ORDER BY revision DESC", (identifier,))]

    def log_step(self, job, step, duration, error_code=None, provider=None):
        with self.transaction() as con:
            runtime = con.execute("SELECT retry_count FROM job_runtime WHERE job_id=?", (job["id"],)).fetchone()
            self.event(con, job["project_id"], "job_step", {"job_id": job["id"], "project_id": job["project_id"],
                "step": step, "provider": provider or ("assemblyai" if step in {"asr_upload", "asr_create_transcript", "asr_observe_known_transcript"} else "ffmpeg" if step in {"asr_local_media_analysis", "asr_extract_audio"} else "openai" if "content" in step else "local_vieneu" if "tts" in step else "ffmpeg" if "render" in step else "local_io"),
                "duration": round(duration, 6), "retry_count": runtime[0] if runtime else 0, "error_code": error_code})

    def create(self, name, prompt, input_kind="prompt"):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 150:
            raise WorkflowError("PROJECT_NAME_REQUIRED", 400)
        prompt = validate_text(input_kind, prompt)
        identifier = uuid.uuid4().hex
        doc = {"name": name.strip(), "prompt": prompt, "input_kind": input_kind, "proposal": None, "asset": None, "assets": [], "scene_media": [], "documents": []}
        stamp = now()
        with self.transaction() as con:
            con.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)",
                        (identifier, 1, json.dumps(doc, ensure_ascii=False), None, stamp, stamp))
            self.event(con, identifier, "project_created", {"revision": 1})
            self.version(con, identifier)
        return self.get(identifier)

    def get(self, identifier):
        with self.transaction() as con:
            project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
            project["jobs"] = [self.job(r, con) for r in con.execute(
                "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC", (identifier,))]
            return project

    def list(self):
        with self.transaction() as con:
            return [self.project(row) for row in con.execute("SELECT * FROM projects ORDER BY updated_at DESC")]

    def editable(self, con, identifier, revision):
        project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
        if project["revision"] != revision:
            raise WorkflowError("STALE_VERSION_RELOAD")
        if con.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('queued','running','retrying')",
                       (identifier,)).fetchone():
            raise WorkflowError("PROJECT_BUSY")
        return project

    def save(self, identifier, revision, *, prompt=None, proposal=None, asset=None, scene_media=None, input_kind=None, scene_options=None, music_enabled=None):
        if prompt is not None and input_kind != "media" and (not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 20000):
            raise WorkflowError("PROMPT_REQUIRED_MAX_20000", 400)
        if proposal is not None:
            try:
                proposal = Proposal.model_validate(proposal).model_dump()
            except ValueError:
                raise WorkflowError("INVALID_PROPOSAL_SCENE_COVERAGE", 400) from None
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            if input_kind is not None:
                validate_text(input_kind, prompt if prompt is not None else doc["prompt"])
                if input_kind != doc.get("input_kind", "prompt"):
                    doc["proposal"], doc["scene_media"] = None, []
                doc["input_kind"] = input_kind
            if prompt is not None and prompt != doc["prompt"]:
                doc["prompt"], doc["proposal"] = prompt, None
                doc["scene_media"] = []
            if proposal is not None:
                doc["proposal"] = proposal
            if asset is not None:
                doc["asset"] = asset
                doc["assets"] = [asset]
                doc.pop("scene_media", None)  # Legacy single-image write remains compatible.
            if scene_media is not None:
                doc["scene_media"] = scene_media
            validate_bindings(doc)
            if music_enabled is not None:
                if type(music_enabled) is not bool:
                    raise WorkflowError("MUSIC_ENABLED_MUST_BE_BOOLEAN",400)
                doc["music_enabled"]=music_enabled
            if scene_options is not None:
                from .editor import build_plan
                doc["edit_plan"]=build_plan(doc,scene_options)
            elif any(v is not None for v in (prompt,proposal,asset,scene_media,input_kind,music_enabled)):
                doc.pop("edit_plan",None)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                        (revision + 1, json.dumps(doc, ensure_ascii=False), now(), identifier))
            self.event(con, identifier, "draft_saved_approval_invalidated", {"revision": revision + 1})
            self.version(con, identifier)
        return self.get(identifier)

    def auto_plan(self, identifier, revision):
        from .editor import build_plan
        with self.transaction() as con:
            project=self.editable(con,identifier,revision); doc=project["document"]
            plan=build_plan(doc,auto_select=True)
            doc["edit_plan"]=plan
            doc["scene_media"]=[{"scene":s["scene"],"asset_id":s["selected_asset"]} for s in plan["scenes"]]
            validate_bindings(doc)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                        (revision+1,json.dumps(doc,ensure_ascii=False),now(),identifier))
            self.version(con,identifier)
            self.event(con,identifier,"editor_plan_saved_review_required",{"revision":revision+1,"plan_sha256":digest(plan)})
        return self.get(identifier)

    def set_music(self, identifier, revision, music):
        with self.transaction() as con:
            project=self.editable(con,identifier,revision); doc=project["document"]
            doc["music"]=music; doc["music_enabled"]=True; doc.pop("edit_plan",None)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                        (revision+1,json.dumps(doc,ensure_ascii=False),now(),identifier))
            self.version(con,identifier)
            self.event(con,identifier,"music_saved_review_required",{"revision":revision+1,"music_id":music["id"],"source_sha256":music["source_sha256"]})
        return self.get(identifier)

    def append_document(self, identifier, revision, document):
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            documents = doc.get("documents", [])
            if len(documents) >= 20:
                raise WorkflowError("DOCUMENT_LIMIT_20", 400)
            doc["documents"] = documents + [document]
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                (revision + 1, json.dumps(doc, ensure_ascii=False), now(), identifier))
            self.version(con, identifier)
            self.event(con, identifier, "document_uploaded_approval_invalidated", {"revision": revision+1, "document_id": document["id"], "sha256": document["sha256"]})
        return self.get(identifier)

    def approve(self, identifier, revision, reviewer, acknowledged):
        if acknowledged is not True or not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 100:
            raise WorkflowError("HUMAN_REVIEW_REQUIRED", 400)
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            if not doc["proposal"]:
                raise WorkflowError("CONTENT_AND_IMAGE_REQUIRED")
            from .editor import validate_plan
            validate_plan(doc)
            selected_media(doc)
            approval = {"revision": revision, "snapshot_sha256": digest(doc),
                        "reviewer": reviewer.strip(), "approved_at": now(), "source": "local_ui_human_review"}
            con.execute("UPDATE projects SET approval=?,updated_at=? WHERE id=?",
                        (json.dumps(approval, ensure_ascii=False), now(), identifier))
            self.event(con, identifier, "human_content_approved", approval)
        return self.get(identifier)

    def enqueue(self, identifier, revision, kind, request_key):
        if kind not in {"content", "render", "asr"} or not isinstance(request_key, str) or not 8 <= len(request_key) <= 100:
            raise WorkflowError("INVALID_JOB_REQUEST", 400)
        identity = digest({"project_id": identifier, "revision": revision, "kind": kind})
        with self.transaction() as con:
            existing = con.execute("SELECT * FROM jobs WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                if existing["request_sha"] != identity:
                    raise WorkflowError("IDEMPOTENCY_KEY_CONFLICT")
                return self.job(existing, con)
            project = self.editable(con, identifier, revision)
            doc, approval = project["document"], project["approval"]
            if kind == "asr":
                from .asr import pending_assets
                if not pending_assets(doc):
                    raise WorkflowError("ASR_NO_UNANALYZED_MEDIA", 400)
                if con.execute("SELECT 1 FROM jobs WHERE project_id=? AND revision=? AND kind='asr'",
                               (identifier, revision)).fetchone():
                    raise WorkflowError("ASR_EXISTING_JOB_RESUME_REQUIRED")
            if kind == "render" and (not approval or approval["revision"] != revision
                                     or approval["snapshot_sha256"] != digest(doc)):
                raise WorkflowError("HUMAN_APPROVAL_REQUIRED_BEFORE_TTS")
            if kind == "render":
                selected_media(doc)
            identifier_job, stamp = uuid.uuid4().hex, now()
            snapshot = {"document": doc, "approval": approval}
            con.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (identifier_job, identifier, revision, kind, "queued", "queued", request_key, identity,
                         json.dumps(snapshot, ensure_ascii=False), None, None, stamp, stamp))
            self.event(con, identifier, "job_queued", {"job_id": identifier_job, "kind": kind, "revision": revision})
            con.execute("INSERT INTO job_runtime(job_id) VALUES(?)", (identifier_job,))
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier_job,)).fetchone(), con)

    def claim(self):
        with self.transaction() as con:
            row = con.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row is None:
                return None
            con.execute("UPDATE jobs SET status='running',stage='starting',updated_at=? WHERE id=?", (now(), row["id"]))
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone(), con)

    def stage(self, identifier, stage):
        with self.transaction() as con:
            retry = stage.startswith("retrying:")
            step = stage.split(":", 1)[1] if retry else stage
            con.execute("UPDATE jobs SET status=?,stage=?,updated_at=? WHERE id=? AND status IN ('running','retrying')",
                        ("retrying" if retry else "running", step, now(), identifier))
            if retry:
                con.execute("INSERT OR IGNORE INTO job_runtime(job_id) VALUES(?)", (identifier,))
                con.execute("UPDATE job_runtime SET retry_count=retry_count+1 WHERE job_id=?", (identifier,))

    def finish(self, job, result=None, error=None):
        with self.transaction() as con:
            row = con.execute("SELECT status FROM jobs WHERE id=?", (job["id"],)).fetchone()
            if row is None or row["status"] not in {"running", "retrying"}:
                raise WorkflowError("JOB_STATE_CONFLICT")
            status = "failed" if error else ("awaiting_review" if job["kind"] == "content" else "succeeded")
            if result and job["kind"] == "content":
                project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (job["project_id"],)).fetchone())
                if project["revision"] != job["revision"]:
                    raise WorkflowError("STALE_CONTENT_RESULT")
                doc = project["document"]
                doc["proposal"] = Proposal.model_validate(result["proposal"]).model_dump()
                doc["scene_media"] = []  # New proposal requires deliberate source choices.
                con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                            (project["revision"] + 1, json.dumps(doc, ensure_ascii=False), now(), project["id"]))
                self.version(con, project["id"])
            if result and job["kind"] == "asr":
                from .asr import analysis_for_asset
                project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (job["project_id"],)).fetchone())
                if project["revision"] != job["revision"] or digest(project["document"]) != digest(job["snapshot"]["document"]):
                    raise WorkflowError("ASR_STALE_RESULT")
                doc = project["document"]
                incoming = result["media_analysis"]
                assets = {a["id"]: a for a in project_assets(doc)}
                if len({r["asset_id"] for r in incoming}) != len(incoming):
                    raise WorkflowError("ASR_DUPLICATE_RESULT")
                for record in incoming:
                    if record["asset_id"] not in assets or not analysis_for_asset({"media_analysis": [record]}, assets[record["asset_id"]]):
                        raise WorkflowError("ASR_RESULT_SOURCE_BINDING_MISMATCH")
                replaced = {r["asset_id"] for r in incoming}
                doc["media_analysis"] = [r for r in doc.get("media_analysis", []) if r["asset_id"] not in replaced] + incoming
                doc.pop("edit_plan",None)
                con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                            (project["revision"]+1, json.dumps(doc, ensure_ascii=False), now(), project["id"]))
                self.version(con, project["id"])
                self.event(con, project["id"], "media_analyzed_approval_invalidated", {"job_id": job["id"], "assets": sorted(replaced)})
            con.execute("UPDATE jobs SET status=?,stage=?,error=?,result=?,updated_at=? WHERE id=?",
                        (status, status, json.dumps(error) if error else None,
                         json.dumps(result, ensure_ascii=False) if result else None, now(), job["id"]))
            self.event(con, job["project_id"], "job_finished", {"job_id": job["id"], "status": status, "error": error})

    def recover(self):
        # Unstarted jobs are safe to drain. Dispatched/ambiguous work is NEVER replayed.
        with self.transaction() as con:
            for row in con.execute("SELECT * FROM jobs WHERE status IN ('running','retrying')").fetchall():
                error = {"code": "INTERRUPTED_NO_AUTOMATIC_REPLAY", "last_stage": row["stage"]}
                con.execute("UPDATE jobs SET status='interrupted',stage='interrupted',error=?,updated_at=? WHERE id=?",
                            (json.dumps(error), now(), row["id"]))
                self.event(con, row["project_id"], "job_interrupted", {"job_id": row["id"], **error})

    def get_job(self, identifier):
        with self.transaction() as con:
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone(), con)

    def resume(self, identifier):
        with self.transaction() as con:
            job = self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone(), con)
            if job["status"] in {"queued", "running", "retrying"} and job["resume_count"]:
                return job  # Double-click/repeated resume keeps one job/output receipt.
            if job["status"] not in {"failed", "interrupted"}:
                raise WorkflowError("JOB_NOT_RESUMABLE")
            project = self.editable(con, job["project_id"], job["revision"])
            if digest({"document": project["document"], "approval": project["approval"]}) != digest(job["snapshot"]):
                raise WorkflowError("STALE_RESUME_SNAPSHOT")
            if job["resume_count"] >= 3:
                raise WorkflowError("RESUME_LIMIT_REACHED")
            resume_boundary(self.root, job)
            con.execute("INSERT OR IGNORE INTO job_runtime(job_id) VALUES(?)", (identifier,))
            con.execute("UPDATE job_runtime SET resume_count=resume_count+1 WHERE job_id=?", (identifier,))
            con.execute("UPDATE jobs SET status='queued',stage='resume_queued',error=NULL,result=NULL,updated_at=? WHERE id=?", (now(), identifier))
            self.event(con, job["project_id"], "job_resume_requested", {"job_id": identifier, "previous_error": job["error"]})
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone(), con)

    def append_media(self, identifier, revision, asset):
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            library = project_assets(doc)
            if len(library) >= MAX_ASSETS:
                raise WorkflowError("PROJECT_MEDIA_LIMIT_50", 400)
            doc["scene_media"] = scene_bindings(doc)
            doc["assets"] = library + [asset]
            doc.pop("edit_plan",None)
            validate_bindings(doc)
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                (revision + 1, json.dumps(doc, ensure_ascii=False), now(), identifier))
            self.event(con, identifier, "media_uploaded_approval_invalidated", {"revision": revision + 1, "asset_id": asset["id"], "kind": asset["kind"]})
            self.version(con, identifier)
        return self.get(identifier)
