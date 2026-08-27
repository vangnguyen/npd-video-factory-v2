#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${VIDEO_FACTORY_SMOKE_BASE_URL:-http://127.0.0.1:8000}"
ready="$(curl --fail --silent --show-error "$BASE_URL/readyz")"
openapi="$(curl --fail --silent --show-error "$BASE_URL/openapi.json")"
capabilities="$(curl --fail --silent --show-error "$BASE_URL/api/v1/capabilities")"
python - "$ready" "$openapi" "$capabilities" <<'PY'
import json, sys
ready, openapi, capabilities = map(json.loads, sys.argv[1:])
assert ready == {"status": "ready"}
assert openapi["info"]["version"] == "0.12.0"
assert capabilities["agent_hub_bridge_implemented"] is True
assert capabilities["shared_agent_hub_database"] is False
assert capabilities["shared_agent_hub_redis"] is False
assert capabilities["publish_enabled"] is False
assert capabilities["publish_external_execution_enabled"] is False
assert capabilities["human_approval_required"] is True
print("smoke=pass")
PY
