# Operations — V2-02

## Read-only health checks

1. `GET /healthz` returns `status=ok`.
2. `GET /readyz` proves PostgreSQL, Redis, object storage and scratch availability.
3. Capabilities report publishing false, approval true, PostgreSQL canonical state,
   transient Redis queue, configured object store and VND currency.
4. `docker compose ps` shows only the seven V2 services.
5. Job events progress and object/cost counts remain consistent; logs contain no secrets.

## Failure handling

- Database unavailable: stop intake; do not fall back to Redis as canonical state.
- Redis unavailable: keep durable records; restore queue service and explicitly reconcile
  non-terminal jobs before requeueing.
- Object storage unavailable/checksum mismatch: do not serve the artifact or publish it.
- TTS/renderer/QC failure: use the stable error code and audit trail; retain evidence.
- Worker restart: claimed IDs are requeued and valid existing artifacts are reused.
- Unpriced provider operation: keep it explicit and block broader paid execution.

## Backup and restore contract

PostgreSQL and object storage form one logical recovery set. Record commit/image, database
dump time, bucket inventory/version marker and checksums. Restore into an isolated V2 target,
verify foreign keys and sampled artifacts, then reconcile queued non-terminal jobs. Redis AOF
is useful operational evidence but is not the authoritative backup.

Never restore into AgentHub state or overwrite any existing NPD service. V2-02 performs no
production backup, rollback or deployment; those remain owner-gated work.
