# VF-V0S-B3 — Bootstrap source candidate

Source-only / zero-call. Owner exact-head G-08 and CI review are required.
No merge or RC creation is performed.

- [Source review](G08_SOURCE_REVIEW.md)
- [WSL Git RCA](WSL_GIT_RCA.md)
- [Local validation environment RCA](LOCAL_VALIDATION_RCA.md)
- [Read-only evidence audit](validate_candidate.py)
- [Isolated PostgreSQL check](postgres_candidate_check.py)
- [Evidence bundle](../../../../../evidence/v3-01/vf-v0s-b3-20260914-bootstrap-candidate/README.md)

PostgreSQL tooling requires explicit --confirm-isolated-candidate-test and a new
--test-sequence, uses only a supplied private Unix peer socket and refuses existing
test databases. Synthetic rc19/rc20 labels in tests are not tags, release candidates,
operation manifests or authority records. Test databases are preserved, not promoted.

The initial offline helper hit ConfigParser percent interpolation on a percent-
encoded Unix socket URI before migrations. The helper was corrected to escape
percent characters; no production migration/source or validator change was needed.
One empty failed-test catalog database is retained. Two new isolated databases
passed full PostgreSQL upgrade/downgrade/replay and custody checks.

Local E2E initially selected a Linux Docker CLI without a Compose plugin; it failed
before container creation. The unchanged script's DOCKER_BIN hook was used with the
verified Desktop CLI and an empty task-specific Docker configuration. No login,
workflow/source/concurrency edit or test bypass occurred.
