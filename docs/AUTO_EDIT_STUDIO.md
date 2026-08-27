# Auto Edit Studio — V2-08

V2-08 keeps the editable V2-07 timeline and asynchronous proxy, then adds a Production Workbench
for subtitle/audio versions, review, human approval, final rendering and full QC. It remains a
local/CI increment: source media is immutable, human approval is mandatory, and no publishing path
exists.

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
- dynamic subtitle text/style/word-timing controls and immutable saves;
- narration/mix controls plus optional project music with explicit rights;
- review playback, exact version-binding labels and recorded owner decision controls;
- 9:16, 16:9 and 1:1 final-render choices with summarized full-QC evidence.

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

The initial subtitle content remains traceable to transcript evidence. V2-08 stores later subtitle
and audio edits as separate immutable production-package versions; it never overwrites transcript
or timeline evidence.

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
- `POST|GET /api/v1/projects/{project_id}/production-package`
- `PUT /api/v1/projects/{project_id}/subtitles`
- `PUT /api/v1/projects/{project_id}/audio-mix`
- `POST /api/v1/projects/{project_id}/review-render`
- `POST /api/v1/projects/{project_id}/approvals`
- `POST /api/v1/projects/{project_id}/approvals/{approval_id}/decision`
- `POST /api/v1/projects/{project_id}/final-render`
- `GET /api/v1/projects/{project_id}/production-history`

## Intentional limits

- The fast proxy remains video-only; review/final jobs are the separate mixed A/V path.
- Transition/effect values exist in the timeline contract, but professional transition/effect
  authoring is not claimed in this MVP.
- The Studio exposes approval and artifact rendering, but no publishing or analytics action.
- eSpeak is a dev/CI voice and does not satisfy human production voice acceptance.
- API authentication, RBAC and workspace membership are not implemented; localhost binding remains
  the access boundary and production deployment is prohibited.
- Live Vision, stock and generation providers remain `not_configured`; fixture assets never become
  production-eligible.
