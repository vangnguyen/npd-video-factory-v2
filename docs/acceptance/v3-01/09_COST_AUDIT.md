# Cost audit

## Current result

| Event | Currency | Approved envelope | Safety-ledger committed | Actual external cost | Attempts |
|---|---|---:|---:|---:|---:|
| RC-3 operation 1 | VND | 1,250 window / 500 operation | 500 estimated | unknown | 1 |
| RC-5 operation 1 | VND | 1,250 window / 500 operation | 137.6287 actual | 137.6287 | 1 |
| V3-01-13 remediation | VND | 0 | 0 | 0 | 0 |

The baseline and remediation audits used repository, GitHub CI and local static/mock evidence. The
later RC-3 operation-1 gate authorized one bounded OpenAI Vision attempt. It failed without a usage
receipt, so its actual provider billing cannot be asserted; the ledger committed the 500 VND
reservation conservatively. A separate RC-5 operation then completed provider execution once and
recorded 1,996 input tokens, 2,371 output tokens and `137.6287 VND` actual/charged cost. Its
post-call evidence artifact remained incomplete. V3-01-13 itself performs zero calls and costs
0 VND. No GPU workflow, hosted render, publish or analytics collection was performed. USD is not
an accepted operating currency for this acceptance program.

## Required provider budget contract

Before G-02, the owner must approve in VND for every real-provider test:

- provider/capability and credential alias;
- model/workflow/version and region;
- maximum calls, media seconds, pixels/tokens or GPU minutes;
- unit-price source and conversion rule if the provider bills in another currency;
- maximum retry and polling count;
- warning thresholds at 50% and 80%;
- hard stop at 100%;
- owner and expiry time.

Failed, timed-out, moderated, retried and partially completed calls count toward actual cost. A
successful response without a usage/cost record is `FAIL` for cost acceptance.

## Current gaps and containment

V3-01-02 implements one VND-only control plane with per-operation/daily reservation, attempt
costing, exact 50/80/100 alerts, bounded retry/poll/timeout/concurrency, circuit state and a global
kill switch. Local tests prove those contracts while all configured limits stay zero and the kill
switch remains engaged.

V3-01-03 moves operation, attempt, daily reservation, threshold alert and circuit state into the
V2-owned PostgreSQL database. A serialized control-row transaction makes duplicate/concurrency and
daily reservation decisions atomic across API instances; startup recovers stale reservations and
opens the associated circuit. Secret-free snapshot fields expose active/stale/recovered operations,
attempt counts and oldest active age. Retention deletion exists as a repository operation but is
configuration-blocked until a later retention/DR gate.

These are local/CI controls only. Production-like PostgreSQL contention/restart evidence and
owner-gated real-provider acceptance are still required. Therefore all external, paid, ComfyUI,
publishing and analytics execution gates remain false.

Operation `v3-01-g03a-openai-vision-call-01` was attempted once with no automatic retry or model
fallback. Its durable record is failed/non-retryable, duplicate preflight is blocked, operation 2
has no ledger row, and the circuit remains closed with one consecutive failure. Because the provider
returned no usage receipt, the 500 VND ledger amount is safety accounting rather than accepted
actual cost. Evidence: `EV-V3-OPENAI-VISION-OP1-FAILED-001`.

Operation `v3-01-rc5-openai-vision-call-01` later completed once with no retry/fallback. Its durable
operation and attempt both succeeded, 500 VND was reserved, `137.6287 VND` was committed and the
remaining reservation returned to zero; the circuit stayed closed with zero consecutive failures.
The post-call serializer did not retain request-level evidence, so the operation remains consumed
and `REVIEW_REQUIRED`. Evidence: `EV-V3-RC5-VISION-OP1-REVIEW-001`. Operation 2 remains unapproved.

No budget is inferred from credential availability. No automatic currency conversion may be stored
as authoritative cost without its dated source and calculated VND value.

Gap `V3-01-GAP-010`: `IN_PROGRESS`, supported by `EV-V3-PROVIDER-SAFETY-001` and
`EV-V3-DURABLE-SAFETY-001` on locked commit
`0f0854466655d2f36cfa8b57785000097b220c4c`, plus the failed bounded-operation evidence above;
the RC-5 cost record and offline V3-01-13 serializer evidence do not close or production-verify it.
