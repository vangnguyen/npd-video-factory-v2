# G-08 source review — VF-ASR-SR-01

**PASS SOURCE-SIDE / FINAL EXACT-HEAD CI REQUIRED / READY FOR OWNER O1 ONLY
AFTER FINAL CI / NOT AUTHORITY.**

## Security and correctness conclusion

The source change is fail closed and keeps the two trust domains structurally
separate. `OperationBinding` rejects custody infrastructure fields;
`CustodyBinding` rejects operation, RC, authority, O2, window, bundle and
credential fields. Authority and operation-manifest JSON accept exact field
sets and only the canonical custody SHA may cross their boundary.

Canonical custody is fixed to binding
`c8d2761e3a5f6f835d6562665aac3eb175b5387bacc9e9e2daa5433c36b00e27`
and database `vf_provider_custody_v3_01`. Socket qualification resolves the
sealed PostgreSQL service user to the exact UID/primary GID, resolves the socket
group to the exact GID, then verifies canonical non-symlink paths, socket type,
ownership and modes. Database name/OID, system identifier, PostgreSQL 16.15,
role, schema and migration head remain independently verified.

Shared custody permits terminal unrelated history but requires a quiescent
global state. Exact operation, attempt, deterministic attempt usage-ID,
receipt, idempotency and lineage collisions fail closed. Active operations,
reserved budget, malformed receipts, inconsistent joined lineage, invalid
control/budget/circuit state and noncanonical identities fail before any secret
or provider boundary. The repository serializes dispatch-marker writes under
the global control lock and rejects reuse of a client-request ID owned by
another operation before mutation.

Check-only inspection executes one `REPEATABLE READ, READ ONLY` snapshot. Its
stateful session test records all 15 emitted SQL expressions plus both ORM
`get()` reads, permits only `SELECT`/transaction-control operations and proves
the associated state is unchanged. The canonical check-only adapter initializes
no engine, provider adapter or dispatch protocol after an earlier binding
failure and reports zero credential reads/provider calls.

Source-integrity tests cover exact HEAD and RC tag, clean worktree, canonical
executable tree, bound implementation presence/blob and exact import path. The
dual-CI tests preserve all required failures and the sole valid shape: distinct
commits, identical executable trees, allowlisted governance-only diff, and two
distinct successful CI runs.

## Evidence reviewed

- focused tests: `453 passed, 1 skipped`;
- full regression: `1427 passed, 1 skipped`;
- migration replay through `0015_v3_01_dispatch`, downgrade to base and replay:
  PASS;
- acceptance/evidence checks: PASS;
- secret scan: PASS;
- diff/scope check: PASS;
- independent code/spec review: no material findings;
- exact-head CI `36562480374`: PASS, five of five jobs;
- Docker deterministic E2E in `36562480374`: PASS;
- Python and Docker identity logs:
  `EXPECTED_HEAD_SHA == CHECKED_OUT_SHA == 0b0e481481fd31fea404755e06a9530aaf465d06`.

The source commit's canonical executable-tree SHA-256 is
`f92bd2acbb2c2bcfb98fbb737567d20b6551724e1c03c0574dfaa4f3733dce9a`;
the executor composite-tree SHA-256 is
`574bda3d7e5183287db486fa6e1075e7c49f472a95ad3898a79a71bfd7134092`.
The existing promotion `5bb03bde...0ae6` is valid only for the previous tree.

This technical G-08 does not approve a merge or grant O1, O2, provider
authority, an execution window, credential resolution, a reservation or an
operation. The review-document commit is non-executable; final exact-head CI
must pass on the resulting PR head before the stop state may become
`READY_FOR_OWNER_O1_ASR_SOURCE_REMEDIATION`.
