# Architecture — V2-04

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
   |
   +----> V2 Redis transient queue ----> Worker ----> Remotion ----> FFmpeg QC
                                            |
                                            +-------> S3-compatible object storage
                                                       (MinIO in local/CI)
```

## Ownership and persistence

| Component | Owns | Durability |
|---|---|---|
| PostgreSQL | workspace/project/job/audit, assets/providers/cost, trend/idea, upload and Auto Edit analysis state | canonical |
| Redis | pending and processing delivery queues | transient/recoverable |
| S3/MinIO | source, generated, metadata and render objects | canonical binary store |
| job volume | resumable local worker scratch/cache | replaceable |
| renderer | strict manifest-to-MP4 execution | stateless apart from job scratch |
| Studio Nginx | responsive Trend Radar assets and same-origin API proxy | stateless |

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

## Durable job rules

- PostgreSQL is the source of truth; Redis never stores canonical job JSON.
- Progress and stage transitions are monotonic and row-locked.
- Creation, transitions, artifact registration and failure are audit events.
- Idempotency keys are stored only as SHA-256 hashes with expiry.
- A worker restart requeues claimed jobs; an API restart reads the same job from PostgreSQL.
- Missing local artifacts may be restored from object storage and must pass the recorded
  SHA-256 before being served.

## Safety state

V2-04 has no publish endpoint. Startup rejects `PUBLISH_ENABLED=true` and
`HUMAN_APPROVAL_REQUIRED=false`. Successful jobs stop at `awaiting_review`. API auth/RBAC is
not yet implemented, so this increment is local/CI only and must not be exposed publicly.
