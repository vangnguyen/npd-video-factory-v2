# V3-01-28 — ASR Canonical Custody Source Remediation

## Decision and boundary

Status: **SOURCE REMEDIATION / NO RC / NO AUTHORITY / ZERO PROVIDER CALL**.

VF-ASR-SR-01 starts from canonical `main`
`10a0384f18a0d6148ac3ba73d47589cfef7d8f4a`. Its pre-change canonical executable-tree
SHA-256 is `66fee79a310c1ba03bc0640bcc1630f65d1671df476074bbca2b1cd96754d541`, and its
pre-change executor composite-tree SHA-256 is
`e4572e70be156c917892d15cbcc0eedff95627d8c30cfc085b7234f7ab42a0cd`.

This change repairs source contracts only. It does not create RC-23, consume an RC name, create an
operation or authority, install O2, mount an execution bundle, enable dispatch, or change RC-22.
Production remains **NO-GO**.

## Independent trust domains

The runtime must receive two independently loaded and independently SHA-256-verified bindings. One
object must not be overloaded to represent both operation authority and PostgreSQL custody.

### Operation/execution binding

The operation binding identifies the future governed operation. Its fields are operation scoped,
including the RC tag and commit, governance main commit, canonical executable tree, executor
composite tree, acceptance lineage and sequence, provider/model/capability/language, slot,
operation key, execution-plane promotion, authority receipt, bundle, prepared and execution scope,
and the prompt/asset/reference/rights bindings.

The operation binding does not define a database, PostgreSQL system identifier, database OID,
socket, schema, migration head, service account, database role, backup, or restore identity. It
cannot grant custody access or provider authority by itself.

### Canonical custody binding

Infrastructure custody is supplied by the existing strict `CustodyBinding` contract and bound by
the exact SHA-256
`c8d2761e3a5f6f835d6562665aac3eb175b5387bacc9e9e2daa5433c36b00e27`.
The canonical database is `vf_provider_custody_v3_01`; it is not derived from an RC tag or
acceptance lineage. The custody binding owns the PostgreSQL major/minor/package and system
identity, database OID, schema, migration head, Unix socket, data and backup roots, service
identity, required table set, database roles, and backup/restore evidence.

The canonical interface is an exact `load_operation_binding(...)` plus an exact
`load_custody_binding(...)`. Host admission binds their paths and hashes independently. A
per-operation catalog cannot replace the protected host custody binding. Check-only qualification
uses `vf_custody_qualifier`; a separately authorized future execution uses
`vf_executor_runtime`. This remediation neither enables runtime LOGIN nor authorizes dispatch.

## Shared-custody isolation

Canonical custody is durable infrastructure shared by sequential future RC/lineage operations.
Its whole database is not required to be virgin for every new lineage. A valid completed operation
from an unrelated lineage is historical state and does not, by itself, block a later fresh
operation.

Fresh-operation validation remains fail closed and read only. It must reject:

- the exact operation ID or an exact-operation lineage mismatch;
- an exact attempt collision or an attempt bound to the wrong lineage;
- a provider-request receipt or idempotency-key collision;
- a conflicting active reservation or incompatible in-flight operation;
- invalid global control, budget, or circuit state;
- the wrong database name, database OID, PostgreSQL system identifier, socket identity, migration
  head, service UID/GID, socket ownership/mode, or custody-binding hash.

The global control row and historical counts may advance normally when internally consistent.
Check-only validation performs no INSERT, UPDATE, DELETE, DDL, reservation, operation consumption,
or provider action. Historical per-RC databases remain historical evidence; no RC-22 operation is
reconstructed or imported into canonical custody.

## Dispatch contract

The canonical bootstrap, check-only path, and future single-dispatch adapter consume the same exact
operation binding, canonical custody binding, and execution-plane qualification promotion. There
is no parallel dispatch path. Existing limits remain `attempts=1`, `concurrency=1`, `retry=0`, and
`fallback=0`.

The custody split is not authority. All future dispatch prerequisites, including exact dual-CI
provenance, a fresh qualified execution plane, an active bundle and explicit O2, remain required.

## Dual-CI invariant

VF-ASR-SR-01 preserves the established dual-CI architecture:

- `executable_rc_commit != governance_main_commit`;
- the RC executable tree and governance-main executable tree are byte-identical;
- executable-RC CI and governance-main CI have distinct successful run IDs;
- the governance closure changes only allowlisted non-executable paths.

A payload that uses the same commit for both roles is `CI_PROVENANCE_INVALID`, even if it supplies
two run IDs. Different commits with executable-tree drift, a non-allowlisted governance path, or
one CI run reused for both roles also fail closed. Different commits, byte-identical executable
trees, an allowlisted governance-only diff, and two distinct successful CI runs are the required
PASS shape. The same-commit failure is resolved by lifecycle ordering, never by weakening
validation.

## Required post-remediation lifecycle

The future governed sequence is exactly:

1. Merge this source remediation into `main` only after Owner O1 approval.
2. Run exact-main CI and require PASS.
3. Re-qualify the execution plane against that exact main commit and its newly calculated trees.
4. Create a fresh RC from that exact executable main.
5. Dispatch and require a distinct executable-RC CI run.
6. Create one governance-only main closure commit after RC creation.
7. Limit the closure diff to allowlisted non-executable governance paths.
8. Prove the closure leaves the executable tree byte-identical to the RC.
9. Run and require a fresh, distinct governance-main CI run.
10. Validate the complete dual-CI provenance contract.

No operation or provider authority exists until step 10 passes. The preferred closure changes only
`docs/acceptance/v3-01/...` and `evidence/v3-01/...`. It must not change application/runtime code,
workflow definitions, Docker/deployment configuration, packages, renderers, services, or
production configuration. An approved test-only path is permitted only when separately proven
non-executable under the canonical tree contract.

## Qualification invalidation

This remediation changes executable source. The existing execution-plane promotion
`5bb03bde3fc00b85b0dbfa9c44c3fc15153d7b8fed81f84765c18016edbf0ae6` is therefore marked:

`VALID_FOR_PREVIOUS_EXECUTABLE_TREE_ONLY`

It cannot authorize the post-merge source tree. A controlled merge must be followed by fresh
exact-main execution-plane qualification and a freshly sealed promotion before any new RC
authority preparation.

## Zero-use invariants and stop condition

Throughout this source-remediation task:

- real provider calls = 0;
- provider credential reads = 0;
- budget reserved = 0 VND;
- operation consumption = 0;
- actual cost = 0 VND;
- bundle mounted = NO;
- kill switch = ENGAGED;
- RC-23 created = NO;
- RC-22 mutation = NONE;
- O2 = NO.

After the scoped source, tests, Docker E2E, migration replay, secret scan, scope review,
provenance, G-08 and exact-head CI pass, this work stops at
`READY_FOR_OWNER_O1_ASR_SOURCE_REMEDIATION`. It does not merge, create RC-23, create authority, or
request O2.
