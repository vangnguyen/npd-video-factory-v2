from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import VideoProjectORM, WorkspaceORM, utc_now
from .repositories import new_id
from .trend_db import (
    ChannelOpportunityORM,
    ContentQueueItemORM,
    IdeaCandidateORM,
    IdeaScoreORM,
    ResearchEvidenceORM,
    TrendClusterORM,
    TrendClusterSignalORM,
    TrendEvidenceORM,
    TrendScoreORM,
    TrendSignalORM,
    TrendSnapshotORM,
    TrendSourceORM,
)
from .trend_models import (
    ContentQueueItemRead,
    ContentQueueRefreshRequest,
    IdeaCandidateRead,
    IdeaGenerateRequest,
    IdeaScoreRead,
    ProviderTrendSignal,
    TrendClusterRead,
    TrendClusterRefreshRequest,
    TrendCollectionRequest,
    TrendCollectionResult,
    TrendEvidenceRead,
    TrendScoreRead,
    TrendSignalRead,
    TrendSnapshotRead,
    TrendSourceRead,
)
from .trend_scoring import ClusterDraft, IdeaDraft, IdeaEngine, ScoreDraft, cluster_signals, score_cluster


def _float(value: Any | None) -> float | None:
    return float(value) if value is not None else None


def _source_read(row: TrendSourceORM) -> TrendSourceRead:
    return TrendSourceRead(
        source_id=row.source_id,
        workspace_id=row.workspace_id,
        provider_key=row.provider_key,
        display_name=row.display_name,
        source_type=row.source_type,
        status=row.status,
        authorized_access=row.authorized_access,
        config_ref=row.config_ref,
        capabilities=row.capabilities_json,
        version=row.version,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _snapshot_read(row: TrendSnapshotORM) -> TrendSnapshotRead:
    return TrendSnapshotRead(
        snapshot_id=row.snapshot_id,
        workspace_id=row.workspace_id,
        source_id=row.source_id,
        provider_key=row.provider_key,
        query=row.query_json,
        signal_count=row.signal_count,
        new_signal_count=row.new_signal_count,
        collected_at=row.collected_at,
        version=row.version,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _signal_read(row: TrendSignalORM) -> TrendSignalRead:
    return TrendSignalRead(
        signal_id=row.signal_id,
        workspace_id=row.workspace_id,
        snapshot_id=row.snapshot_id,
        source_id=row.source_id,
        source=row.source,
        source_reference=row.source_reference,
        observed_at=row.observed_at,
        country=row.country,
        locale=row.locale,
        language=row.language,
        keyword=row.keyword,
        topic=row.topic,
        hashtags=row.hashtags_json,
        media_type=row.media_type,
        format=row.format,
        duration_seconds=_float(row.duration_seconds),
        views=row.views,
        likes=row.likes,
        comments=row.comments,
        shares=row.shares,
        saves=row.saves,
        engagement=_float(row.engagement),
        creator_count=row.creator_count,
        content_count=row.content_count,
        velocity=_float(row.velocity),
        acceleration=_float(row.acceleration),
        raw_signal_hash=row.raw_signal_hash,
        version=row.version,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _evidence_read(row: TrendEvidenceORM) -> TrendEvidenceRead:
    return TrendEvidenceRead(
        evidence_id=row.evidence_id,
        signal_id=row.signal_id,
        claim=row.claim,
        summary=row.summary,
        source_reference=row.source_reference,
        retrieved_at=row.retrieved_at,
        confidence=float(row.confidence),
        freshness=row.freshness,
    )


def _score_read(row: TrendScoreORM) -> TrendScoreRead:
    return TrendScoreRead(
        trend_score_id=row.trend_score_id,
        cluster_id=row.cluster_id,
        channel=row.channel,
        niche=row.niche,
        business_objective=row.business_objective,
        total_score=float(row.total_score),
        components={key: float(value) for key, value in row.components_json.items()},
        weights={key: float(value) for key, value in row.weights_json.items()},
        estimated=True,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _idea_score_read(row: IdeaScoreORM) -> IdeaScoreRead:
    return IdeaScoreRead(
        idea_score_id=row.idea_score_id,
        idea_id=row.idea_id,
        total_score=float(row.total_score),
        components={key: float(value) for key, value in row.components_json.items()},
        estimated=True,
        rationale=row.rationale_json,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _idea_read(row: IdeaCandidateORM, score: IdeaScoreORM) -> IdeaCandidateRead:
    return IdeaCandidateRead(
        idea_id=row.idea_id,
        workspace_id=row.workspace_id,
        cluster_id=row.cluster_id,
        project_id=row.project_id,
        variant_key=row.variant_key,
        channel=row.channel,
        niche=row.niche,
        business_objective=row.business_objective,
        title=row.title,
        angle=row.angle,
        hook_concept=row.hook_concept,
        format=row.format,
        recommended_duration_seconds=row.recommended_duration_seconds,
        visual_concept=row.visual_concept,
        audience=row.audience,
        cta_concept=row.cta_concept,
        trend_references=row.trend_references_json,
        originality_notes=row.originality_notes,
        brief=row.brief_json,
        status=row.status,
        score=_idea_score_read(score),
        version=row.version,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _raw_signal_hash(signal: ProviderTrendSignal) -> str:
    payload = signal.model_dump(mode="json", exclude={"evidence_summary", "evidence_confidence", "freshness"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _trend_request_from_idea(request: IdeaGenerateRequest) -> TrendClusterRefreshRequest:
    return TrendClusterRefreshRequest(
        channel=request.channel,
        niche=request.niche,
        business_objective=request.business_objective,
        weights=request.weights,
    )


class TrendRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def seed_sources(self, definitions: Iterable[dict[str, Any]]) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                for definition in definitions:
                    row = await session.scalar(
                        select(TrendSourceORM).where(
                            TrendSourceORM.workspace_id.is_(None),
                            TrendSourceORM.provider_key == definition["provider_key"],
                        )
                    )
                    values = {
                        "display_name": definition["display_name"],
                        "source_type": definition["source_type"],
                        "status": definition["status"],
                        "authorized_access": definition["authorized_access"],
                        "config_ref": definition.get("config_ref"),
                        "capabilities_json": definition.get("capabilities", {}),
                    }
                    if row is None:
                        session.add(
                            TrendSourceORM(
                                source_id=new_id("tsrc"),
                                workspace_id=None,
                                provider_key=definition["provider_key"],
                                provenance={"source": "trend-provider-registry"},
                                **values,
                            )
                        )
                    elif any(getattr(row, key) != value for key, value in values.items()):
                        for key, value in values.items():
                            setattr(row, key, value)
                        row.version += 1
                        row.updated_at = utc_now()

    async def list_sources(self) -> list[TrendSourceRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(TrendSourceORM).order_by(TrendSourceORM.provider_key)
                )
            ).all()
            return [_source_read(row) for row in rows]

    async def record_collection(
        self,
        *,
        workspace_id: str,
        request: TrendCollectionRequest,
        signals: list[ProviderTrendSignal],
    ) -> TrendCollectionResult:
        async with self.session_factory() as session:
            async with session.begin():
                if await session.get(WorkspaceORM, workspace_id) is None:
                    raise KeyError(workspace_id)
                source = await session.scalar(
                    select(TrendSourceORM).where(
                        TrendSourceORM.workspace_id.is_(None),
                        TrendSourceORM.provider_key == request.provider_key,
                    )
                )
                if source is None:
                    raise KeyError(request.provider_key)
                snapshot = TrendSnapshotORM(
                    snapshot_id=new_id("tsnap"),
                    workspace_id=workspace_id,
                    source_id=source.source_id,
                    provider_key=request.provider_key,
                    query_json=request.model_dump(mode="json"),
                    signal_count=len(signals),
                    new_signal_count=0,
                    provenance={"source": request.provider_key, "mode": "authorized-provider"},
                )
                session.add(snapshot)
                await session.flush()
                persisted: list[TrendSignalORM] = []
                evidence: list[TrendEvidenceORM] = []
                new_count = 0
                for item in signals:
                    digest = _raw_signal_hash(item)
                    row = await session.scalar(
                        select(TrendSignalORM).where(
                            TrendSignalORM.workspace_id == workspace_id,
                            TrendSignalORM.source == item.source,
                            TrendSignalORM.raw_signal_hash == digest,
                        )
                    )
                    if row is None:
                        row = TrendSignalORM(
                            signal_id=new_id("tsig"),
                            workspace_id=workspace_id,
                            snapshot_id=snapshot.snapshot_id,
                            source_id=source.source_id,
                            source=item.source,
                            source_reference=str(item.source_reference),
                            observed_at=item.observed_at,
                            country=item.country,
                            locale=item.locale,
                            language=item.language,
                            keyword=item.keyword,
                            topic=item.topic,
                            hashtags_json=item.hashtags,
                            media_type=item.media_type,
                            format=item.format,
                            duration_seconds=Decimal(str(item.duration_seconds)) if item.duration_seconds is not None else None,
                            views=item.views,
                            likes=item.likes,
                            comments=item.comments,
                            shares=item.shares,
                            saves=item.saves,
                            engagement=Decimal(str(item.engagement)) if item.engagement is not None else None,
                            creator_count=item.creator_count,
                            content_count=item.content_count,
                            velocity=Decimal(str(item.velocity)) if item.velocity is not None else None,
                            acceleration=Decimal(str(item.acceleration)) if item.acceleration is not None else None,
                            raw_signal_hash=digest,
                            provenance={
                                "provider_key": request.provider_key,
                                "source_reference_only": True,
                                "creator_media_downloaded": False,
                            },
                        )
                        session.add(row)
                        await session.flush()
                        evidence_row = TrendEvidenceORM(
                            evidence_id=new_id("tev"),
                            workspace_id=workspace_id,
                            signal_id=row.signal_id,
                            claim=f"Provider observed the topic '{item.topic or item.keyword}'.",
                            summary=item.evidence_summary,
                            source_reference=str(item.source_reference),
                            confidence=Decimal(str(item.evidence_confidence)),
                            freshness=item.freshness,
                            provenance={"source": request.provider_key, "reference_only": True},
                        )
                        session.add(evidence_row)
                        evidence.append(evidence_row)
                        new_count += 1
                    else:
                        existing_evidence = await session.scalar(
                            select(TrendEvidenceORM).where(TrendEvidenceORM.signal_id == row.signal_id)
                        )
                        if existing_evidence is not None:
                            evidence.append(existing_evidence)
                    persisted.append(row)
                snapshot.new_signal_count = new_count
            await session.refresh(snapshot)
            return TrendCollectionResult(
                snapshot=_snapshot_read(snapshot),
                signals=[_signal_read(row) for row in persisted],
                evidence=[_evidence_read(row) for row in evidence],
            )

    async def list_signals(self, workspace_id: str) -> list[TrendSignalRead]:
        async with self.session_factory() as session:
            if await session.get(WorkspaceORM, workspace_id) is None:
                raise KeyError(workspace_id)
            rows = (
                await session.scalars(
                    select(TrendSignalORM)
                    .where(TrendSignalORM.workspace_id == workspace_id)
                    .order_by(TrendSignalORM.observed_at.desc(), TrendSignalORM.signal_id)
                )
            ).all()
            return [_signal_read(row) for row in rows]

    async def refresh_clusters(
        self,
        workspace_id: str,
        request: TrendClusterRefreshRequest,
    ) -> list[TrendClusterRead]:
        as_of = request.as_of or datetime.now(timezone.utc)
        async with self.session_factory() as session:
            async with session.begin():
                if await session.get(WorkspaceORM, workspace_id) is None:
                    raise KeyError(workspace_id)
                signals = (
                    await session.scalars(
                        select(TrendSignalORM)
                        .where(TrendSignalORM.workspace_id == workspace_id)
                        .order_by(TrendSignalORM.observed_at, TrendSignalORM.signal_id)
                    )
                ).all()
                if not signals:
                    return []
                drafts = cluster_signals(
                    list(signals),
                    similarity_threshold=request.similarity_threshold,
                    as_of=as_of,
                )
                by_id = {signal.signal_id: signal for signal in signals}
                refreshed_ids: list[str] = []
                for draft in drafts:
                    cluster_id = "trc_" + hashlib.sha256(
                        f"{workspace_id}|{draft.canonical_key}".encode("utf-8")
                    ).hexdigest()[:24]
                    row = await session.get(TrendClusterORM, cluster_id)
                    values = {
                        "topic": draft.topic,
                        "summary": draft.summary,
                        "lifecycle": draft.lifecycle,
                        "first_observed_at": draft.first_observed_at,
                        "last_observed_at": draft.last_observed_at,
                        "signal_count": len(draft.signal_ids),
                        "platforms_json": draft.platforms,
                        "keywords_json": draft.keywords,
                        "hashtags_json": draft.hashtags,
                    }
                    if row is None:
                        row = TrendClusterORM(
                            cluster_id=cluster_id,
                            workspace_id=workspace_id,
                            canonical_key=draft.canonical_key,
                            provenance={"algorithm": "deterministic-similarity-v1", "estimated": True},
                            **values,
                        )
                        session.add(row)
                        await session.flush()
                    elif any(getattr(row, key) != value for key, value in values.items()):
                        for key, value in values.items():
                            setattr(row, key, value)
                        row.version += 1
                        row.updated_at = utc_now()
                    await session.execute(
                        delete(TrendClusterSignalORM).where(TrendClusterSignalORM.cluster_id == cluster_id)
                    )
                    for signal_id in draft.signal_ids:
                        session.add(
                            TrendClusterSignalORM(
                                cluster_id=cluster_id,
                                signal_id=signal_id,
                                similarity=Decimal(str(draft.similarities[signal_id])),
                            )
                        )
                    score_draft = score_cluster(
                        draft,
                        [by_id[signal_id] for signal_id in draft.signal_ids],
                        request,
                    )
                    score_row = await session.scalar(
                        select(TrendScoreORM).where(
                            TrendScoreORM.cluster_id == cluster_id,
                            TrendScoreORM.profile_hash == score_draft.profile_hash,
                        )
                    )
                    score_values = {
                        "channel": request.channel,
                        "niche": request.niche.value,
                        "business_objective": request.business_objective,
                        "total_score": Decimal(str(score_draft.total_score)),
                        "components_json": score_draft.components,
                        "weights_json": score_draft.weights,
                        "estimated": True,
                    }
                    if score_row is None:
                        session.add(
                            TrendScoreORM(
                                trend_score_id=new_id("tscore"),
                                workspace_id=workspace_id,
                                cluster_id=cluster_id,
                                profile_hash=score_draft.profile_hash,
                                provenance={"algorithm": "trend-opportunity-v1", "observed_performance": False},
                                **score_values,
                            )
                        )
                    elif any(getattr(score_row, key) != value for key, value in score_values.items()):
                        for key, value in score_values.items():
                            setattr(score_row, key, value)
                        score_row.version += 1
                        score_row.updated_at = utc_now()
                    refreshed_ids.append(cluster_id)
            return await self.list_clusters(workspace_id, cluster_ids=refreshed_ids)

    async def _cluster_read(self, session: AsyncSession, row: TrendClusterORM) -> TrendClusterRead:
        score = await session.scalar(
            select(TrendScoreORM)
            .where(TrendScoreORM.cluster_id == row.cluster_id)
            .order_by(TrendScoreORM.updated_at.desc(), TrendScoreORM.created_at.desc())
            .limit(1)
        )
        linked_signals = (
            await session.scalars(
                select(TrendSignalORM)
                .join(TrendClusterSignalORM, TrendClusterSignalORM.signal_id == TrendSignalORM.signal_id)
                .where(TrendClusterSignalORM.cluster_id == row.cluster_id)
                .order_by(TrendSignalORM.source_reference)
            )
        ).all()
        return TrendClusterRead(
            cluster_id=row.cluster_id,
            workspace_id=row.workspace_id,
            canonical_key=row.canonical_key,
            topic=row.topic,
            summary=row.summary,
            lifecycle=row.lifecycle,
            first_observed_at=row.first_observed_at,
            last_observed_at=row.last_observed_at,
            signal_count=row.signal_count,
            platforms=row.platforms_json,
            countries=sorted({item.country for item in linked_signals if item.country}),
            languages=sorted({item.language for item in linked_signals if item.language}),
            formats=sorted({item.format for item in linked_signals if item.format}),
            keywords=row.keywords_json,
            hashtags=row.hashtags_json,
            score=_score_read(score) if score else None,
            source_references=[item.source_reference for item in linked_signals],
            version=row.version,
            provenance=row.provenance,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def list_clusters(
        self,
        workspace_id: str,
        *,
        cluster_ids: list[str] | None = None,
    ) -> list[TrendClusterRead]:
        query = select(TrendClusterORM).where(TrendClusterORM.workspace_id == workspace_id)
        if cluster_ids is not None:
            query = query.where(TrendClusterORM.cluster_id.in_(cluster_ids))
        query = query.order_by(TrendClusterORM.updated_at.desc(), TrendClusterORM.topic)
        async with self.session_factory() as session:
            if await session.get(WorkspaceORM, workspace_id) is None:
                raise KeyError(workspace_id)
            rows = (await session.scalars(query)).all()
            results = [await self._cluster_read(session, row) for row in rows]
            return sorted(
                results,
                key=lambda item: (-(item.score.total_score if item.score else -1), item.topic.casefold()),
            )

    async def get_cluster(self, cluster_id: str) -> TrendClusterRead | None:
        async with self.session_factory() as session:
            row = await session.get(TrendClusterORM, cluster_id)
            return await self._cluster_read(session, row) if row else None

    async def _cluster_inputs(
        self,
        session: AsyncSession,
        cluster_id: str,
    ) -> tuple[TrendClusterORM, list[TrendSignalORM], list[TrendEvidenceORM]]:
        cluster = await session.get(TrendClusterORM, cluster_id)
        if cluster is None:
            raise KeyError(cluster_id)
        signals = (
            await session.scalars(
                select(TrendSignalORM)
                .join(TrendClusterSignalORM, TrendClusterSignalORM.signal_id == TrendSignalORM.signal_id)
                .where(TrendClusterSignalORM.cluster_id == cluster_id)
                .order_by(TrendSignalORM.source, TrendSignalORM.signal_id)
            )
        ).all()
        evidence = (
            await session.scalars(
                select(TrendEvidenceORM)
                .where(TrendEvidenceORM.signal_id.in_([item.signal_id for item in signals]))
                .order_by(TrendEvidenceORM.source_reference)
            )
        ).all()
        return cluster, list(signals), list(evidence)

    async def generate_ideas(
        self,
        cluster_id: str,
        request: IdeaGenerateRequest,
        *,
        engine: IdeaEngine,
    ) -> list[IdeaCandidateRead]:
        trend_request = _trend_request_from_idea(request)
        async with self.session_factory() as session:
            async with session.begin():
                cluster, signals, evidence = await self._cluster_inputs(session, cluster_id)
                topic, canonical_key = cluster.topic, cluster.canonical_key
                draft = ClusterDraft(
                    canonical_key=canonical_key,
                    topic=topic,
                    summary=cluster.summary,
                    lifecycle=cluster.lifecycle,
                    first_observed_at=cluster.first_observed_at,
                    last_observed_at=cluster.last_observed_at,
                    signal_ids=[item.signal_id for item in signals],
                    similarities={item.signal_id: 1.0 for item in signals},
                    platforms=cluster.platforms_json,
                    keywords=cluster.keywords_json,
                    hashtags=cluster.hashtags_json,
                )
                score_draft = score_cluster(draft, signals, trend_request)
                generation_payload = {
                    "algorithm": "deterministic-idea-engine-v1",
                    "cluster_id": cluster_id,
                    "cluster_version": cluster.version,
                    "request": request.model_dump(mode="json", exclude={"count"}),
                }
                generation_key = hashlib.sha256(
                    json.dumps(generation_payload, sort_keys=True).encode("utf-8")
                ).hexdigest()
                existing = (
                    await session.scalars(
                        select(IdeaCandidateORM)
                        .where(
                            IdeaCandidateORM.cluster_id == cluster_id,
                            IdeaCandidateORM.generation_key == generation_key,
                        )
                        .order_by(IdeaCandidateORM.variant_key)
                    )
                ).all()
                created: list[tuple[IdeaCandidateORM, IdeaScoreORM]] = []
                for row in existing:
                    score = await session.scalar(select(IdeaScoreORM).where(IdeaScoreORM.idea_id == row.idea_id))
                    if score is None:
                        raise RuntimeError("idea candidate is missing its score")
                    created.append((row, score))
                if len(created) >= request.count:
                    return [_idea_read(row, score) for row, score in created[: request.count]]
                source_references = sorted({item.source_reference for item in signals})
                evidence_summaries = [item.summary for item in evidence]
                drafts = engine.generate(
                    topic=cluster.topic,
                    trend_score=score_draft,
                    lifecycle=cluster.lifecycle,
                    source_references=source_references,
                    evidence_summaries=evidence_summaries,
                    request=request,
                )
                existing_variants = {row.variant_key for row in existing}
                for idea in drafts:
                    if idea.variant_key in existing_variants:
                        continue
                    row = IdeaCandidateORM(
                        idea_id=new_id("idea"),
                        workspace_id=cluster.workspace_id,
                        cluster_id=cluster_id,
                        generation_key=generation_key,
                        variant_key=idea.variant_key,
                        channel=request.channel,
                        niche=request.niche.value,
                        business_objective=request.business_objective,
                        title=idea.title,
                        angle=idea.angle,
                        hook_concept=idea.hook_concept,
                        format=idea.format,
                        recommended_duration_seconds=idea.recommended_duration_seconds,
                        visual_concept=idea.visual_concept,
                        audience=idea.audience,
                        cta_concept=idea.cta_concept,
                        trend_references_json=idea.trend_references,
                        originality_notes=idea.originality_notes,
                        brief_json=idea.brief,
                        status="draft",
                        provenance={
                            "algorithm": "deterministic-idea-engine-v1",
                            "source_references_only": True,
                            "copied_creator_media": False,
                        },
                    )
                    session.add(row)
                    await session.flush()
                    score = IdeaScoreORM(
                        idea_score_id=new_id("iscore"),
                        workspace_id=cluster.workspace_id,
                        idea_id=row.idea_id,
                        total_score=Decimal(str(idea.total_score)),
                        components_json=idea.score_components,
                        estimated=True,
                        rationale_json=idea.rationale,
                        provenance={"algorithm": "idea-score-v1", "observed_performance": False},
                    )
                    session.add(score)
                    for item in evidence:
                        session.add(
                            ResearchEvidenceORM(
                                research_evidence_id=new_id("rev"),
                                workspace_id=cluster.workspace_id,
                                idea_id=row.idea_id,
                                claim=item.claim,
                                summary=item.summary,
                                source_reference=item.source_reference,
                                confidence=item.confidence,
                                freshness=item.freshness,
                                fact_class="verified_fact",
                                provenance={"source": "trend-evidence", "reference_only": True},
                            )
                        )
                    created.append((row, score))
            return [_idea_read(row, score) for row, score in created[: request.count]]

    async def list_ideas(self, workspace_id: str) -> list[IdeaCandidateRead]:
        async with self.session_factory() as session:
            if await session.get(WorkspaceORM, workspace_id) is None:
                raise KeyError(workspace_id)
            rows = (
                await session.scalars(
                    select(IdeaCandidateORM)
                    .where(IdeaCandidateORM.workspace_id == workspace_id)
                    .order_by(IdeaCandidateORM.created_at.desc(), IdeaCandidateORM.idea_id)
                )
            ).all()
            output: list[IdeaCandidateRead] = []
            for row in rows:
                score = await session.scalar(select(IdeaScoreORM).where(IdeaScoreORM.idea_id == row.idea_id))
                if score is None:
                    raise RuntimeError("idea candidate is missing its score")
                output.append(_idea_read(row, score))
            return output

    async def get_idea(self, idea_id: str) -> IdeaCandidateRead | None:
        async with self.session_factory() as session:
            row = await session.get(IdeaCandidateORM, idea_id)
            if row is None:
                return None
            score = await session.scalar(select(IdeaScoreORM).where(IdeaScoreORM.idea_id == idea_id))
            if score is None:
                raise RuntimeError("idea candidate is missing its score")
            return _idea_read(row, score)

    async def refresh_queue(
        self,
        workspace_id: str,
        request: ContentQueueRefreshRequest,
    ) -> list[ContentQueueItemRead]:
        async with self.session_factory() as session:
            async with session.begin():
                if await session.get(WorkspaceORM, workspace_id) is None:
                    raise KeyError(workspace_id)
                ideas = (
                    await session.scalars(
                        select(IdeaCandidateORM).where(
                            IdeaCandidateORM.workspace_id == workspace_id,
                            IdeaCandidateORM.channel == request.channel,
                            IdeaCandidateORM.niche == request.niche.value,
                            IdeaCandidateORM.business_objective == request.business_objective,
                        )
                    )
                ).all()
                scored: list[tuple[IdeaCandidateORM, IdeaScoreORM, TrendScoreORM | None]] = []
                for idea in ideas:
                    idea_score = await session.scalar(
                        select(IdeaScoreORM).where(IdeaScoreORM.idea_id == idea.idea_id)
                    )
                    trend_score = await session.scalar(
                        select(TrendScoreORM)
                        .where(
                            TrendScoreORM.cluster_id == idea.cluster_id,
                            TrendScoreORM.channel == request.channel,
                            TrendScoreORM.niche == request.niche.value,
                            TrendScoreORM.business_objective == request.business_objective,
                        )
                        .order_by(TrendScoreORM.updated_at.desc())
                        .limit(1)
                    )
                    if idea_score is not None:
                        scored.append((idea, idea_score, trend_score))
                scored.sort(
                    key=lambda item: (
                        -(
                            float(item[1].total_score) * 0.72
                            + (float(item[2].total_score) if item[2] else 0.0) * 0.28
                        ),
                        item[0].idea_id,
                    )
                )
                selected = scored[: request.top_n]
                state_payload = {
                    "algorithm": "content-opportunity-queue-v1",
                    "request": request.model_dump(mode="json"),
                    "ideas": [(item[0].idea_id, str(item[1].total_score)) for item in selected],
                }
                queue_run_id = "qrun_" + hashlib.sha256(
                    json.dumps(state_payload, sort_keys=True).encode("utf-8")
                ).hexdigest()[:24]
                existing_items = (
                    await session.scalars(
                        select(ContentQueueItemORM)
                        .where(ContentQueueItemORM.queue_run_id == queue_run_id)
                        .order_by(ContentQueueItemORM.rank)
                    )
                ).all()
                if existing_items:
                    return await self._queue_reads(session, list(existing_items))
                rows: list[ContentQueueItemORM] = []
                for rank, (idea, idea_score, trend_score) in enumerate(selected, start=1):
                    rank_score = round(
                        float(idea_score.total_score) * 0.72
                        + (float(trend_score.total_score) if trend_score else 0.0) * 0.28,
                        3,
                    )
                    opportunity = await session.scalar(
                        select(ChannelOpportunityORM).where(
                            ChannelOpportunityORM.workspace_id == workspace_id,
                            ChannelOpportunityORM.idea_id == idea.idea_id,
                            ChannelOpportunityORM.channel == request.channel,
                        )
                    )
                    rationale = [
                        f"Idea estimate: {float(idea_score.total_score):.1f}/100.",
                        f"Trend estimate: {float(trend_score.total_score) if trend_score else 0.0:.1f}/100.",
                        "Rank is a planning estimate, not observed performance.",
                    ]
                    if opportunity is None:
                        opportunity = ChannelOpportunityORM(
                            opportunity_id=new_id("opp"),
                            workspace_id=workspace_id,
                            cluster_id=idea.cluster_id,
                            idea_id=idea.idea_id,
                            channel=request.channel,
                            rank_score=Decimal(str(rank_score)),
                            rationale_json=rationale,
                            status="proposed",
                            provenance={"algorithm": "content-opportunity-queue-v1"},
                        )
                        session.add(opportunity)
                        await session.flush()
                    else:
                        opportunity.rank_score = Decimal(str(rank_score))
                        opportunity.rationale_json = rationale
                        opportunity.version += 1
                        opportunity.updated_at = utc_now()
                    row = ContentQueueItemORM(
                        queue_item_id=new_id("queue"),
                        queue_run_id=queue_run_id,
                        workspace_id=workspace_id,
                        opportunity_id=opportunity.opportunity_id,
                        cluster_id=idea.cluster_id,
                        idea_id=idea.idea_id,
                        channel=request.channel,
                        rank=rank,
                        score=Decimal(str(rank_score)),
                        state="proposed",
                        evidence_summary_json=rationale,
                        provenance={"algorithm": "content-opportunity-queue-v1", "execution": False},
                    )
                    session.add(row)
                    rows.append(row)
                await session.flush()
            return await self._queue_reads_external(rows)

    async def _queue_reads(
        self,
        session: AsyncSession,
        rows: list[ContentQueueItemORM],
    ) -> list[ContentQueueItemRead]:
        output: list[ContentQueueItemRead] = []
        for row in rows:
            idea = await session.get(IdeaCandidateORM, row.idea_id)
            if idea is None:
                raise RuntimeError("queue item is missing its idea")
            score = await session.scalar(select(IdeaScoreORM).where(IdeaScoreORM.idea_id == row.idea_id))
            if score is None:
                raise RuntimeError("queue item idea is missing its score")
            output.append(
                ContentQueueItemRead(
                    queue_item_id=row.queue_item_id,
                    queue_run_id=row.queue_run_id,
                    workspace_id=row.workspace_id,
                    opportunity_id=row.opportunity_id,
                    cluster_id=row.cluster_id,
                    idea_id=row.idea_id,
                    channel=row.channel,
                    rank=row.rank,
                    score=float(row.score),
                    state=row.state,
                    evidence_summary=row.evidence_summary_json,
                    generated_at=row.generated_at,
                    idea=_idea_read(idea, score),
                    version=row.version,
                    provenance=row.provenance,
                )
            )
        return output

    async def _queue_reads_external(self, rows: list[ContentQueueItemORM]) -> list[ContentQueueItemRead]:
        if not rows:
            return []
        async with self.session_factory() as session:
            persisted = (
                await session.scalars(
                    select(ContentQueueItemORM)
                    .where(ContentQueueItemORM.queue_run_id == rows[0].queue_run_id)
                    .order_by(ContentQueueItemORM.rank)
                )
            ).all()
            return await self._queue_reads(session, list(persisted))

    async def list_queue(self, workspace_id: str) -> list[ContentQueueItemRead]:
        async with self.session_factory() as session:
            if await session.get(WorkspaceORM, workspace_id) is None:
                raise KeyError(workspace_id)
            latest = await session.scalar(
                select(ContentQueueItemORM)
                .where(ContentQueueItemORM.workspace_id == workspace_id)
                .order_by(ContentQueueItemORM.generated_at.desc())
                .limit(1)
            )
            if latest is None:
                return []
            rows = (
                await session.scalars(
                    select(ContentQueueItemORM)
                    .where(ContentQueueItemORM.queue_run_id == latest.queue_run_id)
                    .order_by(ContentQueueItemORM.rank)
                )
            ).all()
            return await self._queue_reads(session, list(rows))

    async def link_idea_project(self, idea_id: str, project_id: str) -> IdeaCandidateRead:
        async with self.session_factory() as session:
            async with session.begin():
                idea = await session.get(IdeaCandidateORM, idea_id)
                project = await session.get(VideoProjectORM, project_id)
                if idea is None or project is None or idea.workspace_id != project.workspace_id:
                    raise KeyError(idea_id)
                if idea.project_id != project_id or idea.status != "selected":
                    idea.project_id = project_id
                    idea.status = "selected"
                    idea.version += 1
                    idea.updated_at = utc_now()
            score = await session.scalar(select(IdeaScoreORM).where(IdeaScoreORM.idea_id == idea_id))
            if score is None:
                raise RuntimeError("idea candidate is missing its score")
            return _idea_read(idea, score)
