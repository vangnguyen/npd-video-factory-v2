# VF-V0H — Post-materialization G-08 review boundary

This is a governance-only handoff update after an explicitly Owner-authorized
annotated RC-18 tag. It is not an ASR operation authority and does not transfer
any RC-17 package or rights/budget/execution approval.

## Merge review scope

- Source main and new RC commit:
  `03e18c1f0c56fff8a13f167af74f34894c2db811`.
- New RC: `vf-v3-01-rc18`.
- Annotated tag object: `30ca09c4201cd6aea5e733c26ba4dfa1f30d5021`.
- Canonical executable-tree SHA-256:
  `ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.
- Allowed changed paths: the two canonical acceptance handoffs and this new
  `evidence/v3-01/` engineering bundle.
- No runtime/config/workflow, transcript, reference, asset, RightsRecord,
  profile, migration, business logic or historical receipt is edited.
- The draft branch is not actual merged governance main; its successful CI
  cannot be substituted for post-merge exact-main CI.
- Only Owner G-08 may authorize a subsequent exact-head merge.

## Why full dual-CI is still gated

The immutable source includes the existing canonical
`ProviderAcceptanceCiProvenance` model. It requires a distinct governance
commit plus a nonempty allowlisted diff and exact equal selected executable
tree. Actual main currently equals the newly materialized RC commit.

Tag-bound CI success proves the independently dispatched RC checks; it does
not bypass those post-governance provenance requirements. The observed
same-commit rejection is retained, not repaired by weakening the model.

After a separately approved governance-only merge, the next assigned task
must collect successful exact merged-main CI and canonical dual-CI on the
real merged commit. Neither a branch CI nor a fabricated governance SHA may
fill that role. No retag or new executable RC is needed for this strictly
allowlisted handoff diff.

## Historical handoff coordination

[PR #62](https://github.com/vangnguyen/npd-video-factory-v2/pull/62) remains
a separate historical VF-V0G handoff/evidence draft, unchanged.
Its canonical handoff paths overlap this newer view. Owner must coordinate
or rebase the older handoff before any later merge. Preserve its engineering
evidence; do not silently delete history or let an older snapshot overwrite
RC-18 state.

## Explicit terminal safety

- New Operation 1 authority: **NOT_CREATED**.
- RC-17 Operation 1 package: **HISTORICAL_REFERENCE_ONLY / INVALID_FOR_RC18**.
- Operation 2: **NOT_APPROVED / LOCKED / NOT_TRANSFERRED**.
- New live lineage/operation IDs, window, scope and bundle: **NOT_CREATED**.
- Kill switch **ENGAGED**, bundle **UNMOUNTED**.
- Task credential reads, live reservations, real provider calls, production
  writes and provider cost: **0 / 0 / 0 / 0 / 0 VND**.
- ASR **0/2 PASS**, Vision **2/2 PASS**, production **NO-GO**.

**STOP at Owner G-08. No automatic merge, rebind, authority activation,
provider call, credential access, budget reservation, deployment or publish.**
