"""Additive audio parents/immutable snapshots; video transcript FKs stay intact."""
from datetime import datetime
from typing import Any
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utc_now


class UploadedAudioORM(Base):
    __tablename__ = 'uploaded_audio_transcriptions'
    __table_args__ = (UniqueConstraint('project_id', 'request_key_sha256', name='uq_uploaded_audio_request'),)
    audio_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='CASCADE'), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey('assets.asset_id', ondelete='RESTRICT'), nullable=False)
    job_id: Mapped[str] = mapped_column(String(80), ForeignKey('jobs.job_id', ondelete='RESTRICT'), nullable=False, unique=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    request_key_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    media_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    original_evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    original_evidence_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class UploadedAudioVersionORM(Base):
    __tablename__ = 'uploaded_audio_transcript_versions'
    __table_args__ = (UniqueConstraint('audio_id', 'version', name='uq_uploaded_audio_version'),)
    transcript_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audio_id: Mapped[str] = mapped_column(String(64), ForeignKey('uploaded_audio_transcriptions.audio_id', ondelete='RESTRICT'), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    transcript_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    transcript_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
