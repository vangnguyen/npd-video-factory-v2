# V3-01 RC-6 Vision acceptance window

## Decision boundary

```text
RC: vf-v3-01-rc6 / 8df74a202dc2160e9358ca4cc9be54d989af2292
RC STATUS: LOCKED, NO-GO, NOT DEPLOYED
G-08 PR #29: CONSUMED
G-01-A / G-02-A / G-03-A: REBOUND TO EXACT RC-6
GOVERNANCE BUNDLE: VERIFIED OFFLINE; UNMOUNTED
RC-6 OPERATION 1 AUTHORITY: GRANTED, THEN RETIRED AFTER FAIL-CLOSED BLOCK
RC-6 OPERATION 1 RESULT: BLOCKED PRE-CALL / NOT CONSUMED
RC-6 OPERATION 2 AUTHORITY: NOT GRANTED; NOT EXECUTED
EXTERNAL EXECUTION: false
PAID EXECUTION: false
CHECKED-IN BUDGET: 0 VND
GLOBAL KILL SWITCH: engaged
OPENAI CALLS IN THIS CHECKPOINT: 0
ACTUAL COST: 0 VND
DURABLE LEDGER: 0|0|0|0
```

On 2026-08-30, the separately approved operation-1 runner passed outer preflight and then rejected
the authority before reading the credential, reserving budget, creating a durable operation or
sending a provider request. The immutable RC-6 runner expected a private limits dictionary with
legacy field `reservation_vnd` and omitted the owner-approved
`acceptance_window_limit_vnd=1250`. The authority correctly retained that window cap, so the exact
dictionary comparison returned `OPERATION_AUTHORITY_LIMITS_MISMATCH / BLOCKED_0_CALL`.

This is an authority-contract mismatch, not an OpenAI error and not a provider-runtime-path error.
Operation 1 remains not consumed because no provider call, reservation or ledger row exists, but its
RC-6 authority/window is retired and must not be reused. The secret-free receipt is
[`operation-1-blocked-0-call.json`](evidence/rc6-openai-vision-operation-1/operation-1-blocked-0-call.json).

PR #29 merged V3-01-13 as
`8df74a202dc2160e9358ca4cc9be54d989af2292`. Exact-main CI run `33261962445` passed
Python, Studio, Renderer, Safety/Compose and Docker deterministic E2E. Annotated tag
`vf-v3-01-rc6` peels to that exact merge commit; tag object
`b285bfec8c7f398d56ec513cf35cd6f14fb5c596` records `NO-GO` and no provider execution.

V3-01-13 remediates only the future evidence-serialization path. It does not reconstruct or
promote the incomplete RC-5 operation-1 record. That historical operation remains permanently:

```ini
provider_execution = SUCCESS
acceptance_evidence = INCOMPLETE
verdict = REVIEW_REQUIRED
consumed = true
```

RC-5 operation 2 was never approved and is permanently locked. No RC-3, RC-4 or RC-5 operation
identifier can be reused in RC-6.

## Exact RC-6 scope

| Field | Bound value |
|---|---|
| Provider | `openai-vision` |
| Model | `gpt-5-mini` |
| Capability | `vision` |
| Credential reference | `secret://openai/codex-video` only; no value is stored or read |
| RC tag | `vf-v3-01-rc6` |
| RC commit | `8df74a202dc2160e9358ca4cc9be54d989af2292` |
| Asset | `g03-a-owned-vision-test.png` |
| Asset SHA-256 | `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e` |
| RightsRecord canonical SHA-256 | `f469930a74b477751fc4417774b486ccbf2d7822487478875e099552c83e06ba` |
| Execution-scope SHA-256 | `7bb1058dd7f3a15a68e206c5c8dea0e627918bc20a69af86b1d583aebedbd028` |
| Raw bundle SHA-256 | `186ce157e94cbb2f321dbdcf59df1eb80d6d6df84fb5eca5422f4f5b94ba38f9` |
| UTC window | `2026-08-30T14:00:00Z` through `2026-08-30T18:00:00Z` |
| Vietnam time | `21:00 30/08/2026` through `01:00 31/08/2026` |

The verified bundle is
[`V3-01-GATE-RC6-OPENAI-VISION-A.json`](V3-01-GATE-RC6-OPENAI-VISION-A.json).
It embeds exact copies and canonical hashes of the three rebound approval records:

- G-01-A: `V3-01-APP-026`, SHA-256
  `750e6ba038b19d046c4557d9e1ef4cbab19b219fb9c98439b69bc795c0e3be42`;
- G-02-A: `V3-01-APP-027`, SHA-256
  `d09de056d518b190278a54a97b18688f50f2db93353c9edded8d419b28675037`;
- G-03-A: `V3-01-APP-028`, SHA-256
  `e1e5701bdd19169300cc8be0fbfc8c6b61464112bc42e03799f241424873467b`.

These records implement the owner-approved post-PR29 rebind sequence. They do not authorize an API
call by themselves.

## Immutable operations

The executable derivation helper produced exactly:

1. `v3-01-rc6-openai-vision-call-01`
2. `v3-01-rc6-openai-vision-call-02`

Both operation IDs have no durable consumption row. Operation 1 received one separate bounded owner
authority but stopped pre-call; that authority is retired and cannot be reused after executable
remediation. Operation 2 was never authorized and remains locked.

## Budget and execution envelope

- 500 VND atomic reservation per operation;
- 1,250 VND maximum for the entire window;
- one image, maximum 2048 by 2048, detail `high`;
- input accounting ceiling 16,384 tokens;
- output ceiling 4,096 tokens;
- timeout 60 seconds;
- concurrency one;
- one attempt, no automatic retry;
- no fallback model or provider;
- window and budget day must both be 2026-08-30 UTC.

Checked-in runtime defaults remain zero-budget and disabled. The envelope cannot be used until the
exact operation has separate owner authority and every loader, hash, time, rights, budget and
duplicate-operation check passes.

## Required activation conditions for RC-6 operation 1

Every condition must hold simultaneously. Any failure means zero calls:

1. the governance-only RC-6 rebind PR is merged and exact-main governance regression passes;
2. the runtime executes exact immutable RC-6;
3. the raw bundle hash, exact tag, exact commit and execution-scope hash match;
4. G-01-A, G-02-A and G-03-A records verify and are unexpired;
5. current UTC time is inside the bound four-hour window;
6. the exact RC-6 operation-1 ID is separately approved by the owner;
7. operation 1 is unconsumed and a 500 VND atomic reservation succeeds;
8. the exact asset and RightsRecord hashes match;
9. no retry, fallback, second operation, publish, deploy or analytics action is enabled.

The historical RC-6 activation reached condition 6, then failed closed on the authority-limits
contract before credential read or condition 7 reservation. The bundle was mounted only inside the
isolated runner process, no budget was committed, no API call occurred and the production verdict
remains **NO-GO**. Any future attempt requires V3-01-14 merge, a new locked RC, new operation IDs,
new scope/window and new owner authority.
