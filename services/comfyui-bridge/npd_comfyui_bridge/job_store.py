"""Durable bridge state, private inputs and content-free delivery audit.

The optional GPU bridge owns this database. It neither opens the Video Factory
database nor shares Agent Hub state. One process owns a store at a time.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .models import BridgeJobCreate, BridgeJobRead


MAX_DOCUMENT_BYTES = 128 * 1024


def encoded(value):
    result = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    if len(result) > MAX_DOCUMENT_BYTES:
        raise ValueError("BRIDGE_DOCUMENT_TOO_LARGE")
    return result


def checksum(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def linked(path):
    return any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in [path, *path.parents])


class SQLiteBridgeJobStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        if any(linked(p) for p in [self.path, self.path.with_suffix(self.path.suffix + '.lock'),
                Path(str(self.path) + '-wal'), Path(str(self.path) + '-shm')]):
            raise ValueError("BRIDGE_STORE_PATH_INVALID")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lease = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self._lease.seek(0)
                if not self._lease.read(1):
                    self._lease.write(b"1"); self._lease.flush()
                self._lease.seek(0)
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lease.close()
            raise RuntimeError("BRIDGE_STORE_IN_USE") from None
        try:
            self.connection = sqlite3.connect(self.path)
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS bridge_jobs (
                  job_id TEXT PRIMARY KEY, client_request_id TEXT NOT NULL UNIQUE,
                  document BLOB NOT NULL, sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS bridge_events (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                  document BLOB NOT NULL, sha256 TEXT NOT NULL);
            """)
        except Exception:
            self._lease.close()
            raise

    def load(self):
        records = []
        rows = self.connection.execute("SELECT job_id, client_request_id, document, sha256 FROM bridge_jobs").fetchall()
        if len(rows) > 5000:
            raise RuntimeError("BRIDGE_STORE_LIMIT_REACHED")
        for job_id, client_request_id, raw, digest in rows:
            try:
                if len(raw) > MAX_DOCUMENT_BYTES or hashlib.sha256(raw).hexdigest() != digest:
                    raise ValueError()
                document = json.loads(raw)
                if set(document) != {"schema", "job", "request"} or document["schema"] != 1:
                    raise ValueError()
                job = BridgeJobRead.model_validate(document["job"])
                request = BridgeJobCreate.model_validate(document["request"])
                if (job.job_id != job_id or job.workspace_id != request.workspace_id or
                        job.client_request_id != request.client_request_id or
                        checksum([request.workspace_id, request.client_request_id]) != client_request_id):
                    raise ValueError()
                if job.result is not None and checksum(job.result) != job.result_metadata_sha256:
                    raise ValueError()
                if not job.definition_sha256 or (job.status == 'succeeded' and job.result is None):
                    raise ValueError()
                records.append((job, request))
            except (ValueError, TypeError, KeyError):
                raise RuntimeError("BRIDGE_STORE_INVALID") from None
        return records

    def save(self, job: BridgeJobRead, request: BridgeJobCreate):
        raw = encoded({"schema": 1, "job": job.model_dump(mode="json"), "request": request.model_dump(mode="json")})
        audit = encoded({"job_id": job.job_id, "workspace_id": job.workspace_id, "status": job.status, "progress": job.progress,
            "retry_count": job.retry_count, "error_code": job.error_code,
            "definition_sha256": job.definition_sha256, "result_metadata_sha256": job.result_metadata_sha256,
            "recovery_required": job.recovery_required, "recorded_at": job.updated_at.isoformat()})
        with self.connection:
            self.connection.execute("""INSERT INTO bridge_jobs(job_id,client_request_id,document,sha256) VALUES(?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET document=excluded.document,sha256=excluded.sha256""",
                (job.job_id, checksum([request.workspace_id, request.client_request_id]), raw, hashlib.sha256(raw).hexdigest()))
            self.connection.execute("INSERT INTO bridge_events(job_id,document,sha256) VALUES(?,?,?)",
                (job.job_id, audit, hashlib.sha256(audit).hexdigest()))

    def events(self, job_id, *, limit=200):
        rows = self.connection.execute("SELECT sequence,document,sha256 FROM bridge_events WHERE job_id=? ORDER BY sequence DESC LIMIT ?",
            (job_id, min(200, max(1, limit)))).fetchall()
        output = []
        for sequence, raw, digest in reversed(rows):
            if hashlib.sha256(raw).hexdigest() != digest:
                raise RuntimeError("BRIDGE_AUDIT_INVALID")
            output.append({"sequence": sequence, **json.loads(raw)})
        return output

    def close(self):
        self.connection.close()
        self._lease.close()
