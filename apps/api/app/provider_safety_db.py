from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class ProviderSafetyControlORM(Base):
    """Single row used to serialize cross-instance safety reservations."""

    __tablename__ = "provider_safety_control"

    control_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ProviderSafetyBudgetDayORM(Base):
    __tablename__ = "provider_safety_budget_days"
    __table_args__ = (
        CheckConstraint("currency = 'VND'", name="ck_provider_safety_budget_vnd_only"),
        CheckConstraint("daily_limit_vnd >= 0", name="ck_provider_safety_daily_limit_nonnegative"),
        CheckConstraint("committed_vnd >= 0", name="ck_provider_safety_committed_nonnegative"),
        CheckConstraint("reserved_vnd >= 0", name="ck_provider_safety_reserved_nonnegative"),
    )

    budget_day: Mapped[date] = mapped_column(Date, primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    daily_limit_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    committed_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    reserved_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ProviderSafetyCircuitORM(Base):
    __tablename__ = "provider_safety_circuits"
    __table_args__ = (
        CheckConstraint(
            "state IN ('closed', 'open', 'half_open')",
            name="ck_provider_safety_circuit_state",
        ),
        CheckConstraint(
            "consecutive_failures >= 0",
            name="ck_provider_safety_circuit_failures_nonnegative",
        ),
    )

    provider_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    capability: Mapped[str] = mapped_column(String(120), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="closed")
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    half_open_operation_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ProviderSafetyOperationORM(Base):
    __tablename__ = "provider_safety_operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved', 'succeeded', 'failed', 'recovered')",
            name="ck_provider_safety_operation_status",
        ),
        CheckConstraint("external_call = true", name="ck_provider_safety_operation_external"),
        CheckConstraint("currency = 'VND'", name="ck_provider_safety_operation_vnd_only"),
        CheckConstraint("reserved_vnd >= 0", name="ck_provider_safety_reserved_cost_nonnegative"),
        CheckConstraint("charged_vnd >= 0", name="ck_provider_safety_charged_nonnegative"),
        Index("ix_provider_safety_operation_status_updated", "status", "updated_at"),
        Index("ix_provider_safety_operation_provider_created", "provider_key", "capability", "created_at"),
    )

    operation_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    capability: Mapped[str] = mapped_column(String(120), nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    operation: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    external_call: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    estimated_cost_vnd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    reserved_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    charged_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    budget_day: Mapped[date] = mapped_column(Date, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderSafetyAttemptORM(Base):
    __tablename__ = "provider_safety_attempts"
    __table_args__ = (
        UniqueConstraint("operation_key", "attempt", name="uq_provider_safety_operation_attempt"),
        CheckConstraint(
            "status IN ('succeeded', 'failed', 'rate_limited', 'timed_out')",
            name="ck_provider_safety_attempt_status",
        ),
        CheckConstraint("currency = 'VND'", name="ck_provider_safety_attempt_vnd_only"),
        CheckConstraint("charged_cost_vnd >= 0", name="ck_provider_safety_attempt_charge_nonnegative"),
        Index("ix_provider_safety_attempt_operation_created", "operation_key", "created_at"),
    )

    usage_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation_key: Mapped[str] = mapped_column(
        String(200),
        ForeignKey("provider_safety_operations.operation_key", ondelete="CASCADE"),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    estimated_cost_vnd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    actual_cost_vnd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    charged_cost_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    cost_status: Mapped[str] = mapped_column(String(20), nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_evidence: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderSafetyBudgetAlertORM(Base):
    __tablename__ = "provider_safety_budget_alerts"
    __table_args__ = (
        CheckConstraint("threshold_percent IN (50, 80, 100)", name="ck_provider_safety_alert_threshold"),
    )

    budget_day: Mapped[date] = mapped_column(Date, primary_key=True)
    threshold_percent: Mapped[int] = mapped_column(Integer, primary_key=True)
    emitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
