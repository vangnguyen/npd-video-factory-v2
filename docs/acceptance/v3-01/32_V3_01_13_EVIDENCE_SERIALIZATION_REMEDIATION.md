# V3-01-13 — Evidence Serialization Remediation

## Decision boundary

```text
CHECKPOINT: V3-01-13
SCOPE: ZERO-CALL EVIDENCE SERIALIZATION REMEDIATION
MERGED COMMIT: 8df74a202dc2160e9358ca4cc9be54d989af2292
IMPLEMENTED / MOCK-TESTED: PASS EXACT-MAIN
REAL-PROVIDER ACCEPTANCE: NOT TESTED
PRODUCTION-PATH ACCEPTANCE: NOT TESTED
QUALITY ACCEPTANCE: NOT TESTED
EXTERNAL CALLS DURING REMEDIATION: 0
ACTUAL COST DURING REMEDIATION: 0 VND
G-08 FOR THIS REMEDIATION: CONSUMED BY V3-01-APP-025
RC-6: LOCKED AT vf-v3-01-rc6
PRODUCTION VERDICT: NO-GO
```

This checkpoint fixes only the post-call evidence serialization defect found after the single
authorized RC-5 Vision operation. It does not call OpenAI, read a credential value, deploy, publish,
open ingress, collect production analytics or authorize another operation.

## Permanent RC-5 operation disposition

`v3-01-rc5-openai-vision-call-01` remains permanently classified as follows:

| Dimension | Disposition |
|---|---|
| Provider execution | `SUCCESS` |
| Durable operation/attempt | `succeeded` / `succeeded`; one attempt; zero retry; zero fallback |
| Acceptance evidence | `INCOMPLETE` |
| Acceptance verdict | `REVIEW_REQUIRED` |
| Operation 1 | `CONSUMED`; never reusable |
| Operation 2 | `NOT APPROVED`; no ledger row |
| Actual recorded cost | `137.6287 VND` |
| Production | `NO-GO` |

The structured frame payload, provider request ID, client request ID and request/response hashes
were not retained after the runner called the Pydantic-only `model_dump()` method on frozen
dataclass `ProviderVisionFrame`. Those missing values remain `null`. They are not reconstructed,
inferred or promoted into accepted real-provider evidence.

## Remediation

`apps/api/app/evidence_serialization.py` now provides one canonical evidence boundary:

```text
ProviderVisionFrame / nested dataclass / Pydantic model
  -> canonical_evidence_value
  -> deterministic UTF-8 JSON bytes
  -> stable SHA-256
  -> atomic evidence file
```

The serializer supports dataclasses, Pydantic models, nested tuples/lists/dictionaries, nullable
fields, Unicode, VND `Decimal` values, UTC timestamps, paths, UUIDs and enums. Mapping keys must be
strings and non-finite floats or unsupported objects fail closed.

`write_evidence_bundle` writes the canonical payload atomically. If serialization fails, it writes
a separate `*.serialization-error.json` artifact with verdict `REVIEW_REQUIRED` and a secret-free
copy of the already durable operation/usage/cost context. It returns a fallback receipt instead of
discarding or mutating the durable ledger. If that context itself fails secret containment, the
context is withheld while the error classification remains available.

## Offline regression evidence

The exact regression suite covers:

- the real `ProviderVisionFrame` frozen dataclass contract;
- nested `ProviderObjectDetection`, `ProviderOCRDetection` and Pydantic `NormalizedBox` values;
- nullable `track_hint`, tuples, lists, dictionaries and Vietnamese Unicode;
- deterministic canonical bytes and fixed SHA-256;
- a recorded/mock successful `ProviderVisionResult`, including provider metadata, request/response
  hash placeholders, latency, usage and actual VND cost;
- unsupported-result failure with a separate `REVIEW_REQUIRED` fallback;
- preservation of the durable provider result/usage/cost dictionary;
- secret-value detection and fallback-context withholding.

Focused serializer tests pass `5/5`; the API suite passes `221/221`; and the repository-wide API,
worker and ComfyUI bridge suite passes `265/265`. Studio tests pass `14/14`; renderer tests pass
`14/14` together with typecheck and bundle validation. Migration upgrade/downgrade/re-upgrade,
repository evidence validation and the deterministic Docker E2E/DR drill also pass. PR #29 merged
the remediation and exact-main CI run `33261962445` passed all five jobs. Every check ran offline
with fixture providers and performed zero external provider calls.

## Acceptance impact

The new serializer changes only the implemented/mock-tested evidence path. It does not repair the
missing RC-5 artifact retroactively and does not change `VIS-01` real-provider status from
`NOT_TESTED`. GAP-003, GAP-010 and GAP-013 remain `IN_PROGRESS`.

## Sequence status after merge

```text
PR #29 / G-08 / merge / exact-main regression: COMPLETE
  -> vf-v3-01-rc6 lock: COMPLETE
  -> new RC-6 operation IDs and scope/window: COMPLETE OFFLINE
  -> G-01-A / G-02-A / G-03-A rebind: COMPLETE IN UNMOUNTED BUNDLE
  -> governance rebind PR G-08: PENDING
  -> separate owner authority for RC-6 operation 1: PENDING
```

No RC-5 operation ID may be reused. RC-5 operation 2 remains locked.
