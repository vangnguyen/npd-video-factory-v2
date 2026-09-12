# NPD Video Factory Handoff

Canonical machine record: [handoff.json](handoff.json).
These are the only current handoff source-of-truth paths; there are no root
duplicates.

## Current checkpoint

- Task: **VF-V0F**, same-release MinIO Quay immutable-digest remediation candidate.
- Verdict: **REVIEW_REQUIRED — Case B: executable-tree hash changed**.
- Draft [PR #61](https://github.com/vangnguyen/npd-video-factory-v2/pull/61),
  branch `remediation/vf-v0f-minio-quay-digest`; **not merged**.
- Exact source main: `5fef0ecf4dde0c99ec1b220ffd1dc36dcfee6045`.
- Source main CI `34670260472` remains failed (4/5; Docker Hub MinIO pull).
  Candidate PR CI must not be presented as exact-main CI.
- [PR #60](https://github.com/vangnguyen/npd-video-factory-v2/pull/60) remains
  separate, open/draft and unchanged. Its handoff-only changes were not imported.
- ASR: **0/2 PASS**. Vision: **2/2 PASS**. Production: **NO-GO**.
- Task production writes / owned credential reads / paid-provider calls /
  live reservations / provider cost: **0 / 0 / 0 / 0 / 0 VND**.

## Immutable executable and acceptance anchors

- RC-17: `vf-v3-01-rc17` →
  `d08ffc005d7f3ad517d355977b0bc3cc8d686906`.
- RC-17 executable-tree SHA-256:
  `ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.
- RC CI: `34550127181`, completed/success, 5/5.
- Lineage:
  `al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329`.
- Scope SHA-256:
  `6b1d5f25684d0b276c06c4b80b5d636f7845a36fdedc24e88adbd5bae7930fc7`.
- Bundle SHA-256:
  `39867efb2a95d22bf5d4be64e041671cf10517a118d02bece010778ab587a76f`.
- W1 profile SHA-256:
  `9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1`.
- Prompt SHA-256:
  `6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48`.

## Candidate / lineage impact

Old MinIO reference:
`minio/minio:RELEASE.2025-09-07T16-13-09Z`.

New same-release reference:
`quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.

Initial executable candidate commit:
`ed976c0e222ef2d732bd5bf6b822ba845b2a56de`, **not a tagged RC**.

Candidate executable-tree SHA-256:
`ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.

Only `docker-compose.yml` changes a canonical hashed path. Its sole edit is
the image source/digest pin; MinIO configuration, ports, health checks,
credentials, CLI arguments, storage and business logic stay unchanged.
Tests/docs/evidence are outside the executable hash.

RC-17 is not retagged and its lineage remains unchanged. This patched branch
must not be called RC-17. A new executable candidate/RC is required under the
existing contract **after separate authorized merge and exact-main regression**.
No new RC is created by VF-V0F.

RC-17 dual-CI provenance cannot PASS for this runtime-changing candidate.
Candidate CI success does not authorize Operation 1 or repair main until an
Owner-approved merge receives its own exact-main CI/provenance.

## Validation and current evidence

Local checks: **958 Python/API/worker/bridge tests; 32 focused tests; 14 Studio
tests; 14 Renderer tests; typecheck/bundle; 36 safety/Compose steps; MinIO
integration; Docker deterministic E2E; migration replay; existing acceptance
and Flow A–C boundary validation — PASS**.

The original cached Hub image and Quay digest have identical observed image
ID/rootfs layers. Linux/amd64, bucket/object operations, cross-reference
persistence, restart and shutdown were tested. Local E2E also passed MinIO
artifact recovery and disposable DR; these are not production-path evidence.

Environmental test-harness failures and clean reruns are documented in the
[engineering evidence bundle](../../../evidence/v3-01/vf-v0f-20260912T081435Z-5fef0ec-minio-quay-pin/README.md).
Historical provider receipts, transcripts, costs and acceptance verdicts
remain untouched.

Initial candidate CI: `34682929005` on the executable candidate commit,
**completed/success, 5/5 jobs**; observed metadata and E2E excerpt are retained
in the engineering bundle. The final docs/evidence head must pass its exact-head
PR checks; its live run/head binding is reported in the task HANDOFF RECEIPT.
Do not substitute the initial CI for a changed final head.

Canonical handoff JSON SHA-256:
`c9218e693deb5df97bd32a8b53fe9698589b4fd97cbc54bad0b36089119de7ca`.
The final head/CI observation is provided by PR #61's exact required checks and
the task receipt, keeping commit/self-hash and CI self-reference separate.

## Authority state — not activated

Operation 1 remains `PREPARED_NOT_AUTHORIZED`.
Operation 2 remains `NOT_APPROVED / LOCKED / NOT EXECUTED`.
The existing two operation IDs, lineage, scope, bundle, W1 profile, rights and
quality thresholds are not changed by this patch.

Kill switch: **ENGAGED**. Bundle: **UNMOUNTED**.
External/paid execution: **false**. Checked-in provider budget: **0 VND**.
No credentials are resolved and no live provider ledger/reservation is touched.

The Sep 12 21:00 → Sep 13 01:00 ICT window remains
**PROPOSAL_NOT_AUTHORITY**, not a schedule, countdown or permission to execute.

## Next safe action / stop

Owner reviews Draft PR #61's final exact head, compatibility evidence and
Case B executable-tree impact under G-08. **Stop before merge, RC creation,
credential access, budget reservation, provider call or Operation 1 authority.**
Do not execute the next action automatically.
