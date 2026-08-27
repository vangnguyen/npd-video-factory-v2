# API — V2-10

Base path: `/api/v1`. Request models forbid unknown fields. This local/CI increment has no
authentication layer and must not be exposed to an untrusted network.

## Health and capability

- `GET /healthz`: process liveness.
- `GET /readyz`: PostgreSQL, Redis, object storage and writable scratch readiness.
- `GET /api/v1/capabilities`: durable-store, queue, object-store, VND and safety state.

## Workspaces and projects

- `POST|GET /api/v1/workspaces`
- `GET /api/v1/workspaces/{workspace_id}`
- `POST|GET /api/v1/workspaces/{workspace_id}/projects`
- `GET /api/v1/projects/{project_id}`
- `POST|GET /api/v1/projects/{project_id}/versions`
- `POST /api/v1/projects/{project_id}/assets/register`
- `GET /api/v1/projects/{project_id}/assets`

Project versions are ordered snapshots. Video-job compatibility requests without explicit
IDs resolve to the configured default workspace, a project by request slug and its initial
version.

## Video jobs and audit

- `POST /api/v1/video-jobs`: creates and enqueues a project-bound job. Optional
  `Idempotency-Key` is hashed and prevents duplicate execution for 24 hours.
- `GET /api/v1/video-jobs/{job_id}`: canonical state, context IDs, progress, artifacts and
  stable errors.
- `GET /api/v1/video-jobs/{job_id}/events`: ordered audit history.
- `GET /api/v1/video-jobs/{job_id}/artifacts/{artifact_name}`: serves only a recorded safe
  name; if scratch is missing, restores from object storage and checks SHA-256.

The accepted video-job terminal success state is `awaiting_review`. Publishing is a separate,
final-render-bound V2-09 resource and succeeds only as a dry run.

## Providers and cost

- `GET /api/v1/providers?capability=...`
- `GET /api/v1/projects/{project_id}/costs`
- `GET /api/v1/projects/{project_id}/cost-summary`

Currency is always `VND`. An unpriced paid operation is explicit; it is never silently
treated as zero. Provider secrets are represented by config references, not API values.

## Trend and idea intelligence

- `GET /api/v1/trend-sources`
- `POST|GET /api/v1/workspaces/{workspace_id}/trend-signals[/collect]`
- `POST|GET /api/v1/workspaces/{workspace_id}/trend-clusters[/refresh]`
- `GET /api/v1/trend-clusters/{cluster_id}`
- `POST /api/v1/trend-clusters/{cluster_id}/ideas/generate`
- `GET /api/v1/workspaces/{workspace_id}/ideas`
- `POST|GET /api/v1/workspaces/{workspace_id}/content-opportunities[/refresh]`
- `POST /api/v1/ideas/{idea_id}/projects`

Collection accepts a provider key plus optional query/country/locale/language/limit. Cluster and
idea requests carry channel, niche, objective and configurable weights. Response scores always
declare `estimated=true`. Live providers return `PROVIDER_NOT_CONFIGURED` until authorized
credentials/adapters exist. Creating a project from an idea is idempotent and draft-only.

## Upload and Auto Edit Analysis

- `POST /api/v1/uploads/init`: initialize a bounded resumable upload.
- `PUT /api/v1/uploads/{upload_id}/parts/{part_number}`: raw part body; optional
  `X-Part-SHA256` must be lowercase SHA-256.
- `GET /api/v1/uploads/{upload_id}`: durable part and completion status.
- `POST /api/v1/uploads/{upload_id}/complete`: assemble, hash, inspect, deduplicate,
  store and register the source asset.
- `POST /api/v1/projects/{project_id}/analyze`: create or replay an idempotent analysis
  for a validated source video.
- `GET /api/v1/projects/{project_id}/analyses`
- `GET /api/v1/projects/{project_id}/analyses/{analysis_id}`

Completion checks declared size/checksum, file signature and declared MIME/kind before FFprobe.
The source asset records rights/provenance and immutable checksum. Analysis responses contain
the original transcript evidence, scenes, user-toggleable silence decisions and ranked highlights.
They always report `source_media_mutated=false` and `publish_requested=false`.

## Vision AI and Smart Reframe

- `POST /api/v1/projects/{project_id}/analyses/{analysis_id}/vision`: create or replay a
  structured Vision analysis for a succeeded V2-04 analysis.
- `GET /api/v1/projects/{project_id}/vision-analyses`
- `GET /api/v1/projects/{project_id}/vision-analyses/{vision_analysis_id}`

The request selects one or more of `9:16`, `16:9`, `1:1` and `4:5`, sampling/tracking/smoothing
thresholds and optional crop-keyframe overrides. The response contains typed frame/OCR/object,
composition, quality, scene, subject-track, best-frame and reframe-plan evidence. It always reports
`source_media_mutated=false`, `publish_requested=false` and `paid_external_call=false`.

Normal development and CI use `fixture-vision`; its provenance states that it is mock tested and
not real-provider tested. The contract-only live adapter returns `PROVIDER_NOT_CONFIGURED` until an
owner-approved provider and credentials exist.

## Media Intelligence and B-roll resolution

- `POST|GET /api/v1/projects/{project_id}/media-plans`
- `GET /api/v1/projects/{project_id}/media-plans/{media_plan_id}`
- `POST /api/v1/projects/{project_id}/media-plans/{media_plan_id}/items/{item_id}/resolve`
- `GET /api/v1/projects/{project_id}/media-resolution-jobs/{resolution_job_id}`
- `GET /api/v1/projects/{project_id}/media-assets`

A plan requires a succeeded Auto Edit analysis and may reference its matching succeeded Vision
analysis. It contains B-roll intent/query/timing/prompt/confidence, chosen strategy, fallbacks,
ranked stock candidates, provider state and VND budget state. Resolution is asynchronous and
returns HTTP 202. Rights/provenance are mandatory; unknown rights or non-production fixture output
keeps `publishing_blocked=true`. Responses always report no source mutation, no publish request and
no paid external call in the V2-06 path inherited by V2-07.

## Auto Edit timeline and proxy preview

- `POST /api/v1/projects/{project_id}/timeline`: create the project's initial timeline from a
  succeeded Auto Edit analysis and optional matching media plan.
- `GET /api/v1/projects/{project_id}/timeline`: read the canonical current version.
- `PUT /api/v1/projects/{project_id}/timeline`: apply one or more typed operations with required
  `expected_version` optimistic concurrency.
- `POST /api/v1/projects/{project_id}/timeline/restore`: restore a historical snapshot as a new
  current version; history is never overwritten.
- `GET /api/v1/projects/{project_id}/timeline/versions`: ordered immutable version history.
- `POST /api/v1/projects/{project_id}/preview`: enqueue or replay a 540x960 preview bound to a
  timeline version.
- `GET /api/v1/projects/{project_id}/previews/{preview_id}`: status, progress, version validity and
  checksum-bearing manifest.
- `POST /api/v1/projects/{project_id}/previews/{preview_id}/cancel`: request cancellation.
- `GET /api/v1/projects/{project_id}/previews/{preview_id}/content`: serve only the registered
  project-scoped preview asset.

Timeline operations are `move`, `trim`, `split`, `delete`, `reorder`, `disable`, `duplicate`,
`set_clip_properties` and `set_track_state`. Stale writes return HTTP 409 with
`TIMELINE_VERSION_CONFLICT` and the actual current version. Every accepted change creates a new
immutable timeline version, resets approval to `draft` and invalidates earlier previews.

Preview statuses are `queued`, `running`, `ready`, `stale`, `cancelled` and `failed`. Preview remains
the fast video-only V2-07 path. All timeline and preview contracts keep
`source_media_mutated=false`, `publish_requested=false`; preview also keeps `external_call=false`.

## Audio, subtitle, review, approval and final render

- `POST|GET /api/v1/projects/{project_id}/production-package`: create/refresh or read the package
  bound to the current timeline.
- `PUT /api/v1/projects/{project_id}/subtitles`: append an immutable cue/style version using
  expected timeline and subtitle versions.
- `PUT /api/v1/projects/{project_id}/audio-mix`: append an immutable voice/music/mix version using
  expected timeline and audio versions.
- `POST /api/v1/projects/{project_id}/review-render`: enqueue the exact package tuple at
  `review-540x960`.
- `GET /api/v1/projects/{project_id}/renders/{render_id}`: read progress, QC and evidence.
- `POST /api/v1/projects/{project_id}/renders/{render_id}/cancel`: request cancellation.
- `GET /api/v1/projects/{project_id}/renders/{render_id}/content`: serve only the registered
  project-scoped MP4 artifact.
- `POST /api/v1/projects/{project_id}/approvals`: request review for an `awaiting_review` artifact.
- `POST /api/v1/projects/{project_id}/approvals/{approval_id}/decision`: record `approved`,
  `changes_requested` or `rejected` with reviewer identity/comment.
- `POST /api/v1/projects/{project_id}/final-render`: enqueue a final profile only when the supplied
  approval matches the current review/timeline/subtitle/audio tuple.
- `GET /api/v1/projects/{project_id}/production-history`: ordered production audit history.

Review jobs end at `awaiting_review`; final jobs end at `ready` only after full QC. Version conflict
or an invalid approval boundary returns HTTP 409. All render records hard-code
`publishing_allowed=false` and `external_publish_requested=false`. The V2-09 publishing service
never changes the artifact; it validates an approved final render and records a separate receipt.

## Publishing validation and receipts

- `POST /api/v1/projects/{project_id}/publish`: validate and reserve a publishing request. A
  16–200 character `Idempotency-Key` header is required.
- `GET /api/v1/projects/{project_id}/publications`: ordered durable attempts.
- `GET /api/v1/projects/{project_id}/publications/{publication_id}`: one attempt and receipt.
- `GET /api/v1/projects/{project_id}/publication-history`: append-only audit events.
- `GET /api/v1/publishing-platforms`: versioned platform profiles and provider state.

The request names one of `youtube`, `tiktok`, `instagram_reels` or `facebook`, the exact final
render, metadata and `mode`. `dry_run` is the only successful V2-09 mode. Its mock receipt always
states `external_action=false` and `duplicate_post_created=false`, with no remote ID or URL.
`mode=live`, incomplete rights, stale approval, failed QC, unsupported media or invalid metadata
returns HTTP 409. Once reserved, a blocked attempt remains readable for audit. An exact retry
returns the original record with `X-Idempotent-Replay: true`; a reused key with a changed payload
returns `IDEMPOTENCY_KEY_CONFLICT`.

Publication responses never include provider credentials or secret-reference values.

## Analytics and Learning

- `POST /api/v1/projects/{project_id}/analytics/syncs`: enqueue an idempotent fixture or
  contract-only provider sync; requires `Idempotency-Key`.
- `GET /api/v1/projects/{project_id}/analytics`: latest report, snapshot, assessment, feature
  evidence and recommendation-only insights.
- `GET /api/v1/projects/{project_id}/analytics/syncs`: durable sync history.
- `GET /api/v1/projects/{project_id}/analytics/syncs/{sync_id}`: one durable sync.
- `GET /api/v1/projects/{project_id}/analytics/snapshots`: historical normalized snapshots.
- `GET /api/v1/projects/{project_id}/analytics/assessments`: historical winner assessments.
- `GET /api/v1/projects/{project_id}/analytics/learning-insights`: learning evidence.
- `GET /api/v1/projects/{project_id}/analytics/history`: append-only analytics events.
- `GET /api/v1/analytics-providers`: fixture/official provider truth matrix.

The create route requires a successful publication receipt. The enabled development/CI path uses
`provider_mode=fixture`; official modes terminate `not_configured` without a network call. Missing
metrics are returned as JSON `null` with `supported=false`. Revenue and RPM use VND. All responses
retain explicit no-execution literals described in [Analytics and Learning](ANALYTICS_LEARNING.md).

The API has no authentication/RBAC in V2-10 and therefore remains localhost/CI-only.
