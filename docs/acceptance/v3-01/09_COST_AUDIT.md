# Cost audit

## Current result

| Event | Currency | Approved envelope | Safety-ledger committed | Actual external cost | Attempts |
|---|---|---:|---:|---:|---:|
| RC-3 operation 1 | VND | 1,250 window / 500 operation | 500 estimated | unknown | 1 |
| RC-5 operation 1 | VND | 1,250 window / 500 operation | 137.6287 actual | 137.6287 | 1 |
| V3-01-13 remediation | VND | 0 | 0 | 0 | 0 |
| RC-6 operation 1 pre-call block | VND | checked-in runtime budget 0; conditional window/operation envelope 1,250/500 retired after mismatch | 0 | 0 | 0 |
| RC-7 operation 1 timeout | VND | 1,250 window / 500 operation | 500 safety charge | unknown | 1 |
| V3-01-15 remediation | VND | 0 | 0 | 0 | 0 |
| V3-01-16 remediation | VND | 0 | 0 | 0 | 0 |
| RC-9 governance rebind | VND | checked-in runtime budget 0; owner-approved conditional window/operation envelope 1,250/500 | 0 | 0 | 0 |

The baseline and remediation audits used repository, GitHub CI and local static/mock evidence. The
later RC-3 operation-1 gate authorized one bounded OpenAI Vision attempt. It failed without a usage
receipt, so its actual provider billing cannot be asserted; the ledger committed the 500 VND
reservation conservatively. A separate RC-5 operation then completed provider execution once and
recorded 1,996 input tokens, 2,371 output tokens and `137.6287 VND` actual/charged cost. Its
post-call evidence artifact remained incomplete. V3-01-13 itself and V3-01-14 perform zero calls
and cost 0 VND. RC-6 operation 1 stopped before reservation/provider dispatch, so the dated
1,250/500 VND envelope committed nothing and is now retired with that failed window; it grants no
further operation authority and changes no checked-in runtime budget. No GPU workflow, hosted
render, publish or analytics collection was performed. RC-7 operation 1 later timed out after one
attempt. Its ledger committed the conservative 500 VND charge, but no usage receipt exists, so
actual provider cost remains unknown. V3-01-15 performs zero calls, reads no credential and costs
0 VND. V3-01-16 also performs zero calls, reads no credential and costs 0 VND; changing the
timeout architecture does not expand the 500/1,250 VND owner envelope. The RC-9 G-02 record binds
that unchanged envelope and the 90/120-second timeouts to one exact scope/window only; the bundle
is unmounted and no operation authority, reservation, call or cost follows from the record. USD is not an accepted
operating currency for this acceptance program.

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
and `REVIEW_REQUIRED`. Evidence: `EV-V3-RC5-VISION-OP1-REVIEW-001`. Operation 2 remains locked.
RC-6 rebind evidence `EV-V3-RC6-VISION-REBIND-001` validates the new VND envelope offline only;
operation 1 later received separate authority but stopped before reservation/provider dispatch on an
authority-limits mismatch. It remains not consumed, with provider calls 0, actual cost 0 VND and
ledger `0|0|0|0`; its RC-6 authority is retired. Operation 2 remains locked. V3-01-14 keeps both
`per_operation_limit_vnd` and `acceptance_window_limit_vnd` in one canonical VND contract and makes
no external call.

RC-7 rebind evidence `EV-V3-RC7-VISION-REBIND-001` validates the same two limits through the shared
canonical model. Operation 1 later timed out once and is consumed; evidence
`EV-V3-RC7-VISION-OP1-TIMEOUT-001` preserves actual cost as unknown and distinguishes the 500 VND
safety charge. Operation 2 is locked. V3-01-15 does not alter any limit.
V3-01-16 retains 500 VND per operation, 1,250 VND per acceptance window, one attempt, concurrency
one, no retry and no fallback. `EV-V3-RC9-VISION-REBIND-001` verifies the owner-approved exact-RC
G-02 record, canonical budget hash and unmounted bundle offline. Operation 1 still requires separate
authority and operation 2 remains locked.

No budget is inferred from credential availability. No automatic currency conversion may be stored
as authoritative cost without its dated source and calculated VND value.

Gap `V3-01-GAP-010`: `IN_PROGRESS`, supported by `EV-V3-PROVIDER-SAFETY-001` and
`EV-V3-DURABLE-SAFETY-001` on locked commit
`0f0854466655d2f36cfa8b57785000097b220c4c`, plus the failed bounded-operation evidence above;
the RC-5 cost record, exact-main V3-01-13 serializer evidence, offline RC-6/RC-7/RC-9 rebind evidence
and the RC-7 timeout record do not close or production-verify it.
