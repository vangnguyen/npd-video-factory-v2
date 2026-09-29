# VF-ASR-SR-01 scope manifest

Base: `main@10a0384f18a0d6148ac3ba73d47589cfef7d8f4a`

Executable source commit:
`0b0e481481fd31fea404755e06a9530aaf465d06`

## Runtime and security source

| File | Classification | Exact dependency reason |
|---|---|---|
| `apps/api/app/executor_execution.py` | Runtime/security | Injects protected host custody independently from the operation catalog and binds the exact executor tree and qualification promotion. |
| `apps/api/app/executor_qualification.py` | Runtime/security | Enforces the canonical custody hash and rejects E3/E4/E8 when shared custody has active or reserved state. |
| `apps/api/app/provider_custody.py` | Runtime/security | Adds exact canonical receipt loading, named PostgreSQL service/group identity verification and quiescent shared-history semantics. |
| `apps/api/app/provider_runtime_bootstrap.py` | Runtime/security | Replaces the combined RC-derived ledger binding with separate operation and custody bindings and precise read-only shared-custody inspection. |
| `apps/api/app/provider_safety.py` | Runtime | Centralizes deterministic attempt usage-ID derivation so preflight can detect the repository key collision before dispatch. |
| `apps/api/app/provider_safety_repository.py` | Runtime/security | Rejects a globally duplicated dispatch client-request ID before mutating the second operation. |
| `apps/api/app/provider_single_dispatch.py` | Runtime/security | Uses both exact bindings in the sole canonical check-only/live adapter, rejects embedded custody identity and checks circuit state before credential access. |

All seven files are part of the canonical executable-tree contract.

## Test source

- `apps/api/tests/test_executor_execution.py`
- `apps/api/tests/test_executor_plane.py`
- `apps/api/tests/test_executor_qualification_remediation.py`
- `apps/api/tests/test_provider_ci_provenance.py`
- `apps/api/tests/test_provider_custody.py`
- `apps/api/tests/test_provider_runtime_bootstrap.py`
- `apps/api/tests/test_provider_single_dispatch.py`
- `apps/api/tests/test_provider_single_dispatch_check_only.py`

These files prove host custody cannot be overridden; exact identity/promotion
binding; the complete custody matrix; source/tree/blob guards; strict artifact
schemas; stateful zero-write check-only reads; global idempotency collision
rejection; pre-secret circuit handling; and all five required dual-CI cases.
They are excluded from the canonical executable-tree hash by the existing tree
contract.

## Documentation and review evidence

- `docs/acceptance/v3-01/66_V3_01_28_ASR_CANONICAL_CUSTODY_REMEDIATION.md`
- `docs/acceptance/v3-01/reviews/vf-asr-sr-01/README.md`
- `docs/acceptance/v3-01/reviews/vf-asr-sr-01/SCOPE_MANIFEST.md`
- `docs/acceptance/v3-01/reviews/vf-asr-sr-01/G08_SOURCE_REVIEW.md`
- `docs/acceptance/v3-01/reviews/vf-asr-sr-01/candidate-provenance.json`

Review evidence is non-executable. No workflow, migration, deployment, package,
renderer, service, production configuration, credential, RC, authority or
historical evidence file is changed.

## Explicit exclusions

- no RC-23 tag or branch;
- no operation/authority/O2 artifact;
- no reconstructed RC-22 rows or changed RC-22 evidence;
- no provider credential material or resolver activation;
- no workflow redesign or self-hosted runner activation;
- no database migration or canonical custody mutation;
- no dispatch-enabled catalog or production deployment.

Scope conclusion: **PASS — no unrelated dependency or activation behavior is
included**.
