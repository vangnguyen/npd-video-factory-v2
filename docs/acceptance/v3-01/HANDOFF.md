# NPD Video Factory Handoff

Canonical machine record: [handoff.json](handoff.json).
Only these canonical acceptance-governance handoff paths are current sources
of truth; no root duplicates.

## Current checkpoint

- Task: **VF-V0G — controlled merge PR #61 + exact-main verification**.
- Verdict: **PASS**. **NEW_RC_REQUIRED = YES**.
- [PR #61](https://github.com/vangnguyen/npd-video-factory-v2/pull/61) merged
  approved exact head `d7852b682b3042caebe6dfe280fc89591d4874df`.
- Merge / verified main: `03e18c1f0c56fff8a13f167af74f34894c2db811`.
- [Exact-main CI 34691861788](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34691861788):
  **completed/success, 5/5 jobs**.
- Main executable-tree SHA-256:
  `ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.
- The merge's full tree matches the approved head; only the intended Compose
  image-reference edit changes a hashed path from old main.
- ASR **0/2 PASS**. Vision **2/2 PASS**. Production **NO-GO**.

## Immutable RC-17 / provenance boundary

`vf-v3-01-rc17` remains tag object
`ea67843635dddf94ee25d38111fc06782ad9fd74` → commit
`d08ffc005d7f3ad517d355977b0bc3cc8d686906`.

RC-17 executable SHA-256 remains
`ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.
RC-17 is NOT retagged and current main is NOT RC-17.

Exact-main merge provenance PASS verifies both exact-head/main CI identities,
parent/full-tree match and candidate-to-main executable equality. Structural
dual-CI from source candidate C1 to main also PASSes through the unchanged
canonical validator; C1 is not a locked RC and that proof grants no authority.

RC-17 → current main operation provenance remains intentionally
`BLOCKED_0_CALL / CI_PROVENANCE_INVALID`. No old package/authority may be
reused. New RC is required under the current contract, but **no new RC is
created or authorized in VF-V0G**. VF-V0H must be assigned separately.

Existing bundle, scope, W1 profile/prompt and 80 existing asset/approval/
contract files remain exact. Historical provider receipts/verdicts/costs are
untouched; no retrospective acceptance update.

## Validation / evidence

Local exact-main Python/API/worker/bridge **958 PASS**, Studio **14 PASS**,
Renderer **14 PASS**, typecheck/bundle PASS. Migration replay,
acceptance/evidence, ASR compatibility and Flow A–C/DR fixture boundaries
passed. Exact-main CI independently passed all five jobs, including
**36 safety/Compose steps** and the unchanged **Docker deterministic E2E**
with MinIO artifact recovery, disposable DR/Redis recovery and final QC.

[Post-merge engineering evidence](../../../evidence/v3-01/vf-v0g-20260912T115120Z-03e18c1-pr61-postmerge/README.md)
retains exact review, CI, merge/tree and regression provenance.
Prior pull failure and candidate compatibility evidence remain immutable.
Fixture/local DR is not production-path or human-quality acceptance.

Canonical handoff JSON raw SHA-256:
`39d93f86822e820487926d86021bc36fbca184a7e6f02232f3afa96bfc69f408`.

## Authority / zero activity

Operation 1: **PREPARED_NOT_AUTHORIZED**, reference-only package unusable on
current/new RC. Operation 2: **NOT_APPROVED / LOCKED**.
No live provider ledger is accessed or changed by this task.

Kill switch **ENGAGED**; gate **UNMOUNTED**; checked-in external/paid
execution **false**, budget **0 VND**. Old Sep 12 window remains historical
proposal only, never a schedule or fresh authority.

Credential reads **0**; live budget reserved **0 VND**; real provider calls
**0**; provider cost **0 VND**; production writes **0**.

## Handoff branch / stop

This fresh handoff/evidence is persisted on
`handoff/vf-v0g-pr61-postmerge` from verified merge main.
It receives independent draft-PR checks; no additional merge is authorized.
[PR #60](https://github.com/vangnguyen/npd-video-factory-v2/pull/60) is separate,
open/draft/untouched; its older overlapping handoff needs Owner coordination.

**STOP. Await separately assigned VF-V0H** to materialize a fresh RC from
exact main `03e18c1f0c56fff8a13f167af74f34894c2db811` and executable SHA
`ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.
Do not create an RC/operation/authority, resolve credentials, reserve funds,
call a provider or execute this next action automatically.
