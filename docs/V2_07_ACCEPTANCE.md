# V2-07 acceptance — Auto Edit Studio

## Status and scope

V2-07 is implemented for deterministic local and GitHub CI acceptance. It is not merged or
production-deployed by this document. The increment adds the editable timeline, Studio UI and
proxy preview only; V2-08 audio/subtitle/final-render work and all publishing remain separately
gated.

## Required acceptance evidence

The V2-07 branch must pass all of these gates on its final commit:

1. Python compile and the complete API/worker/ComfyUI test suite.
2. Studio unit tests and JavaScript syntax checks.
3. Renderer tests, typecheck and bundle verification.
4. Alembic upgrade, downgrade to base and replay through `0006_v2_07_auto_edit_studio`.
5. Compose contract, fail-closed settings and secret-pattern checks.
6. Docker deterministic E2E from V2-01 through V2-07.

The Docker E2E must retain these review artifacts in the CI bundle:

- `timeline-v1.json`, `timeline-v2.json`, `timeline-before-restart.json` and version history;
- `timeline-conflict.json` proving stale-write HTTP 409;
- `preview-created.json`, `preview-ready.json` and stale preview records;
- `preview.mp4` plus `preview-probe.json` proving 540x960 H.264 and no audio;
- timeline and preview records fetched after API restart;
- the earlier transcript, scenes, highlights, Vision, media-plan, provenance, cost and V1 render
  evidence required by the stacked end-to-end flow.

## Contract assertions

- Timeline version 1 is created from succeeded analysis evidence.
- Every accepted mutation increments the immutable version sequence.
- A stale `expected_version` is rejected with `TIMELINE_VERSION_CONFLICT`.
- Timeline state and version history recover from PostgreSQL after restart.
- The worker can recover incomplete preview delivery from V2-owned Redis.
- Preview is bound to one timeline version, reports progress, supports cancellation and becomes
  stale after a later mutation.
- Preview output is exactly 540x960 H.264, video-only, registered in object storage and served by
  a project-scoped route.
- Source asset checksum/object key remain unchanged.
- Every timeline response states no source mutation and no publish request; every preview response
  additionally states `external_call=false`.

## UI acceptance

Desktop and responsive review must confirm:

- project selection and empty/create-timeline states;
- media, transcript, scenes and B-roll panels;
- timeline tracks and proxy waveform;
- drag/drop, trim, split, move, delete, reorder, disable and duplicate;
- crop/transform/speed/opacity/volume inspector;
- zoom, playhead, snapping, undo/redo, track lock and mute;
- ready/running/stale/cancelled preview states;
- explicit `Draft only`, `Không publish` and V2-08 deferred labels.

## Safety acceptance

- `PUBLISH_ENABLED=false` and `HUMAN_APPROVAL_REQUIRED=true` remain startup invariants.
- There is no publish endpoint or customer-facing delivery action.
- Normal CI performs no paid call and uses only copyright-safe fixtures.
- External media, paid media and ComfyUI execution remain disabled.
- No AgentHub, CRM, Ads, messaging, CMS, n8n, Caddy or shared Redis runtime is added or changed.
- No secret or production media is committed.

## Owner gates after CI

CI green permits review only. Merge requires explicit owner approval. Production deployment is a
separate gate and is still prohibited until authentication/RBAC, backed-up durable storage,
monitoring, guarded deployment/rollback and real-provider acceptance exist.
