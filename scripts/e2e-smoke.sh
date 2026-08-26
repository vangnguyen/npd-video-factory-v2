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
assert after == before, (before, after)
assert queue_after == queue_before, (queue_before, queue_after)
print("[e2e] PostgreSQL job and content queue recovery verified")
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

echo "[e2e] V2-03 Trend Radar and Idea Intelligence passed"
