#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT_DIR/docker-compose.yml"
PROD="$ROOT_DIR/deploy/production/docker-compose.production.yml"

"$ROOT_DIR/scripts/v2-11-preflight.sh"
BACKUP_DIR="$("$ROOT_DIR/scripts/v2-11-backup.sh")"
echo "backup=$BACKUP_DIR"
docker compose -f "$BASE" -f "$PROD" build api worker renderer studio-web
docker compose -f "$BASE" -f "$PROD" run --rm migrate
docker compose -f "$BASE" -f "$PROD" up -d --no-deps api worker renderer studio-web
"$ROOT_DIR/scripts/v2-11-smoke.sh"
echo "deploy=pass"
