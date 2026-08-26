# Deployment — V2-03

V2-03 is a development/CI platform increment and is not approved for production deployment.

## Dev/CI

```bash
cp .env.example .env
docker compose up -d --build
curl --fail http://localhost:8000/readyz
curl --fail http://localhost:8000/api/v1/capabilities
curl --fail http://localhost:3000/
```

Services are `postgres`, `redis`, `minio`, one-shot `migrate`, `api`, `studio-web`, `worker` and
`renderer`. API, Studio and renderer bind only to `127.0.0.1` by default. No AgentHub, n8n,
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

V2-03 additionally requires `TREND_FIXTURE_ENABLED=false` for production and authorized provider
adapters before live trend collection. This branch changes no existing NPD production service and
must not be deployed as-is.
