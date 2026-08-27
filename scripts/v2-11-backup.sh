#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${VIDEO_FACTORY_BACKUP_ROOT:-/var/backups/npd-video-factory-v2}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_ROOT/$STAMP"
PROJECT="npd-video-factory-v2"

mkdir -p "$TARGET"
chmod 0700 "$TARGET"
docker compose -p "$PROJECT" -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
  pg_dump -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  --format=custom --no-owner --no-acl >"$TARGET/postgres.dump"
docker run --rm -v "${PROJECT}_minio-data:/source:ro" -v "$TARGET:/backup" alpine:3.20 \
  tar -C /source -czf /backup/minio-data.tar.gz .
docker run --rm -v "${PROJECT}_redis-data:/source:ro" -v "$TARGET:/backup" alpine:3.20 \
  tar -C /source -czf /backup/redis-aof.tar.gz .
git -C "$ROOT_DIR" rev-parse HEAD >"$TARGET/git-sha.txt"
docker compose -p "$PROJECT" -f "$ROOT_DIR/docker-compose.yml" images --format json >"$TARGET/images.json"
sha256sum "$TARGET"/* >"$TARGET/SHA256SUMS"
chmod -R go-rwx "$TARGET"
echo "$TARGET"
