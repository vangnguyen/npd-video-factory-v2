from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from app.dr_g11_offline import (
    ARTIFACT_KEYS,
    BACKUP_FILES,
    DisposableMonitorStore,
    audit_backup,
    canonical_sha256,
    lock_review_artifacts,
    measure_disposable_drill,
    normalize_operations_snapshot,
    prepare_g11_review,
    rollback_rehearsal_plan,
    validate_g11_review,
    verify_review_artifacts,
)


ROOT = Path(__file__).resolve().parents[3]
G11 = ROOT / "docs/acceptance/v3-01"
RC = "a" * 40


def snapshot(at: str = "2026-09-17T10:00:00Z") -> dict:
    return {
        "captured_at_utc": at,
        "dependency_health": {"postgresql": True, "redis": True, "object_storage": True},
        "queues": [
            {"name": name, "queued": 0, "processing": 0}
            for name in ("video_jobs", "media_resolution", "preview", "production_render", "analytics", "agent_hub_webhook")
        ],
        "failed_jobs": 0,
        "disk_used_percent": 12.5,
        "committed_cost_vnd": "0",
        "currency": "VND",
        "alerts": [{
            "code": "QUEUE_BACKLOG_WARNING", "component": "worker", "severity": "warning",
            "value": 5, "threshold": 5,
            "runbook": "docs/acceptance/v3-01/runbooks/DR_OBSERVABILITY.md#queue-backlog",
            "would_notify_external": False,
        }],
        "provider_safety": {
            "external_execution_enabled": False,
            "paid_execution_enabled": False,
            "global_kill_switch_engaged": True,
            "api_key": "must-not-be-persisted",
        },
        "external_notifications_enabled": False,
        "secret_redaction_enforced": True,
        "customer_name": "must-not-be-persisted",
    }


def test_local_monitor_store_is_hash_chained_and_whitelist_redacted(tmp_path: Path) -> None:
    store = DisposableMonitorStore(tmp_path / "vf-dr-local-one", rc_commit=RC, create=True)
    first = store.append(snapshot())
    assert first["external_alerts_sent"] == 0
    second = store.append(snapshot("2026-09-17T10:01:00Z"))
    assert second["seq"] == 2
    assert store.verify()["samples"] == 2
    raw = store.db_path.read_bytes()
    assert b"must-not-be-persisted" not in raw
    plan = store.prepare_soak()
    assert plan["status"] == "PREPARATION_ONLY_NOT_PRODUCTION_SOAK"
    assert plan["soak_started"] is False
    assert plan["observed_span_seconds"] == 60


def test_monitor_rejects_external_delivery_and_open_kill_switch() -> None:
    payload = snapshot()
    payload["alerts"][0]["would_notify_external"] = True
    with pytest.raises(ValueError, match="unapproved alert"):
        normalize_operations_snapshot(payload)
    payload = snapshot()
    payload["provider_safety"]["global_kill_switch_engaged"] = False
    with pytest.raises(ValueError, match="kill switch"):
        normalize_operations_snapshot(payload)


def test_monitor_rejects_wrong_store_and_timestamp_replay(tmp_path: Path) -> None:
    path = tmp_path / "vf-dr-local-two"
    store = DisposableMonitorStore(path, rc_commit=RC, create=True)
    store.append(snapshot())
    with pytest.raises(ValueError, match="increasing"):
        store.append(snapshot())
    with pytest.raises(ValueError, match="another RC"):
        DisposableMonitorStore(path, rc_commit="b" * 40)


def test_monitor_detects_row_tamper(tmp_path: Path) -> None:
    store = DisposableMonitorStore(tmp_path / "vf-dr-local-three", rc_commit=RC, create=True)
    store.append(snapshot())
    with sqlite3.connect(store.db_path) as db:
        db.execute("UPDATE samples SET payload = ? WHERE seq = 1", ('{"tampered":true}',))
    with pytest.raises((KeyError, ValueError), match="serialization|captured_at"):
        store.verify()


def test_monitor_detects_gaps_but_never_promotes_a_soak(tmp_path: Path) -> None:
    store = DisposableMonitorStore(tmp_path / "vf-dr-local-four", rc_commit=RC, create=True)
    store.append(snapshot())
    store.append(snapshot("2026-09-17T10:10:00Z"))
    plan = store.prepare_soak()
    assert plan["oversized_gap_seconds"] == [600]
    assert plan["human_acceptance"] == "NOT_PERFORMED"
    with pytest.raises(ValueError, match="weakened"):
        store.prepare_soak(minimum_hours=24)


def test_backup_audit_checks_all_files_and_lineage(tmp_path: Path) -> None:
    root = tmp_path / "backup"
    root.mkdir()
    hashes = {}
    for name in BACKUP_FILES:
        value = RC if name == "git-sha.txt" else "redis-recovery=rebuild-from-postgresql" if name == "redis-recovery-policy.txt" else "0015_v3_01_dispatch" if name == "migration-head.txt" else "synthetic"
        (root / name).write_text(value, encoding="utf-8")
        import hashlib
        hashes[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())), encoding="utf-8")
    assert audit_backup(root, RC)["status"] == "PASS_LOCAL_BACKUP_INTEGRITY_ONLY"
    (root / "postgres.dump").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        audit_backup(root, RC)


def test_disposable_rpo_rto_checked_without_production_claim() -> None:
    path = ROOT / "evidence/v3-01/vf-v3-01-20260828T073400Z-527fd1f/operations/dr-observability/drill-summary.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    result = measure_disposable_drill(report)
    assert result["observed_local_rpo_seconds"] == 0
    assert result["drill_elapsed_seconds"] == 33
    assert result["outage_to_recovery_rto_seconds"] is None
    assert result["status"] == "HISTORICAL_DRILL_ELAPSED_ONLY_RTO_NOT_VERIFIED"
    assert result["production_path_tested"] is False
    report["outage_started_at_utc"] = "2026-08-28T07:34:05Z"
    report["recovery_completed_at_utc"] = "2026-08-28T07:34:30Z"
    report["total_drill_elapsed_seconds"] = 33
    report["measured_rto_seconds"] = 25
    report["measured_rpo_basis"] = "all_nine_recovery_target_hashes_and_pending_work_recovered_without_post_backup_writes"
    assert measure_disposable_drill(report)["outage_to_recovery_rto_seconds"] == 25
    report["measured_rto_seconds"] = 1
    with pytest.raises(ValueError, match="outage-to-recovery"):
        measure_disposable_drill(report)


def test_disposable_drill_script_records_actual_outage_window() -> None:
    script = (ROOT / "scripts/v3-01-dr-observability-drill.sh").read_text(encoding="utf-8")
    assert 'outage_started_epoch="$(date -u +%s)"' in script
    assert 'recovery_completed_epoch="$(date -u +%s)"' in script
    assert '"total_drill_elapsed_seconds": int(sys.argv[8])' in script


def test_local_rpo_rto_thresholds_match_existing_v3_policy() -> None:
    policy = json.loads((ROOT / "packages/contracts/dr-observability-acceptance.v1.json").read_text(encoding="utf-8"))
    assert policy["maximum_local_rpo_seconds"] == 60
    assert policy["maximum_local_rto_seconds"] == 900
    assert policy["external_notifications_allowed"] is False
    assert policy["production_restore_allowed"] is False


def test_rollback_plan_requires_immutable_distinct_images_and_never_executes() -> None:
    result = rollback_rehearsal_plan(
        candidate_commit=RC,
        previous_commit="b" * 40,
        candidate_image=f"example/api@sha256:{'1' * 64}",
        previous_image=f"example/api@sha256:{'2' * 64}",
    )
    assert result["status"] == "PLAN_ONLY_NOT_REHEARSED"
    assert result["production_mutation"] is False
    assert len(result["plan_sha256"]) == 64
    with pytest.raises(ValueError, match="immutable"):
        rollback_rehearsal_plan(candidate_commit=RC, previous_commit="b" * 40, candidate_image="example/api:latest", previous_image=f"example/api@sha256:{'2' * 64}")


def artifacts(tmp_path: Path) -> dict[str, Path]:
    result = {}
    for name in ARTIFACT_KEYS:
        path = tmp_path / f"{name}.bin"
        path.write_bytes(f"synthetic {name}".encode())
        result[name] = path
    return result


def g11_files() -> tuple[dict, dict]:
    template = json.loads((G11 / "templates/V3-01-G11-HUMAN-QUALITY-REVIEW.template.json").read_text(encoding="utf-8"))
    schema = json.loads((G11 / "schemas/human-quality-review.schema.json").read_text(encoding="utf-8"))
    return template, schema


def test_review_lock_and_prepared_27_check_package(tmp_path: Path) -> None:
    paths = artifacts(tmp_path)
    lock = lock_review_artifacts(rc_commit=RC, artifacts=paths)
    template, schema = g11_files()
    review = prepare_g11_review(lock, template)
    assert review["decision"] == "REVIEW_REQUIRED"
    assert review["review_context"]["headphones"] is False
    result = validate_g11_review(review, schema, template, lock)
    assert result["checks"] == 27
    assert result["human_acceptance_attested_by_tool"] is False
    assert verify_review_artifacts(lock, paths)["status"] == "PASS_EXACT_ARTIFACT_HASHES_ONLY"
    paths["voice"].write_bytes(b"mutated")
    with pytest.raises(ValueError, match="differ from the exact locked manifest"):
        verify_review_artifacts(lock, paths)


def test_review_rejects_missing_or_duplicate_check(tmp_path: Path) -> None:
    lock = lock_review_artifacts(rc_commit=RC, artifacts=artifacts(tmp_path))
    template, schema = g11_files()
    review = prepare_g11_review(lock, template)
    review["checks"][-1] = deepcopy(review["checks"][0])
    with pytest.raises(ValueError, match="27 distinct"):
        validate_g11_review(review, schema, template, lock)


def test_review_rejects_rewritten_requirements_and_invalidation(tmp_path: Path) -> None:
    lock = lock_review_artifacts(rc_commit=RC, artifacts=artifacts(tmp_path))
    template, schema = g11_files()
    review = prepare_g11_review(lock, template)
    review["checks"][0]["requirement"] = "Everything looks fine."
    with pytest.raises(ValueError, match="check contract changed"):
        validate_g11_review(review, schema, template, lock)
    review = prepare_g11_review(lock, template)
    review["invalidation"] = review["invalidation"][:-1]
    with pytest.raises(ValueError, match="invalidation rules changed"):
        validate_g11_review(review, schema, template, lock)


def test_review_rejects_fake_accept_and_changed_binding(tmp_path: Path) -> None:
    lock = lock_review_artifacts(rc_commit=RC, artifacts=artifacts(tmp_path))
    template, schema = g11_files()
    review = prepare_g11_review(lock, template)
    review["artifact_bindings"]["voice_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="changed after lock"):
        validate_g11_review(review, schema, template, lock)
    review = prepare_g11_review(lock, template)
    review["decision"] = "ACCEPT"
    with pytest.raises(ValueError, match="G-11 schema"):
        validate_g11_review(review, schema, template, lock)


def test_structurally_complete_g11_still_does_not_claim_human_attestation(tmp_path: Path) -> None:
    lock = lock_review_artifacts(rc_commit=RC, artifacts=artifacts(tmp_path))
    template, schema = g11_files()
    review = prepare_g11_review(lock, template)
    review["status"] = "COMPLETE"
    review["decision"] = "ACCEPT"
    review["review_context"] = {key: True for key in review["review_context"]}
    review["reviewer"] = {"name": "Synthetic Test Reviewer", "role": "test", "started_at_utc": "2026-09-17T10:00:00Z", "completed_at_utc": "2026-09-17T10:03:00Z"}
    for check in review["checks"]:
        check["result"] = "PASS"
    review["evidence_sha256"] = canonical_sha256({key: value for key, value in review.items() if key != "evidence_sha256"})
    result = validate_g11_review(review, schema, template, lock)
    assert result["status"] == "PASS_STRUCTURAL_ONLY"
    assert result["human_acceptance_attested_by_tool"] is False


def test_offline_review_page_has_no_external_connect_or_auto_accept() -> None:
    page = (G11 / "tools/g11_offline_review.html").read_text(encoding="utf-8")
    assert "connect-src 'none'" in page
    assert "crypto.subtle.digest('SHA-256'" in page
    assert "HUMAN REVIEW STILL REQUIRED" in page
    assert "fetch(" not in page
    assert "XMLHttpRequest" not in page
