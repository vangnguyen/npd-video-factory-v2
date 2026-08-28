#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${VIDEO_FACTORY_BACKUP_ROOT:-/var/backups/npd-video-factory-v2}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_ROOT/$STAMP"
PROJECT="${VIDEO_FACTORY_COMPOSE_PROJECT:-npd-video-factory-v2}"
DOCKER_CLI="${DOCKER_BIN:-docker}"

docker_host_path() {
  if [[ "$DOCKER_CLI" == *.exe ]] && command -v wslpath >/dev/null 2>&1; then
    wslpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}
COMPOSE_FILE="$(docker_host_path "$ROOT_DIR/docker-compose.yml")"

mkdir -p "$TARGET"
chmod 0700 "$TARGET"
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  --format=custom --no-owner --no-acl >"$TARGET/postgres.dump"
"$DOCKER_CLI" run --rm -v "${PROJECT}_minio-data:/source:ro" -v "$(docker_host_path "$TARGET"):/backup" alpine:3.20 \
  tar -C /source -czf /backup/minio-data.tar.gz .
"$DOCKER_CLI" run --rm -v "${PROJECT}_redis-data:/source:ro" -v "$(docker_host_path "$TARGET"):/backup" alpine:3.20 \
  tar -C /source -czf /backup/redis-aof.tar.gz .
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  -Atc 'SELECT version_num FROM alembic_version' >"$TARGET/migration-head.txt"
printf '%s\n' 'redis-recovery=rebuild-from-postgresql; aof-retained-not-auto-restored' \
  >"$TARGET/redis-recovery-policy.txt"
git -C "$ROOT_DIR" rev-parse HEAD >"$TARGET/git-sha.txt"
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" images --format json >"$TARGET/images.json"
if [[ "$DOCKER_CLI" == *.exe ]]; then
  printf '%s\n' 'permissions=host-acl-inherited; scope=disposable-windows-ci; secrets=none' \
    >"$TARGET/filesystem-permissions.txt"
else
  printf '%s\n' 'permissions=posix-0700; scope=linux-runtime' \
    >"$TARGET/filesystem-permissions.txt"
fi
sha256sum "$TARGET"/* >"$TARGET/SHA256SUMS"
if [[ "$DOCKER_CLI" != *.exe ]]; then
  chmod -R go-rwx "$TARGET"
fi
echo "$TARGET"
