# Auto Edit Studio — V2-07

V2-07 turns the evidence produced by Auto Edit Analysis, Vision and Media Intelligence into an
editable timeline and an asynchronous 540p proxy preview. It remains a local/CI increment: source
media is immutable, human approval is mandatory, and no publishing path exists.

## Studio workflow

Open `http://localhost:3000/studio.html`, select a project, and create its first timeline from a
succeeded Auto Edit analysis. If a matching resolved media plan exists, eligible B-roll references
are included. The Studio then exposes:

- media, transcript, scene and B-roll browsers with search and seek-to-evidence interactions;
- video, B-roll, subtitle, original-audio and metadata tracks;
- drag/drop, trim, split, move, delete, reorder, disable and duplicate operations;
- source crop, position, scale, rotation, speed, opacity and volume controls;
- zoom, playhead, quarter-second snapping, a clearly labelled visual proxy waveform, undo/redo, track lock
  and track mute;
- an asynchronous, cancellable 540x960 video-only preview bound to an immutable timeline version.

The current editable JSON is the source of truth. UI operations never mutate the source asset.

## Timeline contract

`packages/contracts/timeline.schema.json` is the language-neutral JSON Schema. The Pydantic model
is in `apps/api/app/timeline_models.py`. A snapshot contains:

- schema version, canvas, frame rate, aspect ratio and total duration;
- ordered typed tracks and clips;
- each clip's source window, timeline placement, speed, crop, transform, opacity, volume,
  transitions, effects, disabled state and evidence metadata;
- literal safety fields `source_media_mutated=false` and `publish_requested=false`.

PostgreSQL stores one current timeline per project and an immutable row for every version. A write
must include `expected_version`. A stale client receives HTTP 409 with the actual current version;
the Studio reloads that version instead of overwriting another editor's work.

Undo and redo create new version records by restoring an older snapshot. Historical rows are not
rewritten. Any timeline mutation resets approval state to `draft` and marks previews from earlier
versions `stale`.

## Initial timeline derivation

The first version is deterministic and traceable:

1. Read only a succeeded Auto Edit analysis and its immutable source asset.
2. Apply enabled silence decisions only when they do not conflict with speech.
3. Map source scenes to contiguous source-video and original-audio clips.
4. Map transcript segments onto a text track without altering transcript evidence.
5. Add only resolved Media Intelligence assets with recorded provenance; missing or unsupported
   assets remain absent rather than being fabricated.
6. Validate the result against the JSON Schema before persistence.

Subtitle content is visible as evidence, but subtitle styling, TTS, music and final audio mixing are
deliberately deferred to V2-08.

## Preview lifecycle

`POST /api/v1/projects/{project_id}/preview` creates or reuses a preview for one timeline version
and 540x960 dimensions. PostgreSQL is canonical; Redis carries only the recoverable delivery ID.
The worker:

1. claims the preview ID;
2. downloads project-scoped video/raster assets into bounded scratch;
3. renders an H.264 video-only proxy with FFmpeg;
4. uploads `preview.mp4` to the V2 object store;
5. registers a `proxy-preview` render asset and stores a checksum-bearing manifest;
6. deletes bounded scratch.

Status is `queued`, `running`, `ready`, `stale`, `cancelled` or `failed`. Progress is persisted.
Cancellation is checked before download and while FFmpeg runs. Worker restart recovery requeues
only canonical incomplete IDs. A later timeline mutation invalidates the old preview but retains it
as review evidence.

## API

- `POST|GET|PUT /api/v1/projects/{project_id}/timeline`
- `POST /api/v1/projects/{project_id}/timeline/restore`
- `GET /api/v1/projects/{project_id}/timeline/versions`
- `POST /api/v1/projects/{project_id}/preview`
- `GET /api/v1/projects/{project_id}/previews/{preview_id}`
- `POST /api/v1/projects/{project_id}/previews/{preview_id}/cancel`
- `GET /api/v1/projects/{project_id}/previews/{preview_id}/content`

## Intentional limits

- Preview is video-only; the original-audio track is represented in the editor but mixed output is
  V2-08 work.
- Transition/effect values exist in the timeline contract, but professional transition/effect
  authoring is not claimed in this MVP.
- The Studio does not expose approval, final render, publishing or analytics actions.
- API authentication, RBAC and workspace membership are not implemented; localhost binding remains
  the access boundary and production deployment is prohibited.
- Live Vision, stock and generation providers remain `not_configured`; fixture assets never become
  production-eligible.
