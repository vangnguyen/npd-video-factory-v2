"""Durable scoped raw-TTS identities, with no transferable review authority."""
from datetime import datetime
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utc_now


class TTSArtifactReuseORM(Base):
    __tablename__ = 'sql_tts_artifact_reuse'
    __table_args__ = (
        UniqueConstraint('workspace_id', 'project_id', 'content_version_id', 'fingerprint', name='uq_sql_tts_reuse_scope'),
        CheckConstraint("state IN ('pending','ready','unknown')", name='ck_sql_tts_reuse_state'),
    )
    reuse_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'))
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'))
    content_version_id: Mapped[str] = mapped_column(String(64), ForeignKey('project_versions.project_version_id', ondelete='RESTRICT'))
    fingerprint: Mapped[str] = mapped_column(String(64))
    binding_json: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16))
    claim_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_render_id: Mapped[str] = mapped_column(String(64), ForeignKey('production_render_jobs.render_id', ondelete='RESTRICT'))
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
