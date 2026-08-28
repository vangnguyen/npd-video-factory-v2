# V3-01 RC-3 OpenAI Vision operation 1 evidence

## Verdict

```text
OPERATION: v3-01-g03a-openai-vision-call-01
RESULT: REVIEW_REQUIRED
REAL-PROVIDER ACCEPTANCE: NOT ACCEPTED
PRODUCTION VERDICT: NO-GO
OPERATION 2: NOT AUTHORIZED / NOT EXECUTED
RETRY: 0
DEPLOY / PUBLIC INGRESS / PUBLISH / PRODUCTION ANALYTICS: NONE
```

The owner-authorized operation was dispatched once at `2026-08-28T14:00:25.217418Z` on exact
immutable RC-3 `adde8d9c5a7f608db80cbd9d21aecd45f721065e`. It ended at
`2026-08-28T14:00:27.025598Z` with non-retryable `OpenAIVisionResponseError`. The execution did not
produce a structured frame, request/response hashes, provider receipt or usage receipt. It is a
failed real-provider attempt, not real-provider acceptance.

## Bound execution evidence

| Field | Evidence |
|---|---|
| RC | `vf-v3-01-rc3` / `adde8d9c5a7f608db80cbd9d21aecd45f721065e` |
| Governance main | `a73bad37f1f3aa7c2347e6a76503246a46d3c112` after PR #24 |
| Exact-main CI | run `33175813324`, 5/5 PASS |
| Runtime image | `sha256:9339c880b48c8e3e57a8acfa2f9f692d553d316ac265f1133076ba4e99b3eb8a` |
| Bundle SHA-256 | `da4450ce9f3c6f2015d2fbea3af8ca2ffb108c13dd53daafdad294570ecf4d83` |
| Execution-scope SHA-256 | `a5ba3e0e1e39384cb1d6beb892b3c85a2266ea30be436faed529d6fdfe8aa9a0` |
| Authority SHA-256 | `7d50e8c8fc394ef0c98eb788646831a8e9e65a394fc7f78980e96db9a04dcd87` |
| Asset SHA-256 | `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e` |
| Evidence SHA-256 | `e94fcafcbab8adefb9506cb91d98010cdb1713ba79ce209ec2dfdb154f97fd2d` |
| Python runner SHA-256 | `4e47d81a1466543c0b3594cf969fe75533704622954ea0cd8574300b0e4b292b` |
| One-shot launcher SHA-256 | `8edef27b051a023018991253644c64b67277d757e40d790f0c1b372f98801622` |

The exact evidence is under
[`evidence/openai-vision-operation-1`](evidence/openai-vision-operation-1/). The credential value is
not present in any artifact. The launcher passed it only through container stdin after every
preflight gate passed. The exact runner is retained under the `raw/` evidence subdirectory so the
repository's secret scanner does not misclassify its deliberately defensive credential-variable
handling as a stored secret; its recorded SHA-256 is unchanged.

## Durable safety result

| Control | Result |
|---|---|
| Preflight | exact RC/main/CI/image/bundle/scope/authority/asset/window PASS |
| Attempts | exactly 1 |
| Automatic retry | 0 |
| Model fallback | none |
| Operation status | `failed` |
| Attempt status | `failed`, non-retryable |
| Reservation | 500 VND |
| Safety-ledger charge | 500 VND, `estimated` |
| Actual provider cost | unknown; no usage receipt, therefore not accepted |
| Acceptance-window budget | 1,250 VND; 500 VND committed, 0 VND reserved after finish |
| Duplicate preflight | `DUPLICATE_OPERATION_BLOCKED` |
| Circuit | `closed`, consecutive failures `1` |
| Operation 2 ledger count | `0` |
| PostgreSQL | isolated, healthy, restart count `0`, no published port |
| Secret scan | value match `false`; key-pattern matches `0` |

The 500 VND ledger charge is conservative safety accounting when actual usage is unavailable. It
must not be represented as the provider's billed amount.

## Failure diagnosis

The adapter intentionally reduces provider failures to a secret-safe exception class and did not
retain a redacted HTTP error body. The exact server message is therefore unavailable in both the
local evidence and OpenAI Platform Logs.

A deterministic audit of the exact RC-3 generated JSON Schema found one violation:
`#/$defs/_ObjectOutput.track_hint` exists in `properties` but is absent from `required`. OpenAI's
[Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs)
requires every field to be required; an optional value must instead be a required union with
`null`. The request failed quickly and non-retryably before a response/usage receipt was produced.
This makes the schema violation the high-confidence cause, but it remains an inference rather than
a quoted provider error. See
[`schema-contract-audit.json`](evidence/openai-vision-operation-1/schema-contract-audit.json).

## Acceptance impact

- `VIS-01` real-provider-tested stays `NOT_TESTED`.
- `GAP-003`, `GAP-010` and `GAP-013` stay `IN_PROGRESS`.
- The call proves the RC-3 gate loader, atomic reservation, durable attempt ledger, duplicate guard,
  circuit update, rights binding and secret boundary operated fail-closed around one live attempt.
- It does not prove structured Vision output, actual VND cost, provider receipt, pixel/model quality,
  production path or human quality.
- Checked-in defaults, Compose, production and public routes were unchanged.

## Exact next remediation gate

Create a narrow, zero-call remediation proposal (suggested checkpoint `V3-01-11`) that:

1. makes `track_hint` required-but-nullable and validates every object schema has
   `properties == required` plus `additionalProperties=false`;
2. persists only a redacted provider error code/parameter and error-response hash for failed calls;
3. adds contract tests for exact request schema and error evidence without a credential or network;
4. receives a new G-08 before merge, then full exact-main regression;
5. locks a new RC because executable adapter code changes;
6. creates a new bound gate bundle, budget window and operation IDs before any later live attempt.

Operation 1 must never be retried or reused. Operation 2 under the RC-3 bundle remains locked and
must not be executed as a workaround.
