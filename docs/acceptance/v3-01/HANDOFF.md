# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B8
VERDICT: REVIEW_REQUIRED
REPO: vangnguyen/npd-video-factory-v2

## Authoritative lineage

- Governance main: `7ad25cb039c712d450486778d2981d9ef8175385`.
- Main CI `34946537685`: 5/5 PASS; main provenance: PASS.
- RC `vf-v3-01-rc19` → `dc8ff55322267dfe54674fa6c4003a899bf235ab`.
- RC CI `34875483864`: 5/5 PASS.
- RC/main executable-tree SHA:
  `432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
- RC/main dual-CI provenance: PASS; SHA-256
  `77445b206e8712f4b24ddc0910ef18b41264154b26189748c60c1fdc4f632171`.
- Exact RC, governance main and current review head all reproduce the same
  executable tree.

## Prepared RC-19 Operation 1

- Operation:
  `v3-01-rc19-openai-transcription-asr-al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd-call-01`.
- Ledger operation key: exact Operation identity above.
- Execution-scope SHA:
  `7d51c74c2b7c9efe3a12f99d1849997e682bdc028850e8af90db8f5497879a85`.
- Prepared scope SHA:
  `eeac77edc3e88309d1d3b3a883ae5b7c5618fb6a5907f7c13eb3595829fbde49`.
- Operation-manifest SHA:
  `d24e29259fd2cea90f539fc2e60b213f7b9522a515de18defda606607a0673ca`.
- Preparation template SHA:
  `30979114a9ee55fc4bec60433b565ae1473bbbc17ecaf2c2bddbb3b57195ce0f`.
- Status: **PREPARED_NOT_AUTHORIZED**; G-01/G-02/G-03 and Owner authority
  remain NOT_CREATED. The proposed 2026-09-16 21:00 → 2026-09-17 01:00 ICT
  window remains PROPOSED_NOT_AUTHORIZED.

## B8 bootstrap qualification result

Bootstrap entrypoint: `python -m app.provider_runtime_bootstrap` from the exact
RC-19 detached source.

The real entrypoint returned `BOOTSTRAP_BINDING_INVALID` (exit 2) before source
or ledger access. Exact model diagnostics show only two invalid fields:

- `authority_receipt_sha256`: null is not accepted;
- `bundle_sha256`: null is not accepted.

The current bootstrap contract supports only `ZERO_CALL_CUSTODY_ONLY`. It has no
verified pre-authority qualification mode and no result equivalent to
`AUTHORITY_REQUIRED` or `READY_FOR_AUTHORITY_MATERIALIZATION`. Therefore
`RC19_OPERATION_BOUND_BOOTSTRAP = NOT_VERIFIED` and B8 cannot honestly PASS.

No placeholder receipt, RC-18 authority hash, self-signed approval or
preparation-template-as-runtime-bundle substitution was used. This is a
contract-ordering blocker, not an observed operation/ledger/scope hash mismatch.

## Durable ledger state after qualification attempt

- Canonical ledger: `vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed`.
- PostgreSQL `16.15`, system identifier `7685665008963764889`, database OID
  `16384`, schema `public`, peer role `vang_nguyen`.
- Independent `REPEATABLE READ, READ ONLY` audit: control
  `global/revision=0`; operation, attempt, budget, circuit, usage, cost and
  idempotency counts all zero.
- Operation record: absent; consumed: NO; provider request receipt: NONE;
  active reservation: NO; duplicate/idempotency collision: NONE;
  reserved amount: `0 VND`.
- Ledger mutations during B8: 0.

## Immutable inputs and safety state

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
- RightsRecord canonical SHA:
  `5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091`.
- Kill switch: ENGAGED; executable authority bundle: UNMOUNTED.
- Credential reads: 0; budget reserved: 0 VND; provider calls: 0; production
  business writes: 0; actual cost: 0 VND.
- Operation 2: NOT_APPROVED / LOCKED / NOT_TRANSFERRED.
- ASR: 0/2 PASS; Vision: 2/2 PASS; Production: NO-GO.

## Validation and evidence

- Dual-CI provenance revalidation: PASS with exact expected SHA.
- RC/main/review executable-tree equality: PASS.
- B7 deterministic prepared package: PASS, 12 files.
- Linux focused bootstrap/B7/B8 contract suite: 99 PASS.
- Full Linux Python/API/worker/bridge suite: 1,013 PASS.
- Native Windows rerun exposed the existing POSIX socket-fixture path mismatch;
  canonical Linux execution above is clean and no source was changed to hide it.
- Actual durable ledger read-only audit: PASS; no write.
- Actual bootstrap negative qualification: fail-closed as documented.
- JSON/checksum/secret/diff and broader focused safety results are recorded in
  the B8 evidence pack.
- [B8 evidence pack](../../../evidence/v3-01/vf-v0s-b8-20260915-operation-bootstrap-qualification/README.md).
- [Machine-readable handoff](handoff.json).
- Review branch: `governance/vf-v0s-b7-rc19-asr-w1-prepared`.
- [Draft PR #71](https://github.com/vangnguyen/npd-video-factory-v2/pull/71):
  OPEN / DRAFT / NOT_MERGED.

## Next safe action — recommendation only

Owner review of the contract-ordering blocker. Choose either a separately
authorized authority-before-bootstrap ordering using the existing contract, or
a separately bounded source remediation that adds a strict authority-absent
qualification mode. The latter changes the executable tree and would require a
fresh RC, custody rebind and operation rebind. Do not proceed to B9, create
authority, mount a bundle, access credentials, reserve budget or dispatch a
provider automatically.
