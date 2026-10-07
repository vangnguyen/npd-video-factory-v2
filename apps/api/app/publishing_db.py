from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class PublicationORM(Base):
    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key_hash", name="uq_publication_project_idempotency"),
        Index("ix_publication_project_created", "project_id", "created_at"),
        Index("ix_publication_status_updated", "status", "updated_at"),
    )

    publication_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    package_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_packages.package_id", ondelete="RESTRICT"), nullable=False
    )
    approval_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_approvals.approval_id", ondelete="RESTRICT"), nullable=False
    )
    final_render_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_render_jobs.render_id", ondelete="RESTRICT"), nullable=False
    )
    output_asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.asset_id", ondelete="RESTRICT"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    capability_version: Mapped[str] = mapped_column(String(80), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rights_validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    platform_validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider_validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    receipt_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    external_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class PublicationEventORM(Base):
    __tablename__ = "publication_events"
    __table_args__ = (Index("ix_publication_event_project_created", "project_id", "created_at"),)

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("publications.publication_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PublishApprovalORM(Base):
    """Separate immutable publish-only consent; production approval is retained."""
    __tablename__ = 'publication_publish_approvals'
    __table_args__ = (UniqueConstraint('publication_id', 'idempotency_key_hash', name='uq_publish_approval_request'),)
    publish_approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    publication_id: Mapped[str] = mapped_column(String(64), ForeignKey('publications.publication_id', ondelete='RESTRICT'), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    binding_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_token_id: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_subject: Mapped[str] = mapped_column(String(160), nullable=False)
    owner_identity_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PublicationDispatchORM(Base):
    """One durable upload initiation per publication; private session is a ref only."""
    __tablename__ = 'publication_dispatches'
    __table_args__ = (CheckConstraint('version >= 1 AND acknowledged_bytes >= 0', name='ck_publication_dispatch_progress'),
        Index('ix_publication_dispatch_workspace_phase', 'workspace_id', 'phase'))
    publication_id: Mapped[str] = mapped_column(String(64), ForeignKey('publications.publication_id', ondelete='RESTRICT'), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False)
    publish_approval_id: Mapped[str] = mapped_column(String(64), ForeignKey('publication_publish_approvals.publish_approval_id', ondelete='RESTRICT'), nullable=False)
    binding_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    acknowledged_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    private_session_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intent_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intent_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remote_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublicationPrivateSessionORM(Base):
    """Immutable encrypted session receipt; keys and plaintext are never persisted."""
    __tablename__ = 'publication_private_sessions'
    __table_args__ = (UniqueConstraint('publication_id', name='uq_publication_private_session'),
        UniqueConstraint('key_id', 'nonce', name='uq_private_session_key_nonce'),
        CheckConstraint('total_bytes > 0', name='ck_private_session_size'))
    session_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    publication_id: Mapped[str] = mapped_column(String(64), ForeignKey('publication_dispatches.publication_id', ondelete='RESTRICT'), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False)
    binding_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary(8192), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
