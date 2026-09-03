# V3-01-18 OpenAI ASR compatibility and adapter

## Checkpoint

```text
PR #40: MERGED AS 4c74fa18a86b29ae8324885dacc6fdbca74ad066
PR #40 EXACT-MAIN CI: 33706971864 / COMPLETED / SUCCESS / 5 OF 5 JOBS
EXECUTABLE TREE ACROSS PR #40: UNCHANGED
V3-01-18 SOURCE COMMIT: d2f34eb9e57d60ab6d0497ebf4a87c486cba8e63
IMPLEMENTED: PASS
MOCK-TESTED: PASS
REAL-PROVIDER-TESTED: NOT_TESTED
MODEL SELECTION: PROPOSED / NOT APPROVED
ASR RUNTIME AUTHORITY: NONE
PROVIDER CALLS: 0
CREDENTIAL READS: 0
SPEND: 0 VND
PRODUCTION: NO-GO
```

PR #40 closed the RC-10 Vision checkpoint without changing the executable tree, so no RC-11 was
created from that documentation-only merge. V3-01-18 is the next source-only remediation. It adds
an OpenAI transcription adapter and a fail-closed ASR gate contract, but it does not select a model,
grant an owner gate, read a credential, reserve a budget or call a provider.

## Offline compatibility result

The official OpenAI transcription guide, API reference and model pages were inspected on
2026-09-03. The checked-in compatibility record is machine-readable and reproducible with
`python scripts/v3_01_asr_compatibility.py`.

| Candidate | Text | Native segments | Native words | Language | Usage/duration | Request ID | Strict Flow A | Selection |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `whisper-1` | supported | supported | supported | supported | supported | supported | compatible | `PROPOSED_NOT_APPROVED` |
| `gpt-transcribe` | supported | unsupported by the inspected native timestamp contract | unsupported by the inspected native timestamp contract | unresolved | supported | supported | incompatible | `PROPOSED_NOT_APPROVED` |
| `gpt-4o-transcribe` | supported | unsupported by the inspected native timestamp contract | unsupported by the inspected native timestamp contract | unresolved | supported | supported | incompatible | `PROPOSED_NOT_APPROVED` |

The current official guide says timestamp granularities are supported for `whisper-1`. This is
capability evidence, not an owner model decision. V3-01-18 does not add a forced-alignment layer and
does not silently substitute one candidate for another. Any unresolved capability stays unresolved.

Official references, checked 2026-09-03:

- [Speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text)
- [Audio transcription API reference](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create)
- [Whisper model](https://developers.openai.com/api/docs/models/whisper-1)
- [GPT Transcribe model](https://developers.openai.com/api/docs/models/gpt-transcribe)
- [GPT-4o Transcribe model](https://developers.openai.com/api/docs/models/gpt-4o-transcribe)

Availability, response contracts and prices must be refreshed when a later G-01/G-02 proposal is
prepared. No price or budget is approved by this checkpoint.

## Implemented boundary

The executable route is now:

```text
AutoEditAnalysisService
  -> ProviderSafetyController
  -> OpenAITranscriptionProvider
  -> approved OpenAI transcription endpoint
  -> ProviderTranscript / ProviderSegment / ProviderWord
  -> durable provider-safety ledger and canonical evidence
```

The adapter and gate contract provide:

- exact provider, model, capability, credential alias and operation binding;
- source bytes, media duration, source SHA-256, file type and RightsRecord binding;
- strict one-file multipart transcription request using native segment and word timestamps;
- deterministic request-manifest and raw-response hashes;
- Vietnamese Unicode mapping with monotonic, non-overlapping timing validation;
- nullable confidence rather than fabricated confidence;
- redacted provider error metadata, request ID when available and phase-aware timeout evidence;
- duration-based VND cost calculation with missing or invalid cost evidence rejected;
- per-operation and acceptance-window budget limits, durable lease/attempt/circuit accounting and
  duplicate-operation protection through the existing safety controller;
- exactly one attempt, concurrency one, no adapter retry and no fallback;
- canonical ASR gate parsing with unknown, missing, legacy or extra fields rejected.

The default configuration remains fail closed:

```text
TRANSCRIPTION_PROVIDER=fixture
OPENAI_TRANSCRIPTION_MODEL=
OPENAI_TRANSCRIPTION_ESTIMATED_COST_VND=0
OPENAI_TRANSCRIPTION_VND_PER_MINUTE=0
PROVIDER_VERIFIED_GATE_BUNDLE_ENABLED=false
PROVIDER_EXTERNAL_EXECUTION_ENABLED=false
PROVIDER_PAID_EXECUTION_ENABLED=false
PROVIDER_GLOBAL_KILL_SWITCH_ENGAGED=true
PROVIDER_PER_OPERATION_LIMIT_VND=0
PROVIDER_DAILY_LIMIT_VND=0
```

`OpenAITranscriptionProvider` is constructed only after explicit configuration selects the OpenAI
path. Credential resolution is lazy and remains behind the verified gate and safety controller.
V3-01-18 itself performs zero credential reads and zero provider calls.

## Offline validation

Evidence `EV-V3-OPENAI-ASR-ADAPTER-001` covers the source commit and records:

- 50 focused provider/gate/config tests passing on 2026-09-03;
- 363 Python/API tests passing in the source regression;
- compatibility output for all three exact candidates;
- recorded/mock Vietnamese success mapping;
- malformed response, missing timestamp, language, usage and request-ID cases;
- non-2xx, timeout, rights, budget, expiry, duplicate and fail-closed configuration paths;
- migration `0013` upgrade/downgrade/replay;
- zero live calls, zero credential reads and zero VND.

The final exact-head CI run belongs to the draft PR and must be recorded after the branch is pushed.
Local source evidence must not be promoted to real-provider or production-path evidence.

## Acceptance impact

`ASR-01` advances from implemented `FAIL` to implemented `PASS`; mock-tested remains `PASS`.
Real-provider-tested, production-path-tested and quality-accepted remain `NOT_TESTED`.
`V3-01-GAP-003` stays `IN_PROGRESS`: the missing executable adapter is remediated locally, but no
real ASR receipt, reference-transcript score, production path or human quality acceptance exists.

Vision stays officially 2/2 consecutive real-provider PASS. V3-01-18 neither reopens Vision nor
creates any new Vision authority.

## Next owner boundary

This branch must stop at a new **G-08** review. If G-08 is granted, the safe sequence is:

```text
merge V3-01-18
-> exact-main full regression
-> lock a new executable RC
-> review compatibility evidence and select exactly one ASR model
-> separate G-01-ASR
-> separate G-02-ASR duration/file/timeout/VND envelope
-> separate G-03-ASR for two owned Vietnamese media inputs and reference transcripts
-> separate authority for ASR Operation 1
```

No G-01/G-02/G-03-ASR, live operation, deployment, public ingress, publishing or production
analytics is authorized here. The production verdict remains `NO-GO`.
