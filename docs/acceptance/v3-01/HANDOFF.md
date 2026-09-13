# NPD Video Factory Handoff

Canonical machine record: [handoff.json](handoff.json).
These are the only current handoff paths; there are no root duplicates.
This update supersedes only the current checkpoint view, not historical
provider receipts or the separate historical VF-V0G engineering draft.

## Current checkpoint — VF-V0H

**REVIEW_REQUIRED — RC-18 materialized; actual post-merge dual-CI still gated.**

- Annotated executable tag: `vf-v3-01-rc18`.
- Exact executable commit / verified actual main:
  `03e18c1f0c56fff8a13f167af74f34894c2db811`.
- Annotated tag object: `30ca09c4201cd6aea5e733c26ba4dfa1f30d5021`.
- Canonical executable-tree SHA-256:
  `ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.
- Fresh [RC-bound CI 34744690232](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34744690232):
  `workflow_dispatch` on `vf-v3-01-rc18`, completed/success, **5/5**.
- Independently observed [baseline main CI 34691861788](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34691861788):
  completed/success, **5/5**. It is not substituted for RC-bound CI.
- Separate governance handoff branch: `handoff/vf-v0h-rc18-materialization`.
  Any draft-head checks/provenance are **candidate observations**, not merged main.
- ASR **0/2 PASS**, Vision **2/2 PASS**, production **NO-GO**.
- New Operation 1 authority: **NOT_CREATED**.

## Materialization proof

Live preflight verified exact unchanged remote main, two matching canonical
hash recomputations, successful baseline CI, sealed VF-V0G regression evidence,
RC-17 immutability, the existing canonical RC name pattern, sequential RC-1
through RC-17, and absence of RC-18 immediately before creation.

Only an annotated tag was created on that exact commit; no amended, rebased,
cherry-picked or new executable commit was produced. Fresh tag-bound CI was
explicitly dispatched because the unchanged workflow does not auto-run tag
pushes. Tag-to-commit, tag-to-selected-tree, all annotation-bound blobs and
the clean detached executable worktree were independently checked afterward.

The annotation pins the current provider safety plane, canonical provenance/
lineage/acceptance rules, W1 profile, asset-specific rights/media/reference
artifacts and the existing same-release immutable MinIO image. It grants no
provider, budget, credential, deployment or operation authority.

MinIO:
`quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.

W1: `asr-whisper-vi-w1-v1`.
Profile SHA-256:
`9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1`.
Prompt SHA-256:
`6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48`.

## Gate still missing — no provenance workaround

The unchanged canonical `ProviderAcceptanceCiProvenance` requires distinct
executable-RC and governance-main commits, distinct successful CI run IDs,
a nonempty complete allowlisted governance diff and equal selected executable
trees. Actual main currently equals RC-18's commit.

Canonical collection on RC-18 CI plus current main CI therefore returns
**BLOCKED_0_CALL / CI_PROVENANCE_INVALID**. Two successful runs on this same
commit cannot satisfy post-governance dual-CI. No validator, allowlist,
workflow or hash algorithm is changed to bypass this requirement.

A separate governance-only **draft** handoff PR must receive Owner G-08 before
merge; this task does not merge it. After an explicitly authorized merge, a
separately assigned verification must observe the actual new main commit,
its successful exact-main CI and fresh canonical dual-CI. A candidate branch
is never presented as actual main.

## RC-17 and historical authority

RC-17 stays immutable:
`vf-v3-01-rc17` →
`d08ffc005d7f3ad517d355977b0bc3cc8d686906`.
Its tag object remains
`ea67843635dddf94ee25d38111fc06782ad9fd74`;
old executable-tree SHA is
`ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.

- Old Operation 1 package:
  **HISTORICAL_REFERENCE_ONLY / INVALID_FOR_RC18**.
- Operation 2:
  **NOT_APPROVED / LOCKED / NOT_TRANSFERRED**.
- Old operation IDs, scope/bundle hashes, authority receipts, window and
  reservation state are not copied into a new executable package.
- No historical provider outcome, transcript, timing, usage or actual cost is
  rewritten or reconstructed.

[Draft PR #62](https://github.com/vangnguyen/npd-video-factory-v2/pull/62)
remains a separate historical VF-V0G handoff/evidence record, unchanged.
Owner must coordinate its older overlapping handoff paths before any later
merge, preserving historical engineering evidence and preventing stale
handoff overwrite. It is not imported as RC-18 provenance or silently deleted.

## Validation and authority state

New local focused canonical provenance/W1/lineage tests: **168 PASS**.
Fresh tag-bound regression: **958 Python/API/worker/bridge, 14 Studio and
14 Renderer tests PASS**, typecheck/bundle PASS, safety/Compose PASS,
migration upgrade/down/replay through `0014_v3_01_27` PASS,
offline ASR compatibility and acceptance/evidence validation PASS,
Flow A/B/C/DR fixture boundaries remain **BLOCKED_AS_EXPECTED**,
and Docker deterministic E2E PASS. Existing VF-V0F/VF-V0G checksum
entries: **18 verified**, history unchanged.

New full operation rebind inventory is deferred until actual post-merge
dual-CI PASS. A future task must regenerate RC-18 lineage/slot identities,
exact commit/tree, execution scope/scope/bundle, asset/reference/rights and
W1/profile bindings, separately approved window/budget/timeout, kill-switch
binding and separate Owner operation authority.
No new IDs, scope, bundle, window or approval records are created here.

Kill switch **ENGAGED**. Bundle **UNMOUNTED**.
Checked-in external/paid execution **false**, transcription provider **fixture**,
model **blank**, provider budget **0 VND**.
No live provider ledger is accessed.
Task credential reads / reservations / provider calls / production writes /
actual provider cost: **0 / 0 / 0 / 0 / 0 VND**.

## Evidence and stop

[RC-18 engineering evidence](../../../evidence/v3-01/vf-v0h-20260913T071310Z-rc18-materialization/README.md)
contains the pre-tag preflight, exact annotation and blob bindings, canonical
Git-object manifest, independently observed RC/main CI, blocked actual-main
dual-CI receipt and validation. Final raw handoff hashes are sealed separately;
head/CI self-reference is reported in the task receipt, not fabricated inside
the commit.

Canonical handoff JSON SHA-256:
`65362119af0fd59e53dcceb9e6cdd913c93daa107abde4618dfc7fc6c60f8ed6`.

**NEXT_SAFE_ACTION:** Owner G-08 exact-head review of the separate governance-only
RC-18 handoff draft PR. After separately authorized merge, collect actual
exact-main CI and canonical dual-CI before assigning an operation rebind task.

**STOP before any new Operation 1 authority creation or activation, credential
access, reservation or provider execution.** No retag, RC-19, Operation 2,
deployment, publishing, public ingress or analytics. Do not execute the next
safe action automatically.
