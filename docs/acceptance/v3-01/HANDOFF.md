# Video Factory V3-01 — VF-V0S-B4

Canonical machine handoff: [handoff.json](handoff.json). No root duplicates.

VERDICT: PASS — exact approved PR #65 merged; exact-main CI/regression/provenance PASS.
Main/merge SHA: dc8ff55322267dfe54674fa6c4003a899bf235ab.
Approved PR head: 40d8de37e8fb4294a478422ed4f5f546e815ef55.
Pre-merge main: 4507fa593fd8cf5484eb1245f788e9ee54eede39.
Old executable-tree SHA: ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5.
New executable-tree SHA: 432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502.
Expected approved candidate tree match: PASS. Source drift: NONE.

## Merge, CI and provenance

[PR #65](https://github.com/vangnguyen/npd-video-factory-v2/pull/65) merged only at the Owner-approved exact head.
G-08: PASS. All 20 reviewed paths/blob identities unchanged before controlled merge.
Merge parents bind exact baseline and exact approved head. Full Git tree equals
the approved candidate; no merge-resolution source mutation.
Candidate CI 34866823280: 5/5 PASS, retained as pre-merge evidence only.
[Exact-main CI 34869652973](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34869652973):
completed/success, push/main, exact head dc8ff55322267dfe54674fa6c4003a899bf235ab, all canonical jobs 5/5 PASS.
MAIN PROVENANCE: PASS. Canonical executable algorithm unchanged; 12 local/GitHub
objects match and two recomputations produce the new hash above.

## Current source and RC boundary

Entrypoint: python -m app.provider_runtime_bootstrap.
Zero-call custody phase only, no provider dispatch entrypoint.
Database identity is RC tag + full canonical lineage-derived; peer socket/system ID/
database OID/role/schema/PG16 independently pinned. RC18 hardcode: NO.
RC18 is NOT the current-main executable tree; this source-remediation mismatch is expected.

RC18: vf-v3-01-rc18 -> 03e18c1f0c56fff8a13f167af74f34894c2db811.
RC18 tag object: 30ca09c4201cd6aea5e733c26ba4dfa1f30d5021; IMMUTABLE_HISTORICAL.
RC17: vf-v3-01-rc17 -> d08ffc005d7f3ad517d355977b0bc3cc8d686906.
RC17 tag object: ea67843635dddf94ee25d38111fc06782ad9fd74; IMMUTABLE_HISTORICAL.
RC18 -> current-main dual-CI is NOT VALID because the executable tree/runtime diff changed.
No old RC18 dual-CI PASS is claimed for the new main.

NEW_RC_REQUIRED: YES. NEW_RC_CREATED: NO.
FRESH_LEDGER_BINDING_REQUIRED: YES. Future execution namespace: NOT_CREATED.
FRESH_EXECUTION_WINDOW_REQUIRED: YES. No previous window is inherited.

## Authority and zero-call boundary

RC18 historical authority: GRANTED_NOT_CONSUMED.
Its current applicability is HISTORICAL_REFERENCE_ONLY / INVALID_FOR_CURRENT_MAIN.
That applies to old Operation 1 ID, bundle, authority receipt, window, scope hashes,
confirmation-token/reservation bindings. Original historical bytes are not changed.
Current-main Operation 1 authority: NOT_CREATED_FOR_CURRENT_MAIN.
Operation 2: NOT_APPROVED / LOCKED / NOT_TRANSFERRED.
Kill switch: ENGAGED. Bundle: UNMOUNTED. External/paid execution: FALSE.
No RC, rebind, operation identity/package, scope, bundle, window or authority created.
Provider credential reads: 0. Live budget reserved: 0 VND.
Production business writes: 0. Real provider calls: 0. Actual cost: 0 VND.

## Regression and test writes

Exact-main local Python/API/worker/bridge: 1048/1048 PASS (203.88 seconds).
Exact-main CI Python: 1048/1048 PASS (64.46 seconds).
Bootstrap subset: 90 tests; pre-merge bootstrap/repository/provenance focused subset: 135 PASS.
Studio: 14/14 PASS. Renderer: 14/14 PASS, typecheck and bundle PASS.
Safety/Compose and full deterministic Docker E2E: PASS on canonical exact-main CI.
Compileall and migration replay 0001..0014 -> base -> 0014: PASS.
Read-only PostgreSQL custody: 2 pre-existing B3 synthetic test databases; repeat
reads identical, 9 wrong identity/cross-RC denials, no writes or new namespace.
Historical RC18 execution database was not accessed or mutated.
Only isolated Python/SQLite and CI disposable Docker fixtures perform test metadata writes.
Those are not live reservations, provider execution, business production writes
or Operation 1 consumption.
Acceptance/evidence: PASS, 39 registered evidence runs.
Flow A/B/C/DR expected BLOCKED boundary tests: PASS; no aggregate acceptance upgraded.
JSON: 434 tracked files parse. Secret scan: PASS_ZERO_MATCHES.
Diff check: PASS. Historical B3 baseline: 19 checksums/25 Markdown links verified.

## Evidence history and handoff publication

[Post-merge evidence](../../../evidence/v3-01/vf-v0s-b4-20260914-exact-main-verification/README.md).
[Post-merge verifier](reviews/vf-v0s-b4/verify_postmerge.py).
B3 prior canonical handoff is preserved at dc8ff55322267dfe54674fa6c4003a899bf235ab.
B3 original fixtures/evidence/checksum manifest/receipts are not rewritten.
B3 final archive-copy network timeout is preserved with exact artifact ID/digest;
that optional local download did not fail the independently successful candidate CI.
The canonical CI job/required upload succeeded; no gate is bypassed.
The old archive is not used as substitute for post-merge exact-main CI.
This separate governance-only draft handoff is not auto-merged in VF-V0S-B4.
It records the completed main checkpoint, not future CI for its own closing commit.

ASR: 0/2 PASS. Vision: 2/2 PASS. Production: NO-GO.
Historical provider verdicts/costs/transcripts/receipts and quality thresholds unchanged.
Scope drift: PASS. Blockers: NONE for VF-V0S-B4 verification.

NEXT_SAFE_ACTION: Owner assign VF-V0S-B5 — fresh RC materialization from exact verified main.
STOP before RC creation, new ledger namespace, operation rebind, window, authority,
bundle mount, credentials, live reservation or provider dispatch.
