# Backup, restore and rollback audit

## Current result

`BLOCKED / NO DR DRILL EXECUTED`

V2-11 contains guarded deployment, backup, restore, smoke and soak helpers plus runbooks. CI checks
their syntax and deterministic contracts. There is no Video Factory production deployment, image
digest, canonical production database/object store or production backup to restore. This audit did
not create, overwrite or restore any runtime state.

## Data ownership boundary

| Component | Canonical scope | Required backup evidence |
|---|---|---|
| PostgreSQL | V2 workspaces, projects, jobs, audit and artifact metadata | consistent dump, migration head and checksum |
| S3/MinIO | source/generated/final binary objects | version/inventory and checksum coverage |
| Redis | transient queue/replay state | recovery semantics; never treated as sole canonical backup |
| Deployment/config | Compose override, image digests and redacted fingerprint | immutable receipt without secrets |

Backups must be Video Factory-scoped. They must not create or overwrite Agent Hub, SaleHub, n8n,
Caddy or another product's database/Redis namespace.

## Required isolated drill

After G-04 approves the isolated target and before G-10 can accept the result:

1. capture application/config/image/migration fingerprints;
2. create PostgreSQL and object-store backups and their hashes;
3. restore into new isolated names/volumes;
4. start the locked RC against the restored copy;
5. verify project/job/artifact counts, sampled hashes and signed access;
6. replay one incomplete deterministic job and prove recovery;
7. roll application image back to the named previous digest;
8. rerun readiness/API/Studio/render smoke;
9. record RPO, RTO, operator, timestamps and evidence hashes.

No drill may restore over the source system. Redis restoration is never automatic. The source
backup and evidence remain retained after cleanup of the isolated target.

## Acceptance thresholds

Owner-approved RPO/RTO are currently `TBD`; therefore `OPS-06`, `OPS-07` and `OPS-08` cannot pass.
A script existing or returning zero is insufficient without data-integrity, recovery and rollback
evidence bound to one RC.

Open gaps: `V3-01-GAP-007`, `V3-01-GAP-008`.
