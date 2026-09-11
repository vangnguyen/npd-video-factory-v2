# NPD Video Factory Handoff

This file is the human-readable companion to `handoff.json`. It is maintained
inside the repository; the owner does not need to upload or attach it after
each task.

## Current checkpoint

- Workstream: Video Factory V3-01 ASR real-provider acceptance.
- Latest task: RC-17 W1 lineage Operation 1 preflight on 2026-09-11.
- Verdict: `BLOCKED_PRE_CALL`.
- Reason: the observed time was one day before the proposed acceptance window,
  and no separate RC-17 Operation 1 execution authority had been granted.
- Provider calls: `0`.
- Credential reads: `0`.
- Reservations and actual cost: `0 VND`.
- ASR consecutive acceptance: `0/2 PASS`.
- Vision consecutive acceptance: `2/2 PASS`.
- Production verdict: `NO-GO`.

## Immutable anchors

- Executable RC: `vf-v3-01-rc17` at
  `d08ffc005d7f3ad517d355977b0bc3cc8d686906`.
- Governance main: `cfe93b52a0de067066f707e5c7eab0f6e8392863`.
- Executable-tree SHA-256:
  `ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.
- RC CI: `34550127181` (`completed/success`, 5/5 jobs).
- Governance-main CI: `34554458518` (`completed/success`, 5/5 jobs).
- Dual-CI provenance SHA-256:
  `bd6d687a4cab9df2151f91317b8faa3ea23df3c1b5ef6c7c21b741e6a09e6bf5`.
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
  is `NOT_APPROVED_NOT_EXECUTED` and not consumed.
- Operation 2:
  `v3-01-rc17-openai-transcription-asr-al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329-call-02`
  remains `NOT_APPROVED_LOCKED_NOT_EXECUTED`.
- Proposed window only: 2026-09-12 21:00 through 2026-09-13 01:00
  Asia/Ho_Chi_Minh (`2026-09-12T14:00:00Z` through
  `2026-09-12T18:00:00Z`). It is not an execution authority or schedule.

## Latest evidence

- Machine-readable preflight receipt:
  `evidence/v3-01/vf-v3-01-20260911T140243Z-cfe93b5-rc17-asr-w1-op1-blocked-prewindow/preflight.json`.
- Canonical handoff record: `handoff.json`.
- `handoff.json` SHA-256:
  `bdfbdda3bcc9963663f9b8371f5b7eaaba4c59ea744af3166b143ee3e3034b72`.

## Next safe action

Wait for a separate owner decision that explicitly authorizes RC-17 lineage
Operation 1. At execution time, re-run the complete fail-closed preflight
inside the exact approved window. Do not infer authority from this handoff,
the merged governance PR, CI results, or the proposed window. Do not perform
this next action until it is assigned.
