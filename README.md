# NPD Video Factory V2

NPD Video Factory V2 is an independent media execution platform. V2-03 keeps the
deterministic video path and V2-02 durable platform, then adds a research-only Trend Radar,
explainable opportunity scoring, Idea Engine, Content Opportunity Queue and responsive Studio.

## V2-03 status

Implemented and locally acceptance-tested:

- workspace, project and immutable project-version records;
- canonical PostgreSQL job state, idempotency receipts and transition audit;
- V2-owned Redis used only for transient queue delivery;
- MinIO for local/CI and an S3-compatible production provider contract;
- source/generated/render/metadata asset records with checksum, object key and provenance;
- provider registry plus idempotent usage and VND cost records;
- restart recovery and object-store artifact recovery;
- the V2-01 9:16 deterministic render, scene-aligned Vietnamese narration and FFmpeg QC;
- terminal `awaiting_review` state with no publishing implementation.
- provider-agnostic trend sources with deterministic legal fixtures and explicit
  `not_configured` live-provider contracts;
- normalized trend evidence, deterministic clusters, seven-state lifecycle and explainable
  estimated scores;
- six distinct idea strategies, durable evidence/score records and an idempotent ranked queue;
- local responsive Studio with eight radar views, filters, detail, ideas and draft-project flow.

Not implemented in V2-03: API authentication/RBAC, live trend credentials, publishing,
analytics/learning loops, GPU generation or a production rollout. Those remain later,
separately gated increments.

## Safety boundary

- No AgentHub package, database, Redis namespace or process dependency.
- No production route, service or deployment is changed by this branch.
- `PUBLISH_ENABLED=false` and `HUMAN_APPROVAL_REQUIRED=true` are enforced at startup.
- Normal CI uses deterministic providers and makes no paid call.
- Trend references are metadata-only; creator media is never downloaded or copied.
- No secrets or production media are included.

## Local deterministic acceptance

Requirements: Docker Engine with Compose and Python 3.12+.

```bash
cp .env.example .env
bash scripts/e2e-smoke.sh
```

The E2E creates copyright-safe media and trend fixtures, migrates PostgreSQL, renders one MP4,
verifies durable project/cost/audit plus Trend -> Ideas -> Queue -> Draft Project, restarts the
API, restores the final artifact from MinIO and validates decoded video/audio quality. Its
temporary stack and volumes are removed on exit.

Useful endpoints after `docker compose up -d --build`:

- `GET http://localhost:8000/readyz`
- `GET http://localhost:8000/api/v1/capabilities`
- `POST http://localhost:8000/api/v1/video-jobs`
- `GET http://localhost:8000/api/v1/video-jobs/{job_id}`
- `GET http://localhost:8000/api/v1/workspaces`
- `GET http://localhost:8000/api/v1/providers`
- `GET http://localhost:8000/api/v1/trend-sources`
- `GET http://localhost:8000/api/v1/workspaces/{workspace_id}/trend-clusters`
- `GET http://localhost:3000` (local Trend Radar Studio)

See [Architecture](docs/ARCHITECTURE.md), [API](docs/API.md),
[Deployment](docs/DEPLOYMENT.md), [Testing](docs/TESTING.md),
[Security](docs/SECURITY.md), [Trend Radar](docs/TREND_RADAR.md),
[Idea Intelligence](docs/IDEA_INTELLIGENCE.md),
[V2-03 acceptance](docs/V2_03_ACCEPTANCE.md), [V2-02 acceptance](docs/V2_02_ACCEPTANCE.md) and the
[V2 master specification](docs/CODEX_MASTER_SPEC_VIDEO_FACTORY_V2.md).
