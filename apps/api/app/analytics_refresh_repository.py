"""Scoped immutable plan configuration and revisioned Owner controls."""
import hashlib
import json
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .analytics_refresh_db import AnalyticsRefreshPlanORM, AnalyticsRefreshEventORM, AnalyticsRefreshOccurrenceORM
from .analytics_refresh_models import AnalyticsRefreshCreate, AnalyticsRefreshRead
from .analytics_repository import AnalyticsRepository, _aware, _utc_input
from .db import utc_now
from .publishing_db import PublicationORM
from .publishing_models import PublishingTargetBinding
from .publishing_credentials import target_digest
from .analytics_db import AnalyticsSyncORM
from .analytics_models import AnalyticsSyncRequest
from .analytics_logic import analytics_request_fingerprint, hash_idempotency_key


class AnalyticsRefreshError(RuntimeError):
    def __init__(self, code): self.code = code; super().__init__(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def identifier(prefix): return prefix + '_' + uuid.uuid4().hex


def plan_read(row):
    return AnalyticsRefreshRead(plan_id=row.plan_id, workspace_id=row.workspace_id, project_id=row.project_id,
        publication_id=row.publication_id, platform=row.platform, provider_key=row.provider_key,
        target_binding_sha256=row.target_binding_sha256, config=AnalyticsRefreshCreate.model_validate(row.config_json),
        revision=row.revision, enabled=row.enabled, run_count=row.run_count, max_runs=row.max_runs,
        next_due_at=_aware(row.next_due_at), created_by=row.created_by, updated_by=row.updated_by,
        created_at=_aware(row.created_at), updated_at=_aware(row.updated_at))


def event(session, row, category, actor, payload):
    session.add(AnalyticsRefreshEventORM(event_id=identifier('are'), plan_id=row.plan_id, revision=row.revision,
        event_type=category, actor_ref=actor, payload_json=payload, created_at=utc_now()))


class AnalyticsRefreshRepository:
    def __init__(self, factory): self.factory = factory

    async def create(self, *, workspace, project, config, provider_key, target_sha256, publication_fingerprint, actor, key):
        config = AnalyticsRefreshCreate.model_validate(config.model_dump())
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        fingerprint = digest({'workspace': workspace, 'project': project, 'config': config.model_dump(mode='json'),
            'provider_key': provider_key, 'target_sha256': target_sha256, 'publication_fingerprint': publication_fingerprint, 'actor': actor})
        async with self.factory() as session:
            existing = await session.scalar(select(AnalyticsRefreshPlanORM).where(AnalyticsRefreshPlanORM.project_id == project,
                AnalyticsRefreshPlanORM.idempotency_key_hash == key_hash))
            if existing:
                if existing.workspace_id != workspace or existing.request_fingerprint != fingerprint:
                    raise AnalyticsRefreshError('ANALYTICS_REFRESH_IDEMPOTENCY_CONFLICT')
                return plan_read(existing), True
            parent = await session.get(PublicationORM, config.publication_id)
            if parent is None or parent.project_id != project or parent.workspace_id != workspace:
                raise AnalyticsRefreshError('ANALYTICS_REFRESH_PUBLICATION_NOT_FOUND')
            if parent.request_fingerprint != publication_fingerprint or parent.status not in ('published', 'dry_run_succeeded'):
                raise AnalyticsRefreshError('ANALYTICS_REFRESH_PUBLICATION_CHANGED')
            now = utc_now()
            row = AnalyticsRefreshPlanORM(plan_id=identifier('arp'), workspace_id=workspace, project_id=project,
                publication_id=parent.publication_id, platform=parent.platform, provider_mode=config.provider_mode,
                provider_key=provider_key, target_binding_sha256=target_sha256, publication_fingerprint=publication_fingerprint,
                config_json=config.model_dump(mode='json'), request_fingerprint=fingerprint, idempotency_key_hash=key_hash,
                interval_hours=config.interval_hours, max_runs=config.max_runs, run_count=0, revision=1,
                enabled=config.enabled, next_due_at=config.first_run_at, created_by=actor, updated_by=actor, created_at=now, updated_at=now)
            session.add(row)
            try:
                await session.flush()
                event(session, row, 'analytics.refresh_plan.created', actor, {'enabled': row.enabled, 'read_only': True})
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(select(AnalyticsRefreshPlanORM).where(AnalyticsRefreshPlanORM.project_id == project,
                    AnalyticsRefreshPlanORM.idempotency_key_hash == key_hash))
                if existing is None: raise
                if existing.workspace_id != workspace or existing.request_fingerprint != fingerprint:
                    raise AnalyticsRefreshError('ANALYTICS_REFRESH_IDEMPOTENCY_CONFLICT')
                return plan_read(existing), True
            return plan_read(row), False

    async def get(self, project, plan_id):
        async with self.factory() as session:
            row = await session.get(AnalyticsRefreshPlanORM, plan_id)
            return plan_read(row) if row and row.project_id == project else None

    async def list(self, project, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100: raise AnalyticsRefreshError('ANALYTICS_REFRESH_PAGE_LIMIT')
        async with self.factory() as session:
            rows = (await session.scalars(select(AnalyticsRefreshPlanORM).where(AnalyticsRefreshPlanORM.project_id == project)
                .order_by(AnalyticsRefreshPlanORM.created_at.desc(), AnalyticsRefreshPlanORM.plan_id).limit(limit))).all()
            return [plan_read(row) for row in rows]

    async def change_state(self, project, plan_id, *, revision, enabled, actor):
        async with self.factory() as session:
            async with session.begin():
                row = await session.scalar(select(AnalyticsRefreshPlanORM).where(AnalyticsRefreshPlanORM.project_id == project,
                    AnalyticsRefreshPlanORM.plan_id == plan_id).with_for_update())
                if row is None: raise AnalyticsRefreshError('ANALYTICS_REFRESH_NOT_FOUND')
                if row.revision != revision: raise AnalyticsRefreshError('ANALYTICS_REFRESH_REVISION_CONFLICT')
                if enabled and row.run_count >= row.max_runs: raise AnalyticsRefreshError('ANALYTICS_REFRESH_EXHAUSTED')
                changed = await session.execute(update(AnalyticsRefreshPlanORM).where(AnalyticsRefreshPlanORM.plan_id == plan_id,
                    AnalyticsRefreshPlanORM.revision == revision).values(enabled=enabled, revision=revision + 1,
                        updated_by=actor, updated_at=utc_now()).execution_options(synchronize_session=False))
                if changed.rowcount != 1: raise AnalyticsRefreshError('ANALYTICS_REFRESH_REVISION_CONFLICT')
                await session.refresh(row)
                event(session, row, 'analytics.refresh_plan.enabled' if enabled else 'analytics.refresh_plan.disabled', actor,
                    {'enabled': enabled, 'old_revision': revision, 'read_only': True})
            return plan_read(row)

    async def history(self, project, plan_id, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100: raise AnalyticsRefreshError('ANALYTICS_REFRESH_PAGE_LIMIT')
        async with self.factory() as session:
            parent = await session.get(AnalyticsRefreshPlanORM, plan_id)
            if parent is None or parent.project_id != project: raise AnalyticsRefreshError('ANALYTICS_REFRESH_NOT_FOUND')
            rows = (await session.scalars(select(AnalyticsRefreshEventORM).where(AnalyticsRefreshEventORM.plan_id == plan_id)
                .order_by(AnalyticsRefreshEventORM.created_at.desc(), AnalyticsRefreshEventORM.event_id).limit(limit))).all()
            return [{'event_id': row.event_id, 'plan_id': row.plan_id, 'revision': row.revision, 'actor_ref': row.actor_ref,
                'event_type': row.event_type, 'payload': row.payload_json, 'created_at': _aware(row.created_at)} for row in rows]

    async def create_due(self, *, settings, provider_ready, at=None):
        """One bounded occurrence per due plan, atomically with its existing job.

        No queue/provider call is made. A later durable queue tick admits the
        persisted jobs. Missed periods produce one current collection, not a burst.
        """
        if not settings.analytics_scheduled_refresh_enabled: return []
        now = _utc_input(at or utc_now())
        async with self.factory() as session:
            async with session.begin():
                rows = (await session.scalars(select(AnalyticsRefreshPlanORM).where(
                    AnalyticsRefreshPlanORM.enabled.is_(True), AnalyticsRefreshPlanORM.run_count < AnalyticsRefreshPlanORM.max_runs,
                    AnalyticsRefreshPlanORM.next_due_at <= now).order_by(AnalyticsRefreshPlanORM.next_due_at,
                        AnalyticsRefreshPlanORM.plan_id).limit(20).with_for_update(skip_locked=True))).all()
                identifiers = []
                for row in rows:
                    if row.provider_mode == 'fixture' and not settings.analytics_fixture_enabled: continue
                    if not provider_ready(row.platform, row.provider_mode, row.workspace_id, row.provider_key): continue
                    parent = await session.get(PublicationORM, row.publication_id)
                    if (parent is None or parent.workspace_id != row.workspace_id or parent.project_id != row.project_id
                        or parent.platform != row.platform or parent.request_fingerprint != row.publication_fingerprint
                        or parent.status not in ('published', 'dry_run_succeeded')): continue
                    if row.provider_mode == 'official':
                        try:
                            target = PublishingTargetBinding.model_validate((parent.provider_validation_json or {}).get('target_binding'))
                        except ValueError: continue
                        if (target_digest(target) != row.target_binding_sha256 or target.workspace_id != row.workspace_id
                            or target.platform != row.platform or target.provider_key != parent.provider_key
                            or parent.status != 'published' or parent.mode != 'live' or parent.dry_run): continue
                    config = AnalyticsRefreshCreate.model_validate(row.config_json)
                    planned = _aware(row.next_due_at); ordinal = row.run_count + 1
                    skipped = max(0, int((now - planned).total_seconds() // (row.interval_hours * 3600)))
                    changed = await session.execute(update(AnalyticsRefreshPlanORM).where(
                        AnalyticsRefreshPlanORM.plan_id == row.plan_id, AnalyticsRefreshPlanORM.enabled.is_(True),
                        AnalyticsRefreshPlanORM.revision == row.revision, AnalyticsRefreshPlanORM.run_count == row.run_count,
                        AnalyticsRefreshPlanORM.next_due_at == row.next_due_at).values(run_count=ordinal,
                            next_due_at=now + timedelta(hours=row.interval_hours), updated_at=now)
                        .execution_options(synchronize_session=False))
                    if changed.rowcount != 1: continue
                    payload = AnalyticsSyncRequest(publication_id=row.publication_id, provider_mode=row.provider_mode,
                        fixture_profile=config.fixture_profile if row.provider_mode == 'fixture' else 'winner_candidate',
                        trigger='scheduled_refresh', scheduled_for=now, query=config.query_at(now), actor_ref=row.created_by)
                    sync = AnalyticsSyncORM(sync_id=identifier('ans'), workspace_id=row.workspace_id, project_id=row.project_id,
                        publication_id=row.publication_id, platform=row.platform, provider_key=row.provider_key,
                        provider_mode=row.provider_mode, trigger='scheduled_refresh',
                        fixture_profile=config.fixture_profile if row.provider_mode == 'fixture' else None, status='queued',
                        idempotency_key_hash=hash_idempotency_key(f'refresh-plan:{row.plan_id}:{ordinal}'),
                        request_fingerprint=analytics_request_fingerprint(payload), attempt_count=0,
                        max_attempts=settings.analytics_max_attempts, scheduled_for=now, next_retry_at=None,
                        snapshot_id=None, failure_code=None, failure_reason=None, mock=row.provider_mode == 'fixture',
                        external_call=False, query_json=payload.query, actor_ref=row.created_by, created_at=now, updated_at=now)
                    session.add(sync); await session.flush()
                    AnalyticsRepository._event(session, sync, 'analytics.sync_queued', row.created_by,
                        {'trigger': 'scheduled_refresh', 'refresh_plan_id': row.plan_id, 'ordinal': ordinal,
                            'mock': sync.mock, 'external_call': False, 'secret_free': True}, now)
                    session.add(AnalyticsRefreshOccurrenceORM(occurrence_id=identifier('aro'), plan_id=row.plan_id,
                        sync_id=sync.sync_id, plan_revision=row.revision, ordinal=ordinal, planned_for=planned,
                        scheduled_for=now, skipped_slots=skipped, created_at=now))
                    await session.refresh(row)
                    event(session, row, 'analytics.refresh_plan.occurrence_created', 'analytics-scheduler',
                        {'sync_id': sync.sync_id, 'ordinal': ordinal, 'skipped_slots': skipped, 'read_only': True})
                    identifiers.append(sync.sync_id)
                return identifiers
