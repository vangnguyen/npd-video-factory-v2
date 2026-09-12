# NPD Video Factory Handoff

This is the human-readable companion to [handoff.json](handoff.json).
Both canonical artifacts remain under the existing V3-01 governance allowlist.
There are no root handoff duplicates.

## Current checkpoint

- Workstream: Video Factory V3-01.
- Latest task: `VF-V0D`.
- Verdict: `BLOCKED_POST_MERGE_CI`; do not treat this as runtime authority.
- PR [#59](https://github.com/vangnguyen/npd-video-factory-v2/pull/59) merged
  the exact owner-approved head `45eda7c12a7fa79ab76a80ad1c742fae60e65b38`.
- Merge/current main: `5fef0ecf4dde0c99ec1b220ffd1dc36dcfee6045`.
- The merge tree equals the approved head tree; there was no extra merge change.
- Exact-main CI [34670260472](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34670260472)
  completed with `failure`, 4/5 jobs successful, on both attempts.
- Docker deterministic E2E stopped at `minio/minio` image pull:
  `pull access denied`. A failed-job rerun on the same exact commit reproduced
  it. No image, Docker configuration, workflow or executable source was changed.
- Python/API/worker/bridge: 950 tests passed on main. Studio: 14 passed.
  Renderer, safety defaults, migration replay and acceptance/evidence checks passed.
- Local dual-CI tests: 23 passed. The additional local full bundle test collection
  was blocked by missing `tiktoken` in the global Python environment; it is not
  counted as a local PASS. The main CI executed the full 950-test suite.
- Canonical post-merge dual-CI validation: `BLOCKED_0_CALL`,
  `CI_PROVENANCE_INVALID`. No trusted post-merge provenance hash was issued.
  A successful candidate CI must not substitute for failed exact-main CI.
- Provider calls, credential reads, live reservations, production writes and
  task cost: `0` / `0 VND`.
- ASR: `0/2 PASS`; Vision: `2/2 PASS`; production: `NO-GO`.

## Immutable anchors

- Executable RC: `vf-v3-01-rc17` at
  `d08ffc005d7f3ad517d355977b0bc3cc8d686906`.
- Annotated tag object: `ea67843635dddf94ee25d38111fc06782ad9fd74`,
  independently matched to the remote tag.
- RC, approved PR head and merged main executable-tree SHA-256:
  `ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.
- RC CI: `34550127181`, completed/success, 5/5 jobs.
- Approved candidate CI: `34624829162`, completed/success, 5/5 jobs.
- Candidate provenance SHA-256:
  `d830b096b06a0aa74ec8b2e67a695cc6e8e1c26948ebfd3d212af3bc8f1f24e8`.
- Current governance-main CI: `34670260472`, completed/failure, 4/5 jobs.
- Acceptance lineage:
  `al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329`.
- Execution-scope SHA-256:
  `6b1d5f25684d0b276c06c4b80b5d636f7845a36fdedc24e88adbd5bae7930fc7`.
- Gate-bundle SHA-256:
  `39867efb2a95d22bf5d4be64e041671cf10517a118d02bece010778ab587a76f`.
- W1 profile SHA-256:
  `9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1`.
- W1 prompt SHA-256:
  `6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48`.
- No RC was created or retagged. RC-17 executable lineage is unchanged.

## Authority and operation state

- Operation 1:
  `v3-01-rc17-openai-transcription-asr-al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329-call-01`
  remains `PREPARED_NOT_AUTHORIZED`.
- Operation 2:
  `v3-01-rc17-openai-transcription-asr-al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329-call-02`
  remains `NOT_APPROVED / LOCKED`.
- These are unchanged preparation records, not a new live-ledger inspection.
  No acceptance database, runner, credential resolver or operation was accessed
  or started by VF-V0D.
- Proposed window only: 2026-09-12 21:00 through 2026-09-13 01:00 ICT
  (`2026-09-12T14:00:00Z` through `2026-09-12T18:00:00Z`).
  It remains a proposal, not authority, a countdown or an automation.
- Kill switch: `ENGAGED`; bundle remains unmounted; checked-in external/paid
  execution is disabled with zero budget.
- Prepared limits are unchanged: 500 VND/operation, 1,250 VND/window,
  provider/controller 90s/120s, concurrency/attempts 1/1, no retry or fallback.
- No provider/model, operation identity, rights, profile, asset or window changed.

## Handoff delivery and evidence

The exact approved #59 head could not contain its future merge/CI result.
This fresh receipt is on `handoff/vf-v0d-pr59-postmerge`, a separate
governance-only follow-up requiring its own G-08 before merge. Main currently
contains the #59 handoff snapshot; no follow-up merge or direct main write
was performed.

- Fresh [post-merge observations](../../../evidence/v3-01/vf-v0d-20260912T032807Z-5fef0ec-pr59-postmerge/postmerge-observations.json).
- [Pre-merge checks](../../../evidence/v3-01/vf-v0d-20260912T032807Z-5fef0ec-pr59-postmerge/premerge.json).
- [Canonical provenance rejection](../../../evidence/v3-01/vf-v0d-20260912T032807Z-5fef0ec-pr59-postmerge/provenance-validation.json).
- [CI image-pull failure](../../../evidence/v3-01/vf-v0d-20260912T032807Z-5fef0ec-pr59-postmerge/ci-pull-failure.json).
- [Evidence checksums](../../../evidence/v3-01/vf-v0d-20260912T032807Z-5fef0ec-pr59-postmerge/SHA256SUMS.txt).
- Historical pre-window receipt remains untouched:
  `evidence/v3-01/vf-v3-01-20260911T140243Z-cfe93b5-rc17-asr-w1-op1-blocked-prewindow/preflight.json`.
- Canonical handoff JSON SHA-256: `7782d84052dc3e580cc000d5ed89b73b74466ce05f823a71804adbb0d8884764`.

## Next safe action

Owner reviews the CI blocker and this handoff follow-up. Assign a separate
CI diagnosis/remediation task. Exact-main CI and canonical provenance must
PASS before considering a separate RC-17 Operation 1 authority decision.
Do not read credentials, reserve budget, mount an authority bundle or call
the provider. Do not execute this next safe action without a new task.
