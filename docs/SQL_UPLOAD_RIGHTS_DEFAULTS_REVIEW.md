# SQL upload rights defaults

New uploads without a rights declaration now keep `rights_status=unknown`.
The generic Studio checkbox confirms permission to use media in the project;
it no longer labels that permission as ownership. A completed upload tells the
user that publishing rights need separate review. The audio speech panel's
explicit ownership declaration remains unchanged.

Existing upload sessions, assets, accepted artifacts and their rights records
are not migrated or rewritten. Duplicate detection keeps the existing asset's
provenance: a new owned declaration cannot upgrade an existing unknown asset,
and an omitted declaration cannot downgrade an existing owned/licensed asset.
The publishing gate reads the actual asset and continues to block unknown rights.

WAVE: 3/5 — Ingestion and media rights increment.

STATUS: The default-policy defect is fixed and locally tested. Full waves remain PARTIAL.

HEAD SHA: `8840e44ebd66c12517d7084d9b7e788ab9aeda8c` (product commit).

CAPABILITIES COMPLETED: Honest default for all six upload roles; generic Studio
upload initialization; persisted provenance, duplicate preservation and existing
publishing rights gate. Explicit owned/licensed declarations still work.

CAPABILITIES PARTIAL: Full rights evidence/operator workflow, real legal
verification, explicit Owner exceptions and original complete Mode A/B acceptance.

TESTS: 23 SQLite/API cases PASS in 56.32 seconds, including 10 new policy cases,
two existing upload cases, the owned-media resolver path and 10 service-intake
regressions. 69 affected Node cases PASS in 395.843 ms, including six new emitted
request checks and the existing explicit audio ownership flow. Independent
review adds two actual-main SQLite/ASGI cases (27.42 seconds) and one full
initializeMultiInput fake-DOM case (97.7302 ms). Runs overlap; do not add counts.

REAL PROVIDER TESTS: None. No paid operation, provider request or legal certification.

MOCK TESTS: Real owned SQLite, local storage and synthetic WAV bytes decoded by
Python's WAV reader; identity, HTTP transport, ASR/media probes and DOM are
fixtures where stated. Independent API captures persist/read/resume chunks,
complete, read canonical assets and replay completion for omitted/explicit rights.

EVIDENCE: [Hashed support index](north-star/upload-rights-defaults-evidence.json),
six-file source ZIP, independent report, request captures and raw test logs.

REGRESSIONS: Final scoped checks pass. The existing default-upload assertion now
expects unknown. The existing owned-media fixture explicitly declares ownership;
its resolver/publishing assertions remain. Initial SQL RED contained six valid
policy failures and four test-harness errors from calling get_asset on the wrong
repository. Corrected RED preserves four actual policy failures; frontend RED
preserves five failures/one pass. These are historical repros, not final failures.
The first inventory helper stopped before commit because two old test files
were outside the previous audited subset; the inspected resume includes them.

EXTERNAL BLOCKERS: Current browser observation is policy-denied. Real rights,
providers, Owner acceptance, PostgreSQL/production and full A/B/C remain separate.

OWNER ACTION REQUIRED: None for safe implementation. Real publication still needs
the existing rights, platform, approval, credential and Owner enablement gates.

NEXT WAVE: Continue witness-aware B-roll preparation and explicit terminal-release
UI, then the remaining original North Star capabilities.

Compatibility: a historical service idempotency request that omitted rights and
was recorded with the old owned default may fail closed with 409 under the new
default. This is a static compatibility finding, not an independently exercised
historical production scenario. Existing receipts stay immutable; no duplicate,
automatic new key, provenance rewrite or silent rights upgrade is authorized.

SOURCE_PRESERVED=YES. IMPLEMENTATION_COMPLETE=NO;
REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO.
The matrix remains 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED:
59 broad groups remain unclosed. Owner Phase 10 UAT remains deferred.
