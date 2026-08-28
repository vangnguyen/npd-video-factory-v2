from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AxisStatus = Literal["PASS", "FAIL", "BLOCKED"]
REQUIRED_ALERT_SCENARIOS = (
    "queue_backlog",
    "provider_degradation",
    "storage_unavailable",
    "disk_pressure",
    "failed_job",
    "cost_threshold",
    "service_unhealthy",
)
REQUIRED_RECOVERY_TARGETS = (
    "postgresql",
    "object_storage",
    "provider_safety_state",
    "worker_pending_work",
    "render_state",
    "publication_retry_state",
    "webhook_retry_state",
    "analytics_snapshot_state",
    "audit_evidence",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AxisEvaluation(StrictModel):
    status: AxisStatus
    reasons: list[str]


class DRObservabilityPolicy(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-07"] = "V3-01-07"
    required_alert_scenarios: tuple[str, ...]
    required_recovery_targets: tuple[str, ...]
    maximum_local_rpo_seconds: int = Field(gt=0)
    maximum_local_rto_seconds: int = Field(gt=0)
    evidence_retention_days: int = Field(ge=30)
    log_retention_days: int = Field(ge=7)
    currency: Literal["VND"] = "VND"
    external_notifications_allowed: Literal[False] = False
    production_restore_allowed: Literal[False] = False


class RecoveryTarget(StrictModel):
    target: str
    backup_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    restored_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    verified: bool


class AlertScenario(StrictModel):
    scenario: str
    detected: bool
    severity: Literal["warning", "critical"]
    correlation_id: str
    runbook: str
    secret_recorded: Literal[False] = False
    external_notification_sent: Literal[False] = False


class DRDrillRun(StrictModel):
    run_id: str
    release_candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    environment: Literal["LOCAL_DISPOSABLE_DOCKER", "STAGING_PRODUCTION_LIKE"]
    started_at_utc: datetime
    completed_at_utc: datetime
    source_and_restore_targets_isolated: bool
    backup_integrity_verified: bool
    migration_head_before: str
    migration_head_after: str
    recovery_targets: list[RecoveryTarget]
    postgres_counts_equal: bool
    redis_recovery_mode: Literal["rebuild_from_postgresql"]
    redis_queue_rebuilt: bool
    pending_work_resumed: bool
    worker_restarted: bool
    services_ready_after_restore: bool
    no_duplicate_external_action: bool
    external_action_count: int = Field(ge=0)
    external_notification_count: int = Field(ge=0)
    production_write_count: int = Field(ge=0)
    measured_rpo_seconds: int = Field(ge=0)
    measured_rto_seconds: int = Field(ge=0)
    request_id_propagated: bool
    job_id_correlated: bool
    project_id_correlated: bool
    structured_logs_verified: bool
    health_and_readiness_verified: bool
    queue_backlog_visible: bool
    failed_jobs_visible: bool
    provider_degradation_visible: bool
    disk_pressure_visible: bool
    cost_budget_visible: bool
    secret_redaction_verified: bool
    retention_policy_verified: bool
    alert_scenarios: list[AlertScenario]
    currency: Literal["VND"] = "VND"
    cost_total_vnd: int = Field(ge=0)
    secret_recorded: Literal[False] = False
    real_provider_tested: Literal[False] = False
    production_path_tested: bool = False

    @model_validator(mode="after")
    def fixture_cannot_claim_production(self) -> "DRDrillRun":
        if self.environment == "LOCAL_DISPOSABLE_DOCKER" and self.production_path_tested:
            raise ValueError("local disposable drill cannot be promoted to production-path evidence")
        return self


class DRGates(StrictModel):
    g04_production_like_staging: bool = False
    g08_merge: bool = False
    g09_deploy_locked_rc: bool = False
    g10_accept_dr: bool = False
    g12_final_verdict: bool = False
    approval_ids: list[str] = Field(default_factory=list)


class DRSafety(StrictModel):
    external_execution_enabled: Literal[False] = False
    paid_execution_enabled: Literal[False] = False
    global_kill_switch_engaged: Literal[True] = True
    daily_budget_vnd: Literal[0] = 0
    external_notifications_enabled: Literal[False] = False
    production_write_performed: Literal[False] = False
    publish_performed: Literal[False] = False


class DRObservabilityBundle(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-07"] = "V3-01-07"
    release_candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    gates: DRGates
    safety: DRSafety
    drill: DRDrillRun
    soak_started: bool = False
    soak_duration_hours: float = Field(default=0, ge=0)
    secret_recorded: Literal[False] = False

    @model_validator(mode="after")
    def validate_commit_binding(self) -> "DRObservabilityBundle":
        if self.drill.release_candidate_commit != self.release_candidate_commit:
            raise ValueError("DR drill must be bound to the locked evidence commit")
        return self


class DRObservabilityEvaluation(StrictModel):
    implemented: AxisEvaluation
    local_disposable_drill: AxisEvaluation
    production_path_tested: AxisEvaluation
    soak_accepted: AxisEvaluation
    failures: list[str]
    pending_owner_gates: list[str]
    verdict: Literal["PASS", "FAIL", "BLOCKED"]
    external_actions_performed: bool
    external_notifications_sent: bool
    cost_total_vnd: int


def evaluate_dr_observability(
    bundle: DRObservabilityBundle,
    policy: DRObservabilityPolicy,
) -> DRObservabilityEvaluation:
    failures: list[str] = []
    drill = bundle.drill
    targets = {item.target: item for item in drill.recovery_targets}
    for target in policy.required_recovery_targets:
        item = targets.get(target)
        if item is None:
            failures.append(f"RECOVERY_TARGET_MISSING:{target}")
        elif not item.verified or item.backup_sha256 != item.restored_sha256:
            failures.append(f"RECOVERY_TARGET_INTEGRITY_FAILED:{target}")
    alert_names = {item.scenario for item in drill.alert_scenarios if item.detected}
    for scenario in policy.required_alert_scenarios:
        if scenario not in alert_names:
            failures.append(f"ALERT_SCENARIO_NOT_DETECTED:{scenario}")
    checks = {
        "SOURCE_RESTORE_ISOLATION_NOT_PROVEN": drill.source_and_restore_targets_isolated,
        "BACKUP_INTEGRITY_NOT_PROVEN": drill.backup_integrity_verified,
        "MIGRATION_HEAD_CHANGED": drill.migration_head_before == drill.migration_head_after,
        "POSTGRES_COUNTS_CHANGED": drill.postgres_counts_equal,
        "REDIS_QUEUE_REBUILD_NOT_PROVEN": drill.redis_queue_rebuilt,
        "PENDING_WORK_NOT_RESUMED": drill.pending_work_resumed,
        "WORKER_RESTART_NOT_PROVEN": drill.worker_restarted,
        "READINESS_AFTER_RESTORE_FAILED": drill.services_ready_after_restore,
        "DUPLICATE_EXTERNAL_ACTION_DETECTED": drill.no_duplicate_external_action,
        "REQUEST_CORRELATION_NOT_PROVEN": drill.request_id_propagated,
        "JOB_CORRELATION_NOT_PROVEN": drill.job_id_correlated,
        "PROJECT_CORRELATION_NOT_PROVEN": drill.project_id_correlated,
        "STRUCTURED_LOGGING_NOT_PROVEN": drill.structured_logs_verified,
        "HEALTH_READINESS_NOT_PROVEN": drill.health_and_readiness_verified,
        "QUEUE_VISIBILITY_NOT_PROVEN": drill.queue_backlog_visible,
        "FAILED_JOB_VISIBILITY_NOT_PROVEN": drill.failed_jobs_visible,
        "PROVIDER_DEGRADATION_VISIBILITY_NOT_PROVEN": drill.provider_degradation_visible,
        "DISK_PRESSURE_VISIBILITY_NOT_PROVEN": drill.disk_pressure_visible,
        "COST_BUDGET_VISIBILITY_NOT_PROVEN": drill.cost_budget_visible,
        "SECRET_REDACTION_NOT_PROVEN": drill.secret_redaction_verified,
        "RETENTION_POLICY_NOT_PROVEN": drill.retention_policy_verified,
    }
    failures.extend(code for code, passed in checks.items() if not passed)
    if drill.measured_rpo_seconds > policy.maximum_local_rpo_seconds:
        failures.append("LOCAL_RPO_THRESHOLD_EXCEEDED")
    if drill.measured_rto_seconds > policy.maximum_local_rto_seconds:
        failures.append("LOCAL_RTO_THRESHOLD_EXCEEDED")
    if drill.external_action_count or drill.production_write_count or drill.cost_total_vnd:
        failures.append("OFFLINE_DRILL_EXTERNAL_OR_COST_BOUNDARY_VIOLATED")
    if drill.external_notification_count:
        failures.append("EXTERNAL_NOTIFICATION_BOUNDARY_VIOLATED")
    if any(item.external_notification_sent for item in drill.alert_scenarios):
        failures.append("ALERT_DELIVERY_BOUNDARY_VIOLATED")

    implemented = AxisEvaluation(
        status="PASS",
        reasons=["DR contract, guarded scripts, authenticated operations snapshot and alert-preview policy are present."],
    )
    local = AxisEvaluation(
        status="PASS" if not failures else "FAIL",
        reasons=["Disposable Docker backup/failure/restore/restart/recovery drill passed."] if not failures else failures,
    )
    production_pass = (
        drill.environment == "STAGING_PRODUCTION_LIKE"
        and drill.production_path_tested
        and bundle.gates.g04_production_like_staging
        and bundle.gates.g09_deploy_locked_rc
        and bundle.gates.g10_accept_dr
    )
    production = AxisEvaluation(
        status="PASS" if production_pass else "BLOCKED",
        reasons=["G-04/G-09/G-10 production-like DR evidence is pending."] if not production_pass else ["Owner-accepted production-like restore evidence passed."],
    )
    soak_pass = bundle.soak_started and bundle.soak_duration_hours >= 48 and bundle.gates.g09_deploy_locked_rc
    soak = AxisEvaluation(
        status="PASS" if soak_pass else "BLOCKED",
        reasons=["A non-backdated 48-hour locked-RC soak has not been accepted."] if not soak_pass else ["Locked-RC 48-hour soak passed."],
    )
    pending = [
        gate
        for gate, approved in (
            ("G-04", bundle.gates.g04_production_like_staging),
            ("G-08", bundle.gates.g08_merge),
            ("G-09", bundle.gates.g09_deploy_locked_rc),
            ("G-10", bundle.gates.g10_accept_dr),
            ("G-12", bundle.gates.g12_final_verdict),
        )
        if not approved
    ]
    verdict: Literal["PASS", "FAIL", "BLOCKED"] = "FAIL" if failures else ("PASS" if production_pass and soak_pass and not pending else "BLOCKED")
    return DRObservabilityEvaluation(
        implemented=implemented,
        local_disposable_drill=local,
        production_path_tested=production,
        soak_accepted=soak,
        failures=failures,
        pending_owner_gates=pending,
        verdict=verdict,
        external_actions_performed=bool(drill.external_action_count or drill.production_write_count),
        external_notifications_sent=bool(drill.external_notification_count),
        cost_total_vnd=drill.cost_total_vnd,
    )
