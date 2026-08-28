# Backup, restore and rollback audit

## Current result

`LOCAL DISPOSABLE DR PASS / PRODUCTION-LIKE DR BLOCKED`

V3-01-07 executed an actual backup, destructive failure, restore, restart and recovery drill inside
the isolated Compose project `npd-video-factory-v3-dr-e2e`. PostgreSQL and MinIO were restored,
Redis work was reconstructed from canonical PostgreSQL state, one pending analytics job resumed,
and all 9 required recovery target hashes matched. Measured local RPO was 0 seconds and RTO was 33
seconds. Evidence is `EV-V3-DR-OBS-001` on code commit
`527fd1f482e4afa80105cb6ebab92545c10a79fc`.

This did not touch production, deploy an image, restore a shared volume or establish production-like
DR. There is still no accepted immutable RC image or owner-approved production RPO/RTO.

## Data ownership boundary

| Component | Canonical scope | Required backup evidence |
|---|---|---|
| PostgreSQL | V2 workspaces, projects, jobs, audit and artifact metadata | consistent dump, migration head and checksum |
| S3/MinIO | source/generated/final binary objects | version/inventory and checksum coverage |
| Redis | transient queue/replay state | recovery semantics; never treated as sole canonical backup |
| Deployment/config | Compose override, image digests and redacted fingerprint | immutable receipt without secrets |

Backups must be Video Factory-scoped. They must not create or overwrite Agent Hub, SaleHub, n8n,
Caddy or another product's database/Redis namespace.

## Completed local disposable drill

The local drill completed this sequence:

1. captured migration and recovery fingerprints;
2. created PostgreSQL, MinIO and retained Redis-AOF backups with integrity checks;
3. stopped services and destructively cleared only the disposable target;
4. restored PostgreSQL and MinIO, then rebuilt Redis queues from PostgreSQL;
5. restarted services and resumed one deliberately pending analytics job;
6. verified 9/9 state and artifact hashes, readiness and zero duplicate external action;
7. recorded zero provider calls, zero notifications, zero production writes and 0 VND cost.

## Remaining production-like drill

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

`OPS-06`, `OPS-07` and `OPS-08` pass only the implemented/local deterministic axis. Their
production-path axis remains `NOT_TESTED`. Owner-approved production RPO/RTO are still `TBD`, so
G-04/G-09/G-10 remain mandatory before production-like DR can pass.

Open gaps: `V3-01-GAP-007`, `V3-01-GAP-008`.
