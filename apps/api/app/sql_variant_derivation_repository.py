"""Storyboard derivative custody and atomic child creation on the existing SQL engine.

Claims commit before file copies. Completed receipts bind independently stored
bytes and immutable initial content/timeline. Unknown copies are never retried.
"""
import copy
import hashlib
import uuid
from datetime import timedelta
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .db import AssetORM, ProjectVersionORM, VideoProjectORM, utc_now
from .timeline_db import TimelineORM, TimelineVersionORM
from .content_models import ContentDocument
from .sql_variant_db import SqlVariantFamilyORM, SqlVariantMemberORM, SqlVariantArtifactReceiptORM
from .sql_variant_models import FamilySnapshot, VariantProgressSafety, as_utc, canonical, digest
from .sql_variant_derivation_models import DeriveStoryboardRequest, StoryboardDerivationRead
from .sql_variant_repository import SqlVariantFamilyRepository, SqlVariantError, identity, record_value, request_parts
from .sql_variant_identity import child_ids, derive_storyboard
from .object_storage import validate_object_key

UNKNOWN_CODES = frozenset({'SQL_VARIANT_COPY_CANCELLED', 'SQL_VARIANT_COPY_TIMEOUT',
    'SQL_VARIANT_COPY_IO_FAILED', 'SQL_VARIANT_COPY_SIZE_LIMIT', 'SQL_VARIANT_COPY_SOURCE_CHANGED',
    'SQL_VARIANT_COPY_RESULT_CHANGED', 'SQL_VARIANT_COPY_TARGET_EXISTS', 'SQL_VARIANT_COPY_LINK_REJECTED',
    'SQL_VARIANT_COPY_PATH_REJECTED', 'SQL_VARIANT_COPY_MEDIA_INVALID', 'SQL_VARIANT_S3_SOURCE_UNSUPPORTED',
    'SQL_VARIANT_MASTER_BINDING_CHANGED', 'SQL_VARIANT_DERIVATION_LEASE_EXPIRED',
    'SQL_VARIANT_STORAGE_BINDING_CHANGED',
    'SQL_VARIANT_DERIVATION_CONFLICT', 'SQL_VARIANT_DERIVATION_FAILED'})


def target_key(workspace, child, member, source_id, mime):
    suffix = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'audio/wav': 'wav',
        'audio/x-wav': 'wav', 'audio/mpeg': 'mp3', 'audio/ogg': 'ogg'}.get(mime)
    if suffix is None:
        raise SqlVariantError('SQL_VARIANT_S3_SOURCE_UNSUPPORTED')
    return validate_object_key(f'workspaces/{workspace}/projects/{child}/variant-imports/{member}/{source_id}.{suffix}')


def validate_input(row, family, members):
    """Immutable originals match S1 graph proofs, not freely rehashed metadata."""
    value = row.input_json
    request = DeriveStoryboardRequest.model_validate({**value['request'], 'request_key': 'internal-derivation-history-key'})
    member = next(m for m in members if m.member_id == row.member_id)
    snapshot = FamilySnapshot.model_validate(family.snapshot_json)
    sources = value['source_assets']
    if (set(value) != {'schema_version', 'workspace_id', 'master_project_id', 'family_id', 'member_id',
            'planned_project_id', 'family_snapshot_sha256', 'profile', 'request', 'source_content', 'source_timeline',
            'source_assets', 'safety'} or value['schema_version'] != 'sql-variant-storyboard-input.v1'
            or (value['workspace_id'], value['master_project_id'], value['family_id'], value['member_id'],
                value['planned_project_id'], value['family_snapshot_sha256']) != (family.workspace_id,
                family.master_project_id, family.family_id, row.member_id, member.planned_project_id, family.snapshot_sha256)
            or value['profile'] != member.profile_json or digest(value) != row.input_sha256
            or digest(value['request']) != row.request_sha256 or request.member_id != row.member_id
            or request.expected_snapshot_sha256 != family.snapshot_sha256
            or row.receipt_id != identity('vfr_', row.member_id + '/storyboard/' + row.input_sha256)
            or (row.workspace_id, row.family_id, row.kind) != (family.workspace_id, family.family_id, 'storyboard_derivation')
            or value['safety'] != VariantProgressSafety().model_dump(mode='json')
            or snapshot.binding.source_mode != 'storyboard_media'
            or digest(value['source_timeline']) != snapshot.binding.timeline_snapshot_sha256):
        raise ValueError('invalid derivative input')
    content = value['source_content']
    proof = next(p for p in snapshot.binding.records if p.table == 'project_versions'
        and p.owner_ref == snapshot.binding.source_content_version_id)
    if (digest([content]) != proof.sha256 or content['project_version_id'] != proof.owner_ref
            or (content['workspace_id'], content['project_id']) != (family.workspace_id, family.master_project_id)):
        raise ValueError('invalid source content')
    document = ContentDocument.model_validate(content['snapshot']['content'])
    used = {clip['asset_id'] for track in value['source_timeline']['tracks'] for clip in track['clips'] if clip.get('asset_id')}
    used.update(s.asset_id for s in document.scenes if s.asset_id)
    if set(sources) != used or not sources or len(sources) > 5000:
        raise ValueError('invalid derivative inventory')
    for source_id, source in sources.items():
        source_proof = next(a for a in snapshot.binding.assets if a.asset_id == source_id)
        if (digest(source) != source_proof.record_sha256 or source['asset_id'] != source_id
                or source['content_type'].startswith('video/') or source['storage_provider'] != 'local'
                or (source['workspace_id'], source['project_id']) != (family.workspace_id, family.master_project_id)
                or hashlib.sha256(source['object_key'].encode()).hexdigest() != source_proof.object_key_sha256):
            raise ValueError('invalid derivative asset')
    return member


async def validate_progress(session, family, members, events):
    """Reconstruct persisted state from exact claims/completions; no approval transfer."""
    receipts = (await session.scalars(select(SqlVariantArtifactReceiptORM).where(
        SqlVariantArtifactReceiptORM.family_id == family.family_id,
        SqlVariantArtifactReceiptORM.kind == 'storyboard_derivation'))).all()
    by_id, states, children = {}, {m.member_id: 'reserved' for m in members}, {}
    for receipt in receipts:
        validate_input(receipt, family, members)
        if receipt.receipt_id in by_id or receipt.member_id in [r.member_id for r in by_id.values()]:
            raise ValueError('duplicate member derivative')
        by_id[receipt.receipt_id] = receipt
        if receipt.state not in {'pending', 'ready', 'unknown', 'cancelled'} or receipt.target_asset_id is not None:
            raise ValueError('invalid derivative state')
        if receipt.state == 'pending':
            if not receipt.claim_id or receipt.lease_until is None or receipt.result_json is not None or receipt.error_code is not None:
                raise ValueError('invalid derivative claim')
        elif receipt.claim_id is not None or receipt.lease_until is not None:
            raise ValueError('terminal derivative retains lease')
        if receipt.state == 'ready':
            if receipt.result_json is None or digest(receipt.result_json) != receipt.result_sha256 or receipt.error_code is not None:
                raise ValueError('invalid derivative result')
            await validate_completed(session, receipt)
        elif receipt.result_json is not None or receipt.result_sha256 is not None:
            raise ValueError('unfinished derivative result')
        if receipt.state == 'unknown' and receipt.error_code not in UNKNOWN_CODES:
            raise ValueError('invalid bounded failure')
        if receipt.state == 'cancelled' and receipt.error_code is not None:
            raise ValueError('invalid cancellation evidence')
    current_state, claimed, finished = 'reserved', set(), set()
    for event in events[1:]:
        payload = event.payload_json
        if payload.get('from_version') != event.version - 1 or payload.get('to_version') != event.version:
            raise ValueError('invalid event transition')
        if event.event_type == 'family.cancelled':
            # S1 cancellation contract is unchanged, now also valid after a derivative claim.
            from .sql_variant_models import FamilyVersionRequest, NoAuthority
            request = FamilyVersionRequest.model_validate({**payload['request'], 'request_key': 'internal-cancel-history-key'})
            if (request.expected_version != event.version - 1 or request.expected_snapshot_sha256 != family.snapshot_sha256
                    or digest(payload['request']) != event.request_sha256
                    or payload != {'from_version': event.version-1, 'to_version': event.version,
                        'snapshot_sha256': family.snapshot_sha256, 'request': request.model_dump(mode='json', exclude={'request_key'}),
                        'safety': NoAuthority().model_dump(mode='json')} or current_state == 'cancelled'):
                raise ValueError('invalid cancellation')
            current_state = 'cancelled'
            states = {key: (state if state == 'needs_attention' else 'cancelled') for key, state in states.items()}
            continue
        receipt = by_id.get(payload.get('receipt_id'))
        if receipt is None or current_state == 'cancelled' or event.actor_ref != receipt.actor_ref or event.request_sha256 != receipt.request_sha256:
            raise ValueError('invalid receipt event')
        common = {'from_version': event.version-1, 'to_version': event.version,
            'snapshot_sha256': family.snapshot_sha256, 'receipt_id': receipt.receipt_id, 'input_sha256': receipt.input_sha256}
        stage = {'family.derivation.claimed': 'claim', 'family.derivation.completed': 'complete', 'family.derivation.unknown': 'unknown'}.get(event.event_type)
        if stage is None or event.request_key_sha256 != digest({'request_key_sha256': receipt.request_key_sha256, 'stage': stage}):
            raise ValueError('invalid derivative stage')
        if stage == 'claim':
            if receipt.member_id in claimed or states[receipt.member_id] != 'reserved' or receipt.input_json['request']['expected_version'] != event.version-1:
                raise ValueError('invalid repeated claim')
            if set(payload) != set(common) | {'claim_id'} or not isinstance(payload['claim_id'], str) or not payload['claim_id'].startswith('vfc_'):
                raise ValueError('invalid claim identity')
            if receipt.state == 'pending' and receipt.claim_id != payload['claim_id']:
                raise ValueError('claim was rebound')
            claimed.add(receipt.member_id)
            states[receipt.member_id], current_state = 'deriving', 'deriving'
        else:
            if receipt.member_id not in claimed or receipt.member_id in finished:
                raise ValueError('invalid completion order')
            if stage == 'complete':
                if receipt.state != 'ready' or payload != {**common, 'result_sha256': receipt.result_sha256,
                        'child_project_id': receipt.result_json['child_project_id']}:
                    raise ValueError('invalid completion evidence')
                states[receipt.member_id], current_state = 'needs_attention', 'needs_attention'
                children[receipt.member_id] = receipt.result_json
            else:
                if receipt.state != 'unknown' or payload != {**common, 'error_code': receipt.error_code}:
                    raise ValueError('invalid unknown evidence')
                states[receipt.member_id], current_state = 'failed', 'recovery_required'
            finished.add(receipt.member_id)
        if any(payload[k] != v for k, v in common.items()):
            raise ValueError('invalid common event binding')
    if family.state != current_state or any(m.state != states[m.member_id] for m in members):
        raise ValueError('state differs from history')
    for member in members:
        result = children.get(member.member_id)
        if (member.child_project_id, member.initial_timeline_version_id) != ((result['child_project_id'], result['timeline_version_id']) if result else (None, None)):
            raise ValueError('child differs from history')
    if claimed != {r.member_id for r in receipts}:
        raise ValueError('receipt lacks claim event')
    for receipt in receipts:
        if receipt.member_id not in finished and receipt.state != ('cancelled' if current_state == 'cancelled' else 'pending'):
            raise ValueError('receipt terminal state lacks terminal event')


async def validate_completed(session, receipt):
    value, result = receipt.input_json, receipt.result_json
    ids, content, timeline = derive_storyboard(value, result['copies'])
    expected = make_result(value, result['copies'])
    if result != expected:
        raise ValueError('derivative output rebound')
    child = await session.get(VideoProjectORM, result['child_project_id'])
    version = await session.get(ProjectVersionORM, ids['content_version_id'])
    first = await session.get(TimelineVersionORM, ids['timeline_version_id'])
    current = await session.get(TimelineORM, ids['timeline_id'])
    if (child is None or child.workspace_id != receipt.workspace_id or version is None
            or (version.project_id, version.workspace_id, version.label, version.snapshot) != (
                child.project_id, receipt.workspace_id, 'mvp1-content', {'content': content})
            or first is None or first.snapshot_json != timeline or first.project_id != child.project_id
            or first.timeline_id != ids['timeline_id'] or first.version != 1
            or first.actor_ref != receipt.actor_ref or first.mutation_json != {
                'type': 'storyboard_variant_derivative', 'receipt_id': receipt.receipt_id,
                'source_timeline_sha256': digest(value['source_timeline']), 'input_sha256': receipt.input_sha256}
            or current is None
            or current.project_id != child.project_id or current.workspace_id != receipt.workspace_id
            or current.source_content_version_id != ids['content_version_id'] and current.current_version == 1):
        raise ValueError('child immutable history changed')
    for old, new in ids['assets'].items():
        asset = await session.get(AssetORM, new)
        copied = result['copies'][old]
        if (asset is None or (asset.workspace_id, asset.project_id, asset.object_key, asset.size_bytes,
                asset.checksum_sha256, asset.content_type, asset.storage_provider, asset.project_version_id,
                asset.asset_class, asset.kind) != (
                receipt.workspace_id, child.project_id, copied['object_key'], copied['size_bytes'], copied['sha256'],
                copied['content_type'], copied['storage_provider'], ids['content_version_id'],
                value['source_assets'][old]['asset_class'], value['source_assets'][old]['kind'])
                or asset.provenance.get('derivation_receipt_id') != receipt.receipt_id
                or asset.provenance.get('parent_record_sha256') != digest(value['source_assets'][old])
                or asset.provenance.get('source_bytes_verified') is not True
                or (value['source_assets'][old]['provenance'].get('production_eligible') is False
                    and asset.provenance.get('production_eligible') is not False)):
            raise ValueError('child asset custody changed')


def make_result(value, copies):
    ids, content, timeline = derive_storyboard(value, copies)
    if set(copies) != set(value['source_assets']):
        raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
    for old, item in copies.items():
        source = value['source_assets'][old]
        if (set(item) != {'object_key', 'sha256', 'size_bytes', 'content_type', 'storage_provider', 'dimensions'}
                or (item['object_key'], item['sha256'], item['size_bytes'], item['content_type'], item['storage_provider']) != (
                    target_key(value['workspace_id'], value['planned_project_id'], value['member_id'], old, source['content_type']),
                    source['checksum_sha256'], source['size_bytes'], source['content_type'], 'local')):
            raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
        dimensions = item['dimensions']
        if source['content_type'].startswith('image/') and (not isinstance(dimensions, list) or len(dimensions) != 2
                or any(type(n) is not int or not 1 <= n <= 40_000_000 for n in dimensions)
                or dimensions[0]*dimensions[1] > 40_000_000):
            raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
    return {'schema_version': 'sql-variant-storyboard-result.v1', 'child_project_id': value['planned_project_id'],
        'content_version_id': ids['content_version_id'], 'content_sha256': digest(content),
        'timeline_id': ids['timeline_id'], 'timeline_version_id': ids['timeline_version_id'],
        'timeline_sha256': digest(timeline), 'asset_map': ids['assets'], 'copies': copy.deepcopy(copies),
        'safety': VariantProgressSafety(child_projects_created=1, source_bytes_verified=True).model_dump(mode='json'),
        'human_review_required': True, 'rights_review_required': True, 'reframe_attention_required': True}


class SqlStoryboardDerivationRepository:
    def __init__(self, families: SqlVariantFamilyRepository, *, lease_seconds=180):
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 900:
            raise ValueError('SQL_VARIANT_LEASE_INVALID')
        self.families, self.session_factory, self.lease_seconds = families, families.session_factory, lease_seconds

    async def _load(self, session, workspace, master, family_id):
        await self.families._project(session, workspace, master, lock=True)
        # Canonical writers lock TimelineORM (not necessarily ProjectORM).
        # Keep Project -> Timeline -> Family here. Do not acquire Package:
        # existing approval writers take Package -> Timeline, a different order.
        await session.scalar(select(TimelineORM).where(TimelineORM.project_id == master,
            TimelineORM.workspace_id == workspace).with_for_update().execution_options(populate_existing=True))
        row = await session.scalar(select(SqlVariantFamilyORM).where(SqlVariantFamilyORM.family_id == family_id,
            SqlVariantFamilyORM.workspace_id == workspace, SqlVariantFamilyORM.master_project_id == master).with_for_update())
        if row is None:
            raise KeyError('SQL_VARIANT_FAMILY_NOT_FOUND')
        return row, await self.families._read(session, row)

    @staticmethod
    def read(row):
        ready = row.state == 'ready'
        return StoryboardDerivationRead(receipt_id=row.receipt_id, family_id=row.family_id, member_id=row.member_id,
            workspace_id=row.workspace_id, state=row.state, input_sha256=row.input_sha256,
            request_sha256=row.request_sha256, result=copy.deepcopy(row.result_json), result_sha256=row.result_sha256,
            error_code=row.error_code, actor_ref=row.actor_ref,
            safety=VariantProgressSafety(child_projects_created=int(ready), source_bytes_verified=ready))

    @staticmethod
    def event(families, session, family, receipt, stage, extra):
        before = family.version
        family.version += 1
        family.updated_at = utc_now()
        families._event(session, family, {'claim': 'family.derivation.claimed', 'complete': 'family.derivation.completed',
            'unknown': 'family.derivation.unknown'}[stage], digest({'request_key_sha256': receipt.request_key_sha256, 'stage': stage}),
            receipt.request_sha256, receipt.actor_ref, {'from_version': before, 'to_version': family.version,
                'snapshot_sha256': family.snapshot_sha256, 'receipt_id': receipt.receipt_id,
                'input_sha256': receipt.input_sha256, **extra})

    async def claim(self, workspace, master, family_id, payload, *, actor_ref):
        self.families.actor(actor_ref)
        payload = DeriveStoryboardRequest.model_validate(payload.model_dump())
        body, request_sha, key_sha = request_parts(payload)
        async with self.session_factory() as session, session.begin():
            row, family = await self._load(session, workspace, master, family_id)
            prior = await session.scalar(select(SqlVariantArtifactReceiptORM).where(
                SqlVariantArtifactReceiptORM.family_id == family_id, SqlVariantArtifactReceiptORM.request_key_sha256 == key_sha))
            if prior:
                if prior.kind != 'storyboard_derivation' or prior.request_sha256 != request_sha or prior.actor_ref != actor_ref:
                    raise SqlVariantError('SQL_VARIANT_IDEMPOTENCY_CONFLICT')
                return self.read(prior), None, True
            if row.version != payload.expected_version or row.snapshot_sha256 != payload.expected_snapshot_sha256:
                raise SqlVariantError('SQL_VARIANT_VERSION_CHANGED')
            if row.state not in {'reserved', 'needs_attention', 'review_required'}:
                raise SqlVariantError('SQL_VARIANT_STATE_CHANGED')
            if not family.source_current:
                raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
            member = await session.get(SqlVariantMemberORM, payload.member_id)
            if member is None or member.family_id != family_id or member.workspace_id != workspace or member.state != 'reserved':
                raise SqlVariantError('SQL_VARIANT_MEMBER_CHANGED')
            binding = family.snapshot.binding
            canonical_version = await session.get(TimelineVersionORM, binding.timeline_version_id)
            metadata = canonical_version.snapshot_json.get('metadata', {})
            if (binding.source_mode != 'storyboard_media' or metadata.get('uploaded_audio_bindings_v1')
                    or metadata.get('transcript_revision')
                    or any(clip.get('metadata', {}).get('analysis_id') or clip.get('metadata', {}).get('transcript_id')
                        for track in canonical_version.snapshot_json['tracks'] for clip in track['clips'])):
                raise SqlVariantError('SQL_VARIANT_S3_SOURCE_UNSUPPORTED')
            content = await session.get(ProjectVersionORM, binding.source_content_version_id)
            document = ContentDocument.model_validate(content.snapshot['content'])
            used = {clip['asset_id'] for track in canonical_version.snapshot_json['tracks'] for clip in track['clips'] if clip.get('asset_id')}
            used.update(s.asset_id for s in document.scenes if s.asset_id)
            if not used or len(used) > 5000 or any(s.analysis_id for s in document.scenes):
                raise SqlVariantError('SQL_VARIANT_S3_SOURCE_UNSUPPORTED')
            sources = {}
            for source_id in sorted(used):
                asset = await session.get(AssetORM, source_id)
                proof = next((p for p in binding.assets if p.asset_id == source_id), None)
                if asset is None or proof is None or digest(record_value(asset)) != proof.record_sha256:
                    raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
                if asset.storage_provider != 'local':
                    raise SqlVariantError('SQL_VARIANT_STORAGE_NOT_CONFIGURED')
                target_key(workspace, member.planned_project_id, member.member_id, source_id, asset.content_type)
                sources[source_id] = record_value(asset)
            value = {'schema_version': 'sql-variant-storyboard-input.v1', 'workspace_id': workspace, 'master_project_id': master,
                'family_id': family_id, 'member_id': member.member_id, 'planned_project_id': member.planned_project_id,
                'family_snapshot_sha256': family.snapshot_sha256, 'profile': copy.deepcopy(member.profile_json),
                'request': body, 'source_content': record_value(content), 'source_timeline': copy.deepcopy(canonical_version.snapshot_json),
                'source_assets': sources, 'safety': VariantProgressSafety().model_dump(mode='json')}
            if len(canonical(value)) > 8 * 1024 * 1024:
                raise SqlVariantError('SQL_VARIANT_SOURCE_PROOF_LIMIT')
            claim_id = 'vfc_' + uuid.uuid4().hex
            receipt = SqlVariantArtifactReceiptORM(receipt_id=identity('vfr_', member.member_id + '/storyboard/' + digest(value)),
                family_id=family_id, member_id=member.member_id, workspace_id=workspace, kind='storyboard_derivation',
                state='pending', request_key_sha256=key_sha, request_sha256=request_sha, input_json=value,
                input_sha256=digest(value), actor_ref=actor_ref, claim_id=claim_id, lease_until=utc_now()+timedelta(seconds=self.lease_seconds))
            session.add(receipt)
            member.state, row.state = 'deriving', 'deriving'
            self.event(self.families, session, row, receipt, 'claim', {'claim_id': claim_id})
            await session.flush()
            await self.families._read(session, row)
            return self.read(receipt), {'input': copy.deepcopy(value), 'claim_id': claim_id}, False

    async def guard(self, workspace, master, family_id, receipt_id, claim_id):
        async with self.session_factory() as session, session.begin():
            row, family = await self._load(session, workspace, master, family_id)
            receipt = await session.get(SqlVariantArtifactReceiptORM, receipt_id)
            self._active(row, receipt, claim_id)
            if not family.source_current:
                raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')

    @staticmethod
    def _active(family, receipt, claim_id):
        if (receipt is None or receipt.family_id != family.family_id or receipt.workspace_id != family.workspace_id
                or receipt.state != 'pending' or receipt.claim_id != claim_id or family.state != 'deriving'):
            raise SqlVariantError('SQL_VARIANT_DERIVATION_CONFLICT')
        if receipt.lease_until is None or as_utc(receipt.lease_until) <= utc_now():
            raise SqlVariantError('SQL_VARIANT_DERIVATION_LEASE_EXPIRED')

    async def _completion_fence(self, session, family, receipt, claim_id, expected):
        """Fence after all child inserts, while the durable operation is still pending."""
        await session.flush()
        # Conditional writes are SQL CAS, not a stale Python object decision.
        family_cas = await session.execute(update(SqlVariantFamilyORM).where(
            SqlVariantFamilyORM.family_id == family.family_id,
            SqlVariantFamilyORM.workspace_id == family.workspace_id,
            SqlVariantFamilyORM.master_project_id == family.master_project_id,
            SqlVariantFamilyORM.version == expected['version'],
            SqlVariantFamilyORM.state == 'deriving',
            SqlVariantFamilyORM.snapshot_sha256 == expected['snapshot_sha256'])
            .values(updated_at=SqlVariantFamilyORM.updated_at).execution_options(synchronize_session=False))
        receipt_cas = await session.execute(update(SqlVariantArtifactReceiptORM).where(
            SqlVariantArtifactReceiptORM.receipt_id == receipt.receipt_id,
            SqlVariantArtifactReceiptORM.family_id == family.family_id,
            SqlVariantArtifactReceiptORM.workspace_id == family.workspace_id,
            SqlVariantArtifactReceiptORM.kind == 'storyboard_derivation',
            SqlVariantArtifactReceiptORM.state == 'pending',
            SqlVariantArtifactReceiptORM.claim_id == claim_id,
            SqlVariantArtifactReceiptORM.lease_until == expected['lease_until'],
            SqlVariantArtifactReceiptORM.lease_until > utc_now(),
            SqlVariantArtifactReceiptORM.input_sha256 == expected['input_sha256'],
            SqlVariantArtifactReceiptORM.request_sha256 == expected['request_sha256'],
            SqlVariantArtifactReceiptORM.actor_ref == expected['actor_ref'])
            .values(updated_at=SqlVariantArtifactReceiptORM.updated_at).execution_options(synchronize_session=False))
        await session.refresh(family)
        await session.refresh(receipt)
        self._active(family, receipt, claim_id)
        if family_cas.rowcount != 1 or receipt_cas.rowcount != 1:
            raise SqlVariantError('SQL_VARIANT_DERIVATION_CONFLICT')
        current = await self.families._read(session, family)
        if not current.source_current:
            raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
        self._assert_pending_fence(family, receipt, claim_id, expected)

    def _assert_pending_fence(self, family, receipt, claim_id, expected):
        self._active(family, receipt, claim_id)
        if (family.version != expected['version'] or family.snapshot_sha256 != expected['snapshot_sha256']
                or receipt.input_sha256 != expected['input_sha256'] or receipt.request_sha256 != expected['request_sha256']
                or receipt.actor_ref != expected['actor_ref'] or as_utc(receipt.lease_until) != as_utc(expected['lease_until'])):
            raise SqlVariantError('SQL_VARIANT_DERIVATION_CONFLICT')

    @staticmethod
    def _assert_closed_fence(family, receipt, expected, result_sha256):
        # Every final flush and history validation is awaited before this last
        # pre-commit check. An expired claim rolls back children AND ready events.
        if as_utc(expected['lease_until']) <= utc_now():
            raise SqlVariantError('SQL_VARIANT_DERIVATION_LEASE_EXPIRED')
        if (family.state != 'needs_attention' or family.version != expected['version'] + 1
                or family.snapshot_sha256 != expected['snapshot_sha256'] or receipt.state != 'ready'
                or receipt.claim_id is not None or receipt.lease_until is not None
                or receipt.input_sha256 != expected['input_sha256'] or receipt.request_sha256 != expected['request_sha256']
                or receipt.actor_ref != expected['actor_ref'] or receipt.result_sha256 != result_sha256):
            raise SqlVariantError('SQL_VARIANT_DERIVATION_CONFLICT')

    async def complete(self, workspace, master, family_id, receipt_id, claim_id, copies, *, verify):
        try:
            async with self.session_factory() as session, session.begin():
                family, current = await self._load(session, workspace, master, family_id)
                receipt = await session.get(SqlVariantArtifactReceiptORM, receipt_id)
                self._active(family, receipt, claim_id)
                expected = {'version': family.version, 'snapshot_sha256': family.snapshot_sha256,
                    'input_sha256': receipt.input_sha256, 'request_sha256': receipt.request_sha256,
                    'actor_ref': receipt.actor_ref, 'lease_until': receipt.lease_until}
                if not current.source_current:
                    raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
                # Only bounded local checksum verification, never byte copy/network under SQL lock.
                await verify(copies)
                self._active(family, receipt, claim_id)
                value = receipt.input_json
                result = make_result(value, copies)
                ids, content, snapshot = derive_storyboard(value, copies)
                master_row = await session.get(VideoProjectORM, master)
                child = VideoProjectORM(project_id=value['planned_project_id'], workspace_id=workspace,
                    slug='variant-' + value['member_id'][4:], name=(master_row.name[:180] + ' · ' + value['profile']['target']),
                    niche=master_row.niche, status='draft', current_version_id=ids['content_version_id'],
                    provenance={'source_type': 'storyboard_variant_derivative', 'family_id': family_id,
                        'member_id': receipt.member_id, 'master_project_id': master, 'receipt_id': receipt_id,
                        'input_sha256': receipt.input_sha256, 'approval_inherited': False, 'publishing_enabled': False})
                session.add(child)
                await session.flush()
                version = ProjectVersionORM(project_version_id=ids['content_version_id'], workspace_id=workspace,
                    project_id=child.project_id, ordinal=1, label='mvp1-content', snapshot={'content': content},
                    provenance={'content_sha256': digest(content), 'original_text_sha256': hashlib.sha256(content['original_text'].encode()).hexdigest(),
                        'actor_ref': receipt.actor_ref, 'source_type': 'storyboard_variant_derivative', 'external_call': False,
                        'parent_project_id': master, 'parent_content_version_id': value['source_content']['project_version_id'],
                        'parent_record_sha256': digest(value['source_content']), 'derivation_receipt_id': receipt_id,
                        'approved': False, 'supplied_facts_verified': False})
                session.add(version)
                await session.flush()
                for old, new in ids['assets'].items():
                    source, copied = value['source_assets'][old], copies[old]
                    session.add(AssetORM(asset_id=new, workspace_id=workspace, project_id=child.project_id,
                        project_version_id=version.project_version_id, asset_class=source['asset_class'], kind=source['kind'],
                        filename=asset_filename(old, source['content_type']), object_key=copied['object_key'],
                        content_type=copied['content_type'], size_bytes=copied['size_bytes'], checksum_sha256=copied['sha256'],
                        storage_provider=copied['storage_provider'], provenance={'source_type': 'verified_storyboard_derivative',
                            'rights_status': 'unknown', 'license': None, 'production_eligible': source['provenance'].get('production_eligible') is not False,
                            'derivation_receipt_id': receipt_id, 'parent_project_id': master, 'parent_asset_id': old,
                            'parent_record_sha256': digest(source), 'source_bytes_verified': True,
                            'source_rights_evidence_sha256': digest(source['provenance']), 'external_call': False,
                            'new_inference_calls': 0, 'approval_inherited': False, 'rights_override_inherited': False,
                            'media_metadata': {'width': copied['dimensions'][0] if copied['dimensions'] else None,
                                'height': copied['dimensions'][1] if copied['dimensions'] else None}}))
                timeline = TimelineORM(timeline_id=ids['timeline_id'], workspace_id=workspace, project_id=child.project_id,
                    project_version_id=version.project_version_id, source_content_version_id=version.project_version_id,
                    current_version_id=ids['timeline_version_id'], current_version=1, approval_status='draft')
                session.add(timeline)
                await session.flush()
                session.add(TimelineVersionORM(timeline_version_id=ids['timeline_version_id'], timeline_id=timeline.timeline_id,
                    project_id=child.project_id, version=1, snapshot_json=snapshot,
                    mutation_json={'type': 'storyboard_variant_derivative', 'receipt_id': receipt_id,
                        'source_timeline_sha256': digest(value['source_timeline']), 'input_sha256': receipt.input_sha256}, actor_ref=receipt.actor_ref))
                member = await session.get(SqlVariantMemberORM, receipt.member_id)
                await self._completion_fence(session, family, receipt, claim_id, expected)
                # No await between the pending fence and terminal assignments.
                receipt.state, receipt.result_json, receipt.result_sha256 = 'ready', copy.deepcopy(result), digest(result)
                receipt.claim_id = receipt.lease_until = None
                receipt.updated_at = utc_now()
                member.child_project_id, member.initial_timeline_version_id, member.state = child.project_id, ids['timeline_version_id'], 'needs_attention'
                family.state = 'needs_attention'
                self.event(self.families, session, family, receipt, 'complete', {'result_sha256': receipt.result_sha256, 'child_project_id': child.project_id})
                await session.flush()
                final_current = await self.families._read(session, family)
                # The first verification precedes several awaited SQL flushes.
                # Verify the actual owned copies AND original bytes again after
                # the final flush/history read, while the canonical writer lock
                # is held. No new copy, provider dispatch or retry is admitted.
                await verify(copies)
                if not final_current.source_current:
                    raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
                self._assert_closed_fence(family, receipt, expected, digest(result))
                return self.read(receipt)
        except IntegrityError:
            raise SqlVariantError('SQL_VARIANT_DERIVATION_CONFLICT') from None

    async def unknown(self, workspace, master, family_id, receipt_id, claim_id, code):
        code = code if code in UNKNOWN_CODES else 'SQL_VARIANT_DERIVATION_FAILED'
        async with self.session_factory() as session, session.begin():
            family, _ = await self._load(session, workspace, master, family_id)
            receipt = await session.get(SqlVariantArtifactReceiptORM, receipt_id)
            # A cancelled/terminal operation never admits late bytes or overwrites its history.
            if receipt is None or receipt.family_id != family_id or receipt.state != 'pending' or receipt.claim_id != claim_id:
                return
            receipt.state, receipt.error_code = 'unknown', code
            receipt.claim_id = receipt.lease_until = None
            receipt.updated_at = utc_now()
            member = await session.get(SqlVariantMemberORM, receipt.member_id)
            member.state, family.state = 'failed', 'recovery_required'
            self.event(self.families, session, family, receipt, 'unknown', {'error_code': code})
            await session.flush()
            await self.families._read(session, family)

    async def get(self, workspace, master, family_id, receipt_id):
        async with self.session_factory() as session:
            family = await self.families.get(workspace, master, family_id)
            if family is None:
                return None
            receipt = await session.scalar(select(SqlVariantArtifactReceiptORM).where(
                SqlVariantArtifactReceiptORM.receipt_id == receipt_id, SqlVariantArtifactReceiptORM.family_id == family_id,
                SqlVariantArtifactReceiptORM.workspace_id == workspace, SqlVariantArtifactReceiptORM.kind == 'storyboard_derivation'))
            return self.read(receipt) if receipt else None


def asset_filename(source_id, mime):
    return source_id + '.' + {'image/png':'png', 'image/jpeg':'jpg', 'image/webp':'webp',
        'audio/wav':'wav', 'audio/x-wav':'wav', 'audio/mpeg':'mp3', 'audio/ogg':'ogg'}[mime]
