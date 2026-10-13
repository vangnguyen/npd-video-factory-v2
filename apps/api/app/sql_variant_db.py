"""Additive scoped family reservations; existing timeline/package uniqueness stays."""
from datetime import datetime
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utc_now


class SqlVariantFamilyORM(Base):
    __tablename__ = 'sql_variant_families'
    __table_args__ = (
        UniqueConstraint('workspace_id', 'master_project_id', 'request_key_sha256', name='uq_sql_variant_family_request'),
        CheckConstraint('version >= 1', name='ck_sql_variant_family_version'),
        CheckConstraint("state IN ('reserved','deriving','review_required','needs_attention','recovery_required','cancelled','failed')", name='ck_sql_variant_family_state'),
        Index('ix_sql_variant_family_history', 'workspace_id', 'master_project_id', 'created_at', 'family_id'),
    )
    family_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'))
    master_project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'))
    master_timeline_version_id: Mapped[str] = mapped_column(String(64), ForeignKey('timeline_versions.timeline_version_id', ondelete='RESTRICT'))
    version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(32), default='reserved')
    request_key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(JSON)
    result_sha256: Mapped[str] = mapped_column(String(64))
    actor_ref: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SqlVariantMemberORM(Base):
    __tablename__ = 'sql_variant_members'
    __table_args__ = (
        UniqueConstraint('family_id', 'profile_ref', name='uq_sql_variant_member_profile'),
        UniqueConstraint('planned_project_id', name='uq_sql_variant_planned_project'),
        UniqueConstraint('child_project_id', name='uq_sql_variant_child_project'),
        CheckConstraint("state IN ('reserved','deriving','review_required','needs_attention','cancelled','failed')", name='ck_sql_variant_member_state'),
    )
    member_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), ForeignKey('sql_variant_families.family_id', ondelete='RESTRICT'))
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'))
    profile_ref: Mapped[str] = mapped_column(String(80))
    profile_json: Mapped[dict] = mapped_column(JSON)
    profile_sha256: Mapped[str] = mapped_column(String(64))
    planned_project_id: Mapped[str] = mapped_column(String(64))
    child_project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=True)
    initial_timeline_version_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('timeline_versions.timeline_version_id', ondelete='RESTRICT'), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default='reserved')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SqlVariantArtifactReceiptORM(Base):
    __tablename__ = 'sql_variant_artifact_receipts'
    __table_args__ = (
        UniqueConstraint('family_id', 'request_key_sha256', name='uq_sql_variant_receipt_request'),
        UniqueConstraint('member_id', 'kind', 'input_sha256', name='uq_sql_variant_receipt_input'),
        CheckConstraint("state IN ('reserved','pending','ready','unknown','cancelled')", name='ck_sql_variant_receipt_state'),
        Index('ix_sql_variant_receipt_member', 'family_id', 'member_id', 'receipt_id'),
    )
    receipt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), ForeignKey('sql_variant_families.family_id', ondelete='RESTRICT'))
    member_id: Mapped[str] = mapped_column(String(64), ForeignKey('sql_variant_members.member_id', ondelete='RESTRICT'))
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'))
    kind: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default='reserved')
    request_key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    input_json: Mapped[dict] = mapped_column(JSON)
    input_sha256: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_asset_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('assets.asset_id', ondelete='RESTRICT'), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_ref: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SqlVariantEventORM(Base):
    __tablename__ = 'sql_variant_events'
    __table_args__ = (
        UniqueConstraint('family_id', 'request_key_sha256', name='uq_sql_variant_event_request'),
        UniqueConstraint('family_id', 'version', name='uq_sql_variant_event_version'),
    )
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), ForeignKey('sql_variant_families.family_id', ondelete='RESTRICT'))
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'))
    version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(80))
    request_key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    actor_ref: Mapped[str] = mapped_column(String(160))
    payload_json: Mapped[dict] = mapped_column(JSON)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
