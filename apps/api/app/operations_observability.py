from __future__ import annotations

import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import JobORM
from .provider_safety import ProviderSafetyController, ProviderSafetySnapshot


QUEUE_KEY = "npd:video-jobs:queue"
JOB_PROCESSING_KEY = "npd:video-jobs:processing"
MEDIA_RESOLUTION_QUEUE_KEY = "npd:video-factory:v2:media-resolution:queued"
MEDIA_RESOLUTION_PROCESSING_KEY = "npd:video-factory:v2:media-resolution:processing"
PREVIEW_QUEUE_KEY = "npd:video-factory:v2:preview:queued"
PREVIEW_PROCESSING_KEY = "npd:video-factory:v2:preview:processing"
PRODUCTION_RENDER_QUEUE_KEY = "npd:video-factory:v2:production-render:queued"
PRODUCTION_RENDER_PROCESSING_KEY = "npd:video-factory:v2:production-render:processing"
ANALYTICS_SYNC_QUEUE_KEY = "npd:video-factory:v2:analytics:queued"
ANALYTICS_SYNC_PROCESSING_KEY = "npd:video-factory:v2:analytics:processing"
WEBHOOK_QUEUE_KEY = "npd:video-factory:v2:bridge:webhooks:queued"
WEBHOOK_PROCESSING_KEY = "npd:video-factory:v2:bridge:webhooks:processing"
QUEUE_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("video_jobs", QUEUE_KEY, JOB_PROCESSING_KEY),
    ("media_resolution", MEDIA_RESOLUTION_QUEUE_KEY, MEDIA_RESOLUTION_PROCESSING_KEY),
    ("preview", PREVIEW_QUEUE_KEY, PREVIEW_PROCESSING_KEY),
    ("production_render", PRODUCTION_RENDER_QUEUE_KEY, PRODUCTION_RENDER_PROCESSING_KEY),
    ("analytics", ANALYTICS_SYNC_QUEUE_KEY, ANALYTICS_SYNC_PROCESSING_KEY),
    ("agent_hub_webhook", WEBHOOK_QUEUE_KEY, WEBHOOK_PROCESSING_KEY),
)
FORBIDDEN_KEY_PARTS = ("secret", "token", "password", "credential", "cookie", "api_key", "apikey")


class QueueClient(Protocol):
    async def llen(self, key: str) -> int: ...

    async def ping(self) -> object: ...


class DependencyHealthClient(Protocol):
    async def ensure_ready(self) -> None: ...


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueueState(StrictModel):
    name: str
    queued: int = Field(ge=0)
    processing: int = Field(ge=0)


class OperationsAlert(StrictModel):
    code: str
    component: str
    severity: Literal["warning", "critical"]
    value: float
    threshold: float
    runbook: str
    would_notify_external: Literal[False] = False


class RetentionPolicyRead(StrictModel):
    provider_ledger_days: int = Field(ge=1)
    evidence_days: int = Field(ge=1)
    operations_log_days: int = Field(ge=1)
    cleanup_enabled: bool


class OperationsSnapshot(StrictModel):
    schema_version: int = 1
    captured_at_utc: datetime
    state_backend: str = "postgresql"
    queue_backend: str = "redis-transient-rebuildable"
    object_storage_provider: str
    dependency_health: dict[str, bool]
    queues: list[QueueState]
    job_status_counts: dict[str, int]
    failed_jobs: int = Field(ge=0)
    disk_used_percent: float = Field(ge=0, le=100)
    provider_safety: ProviderSafetySnapshot
    committed_cost_vnd: Decimal = Field(ge=0)
    currency: Literal["VND"] = "VND"
    alerts: list[OperationsAlert]
    external_notifications_enabled: Literal[False] = False
    request_id_header: str = "X-Request-ID"
    correlation_id_header: str = "X-Correlation-ID"
    structured_logging_enabled: Literal[True] = True
    secret_redaction_enforced: Literal[True] = True
    retention: RetentionPolicyRead


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def redact_secret_fields(value: Any) -> Any:
    """Return a secret-safe structure for operational logs and evidence."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            redacted[str(key)] = (
                "[REDACTED]"
                if any(part in normalized for part in FORBIDDEN_KEY_PARTS)
                else redact_secret_fields(child)
            )
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_secret_fields(child) for child in value]
    return value


class OperationsObservabilityService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        redis: QueueClient,
        object_storage: DependencyHealthClient,
        provider_safety: ProviderSafetyController,
        job_storage_root: Path,
        object_storage_provider: str,
        queue_backlog_warning: int,
        failed_jobs_warning: int,
        disk_warning_percent: float,
        disk_critical_percent: float,
        provider_ledger_retention_days: int,
        evidence_retention_days: int,
        operations_log_retention_days: int,
        retention_cleanup_enabled: bool,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.object_storage = object_storage
        self.provider_safety = provider_safety
        self.job_storage_root = job_storage_root
        self.object_storage_provider = object_storage_provider
        self.queue_backlog_warning = queue_backlog_warning
        self.failed_jobs_warning = failed_jobs_warning
        self.disk_warning_percent = disk_warning_percent
        self.disk_critical_percent = disk_critical_percent
        self.provider_ledger_retention_days = provider_ledger_retention_days
        self.evidence_retention_days = evidence_retention_days
        self.operations_log_retention_days = operations_log_retention_days
        self.retention_cleanup_enabled = retention_cleanup_enabled

    async def snapshot(self) -> OperationsSnapshot:
        dependency_health = {"postgresql": True, "redis": True, "object_storage": True}
        try:
            await self.redis.ping()
            queues = [
                QueueState(
                    name=name,
                    queued=int(await self.redis.llen(queued_key)),
                    processing=int(await self.redis.llen(processing_key)),
                )
                for name, queued_key, processing_key in QUEUE_PAIRS
            ]
        except Exception:  # pragma: no cover - connector-specific exception classes
            dependency_health["redis"] = False
            queues = [QueueState(name=name, queued=0, processing=0) for name, _, _ in QUEUE_PAIRS]
        try:
            await self.object_storage.ensure_ready()
        except Exception:  # pragma: no cover - connector-specific exception classes
            dependency_health["object_storage"] = False
        try:
            async with self.session_factory() as session:
                rows = (
                    await session.execute(
                        select(JobORM.status, func.count(JobORM.job_id)).group_by(JobORM.status)
                    )
                ).all()
        except Exception:  # pragma: no cover - database driver-specific failures
            dependency_health["postgresql"] = False
            rows = []
        job_status_counts = {str(status): int(count) for status, count in rows}
        failed_jobs = job_status_counts.get("failed", 0)
        provider = await self.provider_safety.snapshot()
        disk_probe = self.job_storage_root
        while not disk_probe.exists() and disk_probe != disk_probe.parent:
            disk_probe = disk_probe.parent
        usage = shutil.disk_usage(disk_probe)
        disk_percent = round((usage.used / usage.total) * 100, 3) if usage.total else 0.0
        return OperationsSnapshot(
            captured_at_utc=utc_now(),
            object_storage_provider=self.object_storage_provider,
            dependency_health=dependency_health,
            queues=queues,
            job_status_counts=job_status_counts,
            failed_jobs=failed_jobs,
            disk_used_percent=disk_percent,
            provider_safety=provider,
            committed_cost_vnd=provider.committed_today_vnd,
            alerts=self._alerts(queues, failed_jobs, disk_percent, provider, dependency_health),
            retention=RetentionPolicyRead(
                provider_ledger_days=self.provider_ledger_retention_days,
                evidence_days=self.evidence_retention_days,
                operations_log_days=self.operations_log_retention_days,
                cleanup_enabled=self.retention_cleanup_enabled,
            ),
        )

    def _alerts(
        self,
        queues: list[QueueState],
        failed_jobs: int,
        disk_percent: float,
        provider: ProviderSafetySnapshot,
        dependency_health: dict[str, bool],
    ) -> list[OperationsAlert]:
        alerts: list[OperationsAlert] = []
        queue_total = sum(item.queued + item.processing for item in queues)
        if queue_total >= self.queue_backlog_warning:
            alerts.append(self._alert("QUEUE_BACKLOG_WARNING", "worker", "warning", queue_total, self.queue_backlog_warning, "queue-backlog"))
        if failed_jobs >= self.failed_jobs_warning:
            alerts.append(self._alert("FAILED_JOB_WARNING", "worker", "warning", failed_jobs, self.failed_jobs_warning, "failed-jobs"))
        if disk_percent >= self.disk_warning_percent:
            critical = disk_percent >= self.disk_critical_percent
            alerts.append(self._alert("DISK_PRESSURE", "storage", "critical" if critical else "warning", disk_percent, self.disk_critical_percent if critical else self.disk_warning_percent, "disk-pressure"))
        if provider.stale_active_operations:
            alerts.append(self._alert("PROVIDER_OPERATION_STALE", "provider-safety", "critical", provider.stale_active_operations, 1, "provider-degradation"))
        if provider.daily_limit_vnd > 0:
            cost_percent = float((provider.committed_today_vnd / provider.daily_limit_vnd) * 100)
            warning_threshold = min(provider.warning_threshold_percent)
            if cost_percent >= warning_threshold:
                severity = "critical" if cost_percent >= 100 else "warning"
                alerts.append(self._alert("COST_THRESHOLD", "provider-safety", severity, cost_percent, warning_threshold, "cost-threshold"))
        if not dependency_health.get("object_storage", False):
            alerts.append(self._alert("STORAGE_UNAVAILABLE", "object-storage", "critical", 0, 1, "storage-unavailable"))
        for component in ("postgresql", "redis"):
            if not dependency_health.get(component, False):
                alerts.append(self._alert("SERVICE_UNHEALTHY", component, "critical", 0, 1, "service-unhealthy"))
        if provider.external_execution_enabled or not provider.global_kill_switch_engaged:
            alerts.append(self._alert("PROVIDER_SAFETY_BOUNDARY_OPEN", "provider-safety", "critical", 1, 0, "safety-boundary"))
        return alerts

    @staticmethod
    def _alert(
        code: str,
        component: str,
        severity: Literal["warning", "critical"],
        value: float,
        threshold: float,
        anchor: str,
    ) -> OperationsAlert:
        return OperationsAlert(
            code=code,
            component=component,
            severity=severity,
            value=value,
            threshold=threshold,
            runbook=f"docs/acceptance/v3-01/runbooks/DR_OBSERVABILITY.md#{anchor}",
        )
