from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    return url


class Base(DeclarativeBase):
    pass


class VersionedMixin:
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkspaceORM(VersionedMixin, Base):
    __tablename__ = "workspaces"

    workspace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_ref: Mapped[str] = mapped_column(String(160), nullable=False)


class VideoProjectORM(VersionedMixin, Base):
    __tablename__ = "video_projects"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_video_project_workspace_slug"),)

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(82), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    niche: Mapped[str] = mapped_column(String(80), nullable=False, default="custom")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProjectVersionORM(VersionedMixin, Base):
    __tablename__ = "project_versions"
    __table_args__ = (UniqueConstraint("project_id", "ordinal", name="uq_project_version_ordinal"),)

    project_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_job_id: Mapped[str | None] = mapped_column(String(80), nullable=True)


class JobORM(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_jobs_progress"),
        Index("ix_jobs_workspace_updated", "workspace_id", "updated_at"),
        Index("ix_jobs_project_updated", "project_id", "updated_at"),
    )

    job_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="SET NULL"), nullable=True
    )
    project_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_versions.project_version_id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    artifacts_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class JobEventORM(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_created", "job_id", "created_at"),)

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    from_stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    to_stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    from_progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False, default="system")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class IdempotencyKeyORM(Base):
    __tablename__ = "idempotency_keys"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AssetORM(VersionedMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_assets_size"),
        Index("ix_assets_project_created", "project_id", "created_at"),
    )

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    project_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_versions.project_version_id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("jobs.job_id", ondelete="SET NULL"), nullable=True
    )
    asset_class: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(768), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(80), nullable=False)


class ProviderRegistryORM(VersionedMixin, Base):
    __tablename__ = "provider_registry"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider_key", "capability", name="uq_provider_scope_capability"),
        Index("ix_provider_capability_status", "capability", "status"),
    )

    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=True
    )
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    capability: Mapped[str] = mapped_column(String(120), nullable=False)
    adapter: Mapped[str] = mapped_column(String(240), nullable=False)
    routing_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="disabled")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_configured")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_ref: Mapped[str | None] = mapped_column(String(240), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class ProviderUsageORM(Base):
    __tablename__ = "provider_usage"
    __table_args__ = (Index("ix_provider_usage_project_created", "project_id", "created_at"),)

    usage_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("jobs.job_id", ondelete="SET NULL"), nullable=True
    )
    provider_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("provider_registry.provider_id", ondelete="RESTRICT"), nullable=False
    )
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    capability: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    operation: Mapped[str] = mapped_column(String(160), nullable=False)
    units: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    unit_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="succeeded")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CostRecordORM(VersionedMixin, Base):
    __tablename__ = "cost_records"
    __table_args__ = (
        CheckConstraint("currency = 'VND'", name="ck_cost_records_vnd_only"),
        CheckConstraint("estimated_cost IS NULL OR estimated_cost >= 0", name="ck_estimated_cost_nonnegative"),
        CheckConstraint("actual_cost IS NULL OR actual_cost >= 0", name="ck_actual_cost_nonnegative"),
        Index("ix_cost_records_project_created", "project_id", "created_at"),
    )

    cost_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("jobs.job_id", ondelete="SET NULL"), nullable=True
    )
    provider_usage_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("provider_usage.usage_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    needs_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(normalize_database_url(database_url), echo=echo, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def verify_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
