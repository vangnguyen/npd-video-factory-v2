# VF-ASR-RC25-01 — RC-25 governance-only closure candidate

Status: `PASS_RC_ONLY / GOVERNANCE_CLOSURE_CANDIDATE`

This record materializes the immutable source-only RC tag and prepares one
governance/evidence-only closure commit. It does not grant provider execution
authority, create an ASR operation, create a runtime activation, or claim final
dual-CI provenance.

## Immutable RC-25 identity

- Pre-materialization main: `ce0b2b802de5c5e6dda72b87dd29bf6a6c6d9b4a`
- Exact-main CI: `36799233422` (`PASS 5/5`, `1493 passed`)
- Tag: `vf-v3-01-rc25` (annotated)
- Tag object: `9eff204f296fea0ff3149298710e0e9c3c329f02`
- Dereferenced commit: `ce0b2b802de5c5e6dda72b87dd29bf6a6c6d9b4a`
- Canonical executable-tree SHA-256:
  `ffae5c544da9521bee97db78229f653e58083fdef7035ea5cd910b891651dfdb`
- GitHub workflows tree object:
  `a7acb6b4574314f2a603fff276ddb03ce95e41e4`
- Executor composite tree SHA-256:
  `4bef029adeb1e3a0d8c99e51b4715bb89ae08c30b103471e9680e2f8e83f8da9`

The tag is a source-only lineage marker. It carries no provider authority,
Operation 1, Operation 2, RuntimeActivationBinding, O2, execution window,
credential resolution, budget reservation, catalog entry, or provider call.

## Executable RC CI

- Workflow: `Video Factory V2 CI`
- Role: `executable_rc`
- Run: `36802107109`
- Ref: `refs/tags/vf-v3-01-rc25`
- Event: `workflow_dispatch`
- Expected SHA: `ce0b2b802de5c5e6dda72b87dd29bf6a6c6d9b4a`
- Checked-out SHA: `ce0b2b802de5c5e6dda72b87dd29bf6a6c6d9b4a`
- Result: `PASS 5/5`
- Regression: `1493 passed`

This run is independent of exact-main run `36799233422`. Final
`governance_main_ci` does not exist yet and may only be collected after a
separate Owner-approved merge of this governance-only commit.

## Bound qualified infrastructure

- Execution-plane promotion SHA-256:
  `4a1d5da4874dad20269a1b01dd4df83e07707fc489274e68659de729a415defd`
- Qualification evidence manifest SHA-256:
  `830a1429c4587a2c086c3730e6653cd9490f4ee9635cdc75ca53f83f096c7038`
- Private execution workflow commit:
  `25e5ff0905333cb6633fedc3d0ce0ff48f3d1e97`
- Installed wrapper SHA-256:
  `cd2946e06dd72fe5c1d5dc4d75fce17b81da3f5d01b6a290deb34644012c419c`
- Qualification run: `36800456572`, `E1–E10 PASS`
- E7: `PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED`
- Custody database: `vf_provider_custody_v3_01`
- Custody binding SHA-256:
  `c8d2761e3a5f6f835d6562665aac3eb175b5387bacc9e9e2daa5433c36b00e27`
- Runner: `ID 6 / npd-vf-executor-ubuntu-02`, `OFFLINE / SAFE`
- Kill switch: `ENGAGED`
- PostgreSQL runtime role: `vf_executor_runtime = NOLOGIN`
- Real RuntimeActivationBinding: `NOT_CREATED`
- Resolver: `INACTIVE`
- Execution catalog: `ABSENT`

The RC-only provenance artifact is
[`rc25-provenance.json`](../../../../../evidence/v3-01/vf-asr-rc25-01/rc25-provenance.json),
SHA-256
`7edf1079142b1ebbe80f46373debee7e3b62b099756d60e7bd5a6b4effccdc1c`.

## Historical RC-24 boundary

RC-24 remains `CANCELLED_NO_DISPATCH / RETIRED_FOR_EXECUTION`. Its operation
authority, O2, runtime activation, execution catalog, and execution request are
historical, immutable, and non-transferable. This candidate does not mutate or
reuse any RC-24 execution artifact.

## Boundaries and next gate

- ASR acceptance lineage created: `NO`
- Operation 1 / Operation 2 created: `NO / NO`
- Operation binding or manifest created: `NO`
- G-01 / G-02 / G-03 created: `NO`
- Bundle or loaded scope created: `NO`
- Runtime activation, authority, or O2 created: `NO / NO / NO`
- Provider credential reads: `0`
- Provider calls: `0`
- Budget reserved: `0 VND`
- Ledger writes: `0`
- Operation consumption: `0`
- Actual cost: `0 VND`
- RC-24 mutation: `NONE`
- Production: `NO-GO`

Next required lifecycle step: obtain a separate Owner decision for controlled
merge of the exact governance-only PR head. After that merge, run fresh exact
governance-main CI and build final canonical dual-CI provenance. Only a final
`DUAL_CI_PROVENANCE = PASS` may unblock preparation of a fresh ASR lineage and
Operation 1. This candidate must not claim final dual-CI PASS.
