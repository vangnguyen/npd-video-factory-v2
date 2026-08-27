#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${VIDEO_FACTORY_SMOKE_BASE_URL:-http://127.0.0.1:8000}"
DURATION_SECONDS="${VIDEO_FACTORY_SOAK_SECONDS:-86400}"
INTERVAL_SECONDS="${VIDEO_FACTORY_SOAK_INTERVAL_SECONDS:-60}"
REPORT="${VIDEO_FACTORY_SOAK_REPORT:-./e2e-artifacts/v2-11-soak.jsonl}"
mkdir -p "$(dirname "$REPORT")"
started="$(date -u +%s)"
deadline="$((started + DURATION_SECONDS))"
failures=0
while [[ "$(date -u +%s)" -lt "$deadline" ]]; do
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if body="$(curl --silent --show-error --fail --max-time 10 "$BASE_URL/readyz")"; then
    printf '{"at":"%s","ready":true,"body":%s}\n' "$now" "$body" >>"$REPORT"
  else
    failures="$((failures + 1))"
    printf '{"at":"%s","ready":false}\n' "$now" >>"$REPORT"
  fi
  sleep "$INTERVAL_SECONDS"
done
printf '{"summary":true,"duration_seconds":%s,"failures":%s}\n' "$DURATION_SECONDS" "$failures" >>"$REPORT"
test "$failures" -eq 0
echo "$REPORT"
