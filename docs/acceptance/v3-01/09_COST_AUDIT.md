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
| RC-9 operation 1 CI-provenance pre-call block | VND | retired conditional envelope 1,250/500 | 0 | 0 | 0 |
| V3-01-17 remediation | VND | 0 | 0 | 0 | 0 |
| RC-10 governance rebind | VND | checked-in runtime budget 0; conditional window/operation envelope 1,250/500 | 0 | 0 | 0 |
| RC-10 operation 1 PASS | VND | 1,250 window / 500 operation | 125.1814 actual; 0 reserved after reconciliation | 125.181420 | 1 |
| RC-10 operation 2 PASS | VND | same 1,250 window / 500 operation | 159.1619 actual; 0 reserved after reconciliation | 159.161860 | 1 |
| RC-10 consecutive total | VND | 1,250 window | 284.3433 actual; 0 reserved | 284.343280 | 2 |
| PR #40 closure + V3-01-18 source remediation | VND | 0 | 0 | 0 | 0 |
| RC-11 ASR gate proposal | VND | checked-in runtime budget 0; conditional 1,250 window / 500 operation | 0 | 0 | 0 |
| RC-11 ASR Operation 1 rights-preflight block | VND | retired conditional 1,250 window / 500 operation | 0 | 0 | 0 |
| V3-01-20 durable multi-asset rights remediation | VND | 0 | 0 | 0 | 0 |
| RC-12 ASR governance rebind | VND | checked-in runtime budget 0; proposed conditional 1,250 window / 500 operation | 0 | 0 | 0 |
| RC-12 ASR Operation 1 response-validation failure | VND | 500 operation / 1,250 window | 500 safety charge; 0 reserved after reconciliation | unknown | 1 provider call; safety charge is not actual provider cost |
| V3-01-21 response-diagnostics remediation | VND | 0 | 0 | 0 | 0 calls; 0 credential reads |

The baseline and remediation audits used repository, GitHub CI and local static/mock evidence.

RC-11 ASR Operation 1 stopped before atomic reservation, ledger mutation, credential read or
provider dispatch because durable preflight had not selected from the approved multi-asset
RightsRecords. It therefore committed and incurred `0 VND`; its conditional 500/1,250 VND
authority is retired. V3-01-20 performs only offline source/mock validation and also costs `0 VND`.
PR #44 merged that remediation as RC-12. The fresh RC-12 bundle remains unmounted and neither
operation is approved, so this governance rebind also reads no credential, reserves nothing, makes
no provider call and costs `0 VND`.

The later RC-3 operation-1 gate authorized one bounded OpenAI Vision attempt. It failed without a usage
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
that unchanged envelope and the 90/120-second timeouts to one exact scope/window only. A separately
authorized RC-9 operation 1 later stopped at inner preflight on ambiguous CI provenance before a
credential read, reservation, ledger mutation or provider call; cost remained 0 VND and the
  authority is retired. V3-01-17 is merged in RC-10 and costs 0 VND. The RC-10 governance bundle
  bound the unchanged 500/1,250 VND envelope. After PR #37 merged, dual-CI provenance passed and a
  separately authorized Operation 1 ran once: 500 VND was atomically reserved, 1,996 input and 2,134
  output tokens produced an actual `125.181420 VND` receipt, and reserved VND returned to zero.
  After evidence-only PR #38 merged and current-main CI passed, separately authorized Operation 2
  repeated the same reservation contract: 1,996 input and 2,781 output tokens produced an actual
  `159.161860 VND` receipt. Total actual cost is `284.343280 VND` (`22.7474624%` of the 1,250 VND
  envelope); durable committed cost is `284.3433 VND` and reserved VND is zero. No retry or fallback
  occurred. PR #40 and V3-01-18 make no provider call, read no credential and cost 0 VND. The owner
  later approved G-02-ASR v1.1 at `162 VND/minute`, 500 VND per operation and 1,250 VND per window.
  The exact inputs model to `326.300400` and `363.394800 VND` respectively; these are estimates, not
  charges. The bundle is unmounted, both operations are unauthorized, no reservation exists and the
  governance proposal costs 0 VND.
  USD is not an accepted operating currency for this acceptance program.

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

RC-10 evidence `EV-V3-RC10-VISION-OP1-PASS-001` records the first complete real-provider cost
receipt: 1,996 input tokens, 0 cached tokens, 2,134 output tokens and `125.181420 VND` actual cost.
`EV-V3-RC10-VISION-CONSECUTIVE-PASS-001` binds it to the second receipt: 1,996 input, 0 cached and
2,781 output tokens with `159.161860 VND` actual cost. Both atomic reservations reconciled to zero;
both operations are consumed/succeeded. No further Vision budget or operation authority is inferred.

No budget is inferred from credential availability. No automatic currency conversion may be stored
as authoritative cost without its dated source and calculated VND value.

For RC-11 ASR, `EV-V3-RC11-ASR-GATE-001` binds the owner-fixed conversion rule of `0.006
USD/minute` at `27,000 VND/USD` to `162 VND/minute`, with a hard 180-second modeled maximum of
486 VND and a 500 VND atomic reservation. That expired envelope remains historical conditional gate
evidence only. For RC-12, `EV-V3-RC12-ASR-GATE-001` rebinds the same accounting rule to budget day
`2026-09-05`, exact scope `6f0aecf227df30d493566a8d089a6097f83c454993b6ce25eb00eeb887fb9cc4`
and fresh operation IDs. It remains conditional, unmounted and non-executable until separate gates
complete. An actual cost may be recorded only from a separately authorized provider receipt; the
current actual cost is 0 VND.

Gap `V3-01-GAP-010`: `IN_PROGRESS`, supported by `EV-V3-PROVIDER-SAFETY-001` and
`EV-V3-DURABLE-SAFETY-001` on locked commit
`0f0854466655d2f36cfa8b57785000097b220c4c`, plus the failed bounded-operation evidence above;
the RC-5 cost record, exact-main V3-01-13 serializer evidence, offline RC-6/RC-7/RC-9/RC-10 rebind
evidence, the RC-7 timeout record and the two complete RC-10 receipts do not production-verify the
broader safety plane. Vision is 2/2 consecutive real-provider PASS, while production-like
multi-instance cost safety remains unaccepted.
