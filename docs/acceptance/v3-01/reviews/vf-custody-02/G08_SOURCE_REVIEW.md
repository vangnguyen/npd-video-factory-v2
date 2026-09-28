# G-08 — VF-CUSTODY-02 source-side review

**PASS SOURCE-SIDE / READY FOR OWNER O1 AFTER EXACT-HEAD CI / NOT EXECUTION AUTHORITY.**

The change is fail-closed and does not weaken existing gates.  The new
`CustodyBinding` accepts only the approved database, migration, filesystem,
package, service-identity, role, table, backup, and restore identities.  Pydantic
extra-field rejection prevents operation ID, O2, execution-window, bundle,
authority, and provider-credential fields from being smuggled into custody.
`AUTHORITY_GRANTED` is structurally fixed to false.

Socket verification rejects wrong service UID/GID, runner ownership,
world-writable mode, non-socket endpoints, and symlink/path substitution.  The
database read verifies PostgreSQL 16.15, system identifier, database OID/name,
role, schema, and migration head before accepting custody.  Qualification
requires SELECT and rejects INSERT/UPDATE/DELETE/TRUNCATE on all six custody
tables and `alembic_version`; it also rejects schema/database CREATE and TEMP.
Four real write/DDL probes fail inside a `REPEATABLE READ, READ ONLY`
transaction, with a SELECT health check after each failure.

Negative unit coverage includes authority-field injection, wrong canonical
database/version/head, runner-owned socket, world-writable socket, path
substitution, and wrong PostgreSQL instance.  Live evidence additionally proves
the dedicated `postgres` process/socket identity and the exact SELECT-only
matrix.  Full Python regression is 1338 passed / 4 declared skips.  Source
secret scan, host/data/backup secret scan, diff check, migration validation,
logical backup, WAL-inclusive physical backup, isolated restore, and restart
all pass.

This changes executable/runtime source, so O1 is required before merge.  No
merge, O1 approval, O2 request, runner activation, executor `/opt` install,
execution allowlist population, provider credential binding/read, provider call,
budget reservation, operation consumption, or RC-22 reconstruction is performed
by this review.

