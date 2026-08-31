# V3-01 RC-7 Vision acceptance window

## Decision boundary

```text
RC: vf-v3-01-rc7 / 94170ed42f6ffba4432f29750402eafe0d922a45
RC STATUS: LOCKED, NO-GO, NOT DEPLOYED
G-08 PR #31: CONSUMED
G-08 PR #32: CONSUMED; GOVERNANCE-ONLY MERGE ebe6f91a9ac88364a23871d587ae4564f30283d3
G-01-A / G-02-A / G-03-A: REBOUND TO EXACT RC-7
GOVERNANCE BUNDLE: VERIFIED; EPHEMERALLY MOUNTED FOR OPERATION 1; UNMOUNTED AFTERWARD
RC-7 OPERATION 1: FAILED — PROVIDER_TIMEOUT; CONSUMED; REVIEW_REQUIRED
RC-7 OPERATION 2: NOT APPROVED; LOCKED; NOT EXECUTED
EXTERNAL EXECUTION: false after the bounded process ended
PAID EXECUTION: false after the bounded process ended
CHECKED-IN BUDGET: 0 VND
GLOBAL KILL SWITCH: engaged
CREDENTIAL: alias resolved only inside the bounded process; no value recorded
PROVIDER ATTEMPTS: 1; request delivery UNKNOWN_POSSIBLY_SENT
ACTUAL COST: UNKNOWN
SAFETY CHARGE: 500 VND; not an actual-cost receipt
PRODUCTION: NO-GO
```

PR #31 merged V3-01-14 as
`94170ed42f6ffba4432f29750402eafe0d922a45`. Exact-main CI run `33321003243` passed
Python, Studio, Renderer, Safety/Compose and Docker deterministic E2E. Annotated tag
`vf-v3-01-rc7` peels to that exact merge commit; tag object
`14e1c09550aaa92c937e275bbe8d1e38c6ed8b8c` records `NO-GO` and no provider execution.

PR #32 later merged governance-only as `ebe6f91a9ac88364a23871d587ae4564f30283d3`
without changing the executable RC. The owner then separately authorized operation 1 for the bound
window. It ran once and timed out at the 60-second provider boundary. The operation is consumed,
retry is forbidden, operation 2 remains locked, actual provider cost is unknown and the durable
500 VND amount is a conservative safety charge only. See
[`36_V3_01_15_PROVIDER_TIMEOUT_EVIDENCE_RUNTIME.md`](36_V3_01_15_PROVIDER_TIMEOUT_EVIDENCE_RUNTIME.md).

V3-01-14 introduces one canonical authority-limits model shared by the verified bundle loader and
the operation runner. It preserves distinct `per_operation_limit_vnd=500` and
`acceptance_window_limit_vnd=1250` authority fields, while the latter is projected to the legacy
same-UTC-day durable ledger only after the bundle proves the window cannot cross a UTC day. The
authority input does not accept `daily_limit_vnd` or `reservation_vnd` aliases.

## Exact RC-7 scope

| Field | Bound value |
|---|---|
| Provider | `openai-vision` |
| Model | `gpt-5-mini` |
| Capability | `vision` |
| Credential reference | `secret://openai/codex-video` only; no value is stored or read |
| RC tag | `vf-v3-01-rc7` |
| RC commit | `94170ed42f6ffba4432f29750402eafe0d922a45` |
| Asset | `g03-a-owned-vision-test.png` |
| Asset SHA-256 | `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e` |
| RightsRecord canonical SHA-256 | `f469930a74b477751fc4417774b486ccbf2d7822487478875e099552c83e06ba` |
| Execution-scope SHA-256 | `60d9898de38f9536ed3391ca81f1d59eca04b61537edad42e85597702c143a56` |
| Raw bundle SHA-256 | `ce772a941766b12a99943b9165cbf588c314e3d1b59543f103c7671a58856a44` |
| UTC window | `2026-08-31T14:00:00Z` through `2026-08-31T18:00:00Z` |
| Vietnam time | `21:00 31/08/2026` through `01:00 01/09/2026` |

The verified bundle is
[`V3-01-GATE-RC7-OPENAI-VISION-A.json`](V3-01-GATE-RC7-OPENAI-VISION-A.json).
It embeds exact copies and canonical hashes of the three rebound approval records:

- G-01-A: `V3-01-APP-030`, SHA-256
  `afe4eed1dc19106bfe79b8fa4fd0fead493ed503a094591c4d11750e14cb3c19`;
- G-02-A: `V3-01-APP-031`, SHA-256
  `acb037fbbd670972d2f0186db30adb6ebde944e4ddbb49b8f33f5e7540316638`;
- G-03-A: `V3-01-APP-032`, SHA-256
  `52f8f88a15ad8c0c07fc88e2387d00ac056fe2c0f54c5ead7e0e4ee07bec9609`.

These records implement the owner-approved post-PR31 rebind sequence. They do not authorize an API
call by themselves.

## Immutable operations

The executable derivation helper produced exactly:

1. `v3-01-rc7-openai-vision-call-01`
2. `v3-01-rc7-openai-vision-call-02`

Operation 1 has one durable timed-out attempt and is consumed. Its authority is retired and it cannot
be retried. Operation 2 has no runtime authority or execution row and remains locked. No RC-3,
RC-4, RC-5, RC-6 or RC-7 operation identifier can be reused by a later release candidate.

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
- window and budget day must both be 2026-08-31 UTC.

Checked-in runtime defaults remain zero-budget and disabled. Operation 1 used this envelope once.
Its durable ledger committed the 500 VND safety charge after the timeout, but no usage receipt exists
and actual provider cost therefore remains unknown. The envelope and operation authority are retired.

## RC-6 historical lineage

RC-6 operation 1 remains permanently recorded as:

```ini
verdict = BLOCKED PRE-CALL
provider_calls = 0
actual_cost_vnd = 0
operation_consumed = false
authority = RETIRED
ledger = 0|0|0|0
```

RC-6 operation 2 was never authorized and remains locked. The RC-6 authority is not reusable even
though operation 1 was not consumed.

## Historical activation outcome

The owner authority required these conditions to hold simultaneously before operation 1:

1. the governance-only RC-7 rebind PR is merged and exact-main governance regression passes;
2. the runtime executes exact immutable RC-7;
3. the raw bundle hash, exact tag, exact commit and execution-scope hash match;
4. G-01-A, G-02-A and G-03-A records verify and are unexpired;
5. current UTC time is inside the bound four-hour window;
6. the exact RC-7 operation-1 ID is separately approved by the owner;
7. operation 1 is unconsumed and a 500 VND atomic reservation succeeds without exceeding 1,250 VND;
8. the exact asset and RightsRecord hashes match;
9. no retry, fallback, second operation, publish, deploy or analytics action is enabled.

The runner passed preflight, mounted the bundle ephemerally, resolved the credential alias and entered
the provider path exactly once. It then reached the 60-second timeout without a provider request ID,
usage receipt, request hash, response hash or structured response. Request delivery cannot be proven
either way. The operation was durably recorded as timed out and consumed; no retry or fallback ran.
The activation scope was closed immediately afterward and operation 2 remained locked.

The frozen classification is `provider execution = FAILED — PROVIDER_TIMEOUT`,
`acceptance = INCOMPLETE / REVIEW_REQUIRED`, `actual cost = UNKNOWN`, `safety charge = 500 VND` and
production **NO-GO**. RC-7 is closed and no authority from this window is reusable.
