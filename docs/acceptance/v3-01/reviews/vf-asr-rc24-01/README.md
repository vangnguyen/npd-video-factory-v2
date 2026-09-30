# VF-ASR-RC24-01 — RC-24 governance-only closure candidate

Status: `PASS_RC_ONLY / GOVERNANCE_CLOSURE_CANDIDATE`

This record materializes the immutable source-only RC tag and prepares one
governance/evidence-only closure commit. It does not grant provider execution
authority, create a runtime activation, or claim final dual-CI provenance.

## Immutable RC-24 identity

- Pre-materialization main: `aaaaf3d09f433efe3499d6447d2715f00e4f9f17`
- Exact-main CI: `36650898059` (`PASS 5/5`)
- Tag: `vf-v3-01-rc24` (annotated)
- Tag object: `d897213308ed746d39009f9803421a78f6d18194`
- Dereferenced commit: `aaaaf3d09f433efe3499d6447d2715f00e4f9f17`
- Canonical executable-tree SHA-256:
  `db2741d231a3589f65e394920e88b2b361a209eaa6c0df3de59448e60fbacc4b`
- GitHub workflows tree object:
  `a7acb6b4574314f2a603fff276ddb03ce95e41e4`
- Executor composite tree SHA-256:
  `e0e8d9d7e8f35bb24cc3281561f48cb2818fb52b17f153c8f79eacbc465e70f2`

The tag is a source-only lineage marker. It carries no O2, execution window,
runtime activation, credential resolution, budget reservation, bundle or
provider authority.

## Executable RC CI

- Workflow: `Video Factory V2 CI`
- Role: `executable_rc`
- Run: `36664650929`
- Ref: `refs/tags/vf-v3-01-rc24`
- Expected SHA: `aaaaf3d09f433efe3499d6447d2715f00e4f9f17`
- Checked-out SHA: `aaaaf3d09f433efe3499d6447d2715f00e4f9f17`
- Result: `PASS 5/5`

This run is independent of exact-main run `36650898059`. Final
`governance_main_ci` does not exist yet and may only be collected after a
separate Owner-approved merge of this governance-only commit.

## Bound qualified infrastructure

- Execution-plane promotion SHA-256:
  `625d45edb0f2c05f9646b36cdf1583cc8832c5ec961cb5a81fe2c7cf326fa617`
- Qualification evidence manifest SHA-256:
  `0851737647d80c1193a9c0656825c437adc6d6cafce0bc742e9dfa39b3dc95d5`
- Exact-main qualification binding SHA-256:
  `a3f1e3be0da52957d676cce2487dbded80c33f717f85e4e013f6b82c19bfe3f6`
- Activation-security receipt SHA-256:
  `d6e8ce969c87e24c750692e85537e5f772059a3d8a3c781063171fba4ec20b6a`
- Custody database: `vf_provider_custody_v3_01`
- Custody binding SHA-256:
  `c8d2761e3a5f6f835d6562665aac3eb175b5387bacc9e9e2daa5433c36b00e27`
- Provider secret source: `PRESENT_NOT_RESOLVED`
- Runner: `ID 6 / npd-vf-executor-ubuntu-02`, `OFFLINE / SAFE`
- Kill switch: `ENGAGED`
- PostgreSQL runtime role: `vf_executor_runtime = NOLOGIN`
- Real RuntimeActivationBinding: `NOT_CREATED`
- Resolver: `INACTIVE`; expiry failsafe: `ACTIVE`
- Execution catalog: `EMPTY / ABSENT`

The RC-only provenance artifact is
[`rc24-provenance.json`](../../../../../evidence/v3-01/vf-asr-rc24-01/rc24-provenance.json),
SHA-256
`137ec3dafff493559affc3221ebf75c1272cfff3b5809711d99051b97b97843a`.

## Historical RC-23 boundary

RC-23 remains `CANCELLED_NO_DISPATCH`. Its approvals, bundle and authority
artifacts are historical, immutable and non-transferable. Operation 1 remains
unconsumed, provider calls remain zero, and this candidate does not mutate or
reuse any RC-23 artifact.

## Boundaries and next gate

- ASR acceptance lineage created: `NO`
- Operation 1 / Operation 2 created: `NO / NO`
- Bundle or loaded scope created: `NO`
- Runtime activation, authority or O2 created: `NO / NO / NO`
- Provider credential reads: `0`
- Provider calls: `0`
- Budget reserved: `0 VND`
- Ledger writes: `0`
- Operation consumption: `0`
- Actual cost: `0 VND`
- RC-23 mutation: `NONE`
- Production: `NO-GO`

Next required lifecycle step: obtain a separate Owner decision for controlled
merge of the exact governance-only PR head. After that merge, run fresh exact
governance-main CI and build final canonical dual-CI provenance. Only a final
`DUAL_CI_PROVENANCE = PASS` may unblock preparation of a fresh ASR lineage and
Operation 1. This candidate must not claim final dual-CI PASS.
