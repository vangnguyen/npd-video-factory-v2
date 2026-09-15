# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B9
VERDICT: PASS
REPO: vangnguyen/npd-video-factory-v2

## Authoritative lineage

- Governance main: `7ad25cb039c712d450486778d2981d9ef8175385`.
- Main CI `34946537685`: 5/5 PASS; main provenance: PASS.
- RC `vf-v3-01-rc19` → `dc8ff55322267dfe54674fa6c4003a899bf235ab`.
- RC CI `34875483864`: 5/5 PASS.
- Executable-tree SHA:
  `432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
- RC/main dual-CI provenance: PASS; SHA-256
  `77445b206e8712f4b24ddc0910ef18b41264154b26189748c60c1fdc4f632171`.
- Source drift: NONE; scope drift: PASS.

## RC-19 Operation 1 authority

- Operation:
  `v3-01-rc19-openai-transcription-asr-al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd-call-01`.
- Execution-scope SHA:
  `7d51c74c2b7c9efe3a12f99d1849997e682bdc028850e8af90db8f5497879a85`.
- Prepared scope SHA:
  `eeac77edc3e88309d1d3b3a883ae5b7c5618fb6a5907f7c13eb3595829fbde49`.
- Operation-manifest SHA:
  `d24e29259fd2cea90f539fc2e60b213f7b9522a515de18defda606607a0673ca`.
- Preparation-template SHA:
  `30979114a9ee55fc4bec60433b565ae1473bbbc17ecaf2c2bddbb3b57195ce0f`.
- G-01 `V3-01-APP-075`: PASS,
  `f6f85619d9ed44fd9a2227b7fb17eb1a5104bc98f1fed5de30e1d583a9657b8c`.
- G-02 `V3-01-APP-076`: PASS,
  `a0c19efa2d18b9f2889271f5578ab2fdafde02d3e7811d137c053d31d3b99055`.
- G-03 `V3-01-APP-077`: PASS,
  `9fc098b30e82f5b592cd243dc9235e6934c6ad8576a8c9e8106719eaba7af995`.
- Final runtime bundle SHA:
  `9dc8b99a8c10fbb1e8e2ba1a6f4a908b8322bca45c6a09d34d14f32a15cf5cdc`.
- Loaded runtime scope SHA:
  `10df8f6da5418c74511692368aaa27084950379e6695b9a4f92aefe0358313b1`.
- Authority receipt SHA:
  `2f4a322a5d3e97861a08412336ccbf0a0fdcc0e0e4c75b75901ec0c38d3bf8e0`.
- Authority: **GRANTED_NOT_CONSUMED**; confirmation token not required by the
  verified ASR contract.

The final bundle reproduced twice with identical bytes and the real gate loader
returned `PASS / VALID` in memory. The bundle is **UNMOUNTED**; loader validation
is not runtime activation.

## Exact window and budget

- Authorized window: 2026-09-16 21:00 → 2026-09-17 01:00 ICT;
  2026-09-16 14:00 → 18:00 UTC; start inclusive, end exclusive.
- 500 VND per Operation 1; 1,250 VND total window ceiling; modeled cost
  326.3004 VND.
- Attempts/concurrency: 1/1; retry/fallback: 0/0; provider/controller timeout:
  90/120 seconds.
- No budget was reserved by B9.

## Durable state after authority materialization

- Canonical ledger: `vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed`.
- PostgreSQL `16.15`, system identifier `7685665008963764889`, database OID
  `16384`, schema `public`, peer role `vang_nguyen`.
- A fresh `REPEATABLE READ, READ ONLY` transaction found all execution tables
  empty: Operation 1 row absent and not consumed; provider request receipt NONE;
  reservation NONE; reserved amount `0`; duplicate/idempotency collision NONE.
- Ledger mutations by B9: 0.

## Immutable inputs and safety

- Provider/model/capability/language:
  `openai-transcription / whisper-1 / asr / vi`.
- W1 profile SHA:
  `9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1`.
- Prompt SHA:
  `6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48`.
- Asset SHA:
  `fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef`.
- Reference transcript SHA:
  `585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e`.
- RightsRecord SHA:
  `5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091`.
- Kill switch: ENGAGED; credential reads: 0; provider calls: 0; production
  business writes: 0; actual cost: 0 VND.
- Operation 2: NOT_APPROVED / LOCKED / NOT_TRANSFERRED.
- ASR: 0/2 PASS; Vision: 2/2 PASS; Production: NO-GO.

## Validation and evidence

- Deterministic materializer and real loader: PASS.
- Focused B9 fail-closed suite: 77 PASS.
- Post-materialization durable readback: PASS / READ ONLY.
- Exact materialization-head candidate CI `34962924047`: 5/5 PASS, including
  1,134 Python/API/worker/bridge tests and Docker deterministic E2E. This CI
  does not authorize B10 or execution.
- [B9 evidence pack](../../../evidence/v3-01/vf-v0s-b9-20260915-final-authority/README.md).
- [Machine-readable handoff](handoff.json).
- Review branch: `governance/vf-v0s-b7-rc19-asr-w1-prepared`.
- [Draft PR #71](https://github.com/vangnguyen/npd-video-factory-v2/pull/71):
  OPEN / DRAFT / NOT_MERGED.

## Next safe action — recommendation only

**VF-V0S-B10 — zero-call operation-bound bootstrap qualification using the
exact final authority and final bundle.** Do not mount the bundle, read provider
credentials, reserve budget, disengage the kill switch, or dispatch a provider
in B10.
