# VF-CUSTODY-02 — controlled custody bootstrap

Status: **SOURCE AND CUSTODY TECHNICALLY QUALIFIED; O1 REQUIRED; NO O2**.

The approved Ubuntu-24.04 WSL2 host now runs PostgreSQL 16.15 from the PGDG
Noble repository as the dedicated `postgres` service identity.  The canonical
database is `vf_provider_custody_v3_01`, schema `public`, migration head
`0015_v3_01_dispatch`, system identifier `7690544205041130268`, and database
OID `16386`.  `listen_addresses` is empty; port 55432 exists only as the Unix
socket `/run/npd-video-factory/provider-custody/postgresql/.s.PGSQL.55432`.

The runtime role `vf_executor_runtime` remains `NOLOGIN` and has only the DML
needed by `ProviderSafetyRepository`.  A synthetic operation exercised those
grants in a transaction that was rolled back.  The qualification role
`vf_custody_qualifier` has CONNECT, schema USAGE, and SELECT only.  Live
qualification used `REPEATABLE READ, READ ONLY`; INSERT, UPDATE, DELETE, and
DDL probes were rejected.  The final baseline contains the one canonical
control row and zero operations, attempts, budgets, circuits, alerts, active
reservations, or reconstructed RC-22 records.

Logical and physical backups were produced.  The physical backup uses streamed
WAL and a SHA-256 `backup_manifest`, passes `pg_verifybackup`, and starts twice
in an isolated restore instance.  The restored system identifier/database OID,
migration head, six-table baseline, and role policy match the source instance.
An encrypted copy is stored outside the WSL virtual disk on the Windows host.
The binding hash is
`c8d2761e3a5f6f835d6562665aac3eb175b5387bacc9e9e2daa5433c36b00e27`.

Candidate source commit `9853ac271973f70e72e8bf2d6865ca359a3bad60` separates
custody binding from operation/authority material, binds socket ownership to the
dedicated PostgreSQL UID/GID, and enforces genuine SELECT-only qualification.
Its executor executable-tree SHA-256 is
`c39b1baef8fa610accc883dd6409a6e2c844098c422258c955c4128c3d0cb23e`.
Focused tests passed (86, with three Windows-only POSIX skips); the exact full
Python regression passed (1338, with four declared skips).  Docker is not
installed locally, so the required GitHub-hosted exact-head CI is the candidate
Docker E2E authority and is recorded in the handoff after the final push.

No provider credential was read.  No provider call, budget reservation,
operation consumption, actual provider cost, RC-22 mutation, authority binding,
or O2 approval occurred.  The GitHub runner remains offline with listener
stopped, runner service not installed, kill switch engaged, and allowlist empty.

