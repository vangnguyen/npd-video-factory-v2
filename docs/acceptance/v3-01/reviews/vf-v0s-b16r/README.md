# VF-V0S-B16R — historical main-based authority CI-binding repair

This review concerns a Draft PR based directly on governance main
`4ac4880d5627c2800eb918d24c59da5f8e047091`. It ports the byte-identical
B15 preparation package and B16 approval/bundle evidence into one governance
branch. Draft PRs #78, #79 and #80 remain unmerged historical evidence. No
executable/runtime path changes, RC tag changes or execution actions are part
of this candidate.

## Exact runner contract and CI evidence

`app.provider_single_dispatch.run_single_dispatch` reads
`authority["executable_rc_ci_run_id"]` and
`authority["governance_main_ci_run_id"]` for the strict dual-CI validator.
They were absent from B16's authority JSON, although the canonical provenance
SHA was present. The verified runs are:

- RC-20 `93b5441d44347c9c40b745bdfed0969880853f68`: run `35124578033`,
  `workflow_dispatch`, five canonical jobs passed.
- Governance main `4ac4880d5627c2800eb918d24c59da5f8e047091`: run
  `35172654970`, `push`, five canonical jobs passed.

The [read-only provenance snapshot](baseline-dual-ci-provenance.json) validates
under the existing `ProviderAcceptanceCiProvenance` schema and hashes to
`5caca534d1cfa6a4e3d9b4f9f9b6b1c33b024ec65afdfc36cf875c673bc1eb86`.
That SHA was already included in each of G-01/G-02/G-03's signed artifact
set. These records, the gate bundle and the loaded scope remain byte-identical;
the strict bundle schema has no CI-run fields. New approval IDs or a new
window are therefore not asserted for the *unchanged current-main baseline*.

The corrected pre-merge authority receipt is
`074c91cf7efff23bd7763bb698905dfe8de9e0d50ed72dea358354a4930e8dce`;
historical B16 receipt
`694693ca50001c93d5264418661bc8a25179a3791d6437e077f67653c2a3140c`
remains available in Draft PR #80. Both receipts are
`HISTORICAL_PRE_MERGE_BINDING / INVALID_AFTER_GOVERNANCE_MERGE`; neither is
executable for the new governance main. Final execution authority is
`NOT_CREATED` until G2 independently binds the new main/CI/provenance and
obtains a renewed window decision. Final bundle SHA stays
`a98a78884d020138c858b608b5462df5a762ebcac9024ce0ff6257e1bdd10019`;
loaded scope SHA stays
`2e049bfe8b2dede3ca8cb3ffdb27fd95bc96dd1d72c8e18cb4dca1788282b5de`.
The [offline reproducer](../../prepared/vf-v0s-b16-rc20-final-authority/materialize.py)
checks the exact authority loader, authority verifier, provenance validator,
real gate loader, deterministic bytes, immutable B15 inputs and negative gate
controls. The top-level runner has no safe check-only entrypoint, so this is
contract validation, **not** a claim that a dispatch path was exercised.

## Read-only custody and safety

The RC-20 PostgreSQL private socket returned database
`vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d`, role
`vang_nguyen`, system identifier `7686186223531422166`, migration head
`0015_v3_01_dispatch`, control seed `global/revision=0`. In a read-only
transaction, all eight execution tables and total reserved VND were zero.
There was no operation record, provider receipt, reservation or idempotency
collision. No ledger mutation, credential read, budget reservation, bundle
mount, kill-switch transition, provider call or business production write
occurred in B16R.

## G-08 decision boundary

Although the branch topology and missing fields are repaired, a governance
merge advances `main` away from the exact SHA in this authority and changes
the required exact-main CI/provenance identity. The runner fails closed on
`GOVERNANCE_MAIN_DRIFT` before custody access. Thus PR #81 may close
governance/evidence only and must not be treated as post-merge execution
authority. RC CI `35124578033` stays stable while RC-20 is unchanged; the new
governance-main CI run ID cannot exist before merge. The runner requires both
`executable_rc_ci_run_id` and `governance_main_ci_run_id`, so G2 must create a
fresh exact binding and window reauthorization. Do not perform B17 or
provider preflight from this branch.
