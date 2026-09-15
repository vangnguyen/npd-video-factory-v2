# VF-V0S-B6 — RC-19 durable ledger custody

This evidence pack records the bounded creation and qualification of the fresh
RC-19 PostgreSQL custody environment. It contains no provider secret, provider
response, runtime bundle, Operation 1 identity, authority record, reservation,
or production write.

## Outcome

- Durable custody: **VERIFIED**.
- Derived database: `vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed` (exact match).
- PostgreSQL: 16.15, private Unix socket, peer authentication, no TCP listener.
- Canonical migration head: `0014_v3_01_27`; control seed: `global`, revision 0.
- State: `VIRGIN_READY_FOR_OPERATION_REBIND`; every provider-safety,
  provider-usage and idempotency table inspected has zero rows; reservation is 0.
- RC-18/RC-19 isolation: **PASS** (different cluster roots, system identifiers,
  databases and namespaces; RC-18 database is absent from the RC-19 cluster).
- Kill switch: `ENGAGED`; external/paid execution: false.

Overall verdict is **REVIEW_REQUIRED**, not PASS. The checked-in bootstrap
schema requires operation-specific fields (`operation_key`, authority receipt,
bundle, execution-scope and scope hashes) before the real entrypoint can run.
VF-V0S-B6 explicitly forbids creating the fresh Operation 1 identity/package.
The source guard, lineage derivation, database naming, socket custody, repository
schema and read-only custody primitives are verified, but a full operation-bound
RC-19 bootstrap invocation must follow the future rebind. No placeholder,
historical RC-18 identity or fabricated hash was used to force a PASS.

## Durable writes allowed by this task

- one new private PostgreSQL 16 cluster and exact RC-19 database;
- canonical migrations 0001 through 0014 and their existing control seed;
- one disposable migration-replay database, removed after `head → base → head`.

No operation row, attempt, budget day, circuit, provider usage, cost record,
idempotency key, bundle, authority or window was created.

## Evidence

- `baseline.json` — immutable Git/CI/provenance inputs.
- `custody-audit.json` — deterministic read-only custody audit.
- `migration-replay.json` — isolated migration replay and cleanup.
- `tests.json` — focused tests and validation results.
- `task-result.json` — final bounded decision and safety accounting.
- `SHA256SUMS.txt` — manifest for the evidence files above.

Reproduction helpers live under
`docs/acceptance/v3-01/reviews/vf-v0s-b6/`. Both helpers use an explicit empty
PostgreSQL password over the private peer-auth socket and remove password-related
environment variables. They do not resolve an OpenAI credential or enter a
provider execution path.

## Stop boundary

Do not create or activate authority, mount a bundle, reserve budget or access a
provider. Owner review is required to authorize the safe ordering: create a
fresh `PREPARED_NOT_AUTHORIZED` RC-19 Operation 1 rebind, then rerun the
operation-bound bootstrap qualification against this existing virgin custody.
