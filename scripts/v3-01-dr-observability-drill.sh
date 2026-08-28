#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm-disposable" || "${VIDEO_FACTORY_DRILL_MODE:-}" != "disposable-ci" ]]; then
  echo "Refusing DR drill: require --confirm-disposable and VIDEO_FACTORY_DRILL_MODE=disposable-ci" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${VIDEO_FACTORY_COMPOSE_PROJECT:-npd-video-factory-v2}"
REPORT_ROOT="${VIDEO_FACTORY_DRILL_REPORT_ROOT:-$ROOT_DIR/e2e-artifacts/v3-01-drill}"
BACKUP_ROOT="$REPORT_ROOT/backups"
API_BASE="${VIDEO_FACTORY_DRILL_API_BASE:-http://localhost:8000}"
TOKEN="${VIDEO_FACTORY_DRILL_HUMAN_TOKEN:-}"
PROJECT_ID="${VIDEO_FACTORY_DRILL_PROJECT_ID:-}"
PUBLICATION_ID="${VIDEO_FACTORY_DRILL_PUBLICATION_ID:-}"
JOB_ID="${VIDEO_FACTORY_DRILL_JOB_ID:-}"
EXPECTED_ARTIFACT_SHA="${VIDEO_FACTORY_DRILL_ARTIFACT_SHA256:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DOCKER_CLI="${DOCKER_BIN:-docker}"

docker_host_path() {
  if [[ "$DOCKER_CLI" == *.exe ]] && command -v wslpath >/dev/null 2>&1; then
    wslpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}
COMPOSE_FILE="$(docker_host_path "$ROOT_DIR/docker-compose.yml")"

case "$PROJECT" in
  npd-video-factory-v3-dr-*) ;;
  *) echo "Refusing non-disposable compose project: $PROJECT" >&2; exit 2 ;;
esac
if [[ -z "$TOKEN" || -z "$PROJECT_ID" || -z "$PUBLICATION_ID" || -z "$JOB_ID" || ! "$EXPECTED_ARTIFACT_SHA" =~ ^[a-f0-9]{64}$ ]]; then
  echo "Disposable drill requires token, project, publication, job and artifact hash from the E2E fixture" >&2
  exit 2
fi

mkdir -p "$REPORT_ROOT" "$BACKUP_ROOT"
started_epoch="$(date -u +%s)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T api python - <<'PY'
from app.config import settings

assert settings.app_env.lower() != "production"
assert settings.provider_external_execution_enabled is False
assert settings.provider_paid_execution_enabled is False
assert settings.provider_global_kill_switch_engaged is True
assert settings.provider_daily_limit_vnd == 0
assert settings.publish_external_execution_enabled is False
assert settings.analytics_external_execution_enabled is False
assert settings.operations_external_notifications_enabled is False
print("drill-safety-preflight=pass")
PY

psql_digest() {
  "$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
    -Atc "$1" | sha256sum | awk '{print $1}'
}

pg_dump_digest() {
  "$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
    pg_dump -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
    --data-only --column-inserts --no-owner --no-acl "$@" \
    | grep -v -E '^\\(un)?restrict ' \
    | sha256sum | awk '{print $1}'
}

count_query="SELECT json_build_object('workspaces',(SELECT count(*) FROM workspaces),'projects',(SELECT count(*) FROM video_projects),'jobs',(SELECT count(*) FROM jobs),'assets',(SELECT count(*) FROM assets),'job_events',(SELECT count(*) FROM job_events),'publications',(SELECT count(*) FROM publications),'analytics_snapshots',(SELECT count(*) FROM analytics_metric_snapshots),'provider_operations',(SELECT count(*) FROM provider_safety_operations))::text;"
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  -Atc "$count_query" >"$REPORT_ROOT/counts-before.json"

"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" stop worker >/dev/null
payload="$REPORT_ROOT/pending-analytics-request.json"
"$PYTHON_BIN" -c 'import json,sys; open(sys.argv[2],"w",encoding="utf-8").write(json.dumps({"publication_id":sys.argv[1],"provider_mode":"fixture","trigger":"manual_refresh","fixture_profile":"normal","actor_ref":"v3-01-07-disposable-drill"}))' "$PUBLICATION_ID" "$payload"
command curl --fail --silent --show-error \
  -X POST "$API_BASE/api/v1/projects/$PROJECT_ID/analytics/syncs" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: v3-01-07-dr-recovery-0001' \
  --data-binary "@$payload" >"$REPORT_ROOT/pending-analytics-created.json"
pending_sync_id="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["sync_id"])' "$REPORT_ROOT/pending-analytics-created.json" | tr -d '\r')"

core_before="$(pg_dump_digest -t workspaces -t video_projects -t jobs -t assets)"
provider_ledger_before="$(pg_dump_digest -t provider_safety_budget_days -t provider_safety_circuits -t provider_safety_operations -t provider_safety_attempts -t provider_safety_budget_alerts)"
provider_control_before="$(psql_digest "SELECT control_key FROM provider_safety_control ORDER BY control_key;")"
provider_before="$(printf '%s%s' "$provider_ledger_before" "$provider_control_before" | sha256sum | awk '{print $1}')"
worker_before="$(psql_digest "SELECT sync_id || '|' || project_id || '|' || publication_id || '|' || request_fingerprint FROM analytics_sync_jobs WHERE sync_id = '$pending_sync_id';")"
render_before="$(pg_dump_digest -t production_render_jobs)"
publication_before="$(pg_dump_digest -t publications -t publication_events)"
webhook_before="$(pg_dump_digest -t agent_hub_webhook_deliveries)"
analytics_before="$(psql_digest "SELECT coalesce(string_agg(snapshot_id || '|' || sync_id || '|' || publication_id, E'\\n' ORDER BY snapshot_id), '') FROM analytics_metric_snapshots WHERE sync_id <> '$pending_sync_id';")"
audit_before="$(pg_dump_digest -t job_events -t production_events -t publication_events -t agent_hub_bridge_events)"

backup_dir="$(DOCKER_BIN="$DOCKER_CLI" VIDEO_FACTORY_BACKUP_ROOT="$BACKUP_ROOT" VIDEO_FACTORY_COMPOSE_PROJECT="$PROJECT" "$ROOT_DIR/scripts/v2-11-backup.sh")"
printf '%s\n' "$backup_dir" >"$REPORT_ROOT/backup-path.txt"

"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" stop api renderer studio-web minio >/dev/null
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T redis redis-cli FLUSHDB >/dev/null
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  -v ON_ERROR_STOP=1 -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;' >/dev/null
"$DOCKER_CLI" run --rm -v "${PROJECT}_minio-data:/target" alpine:3.20 \
  sh -c 'find /target -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +'

DOCKER_BIN="$DOCKER_CLI" VIDEO_FACTORY_BACKUP_ROOT="$BACKUP_ROOT" VIDEO_FACTORY_COMPOSE_PROJECT="$PROJECT" \
  "$ROOT_DIR/scripts/v2-11-restore.sh" --confirm "$backup_dir"
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d redis minio api worker renderer studio-web >/dev/null

ready=0
for _ in $(seq 1 90); do
  if command curl --fail --silent "$API_BASE/readyz" >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" != "1" ]]; then
  echo "API did not become ready after disposable restore" >&2
  exit 1
fi

"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T api python - "$JOB_ID" <<'PY'
from pathlib import Path
import sys

root = Path("/workspace/storage/jobs").resolve()
target = (root / sys.argv[1] / "final.mp4").resolve()
assert target.name == "final.mp4" and target.parent.parent == root
target.unlink(missing_ok=True)
PY
command curl --fail --silent --show-error \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/api/v1/video-jobs/$JOB_ID/artifacts/final.mp4" \
  --output "$REPORT_ROOT/restored-object.bin"
restored_artifact_sha="$(sha256sum "$REPORT_ROOT/restored-object.bin" | awk '{print $1}')"
[[ "$restored_artifact_sha" == "$EXPECTED_ARTIFACT_SHA" ]]
rm -f "$REPORT_ROOT/restored-object.bin"

analytics_terminal=0
for _ in $(seq 1 90); do
  command curl --fail --silent --show-error \
    -H "Authorization: Bearer $TOKEN" \
    "$API_BASE/api/v1/projects/$PROJECT_ID/analytics/syncs/$pending_sync_id" \
    >"$REPORT_ROOT/pending-analytics-after-restore.json"
  analytics_status="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["status"])' "$REPORT_ROOT/pending-analytics-after-restore.json" | tr -d '\r')"
  if [[ "$analytics_status" == "succeeded" ]]; then
    analytics_terminal=1
    break
  fi
  [[ "$analytics_status" != "failed" && "$analytics_status" != "cancelled" && "$analytics_status" != "not_configured" ]] || break
  sleep 1
done
[[ "$analytics_terminal" == "1" ]]

core_after="$(pg_dump_digest -t workspaces -t video_projects -t jobs -t assets)"
provider_ledger_after="$(pg_dump_digest -t provider_safety_budget_days -t provider_safety_circuits -t provider_safety_operations -t provider_safety_attempts -t provider_safety_budget_alerts)"
provider_control_after="$(psql_digest "SELECT control_key FROM provider_safety_control ORDER BY control_key;")"
provider_after="$(printf '%s%s' "$provider_ledger_after" "$provider_control_after" | sha256sum | awk '{print $1}')"
worker_after="$(psql_digest "SELECT sync_id || '|' || project_id || '|' || publication_id || '|' || request_fingerprint FROM analytics_sync_jobs WHERE sync_id = '$pending_sync_id';")"
render_after="$(pg_dump_digest -t production_render_jobs)"
publication_after="$(pg_dump_digest -t publications -t publication_events)"
webhook_after="$(pg_dump_digest -t agent_hub_webhook_deliveries)"
analytics_after="$(psql_digest "SELECT coalesce(string_agg(snapshot_id || '|' || sync_id || '|' || publication_id, E'\\n' ORDER BY snapshot_id), '') FROM analytics_metric_snapshots WHERE sync_id <> '$pending_sync_id';")"
audit_after="$(pg_dump_digest -t job_events -t production_events -t publication_events -t agent_hub_bridge_events)"

"$PYTHON_BIN" - "$REPORT_ROOT/recovery-targets.json" \
  "$core_before" "$core_after" "$EXPECTED_ARTIFACT_SHA" "$restored_artifact_sha" \
  "$provider_before" "$provider_after" "$worker_before" "$worker_after" \
  "$render_before" "$render_after" "$publication_before" "$publication_after" \
  "$webhook_before" "$webhook_after" "$analytics_before" "$analytics_after" \
  "$audit_before" "$audit_after" <<'PY'
import json
import sys

names = (
    "postgresql", "object_storage", "provider_safety_state", "worker_pending_work",
    "render_state", "publication_retry_state", "webhook_retry_state",
    "analytics_snapshot_state", "audit_evidence",
)
values = sys.argv[2:]
targets = []
for index, name in enumerate(names):
    before, after = values[index * 2:index * 2 + 2]
    assert len(before) == len(after) == 64 and before == after, (name, before, after)
    targets.append({"target": name, "backup_sha256": before, "restored_sha256": after, "verified": True})
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(targets, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  -Atc "$count_query" >"$REPORT_ROOT/counts-after.json"
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  -Atc 'SELECT version_num FROM alembic_version' >"$REPORT_ROOT/migration-head-after.txt"
cmp "$backup_dir/migration-head.txt" "$REPORT_ROOT/migration-head-after.txt"
"$PYTHON_BIN" - "$REPORT_ROOT/counts-before.json" "$REPORT_ROOT/counts-after.json" <<'PY'
import json
import sys

before = json.load(open(sys.argv[1], encoding="utf-8"))
after = json.load(open(sys.argv[2], encoding="utf-8"))
assert after["workspaces"] == before["workspaces"]
assert after["projects"] == before["projects"]
assert after["jobs"] == before["jobs"]
assert after["assets"] == before["assets"]
assert after["publications"] == before["publications"]
assert after["provider_operations"] == before["provider_operations"]
assert after["analytics_snapshots"] == before["analytics_snapshots"] + 1
assert after["job_events"] >= before["job_events"]
PY

external_actions="$("$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  -Atc "SELECT (SELECT count(*) FROM publications WHERE external_action) + (SELECT count(*) FROM agent_hub_webhook_deliveries WHERE external_call) + (SELECT count(*) FROM analytics_sync_jobs WHERE external_call);")"
[[ "$external_actions" == "0" ]]

command curl --fail --silent --show-error \
  -H "Authorization: Bearer $TOKEN" \
  -H 'X-Request-ID: v3-01-07-dr-request' \
  -H 'X-Correlation-ID: v3-01-07-dr-correlation' \
  --dump-header "$REPORT_ROOT/operations-headers.txt" \
  "$API_BASE/api/v1/operations/snapshot" >"$REPORT_ROOT/operations-snapshot.json"
tr -d '\r' <"$REPORT_ROOT/operations-headers.txt" | grep -Fqi 'x-request-id: v3-01-07-dr-request'
tr -d '\r' <"$REPORT_ROOT/operations-headers.txt" | grep -Fqi 'x-correlation-id: v3-01-07-dr-correlation'
command curl --fail --silent --show-error \
  -H "Authorization: Bearer $TOKEN" \
  -H 'X-Request-ID: v3-01-07-project-request' \
  -H 'X-Correlation-ID: v3-01-07-project-correlation' \
  "$API_BASE/api/v1/projects/$PROJECT_ID" >/dev/null
command curl --fail --silent --show-error \
  -H "Authorization: Bearer $TOKEN" \
  -H 'X-Request-ID: v3-01-07-job-request' \
  -H 'X-Correlation-ID: v3-01-07-job-correlation' \
  "$API_BASE/api/v1/video-jobs/$JOB_ID" >/dev/null
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" logs --no-color api \
  | tr -d '\r' >"$REPORT_ROOT/structured-api-log.txt"
grep -Fq '"request_id": "v3-01-07-dr-request"' "$REPORT_ROOT/structured-api-log.txt"
grep -Fq '"correlation_id": "v3-01-07-dr-correlation"' "$REPORT_ROOT/structured-api-log.txt"
grep -Fq "\"project_id\": \"$PROJECT_ID\"" "$REPORT_ROOT/structured-api-log.txt"
grep -Fq "\"job_id\": \"$JOB_ID\"" "$REPORT_ROOT/structured-api-log.txt"

completed_epoch="$(date -u +%s)"
completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$PYTHON_BIN" - "$REPORT_ROOT" "$started_at" "$completed_at" "$((completed_epoch - started_epoch))" "$pending_sync_id" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
snapshot = json.loads((root / "operations-snapshot.json").read_text(encoding="utf-8"))
recovery_targets = json.loads((root / "recovery-targets.json").read_text(encoding="utf-8"))
backup_path = Path((root / "backup-path.txt").read_text(encoding="utf-8").strip())
assert snapshot["currency"] == "VND"
assert snapshot["external_notifications_enabled"] is False
assert snapshot["provider_safety"]["external_execution_enabled"] is False
assert snapshot["provider_safety"]["paid_execution_enabled"] is False
assert snapshot["provider_safety"]["global_kill_switch_engaged"] is True
assert snapshot["secret_redaction_enforced"] is True
report = {
    "schema_version": 1,
    "environment": "LOCAL_DISPOSABLE_DOCKER",
    "source_and_restore_targets_isolated": True,
    "backup_integrity_verified": True,
    "started_at_utc": sys.argv[2],
    "completed_at_utc": sys.argv[3],
    "measured_rto_seconds": int(sys.argv[4]),
    "measured_rpo_seconds": 0,
    "postgres_restore_verified": True,
    "object_storage_restore_verified": True,
    "migration_head_before": (backup_path / "migration-head.txt").read_text(encoding="utf-8").strip(),
    "migration_head_after": (root / "migration-head-after.txt").read_text(encoding="utf-8").strip(),
    "recovery_targets": recovery_targets,
    "redis_recovery_mode": "rebuild_from_postgresql",
    "redis_queue_rebuilt": True,
    "pending_analytics_sync_recovered": sys.argv[5],
    "pending_work_resumed": True,
    "worker_restart_verified": True,
    "services_ready_after_restore": True,
    "no_duplicate_external_action": True,
    "duplicate_external_actions": 0,
    "external_notifications": 0,
    "production_writes": 0,
    "request_id_propagated": True,
    "job_id_correlated": True,
    "project_id_correlated": True,
    "structured_logs_verified": True,
    "health_and_readiness_verified": True,
    "cost_vnd": 0,
    "secret_recorded": False,
}
(root / "drill-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
for name in ("drill-report.json", "operations-snapshot.json", "counts-before.json", "counts-after.json", "recovery-targets.json"):
    digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
    assert len(digest) == 64
PY

rm -f "$payload"
echo "$REPORT_ROOT/drill-report.json"
