from __future__ import annotations

from decimal import Decimal

import pytest

from app.db import (
    JobORM,
    ProjectVersionORM,
    VideoProjectORM,
    WorkspaceORM,
    create_engine,
    create_session_factory,
)
from app.operations_observability import (
    OperationsObservabilityService,
    QueueState,
    redact_secret_fields,
)
from app.provider_safety import (
    ProviderBudgetPolicy,
    ProviderSafetyController,
    ProviderSafetyPolicy,
)


class FakeRedis:
    def __init__(self, lengths: dict[str, int] | None = None) -> None:
        self.lengths = lengths or {}
        self.pings = 0

    async def ping(self) -> bool:
        self.pings += 1
        return True

    async def llen(self, key: str) -> int:
        return self.lengths.get(key, 0)


class FakeStorage:
    async def ensure_ready(self) -> None:
        return None


async def service(tmp_path, *, redis: FakeRedis, controller: ProviderSafetyController):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'ops.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: WorkspaceORM.metadata.create_all(
                sync_connection,
                tables=[
                    WorkspaceORM.__table__,
                    VideoProjectORM.__table__,
                    ProjectVersionORM.__table__,
                    JobORM.__table__,
                ],
            )
        )
    sessions = create_session_factory(engine)
    return engine, sessions, OperationsObservabilityService(
        session_factory=sessions,
        redis=redis,
        object_storage=FakeStorage(),
        provider_safety=controller,
        job_storage_root=tmp_path / "jobs",
        object_storage_provider="local",
        queue_backlog_warning=2,
        failed_jobs_warning=1,
        disk_warning_percent=99.0,
        disk_critical_percent=100.0,
        provider_ledger_retention_days=400,
        evidence_retention_days=400,
        operations_log_retention_days=30,
        retention_cleanup_enabled=False,
    )


@pytest.mark.asyncio
async def test_snapshot_reports_queue_job_cost_and_fail_closed_safety(tmp_path) -> None:
    redis = FakeRedis({"npd:video-jobs:queue": 2})
    engine, sessions, collector = await service(
        tmp_path,
        redis=redis,
        controller=ProviderSafetyController.fail_closed(),
    )
    async with sessions() as session:
        async with session.begin():
            session.add(
                JobORM(
                    job_id="job-failed-001",
                    status="failed",
                    stage="render",
                    progress=70,
                    request_json={},
                    artifacts_json=[],
                    error_json={"code": "fixture"},
                )
            )
    snapshot = await collector.snapshot()
    assert redis.pings == 1
    assert not (tmp_path / "jobs").exists()
    assert snapshot.job_status_counts == {"failed": 1}
    assert snapshot.currency == "VND"
    assert snapshot.committed_cost_vnd == Decimal("0")
    assert snapshot.provider_safety.global_kill_switch_engaged is True
    assert snapshot.provider_safety.external_execution_enabled is False
    assert {item.code for item in snapshot.alerts} == {
        "QUEUE_BACKLOG_WARNING",
        "FAILED_JOB_WARNING",
    }
    assert all(item.would_notify_external is False for item in snapshot.alerts)
    assert snapshot.external_notifications_enabled is False
    assert snapshot.secret_redaction_enforced is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_all_required_alert_scenarios_are_secret_free_previews(tmp_path) -> None:
    controller = ProviderSafetyController.fail_closed()
    engine, _, collector = await service(tmp_path, redis=FakeRedis(), controller=controller)
    provider = (await controller.snapshot()).model_copy(
        update={
            "daily_limit_vnd": Decimal("100"),
            "committed_today_vnd": Decimal("80"),
            "stale_active_operations": 1,
        }
    )
    alerts = collector._alerts(
        [QueueState(name="video_jobs", queued=2, processing=0)],
        1,
        100.0,
        provider,
        {"postgresql": False, "redis": False, "object_storage": False},
    )
    assert {item.code for item in alerts} >= {
        "QUEUE_BACKLOG_WARNING",
        "PROVIDER_OPERATION_STALE",
        "STORAGE_UNAVAILABLE",
        "DISK_PRESSURE",
        "FAILED_JOB_WARNING",
        "COST_THRESHOLD",
        "SERVICE_UNHEALTHY",
    }
    assert all(item.would_notify_external is False for item in alerts)
    await engine.dispose()


@pytest.mark.asyncio
async def test_open_provider_boundary_is_visible_as_critical_preview(tmp_path) -> None:
    controller = ProviderSafetyController(
        ProviderSafetyPolicy(
            external_execution_enabled=True,
            paid_execution_enabled=False,
            global_kill_switch_engaged=False,
            credential_gate_approved=True,
            rights_gate_approved=False,
            budget=ProviderBudgetPolicy(
                approved=False,
                per_operation_limit_vnd=Decimal("0"),
                daily_limit_vnd=Decimal("0"),
            ),
        )
    )
    engine, _, collector = await service(tmp_path, redis=FakeRedis(), controller=controller)
    snapshot = await collector.snapshot()
    alert = next(item for item in snapshot.alerts if item.code == "PROVIDER_SAFETY_BOUNDARY_OPEN")
    assert alert.severity == "critical"
    assert alert.would_notify_external is False
    await engine.dispose()


def test_secret_redaction_is_recursive_and_preserves_safe_metadata() -> None:
    payload = {
        "request_id": "req-001",
        "Authorization-Token": "do-not-log",
        "nested": {"password": "do-not-log", "status": "healthy"},
        "items": [{"api_key": "do-not-log", "cost_vnd": 0}],
    }
    redacted = redact_secret_fields(payload)
    assert redacted["request_id"] == "req-001"
    assert redacted["Authorization-Token"] == "[REDACTED]"
    assert redacted["nested"] == {"password": "[REDACTED]", "status": "healthy"}
    assert redacted["items"][0] == {"api_key": "[REDACTED]", "cost_vnd": 0}
