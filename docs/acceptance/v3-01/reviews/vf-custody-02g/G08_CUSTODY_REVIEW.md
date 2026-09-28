# G-08 — VF-CUSTODY-02G custody-only source review

**PASS SOURCE-SIDE / READY FOR OWNER O1 AFTER FINAL EXACT-HEAD CI / NOT EXECUTION AUTHORITY.**

The change is fail-closed. `CustodyBinding` permits only infrastructure custody
identity and fixes `authority_granted` and runtime login to false. It rejects
operation ID, O2 approval, execution window, bundle authorization, and provider
credential material. Socket verification binds the canonical path, dedicated
PostgreSQL UID/GID, group, directory mode, socket type, and socket mode; it
rejects runner ownership, world-writable endpoints, path substitution, and the
wrong PostgreSQL instance.

Qualification verifies PostgreSQL 16.15, system identifier, database name/OID,
role, schema, migration head, six-table set, and clean baseline before accepting
custody. The qualification role must have SELECT but no INSERT, UPDATE, DELETE,
or TRUNCATE on every custody table and `alembic_version`, schema USAGE but no
CREATE, and database CONNECT but no CREATE or TEMP. Real INSERT, UPDATE, DELETE,
and DDL probes must fail while the transaction remains `REPEATABLE READ, READ
ONLY`.

Focused tests, full regression, migration replay, acceptance validation, secret
scan, scope review, and GitHub-hosted exact-head/Docker E2E all pass on source
commit `46027ef75d070030fcd8f545ee3b3c43a11fadc6`. The executable-tree SHA-256 is
`451b1656ff9ce7b8df613c8a798ec3883e05185d8e3f97becd8595117a98d396`.

The MinIO change is explicitly disclosed as the minimum Docker E2E dependency;
run `36422599029` proves the main-compatible Quay digest is inaccessible, while
run `36424025792` proves the immutable public GHCR digest works without a
registry login. This does not introduce executor/provider authority.

O1 is required before merge because executable/runtime source changes. This
review does not merge, request O2, activate a runner, install `/opt` runtime,
populate an execution allowlist, bind/read a provider credential, call a
provider, reserve budget, consume an operation, or mutate/reconstruct RC-22.
