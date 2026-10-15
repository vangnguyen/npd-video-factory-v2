"""Private SQL snapshots for reviewed reuse of registered supporting media.

This module does not create jobs, touch queues or read an object.  A context
binds stored values rather than trusting extensions or a client-supplied graph.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select, text

from .auto_edit_db import AutoEditAnalysisORM
from .auto_edit_repository import _asset_read
from .broll_timeline_review_command import _positive_number
from .db import AssetORM, VideoProjectORM
from .frozen_storage_read import asset_custody, FrozenReadRejected, FrozenStorageRead, MAX_SOURCE_BYTES
from .media_intelligence_db import MediaPlanORM, MediaPlanItemORM, MediaResolutionJobORM
from .media_intelligence_models import MediaPlanRequest
from .service_api_repository import ServiceOperationORM, digest
from .source_linked_edit_command import current, _source, SourceLinkedConflict
from .timeline_db import TimelineORM
from .timeline_models import TimelineSnapshot

NAMESPACE = 'human:broll-internal-resolution.v1'
ACTION = 'broll.internal.resolve.v1'
CLAIM_NAMESPACE = 'worker:broll-internal-resolution.v1'
CLAIM_ACTION = 'broll.internal.claim.v1'
MARKER = 'reviewed_internal_resolution_v1'
ACTIVE = {'queued', 'running', 'needs_approval'}


class InternalResolutionConflict(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise InternalResolutionConflict(code)


async def begin(session, write=False):
    if session.get_bind().dialect.name == 'sqlite':
        await session.execute(text('BEGIN IMMEDIATE' if write else 'BEGIN'))


def row_value(row):
    def value(v):
        return v.isoformat() if isinstance(v, (datetime, date)) else str(v) if isinstance(v, Decimal) else v
    return {c.key: value(getattr(row, c.key)) for c in row.__table__.columns}


def operation_key(authority, project_id, request_key):
    return digest({'authority': authority, 'project_id': project_id, 'request_key': request_key})


def has_marker(job):
    provenance = getattr(job, 'provenance_json', getattr(job, 'provenance', {}))
    return isinstance(provenance, dict) and MARKER in provenance


def usable_asset(asset, primary_id):
    require(asset.asset_id != primary_id and asset.asset_class not in {'render', 'metadata'}
            and asset.kind not in {'logo', 'thumbnail', 'subtitle'}, 'BROLL_INTERNAL_VISUAL_ASSET_REQUIRED')
    require(asset.content_type in {'image/png', 'image/jpeg', 'image/webp'}
            or asset.content_type.startswith('video/'), 'BROLL_INTERNAL_VISUAL_ASSET_REQUIRED')
    require(asset.provenance.get('rights_status', 'unknown') != 'restricted', 'BROLL_INTERNAL_RIGHTS_RESTRICTED')
    measured = asset.provenance.get('media_metadata')
    require(isinstance(measured, dict)
            and all(type(measured.get(k)) is int and 0 < measured[k] <= 1_000_000 for k in ('width', 'height')),
            'BROLL_INTERNAL_MEASURED_MEDIA_REQUIRED')
    require(not asset.content_type.startswith('video/') or _positive_number(measured.get('duration_seconds')),
            'BROLL_INTERNAL_MEASURED_MEDIA_REQUIRED')
    # Also rejects non-finite or malformed provenance before a context is hashed.
    asset_custody(asset)
    FrozenStorageRead(asset.object_key, asset.workspace_id, asset.project_id, asset.size_bytes,
        asset.checksum_sha256, asset.storage_provider, MAX_SOURCE_BYTES)


async def context(session, project_id, plan_id, item_id, authority, *, lock=False, original_item=None):
    """Read all inputs in the same transaction; only own status is normalizable."""
    query = select(VideoProjectORM).where(VideoProjectORM.project_id == project_id)
    project = await session.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    if project is None:
        raise KeyError(project_id)
    first = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id))
    if first is None or not first.source_analysis_id:
        raise InternalResolutionConflict('BROLL_INTERNAL_UPLOADED_TIMELINE_REQUIRED')
    query = select(AutoEditAnalysisORM).where(AutoEditAnalysisORM.analysis_id == first.source_analysis_id)
    analysis = await session.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    require(analysis is not None, 'BROLL_INTERNAL_SOURCE_REQUIRED')
    # current() is also used by older flows and can reuse an existing ORM
    # identity. Refresh here after taking the analysis lock before using it.
    query = select(TimelineORM).where(TimelineORM.project_id == project_id)
    await session.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    row, version = await current(session, project_id, lock=lock)
    require(row.source_analysis_id == analysis.analysis_id and row.workspace_id == project.workspace_id,
            'BROLL_INTERNAL_SOURCE_CHANGED')
    snapshot = TimelineSnapshot.model_validate(version.snapshot_json)
    query = select(MediaPlanORM).where(MediaPlanORM.media_plan_id == plan_id,
        MediaPlanORM.project_id == project_id, MediaPlanORM.workspace_id == project.workspace_id)
    plan = await session.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    if plan is None:
        raise KeyError(plan_id)
    config = MediaPlanRequest.model_validate({'selection_policy': 'scene_variety', **plan.configuration_json})
    require(plan.status == 'draft' and config.purpose == 'supporting_broll'
            and plan.analysis_id == analysis.analysis_id and config.analysis_id == analysis.analysis_id,
            'BROLL_INTERNAL_PLAN_SOURCE_CHANGED')
    query = select(MediaPlanItemORM).where(MediaPlanItemORM.media_plan_item_id == item_id,
        MediaPlanItemORM.media_plan_id == plan_id)
    item = await session.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    if item is None:
        raise KeyError(item_id)
    candidates = item.provenance_json.get('supporting_candidates')
    require(isinstance(candidates, list) and 0 < len(candidates) <= 200
            and all(isinstance(v, dict) and isinstance(v.get('asset_id'), str) for v in candidates),
            'BROLL_INTERNAL_SAVED_CANDIDATES_REQUIRED')
    candidate_ids = [v['asset_id'] for v in candidates]
    require(len(set(candidate_ids)) == len(candidate_ids), 'BROLL_INTERNAL_CANDIDATES_INVALID')
    query = select(AssetORM).where(AssetORM.asset_id.in_(sorted({analysis.asset_id, *candidate_ids}))).order_by(AssetORM.asset_id)
    assets = (await session.scalars((query.with_for_update() if lock else query).execution_options(populate_existing=True))).all()
    require(all(a.project_id == project_id and a.workspace_id == project.workspace_id for a in assets),
            'BROLL_INTERNAL_ASSET_SCOPE_CHANGED')
    assets = {a.asset_id: _asset_read(a) for a in assets}
    require(set(assets) == {analysis.asset_id, *candidate_ids}, 'BROLL_INTERNAL_ASSET_MISSING')
    source, _ = await _source(session, row, analysis, snapshot)
    require(plan.provenance_json.get('source_asset_sha256') == source['source_sha256']
            and plan.provenance_json.get('transcript_id') == source['transcript_id']
            and plan.provenance_json.get('source_analysis_id', analysis.analysis_id) == analysis.analysis_id
            and (config.transcript_id is None or config.transcript_id == source['transcript_id']),
            'BROLL_INTERNAL_PLAN_SOURCE_CHANGED')
    choices = []
    for candidate in candidates:
        asset = assets[candidate['asset_id']]
        # An unavailable candidate is visible as unavailable, never silently
        # repaired or treated as a different saved selection.
        valid, code = True, None
        try:
            usable_asset(asset, analysis.asset_id)
            require(candidate.get('checksum_sha256') == asset.checksum_sha256,
                    'BROLL_INTERNAL_CANDIDATE_CHANGED')
        except (InternalResolutionConflict, FrozenReadRejected) as exc:
            valid, code = False, getattr(exc, 'code', 'BROLL_INTERNAL_ASSET_INVALID')
        choices.append({'candidate': candidate, 'asset_id': asset.asset_id,
            'asset_custody': asset_custody(asset), 'available': valid, 'unavailable_code': code})
    item_input = row_value(item)
    if original_item is not None:
        # Caller must separately prove the owned pending/terminal phase before
        # it can normalize the fields this job is allowed to change.
        for field in ('status', 'updated_at', 'selected_media_asset_id', 'needs_attention'):
            item_input[field] = original_item[field]
    value = {'schema_version': 'broll-internal-resolution-context.v1',
        'workspace_id': project.workspace_id, 'project_id': project_id,
        'actor_ref': authority['subject'], 'authority_sha256': digest(authority),
        'timeline_id': row.timeline_id, 'timeline_version': row.current_version,
        'timeline_version_id': row.current_version_id, 'timeline_sha256': digest(version.snapshot_json),
        'source': source, 'source_asset_custody': asset_custody(assets[analysis.asset_id]),
        'project': {'version': project.version, 'current_version_id': project.current_version_id,
            'niche': project.niche, 'name': project.name, 'provenance': project.provenance},
        'plan': row_value(plan), 'item': item_input, 'candidates': choices,
        'provider_calls': 0, 'publishing_enabled': False, 'owner_approval_inferred': False}
    wire = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return {**value, 'context_json': wire, 'context_sha256': digest(value)}, item, assets


async def admission(session, operation_id):
    op = await session.get(ServiceOperationORM, operation_id)
    require(op is not None and op.service_id == NAMESPACE and op.action == ACTION
            and op.status == 'succeeded' and isinstance(op.response_json, dict)
            and op.response_sha256 == digest(op.response_json), 'BROLL_INTERNAL_RECEIPT_INVALID')
    value = op.response_json
    require(value.get('receipt', {}).get('operation_id') == op.operation_id
            and value['receipt'].get('request_sha256') == op.request_sha256
            and value['receipt'].get('workspace_id') == op.workspace_id
            and value['receipt'].get('project_id') == op.project_id
            and value['receipt'].get('actor_ref') == op.actor_ref,
            'BROLL_INTERNAL_RECEIPT_INVALID')
    return op, value


async def marked_admission(session, job):
    marker = job.provenance_json.get(MARKER)
    require(isinstance(marker, dict) and set(marker) == {'operation_id', 'binding_sha256'},
            'BROLL_INTERNAL_JOB_BINDING_INVALID')
    op, value = await admission(session, marker['operation_id'])
    static = value['private']['job']
    require(all(getattr(job, k) == v for k, v in static.items())
            and marker['binding_sha256'] == value['receipt']['context_sha256']
            and job.provider_key == 'internal-media' and job.capability == 'internal_media'
            and job.operation == 'reuse-user-asset' and job.external_call is False and job.paid is False,
            'BROLL_INTERNAL_JOB_BINDING_INVALID')
    return op, value


async def deny_active_reviewed(session, item_id):
    jobs = (await session.scalars(select(MediaResolutionJobORM).where(
        MediaResolutionJobORM.media_plan_item_id == item_id, MediaResolutionJobORM.status.in_(ACTIVE)))).all()
    for job in jobs:
        if has_marker(job):
            await marked_admission(session, job)
            raise InternalResolutionConflict('BROLL_INTERNAL_REVIEWED_ITEM_OWNED')
