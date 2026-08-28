# V3-01-11 — Structured Output and Error Evidence Remediation

## Decision boundary

```text
CHECKPOINT: V3-01-11
SCOPE: ZERO-CALL STRUCTURED OUTPUT AND ERROR-EVIDENCE REMEDIATION
IMPLEMENTED / MOCK-TESTED: PASS ON EXACT MAIN
REAL-PROVIDER ACCEPTANCE: NOT TESTED
PRODUCTION-PATH ACCEPTANCE: NOT TESTED
QUALITY ACCEPTANCE: NOT TESTED
EXTERNAL CALLS: 0
ACTUAL COST: 0 VND
G-08 FOR THIS REMEDIATION: CONSUMED — V3-01-APP-018 / PR #26
RC-4: LOCKED AT 061ca5d03248d6721ef8dc7a53cf4608e7ebe79e; NOT LIVE-ELIGIBLE
PRODUCTION VERDICT: NO-GO
```

PR #25 was merged as evidence/governance only at main
`2ab6b51d63b86c7e4cc9febe347929d8cc3f2e38`. It records RC-3 operation 1 as
`REVIEW_REQUIRED`; it does not convert that attempt into accepted real-provider, production-path or
quality evidence. Operation 1 remains consumed and old RC-3 operation 2 remains locked.

V3-01-11 changed executable adapter and durable-state code, so it could not run on RC-3 authority.
PR #26 merged after `V3-01-APP-018`; exact-main regression and GitHub CI run `33189441083` passed
5/5, and annotated tag `vf-v3-01-rc4` now points to exact main
`061ca5d03248d6721ef8dc7a53cf4608e7ebe79e`. No provider call occurred during remediation.

The RC-4 post-lock audit then found a separate fail-closed blocker: executable operation IDs still
named RC-3. RC-4 is therefore retained as evidence of blocker detection and must not be used for
live acceptance. V3-01-12 addresses only that RC-bound allowlist contract.

## Confirmed root cause

The exact RC-3 generated JSON Schema had one deterministic strict-contract defect:

```text
#/$defs/_ObjectOutput.track_hint
property exists: yes
required: no
nullable: yes
```

OpenAI Structured Outputs requires every object property to appear in `required`; semantic
optionality is represented by a required nullable type. The relevant official references are the
[Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) and
[API reference](https://developers.openai.com/api/reference/overview). The first failed operation
did not retain the provider's redacted error fields, so the schema defect remains a deterministic,
high-confidence diagnosis rather than a quoted provider response.

## Remediation implemented

### Strict schema

- `_ObjectOutput.track_hint` is now required and has type `string | null`.
- The adapter generates the schema once at initialization and rejects it before credential
  resolution or transport if any nested object is not strict.
- The recursive validator checks that every object has a properties object, a required array,
  exact `properties == required`, no duplicate required values and
  `additionalProperties=false`.
- Tests mutate nested schemas to prove missing, unknown and non-strict fields are rejected.

### Secret-free provider error evidence

Failed provider attempts can persist only a bounded `ProviderErrorEvidence` object:

- internal category and code;
- HTTP status;
- redacted provider error type, code, parameter and message;
- safe provider request ID and generated client request ID;
- SHA-256 of the response bytes;
- retryability flag;
- invariant `secret_recorded=false`.

Raw response bodies, request payloads, prompts, image bytes, credential aliases and credential
values are not persisted in this error record. Unsafe request IDs are replaced with a SHA-256
identifier. Provider text is length-bounded and credential patterns are redacted before model
validation; the durable model rejects residual credential-like material.

The response hash supports correlation without retaining the provider body. OpenAI documents
`x-request-id` as the provider request identifier and permits a caller-supplied
`X-Client-Request-Id`; the adapter now retains the safe forms of both for later support and incident
analysis.

### Failure classification

The adapter distinguishes:

| Category | Examples |
|---|---|
| `http_provider_error` | HTTP 400 schema rejection, 429, 5xx |
| `transport_timeout` | bounded request timeout |
| `transport_error` | network/transport failure |
| `response_parse_failure` | invalid JSON, wrong root, missing output text |
| `structured_output_refusal` | explicit provider refusal |
| `structured_output_incomplete` | incomplete response/status |
| `structured_output_validation` | JSON parses but violates the domain schema |
| `usage_receipt_missing` | successful structured output without usage |
| `usage_receipt_invalid` | malformed or over-limit usage |

Missing usage now fails closed instead of returning a successful result with a pending cost. The
central safety controller carries the structured error into the in-memory and PostgreSQL attempt
ledger. Migration `0012_v3_01_11` adds one nullable JSON column and is backward-compatible with
historical attempts.

## Deterministic validation

Local validation on the isolated remediation worktree:

| Check | Result |
|---|---|
| Focused OpenAI/provider safety tests | 39/39 PASS |
| Full Python/API/worker/bridge tests | 253/253 PASS |
| Studio tests and JavaScript syntax | 14/14 PASS |
| Alembic upgrade → downgrade base → upgrade | PASS through `0012_v3_01_11` |
| Acceptance repository/schema/evidence validation | PASS |
| Flow A/B/C and DR boundary evaluators | expected `BLOCKED` PASS |
| Docker Compose config | PASS |
| Fail-closed defaults / secret scan / `git diff --check` | PASS |
| Renderer/typecheck/bundle | PASS in exact-head and exact-main GitHub CI |

All provider tests use injected mock transport or local callables. No OpenAI credential was read,
no external request was made and no VND budget was enabled.

## Acceptance impact

- V3-01-11 may establish only implemented/mock-tested remediation evidence after exact-head CI.
- `VIS-01` real-provider-tested remains `NOT_TESTED`.
- `GAP-003`, `GAP-010` and `GAP-013` remain `IN_PROGRESS`.
- Actual provider cost for RC-3 operation 1 remains unknown; 500 VND remains only the conservative
  safety-ledger charge.
- RC-3 operation 1 can never be retried or reused.
- RC-3 operation 2 must not be executed.
- Production remains undeployed and `NO-GO`.

## Completed sequence and required next sequence

```text
V3-01-11 PR #26 + exact-head CI + G-08
→ merge + exact-main full regression
→ lock vf-v3-01-rc4
→ detect stale RC-3 operation IDs and retain RC-4 as blocker evidence
→ V3-01-12 zero-call remediation + separate G-08
→ merge only if approved + exact-main regression
→ lock vf-v3-01-rc5
→ derive RC-5 operation IDs
→ rebind G-01/G-02/G-03 to RC-5 and a new execution-scope hash/window
→ separate owner decision for RC-5 operation 1
```

No step in V3-01-11 authorizes a provider call, deployment, public ingress, publishing or
production analytics.
