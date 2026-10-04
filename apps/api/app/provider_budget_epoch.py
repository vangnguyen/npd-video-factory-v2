"""Owner accounting continuity in a fresh dev ledger; no credential or provider IO."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from .provider_safety_db import (
    ProviderSafetyAccountingEpochORM, ProviderSafetyAttemptORM, ProviderSafetyBudgetAlertORM,
    ProviderSafetyBudgetDayORM, ProviderSafetyCircuitORM, ProviderSafetyOperationORM,
)
from .provider_safety_repository import ProviderSafetyRepository

CLASSIFICATION = "OWNER_CARRY_FORWARD_CONSERVATIVE_CHARGE"
SCHEMA_ID = "0017_content_budget_epoch"


def public_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()  # Public metadata and SQLite ledger only.


class BudgetEpochArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_name: Literal["provider-safety-owner-accounting-epoch-v1"] = "provider-safety-owner-accounting-epoch-v1"
    epoch_id: str = Field(pattern=r"^mvp1-content-budget-epoch-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2,}$")
    created_at_utc: datetime
    budget_day: date
    source_head: str = Field(pattern=r"^[a-f0-9]{40}$")
    owner_decision_id: str = Field(pattern=r"^VF-MVP1-CONTENT-BUDGET-CARRY-FORWARD-[0-9]+$")
    currency: Literal["VND"] = "VND"
    daily_limit_vnd: Decimal = Field(gt=0, allow_inf_nan=False)
    opening_committed_vnd: Decimal = Field(ge=0, allow_inf_nan=False)
    opening_reserved_vnd: Literal[0] = 0
    available_vnd: Decimal = Field(ge=0, allow_inf_nan=False)
    per_operation_limit_vnd: Decimal = Field(gt=0, allow_inf_nan=False)
    classification: Literal["OWNER_CARRY_FORWARD_CONSERVATIVE_CHARGE"] = CLASSIFICATION
    historical_ledger_recovery_status: Literal["CONTENT_LEDGER_UNRECOVERABLE"] = "CONTENT_LEDGER_UNRECOVERABLE"
    historical_execution_artifact: Literal["UNAVAILABLE_IN_CURRENT_CLOUD_STATE"] = "UNAVAILABLE_IN_CURRENT_CLOUD_STATE"
    provider: Literal["openai-storyboard-content"] = "openai-storyboard-content"
    model: Literal["gpt-6-luna"] = "gpt-6-luna"
    capability: Literal["content_generation"] = "content_generation"
    evidence_hashes: dict[str, str] = Field(min_length=1)
    production_authority: Literal[False] = False
    execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_accounting(self):
        import re
        now = self.created_at_utc
        if now.tzinfo is None or now.utcoffset() != timedelta(0) or now.date() != self.budget_day:
            raise ValueError("EPOCH_UTC_BUDGET_DAY_REQUIRED")
        if f"-{self.budget_day.isoformat()}-" not in self.epoch_id:
            raise ValueError("EPOCH_ID_BUDGET_DAY_MISMATCH")
        if self.available_vnd != self.daily_limit_vnd - self.opening_committed_vnd:
            raise ValueError("EPOCH_OPENING_BALANCE_MISMATCH")
        if self.per_operation_limit_vnd > self.daily_limit_vnd:
            raise ValueError("EPOCH_OPERATION_CEILING_MISMATCH")
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", key)
               or not re.fullmatch(r"[a-f0-9]{64}", value) for key, value in self.evidence_hashes.items()):
            raise ValueError("EPOCH_PUBLIC_EVIDENCE_HASHES_REQUIRED")
        return self

    @property
    def artifact_bytes(self):
        return public_bytes(self.model_dump(mode="json"))

    @property
    def artifact_sha256(self):
        return sha256(self.artifact_bytes)


class ProviderBudgetEpochRepository(ProviderSafetyRepository):
    async def initialize_epoch(self, artifact: BudgetEpochArtifact):
        """Atomically seed only a fresh opening budget and its provenance; never reset."""
        artifact = BudgetEpochArtifact.model_validate(artifact.model_dump())
        await self.ensure_state()
        async with self.session_factory() as session:
            async with session.begin():
                await self._lock_control(session, now=artifact.created_at_utc)
                existing = await session.get(ProviderSafetyAccountingEpochORM, artifact.epoch_id)
                if existing is not None:
                    if (existing.artifact_sha256 != artifact.artifact_sha256
                            or existing.artifact_json != artifact.model_dump(mode="json")):
                        raise ValueError("EPOCH_ALREADY_EXISTS_DIFFERENT_PROVENANCE")
                    budget = await session.get(ProviderSafetyBudgetDayORM, artifact.budget_day)
                    if (budget is None or budget.currency != "VND"
                            or budget.daily_limit_vnd != artifact.daily_limit_vnd
                            or budget.committed_vnd < artifact.opening_committed_vnd):
                        raise ValueError("EPOCH_BUDGET_CORRUPT")
                    return  # Existing subsequent usage/reservations are never overwritten.
                for table in [ProviderSafetyAccountingEpochORM, ProviderSafetyBudgetDayORM,
                        ProviderSafetyOperationORM, ProviderSafetyAttemptORM,
                        ProviderSafetyCircuitORM, ProviderSafetyBudgetAlertORM]:
                    if await session.scalar(select(func.count()).select_from(table)):
                        raise ValueError("EPOCH_REQUIRES_FRESH_EMPTY_PROVIDER_LEDGER")
                session.add(ProviderSafetyBudgetDayORM(budget_day=artifact.budget_day,
                    currency="VND", daily_limit_vnd=artifact.daily_limit_vnd,
                    committed_vnd=artifact.opening_committed_vnd, reserved_vnd=Decimal(0),
                    updated_at=artifact.created_at_utc))
                await session.flush()
                session.add(ProviderSafetyAccountingEpochORM(epoch_id=artifact.epoch_id,
                    budget_day=artifact.budget_day, classification=CLASSIFICATION,
                    owner_decision_id=artifact.owner_decision_id,
                    opening_committed_vnd=artifact.opening_committed_vnd, opening_reserved_vnd=Decimal(0),
                    artifact_sha256=artifact.artifact_sha256, artifact_json=artifact.model_dump(mode="json"),
                    created_at=artifact.created_at_utc))

    async def budget_precheck(self, *, epoch_id: str, operation_key: str,
                              reservation_vnd: Decimal, now: datetime):
        """Read-only calculation. reserve_operation() remains the atomic dispatch boundary."""
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValueError("EPOCH_PRECHECK_UTC_REQUIRED")
        if not reservation_vnd.is_finite() or reservation_vnd <= 0:
            raise ValueError("EPOCH_RESERVATION_REQUIREMENT_INVALID")
        async with self.session_factory() as session:
            async with session.begin():
                epoch = await session.get(ProviderSafetyAccountingEpochORM, epoch_id)
                if epoch is None:
                    raise ValueError("EPOCH_PROVENANCE_UNAVAILABLE")
                artifact = BudgetEpochArtifact.model_validate(epoch.artifact_json)
                if (epoch.artifact_sha256 != artifact.artifact_sha256
                        or epoch.budget_day != artifact.budget_day
                        or epoch.classification != artifact.classification
                        or epoch.owner_decision_id != artifact.owner_decision_id
                        or epoch.opening_committed_vnd != artifact.opening_committed_vnd
                        or epoch.opening_reserved_vnd != artifact.opening_reserved_vnd
                        or now.date() != epoch.budget_day):
                    raise ValueError("EPOCH_PROVENANCE_OR_DAY_MISMATCH")
                budget = await session.get(ProviderSafetyBudgetDayORM, epoch.budget_day)
                if (budget is None or budget.currency != "VND"
                        or budget.daily_limit_vnd != artifact.daily_limit_vnd
                        or budget.committed_vnd < artifact.opening_committed_vnd):
                    raise ValueError("EPOCH_BUDGET_CORRUPT")
                operation = await session.get(ProviderSafetyOperationORM, operation_key)
                attempts = int(await session.scalar(select(func.count()).select_from(ProviderSafetyAttemptORM)
                    .where(ProviderSafetyAttemptORM.operation_key == operation_key)) or 0)
                active = int(await session.scalar(select(func.count()).select_from(ProviderSafetyOperationORM)
                    .where(ProviderSafetyOperationORM.status == "reserved")) or 0)
                if operation is not None or attempts:
                    raise ValueError("EPOCH_OPERATION_ALREADY_USED")
                if active or budget.reserved_vnd != 0:
                    raise ValueError("EPOCH_OUTSTANDING_RESERVATION_BLOCKED")
                if reservation_vnd > artifact.per_operation_limit_vnd:
                    raise ValueError("EPOCH_OPERATION_CEILING_EXCEEDED")
                maximum = budget.committed_vnd + budget.reserved_vnd + reservation_vnd
                if maximum > budget.daily_limit_vnd:
                    raise ValueError("EPOCH_DAILY_CAPACITY_INSUFFICIENT")
                return {"status": "ACCOUNTING_EPOCH_PRECHECK_PASS", "epoch_id": epoch_id,
                    "epoch_artifact_sha256": epoch.artifact_sha256,
                    "budget_day": epoch.budget_day.isoformat(), "operation_key": operation_key,
                    "opening_committed_vnd": str(artifact.opening_committed_vnd),
                    "committed_vnd": str(budget.committed_vnd), "reserved_vnd": str(budget.reserved_vnd),
                    "daily_limit_vnd": str(budget.daily_limit_vnd),
                    "available_vnd": str(budget.daily_limit_vnd-budget.committed_vnd-budget.reserved_vnd),
                    "reservation_requirement_vnd": str(reservation_vnd),
                    "post_reservation_maximum_vnd": str(maximum),
                    "remaining_headroom_after_reservation_vnd": str(budget.daily_limit_vnd-maximum),
                    "durable_operation_rows_for_key": 0, "durable_attempt_rows_for_key": attempts,
                    "dispatch_record_exists": False, "reservation_exists": False,
                    "reservation_performed": False, "classification": CLASSIFICATION}
