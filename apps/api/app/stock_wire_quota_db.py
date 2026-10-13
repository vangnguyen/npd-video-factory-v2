"""Video Factory SQL-owned stock wire leases and append-only observations."""
from datetime import datetime
from typing import Any
from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utc_now


class StockWireControlORM(Base):
    __tablename__ = 'stock_wire_control'
    control_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class StockWireScopeORM(Base):
    __tablename__ = 'stock_wire_scopes'
    __table_args__ = (
        CheckConstraint('cooldown_until >= 0', name='ck_stock_wire_cooldown_nonnegative'),
        CheckConstraint('(lease_id IS NULL AND lease_until IS NULL) OR '
            '(lease_id IS NOT NULL AND lease_until IS NOT NULL)', name='ck_stock_wire_lease_pair'),
    )
    scope_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    cooldown_until: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    lease_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lease_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class StockWireEventORM(Base):
    __tablename__ = 'stock_wire_events'
    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    scope_sha256: Mapped[str] = mapped_column(String(64), ForeignKey('stock_wire_scopes.scope_sha256', ondelete='RESTRICT'), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
