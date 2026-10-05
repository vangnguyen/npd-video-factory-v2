PHASE: 9B — CONTENT INTELLIGENCE DOMAIN MODEL

STATUS: PASS

HEAD SHA: Parent release-freeze commit `8f0aacc0206b462c542b58c56c196f8fd0e3fb21`; implementation commit recorded in Git history with this evidence.

FILES CHANGED: `intelligence_models.py`, `intelligence_store.py`, `test_intelligence_models.py`, this evidence and `domain-tests.log`.

TESTS: Four meaningful domain/persistence tests PASS, including a separate-process reopen, stale-write refusal, immutable-history tamper refusal, attributed quote enforcement, timezone/provenance validation and no access to production data.

EVIDENCE: `domain-tests.log`; release baseline remains unchanged.

NEW CAPABILITIES: Eight canonical, business-neutral models with stable IDs, UTC timestamps, versions and provenance. Source-reported quotations, model inference and uncertain information are distinct. The local `intelligence.sqlite3` schema version 1 stores records, immutable versions, decisions and explicit operation receipts. Existing `workflow.sqlite3` is not migrated.

REGRESSIONS: No existing application files changed in this increment. Initial test cleanup exposed an open connection in the test; corrected and rerun PASS.

BLOCKERS: Research, idea generation, scoring, UI and practical acceptance are not yet certified.

NEXT ACTION: Implement bounded source retrieval and research/idea engines with transparent configurable scoring.
