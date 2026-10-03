# Provider admission remote closeout and Owner selection candidates

Task: `VF-MVP1-REAL-PROVIDER-ADMISSION-02-REMOTE-CI-CLOSEOUT`.
Source only; no final model/voice approval, provider execution or MVP1 acceptance.

## Reviewed baseline and ancestry

Draft stacked PR [#109](https://github.com/vangnguyen/npd-video-factory-v2/pull/109)
depends on unmerged #108. Base is `codex/vf-mvp1-multi-input-01` at
`57f6e507f9cc3d26f6db61da41012eafdb7936ba`, NOT main.
Baseline head `3b0db4adf1ba826a705b7c06b6395c4f8368826b` passed exact-head
workflow_dispatch [37126374315](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/37126374315):
Python, renderer, Studio, safety/compose and Docker deterministic E2E, 5/5.
Python: 1826 passed / 3 PostgreSQL-only skips; separate PostgreSQL step 67
passed (overlapping suites, not added). Migration up/down/up passed.
Docker included PostgreSQL, Redis, MinIO, API, worker, Studio, renderer,
version-bound preview/final QC, worker restart and disposable DR/queue recovery.
Its artifact ID is 11275171792, ZIP digest
`256e78d0849f8ddcf5e5ee0c1e7728e6e362adec6065ac65457acf554ebe9418`.

The changes below are AFTER that baseline CI. That run is NOT evidence for
this commit. Final new head and fresh exact-head CI belong to the external
closeout receipt, avoiding a documentation commit that would move the head.
No PR merge-SHA run is substituted for branch-head evidence.

## Content: explicit reasoning profile v2

`ContentProviderProfile` v2 binds reasoning effort in the canonical SHA;
Settings/factory/verified scope compare that exact profile. Candidate selection
is Responses / gpt-6-luna / none. The payload sends `reasoning.effort` explicitly.
The parser locates the single structured assistant message independently of
reasoning-item position. Reasoning metadata is not narration. Tools, refusal,
multiple messages/texts, malformed/incomplete items and draft extras fail closed.
Legacy v1 profile hashes/payloads remain unchanged when reasoning is absent.
The existing proposal/diff/apply, immutable versions and human approval remain.

The selector JSON is NOT an executable profile or approval. No live token rates,
budget or bounded input set was chosen here, so its full content profile SHA is
not finalized. Synthetic profiles bind concrete reasoning/rates/digests in tests;
their prices, rights and scope identifiers are NOT Owner decisions. Changing
reasoning necessarily changes the profile/request and operation identity.

## TTS: separate Realtime migration adapter candidate

`RealtimeVietnameseTTSMigrationCandidate` retains the existing TTSProvider:
text -> PCM event stream -> fresh persisted WAV -> decoded sample duration ->
TTSArtifactEvidence -> existing audio mixer/timeline/review contract.
`WebSocketRealtimeExchange` has a fixed official URI/model, no ambient key lookup,
no proxy, no reconnect/retry, waits for verified session.updated before one
response.create and closes on terminal/error/cancellation. It is NOT registered
or constructed by live Settings/API/worker. A future protected backend may
instantiate it ONLY within independently verified durable authority/budget and
one-shot secret resolution. No live key was handed to it in this task.

Profile v2 separately binds Realtime API, model, one of two candidate voices,
Vietnamese locale, PCM format/rate, style, output ceiling, audio limit and timeout.
It does not inherit the historical audio/speech model, request format/speed or
character-priced budget. Historical v1 profiles/evidence remain loadable.
The existing v1 character-priced TTS scope explicitly REJECTS v2 Realtime profiles.
Before live admission, code must extend the verified scope/controller cost model
for Realtime text/audio input/output token rates and bind the protected resolver
backend and render units. This is CODE_REMAINING, not merely “missing API key”.

Audio deltas, transcript and terminal response/job identity must agree. Missing
PCM/completion/usage, changed narration, tools/refusal, duplicate/foreign response,
audio limits or cancellation fail closed; a second attempt is forbidden. Output
publication never replaces a late-created asset. Token usage is provider-reported
metadata, not a price, credit debit or actual billed spend.

Measured duration is decoded PCM samples only. Timing source is NONE, no words.
Provider transcript events contain no word alignment: WORD_ALIGNMENT_OPEN.
Synthetic PCM is not speech, professional Vietnamese voice or human audition.
marin/cedar are NOT selected final voices; names, pronunciation, sentence rhythm,
missing/repeated words and A/V/subtitles require bounded real output and human review.

## Current lane status

| Lane | Source/config candidate | Live blockers | Next smallest action |
|---|---|---|---|
| Content | Reasoning compatibility + public version-bound admission tested | Owner selection/input/budget; protected resolver/runtime qualification; separate execution authority | Owner confirm gpt-6-luna/none and exact bounded inputs/rates/budget |
| TTS | Realtime request/WebSocket/event/audio codec candidate tested | Token-budget scope/controller implementation; protected resolver admission; Owner voice/model/input/budget and audition; WORD_ALIGNMENT_OPEN | Review two voice profiles and approve scope of token-budget admission extension; no live call |
| ASR | Existing adapter; additive systemd mapping package only | HOST_REMEDIATION_REQUIRED and separate protected zero-call load validation/fresh authority | Separate Owner host-remediation decision; do not retry spent RC28 context |

PR #108, sealed RC28 source/evidence/authority and spent markers are unchanged.
No host mapping install, service mutation, authority/window/reservation, production
write, merge, deployment, publication or RC. Task real-provider calls/credential
reads/spend are zero; GitHub/docs networking is nonzero. Host lifetime counters
are NOT_VERIFIED. Fixture tests never grant live authority or quality acceptance.

## Primary documentation checked 2026-10-03

- [gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna): Responses/structured outputs and none reasoning support.
- [gpt-realtime-2.1-mini](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini): Realtime transport/model candidate.
- [Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations): request/event lifecycle, PCM, VAD off, out-of-band input; marin/cedar recommendation is not Vietnamese acceptance.
- [WebSocket connection](https://developers.openai.com/api/docs/guides/realtime-websocket): fixed server-side transport.
- [Realtime server event reference](https://platform.openai.com/docs/api-reference/realtime-server-events/response/output_audio_transcript/done): output_audio content and token usage details (search-readable reference; full page exceeds browser extraction limit).
- [Deprecations](https://developers.openai.com/api/docs/deprecations): old audio/speech production model is not selected anew.
