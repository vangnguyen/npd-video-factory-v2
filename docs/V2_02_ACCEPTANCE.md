# V2-02 durable project platform acceptance

Date: 2026-08-26  
Scope: branch `feat/v2-02-durable-project-platform`, stacked on V2-01  
Production deployment: **not performed**

## Delivered

- initial Alembic schema for workspace, project, version, canonical jobs, events,
  idempotency, assets, provider usage and costs;
- PostgreSQL repository and transient V2 Redis queue boundary;
- local filesystem plus S3-compatible object-storage interface; MinIO local/CI profile;
- project-bound jobs, asset checksum/provenance and object recovery;
- provider registry and idempotent VND-only cost ledger;
- backward-compatible V2-01 API/render pipeline and `awaiting_review` terminal gate.

## Acceptance evidence

The required evidence is generated without paid calls by `scripts/e2e-smoke.sh`:

| Gate | Required result |
|---|---|
| Alembic | upgrade, downgrade and replay PASS |
| Python | all API/worker unit and contract tests PASS |
| Renderer | tests, typecheck and bundle PASS |
| Docker | PostgreSQL, Redis, MinIO, API, worker and renderer healthy |
| Project model | workspace/project/version IDs survive API restart |
| Idempotency | replay returns the original job and does not execute twice |
| Assets | every recorded artifact has asset ID, S3 key, SHA-256 and provenance |
| Cost | three deterministic provider operations, all `0 VND`, no duplicate record |
| Recovery | local final video deletion restores checksum-identical bytes from MinIO |
| Media QC | 1080x1920 H.264/AAC, visible frames, audible narration and aligned subtitles |
| Safety | no publish API, no paid call, approval required, no AgentHub dependency |

CI uploads the secret-free JSON/QC/contact-sheet bundle as
`v2-02-durable-platform-e2e`. The draft PR remains the review gate; green CI is not merge or
production authorization.

## Verified local result

- Python compile and **53/53** API/worker tests: PASS.
- Alembic upgrade → downgrade → upgrade: PASS on SQLite; initial migration also applied to
  PostgreSQL in Docker: PASS.
- Renderer **9/9** tests: PASS; TypeScript and Remotion bundle checks: PASS.
- Compose configuration, Bash syntax, `git diff --check`, docs/path sanity and secret pattern
  scan: PASS.
- Final Docker acceptance: PASS, including API restart, PostgreSQL recovery, idempotency,
  audit, VND ledger and MinIO recovery.
- Final MP4 QC: 30.059 s, 1080x1920, 30 fps, H.264/AAC, 30 visual samples,
  dark ratio 0.0, audio mean -22.7 dB and peak -3.0 dB.

These are local pre-commit results. GitHub checks on the pushed draft PR remain an
independent required gate.

## Intentional limits and next gate

API auth/RBAC, Studio UI, real provider pricing, Trend Radar, publishing, analytics and GPU
generation are not part of V2-02. The immediate next increment after owner review is V2-03
Studio foundation, but it must keep publishing disabled and must not be started by merging or
deploying this branch implicitly.
