# API — V2-04

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

The accepted terminal success state is `awaiting_review`; there is no publish API.

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
