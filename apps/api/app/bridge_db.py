from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class BridgeRequestORM(Base):
    __tablename__ = "agent_hub_bridge_requests"
    __table_args__ = (
        UniqueConstraint("service_id", "idempotency_key_hash", name="uq_bridge_request_service_idempotency"),
        CheckConstraint("execution_started = false", name="ck_bridge_request_no_execution"),
        CheckConstraint("external_action = false", name="ck_bridge_request_no_external_action"),
        Index("ix_bridge_request_project_created", "project_id", "created_at"),
    )

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    service_id: Mapped[str] = mapped_column(String(160), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("video_projects.project_id", ondelete="SET NULL"), nullable=True)
    project_version_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("project_versions.project_version_id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_started: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    external_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class BridgeEventORM(Base):
    __tablename__ = "agent_hub_bridge_events"
    __table_args__ = (
        CheckConstraint("contains_secret = false", name="ck_bridge_event_secret_free"),
        Index("ix_bridge_event_project_created", "project_id", "created_at"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_hub_bridge_requests.request_id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("video_projects.project_id", ondelete="SET NULL"), nullable=True)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    contains_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class WebhookDeliveryORM(Base):
    __tablename__ = "agent_hub_webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("event_id", "destination_ref", name="uq_bridge_delivery_event_destination"),
        Index("ix_bridge_delivery_status_schedule", "status", "next_retry_at"),
    )

    delivery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_hub_bridge_events.event_id", ondelete="CASCADE"), nullable=False)
    destination_ref: Mapped[str] = mapped_column(String(240), nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    key_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    signed_at_unix: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receipt_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_call: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
