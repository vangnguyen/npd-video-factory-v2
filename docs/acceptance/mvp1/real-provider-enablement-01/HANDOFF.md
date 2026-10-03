# VF-MVP1-REAL-PROVIDER-ENABLEMENT-01

SOURCE CANDIDATE ONLY. No real-provider or human-quality acceptance, dispatch,
deployment or production authority is created by these changes.

## Source and dependency

Repository: `vangnguyen/npd-video-factory-v2`.
Provider branch: `codex/vf-mvp1-real-provider-enablement-01`.
Parent/integration candidate: `57f6e507f9cc3d26f6db61da41012eafdb7936ba`.
Observed main: `fa81c59fbe6b745cba8fed979e30e52a13199afa`.
PR #108 is still OPEN / DRAFT / unmerged, with that exact parent head and no
auto-merge. Its original worktree is clean. This branch depends on #108; main
does NOT yet contain the nine integration commits. No reset/cherry-pick,
historical evidence modification, RC creation or PR #108 mutation.

## Lane inventory and actual readiness

| Capability | Real adapter | Config | Zero-call readiness | Authority needed | Code remaining | Next executable action |
| --- | --- | --- | --- | --- | --- | --- |
| Content generation | IMPLEMENTED: `ResponsesStoryboardContentProvider`, transport-mock tested through existing jobs, versions, diff, apply, usage and cost stores | REAL_ADAPTER_PRESENT_NOT_CONFIGURED: model and current token prices deliberately blank/zero; default `contract`, external execution false | Schema/transport/job tests PASS; metadata denies absent/wrong scope before key callback. FULL PREFLIGHT NOT_RUN | A separate content input/rights/model/budget/window decision and exact capability credential admission; NOT ASR approvals | Existing verified gate loader only supports Vision/ASR. A content-specific sealed scope loader and protected resolver injection into API/worker remain to be implemented/reviewed, without broadening historical gates | Agree an exact content model/profile and bounded input fixture with Owner; add only the missing content scope/resolver admission, then zero-call validation before separately approved one real proposal run |
| Vietnamese TTS | IMPLEMENTED: existing OpenAI WAV adapter plus new `GovernedVietnameseTTSProvider`, decoded duration and raw-audio/profile/request evidence | REAL_ADAPTER_PRESENT_NOT_CONFIGURED: production model/voice ID blank; historical `gpt-4o-mini-tts` / `marin` are not an Owner voice selection; external audio disabled | Actual WAV decoding and synthetic transport PASS. Profile/input/voice digest and durable admission guard tested. FULL PREFLIGHT NOT_RUN | TTS-specific voice/privacy/rights/cost/window authority, protected credential binding and approved narration units; not content or ASR authority | Production worker needs a verified TTS scope/approved-unit loader and resolver injection. Forced-aligner adapter is absent; required if measured word highlighting is chosen, not for honestly labelled estimated segment captions | Owner selects a Vietnamese candidate voice/model and review utterances; wire their hashed narration-unit admission, zero-call preflight, then a separately bounded real voice sample and human pronunciation/quality review |
| Spoken/mixed-audio ASR | IMPLEMENTED: dedicated `AssemblyAITranscriptionProvider`, static factory, immutable profile, native positive-duration words, async identity and normalization | Historical RC28 profile present; installed host credential mount/load NOT_VERIFIED. Prior run 36998080744 / CREDENTIAL_UNAVAILABLE and spent context are Owner handoff facts, not fresh host attestation | Exact source mapping reproduction and candidate drop-in metadata PASS; live credential-load validation NOT_RUN | Separate Owner host mapping/custody validation, then fresh one-shot context/window and exact Op1 decision; expired/spent context is unusable | Source resolver selects the AssemblyAI ID correctly; source unit mounts only OpenAI. New source-only override resets the old mount and mounts exactly AssemblyAI. No ASR adapter rewrite identified | Obtain narrowly scoped Owner permission to inspect/install the exact mapping candidate and protected zero-provider-call backend/load validation; only after that prepare a fresh context, never use Op1 as a credential-config test |

All three lanes remain independent. Unconfigured TTS now becomes a blocked
synthesis adapter rather than aborting shared-worker construction. Neither
content nor TTS substitutes the historical ASR key for its new capability alias.
`CONFIG_AND_SCOPE_PRESENT` is only adapter metadata; it is NOT durable
preflight, credential readiness, authorization or acceptance. Durable preflight
reserves funds and was not invoked as a readiness check.

## Implemented content path

- Existing `StoryboardContentProvider` service seam, static concrete factory,
  registry/config and Studio controls; no second API, database or renderer.
- Explicit generation job, pinned input/project-version/profile digest and
  operation identity. Save/Refresh does not generate. Free prompt needs no
  `lời đọc:` label. Model, response ID, request/raw-response hashes, usage and
  modelled token cost follow the proposal. Actual billing remains UNKNOWN.
- Structured Responses request, no tools, no URL/file/command execution,
  no redirects or environment-proxy transport, no retry/fallback. Exact model
  identity, refusal/incomplete/invalid result, usage and protected-name checks.
- Model text is an unapproved proposal. All model facts are unverified; diff
  and explicit user Apply are required. Supplied facts are not independent
  evidence. User edits/cancellation win; duplicate delivery and interrupted
  claimed jobs cannot automatically invoke a second provider call.
- Existing deterministic direct-script and fixture generation paths retained.
  Fixtures are not real AI. Input bounds can reject an oversized proposal;
  there is no silent truncation or repair to make it fit.

## TTS evidence and limitations

- Strict provider-neutral profile binds provider/model/voice, vi-VN, speed,
  style and alignment capability. Human-quality acceptance is always false
  in source evidence. Owner production model/voice are not auto-selected.
- Exact returned WAV is decoded; sample payload, not narration character
  count, determines actual audio duration. Preserve request/text/audio/profile
  hashes, latency, usage availability and billing UNKNOWN. Provider credit
  debit and cash spend are separate nullable fields, never fabricated zeros.
- Production renders persist each provider source WAV separately through the
  existing object store. Mixed/normalized/trimmed audio is a different identity.
  Source timing cannot silently become timeline timing after those transforms.
- WAV speech candidate currently has `alignment_capability=none` and native
  timing source `NONE`. Caption scheduling remains explicitly
  `estimated_editorial_segment_schedule_NOT_word_alignment`, with empty words.
  Measured/provider and forced alignment schemas reject nonpositive,
  overlapping, out-of-audio or incomplete token sequences. Forced alignment
  requires a named aligner and exact source audio/text identity; no aligner is
  implemented or claimed here. Word highlighting stays blocked without it.
- Existing semantic-unit synthesis, duration reflow, subtitle/timeline review,
  stale approval invalidation and final QC are reused. A renderer failure does
  not prove an external call was free: durable paid-operation accounting is
  separate from the render-summary row, whose actual cost stays UNKNOWN.
- eSpeak/PCM fixtures remain dev-only. No professional/natural Vietnamese
  voice, pronunciation, sync or human acceptance is inferred from them.

## ASR source mapping finding

`provider_credentials.py` and the resolver's credential loader already select
`assemblyai-stt-video-factory-benchmark` for the exact AssemblyAI alias.
`deploy/executor/npd-vf-secret-resolver.service` instead has only the historical
OpenAI encrypted mount. The new candidate is:

`deploy/executor/assemblyai-secret-resolver.service.d/20-provider-credential.conf`.

It resets `LoadCredentialEncrypted` and mounts only the exact AssemblyAI source.
The original OpenAI unit is unchanged and still validates separately. The pure
metadata checker reads unit text, NOT encrypted credential bytes. Cross-provider
alias/ID/source and arbitrary/plaintext mounts fail. This is NOT a deployed
host fix or evidence of a successful live credential load.

No RC28/systemd/spent-marker/authority/window/runtime file was accessed or
mutated. No spoken-video ASR success was synthesized. T01 and audio-bearing
T07 remain fail-closed pending real authorized ASR.

## Acceptance sequence, per lane

One adapter/profile/config check → zero-call admission → one separately
bounded real run → lane quality review → repeat/consecutive run only where
the existing acceptance contract requires it. Do not manufacture extra RCs,
reuse RC28 authority or issue a joint content/TTS/ASR gate. New executable
bytes need their own eventual source review; this task creates no production RC.

Failures distinguish CONFIG, AUTH, QUOTA, TRANSPORT, MAPPING and QUALITY.
The historical ASR credential mount failure is MAPPING/config admission, not
an ASR quality failure or justification for another unvalidated Op1 call.

## MVP evidence state

MI-01/MI-03 saved multi-input, media/timeline validation and direct-script
behavior remain regression covered. MI-02 now has a real executable transport
candidate, not a real generated acceptance result. MI-04 gains governed audio
and honest timing evidence, not an accepted production voice.

T02/T03/T06/T07-silent/T08 retain dev/fixture status. T04/T05 remain
REAL_PROVIDER_NOT_TESTED. T01/T07-spoken remain ASR-blocked. No new UI E2E,
real-provider E2E, MP4 proof or human acceptance is claimed in this task.
Old integration videos/evidence retain their original commit identity.

The PR #108 exact-head CI is historical baseline evidence only. It does not
cover this provider branch. Current branch PR/CI and actual local test commands,
counts, skips, commit and checksums are recorded in the task's external closeout
receipt after tests complete. Overlapping targeted/full suites must not be added
as unique tests. No schema migration is required for the new JSON job/provenance
fields; historical fixture requests retain their defaults and validation.

Final local source regression: EXIT 0, 1782 passed / 4 skipped in 435.14 s.
Targeted provider contracts: EXIT 0, 54 passed (46 new cases + 8 existing).
Studio: EXIT 0, 17 passed. Supplemental non-root DAC node: EXIT 0, 1 passed.
The four full-suite skips are that same DAC node (separately exercised non-root)
and three PostgreSQL-only concurrency cases NOT_RUN in this task. These counts
are overlapping, not additive. Historical evidence replay and syntax/compile/
diff checks PASS. Remote CI, renderer/Docker E2E and human/provider acceptance
for this provider branch are NOT_RUN; do not substitute #108's older evidence.

## Guardrails and counters

Task real provider API calls 0; real credential resolutions/reads 0; real
reservations/spend 0 VND; production writes 0. Synthetic key callbacks and
MockTransport requests occur only in labelled tests, not provider execution.
Source/docs GitHub and official documentation network reads are nonzero.
No host/DB live-state or lifetime-counter attestation was obtained.

No merge, deploy, publish, external TTS smoke, TLS probe, ASR retry, RC creation,
execution catalog, runtime role activation, secret rotation or acceptance grant.

Wire-contract references used for source implementation, not pricing or
human-quality claims:
[Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[Text to speech](https://developers.openai.com/api/docs/guides/text-to-speech).
The platform-key skill influenced the secret-free injectable tests and refusal
to provision credentials; user zero-call instructions took precedence over
credential onboarding. No key was inspected or created.
