# VF-EXECUTOR-05B G-08 executor review

Status: `SOURCE-SIDE PASS / LIVE QUALIFICATION PENDING`

## Fixed boundaries

- Canonical base: `50cb6d452ea64fbded31a8bfce86fc431835acc6`.
- Target runner identity is read from root-owned
  `/etc/npd-video-factory/executor.json`; production source does not hard-code
  runner ID 6.
- Qualification admission requires the private execution repository, main ref,
  exact workflow path and exact execution-repository workflow commit.
- Qualification mode requires an empty paid/provider execution allowlist.
- The kill switch must be `ENGAGED`.
- Qualification reads custody in a read-only transaction and does not create a
  reservation, consume an operation, or read provider credential plaintext.
- Promotion consumes separately sealed probe, hostile-job review, and evidence
  manifest artifacts. Raw probes cannot self-promote.
- `SELF_HOSTED_EXECUTION_PLANE_QUALIFIED` is explicitly not O2 and not provider
  authority.

## Hostile-job coverage

The source tests require denial of an unapproved repository, workflow, ref,
modified workflow, PR trigger, command injection, environment injection, stale
source commit, wrong executable-tree SHA, cross-runner receipt, and concurrent
attempt.

## Source validation

- Focused executor tests: `250 passed, 1 skipped`.
- Full regression: `1386 passed, 1 skipped`.
- Migration head: `0015_v3_01_dispatch`.
- Local Docker E2E: unavailable because no Docker CLI/daemon is installed; the
  canonical GitHub-hosted `Docker deterministic E2E` job is required before the
  final verdict.

## Pending before final PASS

- Immutable source commit and executable-tree SHA.
- Exact-head GitHub-hosted CI and Docker E2E.
- Exact candidate installation in the protected host root.
- Live E1-E10, hostile-job security review, independent promotion, safe runner
  shutdown, and sealed evidence hashes.

This review does not grant provider authority, O2, budget, operation
consumption, or RC-22 mutation.
