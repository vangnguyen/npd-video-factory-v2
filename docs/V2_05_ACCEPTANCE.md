# V2-05 Vision AI and Smart Reframe acceptance

Completed locally: 2026-08-27. Branch: `feat/v2-05-vision-smart-reframe`, based on approved
`main` after PR #4. GitHub CI evidence remains required before merge consideration.

## Delivered

- [x] provider-neutral `VisionProvider` and fail-closed live-provider contract;
- [x] deterministic structured local/CI fixture with explicit mock provenance;
- [x] typed frame caption, scene, object/person/product/building, environment and action output;
- [x] OCR boxes, confidence and evidence-frame references;
- [x] composition and frame-quality signals;
- [x] scene insights, best frames and thumbnail candidates;
- [x] subject tracks with timestamped observations;
- [x] crop keyframes for `9:16`, `16:9`, `1:1` and `4:5`;
- [x] bounded smoothing, maximum-jump guard and subtitle-safe area;
- [x] manual overrides and low-confidence `center_crop`/`needs_attention` fallback;
- [x] PostgreSQL migration, idempotency, restart recovery and audit provenance;
- [x] VND provider ledger record with zero-cost fixture execution;
- [x] no source mutation, paid call, render or publish.

## Acceptance matrix

| Gate | Expected |
|---|---|
| focused Vision/safety tests | PASS |
| full Python API/worker regression | PASS |
| Alembic upgrade -> downgrade base -> upgrade | PASS |
| renderer tests/typecheck/bundle | PASS |
| Studio tests and JavaScript syntax | PASS |
| Compose/safety/secret/diff checks | PASS |
| Docker deterministic E2E and API restart | PASS |
| GitHub `Video Factory V2 CI` | PASS before merge consideration |

## Local evidence

- Python compile: PASS.
- Python API/worker regression: **78 passed**, including **15** focused Vision/safety tests.
- Alembic upgrade -> downgrade base -> upgrade through `0004_v2_05`: PASS on SQLite.
- Renderer: **9 passed**; TypeScript typecheck and Remotion bundle smoke PASS.
- Studio: **4 passed**; JavaScript syntax checks PASS.
- Docker Compose configuration: PASS.
- Docker deterministic E2E: PASS on fresh PostgreSQL, Redis and MinIO volumes.
- Render QC: 30.059 seconds, 1080 x 1920, 30 fps, H.264/AAC, no dark sampled frames.
- Git diff, shell syntax, documentation links and secret-pattern checks: PASS.

## Required E2E assertions

The disposable Docker run must prove a complete V2-04 analysis can create a succeeded V2-05
analysis, structured frames/OCR/quality/tracks are present, all four reframe ratios exist, crop
jumps stay bounded, evidence references point to the immutable source asset, the fixture cost is
zero VND, and the exact response survives API restart from PostgreSQL.

## Boundary

The only tested provider in normal CI is a deterministic fixture. `real_provider_tested=false` is
preserved in provenance and the live provider returns `PROVIDER_NOT_CONFIGURED`. V2-05 is not
approved for production deployment. It does not render crop plans and does not provide an editor
UI. V2-06 Media Intelligence is the next planned implementation increment after owner review and
merge of this PR.
