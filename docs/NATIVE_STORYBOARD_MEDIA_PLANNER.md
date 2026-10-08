# Native storyboard Media Planner

Authority: Master Spec section 35 and completion-program Wave 6A. This is a versioned Mode A consumer over the existing Native project, Proposal, canonical shot adapter, registered assets, provider catalogs and cost records. It does not invent an uploaded-footage analysis ID or introduce another timeline/database.

## Saved decisions

`studio_media_plans` is append-only inside the existing immutable Native project versions. Each record holds a strict `native-storyboard-media-plan-v1`, canonical SHA256, project/workspace identity, plan version and input/options fingerprint. Inputs include the actual script and storyboard, canonical timeline digest/version, configured niche/channel/brand, canvas, physically hash-checked project assets, raw rights/attributed upload attestation/current scoped Owner exceptions, saved pixel observations, protected provider configuration and recorded budget exposure. Missing semantic Vision confidence and generation price stay null.

Each shot records visual/narration/title, draft duration, target media aspect, strategy, fallbacks, search query, editable prompt, ranked project candidates, selection/hash, attention/approval and decision basis. Rankings use saved filename/description/tags with measured, uncalibrated pixel quality as a tie-break. They do not claim image semantics, saliency, subject tracking or a model seeing pixels. Duration remains subject to the certified measured-voice fit path.

Provider catalogs are inspected without network calls. Pexels/Pixabay and eight ComfyUI operations retain their default-off protected configuration. Existing uploaded/internal/stock/generated assets preserve source and rights evidence. Unknown/restricted/ineligible assets cannot become selected solely because they exist in the library; a current Owner exception is evaluated through the established scoped exception boundary. An upload attestation is explicitly attributed and is not independent legal verification. Publishing gates remain independent.

## Human workflow and canonical apply

The Assets stage includes “Kế hoạch tư liệu theo shot” for storyboard projects. Read the plan, choose the platform/media ratio, create a versioned plan, edit a query/strategy/prompt, select project media, view its local file and acknowledge applying one shot. The media ratio is a planning preference; the actual render canvas remains the project template. Source-footage projects retain their existing B-roll workflow.

Creating/revising/selecting a plan leaves canonical editing unchanged. Explicit apply uses the existing shot adapter's validation/projection/clip builder in one SQLite transaction, saves the same `TimelineSnapshot` consumed by shots, preview and final production, records affected-shot scope, clears approval and creates an immutable project/plan version. Narration, subtitles, duration, other shots and source bytes remain intact. No render/provider job is queued. Plan input includes the resulting source state, so subsequent edits require a fresh plan. A duplicate project carries only origin history digest and must create a new scoped plan.

Stock/generation operations are requested separately through the existing Assets workers and their explicit consent, current project/source/configuration, cost, idempotency, rights, actual decoding and import gates. This increment does not execute an automatic end-to-end resolver or assign a provider result to the timeline. An imported asset changes inputs and requires a fresh plan. Unknown generation pricing grants no payment authority.

## Finite-budget planning policy

Algorithm `native-storyboard-media-planner-v2` mirrors the existing cost ledger: a missing generation estimate cannot fit a finite project budget, including zero and positive limits. Such new AI image/video choices are deferred while the configured resolver order continues through eligible existing assets or configured stock. Reusing registered AI media with valid attributed rights requires no new generation operation. Unknown/restricted/ineligible media remains unavailable for automatic selection. If no feasible fallback exists, the planned AI choice keeps its null price, `requires_approval` and attention; no job/payment is dispatched. The UI identifies generation strategies blocked by unknown price. An unset budget is not an estimate or a grant of provider/payment authority.

Version 1 plans remain exact hashed, read-only history. Reads return their original JSON without new model defaults; prior records, applied edits and artifacts are not rewritten. A new version 2 plan must be explicitly created before current-policy changes/apply. Fingerprints use each saved plan's actual algorithm version. No data migration occurs.

The optional `--budget-provider-fixture` rehearsal flag is confined to fresh owned fixture roots. It supplies a configured mock catalog whose transport forbids every request, and saves a zero budget through actual Owner-fixture HTTP. Two configured niches choose real project media, produce local visual previews and restore exactly with zero provider/paid calls. This is not a genuine enabled GPU/provider account or a verified license. The registered-AI reuse and stock-catalog unit cases also use explicit mock rights/catalog assertions.

## HTTP and bounds

- `GET /api/projects/{id}/media-plans`: scoped read, current input, latest plans and stale/applied markers.
- `POST /api/projects/{id}/media-plans`: current project revision and canonical timeline version, strict planning options.
- `POST /api/projects/{id}/media-plans/{plan}/select|revise|apply`: current revision, exact latest plan version/SHA; selection also checks asset SHA; apply requires explicit acknowledgment and unique shot IDs.

Owner/editor may write; reviewer/viewer may read. Existing human session/CSRF/origin/loopback checks run before forbidden bodies. A service bearer cannot replace a human session. Clients cannot supply provider results, graph, endpoint, token, billing price or publishing authority. Reads and writes are no-store. Plans are limited to 20 shots, 50 candidates per shot, 1 MiB per plan, 100 saved versions and 16 MiB total plan history. Native backups already preserve projects, immutable versions, assets and preview files.

## Evidence and acceptance limits

`scripts/north_star_native_studio_media_planner.py` creates fresh owned fixture roots and two configured niches through real human HTTP. The script deliberately writes fixture narration/storyboards and synthetic owned PNG files; it does not call research/LLM/TTS/stock/generation providers. It verifies real upload normalization/physical hashes, saved fingerprints, deduplication, selection without timeline changes, explicit canonical apply, stale replay refusal and actual FFmpeg 540×960 visual proxies. Both three-second proxies include Vietnamese captions; source hashes remain unchanged. Separate-process exact project/version/event/asset/preview/cost replay and actual backup/restore pass.

The authoritative index is `docs/north-star/native-studio-media-plan-evidence.json`; exported evidence, logs, preview MP4/frame, plan/timeline/project/script/provenance and recovery records remain in the external recovery directory. Failed rehearsal roots/logs are retained. These are silent visual proxies and cannot establish final approval, measured spoken TTS, final-render QC, genuine provider/legal/billing acceptance, browser viewport usability or Owner UAT. Full Mode A/B, automatic resolution, semantic Vision/tracking, research and personalized feedback, publishing/analytics and production acceptance remain applicable original work. No main merge, new paid call, external publication, live migration or deployment occurred.
