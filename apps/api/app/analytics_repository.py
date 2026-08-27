from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .analytics_db import (
    AnalyticsEventORM,
    AnalyticsFeatureSnapshotORM,
    AnalyticsLearningInsightORM,
    AnalyticsMetricPointORM,
    AnalyticsMetricSnapshotORM,
    AnalyticsSyncORM,
    WinnerAssessmentORM,
)
from .analytics_logic import (
    ANALYTICS_ALGORITHM_VERSION,
    AssessmentDraft,
    InsightDraft,
    metric_points,
)
from .analytics_models import (
    AnalyticsEventRead,
    AnalyticsMetricPointRead,
    AnalyticsMetricSnapshotRead,
    AnalyticsReportRead,
    AnalyticsSyncRead,
    LearningInsightRead,
    NormalizedMetrics,
    VideoFeatureMetadata,
    WinnerAssessmentRead,
    WinnerFactorRead,
)
from .analytics_providers import AnalyticsCollection
from .db import utc_now


class AnalyticsIdempotencyConflict(RuntimeError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class AnalyticsRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def reserve_sync(
        self,
        *,
        workspace_id: str,
        project_id: str,
        publication_id: str,
        platform: str,
        provider_key: str,
        provider_mode: str,
        trigger: str,
        fixture_profile: str | None,
        scheduled_for: datetime | None,
        idempotency_key_hash: str,
        request_fingerprint: str,
        max_attempts: int,
        actor_ref: str,
    ) -> tuple[AnalyticsSyncRead, bool]:
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(AnalyticsSyncORM).where(
                    AnalyticsSyncORM.project_id == project_id,
                    AnalyticsSyncORM.idempotency_key_hash == idempotency_key_hash,
                )
            )
            if existing is not None:
                return self._assert_replay(existing, request_fingerprint), True
            now = utc_now()
            status = "scheduled" if scheduled_for is not None and scheduled_for > now else "queued"
            row = AnalyticsSyncORM(
                sync_id=_new_id("ans"),
                workspace_id=workspace_id,
                project_id=project_id,
                publication_id=publication_id,
                platform=platform,
                provider_key=provider_key,
                provider_mode=provider_mode,
                trigger=trigger,
                fixture_profile=fixture_profile if provider_mode == "fixture" else None,
                status=status,
                idempotency_key_hash=idempotency_key_hash,
                request_fingerprint=request_fingerprint,
                attempt_count=0,
                max_attempts=max_attempts,
                scheduled_for=scheduled_for,
                next_retry_at=None,
                snapshot_id=None,
                failure_code=None,
                failure_reason=None,
                mock=provider_mode == "fixture",
                external_call=False,
                actor_ref=actor_ref,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            self._event(
                session,
                row,
                "analytics.sync_scheduled" if status == "scheduled" else "analytics.sync_queued",
                actor_ref,
                {
                    "trigger": trigger,
                    "provider_mode": provider_mode,
                    "mock": row.mock,
                    "external_call": False,
                    "secret_free": True,
                },
                now,
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(AnalyticsSyncORM).where(
                        AnalyticsSyncORM.project_id == project_id,
                        AnalyticsSyncORM.idempotency_key_hash == idempotency_key_hash,
                    )
                )
                if existing is None:
                    raise
                return self._assert_replay(existing, request_fingerprint), True
            return _sync_read(row), False

    async def claim(self, sync_id: str) -> AnalyticsSyncRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(AnalyticsSyncORM, sync_id, with_for_update=True)
                if row is None:
                    return None
                now = utc_now()
                if row.status not in {"queued", "scheduled", "retry_scheduled"}:
                    return _sync_read(row)
                due_at = row.next_retry_at if row.status == "retry_scheduled" else row.scheduled_for
                if due_at is not None and _aware(due_at) > now:
                    return _sync_read(row)
                row.status = "running"
                row.attempt_count += 1
                row.next_retry_at = None
                row.updated_at = now
                self._event(
                    session,
                    row,
                    "analytics.sync_started",
                    "analytics-worker",
                    {"attempt_count": row.attempt_count, "external_call": False, "secret_free": True},
                    now,
                )
            return _sync_read(row)

    async def complete(
        self,
        sync_id: str,
        *,
        collection: AnalyticsCollection,
        features: VideoFeatureMetadata,
        assessment: AssessmentDraft,
        insights: list[InsightDraft],
    ) -> AnalyticsSyncRead:
        if collection.external_call:
            raise ValueError("V2-10 analytics collection must not report an external call")
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(AnalyticsSyncORM, sync_id, with_for_update=True)
                if row is None:
                    raise KeyError(sync_id)
                if row.status == "succeeded":
                    return _sync_read(row)
                if row.status != "running":
                    raise RuntimeError(f"analytics sync {sync_id} is not running")
                now = utc_now()
                snapshot_id = _new_id("ams")
                snapshot = AnalyticsMetricSnapshotORM(
                    snapshot_id=snapshot_id,
                    sync_id=row.sync_id,
                    workspace_id=row.workspace_id,
                    project_id=row.project_id,
                    publication_id=row.publication_id,
                    platform=row.platform,
                    provider_key=collection.provider_key,
                    source=collection.source,
                    source_kind=collection.source_kind,
                    collected_at=collection.collected_at,
                    mock=collection.mock,
                    external_call=False,
                    created_at=now,
                )
                session.add(snapshot)
                await session.flush()
                for point in metric_points(collection.metrics):
                    session.add(
                        AnalyticsMetricPointORM(
                            point_id=_new_id("amp"),
                            snapshot_id=snapshot_id,
                            metric_name=point["metric"],
                            value=(
                                Decimal(str(point["value"])) if point["value"] is not None else None
                            ),
                            unit=point["unit"],
                            supported=point["supported"],
                        )
                    )
                feature_id = _new_id("afp")
                session.add(
                    AnalyticsFeatureSnapshotORM(
                        feature_snapshot_id=feature_id,
                        snapshot_id=snapshot_id,
                        project_id=row.project_id,
                        publication_id=row.publication_id,
                        trend_cluster_id=features.trend_cluster_id,
                        idea_id=features.idea_id,
                        hook_type=features.hook_type,
                        duration_seconds=(
                            Decimal(str(features.duration_seconds))
                            if features.duration_seconds is not None
                            else None
                        ),
                        scene_count=features.scene_count,
                        subtitle_template=features.subtitle_template,
                        voice_profile=features.voice_profile,
                        music_profile=features.music_profile,
                        visual_strategy=features.visual_strategy,
                        niche=features.niche,
                        topic=features.topic,
                        cta=features.cta,
                        publishing_time=features.publishing_time,
                        evidence_json=features.evidence,
                        captured_at=now,
                    )
                )
                assessment_id = _new_id("awa")
                session.add(
                    WinnerAssessmentORM(
                        assessment_id=assessment_id,
                        snapshot_id=snapshot_id,
                        project_id=row.project_id,
                        publication_id=row.publication_id,
                        state=assessment.state,
                        score=Decimal(str(assessment.score)) if assessment.score is not None else None,
                        data_coverage=Decimal(str(assessment.data_coverage)),
                        factors_json=[item.model_dump(mode="json") for item in assessment.factors],
                        evidence_json=assessment.evidence,
                        recommendations_json=assessment.recommendations,
                        algorithm_version=ANALYTICS_ALGORITHM_VERSION,
                        automatic_action=False,
                        paid_media_mutation=False,
                        content_deletion=False,
                        created_at=now,
                    )
                )
                await session.flush()
                for draft in insights:
                    session.add(
                        AnalyticsLearningInsightORM(
                            insight_id=_new_id("ali"),
                            project_id=row.project_id,
                            publication_id=row.publication_id,
                            snapshot_id=snapshot_id,
                            assessment_id=assessment_id,
                            trend_cluster_id=features.trend_cluster_id,
                            idea_id=features.idea_id,
                            insight_type=draft.insight_type,
                            statement=draft.statement,
                            recommendation=draft.recommendation,
                            confidence=Decimal(str(draft.confidence)),
                            evidence_refs_json=draft.evidence_refs,
                            applied=False,
                            autonomous_execution=False,
                            created_at=now,
                        )
                    )
                row.status = "succeeded"
                row.snapshot_id = snapshot_id
                row.failure_code = None
                row.failure_reason = None
                row.mock = collection.mock
                row.external_call = False
                row.updated_at = now
                self._event(
                    session,
                    row,
                    "video.analytics.updated",
                    "analytics-worker",
                    {
                        "snapshot_id": snapshot_id,
                        "assessment_id": assessment_id,
                        "winner_state": assessment.state,
                        "mock": collection.mock,
                        "external_call": False,
                        "learning_insights": len(insights),
                        "secret_free": True,
                    },
                    now,
                )
                if assessment.state == "winner_candidate":
                    self._event(
                        session,
                        row,
                        "video.winner.detected",
                        "analytics-worker",
                        {
                            "assessment_id": assessment_id,
                            "recommendation_only": True,
                            "automatic_action": False,
                            "secret_free": True,
                        },
                        now,
                    )
            return _sync_read(row)

    async def schedule_retry(
        self,
        sync_id: str,
        *,
        next_retry_at: datetime,
        code: str,
        reason: str,
    ) -> AnalyticsSyncRead:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(AnalyticsSyncORM, sync_id, with_for_update=True)
                if row is None:
                    raise KeyError(sync_id)
                now = utc_now()
                if row.attempt_count >= row.max_attempts:
                    row.status = "failed"
                    row.next_retry_at = None
                    event_type = "analytics.sync_failed"
                else:
                    row.status = "retry_scheduled"
                    row.next_retry_at = next_retry_at
                    event_type = "analytics.sync_retry_scheduled"
                row.failure_code = code
                row.failure_reason = reason[:2000]
                row.updated_at = now
                self._event(
                    session,
                    row,
                    event_type,
                    "analytics-worker",
                    {
                        "failure_code": code,
                        "attempt_count": row.attempt_count,
                        "next_retry_at": row.next_retry_at.isoformat() if row.next_retry_at else None,
                        "external_call": False,
                        "secret_free": True,
                    },
                    now,
                )
            return _sync_read(row)

    async def terminal_failure(
        self,
        sync_id: str,
        *,
        status: str,
        code: str,
        reason: str,
    ) -> AnalyticsSyncRead:
        if status not in {"failed", "not_configured", "cancelled"}:
            raise ValueError(status)
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(AnalyticsSyncORM, sync_id, with_for_update=True)
                if row is None:
                    raise KeyError(sync_id)
                now = utc_now()
                row.status = status
                row.next_retry_at = None
                row.failure_code = code
                row.failure_reason = reason[:2000]
                row.updated_at = now
                self._event(
                    session,
                    row,
                    f"analytics.sync_{status}",
                    "analytics-worker",
                    {
                        "failure_code": code,
                        "external_call": False,
                        "secret_free": True,
                    },
                    now,
                )
            return _sync_read(row)

    async def recover_incomplete_sync_ids(self) -> list[str]:
        async with self.session_factory() as session:
            async with session.begin():
                now = utc_now()
                rows = (
                    await session.scalars(
                        select(AnalyticsSyncORM).where(
                            or_(
                                AnalyticsSyncORM.status.in_(["queued", "running"]),
                                (
                                    AnalyticsSyncORM.status == "scheduled"
                                )
                                & (AnalyticsSyncORM.scheduled_for <= now),
                                (
                                    AnalyticsSyncORM.status == "retry_scheduled"
                                )
                                & (AnalyticsSyncORM.next_retry_at <= now),
                            )
                        )
                    )
                ).all()
                identifiers: list[str] = []
                for row in rows:
                    if row.status == "running":
                        row.status = "queued"
                        row.updated_at = now
                        self._event(
                            session,
                            row,
                            "analytics.sync_recovered",
                            "analytics-worker",
                            {"external_call": False, "secret_free": True},
                            now,
                        )
                    identifiers.append(row.sync_id)
            return identifiers

    async def activate_due_sync_ids(self, *, at: datetime | None = None) -> list[str]:
        now = at or utc_now()
        async with self.session_factory() as session:
            async with session.begin():
                rows = (
                    await session.scalars(
                        select(AnalyticsSyncORM)
                        .where(
                            or_(
                                (AnalyticsSyncORM.status == "scheduled")
                                & (AnalyticsSyncORM.scheduled_for <= now),
                                (AnalyticsSyncORM.status == "retry_scheduled")
                                & (AnalyticsSyncORM.next_retry_at <= now),
                            )
                        )
                        .order_by(AnalyticsSyncORM.updated_at)
                        .with_for_update()
                    )
                ).all()
                for row in rows:
                    row.status = "queued"
                    row.updated_at = now
                    self._event(
                        session,
                        row,
                        "analytics.sync_due_queued",
                        "analytics-worker",
                        {"external_call": False, "secret_free": True},
                        now,
                    )
                return [row.sync_id for row in rows]

    async def get_sync(self, project_id: str, sync_id: str) -> AnalyticsSyncRead | None:
        async with self.session_factory() as session:
            row = await session.get(AnalyticsSyncORM, sync_id)
            return _sync_read(row) if row is not None and row.project_id == project_id else None

    async def list_syncs(self, project_id: str) -> list[AnalyticsSyncRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(AnalyticsSyncORM)
                    .where(AnalyticsSyncORM.project_id == project_id)
                    .order_by(AnalyticsSyncORM.created_at.desc())
                )
            ).all()
            return [_sync_read(row) for row in rows]

    async def list_snapshots(self, project_id: str) -> list[AnalyticsMetricSnapshotRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(AnalyticsMetricSnapshotORM)
                    .where(AnalyticsMetricSnapshotORM.project_id == project_id)
                    .order_by(AnalyticsMetricSnapshotORM.collected_at.desc())
                )
            ).all()
            return [await _snapshot_read(session, row) for row in rows]

    async def list_assessments(self, project_id: str) -> list[WinnerAssessmentRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(WinnerAssessmentORM)
                    .where(WinnerAssessmentORM.project_id == project_id)
                    .order_by(WinnerAssessmentORM.created_at.desc())
                )
            ).all()
            return [_assessment_read(row) for row in rows]

    async def list_insights(self, project_id: str) -> list[LearningInsightRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(AnalyticsLearningInsightORM)
                    .where(AnalyticsLearningInsightORM.project_id == project_id)
                    .order_by(AnalyticsLearningInsightORM.created_at.desc())
                )
            ).all()
            return [_insight_read(row) for row in rows]

    async def list_events(self, project_id: str) -> list[AnalyticsEventRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(AnalyticsEventORM)
                    .where(AnalyticsEventORM.project_id == project_id)
                    .order_by(AnalyticsEventORM.created_at.desc())
                )
            ).all()
            return [_event_read(row) for row in rows]

    async def report(self, project_id: str) -> AnalyticsReportRead:
        syncs = await self.list_syncs(project_id)
        snapshots = await self.list_snapshots(project_id)
        assessments = await self.list_assessments(project_id)
        insights = await self.list_insights(project_id)
        feature: VideoFeatureMetadata | None = None
        if snapshots:
            async with self.session_factory() as session:
                row = await session.scalar(
                    select(AnalyticsFeatureSnapshotORM).where(
                        AnalyticsFeatureSnapshotORM.snapshot_id == snapshots[0].snapshot_id
                    )
                )
                feature = _feature_read(row) if row is not None else None
        latest_sync = syncs[0] if syncs else None
        if snapshots:
            status = "ready"
        elif latest_sync and latest_sync.status in {"queued", "running", "scheduled", "retry_scheduled"}:
            status = "collecting"
        elif latest_sync and latest_sync.status == "not_configured":
            status = "not_configured"
        elif latest_sync and latest_sync.status == "failed":
            status = "failed"
        else:
            status = "not_started"
        return AnalyticsReportRead(
            project_id=project_id,
            status=status,  # type: ignore[arg-type]
            latest_sync=latest_sync,
            latest_snapshot=snapshots[0] if snapshots else None,
            latest_assessment=assessments[0] if assessments else None,
            video_features=feature,
            learning_insights=(
                [item for item in insights if not snapshots or item.snapshot_id == snapshots[0].snapshot_id]
            ),
            history_count=len(snapshots),
            recommendation_only=True,
            external_execution_enabled=False,
        )

    @staticmethod
    def _assert_replay(row: AnalyticsSyncORM, fingerprint: str) -> AnalyticsSyncRead:
        if row.request_fingerprint != fingerprint:
            raise AnalyticsIdempotencyConflict(
                "Idempotency-Key was already used for a different analytics request"
            )
        return _sync_read(row)

    @staticmethod
    def _event(
        session: AsyncSession,
        row: AnalyticsSyncORM,
        event_type: str,
        actor_ref: str,
        payload: dict,
        created_at: datetime,
    ) -> None:
        session.add(
            AnalyticsEventORM(
                event_id=_new_id("ane"),
                sync_id=row.sync_id,
                project_id=row.project_id,
                event_type=event_type,
                actor_ref=actor_ref,
                payload_json=payload,
                created_at=created_at,
            )
        )


def _sync_read(row: AnalyticsSyncORM) -> AnalyticsSyncRead:
    return AnalyticsSyncRead(
        sync_id=row.sync_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        publication_id=row.publication_id,
        platform=row.platform,
        provider_key=row.provider_key,
        provider_mode=row.provider_mode,
        trigger=row.trigger,
        fixture_profile=row.fixture_profile,
        status=row.status,
        request_fingerprint=row.request_fingerprint,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        scheduled_for=row.scheduled_for,
        next_retry_at=row.next_retry_at,
        snapshot_id=row.snapshot_id,
        failure_code=row.failure_code,
        failure_reason=row.failure_reason,
        mock=row.mock,
        external_call=False,
        actor_ref=row.actor_ref,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _snapshot_read(
    session: AsyncSession, row: AnalyticsMetricSnapshotORM
) -> AnalyticsMetricSnapshotRead:
    points = (
        await session.scalars(
            select(AnalyticsMetricPointORM)
            .where(AnalyticsMetricPointORM.snapshot_id == row.snapshot_id)
            .order_by(AnalyticsMetricPointORM.metric_name)
        )
    ).all()
    values = {point.metric_name: float(point.value) if point.value is not None else None for point in points}
    return AnalyticsMetricSnapshotRead(
        snapshot_id=row.snapshot_id,
        sync_id=row.sync_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        publication_id=row.publication_id,
        platform=row.platform,
        provider_key=row.provider_key,
        source=row.source,
        source_kind=row.source_kind,
        collected_at=row.collected_at,
        metrics=NormalizedMetrics.model_validate(values),
        points=[
            AnalyticsMetricPointRead(
                point_id=point.point_id,
                metric=point.metric_name,
                value=float(point.value) if point.value is not None else None,
                unit=point.unit,
                supported=point.supported,
            )
            for point in points
        ],
        mock=row.mock,
        external_call=False,
        created_at=row.created_at,
    )


def _feature_read(row: AnalyticsFeatureSnapshotORM) -> VideoFeatureMetadata:
    return VideoFeatureMetadata(
        feature_snapshot_id=row.feature_snapshot_id,
        project_id=row.project_id,
        publication_id=row.publication_id,
        trend_cluster_id=row.trend_cluster_id,
        idea_id=row.idea_id,
        hook_type=row.hook_type,
        duration_seconds=float(row.duration_seconds) if row.duration_seconds is not None else None,
        scene_count=row.scene_count,
        subtitle_template=row.subtitle_template,
        voice_profile=row.voice_profile,
        music_profile=row.music_profile,
        visual_strategy=row.visual_strategy,
        niche=row.niche,
        topic=row.topic,
        cta=row.cta,
        publishing_time=row.publishing_time,
        evidence=dict(row.evidence_json or {}),
        captured_at=row.captured_at,
    )


def _assessment_read(row: WinnerAssessmentORM) -> WinnerAssessmentRead:
    return WinnerAssessmentRead(
        assessment_id=row.assessment_id,
        snapshot_id=row.snapshot_id,
        project_id=row.project_id,
        publication_id=row.publication_id,
        state=row.state,
        score=float(row.score) if row.score is not None else None,
        data_coverage=float(row.data_coverage),
        factors=[WinnerFactorRead.model_validate(item) for item in row.factors_json],
        evidence=list(row.evidence_json or []),
        recommendations=list(row.recommendations_json or []),
        algorithm_version=row.algorithm_version,
        automatic_action=False,
        paid_media_mutation=False,
        content_deletion=False,
        created_at=row.created_at,
    )


def _insight_read(row: AnalyticsLearningInsightORM) -> LearningInsightRead:
    return LearningInsightRead(
        insight_id=row.insight_id,
        project_id=row.project_id,
        publication_id=row.publication_id,
        snapshot_id=row.snapshot_id,
        assessment_id=row.assessment_id,
        trend_cluster_id=row.trend_cluster_id,
        idea_id=row.idea_id,
        insight_type=row.insight_type,
        statement=row.statement,
        recommendation=row.recommendation,
        confidence=float(row.confidence),
        evidence_refs=list(row.evidence_refs_json or []),
        applied=False,
        autonomous_execution=False,
        created_at=row.created_at,
    )


def _event_read(row: AnalyticsEventORM) -> AnalyticsEventRead:
    return AnalyticsEventRead(
        event_id=row.event_id,
        sync_id=row.sync_id,
        project_id=row.project_id,
        event_type=row.event_type,
        actor_ref=row.actor_ref,
        payload=dict(row.payload_json or {}),
        created_at=row.created_at,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
