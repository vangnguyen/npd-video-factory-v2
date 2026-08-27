# Architecture — V2-10

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
   |   production package/subtitle/audio/approval/render/audit versions
   |
   +----> V2 Redis transient queues ---> Worker ----> Remotion ----> full FFmpeg QC
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
| PostgreSQL | workspace/project/job/audit, assets/providers/cost, trend/idea, upload, Auto Edit, Vision/reframe, Media Intelligence, timeline versions, preview state, production packages, subtitle/audio versions, approvals and render state | canonical |
| Redis | pending and processing job/media/preview/production-render delivery IDs | transient/recoverable |
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

V2-08 creates one production package for the project's current timeline. Subtitle and audio-mix
edits append immutable versions. Review renders are bound to the exact timeline/subtitle/audio
tuple and stop at `awaiting_review`. An approval adds the review-render version to that tuple; only
an exact current `approved` tuple can enqueue a final render. Any later edit invalidates the
approval and affected renders. Production render IDs use the same transient Redis delivery model,
while PostgreSQL and the object store remain canonical. The worker composes per-cue Vietnamese
narration, optional licensed music, dynamic subtitles and timeline layers through Remotion, then
runs full FFmpeg/FFprobe QC before persisting evidence and the H.264/AAC artifact.

V2-09 adds a publishing boundary after the approved final artifact. A publication reservation is
written to PostgreSQL before provider work and is keyed by a hashed idempotency key plus canonical
request fingerprint. The service validates the exact current approval/render tuple, every active
asset's rights, full-QC evidence and a versioned platform profile. The deterministic provider then
creates a durable mock receipt without network access. Official YouTube, TikTok, Instagram and
Facebook adapters stop at a typed contract-only boundary; they contain no live call and no browser
automation. Publication and event rows survive API restart without using Redis as canonical state.

V2-10 adds a read-only analytics boundary after a successful publication or explicitly mock
receipt. A hashed-idempotency sync row is canonical in PostgreSQL before its identifier enters the
V2-owned Redis analytics queue. The worker normalizes provider output into one immutable snapshot
and 16 nullable metric rows, captures the current video-feature evidence, creates a deterministic
winner assessment and writes recommendation-only learning insights. Historical snapshots are
append-only and incomplete work is recoverable after worker restart. Official providers remain
contract-only and no analytics record contains a credential value.

## Durable job rules

- PostgreSQL is the source of truth; Redis never stores canonical job JSON.
- Progress and stage transitions are monotonic and row-locked.
- Creation, transitions, artifact registration and failure are audit events.
- Idempotency keys are stored only as SHA-256 hashes with expiry.
- A worker restart requeues claimed jobs; an API restart reads the same job from PostgreSQL.
- Missing local artifacts may be restored from object storage and must pass the recorded
  SHA-256 before being served.

## Safety state

V2-10 retains the V2-09 dry-run-only publishing endpoint. Startup requires all live publishing gates to remain
coherent, requires an external secret-store contract and rejects every live gate in CI/test.
Official adapters remain contract-only and cannot execute even if configuration is accidentally
changed. `HUMAN_APPROVAL_REQUIRED=false` is rejected. API auth/RBAC is not yet implemented, so this
increment is local/CI only and must not be exposed publicly. The
Vision and media fixtures are rejected in production, and mock provenance must not be interpreted
as real pixel-model or provider-quality evidence. External/paid media and ComfyUI execution are
separate fail-closed settings. Proxy previews are explicitly non-final, video-only, zero-external-call
artifacts and cannot be published. Review and final render contracts both hard-code
`publishing_allowed=false`; final rendering requires human approval but still creates only an
artifact. Publishing creates only a separate mock receipt with `external_action=false`. eSpeak is
dev/CI evidence rather than a production voice acceptance.

Analytics adds a second fail-closed boundary: production rejects deterministic fixtures and V2-10
always rejects external analytics execution. Database constraints prohibit external-call,
automatic-action, paid-media-mutation, content-deletion and autonomous-execution state. Missing
provider metrics remain null, and learning never mutates Trend/Idea rank or downstream systems.
