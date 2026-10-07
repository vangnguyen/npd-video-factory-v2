"""Additive, local persistence; never migrates the accepted production database."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from .contracts import WorkflowError, canonical, digest
from .intelligence_models import MODELS


class IntelligenceStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "intelligence.sqlite3"
        with self.transaction() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise WorkflowError("INTELLIGENCE_SCHEMA_UNSUPPORTED")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,id TEXT PRIMARY KEY,version INTEGER NOT NULL,document TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS record_kind ON records(kind);
                CREATE TABLE IF NOT EXISTS versions(id TEXT NOT NULL,version INTEGER NOT NULL,kind TEXT NOT NULL,document TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(id,version));
                CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT,record_id TEXT NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,action TEXT NOT NULL,status TEXT NOT NULL,request_key TEXT UNIQUE NOT NULL,request_sha256 TEXT NOT NULL,error TEXT,created_at TEXT NOT NULL);
                PRAGMA user_version=1;
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

    def get(self, identifier, kind=None, con=None):
        if con is None:
            with self.transaction() as conn:
                return self.get(identifier, kind, conn)
        row = con.execute("SELECT * FROM records WHERE id=?", (identifier,)).fetchone()
        if not row or (kind and row["kind"] != kind):
            raise WorkflowError("INTELLIGENCE_RECORD_NOT_FOUND", 404)
        value = MODELS[row['kind']].model_validate_json(row['document']).model_dump(mode='json')
        version = con.execute("SELECT sha256 FROM versions WHERE id=? AND version=?", (identifier, value['version'])).fetchone()
        if not version or version[0] != digest(value) or row['version'] != value['version']:
            raise WorkflowError("INTELLIGENCE_HISTORY_INTEGRITY_FAILED")
        return value

    def put(self, kind, value, expected=None, con=None):
        if con is None:
            with self.transaction() as conn:
                return self.put(kind, value, expected, conn)
        value = MODELS[kind].model_validate(value).model_dump(mode='json')
        previous = con.execute("SELECT * FROM records WHERE id=?", (value['id'],)).fetchone()
        if previous:
            if previous['kind'] != kind or expected != previous['version']:
                raise WorkflowError("INTELLIGENCE_STALE_VERSION_RELOAD")
            old = self.get(value['id'], kind, con)
            value.update(version=expected+1, created_at=old['created_at'], updated_at=datetime.now(timezone.utc).isoformat())
        elif expected is not None or value['version'] != 1:
            raise WorkflowError("INTELLIGENCE_NEW_RECORD_VERSION_INVALID")
        value = MODELS[kind].model_validate(value).model_dump(mode='json')
        raw = canonical(value).decode('utf-8')
        con.execute("INSERT INTO versions VALUES(?,?,?,?,?)", (value['id'], value['version'], kind, raw, digest(value)))
        con.execute("INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,document=excluded.document", (kind, value['id'], value['version'], raw))
        bridge=getattr(self,'bridge',None)
        if bridge is not None:bridge.capture_intelligence(con,kind,value)
        return value

    def list(self, kind):
        with self.transaction() as con:
            return [self.get(r[0], kind, con) for r in con.execute("SELECT id FROM records WHERE kind=? ORDER BY rowid DESC", (kind,)).fetchall()]

    def history(self, identifier):
        with self.transaction() as con:
            self.get(identifier, con=con)
            return [json.loads(r[0]) for r in con.execute("SELECT document FROM versions WHERE id=? ORDER BY version", (identifier,))]

    def decision(self, con, identifier, action, payload):
        con.execute("INSERT INTO decisions(record_id,action,payload,created_at) VALUES(?,?,?,?)", (identifier, action, canonical(payload).decode(), datetime.now(timezone.utc).isoformat()))
