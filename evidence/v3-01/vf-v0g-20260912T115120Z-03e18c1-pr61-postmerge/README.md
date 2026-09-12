# VF-V0G — PR #61 controlled merge and exact-main verification

## Result

**PASS — NEW_RC_REQUIRED = YES.** Only the Owner-approved exact head was
merged. No RC/tag, operation, authority, credential access, live reservation,
provider call, production deployment or publish occurred.

- [Merged PR #61](https://github.com/vangnguyen/npd-video-factory-v2/pull/61).
- Pre-merge main: `5fef0ecf4dde0c99ec1b220ffd1dc36dcfee6045`.
- Approved exact head: `d7852b682b3042caebe6dfe280fc89591d4874df`.
- Merge / verified exact main: `03e18c1f0c56fff8a13f167af74f34894c2db811`.
- [Exact-main CI 34691861788](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34691861788):
  completed/success, all five jobs and required steps successful.
- Main executable-tree SHA-256:
  `ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.

## Exact-head review / controlled merge

[G-08 review](G08_REVIEW.md) classifies all 17 PR files: one runtime Compose
image-reference line, one focused test file, two canonical handoffs and 13
engineering evidence files. Required exact-head CI `34683338030` passed 5/5;
zero unresolved review threads. The controlled merge used exact head matching
and normal merge-commit governance, not an admin/protection bypass.

The merge has precisely the old main and approved head as parents; its full
Git tree matches the approved head. The Quay reference is the verified same
release pinned by immutable digest. No MinIO configuration/storage/ports/
healthcheck/CLI or business/provider logic changes accompany it.

Prior compatibility proof and its twelve immutable checksums remain in the
[VF-V0F evidence](../vf-v0f-20260912T081435Z-5fef0ec-minio-quay-pin/README.md).
The one runtime edit is intentional Case B, not unexpected scope drift.

## Provenance: distinguish merge proof from operation eligibility

[Merge provenance](merge-provenance.json) verifies live CI/head bindings,
merge parents/tree, canonical object hashes and the live annotated RC tag.

The exact approved final PR head CI and exact main CI bind separately to
their own commits; both are completed/success, 5/5.

The unchanged canonical dual-CI validator also passes the structural
executable source candidate `ed976c0e222ef2d732bd5bf6b822ba845b2a56de` / CI
`34682929005` to exact main / CI `34691861788`: their executable hash
matches and the intervening 15 files are existing-allowlisted governance only.
Structural provenance SHA-256:
`227a15d11a052bc87f1f4c9dc4513674e27df1a185dd1782654f8bdd26915337`.

**That source candidate is not an annotated locked RC. The structural proof
is not a provider-operation authority or an RC materialization.**

Conversely, RC-17 → current main MUST remain
`BLOCKED_0_CALL / CI_PROVENANCE_INVALID` because Compose is a hashed runtime
path and the hashes differ. This negative check passes as a safety guard.
No validator/allowlist/CI gate was relaxed to report this task PASS.
A newly materialized RC and fresh provenance/rebind are separately required
before any future operation. This task's provenance PASS is for the approved
infra merge, not RC-17 operation eligibility.

## RC and historical evidence

- `vf-v3-01-rc17` remains annotated tag object
  `ea67843635dddf94ee25d38111fc06782ad9fd74`, peeled commit
  `d08ffc005d7f3ad517d355977b0bc3cc8d686906`.
- RC-17 executable SHA-256 remains
  `ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.
- Only `docker-compose.yml` changes a hashed path from old main; main matches
  the reviewed candidate hash.
- The existing RC-17 bundle raw hash remains
  `39867efb2a95d22bf5d4be64e041671cf10517a118d02bece010778ab587a76f`.
- Eighty existing asset/approval/contract files are byte-unchanged.
- Original provider receipts, IDs, transcripts, actual/unknown costs, verdicts
  and historical acceptance axes are not rewritten.
- ASR **0/2 PASS**, Vision **2/2 PASS**, production **NO-GO**.

RC-17 Op1 remains `PREPARED_NOT_AUTHORIZED`, Op2 `NOT_APPROVED / LOCKED`.
The package is reference-only and cannot be reused against current/new RC.
The Sep 12 window is retained as an old proposal only, not current authority.
Kill switch ENGAGED; bundle unmounted; checked-in external/paid false,
budget 0 VND. No live provider ledger was accessed in this task.

## Regression / evidence scope

[CI metadata](exact-main-ci.json), [regression receipt](regression.json) and
[CI excerpt](exact-main-e2e-excerpt.txt) retain observed counts and outcomes.

Local exact-main imports verified; Python/API/worker/bridge **958 PASS**,
Studio **14 PASS**, Renderer **14 PASS**, typecheck/bundle PASS. Exact-main CI
independently passed these suites, all **36** safety/Compose run steps,
migration upgrade/downgrade/replay, ASR compatibility and acceptance/evidence
checks. Flow A/B/C and DR fixture verdicts remain BLOCKED as expected.

Docker deterministic E2E used the unchanged script; MinIO pull, artifact
recovery, final QC, fail-closed publishing dry-run and disposable DR/Redis
recovery passed. No fixture is relabelled production-path evidence.
The CI excerpt is allowlisted and LF/trailing-whitespace normalized; original
GitHub logs/artifact remain the source, not reconstructed provider data.

The existing Node-action deprecation and renderer dependency-audit warnings
are recorded as unchanged technical debt, not fixed or bypassed here.

## Handoff persistence / remaining gates

Canonical [HANDOFF.md](../../../docs/acceptance/v3-01/HANDOFF.md) and
[handoff.json](../../../docs/acceptance/v3-01/handoff.json) are updated on
`handoff/vf-v0g-pr61-postmerge`, without an unapproved direct main write.
This branch contains governance/evidence only, receives its own PR checks
and must not be auto-merged. The verified runtime main baseline remains the
merge commit above. PR #60 stays open/draft/separate and is not imported;
its older handoff overlaps these paths and needs separate Owner coordination.

Engineering bundle checksums are in [SHA256SUMS.txt](SHA256SUMS.txt); this is
not a new real-provider acceptance run or aggregate PASS upgrade.

**STOP.** Await explicitly assigned VF-V0H to materialize a fresh RC from
exact verified main/tree. Do not create/tag an RC, rebind/activate authority,
resolve credentials, reserve funds or call providers automatically.
