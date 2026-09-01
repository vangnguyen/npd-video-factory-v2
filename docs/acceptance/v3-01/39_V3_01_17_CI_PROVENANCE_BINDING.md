# V3-01-17 CI provenance binding remediation

## Outcome

V3-01-17 is a source-only, zero-call remediation for the RC-9 bootstrap blocker. The blocked
operation did not reach the provider path: no credential value was read, no reservation or ledger
row was created, no OpenAI request was dispatched and no VND cost was incurred.

```text
RC-9 operation 1: BLOCKED_PRE_CALL; NOT CONSUMED; AUTHORITY RETIRED
Provider calls: 0
Reservation / actual cost: 0 VND / 0 VND
Ledger: 0|0|0|0
RC-9 operation 2: LOCKED
Production: NO-GO
```

The blocker was an authority-contract ambiguity, not an OpenAI or Vision-adapter failure. The old
bootstrap had one CI field but two legitimate provenance roles:

| Role | Exact commit | Video Factory V2 CI run | Result |
|---|---|---:|---|
| executable RC | `256bda59eed028ddd642cdb0988c409c489fd655` | `33449162326` | completed, success, 5/5 jobs |
| governance main after PR #35 | `e48d7edebcbfb1bd4113c2e40ab4ce46c186f6e4` | `33499392585` | completed, success, 5/5 jobs |

Neither run may substitute for the other.

## Canonical contract

`ProviderAcceptanceCiProvenance` is the single strict model shared by the collector and future
acceptance bootstrap. It requires separate `executable_rc_ci` and `governance_main_ci` records,
each bound to its exact role, run ID and 40-character commit SHA. Both runs must be the exact
`Video Factory V2 CI` workflow, complete successfully and report every job successful.

The contract also requires:

- distinct run IDs and commits for the two roles;
- the complete, sorted governance diff between the locked RC and governance commit;
- every changed path to be within the explicit test, acceptance-doc or evidence allowlist;
- independently collected Git object IDs for the canonical executable paths at both commits;
- equal executable-tree SHA-256 values;
- strict JSON types and no legacy `exact_main_ci_run_id` or extra fields;
- a stable provenance SHA based on the immutable GitHub CI completion timestamps.

The zero-call collector is `scripts/v3_01_ci_provenance.py`. It can read Git/GitHub metadata only;
it has no code path for credential resolution, budget reservation, provider execution, deployment,
publishing or ingress activation.

## Verified historical diagnosis

The canonical collector validated the two historical runs and produced:

```text
executable tree SHA-256: b57ef070664067f789424bf58f482f40087160a0e446e3e02aa2b1d45b4d9f53
governance executable tree SHA-256: b57ef070664067f789424bf58f482f40087160a0e446e3e02aa2b1d45b4d9f53
dual-CI provenance SHA-256: 95af692024f6573b839d8df384c02bf08581cef59b255b216c225bbde0b039e0
verdict: PASS
credential reads / provider calls / reservation: 0 / 0 / 0 VND
```

This proves that both CI runs were valid for their separate roles and that PR #35 did not change
the selected executable tree. It does not retroactively authorize or execute RC-9 operation 1 and
does not promote any real-provider, production-path or quality axis.

Evidence:

- [`operation-1-blocked-0-call.json`](evidence/rc9-openai-vision-operation-1/operation-1-blocked-0-call.json)
- [`operation-1-blocked-secret-scan.json`](evidence/rc9-openai-vision-operation-1/operation-1-blocked-secret-scan.json)
- [`dual-ci-provenance-pass.json`](evidence/rc9-openai-vision-operation-1/dual-ci-provenance-pass.json)

## Fail-closed coverage

Deterministic tests cover valid dual provenance plus swapped IDs, one run used for both roles,
stale governance CI, wrong authority commit, failed/incomplete CI, a governance runtime-file
change, executable-tree drift, missing fields, a legacy single CI field, non-canonical paths,
extra fields, and incomplete or malformed Git object maps.

## Next gate sequence

V3-01-17 changes executable contract code, so RC-9 is retired for future live acceptance. After a
separate G-08 review and merge:

```text
exact-main full regression
-> lock vf-v3-01-rc10
-> derive fresh RC-10 operation IDs
-> create a dual-CI provenance record for the exact RC/governance pair
-> create new scope, bundle and dated window
-> rebind G-01-A / G-02-A / G-03-A
-> request separate RC-10 operation-1 authority
```

RC-9 authority and operation IDs must not be reused. Operation 2 remains locked. No provider call,
deployment, public ingress, publishing or production analytics action is authorized by this
remediation.
