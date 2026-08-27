from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .auto_edit_db import (
    AutoEditAnalysisORM,
    HighlightORM,
    SceneORM,
    SilenceDecisionORM,
    TranscriptORM,
    TranscriptSegmentORM,
    TranscriptWordORM,
    UploadSessionORM,
)
from .auto_edit_models import (
    AutoEditAnalysisRead,
    AutoEditAnalysisRequest,
    HighlightRead,
    MediaMetadata,
    SceneRead,
    SilenceDecisionRead,
    TranscriptRead,
    TranscriptSegmentRead,
    TranscriptWordRead,
    UploadInitRequest,
    UploadPartRead,
    UploadRead,
)
from .auto_edit_providers import ProviderTranscript
from .db import AssetORM, ProjectVersionORM, VideoProjectORM, utc_now
from .platform_models import AssetRead


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _asset_read(row: AssetORM) -> AssetRead:
    return AssetRead(
        asset_id=row.asset_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        project_version_id=row.project_version_id,
        job_id=row.job_id,
        asset_class=row.asset_class,
        kind=row.kind,
        filename=row.filename,
        object_key=row.object_key,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        checksum_sha256=row.checksum_sha256,
        storage_provider=row.storage_provider,
        version=row.version,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _upload_read(row: UploadSessionORM) -> UploadRead:
    parts = [UploadPartRead.model_validate(item) for item in row.received_parts_json]
    parts.sort(key=lambda item: item.part_number)
    return UploadRead(
        upload_id=row.upload_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        project_version_id=row.project_version_id,
        original_filename=row.original_filename,
        safe_filename=row.safe_filename,
        media_kind=row.media_kind,
        declared_content_type=row.declared_content_type,
        size_bytes=row.size_bytes,
        expected_checksum_sha256=row.expected_checksum_sha256,
        part_size_bytes=row.part_size_bytes,
        total_parts=row.total_parts,
        rights_status=row.rights_status,
        license=row.license,
        received_parts=parts,
        received_bytes=row.received_bytes,
        status=row.status,
        asset_id=row.asset_id,
        duplicate_of_asset_id=row.duplicate_of_asset_id,
        media_metadata=(
            MediaMetadata.model_validate(row.media_metadata_json) if row.media_metadata_json else None
        ),
        error_code=row.error_code,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AutoEditRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def create_upload(
        self,
        *,
        upload_id: str,
        payload: UploadInitRequest,
        safe_filename: str,
        part_size_bytes: int,
        total_parts: int,
    ) -> UploadRead:
        async with self.session_factory() as session:
            project = await session.get(VideoProjectORM, payload.project_id)
            if project is None:
                raise KeyError(payload.project_id)
            if payload.project_version_id:
                version = await session.get(ProjectVersionORM, payload.project_version_id)
                if version is None or version.project_id != payload.project_id:
                    raise KeyError(payload.project_version_id)
            row = UploadSessionORM(
                upload_id=upload_id,
                workspace_id=project.workspace_id,
                project_id=payload.project_id,
                project_version_id=payload.project_version_id,
                original_filename=payload.filename,
                safe_filename=safe_filename,
                media_kind=payload.media_kind,
                declared_content_type=payload.content_type.split(";", 1)[0].strip().lower(),
                size_bytes=payload.size_bytes,
                expected_checksum_sha256=payload.checksum_sha256,
                part_size_bytes=part_size_bytes,
                total_parts=total_parts,
                received_parts_json=[],
                received_bytes=0,
                status="initialized",
                rights_status=payload.rights_status,
                license=payload.license,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _upload_read(row)

    async def get_upload(self, upload_id: str) -> UploadRead | None:
        async with self.session_factory() as session:
            row = await session.get(UploadSessionORM, upload_id)
            return _upload_read(row) if row else None

    async def record_part(self, upload_id: str, part: UploadPartRead) -> UploadRead:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    select(UploadSessionORM)
                    .where(UploadSessionORM.upload_id == upload_id)
                    .with_for_update()
                )
                if row is None:
                    raise KeyError(upload_id)
                if row.status not in {"initialized", "uploading"}:
                    raise ValueError("upload is not accepting parts")
                parts = [item for item in row.received_parts_json if item["part_number"] != part.part_number]
                parts.append(part.model_dump(mode="json"))
                parts.sort(key=lambda item: item["part_number"])
                row.received_parts_json = parts
                row.received_bytes = sum(int(item["size_bytes"]) for item in parts)
                row.status = "uploading"
                row.updated_at = utc_now()
            await session.refresh(row)
            return _upload_read(row)

    async def mark_upload_failed(self, upload_id: str, error_code: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(UploadSessionORM, upload_id)
            if row is None:
                return
            row.status = "failed"
            row.error_code = error_code
            row.updated_at = utc_now()
            await session.commit()

    async def finish_upload(
        self,
        upload_id: str,
        *,
        asset_id: str,
        duplicate_of_asset_id: str | None,
        media_metadata: MediaMetadata,
    ) -> UploadRead:
        async with self.session_factory() as session:
            row = await session.get(UploadSessionORM, upload_id)
            if row is None:
                raise KeyError(upload_id)
            row.asset_id = asset_id
            row.duplicate_of_asset_id = duplicate_of_asset_id
            row.media_metadata_json = media_metadata.model_dump(mode="json")
            row.status = "completed_duplicate" if duplicate_of_asset_id else "completed"
            row.error_code = None
            row.updated_at = utc_now()
            await session.commit()
            await session.refresh(row)
            return _upload_read(row)

    async def get_asset(self, asset_id: str) -> AssetRead | None:
        async with self.session_factory() as session:
            row = await session.get(AssetORM, asset_id)
            return _asset_read(row) if row else None

    async def find_duplicate_asset(
        self, *, project_id: str, checksum_sha256: str, size_bytes: int
    ) -> AssetRead | None:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(AssetORM)
                .where(
                    AssetORM.project_id == project_id,
                    AssetORM.checksum_sha256 == checksum_sha256,
                    AssetORM.size_bytes == size_bytes,
                    AssetORM.asset_class == "source",
                )
                .order_by(AssetORM.created_at)
            )
            return _asset_read(row) if row else None

    async def create_analysis(
        self,
        *,
        project_id: str,
        asset: AssetRead,
        fingerprint: str,
        configuration: AutoEditAnalysisRequest,
        source_media: MediaMetadata,
        provenance: dict[str, Any],
    ) -> tuple[str, bool]:
        async with self.session_factory() as session:
            project = await session.get(VideoProjectORM, project_id)
            if project is None or asset.project_id != project_id:
                raise KeyError(project_id)
            existing = await session.scalar(
                select(AutoEditAnalysisORM).where(
                    AutoEditAnalysisORM.project_id == project_id,
                    AutoEditAnalysisORM.fingerprint == fingerprint,
                )
            )
            if existing:
                return existing.analysis_id, False
            row = AutoEditAnalysisORM(
                analysis_id=_new_id("ana"),
                workspace_id=asset.workspace_id,
                project_id=project_id,
                project_version_id=asset.project_version_id,
                asset_id=asset.asset_id,
                status="pending",
                fingerprint=fingerprint,
                configuration_json=configuration.model_dump(mode="json"),
                source_media_json=source_media.model_dump(mode="json"),
                provenance_json=provenance,
            )
            session.add(row)
            try:
                await session.commit()
                return row.analysis_id, True
            except IntegrityError:
                # Two identical requests can pass the read check concurrently.
                # The unique fingerprint is the authority; recover the winner
                # after rollback so replay stays idempotent instead of surfacing
                # a database exception.
                await session.rollback()
                existing = await session.scalar(
                    select(AutoEditAnalysisORM).where(
                        AutoEditAnalysisORM.project_id == project_id,
                        AutoEditAnalysisORM.fingerprint == fingerprint,
                    )
                )
                if existing is None:
                    raise
                return existing.analysis_id, False

    async def mark_analysis_running(self, analysis_id: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(AutoEditAnalysisORM, analysis_id)
            if row is None:
                raise KeyError(analysis_id)
            row.status = "analyzing"
            row.updated_at = utc_now()
            await session.commit()

    async def mark_analysis_failed(self, analysis_id: str, error_code: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(AutoEditAnalysisORM, analysis_id)
            if row is None:
                return
            row.status = "failed"
            row.error_code = error_code
            row.updated_at = utc_now()
            await session.commit()

    async def save_analysis_results(
        self,
        *,
        analysis_id: str,
        asset_id: str,
        provider_key: str,
        transcript: ProviderTranscript,
        scenes: list[dict[str, Any]],
        silence_decisions: list[dict[str, Any]],
        highlights: list[dict[str, Any]],
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                analysis = await session.scalar(
                    select(AutoEditAnalysisORM)
                    .where(AutoEditAnalysisORM.analysis_id == analysis_id)
                    .with_for_update()
                )
                if analysis is None:
                    raise KeyError(analysis_id)
                if analysis.status == "succeeded":
                    return
                transcript_id = _new_id("trn")
                session.add(
                    TranscriptORM(
                        transcript_id=transcript_id,
                        analysis_id=analysis_id,
                        asset_id=asset_id,
                        version=1,
                        is_original_evidence=True,
                        provider_key=provider_key,
                        language=transcript.language,
                        confidence=transcript.confidence,
                        provenance_json=transcript.provenance,
                    )
                )
                word_ordinal = 0
                for segment_ordinal, segment in enumerate(transcript.segments):
                    segment_id = _new_id("seg")
                    session.add(
                        TranscriptSegmentORM(
                            segment_id=segment_id,
                            transcript_id=transcript_id,
                            ordinal=segment_ordinal,
                            start_seconds=segment.start_seconds,
                            end_seconds=segment.end_seconds,
                            text=segment.text,
                            speaker=segment.speaker,
                            confidence=segment.confidence,
                        )
                    )
                    for word in segment.words:
                        session.add(
                            TranscriptWordORM(
                                word_id=_new_id("wrd"),
                                transcript_id=transcript_id,
                                segment_id=segment_id,
                                ordinal=word_ordinal,
                                start_seconds=word.start_seconds,
                                end_seconds=word.end_seconds,
                                text=word.text,
                                confidence=word.confidence,
                            )
                        )
                        word_ordinal += 1
                scene_ids: dict[int, str] = {}
                for item in scenes:
                    scene_id = _new_id("scn")
                    scene_ids[int(item["ordinal"])] = scene_id
                    session.add(
                        SceneORM(
                            scene_id=scene_id,
                            analysis_id=analysis_id,
                            ordinal=item["ordinal"],
                            start_seconds=item["start_seconds"],
                            end_seconds=item["end_seconds"],
                            semantic_label=item["semantic_label"],
                            description=item["description"],
                            subjects_json=item["subjects"],
                            quality_score=item["quality_score"],
                            motion_score=item["motion_score"],
                            speech_score=item["speech_score"],
                            confidence=item["confidence"],
                            evidence_json=item["evidence"],
                        )
                    )
                # Highlights reference scenes created in this same transaction.  An
                # explicit flush keeps the dependency order deterministic across
                # PostgreSQL and SQLite instead of relying on ORM mapper ordering.
                await session.flush()
                for item in silence_decisions:
                    session.add(
                        SilenceDecisionORM(
                            decision_id=_new_id("sil"),
                            analysis_id=analysis_id,
                            start_seconds=item["start_seconds"],
                            end_seconds=item["end_seconds"],
                            padding_before_seconds=item["padding_before_seconds"],
                            padding_after_seconds=item["padding_after_seconds"],
                            enabled=item["enabled"],
                            reason=item["reason"],
                            conflicts_with_speech=item["conflicts_with_speech"],
                            evidence_json=item["evidence"],
                        )
                    )
                for item in highlights:
                    session.add(
                        HighlightORM(
                            highlight_id=_new_id("hlt"),
                            analysis_id=analysis_id,
                            scene_id=scene_ids.get(int(item["scene_ordinal"])),
                            rank=item["rank"],
                            highlight_score=item["highlight_score"],
                            reason=item["reason"],
                            recommended_start=item["recommended_start"],
                            recommended_end=item["recommended_end"],
                            recommended_platform=item["recommended_platform"],
                            evidence_json=item["evidence"],
                        )
                    )
                analysis.status = "succeeded"
                analysis.error_code = None
                analysis.updated_at = utc_now()

    async def get_analysis(self, analysis_id: str) -> AutoEditAnalysisRead | None:
        async with self.session_factory() as session:
            analysis = await session.get(AutoEditAnalysisORM, analysis_id)
            if analysis is None:
                return None
            transcript_row = await session.scalar(
                select(TranscriptORM)
                .where(TranscriptORM.analysis_id == analysis_id)
                .order_by(TranscriptORM.version.desc())
            )
            transcript_read: TranscriptRead | None = None
            if transcript_row:
                segment_rows = (
                    await session.scalars(
                        select(TranscriptSegmentORM)
                        .where(TranscriptSegmentORM.transcript_id == transcript_row.transcript_id)
                        .order_by(TranscriptSegmentORM.ordinal)
                    )
                ).all()
                word_rows = (
                    await session.scalars(
                        select(TranscriptWordORM)
                        .where(TranscriptWordORM.transcript_id == transcript_row.transcript_id)
                        .order_by(TranscriptWordORM.ordinal)
                    )
                ).all()
                words_by_segment: dict[str, list[TranscriptWordRead]] = {}
                for word in word_rows:
                    words_by_segment.setdefault(word.segment_id, []).append(
                        TranscriptWordRead(
                            word_id=word.word_id,
                            ordinal=word.ordinal,
                            start_seconds=word.start_seconds,
                            end_seconds=word.end_seconds,
                            text=word.text,
                            confidence=word.confidence,
                        )
                    )
                transcript_read = TranscriptRead(
                    transcript_id=transcript_row.transcript_id,
                    analysis_id=analysis_id,
                    asset_id=transcript_row.asset_id,
                    version=transcript_row.version,
                    is_original_evidence=transcript_row.is_original_evidence,
                    provider_key=transcript_row.provider_key,
                    language=transcript_row.language,
                    confidence=transcript_row.confidence,
                    segments=[
                        TranscriptSegmentRead(
                            segment_id=segment.segment_id,
                            ordinal=segment.ordinal,
                            start_seconds=segment.start_seconds,
                            end_seconds=segment.end_seconds,
                            text=segment.text,
                            speaker=segment.speaker,
                            confidence=segment.confidence,
                            words=words_by_segment.get(segment.segment_id, []),
                        )
                        for segment in segment_rows
                    ],
                    provenance=transcript_row.provenance_json,
                    created_at=transcript_row.created_at,
                )
            scene_rows = (
                await session.scalars(
                    select(SceneORM).where(SceneORM.analysis_id == analysis_id).order_by(SceneORM.ordinal)
                )
            ).all()
            silence_rows = (
                await session.scalars(
                    select(SilenceDecisionORM)
                    .where(SilenceDecisionORM.analysis_id == analysis_id)
                    .order_by(SilenceDecisionORM.start_seconds)
                )
            ).all()
            highlight_rows = (
                await session.scalars(
                    select(HighlightORM)
                    .where(HighlightORM.analysis_id == analysis_id)
                    .order_by(HighlightORM.rank)
                )
            ).all()
            return AutoEditAnalysisRead(
                analysis_id=analysis.analysis_id,
                workspace_id=analysis.workspace_id,
                project_id=analysis.project_id,
                project_version_id=analysis.project_version_id,
                asset_id=analysis.asset_id,
                status=analysis.status,
                fingerprint=analysis.fingerprint,
                configuration=AutoEditAnalysisRequest.model_validate(analysis.configuration_json),
                source_media=MediaMetadata.model_validate(analysis.source_media_json),
                transcript=transcript_read,
                scenes=[
                    SceneRead(
                        scene_id=row.scene_id,
                        ordinal=row.ordinal,
                        start_seconds=row.start_seconds,
                        end_seconds=row.end_seconds,
                        semantic_label=row.semantic_label,
                        description=row.description,
                        subjects=row.subjects_json,
                        quality_score=row.quality_score,
                        motion_score=row.motion_score,
                        speech_score=row.speech_score,
                        confidence=row.confidence,
                        evidence=row.evidence_json,
                    )
                    for row in scene_rows
                ],
                silence_decisions=[
                    SilenceDecisionRead(
                        decision_id=row.decision_id,
                        start_seconds=row.start_seconds,
                        end_seconds=row.end_seconds,
                        padding_before_seconds=row.padding_before_seconds,
                        padding_after_seconds=row.padding_after_seconds,
                        enabled=row.enabled,
                        reason=row.reason,
                        conflicts_with_speech=row.conflicts_with_speech,
                        evidence=row.evidence_json,
                    )
                    for row in silence_rows
                ],
                highlights=[
                    HighlightRead(
                        highlight_id=row.highlight_id,
                        rank=row.rank,
                        highlight_score=row.highlight_score,
                        reason=row.reason,
                        recommended_start=row.recommended_start,
                        recommended_end=row.recommended_end,
                        recommended_platform=row.recommended_platform,
                        scene_id=row.scene_id,
                        evidence=row.evidence_json,
                    )
                    for row in highlight_rows
                ],
                error_code=analysis.error_code,
                provenance=analysis.provenance_json,
                created_at=analysis.created_at,
                updated_at=analysis.updated_at,
            )

    async def list_analyses(self, project_id: str) -> list[AutoEditAnalysisRead]:
        async with self.session_factory() as session:
            identifiers = (
                await session.scalars(
                    select(AutoEditAnalysisORM.analysis_id)
                    .where(AutoEditAnalysisORM.project_id == project_id)
                    .order_by(AutoEditAnalysisORM.created_at.desc())
                )
            ).all()
        return [item for identifier in identifiers if (item := await self.get_analysis(identifier))]
