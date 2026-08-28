#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm" || -z "${2:-}" ]]; then
  echo "Usage: $0 --confirm /absolute/path/to/backup" >&2
  exit 2
fi
BACKUP_ROOT="$(realpath "${VIDEO_FACTORY_BACKUP_ROOT:-/var/backups/npd-video-factory-v2}")"
BACKUP_DIR="$(realpath "$2")"
case "$BACKUP_DIR" in
  "$BACKUP_ROOT"/*) ;;
  *) echo "Backup must be inside /var/backups/npd-video-factory-v2" >&2; exit 2 ;;
esac
test -f "$BACKUP_DIR/postgres.dump"
test -f "$BACKUP_DIR/minio-data.tar.gz"
test -f "$BACKUP_DIR/redis-aof.tar.gz"
(cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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
running="$("$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" ps --status running --services)"
if grep -Eq '^(api|worker|renderer|studio-web)$' <<<"$running"; then
  echo "Stop application services before restore; database/object services may remain running." >&2
  exit 1
fi
"$DOCKER_CLI" compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
  pg_restore -U "${VIDEO_POSTGRES_USER:-video_factory}" -d "${VIDEO_POSTGRES_DB:-video_factory}" \
  --clean --if-exists --no-owner --no-acl <"$BACKUP_DIR/postgres.dump"
"$DOCKER_CLI" run --rm -v "${PROJECT}_minio-data:/target" -v "$(docker_host_path "$BACKUP_DIR"):/backup:ro" alpine:3.20 \
  sh -c 'find /target -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -C /target -xzf /backup/minio-data.tar.gz'
echo "restore=complete; run guarded deploy and smoke before reopening traffic"
