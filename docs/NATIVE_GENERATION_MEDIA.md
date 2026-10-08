# Native generated-media staging

`NativeGenerationMedia` accepts only a trusted worker's job-bound registered
binary result. A fenced running claim, exact successful provider observation,
workspace/ticket/request/input binding, protected workflow fingerprint, model,
graph, reference hashes and typed bridge provenance are required. Metadata-only
results, foreign scopes, fixture promotion, changed inputs and rights promotion
fail. This module calls no provider and exposes no client result-submission API.

Actual bytes pass existing Native MIME/magic checks, PIL image decoding or
FFprobe plus full FFmpeg video decoding. Video dimensions, duration, frame rate
and audio presence must agree with the registered result. Existing image limits,
including the 240-pixel minimum on both sides, remain enforced. Original bytes,
normalized media and thumbnail are retained with hashes. Images normalize to
JPEG; original alpha remains in the preserved original, and alpha-aware logo/
mask editing is still a separate gap.

An additive immutable SQLite receipt binds the frozen workflow definition,
actual source/input/output hashes and registered metadata to the Native asset.
Reads validate semantics and actual original/normalized/thumbnail bytes; an
exact replay returns the same asset. Expired workers and conflicting replays
fail. Failed intake removes only its own newly created temporary/media files.
Unknown rights, attention and ineligibility remain explicit. Actual cost stays
null. The project, approval and canonical timeline remain unchanged.

This prerequisite does **not** settle a generation job as successful, start an
executing worker, attach the asset or expose HTTP/Assets controls. Those consumer
steps remain next. Rehearsal claims end honestly in `recovery_required`, with
the staged assets preserved. Default factory configuration remains inactive.

Seven new cases cover actual local PNG/MP4 intake, immutable replay/conflicts,
scope/provenance/rights rejection, fencing, malformed/small images, physical
corruption and rehashed semantic tampering. Final affected Native media/queue/
registry/reference/cost tests pass 56 cases. Earlier iterations retained two
failures: fixture model mismatch and an incorrect source-snapshot key; both were
corrected without weakening validation. The initial 35-case count included 14
queue cases twice through a test helper import; the final 56 count has no such
duplicate discovery.

`scripts/north_star_native_generation_media.py` produces actual synthetic
640x360 PNG and 0.6-second MP4 pixels, stages two assets, verifies exact replay,
and exports 12 files under external recovery `native-generation-media-n1`.
A separate process reopens with no configured factory and verifies exact
projects, versions, jobs, events, cost intents and staged receipts, including
physical hashes. No network request occurs. Bridge metadata and observations
are explicit mocks; these are local media/persistence tests, not real GPU/model
generation, legal clearance, billed outcomes, Owner UAT or deployment evidence.
