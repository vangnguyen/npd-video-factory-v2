# NPD Video Factory V2

NPD Video Factory V2 is an independent media execution platform. V2-01 extracts the
working deterministic video path from `vangnguyen/npd-ai-video-factory`, preserves the
useful Sprint 1 and production-TTS work, and removes every AgentHub runtime dependency.

## V2-01 status

Implemented:

- FastAPI video-job API with idempotent enqueueing;
- V2-owned Redis queue/state and restart recovery;
- deterministic multi-niche content profiles with a generic vertical template;
- backward-compatible real-estate template adapter;
- local media preflight and deterministic asset resolution;
- scene-aligned Vietnamese TTS, measured subtitle timing and resumability;
- Remotion rendering plus FFmpeg/FFprobe black-frame, audio and metadata QC;
- terminal `awaiting_review` state with no publishing implementation;
- isolated Docker Compose, unit/contract tests and deterministic Docker E2E.

Not implemented in V2-01: PostgreSQL project storage, object storage, Studio UI,
Trend Radar, publishing providers, analytics or learning loops. Those are delivered by
later PRs in the master specification.

## Safety boundary

- No AgentHub package, database, Redis namespace or process dependency.
- No production route, service or deployment is changed by this PR.
- `PUBLISH_ENABLED=false` and `HUMAN_APPROVAL_REQUIRED=true` are enforced at startup.
- External TTS smoke is manual, owner-gated and never runs on normal CI.
- No secrets or production media are included.

## Local deterministic run

Requirements: Docker Engine with Compose and Python 3.12+.

```bash
cp .env.example .env
bash scripts/e2e-smoke.sh
```

The E2E creates copyright-safe fixtures, boots the independent stack, renders one MP4,
verifies narration/subtitle timing and inspects decoded video/audio. Artifacts are written
under `e2e-artifacts/` and are git-ignored.

Useful endpoints after `docker compose up -d --build`:

- `GET http://localhost:8000/healthz`
- `GET http://localhost:8000/readyz`
- `GET http://localhost:8000/api/v1/capabilities`
- `POST http://localhost:8000/api/v1/video-jobs`
- `GET http://localhost:8000/api/v1/video-jobs/{job_id}`

See [Architecture](docs/ARCHITECTURE.md), [Migration audit](docs/MIGRATION_AUDIT.md),
[API](docs/API.md), [Testing](docs/TESTING.md), [Security](docs/SECURITY.md) and the
[V2 master specification](docs/CODEX_MASTER_SPEC_VIDEO_FACTORY_V2.md).
