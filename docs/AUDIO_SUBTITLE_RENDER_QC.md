# Audio, Subtitle, Render and QC — V2-08

## Outcome

V2-08 turns an approved editable timeline into review and final media artifacts without adding a
publishing path. Subtitle, audio, review, approval and final-render records are immutable/versioned
and bound to the exact timeline version that produced them. Any accepted edit invalidates stale
approvals and renders.

The implementation remains a development/CI increment. eSpeak is an audible offline test voice,
not an accepted production Vietnamese voice. Authentication/RBAC and publishing remain outside
V2-08.

## Execution flow

```text
Current timeline version
        |
        v
Production package
  | subtitle version
  | audio-mix version
  v
Review render (540x960, H.264/AAC)
        |
        v
Human review request -> owner decision
        |
        | exact timeline + review + subtitle + audio tuple
        v
Final render (9:16, 16:9 or 1:1)
        |
        v
Full QC -> ready or failed_qc

No branch in this flow publishes media.
```

PostgreSQL is canonical for packages, versions, approvals, jobs and audit events. Redis carries
only queued/processing render IDs. The worker recovers incomplete IDs from PostgreSQL after a
restart. Source and output binaries use the existing V2 object store; bounded scratch directories
are removed after processing.

## Version and approval model

Each production package records:

- `timeline_version_id` and numeric `timeline_version`;
- current immutable subtitle version;
- current immutable audio-mix version;
- current approval, latest review render and latest final render;
- timestamps and actor references, but no credentials or secret values.

An approval records the review render/version plus the timeline, subtitle and audio versions. A
final render is rejected unless that exact tuple has status `approved`. Timeline, subtitle or audio
mutation clears the package's current approval and marks affected render records `stale`.

Review states are `draft`, `awaiting_review`, `changes_requested`, `approved` and `rejected`.
Render states are `queued`, `running`, `awaiting_review`, `ready`, `stale`, `cancelled`, `failed`
and `failed_qc`. Review jobs stop at `awaiting_review`; successful final jobs stop at `ready`.

## Subtitle contract

Subtitles are stored as ordered cues with optional word-level timing. Validation requires:

- unique cue IDs and positive, monotonic, non-overlapping time windows;
- all cues and words to stay within timeline/cue duration;
- at most three displayed lines and an estimated mobile safe-area character limit;
- Noto Sans/Noto Sans Display for Vietnamese glyph coverage;
- explicit position, colors, background opacity, safe margin and animation;
- a generated SRT artifact for each render in addition to the render manifest evidence.

The Remotion `timeline-render-v1` composition supports dynamic word highlighting while keeping cue
text inside the configured safe margin.

## Audio contract

Narration is synthesized per subtitle cue instead of as one large track. Each chunk is normalized
to mono PCM at 48 kHz, measured, trimmed and fitted only within the bounded timing adjustment. A
chunk that cannot fit its cue fails the job instead of silently drifting.

The audio mixer provides:

- narration gain and bounded speech speed;
- optional project music with explicit owned/licensed/public-domain/royalty-free provenance;
- licensed-music fade in/out and speech-window ducking;
- 48 kHz stereo PCM intermediate output;
- a configured peak limiter and effective-silence rejection.

Provider states are explicit:

| Provider | Default state | Meaning |
|---|---|---|
| eSpeak | configured in dev/CI | Audible deterministic/offline acceptance only |
| contract | `not_configured` | Interface exists; no live provider is claimed |
| OpenAI TTS | disabled/not configured | Requires credential plus explicit external-audio gate |

No credential appears in production-package, render, audit, cost or API responses. External audio
execution defaults to false. A production voice still needs explicit human Vietnamese listening
acceptance.

## Renderer contract

`packages/contracts/timeline-render.schema.json` is a strict JSON Schema 2020-12 contract. It
contains local render-time visual URIs, the mixed-audio URI, subtitle cues/style, dimensions/fps
and literal safety values. Evidence persisted after render replaces local paths with asset/artifact
references.

Supported profiles:

| Profile | Resolution | Purpose |
|---|---:|---|
| `review-540x960` | 540x960 | Fast human review |
| `vertical-1080x1920` | 1080x1920 | Final vertical artifact |
| `landscape-1920x1080` | 1920x1080 | Final landscape artifact |
| `square-1080x1080` | 1080x1080 | Final square artifact |

Remotion composes ordered image/video layers with crop, transform and opacity, then FFmpeg emits
H.264 video with AAC 48 kHz audio. Timeline visual coverage and referenced assets are validated
before rendering; uncovered gaps fail closed. Planning fixtures marked `production_eligible=false`
and simulated JSON/SVG assets cannot enter review/final rendering. They must first be replaced by
eligible MP4/WebM/QuickTime video or JPEG/PNG/WebP imagery.

## Full QC

Final success is not inferred from a renderer exit code. Full QC inspects:

- expected duration (tolerance 0.5 seconds), resolution and frame rate (tolerance 0.02 fps);
- H.264 video, AAC audio and 48 kHz sample rate;
- video/audio duration delta no greater than 0.25 seconds;
- black-frame ratio no greater than 10 percent;
- freeze-frame ratio no greater than 15 percent;
- effective silence, silence ratio no greater than 80 percent, and possible clipping;
- full decode errors/broken frames;
- subtitle safe-area result and timeline asset/gap result;
- sampled central-frame luminance with no external Vision call;
- SHA-256 of the accepted output.

A failed check records `failed_qc`, retains the report/evidence record and cannot be approved or
published.

## API surface

- `POST|GET /api/v1/projects/{project_id}/production-package`
- `PUT /api/v1/projects/{project_id}/subtitles`
- `PUT /api/v1/projects/{project_id}/audio-mix`
- `POST /api/v1/projects/{project_id}/review-render`
- `GET /api/v1/projects/{project_id}/renders/{render_id}`
- `POST /api/v1/projects/{project_id}/renders/{render_id}/cancel`
- `GET /api/v1/projects/{project_id}/renders/{render_id}/content`
- `POST /api/v1/projects/{project_id}/approvals`
- `POST /api/v1/projects/{project_id}/approvals/{approval_id}/decision`
- `POST /api/v1/projects/{project_id}/final-render`
- `GET /api/v1/projects/{project_id}/production-history`

All write requests reject unknown fields. Version conflicts and approval-boundary violations use
HTTP 409; invalid media/subtitle/audio contracts use HTTP 422.

## Safety boundary

- `PUBLISH_ENABLED=false` and `HUMAN_APPROVAL_REQUIRED=true` remain startup invariants.
- Render models and JSON Schema require `publishing_allowed=false` and
  `external_publish_requested=false`.
- V2-08 has no publish endpoint, platform token flow or automatic customer action.
- Final render is owner-gated and version-bound, but it is still only an artifact-generation action.
- Source media is downloaded to bounded scratch and never replaced or mutated.
- No AgentHub package, database or Redis namespace is imported or shared.
- Production deployment remains prohibited before V2-11 security and operational acceptance.

## Intentional limits

- no authentication, workspace membership or RBAC yet;
- no production Vietnamese voice has been accepted;
- no automatic voice cloning;
- no external music catalog or unclear-rights music;
- no publishing, platform OAuth, analytics or winner detection;
- no production deployment or shared-runtime integration with AgentHub.
