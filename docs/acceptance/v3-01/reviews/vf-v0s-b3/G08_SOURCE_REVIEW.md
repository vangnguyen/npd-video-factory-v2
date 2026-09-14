# G-08 source review — VF-V0S-B3

Scope review: PASS, subject to exact final-head candidate CI and Owner merge decision.
This report does not approve merge, a new RC, a window, or provider execution.

## Baseline and patch

Base main: 4507fa593fd8cf5484eb1245f788e9ee54eede39.
Only executable addition: apps/api/app/provider_runtime_bootstrap.py.
New/expanded test file: apps/api/tests/test_provider_runtime_bootstrap.py.
Remaining changes: canonical handoff, this offline review/tooling directory and redacted evidence.
No settings, .env.example, workflow, Compose, migration, adapter, ASR quality,
W1 profile, evaluator, timestamp consumer or ProviderSafetyRepository code changes.

All 24 B2 changes were audited: 1 bootstrap source, 1 test, 2 handoffs and 20
evidence files. B2 is preserved locally at
1c3eb35b52337bc9aeda0fad93ec3b3bd00d089d. The 194-file unmerged I/T/U/S/B1
governance chain is deliberately not imported from that branch into main.
No historical evidence is deleted or rewritten. B3 copies only the two B2 source/test
files and adds this independent review/evidence.

## Bootstrap and custody semantics

The new CLI is a zero-call custody phase of the existing safety plane, not a
parallel provider execution route. It calls the unchanged repository's ensure_state
only behind explicit initialization, verified source, private peer socket,
matching system/database/role/schema/major-version identity and an empty ledger.
There is no credential resolver, Settings/.env import, adapter, reserve_operation
or dispatch entrypoint. It cannot execute even if a caller passes an authority hash.

The externally pinned binding bytes are strict/frozen/extra-forbid. Exact RC commit,
tag, clean checkout, canonical tree and loaded module blob/import origin qualify
before database access. The old RC18 does not contain this module and is correctly
rejected. An untagged candidate is not represented as an executable RC.

Database identity derives from RC tag plus full canonical acceptance lineage:
vf_ + normalized RC tag + first 32 hex characters of SHA256(RC tag + LF + lineage).
Canonical lineage already binds RC commit/provider/model/capability/sequence.
Operation key binds lineage and slot. Role/system ID/database OID/private socket
are independently pinned; no fallback endpoint or namespace is allowed.
There is no RC18-specific database name in reusable source.

SELECT-only custody checks run in REPEATABLE READ, READ ONLY transactions. They deny
exact operation/attempt reuse, cross-lineage/null historical state, active
reservations, nonfinite/nonzero reserved totals and nonvirgin namespaces when
requested. A virgin lookup does not create an operation row. The database scopes
budget-day and provider/capability circuit keys as well as lineage-bearing op/attempt
keys. Successful request receipts remain external operation evidence; no receipt
absence outside the explicitly selected database is claimed.

## Boundaries and residual requirements

Hash fields in custody configuration pin references; this phase does not load,
approve or mount a gate, validate live provider availability, or replace fresh
main/dual-CI/rights/window/budget/evidence checks at future dispatch.
Kill-switch True / external False / paid False are required custody configuration;
checked-in runtime defaults remain engaged/disabled. No live transition is made.

The B2 database name is historical RC18-era testing, not a future execution
database. After Owner-approved merge and exact-main regression, a fresh RC and
new lineage/database/custody binding/scope/bundle/window/authority are required.
RC18 authority remains historically GRANTED_NOT_CONSUMED but INVALID_FOR_NEW_CANDIDATE.
No identity, authority, confirmation token, reservation or window is transferred.

## Migration and rollback

No new migration and no history rewrite. Existing 0001..0014 replayed on isolated
PostgreSQL 16 test databases. Existing migration control seed and idempotent
ensure_state create no execution/budget rows. Test metadata writes are reported
separately. Removing/reverting the addition is a future reviewed source action;
old RC17/18 tags and all prior operation receipts remain immutable.

## Quality and operational invariants

No ASR/provider/model/quality change. WER <=15%, critical terms 8/8, W1/profile/
prompt/assets/reference/RightsRecords and PositiveDurationTranscript are unchanged.
ASR 0/2 PASS; Vision 2/2 PASS; Operation 2 locked; Production NO-GO.
ZERO provider credential reads, live reservations, provider calls or production business writes.
