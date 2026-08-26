# V2-01 migration audit

## Audited baselines

| Source | State audited | Exact SHA | Disposition |
|---|---|---:|---|
| `vangnguyen/npd-ai-video-factory` | `main` | `02c31be4729bf19f150791ee623dfb25d957ada7` | Read-only baseline; unchanged |
| Legacy PR #8 | Closed head | `d1da6ad37091df3b6854adfec46d9193c1dca61f` | Do not merge; use only reviewed value |
| Clean-port PR #34 | Open head derived from PR #8 | `a156dcdd5e1f013e3b0799a608b5339dfa752630` | Selected parity source |
| Legacy PR #6 | Closed head | `48cc333b9c178e333bd8f0e922d59238532c6056` | Do not merge; use only reviewed value |
| Clean-port PR #35 | Open stacked head derived from PR #6 | `24edafa83cf425eeac89129ad700fe72b5a8f556` | Selected production-pilot source |

The extracted files use the clean-port snapshot at `24edafa...`, which contains the
reviewed PR #34 parity work plus PR #35 production-pilot work. The source baseline is
recorded by immutable SHA; no source tag or source-repository mutation was necessary.

## Component inventory

Classification values are `KEEP`, `PORT`, `REWRITE`, `DEPRECATE`, and `DROP`.

| Component | Source path / provenance | Decision | V2 destination | Reason |
|---|---|---|---|---|
| Video API | `apps/api/` at `24edafa...`, PR #34/#35 | PORT + REWRITE | `apps/api/` | Preserve idempotent jobs/artifact safety; rename product and add niche/profile boundary |
| Video worker | `services/worker/` at `24edafa...`, PR #34/#35 | PORT | `services/worker/` | Preserve resumability, bounded renderer retry, stable errors, TTS timing and QC |
| AgentHub | `services/agent_hub/` on source `main` | DROP | none | Control plane is outside the V2 media plane; no import/runtime/state dependency allowed |
| Renderer | `renderer/` at `24edafa...`, PR #34/#35 | PORT + REWRITE | `renderer/` | Preserve tested Remotion render path; generic `VerticalShort` is core and real estate is an adapter ID |
| Video contracts | `packages/contracts/` at `24edafa...` | PORT + REWRITE | `packages/contracts/` | Preserve strict manifest; add explicit niche and generic template ID |
| n8n smoke | `workflows/n8n/sprint-1-smoke-test.json` at `24edafa...` | PORT | same path | Keep inactive deterministic smoke only; no production import or activation |
| Examples | `examples/` at `24edafa...` | PORT + REWRITE | `examples/` | Keep real-estate parity fixture and add non-real-estate contract fixture |
| Storage layout | `storage/assets`, `storage/jobs` | KEEP (layout only) | same paths | Runtime files remain ignored; no old Redis/job/media data migrated |
| Docker Compose | root Compose at `24edafa...` | REWRITE | `docker-compose.yml` | Remove AgentHub; V2 owns its Redis/project/network namespace and localhost binds |
| GitHub Actions | source `.github/workflows/api-ci.yml` | REWRITE | `.github/workflows/ci.yml` | Valid independent triggers, unit/renderer/safety/Docker E2E, no paid calls |
| Redis job state | source DB 0/job keys | DEPRECATE | fresh V2-owned Redis volume | No cross-repo state migration or shared Redis; old state stays untouched |
| Video manifest | source schema and builder | PORT + REWRITE | schema, Python builder, TS contract | Dynamic brand and niche fields; strict Python/TS parity |
| TTS providers | API providers + worker at PR #35 | PORT | same service packages | Keep eSpeak CI and mocked OpenAI adapter; real provider remains manual and gated |
| Remotion composition | PR #34/#35 renderer | PORT + REWRITE | `VerticalShort.tsx` + legacy adapter | Remove real-estate naming from core without breaking prior manifest ID |
| FFmpeg/FFprobe QC | PR #34/#35 worker | PORT | worker pipeline | Retain decoded luminance/audio checks and output metadata verification |
| Asset resolver | source `apps/api/app/assets.py` | PORT | same path | Retain root containment, extension allowlist and deterministic scene assignment |
| Subtitle timing | PR #34/#35 pipeline | PORT | worker pipeline | Retain measured per-scene voice timing and monotonic subtitle cues |
| Production pilot | PR #35 scripts/preflight | PORT + REWRITE | `scripts/`, worker preflight | Keep strict opt-in asset/TTS smoke; no production execution in V2-01 |
| Marketing/Campaign/CRM logic | AgentHub source modules | DROP | none | Explicitly belongs to AgentHub control plane |

## PR #8 value retained

- strict API/renderer contracts and stable error envelopes;
- visible copyright-safe E2E fixtures;
- renderer unit/contract tests;
- black-frame and silent-audio rejection;
- idempotency, resumability and worker recovery;
- deterministic Docker E2E artifacts.

## PR #6 value retained

- OpenAI TTS adapter with mocked, zero-cost CI tests;
- offline eSpeak adapter for deterministic CI;
- asset/logo preflight and strict pilot mode;
- scene-aligned narration and measured subtitle cues;
- Vietnamese font/render support and motion/pacing improvements;
- manual provider smoke that requires explicit authorization.

## Intentionally not migrated

- AgentHub code, dashboards, provider-health, Campaign OS, attribution and CRM logic;
- production credentials, tokens, media, Redis state or audit data;
- production n8n activation or Caddy configuration;
- old divergent Git history.

Legacy video code remains in the source repository until V2 parity is owner-accepted.
Human Vietnamese voice listening remains a separate acceptance gate before any production
pilot; automated waveform/QC checks do not replace it.
