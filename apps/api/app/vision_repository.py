from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .auto_edit_db import AutoEditAnalysisORM
from .auto_edit_models import AutoEditAnalysisRead, MediaMetadata
from .db import utc_now
from .platform_models import AssetRead
from .vision_db import (
    VisionAnalysisORM,
    VisionFrameORM,
    VisionReframePlanORM,
    VisionSceneInsightORM,
    VisionSubjectTrackORM,
)
from .vision_models import (
    FrameCompositionRead,
    FrameQualityRead,
    ObjectDetectionRead,
    OCRDetectionRead,
    ReframeKeyframeRead,
    ReframePlanRead,
    SubjectObservationRead,
    SubjectTrackRead,
    VisionAnalysisRead,
    VisionAnalysisRequest,
    VisionFrameRead,
    VisionSceneRead,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


class VisionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def create_analysis(
        self,
        *,
        base_analysis: AutoEditAnalysisRead,
        asset: AssetRead,
        fingerprint: str,
        configuration: VisionAnalysisRequest,
        provider_key: str,
        model: str,
        provenance: dict[str, Any],
    ) -> tuple[str, bool]:
        async with self.session_factory() as session:
            base = await session.get(AutoEditAnalysisORM, base_analysis.analysis_id)
            if (
                base is None
                or base.project_id != base_analysis.project_id
                or base.status != "succeeded"
                or asset.asset_id != base.asset_id
            ):
                raise KeyError(base_analysis.analysis_id)
            existing = await session.scalar(
                select(VisionAnalysisORM).where(
                    VisionAnalysisORM.project_id == base.project_id,
                    VisionAnalysisORM.fingerprint == fingerprint,
                )
            )
            if existing:
                return existing.vision_analysis_id, False
            row = VisionAnalysisORM(
                vision_analysis_id=_new_id("vis"),
                workspace_id=base.workspace_id,
                project_id=base.project_id,
                project_version_id=base.project_version_id,
                analysis_id=base.analysis_id,
                asset_id=base.asset_id,
                status="pending",
                fingerprint=fingerprint,
                configuration_json=configuration.model_dump(mode="json"),
                source_media_json=base.source_media_json,
                provider_key=provider_key,
                model=model,
                best_frame_ids_json=[],
                thumbnail_candidate_ids_json=[],
                provenance_json=provenance,
            )
            session.add(row)
            try:
                await session.commit()
                return row.vision_analysis_id, True
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(VisionAnalysisORM).where(
                        VisionAnalysisORM.project_id == base.project_id,
                        VisionAnalysisORM.fingerprint == fingerprint,
                    )
                )
                if existing is None:
                    raise
                return existing.vision_analysis_id, False

    async def mark_running(self, vision_analysis_id: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(VisionAnalysisORM, vision_analysis_id)
            if row is None:
                raise KeyError(vision_analysis_id)
            row.status = "analyzing"
            row.updated_at = utc_now()
            await session.commit()

    async def mark_failed(self, vision_analysis_id: str, error_code: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(VisionAnalysisORM, vision_analysis_id)
            if row is None:
                return
            row.status = "failed"
            row.error_code = error_code
            row.updated_at = utc_now()
            await session.commit()

    async def save_results(
        self,
        *,
        vision_analysis_id: str,
        frames: list[VisionFrameRead],
        scenes: list[VisionSceneRead],
        tracks: list[SubjectTrackRead],
        reframe_plans: list[ReframePlanRead],
        best_frame_ids: list[str],
        thumbnail_candidate_ids: list[str],
        provider_provenance: dict[str, Any],
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                analysis = await session.scalar(
                    select(VisionAnalysisORM)
                    .where(VisionAnalysisORM.vision_analysis_id == vision_analysis_id)
                    .with_for_update()
                )
                if analysis is None:
                    raise KeyError(vision_analysis_id)
                if analysis.status == "succeeded":
                    return
                for ordinal, item in enumerate(frames):
                    session.add(
                        VisionFrameORM(
                            frame_id=item.frame_id,
                            vision_analysis_id=vision_analysis_id,
                            ordinal=ordinal,
                            timestamp_seconds=item.timestamp_seconds,
                            evidence_frame_reference=item.evidence_frame_reference,
                            caption=item.caption,
                            scene_description=item.scene_description,
                            semantic_label=item.semantic_label,
                            environment=item.environment,
                            action=item.action,
                            objects_json=[value.model_dump(mode="json") for value in item.objects],
                            ocr_json=[value.model_dump(mode="json") for value in item.ocr],
                            composition_json=item.composition.model_dump(mode="json"),
                            quality_json=item.quality.model_dump(mode="json"),
                            confidence=item.confidence,
                            provider_key=item.provider_key,
                            model=item.model,
                        )
                    )
                for item in scenes:
                    session.add(
                        VisionSceneInsightORM(
                            vision_scene_id=item.vision_scene_id,
                            vision_analysis_id=vision_analysis_id,
                            scene_id=item.scene_id,
                            ordinal=item.ordinal,
                            start_seconds=item.start_seconds,
                            end_seconds=item.end_seconds,
                            semantic_label=item.semantic_label,
                            description=item.description,
                            subjects_json=item.subjects,
                            quality_score=item.quality_score,
                            confidence=item.confidence,
                            evidence_frame_ids_json=item.evidence_frame_ids,
                        )
                    )
                for item in tracks:
                    session.add(
                        VisionSubjectTrackORM(
                            track_id=item.track_id,
                            vision_analysis_id=vision_analysis_id,
                            label=item.label,
                            category=item.category,
                            start_seconds=item.start_seconds,
                            end_seconds=item.end_seconds,
                            confidence=item.confidence,
                            continuity_score=item.continuity_score,
                            observations_json=[value.model_dump(mode="json") for value in item.observations],
                        )
                    )
                await session.flush()
                for item in reframe_plans:
                    session.add(
                        VisionReframePlanORM(
                            reframe_id=item.reframe_id,
                            vision_analysis_id=vision_analysis_id,
                            aspect_ratio=item.aspect_ratio,
                            strategy=item.strategy,
                            subject_track_id=item.subject_track_id,
                            keyframes_json=[value.model_dump(mode="json") for value in item.keyframes],
                            smoothing=item.smoothing,
                            maximum_jump=item.maximum_jump,
                            subtitle_safe_area_bottom=item.subtitle_safe_area_bottom,
                            confidence=item.confidence,
                            fallback=item.fallback,
                            needs_attention=item.needs_attention,
                            manual_override_applied=item.manual_override_applied,
                        )
                    )
                analysis.best_frame_ids_json = best_frame_ids
                analysis.thumbnail_candidate_ids_json = thumbnail_candidate_ids
                analysis.provenance_json = {
                    **analysis.provenance_json,
                    "provider_evidence": provider_provenance,
                }
                analysis.status = "succeeded"
                analysis.error_code = None
                analysis.updated_at = utc_now()

    async def get_analysis(self, vision_analysis_id: str) -> VisionAnalysisRead | None:
        async with self.session_factory() as session:
            analysis = await session.get(VisionAnalysisORM, vision_analysis_id)
            if analysis is None:
                return None
            frame_rows = (
                await session.scalars(
                    select(VisionFrameORM)
                    .where(VisionFrameORM.vision_analysis_id == vision_analysis_id)
                    .order_by(VisionFrameORM.ordinal)
                )
            ).all()
            scene_rows = (
                await session.scalars(
                    select(VisionSceneInsightORM)
                    .where(VisionSceneInsightORM.vision_analysis_id == vision_analysis_id)
                    .order_by(VisionSceneInsightORM.ordinal)
                )
            ).all()
            track_rows = (
                await session.scalars(
                    select(VisionSubjectTrackORM)
                    .where(VisionSubjectTrackORM.vision_analysis_id == vision_analysis_id)
                    .order_by(VisionSubjectTrackORM.track_id)
                )
            ).all()
            reframe_rows = (
                await session.scalars(
                    select(VisionReframePlanORM)
                    .where(VisionReframePlanORM.vision_analysis_id == vision_analysis_id)
                )
            ).all()
            configuration = VisionAnalysisRequest.model_validate(analysis.configuration_json)
            ratio_order = {
                aspect_ratio: ordinal
                for ordinal, aspect_ratio in enumerate(configuration.aspect_ratios)
            }
            reframe_rows.sort(key=lambda row: ratio_order.get(row.aspect_ratio, len(ratio_order)))
            frames = [
                VisionFrameRead(
                    frame_id=row.frame_id,
                    timestamp_seconds=row.timestamp_seconds,
                    evidence_frame_reference=row.evidence_frame_reference,
                    caption=row.caption,
                    scene_description=row.scene_description,
                    semantic_label=row.semantic_label,
                    environment=row.environment,
                    action=row.action,
                    objects=[ObjectDetectionRead.model_validate(item) for item in row.objects_json],
                    ocr=[OCRDetectionRead.model_validate(item) for item in row.ocr_json],
                    composition=FrameCompositionRead.model_validate(row.composition_json),
                    quality=FrameQualityRead.model_validate(row.quality_json),
                    confidence=row.confidence,
                    provider_key=row.provider_key,
                    model=row.model,
                )
                for row in frame_rows
            ]
            tracks = [
                SubjectTrackRead(
                    track_id=row.track_id,
                    label=row.label,
                    category=row.category,
                    start_seconds=row.start_seconds,
                    end_seconds=row.end_seconds,
                    confidence=row.confidence,
                    continuity_score=row.continuity_score,
                    observations=[
                        SubjectObservationRead.model_validate(item) for item in row.observations_json
                    ],
                )
                for row in track_rows
            ]
            return VisionAnalysisRead(
                vision_analysis_id=analysis.vision_analysis_id,
                workspace_id=analysis.workspace_id,
                project_id=analysis.project_id,
                project_version_id=analysis.project_version_id,
                analysis_id=analysis.analysis_id,
                asset_id=analysis.asset_id,
                status=analysis.status,
                fingerprint=analysis.fingerprint,
                configuration=configuration,
                source_media=MediaMetadata.model_validate(analysis.source_media_json),
                provider_key=analysis.provider_key,
                model=analysis.model,
                frames=frames,
                scenes=[
                    VisionSceneRead(
                        vision_scene_id=row.vision_scene_id,
                        scene_id=row.scene_id,
                        ordinal=row.ordinal,
                        start_seconds=row.start_seconds,
                        end_seconds=row.end_seconds,
                        semantic_label=row.semantic_label,
                        description=row.description,
                        subjects=row.subjects_json,
                        quality_score=row.quality_score,
                        confidence=row.confidence,
                        evidence_frame_ids=row.evidence_frame_ids_json,
                    )
                    for row in scene_rows
                ],
                subject_tracks=tracks,
                reframe_plans=[
                    ReframePlanRead(
                        reframe_id=row.reframe_id,
                        aspect_ratio=row.aspect_ratio,
                        strategy=row.strategy,
                        subject_track_id=row.subject_track_id,
                        keyframes=[ReframeKeyframeRead.model_validate(item) for item in row.keyframes_json],
                        smoothing=row.smoothing,
                        maximum_jump=row.maximum_jump,
                        subtitle_safe_area_bottom=row.subtitle_safe_area_bottom,
                        confidence=row.confidence,
                        fallback=row.fallback,
                        needs_attention=row.needs_attention,
                        manual_override_applied=row.manual_override_applied,
                    )
                    for row in reframe_rows
                ],
                best_frame_ids=analysis.best_frame_ids_json,
                thumbnail_candidate_ids=analysis.thumbnail_candidate_ids_json,
                ocr_detection_count=sum(len(frame.ocr) for frame in frames),
                error_code=analysis.error_code,
                provenance=analysis.provenance_json,
                created_at=analysis.created_at,
                updated_at=analysis.updated_at,
            )

    async def list_analyses(self, project_id: str) -> list[VisionAnalysisRead]:
        async with self.session_factory() as session:
            identifiers = (
                await session.scalars(
                    select(VisionAnalysisORM.vision_analysis_id)
                    .where(VisionAnalysisORM.project_id == project_id)
                    .order_by(VisionAnalysisORM.created_at.desc())
                )
            ).all()
        return [item for identifier in identifiers if (item := await self.get_analysis(identifier))]
