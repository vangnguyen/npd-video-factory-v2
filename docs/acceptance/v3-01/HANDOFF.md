# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B7
VERDICT: PASS
REPO: vangnguyen/npd-video-factory-v2

## Authoritative lineage

- Governance main: `7ad25cb039c712d450486778d2981d9ef8175385`.
- Main CI `34946537685`: 5/5 PASS; main provenance: PASS.
- RC `vf-v3-01-rc19` → `dc8ff55322267dfe54674fa6c4003a899bf235ab`.
- RC CI `34875483864`: 5/5 PASS.
- RC executable-tree SHA: `432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
- RC/main dual-CI provenance: PASS; provenance SHA-256
  `77445b206e8712f4b24ddc0910ef18b41264154b26189748c60c1fdc4f632171`.
- Bootstrap entrypoint: `python -m app.provider_runtime_bootstrap`.

## Canonical ledger and virgin state

- Ledger: `vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed`.
- PostgreSQL `16.15`, system identifier `7685665008963764889`, database OID
  `16384`, schema `public`, peer role `vang_nguyen`.
- Migration head `0014_v3_01_27`; control seed `global/revision=0`.
- State before rebind: `VIRGIN_READY_FOR_OPERATION_REBIND`.
- Exact fresh operation rows/attempts: 0/0; no consumed state, request receipt,
  active reservation or duplicate/idempotency collision.
- RC-18/RC-19 custody and operation identities remain isolated: PASS.
- No prepared-operation metadata write was required.

## Fresh RC-19 Operation 1 preparation

- Acceptance lineage:
  `al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd`.
- Operation 1:
  `v3-01-rc19-openai-transcription-asr-al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd-call-01`.
- Ledger operation key: exact Operation 1 identity above.
- Ledger operation binding SHA:
  `867ec5d9eb6b3b4756d74a051941ca3104a7c4a370832df263dea261828bcf63`.
- Execution-scope SHA:
  `7d51c74c2b7c9efe3a12f99d1849997e682bdc028850e8af90db8f5497879a85`.
- Scope SHA:
  `eeac77edc3e88309d1d3b3a883ae5b7c5618fb6a5907f7c13eb3595829fbde49`.
- Operation-manifest SHA:
  `d24e29259fd2cea90f539fc2e60b213f7b9522a515de18defda606607a0673ca`.
- Preparation bundle/template SHA:
  `30979114a9ee55fc4bec60433b565ae1473bbbc17ecaf2c2bddbb3b57195ce0f`.

The package status is **PREPARED_NOT_AUTHORIZED**. The gate template is
deliberately not loader-valid because G-01/G-02/G-03, Owner authority receipt,
confirmation-token binding and final runtime-bundle identity do not exist. The
preparation hash must never be substituted for a runtime authority bundle.

## Immutable ASR binding

- Provider/model/capability/language:
  `openai-transcription / whisper-1 / asr / vi`.
- W1 profile SHA:
  `9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1`.
- Prompt SHA:
  `6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48`.
- Asset 01 SHA:
  `fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef`.
- Reference transcript SHA:
  `585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e`.
- RightsRecord canonical SHA:
  `5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091`.

All values were recomputed from repository material; no RC-18
operation-specific identity, scope, bundle, authority, reservation or window
was inherited.

## Proposal and safety state

- Proposed window: `2026-09-16 21:00` → `2026-09-17 01:00` ICT
  (`2026-09-16 14:00` → `18:00` UTC), `PROPOSED_NOT_AUTHORIZED`.
- Modeled cost: `326.3004 VND`; proposed ceilings: `500 VND` per operation and
  `1,250 VND` per window.
- One attempt, concurrency one, 90s/120s provider/controller timeout,
  retry/fallback 0/0.
- Kill switch: ENGAGED. Bundle: UNMOUNTED.
- Operation 1: PREPARED_NOT_AUTHORIZED / NOT_CONSUMED.
- Operation 2: NOT_APPROVED / LOCKED / NOT_TRANSFERRED.
- Credential reads: 0; budget reserved: 0 VND; provider calls: 0; production
  business writes: 0; actual cost: 0 VND.
- ASR: 0/2 PASS. Vision: 2/2 PASS. Production: NO-GO.

## Validation and evidence

- Focused Linux bootstrap/gate/W1/safety suite: 473 PASS.
- Full Python/API/worker/bridge: 1,052 PASS.
- Studio: 14 PASS. Renderer: 14 PASS plus typecheck/bundle check.
- Migration replay, acceptance validation, deterministic package reproduction,
  Compose contract, JSON/checksum/secret/diff validation: PASS.
- [B7 evidence pack](../../../evidence/v3-01/vf-v0s-b7-20260915-rc19-asr-w1-prepared/README.md).
- [Machine-readable handoff](handoff.json).
- Review branch: `governance/vf-v0s-b7-rc19-asr-w1-prepared`.
- [Draft PR #71](https://github.com/vangnguyen/npd-video-factory-v2/pull/71):
  OPEN / DRAFT / NOT_MERGED; never merge automatically.
- Historical handoff/evidence remains in Git history; nothing was silently removed.

## Next safe action — recommendation only

Owner assignment of **VF-V0S-B8 — zero-call operation-bound bootstrap
qualification** using this exact prepared identity and the existing virgin RC-19
custody. Stop before G-01/G-02/G-03, Owner authority/window activation, final
runtime bundle mount, credential access, budget reservation, kill-switch
transition or provider dispatch.
