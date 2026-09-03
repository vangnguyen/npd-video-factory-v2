# V3-01 Vision closure and ASR real-provider gate design

## Checkpoint

```text
G-08 PR #39: CONSUMED
PR #39 MERGE: fd0db431d2e3786b6b07dcb4b47b7bc74cfa7aed
EXACT-MAIN CI: 33703619599 / COMPLETED / SUCCESS / 5 OF 5 JOBS
EXECUTABLE RC: vf-v3-01-rc10 / c2b1aec2d54dd90bcb486f8a68c97746b39963aa
EXECUTABLE TREE: UNCHANGED
VISION REAL-PROVIDER-TESTED: PASS / 2 OF 2 CONSECUTIVE OPERATIONS
FURTHER STANDALONE VISION OPERATION: RETIRED / NOT AUTHORIZED
ASR REAL-PROVIDER-TESTED: NOT_TESTED
ASR RUNTIME AUTHORITY: NONE
PRODUCTION: NO-GO
```

The owner-approved RC-10 consecutive evidence PR merged as PR #39. Exact-main CI passed all five
jobs, the dual-CI provenance collector returned `PASS`, and the executable-tree SHA-256 remained
`f1f75f632ca3b1380985c5a532c9f4c601e39d45276135666f335cc3d041125c` on both immutable RC-10 and
post-merge governance `main`.

The Operation 1 source receipt remains SHA-256
`11fd1f7cb8eca120964033aba098e051d2d380713c52ceffec02979a77c9a620`; the Operation 2 source receipt
remains SHA-256 `deed47e573079bd53118859f616991aae42b420992aad84f39cbfb4bdb3df0a2`.
Both operations are consumed/succeeded. Their common request hash and distinct response hashes are
retained as separate evidence. No Operation 3 is needed or authorized. The source consecutive-run
snapshot in [42_V3_01_RC10_VISION_CONSECUTIVE_EVIDENCE.md](42_V3_01_RC10_VISION_CONSECUTIVE_EVIDENCE.md)
is preserved rather than rewritten.

This closes only `VIS-01` on the real-provider-tested axis. Production-path-tested and
quality-accepted remain `NOT_TESTED`, and the repository-wide verdict remains `NO-GO`.

## Current ASR boundary

Repository inspection on exact governance `main` shows:

- `TRANSCRIPTION_PROVIDER` accepts only `fixture` or `contract`;
- `DeterministicTranscriptionProvider` is the only working transcription implementation;
- `ContractOnlyTranscriptionProvider` fails closed;
- `AutoEditAnalysisService` already routes transcription through `ProviderSafetyController`;
- the domain contract already requires segments and words with timestamps, confidence and
  provenance;
- no live ASR adapter, real ASR receipt or real-media ASR accuracy evidence exists.

Therefore `ASR-01` remains `NOT_TESTED` on the real-provider axis and `V3-01-GAP-003` remains
`IN_PROGRESS`. A live call is not the next safe action; the missing executable adapter and its
offline contract tests must be remediated first.

## Provider/model recommendation for the first ASR acceptance

The current OpenAI file-transcription guide recommends `gpt-transcribe` for ordinary recorded
speech, but the documented `timestamp_granularities[]` option for word/segment timestamps is
currently supported only by `whisper-1`. Flow A requires word timing for transcript evidence,
speech-safe edit decisions and subtitle-drift measurement. For that reason, the proposed first
strict-contract candidate is:

```text
provider: openai-transcription
model: whisper-1
capability: asr
response format: verbose_json
timestamp granularities: word, segment
language: vi
```

This is a design recommendation, not G-01 approval. The official `whisper-1` model page lists a
dated reference price of USD 0.006 per minute as of 2026-09-03. Price and availability must be
refreshed when G-02 is proposed; no VND budget is inferred here. A future quality-first move to
`gpt-transcribe` requires a separately reviewed deterministic alignment layer if the API still does
not expose the timing contract needed by Flow A.

Official references, checked 2026-09-03:

- [Speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text)
- [Whisper model](https://developers.openai.com/api/docs/models/whisper-1)
- [GPT Transcribe model](https://developers.openai.com/api/docs/models/gpt-transcribe)

## Proposed V3-01-18 — OpenAI timestamped ASR adapter

V3-01-18 should be a source-only, zero-call remediation. The intended execution path is:

```text
AutoEditAnalysisService
  -> ProviderSafetyController
  -> OpenAITranscriptionProvider
  -> approved OpenAI transcription endpoint
  -> canonical ProviderTranscript
  -> durable evidence and cost ledger
```

Business logic must not call an SDK or HTTP endpoint directly. The adapter must preserve the
existing fail-closed safety plane and map provider output into the canonical `ProviderTranscript`,
`ProviderSegment` and `ProviderWord` contracts.

Required source contract:

- exact provider/model/capability and credential alias metadata, with no credential value in Git or
  evidence;
- exact source-asset and RightsRecord hashes before dispatch;
- canonical request hash and response hash;
- provider request ID when returned, redacted error metadata and phase-aware timeout evidence;
- language, transcript text, segment and word timing, confidence and provenance;
- monotonic, non-overlapping timing inside media duration;
- provider-native usage or duration fields and an actual VND cost receipt; missing cost evidence
  must remain unknown and fail acceptance rather than be invented;
- atomic reservation, durable operation/attempt/circuit rows and duplicate-operation protection;
- one attempt, concurrency one, no automatic retry and no fallback;
- canonical JSON serialization, evidence checksum and secret-containment scan.

Required offline tests:

- recorded/mock success with Vietnamese Unicode, segments, words and nullable speaker/confidence
  fields;
- malformed JSON, missing words, missing segments, empty transcript and wrong language;
- non-monotonic, overlapping, negative or out-of-duration timestamps;
- provider non-2xx, refusal/incomplete response, connect/read/controller timeout and missing request
  ID;
- missing/invalid usage or cost receipt;
- missing credential alias, rights failure, budget failure, expired gate and kill switch;
- duplicate operation, concurrent lease and restart/recovery behavior;
- deterministic request/response/evidence hashes and zero secret-pattern matches;
- proof that tests perform zero provider calls, zero credential reads and zero VND spend.

## Future bounded acceptance design

The current Flow A evaluator requires two consecutive runs on two distinct source hashes. Before a
live ASR operation can be proposed, the owner must separately approve:

1. **G-08** for the V3-01-18 source-only adapter PR after exact-head CI.
2. Merge, exact-main full regression and a new locked RC because executable code changes.
3. **G-01-ASR** for exactly one provider, one model, capability `asr` and one credential alias.
4. **G-02-ASR** for an ASR-specific duration, file-size, timeout and VND envelope. It must use a
   fresh price and exchange-rate snapshot; the Vision 500/1,250 VND authority is not reusable.
5. **G-03-ASR** for exactly two owned/authorized Vietnamese media inputs, each at least 90 seconds,
   each with a RightsRecord, a human-verified reference transcript and an explicit critical-term
   list.
6. Separate immutable operation IDs, dated windows and owner authority for Operation 1 and then
   Operation 2 only after review of Operation 1 evidence.

Each accepted run must satisfy the existing Flow A thresholds: WER at most `0.15`, critical-term
accuracy `1.0`, and complete timing/provider/usage/cost/rights/ledger/secret evidence. Passing ASR
alone does not promote scene detection, reframe, TTS, subtitle/audio, production-path or
human-quality axes.

## Current authority

This checkpoint performs zero provider calls, zero credential reads, zero reservation and zero VND
spend. It changes no executable/runtime file and does not create RC-11. External execution, paid
execution and production writes remain disabled; the global kill switch remains engaged. No deploy,
public ingress, publishing, production analytics or new provider authority is granted.

The next owner action is G-08 review of this Vision-closure/ASR-design PR. After that merge, the next
technical checkpoint is the separately reviewed V3-01-18 zero-call adapter implementation.
