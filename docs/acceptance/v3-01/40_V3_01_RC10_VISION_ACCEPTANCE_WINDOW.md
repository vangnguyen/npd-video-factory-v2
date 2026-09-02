# V3-01 RC-10 Vision acceptance window

This checkpoint records the owner-directed RC-10 rebind after V3-01-17 merged and the later
bounded Operation 1 outcome. The original pre-execution bindings are retained below as historical
governance evidence; the current outcome is detailed in
[41_V3_01_RC10_VISION_OPERATION_1_EVIDENCE.md](41_V3_01_RC10_VISION_OPERATION_1_EVIDENCE.md).

## Decision boundary

```text
RC: vf-v3-01-rc10 / c2b1aec2d54dd90bcb486f8a68c97746b39963aa
RC STATUS: LOCKED, NO-GO, NOT DEPLOYED
G-08 PR #36: CONSUMED
G-08 GOVERNANCE REBIND PR #37: CONSUMED
G-01-A / G-02-A / G-03-A: CONSUMED BY EXACT RC-10 OPERATION 1
GOVERNANCE BUNDLE: VERIFIED; UNMOUNTED AFTER OPERATION
RC-10 OPERATION 1: PASS; CONSUMED / SUCCEEDED
RC-10 OPERATION 2: NOT APPROVED; LOCKED; NOT EXECUTED
EXTERNAL EXECUTION: false
PAID EXECUTION: false
CHECKED-IN BUDGET: 0 VND
GLOBAL KILL SWITCH: engaged
CREDENTIAL: alias only in evidence; value not recorded
PROVIDER CALLS: 1 HISTORICAL ACCEPTANCE CALL; 0 IN THIS EVIDENCE PR
RESERVATION / ACTUAL COST: 500 VND / 125.181420 VND; RESERVED AFTER RECONCILIATION 0 VND
VISION CONSECUTIVE STATUS: 1/2 PASS
PRODUCTION: NO-GO
```

PR #36 merged V3-01-17 as
`c2b1aec2d54dd90bcb486f8a68c97746b39963aa`. Exact-main CI run `33527973264` passed
Python, Studio, Renderer, Safety/Compose and Docker deterministic E2E. Annotated tag
`vf-v3-01-rc10` peels to that exact merge commit; tag object
`32bd6a78048a6ae92538a9195a1386318ebd72b8` records `NO-GO`, no provider execution and the
requirement for fresh scope and separate operation authority.

V3-01-17 supplies one canonical dual-CI provenance contract. The executable-RC CI and the
post-governance-main CI have different roles, exact commits and run identifiers. Neither run can
substitute for the other. Governance-only PR #37 merged as
`fd78a1690a5a2fd7b07e9e7822deda834f02ea6d`; governance-main CI `33532594395` completed
successfully. The dual-CI record verified the governance diff was allowlisted and both executable
trees hash to `f1f75f632ca3b1380985c5a532c9f4c601e39d45276135666f335cc3d041125c`.

## Exact RC-10 scope

| Field | Bound value |
|---|---|
| Provider | `openai-vision` |
| Model | `gpt-5-mini` |
| Capability | `vision` |
| Credential reference | `secret://openai/codex-video` only; no value is stored or read |
| RC tag | `vf-v3-01-rc10` |
| RC commit | `c2b1aec2d54dd90bcb486f8a68c97746b39963aa` |
| Executable RC CI | run `33527973264`, exact commit, completed/success, 5/5 jobs |
| Governance main | `fd78a1690a5a2fd7b07e9e7822deda834f02ea6d` |
| Governance main CI | run `33532594395`, exact commit, completed/success, 5/5 jobs |
| Asset | `g03-a-owned-vision-test.png` |
| Asset SHA-256 | `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e` |
| RightsRecord canonical SHA-256 | `f469930a74b477751fc4417774b486ccbf2d7822487478875e099552c83e06ba` |
| Provider-scope canonical SHA-256 | `f1cff1c8370caf6218577cdabfbd06c0665dfabb2407ec320b4668f7bf50072a` |
| Budget-envelope canonical SHA-256 | `b1452a62b4cd05d7f2de1f51437a0eca300d4c7c7fc9d7c4a8e58d810259fc14` |
| Execution-scope SHA-256 | `a77a2e38d604214dbcaf0933cbdbf6f2fafa6ee258369e1a629ef5b0d55c6cc0` |
| Raw bundle SHA-256 | `30f4ffd9353a00b7fdf97d0998dce43798937a2c577ca3fa618c947bbb8040e1` |
| UTC window | `2026-09-02T14:00:00Z` through `2026-09-02T18:00:00Z` |
| Vietnam time | `21:00 02/09/2026` through `01:00 03/09/2026` |

The verified bundle is
[`V3-01-GATE-RC10-OPENAI-VISION-A.json`](V3-01-GATE-RC10-OPENAI-VISION-A.json).
It embeds exact copies and canonical hashes of the three rebound approval records:

- G-01-A: `V3-01-APP-038`, SHA-256
  `5f223eee2e6bed86e8f4d6af79906f1c5a30a7cde6717fb0b2efdfd2665b8e3c`;
- G-02-A: `V3-01-APP-039`, SHA-256
  `e84415fb511c79c5495d899b68250067fe6c341fa11f7b99d3c541c25a4284e0`;
- G-03-A: `V3-01-APP-040`, SHA-256
  `77caf62c7ded8c9298df932b776886f96a49d59ed0fe280a1f04b15e4d3adcd5`.

These records implement the owner-directed post-PR36 sequence. A later separate authority bound
exactly Operation 1 and was consumed by its single successful attempt. These records and that
consumed authority do not authorize Operation 2 or any further API call. Any mutation of the exact
RC, provider, model, capability, asset, RightsRecord, budget, timeout envelope, operation IDs, scope
hash or window invalidates the binding.

## Immutable operations

The executable derivation helper produced exactly:

1. `v3-01-rc10-openai-vision-call-01`
2. `v3-01-rc10-openai-vision-call-02`

Operation 1 received one exact owner authority, completed successfully and now has one durable
`succeeded` row and one attempt. It is consumed and cannot be reused. Operation 2 has no authority
or ledger row and remains locked. No historical RC operation identifier can be reused on RC-10.

## Budget and execution envelope

- 500 VND atomic reservation per operation;
- 1,250 VND maximum for the entire window;
- one image, maximum 2048 by 2048, detail `high`;
- input accounting ceiling 16,384 tokens;
- output ceiling 4,096 tokens;
- provider HTTP timeout 90 seconds;
- controller hard envelope 120 seconds;
- concurrency one;
- one attempt, no automatic retry;
- no fallback model or provider;
- window and budget day must both be 2026-09-02 UTC.

Checked-in runtime defaults remain zero-budget and disabled. During the single authorized attempt,
500 VND was reserved and `125.181420 VND` was charged from actual usage; reserved VND returned to
zero. The bundle is unmounted after the attempt, so no further reservation, credential read or
provider call is authorized by this artifact.

## Completed activation and result

All of the following were verified before Operation 1 execution:

1. governance-only RC-10 rebind PR #37 received a separate G-08 and merged;
2. exact governance-main CI `33532594395` completed successfully on its exact merge commit;
3. executable-RC CI run `33527973264` and governance-main CI verified as distinct roles;
4. the governance diff is allowlisted and both commits have identical executable-tree hashes;
5. the runtime executes exact immutable RC-10;
6. the raw bundle, exact tag, exact commit, execution-scope, budget, asset and RightsRecord hashes
   match;
7. G-01-A, G-02-A and G-03-A records verify and are unexpired;
8. current UTC time is inside the bound four-hour window and the same UTC budget day;
9. the exact RC-10 operation-1 ID received a separate owner approval;
10. operation 1 was unconsumed and a 500 VND atomic reservation succeeded without exceeding 1,250
    VND;
11. the secret alias exists without exposing its value;
12. operation 2, retry, fallback, publish, deploy, public ingress and production analytics remain
    disabled.

The one attempt completed in `27,790.325 ms` without timeout, retry or fallback. Strict structured
output, request/response hashes, provider request metadata, usage/cost receipt, RightsRecord,
durable ledger, closed circuit, duplicate blocking and secret containment all passed. The runner
then stopped and unmounted the gate. Operation 2 authority cannot be inferred from this outcome.

## Historical lineage

RC-9 operation 1 remains `BLOCKED_PRE_CALL`, not consumed, with zero provider calls, zero reservation
and zero VND; its authority is retired. RC-9 operation 2 remains locked. Earlier provider attempts
retain their historical verdicts. RC-10 Operation 1 is a real-provider PASS and is consumed;
aggregate Vision remains 1/2 consecutive PASS, while Operation 2 is not approved/locked and no
production-path or quality axis is promoted.
