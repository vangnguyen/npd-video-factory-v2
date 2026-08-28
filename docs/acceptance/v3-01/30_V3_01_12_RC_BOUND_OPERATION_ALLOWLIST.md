# V3-01-12 — RC-bound Operation Allowlist

## Decision boundary

```text
CHECKPOINT: V3-01-12
SCOPE: ZERO-CALL EXECUTABLE OPERATION-ID REMEDIATION
BASE: vf-v3-01-rc4 / 061ca5d03248d6721ef8dc7a53cf4608e7ebe79e
RC-4 LIVE ACCEPTANCE: PROHIBITED
EXTERNAL EXECUTION: false
PAID EXECUTION: false
CHECKED-IN BUDGET: 0 VND
GLOBAL KILL SWITCH: engaged
CREDENTIAL READ: none
EXTERNAL CALLS: 0
ACTUAL COST: 0 VND
PRODUCTION VERDICT: NO-GO
```

PR #26 merged V3-01-11 at `061ca5d03248d6721ef8dc7a53cf4608e7ebe79e` after exact-main
CI run `33189441083` passed all five jobs. Annotated tag `vf-v3-01-rc4` peels to that exact
commit. RC-4 is retained as evidence of the fail-closed blocker described below; it must never be
used for live provider acceptance.

## Confirmed executable blocker

The RC-4 loader embedded the two RC-3 operation IDs as a module constant and required an exact
tuple match. Therefore a correctly new RC-4 bundle could not use new operation IDs, while the only
IDs accepted by executable code were consumed or locked RC-3 IDs. Reusing those IDs would violate
the owner decision and evidence lineage.

No governance-only bundle can correct an executable allowlist. The correct response is a new
zero-call executable remediation, a separate G-08 merge decision and a later locked RC.

## RC-bound identifier contract

V3-01-12 derives each identifier from the normalized exact RC tag, provider/capability namespace
and ordered slot:

```text
vf-v3-01-rc5 + openai-vision + vision + slot 1
→ v3-01-rc5-openai-vision-call-01

vf-v3-01-rc5 + openai-vision + vision + slot 2
→ v3-01-rc5-openai-vision-call-02
```

The ID is only one part of the binding. The verified bundle and execution-scope SHA-256 also bind:

- exact RC commit SHA and exact RC tag;
- provider `openai-vision`, model `gpt-5-mini` and capability `vision`;
- credential alias only, never a credential value;
- approved RightsRecord and asset SHA-256;
- ordered operation slot and operation type;
- dated activation/expiry window and UTC budget day;
- VND pricing, reservation, token/frame/dimension, timeout, retry and concurrency limits.

Every G-01/G-02/G-03 approval must contain the exact RC commit and identical execution-scope hash.
The deployment configuration must independently pin the raw bundle SHA-256 plus expected RC commit
and tag. Drift at any layer rejects the bundle before credential resolution or transport.

## Fail-closed behavior

- Slots are exactly `1` then `2`; any other value or order is invalid.
- RC-3 IDs presented in an RC-5 bundle are invalid.
- An otherwise valid old-RC bundle is rejected against the current expected RC identity.
- Provider, model, capability, asset, window or operation drift invalidates the approval scope.
- A consumed operation key remains blocked in both in-memory and PostgreSQL-backed controllers.
- No retry or model fallback is introduced.
- The historical RC-3 bundle remains immutable evidence and is not rewritten.

## Regression matrix

| Case | Expected result |
|---|---|
| derived RC-5 IDs with exact mock bundle | accept bundle while runtime execution stays disabled |
| RC-3 IDs on RC-5 | reject |
| correct ID with wrong expected commit | reject |
| correct commit with wrong expected tag | reject |
| wrong provider, model or capability | reject |
| slot outside `1,2` or wrong slot order | reject |
| duplicate consumed operation | reject |
| tampered operation ID | reject |
| expired acceptance window | reject |
| valid bundle from an older RC against RC-5 | reject |

All tests use Pydantic validation, mock callables or disposable SQLite. They read no credential,
perform no network request and spend 0 VND.

## Deterministic validation

Local evidence is retained as
[`EV-V3-RC-BOUND-ALLOWLIST-001`](../../../evidence/v3-01/vf-v3-01-20260828T170154Z-4ecc7ff/matrix/evidence-EV-V3-RC-BOUND-ALLOWLIST-001.json)
on code commit `4ecc7ff2e687879bdb1e5b5acb42a144cbe8b806`:

| Check | Result |
|---|---|
| Focused gate/provider/Vision tests | 59/59 PASS |
| Full Python/API/worker/bridge tests | 259/259 PASS |
| Studio tests and JavaScript syntax | 14/14 PASS |
| Renderer tests | 14/14 PASS |
| Renderer typecheck and bundle | PASS |
| Alembic upgrade → downgrade base → upgrade | PASS through `0012_v3_01_11` |
| Acceptance repository and Flow A/B/C/DR boundary validation | PASS with external axes still `BLOCKED` |
| Credential reads / external calls / VND spend | 0 / 0 / 0 |
| Compose and Docker deterministic E2E | pending exact-head GitHub CI |

These results establish only the implemented/mock-tested remediation contract. Exact-head CI and a
separate owner G-08 remain mandatory before merge.

## Required next sequence

```text
draft V3-01-12 PR
→ exact-head CI
→ separate owner G-08 review
→ merge only if approved
→ exact-main full regression
→ lock vf-v3-01-rc5
→ generate the two RC-5 operation IDs
→ rebind G-01/G-02/G-03, asset, scope hash and dated window
→ separate owner decision for RC-5 operation 1
```

No step in V3-01-12 authorizes an OpenAI call, credential read, deployment, public ingress,
publishing or production analytics.
