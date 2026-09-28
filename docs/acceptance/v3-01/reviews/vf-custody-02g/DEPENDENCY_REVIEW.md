# VF-CUSTODY-02G dependency and scope review

## Custody source isolation

Source commit `9853ac271973f70e72e8bf2d6865ca359a3bad60` changed five files. The clean
candidate ports only `apps/api/app/provider_custody.py` and
`apps/api/tests/test_provider_custody.py`. Those files import only Python
standard-library modules plus Pydantic and SQLAlchemy facilities already present
on canonical main. They do not import or call the changed executor qualification
module, executor plane, provider dispatch, runner admission, or workflow code.

The following paths from that commit are deliberately excluded:

- `apps/api/app/executor_qualification.py`;
- `apps/api/tests/test_executor_plane.py`;
- `apps/api/tests/test_executor_qualification_remediation.py`.

Therefore custody correctness has no dependency on the earlier executor commits
in PR #91, and importing unqualified executor behavior is unnecessary.

## Bounded supporting dependencies

| Exact file | Reason included | Why canonical main is insufficient | Activation analysis |
|---|---|---|---|
| `.github/workflows/ci.yml` | Records and enforces the workflow-dispatch expected SHA in both Python and Docker jobs. | Main did not provide the required `EXPECTED_HEAD_SHA == CHECKED_OUT_SHA` proof for a manually dispatched branch head. | GitHub-hosted CI metadata/check only; it does not target, install, or activate the self-hosted runner and grants no provider authority. |
| `docker-compose.yml` | Pins MinIO to the verified immutable public GHCR digest `sha256:d37f79cb57ba531f92eeaf2a1a0e5f827dea982a429bb5a2903043c57ed04528`. | Exact-head run `36422599029` failed before Docker E2E because canonical main's Quay dependency returned `unauthorized`. | Dependency substitution only; no credential, provider, executor, runner, or workflow-admission behavior is added. |
| `apps/api/tests/test_minio_ghcr_digest_contract.py` | Locks the exact GHCR registry/name/digest and rejects Quay and floating `latest`. | Main's old contract required the inaccessible Quay reference. | Test-only contract; it cannot activate runtime or external authority. |

No MinIO compatibility helper, registry workflow, executor topology, runner ID,
qualification promotion, provider workflow, or provider credential material is
included. The GHCR image was pulled without a registry login by successful
GitHub-hosted Docker E2E run `36424025792`.

## Diff conclusion

The candidate consists of the custody module/tests, exact-head CI evidence
support, the single unavoidable immutable MinIO dependency replacement, its
contract test, and these bounded review records. The split is technically
isolated from PR #91's live executor qualification work.
