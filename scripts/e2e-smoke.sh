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
}
trap cleanup EXIT

mkdir -p e2e-artifacts storage/assets/vinhomes-green-paradise storage/jobs
cp .env.example .env

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
  > e2e-artifacts/timeline-before-restart.json
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
v3 = json.loads((root / "timeline-before-restart.json").read_text(encoding="utf-8"))
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
timeline_before = json.loads((root / "timeline-before-restart.json").read_text(encoding="utf-8"))
timeline_after = json.loads((root / "timeline-after-restart.json").read_text(encoding="utf-8"))
preview_before = json.loads((root / "preview-stale-before-restart.json").read_text(encoding="utf-8"))
preview_after = json.loads((root / "preview-stale-after-restart.json").read_text(encoding="utf-8"))
assert after == before, (before, after)
assert queue_after == queue_before, (queue_before, queue_after)
assert analysis_after == analysis_before, (analysis_before, analysis_after)
assert vision_after == vision_before, (vision_before, vision_after)
assert media_after == media_before, (media_before, media_after)
assert media_assets_after == media_assets_before, (media_assets_before, media_assets_after)
assert timeline_after == timeline_before, (timeline_before, timeline_after)
assert preview_after == preview_before, (preview_before, preview_after)
print("[e2e] PostgreSQL job, content queue, Auto Edit, Vision, Media Intelligence and timeline recovery verified")
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
