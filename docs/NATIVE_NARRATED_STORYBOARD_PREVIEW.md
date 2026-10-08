# Native narrated storyboard preview

Storyboard projects with an explicitly applied measured narration plan now
produce a combined audible preview. The preview uses the same canonical shots,
actual prepared PCM, subtitles, crop/motion, music and mix path as final rendering.
It runs transport and full media QC, including actual Vietnamese subtitle pixel
bounds. Source-footage previews retain their existing workflow; older storyboard
projects without prepared narration retain their labelled silent visual proxy.

## Approval and rendering

The Studio narration panel supports explicit human approval for voice preparation.
The request uses `purpose=narration`; its recorded `approval_scope=narration_only`
permits the existing narration job but cannot authorize final rendering. No job
is automatically dispatched by approval. Existing human roles, CSRF, revision
and acknowledgement guards apply.

Preparing narration leaves canonical editing unchanged. Applying the measured
plan explicitly updates the shared canonical timeline and clears approval.
Generating the audible preview grants no final-render, inference or publishing
authority. The user reviews the combined video before production approval.
That approval binds the current preview bytes, manifest, document, canonical
timeline, original narration job/plan/audio and voice-input fingerprint.
Final-job admission and new rendering verify this exact binding again.
Historical verified render checkpoint replay remains possible after later
project edits, without granting the old video current approval authority.

## Physical evidence and invalidation

`native-narrated-storyboard-preview-v1` previews have separate scoped folders.
Private attempts retain failures. The playable preview, full/transport/combined
QC reports, actual subtitle masks, ASS, timeline, voice metadata and render
manifest have measured byte hashes. Current review and media serving verify
all required artifacts and original selected sources. Corruption or canonical
edits invalidate review eligibility. Original prepared voice bytes remain intact;
no new inference, resynthesis or automatic paid fallback occurs.

Hard preview QC failures make the preview unavailable for production approval
and final-job admission. This is a failed preview with a `failed_qc` report;
it is not a fabricated terminal render job. Final-render hard QC failures still
use the existing `failed_qc` job state. Preview cancellation is checked before
and after the bounded rendering operation; immediate FFmpeg interruption is
not implemented by this path.

Studio displays whether a preview is a silent visual proxy, source-footage
preview or measured narrated preview. Current narrated-preview readiness updates
the production approval controls after asynchronous completion. Narration-only
approval does not expose final-render controls. Final video review remains
separate: rendering-effects parity does not mean Owner acceptance or identical
preview/final encoded bytes.

## Verification limits

Six new Native cases exercise actual FFmpeg output, full QC/subtitle masks,
source approval, authority separation, exact preview approval binding, stale
edits, corruption and cancellation. Three additional Studio cases cover explicit
narration approval and narrated-preview eligibility. Existing narration HTTP,
worker, render and Studio tests remain applicable.

The isolated signed-human technology rehearsal performs actual HTTP ingestion,
MediaPlan/canonical edits, narration preparation, measured timing apply, audible
preview, production approval, final rendering, full QC, frozen-video rejection,
backup/restore and separate-process verified checkpoint replay. Its audio is
explicit cached synthetic PCM. No genuine voice inference, semantic Vision,
independent rights, paid operation, browser usability or Owner UAT is inferred.

See `north-star/native-narrated-preview-evidence.json` and
`NORTH_STAR_WAVE_REPORTS.md` for this increment's exact tests and hashes. Current
guided project defaults and actual installed local-model inference are described
in `NATIVE_GUIDED_NARRATION_WORKFLOW.md`, with separate final-source evidence.
Speech/Owner/browser acceptance, provider-neutral voices/languages/styles and
the remaining original Mode A/B, Trend, publishing, analytics, learning,
Agent Hub, hardening and final A/B/C acceptance remain program work.
This increment does not certify North Star completion or production deployment.
