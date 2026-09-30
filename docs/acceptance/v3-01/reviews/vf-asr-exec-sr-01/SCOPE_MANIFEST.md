# VF-ASR-EXEC-SR-01 scope manifest

The candidate is based directly on canonical main
`ebfc20dc8cb46a1d95493e2bfc37c2723100ce9c`.

## Runtime and security

- `apps/api/app/provider_secret_resolver.py` — strict one-shot AF_UNIX
  resolver protocol and systemd credential service.
- `apps/api/app/runtime_activation.py` — strict non-authorizing activation
  binding and exact context/window checks.
- `apps/api/app/runtime_activation_host.py` — fixed root-only PostgreSQL
  `LOGIN`/`NOLOGIN` lifecycle and crash/expiry cleanup.
- `apps/api/app/executor_execution.py` — requires activation and the privileged
  resolver; accounts for one successful in-memory handoff.
- `apps/api/app/provider_runtime_bootstrap.py` and
  `apps/api/app/provider_single_dispatch.py` — exact live role privilege audit
  before the secret boundary.
- `apps/api/app/executor_provenance.py` and
  `apps/api/app/executor_qualification.py` — persistent exact Git trust,
  without `safe.directory=*` or caller-selected paths.

## Host controls

- `deploy/executor/npd-vf-secret-resolver.{socket,service}`
- `deploy/executor/npd-vf-runtime-role-failsafe.{service,timer}`
- `deploy/executor/npd-vf-provider-execution.sudoers`
- `scripts/provider-secret-resolver-installed.py`
- `scripts/runtime-activation-installed.py`
- `scripts/provider-execution-wrapper.sh`
- `scripts/provision-execution-activation.sh`
- `.github/workflows/video-factory-provider-execution.yml`

These files install fixed commands and paths only. They create no operation
binding, authority, O2 window, live catalog entry, or provider secret.

## Tests

- `apps/api/tests/test_provider_secret_resolver.py`
- `apps/api/tests/test_runtime_activation.py`
- bounded additions to executor, provenance, and runtime-bootstrap tests.

No RC-23 artifact, approval, bundle, authority receipt, ledger row, RC tag, or
historical evidence file is modified by this candidate.
