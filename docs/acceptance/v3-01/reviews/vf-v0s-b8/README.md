# VF-V0S-B8 — operation-bound bootstrap qualification

Verdict: **REVIEW_REQUIRED**.

The RC-19 operation, scope, immutable inputs and durable custody all revalidate,
but the verified bootstrap contract cannot represent a pre-authority
qualification. `BootstrapLedgerBinding` requires non-null
`authority_receipt_sha256` and `bundle_sha256` before the real bootstrap reaches
source or ledger validation. The CLI exposes only `ZERO_CALL_CUSTODY_ONLY`; it
has no verified `qualification`/`dry-run` mode that returns
`AUTHORITY_REQUIRED` after validating the operation-bound preparation package.

The real RC-19 entrypoint was invoked with the complete pre-authority binding in
this directory. Exactly the two deliberately absent fields failed validation:

- `authority_receipt_sha256`
- `bundle_sha256`

The safe CLI result was `BOOTSTRAP_BINDING_INVALID`, exit 2, with zero provider
calls and zero credential reads. No placeholder hash, historical RC-18
authority, fabricated receipt or preparation-template-as-runtime-bundle
substitution was used.

An independent `REPEATABLE READ, READ ONLY` query reconfirmed the canonical
PostgreSQL custody: control `global/revision=0`, all operation/attempt/budget/
circuit/usage/cost/idempotency tables empty, and numeric reservation zero. The
RC-19 operation therefore remains virgin and unconsumed; this does not turn the
bootstrap result into PASS.

Evidence: [VF-V0S-B8 bundle](../../../../../evidence/v3-01/vf-v0s-b8-20260915-operation-bootstrap-qualification/README.md).

No source/runtime fix is made in B8. Owner review must choose a separately
bounded path: either change the governance ordering so authority/final bundle
materialization precedes the existing custody bootstrap, or authorize a source
remediation adding a strict pre-authority qualification contract (which would
change the executable tree and require a fresh RC/rebind).
