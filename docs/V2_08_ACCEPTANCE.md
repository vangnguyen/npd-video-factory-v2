# V2-08 acceptance — Audio, Subtitle, Render and QC

## Scope and gate

V2-08 delivers TTS, dynamic subtitles, licensed-music mixing/ducking, human review and approval,
production-profile rendering and full QC. It does not deliver publishing or authorize production
deployment.

Acceptance is valid only on the final PR head when every `Video Factory V2 CI` job is green. CI
success is not authorization to merge or deploy; those remain separate owner decisions.

## Required automated gates

1. Python compile for API, worker and optional ComfyUI bridge.
2. API/worker/bridge unit and contract tests.
3. Alembic upgrade -> downgrade base -> upgrade replay through `0007_v2_08`.
4. Renderer unit/contract tests, TypeScript check and Remotion bundle check.
5. Studio JavaScript syntax and utility/interaction tests.
6. Compose/safety/secret checks.
7. Docker deterministic E2E from V2-01 through V2-08.
8. `git diff --check` and no committed runtime secrets or acceptance media.

## Local verification on the implementation branch

The pre-PR verification on `feat/v2-08-audio-subtitle-render-qc` completed with:

- Python API/worker/bridge: **107 passed**;
- renderer: **14 passed**, TypeScript check and Remotion bundle check passed;
- Studio: **9 passed** and JavaScript syntax check passed;
- Alembic upgrade -> downgrade base -> upgrade head passed;
- Docker deterministic E2E through V2-08 passed, including review/full-QC, owner approval,
  final 1080x1920 render, PostgreSQL recovery and MinIO artifact recovery;
- responsive browser QA passed at desktop and 390 px mobile width with no horizontal overflow,
  all three subtitle cues present and no publish button exposed.

These are local implementation-head results. GitHub CI on the final pushed PR head remains the
authoritative automated gate.

## Required V2-08 assertions

| Area | Acceptance evidence |
|---|---|
| Version binding | Package, subtitles and audio point to one exact timeline version |
| Concurrency | Stale expected versions return HTTP 409 and do not mutate state |
| Subtitle editor | Cue/word timing, Vietnamese text, safe area and style validate |
| Audio | Per-cue narration is audible; output mix is stereo 48 kHz |
| Music | Only an audio asset with explicit usable rights may enter the mix |
| Review | 540x960 H.264/AAC job reaches `awaiting_review` after full QC |
| Negative approval gate | Final render before approval returns HTTP 409 |
| Owner decision | Approval binds review/timeline/subtitle/audio versions |
| Final render | 1080x1920 H.264/AAC/48 kHz job reaches `ready` after full QC |
| Invalidation | Timeline/subtitle/audio changes invalidate prior approval and renders |
| Recovery | Package, approval, render and audit records are equal after API restart |
| Worker recovery | Queued/processing render IDs are deterministically requeued from PostgreSQL |
| Cost | Provider operations use VND only; offline eSpeak/Remotion record zero VND |
| Safety | Every review/final response and manifest keeps publishing/external action false |

## Docker E2E evidence bundle

The Docker acceptance script creates copyright-safe fixtures and persists, among other evidence:

- `production-package-before-restart.json` and `production-package-after-restart.json`;
- `review-render-ready.json`, `review-render.mp4` and `review-render-probe.json`;
- `approval-approved.json` and the rejected `final-without-approval.json`;
- `final-render-ready.json`, `final-render-v2-08.mp4` and `final-render-probe.json`;
- production history before/after restart;
- Compose logs and all earlier V2 acceptance artifacts.

GitHub uploads the secret-free bundle as `v2-08-audio-subtitle-render-qc-e2e` for seven days.

## Human UI and media acceptance

Before calling a future production rollout accepted, a non-developer must be able to:

1. open the Production Workbench in Auto Edit Studio;
2. edit subtitle text/style and save a new immutable version;
3. configure narration and optional licensed music without exposing credentials;
4. render and play a review artifact;
5. see the exact timeline/subtitle/audio versions being approved;
6. approve, request changes or reject with an auditable comment;
7. render a chosen final profile and understand the QC result;
8. verify that no publish action exists.

Automated audio checks do not replace human Vietnamese listening. eSpeak output is test evidence
only. A real production voice requires separate owner-approved provider configuration, cost review,
consent where applicable and human listening acceptance.

## Explicit non-acceptance

- no production deploy;
- no public API exposure;
- no authentication/RBAC claim;
- no social/video-platform publication;
- no external/paid provider enabled by CI;
- no voice cloning;
- no production-quality claim for deterministic fixture media or eSpeak.
