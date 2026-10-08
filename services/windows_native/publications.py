"""Durable Native dry-run distribution. Live transport is deliberately unconfigured."""
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace
import uuid

from .backup import guard
from .contracts import WorkflowError, digest
from .source_assets import canonical_assets
from .store import now
from app.publishing_logic import PublishingCapabilityRegistry, validate_platform, validate_rights
from app.publishing_models import PublicationReceipt
from app.publishing_providers import MockPublishingProvider, PublishingContext

VERSION = 'native-publication-v1'
PROFILES = {(1080, 1920): 'vertical-1080x1920', (1920, 1080): 'landscape-1920x1080', (1080, 1080): 'square-1080x1080'}


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None: raise WorkflowError('NATIVE_PUBLICATION_TIME_INVALID', 400)
    return value.astimezone(timezone.utc)


class NativePublications:
    def __init__(self, store, capabilities_path, *, workspace_id='wsp_native_local', clock=lambda: datetime.now(timezone.utc)):
        self.store, self.workspace_id, self.clock = store, workspace_id, clock
        self.capabilities_path = guard(capabilities_path, exists=True)
        guard(store.db, exists=True)
        self.provider = MockPublishingProvider()
        self.capabilities = PublishingCapabilityRegistry(self.capabilities_path)
        from .contracts import file_sha
        self.capabilities_sha256 = file_sha(self.capabilities_path)
        with store.transaction() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS native_publications (
                    publication_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    request_key_sha256 TEXT NOT NULL, request_fingerprint TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL, status TEXT NOT NULL, approval_json TEXT,
                    receipt_json TEXT, failure_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(workspace_id,project_id,request_key_sha256));
                CREATE INDEX IF NOT EXISTS native_publication_history ON native_publications(workspace_id,project_id,created_at,publication_id);
                CREATE TABLE IF NOT EXISTS native_publication_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, publication_id TEXT NOT NULL,
                    project_id TEXT NOT NULL, action TEXT NOT NULL, actor_ref TEXT NOT NULL,
                    evidence_json TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')

    def event(self, con, row, action, actor, **evidence):
        con.execute('INSERT INTO native_publication_events(publication_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?)',
            (row['publication_id'], row['project_id'], action, actor, json.dumps(evidence), now()))
        bridge=getattr(self.store,'bridge',None)
        if bridge is not None:bridge.capture_publication(con,row,action)

    def read(self, row):
        value = dict(row); snapshot = json.loads(value.pop('snapshot_json'))
        if (digest(snapshot) != value['snapshot_sha256'] or snapshot.get('workspace_id') != self.workspace_id
            or snapshot.get('project_id') != value['project_id'] or snapshot.get('request_fingerprint') != value['request_fingerprint']
            or digest(snapshot.get('request')) != value['request_fingerprint']):
            raise WorkflowError('NATIVE_PUBLICATION_IMMUTABLE_EVIDENCE_INVALID')
        value.pop('request_key_sha256'); value['snapshot'] = snapshot
        for key in ('approval', 'receipt'):
            raw = value.pop(key + '_json'); value[key] = json.loads(raw) if raw else None
        if value['receipt'] is not None:
            try: receipt = PublicationReceipt.model_validate(value['receipt'])
            except ValueError: raise WorkflowError('NATIVE_PUBLICATION_RECEIPT_INVALID') from None
            if (receipt.mode != 'dry_run' or receipt.mock is not True or receipt.external_action is not False
                or receipt.provider_key != 'mock-publishing' or receipt.request_fingerprint != value['request_fingerprint']
                or receipt.platform != snapshot['request']['platform'] or receipt.remote_post_id is not None or receipt.remote_url is not None
                or value['status'] != 'dry_run_succeeded'):
                raise WorkflowError('NATIVE_PUBLICATION_RECEIPT_INVALID')
        elif value['status'] == 'dry_run_succeeded': raise WorkflowError('NATIVE_PUBLICATION_RECEIPT_INVALID')
        return {**value, 'schema_version': VERSION, 'mock': True, 'external_action': False,
            'publish_enabled': False, 'live_adapter_state': 'not_configured', 'production_deployed': False}

    def get_row(self, con, project, identity):
        self.store.project(con.execute('SELECT * FROM projects WHERE id=?', (project,)).fetchone())
        row = con.execute('SELECT * FROM native_publications WHERE publication_id=? AND project_id=? AND workspace_id=?',
            (identity, project, self.workspace_id)).fetchone()
        if row is None: raise WorkflowError('NATIVE_PUBLICATION_NOT_FOUND', 404)
        return row

    def get(self, project, identity):
        with self.store.transaction() as con:
            row = self.get_row(con, project, identity); result = self.read(row)
            events = con.execute('SELECT * FROM native_publication_events WHERE publication_id=? ORDER BY event_id DESC LIMIT 101', (identity,)).fetchall()
            result['events'] = [{**dict(item), 'evidence_json': json.loads(item['evidence_json'])} for item in events[:100]]
            result['events_truncated'] = len(events) > 100
            return result

    def page(self, project, *, limit=25, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 100: raise WorkflowError('NATIVE_PUBLICATION_PAGE_INVALID', 400)
        after = None
        if cursor is not None:
            try:
                if not isinstance(cursor, str) or len(cursor) > 1000: raise ValueError()
                after = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
                if (not isinstance(after, list) or len(after) != 4 or after[:2] != [self.workspace_id, project]
                    or not isinstance(after[2], str) or not isinstance(after[3], str)):
                    raise ValueError()
                utc(datetime.fromisoformat(after[2]))
            except (ValueError, TypeError, WorkflowError): raise WorkflowError('NATIVE_PUBLICATION_CURSOR_INVALID', 400) from None
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?', (project,)).fetchone())
            where = 'workspace_id=? AND project_id=?'; params = [self.workspace_id, project]
            if after:
                where += ' AND (created_at<? OR (created_at=? AND publication_id<?))'; params.extend([after[2], after[2], after[3]])
            rows = con.execute('SELECT * FROM native_publications WHERE ' + where + ' ORDER BY created_at DESC,publication_id DESC LIMIT ?', (*params, limit + 1)).fetchall()
            items = [self.read(row) for row in rows[:limit]]; next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                next_cursor = base64.urlsafe_b64encode(json.dumps([self.workspace_id, project, last['created_at'], last['publication_id']]).encode()).decode().rstrip('=')
            return {'schema_version': 'native-publication-page-v1', 'workspace_id': self.workspace_id, 'project_id': project,
                'items': items, 'next_cursor': next_cursor, 'limit': limit, 'publish_enabled': False, 'external_action': False}

    def render(self, con, project, identity):
        path = guard(self.store.root / 'jobs' / identity / 'final.mp4', exists=True)
        job, actual = self.store.verified_render(identity, con)
        review = job['final_review']
        if (job['project_id'] != project or not review or review['decision'] != 'approve'
            or review['revision'] != job['revision'] or review['artifact_sha256'] != actual
            or review['snapshot_sha256'] != digest(job['snapshot'])):
            raise WorkflowError('HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED')
        return job, actual, path

    def validation(self, job, path, payload):
        document = job['snapshot']['document']; timeline = document.get('canonical_timeline', {}).get('snapshot')
        assets = canonical_assets(document)
        if timeline:
            used = {clip.get('metadata', {}).get('native_asset_id') for track in timeline['tracks'] if not track['disabled']
                for clip in track['clips'] if not clip['disabled'] and clip.get('asset_id')}
        else:
            used = {item['asset_id'] for item in document.get('scene_media', [])}
            if not used and document.get('asset'): used.add(document['asset']['id'])
            if document.get('music') and document.get('music_enabled') is not False: used.add(document['music']['id'])
        available = {item['id']: item for item in assets}
        projections = [SimpleNamespace(asset_id=identity, provenance={**available.get(identity, {}).get('provenance', {}),
            **{key: available.get(identity, {})[key] for key in ('rights_status', 'license', 'production_eligible') if key in available.get(identity, {})}}) for identity in used]
        rights = validate_rights(projections)
        from .rights_override import validate_publication_rights
        rights=validate_publication_rights(self.store,document,job['project_id'],assets,used,rights)
        from .publication_qc import project as project_qc
        qc = project_qc(job); profile = PROFILES.get((qc.get('width'), qc.get('height')), 'native-unmapped-profile')
        platform = validate_platform(capability=self.capabilities.get(payload.platform), metadata=payload.metadata,
            render=SimpleNamespace(profile=profile, qc_report=qc), output_asset=SimpleNamespace(size_bytes=path.stat().st_size), mode='dry_run')
        attention = []
        # Physical source rights alone do not establish locked/generated voice/model rights for publication.
        if not timeline or timeline.get('metadata', {}).get('native_auto_edit_schema') != 'native-auto-edit-timeline-v1':
            attention.append('NATIVE_GENERATED_VOICE_PUBLICATION_PROVENANCE_REQUIRED')
        if payload.metadata.thumbnail_asset_id is not None: attention.append('NATIVE_THUMBNAIL_PUBLICATION_BINDING_NOT_CONFIGURED')
        passed = rights.status == platform.status == 'passed' and not attention
        return {'rights': rights.model_dump(mode='json'), 'platform': platform.model_dump(mode='json'), 'attention': attention,
            'status': 'passed' if passed else 'failed', 'provider': self.provider.validate().model_dump(mode='json')}

    def create(self, project, payload, *, actor):
        request_hash = digest(payload.model_dump(mode='json', exclude={'request_key'})); key_hash = hashlib.sha256(payload.request_key.encode()).hexdigest()
        with self.store.transaction() as con:
            prior = con.execute('SELECT * FROM native_publications WHERE workspace_id=? AND project_id=? AND request_key_sha256=?',
                (self.workspace_id, project, key_hash)).fetchone()
            if prior:
                if prior['request_fingerprint'] != request_hash: raise WorkflowError('NATIVE_PUBLICATION_IDEMPOTENCY_CONFLICT')
                return self.read(prior), True
            job, actual, path = self.render(con, project, payload.final_job_id)
            if payload.revision != job['revision']: raise WorkflowError('STALE_VERSION_RELOAD')
            scheduled = payload.metadata.scheduled_at
            if scheduled and not utc(self.clock()) < utc(scheduled) <= utc(self.clock()) + timedelta(days=365):
                raise WorkflowError('NATIVE_PUBLICATION_SCHEDULE_INVALID', 400)
            validation = self.validation(job, path, payload)
            from .contracts import file_sha
            if file_sha(self.capabilities_path) != self.capabilities_sha256:
                raise WorkflowError('NATIVE_PUBLICATION_CAPABILITIES_CHANGED_RESTART_REQUIRED')
            snapshot = {'schema_version': 'native-publication-snapshot-v1', 'workspace_id': self.workspace_id, 'project_id': project,
                'request': payload.model_dump(mode='json', exclude={'request_key'}), 'request_fingerprint': request_hash,
                'job_snapshot_sha256': digest(job['snapshot']), 'final_sha256': actual, 'final_bytes': path.stat().st_size,
                'final_review': job['final_review'], 'canonical_timeline_sha256': digest(job['snapshot']['document'].get('canonical_timeline')),
                'capabilities_sha256': file_sha(self.capabilities_path), 'validation': validation,
                'human_publish_approval_required': True, 'publish_enabled': False, 'external_action': False}
            identity = 'npub_' + uuid.uuid4().hex; created = now()
            status = 'awaiting_publish_approval' if validation['status'] == 'passed' else 'blocked'
            con.execute('INSERT INTO native_publications VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity, self.workspace_id, project, key_hash, request_hash, digest(snapshot), json.dumps(snapshot, ensure_ascii=False),
                 status, None, None, None, created, created))
            row = self.get_row(con, project, identity)
            self.event(con, row, 'publication.review.created', actor, request_fingerprint=request_hash, final_sha256=actual, status=status, external_action=False)
            return self.read(row), False

    def revalidate(self, con, row):
        from .contracts import file_sha
        from .publication_models import NativePublicationCreate
        value = self.read(row); snapshot = value['snapshot']
        payload = NativePublicationCreate.model_validate({**snapshot['request'], 'request_key': 'internal-no-dispatch-key'})
        job, actual, path = self.render(con, row['project_id'], payload.final_job_id)
        if (payload.revision != job['revision'] or digest(job['snapshot']) != snapshot['job_snapshot_sha256']
            or actual != snapshot['final_sha256'] or path.stat().st_size != snapshot['final_bytes']
            or job['final_review'] != snapshot['final_review'] or file_sha(self.capabilities_path) != snapshot['capabilities_sha256']):
            raise WorkflowError('NATIVE_PUBLICATION_REVIEW_BINDING_CHANGED')
        if self.validation(job, path, payload) != snapshot['validation'] or snapshot['validation']['status'] != 'passed':
            raise WorkflowError('NATIVE_PUBLICATION_VALIDATION_FAILED')
        return value, payload

    def approve(self, project, identity, payload, *, actor):
        with self.store.transaction() as con:
            row = self.get_row(con, project, identity); value, request = self.revalidate(con, row)
            if payload.expected_fingerprint != row['request_fingerprint'] or payload.expected_artifact_sha256 != value['snapshot']['final_sha256']:
                raise WorkflowError('NATIVE_PUBLICATION_REVIEW_BINDING_CHANGED')
            if row['status'] in ('queued', 'scheduled', 'dry_run_succeeded') and value['approval']:
                return value
            if row['status'] != 'awaiting_publish_approval': raise WorkflowError('NATIVE_PUBLICATION_NOT_REVIEWABLE')
            approval = {'actor_ref': actor, 'acknowledged': True, 'request_fingerprint': row['request_fingerprint'],
                'snapshot_sha256': row['snapshot_sha256'], 'final_sha256': value['snapshot']['final_sha256'], 'created_at': now(),
                'mode': 'dry_run', 'live_publication_authorized': False}
            status = 'scheduled' if request.metadata.scheduled_at and utc(request.metadata.scheduled_at) > utc(self.clock()) else 'queued'
            con.execute('UPDATE native_publications SET status=?,approval_json=?,updated_at=? WHERE publication_id=?',
                (status, json.dumps(approval), now(), identity))
            self.event(con, row, 'publication.dry_run.approved', actor, snapshot_sha256=row['snapshot_sha256'], external_action=False)
            return self.read(self.get_row(con, project, identity))

    def cancel(self, project, identity, payload, *, actor):
        with self.store.transaction() as con:
            row = self.get_row(con, project, identity)
            if payload.expected_fingerprint != row['request_fingerprint']: raise WorkflowError('NATIVE_PUBLICATION_REVIEW_BINDING_CHANGED')
            if row['status'] == 'dry_run_succeeded': raise WorkflowError('NATIVE_PUBLICATION_ALREADY_COMPLETED')
            if row['status'] != 'cancelled':
                con.execute('UPDATE native_publications SET status=?,approval_json=NULL,updated_at=? WHERE publication_id=?', ('cancelled', now(), identity))
                self.event(con, row, 'publication.cancelled', actor, external_action=False)
            return self.read(self.get_row(con, project, identity))

    def process(self, *, project=None, identity=None, fingerprint=None):
        with self.store.transaction() as con:
            if identity:
                row = self.get_row(con, project, identity)
                if fingerprint != row['request_fingerprint']: raise WorkflowError('NATIVE_PUBLICATION_REVIEW_BINDING_CHANGED')
                if row['status'] == 'dry_run_succeeded': return self.read(row)
                candidates = [row]
            else:
                candidates = con.execute("SELECT * FROM native_publications WHERE workspace_id=? AND (status='queued' OR (status='scheduled' AND julianday(json_extract(snapshot_json,'$.request.metadata.scheduled_at'))<=julianday(?))) ORDER BY created_at,publication_id LIMIT 20",
                    (self.workspace_id, utc(self.clock()).isoformat())).fetchall()
            for row in candidates:
                if row['status'] not in ('queued', 'scheduled'): continue
                try:
                    value, payload = self.revalidate(con, row)
                    approval = value['approval'] or {}
                    if (approval.get('acknowledged') is not True or approval.get('mode') != 'dry_run'
                        or approval.get('snapshot_sha256') != row['snapshot_sha256'] or approval.get('request_fingerprint') != row['request_fingerprint']
                        or approval.get('final_sha256') != value['snapshot']['final_sha256'] or approval.get('live_publication_authorized') is not False):
                        raise WorkflowError('NATIVE_PUBLISH_REVIEW_REQUIRED')
                    if payload.metadata.scheduled_at and utc(payload.metadata.scheduled_at) > utc(self.clock()): continue
                    context = PublishingContext(platform=payload.platform, project_id=row['project_id'], final_render_id=payload.final_job_id,
                        output_asset_id=payload.final_job_id, request_fingerprint=row['request_fingerprint'], metadata=payload.metadata, publication_id=row['publication_id'])
                    # The shared mock provider is the only admitted implementation. No runtime factory, credentials or network calls.
                    if type(self.provider) is not MockPublishingProvider: raise WorkflowError('NATIVE_LIVE_PUBLICATION_NOT_CONFIGURED')
                    receipt = asyncio.run(self.provider.publish(context))
                    if (type(receipt) is not PublicationReceipt or receipt.provider_key != 'mock-publishing' or receipt.mode != 'dry_run'
                        or receipt.mock is not True or receipt.external_action is not False or receipt.remote_post_id is not None
                        or receipt.remote_url is not None or receipt.request_fingerprint != row['request_fingerprint'] or receipt.platform != payload.platform):
                        raise WorkflowError('NATIVE_PUBLICATION_RECEIPT_INVALID')
                    con.execute('UPDATE native_publications SET status=?,receipt_json=?,updated_at=? WHERE publication_id=?',
                        ('dry_run_succeeded', receipt.model_dump_json(), now(), row['publication_id']))
                    self.event(con, row, 'publication.dry_run.completed', 'native-dry-run-worker', receipt_id=receipt.receipt_id, mock=True, external_action=False)
                except WorkflowError as error:
                    con.execute('UPDATE native_publications SET status=?,failure_code=?,updated_at=? WHERE publication_id=?',
                        ('blocked', error.code, now(), row['publication_id']))
                    self.event(con, row, 'publication.dry_run.blocked', 'native-dry-run-worker', failure_code=error.code, external_action=False)
                except Exception:
                    con.execute('UPDATE native_publications SET status=?,failure_code=?,updated_at=? WHERE publication_id=?',
                        ('blocked', 'NATIVE_DRY_RUN_FAILED', now(), row['publication_id']))
                    self.event(con, row, 'publication.dry_run.blocked', 'native-dry-run-worker', failure_code='NATIVE_DRY_RUN_FAILED', external_action=False)
                return self.read(self.get_row(con, row['project_id'], row['publication_id']))
            return None
