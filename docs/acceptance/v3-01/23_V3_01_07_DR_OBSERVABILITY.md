# V3-01-07 — DR and observability remediation

## Decision and scope

V3-01-07 adds a fail-closed local/CI recovery and operations plane. It does not deploy Video
Factory, expose ingress, activate credentials, call a provider, publish, send an external alert or
start the 48-hour soak. The repository verdict remains `NO-GO`.

The checkpoint covers:

- guarded PostgreSQL, MinIO and Redis-AOF backup with checksums and migration metadata;
- destructive failure simulation only inside the disposable E2E Compose project;
- PostgreSQL and object-storage restore, followed by Redis queue reconstruction from canonical
  PostgreSQL state;
- restart and completion of one deliberately pending analytics job;
- integrity fingerprints for core PostgreSQL data, object storage, provider safety, worker pending
  work, render, publication retry, webhook retry, analytics snapshots and audit evidence;
- authenticated read-only operations snapshot for dependency, queue, failed-job, disk, provider,
  VND cost and retention state;
- request and correlation IDs plus structured secret-redacted request logs;
- internal alert previews for backlog, provider degradation, storage failure, disk pressure, failed
  jobs, VND cost thresholds and unhealthy services;
- external alert delivery hard-disabled.

## Safety boundaries

- the drill requires both `--confirm-disposable` and
  `VIDEO_FACTORY_DRILL_MODE=disposable-ci`;
- only disposable Compose project names prefixed `npd-video-factory-v3-dr-` are accepted;
- runtime preflight rejects production, external or paid execution, a released kill switch,
  non-zero provider budget, live publish/analytics or external operations notifications;
- Redis is never restored automatically; it is rebuilt from PostgreSQL after service restart;
- no production restore, deployment, public route, provider credential or customer data is used;
- Windows CI backups inherit host ACLs and contain synthetic data only; Linux runtime backups
  retain POSIX-restricted permissions.

## Acceptance axes

| Axis | V3-01-07 status | Meaning |
|---|---|---|
| Implemented | PASS | contracts, guarded scripts, read-only API and tests exist |
| Local disposable drill | PASS | actual backup/failure/restore/restart/recovery and 9/9 hash comparison; RPO 0s/RTO 33s |
| Production path | BLOCKED | G-04, G-09 and G-10 are not approved |
| 48-hour soak | BLOCKED | no locked RC deployment and no non-backdated soak |
| Human quality | N/A | no media-quality claim is made by this checkpoint |

The checked-in secret-free evidence is `EV-V3-DR-OBS-001`, bound to code commit
`527fd1f482e4afa80105cb6ebab92545c10a79fc`. PR #19 exact head
`4b17fc1352ee4582db9b69f795531ef9b6a4feb4` passed all five CI jobs and merged under
`V3-01-APP-008` as exact `main` `b132e839904b377ec7e82e9135920f895ddf704e`.
Neither local PASS may be promoted to production evidence.

## Remaining gates and gaps

- `V3-01-GAP-007` remains `OPEN`: no production-like staging or production route exists.
- `V3-01-GAP-008` may move to `IN_PROGRESS`: local disposable restore is useful evidence, but no
  owner-approved production-like DR/rollback drill or accepted RPO/RTO exists.
- `V3-01-GAP-009` may move to `IN_PROGRESS`: local signals and alert previews exist, but there is no
  monitoring backend, accepted alert destination or 48-hour soak.
- `V3-01-GAP-010` remains `IN_PROGRESS`: no provider is activated.
- G-08 was consumed by the repository merge only. G-04, G-09, G-10 and G-12 remain pending.

## Exact next gate

The repository merge is complete. The next checkpoint is V3-01-08 consolidation/RC review. Any
production-like staging/deployment, DR acceptance or final verdict remains separately bound to
G-04/G-09, G-10 and G-12 and must not imply a real-provider or publishing gate.
