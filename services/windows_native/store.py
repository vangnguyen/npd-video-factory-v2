from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .contracts import Proposal, WorkflowError, digest


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
            """)

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
        return {**dict(row), "document": json.loads(row["document"]),
                "approval": json.loads(row["approval"]) if row["approval"] else None}

    @staticmethod
    def job(row):
        if row is None:
            raise WorkflowError("JOB_NOT_FOUND", 404)
        result = dict(row)
        for key in ("snapshot", "error", "result"):
            result[key] = json.loads(row[key]) if row[key] else None
        return result

    def create(self, name, prompt):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 150:
            raise WorkflowError("PROJECT_NAME_REQUIRED", 400)
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 20000:
            raise WorkflowError("PROMPT_REQUIRED_MAX_20000", 400)
        identifier = uuid.uuid4().hex
        doc = {"name": name.strip(), "prompt": prompt, "proposal": None, "asset": None}
        stamp = now()
        with self.transaction() as con:
            con.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)",
                        (identifier, 1, json.dumps(doc, ensure_ascii=False), None, stamp, stamp))
            self.event(con, identifier, "project_created", {"revision": 1})
        return self.get(identifier)

    def get(self, identifier):
        with self.transaction() as con:
            project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
            project["jobs"] = [self.job(r) for r in con.execute(
                "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC", (identifier,))]
            return project

    def list(self):
        with self.transaction() as con:
            return [self.project(row) for row in con.execute("SELECT * FROM projects ORDER BY updated_at DESC")]

    def editable(self, con, identifier, revision):
        project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
        if project["revision"] != revision:
            raise WorkflowError("STALE_VERSION_RELOAD")
        if con.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('queued','running')",
                       (identifier,)).fetchone():
            raise WorkflowError("PROJECT_BUSY")
        return project

    def save(self, identifier, revision, *, prompt=None, proposal=None, asset=None):
        if prompt is not None and (not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 20000):
            raise WorkflowError("PROMPT_REQUIRED_MAX_20000", 400)
        if proposal is not None:
            try:
                proposal = Proposal.model_validate(proposal).model_dump()
            except ValueError:
                raise WorkflowError("INVALID_PROPOSAL_SCENE_COVERAGE", 400) from None
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            if prompt is not None and prompt != doc["prompt"]:
                doc["prompt"], doc["proposal"] = prompt, None
            if proposal is not None:
                doc["proposal"] = proposal
            if asset is not None:
                doc["asset"] = asset
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                        (revision + 1, json.dumps(doc, ensure_ascii=False), now(), identifier))
            self.event(con, identifier, "draft_saved_approval_invalidated", {"revision": revision + 1})
        return self.get(identifier)

    def approve(self, identifier, revision, reviewer, acknowledged):
        if acknowledged is not True or not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 100:
            raise WorkflowError("HUMAN_REVIEW_REQUIRED", 400)
        with self.transaction() as con:
            project = self.editable(con, identifier, revision)
            doc = project["document"]
            if not doc["proposal"] or not doc["asset"]:
                raise WorkflowError("CONTENT_AND_IMAGE_REQUIRED")
            approval = {"revision": revision, "snapshot_sha256": digest(doc),
                        "reviewer": reviewer.strip(), "approved_at": now(), "source": "local_ui_human_review"}
            con.execute("UPDATE projects SET approval=?,updated_at=? WHERE id=?",
                        (json.dumps(approval, ensure_ascii=False), now(), identifier))
            self.event(con, identifier, "human_content_approved", approval)
        return self.get(identifier)

    def enqueue(self, identifier, revision, kind, request_key):
        if kind not in {"content", "render"} or not isinstance(request_key, str) or not 8 <= len(request_key) <= 100:
            raise WorkflowError("INVALID_JOB_REQUEST", 400)
        identity = digest({"project_id": identifier, "revision": revision, "kind": kind})
        with self.transaction() as con:
            existing = con.execute("SELECT * FROM jobs WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                if existing["request_sha"] != identity:
                    raise WorkflowError("IDEMPOTENCY_KEY_CONFLICT")
                return self.job(existing)
            project = self.editable(con, identifier, revision)
            doc, approval = project["document"], project["approval"]
            if kind == "render" and (not approval or approval["revision"] != revision
                                     or approval["snapshot_sha256"] != digest(doc)):
                raise WorkflowError("HUMAN_APPROVAL_REQUIRED_BEFORE_TTS")
            identifier_job, stamp = uuid.uuid4().hex, now()
            snapshot = {"document": doc, "approval": approval}
            con.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (identifier_job, identifier, revision, kind, "queued", "queued", request_key, identity,
                         json.dumps(snapshot, ensure_ascii=False), None, None, stamp, stamp))
            self.event(con, identifier, "job_queued", {"job_id": identifier_job, "kind": kind, "revision": revision})
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier_job,)).fetchone())

    def claim(self):
        with self.transaction() as con:
            row = con.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row is None:
                return None
            con.execute("UPDATE jobs SET status='running',stage='starting',updated_at=? WHERE id=?", (now(), row["id"]))
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def stage(self, identifier, stage):
        with self.transaction() as con:
            con.execute("UPDATE jobs SET stage=?,updated_at=? WHERE id=? AND status='running'", (stage, now(), identifier))

    def finish(self, job, result=None, error=None):
        with self.transaction() as con:
            row = con.execute("SELECT status FROM jobs WHERE id=?", (job["id"],)).fetchone()
            if row is None or row["status"] != "running":
                raise WorkflowError("JOB_STATE_CONFLICT")
            status = "failed" if error else ("awaiting_review" if job["kind"] == "content" else "succeeded")
            if result and job["kind"] == "content":
                project = self.project(con.execute("SELECT * FROM projects WHERE id=?", (job["project_id"],)).fetchone())
                if project["revision"] != job["revision"]:
                    raise WorkflowError("STALE_CONTENT_RESULT")
                doc = project["document"]
                doc["proposal"] = Proposal.model_validate(result["proposal"]).model_dump()
                con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
                            (project["revision"] + 1, json.dumps(doc, ensure_ascii=False), now(), project["id"]))
            con.execute("UPDATE jobs SET status=?,stage=?,error=?,result=?,updated_at=? WHERE id=?",
                        (status, status, json.dumps(error) if error else None,
                         json.dumps(result, ensure_ascii=False) if result else None, now(), job["id"]))
            self.event(con, job["project_id"], "job_finished", {"job_id": job["id"], "status": status, "error": error})

    def recover(self):
        # Unstarted jobs are safe to drain. Dispatched/ambiguous work is NEVER replayed.
        with self.transaction() as con:
            for row in con.execute("SELECT * FROM jobs WHERE status='running'").fetchall():
                error = {"code": "INTERRUPTED_NO_AUTOMATIC_REPLAY", "last_stage": row["stage"]}
                con.execute("UPDATE jobs SET status='interrupted',stage='interrupted',error=?,updated_at=? WHERE id=?",
                            (json.dumps(error), now(), row["id"]))
                self.event(con, row["project_id"], "job_interrupted", {"job_id": row["id"], **error})

    def get_job(self, identifier):
        with self.transaction() as con:
            return self.job(con.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone())
