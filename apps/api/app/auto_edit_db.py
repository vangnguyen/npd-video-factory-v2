from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class UploadSessionORM(Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        Index("ix_upload_sessions_project_created", "project_id", "created_at"),
    )

    upload_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    project_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_versions.project_version_id", ondelete="SET NULL"), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    safe_filename: Mapped[str] = mapped_column(String(128), nullable=False)
    media_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    declared_content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    part_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_parts: Mapped[int] = mapped_column(Integer, nullable=False)
    received_parts_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    received_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="initialized")
    rights_status: Mapped[str] = mapped_column(String(32), nullable=False)
    license: Mapped[str] = mapped_column(String(160), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.asset_id", ondelete="SET NULL"), nullable=True
    )
    duplicate_of_asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    media_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    quarantine_state: Mapped[str] = mapped_column(String(32), nullable=False, default="not_scanned")
    scan_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scan_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    scan_signature_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scan_result_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scan_checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scan_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scan_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trusted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AutoEditAnalysisORM(Base):
    __tablename__ = "auto_edit_analyses"
    __table_args__ = (
        UniqueConstraint("project_id", "fingerprint", name="uq_auto_edit_project_fingerprint"),
        Index("ix_auto_edit_project_created", "project_id", "created_at"),
    )

    analysis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    project_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_versions.project_version_id", ondelete="SET NULL"), nullable=True
    )
    asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.asset_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_media_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class TranscriptORM(Base):
    __tablename__ = "transcripts"
    __table_args__ = (
        UniqueConstraint("analysis_id", "version", name="uq_transcript_analysis_version"),
    )

    transcript_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auto_edit_analyses.analysis_id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.asset_id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_original_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class TranscriptSegmentORM(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("transcript_id", "ordinal", name="uq_transcript_segment_ordinal"),)

    segment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transcript_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("transcripts.transcript_id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(String(4000), nullable=False)
    speaker: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class TranscriptWordORM(Base):
    __tablename__ = "transcript_words"
    __table_args__ = (UniqueConstraint("transcript_id", "ordinal", name="uq_transcript_word_ordinal"),)

    word_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transcript_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("transcripts.transcript_id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("transcript_segments.segment_id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(String(240), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class SceneORM(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("analysis_id", "ordinal", name="uq_scene_analysis_ordinal"),)

    scene_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auto_edit_analyses.analysis_id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    semantic_label: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    subjects_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    motion_score: Mapped[float] = mapped_column(Float, nullable=False)
    speech_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class SilenceDecisionORM(Base):
    __tablename__ = "silence_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auto_edit_analyses.analysis_id", ondelete="CASCADE"), nullable=False
    )
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    padding_before_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    padding_after_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    conflicts_with_speech: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class HighlightORM(Base):
    __tablename__ = "highlights"
    __table_args__ = (UniqueConstraint("analysis_id", "rank", name="uq_highlight_analysis_rank"),)

    highlight_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auto_edit_analyses.analysis_id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("scenes.scene_id", ondelete="SET NULL"), nullable=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    highlight_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    recommended_start: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_end: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_platform: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
