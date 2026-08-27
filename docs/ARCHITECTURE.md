# Architecture — V2-07

## Bounded context

Video Factory V2 is the media execution plane. AgentHub remains a separate control plane.
V2 imports no AgentHub package and reads no AgentHub database or Redis namespace. A future
integration must use versioned REST/events or signed webhooks, never shared runtime state.

```text
Local Trend Radar Studio
        |
        v
FastAPI API -------------------------- PostgreSQL
   |   workspace/project/version        canonical jobs/audit/idempotency
   |   provider/cost/asset metadata      trend/evidence/cluster/idea/queue
   |   upload/transcript/scene/silence/highlight
   |   vision-frame/OCR/quality/track/reframe evidence
   |   media plans/items/rights/provenance/resolution jobs
   |   timeline/current version/history/preview jobs
   |
   +----> V2 Redis transient queues ---> Worker ----> Remotion ----> FFmpeg QC
   |                                      |
   |                                      +---- media resolver/provider contracts
   |                                      +---- FFmpeg 540p proxy renderer
   |                                                  |
   |                                                  +---- optional allowlisted ComfyUI bridge
                                            |
                                            +-------> S3-compatible object storage
                                                       (MinIO in local/CI)
```

## Ownership and persistence

| Component | Owns | Durability |
|---|---|---|
| PostgreSQL | workspace/project/job/audit, assets/providers/cost, trend/idea, upload, Auto Edit, Vision/reframe, Media Intelligence, timeline versions and preview state | canonical |
| Redis | pending and processing job/media/preview delivery IDs | transient/recoverable |
| S3/MinIO | source, generated, metadata, final-render and proxy-preview objects | canonical binary store |
| job volume | resumable local worker scratch/cache | replaceable |
| renderer | strict manifest-to-MP4 execution | stateless apart from job scratch |
| Studio Nginx | responsive Trend Radar/Auto Edit Studio assets and same-origin API proxy | stateless |

The Compose project remains `npd-video-factory-v2`. PostgreSQL, Redis and MinIO are V2-owned
and are not published to the host. API and renderer bind to `127.0.0.1` by default.

## Domain and provenance

A workspace owns projects. A project owns ordered immutable version snapshots. Every job is
bound to one workspace/project/version. Every persisted asset records class, type, filename,
object key, content type, byte size, SHA-256, storage provider, source job and provenance.
Provider operations use an idempotent operation key and create exactly one VND cost record.

Trend providers normalize only authorized metadata into immutable snapshots/signals and evidence.
Pure deterministic services cluster signals, assign lifecycle and calculate context-specific score
profiles. Idea drafts and ranked queue runs are durable planning objects. Selecting an idea creates
only an immutable draft project snapshot.

Upload parts live only in bounded staging scratch. Completion assembles the bytes once, validates
SHA-256 and magic bytes, records FFprobe metadata and places immutable source bytes in object
storage. PostgreSQL holds the upload receipt. Auto Edit downloads a scratch copy for analysis,
persists normalized transcript/scene/silence/highlight evidence and removes only that scratch copy.
It never changes or replaces the source object.

V2-05 starts only from a succeeded Auto Edit analysis and the same immutable source asset. A
provider emits structured frame evidence. Pure deterministic services normalize frames, combine
them with existing scenes, build subject tracks, rank candidate frames and generate smoothed crop
keyframes for four ratios. The service persists these decisions under a source/provider/config
fingerprint, records the provider operation in VND, and deletes its bounded scratch copy. A manual
override creates a new fingerprint; historical analyses are not overwritten.

V2-06 consumes those succeeded analyses without modifying them. B-roll and media plans are pure,
versioned decisions. Resolution IDs travel through the existing V2 Redis, while PostgreSQL remains
canonical. Resolved binaries are registered in the same V2 object store and linked to explicit
rights/source/generation provenance. Unknown rights, non-production fixture media and unresolved
items keep the plan publishing-blocked. The optional ComfyUI bridge is a separate bounded adapter:
only allowlisted workflow IDs cross the API boundary and its Compose `gpu` profile is off by default.

V2-07 converts the same persisted evidence into one canonical timeline per project. The current
snapshot points at immutable version rows; every write uses optimistic concurrency and creates a
new row. Timeline edits reference existing assets and never modify their object keys or bytes.
Earlier previews are marked stale after a mutation, so UI playback cannot silently represent a
different timeline version. Preview IDs travel through V2 Redis, while PostgreSQL remains canonical.
The worker downloads bounded scratch inputs, renders a 540x960 H.264 video-only proxy with FFmpeg,
stores it in the same V2 object store, registers it as a non-publishing render asset and removes
scratch. Incomplete preview IDs are recoverable after worker restart.

## Durable job rules

- PostgreSQL is the source of truth; Redis never stores canonical job JSON.
- Progress and stage transitions are monotonic and row-locked.
- Creation, transitions, artifact registration and failure are audit events.
- Idempotency keys are stored only as SHA-256 hashes with expiry.
- A worker restart requeues claimed jobs; an API restart reads the same job from PostgreSQL.
- Missing local artifacts may be restored from object storage and must pass the recorded
  SHA-256 before being served.

## Safety state

V2-07 has no publish endpoint. Startup rejects `PUBLISH_ENABLED=true` and
`HUMAN_APPROVAL_REQUIRED=false`. Successful jobs stop at `awaiting_review`. API auth/RBAC is
not yet implemented, so this increment is local/CI only and must not be exposed publicly. The
Vision and media fixtures are rejected in production, and mock provenance must not be interpreted
as real pixel-model or provider-quality evidence. External/paid media and ComfyUI execution are
separate fail-closed settings. Proxy previews are explicitly non-final, video-only, zero-external-call
artifacts and cannot be published.
