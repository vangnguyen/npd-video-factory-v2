# Phase 10 — Studio gap analysis

Baseline: `4c4043cb8a6a559aeb9dae598fd0391045626b23`, branch `codex/vf-post-mvp-roadmap-execution-01`, clean checkout before work. Phase 8 INTERNAL_PRODUCTION_READY and Phase 9 CONTENT_INTELLIGENCE_READY remain YES. This audit does not reopen their acceptance.

The certified Windows app is the loopback Native service on port 8026 and `native.html/native.mjs/native.css`. The separate Docker Studio has an advanced track editor; it is not the accepted Windows runtime and must not become a new dependency. The current Native screen was inspected on the accepted Phase 9 case 04 without editing it.

## Observed gaps and implementation order

| Area | Existing capability | Phase 10 addition |
|---|---|---|
| Navigation | Long page containing request, sources, scene forms, approvals and output | Four Script / Assets / Storyboard / Video stages; compact sidebar; existing controls retained |
| Preview | Small output column; current approved render only | Large portrait canvas, selected-shot media preview, version-bound proxy status and explicit final render |
| Shots | Up to five numbered scene forms, source/crop/motion/trim/transition | Stable shot identity, strip, selected-shot editor, reorder/duplicate/delete/revert, explicit regeneration |
| Canonical editing | Persisted Native proposal/media/edit_plan; render projects these through the existing TimelineSnapshot 1.1 DTO into immutable job/timeline.json | Add an opt-in adapter in the same Native Store and document transaction. Reuse existing timeline DTOs, atomically derive proposal/media/plan, validate projection before render. No separate editing database, Redis runtime, independent UI timeline or mutable accepted job artifacts |
| Timing | Text estimates in editor; final cuts use measured voice | Explicit requested duration consumed by renderer; reject narration overflow rather than truncate or change voice speed |
| AI Edit | Whole-script generation and deterministic media proposal | Reviewable scope-specific edit suggestions using existing provider; explicit apply, no automatic TTS/render |
| Script | Editable scene narration, source notes, history, production review | Focused script screen and script-only approval; expandable brief/lineage |
| Assets | Real uploads, originals, rights, provenance and analysis | Used/unused, tags, remove association while preserving originals, selected-shot replacement |
| Queue | Phase 9 Opportunity states and explicit approved-brief handoff | Derived unified production stages; separate additive planning metadata. Preserve Phase 9 statuses/decisions |
| Planning | No calendar/campaign/assignee | Local campaign/date/priority planning, no publishing |
| Profiles/brands | Four content profiles; NPD/Vang brands; portrait 30/45/60 templates | Infrastructure profile and configurable production defaults; additive landscape templates with renderer support |
| Source intelligence | Publication and retrieval timestamps retained separately | Visible unknown publication, stale/revalidate badges, transparent similarity warnings and configured heuristic priority |
| Batch | One brief/script job at a time | Explicit multi-select script/storyboard actions; keep script/media/video human gates |
| Library | Per-project final download with exact artifact approval | Approved final video library with full source-to-render lineage and version details |
| Verification | 159 Native and 32 Studio baseline tests; preserved accepted evidence | Adapter/failure/persistence/proxy/queue tests, screenshots at 1366/1920/2560, actual local render checks and human campaign UAT |

## Integrity rules

Existing projects open read-only through derived adapters until an explicit edit enables the new format. GET must not migrate an accepted project. Project revision is the concurrency boundary; a successful shot edit increments the timeline version and project revision in one transaction, invalidates current preview/production approval and appends history. UI selection and drafts are transient; saved edits use only the backend canonical state. Reorder moves narration, media and shot properties together. A narration edit or changed warm-context adjacency invalidates the affected voice dependencies; asset-only edits retain reusable voice. Render checks canonical projection equality. Immutable prior videos, approvals, timelines and research receipts are preserved.

The advanced view will expose the same canonical tracks and scoped controls in Native; the Docker editor remains available in its original environment. No claim that its independent project storage is the Native canonical timeline.

## Acceptance boundary

Technical verification and simulated fixtures are not human campaign acceptance. Phase 10 remains NO until a real campaign includes at least ten selected ideas, at least five production selections, explicit script/media gates, actual previews/final renders and Owner-performed asset/narration/duration/reorder/regeneration actions. Existing Phase 8/9 acceptance is preserved independently.

## UX reference

BytePlus describes an editable script → assets → storyboard → preview workflow in its [official Dramagic product introduction](https://docs.byteplus.com/de/docs/Dramagic/ProductIntroduction). That workflow is inspiration only. No BytePlus branding, artwork, multi-agent runtime or proprietary assets are copied. The implementation will use NPD's own neutral Studio surfaces and existing licensed/local assets.

## Next action

Capture consistent SQLite backups, historical evidence/media hashes and actual baseline test results, then implement the shot adapter, Studio shell and production intelligence contracts in parallel. No destructive migration, new credential, new paid provider or publishing is required for these additions.
