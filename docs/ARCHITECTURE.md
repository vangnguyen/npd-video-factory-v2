# Architecture — V2-01

## Bounded context

Video Factory V2 is the media execution plane. AgentHub remains a separate control plane.
V2 imports no AgentHub packages and reads no AgentHub database or Redis namespace. A future
integration may use versioned REST, signed webhooks and versioned event contracts only.

```text
Client / future Studio
        |
        v
FastAPI video-job API ---- V2-owned Redis queue/state
        |                         |
        |                         v
        +-------------------- Video worker
                                  | content profile
                                  | local asset resolver
                                  | TTS + subtitle timing
                                  | manifest validation
                                  v
                            Remotion renderer
                                  |
                                  v
                         FFmpeg/FFprobe QC
                                  |
                                  v
                         awaiting_review artifact
```

## Runtime services

| Service | Responsibility | Persistence |
|---|---|---|
| `api` | Validate/enqueue jobs; expose state and safe artifacts | Redis + job artifact volume |
| `worker` | Deterministic pipeline and recovery | Redis + job artifact volume |
| `renderer` | Strict manifest validation and MP4 render | job artifact volume |
| `redis` | V2-only job queue/state | dedicated Compose volume with AOF |

The Compose project is `npd-video-factory-v2`; Redis is not published to the host. API and
renderer bind to `127.0.0.1` by default.

## Multi-niche boundary

`VideoJobCreate.niche` selects a `NicheProfile`. The deterministic provider consumes that
profile; the job engine, state machine, assets, renderer and QC do not inspect business
niche. `vertical-short-v1` is the generic core template. `real-estate-short-v1` remains a
backward-compatible adapter that uses the same renderer component.

V2-01 supports one vertical output contract (`9:16`, 1080x1920, Vietnamese) to preserve
verified parity. More channel, brand, language and video templates belong in the durable
provider/profile registry in V2-02, not ad-hoc conditionals in the engine.

## State and recovery

The API persists strict job records and idempotency keys in the V2 Redis instance. The
worker atomically claims jobs into a processing list and requeues in-flight IDs on restart.
Artifacts are written per safe `vid_*` directory; valid existing artifacts are reused.
There is no migration of old Redis keys.

## Safety state

V2-01 has no publish provider or publish endpoint. Startup rejects
`PUBLISH_ENABLED=true` and rejects `HUMAN_APPROVAL_REQUIRED=false`. Successful jobs stop at
`awaiting_review`. External provider smoke is a separately dispatched, owner-gated workflow.

## Next architecture increment

V2-02 introduces PostgreSQL project/workspace records, object storage, asset versioning,
durable provider/cost records and explicit dev/CI/production CPU deployment profiles while
preserving the V2-01 API and manifest compatibility contract.
