# VF-ASR-EXEC-WRAP-SR-01 scope manifest

Base: `616aea759aa94ec49eaafca4a30031429c32147c`

Allowed source scope:

| Path | Classification | Reason |
| --- | --- | --- |
| `scripts/provider-execution-wrapper.sh` | REQUIRED_RUNTIME_SECURITY | Replace the removed root `expire` action with the fixed PostgreSQL-user systemd failsafe preflight. |
| `apps/api/tests/test_execution_activation_host_controls.py` | REQUIRED_SECURITY_TEST | Enforce the exact systemctl path/unit, ordering, role gate, and signal cleanup contract. |
| `apps/api/tests/test_provider_execution_wrapper.py` | REQUIRED_SECURITY_TEST | Exercise fail-closed preflight and cleanup behavior with an isolated synthetic child. |
| `docs/acceptance/v3-01/reviews/vf-asr-exec-wrap-sr-01/*` | REVIEW_EVIDENCE | Record bounded scope, non-authority boundary, and validation contract. |

Explicitly excluded:

- `runtime_activation_host.py` or `runtime_role_failsafe.py` changes;
- provider workflow or private executor workflow changes;
- provider adapter, custody, resolver, or operation-identity changes;
- RC-25 materialization or RC-24 mutation;
- execution-plane promotion, O2, execution catalog, or live activation;
- provider credential resolution, reservation, ledger write, provider call, or
  production business write.

The private executor workflow remains
`25e5ff0905333cb6633fedc3d0ce0ff48f3d1e97`; a private workflow rebind is not
required by this candidate.
