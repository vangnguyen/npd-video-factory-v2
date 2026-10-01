# GPT Transcribe canonical text + reviewed local alignment

Status: source-only prototype; Owner G-08 review required.

Task: `VF-ASR-GPT-ALIGNMENT-SOURCE-PROTOTYPE-01`

Base main: `996ccb7b6aced3e3b41bc673eef124a9a8d9b454`

The source prototype adds no provider, runtime, release-candidate, lineage, budget,
or execution authority. `GPT_ALIGNMENT_LIVE_EXECUTION_ENABLED` is fixed to
`false`, and application validation rejects attempts to enable it.

## TEXT_PROVIDER_CONTRACT

Stage A is a versioned text-only contract for provider
`openai-transcription`, model `gpt-transcribe`, capability `asr_text`.
The immutable request profile binds the model, `languages`, context `prompt`,
literal `keywords`, JSON response format, profile ID, exact profile hash, and
request-manifest hash. It forbids timestamp fields, model substitution,
automatic retry, fallback to Whisper, and unbound request fields.

The current official OpenAI file-transcription guide documents `prompt`,
`keywords`, and `languages` for `gpt-transcribe`, and says keywords are hints
whose insertion behavior must be evaluated. It also states that word/segment
timestamp workflows use `whisper-1` and that `timestamp_granularities[]` is
supported only for `whisper-1`:

- <https://developers.openai.com/api/docs/guides/speech-to-text>
- <https://developers.openai.com/api/reference/cli/resources/audio/subresources/transcriptions/methods/create>
- <https://developers.openai.com/api/docs/models/gpt-transcribe>

The prototype uses `languages: ["vi"]` as a governed request hint because the
current API contract supports ISO-639-1 language hints. It does not claim that
Vietnamese has been validated for this account or acceptance workload:
`VIETNAMESE_PROVIDER_CONTRACT = NOT_LIVE_VALIDATED`.

Stage A results contain exact UTF-8 text, transcript SHA-256, request/response
hashes, request ID, detected-language metadata when present, usage, latency,
cost, and provider provenance. Timestamp absence is valid and explicit.

## ALIGNMENT_INTERFACE

Stage B is provider-independent. Its input binds the exact audio SHA-256,
provider-text-result hash, canonical transcript SHA-256, immutable token
sequence, aligner implementation/version, model identity/hash when applicable,
configuration hash, and optional lexicon hash.

The aligner may assign timing and confidence only to the exact canonical token
sequence. Insertion, deletion, substitution, spelling repair, accent removal,
reference-answer rescue, or any other text mutation fails token coverage.

The repository includes only `DeterministicFixtureAligner`, labeled
`SYNTHETIC_OFFLINE_FIXTURE`. It performs no network access and loads no model.
It is not production evidence.

Production engine status: `ALIGNER_ENGINE_NOT_SELECTED`.

No candidate engine or model is selected or downloaded by this change. A later
decision must compare candidates on software/model licensing, redistribution,
commercial use, Vietnamese support, deterministic behavior, word timing, OOV
handling, compute needs, model size, and deployment complexity.

## TIMING_PROVENANCE_MODEL

The contract distinguishes:

- `provider_native_word_and_segment`;
- historical `derived_from_provider_native_word_boundaries`;
- `derived_local_alignment`.

Local alignment output always records `provider_native_timestamps = false`.
Provider transcript text and derived timing hashes remain separate. The
PositiveDuration projection preserves the exact provider token sequence and
accepts only positive, monotonic, non-overlapping, audio-bounded timing with
full token coverage.

## QUALITY_GATE_SPLIT

Text quality is evaluated before alignment acceptance, with unchanged gates:

- WER `<= 0.15`;
- exact contiguous critical-term recall `1.0` / `8-of-8`;
- Vietnamese diacritics preserved;
- no fuzzy, synonym, accent-stripped, or transcript-rewrite rescue.

Alignment quality independently verifies provenance, exact token coverage,
positive duration, monotonicity, audio bounds, and critical-term confidence.
A low-confidence critical-term alignment is `REVIEW_REQUIRED`.

Overall composition is fail closed:

- text FAIL + alignment PASS = `TEXT_QUALITY_FAIL`;
- text PASS + alignment FAIL = `ALIGNMENT_QUALITY_FAIL`;
- text PASS + uncertain critical timing = `ALIGNMENT_REVIEW_REQUIRED`;
- both PASS = `OFFLINE_COMPATIBILITY_CANDIDATE`, never a live claim.

Human alignment review may confirm timing. It cannot rewrite provider text or
convert a text-quality failure into acceptance.

## FAILURE_SEMANTICS

The prototype defines and tests:

- `ALIGNMENT_FAILED_NO_TIMED_TRANSCRIPT`;
- `ALIGNMENT_TOKEN_COVERAGE_FAILED`;
- `ALIGNMENT_NON_MONOTONIC`;
- `ALIGNMENT_ZERO_DURATION`;
- `ALIGNMENT_AUDIO_BOUNDS_FAILED`;
- `ALIGNMENT_LOW_CONFIDENCE_REVIEW_REQUIRED`;
- `ALIGNMENT_PROVENANCE_INVALID`.

There is no automatic Whisper fallback and no second provider call.

## LICENCE_REVIEW

Existing audio RightsRecords remain source references only. They do not grant
rights to an aligner implementation, acoustic/language model, or pronunciation
lexicon. Before any live gate, G-03 must review software license, model license,
redistribution, commercial-use, attribution, and derived-artifact restrictions.

The deterministic fixture uses no external model. Its license status is
`IN_REPO_TEST_FIXTURE / NO_EXTERNAL_MODEL`. Every future production aligner,
model, and lexicon remains `NOT_REVIEWED` until separately approved.

## COST_MODEL

Cost evidence has separate fields for provider cost, local alignment compute,
and total pipeline cost. Planning retains the Asset-01 provider-only estimate
`244.725300 VND` at the historical `27,000 VND/USD` assumption. Local compute
and total cost remain unknown until an engine is selected. This is not G-02,
and the historical `500 VND` ceiling does not transfer.

## TIMEOUT_MODEL

The schema separates provider transcription timeout, local alignment timeout,
and pipeline hard timeout with explicit orchestration headroom. It does not
reuse the Whisper `90 / 120 second` pair as a complete pipeline contract.
Concrete timeout values require engine benchmarking and a later Owner gate.

## FLOW_A_COMPATIBILITY

The new route is explicitly `TEXT_PROVIDER + ALIGNMENT_PIPELINE`. It cannot
claim Flow-A timing compatibility until both `TEXT_QUALITY_PASS` and
`ALIGNMENT_QUALITY_PASS` exist. It constructs a PositiveDuration-compatible
representation only after every timing invariant passes and always retains
`derived_local_alignment` provenance.

Historical W0/W1/W2 Whisper paths, evidence, prompt profiles, native timestamp
contracts, and gate loaders are unchanged. The new route does not replace or
weaken their strict native-timestamp guard.

## EVIDENCE_SEPARATION

Independent hashes are required for provider request/response/text, alignment
input, aligner/model/config, alignment result, text evaluation, alignment
evaluation, and Flow-A projection. The repository schema
`packages/contracts/gpt-alignment-evidence.v1.schema.json` enforces the sealed
separation and zero-call fixture classification.

## UNRESOLVED_BLOCKERS

1. Vietnamese behavior and account/model availability are not live validated.
2. A production aligner engine/model has not been selected or licensed.
3. Vietnamese OOV/domain-term alignment quality is unproven.
4. Local compute cost, latency, timeout, and deployment envelope are unproven.
5. PositiveDuration behavior is proven only with deterministic synthetic data.
6. Provider text quality and prompt/keyword insertion behavior have no live GPT
   Transcribe evidence.
7. New G-02/G-03 decisions, executable RC, qualification, lineage, authority,
   and O2 are required before any future provider execution.

## Zero-use boundary

- credential reads: `0`;
- provider calls: `0`;
- reservations: `0 VND`;
- spend: `0 VND`;
- live deployment: absent;
- RC27: absent;
- new lineage: absent;
- G-01/G-02/G-03: absent;
- O2: absent.
