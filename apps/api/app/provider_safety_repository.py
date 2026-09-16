from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import re

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .provider_safety import ProviderAttemptRecord, ProviderCallContext
from .provider_safety_db import (
    ProviderSafetyAttemptORM,
    ProviderSafetyBudgetAlertORM,
    ProviderSafetyBudgetDayORM,
    ProviderSafetyCircuitORM,
    ProviderSafetyControlORM,
    ProviderSafetyOperationORM,
)


@dataclass(frozen=True)
class DurableReservation:
    allowed: bool
    code: str
    reserved_vnd: Decimal = Decimal("0")
    circuit_state: str = "closed"


@dataclass(frozen=True)
class DurableFinish:
    status: str
    charged_vnd: Decimal
    alerts: tuple[int, ...]
    circuit_state: str


@dataclass(frozen=True)
class DurableDispatchState:
    status: str | None
    protocol_version: int | None
    started: bool
    request_sha256: str | None
    client_request_id: str | None


@dataclass(frozen=True)
class DurableSafetySnapshot:
    committed_today_vnd: Decimal = Decimal("0")
    reserved_today_vnd: Decimal = Decimal("0")
    operations_total: int = 0
    active_operations: int = 0
    recovered_operations: int = 0
    external_calls_recorded: int = 0
    paid_calls_recorded: int = 0
    attempts_recorded: int = 0
    stale_active_operations: int = 0
    oldest_active_age_seconds: float | None = None
    circuits: dict[tuple[str, str], str] = field(default_factory=dict)


def _decimal(value: Decimal | int | float | None) -> Decimal:
    return Decimal(str(value or 0))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ProviderSafetyRepository:
    """PostgreSQL-backed safety ledger with a cross-instance transaction mutex.

    The control-row update is intentionally the first write in reservation and completion
    transactions. PostgreSQL serializes competing instances on that row; SQLite serializes the
    write in deterministic tests. No provider payload, response body or credential value is stored.
    """

    CONTROL_KEY = "global"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def ensure_state(self) -> None:
        async with self.session_factory() as session:
            if await session.get(ProviderSafetyControlORM, self.CONTROL_KEY) is not None:
                return
            session.add(ProviderSafetyControlORM(control_key=self.CONTROL_KEY, revision=0))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()

    async def _lock_control(self, session: AsyncSession, *, now: datetime) -> None:
        result = await session.execute(
            update(ProviderSafetyControlORM)
            .where(ProviderSafetyControlORM.control_key == self.CONTROL_KEY)
            .values(
                revision=ProviderSafetyControlORM.revision + 1,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("provider safety control row is not initialized")

    async def reserve_operation(
        self,
        context: ProviderCallContext,
        *,
        now: datetime,
        max_attempts: int,
        max_concurrent_calls: int,
        per_operation_limit_vnd: Decimal,
        daily_limit_vnd: Decimal,
        circuit_failure_threshold: int,
        circuit_cooldown_seconds: int,
        retention_days: int,
        single_dispatch_protocol: bool = False,
    ) -> DurableReservation:
        del circuit_failure_threshold  # threshold is applied when an operation is finished
        budget_day = now.date()
        estimate = context.estimated_cost_vnd or Decimal("0")
        reservation = estimate * max_attempts if context.paid else Decimal("0")
        async with self.session_factory() as session:
            async with session.begin():
                await self._lock_control(session, now=now)
                if await session.get(ProviderSafetyOperationORM, context.operation_key) is not None:
                    return DurableReservation(False, "DUPLICATE_OPERATION_BLOCKED")

                active = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ProviderSafetyOperationORM)
                        .where(ProviderSafetyOperationORM.status == "reserved")
                    )
                    or 0
                )
                if active >= max_concurrent_calls:
                    return DurableReservation(False, "PROVIDER_CONCURRENCY_LIMIT")

                circuit = await session.get(
                    ProviderSafetyCircuitORM,
                    (context.provider_key, context.capability),
                )
                if circuit is None:
                    circuit = ProviderSafetyCircuitORM(
                        provider_key=context.provider_key,
                        capability=context.capability,
                        state="closed",
                        consecutive_failures=0,
                        opened_at=None,
                        half_open_operation_key=None,
                        updated_at=now,
                    )
                    session.add(circuit)
                    await session.flush()
                if circuit.state == "open":
                    opened_at = _utc(circuit.opened_at or now)
                    if now < opened_at + timedelta(seconds=circuit_cooldown_seconds):
                        return DurableReservation(False, "CIRCUIT_OPEN", circuit_state="open")
                    circuit.state = "half_open"
                    circuit.half_open_operation_key = None
                if circuit.state == "half_open" and circuit.half_open_operation_key:
                    return DurableReservation(False, "CIRCUIT_HALF_OPEN_BUSY", circuit_state="half_open")

                budget = await session.get(ProviderSafetyBudgetDayORM, budget_day)
                if budget is None:
                    budget = ProviderSafetyBudgetDayORM(
                        budget_day=budget_day,
                        currency="VND",
                        daily_limit_vnd=daily_limit_vnd,
                        committed_vnd=Decimal("0"),
                        reserved_vnd=Decimal("0"),
                        updated_at=now,
                    )
                    session.add(budget)
                    await session.flush()
                elif _decimal(budget.daily_limit_vnd) != daily_limit_vnd:
                    return DurableReservation(False, "BUDGET_POLICY_MISMATCH", circuit_state=circuit.state)

                if context.paid and reservation > per_operation_limit_vnd:
                    return DurableReservation(
                        False,
                        "PER_OPERATION_BUDGET_EXCEEDED",
                        circuit_state=circuit.state,
                    )
                if context.paid and (
                    _decimal(budget.committed_vnd) + _decimal(budget.reserved_vnd) + reservation
                    > daily_limit_vnd
                ):
                    return DurableReservation(False, "DAILY_BUDGET_EXCEEDED", circuit_state=circuit.state)

                if circuit.state == "half_open":
                    circuit.half_open_operation_key = context.operation_key
                circuit.updated_at = now
                budget.reserved_vnd = _decimal(budget.reserved_vnd) + reservation
                budget.updated_at = now
                session.add(
                    ProviderSafetyOperationORM(
                        operation_key=context.operation_key,
                        acceptance_lineage_id=context.acceptance_lineage_id,
                        provider_key=context.provider_key,
                        capability=context.capability,
                        workspace_id=context.workspace_id,
                        project_id=context.project_id,
                        job_id=context.job_id,
                        operation=context.operation,
                        status="reserved",
                        external_call=True,
                        paid=context.paid,
                        currency="VND",
                        estimated_cost_vnd=context.estimated_cost_vnd,
                        reserved_vnd=reservation,
                        charged_vnd=Decimal("0"),
                        budget_day=budget_day,
                        attempt_count=0,
                        dispatch_protocol_version=1 if single_dispatch_protocol else None,
                        dispatch_started_at=None,
                        dispatch_request_sha256=None,
                        dispatch_client_request_id=None,
                        failure_code=None,
                        created_at=now,
                        updated_at=now,
                        completed_at=None,
                        retention_until=now + timedelta(days=retention_days),
                    )
                )
            return DurableReservation(
                True,
                "PROVIDER_CALL_RESERVED",
                reserved_vnd=reservation,
                circuit_state=circuit.state,
            )

    async def dispatch_state(self, context: ProviderCallContext) -> DurableDispatchState:
        """Read the durable boundary; callers must fail closed if the read fails."""
        async with self.session_factory() as session:
            operation = await session.get(ProviderSafetyOperationORM, context.operation_key)
            if operation is None:
                return DurableDispatchState(None, None, False, None, None)
            if operation.acceptance_lineage_id != context.acceptance_lineage_id:
                raise RuntimeError("provider safety dispatch lineage mismatch")
            return DurableDispatchState(
                operation.status,
                operation.dispatch_protocol_version,
                operation.dispatch_started_at is not None,
                operation.dispatch_request_sha256,
                operation.dispatch_client_request_id,
            )

    async def mark_dispatch_started(
        self,
        context: ProviderCallContext,
        *,
        now: datetime,
        request_sha256: str,
        client_request_id: str,
    ) -> None:
        """Commit once immediately before send. A committed marker is never retryable."""
        if not re.fullmatch(r"[a-f0-9]{64}", request_sha256):
            raise ValueError("single-dispatch request SHA-256 is invalid")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", client_request_id):
            raise ValueError("single-dispatch client request ID is invalid")
        async with self.session_factory() as session:
            async with session.begin():
                await self._lock_control(session, now=now)
                operation = await session.get(
                    ProviderSafetyOperationORM, context.operation_key, with_for_update=True,
                )
                if (
                    operation is None
                    or operation.acceptance_lineage_id != context.acceptance_lineage_id
                    or operation.status != "reserved"
                    or operation.dispatch_protocol_version != 1
                    or operation.dispatch_started_at is not None
                    or operation.attempt_count != 0
                ):
                    raise RuntimeError("single-dispatch operation is not virgin and reserved")
                operation.dispatch_started_at = now
                operation.dispatch_request_sha256 = request_sha256
                operation.dispatch_client_request_id = client_request_id
                operation.updated_at = now

    async def release_pre_dispatch(self, context: ProviderCallContext, *, now: datetime) -> bool:
        """Release only an unstarted v1 reservation; historical rows are untouched."""
        async with self.session_factory() as session:
            async with session.begin():
                await self._lock_control(session, now=now)
                operation = await session.get(
                    ProviderSafetyOperationORM, context.operation_key, with_for_update=True,
                )
                if operation is None:
                    return False
                if (
                    operation.acceptance_lineage_id != context.acceptance_lineage_id
                    or operation.status != "reserved"
                    or operation.dispatch_protocol_version != 1
                    or operation.dispatch_started_at is not None
                    or operation.attempt_count != 0
                ):
                    return False
                attempts = await session.scalar(
                    select(func.count()).select_from(ProviderSafetyAttemptORM).where(
                        ProviderSafetyAttemptORM.operation_key == context.operation_key,
                    )
                )
                if attempts:
                    return False
                budget = await session.get(
                    ProviderSafetyBudgetDayORM, operation.budget_day, with_for_update=True,
                )
                circuit = await session.get(
                    ProviderSafetyCircuitORM,
                    (operation.provider_key, operation.capability),
                    with_for_update=True,
                )
                if budget is None or circuit is None:
                    raise RuntimeError("single-dispatch reservation state is incomplete")
                if _decimal(budget.reserved_vnd) < _decimal(operation.reserved_vnd):
                    raise RuntimeError("single-dispatch budget reservation underflow")
                budget.reserved_vnd = _decimal(budget.reserved_vnd) - _decimal(operation.reserved_vnd)
                budget.updated_at = now
                if circuit.half_open_operation_key == context.operation_key:
                    circuit.half_open_operation_key = None
                    circuit.updated_at = now
                await session.delete(operation)
                return True

    async def record_attempt(self, record: ProviderAttemptRecord) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                operation = await session.get(
                    ProviderSafetyOperationORM,
                    record.operation_key,
                    with_for_update=True,
                )
                if operation is None:
                    raise RuntimeError("provider safety operation reservation is missing")
                if operation.acceptance_lineage_id != record.acceptance_lineage_id:
                    raise RuntimeError("provider safety attempt lineage does not match its operation")
                if operation.dispatch_protocol_version == 1 and (
                    operation.status != "reserved" or operation.dispatch_started_at is None
                ):
                    raise RuntimeError("single-dispatch attempt requires a committed dispatch marker")
                existing = await session.scalar(
                    select(ProviderSafetyAttemptORM).where(
                        ProviderSafetyAttemptORM.operation_key == record.operation_key,
                        ProviderSafetyAttemptORM.attempt == record.attempt,
                    )
                )
                if existing is not None:
                    return
                session.add(
                    ProviderSafetyAttemptORM(
                        usage_id=record.usage_id,
                        operation_key=record.operation_key,
                        acceptance_lineage_id=record.acceptance_lineage_id,
                        attempt=record.attempt,
                        status=record.status,
                        currency="VND",
                        estimated_cost_vnd=record.estimated_cost_vnd,
                        actual_cost_vnd=record.actual_cost_vnd,
                        charged_cost_vnd=record.charged_cost_vnd,
                        cost_status=record.cost_status,
                        retryable=record.retryable,
                        error_code=record.error_code,
                        error_evidence=(
                            record.error_evidence.model_dump(mode="json")
                            if record.error_evidence is not None
                            else None
                        ),
                        created_at=record.created_at,
                        completed_at=record.completed_at,
                    )
                )
                operation.attempt_count = max(operation.attempt_count, record.attempt)
                operation.updated_at = record.completed_at

    async def finish_operation(
        self,
        context: ProviderCallContext,
        *,
        now: datetime,
        attempts: int,
        charged_vnd: Decimal,
        succeeded: bool,
        failure_code: str | None,
        circuit_failure_threshold: int,
        warning_thresholds: tuple[int, ...],
    ) -> DurableFinish:
        async with self.session_factory() as session:
            async with session.begin():
                await self._lock_control(session, now=now)
                operation = await session.get(
                    ProviderSafetyOperationORM,
                    context.operation_key,
                    with_for_update=True,
                )
                if operation is None:
                    raise RuntimeError("provider safety operation reservation is missing")
                if operation.acceptance_lineage_id != context.acceptance_lineage_id:
                    raise RuntimeError("provider safety completion lineage does not match its operation")
                if operation.dispatch_protocol_version == 1 and operation.dispatch_started_at is None:
                    raise RuntimeError("single-dispatch operation cannot finish before dispatch")
                if operation.status != "reserved":
                    alerts = await self._existing_alerts(session, operation.budget_day)
                    circuit = await session.get(
                        ProviderSafetyCircuitORM,
                        (operation.provider_key, operation.capability),
                    )
                    return DurableFinish(
                        operation.status,
                        _decimal(operation.charged_vnd),
                        tuple(alerts),
                        circuit.state if circuit else "closed",
                    )

                budget = await session.get(
                    ProviderSafetyBudgetDayORM,
                    operation.budget_day,
                    with_for_update=True,
                )
                if budget is None:
                    raise RuntimeError("provider safety budget reservation is missing")
                budget.reserved_vnd = max(
                    Decimal("0"),
                    _decimal(budget.reserved_vnd) - _decimal(operation.reserved_vnd),
                )
                budget.committed_vnd = _decimal(budget.committed_vnd) + charged_vnd
                budget.updated_at = now

                circuit = await session.get(
                    ProviderSafetyCircuitORM,
                    (operation.provider_key, operation.capability),
                    with_for_update=True,
                )
                if circuit is None:
                    raise RuntimeError("provider safety circuit state is missing")
                circuit.half_open_operation_key = None
                if succeeded:
                    circuit.state = "closed"
                    circuit.consecutive_failures = 0
                    circuit.opened_at = None
                else:
                    circuit.consecutive_failures += 1
                    if (
                        circuit.state == "half_open"
                        or circuit.consecutive_failures >= circuit_failure_threshold
                    ):
                        circuit.state = "open"
                        circuit.opened_at = now
                circuit.updated_at = now

                operation.status = "succeeded" if succeeded else "failed"
                operation.charged_vnd = charged_vnd
                operation.attempt_count = attempts
                operation.failure_code = None if succeeded else (failure_code or "PROVIDER_EXECUTION_FAILED")
                operation.updated_at = now
                operation.completed_at = now

                new_alerts: list[int] = []
                limit = _decimal(budget.daily_limit_vnd)
                percent = (_decimal(budget.committed_vnd) / limit * 100) if limit > 0 else Decimal("0")
                for threshold in warning_thresholds:
                    if percent < threshold:
                        continue
                    if await session.get(
                        ProviderSafetyBudgetAlertORM,
                        (operation.budget_day, threshold),
                    ) is None:
                        session.add(
                            ProviderSafetyBudgetAlertORM(
                                budget_day=operation.budget_day,
                                threshold_percent=threshold,
                                emitted_at=now,
                            )
                        )
                        new_alerts.append(threshold)
            return DurableFinish(
                operation.status,
                charged_vnd,
                tuple(new_alerts),
                circuit.state,
            )

    async def _existing_alerts(self, session: AsyncSession, budget_day: date) -> list[int]:
        return list(
            await session.scalars(
                select(ProviderSafetyBudgetAlertORM.threshold_percent)
                .where(ProviderSafetyBudgetAlertORM.budget_day == budget_day)
                .order_by(ProviderSafetyBudgetAlertORM.threshold_percent)
            )
        )

    async def recover_stale_operations(
        self,
        *,
        stale_before: datetime,
        now: datetime,
        warning_thresholds: tuple[int, ...],
    ) -> list[str]:
        recovered: list[str] = []
        async with self.session_factory() as session:
            async with session.begin():
                await self._lock_control(session, now=now)
                rows = list(
                    await session.scalars(
                        select(ProviderSafetyOperationORM)
                        .where(
                            ProviderSafetyOperationORM.status == "reserved",
                            ProviderSafetyOperationORM.updated_at < stale_before,
                        )
                        .with_for_update()
                    )
                )
                for operation in rows:
                    if operation.dispatch_protocol_version == 1 and operation.dispatch_started_at is None:
                        attempt_rows = int(await session.scalar(
                            select(func.count()).select_from(ProviderSafetyAttemptORM).where(
                                ProviderSafetyAttemptORM.operation_key == operation.operation_key,
                            )
                        ) or 0)
                        if attempt_rows:
                            raise RuntimeError("unstarted single-dispatch operation has attempts")
                        budget = await session.get(
                            ProviderSafetyBudgetDayORM, operation.budget_day, with_for_update=True,
                        )
                        circuit = await session.get(
                            ProviderSafetyCircuitORM,
                            (operation.provider_key, operation.capability),
                            with_for_update=True,
                        )
                        if budget is None or circuit is None:
                            raise RuntimeError("stale single-dispatch reservation state is incomplete")
                        if _decimal(budget.reserved_vnd) < _decimal(operation.reserved_vnd):
                            raise RuntimeError("stale single-dispatch budget reservation underflow")
                        budget.reserved_vnd = _decimal(budget.reserved_vnd) - _decimal(operation.reserved_vnd)
                        budget.updated_at = now
                        if circuit.half_open_operation_key == operation.operation_key:
                            circuit.half_open_operation_key = None
                            circuit.updated_at = now
                        recovered.append(operation.operation_key)
                        await session.delete(operation)
                        continue
                    charged_vnd = _decimal(
                        await session.scalar(
                            select(func.sum(ProviderSafetyAttemptORM.charged_cost_vnd)).where(
                                ProviderSafetyAttemptORM.operation_key == operation.operation_key
                            )
                        )
                    )
                    attempt_count = int(
                        await session.scalar(
                            select(func.max(ProviderSafetyAttemptORM.attempt)).where(
                                ProviderSafetyAttemptORM.operation_key == operation.operation_key
                            )
                        )
                        or 0
                    )
                    if operation.dispatch_protocol_version == 1:
                        # The request may have been sent before a crash. This is
                        # a safety charge, never a claim of actual provider cost.
                        charged_vnd = max(charged_vnd, _decimal(operation.reserved_vnd))
                    budget = await session.get(
                        ProviderSafetyBudgetDayORM,
                        operation.budget_day,
                        with_for_update=True,
                    )
                    if budget is not None:
                        budget.reserved_vnd = max(
                            Decimal("0"),
                            _decimal(budget.reserved_vnd) - _decimal(operation.reserved_vnd),
                        )
                        budget.committed_vnd = _decimal(budget.committed_vnd) + charged_vnd
                        budget.updated_at = now
                        limit = _decimal(budget.daily_limit_vnd)
                        percent = (
                            _decimal(budget.committed_vnd) / limit * 100
                            if limit > 0
                            else Decimal("0")
                        )
                        for threshold in warning_thresholds:
                            if percent >= threshold and await session.get(
                                ProviderSafetyBudgetAlertORM,
                                (operation.budget_day, threshold),
                            ) is None:
                                session.add(
                                    ProviderSafetyBudgetAlertORM(
                                        budget_day=operation.budget_day,
                                        threshold_percent=threshold,
                                        emitted_at=now,
                                    )
                                )
                    circuit = await session.get(
                        ProviderSafetyCircuitORM,
                        (operation.provider_key, operation.capability),
                        with_for_update=True,
                    )
                    if circuit is not None:
                        if circuit.half_open_operation_key == operation.operation_key:
                            circuit.half_open_operation_key = None
                        circuit.state = "open"
                        circuit.consecutive_failures += 1
                        circuit.opened_at = now
                        circuit.updated_at = now
                    operation.status = "recovered"
                    operation.charged_vnd = charged_vnd
                    operation.attempt_count = attempt_count
                    operation.failure_code = (
                        "STALE_DISPATCH_RECOVERED_COST_UNKNOWN"
                        if operation.dispatch_protocol_version == 1
                        else "STALE_RESERVATION_RECOVERED"
                    )
                    operation.updated_at = now
                    operation.completed_at = now
                    recovered.append(operation.operation_key)
        return recovered

    async def purge_expired_operations(self, *, now: datetime) -> int:
        """Delete only terminal rows whose configured retention period elapsed."""

        async with self.session_factory() as session:
            async with session.begin():
                await self._lock_control(session, now=now)
                keys = list(
                    await session.scalars(
                        select(ProviderSafetyOperationORM.operation_key).where(
                            ProviderSafetyOperationORM.status.in_(("succeeded", "failed", "recovered")),
                            ProviderSafetyOperationORM.retention_until < now,
                        )
                    )
                )
                if not keys:
                    return 0
                await session.execute(
                    delete(ProviderSafetyAttemptORM).where(
                        ProviderSafetyAttemptORM.operation_key.in_(keys)
                    )
                )
                await session.execute(
                    delete(ProviderSafetyOperationORM).where(
                        ProviderSafetyOperationORM.operation_key.in_(keys)
                    )
                )
                return len(keys)

    async def snapshot(
        self,
        *,
        now: datetime,
        stale_after_seconds: int,
    ) -> DurableSafetySnapshot:
        async with self.session_factory() as session:
            budget = await session.get(ProviderSafetyBudgetDayORM, now.date())
            operations_total = int(
                await session.scalar(select(func.count()).select_from(ProviderSafetyOperationORM)) or 0
            )
            active_operations = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProviderSafetyOperationORM)
                    .where(ProviderSafetyOperationORM.status == "reserved")
                )
                or 0
            )
            recovered_operations = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProviderSafetyOperationORM)
                    .where(ProviderSafetyOperationORM.status == "recovered")
                )
                or 0
            )
            paid_calls = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProviderSafetyOperationORM)
                    .where(
                        ProviderSafetyOperationORM.paid.is_(True),
                        or_(
                            ProviderSafetyOperationORM.dispatch_protocol_version.is_(None),
                            ProviderSafetyOperationORM.dispatch_started_at.is_not(None),
                        ),
                    )
                )
                or 0
            )
            external_calls = int(await session.scalar(
                select(func.count()).select_from(ProviderSafetyOperationORM).where(
                    or_(
                        ProviderSafetyOperationORM.dispatch_protocol_version.is_(None),
                        ProviderSafetyOperationORM.dispatch_started_at.is_not(None),
                    ),
                )
            ) or 0)
            attempts = int(
                await session.scalar(select(func.count()).select_from(ProviderSafetyAttemptORM)) or 0
            )
            stale_before = now - timedelta(seconds=stale_after_seconds)
            stale_active = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProviderSafetyOperationORM)
                    .where(
                        ProviderSafetyOperationORM.status == "reserved",
                        ProviderSafetyOperationORM.updated_at < stale_before,
                    )
                )
                or 0
            )
            oldest = await session.scalar(
                select(func.min(ProviderSafetyOperationORM.created_at)).where(
                    ProviderSafetyOperationORM.status == "reserved"
                )
            )
            circuit_rows = list(await session.scalars(select(ProviderSafetyCircuitORM)))
            return DurableSafetySnapshot(
                committed_today_vnd=_decimal(budget.committed_vnd) if budget else Decimal("0"),
                reserved_today_vnd=_decimal(budget.reserved_vnd) if budget else Decimal("0"),
                operations_total=operations_total,
                active_operations=active_operations,
                recovered_operations=recovered_operations,
                external_calls_recorded=external_calls,
                paid_calls_recorded=paid_calls,
                attempts_recorded=attempts,
                stale_active_operations=stale_active,
                oldest_active_age_seconds=(
                    max(0.0, (now - _utc(oldest)).total_seconds()) if oldest else None
                ),
                circuits={(row.provider_key, row.capability): row.state for row in circuit_rows},
            )
