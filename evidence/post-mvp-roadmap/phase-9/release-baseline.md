# Phase 9A — accepted Internal Production Release

PHASE: 9A — RELEASE FREEZE

STATUS: PASS

HEAD SHA: `f61d8de6545653ea46f8ab5f91e6c0c0c167b7af`

Branch at capture: `codex/vf-post-mvp-roadmap-execution-01`.

INTERNAL_PRODUCTION_READY = YES

Scope: Windows Native internal production only; legacy stack not certified.

Release marker: annotated Git tag `internal-production-v1`, pointing to the exact accepted HEAD above. Repository release markers are annotated tags. No history rewriting or replacement of accepted evidence.

FILES CHANGED: This baseline, `release-baseline.json`, and the read-only capture helper `scripts/freeze-internal-production-release.py`.

TESTS: Accepted native 103/103 and Studio 27/27 PASS logs are bound by SHA-256. Application code is byte-identical to tested implementation `9c3e9e9dfa61fe29f76380f6811f4db1b0a26257`. Fresh read-only checks verify SQLite integrity, zero active jobs, ten current human final decisions, ten exact MP4 hashes, the locked voice SDK/model/preset/runtime. No new provider, TTS or render calls.

EVIDENCE: `release-baseline.json` captures all seven tables' DDL, row counts and row hashes; schema versions; installed runtime dependency inventory; immutable Phase 8 evidence hashes; exact final video paths/hashes/decisions. A consistent SQLite backup is preserved at `C:\NPD-Video-Factory\post-mvp-validation\owner-phase9-release-freeze-f61d8de65456.sqlite3`. Phase 8 evidence remains unchanged.

Persisted schemas: project-input-v1; native-editor-v1; native-brand-template-v1; timeline 1.1; checkpoint 1; voice profile 1. Existing project/job/version/review records remain intact. Native SQLite tables are additive, with exact DDL recorded instead of an invented historical migration version.

NEW CAPABILITIES: Stable accepted release marker and reproducible read-only baseline inventory.

REGRESSIONS: None observed in the accepted native scope. The historical legacy Windows failures remain outside that release's certificate.

BLOCKERS: None for Phase 9 development. New Content Intelligence practical cases require their own human selections and approvals.

NEXT ACTION: Add generic, versioned Content Intelligence records and a separate additive SQLite store; connect approved briefs to the existing native production system.
