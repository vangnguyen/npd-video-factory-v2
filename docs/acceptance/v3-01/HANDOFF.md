# NPD Video Factory Handoff

This file is the human-readable companion to
`docs/acceptance/v3-01/handoff.json`. Both handoff artifacts live under the
canonical V3-01 governance path accepted by the dual-CI provenance contract.

## Current checkpoint

- Workstream: Video Factory V3-01 ASR real-provider acceptance.
- Latest task: `VF-V0C` governance-only repair for draft PR #59.
- Status: `READY_FOR_OWNER_G08_REVIEW`; this is not merge approval or runtime
  authority.
- The root handoff copies were removed; there is one canonical source of truth.
- Provider calls: `0`.
- Credential reads: `0`.
- Reservations and actual cost: `0 VND`.
- ASR consecutive acceptance: `0/2 PASS`.
- Vision consecutive acceptance: `2/2 PASS`.
- Production verdict: `NO-GO`.

## Immutable anchors

- Executable RC: `vf-v3-01-rc17` at
  `d08ffc005d7f3ad517d355977b0bc3cc8d686906`.
- Governance main baseline:
  `cfe93b52a0de067066f707e5c7eab0f6e8392863`.
- Executable-tree SHA-256:
  `ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.
- RC CI: `34550127181` (`completed/success`, 5/5 jobs).
- Baseline governance-main CI: `34554458518` (`completed/success`, 5/5
  jobs).
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

## Operation state

- Operation 1:
  `v3-01-rc17-openai-transcription-asr-al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329-call-01`
  remains `PREPARED_NOT_AUTHORIZED`, not executed and not consumed.
- Operation 2:
  `v3-01-rc17-openai-transcription-asr-al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329-call-02`
  remains `NOT_APPROVED_LOCKED_NOT_EXECUTED`.
- Proposed window only: 2026-09-12 21:00 through 2026-09-13 01:00
  Asia/Ho_Chi_Minh (`2026-09-12T14:00:00Z` through
  `2026-09-12T18:00:00Z`). It is not execution authority or a schedule.
- Checked-in kill switch remains engaged; the bundle remains unmounted and
  checked-in external/paid execution remains disabled with zero budget.

## Governance repair

- Canonical handoff paths:
  `docs/acceptance/v3-01/HANDOFF.md` and
  `docs/acceptance/v3-01/handoff.json`.
- Both paths are inside the existing `docs/acceptance/v3-01/` governance
  allowlist; the allowlist and all executable/runtime files are unchanged.
- Final exact-head CI and dual-CI candidate provenance must pass before G-08
  can be consumed. A post-merge governance-main CI/provenance record is still
  required before any later operation authority.
- Canonical handoff record SHA-256:
  `e98659927c88eaec13aa0b518bbb77930592b59862abc08dbbdf967726ab7311`.

## Evidence pointer

- Fail-closed pre-window receipt:
  `evidence/v3-01/vf-v3-01-20260911T140243Z-cfe93b5-rc17-asr-w1-op1-blocked-prewindow/preflight.json`.

## Next safe action

Owner reviews the final exact PR #59 head under G-08. Do not merge
automatically. Even after a permitted merge, do not read credentials, reserve
budget or call the provider until a separate owner task grants exact RC-17
Operation 1 authority and the complete in-window preflight passes.
