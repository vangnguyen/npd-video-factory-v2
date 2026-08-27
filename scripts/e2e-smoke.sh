#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ -n "${DOCKER_BIN:-}" ]]; then
  docker_bin="$DOCKER_BIN"
elif grep -qi microsoft /proc/version 2>/dev/null && command -v docker.exe >/dev/null 2>&1; then
  docker_bin="docker.exe"
elif command -v docker >/dev/null 2>&1; then
  docker_bin="docker"
elif command -v docker.exe >/dev/null 2>&1; then
  docker_bin="docker.exe"
else
  echo "Docker CLI was not found" >&2
  exit 1
fi
env_backup=""
had_env=0
if [[ -f .env ]]; then
  env_backup="$(mktemp)"
  cp .env "$env_backup"
  had_env=1
fi

cleanup() {
  "$docker_bin" compose logs --no-color > e2e-artifacts/compose.log 2>&1 || true
  "$docker_bin" compose down -v >/dev/null 2>&1 || true
  if [[ "$had_env" == "1" ]]; then
    cp "$env_backup" .env
  else
    rm -f .env
  fi
  [[ -z "$env_backup" ]] || rm -f "$env_backup"
  rm -f storage/e2e-agent-hub-keys.json
}
trap cleanup EXIT

mkdir -p e2e-artifacts storage/assets/vinhomes-green-paradise storage/jobs
cp .env.example .env

# Ephemeral deterministic HMAC material exists only for this disposable E2E stack.
# It is mounted read-only, removed on exit and never copied into acceptance artifacts.
"$PYTHON_BIN" - <<'PY'
import base64
import json
from pathlib import Path

key_v1 = b"v2-11-e2e-inbound-key-at-least-32-bytes"
key_v2 = b"v2-11-e2e-outbound-key-at-least-32-bytes"
Path("storage/e2e-agent-hub-keys.json").write_text(
    json.dumps(
        {
            "version": 1,
            "service_identities": {
                "agent-hub-e2e": {
                    "roles": ["service"],
                    "keys": {"inbound-v1": base64.b64encode(key_v1).decode("ascii")},
                }
            },
            "webhook_signing": {
                "active_key_id": "outbound-v2",
                "keys": {"outbound-v2": base64.b64encode(key_v2).decode("ascii")},
            },
        },
        sort_keys=True,
    ),
    encoding="utf-8",
)
PY
chmod 0600 storage/e2e-agent-hub-keys.json
printf '%s\n' \
  'VIDEO_FACTORY_AGENT_HUB_KEYS_FILE=./storage/e2e-agent-hub-keys.json' \
  'AGENT_HUB_BRIDGE_ENABLED=true' \
  'AGENT_HUB_WEBHOOK_MODE=fixture' >>.env

# Copyright-safe, visibly distinct PNG fixtures. A previous 1x1 fixture encoded
# an opaque black pixel, which let a black video pass metadata-only QC.
"$PYTHON_BIN" scripts/generate-e2e-fixtures.py

echo "[e2e] building and starting stack"
"$docker_bin" compose up -d --build

echo "[e2e] waiting for API readiness"
ready=0
for _ in $(seq 1 90); do
  if curl --fail --silent http://localhost:8000/readyz >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" != "1" ]]; then
  echo "API did not become ready" >&2
  exit 1
fi

if ! curl --fail --silent http://localhost:3001/healthz >/dev/null; then
  echo "Renderer health check failed" >&2
  exit 1
fi

if ! curl --fail --silent http://localhost:3000/ >/dev/null; then
  echo "Studio health check failed" >&2
  exit 1
fi
if ! curl --fail --silent http://localhost:3000/studio.html | grep -q 'Auto Edit Studio'; then
  echo "Auto Edit Studio route/content check failed" >&2
  exit 1
fi
if ! curl --fail --silent --show-error --head http://localhost:3000/studio-utils.mjs | tr -d '\r' | grep -qi '^content-type: application/javascript'; then
  echo "Auto Edit Studio ES module MIME check failed" >&2
  exit 1
fi

echo "[e2e] exercising V2-11 signed Agent Hub bridge"
unsigned_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  http://localhost:8000/api/v1/bridge/contract)"
if [[ "$unsigned_status" != "400" && "$unsigned_status" != "401" ]]; then
  echo "Unsigned bridge request did not fail closed: HTTP $unsigned_status" >&2
  exit 1
fi
"$PYTHON_BIN" - <<'PY'
import hashlib
import hmac
import json
import time
import urllib.request
from pathlib import Path

base = "http://localhost:8000"
service_id = "agent-hub-e2e"
key_id = "inbound-v1"
key = b"v2-11-e2e-inbound-key-at-least-32-bytes"

def call(method, path, payload=None, nonce="nonce"):
    body = b"" if payload is None else json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    timestamp = int(time.time())
    content_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join((method, path, "", str(timestamp), nonce, content_hash))
    signature = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "X-NPD-Service-Id": service_id,
        "X-NPD-Key-Id": key_id,
        "X-NPD-Timestamp": str(timestamp),
        "X-NPD-Nonce": nonce,
        "X-NPD-Content-SHA256": content_hash,
        "X-NPD-Signature": signature,
        "X-NPD-Contract-Version": "agent-hub-bridge.v1",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=body if payload is not None else None, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)

project_request = {
    "workspace_id": None,
    "slug": "v2-11-agent-hub-e2e",
    "name": "V2-11 Agent Hub E2E",
    "niche": "real_estate",
    "source_campaign_id": "CMP-V2-11-E2E",
    "brief": {"objective": "contract_acceptance", "fixture": True},
    "execution_mode": "draft_only",
    "start_pipeline": False,
    "publish_requested": False,
    "external_action_requested": False,
}
body = json.dumps(project_request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
timestamp = int(time.time())
content_hash = hashlib.sha256(body).hexdigest()
path = "/api/v1/bridge/project-requests"
canonical = "\n".join(("POST", path, "", str(timestamp), "project-create-0001", content_hash))
headers = {
    "X-NPD-Service-Id": service_id,
    "X-NPD-Key-Id": key_id,
    "X-NPD-Timestamp": str(timestamp),
    "X-NPD-Nonce": "project-create-0001",
    "X-NPD-Content-SHA256": content_hash,
    "X-NPD-Signature": hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest(),
    "X-NPD-Contract-Version": "agent-hub-bridge.v1",
    "Idempotency-Key": "v2-11-docker-e2e-project-0001",
    "Content-Type": "application/json",
}
request = urllib.request.Request(base + path, data=body, headers=headers, method="POST")
with urllib.request.urlopen(request, timeout=10) as response:
    created = json.load(response)
Path("e2e-artifacts/bridge-project-created.json").write_text(json.dumps(created, indent=2, ensure_ascii=False), encoding="utf-8")
assert created["project"]["status"] == "draft", created
assert created["bridge_request"]["execution_started"] is False, created
assert created["bridge_request"]["external_action"] is False, created

deliveries = []
for attempt in range(30):
    deliveries = call("GET", "/api/v1/bridge/webhook-deliveries", nonce=f"delivery-poll-{attempt:04d}")
    if deliveries and deliveries[0]["status"] == "succeeded":
        break
    time.sleep(1)
assert deliveries and deliveries[0]["status"] == "succeeded", deliveries
assert deliveries[0]["provider_mode"] == "fixture" and deliveries[0]["external_call"] is False, deliveries
assert deliveries[0]["key_id"] == "outbound-v2", deliveries
assert isinstance(deliveries[0]["signed_at_unix"], int), deliveries
assert deliveries[0]["receipt"]["signed_at_unix"] == deliveries[0]["signed_at_unix"], deliveries
Path("e2e-artifacts/bridge-deliveries-before-restart.json").write_text(json.dumps(deliveries, indent=2), encoding="utf-8")
events = call("GET", "/api/v1/bridge/events", nonce="event-history-0001")
assert events[0]["event_type"] == "video.project.created" and events[0]["contains_secret"] is False, events
Path("e2e-artifacts/bridge-events-before-restart.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
print("[e2e] V2-11 service auth, draft boundary and signed webhook verified")
PY

expected_duration="$("$PYTHON_BIN" -c 'import json; print(json.load(open("examples/vinhomes-green-paradise.request.json", encoding="utf-8"))["video"]["duration_seconds"])')"
echo "[e2e] creating ${expected_duration}-second video job"
create_response="$(
  curl --fail --silent --show-error \
    -X POST http://localhost:8000/api/v1/video-jobs \
    -H 'Content-Type: application/json' \
    -H 'Idempotency-Key: github-actions-sprint-1-e2e' \
    --data-binary @examples/vinhomes-green-paradise.request.json
)"
printf '%s\n' "$create_response" > e2e-artifacts/create-response.json
job_id="$(printf '%s' "$create_response" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["job_id"])' | tr -d '\r')"
echo "[e2e] job_id=$job_id"

printf '%s' "$create_response" | "$PYTHON_BIN" -c '
import json, sys
d = json.load(sys.stdin)
assert d["workspace_id"].startswith("wsp_"), d
assert d["project_id"].startswith("prj_"), d
assert d["project_version_id"].startswith("pver_"), d
'

terminal=0
for attempt in $(seq 1 120); do
  status_json="$(curl --fail --silent --show-error "http://localhost:8000/api/v1/video-jobs/$job_id")"
  printf '%s\n' "$status_json" > e2e-artifacts/job-status.json
  read -r job_status job_stage progress < <(
    printf '%s' "$status_json" | "$PYTHON_BIN" -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], d["stage"], d["progress"])' | tr -d '\r'
  )
  echo "[e2e] poll=$attempt status=$job_status stage=$job_stage progress=$progress"
  if [[ "$job_status" == "awaiting_review" ]]; then
    terminal=1
    break
  fi
  if [[ "$job_status" == "failed" ]]; then
    echo "Video job failed" >&2
    printf '%s\n' "$status_json" >&2
    exit 1
  fi
  sleep 5
done

if [[ "$terminal" != "1" ]]; then
  echo "Video job did not reach awaiting_review before timeout" >&2
  exit 1
fi

job_dir="storage/jobs/$job_id"
for required in script.json storyboard.json narration.wav narration-timing.json subtitles.srt video-manifest.json final.mp4 qc.json; do
  if [[ ! -f "$job_dir/$required" ]]; then
    echo "Missing required artifact: $required" >&2
    exit 1
  fi
done

cp "$job_dir/final.mp4" e2e-artifacts/final.mp4
cp "$job_dir/qc.json" e2e-artifacts/qc.json
cp "$job_dir/video-manifest.json" e2e-artifacts/video-manifest.json
cp "$job_dir/narration.wav" e2e-artifacts/narration.wav
cp "$job_dir/narration-timing.json" e2e-artifacts/narration-timing.json
cp "$job_dir/subtitles.srt" e2e-artifacts/subtitles.srt

workspace_id="$(printf '%s' "$status_json" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["workspace_id"])' | tr -d '\r')"
project_id="$(printf '%s' "$status_json" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["project_id"])' | tr -d '\r')"
project_version_id="$(printf '%s' "$status_json" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["project_version_id"])' | tr -d '\r')"

curl --fail --silent --show-error "http://localhost:8000/api/v1/workspaces/$workspace_id" > e2e-artifacts/workspace.json
curl --fail --silent --show-error "http://localhost:8000/api/v1/projects/$project_id" > e2e-artifacts/project.json
curl --fail --silent --show-error "http://localhost:8000/api/v1/projects/$project_id/versions" > e2e-artifacts/project-versions.json
curl --fail --silent --show-error "http://localhost:8000/api/v1/projects/$project_id/assets" > e2e-artifacts/project-assets.json
curl --fail --silent --show-error "http://localhost:8000/api/v1/providers" > e2e-artifacts/providers.json
curl --fail --silent --show-error "http://localhost:8000/api/v1/projects/$project_id/costs" > e2e-artifacts/cost-records.json
curl --fail --silent --show-error "http://localhost:8000/api/v1/projects/$project_id/cost-summary" > e2e-artifacts/cost-summary.json
curl --fail --silent --show-error "http://localhost:8000/api/v1/video-jobs/$job_id/events" > e2e-artifacts/job-events.json

echo "[e2e] uploading rendered fixture through resumable V2-04 upload contract"
upload_source="e2e-artifacts/final.mp4"
upload_size="$(wc -c < "$upload_source" | tr -d ' ')"
upload_checksum="$("$PYTHON_BIN" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$upload_source" | tr -d '\r')"
upload_init_payload="$(
  "$PYTHON_BIN" -c '
import json, sys
print(json.dumps({
    "project_id": sys.argv[1],
    "project_version_id": sys.argv[2],
    "filename": "uploaded-footage.mp4",
    "media_kind": "video",
    "content_type": "video/mp4",
    "size_bytes": int(sys.argv[3]),
    "checksum_sha256": sys.argv[4],
    "part_size_bytes": 8388608,
    "rights_status": "owned",
    "license": "ci-synthetic-fixture"
}))
' "$project_id" "$project_version_id" "$upload_size" "$upload_checksum"
)"
printf '%s' "$upload_init_payload" | curl --fail --silent --show-error \
  -X POST http://localhost:8000/api/v1/uploads/init \
  -H 'Content-Type: application/json' \
  --data-binary @- > e2e-artifacts/upload-init.json
upload_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/upload-init.json", encoding="utf-8"))["upload_id"])' | tr -d '\r')"
upload_part_size="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/upload-init.json", encoding="utf-8"))["part_size_bytes"])' | tr -d '\r')"
upload_total_parts="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/upload-init.json", encoding="utf-8"))["total_parts"])' | tr -d '\r')"
for part_number in $(seq 1 "$upload_total_parts"); do
  part_file="e2e-artifacts/upload-part-${part_number}.bin"
  dd if="$upload_source" of="$part_file" bs="$upload_part_size" skip=$((part_number - 1)) count=1 status=none
  part_checksum="$("$PYTHON_BIN" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$part_file" | tr -d '\r')"
  curl --fail --silent --show-error \
    -X PUT "http://localhost:8000/api/v1/uploads/$upload_id/parts/$part_number" \
    -H "X-Part-SHA256: $part_checksum" \
    --data-binary "@$part_file" > "e2e-artifacts/upload-part-${part_number}.json"
  rm -f "$part_file"
done
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/uploads/$upload_id/complete" \
  -H 'Content-Type: application/json' \
  --data "{\"checksum_sha256\":\"$upload_checksum\"}" \
  > e2e-artifacts/upload-complete.json
source_asset_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/upload-complete.json", encoding="utf-8"))["asset_id"])' | tr -d '\r')"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$project_id/analyze" \
  -H 'Content-Type: application/json' \
  --data "{\"asset_id\":\"$source_asset_id\",\"top_highlights\":3}" \
  > e2e-artifacts/auto-edit-analysis.json
analysis_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/auto-edit-analysis.json", encoding="utf-8"))["analysis_id"])' | tr -d '\r')"
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/analyses/$analysis_id" \
  > e2e-artifacts/auto-edit-analysis-before-restart.json
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$project_id/analyses/$analysis_id/vision" \
  -H 'Content-Type: application/json' \
  --data '{"aspect_ratios":["9:16","16:9","1:1","4:5"],"sample_interval_seconds":4,"minimum_tracking_confidence":0.6,"subtitle_safe_area_bottom":0.18,"maximum_crop_jump":0.08,"manual_overrides":[]}' \
  > e2e-artifacts/vision-analysis.json
vision_analysis_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/vision-analysis.json", encoding="utf-8"))["vision_analysis_id"])' | tr -d '\r')"
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/vision-analyses/$vision_analysis_id" \
  > e2e-artifacts/vision-analysis-before-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/assets" \
  > e2e-artifacts/project-assets-after-upload.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/cost-summary" \
  > e2e-artifacts/cost-summary-after-vision.json

echo "[e2e] building V2-06 media plan and resolving fixture media asynchronously"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$project_id/media-plans" \
  -H 'Content-Type: application/json' \
  --data "{\"analysis_id\":\"$analysis_id\",\"vision_analysis_id\":\"$vision_analysis_id\",\"platform\":\"facebook_reels\",\"brand_context\":\"Ngoc Phuong Dong original media\",\"max_ai_cost_vnd\":0}" \
  > e2e-artifacts/media-plan.json
media_plan_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/media-plan.json", encoding="utf-8"))["media_plan_id"])' | tr -d '\r')"
media_item_ids="$("$PYTHON_BIN" -c 'import json; print(" ".join(item["media_plan_item_id"] for item in json.load(open("e2e-artifacts/media-plan.json", encoding="utf-8"))["items"]))' | tr -d '\r')"
: > e2e-artifacts/media-resolution-jobs.jsonl
for media_item_id in $media_item_ids; do
  curl --fail --silent --show-error \
    -X POST "http://localhost:8000/api/v1/projects/$project_id/media-plans/$media_plan_id/items/$media_item_id/resolve" \
    -H 'Content-Type: application/json' \
    --data '{}' >> e2e-artifacts/media-resolution-jobs.jsonl
  printf '\n' >> e2e-artifacts/media-resolution-jobs.jsonl
done
media_job_ids="$("$PYTHON_BIN" -c 'import json; print(" ".join(json.loads(line)["resolution_job_id"] for line in open("e2e-artifacts/media-resolution-jobs.jsonl", encoding="utf-8") if line.strip()))' | tr -d '\r')"
for media_job_id in $media_job_ids; do
  media_terminal=0
  for _ in $(seq 1 60); do
    media_status_json="$(curl --fail --silent --show-error "http://localhost:8000/api/v1/projects/$project_id/media-resolution-jobs/$media_job_id")"
    printf '%s\n' "$media_status_json" > "e2e-artifacts/media-resolution-$media_job_id.json"
    media_status="$(printf '%s' "$media_status_json" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["status"])' | tr -d '\r')"
    if [[ "$media_status" == "succeeded" ]]; then
      media_terminal=1
      break
    fi
    if [[ "$media_status" == "failed" || "$media_status" == "cancelled" || "$media_status" == "needs_approval" ]]; then
      echo "Media resolution job ended unexpectedly: $media_status" >&2
      printf '%s\n' "$media_status_json" >&2
      exit 1
    fi
    sleep 1
  done
  if [[ "$media_terminal" != "1" ]]; then
    echo "Media resolution job did not finish before timeout: $media_job_id" >&2
    exit 1
  fi
done
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/media-plans/$media_plan_id" \
  > e2e-artifacts/media-plan-resolved.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/media-assets" \
  > e2e-artifacts/media-assets.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/cost-summary" \
  > e2e-artifacts/cost-summary-after-media.json

echo "[e2e] creating the V2-07 editable timeline and version-bound 540p preview"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$project_id/timeline" \
  -H 'Content-Type: application/json' \
  --data "{\"analysis_id\":\"$analysis_id\",\"media_plan_id\":\"$media_plan_id\",\"actor_ref\":\"github-actions-e2e\"}" \
  > e2e-artifacts/timeline-v1.json
timeline_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/timeline-v1.json", encoding="utf-8"))["timeline_id"])' | tr -d '\r')"
source_clip_id="$("$PYTHON_BIN" -c 'import json; d=json.load(open("e2e-artifacts/timeline-v1.json", encoding="utf-8")); print(next(c["clip_id"] for t in d["snapshot"]["tracks"] if t["kind"] == "source" for c in t["clips"]))' | tr -d '\r')"
curl --fail --silent --show-error \
  -X PUT "http://localhost:8000/api/v1/projects/$project_id/timeline" \
  -H 'Content-Type: application/json' \
  --data "{\"expected_version\":1,\"actor_ref\":\"github-actions-e2e\",\"reason\":\"e2e-editor-interaction\",\"operations\":[{\"type\":\"move\",\"clip_id\":\"$source_clip_id\",\"timeline_start\":0.25}]}" \
  > e2e-artifacts/timeline-v2.json
stale_status="$(curl --silent --show-error \
  -o e2e-artifacts/timeline-conflict.json \
  -w '%{http_code}' \
  -X PUT "http://localhost:8000/api/v1/projects/$project_id/timeline" \
  -H 'Content-Type: application/json' \
  --data "{\"expected_version\":1,\"actor_ref\":\"stale-editor\",\"operations\":[{\"type\":\"disable\",\"clip_id\":\"$source_clip_id\",\"disabled\":true}]}")"
if [[ "$stale_status" != "409" ]]; then
  echo "Expected optimistic-concurrency HTTP 409, received $stale_status" >&2
  exit 1
fi
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$project_id/preview" \
  -H 'Content-Type: application/json' \
  --data '{"timeline_version":2,"width":540,"height":960,"actor_ref":"github-actions-e2e"}' \
  > e2e-artifacts/preview-created.json
preview_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/preview-created.json", encoding="utf-8"))["preview_id"])' | tr -d '\r')"
preview_terminal=0
for _ in $(seq 1 180); do
  preview_json="$(curl --fail --silent --show-error "http://localhost:8000/api/v1/projects/$project_id/previews/$preview_id")"
  printf '%s\n' "$preview_json" > e2e-artifacts/preview-ready.json
  preview_status="$(printf '%s' "$preview_json" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["status"])' | tr -d '\r')"
  if [[ "$preview_status" == "ready" ]]; then
    preview_terminal=1
    break
  fi
  if [[ "$preview_status" == "failed" || "$preview_status" == "cancelled" || "$preview_status" == "stale" ]]; then
    echo "Preview ended unexpectedly: $preview_status" >&2
    printf '%s\n' "$preview_json" >&2
    exit 1
  fi
  sleep 1
done
if [[ "$preview_terminal" != "1" ]]; then
  echo "Preview did not finish before timeout: $preview_id" >&2
  exit 1
fi
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/previews/$preview_id/content" \
  --output e2e-artifacts/preview.mp4
"$docker_bin" compose cp e2e-artifacts/preview.mp4 worker:/tmp/v2-07-e2e-preview.mp4 >/dev/null
"$docker_bin" compose exec -T worker ffprobe -v error \
  -show_entries stream=codec_type,codec_name,width,height \
  -show_entries format=duration \
  -of json /tmp/v2-07-e2e-preview.mp4 \
  > e2e-artifacts/preview-probe.json
curl --fail --silent --show-error \
  -X PUT "http://localhost:8000/api/v1/projects/$project_id/timeline" \
  -H 'Content-Type: application/json' \
  --data "{\"expected_version\":2,\"actor_ref\":\"github-actions-e2e\",\"reason\":\"preview-invalidation\",\"operations\":[{\"type\":\"set_clip_properties\",\"clip_id\":\"$source_clip_id\",\"opacity\":0.9}]}" \
  > e2e-artifacts/timeline-v3.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/previews/$preview_id" \
  > e2e-artifacts/preview-stale-before-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/timeline/versions" \
  > e2e-artifacts/timeline-versions-before-restart.json

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path("e2e-artifacts")
v1 = json.loads((root / "timeline-v1.json").read_text(encoding="utf-8"))
v2 = json.loads((root / "timeline-v2.json").read_text(encoding="utf-8"))
v3 = json.loads((root / "timeline-v3.json").read_text(encoding="utf-8"))
conflict = json.loads((root / "timeline-conflict.json").read_text(encoding="utf-8"))
ready = json.loads((root / "preview-ready.json").read_text(encoding="utf-8"))
stale = json.loads((root / "preview-stale-before-restart.json").read_text(encoding="utf-8"))
probe = json.loads((root / "preview-probe.json").read_text(encoding="utf-8"))
versions = json.loads((root / "timeline-versions-before-restart.json").read_text(encoding="utf-8"))

assert v1["current_version"] == 1 and v2["current_version"] == 2 and v3["current_version"] == 3
assert v1["source_media_mutated"] is False and v3["publish_requested"] is False
assert conflict["detail"]["code"] == "TIMELINE_VERSION_CONFLICT", conflict
assert conflict["detail"]["current_version"] == 2, conflict
assert len(versions) == 3 and [item["version"] for item in versions] == [3, 2, 1], versions
assert ready["status"] == "ready" and ready["timeline_version"] == 2, ready
assert ready["progress"] == 100 and ready["valid_for_current_timeline"] is True, ready
assert ready["manifest"]["renderer"] == "ffmpeg-proxy-v1", ready
assert ready["manifest"]["proxy_only"] is True and ready["manifest"]["audio_included"] is False, ready
assert ready["external_call"] is False and ready["publish_requested"] is False, ready
assert stale["status"] == "stale" and stale["valid_for_current_timeline"] is False, stale
video_streams = [item for item in probe["streams"] if item["codec_type"] == "video"]
audio_streams = [item for item in probe["streams"] if item["codec_type"] == "audio"]
assert len(video_streams) == 1 and video_streams[0]["codec_name"] == "h264", probe
assert video_streams[0]["width"] == 540 and video_streams[0]["height"] == 960, probe
assert not audio_streams and float(probe["format"]["duration"]) > 0, probe
print("[e2e] V2-07 timeline, version conflict, 540p preview and invalidation verified")
PY

echo "[e2e] exercising V2-08 subtitle, audio, approval and final-render workflow"
echo "[e2e] generating a short encoded A/V fixture for bounded production-render acceptance"
"$docker_bin" compose exec -T worker ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i 'testsrc2=size=1080x1920:rate=30' \
  -f lavfi -i 'sine=frequency=440:sample_rate=48000' \
  -t 3 -shortest \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
  -c:a aac -ar 48000 -movflags +faststart \
  /tmp/v2-08-short-source.mp4
"$docker_bin" compose cp worker:/tmp/v2-08-short-source.mp4 e2e-artifacts/v2-08-short-source.mp4 >/dev/null

curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/workspaces/$workspace_id/projects" \
  -H 'Content-Type: application/json' \
  --data '{"slug":"v2-08-render-qc","name":"V2-08 Audio Subtitle Render QC","niche":"real_estate","provenance":{"source":"docker-e2e","production_fixture":true}}' \
  > e2e-artifacts/production-project.json
production_project_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/production-project.json", encoding="utf-8"))["project_id"])' | tr -d '\r')"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/versions" \
  -H 'Content-Type: application/json' \
  --data '{"label":"v2-10-learning-source","snapshot":{"acceptance":"analytics-learning","topic":"Vịnh Tiên","source_idea":{"cluster_id":"cluster_fixture_v2_10","idea_id":"idea_fixture_v2_10","title":"Vịnh Tiên - hành trình sống ven biển","hook_concept":"Mở bằng câu hỏi về không gian sống ven biển","cta_concept":"Đăng ký nhận tư vấn","visual_concept":"flycam-waterfront-plus-lifestyle"}},"provenance":{"source":"docker-e2e","fixture":true}}' \
  > e2e-artifacts/production-project-version.json
production_project_version_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/production-project-version.json", encoding="utf-8"))["project_version_id"])' | tr -d '\r')"

production_upload_source="e2e-artifacts/v2-08-short-source.mp4"
production_upload_size="$(wc -c < "$production_upload_source" | tr -d ' ')"
production_upload_checksum="$("$PYTHON_BIN" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$production_upload_source" | tr -d '\r')"
production_upload_init_payload="$(
  "$PYTHON_BIN" -c '
import json, sys
print(json.dumps({
    "project_id": sys.argv[1],
    "project_version_id": sys.argv[2],
    "filename": "v2-08-short-source.mp4",
    "media_kind": "video",
    "content_type": "video/mp4",
    "size_bytes": int(sys.argv[3]),
    "checksum_sha256": sys.argv[4],
    "part_size_bytes": 8388608,
    "rights_status": "owned",
    "license": "ci-synthetic-fixture"
}))
' "$production_project_id" "$production_project_version_id" "$production_upload_size" "$production_upload_checksum"
)"
printf '%s' "$production_upload_init_payload" | curl --fail --silent --show-error \
  -X POST http://localhost:8000/api/v1/uploads/init \
  -H 'Content-Type: application/json' \
  --data-binary @- > e2e-artifacts/production-upload-init.json
production_upload_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/production-upload-init.json", encoding="utf-8"))["upload_id"])' | tr -d '\r')"
production_part_checksum="$("$PYTHON_BIN" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$production_upload_source" | tr -d '\r')"
curl --fail --silent --show-error \
  -X PUT "http://localhost:8000/api/v1/uploads/$production_upload_id/parts/1" \
  -H "X-Part-SHA256: $production_part_checksum" \
  --data-binary "@$production_upload_source" > e2e-artifacts/production-upload-part-1.json
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/uploads/$production_upload_id/complete" \
  -H 'Content-Type: application/json' \
  --data "{\"checksum_sha256\":\"$production_upload_checksum\"}" \
  > e2e-artifacts/production-upload-complete.json
production_source_asset_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/production-upload-complete.json", encoding="utf-8"))["asset_id"])' | tr -d '\r')"

curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/analyze" \
  -H 'Content-Type: application/json' \
  --data "{\"asset_id\":\"$production_source_asset_id\",\"top_highlights\":3}" \
  > e2e-artifacts/production-auto-edit-analysis.json
production_analysis_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/production-auto-edit-analysis.json", encoding="utf-8"))["analysis_id"])' | tr -d '\r')"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/timeline" \
  -H 'Content-Type: application/json' \
  --data "{\"analysis_id\":\"$production_analysis_id\",\"actor_ref\":\"github-actions-e2e\"}" \
  > e2e-artifacts/production-timeline-before-restart.json

curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/production-package" \
  -H 'Content-Type: application/json' \
  --data '{"expected_timeline_version":1,"actor_ref":"github-actions-e2e"}' \
  > e2e-artifacts/production-package-created.json

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path("e2e-artifacts")
timeline = json.loads((root / "production-timeline-before-restart.json").read_text(encoding="utf-8"))
package = json.loads((root / "production-package-created.json").read_text(encoding="utf-8"))
duration = float(timeline["snapshot"]["duration_seconds"])
words = ["Vịnh", "Tiên", "xanh"]
slot = duration / len(words)
payload = {
    "expected_timeline_version": 1,
    "expected_subtitle_version": 1,
    "cues": [
        {
            "cue_id": "sub_vinh_tien_e2e",
            "start_seconds": 0,
            "end_seconds": duration,
            "text": "Vịnh Tiên xanh",
            "words": [
                {
                    "text": word,
                    "start_seconds": index * slot,
                    "end_seconds": (index + 1) * slot,
                }
                for index, word in enumerate(words)
            ],
        }
    ],
    "style": package["subtitle"]["style"],
    "actor_ref": "github-actions-e2e",
    "reason": "v2-08-e2e-subtitle",
}
(root / "subtitle-request.json").write_text(
    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
)
assert timeline["current_version"] == 1, timeline
assert package["timeline_version"] == 1, package
assert 2.9 <= duration <= 3.1, timeline
assert not next(track for track in timeline["snapshot"]["tracks"] if track["kind"] == "broll")["clips"]
assert package["subtitle"]["version"] == 1 and package["audio_mix"]["version"] == 1, package
assert package["publishing_allowed"] is False, package
PY

curl --fail --silent --show-error \
  -X PUT "http://localhost:8000/api/v1/projects/$production_project_id/subtitles" \
  -H 'Content-Type: application/json' \
  --data-binary @e2e-artifacts/subtitle-request.json \
  > e2e-artifacts/production-package-subtitles-v2.json

final_without_approval_status="$(curl --silent --show-error \
  -o e2e-artifacts/final-without-approval.json \
  -w '%{http_code}' \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/final-render" \
  -H 'Content-Type: application/json' \
  --data '{"expected_timeline_version":1,"expected_subtitle_version":2,"expected_audio_version":1,"profile":"vertical-1080x1920","approval_id":"apr_missing_fixture","actor_ref":"github-actions-e2e"}')"
if [[ "$final_without_approval_status" != "409" ]]; then
  echo "Expected final render without approval to fail with HTTP 409, received $final_without_approval_status" >&2
  exit 1
fi

curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/review-render" \
  -H 'Content-Type: application/json' \
  --data '{"expected_timeline_version":1,"expected_subtitle_version":2,"expected_audio_version":1,"profile":"review-540x960","actor_ref":"github-actions-e2e"}' \
  > e2e-artifacts/review-render-created.json
review_render_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/review-render-created.json", encoding="utf-8"))["render_id"])' | tr -d '\r')"
review_terminal=0
for _ in $(seq 1 300); do
  review_json="$(curl --fail --silent --show-error "http://localhost:8000/api/v1/projects/$production_project_id/renders/$review_render_id")"
  printf '%s\n' "$review_json" > e2e-artifacts/review-render-ready.json
  review_status="$(printf '%s' "$review_json" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["status"])' | tr -d '\r')"
  if [[ "$review_status" == "awaiting_review" ]]; then
    review_terminal=1
    break
  fi
  if [[ "$review_status" == "failed" || "$review_status" == "failed_qc" || "$review_status" == "cancelled" || "$review_status" == "stale" ]]; then
    echo "V2-08 review render ended unexpectedly: $review_status" >&2
    printf '%s\n' "$review_json" >&2
    exit 1
  fi
  sleep 1
done
if [[ "$review_terminal" != "1" ]]; then
  echo "V2-08 review render did not finish before timeout: $review_render_id" >&2
  exit 1
fi
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/renders/$review_render_id/content" \
  --output e2e-artifacts/review-render.mp4
"$docker_bin" compose cp e2e-artifacts/review-render.mp4 worker:/tmp/v2-08-e2e-review.mp4 >/dev/null
"$docker_bin" compose exec -T worker ffprobe -v error \
  -show_entries stream=codec_type,codec_name,width,height,sample_rate \
  -show_entries format=duration \
  -of json /tmp/v2-08-e2e-review.mp4 \
  > e2e-artifacts/review-render-probe.json

curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/approvals" \
  -H 'Content-Type: application/json' \
  --data "{\"review_render_id\":\"$review_render_id\",\"requester_ref\":\"github-actions-e2e\",\"note\":\"V2-08 deterministic review\"}" \
  > e2e-artifacts/approval-requested.json
approval_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/approval-requested.json", encoding="utf-8"))["approval_id"])' | tr -d '\r')"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/approvals/$approval_id/decision" \
  -H 'Content-Type: application/json' \
  --data '{"decision":"approved","reviewer_ref":"owner-github-actions-e2e","comment":"Reviewed voice, subtitles and preview fixture."}' \
  > e2e-artifacts/approval-approved.json

curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/final-render" \
  -H 'Content-Type: application/json' \
  --data "{\"expected_timeline_version\":1,\"expected_subtitle_version\":2,\"expected_audio_version\":1,\"profile\":\"vertical-1080x1920\",\"approval_id\":\"$approval_id\",\"actor_ref\":\"owner-github-actions-e2e\"}" \
  > e2e-artifacts/final-render-created.json
final_render_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/final-render-created.json", encoding="utf-8"))["render_id"])' | tr -d '\r')"
final_terminal=0
for _ in $(seq 1 600); do
  final_json="$(curl --fail --silent --show-error "http://localhost:8000/api/v1/projects/$production_project_id/renders/$final_render_id")"
  printf '%s\n' "$final_json" > e2e-artifacts/final-render-ready.json
  final_status="$(printf '%s' "$final_json" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["status"])' | tr -d '\r')"
  if [[ "$final_status" == "ready" ]]; then
    final_terminal=1
    break
  fi
  if [[ "$final_status" == "failed" || "$final_status" == "failed_qc" || "$final_status" == "cancelled" || "$final_status" == "stale" ]]; then
    echo "V2-08 final render ended unexpectedly: $final_status" >&2
    printf '%s\n' "$final_json" >&2
    exit 1
  fi
  sleep 1
done
if [[ "$final_terminal" != "1" ]]; then
  echo "V2-08 final render did not finish before timeout: $final_render_id" >&2
  exit 1
fi
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/renders/$final_render_id/content" \
  --output e2e-artifacts/final-render-v2-08.mp4
"$docker_bin" compose cp e2e-artifacts/final-render-v2-08.mp4 worker:/tmp/v2-08-e2e-final.mp4 >/dev/null
"$docker_bin" compose exec -T worker ffprobe -v error \
  -show_entries stream=codec_type,codec_name,width,height,sample_rate \
  -show_entries format=duration \
  -of json /tmp/v2-08-e2e-final.mp4 \
  > e2e-artifacts/final-render-probe.json

echo "[e2e] exercising V2-09 rights/platform gates and idempotent publishing dry-run"
"$PYTHON_BIN" -c '
import json, sys
payload = {
    "platform": "youtube",
    "final_render_id": sys.argv[1],
    "mode": "dry_run",
    "metadata": {
        "title": "Vịnh Tiên - hành trình sống ven biển",
        "description": "Deterministic V2-09 publishing validation.",
        "caption": "Dry-run only; no external post.",
        "hashtags": ["VinhTien", "NgocPhuongDong"],
        "privacy": "private"
    },
    "actor_ref": "owner-github-actions-e2e"
}
open("e2e-artifacts/publication-request.json", "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False))
' "$final_render_id"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/publish" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: github-actions-v2-09-dry-run-0001' \
  --data-binary @e2e-artifacts/publication-request.json \
  > e2e-artifacts/publication-dry-run.json
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/publish" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: github-actions-v2-09-dry-run-0001' \
  --data-binary @e2e-artifacts/publication-request.json \
  > e2e-artifacts/publication-idempotent-replay.json
"$PYTHON_BIN" -c '
import json
path = "e2e-artifacts/publication-request.json"
payload = json.load(open(path, encoding="utf-8"))
payload["mode"] = "live"
open("e2e-artifacts/publication-live-request.json", "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False))
'
publication_live_status="$(curl --silent --show-error \
  -o e2e-artifacts/publication-live-blocked.json \
  -w '%{http_code}' \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/publish" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: github-actions-v2-09-live-blocked-01' \
  --data-binary @e2e-artifacts/publication-live-request.json)"
if [[ "$publication_live_status" != "409" ]]; then
  echo "Expected V2-09 live publishing to fail closed with HTTP 409, received $publication_live_status" >&2
  exit 1
fi
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/publications" \
  > e2e-artifacts/publications-before-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/publication-history" \
  > e2e-artifacts/publication-history-before-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/publishing-platforms" \
  > e2e-artifacts/publishing-platforms.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/production-package" \
  > e2e-artifacts/production-package-before-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/production-history" \
  > e2e-artifacts/production-history-before-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/timeline" \
  > e2e-artifacts/production-timeline-before-restart.json

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path("e2e-artifacts")
package = json.loads((root / "production-package-before-restart.json").read_text(encoding="utf-8"))
review = json.loads((root / "review-render-ready.json").read_text(encoding="utf-8"))
review_probe = json.loads((root / "review-render-probe.json").read_text(encoding="utf-8"))
approval = json.loads((root / "approval-approved.json").read_text(encoding="utf-8"))
final = json.loads((root / "final-render-ready.json").read_text(encoding="utf-8"))
final_probe = json.loads((root / "final-render-probe.json").read_text(encoding="utf-8"))
blocked = json.loads((root / "final-without-approval.json").read_text(encoding="utf-8"))
history = json.loads((root / "production-history-before-restart.json").read_text(encoding="utf-8"))
publication = json.loads((root / "publication-dry-run.json").read_text(encoding="utf-8"))
publication_replay = json.loads((root / "publication-idempotent-replay.json").read_text(encoding="utf-8"))
publication_live = json.loads((root / "publication-live-blocked.json").read_text(encoding="utf-8"))
publications = json.loads((root / "publications-before-restart.json").read_text(encoding="utf-8"))
publication_history = json.loads((root / "publication-history-before-restart.json").read_text(encoding="utf-8"))
publishing_platforms = json.loads((root / "publishing-platforms.json").read_text(encoding="utf-8"))

def assert_av(probe, width, height):
    video = [item for item in probe["streams"] if item["codec_type"] == "video"]
    audio = [item for item in probe["streams"] if item["codec_type"] == "audio"]
    assert len(video) == 1 and video[0]["codec_name"] == "h264", probe
    assert video[0]["width"] == width and video[0]["height"] == height, probe
    assert len(audio) == 1 and audio[0]["codec_name"] == "aac", probe
    assert int(audio[0]["sample_rate"]) == 48000, probe
    assert float(probe["format"]["duration"]) > 0, probe

assert blocked["detail"]["code"] == "PRODUCTION_PACKAGE_CONFLICT", blocked
assert review["status"] == "awaiting_review" and review["qc_status"] == "passed", review
assert review["manifest"]["safety"]["publishing_allowed"] is False, review
assert review["external_publish_requested"] is False, review
assert approval["status"] == "approved" and approval["timeline_version"] == 1, approval
assert approval["subtitle_version"] == 2 and approval["audio_version"] == 1, approval
assert final["status"] == "ready" and final["qc_status"] == "passed", final
assert final["profile"] == "vertical-1080x1920", final
assert final["publishing_allowed"] is False and final["external_publish_requested"] is False, final
assert final["manifest"]["qc_status"] == "passed", final
assert package["approval"]["approval_id"] == approval["approval_id"], package
assert package["latest_final_render"]["render_id"] == final["render_id"], package
assert package["current_for_timeline"] is True and package["publishing_allowed"] is False, package
assert {item["event_type"] for item in history} >= {
    "production_package.created",
    "subtitles.version_created",
    "render.review_completed",
    "approval.approved",
    "render.final_completed",
}, history
assert_av(review_probe, 540, 960)
assert_av(final_probe, 1080, 1920)
assert publication["status"] == "dry_run_succeeded", publication
assert publication["rights_validation"]["status"] == "passed", publication
assert publication["platform_validation"]["status"] == "passed", publication
assert publication["receipt"]["mock"] is True, publication
assert publication["receipt"]["external_action"] is False, publication
assert publication["receipt"]["remote_post_id"] is None, publication
assert publication_replay["publication_id"] == publication["publication_id"], publication_replay
assert publication_live["detail"]["error"]["external_action"] is False, publication_live
assert len(publications) == 2, publications
assert {item["status"] for item in publications} == {"dry_run_succeeded", "blocked"}, publications
assert {item["event_type"] for item in publication_history} >= {
    "publication.validation_reserved",
    "publication.dry_run_succeeded",
    "publication.blocked",
}, publication_history
assert len(publishing_platforms) == 4, publishing_platforms
assert all(item["live_execution_enabled"] is False for item in publishing_platforms), publishing_platforms
assert all(item["official_provider"]["supports_live_publish"] is False for item in publishing_platforms), publishing_platforms
print("[e2e] V2-08 final QC and V2-09 fail-closed publishing dry-run verified")
PY

echo "[e2e] exercising V2-10 normalized analytics, winner detection and learning feedback"
publication_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/publication-dry-run.json", encoding="utf-8"))["publication_id"])' | tr -d '\r')"
"$PYTHON_BIN" -c '
import json, sys
payload = {
    "publication_id": sys.argv[1],
    "provider_mode": "fixture",
    "trigger": "initial",
    "fixture_profile": "winner_candidate",
    "actor_ref": "owner-github-actions-e2e"
}
open("e2e-artifacts/analytics-winner-request.json", "w", encoding="utf-8").write(json.dumps(payload))
' "$publication_id"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/analytics/syncs" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: github-actions-v2-10-winner-0001' \
  --data-binary @e2e-artifacts/analytics-winner-request.json \
  > e2e-artifacts/analytics-winner-created.json
analytics_winner_sync_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/analytics-winner-created.json", encoding="utf-8"))["sync_id"])' | tr -d '\r')"
analytics_terminal="0"
for _attempt in $(seq 1 90); do
  curl --fail --silent --show-error \
    "http://localhost:8000/api/v1/projects/$production_project_id/analytics/syncs/$analytics_winner_sync_id" \
    > e2e-artifacts/analytics-winner-status.json
  analytics_status="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/analytics-winner-status.json", encoding="utf-8"))["status"])' | tr -d '\r')"
  if [[ "$analytics_status" == "succeeded" ]]; then
    analytics_terminal="1"
    break
  fi
  if [[ "$analytics_status" == "failed" || "$analytics_status" == "not_configured" || "$analytics_status" == "cancelled" ]]; then
    break
  fi
  sleep 1
done
if [[ "$analytics_terminal" != "1" ]]; then
  echo "V2-10 winner analytics sync did not succeed: $analytics_winner_sync_id" >&2
  exit 1
fi
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/analytics" \
  > e2e-artifacts/analytics-winner-report.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/analytics/snapshots" \
  > e2e-artifacts/analytics-winner-snapshots.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/analytics/learning-insights" \
  > e2e-artifacts/analytics-winner-insights.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/analytics-providers" \
  > e2e-artifacts/analytics-providers.json

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path("e2e-artifacts")
report = json.loads((root / "analytics-winner-report.json").read_text(encoding="utf-8"))
snapshots = json.loads((root / "analytics-winner-snapshots.json").read_text(encoding="utf-8"))
insights = json.loads((root / "analytics-winner-insights.json").read_text(encoding="utf-8"))
providers = json.loads((root / "analytics-providers.json").read_text(encoding="utf-8"))
assert report["status"] == "ready" and report["history_count"] == 1, report
assert report["latest_snapshot"]["mock"] is True, report
assert report["latest_snapshot"]["external_call"] is False, report
assert len(report["latest_snapshot"]["points"]) == 16, report
assert report["latest_assessment"]["state"] == "winner_candidate", report
assert report["latest_assessment"]["automatic_action"] is False, report
assert report["latest_assessment"]["paid_media_mutation"] is False, report
assert report["latest_assessment"]["content_deletion"] is False, report
assert report["video_features"]["trend_cluster_id"] == "cluster_fixture_v2_10", report
assert report["video_features"]["idea_id"] == "idea_fixture_v2_10", report
assert report["video_features"]["evidence"]["trend_rank_mutated"] is False, report
assert report["video_features"]["evidence"]["idea_rank_mutated"] is False, report
assert len(snapshots) == 1 and snapshots[0]["metrics"]["revenue"] == 12000000, snapshots
assert insights and all(item["applied"] is False for item in insights), insights
assert all(item["autonomous_execution"] is False for item in insights), insights
assert any(item["trend_cluster_id"] == "cluster_fixture_v2_10" for item in insights), insights
assert len(providers) == 8, providers
assert all(item["external_calls_enabled"] is False for item in providers), providers
assert all(item["production_deployed"] is False for item in providers), providers
assert all(item["supports_sync"] is False for item in providers if item["mode"] == "official"), providers
PY

echo "[e2e] restarting worker before a second analytics snapshot"
"$docker_bin" compose restart worker >/dev/null
"$PYTHON_BIN" -c '
import json, sys
payload = {
    "publication_id": sys.argv[1],
    "provider_mode": "fixture",
    "trigger": "manual_refresh",
    "fixture_profile": "normal",
    "actor_ref": "owner-github-actions-e2e"
}
open("e2e-artifacts/analytics-normal-request.json", "w", encoding="utf-8").write(json.dumps(payload))
' "$publication_id"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/projects/$production_project_id/analytics/syncs" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: github-actions-v2-10-normal-0002' \
  --data-binary @e2e-artifacts/analytics-normal-request.json \
  > e2e-artifacts/analytics-normal-created.json
analytics_normal_sync_id="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/analytics-normal-created.json", encoding="utf-8"))["sync_id"])' | tr -d '\r')"
analytics_terminal="0"
for _attempt in $(seq 1 90); do
  curl --fail --silent --show-error \
    "http://localhost:8000/api/v1/projects/$production_project_id/analytics/syncs/$analytics_normal_sync_id" \
    > e2e-artifacts/analytics-normal-status.json
  analytics_status="$("$PYTHON_BIN" -c 'import json; print(json.load(open("e2e-artifacts/analytics-normal-status.json", encoding="utf-8"))["status"])' | tr -d '\r')"
  if [[ "$analytics_status" == "succeeded" ]]; then
    analytics_terminal="1"
    break
  fi
  if [[ "$analytics_status" == "failed" || "$analytics_status" == "not_configured" || "$analytics_status" == "cancelled" ]]; then
    break
  fi
  sleep 1
done
if [[ "$analytics_terminal" != "1" ]]; then
  echo "V2-10 normal analytics sync did not succeed after worker restart: $analytics_normal_sync_id" >&2
  exit 1
fi
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/analytics" \
  > e2e-artifacts/analytics-report-before-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/analytics/history" \
  > e2e-artifacts/analytics-history-before-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/analytics/assessments" \
  > e2e-artifacts/analytics-assessments-before-restart.json
"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path("e2e-artifacts")
report = json.loads((root / "analytics-report-before-restart.json").read_text(encoding="utf-8"))
history = json.loads((root / "analytics-history-before-restart.json").read_text(encoding="utf-8"))
assessments = json.loads((root / "analytics-assessments-before-restart.json").read_text(encoding="utf-8"))
assert report["history_count"] == 2, report
assert report["latest_assessment"]["state"] == "normal", report
assert report["latest_snapshot"]["metrics"]["revenue"] is None, report
revenue = next(item for item in report["latest_snapshot"]["points"] if item["metric"] == "revenue")
assert revenue["value"] is None and revenue["supported"] is False, revenue
assert {item["state"] for item in assessments} >= {"winner_candidate", "normal"}, assessments
assert {item["event_type"] for item in history} >= {"video.analytics.updated", "video.winner.detected"}, history
print("[e2e] V2-10 mock snapshots, null semantics, worker restart and learning verified")
PY

replay_response="$(
  curl --fail --silent --show-error \
    -X POST http://localhost:8000/api/v1/video-jobs \
    -H 'Content-Type: application/json' \
    -H 'Idempotency-Key: github-actions-sprint-1-e2e' \
    --data-binary @examples/vinhomes-green-paradise.request.json
)"
printf '%s\n' "$replay_response" > e2e-artifacts/idempotency-replay.json

"$PYTHON_BIN" - <<'PY'
import json
from decimal import Decimal
from pathlib import Path

root = Path("e2e-artifacts")
create = json.loads((root / "create-response.json").read_text(encoding="utf-8"))
job = json.loads((root / "job-status.json").read_text(encoding="utf-8"))
workspace = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
project = json.loads((root / "project.json").read_text(encoding="utf-8"))
versions = json.loads((root / "project-versions.json").read_text(encoding="utf-8"))
assets = json.loads((root / "project-assets.json").read_text(encoding="utf-8"))
providers = json.loads((root / "providers.json").read_text(encoding="utf-8"))
costs = json.loads((root / "cost-records.json").read_text(encoding="utf-8"))
summary = json.loads((root / "cost-summary.json").read_text(encoding="utf-8"))
events = json.loads((root / "job-events.json").read_text(encoding="utf-8"))
replay = json.loads((root / "idempotency-replay.json").read_text(encoding="utf-8"))

assert replay["job_id"] == create["job_id"], (replay, create)
assert workspace["workspace_id"] == job["workspace_id"]
assert project["project_id"] == job["project_id"]
assert project["current_version_id"] == job["project_version_id"]
assert versions and versions[0]["project_version_id"] == job["project_version_id"]
assert all(
    artifact.get("asset_id")
    and artifact.get("object_key")
    and artifact.get("checksum_sha256")
    and artifact.get("storage_provider") == "s3"
    for artifact in job["artifacts"]
), job["artifacts"]
assert len(assets) == len(job["artifacts"]), (len(assets), len(job["artifacts"]))
assert {asset["asset_id"] for asset in assets} == {item["asset_id"] for item in job["artifacts"]}
provider_keys = {(item["provider_key"], item["capability"]) for item in providers}
assert {
    ("deterministic-content", "content"),
    ("espeak", "tts"),
    ("openai-tts", "tts"),
    ("remotion", "rendering"),
    ("s3", "object_storage"),
}.issubset(provider_keys), provider_keys
assert len(costs) == 3, costs
assert all(item["currency"] == "VND" for item in costs), costs
assert summary["project_id"] == job["project_id"], summary
assert summary["currency"] == "VND", summary
assert Decimal(str(summary["estimated_cost"])) == 0, summary
assert Decimal(str(summary["actual_cost"])) == 0, summary
assert summary["unpriced_operations"] == 0, summary
assert summary["needs_approval"] is False, summary
assert summary["records"] == 3, summary
event_types = [item["event_type"] for item in events]
assert event_types[0] == "job.created", event_types
assert "job.transitioned" in event_types, event_types
assert event_types.count("job.artifact_recorded") == len(job["artifacts"]), event_types
print("[e2e] durable project metadata, VND ledger and audit verified")
PY

echo "[e2e] collecting deterministic trend evidence and building draft opportunities"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/workspaces/$workspace_id/trend-signals/collect" \
  -H 'Content-Type: application/json' \
  --data '{"provider_key":"fixture-trends","country":"VN","language":"vi"}' \
  > e2e-artifacts/trend-collection.json
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/workspaces/$workspace_id/trend-clusters/refresh" \
  -H 'Content-Type: application/json' \
  --data '{"channel":"short-video","niche":"real_estate","business_objective":"lead_generation","as_of":"2026-08-26T08:00:00Z"}' \
  > e2e-artifacts/trend-clusters.json
cluster_id="$("$PYTHON_BIN" -c 'import json; d=json.load(open("e2e-artifacts/trend-clusters.json", encoding="utf-8")); print(d[0]["cluster_id"])' | tr -d '\r')"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/trend-clusters/$cluster_id/ideas/generate" \
  -H 'Content-Type: application/json' \
  --data '{"channel":"short-video","niche":"real_estate","business_objective":"lead_generation","audience":"Khach hang quan tam bat dong san","cta":"Dang ky nhan tu van","count":6}' \
  > e2e-artifacts/trend-ideas.json
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/workspaces/$workspace_id/content-opportunities/refresh" \
  -H 'Content-Type: application/json' \
  --data '{"channel":"short-video","niche":"real_estate","business_objective":"lead_generation","audience":"Khach hang quan tam bat dong san","cta":"Dang ky nhan tu van","top_n":6,"ideas_per_cluster":3}' \
  > e2e-artifacts/content-opportunity-queue.json
idea_id="$("$PYTHON_BIN" -c 'import json; d=json.load(open("e2e-artifacts/trend-ideas.json", encoding="utf-8")); print(d[0]["idea_id"])' | tr -d '\r')"
curl --fail --silent --show-error \
  -X POST "http://localhost:8000/api/v1/ideas/$idea_id/projects" \
  -H 'Content-Type: application/json' \
  --data '{}' \
  > e2e-artifacts/idea-project.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/workspaces/$workspace_id/content-opportunities" \
  > e2e-artifacts/content-opportunity-queue-before-restart.json
curl --fail --silent --show-error http://localhost:3000/ > e2e-artifacts/studio-index.html
curl --fail --silent --show-error -D e2e-artifacts/studio-headers.txt -o /dev/null http://localhost:3000/

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path("e2e-artifacts")
collection = json.loads((root / "trend-collection.json").read_text(encoding="utf-8"))
clusters = json.loads((root / "trend-clusters.json").read_text(encoding="utf-8"))
ideas = json.loads((root / "trend-ideas.json").read_text(encoding="utf-8"))
queue = json.loads((root / "content-opportunity-queue.json").read_text(encoding="utf-8"))
idea_project = json.loads((root / "idea-project.json").read_text(encoding="utf-8"))
studio = (root / "studio-index.html").read_text(encoding="utf-8")
headers = (root / "studio-headers.txt").read_text(encoding="utf-8").casefold()

assert collection["snapshot"]["signal_count"] == 8, collection
assert collection["snapshot"]["new_signal_count"] == 8, collection
assert len(collection["signals"]) == 8, collection
search_signal = next(item for item in collection["signals"] if item["source"] == "google_trends")
assert search_signal["views"] is None and search_signal["likes"] is None, search_signal
assert all(item["provenance"]["creator_media_downloaded"] is False for item in collection["signals"])
assert len(clusters) == 4, clusters
assert any(item["lifecycle"] == "breakout" for item in clusters), clusters
assert all(item["score"]["estimated"] is True for item in clusters), clusters
assert len(ideas) == 6 and len({item["variant_key"] for item in ideas}) == 6, ideas
assert all(item["status"] == "draft" for item in ideas), ideas
assert all(item["provenance"]["copied_creator_media"] is False for item in ideas), ideas
assert len(queue) == 6 and [item["rank"] for item in queue] == list(range(1, 7)), queue
assert [item["score"] for item in queue] == sorted((item["score"] for item in queue), reverse=True), queue
assert all(item["state"] == "proposed" and item["provenance"]["execution"] is False for item in queue)
assert idea_project["status"] == "selected", idea_project
assert idea_project["project_id"].startswith("prj_"), idea_project
assert idea_project["project_version_id"].startswith("pver_"), idea_project
assert "Trend Radar" in studio and "Idea Engine" in studio and "Content Opportunity Queue" in studio
assert "content-security-policy:" in headers, headers
print("[e2e] V2-03 trend, idea, queue and Studio contracts verified")
PY

"$PYTHON_BIN" - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path("e2e-artifacts")
upload = json.loads((root / "upload-complete.json").read_text(encoding="utf-8"))
analysis = json.loads((root / "auto-edit-analysis.json").read_text(encoding="utf-8"))
assets = json.loads((root / "project-assets-after-upload.json").read_text(encoding="utf-8"))
vision = json.loads((root / "vision-analysis.json").read_text(encoding="utf-8"))
cost = json.loads((root / "cost-summary-after-vision.json").read_text(encoding="utf-8"))
source = root / "final.mp4"

assert upload["duplicate"] is False, upload
assert upload["checksum_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest(), upload
assert upload["media_metadata"]["media_kind"] == "video", upload
assert upload["media_metadata"]["width"] == 1080, upload
assert upload["media_metadata"]["height"] == 1920, upload
asset = next(item for item in assets if item["asset_id"] == upload["asset_id"])
assert asset["asset_class"] == "source" and asset["kind"] == "video", asset
assert asset["provenance"]["source_type"] == "user_upload", asset
assert asset["provenance"]["rights_status"] == "owned", asset
assert analysis["status"] == "succeeded", analysis
assert analysis["transcript"]["is_original_evidence"] is True, analysis
assert analysis["transcript"]["version"] == 1, analysis
assert len(analysis["transcript"]["segments"]) == 4, analysis
assert len(analysis["scenes"]) == 4, analysis
assert len(analysis["silence_decisions"]) == 3, analysis
assert len(analysis["highlights"]) == 3, analysis
assert [item["rank"] for item in analysis["highlights"]] == [1, 2, 3], analysis
assert all(not item["conflicts_with_speech"] for item in analysis["silence_decisions"] if item["enabled"])
assert analysis["source_media_mutated"] is False, analysis
assert analysis["publish_requested"] is False, analysis
assert vision["status"] == "succeeded", vision
assert vision["provider_key"] == "fixture-vision", vision
assert vision["model"] == "deterministic-vision-v2-05", vision
assert vision["frames"] and vision["scenes"] and vision["subject_tracks"], vision
assert vision["ocr_detection_count"] > 0, vision
assert [item["aspect_ratio"] for item in vision["reframe_plans"]] == ["9:16", "16:9", "1:1", "4:5"], vision
assert all(item["keyframes"] for item in vision["reframe_plans"]), vision
for plan in vision["reframe_plans"]:
    for previous, current in zip(plan["keyframes"], plan["keyframes"][1:]):
        assert abs(current["x"] - previous["x"]) <= plan["maximum_jump"] + 1e-9, plan
        assert abs(current["y"] - previous["y"]) <= plan["maximum_jump"] + 1e-9, plan
assert all(frame["evidence_frame_reference"].startswith("asset://") for frame in vision["frames"]), vision
assert all(0 <= frame["quality"]["quality_score"] <= 1 for frame in vision["frames"]), vision
assert vision["best_frame_ids"] and vision["thumbnail_candidate_ids"], vision
assert vision["source_media_mutated"] is False, vision
assert vision["publish_requested"] is False, vision
assert vision["paid_external_call"] is False, vision
assert vision["provenance"]["provider_evidence"]["fixture"] is True, vision
assert vision["provenance"]["provider_evidence"]["real_provider_tested"] is False, vision
assert cost["currency"] == "VND" and float(cost["actual_cost"]) == 0, cost
assert cost["records"] >= 6, cost
print("[e2e] V2-04 plus V2-05 structured Vision and Smart Reframe contracts verified")
PY

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path("e2e-artifacts")
plan = json.loads((root / "media-plan-resolved.json").read_text(encoding="utf-8"))
assets = json.loads((root / "media-assets.json").read_text(encoding="utf-8"))
cost = json.loads((root / "cost-summary-after-media.json").read_text(encoding="utf-8"))
strategies = [item["strategy"] for item in plan["items"]]

assert strategies == ["user_asset", "stock_video", "ai_image", "ai_video"], strategies
assert all(item["broll"]["search_query"] and item["broll"]["generation_prompt"] for item in plan["items"])
assert all(item["status"] == "resolved" for item in plan["items"]), plan
assert plan["unresolved_items"] == 0, plan
assert plan["projected_ai_cost_vnd"] == "0.0000", plan
assert plan["source_media_mutated"] is False and plan["publish_requested"] is False, plan
assert plan["paid_external_call"] is False, plan
assert plan["publishing_blocked"] is True, plan
assert len(assets) == 4, assets
assert any(item["source_type"] == "user_upload" and item["publishing_allowed"] for item in assets), assets
fixtures = [item for item in assets if item["source_type"] != "user_upload"]
assert fixtures and all(not item["production_eligible"] for item in fixtures), fixtures
assert all(not item["publishing_allowed"] and not item["owner_override_recorded"] for item in fixtures), fixtures
assert all(item["generation_provenance"].get("real_provider_tested") is False for item in fixtures), fixtures
assert all(job["status"] == "succeeded" and not job["external_call"] and not job["paid"] and not job["real_provider_tested"] for job in plan["resolution_jobs"]), plan["resolution_jobs"]
assert all(candidate["provenance"]["social_media_downloaded"] is False for item in plan["items"] for candidate in item["candidates"])
assert cost["currency"] == "VND" and float(cost["actual_cost"]) == 0, cost
assert cost["records"] >= 11, cost
print("[e2e] V2-06 B-roll, media provider, rights and asynchronous resolution contracts verified")
PY

echo "[e2e] restarting API to verify PostgreSQL recovery"
"$docker_bin" compose restart api >/dev/null
ready=0
for _ in $(seq 1 45); do
  if curl --fail --silent http://localhost:8000/readyz >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" != "1" ]]; then
  echo "API did not recover after restart" >&2
  exit 1
fi
"$PYTHON_BIN" - <<'PY'
import hashlib
import hmac
import json
import time
import urllib.request
from pathlib import Path

key = b"v2-11-e2e-inbound-key-at-least-32-bytes"
def get(path, nonce):
    timestamp = int(time.time())
    content_hash = hashlib.sha256(b"").hexdigest()
    canonical = "\n".join(("GET", path, "", str(timestamp), nonce, content_hash))
    headers = {
        "X-NPD-Service-Id": "agent-hub-e2e",
        "X-NPD-Key-Id": "inbound-v1",
        "X-NPD-Timestamp": str(timestamp),
        "X-NPD-Nonce": nonce,
        "X-NPD-Content-SHA256": content_hash,
        "X-NPD-Signature": hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest(),
        "X-NPD-Contract-Version": "agent-hub-bridge.v1",
    }
    with urllib.request.urlopen(urllib.request.Request("http://localhost:8000" + path, headers=headers), timeout=10) as response:
        return json.load(response)

deliveries = get("/api/v1/bridge/webhook-deliveries", "delivery-after-restart-0001")
events = get("/api/v1/bridge/events", "events-after-restart-0001")
Path("e2e-artifacts/bridge-deliveries-after-restart.json").write_text(json.dumps(deliveries, indent=2), encoding="utf-8")
Path("e2e-artifacts/bridge-events-after-restart.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
before_deliveries = json.loads(Path("e2e-artifacts/bridge-deliveries-before-restart.json").read_text(encoding="utf-8"))
before_events = json.loads(Path("e2e-artifacts/bridge-events-before-restart.json").read_text(encoding="utf-8"))
assert deliveries == before_deliveries, (before_deliveries, deliveries)
assert events == before_events, (before_events, events)
print("[e2e] V2-11 bridge PostgreSQL recovery verified")
PY
curl --fail --silent --show-error "http://localhost:8000/api/v1/video-jobs/$job_id" > e2e-artifacts/job-status-after-restart.json
curl --fail --silent --show-error "http://localhost:8000/api/v1/workspaces/$workspace_id/content-opportunities" > e2e-artifacts/content-opportunity-queue-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/analyses/$analysis_id" \
  > e2e-artifacts/auto-edit-analysis-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/vision-analyses/$vision_analysis_id" \
  > e2e-artifacts/vision-analysis-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/media-plans/$media_plan_id" \
  > e2e-artifacts/media-plan-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/media-assets" \
  > e2e-artifacts/media-assets-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/timeline" \
  > e2e-artifacts/timeline-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$project_id/previews/$preview_id" \
  > e2e-artifacts/preview-stale-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/timeline" \
  > e2e-artifacts/production-timeline-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/production-package" \
  > e2e-artifacts/production-package-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/renders/$final_render_id" \
  > e2e-artifacts/final-render-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/production-history" \
  > e2e-artifacts/production-history-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/publications" \
  > e2e-artifacts/publications-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/publication-history" \
  > e2e-artifacts/publication-history-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/analytics" \
  > e2e-artifacts/analytics-report-after-restart.json
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/projects/$production_project_id/analytics/history" \
  > e2e-artifacts/analytics-history-after-restart.json
"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path("e2e-artifacts")
before = json.loads((root / "job-status.json").read_text(encoding="utf-8"))
after = json.loads((root / "job-status-after-restart.json").read_text(encoding="utf-8"))
queue_before = json.loads(
    (root / "content-opportunity-queue-before-restart.json").read_text(encoding="utf-8")
)
queue_after = json.loads((root / "content-opportunity-queue-after-restart.json").read_text(encoding="utf-8"))
analysis_before = json.loads((root / "auto-edit-analysis-before-restart.json").read_text(encoding="utf-8"))
analysis_after = json.loads((root / "auto-edit-analysis-after-restart.json").read_text(encoding="utf-8"))
vision_before = json.loads((root / "vision-analysis-before-restart.json").read_text(encoding="utf-8"))
vision_after = json.loads((root / "vision-analysis-after-restart.json").read_text(encoding="utf-8"))
media_before = json.loads((root / "media-plan-resolved.json").read_text(encoding="utf-8"))
media_after = json.loads((root / "media-plan-after-restart.json").read_text(encoding="utf-8"))
media_assets_before = json.loads((root / "media-assets.json").read_text(encoding="utf-8"))
media_assets_after = json.loads((root / "media-assets-after-restart.json").read_text(encoding="utf-8"))
timeline_before = json.loads((root / "timeline-v3.json").read_text(encoding="utf-8"))
timeline_after = json.loads((root / "timeline-after-restart.json").read_text(encoding="utf-8"))
preview_before = json.loads((root / "preview-stale-before-restart.json").read_text(encoding="utf-8"))
preview_after = json.loads((root / "preview-stale-after-restart.json").read_text(encoding="utf-8"))
production_timeline_before = json.loads(
    (root / "production-timeline-before-restart.json").read_text(encoding="utf-8")
)
production_timeline_after = json.loads(
    (root / "production-timeline-after-restart.json").read_text(encoding="utf-8")
)
package_before = json.loads((root / "production-package-before-restart.json").read_text(encoding="utf-8"))
package_after = json.loads((root / "production-package-after-restart.json").read_text(encoding="utf-8"))
final_before = json.loads((root / "final-render-ready.json").read_text(encoding="utf-8"))
final_after = json.loads((root / "final-render-after-restart.json").read_text(encoding="utf-8"))
production_history_before = json.loads((root / "production-history-before-restart.json").read_text(encoding="utf-8"))
production_history_after = json.loads((root / "production-history-after-restart.json").read_text(encoding="utf-8"))
publications_before = json.loads((root / "publications-before-restart.json").read_text(encoding="utf-8"))
publications_after = json.loads((root / "publications-after-restart.json").read_text(encoding="utf-8"))
publication_history_before = json.loads((root / "publication-history-before-restart.json").read_text(encoding="utf-8"))
publication_history_after = json.loads((root / "publication-history-after-restart.json").read_text(encoding="utf-8"))
analytics_report_before = json.loads((root / "analytics-report-before-restart.json").read_text(encoding="utf-8"))
analytics_report_after = json.loads((root / "analytics-report-after-restart.json").read_text(encoding="utf-8"))
analytics_history_before = json.loads((root / "analytics-history-before-restart.json").read_text(encoding="utf-8"))
analytics_history_after = json.loads((root / "analytics-history-after-restart.json").read_text(encoding="utf-8"))
assert after == before, (before, after)
assert queue_after == queue_before, (queue_before, queue_after)
assert analysis_after == analysis_before, (analysis_before, analysis_after)
assert vision_after == vision_before, (vision_before, vision_after)
assert media_after == media_before, (media_before, media_after)
assert media_assets_after == media_assets_before, (media_assets_before, media_assets_after)
assert timeline_after == timeline_before, (timeline_before, timeline_after)
assert preview_after == preview_before, (preview_before, preview_after)
assert production_timeline_after == production_timeline_before, (
    production_timeline_before,
    production_timeline_after,
)
assert package_after == package_before, (package_before, package_after)
assert final_after == final_before, (final_before, final_after)
assert production_history_after == production_history_before, (
    production_history_before,
    production_history_after,
)
assert publications_after == publications_before, (publications_before, publications_after)
assert publication_history_after == publication_history_before, (
    publication_history_before,
    publication_history_after,
)
assert analytics_report_after == analytics_report_before, (analytics_report_before, analytics_report_after)
assert analytics_history_after == analytics_history_before, (analytics_history_before, analytics_history_after)
assert package_after["approval"]["status"] == "approved", package_after
assert final_after["status"] == "ready" and final_after["publishing_allowed"] is False, final_after
assert {item["status"] for item in publications_after} == {"dry_run_succeeded", "blocked"}, publications_after
assert all(item["external_action"] is False for item in publications_after), publications_after
assert analytics_report_after["history_count"] == 2, analytics_report_after
assert analytics_report_after["external_execution_enabled"] is False, analytics_report_after
print("[e2e] PostgreSQL jobs, V2-08 production, V2-09 publication and V2-10 analytics recovery verified")
PY

"$docker_bin" compose exec -T api python -c '
from pathlib import Path
import sys

root = Path("/workspace/storage/jobs").resolve()
target = Path(sys.argv[1]).resolve()
assert target.name == "final.mp4" and target.parent.parent == root, target
target.unlink()
' "/workspace/storage/jobs/$job_id/final.mp4"
curl --fail --silent --show-error \
  "http://localhost:8000/api/v1/video-jobs/$job_id/artifacts/final.mp4" \
  --output e2e-artifacts/recovered-final.mp4
"$PYTHON_BIN" - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path("e2e-artifacts")
job = json.loads((root / "job-status.json").read_text(encoding="utf-8"))
video = next(item for item in job["artifacts"] if item["name"] == "final.mp4")
recovered = root / "recovered-final.mp4"
assert hashlib.sha256(recovered.read_bytes()).hexdigest() == video["checksum_sha256"], video
assert hashlib.sha256((root / "final.mp4").read_bytes()).hexdigest() == video["checksum_sha256"], video
print("[e2e] MinIO artifact recovery verified")
PY

"$docker_bin" compose exec -T worker ffmpeg -hide_banner -loglevel error -y \
  -i "/workspace/storage/jobs/$job_id/final.mp4" \
  -vf "fps=1/5,scale=360:640,tile=3x3:padding=8:margin=8:color=white" \
  -frames:v 1 "/workspace/storage/jobs/$job_id/contact-sheet.jpg"
cp "$job_dir/contact-sheet.jpg" e2e-artifacts/contact-sheet.jpg

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

qc = json.loads(Path("e2e-artifacts/qc.json").read_text(encoding="utf-8"))
request = json.loads(
    Path("examples/vinhomes-green-paradise.request.json").read_text(encoding="utf-8")
)
expected_duration = float(request["video"]["duration_seconds"])
assert qc["width"] == 1080, qc
assert qc["height"] == 1920, qc
assert abs(float(qc["fps"]) - 30.0) <= 0.01, qc
assert qc["video_codec"] == "h264", qc
assert qc["audio_codec"], qc
assert abs(float(qc["duration_seconds"]) - expected_duration) <= 3.0, qc
assert int(qc["size_bytes"]) > 100_000, qc
assert int(qc["visual_sample_count"]) >= max(1, int(expected_duration) - 1), qc
assert float(qc["dark_visual_sample_ratio"]) <= 0.10, qc
assert float(qc["visual_luma_min"]) >= 8.0, qc
assert float(qc["audio_peak_db"]) >= -35.0, qc

timing = json.loads(Path("e2e-artifacts/narration-timing.json").read_text(encoding="utf-8"))
manifest = json.loads(Path("e2e-artifacts/video-manifest.json").read_text(encoding="utf-8"))
assert len(timing["cues"]) == len(manifest["scenes"]), timing
assert manifest["subtitles"] == [
    {
        "start_seconds": cue["start_seconds"],
        "end_seconds": cue["end_seconds"],
        "text": cue["text"][:160],
    }
    for cue in timing["cues"]
], (timing, manifest["subtitles"])
for cue, scene in zip(timing["cues"], manifest["scenes"], strict=True):
    assert cue["scene_id"] == scene["id"]
    assert scene["start_seconds"] <= cue["start_seconds"] < cue["end_seconds"]
    assert cue["end_seconds"] <= scene["start_seconds"] + scene["duration_seconds"]
print("[e2e] QC verified", json.dumps(qc, ensure_ascii=False))
PY

echo "[e2e] V2-07 Auto Edit Studio passed"
