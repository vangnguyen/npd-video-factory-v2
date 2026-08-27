# V2-11 Production Deployment Runbook

## Gate

This PR supplies a deployment bundle; it does not authorize a deployment. Production requires a
separate owner approval, a clean tagged/approved commit, green required CI, a prepared rollback
image and a current backup. Caddy changes are out of scope.

## Pre-deploy

1. Use an isolated checkout at the exact approved SHA.
2. Provision `.env` outside Git with production S3 credentials and every deterministic fixture false.
3. Provision the external Agent Hub key file with mode `0400`/`0440`.
4. Set `VIDEO_FACTORY_AGENT_HUB_KEYS_FILE` to its absolute host path.
5. Keep bridge/webhook disabled unless this exact integration is separately approved.
6. Run `./scripts/v2-11-preflight.sh`.
7. Record current containers/images/restart counts and available disk space.

The production override creates only the existing V2 services on the dedicated
`npd-video-factory-v2` network. It contains no Agent Hub, Caddy, n8n or shared Redis service.

## Guarded deployment

```bash
./scripts/v2-11-deploy.sh
```

The sequence is preflight -> backup -> build -> migration -> targeted V2 service update -> smoke.
It does not reload Caddy and does not expose a new route. Preserve the backup path printed by the
script and label the prior API/worker images for rollback before traffic changes.

## Acceptance

- `/readyz` is 200 and OpenAPI is `0.12.0`;
- capabilities truthfully report bridge implemented/enabled state;
- DB/Redis/MinIO/worker/renderer/Studio are healthy with no unexplained restart;
- signed bridge contract request passes; unsigned/replayed/tampered requests fail;
- one draft-only acceptance request creates no job and no publication;
- one signed webhook receipt verifies and persists across API/worker restart;
- Agent Hub outage leaves Video Factory ready and the delivery retry durable;
- no secrets appear in API, logs, database audit or artifacts;
- publishing and external/paid execution remain disabled.

## Rollback

1. Stop traffic to V2 only; do not touch Caddy/n8n/Agent Hub services.
2. Restore the prior V2 API/worker/renderer/Studio images.
3. Downgrade schema only if the approved rollback plan requires it; migration `0010_v2_11` is
   additive and the prior release can normally ignore the new tables.
4. Restore canonical data only when validation proves it is needed. Use the explicit restore runbook.
5. Run the prior release smoke and retain all failure/rollback evidence.

Never auto-restore Redis, delete a backup, rotate an HMAC key or enable a publishing capability as
part of rollback.
