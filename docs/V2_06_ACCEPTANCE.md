# V2-06 acceptance — Media Intelligence

## Decision

V2-06 is implemented for deterministic local/CI acceptance. It is not production-deployed and it
does not authorize merge, real provider execution or publishing. Stock/image/video fixtures and the
ComfyUI mock prove contracts only; real-provider and human media-quality acceptance remain open.

## Acceptance coverage

| Area | Evidence | Result |
|---|---|---|
| MediaPlanner and BrollPlanner | four-scene fixture selects user asset, stock video, AI image and AI video with intent/query/prompt/placement/confidence | PASS |
| Stock provider contract | search image/video, candidate lookup, materialization, license/creator/source/dimensions/duration | PASS with synthetic fixture |
| Image/video provider contracts | typed request, VND estimate, deterministic artifact and full generation provenance | PASS with synthetic fixtures |
| Async resolution | persistent jobs, Redis queue, worker claim/ack, restart recovery and idempotent replay | PASS |
| Rights/provenance | source type, rights, license, source, creator, generation evidence and production eligibility | PASS |
| Unknown rights | blocks publishing with no owner override | PASS |
| Cost boundary | VND only; over-budget generation stops before provider call | PASS |
| External/paid boundary | disabled providers are not estimated or executed | PASS |
| Missing providers | explicit `not_configured`/failed resolution, no pretend-live state | PASS |
| ComfyUI bridge | eight allowlisted/versioned workflow contracts; queue/status/progress/result/cancel/timeout/retry | PASS with mock backend |
| Arbitrary graph prevention | request schema has workflow ID and typed inputs, no graph field | PASS |
| Source integrity | source checksum unchanged; resolution scratch cleaned | PASS |
| Persistence | Alembic upgrade/downgrade/replay and repository restart reads | PASS |
| API | create/list/get plan, enqueue/read resolution, list media provenance | PASS |
| Existing V2 regression | API/worker/renderer/Studio plus Docker E2E are required CI gates | local PASS; authoritative GitHub evidence is the draft PR checks |

## Deterministic expected output

For the four V2-04 scenes, V2-06 produces this fixture strategy sequence:

1. reuse immutable user upload;
2. resolve a licensed synthetic stock-video contract;
3. generate a synthetic SVG image contract;
4. generate a non-playable video-generation JSON contract.

All operations cost `0 VND`, make no external/paid call and report
`real_provider_tested=false`. The user upload may be publishing-eligible because it is owned; all
other fixture outputs remain `production_eligible=false`, therefore the complete media plan is
still `publishing_blocked=true`.

## Required checks before merge consideration

```bash
python -m compileall -q apps/api/app services/worker/npd_worker services/comfyui-bridge/npd_comfyui_bridge
python -m pytest apps/api/tests services/worker/tests services/comfyui-bridge/tests -q
cd apps/api && alembic -c alembic.ini upgrade head
cd renderer && npm test && npm run typecheck && npm run bundle:check
cd apps/studio-web && npm test && node --check app.js
bash scripts/e2e-smoke.sh
git diff --check
```

The GitHub PR must be draft, all CI gates must be green and owner review is still required. CI
success is not permission to merge or deploy.

## Remaining owner gates

- select and license a real stock provider, then run manual search/download/rights acceptance;
- provision and secure real ComfyUI/GPU or another generation provider;
- approve versioned executable workflow graphs and model checksums;
- define live VND budgets and separately authorize external/paid execution;
- conduct visual/human quality and rights review on real outputs;
- implement API authentication/RBAC before any public deployment;
- retain `PUBLISH_ENABLED=false` until a later publishing phase and explicit owner gate.
