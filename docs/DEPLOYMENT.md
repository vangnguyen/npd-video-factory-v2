# Deployment — V2-07

V2-07 is a development/CI platform increment and is not approved for production deployment.

## Dev/CI

```bash
cp .env.example .env
docker compose up -d --build
curl --fail http://localhost:8000/readyz
curl --fail http://localhost:8000/api/v1/capabilities
curl --fail http://localhost:3000/
```

Default services are `postgres`, `redis`, `minio`, one-shot `migrate`, `api`, `studio-web`,
`worker` and `renderer`. The optional `comfyui-bridge` is behind the `gpu` profile and remains
disabled/not configured. API, Studio and renderer bind only to `127.0.0.1` by default. No AgentHub, n8n,
Caddy, CRM or shared Redis service is created. Stop with
`docker compose down`; add `-v` only for an explicitly disposable development stack.

Local/CI MinIO uses a pinned official image tag. Production must provide a separately owned
S3-compatible endpoint and credentials through a secret manager, not `.env` in Git.

## Production gate

Before any production proposal, a separate owner-approved PR/task must add and verify:

1. authentication, RBAC and tenant/workspace authorization;
2. managed or backed-up PostgreSQL and S3-compatible storage;
3. unique network, host ports and object bucket with retention/lifecycle policy;
4. backup/restore drill for PostgreSQL plus object-store consistency;
5. guarded deployment, rollback image, TLS route and public smoke;
6. resource limits, monitoring and incident runbook;
7. Vietnamese human voice acceptance for any production TTS;
8. explicit owner gate for every paid provider or publishing capability.
9. upload malware scanning/quarantine, API rate limits and workspace authorization;
10. owner-approved live Vision adapter, credential isolation, paid-call budget and real-media
    OCR/tracking/reframe accuracy acceptance.
11. owner-approved stock and image/video-generation adapters with rights and VND pricing acceptance;
12. reviewed/pinned ComfyUI graph, nodes and model checksums plus authenticated bridge networking.
13. Auto Edit Studio authentication, project/workspace authorization and auditable human identity;
14. timeline/preview retention, quota and cleanup policies plus a PostgreSQL/object-store restore drill;
15. resource ceilings and observability for FFmpeg preview workers.

V2-07 additionally requires `TREND_FIXTURE_ENABLED=false`, `AUTO_EDIT_FIXTURE_ENABLED=false`,
`VISION_FIXTURE_ENABLED=false`, `VISION_PROVIDER=contract`,
`MEDIA_FIXTURE_ENABLED=false`, media providers set to `contract`, and external/paid/ComfyUI
execution disabled until their separate owner gates;
`TRANSCRIPTION_PROVIDER=contract` (until a live adapter is approved) and
`AUTO_EDIT_SIGNAL_PROVIDER=ffmpeg` for production. This branch changes no existing NPD production
service and must not be deployed as-is.
