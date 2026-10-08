# Native scene narration preparation

Storyboard projects can prepare narration as a separate job before final
rendering. The existing worker and locked Thùy Dung TTS engine remain the
execution path. Current human approval, canonical shots and selected source
media are required before job admission or synthesis. Source-footage projects
retain their own audio workflow. No new voice cloning or paid provider is
enabled by this feature.

## Preparation and review

POST `/api/projects/{id}/jobs` with `kind=narration` uses the existing revision,
request-key deduplication, frozen approval, job states, recovery and logging.
The existing TTS child/checkpoint path produces the original WAV, metadata and
generation plan. A separate immutable `narration-plan.json` binds the source
document, approval, canonical timeline, voice profile/policies and exact PCM.

Measured scene intervals and brand intro/outro produce recommended scene
durations. Preparation does not mutate the timeline, approve media, dispatch a
render, or claim speech quality or word-level alignment. GET
`/api/projects/{id}/narration` returns scoped history; GET
`/api/projects/{id}/narration/{job}/audio` serves verified original audio.
Corrupted checkpoints are rejected before history, audio or edits are served.

The Studio panel lets the user explicitly request preparation, listen to the
audio, inspect scene timings, acknowledge them and apply them. It uses literal
text rendering and exact scoped audio paths. Stale, dirty, busy, archived,
read-only and source-footage projects cannot apply changes. An uncertain
preparation response retains the exact request key for a manual retry; it
never automatically resubmits. A late response cannot restore another
project's results.

## Canonical timing apply

POST `/api/projects/{id}/narration/{job}/apply` requires edit permission, CSRF,
current revision, exact plan SHA and explicit acknowledgement. The source
document and brand must still match and use a fit-narration template. One
SQLite FULL transaction updates the same canonical shot snapshot and derived
projections, records the measured durations and original audio reference,
increments the version/revision, and clears approval. No provider call or
automatic render occurs. The original voice bytes and source approval remain
unchanged.

Duplicating a project retains origin evidence but removes prepared-narration
authority. A different project cannot read or apply another project's job.
Changed narration, scene ordering/identity, enabled narration, voice policy or
production policy invalidate voice reuse. Visual-only edits may reuse the same
voice inputs, but a measured timing plan still requires its exact original
document before application.

## Final audio reuse

After the user approves the edited document, rendering verifies the original
successful narration job, its approved snapshot, both checkpoints, plan and
current voice fingerprint. It copies the original WAV, metadata and TTS plan
into a new final-job checkpoint and records `voice-reuse.json`, including
source snapshot/plan/audio hashes and zero new inference calls. The existing
voice publisher verifies narration, profile and policy binding. Render
checkpoints include this reuse receipt. Changed bytes fail before inference
or successful rendering.

Scene timestamp mapping now uses the exact 48 kHz sample indices used for
PCM placement. This fixes tiny float boundary inversions without stretching,
resampling or changing the original voice samples.

## Evidence and remaining work

Eight core cases and four real HTTP cases cover measurement, replay, approval,
shared canonical apply, stale/hash/content rejection, scope, duplication,
corruption, CSRF, RBAC and inference-free final rendering. Six UI cases cover
scoped evidence, literal text, acknowledgement, role/state guards, uncertain
response handling and late response rejection.

The isolated worker rehearsal uses a technology channel, 51 actual human HTTP
requests, actual ingestion, MediaPlan/canonical application, preparation,
explicit timing apply/reapproval, final FFmpeg/full QC, frozen-video failure,
and actual backup/restore plus exact separate-process replay. Its audio is
explicitly cached synthetic PCM; no model inference, paid operation, semantic
Vision, genuine speech quality, browser usability or Owner UAT is inferred.

The current visual preview remains a silent proxy. Listening to the separate
audio and inspecting measured timings does not complete the required combined
audible preview/final approval flow. That integration is next, followed by the
remaining original Mode A/B, Trend Radar, publishing, analytics, learning,
Agent Hub, hardening and final acceptance work. Provider-neutral languages and
voice styles remain partial. This increment does not certify North Star
completion or production deployment.

See `north-star/native-narration-preparation-evidence.json` and
`NORTH_STAR_WAVE_REPORTS.md` for final tests, source hashes and recovery evidence.
