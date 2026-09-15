# RC-19 ASR W1 Operation 1 preparation package

Status: **PREPARED_NOT_AUTHORIZED**. This package creates no Owner gate record,
authority receipt, confirmation token, active window, mounted bundle, reservation,
credential read or provider call.

## Fresh identity

- RC: `vf-v3-01-rc19` -> `dc8ff55322267dfe54674fa6c4003a899bf235ab`
- Governance main: `7ad25cb039c712d450486778d2981d9ef8175385`
- Executable tree: `432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`
- Dual-CI provenance: PASS, `77445b206e8712f4b24ddc0910ef18b41264154b26189748c60c1fdc4f632171`
- Lineage: `al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd`
- Operation 1: `v3-01-rc19-openai-transcription-asr-al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd-call-01`
- Canonical ledger: `vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed`
- Ledger state: `VIRGIN_NOT_REGISTERED / NOT_CONSUMED`
- Ledger operation binding: `867ec5d9eb6b3b4756d74a051941ca3104a7c4a370832df263dea261828bcf63`

The operation name follows the existing identity-v2 contract. The scope and
manifest bind governance/provenance/tree, ledger, W1 profile/prompt, assets,
references, RightsRecords, proposed budget/window and terminal rules. RC-18
operation-specific identity, scope, bundle, authority, window and reservation
are historical only and were not transferred.

## Prepared hashes

- execution-scope SHA: `7d51c74c2b7c9efe3a12f99d1849997e682bdc028850e8af90db8f5497879a85`
- scope SHA: `eeac77edc3e88309d1d3b3a883ae5b7c5618fb6a5907f7c13eb3595829fbde49`
- operation manifest SHA: `d24e29259fd2cea90f539fc2e60b213f7b9522a515de18defda606607a0673ca`
- preparation bundle/template SHA: `30979114a9ee55fc4bec60433b565ae1473bbbc17ecaf2c2bddbb3b57195ce0f`

`gate-template.json` is intentionally not loader-valid: G-01/G-02/G-03 and
final runtime/authority material do not exist. `bootstrap-binding-plan.json`
keeps those slots unbound. A later bounded task must not substitute this
preparation hash for a final runtime bundle or authority receipt.

## Proposal only

- Window: **2026-09-16 21:00 -> 2026-09-17 01:00 ICT**
  (2026-09-16 14:00 -> 18:00 UTC), `PROPOSED_NOT_AUTHORIZED`.
- 500 VND per operation; 1,250 VND window; modeled asset-01 cost 326.3004 VND.
- One attempt, concurrency one, provider/controller timeout 90s/120s,
  retry/fallback 0/0.

Official OpenAI documentation observed on 2026-09-15 lists `whisper-1` at
$0.006 per minute. The fixed 27,000 VND/USD value is the already approved
accounting basis, not a live FX claim. Any price/FX/binding drift fails closed.

Kill switch ENGAGED; bundle UNMOUNTED; Operation 2 NOT_APPROVED / LOCKED /
NOT_TRANSFERRED. Credential reads, budget reserved, provider calls, production
business writes and actual cost are all zero.

**NEXT_SAFE_ACTION: VF-V0S-B8 — zero-call operation-bound bootstrap
qualification. Stop before Owner approvals, authority/window activation,
bundle mount, credentials, reservation or provider dispatch.**
