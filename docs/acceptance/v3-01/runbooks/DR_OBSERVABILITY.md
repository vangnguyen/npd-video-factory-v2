# DR and observability runbook

## Stop conditions

Stop immediately if the target is not a disposable local/CI stack, the Git commit is not the
reviewed candidate, any external/paid execution flag is enabled, the provider kill switch is
released, budget is non-zero, or production writes/notifications are enabled. Never run the
destructive drill against a production Compose project or shared volume.

## Local disposable drill

The normal entry point is `scripts/e2e-smoke.sh`. It creates synthetic data, invokes
`scripts/v3-01-dr-observability-drill.sh` with the required disposable guards, and destroys the
isolated stack on completion. The drill sequence is:

1. verify fail-closed runtime settings;
2. stop the worker and enqueue one deterministic pending analytics job;
3. capture target-specific source fingerprints;
4. create PostgreSQL, MinIO and Redis-AOF backups plus checksums and migration head;
5. stop application services, flush Redis, drop the disposable PostgreSQL schema and wipe the
   disposable MinIO volume;
6. restore PostgreSQL and MinIO; retain Redis AOF only as evidence;
7. restart services, reconstruct Redis queues from PostgreSQL and resume the pending job;
8. verify one controlled analytics delta and zero duplicate external action;
9. compare all recovery fingerprints, migration head and an actual restored artifact checksum;
10. capture the authenticated operations snapshot and secret-free drill report.

Raw dumps, session tokens and binary artifacts are never checked into Git. Only redacted summaries,
hashes, durations and validation results may enter the V3 evidence bundle.

## Alert-preview response

### queue-backlog

Inspect queue and processing counts, correlate project/job IDs, pause producers if growth is
unbounded, and do not enable additional workers until poison work is excluded.

### provider-degradation

Keep external execution disabled. Inspect durable operation/circuit state and stale leases; do not
retry a paid provider without a separate owner gate.

### storage-unavailable

Stop new media work, preserve PostgreSQL state, verify object-store health and capacity, and restore
only into an owner-approved isolated target.

### disk-pressure

Stop ingestion before the critical threshold. Preserve evidence and backups; follow retention
policy rather than deleting data ad hoc.

### failed-jobs

Group by correlation/project/job ID and failure code. Quarantine poison inputs and use deterministic
retry boundaries; never trigger an external action during diagnosis.

### cost-threshold

Keep the kill switch engaged and budget at 0 VND in V3-01. Any later cost incident requires owner
review of the durable VND ledger before execution resumes.

### service-unhealthy

Identify the failed dependency, keep ingress closed, and verify readiness only after PostgreSQL,
Redis and object storage are healthy. Avoid blind restarts that can hide the original evidence.

## Production-like DR gate

Production-like DR requires separate G-04, G-09 and G-10 approvals, an immutable RC image, accepted
RPO/RTO, isolated source/restore targets, backup retention and an explicit rollback candidate. The
local drill is not authority to deploy or restore production.

## Soak gate

The 48-hour clock may start only after a locked RC is deployed under G-09. It cannot be backdated.
Green CI, an idle process or this local drill is not a soak result.
