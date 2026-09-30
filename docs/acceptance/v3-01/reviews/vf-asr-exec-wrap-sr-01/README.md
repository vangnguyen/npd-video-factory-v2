# VF-ASR-EXEC-WRAP-SR-01 — root-wrapper expiry preflight remediation

Status: bounded source candidate. This review is not O1, O2, provider
authority, execution-plane qualification, an execution catalog, or an
execution window.

The candidate starts from exact canonical main
`616aea759aa94ec49eaafca4a30031429c32147c`. RC-24 remains immutable with
status `CANCELLED_NO_DISPATCH / RETIRED_FOR_EXECUTION`. Because this candidate
changes the executable tree, successful merge and fresh execution-plane
qualification must precede a new RC lifecycle.

## Root cause

The root provider-execution wrapper still called
`runtime-activation.py expire`. The root activation helper deliberately no
longer supports that action: expiry enforcement moved to the dedicated
`runtime-role-failsafe.py expire` helper, which systemd runs directly as
`postgres:postgres`.

The stale wrapper call therefore failed before a governed child could start.
Restoring the root expiry action or adding a nested UID transition would break
the approved privilege separation.

## Correction

The wrapper now starts the fixed systemd oneshot directly with:

`/usr/bin/systemctl start npd-vf-runtime-role-failsafe.service`

Neither the executable, action, nor unit is caller-selectable. A service
failure produces `RUNTIME_FAILSAFE_PREFLIGHT_FAILED` and stops before the
child boundary. Service success is not authority: the independent role-state
gate still requires a legitimate active LOGIN state. NOLOGIN produces
`RUNTIME_ACTIVATION_REQUIRED`.

Immediate root cleanup remains unchanged, including EXIT, HUP, INT, and TERM
handling. The periodic PostgreSQL-user failsafe remains the independent crash
and expiry backstop. No root expiry action, `runuser -u postgres`, sudo-to-
postgres, or `su` was introduced.

## Validation boundary

Focused tests cover the fixed command, failure-before-child behavior,
NOLOGIN rejection, synthetic LOGIN continuation, child success/failure
cleanup, fixed signal traps, and absence of credential, budget, or provider
transport work in the expiry preflight. The existing failsafe suite continues
to cover valid, expired, missing, malformed, symlinked, and writable markers,
session termination, and fixed PostgreSQL controls.

Synthetic host validation may temporarily install the candidate wrapper only
for zero-call scenarios. The pre-review live wrapper must be restored after
testing because this candidate has not received O1 merge approval.

The bounded host test passed NOLOGIN, valid synthetic LOGIN, expired marker,
missing marker, and malformed marker scenarios. The valid synthetic child
stopped at `BLOCKED_PRE_CALL / INPUT_FIELDS_INVALID` with zero provider calls,
credential reads, reservation, consumption, and cost. The original wrapper
was restored, and the final role was NOLOGIN with zero runtime sessions. The
root-only host log SHA-256 is
`5ee36cf95b01fb19f0d4e35fdea16a0f1484fa9219840d471e8f179f9d397cb8`.

The source candidate completed 38 focused wrapper/failsafe/activation tests,
the full Python regression (`1492 passed, 1 skipped`), migration replay through
`0015_v3_01_dispatch`, systemd unit verification, and the repository secret
scan. Docker deterministic E2E and exact-head identity remain CI gates; local
Docker was unavailable and is not represented as a local PASS.

## Zero-use boundary

Real provider calls, real provider credential reads, reservations, ledger
writes, operation consumption, and actual cost remain zero. The execution
catalog is absent, the runtime role ends NOLOGIN, the resolver ends inactive,
the kill switch remains engaged, and no O2 or promotion is created.
