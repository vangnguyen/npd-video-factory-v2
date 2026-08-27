# NPD Video Factory V2

NPD Video Factory V2 is an independent media execution platform. V2-05 keeps the durable
video, Trend/Idea and Auto Edit platform, then adds structured Vision evidence and
non-destructive Smart Reframe plans for uploaded footage.

## V2-05 status

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
- resumable chunk uploads with safe names, SHA-256, duplicate detection, magic-byte validation,
  FFprobe metadata and S3-compatible source-asset storage;
- provider-independent Vietnamese transcript evidence with segments and word timestamps;
- combined scene evidence, non-destructive silence decisions that never cut through words,
  and explainable Top 3/Top 5 highlight recommendations;
- PostgreSQL recovery for upload, transcript, scene, silence and highlight state.
- a provider-neutral Vision contract with a deterministic local/CI fixture and an explicit
  `not_configured` live-provider adapter;
- structured frame, OCR, object, composition and quality evidence with provider/model/confidence;
- scene insights, subject tracks, best-frame ranking and thumbnail candidates;
- smooth crop keyframes for `9:16`, `16:9`, `1:1` and `4:5`, subtitle-safe configuration,
  manual overrides and low-confidence center-crop fallback;
- PostgreSQL recovery for Vision evidence and reframe plans, with an idempotent zero-VND fixture
  provider operation.

Not implemented in V2-05: real Vision credentials/accuracy acceptance, reframe rendering,
transcript/crop editing UI, editable timeline, API authentication/RBAC, publishing,
analytics/learning loops, GPU generation or a production rollout. Those remain later,
separately gated increments.

## Safety boundary

- No AgentHub package, database, Redis namespace or process dependency.
- No production route, service or deployment is changed by this branch.
- `PUBLISH_ENABLED=false` and `HUMAN_APPROVAL_REQUIRED=true` are enforced at startup.
- Normal CI uses deterministic providers and makes no paid call.
- Auto Edit outputs decisions only; uploaded source bytes are immutable.
- Vision fixture output is explicitly mock evidence; live Vision remains `not_configured`.
- Smart Reframe stores decision keyframes only and never changes source media.
- Trend references are metadata-only; creator media is never downloaded or copied.
- No secrets or production media are included.

## Local deterministic acceptance

Requirements: Docker Engine with Compose and Python 3.12+.

```bash
cp .env.example .env
bash scripts/e2e-smoke.sh
```

The E2E creates copyright-safe media and trend fixtures, migrates PostgreSQL, renders one MP4,
verifies Trend -> Ideas -> Queue -> Draft Project, uploads the MP4 through the resumable API,
persists transcript/scene/silence/highlight and Vision/reframe evidence, restarts the API,
restores the final artifact from MinIO and validates decoded video/audio quality. Its temporary
stack and volumes are removed on exit.

Useful endpoints after `docker compose up -d --build`:

- `GET http://localhost:8000/readyz`
- `GET http://localhost:8000/api/v1/capabilities`
- `POST http://localhost:8000/api/v1/video-jobs`
- `GET http://localhost:8000/api/v1/video-jobs/{job_id}`
- `GET http://localhost:8000/api/v1/workspaces`
- `GET http://localhost:8000/api/v1/providers`
- `GET http://localhost:8000/api/v1/trend-sources`
- `GET http://localhost:8000/api/v1/workspaces/{workspace_id}/trend-clusters`
- `POST http://localhost:8000/api/v1/uploads/init`
- `POST http://localhost:8000/api/v1/projects/{project_id}/analyze`
- `POST http://localhost:8000/api/v1/projects/{project_id}/analyses/{analysis_id}/vision`
- `GET http://localhost:3000` (local Trend Radar Studio)

See [Architecture](docs/ARCHITECTURE.md), [API](docs/API.md),
[Deployment](docs/DEPLOYMENT.md), [Testing](docs/TESTING.md),
[Security](docs/SECURITY.md), [Trend Radar](docs/TREND_RADAR.md),
[Idea Intelligence](docs/IDEA_INTELLIGENCE.md),
[Auto Edit Analysis](docs/AUTO_EDIT_ANALYSIS.md),
[Vision and Smart Reframe](docs/VISION_SMART_REFRAME.md),
[V2-05 acceptance](docs/V2_05_ACCEPTANCE.md), [V2-04 acceptance](docs/V2_04_ACCEPTANCE.md) and the
[V2 master specification](docs/CODEX_MASTER_SPEC_VIDEO_FACTORY_V2.md).
