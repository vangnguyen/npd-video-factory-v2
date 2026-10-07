"""Bounded, read-only projections over immutable analytics observations.

Channel rows represent individual publication reports, never account totals.
No provider, queue, credential or publishing operation is dispatched here.
"""
from datetime import datetime
from typing import Literal

from pydantic import Field
from sqlalchemy import and_, func, or_, select

from .analytics_db import AnalyticsMetricSnapshotORM
from .analytics_models import AnalyticsMetricSnapshotRead, AnalyticsProviderMode
from .analytics_repository import _snapshot_read
from .db import utc_now
from .models import StrictModel
from .publishing_credentials import target_digest
from .publishing_db import PublicationORM
from .publishing_models import PublishingTargetBinding


class ObservationPage(StrictModel):
    workspace_id: str
    project_id: str
    publication_id: str
    provider_mode: AnalyticsProviderMode
    items: list[AnalyticsMetricSnapshotRead]
    next_cursor: str | None
    total_count: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class ChannelVideoRead(StrictModel):
    project_id: str
    publication_id: str
    title: str
    remote_post_id: str | None
    status: str
    latest_snapshot: AnalyticsMetricSnapshotRead | None
    binding_state: Literal['matched', 'fixture_unverified', 'unbound', 'mismatch', 'not_collected']


class ChannelObservationRead(StrictModel):
    channel_key: str
    platform: str
    provider_key: str | None
    target_account_id: str | None
    profile_id: str | None
    profile_version: int | None
    target_binding_sha256: str | None
    provider_mode: AnalyticsProviderMode
    mock: bool | None
    videos: list[ChannelVideoRead]


class ChannelObservationPage(StrictModel):
    workspace_id: str
    provider_mode: AnalyticsProviderMode
    channels: list[ChannelObservationRead]
    publications_in_page: int = Field(ge=0)
    next_cursor: str | None
    limit: int = Field(ge=1, le=100)
    generated_at: datetime
    account_totals: None = None
    recommendation_only: Literal[True] = True
    note: str = 'Latest per-publication reports in this page; intervals and null metrics remain separate. These are not channel/account totals.'


def _bounded(limit):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('ANALYTICS_PAGE_LIMIT_INVALID')


async def observation_page(factory, *, workspace, project, publication, mode, limit=50, cursor=None):
    _bounded(limit)
    kind = 'fixture' if mode == 'fixture' else 'official_api'
    async with factory() as session:
        filters = [AnalyticsMetricSnapshotORM.workspace_id == workspace,
            AnalyticsMetricSnapshotORM.project_id == project,
            AnalyticsMetricSnapshotORM.publication_id == publication,
            AnalyticsMetricSnapshotORM.source_kind == kind]
        count = await session.scalar(select(func.count()).select_from(AnalyticsMetricSnapshotORM).where(*filters))
        paging = []
        if cursor:
            anchor = await session.scalar(select(AnalyticsMetricSnapshotORM).where(*filters,
                AnalyticsMetricSnapshotORM.snapshot_id == cursor))
            if anchor is None: raise ValueError('ANALYTICS_CURSOR_SCOPE_INVALID')
            paging.append(or_(AnalyticsMetricSnapshotORM.collected_at < anchor.collected_at,
                and_(AnalyticsMetricSnapshotORM.collected_at == anchor.collected_at,
                    AnalyticsMetricSnapshotORM.created_at < anchor.created_at),
                and_(AnalyticsMetricSnapshotORM.collected_at == anchor.collected_at,
                    AnalyticsMetricSnapshotORM.created_at == anchor.created_at,
                    AnalyticsMetricSnapshotORM.snapshot_id < anchor.snapshot_id)))
        rows = (await session.scalars(select(AnalyticsMetricSnapshotORM).where(*filters, *paging)
            .order_by(AnalyticsMetricSnapshotORM.collected_at.desc(), AnalyticsMetricSnapshotORM.created_at.desc(),
                AnalyticsMetricSnapshotORM.snapshot_id.desc()).limit(limit + 1))).all()
        return ObservationPage(workspace_id=workspace, project_id=project, publication_id=publication,
            provider_mode=mode, items=[await _snapshot_read(session, row) for row in rows[:limit]],
            next_cursor=rows[limit-1].snapshot_id if len(rows) > limit else None, total_count=count, limit=limit)


def _target(publication):
    try:
        value = PublishingTargetBinding.model_validate((publication.provider_validation_json or {}).get('target_binding'))
        if value.workspace_id != publication.workspace_id or value.platform != publication.platform or value.provider_key != publication.provider_key:
            return None
        return value
    except ValueError:
        return None


async def channel_page(factory, *, workspace, mode, limit=50, cursor=None):
    """Page publications, then fetch one latest observation of each transport kind.

    Mock official protocol results and actual provider observations are kept apart.
    Unbound or mismatched reports each get their own group; no invented account.
    """
    _bounded(limit)
    async with factory() as session:
        filters = [PublicationORM.workspace_id == workspace,
            PublicationORM.status.in_(['published', 'dry_run_succeeded'])]
        if cursor:
            exists = await session.scalar(select(PublicationORM.publication_id).where(*filters, PublicationORM.publication_id == cursor))
            if exists is None: raise ValueError('ANALYTICS_CURSOR_SCOPE_INVALID')
        rows = (await session.scalars(select(PublicationORM).where(*filters,
            *([PublicationORM.publication_id > cursor] if cursor else []))
            .order_by(PublicationORM.publication_id).limit(limit + 1))).all()
        page = rows[:limit]
        rank = select(AnalyticsMetricSnapshotORM.snapshot_id,
            func.row_number().over(partition_by=(AnalyticsMetricSnapshotORM.publication_id, AnalyticsMetricSnapshotORM.mock),
                order_by=(AnalyticsMetricSnapshotORM.collected_at.desc(), AnalyticsMetricSnapshotORM.created_at.desc(),
                    AnalyticsMetricSnapshotORM.snapshot_id.desc())).label('position')).where(
                AnalyticsMetricSnapshotORM.workspace_id == workspace,
                AnalyticsMetricSnapshotORM.publication_id.in_([row.publication_id for row in page]),
                AnalyticsMetricSnapshotORM.source_kind == ('fixture' if mode == 'fixture' else 'official_api')).subquery()
        snapshots = (await session.scalars(select(AnalyticsMetricSnapshotORM).join(rank,
            rank.c.snapshot_id == AnalyticsMetricSnapshotORM.snapshot_id).where(rank.c.position == 1))).all()
        by_publication = {}
        for snapshot in snapshots: by_publication.setdefault(snapshot.publication_id, []).append(snapshot)
        groups = {}
        for parent in page:
            target = _target(parent); digest = target_digest(target) if target else None
            receipt = parent.receipt_json or {}
            for snapshot in by_publication.get(parent.publication_id, [None]):
                evidence = snapshot.evidence_json or {} if snapshot else {}
                matched = bool(target and snapshot and evidence.get('target_binding_sha256') == digest and evidence.get('account_match') is True)
                state = ('not_collected' if snapshot is None else 'unbound' if target is None else
                    'fixture_unverified' if mode == 'fixture' else 'matched' if matched else 'mismatch')
                mock = snapshot.mock if snapshot else None
                suffix = parent.publication_id if state in ('unbound', 'mismatch', 'not_collected') else digest
                provider_key = snapshot.provider_key if snapshot else None
                key = f'{parent.platform}:{provider_key}:{mode}:{mock}:{suffix}'
                if key not in groups:
                    groups[key] = ChannelObservationRead(channel_key=key, platform=parent.platform, provider_key=provider_key,
                        target_account_id=target.target_account_id if target else None, profile_id=target.profile_id if target else None,
                        profile_version=target.profile_version if target else None, target_binding_sha256=digest,
                        provider_mode=mode, mock=mock, videos=[])
                groups[key].videos.append(ChannelVideoRead(project_id=parent.project_id, publication_id=parent.publication_id,
                    title=parent.metadata_json.get('title', ''), remote_post_id=receipt.get('remote_post_id'), status=parent.status,
                    latest_snapshot=await _snapshot_read(session, snapshot) if snapshot else None, binding_state=state))
        return ChannelObservationPage(workspace_id=workspace, provider_mode=mode, channels=list(groups.values()),
            publications_in_page=len(page), next_cursor=page[-1].publication_id if len(rows) > limit else None,
            limit=limit, generated_at=utc_now())
