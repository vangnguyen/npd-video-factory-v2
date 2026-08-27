#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_COMPOSE="$ROOT_DIR/docker-compose.yml"
PROD_COMPOSE="$ROOT_DIR/deploy/production/docker-compose.production.yml"
: "${VIDEO_FACTORY_AGENT_HUB_KEYS_FILE:?set VIDEO_FACTORY_AGENT_HUB_KEYS_FILE}"

test -f "$VIDEO_FACTORY_AGENT_HUB_KEYS_FILE"
test ! -L "$VIDEO_FACTORY_AGENT_HUB_KEYS_FILE"
python - "$VIDEO_FACTORY_AGENT_HUB_KEYS_FILE" <<'PY'
import json, os, stat, sys
path = sys.argv[1]
mode = stat.S_IMODE(os.stat(path).st_mode)
if mode & 0o077:
    raise SystemExit("Agent Hub key file must not be group/world readable")
payload = json.load(open(path, encoding="utf-8"))
if payload.get("version") != 1 or not payload.get("service_identities") or not payload.get("webhook_signing"):
    raise SystemExit("Agent Hub key file contract is incomplete")
print("service-key-contract=valid")
PY

docker compose -f "$BASE_COMPOSE" -f "$PROD_COMPOSE" config --quiet
rendered_services="$(docker compose -f "$BASE_COMPOSE" -f "$PROD_COMPOSE" config --services)"
for forbidden in agent-hub agent_hub caddy n8n; do
  if grep -Fxq "$forbidden" <<<"$rendered_services"; then
    echo "Forbidden shared service in Video Factory stack: $forbidden" >&2
    exit 1
  fi
done

grep -qx 'PUBLISH_ENABLED=false' "$ROOT_DIR/.env"
grep -qx 'PUBLISH_EXTERNAL_EXECUTION_ENABLED=false' "$ROOT_DIR/.env"
grep -qx 'PUBLISH_OWNER_GATE_ENABLED=false' "$ROOT_DIR/.env"
grep -qx 'HUMAN_APPROVAL_REQUIRED=true' "$ROOT_DIR/.env"
echo "preflight=pass"
