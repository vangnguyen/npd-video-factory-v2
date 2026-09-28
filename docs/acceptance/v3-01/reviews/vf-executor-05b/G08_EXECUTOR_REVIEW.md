# VF-EXECUTOR-05B G-08 executor review

Status: `SOURCE-SIDE PASS / LIVE QUALIFICATION BLOCKED_E7 / NOT READY FOR O1`

## Fixed boundaries

- Canonical base: `50cb6d452ea64fbded31a8bfce86fc431835acc6`.
- Target runner identity is read from root-owned
  `/etc/npd-video-factory/executor.json`; production source does not hard-code
  runner ID 6.
- Qualification admission requires the private execution repository, main ref,
  exact workflow path and exact execution-repository workflow commit.
- Private-repository E5 provenance is supplied by a root-owned operator artifact
  bound to the observed runner-group repository/workflow restrictions and exact
  execution-repository main commit; the runner receives no GitHub read token.
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

- Focused executor tests: `252 passed, 1 skipped`.
- Full regression: `1388 passed, 1 skipped`.
- Migration head: `0015_v3_01_dispatch`.
- Local Docker E2E: unavailable because no Docker CLI/daemon is installed; the
  canonical GitHub-hosted `Docker deterministic E2E` job is required before the
  final verdict.

## Candidate and live evidence

- Executable source commit:
  `cf55b47e5b33de183ef9c3f76993fbb65d63a6e9`.
- Executor executable-tree SHA-256:
  `b35b71396c295339f47803426bf608f7e6af60df5bd303baa03d635d12f41248`.
- Exact-head CI `36436731347`: PASS, including Docker deterministic E2E.
- `EXPECTED_HEAD_SHA == CHECKED_OUT_SHA == cf55b47e5b33de183ef9c3f76993fbb65d63a6e9`.
- Hostile-job security review: PASS; SHA-256
  `ac528669fa139f9598e30f0f4bea60107b5957bd1bb02892f268089fc9f4bd03`.
- Live runner qualification `36437615585`: E1-E6 and E8-E10 PASS; E7
  BLOCKED because no approved provider secret source exists on the host.
- Qualification receipt SHA-256:
  `0548b04beeef9041d497cbe925f8e9a942cf54b2007098adcf9b6aa2b8c09de4`.
- Probe manifest SHA-256:
  `355aa5a4238c770eba211e2d1e0ed1f6dee2f116603e2fcf1aa21f086d3db588`.
- Qualification promotion: NOT CREATED.
- Runner after the bounded run: Offline; listener stopped; service not
  installed; kill switch engaged.

## Final blocker

E7 must be rerun only after the Owner identifies an already-approved provider
secret source or separately authorizes creation of the intended binding. A
runner registration credential, synthetic placeholder, empty file, or custody
backup key is not an acceptable substitute. The qualification implementation
will stat the source but will not open or read credential plaintext.

This review does not grant provider authority, O2, budget, operation
consumption, or RC-22 mutation.
