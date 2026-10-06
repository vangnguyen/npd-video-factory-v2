"""Additive local planning metadata; never changes production or research records."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3

from .contracts import WorkflowError, digest


def now():
    return datetime.now(timezone.utc).isoformat()


def human(reviewer):
    if not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 100:
        raise WorkflowError('PLANNING_REVIEWER_REQUIRED', 400)
    return reviewer.strip()


FIELDS = {'campaign', 'planned_date', 'format', 'duration_seconds', 'project_priority',
          'campaign_priority', 'assigned_to', 'assigned_status', 'similarity_override'}


def validate_changes(changes):
    if not isinstance(changes, dict) or not changes or set(changes) - FIELDS:
        raise WorkflowError('PLANNING_FIELDS_INVALID', 400)
    result = dict(changes)
    for key in ('campaign', 'assigned_to'):
        if key in result and (not isinstance(result[key], str) or len(result[key]) > 150):
            raise WorkflowError('PLANNING_TEXT_INVALID', 400)
        if key in result:
            result[key] = result[key].strip()
    if 'planned_date' in result and result['planned_date'] is not None:
        try:
            if not isinstance(result['planned_date'], str) or date.fromisoformat(result['planned_date']).isoformat() != result['planned_date']:
                raise ValueError()
        except ValueError:
            raise WorkflowError('PLANNING_DATE_INVALID', 400) from None
    if 'format' in result and result['format'] not in {'9:16', '16:9'}:
        raise WorkflowError('PLANNING_FORMAT_INVALID', 400)
    if 'duration_seconds' in result and result['duration_seconds'] not in {30, 45, 60}:
        raise WorkflowError('PLANNING_DURATION_INVALID', 400)
    for key in ('project_priority', 'campaign_priority'):
        if key in result and (type(result[key]) not in (int, float) or not 0 <= result[key] <= 100):
            raise WorkflowError('PLANNING_PRIORITY_INVALID', 400)
    if 'assigned_status' in result and result['assigned_status'] not in {'UNASSIGNED', 'ASSIGNED', 'IN_PROGRESS', 'DONE'}:
        raise WorkflowError('PLANNING_ASSIGNMENT_INVALID', 400)
    if 'similarity_override' in result and result['similarity_override'] is not None:
        value = result['similarity_override']
        if (not isinstance(value, dict) or set(value) != {'warning_sha256', 'note'}
                or not isinstance(value['warning_sha256'], str) or len(value['warning_sha256']) != 64
                or not isinstance(value['note'], str) or not 1 <= len(value['note'].strip()) <= 2000):
            raise WorkflowError('SIMILARITY_OVERRIDE_REASON_REQUIRED', 400)
    return result


class PlanningStore:
    schema_version = 'local-production-planning-v1'

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'localplanning.sqlite3'
        with self.transaction() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS planning(id TEXT PRIMARY KEY, version INTEGER NOT NULL, document TEXT NOT NULL, sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS planning_versions(id TEXT NOT NULL, version INTEGER NOT NULL, document TEXT NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(id,version));
                CREATE TABLE IF NOT EXISTS planning_decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS planning_batches(request_key TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, document TEXT NOT NULL, receipt_sha256 TEXT);
            ''')
            columns = {r['name'] for r in con.execute('PRAGMA table_info(planning_batches)')}
            if 'receipt_sha256' not in columns:
                con.execute('ALTER TABLE planning_batches ADD COLUMN receipt_sha256 TEXT')
            for row in con.execute('SELECT request_key,document FROM planning_batches WHERE receipt_sha256 IS NULL').fetchall():
                con.execute('UPDATE planning_batches SET receipt_sha256=? WHERE request_key=?', (digest(json.loads(row['document'])), row['request_key']))

    @contextmanager
    def transaction(self):
        con = sqlite3.connect(self.db, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA synchronous=FULL')
        con.execute('BEGIN IMMEDIATE')
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def decode(row):
        value = json.loads(row['document'])
        if digest(value) != row['sha256'] or value['version'] != row['version']:
            raise WorkflowError('PLANNING_RECORD_INTEGRITY_FAILED')
        return value

    def get(self, identifier, defaults):
        with self.transaction() as con:
            row = con.execute('SELECT * FROM planning WHERE id=?', (identifier,)).fetchone()
            if not row:
                return defaults
            historical = con.execute('SELECT * FROM planning_versions WHERE id=? AND version=?', (identifier, row['version'])).fetchone()
            if not historical or historical['sha256'] != row['sha256']:
                raise WorkflowError('PLANNING_HISTORY_INTEGRITY_FAILED')
            return self.decode(row)

    def save(self, identifier, defaults, version, changes, reviewer, binding):
        changes = validate_changes(changes)
        reviewer = human(reviewer)
        if type(version) is not int:
            raise WorkflowError('PLANNING_VERSION_REQUIRED', 400)
        with self.transaction() as con:
            row = con.execute('SELECT * FROM planning WHERE id=?', (identifier,)).fetchone()
            old = self.decode(row) if row else defaults
            if old['version'] != version:
                raise WorkflowError('PLANNING_STALE_VERSION_RELOAD')
            if changes.get('similarity_override'):
                changes['similarity_override'] = {**changes['similarity_override'], 'reviewer': reviewer, 'reviewed_at': now()}
            value = {**old, **changes, 'version': version + 1, 'updated_at': now(),
                     'provenance': {**old['provenance'], 'last_edit': {'reviewer': reviewer, 'binding': binding, 'at': now()}}}
            encoded = json.dumps(value, ensure_ascii=False)
            sha = digest(value)
            con.execute('INSERT INTO planning VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,document=excluded.document,sha256=excluded.sha256', (identifier, value['version'], encoded, sha))
            con.execute('INSERT INTO planning_versions VALUES(?,?,?,?)', (identifier, value['version'], encoded, sha))
            con.execute('INSERT INTO planning_decisions(item_id,action,payload,created_at) VALUES(?,?,?,?)',
                        (identifier, 'human_planning_saved', json.dumps({'reviewer': reviewer, 'changes': changes, 'binding': binding}, ensure_ascii=False), now()))
            return value

    def history(self, identifier):
        with self.transaction() as con:
            return [self.decode(r) for r in con.execute('SELECT * FROM planning_versions WHERE id=? ORDER BY version DESC', (identifier,))]

    def begin_batch(self, request_key, request):
        sha = digest(request)
        with self.transaction() as con:
            row = con.execute('SELECT * FROM planning_batches WHERE request_key=?', (request_key,)).fetchone()
            if row:
                if row['request_sha256'] != sha:
                    raise WorkflowError('BATCH_IDEMPOTENCY_KEY_CONFLICT')
                return self.decode_batch(row), False
            value = {'schema_version': 'human-production-batch-v1', 'id': request_key, 'version': 1, 'status': 'RUNNING',
                     'action': request['action'], 'created_at': now(), 'updated_at': now(),
                     'provenance': {'request_sha256': sha, 'reviewer': request['reviewer'], 'explicit_action': True},
                     'request': request, 'items': [], 'automatic_approval': False, 'render_dispatched': False}
            con.execute('INSERT INTO planning_batches VALUES(?,?,?,?)', (request_key, sha, json.dumps(value, ensure_ascii=False), digest(value)))
            return value, True

    @staticmethod
    def decode_batch(row):
        value = json.loads(row['document'])
        if digest(value) != row['receipt_sha256'] or value['provenance']['request_sha256'] != row['request_sha256']:
            raise WorkflowError('BATCH_RECEIPT_INTEGRITY_FAILED')
        if 'request' in value and digest(value['request']) != row['request_sha256']:
            raise WorkflowError('BATCH_REQUEST_INTEGRITY_FAILED')
        return value

    def batch_receipt(self, request_key):
        with self.transaction() as con:
            row = con.execute('SELECT * FROM planning_batches WHERE request_key=?', (request_key,)).fetchone()
            if not row:
                raise WorkflowError('BATCH_RECEIPT_NOT_FOUND', 404)
            value = self.decode_batch(row)
            return {**value, 'status': 'OUTCOME_UNKNOWN_NO_REPLAY', 'resume_required': True} if value['status'] == 'RUNNING' else value

    def batch_progress(self, request_key, value):
        value = {**value, 'version': value.get('version', 1) + 1, 'updated_at': now()}
        with self.transaction() as con:
            con.execute('UPDATE planning_batches SET document=?,receipt_sha256=? WHERE request_key=?', (json.dumps(value, ensure_ascii=False), digest(value), request_key))
        return value
