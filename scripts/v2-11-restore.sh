#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm" || -z "${2:-}" ]]; then
  echo "Usage: $0 --confirm /absolute/path/to/backup" >&2
  exit 2
fi
BACKUP_DIR="$(realpath "$2")"
case "$BACKUP_DIR" in
  /var/backups/npd-video-factory-v2/*) ;;
  *) echo "Backup must be inside /var/backups/npd-video-factory-v2" >&2; exit 2 ;;
esac
test -f "$BACKUP_DIR/postgres.dump"
test -f "$BACKUP_DIR/minio-data.tar.gz"
(cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="npd-video-factory-v2"
running="$(docker compose -p "$PROJECT" -f "$ROOT_DIR/docker-compose.yml" ps --status running --services)"
if grep -Eq '^(api|worker|renderer|studio-web)$' <<<"$running"; then
  echo "Stop application services before restore; database/object services may remain running." >&2
  exit 1
fi
docker compose -p "$PROJECT" -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
  pg_restore -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  --clean --if-exists --no-owner --no-acl <"$BACKUP_DIR/postgres.dump"
docker run --rm -v "${PROJECT}_minio-data:/target" -v "$BACKUP_DIR:/backup:ro" alpine:3.20 \
  sh -c 'find /target -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -C /target -xzf /backup/minio-data.tar.gz'
echo "restore=complete; run guarded deploy and smoke before reopening traffic"
