# VF-ASR-EXEC-FS-SR-02 scope manifest

Base: `0723211c67d08d5dc886bce74f7559b50efedc89`

Allowed source scope:

| Path | Classification | Reason |
| --- | --- | --- |
| `apps/api/app/runtime_role_failsafe.py` | REQUIRED_RUNTIME_SECURITY | Dedicated postgres-identity, NOLOGIN-only expiry helper. |
| `apps/api/app/runtime_activation_host.py` | REQUIRED_RUNTIME_SECURITY | Atomic root:postgres marker custody and removal of the root expiry entrypoint. |
| `deploy/executor/npd-vf-runtime-role-failsafe.service` | REQUIRED_HOST_CONTROL | Runs the dedicated helper as postgres under retained/tighter sandboxing. |
| `scripts/provision-execution-activation.sh` | REQUIRED_HOST_PROVISIONING | Installs the dedicated helper without creating authority or activation. |
| `apps/api/tests/test_runtime_role_failsafe.py` | REQUIRED_SECURITY_TEST | Marker, fixed-SQL, expiry, session-termination, and negative-path contract tests. |
| `apps/api/tests/test_runtime_activation.py` | REQUIRED_SECURITY_TEST | Root marker custody, stale-state rejection, and immediate cleanup tests. |
| `apps/api/tests/test_execution_activation_host_controls.py` | REQUIRED_HOST_TEST | Static unit/provisioning hardening assertions. |
| `docs/acceptance/v3-01/reviews/vf-asr-exec-fs-sr-02/*` | REVIEW_EVIDENCE | Bounded scope and non-authority review. |

Explicitly excluded:

- provider workflow changes;
- private executor workflow rebinding;
- RC-25 materialization;
- RC-24 tag, authority, O2, bundle, or operation mutation;
- live execution catalog or resolver activation;
- provider credential resolution, budget reservation, ledger writes, provider
  transport, and production business writes.

The private workflow remains pinned separately at
`25e5ff0905333cb6633fedc3d0ce0ff48f3d1e97` and is outside this source PR.
