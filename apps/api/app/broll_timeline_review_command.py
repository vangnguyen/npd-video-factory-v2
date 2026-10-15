"""Schema-zero, provider-free B-roll placement with one SQL receipt transaction.

Plan, selected provenance, full asset custody and source speech are read inside
the same transaction as canonical history and preview/approval invalidation.
The existing unreviewed endpoint remains compatible; Studio migration follows.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import math
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError

from .auto_edit_db import AutoEditAnalysisORM
from .auto_edit_repository import _asset_read
from .broll_planner import place_broll
from .broll_timeline_review_api import BrollTimelineReceipt
from .db import AssetORM, VideoProjectORM
from .frozen_storage_read import asset_custody, FrozenReadRejected
from .media_intelligence_db import MediaPlanORM, MediaPlanItemORM, MediaAssetProvenanceORM
from .media_intelligence_models import MediaPlanRequest
from .media_intelligence_repository import _item_read, _media_asset_read
from .source_linked_edit_command import current, _source, digest, SourceLinkedConflict
from .timeline_db import TimelineORM, TimelineVersionORM
from .timeline_logic import TimelineEditError
from .timeline_models import TimelineSnapshot
from .timeline_repository import TimelineConflictError


KIND = 'broll-timeline-review'


class BrollTimelineConflict(RuntimeError):
    def __init__(self, code, current_version=None):
        self.code, self.current_version = code, current_version
        super().__init__(code)


def _value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _row_value(row):
    # Only server-defined SQL columns, never ORM state or a client graph.
    return {column.key: _value(getattr(row, column.key)) for column in row.__table__.columns}


def _positive_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _receipt(version):
    mutation = version.mutation_json
    if mutation.get('type') != KIND:
        return None
    try:
        saved = BrollTimelineReceipt.model_validate(mutation['receipt']).model_dump(mode='json')
        if (saved['timeline_id'] != version.timeline_id or saved['project_id'] != version.project_id
                or saved['result_version'] != version.version or saved['actor_ref'] != version.actor_ref
                or saved['result_snapshot_sha256'] != digest(version.snapshot_json)
                or mutation.get('source_media_mutated') is not False or mutation.get('publish_requested') is not False):
            raise ValueError('receipt does not describe its saved timeline')
        return saved
    except (KeyError, ValidationError, ValueError):
        raise BrollTimelineConflict('BROLL_TIMELINE_RECEIPT_INVALID') from None


async def _begin(session, write=False):
    if session.get_bind().dialect.name == 'sqlite':
        await session.execute(text('BEGIN IMMEDIATE' if write else 'BEGIN'))


async def _locked_current(session, project_id, lock):
    if lock:
        # Preparation/recovery also acquire project before canonical timeline.
        # Keep the same order and freeze the project identity for this write.
        project = await session.scalar(select(VideoProjectORM).where(VideoProjectORM.project_id == project_id)
            .with_for_update().execution_options(populate_existing=True))
        if project is None:
            raise KeyError(project_id)
    first = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id))
    if first is None:
        raise KeyError(project_id)
    query = select(AutoEditAnalysisORM).where(AutoEditAnalysisORM.analysis_id == first.source_analysis_id)
    analysis = await session.scalar(query.with_for_update() if lock else query)
    if analysis is None:
        raise BrollTimelineConflict('BROLL_SOURCE_ANALYSIS_REQUIRED')
    query = select(TimelineORM).where(TimelineORM.project_id == project_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query.execution_options(populate_existing=True))
    if row is None or row.source_analysis_id != analysis.analysis_id:
        raise BrollTimelineConflict('BROLL_SOURCE_ANALYSIS_CHANGED')
    row, version = await current(session, project_id)
    return row, version, analysis


async def _media(session, row, version, analysis, media_plan_id, lock):
    snapshot = TimelineSnapshot.model_validate(version.snapshot_json)
    query = select(MediaPlanORM).where(MediaPlanORM.media_plan_id == media_plan_id,
        MediaPlanORM.project_id == row.project_id, MediaPlanORM.workspace_id == row.workspace_id)
    plan_row = await session.scalar(query.with_for_update() if lock else query)
    if plan_row is None:
        raise KeyError(media_plan_id)
    configuration = MediaPlanRequest.model_validate({'selection_policy': 'scene_variety', **plan_row.configuration_json})
    if (configuration.purpose != 'supporting_broll' or plan_row.status != 'draft'
            or plan_row.analysis_id != analysis.analysis_id or configuration.analysis_id != analysis.analysis_id
            or plan_row.provenance_json.get('source_analysis_id', analysis.analysis_id) != analysis.analysis_id):
        raise BrollTimelineConflict('BROLL_PLAN_SOURCE_CHANGED')
    query = select(MediaPlanItemORM).where(MediaPlanItemORM.media_plan_id == media_plan_id).order_by(MediaPlanItemORM.ordinal)
    items = (await session.scalars(query.with_for_update() if lock else query)).all()
    if not items or len(items) > 200:
        raise BrollTimelineConflict('BROLL_PLAN_ITEMS_INVALID')
    selected_ids = sorted({item.selected_media_asset_id for item in items if item.selected_media_asset_id})
    query = select(MediaAssetProvenanceORM).where(MediaAssetProvenanceORM.media_asset_id.in_(selected_ids)).order_by(MediaAssetProvenanceORM.media_asset_id)
    evidence_rows = (await session.scalars(query.with_for_update() if lock else query)).all()
    if any(e.project_id != row.project_id or e.workspace_id != row.workspace_id for e in evidence_rows):
        raise BrollTimelineConflict('BROLL_PROVENANCE_SCOPE_CHANGED')
    # Shared registry provenance may originate in an earlier plan. Exact saved
    # item.selected_media_asset_id, project/workspace and asset custody bind it.
    query = select(AssetORM).where(AssetORM.asset_id.in_(sorted({analysis.asset_id, *[e.asset_id for e in evidence_rows]}))).order_by(AssetORM.asset_id)
    query = query.with_for_update() if lock else query
    asset_rows = (await session.scalars(query.execution_options(populate_existing=True))).all()
    if any(a.project_id != row.project_id or a.workspace_id != row.workspace_id for a in asset_rows):
        raise BrollTimelineConflict('BROLL_ASSET_SCOPE_CHANGED')
    assets = {a.asset_id: _asset_read(a) for a in asset_rows}
    # Rebuild speech/source proof only after refreshing and locking its asset.
    # A prior ORM identity must not hide a concurrent storage/provenance change.
    source, _ = await _source(session, row, analysis, snapshot)
    if (plan_row.provenance_json.get('transcript_id') != source['transcript_id']
            or configuration.transcript_id is not None and configuration.transcript_id != source['transcript_id']
            or plan_row.provenance_json.get('source_asset_sha256') != source['source_sha256']):
        raise BrollTimelineConflict('BROLL_PLAN_SOURCE_CHANGED')
    evidence = {e.media_asset_id: _media_asset_read(e) for e in evidence_rows}
    ready = []
    for item in items:
        if item.status != 'resolved':
            continue
        e = evidence.get(item.selected_media_asset_id)
        a = assets.get(e.asset_id) if e else None
        if (e is None or a is None or a.asset_id == analysis.asset_id
                or e.provenance.get('asset_checksum_sha256') != a.checksum_sha256
                or e.rights_status == 'restricted' or a.provenance.get('rights_status') == 'restricted'
                or e.rights_status != a.provenance.get('rights_status', 'unknown')
                or e.license != str(a.provenance.get('license', 'unknown'))
                or not (a.content_type.startswith('video/') or a.content_type in {'image/png', 'image/jpeg', 'image/webp'})
                or a.asset_class in {'render', 'metadata'} or a.kind in {'logo', 'thumbnail', 'subtitle'}):
            raise BrollTimelineConflict('BROLL_RESOLVED_ASSET_CHANGED')
        if e.publishing_allowed and (e.rights_status not in {'owned', 'licensed', 'verified'}
                or not e.production_eligible or bool(a.provenance.get('fixture'))):
            raise BrollTimelineConflict('BROLL_PUBLISHING_PROVENANCE_INVALID')
        measured = a.provenance.get('media_metadata')
        if (not isinstance(measured, dict)
                or any(type(measured.get(k)) is not int or not 0 < measured[k] <= 1_000_000 for k in ('width', 'height'))
                or any(getattr(e, k) is not None and getattr(e, k) != measured[k] for k in ('width', 'height'))
                or a.content_type.startswith('video/') and (not _positive_number(measured.get('duration_seconds'))
                    or e.duration_seconds is not None and (not _positive_number(e.duration_seconds)
                        or e.duration_seconds != measured['duration_seconds']))):
            raise BrollTimelineConflict('BROLL_MEASURED_ASSET_REQUIRED')
        ready.append(item.media_plan_item_id)
    project = await session.get(VideoProjectORM, row.project_id)
    binding = digest({'source': source, 'source_asset': asset_custody(assets[analysis.asset_id]),
        'plan': _row_value(plan_row), 'items': [_row_value(v) for v in items],
        'evidence': [_row_value(v) for v in evidence_rows], 'assets': [asset_custody(v) for v in assets.values()],
        'project': {'workspace_id': project.workspace_id, 'version': project.version,
            'current_version_id': project.current_version_id, 'niche': project.niche, 'provenance': project.provenance}})
    plan = SimpleNamespace(media_plan_id=media_plan_id, fingerprint=plan_row.fingerprint, configuration=configuration)
    return snapshot, source, binding, plan, [_item_read(v) for v in items], evidence, assets, ready


def _context(row, version, actor_ref, media_plan_id, media_binding):
    value = {'workspace_id': row.workspace_id, 'project_id': row.project_id, 'actor_ref': actor_ref,
        'timeline_id': row.timeline_id, 'timeline_version_id': version.timeline_version_id,
        'timeline_version': version.version, 'timeline_sha256': digest(version.snapshot_json),
        'media_plan_id': media_plan_id, 'media_binding_sha256': media_binding}
    return {**value, 'context_sha256': digest(value)}


async def _result(service, session, row, version, actor_ref, media_plan_id, media, replayed):
    _, source, binding, _, items, _, _, ready = media
    saved = _receipt(version)
    if saved:
        parent = await session.get(TimelineVersionORM, saved['parent_version_id'])
        if (saved['workspace_id'] != row.workspace_id or parent is None or parent.timeline_id != row.timeline_id
                or parent.project_id != row.project_id or parent.version != saved['parent_version']):
            raise BrollTimelineConflict('BROLL_TIMELINE_RECEIPT_INVALID')
        # A plan-B read must never carry a plan-A adoption receipt. A changed
        # media binding similarly cannot certify the prior observation.
        if saved['media_plan_id'] != media_plan_id or saved['media_binding_sha256'] != binding:
            saved = None
        elif _context(row, parent, saved['actor_ref'], media_plan_id, binding)['context_sha256'] != saved['context_sha256']:
            raise BrollTimelineConflict('BROLL_TIMELINE_RECEIPT_INVALID')
    return {'schema_version': 'broll-timeline-review-read.v1',
        **_context(row, version, actor_ref, media_plan_id, binding),
        'source': {k: v for k, v in source.items() if k != 'object_key'},
        'timeline': (await service.repository._timeline_read(session, row)).model_dump(mode='json'),
        'items': [v.model_dump(mode='json') for v in items], 'ready_item_ids': ready,
        'receipt': saved, 'replayed': replayed, 'provider_calls': 0,
        'publishing_enabled': False, 'owner_approval_inferred': False}


def _actor(actor_ref):
    if not isinstance(actor_ref, str) or not actor_ref or len(actor_ref) > 160 or any(ord(c) < 32 for c in actor_ref):
        raise BrollTimelineConflict('BROLL_ACTOR_INVALID')


async def read_broll_timeline(service, project_id, media_plan_id, *, actor_ref):
    _actor(actor_ref)
    try:
        async with service.repository.session_factory() as session:
            async with session.begin():
                await _begin(session)
                row, version, analysis = await _locked_current(session, project_id, False)
                media = await _media(session, row, version, analysis, media_plan_id, False)
                return await _result(service, session, row, version, actor_ref, media_plan_id, media, False)
    except SourceLinkedConflict as exc:
        raise BrollTimelineConflict(exc.code, exc.current_version) from exc
    except (ValidationError, FrozenReadRejected) as exc:
        raise BrollTimelineConflict('BROLL_REVIEW_SOURCE_INVALID') from exc


async def apply_broll_timeline(service, project_id, media_plan_id, payload, *, actor_ref):
    _actor(actor_ref)
    requested = payload.model_dump(mode='json')
    request_sha = digest({'project_id': project_id, 'media_plan_id': media_plan_id, 'actor_ref': actor_ref, 'request': requested})
    try:
        async with service.repository.session_factory() as session:
            async with session.begin():
                await _begin(session, True)
                row, version, analysis = await _locked_current(session, project_id, True)
                if row.timeline_id != payload.expected_timeline_id:
                    raise BrollTimelineConflict('BROLL_TIMELINE_IDENTITY_CHANGED', row.current_version)
                media = await _media(session, row, version, analysis, media_plan_id, True)
                snapshot, _, binding, plan, items, evidence, assets, ready = media
                prior = (await session.scalars(select(TimelineVersionORM).where(
                    TimelineVersionORM.timeline_id == row.timeline_id, TimelineVersionORM.project_id == project_id,
                    TimelineVersionORM.mutation_json['type'].as_string() == KIND,
                    TimelineVersionORM.mutation_json['receipt']['request_key'].as_string() == payload.request_key))).all()
                if prior:
                    if len(prior) != 1:
                        raise BrollTimelineConflict('BROLL_TIMELINE_RECEIPT_INVALID')
                    saved = _receipt(prior[0])
                    if saved['request_sha256'] != request_sha or saved['actor_ref'] != actor_ref:
                        raise BrollTimelineConflict('BROLL_TIMELINE_KEY_CONFLICT', row.current_version)
                    parent = await session.get(TimelineVersionORM, saved['parent_version_id'])
                    if (parent is None or parent.timeline_id != row.timeline_id or parent.project_id != project_id
                            or parent.version != payload.expected_version or saved['workspace_id'] != row.workspace_id
                            or saved['media_plan_id'] != media_plan_id or saved['item_ids'] != payload.item_ids
                            or saved['replace_plan_clips'] != payload.replace_plan_clips
                            or saved['context_sha256'] != payload.expected_context_sha256
                            or saved['media_binding_sha256'] != binding
                            or _context(row, parent, actor_ref, media_plan_id, binding)['context_sha256'] != saved['context_sha256']):
                        raise BrollTimelineConflict('BROLL_TIMELINE_RECEIPT_INVALID', row.current_version)
                    if row.current_version_id != prior[0].timeline_version_id:
                        raise BrollTimelineConflict('BROLL_TIMELINE_RECEIPT_SUPERSEDED', row.current_version)
                    return await _result(service, session, row, version, actor_ref, media_plan_id, media, True)
                if row.current_version != payload.expected_version:
                    raise BrollTimelineConflict('TIMELINE_VERSION_CONFLICT', row.current_version)
                if _context(row, version, actor_ref, media_plan_id, binding)['context_sha256'] != payload.expected_context_sha256:
                    raise BrollTimelineConflict('BROLL_REVIEW_CONTEXT_CHANGED', row.current_version)
                if any(value not in ready for value in payload.item_ids):
                    raise BrollTimelineConflict('BROLL_RESOLVED_SELECTION_REQUIRED')
                chosen = [(item, evidence[item.selected_media_asset_id]) for value in payload.item_ids
                    for item in items if item.media_plan_item_id == value]
                changed = place_broll(snapshot, plan, chosen, assets, replace_plan_clips=payload.replace_plan_clips)
                service.validator.validate(changed)
                reserved = await session.execute(update(TimelineORM).where(TimelineORM.project_id == project_id,
                    TimelineORM.timeline_id == row.timeline_id, TimelineORM.current_version == payload.expected_version,
                    TimelineORM.current_version_id == version.timeline_version_id).values(current_version=payload.expected_version)
                    .execution_options(synchronize_session=False))
                if reserved.rowcount != 1:
                    raise BrollTimelineConflict('TIMELINE_VERSION_CONFLICT')
                saved = BrollTimelineReceipt(schema_version='broll-timeline-review.v1', workspace_id=row.workspace_id,
                    project_id=project_id, timeline_id=row.timeline_id, media_plan_id=media_plan_id,
                    parent_version_id=version.timeline_version_id, parent_version=payload.expected_version,
                    result_version=payload.expected_version + 1, actor_ref=actor_ref, request_key=payload.request_key,
                    request_sha256=request_sha, context_sha256=payload.expected_context_sha256,
                    media_binding_sha256=binding, item_ids=payload.item_ids, replace_plan_clips=payload.replace_plan_clips,
                    result_snapshot_sha256=digest(changed.model_dump(mode='json'))).model_dump(mode='json')
                row = await service.repository.commit_mutation_in_session(session=session, project_id=project_id,
                    expected_version=payload.expected_version, snapshot=changed,
                    mutation={'type': KIND, 'receipt': saved, 'source_media_mutated': False, 'publish_requested': False}, actor_ref=actor_ref)
                await session.flush()
                result_version = await session.get(TimelineVersionORM, row.current_version_id)
                return await _result(service, session, row, result_version, actor_ref, media_plan_id, media, False)
    except SourceLinkedConflict as exc:
        raise BrollTimelineConflict(exc.code, exc.current_version) from exc
    except (TimelineEditError, ValidationError, FrozenReadRejected) as exc:
        raise BrollTimelineConflict('BROLL_REVIEW_SOURCE_OR_PLACEMENT_INVALID') from exc
    except TimelineConflictError as exc:
        raise BrollTimelineConflict('TIMELINE_VERSION_CONFLICT', exc.actual) from exc
    except IntegrityError as exc:
        raise BrollTimelineConflict('TIMELINE_VERSION_CONFLICT') from exc
    except OperationalError as exc:
        if not any(word in str(exc.orig).lower() for word in ('locked', 'busy')):
            raise
        raise BrollTimelineConflict('TIMELINE_VERSION_CONFLICT') from exc
