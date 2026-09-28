# VF-EXECUTOR-05B clean executor scope manifest

Base: `main@50cb6d452ea64fbded31a8bfce86fc431835acc6`

This candidate is an executor-only extraction from the historical PR #91 line.
It does not include the custody implementation, custody tests, MinIO migration,
runner-21 bindings, or the obsolete personal-repository admission topology.

## Included files

### A. REQUIRED_EXECUTOR_RUNTIME

- `apps/api/app/data/executor/README.md` — immutable qualification fixture contract.
- `apps/api/app/data/executor/expired-loader-fixture.json` — expired, synthetic,
  non-authoritative E9 fixture.
- `apps/api/app/executor_execution.py` — root-bound execution entrypoint; remains
  denied without qualification promotion and later operation authority.
- `apps/api/app/executor_promotion.py` — independent zero-call qualification
  promotion verifier; it cannot grant provider authority.
- `apps/api/app/executor_qualification.py` — E1-E10 check-only qualification.
- `apps/api/app/executor_request.py` — immutable request-envelope validation.
- `apps/api/app/provider_single_dispatch.py` — minimum canonical dispatch
  integration needed for exact executor state transitions, final preflight,
  durable intent evidence, and fail-closed reservation reconciliation.
- `apps/api/pyproject.toml` — packages the immutable executor fixture.
- `scripts/executor-promote-installed.py` — installed-runtime promotion wrapper.
- `scripts/executor-qualify-installed.py` — installed-runtime qualification wrapper.
- `scripts/executor-request-installed.py` — installed-runtime execution wrapper.

### B. REQUIRED_EXECUTOR_SECURITY

- `.github/workflows/manual-provider-smoke.yml` — retires the legacy hosted paid
  provider path and fails closed before any secret or call.
- `apps/api/app/executor_provenance.py` — executable-tree identity calculation.
- `apps/api/app/executor_security.py` — independent hostile-job denial review.
- `scripts/executor-job-started.py` — exact repository/ref/workflow/SHA and
  qualification-only admission guard.
- `scripts/executor-job-started.sh` — fail-closed runner hook wrapper.
- `scripts/executor-security-review-installed.py` — installed-runtime security
  review wrapper.
- `scripts/provision-executor-quarantine.sh` — quarantine provisioning with an
  empty execution allowlist and engaged kill switch.

### C. REQUIRED_EXECUTOR_TEST

- `apps/api/tests/test_executor_execution.py`
- `apps/api/tests/test_executor_plane.py`
- `apps/api/tests/test_executor_promotion.py`
- `apps/api/tests/test_executor_provenance.py`
- `apps/api/tests/test_executor_qualification_promotion.py`
- `apps/api/tests/test_executor_qualification_remediation.py`
- `apps/api/tests/test_executor_security.py`

### D. REQUIRED_EXECUTOR_WORKFLOW

- `.github/workflows/video-factory-executor-qualification.yml` — the sole
  qualification workflow selected for zero-call activation.
- `.github/workflows/video-factory-provider-execution.yml` — governed execution
  definition retained for architecture completeness, but denied by the host
  qualification manifest and not run by VF-EXECUTOR-05B.

### E. HISTORICAL_EVIDENCE_ONLY

None. PR #91 remains the historical integration evidence and is not copied into
this merge candidate.

## F. EXCLUDE

- `apps/api/app/provider_custody.py` and custody tests/evidence: already canonical
  on main.
- PR #91 MinIO workflow, harness, contract, and digest changes: already canonical
  on main.
- PR #91 `ci.yml`: superseded by canonical main exact-head and Docker E2E jobs.
- Any hard-coded runner ID 21 or runner ID 6.
- Personal-repository runner admission and old runner provisioning.
- Historical RC-22 evidence and executor RCA documents not required at runtime.
- Live E1-E10 receipts: sealed outside the executable source tree, then recorded
  as bounded review evidence after qualification.

## Minimum non-executor dependency

`apps/api/app/provider_single_dispatch.py` is the only canonical provider module
changed. The executor calls its single-dispatch state machine and therefore
requires its transition callback, last-moment preflight, durable dispatch-intent
record, and ambiguous reservation reconciliation. These changes do not enable a
provider: the kill switch, admission manifest, qualification promotion,
operation authority, active bundle, and explicit execution workflow remain
independent mandatory gates.
