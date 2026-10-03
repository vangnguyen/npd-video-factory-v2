# Canonical handoff — multi-input continuation (source/dev only)

TASK: `VF-MVP1-MULTI-INPUT-IMPLEMENT-02`
VERDICT: `MULTI_INPUT_DEV_CANDIDATE / REAL_PROVIDER_AND_HUMAN_ACCEPTANCE_OPEN`
REPO: `vangnguyen/npd-video-factory-v2`
BRANCH: `codex/vf-mvp1-multi-input-01`
CONTINUED FROM: `3f4c1953526b77f1a202ffcbe0607cb3708b887e`
FETCHED MAIN: `fa81c59fbe6b745cba8fed979e30e52a13199afa`

This is an additive continuation of the existing platform. Task-01 proofs and
sealed RC28 executable/evidence are historical, not replaced by this candidate.
The final local receipt records the exact tested commit, new UI proof paths,
archive SHA and actual PR/CI state without a self-referential commit hash here.

## Changed contracts

- Save/Refresh never generates an idea/prompt proposal. Instructions-only input
  stays input, not narration. A separate explicit action queues a version-bound
  job, displays its status, proposal/diff and permits explicit application as an
  unapproved new draft. The direct-script path remains deterministic.
- Reuses jobs/events, project versions, provider registry, cost records and the
  existing worker. Default `CONTENT_GENERATION_PROVIDER=contract` fails closed
  with `CONTENT_PROVIDER_NOT_CONFIGURED`. The only executable adapter in this
  task is the explicitly selected, zero-cost offline fixture. It is not AI,
  real-provider acceptance, a production voice, or factual verification.
- Generation input facts remain unverified. Arbitrary instructions, URLs and
  supposed property facts are not executed or copied into fixture narration.
- Long narration is split at whole-word/sentence boundaries with exact source
  offsets, <=180 characters per scene, preserving source text/token order.
  Existing 40-scene/180-second limits fail explicitly, never truncate. Suggested
  scene durations are planning estimates, not measured speech timestamps.
- Synthetic tests exercise actor/workspace scoping, duplicate delivery, CAS,
  cancellation, restart ambiguity and edits during in-flight render. Completion
  cannot resurrect stale approval/final state. These tests use SQLite; they do
  not establish PostgreSQL locking/concurrency acceptance.
- Audio records actual provider/voice/rate, decoded PCM duration, any speed-up,
  exact source text SHA and editorial placement. It does not fabricate word
  alignment. Trimming removes digital-zero padding, not quiet non-zero phonemes.

## API on the existing project lifecycle

All routes retain authenticated human/workspace authorization. Editors create,
cancel and apply; viewers may inspect. The trusted actor is the authenticated
principal, not a caller-supplied `actor_ref`.

| Route under `/api/v1/projects/{project_id}` | Meaning |
| --- | --- |
| `GET /content-provider` | `FIXTURE_ONLY` or exact not-configured blocker |
| `GET /content-generation` | Latest durable proposal job (read only) |
| `POST /content-generation` | Explicit saved version + idempotency key, HTTP202 |
| `GET /content-generation/{job_id}` | Project-scoped status/proposal/diff |
| `POST /content-generation/{job_id}/cancel` | Cancellation, never automatic regeneration |
| `POST /content-generation/{job_id}/apply` | CAS application to a new unapproved content version |

Queued jobs recover through the existing worker. Claimed jobs interrupted at
restart fail `GENERATION_OBSERVATION_UNCERTAIN`, not a second provider attempt.
A proposal completed after a saved edit remains visible as stale evidence and
cannot overwrite the edit. Save does not approve an external generation result.
No schema migration is needed beyond task-01's existing migration0016.

## MI / T status and acceptance boundaries

| Work item | Implemented / deterministically tested | Still missing |
| --- | --- | --- |
| MI-01 | Existing durable image/video/text upload and versions retained | Production storage/malware/deployment qualification |
| MI-02 | Explicit proposal workflow, registry blocker, source-preserving splitting, version/diff, user apply/approval | Authorized creative generation/model, real quality/input acceptance |
| MI-03 | Existing storyboard/mixed timeline, image timing/fit, explicit media capability choices retained | Real requested AI media providers; no slideshow substitution |
| MI-04 | Existing A/V review/final/QC, stronger audio provenance and stale in-flight regression | Professional Vietnamese voice, trustworthy word alignment and human full watch/listen |

| Case | Development expectation / test | Real provider / production / human |
| --- | --- | --- |
| T01 speech video | Guarded ASR unavailable; no fabricated analysis/transcript | BLOCKED / NOT_RUN / NOT_ACCEPTED |
| T02 ordinary image | Existing image-only montage + explicit caption path retained | External TTS NOT_RUN / NOT_RUN / NOT_ACCEPTED |
| T03 architecture + script | Existing synthetic illustrative architecture, not official rendering | External TTS NOT_RUN / NOT_RUN / NOT_ACCEPTED |
| T04 idea only | Explicit offline proposal/apply path; no video required | PARTIAL: creative AI not configured / NOT_RUN / NOT_ACCEPTED |
| T05 free prompt | No narration label required for explicit offline proposal | PARTIAL: creative AI not configured / NOT_RUN / NOT_ACCEPTED |
| T06 script | Source-preserving short/long scene planning | External TTS NOT_RUN / NOT_RUN / NOT_ACCEPTED |
| T07 mixed | No-audio video path retained; audio-bearing video remains blocked even if mute is selected | Real ASR/TTS not tested / NOT_RUN / NOT_ACCEPTED |
| T08 edit after approval | In-flight edit cannot restore ready; re-review/re-approval/rerender path retained | NOT_RUN / NOT_RUN / NOT_ACCEPTED |

## Reproduction and evidence

Final results are in the fresh local root:
`C:/Users/PC/Documents/Codex/2026-09-28/ti-p-t-c-vf-executor/work/vf-mvp1-proof-20261003-02`.
The localhost harness uses existing API/Studio/production renderer with isolated
SQLite/object storage and a synthetic dev session. Its outbound socket guard
allows only loopback. No executor/systemd/ASR authority is used.

Run `scripts/mvp1-dev-server.py` with a fresh local `--root`, existing local
`--tools` and loopback renderer. Generate first-party fixtures with
`scripts/mvp1-dev-fixtures.py`. `scripts/mvp1-ui-proof.mjs` operates the Studio
with local Playwright and requires clean committed source. Cases include
image-script/T08, mixed silent video, image-only, script, script-long, idea,
prompt, mixed-audio-blocked and spoken-blocked. Successful render reports must
have actual QC and real MP4. `scripts/mvp1-review-package.py` verifies the commit,
full decode, codecs/size, audio cue bounds and shareable input rights before
making a new local ZIP. No media is committed to the public repository.

PR creation previously returned connector403; do not loop/retry that integration.
An unsubmitted browser form is not a PR. Required browser confirmation and CI
dispatch permission remain separate. PR merge SHA is not an exact branch-head
test. Local tests are not a GitHub PASS5/5 or Docker/PostgreSQL E2E claim.

## Boundary receipt

Task external-provider calls/credential reads/uploads/jobs/reservations/spend:
`0 / 0 / 0 / 0 / 0 VND / 0 VND` in isolated dev only.
Production writes, merge/deploy/publish/new RC: `NONE`.
ASR spent context, RC28 authority/evidence, systemd/runtime: `UNTOUCHED`.
Host-lifetime ASR/runtime/ledger counters: `NOT_VERIFIED`, not zero.
Source/tool/GitHub network: separate from provider network, not claimed zero.
Op2 remains `LOCKED / NOT_AUTHORIZED`; no authority transfer to this branch.
MVP-1 acceptance: `OPEN` — no human/professional voice/production evidence.
NEXT_SAFE_ACTION: review the exact source and new local video package, then
choose separate real-provider/real-input acceptance authority. Not executed.
