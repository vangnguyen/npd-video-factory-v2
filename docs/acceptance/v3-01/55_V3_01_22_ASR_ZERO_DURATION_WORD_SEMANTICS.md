# V3-01-22 ASR zero-duration word timestamp semantics remediation

## Decision boundary

This checkpoint is the forensic completion of V3-01-22 after RC-14 ASR Operation 1 exposed an
exact timestamp shape that RC-13 evidence could not retain. It is source-only and offline.

```text
provider calls in this checkpoint: 0
credential reads in this checkpoint: 0
reservations in this checkpoint: 0 VND
spend in this checkpoint: 0 VND
RC-14 Operation 1: consumed; never retry or reuse
RC-14 Operation 2: not approved; locked
ASR real-provider-tested: NOT_TESTED
Production: NO-GO
```

The historical operation remains immutable. OpenAI returned HTTP 200 and an allowlisted payload,
but the adapter rejected the response during timestamp validation. In this document,
`provider transport success` means only that an HTTP 200 response was received; the durable
operation remains failed/`REVIEW_REQUIRED` because no accepted `ProviderTranscript`, usage receipt
or actual-cost receipt was produced. Its 500 VND ledger entry is a conservative safety charge, not
actual provider cost.

## Forensic source and limits

The source receipt is the unchanged local file
`operation-acceptance-rc14-asr-op1/evidence/operation-1-result.json`, SHA-256
`2d65b3e4c1ec1afc5f6b262a1ea294c811be5dba9718a06992da9fe3a8d2b1bd`. The exhaustive derived
report is
[`rc14-asr-operation-1-word-timestamp-forensics.json`](../../../evidence/v3-01/vf-v3-01-20260907T145428Z-46937d9-rc14-asr-forensics/rc14-asr-operation-1-word-timestamp-forensics.json).
It is schema-validated and hash-bound.

The source retained all 20 segment timing diagnostics and all 413 word timing diagnostics, but it
did not retain the raw provider response, transcript text or word text. Therefore token identity,
punctuation class and transcript-coverage contribution are explicitly
`UNKNOWN_NOT_RETAINED`. They are not reconstructed from the reference transcript because that
would falsely convert a reference into provider evidence.

## Forensic result

| Finding | Exact result |
| --- | ---: |
| Source duration | 120.852 seconds |
| Segments | 20; all positive and within source bounds |
| Words | 413 |
| Positive-duration words | 386 |
| Exact zero-duration words | 27 (6.53753%) |
| Zero points outside source | 0 |
| Zero points outside selected segment | 0 |
| Zero points non-monotonic | 0 |
| Zero points overlapping the previous word | 0 |
| Zero points equal to the next word start | 27/27 |
| Zero points also equal to the previous word end | 9/27 |
| Segment-start zero points | 10 |
| Segment-interior zero points | 17 |
| Segment-end zero points | 0 |
| Consecutive zero-point records | 6 |
| Duplicate zero-point groups | indexes 86/87, 139/140 and 185/186 |

The exact zero-duration indexes are:

```text
5, 7, 10, 17, 25, 38, 59, 64, 66, 86, 87, 114, 135, 139,
140, 146, 169, 185, 186, 197, 226, 230, 265, 271, 295, 345, 373
```

This is enough evidence to classify all 27 retained records as provider-emitted, bounded,
monotonic word boundary points. It is not evidence of their lexical or punctuation role. The
official Transcriptions API contract describes numeric `start` and `end` values for word and
segment timestamp granularities; it does not state an exclusive `start < end` invariant for every
word. See the dated official API reference used for this review:
[Create transcription](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create).

## Root cause

The former adapter used one interval rule for two different representations:

1. provider evidence, where a word may be represented by an ordered boundary point; and
2. edit/render consumers, where a cue must have positive duration.

The `_ProviderWord` model rejected `end <= start` before the adapter could preserve the provider
shape. That made a valid HTTP response fail as a whole even though the 27 equality cases were
bounded and ordered. The prior fail-closed behavior was safe, but its contract was too coarse.

## Canonical contract

The replacement contract keeps both layers explicit:

| Layer | Rule | Zero-duration behavior |
| --- | --- | --- |
| Raw provider evidence | retain original bytes/hash and numeric diagnostics | never changed |
| ASR adapter word evidence | `0 <= start <= end <= source_duration`, ordered, inside one segment | allowed only when the exact point touches an adjacent word boundary; marked `provider_boundary_point` |
| ASR adapter segments | `0 <= start < end <= source_duration`, ordered | always rejected |
| Provider transcript | retains every word and its `timing_semantics` | no epsilon, duration fabrication, endpoint swap or silent drop |
| Post-run ASR evaluator | accepts anchored boundary points for provider-evidence assessment | counts them and reports downstream readiness separately |
| Edit/subtitle/reframe persistence boundary | requires explicit `PositiveDurationTranscript` | blocked until a separately reviewed derived representation exists |

The adapter still fails closed on inverted, negative, non-numeric, missing, out-of-source,
out-of-segment, overlapping or unbound timestamps. Six-decimal canonicalization remains allowed
only when representation/order is preserved. A zero point in an arbitrary gap is rejected. Segment
boundaries use deterministic half-open ownership so one point cannot be silently assigned twice.

No positive-duration cue is fabricated in this checkpoint. `PositiveDurationTranscript` is a
proof wrapper over an already-positive transcript, not a repair algorithm. A future alignment or
cue-derivation design would need its own provenance, policy, tests and owner review.

## Consumer audit

| Component | Actual requirement after this remediation |
| --- | --- |
| `ProviderTranscript` / OpenAI adapter | permits explicitly marked provider boundary points |
| Durable and in-memory provider safety | preserve the same provider value and evidence counts; neither rewrites timing |
| ASR post-run evaluator | accepts anchored boundary points for provider evidence; exposes `downstream_positive_duration_ready=false` when any remain |
| `AutoEditAnalysisService` | requires `PositiveDurationTranscript` before scene/silence generation and persistence |
| Transcript database/API models | retain strict positive word intervals |
| Scene/highlight/reframe logic | consumes positive segment/cue intervals; it receives no unchecked provider boundary points |
| Subtitle/audio/timeline/render contracts | retain positive-duration cue requirements |
| Flow A aggregate acceptance | remains blocked until real ASR evidence is accepted and downstream real-media/quality axes pass |

This separation avoids a global relaxation. ASR provider evidence may preserve what the provider
returned, while downstream systems that divide, render or cut by duration continue to require
`start < end`.

## Historical evidence rule

RC-14 Operation 1 remains:

```text
HTTP/provider transport: SUCCESS / 200
durable operation: FAILED_RESPONSE_VALIDATION
acceptance: REVIEW_REQUIRED
consumed: true
retry/reuse: forbidden
actual provider cost: UNKNOWN
safety charge: 500 VND (not actual cost)
Operation 2: NOT APPROVED / LOCKED
```

Neither this forensic analysis nor the new semantics retroactively upgrades RC-14. No transcript,
usage or cost field is reconstructed.

## Verification and next gate

The focused suite covers positive intervals, one and consecutive boundary points, segment start
and end, duplicate shared boundaries, inverted/negative/out-of-source/out-of-segment timestamps,
invalid segment ordering, transcript coverage loss, deterministic segment ownership,
durable/non-durable parity and the downstream no-repair guard. The forensic report accounts for
all 413 word indexes and validates its own canonical SHA-256.

This draft must stop at a new G-08. A merge would change executable timestamp semantics and would
therefore require exact-main regression and a new RC before any later ASR authority. This PR does
not create that RC, operation ID, bundle, window or authority.
