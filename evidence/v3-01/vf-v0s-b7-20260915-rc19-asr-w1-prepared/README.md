# VF-V0S-B7 — RC-19 ASR W1 Operation 1 prepared rebind

This evidence pack records a fresh RC-19-bound Operation 1 identity and an
unsigned preparation package. The end state is **PREPARED_NOT_AUTHORIZED**.
Nothing in this pack is an Owner approval, authority receipt, confirmation
token, active window, loader-valid runtime bundle, budget reservation or
provider evidence.

## Outcome

- Governance main, RC-19, executable tree and dual-CI provenance: **PASS**.
- Canonical RC-19 PostgreSQL custody: **VERIFIED** and still virgin.
- Immutable W1 profile, prompt, asset, reference transcript and RightsRecord:
  exact hash match.
- Fresh lineage: `al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd`.
- Fresh Operation 1: `v3-01-rc19-openai-transcription-asr-al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd-call-01`.
- Exact ledger lookup: no operation/attempt/request receipt, consumed state,
  active reservation or duplicate/idempotency collision.
- No prepared-operation metadata write was required or performed.

## Prepared material

The deterministic generator and generated artifacts live under
`docs/acceptance/v3-01/prepared/vf-v0s-b7-rc19-asr-w1/`.

- execution-scope SHA-256:
  `7d51c74c2b7c9efe3a12f99d1849997e682bdc028850e8af90db8f5497879a85`
- scope SHA-256:
  `eeac77edc3e88309d1d3b3a883ae5b7c5618fb6a5907f7c13eb3595829fbde49`
- operation-manifest SHA-256:
  `d24e29259fd2cea90f539fc2e60b213f7b9522a515de18defda606607a0673ca`
- preparation bundle/template SHA-256:
  `30979114a9ee55fc4bec60433b565ae1473bbbc17ecaf2c2bddbb3b57195ce0f`

The gate template deliberately has no G-01/G-02/G-03 records, authority
receipt, confirmation token or final runtime-bundle identity. It is therefore
non-executable and must fail the real gate loader until later bounded tasks
materialize those missing approvals.

## Proposal only

- Window: `2026-09-16 21:00` to `2026-09-17 01:00` ICT
  (`2026-09-16 14:00` to `18:00` UTC), **PROPOSED_NOT_AUTHORIZED**.
- Modeled cost: `326.3004 VND`, based on 120.852 seconds at the approved
  accounting basis of `162 VND/minute`.
- Proposed ceilings: `500 VND` per operation and `1,250 VND` per window.
- One attempt, one concurrent call, provider/controller timeouts 90s/120s,
  retry/fallback 0/0.

## Safety boundary

Kill switch remains `ENGAGED`; bundle remains `UNMOUNTED`; Operation 2 remains
`NOT_APPROVED / LOCKED / NOT_TRANSFERRED`. Credential reads, budget reserved,
real provider calls, production business writes and actual cost are all zero.

## Stop boundary

The next safe action is Owner assignment of **VF-V0S-B8 — zero-call
operation-bound bootstrap qualification**. Do not proceed to Owner approvals,
authority/window activation, bundle mount, credential access, reservation or
provider dispatch in this task.
