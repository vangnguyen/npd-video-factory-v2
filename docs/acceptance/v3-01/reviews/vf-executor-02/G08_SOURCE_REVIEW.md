# G-08 — VF-EXECUTOR-02

**BLOCKED FOR ACCEPTANCE / NO MERGE RECOMMENDATION.** This is not O1 authority.

Bounded independent source review found the canonical adapter outcome and
qualification-receipt mismatch findings resolved. Ordered callbacks precede the
dispatch marker; cleanup cannot reset dispatch/consumption to initial zeros.
Raw qualification schema, manifest, tree and separate security evidence are
verified during promotion. Tests cover missing resources, hostile structured
inputs, ledger collisions, lock contention, zero-call probes, state ordering,
reservation-ack ambiguity and terminal cleanup failures.

Historical executable hashing is preserved; versioned executor hashing includes
the entire workflow tree. This candidate changes executable/runtime source and
requires O1, but is **not ready to request it**.

Remaining blockers: actual runner offline/quarantine; enforced admission security
not qualified; canonical custody/evidence/secret binding missing; MinIO registry
pull unavailable; Docker E2E and all live E1–E10 evidence absent. Unit tests and
source review do not discharge these. Exact final candidate, tests and CI are
recorded separately in the final handoff to avoid self-referential commit hashes.
