# MVP1 integration-03 — source/dev candidate, not acceptance

TASK: `VF-MVP1-MULTI-INPUT-INTEGRATION-03` (UPDATED decision only)
Repository: `vangnguyen/npd-video-factory-v2`
Branch: `codex/vf-mvp1-multi-input-01`
Continued from: `e15fb4b1350d7481ef01ab11a8c0eea5eb911cf4`
Fetched main: `fa81c59fbe6b745cba8fed979e30e52a13199afa`

R01: sentence narration is independent of visual scenes/caption cues. A measured
review permits explicit reflow into a NEW draft timeline using decoded PCM
durations. Auto scenes change; locked durations and explicit pauses remain.
No automatic TTS fitting/speedup on this path. Too-long audio/source windows fail
with an actionable error. Shared CAS, approval/final invalidation and re-review
remain mandatory. Source text/offsets are preserved; editorial cue allocation
inside a measured sentence is ESTIMATED, not measured word alignment.

R02: input-supplied protected terms and capitalized multi-word names constrain
caption boundaries. Oversize terms fail explicitly; no truncation or hidden
font shrinking. A single TTS sentence can span multiple visual scenes/cues.
New storyboard packages default to segment captions. Word highlight without
measured words is rejected on the storyboard path and disabled in Studio.
Historical video evidence/contracts remain loadable unchanged.

R03: historical explicit `fade` remains fade-through-background. Studio offers
separate `crossfade`: a contiguous predecessor stays under the incoming visual.
Source-video tails freeze the last validated frame, not read extra source time.
Boundary frames/blackdetect and actual-font/layout checks are required in the
new review evidence; no thresholds or renderer overflow guards are weakened.

Persistence: JSON authoring fields are additive; migration0016 remains the DB
contract. The isolated dev harness can use a synthetic loopback PostgreSQL DB,
never the runtime custody DB. PostgreSQL transaction-barrier tests and a
disposable PostgreSQL service step are added to the existing public dev CI.
No private/provider/deployment workflow changes. The local harness still uses
an in-process test queue/local object storage; it is not Redis/MinIO/Docker E2E.

Exact-head test results, before/after movies, signal measurements, frame images,
audio provenance, review ZIP hash, PR/CI state, MI01–04/T01–08 and dependency
matrix are in the fresh external task receipt (no self-referential head here):
`work/vf-mvp1-integration-03-20261003/` outside the repository.

Real content generation/provider selection, professional Vietnamese voice,
measured word alignment, spoken-video ASR, full production-stack E2E and human
full-watch/listen are separate open dependencies. eSpeak/fixture PASS is not
professional/real-provider/human acceptance. T01 and audio-bearing T07 must
remain blocked, even if mute is selected. Op2 remains locked.

RC28/spent context/authority/systemd/old evidence/proofs: untouched.
No merge/deploy/provider credential read/real provider request/publication/RC.
Task-local zero-use is distinct from host-lifetime state (NOT_VERIFIED).
MVP1 acceptance remains OPEN. Stop at the final report, not its next action.

## Closeout continuation from 0d03a3a (same task, not a new acceptance gate)

Renderer `/render` failures classify an allowlisted error code before structured
logging. The failure record contains only event, schema-validated job ID and
stable code; raw exception message/stack, narration, signed URL, authorization
material and local paths are excluded. `SUBTITLE_LAYOUT_OVERFLOW` retains its
actionable HTTP/UI diagnosis. Generic and non-Error failures remain failures.
Synthetic regression checks both HTTP bodies and the existing console logger;
invalid correlation IDs are rejected before engine invocation/logging.

R01/R02/R03 visual/audio behavior is unchanged by this logging-only patch.
The byte-identical prior review ZIP and its MP4s remain valid baseline evidence,
not newly rendered/accepted output. Closeout results, exact head, test commands,
skip reconciliation and updated existing dependency matrix are recorded outside
the repository under `work/vf-mvp1-integration-03-closeout-20261003/`.

Full-stack evidence is not replaced with another PostgreSQL-only run. The local
Windows/WSL environment currently lacks Docker CLI/socket; context, daemon,
Compose resources and full Redis/worker/MinIO/PostgreSQL UI lifecycle cannot be
verified here. No daemon installation, production host substitution or global
cleanup is authorized. Existing `docker-compose.yml` and `scripts/e2e-smoke.sh`
must only run in a separately verified disposable checkout/project: the harness
changes `.env` and performs project-scoped `down -v`.

Prior full-suite and real-PG results retain their original head and commands.
Targeted closeout reruns overlap that suite and must not be added as unique tests.
The root DAC skip and the three real-PG barrier cases are reported individually;
non-root proof only covers the matching DAC node, not PostgreSQL contention.

Remote PR/CI is subject to actual access and action-time browser confirmation.
A prepared form is not a PR; PR merge-event SHA is not exact branch head CI.
No old run is relabeled as current. Provider generation/model selection, voice
quality/alignment and spoken ASR authority remain the existing dependencies.
No live-provider call, credential access, RC28/spent/systemd/authority mutation,
merge, deployment, publication or new RC is permitted by this continuation.
