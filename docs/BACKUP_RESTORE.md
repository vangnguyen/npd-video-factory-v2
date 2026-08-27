# Backup and Restore Runbook

## Scope

The V2-11 backup contains only Video Factory V2 state:

- PostgreSQL custom-format dump;
- V2 MinIO volume archive;
- V2 Redis AOF archive for queue investigation/recovery;
- Git SHA, image inventory and SHA-256 manifest.

It excludes `.env`, service-auth keys, OAuth/provider credentials, Agent Hub data, n8n, Caddy and
every unrelated Docker volume. PostgreSQL and object storage are canonical; Redis is a recoverable
delivery cache and must not overwrite another system's Redis.

## Backup

From the checked-out release with the production `.env` already provisioned:

```bash
export VIDEO_FACTORY_BACKUP_ROOT=/var/backups/npd-video-factory-v2
./scripts/v2-11-backup.sh
```

The script creates a timestamped mode-0700 directory and prints only its path. Retain the
`SHA256SUMS` file with the archive. Store an encrypted off-host copy according to the owner's
retention policy. Keep the external service-key backup in the approved secret system, never in
this archive.

## Restore rehearsal

Use an isolated host/project first. Verify checksums and confirm the target path resolves under
`/var/backups/npd-video-factory-v2`. Stop only V2 application services. Then run:

```bash
./scripts/v2-11-restore.sh --confirm /var/backups/npd-video-factory-v2/<timestamp>
```

The explicit flag and bounded path are mandatory. The script refuses to proceed while V2 API,
worker, renderer or Studio is running. It restores only the V2 database and V2 MinIO volume.

After restore:

1. run migrations from the restored release;
2. start V2 services through the guarded deployment script;
3. run `v2-11-smoke.sh`;
4. verify recent project/assets/audit and webhook receipt hashes;
5. verify `PUBLISH_*` remain false and human approval remains required;
6. retain the restore evidence and do not delete the source backup automatically.

Redis delivery state should normally be reconstructed from PostgreSQL recovery. Restoring its AOF
is an incident-specific decision, never an automatic deployment step.
