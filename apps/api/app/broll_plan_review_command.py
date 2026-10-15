"""Schema-zero human receipts. UNKNOWN is observable and never redispatched.

Preparation may persist a stock schedule, but cannot search/download/generate.
Existing stock review and canonical B-roll apply remain separate commands.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select, text

from .auto_edit_db import AutoEditAnalysisORM
from .db import AssetORM, VideoProjectORM, WorkspaceORM, utc_now
from .media_intelligence_models import MediaPlanRequest
from .service_api_repository import ServiceOperationORM, digest
from .source_linked_edit_command import current, _source, SourceLinkedConflict
from .timeline_models import TimelineSnapshot
from .learning_service import LearningError


NAMESPACE = 'human:broll-plan-review.v1'
ACTION = 'broll.plan.prepare.v1'


class BrollPlanConflict(RuntimeError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


async def _begin(session, *, write=False):
    if session.get_bind().dialect.name == 'sqlite':
        await session.execute(text('BEGIN IMMEDIATE' if write else 'BEGIN'))


def _identity(authority, key, project_id):
    # A different credential, actor or request cannot take custody of a receipt.
    return digest({'authority': authority, 'project_id': project_id, 'request_key': key})


def _preparation_ready(plan):
    if not isinstance(plan, dict):
        return False
    if plan.get('status') == 'draft':
        return isinstance(plan.get('items'), list) and bool(plan['items'])
    stock = plan.get('stock_planning')
    return plan.get('status') == 'stock_waiting' and isinstance(stock, dict) and stock.get('status') == 'waiting' \
        and type(stock.get('total_searches')) is int and stock['total_searches'] > 0


async def _context(service, session, project_id, authority, *, lock=False):
    project = await session.scalar(select(VideoProjectORM).where(VideoProjectORM.project_id == project_id)
        .with_for_update() if lock else select(VideoProjectORM).where(VideoProjectORM.project_id == project_id))
    if project is None:
        raise KeyError(project_id)
    try:
        row, version = await current(session, project_id, lock=lock)
    except SourceLinkedConflict:
        raise BrollPlanConflict('BROLL_CANONICAL_BINDING_INVALID') from None
    analysis = await session.get(AutoEditAnalysisORM, row.source_analysis_id) if row.source_analysis_id else None
    if analysis is None:
        raise BrollPlanConflict('BROLL_UPLOADED_TIMELINE_REQUIRED')
    try:
        source, _ = await _source(session, row, analysis, TimelineSnapshot.model_validate(version.snapshot_json))
    except (SourceLinkedConflict, ValueError):
        raise BrollPlanConflict('BROLL_SOURCE_BINDING_INVALID') from None
    assets = (await session.scalars(select(AssetORM).where(AssetORM.project_id == project_id,
        AssetORM.workspace_id == project.workspace_id).order_by(AssetORM.asset_id))).all()
    supporting = [{'asset_id': a.asset_id, 'sha256': a.checksum_sha256, 'size_bytes': a.size_bytes,
        'version': a.version, 'filename': a.filename, 'content_type': a.content_type,
        'asset_class': a.asset_class, 'kind': a.kind, 'provenance': a.provenance,
        'storage_provider': a.storage_provider, 'object_key': a.object_key} for a in assets]
    providers = service._provider_status()
    stock = providers['stock']
    managed = service._managed_stock()
    stock_binding = service._stock_identity() if managed else None
    workspace = await session.get(WorkspaceORM, project.workspace_id)
    roles = [authority.get('platform_role'), authority['workspace_roles'].get('*'),
        authority['workspace_roles'].get(project.workspace_id),
        authority['workspace_roles'].get('slug:' + workspace.slug) if workspace else None]
    editable = any(role in {'editor', 'reviewer', 'owner'} for role in roles)
    safe_source = {k: v for k, v in source.items() if k != 'object_key'}
    value = {'schema_version': 'broll-plan-review-context.v1', 'workspace_id': project.workspace_id,
        'project_id': project_id, 'actor_ref': authority['subject'], 'authority_sha256': digest(authority),
        'can_prepare': editable, 'timeline_id': row.timeline_id, 'timeline_version': row.current_version,
        'timeline_version_id': row.current_version_id, 'timeline_sha256': digest(version.snapshot_json),
        'source': safe_source, 'supporting_assets_sha256': digest(supporting),
        'project_sha256': digest({'version': project.version, 'current_version_id': project.current_version_id,
            'niche': project.niche, 'name': project.name, 'provenance': project.provenance}),
        'platform': TimelineSnapshot.model_validate(version.snapshot_json).metadata.get('platform', 'facebook_reels'),
        'providers': providers, 'stock_binding': stock_binding,
        'licensed_stock_enabled': managed and stock['status'] == 'healthy' and stock['paid'] is False,
        'ai_planning_enabled': False, 'ai_disabled_reason': 'APPROVED_GENERATIVE_PLANNING_NOT_IN_THIS_INCREMENT',
        'max_ai_cost_vnd': '0', 'preparation_provider_calls': 0, 'publishing_enabled': False,
        'owner_approval_inferred': False}
    # Preserve the exact JSON number representation across Python/browser
    # clocks (16.0 versus 16). Browsers hash these literal bytes and compare
    # the parsed value with the separately typed public fields.
    wire = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return {**value, 'context_json': wire, 'context_sha256': hashlib.sha256(wire.encode()).hexdigest()}


async def read_context(service, project_id, authority):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await _begin(session)
            return await _context(service, session, project_id, authority)


def _public(row, *, replayed):
    value = row.response_json
    if (row.service_id != NAMESPACE or row.action != ACTION
            or not isinstance(value, dict) or not isinstance(value.get('receipt'), dict)
            or value['receipt'].get('request_sha256') != row.request_sha256
            or value['receipt'].get('operation_id') != row.operation_id
            or value['receipt'].get('actor_ref') != row.actor_ref
            or value['receipt'].get('project_id') != row.project_id
            or value['receipt'].get('workspace_id') != row.workspace_id):
        raise BrollPlanConflict('BROLL_RECEIPT_INVALID')
    if row.status == 'succeeded':
        if row.response_sha256 != digest(value) or value.get('state') != 'prepared' or not _preparation_ready(value.get('plan')):
            raise BrollPlanConflict('BROLL_RECEIPT_INVALID')
        return {**value, 'replayed': replayed}
    if row.status == 'rejected':
        if row.response_sha256 != digest(value) or value.get('state') != 'rejected':
            raise BrollPlanConflict('BROLL_RECEIPT_INVALID')
        return {**value, 'replayed': replayed}
    if row.status not in {'running', 'uncertain'}:
        raise BrollPlanConflict('BROLL_RECEIPT_INVALID')
    return {'schema_version': 'broll-plan-review-result.v1', 'state': 'unknown',
        'receipt': value['receipt'], 'plan': None, 'replayed': replayed,
        'preparation_provider_calls': 0, 'publishing_enabled': False, 'owner_approval_inferred': False}


async def _find(session, project_id, authority, key, *, lock=False):
    query = select(ServiceOperationORM).join(VideoProjectORM,
        ServiceOperationORM.project_id == VideoProjectORM.project_id).where(ServiceOperationORM.service_id == NAMESPACE,
        ServiceOperationORM.project_id == project_id,
        ServiceOperationORM.workspace_id == VideoProjectORM.workspace_id,
        ServiceOperationORM.key_sha256 == _identity(authority, key, project_id))
    return await session.scalar(query.with_for_update() if lock else query)


async def read_request(service, project_id, authority, key):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await _begin(session)
            row = await _find(session, project_id, authority, key)
            if row is None:
                raise KeyError(key)
            return _public(row, replayed=True)


async def prepare_plan(service, project_id, authority, payload):
    request = payload.model_dump(mode='json')
    fingerprint = digest({'project_id': project_id, 'authority': authority, 'request': request})
    factory = service.repository.session_factory
    async with factory() as session:
        async with session.begin():
            await _begin(session, write=True)
            # Project lock serializes receipts without changing project metadata.
            project = await session.get(VideoProjectORM, project_id, with_for_update=True)
            if project is None:
                raise KeyError(project_id)
            prior = await _find(session, project_id, authority, payload.request_key, lock=True)
            if prior:
                if prior.request_sha256 != fingerprint:
                    raise BrollPlanConflict('BROLL_IDEMPOTENCY_CONFLICT')
                return _public(prior, replayed=True)
            context = await _context(service, session, project_id, authority, lock=True)
            if context['context_sha256'] != payload.context_sha256 or not context['can_prepare']:
                raise BrollPlanConflict('BROLL_REVIEW_CONTEXT_CHANGED')
            if payload.settings.allow_stock and not context['licensed_stock_enabled']:
                raise BrollPlanConflict('BROLL_STOCK_NOT_AVAILABLE')
            feedback = None
            if payload.learning_snapshot_id:
                if service.learning is None:
                    raise BrollPlanConflict('LEARNING_SERVICE_NOT_CONFIGURED', 503)
                try:
                    feedback = await service.learning.feedback(project.workspace_id,
                        payload.learning_snapshot_id, niche=project.niche)
                except LearningError as exc:
                    raise BrollPlanConflict(exc.code, 404 if exc.code.endswith('_NOT_FOUND') else 409) from None
            stamp = utc_now()
            operation_id = 'sop_' + uuid.uuid4().hex
            receipt = {'schema_version': 'broll-plan-review-receipt.v1', 'operation_id': operation_id,
                'workspace_id': context['workspace_id'], 'project_id': project_id,
                'actor_ref': authority['subject'], 'authority_sha256': context['authority_sha256'],
                'request_key': payload.request_key, 'request_sha256': fingerprint,
                'context_sha256': payload.context_sha256, 'settings': request['settings'],
                'learning_snapshot_id': payload.learning_snapshot_id,
                'learning_feedback_sha256': digest(feedback) if feedback is not None else None,
                'source': context['source'], 'timeline_id': context['timeline_id'],
                'timeline_version': context['timeline_version'], 'timeline_version_id': context['timeline_version_id']}
            row = ServiceOperationORM(operation_id=operation_id, workspace_id=project.workspace_id,
                service_id=NAMESPACE, action=ACTION, project_id=project_id, actor_ref=authority['subject'],
                key_sha256=_identity(authority, payload.request_key, project_id), request_sha256=fingerprint,
                status='running', response_json={'receipt': receipt}, created_at=stamp, updated_at=stamp)
            session.add(row)
    # The one attempt has durable custody before any planning await. A crash or
    # uncertain SQL outcome is read-only UNKNOWN, never another execution.
    configuration = MediaPlanRequest(purpose='supporting_broll', analysis_id=context['source']['analysis_id'],
        learning_snapshot_id=payload.learning_snapshot_id,
        transcript_id=context['source']['transcript_id'], platform=context['platform'],
        allow_stock=payload.settings.allow_stock, allow_ai_image=False, allow_ai_video=False,
        max_ai_cost_vnd='0', resolver_priority=payload.settings.resolver_priority)
    try:
        plan = await service.create(project_id=project_id, payload=configuration, defer_stock_execution=True)
        if not _preparation_ready(plan.model_dump(mode='json')):
            raise BrollPlanConflict('BROLL_PLAN_NOT_PREPARATION_READY')
        if (plan.project_id != project_id or plan.workspace_id != context['workspace_id']
                or plan.configuration != configuration
                or plan.provenance.get('source_asset_sha256') != context['source']['source_sha256']
                or plan.provenance.get('transcript_id') != context['source']['transcript_id']):
            raise BrollPlanConflict('BROLL_PREPARED_PLAN_BINDING_CHANGED')
        if feedback is not None and digest(plan.provenance.get('learning_feedback')) != digest(feedback):
            raise BrollPlanConflict('BROLL_LEARNING_SNAPSHOT_CHANGED')
        async with factory() as session:
            async with session.begin():
                await _begin(session, write=True)
                latest = await _context(service, session, project_id, authority, lock=True)
                row = await session.get(ServiceOperationORM, operation_id, with_for_update=True)
                if row is None or row.status != 'running' or row.request_sha256 != fingerprint:
                    raise BrollPlanConflict('BROLL_RECEIPT_CHANGED')
                changed = latest['context_sha256'] != payload.context_sha256
                if feedback is not None:
                    project = await session.get(VideoProjectORM, project_id)
                    current_feedback = await service.learning.feedback(project.workspace_id,
                        payload.learning_snapshot_id, niche=project.niche)
                    changed = changed or digest(current_feedback) != digest(feedback)
                result = {'schema_version': 'broll-plan-review-result.v1', 'state': 'rejected' if changed else 'prepared',
                    'receipt': receipt, 'plan': None if changed else plan.model_dump(mode='json'),
                    'error_code': 'BROLL_REVIEW_CONTEXT_CHANGED' if changed else None,
                    'preparation_provider_calls': 0, 'publishing_enabled': False, 'owner_approval_inferred': False}
                row.status = 'rejected' if changed else 'succeeded'
                row.response_status = 409 if changed else 201
                row.response_json, row.response_sha256, row.updated_at = result, digest(result), utc_now()
                return {**result, 'replayed': False}
    except Exception:
        # Do not fabricate a successful receipt or redispatch after a partial
        # plan/commit. A later GET exposes the same request as UNKNOWN.
        raise BrollPlanConflict('BROLL_PREPARATION_OUTCOME_UNKNOWN', 503) from None
