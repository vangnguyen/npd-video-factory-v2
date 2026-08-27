# Testing — V2-06

## Local checks

```bash
python -m pip install -e "apps/api[dev]" -e "services/worker[dev]" -e "services/comfyui-bridge[dev]"
python -m compileall -q apps/api/app services/worker/npd_worker services/comfyui-bridge/npd_comfyui_bridge
python -m pytest apps/api/tests services/worker/tests services/comfyui-bridge/tests -q
```

```bash
cd renderer
npm ci
npm test
npm run typecheck
npm run bundle:check
```

```bash
cd apps/studio-web
npm ci
npm test
node --check app.js
```

Independent Docker acceptance:

```bash
bash scripts/e2e-smoke.sh
```

## Durable acceptance

The E2E creates five copyright-safe fixtures and one deterministic job, then verifies:

- Alembic migration and healthy PostgreSQL, Redis and MinIO;
- workspace/project/version binding and idempotent job replay;
- monotonic job transitions and complete audit events;
- source/generated/render/metadata assets with SHA-256 and S3 object keys;
- provider registry and exactly one VND record per provider operation;
- API restart recovery from PostgreSQL;
- deletion of local `final.mp4` followed by checksum-valid recovery from MinIO;
- 1080x1920 H.264, audio, duration, luminance/black ratio and subtitle timing.
- eight normalized trend signals, four deterministic clusters and preserved `null` metrics;
- lifecycle/opportunity components, six distinct ideas and a ranked proposed queue;
- draft-project selection, Studio response/CSP and queue recovery after API restart.
- multi-part upload, exact part/file checksums and a valid signature/MIME path;
- FFprobe metadata and source-asset provenance;
- original Vietnamese transcript evidence with word timestamps;
- four deterministic scenes, three non-destructive silence decisions and Top 3 highlights;
- no enabled silence decision overlaps a spoken word;
- Auto Edit recovery after API restart and fail-closed missing live transcription provider.
- structured Vision/OCR/composition/quality evidence and explicit mock provenance;
- subject tracking, best frames and thumbnail candidates;
- all four reframe ratios, bounded crop jumps, subtitle-safe metadata and manual override;
- low-confidence center-crop fallback and fail-closed missing live Vision provider;
- Vision/reframe recovery after API restart and a zero-VND fixture provider record.
- four deterministic media strategies with explainable B-roll decisions and ranked stock evidence;
- async resolution, rights/provenance registration, VND-only cost and scratch cleanup;
- unknown-rights, over-budget, external/paid and missing-provider fail-closed behavior;
- media-plan/assets recovery after API restart and worker queue recovery;
- ComfyUI manifest allowlisting plus mock progress/result/cancel/timeout/retry behavior.

The API/unit suite separately covers signature/MIME rejection, missing or corrupt upload parts,
same-project checksum duplicate reuse and Top 5 output. The repository also resolves a
unique-fingerprint race to the already-created analysis instead of leaking a database conflict.
The Vision suite separately covers normalized box/request validation, replay idempotency, restart
reads, manual-override versioning, provider failure state and source immutability.

The script removes only its disposable Compose volumes on exit. Normal CI performs no paid
call. The manual paid-provider smoke still requires explicit dispatch, protected-environment
approval and a secret; it is not human Vietnamese voice acceptance.

## CI gates

`Video Factory V2 CI` runs Python plus Alembic upgrade/downgrade/replay, renderer tests and
bundle, Studio tests, safety/secret/Compose checks, and the durable Docker E2E. A stacked PR must be
retargeted to the latest approved base and rerun all gates before merge consideration.
