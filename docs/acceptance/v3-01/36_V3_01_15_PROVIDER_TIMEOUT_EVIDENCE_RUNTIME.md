# V3-01-15 Provider Timeout Evidence & Runtime Remediation

## Decision boundary

V3-01-15 is a source-only, zero-call remediation. It does not increase the approved timeout, read a
credential, mount a gate bundle, reserve budget, call a provider, deploy, publish, open ingress or
promote any acceptance axis.

```text
RC-7 operation 1: CONSUMED / REVIEW_REQUIRED
provider execution: FAILED — PROVIDER_TIMEOUT
acceptance evidence: INCOMPLETE
retry: FORBIDDEN; none performed
actual provider cost: UNKNOWN
safety charge: 500 VND; not an actual-cost receipt
RC-7 operation 2: LOCKED / NOT APPROVED
V3-01-15 external calls: 0
V3-01-15 credential reads: 0
V3-01-15 spend: 0 VND
production: NO-GO
```

The secret-free historical receipt projection is
[`operation-1-timeout-review.json`](evidence/rc7-openai-vision-operation-1/operation-1-timeout-review.json).
Its source receipt SHA-256 is pinned; missing request-level evidence and actual provider cost are not
reconstructed or inferred.

## Evidence versus inference

### Direct evidence

- Exact RC-7 operation 1 ran once from `2026-08-31T14:18:02.050024Z` to
  `2026-08-31T14:19:02.146021Z` and ended with `PROVIDER_TIMEOUT` at the 60-second envelope.
- The operation and attempt are durable, the operation is consumed, no retry or fallback occurred,
  and duplicate protection remains active.
- The durable ledger committed a conservative 500 VND safety charge. No usage receipt or actual-cost
  receipt exists, so actual cost is `UNKNOWN`.
- Provider request ID, request hash, response hash and structured response are absent. Operation 2
  was not authorized or executed.
- Canonical evidence serialization completed for the context that existed after the timeout; this is
  not a provider-success receipt.

### Source-based inference

At RC-7, both the central safety controller and the OpenAI HTTP adapter used a 60-second deadline.
The controller wrapped the adapter with `asyncio.wait_for`, while the adapter independently used an
HTTP client timeout. The historical attempt lacks adapter error evidence. The most likely explanation
is that the outer controller deadline cancelled the adapter at the boundary before the adapter could
persist its phase-specific timeout evidence. This inference does not prove whether the request reached
OpenAI, and the request-delivery state therefore remains `UNKNOWN_POSSIBLY_SENT`.

## Remediation

V3-01-15 adds a shared, secret-free `ProviderExecutionTrace` that follows one call through:

```text
service dispatch
→ credential resolution
→ frame extraction
→ request build
→ HTTP pool/connect/write/dispatch
→ response wait/read
→ response parse
```

Timeout evidence now records:

- the last known phase and timeout kind;
- configured timeout and monotonic elapsed milliseconds;
- request-dispatch state (`not_sent`, `possibly_sent`, or `response_headers_received`);
- client request ID and a redacted provider request ID when response headers exist;
- a bounded exception type chain without exception messages or payloads;
- final retry authorization, which is false for the one-attempt acceptance policy.

The adapter streams the response so safe response headers can be retained before body reading. If
the central controller deadline wins the race, it asks the same trace for structured evidence instead
of producing a bare `PROVIDER_TIMEOUT`. A defensive fallback still emits structured
`controller_envelope` evidence if trace serialization itself fails.

## Deterministic boundary tests

The test transport advances a virtual monotonic clock; it does not sleep for 60 real seconds.

| Virtual response delay | Expected result | Required evidence |
|---:|---|---|
| 59 s | success | one request, provider request ID retained, latency 59,000 ms |
| 60 s | read timeout | phase/kind/elapsed/dispatch state/request ID retained; one request |
| 61 s | read timeout | phase/kind/elapsed/dispatch state/request ID retained; one request |

Separate controller-envelope and durable-repository tests prove one attempt, no retry, unknown actual
cost, conservative charge preservation, structured timeout evidence, consumed operation state and
duplicate-operation rejection.

## Timeout-envelope assessment

OpenAI documents timeout errors separately and recommends logging request IDs; its SDK documentation
also shows a much larger default request timeout than this project's 60-second bounded envelope.
That comparison establishes that RC-7 was intentionally stricter, not that 90 or 120 seconds is the
correct replacement. One timeout without a usage/request receipt is insufficient to choose a new
limit.

V3-01-15 therefore leaves the executable timeout at **60 seconds**. Any proposal to use 90 or 120
seconds changes the safety envelope and requires a fresh G-02 rebind, new RC, new operation IDs,
new scope/window and separate owner authority. There is no automatic fallback or retry.

## Acceptance impact and next sequence

This remediation improves the mock-tested timeout/evidence boundary only. `VIS-01`, `OPS-01` and
`OPS-03` remain `NOT_TESTED` on the real-provider axis; GAP-003, GAP-010 and GAP-013 remain
`IN_PROGRESS`.

```text
V3-01-15 draft PR
→ G-08 review
→ merge
→ exact-main full regression
→ lock vf-v3-01-rc8
→ decide and rebind timeout/budget envelope if needed
→ derive fresh operation IDs and hashes/window
→ rebind G-01-A / G-02-A / G-03-A
→ separate authority for RC-8 operation 1
```

RC-7 operation 2 stays locked. No RC-7 authority is reusable. Overall production verdict remains
**NO-GO**.
