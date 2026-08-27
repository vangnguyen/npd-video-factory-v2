# Media Intelligence — V2-06

## Purpose and boundary

V2-06 turns succeeded Auto Edit scenes and optional V2-05 Vision evidence into a durable,
explainable media plan. It decides where supporting media is useful, evaluates reusable source
media, licensed stock and synthetic generation options, and resolves approved plan items through
an asynchronous worker queue. It does not publish, mutate source footage or download media from
social platforms.

Normal CI uses copyright-safe deterministic fixtures. Those fixtures are contract evidence only:
stock/AI fixture outputs are explicitly `production_eligible=false`, and generated video fixtures
are not playable production video. No real stock, image-generation, video-generation or GPU
provider was exercised in V2-06.

## Planning flow

```text
succeeded Auto Edit analysis ----+
                                  +--> BrollPlanner --> MediaPlanner --> PostgreSQL media plan
optional succeeded Vision --------+          |               |
                                             |               +--> rights/cost/provider state
immutable user source asset -----------------+                         |
                                                                       v
                                                           Redis resolution queue
                                                                       |
                                                                       v
                                                        worker materializes/registers
                                                                       |
                                                                       v
                                                        object storage + provenance
```

Every scene receives a B-roll decision with:

- intent and copyright-safe search query;
- requested duration and exact placement window;
- preferred media type and original generation prompt;
- evidence-derived confidence.

The deterministic resolver order is configurable per request and defaults to user asset,
licensed stock, internal library, AI image, AI video and motion graphic. The chosen strategy,
fallbacks, stock candidates, semantic score, Vision rerank, estimated VND cost and reason metadata
are persisted. Replaying the same inputs/provider state returns the same plan.

## Provider contracts

`StockMediaProvider` exposes `search_images`, `search_videos`, `get_asset` and `download_asset`.
Every candidate carries provider/source identifiers, creator, license, attribution requirement,
dimensions/duration, rights status, source reference, cost and provenance.

`ImageGenerationProvider` and `VideoGenerationProvider` accept normalized typed inputs and expose
an explicit VND estimate before execution. Video generation is resolved through the durable async
queue. Contract-only adapters return `not_configured`; no missing provider is represented as live.

The deterministic fixtures:

- make no network or paid call;
- create synthetic SVG or JSON contract artifacts;
- state `real_provider_tested=false`;
- preserve prompts, seed, model/workflow and checksums;
- remain ineligible for production publishing.

## Rights and provenance gate

Every resolved media asset records one source type: `user_upload`, `stock`, `ai_generated` or
`internal_library`. It also records rights status, license, provider, creator, source reference,
attribution, generation evidence, technical metadata and production eligibility.

Publishing is fail-closed. `publishing_allowed=true` requires both:

1. `production_eligible=true`; and
2. rights status `owned`, `licensed` or `verified`.

`unknown` or `restricted` rights block publishing. V2-06 has no API or code path that records an
owner override; `owner_override_recorded` is always false. A future override must be an audited,
owner-gated feature rather than a data edit.

## Persistence and recovery

PostgreSQL is canonical for plans, plan items, media provenance and resolution jobs. Redis contains
only queued/processing delivery IDs. On worker restart, in-flight Redis IDs and PostgreSQL
`queued`/`running` jobs are deduplicated and requeued. Generated binaries live in the existing
V2-owned object store; scratch files are bounded and deleted after each attempt.

Stable fingerprints protect plan and resolution idempotency. Provider usage produces exactly one
VND cost record per operation. Unknown paid costs are never silently converted to zero.

## API

- `POST /api/v1/projects/{project_id}/media-plans`
- `GET /api/v1/projects/{project_id}/media-plans`
- `GET /api/v1/projects/{project_id}/media-plans/{media_plan_id}`
- `POST /api/v1/projects/{project_id}/media-plans/{media_plan_id}/items/{item_id}/resolve`
- `GET /api/v1/projects/{project_id}/media-resolution-jobs/{resolution_job_id}`
- `GET /api/v1/projects/{project_id}/media-assets`

Resolution creation returns HTTP 202. The worker advances `queued -> running -> succeeded`, or
ends in `needs_approval`, `failed` or `cancelled`. Cost above `max_ai_cost_vnd` stops before
generation. External and paid execution stay disabled unless separately owner-approved.

## Intentional limits

- no production publishing or source mutation;
- no social-media scraping/downloading;
- no live stock-provider acceptance;
- no real image/video generation acceptance;
- no production ComfyUI/GPU execution;
- no automatic rights override;
- no UI timeline/editor in this increment;
- no API auth/RBAC or public deployment.
