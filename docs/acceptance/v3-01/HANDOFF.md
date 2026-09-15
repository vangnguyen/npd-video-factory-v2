# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B10
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

## Final authority and gate material

- Operation:
  `v3-01-rc19-openai-transcription-asr-al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd-call-01`.
- Execution-scope SHA:
  `7d51c74c2b7c9efe3a12f99d1849997e682bdc028850e8af90db8f5497879a85`.
- Prepared scope SHA:
  `eeac77edc3e88309d1d3b3a883ae5b7c5618fb6a5907f7c13eb3595829fbde49`.
- Operation-manifest SHA:
  `d24e29259fd2cea90f539fc2e60b213f7b9522a515de18defda606607a0673ca`.
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
- Authority: **GRANTED_NOT_CONSUMED**.

The bundle reproduced twice with identical bytes and the real gate loader
returned `PASS / VALID_IN_MEMORY_NOT_MOUNTED`. It was loaded only in memory for
validation and was never mounted for execution.

## RC-19 final-authority bootstrap qualification

- Entrypoint: `python -m app.provider_runtime_bootstrap` from the exact detached
  `vf-v3-01-rc19` source.
- Binding SHA:
  `0387f6a8c432e609b01b398fea739438160c3b8ccb975afe59c643fc39760779`.
- Mode: `ZERO_CALL_CUSTODY_ONLY / --require-virgin-namespace`.
- `--initialize-control` was not supplied; transaction isolation was
  `REPEATABLE READ, READ ONLY`.
- Real bootstrap exit: 0; low-level result:
  `CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED`.
- Contract classification: `BOOTSTRAP_BINDING_VALID`.
- `RC19_OPERATION_BOUND_BOOTSTRAP = VERIFIED`.
- Ready state: `READY_FOR_EXECUTION_PREFLIGHT`.
- Provider-dispatch ready: **NO**.

This task structurally verified the already-approved window and budget. It did
not evaluate the clock for execution, check credentials, reserve funds, mount
the bundle, transition the kill switch or enter a dispatch path.

## Durable ledger after qualification

- Canonical ledger: `vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed`.
- PostgreSQL `16.15`, system identifier `7685665008963764889`, database OID
  `16384`, schema `public`, peer role `vang_nguyen`.
- Operation state: `VIRGIN_NOT_REGISTERED / NOT_CONSUMED`.
- Operations/attempts/budget-days/circuits/budget-alerts: 0/0/0/0/0.
- Provider request receipt: NONE; active reservation: NONE; duplicate or
  idempotency collision: NONE; reserved VND: `0`.
- Bootstrap/ledger mutations by B10: 0.

## Window, budget and safety

- Bound window: 2026-09-16 21:00 → 2026-09-17 01:00 ICT;
  2026-09-16 14:00 → 18:00 UTC; start inclusive, end exclusive.
- 500 VND per Operation 1; 1,250 VND window ceiling; modeled cost 326.3004 VND.
- Attempts/concurrency: 1/1; retry/fallback: 0/0; timeouts: 90/120 seconds.
- Kill switch: ENGAGED; bundle mounted: NO; credentials read: 0; budget
  reserved: 0 VND; provider calls: 0; production business writes: 0; actual
  cost: 0 VND.
- Operation 1: NOT_CONSUMED. Operation 2: NOT_APPROVED / LOCKED /
  NOT_TRANSFERRED.
- ASR: 0/2 PASS; Vision: 2/2 PASS; Production: NO-GO.

## Validation and evidence

- Exact RC-19 bootstrap invocation: PASS / exit 0.
- Linux bootstrap contract suite against exact RC-19 source: 90 PASS.
- Deterministic materializer and real loader: PASS.
- B10 qualification-head candidate CI `34970455978` at
  `2bd78bc55beb51763d5d9971c46cd5c445b9bf45`: 5/5 PASS, including 1,142
  Python/API/worker/bridge tests and Docker deterministic E2E.
- [B10 evidence pack](../../../evidence/v3-01/vf-v0s-b10-20260915-final-bootstrap-qualification/README.md).
- [Historical B9 authority evidence](../../../evidence/v3-01/vf-v0s-b9-20260915-final-authority/README.md).
- [Machine-readable handoff](handoff.json).
- Review branch: `governance/vf-v0s-b7-rc19-asr-w1-prepared`.
- [Draft PR #71](https://github.com/vangnguyen/npd-video-factory-v2/pull/71):
  OPEN / DRAFT / NOT_MERGED.

## Next safe action — recommendation only

**VF-V0S-B11 — fresh in-window execution preflight on 16/09/2026.** This is a
future Owner-assigned task only. B10 grants no dispatch and performs no part of
B11.
