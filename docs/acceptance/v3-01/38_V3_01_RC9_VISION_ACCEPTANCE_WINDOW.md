# V3-01 RC-9 Vision acceptance window

The decision boundary below is the historical pre-operation snapshot. The authoritative final
window outcome is recorded at the end of this document.

## Decision boundary

```text
RC: vf-v3-01-rc9 / 256bda59eed028ddd642cdb0988c409c489fd655
RC STATUS: LOCKED, NO-GO, NOT DEPLOYED
G-08 PR #34: CONSUMED
G-08 GOVERNANCE REBIND PR: PENDING
G-01-A / G-02-A / G-03-A: REBOUND TO EXACT RC-9
GOVERNANCE BUNDLE: VERIFIED OFFLINE; CHECKED IN; NOT MOUNTED
RC-9 OPERATION 1: NOT APPROVED; NOT EXECUTED
RC-9 OPERATION 2: NOT APPROVED; LOCKED; NOT EXECUTED
EXTERNAL EXECUTION: false
PAID EXECUTION: false
CHECKED-IN BUDGET: 0 VND
GLOBAL KILL SWITCH: engaged
CREDENTIAL: alias only; value not read or recorded
PROVIDER CALLS: 0
RESERVATION / ACTUAL COST: 0 VND / 0 VND
PRODUCTION: NO-GO
```

PR #34 merged V3-01-16 as
`256bda59eed028ddd642cdb0988c409c489fd655`. Exact-main CI run `33449162326` passed
Python, Studio, Renderer, Safety/Compose and Docker deterministic E2E. Annotated tag
`vf-v3-01-rc9` peels to that exact merge commit; tag object
`0a6d091eb22b9d313a2e6894e5abf379bfa0d504` records `NO-GO`, no provider execution and the
requirement for a fresh G-02 and operation authority.

V3-01-16 supplies one canonical timeout model across settings, verified gate loading, authority
limits, runner, provider adapter, controller and timeout evidence. The provider HTTP timeout is
90 seconds and the controller hard envelope is 120 seconds. The invariant is strict:
`provider_http_timeout_seconds < controller_hard_timeout_seconds`. Legacy single-timeout input,
missing or extra fields, wrong types, equal values and reversed values fail closed. The operation
lease derives from the controller envelope so it cannot expire before the hard boundary.

The owner approved G-02 for the exact RC-9 scope and window without increasing the existing VND
envelope. The approval is budget-and-timeout authority only. It does not authorize operation 1,
operation 2, a credential read, a provider call or any production action.

## Exact RC-9 scope

| Field | Bound value |
|---|---|
| Provider | `openai-vision` |
| Model | `gpt-5-mini` |
| Capability | `vision` |
| Credential reference | `secret://openai/codex-video` only; no value is stored or read |
| RC tag | `vf-v3-01-rc9` |
| RC commit | `256bda59eed028ddd642cdb0988c409c489fd655` |
| Asset | `g03-a-owned-vision-test.png` |
| Asset SHA-256 | `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e` |
| RightsRecord canonical SHA-256 | `f469930a74b477751fc4417774b486ccbf2d7822487478875e099552c83e06ba` |
| Budget-envelope canonical SHA-256 | `e48c7b634d9dc6b2903b932c69c99dd2f7884bd930da4896e54be74bf05ddc6c` |
| Execution-scope SHA-256 | `f3ff461f27537700160b1ec417905c2bb98aeb874c1e39981762bf4ac32970d4` |
| Raw bundle SHA-256 | `965ed58e4d1c73e3452aedd90e367ed6ec84d85bff1a9fdd11afe5d7cd64155f` |
| UTC window | `2026-09-01T14:00:00Z` through `2026-09-01T18:00:00Z` |
| Vietnam time | `21:00 01/09/2026` through `01:00 02/09/2026` |

The verified bundle is
[`V3-01-GATE-RC9-OPENAI-VISION-A.json`](V3-01-GATE-RC9-OPENAI-VISION-A.json).
It embeds exact copies and canonical hashes of the three rebound approval records:

- G-01-A: `V3-01-APP-034`, SHA-256
  `5efa58a263793a99acc5bc967c0ae6b7c14b0f688dc574d33f3af9e24af61e81`;
- G-02-A: `V3-01-APP-035`, SHA-256
  `9ca16aba47e6819f5432efc531e643aa51da32ecd2c2551d5ccc9f35f73c4d0b`;
- G-03-A: `V3-01-APP-036`, SHA-256
  `756cc075e64934055012db5637839b298d96769ef5d22a9258b2f6d054e31b78`.

These records implement the owner-directed post-PR34 rebind sequence. They do not authorize an API
call by themselves. Any mutation of the exact RC, provider, model, capability, asset, RightsRecord,
budget, timeout envelope, operation IDs, scope hash or window invalidates the current binding.

## Immutable operations

The executable derivation helper produced exactly:

1. `v3-01-rc9-openai-vision-call-01`
2. `v3-01-rc9-openai-vision-call-02`

Neither operation has runtime authority or a durable execution row. Operation 1 requires a separate
owner decision after this governance PR merges and exact-main governance regression passes.
Operation 2 remains locked. No RC-3, RC-4, RC-5, RC-6, RC-7 or RC-8 operation identifier can be
reused on RC-9.

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
- window and budget day must both be 2026-09-01 UTC.

Checked-in runtime defaults remain zero-budget and disabled. Increasing the timeout does not increase
the cost envelope. The bundle remains unmounted, so no reservation, credential read or call is
possible from the checked-in governance artifact.

## Required activation sequence

All of the following must happen before operation 1 can be considered for execution:

1. this governance-only RC-9 rebind PR receives a separate G-08 and merges;
2. exact-main governance regression passes without changing the executable RC-9 tree;
3. the runtime executes exact immutable RC-9;
4. the raw bundle, exact tag, exact commit, execution-scope, budget, asset and RightsRecord hashes
   match;
5. G-01-A, G-02-A and G-03-A records verify and are unexpired;
6. current UTC time is inside the bound four-hour window and the same UTC budget day;
7. the exact RC-9 operation-1 ID receives a separate owner approval;
8. operation 1 is unconsumed and a 500 VND atomic reservation succeeds without exceeding 1,250 VND;
9. the secret alias exists without exposing its value;
10. operation 2, retry, fallback, publish, deploy, public ingress and production analytics remain
    disabled.

If any condition fails, the result must be zero calls. After any authorized operation-1 attempt, the
runner must stop and return evidence for review; it may not infer authority for operation 2.

## Historical lineage

RC-7 operation 1 remains consumed and `REVIEW_REQUIRED` after one provider timeout; actual cost is
unknown and its 500 VND ledger amount is a safety charge only. RC-7 operation 2 is locked. RC-8 is
retained as NO-GO evidence that a shared provider/controller deadline was unsuitable and has no live
authority. RC-9 supersedes that timeout architecture only; it does not upgrade any real-provider,
production-path or human-quality acceptance axis.

## Final window outcome

The governance-only PR #35 merged as
`e48d7edebcbfb1bd4113c2e40ab4ce46c186f6e4`, and its Video Factory V2 CI run
`33499392585` completed successfully with 5/5 jobs. A later separate owner decision authorized only
RC-9 operation 1 inside this window.

Manual preflight stopped at the inner runner before credential read, reservation, ledger mutation
or provider dispatch. The bootstrap bound the executable RC CI run `33449162326`, while the
launcher supplied governance-main CI run `33499392585`; both runs were legitimate but represented
different roles that the old single field could not express.

```text
RC-9 OPERATION 1: BLOCKED_PRE_CALL; NOT CONSUMED; AUTHORITY RETIRED
PROVIDER CALLS / ATTEMPTS: 0 / 0
RESERVATION / ACTUAL COST: 0 VND / 0 VND
LEDGER: 0|0|0|0
RC-9 OPERATION 2: LOCKED
PRODUCTION: NO-GO
```

No current authority from this window may be reused. V3-01-17 provides a dual-CI provenance
contract offline; because it changes executable contract code, future live acceptance requires a
new RC-10, fresh operation IDs/scope/window, G-01-A/G-02-A/G-03-A rebind and separate operation-1
authority. See [`39_V3_01_17_CI_PROVENANCE_BINDING.md`](39_V3_01_17_CI_PROVENANCE_BINDING.md).
