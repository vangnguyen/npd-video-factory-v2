# Deployment — V2-01

V2-01 is a development/CI extraction and is not approved for production deployment.

## Dev/CI

```bash
cp .env.example .env
docker compose up -d --build
curl --fail http://localhost:8000/readyz
curl --fail http://localhost:8000/api/v1/capabilities
```

Expected services: `redis`, `api`, `worker`, `renderer`. No AgentHub, n8n, Caddy, CRM or
shared Redis service is created. Stop with `docker compose down`; add `-v` only when the
explicit intent is to remove this V2 development Redis volume.

## Production gate

Production requires a separate owner-approved PR/task, backup/rollback plan, unique host
ports, unique storage paths, V2-owned PostgreSQL/object storage/Redis, isolated network and
guarded reverse-proxy change. Extraction does not modify any existing NPD production service.

CPU services must remain able to start without future GPU/ComfyUI services. GPU provisioning,
real TTS, human Vietnamese voice acceptance and publishing are separate manual gates.
