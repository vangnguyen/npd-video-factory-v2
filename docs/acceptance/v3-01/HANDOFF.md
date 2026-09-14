# Video Factory V3-01 — VF-V0S-B3

Canonical machine handoff: [handoff.json](handoff.json). No root duplicates.
Historical handoffs and receipts remain immutable in their original commits.

VERDICT: REVIEW_REQUIRED — exact-head candidate CI pending.
Base main: 4507fa593fd8cf5484eb1245f788e9ee54eede39.
Branch: remediation/vf-v0s-b3-runtime-ledger-bootstrap.
Candidate executable-tree SHA: 432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502.
Historical RC18 tree: ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5.

## Scope and lineage

Only runtime addition is apps/api/app/provider_runtime_bootstrap.py.
Entrypoint: python -m app.provider_runtime_bootstrap.
Zero-call custody phase only; no dispatch mode, key/settings import or live reservation.
Database derives from RC tag plus full canonical lineage, independently pinned to
peer socket/system/database/role/schema/version. No RC18 hardcode or fallback.

B2 local history is sealed at 1c3eb35b52337bc9aeda0fad93ec3b3bd00d089d.
Its unmerged I/T/U/S/B1 receipts/authority are not imported into the new source PR.
Historical RC18-era database is not a final future lineage binding and is untouched.
RC17 and RC18 tag objects/commits remain immutable. Candidate is NOT RC18.
New RC is required only after a later Owner merge and exact-main regression.

## Tests and CI

Pre-hardening Python/API/worker/bridge: 1047 PASS, 0 failed, 286.55 seconds.
Post-hardening serial Python/API/worker/bridge: 1048/1048 PASS, 190.99 seconds.
The overlapped E2E/pytest environment failure is retained and reproduced separately;
its clean isolated rerun passed. No test or CI gate was skipped or relaxed.
Bootstrap: 90 PASS. Focused bootstrap/repository/provenance: 135 PASS after hardening.
Studio: 14/14 PASS. Renderer: 14/14 PASS, typecheck and bundle PASS.
PostgreSQL: two isolated test databases, full 0001..0014 replay PASS,
identical repeat reads and nine wrong custody/cross-RC denials.

WSL Git: reproduced 2/2 original failures (Windows-absolute .git worktree pointer).
Identical historical cases: native Git 2/2 PASS (6.52s), correct mapped WSL metadata
2/2 PASS (13.49s). No historical validator, receipt or canonical hash relaxed.
Full candidate suite ran independently, not a claim that B2's failed sweep was clean.

Docker E2E: PASS on pre-hardening source snapshot; final source CI must independently
pass full E2E. Candidate CI: PENDING_DRAFT_PR_AND_EXACT_HEAD_VERIFICATION.
Historical main/RC18 CI are baseline evidence ONLY, not candidate CI substitutes.

## Authority and write boundary

RC18 historical authority: GRANTED_NOT_CONSUMED / INVALID_FOR_NEW_CANDIDATE.
Candidate authority: NOT_CREATED. No rebind, scope/bundle/window/token/authority generated.
Operation 2: NOT_APPROVED / LOCKED / NOT_TRANSFERRED.
Kill switch: ENGAGED. Bundle: UNMOUNTED. External/paid execution: FALSE.
Provider credential reads: 0. Live reservations: 0 VND.
Real provider calls: 0. Production business writes: 0. Actual cost: 0 VND.
Isolated test catalog/schema/control writes and fixture writes are reported separately.

ASR: 0/2 PASS. Vision: 2/2 PASS. Production: NO-GO.
Historical provider verdicts/costs/receipts and quality thresholds remain unchanged.

## Evidence and stop

[Evidence bundle](../../../evidence/v3-01/vf-v0s-b3-20260914-bootstrap-candidate/README.md).
[Source G-08](reviews/vf-v0s-b3/G08_SOURCE_REVIEW.md).
[WSL RCA](reviews/vf-v0s-b3/WSL_GIT_RCA.md).
[Local validation environment RCA](reviews/vf-v0s-b3/LOCAL_VALIDATION_RCA.md).

Scope drift: PASS. G-08 scope PASS, conditional on exact final-head CI and Owner review.
NEXT_SAFE_ACTION: Owner review exact candidate head after CI; STOP before merge,
new RC creation, operation rebind, authority, bundle mount, credentials, reserve or dispatch.
