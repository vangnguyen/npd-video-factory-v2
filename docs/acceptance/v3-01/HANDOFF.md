# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B5
VERDICT: REVIEW_REQUIRED
REPO: vangnguyen/npd-video-factory-v2

## Verified source and RC

- Main: `dc8ff55322267dfe54674fa6c4003a899bf235ab`; main CI `34869652973`: 5/5 PASS; main provenance: PASS.
- Canonical executable-tree SHA: `432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
- RC sequencing: PASS, tags 1–18 existed and RC-19 was absent immediately before creation.
- New annotated `vf-v3-01-rc19` → `dc8ff55322267dfe54674fa6c4003a899bf235ab`, tag object `09a9a51628ab2e33d4ee85a1620f7afca692d18e`.
- Tagger date: `2026-09-14T17:33:21Z`; tag/commit, tag/tree, main/RC tree equality: PASS.
- RC CI `34875483864`: attempt 1, workflow_dispatch on exact tag, completed/success, 5/5 PASS.
- Bootstrap entrypoint: `python -m app.provider_runtime_bootstrap`, present in exact RC source.
- Source mutation: NONE. Runtime ledger qualification: NOT_PERFORMED.

## Unclosed gate

Main/RC dual-CI: **BLOCKED_DISTINCT_GOVERNANCE_MAIN_REQUIRED**.
The real canonical collector exited 2 / `CI_PROVENANCE_INVALID`. Both CI runs passed independently,
but RC and current main are the same commit; the actual governance diff is empty. The existing schema
requires distinct commits and a nonempty allowlisted diff. No fake path, substituted CI, validator change
or false dual-CI PASS was used. RC-19 is materialized; authoritative governance closure remains pending.

## Execution safety

Operation 1 ID: NOT_GENERATED. Operation 1 authority: NOT_CREATED.
Fresh ledger binding, Operation 1 rebind, fresh authority and fresh execution window: REQUIRED.
Operation 2: NOT_APPROVED / LOCKED / NOT_TRANSFERRED.
Kill switch: ENGAGED. Bundle: UNMOUNTED. External/paid execution: false.
Runtime ledger writes: 0. Provider credential reads: 0. Budget reserved: 0 VND.
Real provider calls: 0. Production business writes: 0. Actual cost: 0 VND.
Tests/CI used only isolated disposable fixtures, not a real RC-19 execution ledger.

RC-18 remains IMMUTABLE / HISTORICAL at `03e18c1f0c56fff8a13f167af74f34894c2db811`,
tag object `30ca09c4201cd6aea5e733c26ba4dfa1f30d5021`, old tree
`ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.
RC-18 material remains HISTORICAL_REFERENCE_ONLY / INVALID_FOR_CURRENT_MAIN and is not transferred.
RC-17 is unchanged. No old operation ID, scope, bundle, approval, receipt, token binding, window,
ledger namespace or reservation was reused.

## Future ledger naming preview

Assuming sequence 1 for W1/openai-transcription/whisper-1/asr under exact RC-19:
`vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed`.

Status: PLAN_ONLY_NOT_CREATED_OR_APPROVED. Formula: `vf_` + RC tag with hyphens replaced by underscores +
`_` + first 32 hex characters of SHA-256(UTF-8(RC tag + LF + full canonical acceptance lineage ID)).
Actual instance/socket/system ID/database OID/peer role/port/public schema must be pinned in a later task.
No database connection, namespace creation, durable registration, reservation or fresh Operation ID
generation occurred. Do not reuse historical RC18 custody or B3 synthetic RC19/RC20 test databases.

## Validation and acceptance

Focused bootstrap/provenance/lineage/W1/loader: 284 PASS, 6.40 s.
RC CI Python/API/worker/bridge: 1048 PASS, 55.33 s. Studio: 14 PASS. Renderer: 14 PASS + typecheck/bundle.
Safety/Compose, Docker deterministic E2E, migration replay, acceptance/evidence and expected-blocked
Flow A/B/C/DR boundaries: PASS. Canonical hash independently reproduced in two clean source worktrees
and matched all 12 GitHub objects.

ASR: 0/2 PASS. Vision: 2/2 PASS. Production: NO-GO.

## Evidence and historical draft

- [B5 evidence/reproduction](../../../evidence/v3-01/vf-v0s-b5-20260915-rc19-materialization/README.md)
- [Machine-readable handoff](handoff.json)
- [PR #66](https://github.com/vangnguyen/npd-video-factory-v2/pull/66): OPEN / DRAFT / NOT_MERGED,
  exact head `71609bdb691ceabb9cc1b4ee3175260a28132395`, CI `34871006869` 5/5 PASS; unchanged.
- B4 provenance is imported verbatim by original SHA; full original pack remains on PR #66.
- Previous canonical handoff/checksums remain in exact-main Git history. No historical receipt was rewritten.

## Next safe action — recommendation only

Owner G-08 review of the separate B5 governance-only draft; a later controlled merge, fresh exact-main CI
and RC-19/main dual-CI closure are required. Do not merge automatically.
STOP before ledger creation, Operation 1 rebind, authority/window creation, bundle mount,
credential access, reservation or provider dispatch. This handoff does not preclaim its own future commit CI.
