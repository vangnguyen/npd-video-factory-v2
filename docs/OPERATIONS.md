# Operations — V2-01

## Read-only health checks

1. `GET /healthz` returns `status=ok`.
2. `GET /readyz` returns `status=ready`.
3. `GET /api/v1/capabilities` reports publishing false, human approval true and AgentHub
   runtime dependency false.
4. `docker compose ps` shows the four V2 services only.
5. Worker logs show queue claims and terminal `job_awaiting_review`; secrets must never be
   printed.

## Failure handling

- Invalid request: correct input; do not bypass strict validation.
- Missing assets/logo in strict pilot mode: run worker preflight and fix the asset bundle.
- TTS/renderer failure: inspect stable job error code and service logs; do not expose secrets.
- Failed QC: retain the artifact bundle for diagnosis; do not publish it.
- Worker restart: in-flight IDs are recovered to the V2 queue.

## Backup and rollback

For a future approved deployment, back up the V2 Redis AOF and V2 storage directory together,
record the image/commit SHA and restore only into the V2 namespace. Never restore into or
overwrite AgentHub state. V2-01 performs no production backup, rollback or deployment.
