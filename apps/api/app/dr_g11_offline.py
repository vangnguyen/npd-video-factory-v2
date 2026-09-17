"""Offline DR/monitoring/G-11 preparation; never a production control plane.

This module deliberately has no network, provider, restore, deploy, or alert-delivery
client. Every state-changing helper is restricted to a disposable local directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import argparse
import math
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from .dr_observability_acceptance import REQUIRED_RECOVERY_TARGETS


SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
BACKUP_FILES = frozenset(
    {
        "postgres.dump",
        "minio-data.tar.gz",
        "redis-aof.tar.gz",
        "migration-head.txt",
        "redis-recovery-policy.txt",
        "git-sha.txt",
        "images.json",
        "filesystem-permissions.txt",
    }
)
ARTIFACT_KEYS = (
    "final_video",
    "timeline",
    "subtitle",
    "voice",
    "music",
    "rights_manifest",
    "automated_qc",
)
ALERT_CODES = frozenset(
    {
        "QUEUE_BACKLOG_WARNING",
        "PROVIDER_OPERATION_STALE",
        "STORAGE_UNAVAILABLE",
        "DISK_PRESSURE",
        "FAILED_JOB_WARNING",
        "COST_THRESHOLD",
        "SERVICE_UNHEALTHY",
        "PROVIDER_SAFETY_BOUNDARY_OPEN",
    }
)
ALERT_RUNBOOKS = {
    "QUEUE_BACKLOG_WARNING": "queue-backlog",
    "PROVIDER_OPERATION_STALE": "provider-degradation",
    "STORAGE_UNAVAILABLE": "storage-unavailable",
    "DISK_PRESSURE": "disk-pressure",
    "FAILED_JOB_WARNING": "failed-jobs",
    "COST_THRESHOLD": "cost-threshold",
    "SERVICE_UNHEALTHY": "service-unhealthy",
    "PROVIDER_SAFETY_BOUNDARY_OPEN": "safety-boundary",
}
MONITOR_QUEUE_NAMES = frozenset(
    {"video_jobs", "media_resolution", "preview", "production_render", "analytics", "agent_hub_webhook"}
)


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"regular non-symlink file required: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_datetime(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        raise ValueError("UTC timestamp with timezone required")
    return result.astimezone(timezone.utc)


def audit_backup(backup_dir: Path, expected_commit: str) -> dict[str, Any]:
    """Hash a local backup without opening dumps or performing a restore."""
    if not GIT_SHA.fullmatch(expected_commit):
        raise ValueError("expected commit must be a full Git SHA")
    root = backup_dir.resolve(strict=True)
    if not root.is_dir() or backup_dir.is_symlink():
        raise ValueError("backup directory must be a regular directory")
    sums = root / "SHA256SUMS"
    if sums.is_symlink() or not sums.is_file():
        raise ValueError("SHA256SUMS missing or symbolic link")
    observed: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise ValueError("invalid checksum line")
        named = Path(match.group(2))
        target = named if named.is_absolute() else root / named
        if target.is_symlink():
            raise ValueError("backup checksum target is a symbolic link")
        resolved = target.resolve(strict=True)
        if resolved.parent != root or resolved.name not in BACKUP_FILES or resolved.name in observed:
            raise ValueError("checksum target escapes or duplicates the backup allowlist")
        actual = file_sha256(resolved)
        if actual != match.group(1):
            raise ValueError(f"backup checksum mismatch: {resolved.name}")
        observed[resolved.name] = actual
    if set(observed) != BACKUP_FILES:
        raise ValueError(f"backup files incomplete: {sorted(BACKUP_FILES - set(observed))}")
    if (root / "git-sha.txt").read_text(encoding="utf-8").strip() != expected_commit:
        raise ValueError("backup commit does not match reviewed lineage")
    if not (root / "migration-head.txt").read_text(encoding="utf-8").strip():
        raise ValueError("migration head missing")
    if "rebuild-from-postgresql" not in (root / "redis-recovery-policy.txt").read_text(encoding="utf-8"):
        raise ValueError("Redis must be rebuilt from PostgreSQL")
    return {
        "status": "PASS_LOCAL_BACKUP_INTEGRITY_ONLY",
        "commit": expected_commit,
        "migration_head": (root / "migration-head.txt").read_text(encoding="utf-8").strip(),
        "files": observed,
        "production_restore_performed": False,
    }


def measure_disposable_drill(report: Mapping[str, Any]) -> dict[str, Any]:
    """Separate total drill duration from outage-to-recovery RTO."""
    if report.get("environment") != "LOCAL_DISPOSABLE_DOCKER":
        raise ValueError("only local disposable DR may be measured here")
    start = utc_datetime(str(report["started_at_utc"]))
    end = utc_datetime(str(report["completed_at_utc"]))
    duration = int((end - start).total_seconds())
    if duration < 0:
        raise ValueError("drill completion precedes start")
    rpo = int(report["measured_rpo_seconds"])
    if rpo < 0 or rpo > 60:
        raise ValueError("local RPO policy exceeded")
    targets = report.get("recovery_targets")
    if targets is not None:
        if not isinstance(targets, list) or len(targets) != len(REQUIRED_RECOVERY_TARGETS):
            raise ValueError("nine recovery targets required")
        target_names: list[str] = []
        for target in targets:
            if not isinstance(target, dict):
                raise ValueError("invalid recovery target")
            name = target.get("target")
            before = target.get("backup_sha256")
            after = target.get("restored_sha256")
            if (
                not isinstance(name, str)
                or not isinstance(before, str)
                or not isinstance(after, str)
                or SHA256.fullmatch(before) is None
                or before != after
                or target.get("verified") is not True
            ):
                raise ValueError("recovery target hash or verification mismatch")
            target_names.append(name)
        if set(target_names) != set(REQUIRED_RECOVERY_TARGETS) or len(set(target_names)) != len(target_names):
            raise ValueError("required recovery target names mismatch")
    elif int(report.get("recovery_targets_verified", 0)) != len(REQUIRED_RECOVERY_TARGETS):
        raise ValueError("nine recovery targets required")
    cost_keys = [key for key in ("cost_vnd", "cost_total_vnd") if key in report]
    if not cost_keys:
        raise ValueError("disposable drill cost field missing")
    if any(int(report.get(key, -1)) != 0 for key in (*cost_keys, "duplicate_external_actions", "external_notifications", "production_writes")):
        raise ValueError("disposable drill crossed external or production boundary")
    outage_at = report.get("outage_started_at_utc")
    recovered_at = report.get("recovery_completed_at_utc")
    if (outage_at is None) != (recovered_at is None):
        raise ValueError("incomplete outage/recovery timestamp pair")
    if outage_at is None:
        return {
            "status": "HISTORICAL_DRILL_ELAPSED_ONLY_RTO_NOT_VERIFIED",
            "observed_local_rpo_seconds": rpo,
            "drill_elapsed_seconds": duration,
            "historical_reported_rto_seconds": int(report["measured_rto_seconds"]),
            "outage_to_recovery_rto_seconds": None,
            "production_path_tested": False,
            "production_rpo_rto_accepted": False,
        }
    outage = utc_datetime(str(outage_at))
    recovered = utc_datetime(str(recovered_at))
    rto = int((recovered - outage).total_seconds())
    if not start <= outage < recovered <= end or rto < 0 or rto > 900:
        raise ValueError("local outage/recovery bounds invalid")
    if abs(rto - int(report["measured_rto_seconds"])) > 1:
        raise ValueError("reported RTO does not match outage-to-recovery timestamps")
    if abs(duration - int(report["total_drill_elapsed_seconds"])) > 1:
        raise ValueError("reported drill duration does not match timestamps")
    if report.get("measured_rpo_basis") != "all_nine_recovery_target_hashes_and_pending_work_recovered_without_post_backup_writes":
        raise ValueError("local RPO basis missing")
    return {
        "status": "PASS_LOCAL_DISPOSABLE_RTO_MEASURED",
        "observed_local_rpo_seconds": rpo,
        "outage_to_recovery_rto_seconds": rto,
        "drill_elapsed_seconds": duration,
        "production_path_tested": False,
        "production_rpo_rto_accepted": False,
    }


def rollback_rehearsal_plan(*, candidate_commit: str, previous_commit: str, candidate_image: str, previous_image: str) -> dict[str, Any]:
    """Lock a rollback *plan*, not a deployment or actual image transition."""
    if not GIT_SHA.fullmatch(candidate_commit) or not GIT_SHA.fullmatch(previous_commit):
        raise ValueError("full commit SHAs required")
    if candidate_commit == previous_commit:
        raise ValueError("rollback candidate must differ from current commit")
    for image in (candidate_image, previous_image):
        if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image):
            raise ValueError("immutable image digest required")
    plan = {
        "candidate_commit": candidate_commit,
        "previous_commit": previous_commit,
        "candidate_image": candidate_image,
        "previous_image": previous_image,
        "steps": ["isolate_restore_target", "verify_backup", "restore_copy", "switch_disposable_image", "check_readiness", "replay_pending_work", "compare_hashes"],
        "status": "PLAN_ONLY_NOT_REHEARSED",
        "production_mutation": False,
        "owner_gates_required": ["G-04", "G-09", "G-10"],
    }
    return {**plan, "plan_sha256": canonical_sha256(plan)}


def normalize_operations_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Whitelist-safe monitoring projection; never persist raw provider/PII fields."""
    if snapshot.get("external_notifications_enabled") is not False:
        raise ValueError("external alert delivery must remain disabled")
    if snapshot.get("secret_redaction_enforced") is not True:
        raise ValueError("secret redaction must be enforced")
    provider = snapshot["provider_safety"]
    if provider.get("external_execution_enabled") is not False or provider.get("paid_execution_enabled") is not False:
        raise ValueError("provider execution must remain disabled")
    if provider.get("global_kill_switch_engaged") is not True:
        raise ValueError("provider kill switch must remain engaged")
    captured = utc_datetime(str(snapshot["captured_at_utc"]))
    alerts = []
    for raw in snapshot["alerts"]:
        if raw.get("would_notify_external") is not False or raw.get("code") not in ALERT_CODES:
            raise ValueError("unapproved alert route or code")
        if raw.get("severity") not in {"warning", "critical"} or not raw.get("runbook"):
            raise ValueError("invalid alert severity or runbook")
        if raw["runbook"] != f"docs/acceptance/v3-01/runbooks/DR_OBSERVABILITY.md#{ALERT_RUNBOOKS[raw['code']]}":
            raise ValueError("alert runbook binding mismatch")
        if raw["component"] not in {"worker", "storage", "provider-safety", "object-storage", "postgresql", "redis"}:
            raise ValueError("unapproved alert component")
        value, threshold = float(raw["value"]), float(raw["threshold"])
        if not math.isfinite(value) or not math.isfinite(threshold):
            raise ValueError("non-finite alert metric")
        alerts.append({
            "code": raw["code"],
            "component": raw["component"],
            "severity": raw["severity"],
            "value": value,
            "threshold": threshold,
            "runbook": raw["runbook"],
            "delivery": "INTERNAL_PREVIEW_ONLY",
        })
    queues = [
        {"name": item["name"], "queued": int(item["queued"]), "processing": int(item["processing"])}
        for item in snapshot["queues"]
    ]
    if {item["name"] for item in queues} != MONITOR_QUEUE_NAMES or len(queues) != len(MONITOR_QUEUE_NAMES):
        raise ValueError("complete canonical queue set required")
    for item in queues:
        if item["queued"] < 0 or item["processing"] < 0:
            raise ValueError("negative queue count")
    dependency = snapshot["dependency_health"]
    if set(dependency) != {"postgresql", "redis", "object_storage"} or not all(type(value) is bool for value in dependency.values()):
        raise ValueError("dependency health must be boolean")
    disk = float(snapshot["disk_used_percent"])
    cost = Decimal(str(snapshot["committed_cost_vnd"]))
    failed_jobs = int(snapshot["failed_jobs"])
    if not math.isfinite(disk) or not 0 <= disk <= 100 or not cost.is_finite() or cost < 0 or failed_jobs < 0 or snapshot.get("currency") != "VND":
        raise ValueError("invalid disk or VND cost metric")
    return {
        "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
        "dependency_health": dict(sorted(dependency.items())),
        "queues": queues,
        "failed_jobs": failed_jobs,
        "disk_used_percent": disk,
        "committed_cost_vnd": str(cost),
        "currency": "VND",
        "alerts": alerts,
        "kill_switch": "ENGAGED",
        "external_alert_delivery": "DISABLED",
    }


class DisposableMonitorStore:
    """SQLite-backed, hash-chained offline monitoring evidence; no delivery client."""

    def __init__(self, root: Path, *, rc_commit: str, create: bool = False) -> None:
        if not GIT_SHA.fullmatch(rc_commit):
            raise ValueError("full RC commit required")
        if not root.name.startswith("vf-dr-local-") or root.is_symlink():
            raise ValueError("monitor store requires an explicit disposable local directory")
        if create:
            root.mkdir(parents=True, exist_ok=True)
        elif not root.is_dir():
            raise ValueError("existing disposable monitor store required")
        self.root = root.resolve(strict=True)
        self.db_path = self.root / "monitor.sqlite3"
        if self.db_path.is_symlink() or (not create and not self.db_path.is_file()):
            raise ValueError("existing non-symlink monitor database required")
        self.rc_commit = rc_commit
        with self._connect(readonly=not create) as db:
            if create:
                db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS samples (seq INTEGER PRIMARY KEY, captured_at TEXT NOT NULL, payload TEXT NOT NULL, previous_sha TEXT NOT NULL, row_sha TEXT NOT NULL)")
            row = db.execute("SELECT value FROM metadata WHERE key = 'rc_commit'").fetchone()
            if row and row[0] != rc_commit:
                raise ValueError("monitor store bound to another RC")
            if create:
                db.execute("INSERT OR IGNORE INTO metadata(key, value) VALUES ('rc_commit', ?)", (rc_commit,))
            elif row is None:
                raise ValueError("monitor store has no RC binding")
        if create and os.name != "nt":
            self.db_path.chmod(0o600)

    @contextmanager
    def _connect(self, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True) if readonly else sqlite3.connect(self.db_path)
        try:
            yield db
            if not readonly:
                db.commit()
        except BaseException:
            if not readonly:
                db.rollback()
            raise
        finally:
            db.close()

    def append(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        payload = normalize_operations_snapshot(snapshot)
        text = canonical_bytes(payload).decode("utf-8")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT seq, captured_at, row_sha FROM samples ORDER BY seq DESC LIMIT 1").fetchone()
            if prior and utc_datetime(payload["captured_at_utc"]) <= utc_datetime(prior[1]):
                raise ValueError("monitor samples must have strictly increasing UTC timestamps")
            seq = 1 if prior is None else prior[0] + 1
            previous = "0" * 64 if prior is None else prior[2]
            row_sha = hashlib.sha256(f"{self.rc_commit}|{seq}|{previous}|{text}".encode("utf-8")).hexdigest()
            db.execute(
                "INSERT INTO samples(seq, captured_at, payload, previous_sha, row_sha) VALUES (?, ?, ?, ?, ?)",
                (seq, payload["captured_at_utc"], text, previous, row_sha),
            )
        return {"seq": seq, "row_sha256": row_sha, "alert_previews": len(payload["alerts"]), "external_alerts_sent": 0}

    def verify(self) -> dict[str, Any]:
        with self._connect(readonly=True) as db:
            rows = db.execute("SELECT seq, captured_at, payload, previous_sha, row_sha FROM samples ORDER BY seq").fetchall()
            binding = db.execute("SELECT value FROM metadata WHERE key = 'rc_commit'").fetchone()
        if binding is None or binding[0] != self.rc_commit:
            raise ValueError("monitor RC binding mismatch")
        previous = "0" * 64
        last_at: datetime | None = None
        for expected_seq, (seq, captured_at, text, stored_previous, stored_sha) in enumerate(rows, start=1):
            if seq != expected_seq or stored_previous != previous:
                raise ValueError("monitor sequence/chain gap")
            payload = json.loads(text)
            if canonical_bytes(payload).decode("utf-8") != text or payload["captured_at_utc"] != captured_at:
                raise ValueError("monitor row serialization mismatch")
            if payload.get("external_alert_delivery") != "DISABLED" or payload.get("kill_switch") != "ENGAGED":
                raise ValueError("monitor safety state changed")
            if any(alert.get("delivery") != "INTERNAL_PREVIEW_ONLY" for alert in payload.get("alerts", [])):
                raise ValueError("monitor alert delivery changed")
            current_at = utc_datetime(captured_at)
            if last_at is not None and current_at <= last_at:
                raise ValueError("monitor timestamps out of order")
            expected = hashlib.sha256(f"{self.rc_commit}|{seq}|{previous}|{text}".encode("utf-8")).hexdigest()
            if stored_sha != expected:
                raise ValueError("monitor chain hash mismatch")
            previous, last_at = expected, current_at
        return {"status": "PASS_LOCAL_MONITOR_CHAIN", "samples": len(rows), "head_sha256": previous, "external_alerts_sent": 0}

    def prepare_soak(self, *, minimum_hours: int = 48, maximum_gap_seconds: int = 300) -> dict[str, Any]:
        if minimum_hours < 48 or maximum_gap_seconds <= 0:
            raise ValueError("soak policy may not be weakened")
        chain = self.verify()
        with self._connect(readonly=True) as db:
            rows = db.execute("SELECT captured_at, payload FROM samples ORDER BY seq").fetchall()
        gaps = []
        critical = 0
        unhealthy = 0
        for index, (_, text) in enumerate(rows):
            payload = json.loads(text)
            critical += sum(alert["severity"] == "critical" for alert in payload["alerts"])
            unhealthy += sum(value is False for value in payload["dependency_health"].values())
            if index:
                gap = int((utc_datetime(rows[index][0]) - utc_datetime(rows[index - 1][0])).total_seconds())
                if gap > maximum_gap_seconds:
                    gaps.append(gap)
        span = int((utc_datetime(rows[-1][0]) - utc_datetime(rows[0][0])).total_seconds()) if len(rows) > 1 else 0
        return {
            "status": "PREPARATION_ONLY_NOT_PRODUCTION_SOAK",
            "rc_commit": self.rc_commit,
            "minimum_hours": minimum_hours,
            "maximum_gap_seconds": maximum_gap_seconds,
            "observed_span_seconds": span,
            "sample_count": len(rows),
            "oversized_gap_seconds": gaps,
            "critical_alert_previews": critical,
            "unhealthy_dependencies": unhealthy,
            "monitor_chain_sha256": chain["head_sha256"],
            "soak_started": False,
            "g09_deployment_approved": False,
            "human_acceptance": "NOT_PERFORMED",
        }


def lock_review_artifacts(*, rc_commit: str, artifacts: Mapping[str, Path]) -> dict[str, Any]:
    if not GIT_SHA.fullmatch(rc_commit) or set(artifacts) != set(ARTIFACT_KEYS):
        raise ValueError("RC and all seven exact G-11 artifacts are required")
    resolved = [value.resolve(strict=True) for value in artifacts.values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError("G-11 artifacts must be distinct files")
    bindings = {name: file_sha256(artifacts[name]) for name in ARTIFACT_KEYS}
    payload = {
        "schema_version": 1,
        "status": "LOCKED_FOR_REVIEW_NOT_ACCEPTED",
        "release_candidate_commit": rc_commit,
        "artifact_sha256": bindings,
        "contexts_required": ["desktop_full_watch", "mobile_full_watch", "headphones_full_listen", "phone_speaker_full_listen"],
        "external_upload": False,
        "human_review": "NOT_PERFORMED",
    }
    return {**payload, "manifest_sha256": canonical_sha256(payload)}


def verify_review_artifacts(lock: Mapping[str, Any], artifacts: Mapping[str, Path]) -> dict[str, Any]:
    current = lock_review_artifacts(rc_commit=lock["release_candidate_commit"], artifacts=artifacts)
    if current != lock:
        raise ValueError("G-11 artifacts differ from the exact locked manifest")
    return {
        "status": "PASS_EXACT_ARTIFACT_HASHES_ONLY",
        "release_candidate_commit": lock["release_candidate_commit"],
        "manifest_sha256": lock["manifest_sha256"],
        "human_review": "NOT_ATTESTED",
    }


def prepare_g11_review(lock: Mapping[str, Any], template: Mapping[str, Any]) -> dict[str, Any]:
    if canonical_sha256({key: value for key, value in lock.items() if key != "manifest_sha256"}) != lock.get("manifest_sha256"):
        raise ValueError("G-11 artifact lock hash mismatch")
    review = json.loads(json.dumps(template))
    review["review_id"] = f"g11-{lock['release_candidate_commit'][:12]}-{lock['artifact_sha256']['final_video'][:12]}"
    review["artifact_bindings"]["release_candidate_commit"] = lock["release_candidate_commit"]
    for name in ARTIFACT_KEYS:
        review["artifact_bindings"][f"{name}_sha256"] = lock["artifact_sha256"][name]
    review["notes"] = "Prepared from exact artifact lock. Human desktop/mobile watch and two full listening contexts NOT PERFORMED."
    return review


def validate_g11_review(review: Mapping[str, Any], schema: Mapping[str, Any], template: Mapping[str, Any], lock: Mapping[str, Any] | None = None) -> dict[str, Any]:
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(review))
    if errors:
        raise ValueError("G-11 schema invalid: " + "; ".join(error.message for error in errors[:3]))
    required = {item["check_id"] for item in template["checks"]}
    ids = [item["check_id"] for item in review["checks"]]
    if len(required) != 27 or len(ids) != 27 or set(ids) != required or len(set(ids)) != 27:
        raise ValueError("G-11 requires exactly the canonical 27 distinct checks")
    canonical_checks = {item["check_id"]: item for item in template["checks"]}
    for item in review["checks"]:
        expected = canonical_checks[item["check_id"]]
        if item["category"] != expected["category"] or item["requirement"] != expected["requirement"]:
            raise ValueError(f"G-11 check contract changed: {item['check_id']}")
        if item["result"] in {"FAIL", "REVIEW_REQUIRED"} and not item["notes"]:
            raise ValueError(f"G-11 non-pass result requires a note: {item['check_id']}")
    if set(review["invalidation"]) != set(template["invalidation"]):
        raise ValueError("G-11 artifact invalidation rules changed")
    if lock is not None:
        if lock["release_candidate_commit"] != review["artifact_bindings"]["release_candidate_commit"]:
            raise ValueError("G-11 RC differs from artifact lock")
        for name in ARTIFACT_KEYS:
            if lock["artifact_sha256"][name] != review["artifact_bindings"][f"{name}_sha256"]:
                raise ValueError(f"G-11 artifact changed after lock: {name}")
        if canonical_sha256({key: value for key, value in lock.items() if key != "manifest_sha256"}) != lock["manifest_sha256"]:
            raise ValueError("G-11 artifact lock hash mismatch")
    if review["decision"] == "ACCEPT":
        if lock is None:
            raise ValueError("G-11 ACCEPT requires an exact artifact lock")
        if review["status"] != "COMPLETE" or any(item["result"] != "PASS" for item in review["checks"]):
            raise ValueError("G-11 ACCEPT requires completed PASS checks")
        if not all(review["review_context"].values()):
            raise ValueError("G-11 ACCEPT requires all watch/listen contexts")
        reviewer = review["reviewer"]
        if not reviewer["name"] or not reviewer["role"] or not reviewer["started_at_utc"] or not reviewer["completed_at_utc"]:
            raise ValueError("G-11 ACCEPT requires a named, timed reviewer")
        if utc_datetime(reviewer["completed_at_utc"]) <= utc_datetime(reviewer["started_at_utc"]):
            raise ValueError("G-11 review end must follow start")
        payload = {key: value for key, value in review.items() if key != "evidence_sha256"}
        if review["evidence_sha256"] != canonical_sha256(payload):
            raise ValueError("G-11 review evidence hash mismatch")
    return {
        "status": "PASS_STRUCTURAL_ONLY",
        "checks": 27,
        "decision_recorded": review["decision"],
        "human_acceptance_attested_by_tool": False,
        "production_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline-only V3-01 DR/observability/G-11 preparation")
    command = parser.add_subparsers(dest="command", required=True)
    backup = command.add_parser("audit-backup")
    backup.add_argument("directory", type=Path)
    backup.add_argument("--rc-commit", required=True)
    drill = command.add_parser("measure-drill")
    drill.add_argument("report", type=Path)
    rollback = command.add_parser("rollback-plan")
    for flag in ("candidate-commit", "previous-commit", "candidate-image", "previous-image"):
        rollback.add_argument(f"--{flag}", required=True)
    for name in ("monitor-ingest", "monitor-verify", "soak-plan"):
        option = command.add_parser(name)
        option.add_argument("--directory", type=Path, required=True)
        option.add_argument("--rc-commit", required=True)
        if name == "monitor-ingest":
            option.add_argument("snapshot", type=Path)
    for name in ("lock-review", "verify-lock"):
        option = command.add_parser(name)
        if name == "lock-review":
            option.add_argument("--rc-commit", required=True)
        else:
            option.add_argument("lock", type=Path)
        for artifact in ARTIFACT_KEYS:
            option.add_argument(f"--{artifact.replace('_', '-')}", type=Path, required=True)
    prepared = command.add_parser("prepare-review")
    prepared.add_argument("lock", type=Path)
    validate = command.add_parser("validate-review")
    validate.add_argument("review", type=Path)
    validate.add_argument("--lock", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    template_path = root / "docs/acceptance/v3-01/templates/V3-01-G11-HUMAN-QUALITY-REVIEW.template.json"
    schema_path = root / "docs/acceptance/v3-01/schemas/human-quality-review.schema.json"
    try:
        if args.command == "audit-backup":
            result = audit_backup(args.directory, args.rc_commit)
        elif args.command == "measure-drill":
            result = measure_disposable_drill(json.loads(args.report.read_text(encoding="utf-8")))
        elif args.command == "rollback-plan":
            result = rollback_rehearsal_plan(
                candidate_commit=args.candidate_commit,
                previous_commit=args.previous_commit,
                candidate_image=args.candidate_image,
                previous_image=args.previous_image,
            )
        elif args.command in {"monitor-ingest", "monitor-verify", "soak-plan"}:
            store = DisposableMonitorStore(args.directory, rc_commit=args.rc_commit, create=args.command == "monitor-ingest")
            if args.command == "monitor-ingest":
                result = store.append(json.loads(args.snapshot.read_text(encoding="utf-8")))
            elif args.command == "monitor-verify":
                result = store.verify()
            else:
                result = store.prepare_soak()
        elif args.command == "lock-review":
            result = lock_review_artifacts(
                rc_commit=args.rc_commit,
                artifacts={name: getattr(args, name) for name in ARTIFACT_KEYS},
            )
        elif args.command == "verify-lock":
            result = verify_review_artifacts(
                json.loads(args.lock.read_text(encoding="utf-8")),
                {name: getattr(args, name) for name in ARTIFACT_KEYS},
            )
        elif args.command == "prepare-review":
            result = prepare_g11_review(
                json.loads(args.lock.read_text(encoding="utf-8")),
                json.loads(template_path.read_text(encoding="utf-8")),
            )
        elif args.command == "validate-review":
            result = validate_g11_review(
                json.loads(args.review.read_text(encoding="utf-8")),
                json.loads(schema_path.read_text(encoding="utf-8")),
                json.loads(template_path.read_text(encoding="utf-8")),
                json.loads(args.lock.read_text(encoding="utf-8")) if args.lock else None,
            )
        else:
            raise AssertionError(args.command)
    except (KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f"OFFLINE_PREPARATION_BLOCKED: {type(exc).__name__}: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
