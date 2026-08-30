# V3-01-14 — Operation Authority Limits Contract Remediation

## Decision boundary

V3-01-14 is a source-only, zero-call remediation for the RC-6 fail-closed blocker. It does not
authorize or perform a credential read, provider request, budget reservation, deploy, public
ingress, publish or production analytics action.

```text
RC-6 operation 1: BLOCKED PRE-CALL / NOT CONSUMED
Provider requests: 0
Actual cost: 0 VND
Durable ledger: 0 operations | 0 attempts | 0 budget days | 0 circuits
RC-6 operation 2: LOCKED
Production: NO-GO
```

The preserved blocker receipt is
[`operation-1-blocked-0-call.json`](evidence/rc6-openai-vision-operation-1/operation-1-blocked-0-call.json).
It is evidence of correct fail-closed behavior only and changes no acceptance axis.

## Root cause

The verified RC-6 gate bundle contained both intentional G-02-A controls:

- `per_operation_limit_vnd = 500`;
- `acceptance_window_limit_vnd = 1250`.

The immutable RC-6 runner separately hard-coded an authority dictionary that used the legacy name
`reservation_vnd` and did not declare `acceptance_window_limit_vnd`. The approved authority retained
the window cap, so exact dictionary equality failed before any provider-side action. OpenAI did not
receive a request and the provider adapter did not fail.

Removing the window cap or weakening equality is explicitly prohibited. RC-6 remains immutable
blocker evidence and its authority must not be reused.

## Canonical contract

`ProviderOperationAuthorityLimits` in `provider_gate_loader.py` is now the one authority/runner
limits model. `ProviderGateBudgetEnvelope` is adapted into that model before the loader creates the
runtime gate scope, and future acceptance runners must validate their authority through
`validate_operation_authority_limits` before reading a credential.

The canonical JSON contract contains exactly:

| Field | Type/unit | RC-6 bounded value |
|---|---|---:|
| `currency` | literal string | `VND` |
| `images` | JSON integer | `1` |
| `max_dimension_pixels` | JSON integer | `2048` |
| `image_detail` | literal string | `high` |
| `input_token_ceiling` | JSON integer | `16384` |
| `max_output_tokens` | JSON integer | `4096` |
| `per_operation_limit_vnd` | canonical decimal string, VND | `500` |
| `acceptance_window_limit_vnd` | canonical decimal string, VND | `1250` |
| `timeout_seconds` | JSON integer | `60` |
| `max_concurrent_calls` | JSON integer | `1` |
| `max_attempts` | JSON integer | `1` |
| `automatic_retry` | JSON boolean | `false` |
| `model_fallback` | JSON boolean | `false` |

Unknown fields are forbidden. In particular, neither legacy `reservation_vnd` nor
`daily_limit_vnd` is accepted as authority input.

## Window versus durable daily limit

`acceptance_window_limit_vnd` is the owner-approved aggregate cap for the dated acceptance window.
`daily_limit_vnd` is only the existing durable-ledger column used at runtime. The verified bundle
already requires its window to stay within one UTC budget day. Only after that invariant passes does
the canonical adapter project the window cap onto the ledger's daily column. The authority cannot
supply or override a separate daily value, preventing accidental mapping of a broader daily budget
onto the narrower acceptance scope.

## Fail-closed coverage

`test_operation_authority_limits.py` runs completely offline against the checked-in RC-6 bundle and
proves:

- exact canonical authority limits pass;
- a missing `acceptance_window_limit_vnd` fails;
- legacy `reservation_vnd` fails;
- injected `daily_limit_vnd` fails;
- wrong JSON integer, boolean or VND amount types fail;
- wrong per-operation or window amounts fail;
- a window smaller than two allowlisted reservations fails;
- the exact RC-6 blocked authority shape reproduces the pre-call rejection;
- the loader's durable runtime scope derives its limits from the same canonical adapter.

No test resolves `secret://openai/codex-video`, opens a network transport or invokes the provider
adapter. Checked-in defaults remain external/paid execution false, budget 0 VND and global kill
switch engaged.

## Acceptance and rollback

V3-01-14 is acceptable for G-08 review only when focused and full repository CI pass, the historical
RC-6 receipt/raw evidence remain secret-free, and secret/path/link/diff checks pass. It grants no
runtime authority and does not promote real-provider, production-path or human-quality evidence.

Rollback is a normal revert of this source/docs PR. There is no production rollback because the PR
does not deploy or alter production state.

## Required next sequence

```text
G-08 review
→ merge V3-01-14
→ exact-main full regression
→ lock vf-v3-01-rc7
→ derive new RC-7 operation IDs
→ rebind G-01-A / G-02-A / G-03-A
→ create a new execution-scope hash and dated window
→ obtain separate owner authority for RC-7 operation 1
```

No RC-6 operation authority or identifier may cross that boundary. Production remains **NO-GO**.
