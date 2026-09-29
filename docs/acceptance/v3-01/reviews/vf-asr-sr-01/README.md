# VF-ASR-SR-01 — canonical custody source remediation

Status: **SOURCE-SIDE PASS / FINAL EXACT-HEAD CI REQUIRED / OWNER O1 REQUIRED**.

This clean Draft candidate starts directly from canonical
`main@10a0384f18a0d6148ac3ba73d47589cfef7d8f4a`. Executable source is sealed at
`0b0e481481fd31fea404755e06a9530aaf465d06` and changes only the existing
canonical bootstrap, custody, executor-adapter, provider-safety and
single-dispatch contracts needed by VF-ASR-SR-01. It does not create an RC,
operation, authority, O2, provider call, credential read, reservation or
production deployment.

The remediation separates operation/execution identity from infrastructure
custody. The former is an exact `OperationBinding`; the latter is the existing
strict `CustodyBinding`, loaded independently and fixed to:

- database: `vf_provider_custody_v3_01`;
- binding SHA-256:
  `c8d2761e3a5f6f835d6562665aac3eb175b5387bacc9e9e2daa5433c36b00e27`;
- migration head: `0015_v3_01_dispatch`;
- qualification role: `vf_custody_qualifier`;
- future runtime role: `vf_executor_runtime`.

Completed unrelated lineages are valid durable history. A fresh operation still
fails closed on an exact operation, attempt, deterministic usage-ID, receipt or
idempotency collision; lineage inconsistency; active reservation; outstanding
reserved budget; malformed global control/budget/circuit state; wrong
PostgreSQL/database/socket/service identity; or a noncanonical binding hash.
Check-only inspection uses one `REPEATABLE READ, READ ONLY` snapshot and cannot
reserve, consume, resolve a credential or cross the provider boundary.

## Source validation

Validation on executable source commit
`0b0e481481fd31fea404755e06a9530aaf465d06`:

- focused custody/bootstrap/dispatch/executor/provenance suite:
  `453 passed, 1 skipped`;
- full API/worker/bridge regression: `1427 passed, 1 skipped`;
- migration replay: `0001` through `0015`, downgrade to base, then re-upgrade
  to `0015_v3_01_dispatch`;
- acceptance register, ASR compatibility, Flow A/B/C and DR boundary checks:
  PASS with existing unapproved production gates remaining BLOCKED/NO-GO;
- repository secret scan: PASS, no matching token/private-key material;
- diff/scope review: PASS;
- independent correctness/security/spec review: no material findings;
- pre-seal exact-head CI `36562480374`: PASS, five of five jobs including
  Docker deterministic E2E.

Both the Python and Docker jobs in run `36562480374` record:

`EXPECTED_HEAD_SHA == CHECKED_OUT_SHA == 0b0e481481fd31fea404755e06a9530aaf465d06`

with `EVENT_NAME=workflow_dispatch` and
`HEAD_IDENTITY=EXACT_HEAD_CANDIDATE`.

## Tree identity and governance boundary

- canonical executable-tree SHA-256:
  `f92bd2acbb2c2bcfb98fbb737567d20b6551724e1c03c0574dfaa4f3733dce9a`;
- `.github/workflows` Git tree object:
  `e2048a15188852df9f6c43ecd1ae982ee56b4588`;
- executor composite-tree SHA-256:
  `574bda3d7e5183287db486fa6e1075e7c49f472a95ad3898a79a71bfd7134092`.

The current execution-plane promotion
`5bb03bde3fc00b85b0dbfa9c44c3fc15153d7b8fed81f84765c18016edbf0ae6`
is `VALID_FOR_PREVIOUS_EXECUTABLE_TREE_ONLY`. A fresh exact-main
qualification/promotion is mandatory after an Owner-controlled merge.

The dual-CI architecture remains unchanged: the future executable RC and
governance-main closure must be distinct commits, their executable trees must
be identical, their successful CI runs must be distinct, and the intervening
diff must be allowlisted governance-only content. The lifecycle is documented
in `66_V3_01_28_ASR_CANONICAL_CUSTODY_REMEDIATION.md`.

This review commit contains only non-executable documentation. A final
workflow-dispatch CI run must bind the resulting exact PR head. Its run ID and
exact-head equality are recorded externally in the PR conversation and task
handoff to avoid a self-referential source commit.

Zero-use invariants remain: provider calls 0, provider credential reads 0,
budget reserved 0 VND, operation consumption 0, actual cost 0 VND, bundle
mounted NO, kill switch ENGAGED, RC-23 not created, RC-22 mutation NONE, O2 NO,
and production NO-GO.
