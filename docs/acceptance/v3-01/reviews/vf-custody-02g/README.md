# VF-CUSTODY-02G — clean custody-only O1 candidate

Status: **SOURCE-SIDE PASS / OWNER O1 REQUIRED / NO O2 OR EXECUTION AUTHORITY**.

This candidate is based directly on canonical main
`7c023307d6a1e56a732a6ca96235a7ab3b32a253`. It ports only the standalone
PostgreSQL custody qualification module and its tests from custody source commit
`9853ac271973f70e72e8bf2d6865ca359a3bad60`; it does not port that commit's
executor-qualification changes or any earlier runner/topology work from PR #91.

The source contract binds PostgreSQL 16.15, database
`vf_provider_custody_v3_01`, schema `public`, migration head
`0015_v3_01_dispatch`, the six ProviderSafetyRepository tables, dedicated
PostgreSQL service/socket identity, and strict SELECT-only qualification in a
`REPEATABLE READ, READ ONLY` transaction. `CustodyBinding` rejects extra
operation, O2, execution-window, bundle, authority, and credential fields;
`AUTHORITY_GRANTED` is fixed to `NO`.

The previously qualified custody instance remains identified by system ID
`7690544205041130268`, database OID `16386`, and custody-binding SHA-256
`c8d2761e3a5f6f835d6562665aac3eb175b5387bacc9e9e2daa5433c36b00e27`.
Its PostgreSQL package identity is `16.15-1.pgdg24.04+2`. This split neither
recreates the instance nor changes its records.

Local validation on executable source commit
`46027ef75d070030fcd8f545ee3b3c43a11fadc6` passed:

- focused custody and immutable-MinIO contract tests: 23 passed;
- full Python regression: 1136 passed;
- complete migration replay: `0001` through `0015_v3_01_dispatch`, downgrade to
  base, and re-upgrade to `0015_v3_01_dispatch`;
- acceptance evidence/matrix validation: 39 evidence runs and 60 matrix rows;
- patch secret scan: no matches;
- executable-tree SHA-256:
  `451b1656ff9ce7b8df613c8a798ec3883e05185d8e3f97becd8595117a98d396`.

GitHub-hosted exact-head run `36424025792` passed all five jobs, including
Docker deterministic E2E. Its identity step recorded
`EXPECTED_HEAD_SHA=46027ef75d070030fcd8f545ee3b3c43a11fadc6` and
`CHECKED_OUT_SHA=46027ef75d070030fcd8f545ee3b3c43a11fadc6`. A final exact-head run is required
after this bounded evidence commit; the run output, rather than a self-referential
source file, is the authority for the final branch-head equality.

The only non-custody runtime dependency is the immutable public MinIO image
recorded in [DEPENDENCY_REVIEW.md](DEPENDENCY_REVIEW.md). It was added only after
the canonical-main Quay digest failed anonymously with `unauthorized` in run
`36422599029`. No executor qualification, organization-runner adaptation,
provider workflow, dispatch enablement, live E1-E10 promotion, or runner
provisioning is present.

Zero-call invariants remain: provider calls 0, credential reads 0, budget
reserved 0 VND, operation consumption 0, actual cost 0 VND, RC-22 mutation
none, O2 no, and runner activation no. PR #91 remains Draft and unmerged.
