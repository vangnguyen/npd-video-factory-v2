from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.dr_observability_acceptance import (
    REQUIRED_ALERT_SCENARIOS,
    REQUIRED_RECOVERY_TARGETS,
    DRObservabilityBundle,
    DRObservabilityPolicy,
    evaluate_dr_observability,
)


def policy() -> DRObservabilityPolicy:
    root = Path(__file__).resolve().parents[3]
    return DRObservabilityPolicy.model_validate_json(
        (root / "packages" / "contracts" / "dr-observability-acceptance.v1.json").read_text(
            encoding="utf-8"
        )
    )


def bundle() -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema_version": 1,
        "checkpoint": "V3-01-07",
        "release_candidate_commit": "b" * 40,
        "gates": {
            "g04_production_like_staging": False,
            "g08_merge": False,
            "g09_deploy_locked_rc": False,
            "g10_accept_dr": False,
            "g12_final_verdict": False,
            "approval_ids": [],
        },
        "safety": {
            "external_execution_enabled": False,
            "paid_execution_enabled": False,
            "global_kill_switch_engaged": True,
            "daily_budget_vnd": 0,
            "external_notifications_enabled": False,
            "production_write_performed": False,
            "publish_performed": False,
        },
        "drill": {
            "run_id": "dr-local-001",
            "release_candidate_commit": "b" * 40,
            "environment": "LOCAL_DISPOSABLE_DOCKER",
            "started_at_utc": "2026-08-28T07:00:00Z",
            "completed_at_utc": "2026-08-28T07:05:00Z",
            "source_and_restore_targets_isolated": True,
            "backup_integrity_verified": True,
            "migration_head_before": "0011_v3_01_03",
            "migration_head_after": "0011_v3_01_03",
            "recovery_targets": [
                {
                    "target": target,
                    "backup_sha256": digest,
                    "restored_sha256": digest,
                    "verified": True,
                }
                for target in REQUIRED_RECOVERY_TARGETS
            ],
            "postgres_counts_equal": True,
            "redis_recovery_mode": "rebuild_from_postgresql",
            "redis_queue_rebuilt": True,
            "pending_work_resumed": True,
            "worker_restarted": True,
            "services_ready_after_restore": True,
            "no_duplicate_external_action": True,
            "external_action_count": 0,
            "external_notification_count": 0,
            "production_write_count": 0,
            "measured_rpo_seconds": 0,
            "measured_rto_seconds": 300,
            "request_id_propagated": True,
            "job_id_correlated": True,
            "project_id_correlated": True,
            "structured_logs_verified": True,
            "health_and_readiness_verified": True,
            "queue_backlog_visible": True,
            "failed_jobs_visible": True,
            "provider_degradation_visible": True,
            "disk_pressure_visible": True,
            "cost_budget_visible": True,
            "secret_redaction_verified": True,
            "retention_policy_verified": True,
            "alert_scenarios": [
                {
                    "scenario": scenario,
                    "detected": True,
                    "severity": "critical" if scenario in {"storage_unavailable", "service_unhealthy"} else "warning",
                    "correlation_id": f"corr-{scenario}",
                    "runbook": f"runbook#{scenario}",
                    "secret_recorded": False,
                    "external_notification_sent": False,
                }
                for scenario in REQUIRED_ALERT_SCENARIOS
            ],
            "currency": "VND",
            "cost_total_vnd": 0,
            "secret_recorded": False,
            "real_provider_tested": False,
            "production_path_tested": False,
        },
        "soak_started": False,
        "soak_duration_hours": 0,
        "secret_recorded": False,
    }


def evaluation(payload: dict[str, object]):
    return evaluate_dr_observability(DRObservabilityBundle.model_validate(payload), policy())


def test_disposable_drill_passes_local_axis_but_keeps_production_and_soak_blocked() -> None:
    result = evaluation(bundle())
    assert result.implemented.status == "PASS"
    assert result.local_disposable_drill.status == "PASS"
    assert result.production_path_tested.status == "BLOCKED"
    assert result.soak_accepted.status == "BLOCKED"
    assert result.pending_owner_gates == ["G-04", "G-08", "G-09", "G-10", "G-12"]
    assert result.verdict == "BLOCKED"
    assert result.external_actions_performed is False
    assert result.external_notifications_sent is False
    assert result.cost_total_vnd == 0


def test_restore_hash_tamper_fails_local_axis() -> None:
    payload = bundle()
    payload["drill"]["recovery_targets"][0]["restored_sha256"] = "c" * 64  # type: ignore[index]
    result = evaluation(payload)
    assert result.local_disposable_drill.status == "FAIL"
    assert "RECOVERY_TARGET_INTEGRITY_FAILED:postgresql" in result.failures
    assert result.verdict == "FAIL"


def test_missing_alert_and_recovery_target_fail_closed() -> None:
    payload = bundle()
    payload["drill"]["alert_scenarios"].pop()  # type: ignore[index]
    payload["drill"]["recovery_targets"].pop()  # type: ignore[index]
    result = evaluation(payload)
    assert any(item.startswith("ALERT_SCENARIO_NOT_DETECTED:") for item in result.failures)
    assert any(item.startswith("RECOVERY_TARGET_MISSING:") for item in result.failures)


def test_rpo_rto_and_pending_recovery_are_measured() -> None:
    payload = bundle()
    payload["drill"]["measured_rpo_seconds"] = 61  # type: ignore[index]
    payload["drill"]["measured_rto_seconds"] = 901  # type: ignore[index]
    payload["drill"]["pending_work_resumed"] = False  # type: ignore[index]
    result = evaluation(payload)
    assert set(result.failures) >= {
        "LOCAL_RPO_THRESHOLD_EXCEEDED",
        "LOCAL_RTO_THRESHOLD_EXCEEDED",
        "PENDING_WORK_NOT_RESUMED",
    }


def test_external_action_cost_or_notification_fails_local_drill() -> None:
    payload = bundle()
    payload["drill"]["external_action_count"] = 1  # type: ignore[index]
    payload["drill"]["external_notification_count"] = 1  # type: ignore[index]
    payload["drill"]["cost_total_vnd"] = 1  # type: ignore[index]
    result = evaluation(payload)
    assert set(result.failures) >= {
        "OFFLINE_DRILL_EXTERNAL_OR_COST_BOUNDARY_VIOLATED",
        "EXTERNAL_NOTIFICATION_BOUNDARY_VIOLATED",
    }


def test_local_fixture_cannot_claim_production_path() -> None:
    payload = bundle()
    payload["drill"]["production_path_tested"] = True  # type: ignore[index]
    with pytest.raises(ValidationError, match="local disposable drill"):
        DRObservabilityBundle.model_validate(payload)


def test_commit_binding_is_required() -> None:
    payload = bundle()
    payload["drill"]["release_candidate_commit"] = "d" * 40  # type: ignore[index]
    with pytest.raises(ValidationError, match="locked evidence commit"):
        DRObservabilityBundle.model_validate(payload)


def test_policy_is_strict_vnd_and_no_external_notification_or_production_restore() -> None:
    checked = policy()
    assert checked.currency == "VND"
    assert checked.external_notifications_allowed is False
    assert checked.production_restore_allowed is False
    raw = json.loads(checked.model_dump_json())
    raw["currency"] = "USD"
    with pytest.raises(ValidationError):
        DRObservabilityPolicy.model_validate(raw)
