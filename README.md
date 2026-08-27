# NPD Video Factory V2

NPD Video Factory V2 is an independent media execution platform. V2-09 keeps the durable
video, Trend/Idea, Auto Edit, Vision and Media Intelligence platform, editable timeline,
human approval, production-profile rendering and full media QC, then adds fail-closed publishing
validation, versioned platform contracts and durable dry-run receipts.

## V2-09 status

Implemented and locally acceptance-tested:

- workspace, project and immutable project-version records;
- canonical PostgreSQL job state, idempotency receipts and transition audit;
- V2-owned Redis used only for transient queue delivery;
- MinIO for local/CI and an S3-compatible production provider contract;
- source/generated/render/metadata asset records with checksum, object key and provenance;
- provider registry plus idempotent usage and VND cost records;
- restart recovery and object-store artifact recovery;
- the V2-01 9:16 deterministic render, scene-aligned Vietnamese narration and FFmpeg QC;
- terminal `awaiting_review` video-job state and an independently gated publishing layer.
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
- deterministic MediaPlanner and BrollPlanner outputs for reusable, stock and generated media;
- provider-neutral stock/image/video contracts with explicit `not_configured` live state;
- durable resolution jobs, Redis delivery, worker recovery and object-store registration;
- per-asset license, creator, source and generation provenance with fail-closed rights checks;
- an optional, disabled-by-default ComfyUI bridge with eight versioned allowlisted workflows.
- a strict JSON Schema/Pydantic timeline contract with typed tracks, clips, crop, transform,
  audio-level, transition/effect and evidence fields;
- immutable PostgreSQL timeline versions, optimistic concurrency, restart recovery and preview
  invalidation after every accepted edit;
- responsive Auto Edit Studio media/transcript/scene/B-roll browsers and a genuinely editable
  multi-track timeline;
- drag/drop, trim, split, move, delete, reorder, disable, duplicate, zoom, proxy waveform,
  playhead, snapping, undo/redo, track lock and mute interactions;
- worker-rendered, cancellable 540x960 H.264 video-only previews with persisted progress,
  object-store checksums and version-bound playback.
- immutable subtitle and audio-mix versions bound to the exact timeline version;
- a responsive Subtitle Editor and Audio Mixer with safe-area/style controls, Vietnamese
  per-cue narration, optional licensed music, ducking, fades and a 48 kHz limited mix;
- review renders that stop at `awaiting_review`, plus recorded owner decisions bound to the
  review, timeline, subtitle and audio versions;
- final 1080x1920, 1920x1080 and 1080x1080 H.264/AAC renders that require the current approved
  review package and remain non-publishing artifacts;
- automatic invalidation of approvals and render artifacts after any accepted timeline,
  subtitle or audio change;
- full QC for duration, resolution, frame rate, codecs, decoded frames, black/freeze ratios,
  audio silence/clipping, A/V sync, subtitle bounds and missing timeline assets;
- PostgreSQL recovery for packages, approvals, render jobs and audit history, with transient
  Redis delivery and deterministic worker recovery.
- versioned YouTube, TikTok, Instagram Reels and Facebook capability profiles;
- official-API provider contracts plus a deterministic no-network dry-run provider;
- exact final-render, approval, rights, QC, platform and metadata validation;
- durable publication/audit records, hashed idempotency keys and exact replay after restart;
- a responsive Publishing Panel that can create only mock receipts and exposes no live button;
- all live publishing gates false and official adapters contract-only.

Not implemented in V2-09: real Vision/stock/generation credentials or accuracy acceptance,
production ComfyUI/GPU execution, a human-accepted production Vietnamese voice/provider,
API authentication/RBAC, live publishing credentials/adapters, analytics/learning loops or a
production rollout. Those remain later, separately gated increments.

## Safety boundary

- No AgentHub package, database, Redis namespace or process dependency.
- No production route, service or deployment is changed by this branch.
- `PUBLISH_ENABLED=false`, `PUBLISH_EXTERNAL_EXECUTION_ENABLED=false`,
  `PUBLISH_OWNER_GATE_ENABLED=false` and `HUMAN_APPROVAL_REQUIRED=true` are enforced at startup.
- Normal CI uses deterministic providers and makes no paid call.
- Auto Edit outputs decisions only; uploaded source bytes are immutable.
- Vision fixture output is explicitly mock evidence; live Vision remains `not_configured`.
- Smart Reframe stores decision keyframes only and never changes source media.
- Media fixture artifacts are synthetic, not production-eligible and never imply a real-provider test.
- Unknown rights and unapproved costs block resolution/publishing; external and paid execution are off.
- ComfyUI accepts only versioned workflow IDs; the optional `gpu` profile is disabled by default.
- Timeline writes require an expected version, source bytes stay immutable and old previews become
  stale instead of being silently reused.
- Proxy preview is video-only, performs no external call, cannot publish and is never a final
  output claim.
- Review/final renders remain non-publishing artifacts. V2-09 can validate the exact current
  owner-approved tuple and issue a mock dry-run receipt, but cannot contact a platform.
- Publishing idempotency keys are hashed; raw OAuth tokens are rejected as configuration and never
  enter the API, PostgreSQL, audit history or logs.
- eSpeak is an offline dev/CI voice and is not a production voice acceptance. External audio is
  disabled by default and requires a separate owner gate.
- Music is accepted only from a project asset with explicit usable rights; unclear rights fail closed.
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
persists transcript/scene/silence/highlight, Vision/reframe and media-plan/provenance evidence,
resolves four fixture strategies asynchronously, builds and edits a versioned timeline, rejects a
stale write, renders and invalidates a 540p proxy, restores a safe timeline version, edits dynamic
subtitles, proves that unapproved final rendering is blocked, renders an A/V review, records owner
approval, renders the approved 1080x1920 final profile, performs full QC, restarts the API,
restores the final artifact from MinIO, creates and exactly replays one platform dry-run receipt,
proves that live mode is blocked with no external action, and validates decoded video/audio
quality. Its temporary stack and volumes are removed on exit.

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
- `POST http://localhost:8000/api/v1/projects/{project_id}/media-plans`
- `GET http://localhost:8000/api/v1/projects/{project_id}/media-assets`
- `POST|GET|PUT http://localhost:8000/api/v1/projects/{project_id}/timeline`
- `POST http://localhost:8000/api/v1/projects/{project_id}/preview`
- `POST|GET http://localhost:8000/api/v1/projects/{project_id}/production-package`
- `PUT http://localhost:8000/api/v1/projects/{project_id}/subtitles`
- `PUT http://localhost:8000/api/v1/projects/{project_id}/audio-mix`
- `POST http://localhost:8000/api/v1/projects/{project_id}/review-render`
- `POST http://localhost:8000/api/v1/projects/{project_id}/approvals`
- `POST http://localhost:8000/api/v1/projects/{project_id}/final-render`
- `POST http://localhost:8000/api/v1/projects/{project_id}/publish` (dry run only)
- `GET http://localhost:8000/api/v1/projects/{project_id}/publications`
- `GET http://localhost:8000/api/v1/publishing-platforms`
- `GET http://localhost:3000` (local Trend Radar)
- `GET http://localhost:3000/studio.html` (local Auto Edit Studio)

See [Architecture](docs/ARCHITECTURE.md), [API](docs/API.md),
[Deployment](docs/DEPLOYMENT.md), [Testing](docs/TESTING.md),
[Security](docs/SECURITY.md), [Trend Radar](docs/TREND_RADAR.md),
[Idea Intelligence](docs/IDEA_INTELLIGENCE.md),
[Auto Edit Analysis](docs/AUTO_EDIT_ANALYSIS.md),
[Vision and Smart Reframe](docs/VISION_SMART_REFRAME.md),
[Media Intelligence](docs/MEDIA_INTELLIGENCE.md), [media provider contracts](docs/MEDIA_PROVIDERS.md), [ComfyUI setup](docs/COMFYUI_SETUP.md),
[Auto Edit Studio](docs/AUTO_EDIT_STUDIO.md),
[Audio, Subtitle, Render and QC](docs/AUDIO_SUBTITLE_RENDER_QC.md),
[Publishing](docs/PUBLISHING.md), [V2-09 acceptance](docs/V2_09_ACCEPTANCE.md),
[V2-08 acceptance](docs/V2_08_ACCEPTANCE.md), [V2-07 acceptance](docs/V2_07_ACCEPTANCE.md),
[V2-06 acceptance](docs/V2_06_ACCEPTANCE.md) and the
[V2 master specification](docs/CODEX_MASTER_SPEC_VIDEO_FACTORY_V2.md).
