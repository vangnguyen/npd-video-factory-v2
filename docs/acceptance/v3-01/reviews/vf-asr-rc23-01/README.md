# VF-ASR-RC23-01 — RC-23 governance-only closure candidate

Status: `PASS_RC_ONLY / GOVERNANCE_CLOSURE_CANDIDATE`

This record materializes the immutable source-only RC tag and prepares one
governance/evidence-only closure commit. It does not grant provider execution
authority and is not final dual-CI provenance.

## Immutable RC-23 identity

- Tag: `vf-v3-01-rc23` (annotated)
- Tag object: `820657795fe17a6048259c7bf8ad59e55375e6a0`
- Dereferenced commit: `ff19b812d6062baa4a0a284333a06a7722f61757`
- Canonical executable-tree SHA-256:
  `f92bd2acbb2c2bcfb98fbb737567d20b6551724e1c03c0574dfaa4f3733dce9a`
- GitHub workflows tree object:
  `e2048a15188852df9f6c43ecd1ae982ee56b4588`
- Executor composite tree SHA-256:
  `574bda3d7e5183287db486fa6e1075e7c49f472a95ad3898a79a71bfd7134092`

The tag is a source-only lineage marker. It carries no O2, execution window,
credential resolution, budget reservation, bundle or provider authority.

## Executable RC CI

- Workflow: `Video Factory V2 CI`
- Role: `executable_rc`
- Run: `36573791015`
- Ref: `refs/tags/vf-v3-01-rc23`
- Expected SHA: `ff19b812d6062baa4a0a284333a06a7722f61757`
- Checked-out SHA: `ff19b812d6062baa4a0a284333a06a7722f61757`
- Result: `PASS 5/5`

This is distinct from exact-main run `36570459844`. Final
`governance_main_ci` does not exist yet and may only be collected after a
separate Owner-approved merge of this governance-only commit.

## Bound qualified infrastructure

- Execution-plane promotion SHA-256:
  `6d538d87d50024dcf4d549d3e2be9f5ff33cf341914f7f92cbac7c077b50def6`
- Qualification evidence manifest SHA-256:
  `0b33ca50dd3361315c610915e2f3ab435c49270be6453dbed49bc517eb61c338`
- Exact-main qualification binding SHA-256:
  `32ee5ac5a96573ab2a4392340bef992222ad16d973ce646f25c23aa64ab57ddb`
- Custody database: `vf_provider_custody_v3_01`
- Custody binding SHA-256:
  `c8d2761e3a5f6f835d6562665aac3eb175b5387bacc9e9e2daa5433c36b00e27`
- Runner: `ID 6 / npd-vf-executor-ubuntu-02`, `OFFLINE / SAFE`
- Kill switch: `ENGAGED`

The RC-only provenance artifact is
[`rc23-provenance.json`](../../../../../evidence/v3-01/vf-asr-rc23-01/rc23-provenance.json),
SHA-256
`5a3cb4afefa54a4d917031aebb2ad0f340cd582c913721bed16b5d3bf1b51cfb`.

## Boundaries and next gate

- ASR acceptance lineage created: `NO`
- Operation 1 / Operation 2 created: `NO / NO`
- Bundle or loaded scope created: `NO`
- Authority or O2 created: `NO / NO`
- Provider credential reads: `0`
- Provider calls: `0`
- Budget reserved: `0 VND`
- Operation consumption: `0`
- Actual cost: `0 VND`
- RC-22 mutation: `NONE`
- Production: `NO-GO`

Next required lifecycle step: obtain a separate Owner decision for controlled
merge of the exact governance-only PR head. After that merge, run fresh exact
governance-main CI and build final canonical dual-CI provenance. Only a final
`DUAL_CI_PROVENANCE = PASS` may unblock preparation of a fresh ASR lineage and
Operation 1. This candidate must not claim final dual-CI PASS.
