from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Sequence, cast

from .provider_safety import (
    CircuitState,
    ProviderAttemptRecord,
    ProviderCallContext,
    ProviderCapabilitySafetyRead,
    ProviderExecutionReceipt,
    ProviderErrorEvidence,
    ProviderRightsDecision,
    ProviderSafetyController,
    ProviderSafetyDecision,
    ProviderSafetyPolicy,
    ProviderSafetySnapshot,
    utc_now,
)
from .provider_safety_repository import ProviderSafetyRepository


class DurableProviderSafetyController(ProviderSafetyController):
    """Provider controller whose external-call safety state survives restarts.

    Static owner gates remain in the controller. Only secret-free operation metadata, VND amounts,
    attempt outcomes and circuit state are delegated to the durable repository.
    """

    def __init__(
        self,
        policy: ProviderSafetyPolicy,
        *,
        repository: ProviderSafetyRepository,
        provider_definitions: Sequence[dict[str, Any]] = (),
        clock=utc_now,
        sleeper=None,
        operation_lease_seconds: int = 900,
        operation_retention_days: int = 400,
    ) -> None:
        kwargs: dict[str, Any] = {
            "provider_definitions": provider_definitions,
            "clock": clock,
        }
        if sleeper is not None:
            kwargs["sleeper"] = sleeper
        super().__init__(policy, **kwargs)
        self.repository = repository
        self.operation_lease_seconds = operation_lease_seconds
        self.operation_retention_days = operation_retention_days

    async def recover_stale_operations(self) -> list[str]:
        now = self._clock()
        return await self.repository.recover_stale_operations(
            stale_before=now - timedelta(seconds=self.operation_lease_seconds),
            now=now,
            warning_thresholds=tuple(self.policy.budget.warning_threshold_percent),
        )

    async def preflight(self, context: ProviderCallContext) -> ProviderSafetyDecision:
        if not context.external_call:
            return await super().preflight(context)

        now = self._clock()
        rights_records = context.rights
        if self.policy.verified_gate_required:
            scope = self.policy.execution_gate
            if scope is None:
                rights = self.evaluate_rights(
                    rights_records,
                    required=context.rights_required,
                    now=now,
                )
                return self._denied(context, "VERIFIED_GATE_BUNDLE_REQUIRED", rights)
            rights_records = [scope.rights_record]
            rights = self.evaluate_rights(
                rights_records,
                required=context.rights_required,
                now=now,
            )
            scope_denial = self._verified_scope_denial(scope, context=context, now=now)
            if scope_denial is not None:
                return self._denied(context, scope_denial, rights)
        else:
            rights = self.evaluate_rights(
                rights_records,
                required=context.rights_required,
                now=now,
            )
        denied = self._static_denial(context, rights, now)
        if denied is not None:
            return denied

        reservation = await self.repository.reserve_operation(
            context,
            now=now,
            max_attempts=self.policy.retry.max_attempts,
            max_concurrent_calls=self.policy.retry.max_concurrent_calls,
            per_operation_limit_vnd=self.policy.budget.per_operation_limit_vnd,
            daily_limit_vnd=self.policy.budget.daily_limit_vnd,
            circuit_failure_threshold=self.policy.circuit.failure_threshold,
            circuit_cooldown_seconds=self.policy.circuit.cooldown_seconds,
            retention_days=self.operation_retention_days,
        )
        return ProviderSafetyDecision(
            allowed=reservation.allowed,
            code=reservation.code,
            external_call=True,
            paid=context.paid,
            reserved_vnd=reservation.reserved_vnd,
            circuit_state=cast(CircuitState, reservation.circuit_state),
            rights=rights,
        )

    def _static_denial(
        self,
        context: ProviderCallContext,
        rights: ProviderRightsDecision,
        now: datetime,
    ) -> ProviderSafetyDecision | None:
        if self.policy.global_kill_switch_engaged:
            return self._denied(context, "GLOBAL_KILL_SWITCH_ENGAGED", rights)
        if not self.policy.external_execution_enabled:
            return self._denied(context, "EXTERNAL_EXECUTION_DISABLED", rights)
        if not self.policy.credential_gate_approved:
            return self._denied(context, "CREDENTIAL_OWNER_GATE_REQUIRED", rights)
        if not context.credential_alias:
            return self._denied(context, "CREDENTIAL_ALIAS_REQUIRED", rights)
        if not rights.allowed:
            return self._denied(context, rights.code, rights)
        if context.rights_required and not self.policy.rights_gate_approved:
            return self._denied(context, "RIGHTS_OWNER_GATE_REQUIRED", rights)
        if context.paid and not self.policy.paid_execution_enabled:
            return self._denied(context, "PAID_EXECUTION_DISABLED", rights)
        if context.paid and not self.policy.budget.active(now):
            return self._denied(context, "BUDGET_OWNER_GATE_REQUIRED", rights)
        if context.paid and context.estimated_cost_vnd is None:
            return self._denied(context, "COST_ESTIMATE_REQUIRED", rights)
        return None

    async def _record_attempt(
        self,
        context: ProviderCallContext,
        *,
        attempt: int,
        status: Literal["succeeded", "failed", "rate_limited", "timed_out"],
        retryable: bool,
        error_code: str | None,
        actual_cost_vnd: Decimal | None,
        charged_cost_vnd: Decimal,
        started_at: datetime,
        error_evidence: ProviderErrorEvidence | None = None,
    ) -> None:
        record: ProviderAttemptRecord = self._build_attempt_record(
            context,
            attempt=attempt,
            status=status,
            retryable=retryable,
            error_code=error_code,
            error_evidence=error_evidence,
            actual_cost_vnd=actual_cost_vnd,
            charged_cost_vnd=charged_cost_vnd,
            started_at=started_at,
        )
        await self.repository.record_attempt(record)

    async def _finish(
        self,
        context: ProviderCallContext,
        decision: ProviderSafetyDecision,
        *,
        attempts: int,
        charged: Decimal,
        succeeded: bool,
    ) -> ProviderExecutionReceipt:
        result = await self.repository.finish_operation(
            context,
            now=self._clock(),
            attempts=attempts,
            charged_vnd=charged,
            succeeded=succeeded,
            failure_code=None if succeeded else "PROVIDER_EXECUTION_FAILED",
            circuit_failure_threshold=self.policy.circuit.failure_threshold,
            warning_thresholds=tuple(self.policy.budget.warning_threshold_percent),
        )
        return ProviderExecutionReceipt(
            operation_key=context.operation_key,
            provider_key=context.provider_key,
            capability=context.capability,
            status="succeeded" if succeeded else "failed",
            attempts=attempts,
            retries=max(0, attempts - 1),
            charged_cost_vnd=result.charged_vnd,
            budget_alerts=cast(list[Literal[50, 80, 100]], list(result.alerts)),
            circuit_state=cast(CircuitState, result.circuit_state),
            external_call=True,
            paid=context.paid,
            rights_allowed=decision.rights.allowed,
        )

    async def snapshot(self) -> ProviderSafetySnapshot:
        metrics = await self.repository.snapshot(
            now=self._clock(),
            stale_after_seconds=self.operation_lease_seconds,
        )
        providers: list[ProviderCapabilitySafetyRead] = []
        for definition in self._provider_definitions:
            item = self._capability_snapshot(definition)
            state = metrics.circuits.get((item.provider_key, item.capability), item.circuit_state)
            providers.append(item.model_copy(update={"circuit_state": state}))
        return ProviderSafetySnapshot(
            external_execution_enabled=self.policy.external_execution_enabled,
            paid_execution_enabled=self.policy.paid_execution_enabled,
            global_kill_switch_engaged=self.policy.global_kill_switch_engaged,
            credential_gate_approved=self.policy.credential_gate_approved,
            budget_gate_approved=self.policy.budget.approved,
            rights_gate_approved=self.policy.rights_gate_approved,
            daily_limit_vnd=self.policy.budget.daily_limit_vnd,
            committed_today_vnd=metrics.committed_today_vnd,
            reserved_today_vnd=metrics.reserved_today_vnd,
            warning_threshold_percent=self.policy.budget.warning_threshold_percent,
            retry=self.policy.retry,
            circuit=self.policy.circuit,
            providers=providers,
            external_calls_recorded=metrics.external_calls_recorded,
            paid_calls_recorded=metrics.paid_calls_recorded,
            state_backend="postgresql",
            durable_operations_recorded=metrics.operations_total,
            active_operations=metrics.active_operations,
            recovered_operations=metrics.recovered_operations,
            attempts_recorded=metrics.attempts_recorded,
            stale_active_operations=metrics.stale_active_operations,
            oldest_active_age_seconds=metrics.oldest_active_age_seconds,
            operation_retention_days=self.operation_retention_days,
        )
