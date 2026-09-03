# V3-01 ASR post-run evaluator and Flow A real-media preparation

## Checkpoint

```text
PACKAGE: OFFLINE / ZERO-CALL PREPARATION
BASE GOVERNANCE MAIN: 8ad490c02c36aafe9447a3eb0766a1d1f1f122d7
EXECUTABLE RC: vf-v3-01-rc11 -> 207ff9fee5557eb0976f575c9263b61d995b20a0
EXECUTABLE RC MODIFIED: NO
ASR OPERATION 1 EXECUTED BY THIS PACKAGE: NO
ASR OPERATION 2 AUTHORITY: NOT APPROVED / LOCKED
PROVIDER CALLS / CREDENTIAL READS / RESERVATION / SPEND: 0 / 0 / 0 VND / 0 VND
ACCEPTANCE AXIS PROMOTED: NO
DEPLOY / PUBLISH / PUBLIC INGRESS: NO / NO / NO
PRODUCTION: NO-GO
```

This package prepares deterministic post-run evaluation and a complete evidence shape while the
separately approved RC-11 ASR Operation 1 remains governed by its own dated window. Nothing here
mounts that gate bundle, resolves its credential alias, reserves budget or invokes a provider.

## ASR evaluator

The read-only evaluator is
[`tools/v3_01_asr_post_run_evaluator.py`](tools/v3_01_asr_post_run_evaluator.py). It accepts one
JSON document conforming to
[`asr-post-run-input.schema.json`](schemas/asr-post-run-input.schema.json), returns a document
conforming to
[`asr-post-run-evaluation.schema.json`](schemas/asr-post-run-evaluation.schema.json), and computes a
deterministic SHA-256 over the result before adding that hash.

The normalization rule is explicit and intentionally conservative:

1. normalize Unicode with NFKC;
2. use Unicode-aware `casefold`;
3. replace punctuation and symbols with whitespace;
4. collapse whitespace by tokenization;
5. preserve Vietnamese diacritics;
6. retain critical terms in the transcript used for WER.

The evaluator measures:

- full-transcript word error rate with a maximum of `0.15`;
- exact and normalized critical-term recall, requiring `1.0` for PASS;
- word and segment windows, monotonicity, bounds, overlap, word-in-segment containment and timed
  transcript coverage;
- expected language `vi` and provider/source duration parity;
- canonical `ProviderTranscript` mapping, including nullable confidence and provenance;
- provider request ID, hashes, duration/usage and cost receipts, latency, ledger, circuit, duplicate
  block, reconciliation, source provenance and secret-scan completeness.

`PASS`, `REVIEW_REQUIRED` and `FAIL` include machine-readable reason arrays. Missing provider output
or incomplete receipts cannot become PASS. A measured transcript/safety threshold failure becomes
FAIL. A provider failure or uncertain dispatch with no complete transcript remains REVIEW_REQUIRED
unless a mandatory safety control, including secret containment or attempt count, failed.

Fixtures cover all three verdicts under
[`fixtures/asr-post-run`](fixtures/asr-post-run). They contain no provider response captured from a
live call. The reviewer fills
[`V3_01_ASR_OPERATION_EVIDENCE_REVIEW.md`](templates/V3_01_ASR_OPERATION_EVIDENCE_REVIEW.md) only
from preserved source evidence; missing fields must stay missing.

## Flow A real-media contract

The machine-readable contract is
[`V3-01-FLOW-A-REAL-MEDIA-ACCEPTANCE.v1.json`](contracts/V3-01-FLOW-A-REAL-MEDIA-ACCEPTANCE.v1.json)
and validates against
[`flow-a-real-media-acceptance.schema.json`](schemas/flow-a-real-media-acceptance.schema.json). It
defines this pipeline without executing it:

```text
upload
-> ASR
-> transcript
-> scene detection
-> silence decisions
-> highlights
-> Vision
-> smart reframe
-> subtitle
-> render
-> automated QC
-> G-11 human review
```

Two distinct inputs on one immutable executable RC are required. Both runs must pass individually
and be chronological before an aggregate 2/2 result can be proposed. The prepared reference files
are:

- [`V3-01-FLOW-A-REAL-MEDIA-RUN-01.json`](templates/V3-01-FLOW-A-REAL-MEDIA-RUN-01.json);
- [`V3-01-FLOW-A-REAL-MEDIA-RUN-02.json`](templates/V3-01-FLOW-A-REAL-MEDIA-RUN-02.json).

The corresponding review forms are
[`V3_01_FLOW_A_REAL_MEDIA_RUN_REVIEW.md`](templates/V3_01_FLOW_A_REAL_MEDIA_RUN_REVIEW.md) for each
run and
[`V3_01_FLOW_A_REAL_MEDIA_CONSECUTIVE_REVIEW.md`](templates/V3_01_FLOW_A_REAL_MEDIA_CONSECUTIVE_REVIEW.md)
for the aggregate 2/2 decision.

They bind the two owner-cleared ASR WAVs, transcripts, RightsRecords and critical terms already in
RC-11. They deliberately leave the visual source, annotated scene boundaries, subject/reframe
zones, subtitle cues and expected final duration as `null`. Those values cannot be invented from
the audio inputs. Before a real-media run, an owner-cleared video and human reference annotations
must replace every null under a new hash-bound gate and separate owner approval.

## Measured thresholds

| Area | Required result |
|---|---|
| ASR | WER <= 0.15 and critical-term recall = 1.0 |
| Scene detection | boundary F1 >= 0.80 within 0.50 s tolerance |
| Smart reframe | safe subject coverage >= 0.95 |
| Subtitle | median drift <= 0.20 s and P95 drift <= 0.50 s |
| Render duration | expected/final delta <= 0.50 s |
| A/V parity | audio/video delta <= 0.25 s |
| Output | at least 1080 x 1920, H.264 + AAC 48 kHz, full decode |
| Visual QC | black ratio <= 0.10, freeze ratio <= 0.15, dark-sample ratio <= 0.10, broken frames = 0 |
| Audio QC | silence ratio <= 0.80 and peak within -35.0 to -0.05 dB |
| Layout | subtitle safe area and timeline renderability must pass |
| Human quality | exact artifact-bound G-11 must be ACCEPT |

These thresholds reuse the existing deterministic Flow A/render/QC policy. This package does not
claim that the values have been met by real media.

## Evidence layout

Each future run uses the layout enumerated in the contract: source binding, ASR transcript and
evaluation, scene/silence decisions, Vision subject evidence, reframe coverage, subtitle alignment,
final render, automated QC, G-11 review and final status. A run manifest and checksums cover the
entire evidence set. An aggregate record may reference two complete run manifests; it must not
rewrite either run or deduplicate two provider responses merely because an input hash matches.

## Current blockers and acceptance effect

- no owner-cleared full video is bound;
- no human scene, subject/reframe or subtitle reference annotations exist;
- G-04 production-like path and G-11 human quality are not approved;
- RC-11 ASR Operation 1 has not been executed by this package; Operation 2 is locked;
- provider execution, production-path and human-quality evidence remain absent for Flow A.

The current matrix and gap states do not change. This package adds preparation evidence only.
