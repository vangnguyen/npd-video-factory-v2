# V3-01-22 ASR timestamp canonicalization and validation remediation

## Outcome

V3-01-22 is a source-only, zero-call remediation for the timestamp validation boundary exposed by
RC-13 ASR Operation 1. The operation reached OpenAI, received HTTP 200 and returned an allowlisted
shape containing 17 segments and 412 words. Twenty-seven word objects failed the RC-13 model-level
rule `end <= start`; no accepted `ProviderTranscript` was produced.

```text
RC-13 ASR Operation 1: FAILED_RESPONSE_VALIDATION / REVIEW_REQUIRED / CONSUMED
Provider HTTP: 200
Segments / words received: 17 / 412
Invalid word objects: 27 (about 6.6%)
Actual provider cost: UNKNOWN
Conservative safety charge: 500 VND
RC-13 ASR Operation 2: NOT APPROVED / LOCKED / RETIRED
V3-01-22 provider calls / real credential reads / spend: 0 / 0 / 0 VND
ASR real-provider-tested: NOT_TESTED
Production: NO-GO
```

The immutable review is
[`operation-1-review.json`](../../../evidence/v3-01/vf-v3-01-20260906T143658Z-392ce0e/operations/rc13-asr-operation-1/operation-1-review.json).
It preserves only evidence that was actually retained, including the provider/request hashes,
request ID, paths, counts, ledger and secret scan.

## Historical evidence boundary

The RC-13 executable used one `_ProviderWord` model validator for both `start == end` and
`end < start`. Its error extractor intentionally omitted input values. Therefore the historical 27
failures can be classified exactly only as `end <= start`; their split between equality and
inversion is unknown. No raw provider response or raw timestamp values were retained, so this PR
does not reconstruct them and does not claim counts for overlap, segment containment, rounding,
missing or non-numeric values.

The redacted fixture
[`rc13-operation-1-redacted-timestamp-diagnostic.json`](../../../apps/api/tests/fixtures/openai_transcription/rc13-operation-1-redacted-timestamp-diagnostic.json)
contains the retained diagnostic shape and all 27 paths. It is explicitly not a provider-response
fixture.

## Canonical timestamp contract

The adapter now classifies timestamps before Pydantic domain mapping. Every diagnostic contains an
allowlisted path, item type/index, classification, action, numeric raw values when they exist,
numeric canonical values when a transformation exists, and a stable reason code. Transcript text,
word text, provider payloads and credential values are excluded from failure diagnostics.

The classifications are:

- `start_equals_end`;
- `end_before_start`;
- `word_outside_segment`;
- `overlap`;
- `precision_rounding`;
- `missing`;
- `non_numeric`;
- `out_of_range`.

The report records segment/word counts plus transformed, rejected and per-class counts. Failure
evidence is persisted through the existing durable JSON evidence column, so no database migration
is needed.

## Transformation policy

Canonicalization is intentionally narrower than validation:

- a finite timestamp may be rounded half-up to six decimal places only when the resulting interval
  remains positive and ordered;
- negative zero may be represented canonically as positive zero;
- the raw response SHA-256 is always computed from the original bytes and never from the canonical
  copy;
- each actual transformation keeps raw and canonical numeric values separately;
- transcript/segment/word text is never changed;
- `start == end` is rejected because inventing duration is not permitted;
- `end < start` is rejected and never repaired by swapping endpoints;
- rounding that collapses an interval, overlap, out-of-range values and word/segment containment
  violations are rejected rather than rewritten;
- missing and non-numeric timestamps are rejected without storing the unsafe field value.

This is not a relaxed validator. The canonicalizer makes only representation-preserving changes;
all semantic uncertainty remains fail-closed.

## Deterministic tests

On source commit `392ce0ecfb45d9f4699c1c56b6bde388ffc64a25`, focused tests cover every
classification above, multiple rejected words in one response, negative-zero/precision
canonicalization, stable raw response hashing, unchanged Vietnamese text, durable JSON persistence
and the non-reconstructed RC-13 fixture. The full local regression passed:

- Python/API/worker/bridge: 442 tests;
- focused timestamp/provider safety subset: 54 tests;
- Studio: 14 tests;
- Renderer: 14 tests plus typecheck and bundle check;
- acceptance register and ASR compatibility validation: PASS;
- migration upgrade/downgrade/replay through `0013`: PASS;
- Docker Compose configuration: PASS.

GitHub exact-head CI, including deterministic Docker E2E, remains required before G-08 review.

## Acceptance effect and next boundary

V3-01-22 advances only implemented/mock-tested remediation evidence. It does not convert RC-13
Operation 1 into PASS, does not infer actual cost from the 500 VND safety charge and does not
promote `ASR-01` real-provider-tested. RC-13 Operation 1 remains consumed/`REVIEW_REQUIRED`; RC-13
Operation 2 remains locked and retired.

Because this PR changes executable adapter/evidence behavior, a merge requires a new immutable
candidate. The post-merge sequence is:

```text
G-08 review of this draft PR
-> merge
-> exact-main full regression
-> lock vf-v3-01-rc14
-> fresh ASR operation IDs, scope, bundle and dated window
-> rebind G-01/G-02/G-03-ASR
-> separate governance G-08
-> separate RC-14 ASR Operation 1 authority
```

No part of this checkpoint grants merge authority, credential read, provider call, budget
reservation, deployment, publishing, public ingress or production analytics. Production remains
`NO-GO`.
