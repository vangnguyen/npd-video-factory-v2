# V3-01-21 ASR response diagnostics and credential-alias scan remediation

## Outcome

V3-01-21 is a source-only, zero-call remediation for the two post-response defects exposed by
RC-12 ASR Operation 1. The authorized operation reached the OpenAI transcription response path,
then failed strict mapping/validation. Its primary evidence writer subsequently rejected the
approved credential reference as if it were a credential value.

```text
RC-12 ASR Operation 1: FAILED_RESPONSE_VALIDATION / REVIEW_REQUIRED / CONSUMED
Provider calls / attempts: 1 / 1
Retry / fallback: 0 / 0
Actual provider cost: UNKNOWN
Conservative safety charge: 500 VND
RC-12 ASR Operation 2: NOT APPROVED / LOCKED / RETIRED
ASR real-provider-tested: NOT_TESTED
V3-01-21 provider calls / credential reads / spend: 0 / 0 / 0 VND
Production: NO-GO
```

The machine-readable immutable review is
[`operation-1-review.json`](../../../evidence/v3-01/vf-v3-01-20260905T144918Z-75f693a/operations/rc12-asr-operation-1/operation-1-review.json).
It preserves the request identifiers and response hash that were actually retained, explicitly
leaves the missing request hash, transcript, usage and actual cost null, and does not reconstruct
the provider payload.

## What RC-12 proved and did not prove

The RC-12 preflight, exact asset-specific RightsRecord selection, budget reservation, credential
alias resolution and one-attempt provider dispatch all passed. A provider response was received and
entered the strict validation path. This is useful execution-infrastructure evidence, but it is not
a successful ASR result: there is no accepted transcript, timestamp mapping, usage/duration receipt
or actual-cost receipt.

The persisted RC-12 diagnostic contains the provider request ID
`req_cd17bc6b28c241a58a59805ed8f039fd`, client request ID
`vf-bc06bd7a4f4147dab77a3005f1e12882` and response SHA-256
`1d55f138d8518dfc171fe345be7f7cba948dfa2a3036b9f292ef87230aa22878`. It recorded only the
generic `ValidationError` classification. It did not retain an exact field path, safe response
shape or the raw response. Consequently this checkpoint does not claim whether the real response
was missing a field, had an invalid type or failed timestamp-to-segment mapping.

The checked-in malformed-response fixture is explicitly synthetic. It proves the new diagnostic
path offline; it is not represented as a reconstruction of the RC-12 response.

## Safe response-validation diagnostics

Future OpenAI ASR validation failures now retain only bounded, value-free diagnostic data:

- phase/category `structured_output_validation` and stable error code;
- HTTP status when available, safe provider/client request IDs and request/response SHA-256;
- monotonic elapsed time, response dispatch state and exception type chain;
- at most 32 validation issues containing only JSON path, stable code and issue kind;
- an allowlisted shape summary for `task`, `language`, `duration`, `text`, `segments` and `words`;
- segment/word counts and the count of unknown top-level fields, never their values.

Known mapping failures use explicit safe paths such as `$.words[2]`; Pydantic validation paths are
normalized to the same bounded syntax. Transcript text, word values, raw response bytes and
exception messages are not written to diagnostic evidence. The response hash remains sufficient
to bind a later review to the exact received bytes without exposing them.

Durable and non-durable paths continue to fail closed. A diagnostic failure is stored in the
existing JSON error-evidence column, so no database migration is required. The durable test proves
that these diagnostics survive a failed attempt without losing the operation ledger and without
persisting fixture text or credentials.

## Credential reference versus credential value

The canonical evidence writer now treats these bounded URI forms as references:

```text
secret://namespace/name
vault://namespace/name
external://namespace/name
```

References may be recorded because they contain routing identity rather than a credential value.
The scanner still rejects exact forbidden values, OpenAI-style key patterns, Bearer values and
assigned API key/token/password/secret values. A key-shaped string embedded inside an otherwise
valid reference is also rejected. The RC-12 fallback remains historical evidence of the old false
positive and is not rewritten.

## Deterministic validation

Local validation on source commit `75f693ab1a1a600b6069a6e13fdd2b3414f91960` includes:

- a synthetic response missing `words`, with safe `$.words / missing` diagnostics;
- an exact mapping failure at `$.words[2]` without transcript leakage;
- request/response hashes, request IDs, elapsed time, HTTP status and response-shape metadata;
- durable JSON persistence of value-free validation diagnostics;
- positive canonical alias cases and negative real key/Bearer/assignment cases;
- nested credential references plus a key-shaped value embedded in an alias;
- the complete Python/API/worker/bridge regression.

The final test summary and checksum-covered evidence are stored under
[`vf-v3-01-20260905T144918Z-75f693a`](../../../evidence/v3-01/vf-v3-01-20260905T144918Z-75f693a/).
Exact-head GitHub CI, including isolated Docker E2E, remains required before G-08 review.

## Acceptance effect and next boundary

V3-01-21 adds only implemented/mock-tested remediation evidence. `ASR-01` remains
real-provider-tested `NOT_TESTED`; RC-12 Operation 1 remains consumed/failed/`REVIEW_REQUIRED` and
cannot be retried. RC-12 Operation 2 is retired from live acceptance. Vision remains 2/2 PASS and
Production remains `NO-GO`.

Because this PR changes executable diagnostics and scanner behavior, a merge requires a new locked
candidate:

```text
G-08 review of this draft PR
-> merge
-> exact-main full regression
-> lock vf-v3-01-rc13
-> fresh ASR operation IDs, scope, bundle and dated window
-> rebind G-01/G-02/G-03-ASR
-> separate governance G-08
-> separate RC-13 ASR Operation 1 authority
```

This checkpoint grants no merge, credential read, provider call, reservation, deployment,
publishing, public ingress or production analytics authority.
