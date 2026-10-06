# PHASE10 STUDIO UX REMEDIATION REPORT

Task: VF-PHASE10-STUDIO-UX-STANDARDIZATION-02. Status: **TECHNICAL REMEDIATION AND RESPONSIVE VISIBLE-REGION QA VERIFIED; OWNER UAT PENDING**. Report updated 2026-10-06.

HEAD SHA: implementation `84c0da23f970b82c94f589586aefa9e859e7cad6`. The final 79-test run occurred at `51633c1` with the exact frontend working-tree fingerprint below; all 43 current source files still match that tested manifest after the implementation commit. Final evidence/report commits will follow.

Implementation baseline: `95b0a7fa19e26446e2556a055c7b736ae043be39`. Accepted Phase8/9 preservation baseline: `4c4043cb8a6a559aeb9dae598fd0391045626b23`.

Owner reviewed the five new Phase10 candidates and requested changes: missing or incorrect project names, long pauses and excessive video duration after the narration ends. Exact current artifact hashes, render revisions and real reject decisions were recorded through the existing Studio API in [Owner feedback](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/ux-remediation/owner-feedback/20261006T140221734412Z-execution-8e5db73c/owner-request-changes.json). The original five MP4s remain unchanged. Owner separately selected a repaired case 08 format of **9:16, 1080×1920**.

The prior technical Studio verdict is superseded by Owner UAT. This task requires distinct Owner acceptance of both the repaired five videos and the coherent Studio workflow. Phase11 is outside this task.

## Implementation and evidence

| Required field | Current result |
| --- | --- |
| UI ARCHITECTURE | One shared shell, persistent navigation/topbar, PageHeader, common page bounds and tokens across Native, Production, Intelligence and Settings. Capabilities gate optional imports so the old accepted server retains its compatible frontend. |
| SHARED COMPONENTS | Shared shell/tokens, page headers, cards, panels, toolbars, badges, empty/loading/error states and dialog styling; reusable Asset Picker and ratio-aware Video Preview. Original Native and CI controls retain their handlers. |
| ASSETS WORKFLOW | New projects expose an Assets stage immediately, including useful empty state, image/video upload and Library selection. Project association changes are atomic and revision checked. Used assets require replacement before removal. Removal keeps original bytes and immutable history. |
| ASSET PICKER | One module for project/global media, search, image/video filter, pagination, previews and single/multiple selection. Assets and Storyboard consume the same picker. Actual new-project multi-attach/upload/remove and Storyboard picker → explicit SaveShot have persisted evidence below. |
| VERTICAL PREVIEW | Logical ratio derives from the project/template; the final review uses verified rendered dimensions. Portrait uses 9:16 and contained full-frame media, landscape uses 16:9. Historical Final Videos dimensions remain unknown when no verified saved probe exists; no FullHD dimensions are invented. |
| REVIEW MODE | Video-focused review with measured duration/resolution/version/QC, Accept/Request Changes, and collapsible engineering details. Current render and approval guards remain authoritative. Owner decisions must be explicit. |
| RESPONSIVE QA | Required visible screen cells are verified at **1366×768, 1920×1080 and 2560×1440**, with current geometry/hash-bound captures. [Independent matrix](C:/NPD-Video-Factory/source/PHASE10_STUDIO_UI_CONSISTENCY_AUDIT.md) records exact visible/scroll scope and excluded diagnostics. Static pixels do not certify moving media, every optional expansion or Owner usability acceptance. |
| NATIVE TESTS | **255/255 PASS**, zero failures/errors/skips, 157.875s at `cd435328c5c37999a8c639922a89dc734c651e64`. Backend is unchanged since that run. [Exact log/receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/tests/full-native/20261006T144123770634Z/summary.json). |
| STUDIO TESTS | **79/79 PASS**, zero failures/cancellations/skips/todo, 0.429s at `51633c1`, with final 43-file working-tree fingerprint `151c9d2b1dd124e15daa914560c1fd826f098b571da6e9145a60cb276c71ba5d` unchanged before/after testing. [Exact final log/source manifests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/tests/full-studio/20261006T154653648027Z/summary.json). |
| PHASE 8 REGRESSION | Accepted Internal Production state retained; the prior ten accepted MP4s remain unchanged and accessible. |
| PHASE 9 REGRESSION | Accepted Content Intelligence state and its five accepted MP4s retained. The combined audit verified **15/15** exact MP4 hashes, FFprobe, HTTP200/range206, main database rows and runtime locks; **1,596** frozen evidence files unchanged. [Read-only release audit](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/regression/20261006T143512395769Z-0f9e14fd/summary.json). |
| PHASE 10 REGRESSION | Existing canonical/provenance/approval paths covered by the Native and Studio suites; real historical shot/AI evidence remains byte exact, and eight current project states passed the final actual isolated restart comparison. |
| SCREENSHOTS | Current captures are bound in the [pixel inventory](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/screenshots/20261006-actual-ui/pixel-audit.json). Coherent 1366 landscape uses an authentic native JPEG bound to its DOM viewport; 1920/2560 use coherent PNGs. Invalid tiled/blank captures and cropped partial diagnostics remain archived and excluded from PASS. |
| EVIDENCE | Links below bind real UI workflow, restart, historical edit/AI proofs and the five newly repaired renders. Tests use disposable DBs and explicit fixtures; no fixture result represents provider production or human acceptance. |

The former **231 Native / 56 Studio** results are historical Phase10 baseline counts. They are superseded for this remediation by the runs above, whose 255 Native total adds 16 Library tests, seven duration-fit tests and one final-video metadata test. No new credentials, publication, autonomous production, second renderer or distributed orchestration were introduced.

Backend support is additive: Library browse and authenticated file/thumbnail routes derive verified metadata from existing immutable project history. Multi-attach reuses those source bytes and provenance. Optional configured content profiles and explicit duration policy are stored in the existing project document. There is **no new table, DDL or data migration**. Missing optional creation fields preserve legacy document shape. Existing fixed-duration selections remain byte exact; the new fit-narration mode is opt-in and preserves source PCM, speed and pitch. Real provider/source receipts and superseded attempts remain archived.

Progressive implementation commits: `97c0c10` (Owner feedback/gate), `4984abb` (Library and opt-in duration), `cd43532` (raw receipt bytes), `170ef9f` (shared shell) and `0bd1615` (Assets/picker/portrait review). Later `f870a11` preserves frontend refinements and `51633c1` preserves the real repair scripts/six attempts. Backend files: media, asset association, Store, server, production projection and focused tests. Frontend files: shared shell/tokens, Native workspace, Asset Picker, Video Preview, Shot Studio and secondary page integration. Final wording/visual adjustments and this report will be recorded in subsequent commits.

## Actual Assets and restart workflow

The actual UI created media-first project `9563402cf06f4716959db48a067f64fc` with the configured Green Paradise profile and deliberate portrait/fit-narration selection. Immutable history proves **r2 empty → r3 two Library assets → r4 uploaded image → r5 removal leaving two assets**. Independent live reads captured r3 and r5; r2/r4 are history proofs, not claimed live captures. Root separately observed cancelling removal retained r4 before confirming removal.

The new upload's source hash equals the self-authored case01 PNG. All **64** preceding originals stayed byte exact, precisely one original was added, and the removed Library asset remained available. [Actual workflow proof](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/ux-remediation/asset-workflow/20261006T144405745657Z-after-library-remove-b2d1feb0/summary.json). Video upload/thumbnail/range/reuse, multi-selection rollback, rights/max50/stale/busy guards and restart are independently covered by disposable HTTP tests.

A second media-first project, `51d6c011721a4e33b3864060fed59916`, was created through the actual UI at 2560×1440. Root observed correct New Project → project-ID navigation and refresh retaining the empty Assets stage; the [independent persisted read](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/ux-remediation/asset-workflow/20261006T153138838701Z-new-empty-project-read-918faf67/summary.json) verifies r2, zero assets/jobs/approval and portrait format. The helper does not claim screen geometry from that API read.

Only idle isolated Studio **8030** was restarted. Main Studio **8026** was untouched. The [actual after-restart comparison](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/ux-remediation/restart/20261006T150255306764Z-after-restart-c9f0da2c/summary.json) passed **50/50 checks**: five current project/canonical/approval/jobs states, all media hashes and HTTP200/range206, fixture r5 and associations, removed Library metadata, all **65** originals, and every schema/table count/digest across three SQLite databases. At that capture there were **29 projects, zero active jobs and zero current final approvals**; the audit issued GET/read-only SQL only.

The shared Storyboard picker was exercised through the actual UI on separate clone `b458264408134ba28aa9434a0331681b`: first-shot asset replacement and explicit SaveShot moved r1 → r2. The [22/22 comparison](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/ux-remediation/storyboard-picker/comparison-verified.json) verifies stable shot IDs/order, unchanged narration/research, the four other shots, source/derivative hashes and approval guards. No asset was added and no job ran. An earlier verifier compared the wrong envelope/snapshot digest; its failed receipt and the documented checker correction remain preserved.

The [final eight-project restart comparison](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/ux-remediation/final-restart/20261006T154814550755Z-after-final-refresh-1fc59da9/final-refresh-restart-persistence-summary.json) verifies that clone, both Assets fixtures and all five current video projects exactly: document/revision, canonical shots/version, source/derivative bytes, jobs, reviews and history. All five MP4 hashes/statuses and absent final reviews persisted. The bound process receipt verifies main8026 PIDs/creation times unchanged. This 15:48 UTC comparison confirms the later session-recovery restart against the preserved 15:37 UTC eight-project baseline, expanding the earlier six-project/50-check scope without rewriting any receipt.

Actual existing-tab UAT exposed a session recovery defect after restart: Production Refresh reused a stale cookie and reported `LOCAL_SESSION_REQUIRED`. Explicit Refresh now obtains `GET /api/session`, updates CSRF and only then reloads GET data in Production, Native and Intelligence; Settings already follows that sequence. Four actual-module runtime tests simulate rotation, forbid POST replay and verify Native unsaved content survives, with the new CSRF used only by a subsequent explicit Save. The prior 75-test receipt remains historical; the final 79-test run includes this fix. [Actual existing-tab recovery](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/screenshots/20261006-actual-ui/actual-refresh-after-restart-receipt.json) passed after the real 15:47 UTC restart: clicking Làm mới, without browser reload/navigation, restored five VIDEO_REVIEW rows and a clear success message; no reviewer/acknowledgment was submitted.

## Preserved shot and AI capabilities

The [historical proof registry](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/ux-remediation/prior-shot-ai-registry/20261006T150646187348Z/summary.json) verified **114** referenced files from seven existing aggregates without changing them. They prove **13** saves across all five required edit types; three real provider suggestions with explicit applies; case01 undo; eight silent proxy previews with scoped cache reuse; and the prior five-project restart.

“Regenerate visual” in that evidence selects a deterministic alternate existing media candidate; it does not generate AI media. Proxy preview checks do not certify narration quality. Codex preparation and apply records do not establish personal Owner review. Those historical renders were later rejected on audio grounds and their evidence remains intact.

## Five repaired videos and remaining Owner review

Current technical integrity is **5/5 PASS; personal Owner acceptance 0/5**. [Current review bundle](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/video-repair/20261006T145547812042Z-execution-babd7f0f/current-five-review-bundle.md) and [measured summary](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/video-repair/20261006T145547812042Z-execution-babd7f0f/current-five-repaired-video-summary.json) bind these exact artifacts:

| Case | Current job / revision | Actual duration | Actual canvas | Owner |
| --- | --- | --- | --- | --- |
| 01 | `24cc405c95eb4a4a9b3d68b665cbc45e` / r21 | 22.63s | 1080×1920 | PENDING |
| 02 | `6ac1fa1d462746dbab5538979dc47c40` / r20 | 23.88s | 1080×1920 | PENDING |
| 04 | `b1eaffa4c70d4cdca5f38750f6061cc8` / r18 | 22.93s | 1920×1080 | PENDING |
| 06 | `4bbaf04f737249ccb28358467fc050a3` / r16 | 19.93s | 1080×1920 | PENDING |
| 08 | `bb9b5668627c4a8681e23549e92679da` / r19 | 20.61s | 1080×1920 | PENDING |

The original rejected five are preserved. A first repaired case02 was superseded after a material name discrepancy; its actual artifact and costs are retained. Current five attempts used six fresh and 19 reused inferences; all six repair attempts together used eight fresh and 22 reused inferences. The summaries retain actual uploads/transcript creates/observations separately. The final videos end after narration and the configured short outro; no source speech speed/pitch adjustment was used. Case04 retains its deliberate landscape template; case08 follows Owner's new portrait decision.

Automatic transcription remains a diagnostic, with case02 project/location discrepancies explicitly visible in the review bundle. It does not certify pronunciation or replace listening. No new full-video Owner acceptance or publishing occurred.

## Responsive scope and resolved findings

Independent pixel inspection closes the required screen cells at all three viewport sizes. Portrait preview/review show the complete 9:16 frame; landscape retains the full 16:9 frame. The audit closes the verified P2 shot-strip overlap after the shared block-layout fix, including the coherent final 2560 Advanced Timeline PNG. CI alignment, the 1366 picker footer and keyboard focus return were also corrected and verified. Planned durations carry Kế hoạch; unmeasured fit-mode shot timings carry Dự kiến. Actual final duration/resolution remain bound to rendered media.

The [matrix](C:/NPD-Video-Factory/source/PHASE10_STUDIO_UI_CONSISTENCY_AUDIT.md) retains the limits: static visible regions and separate scrolled controls, connected Settings state, some optional pane/modal expansions uninspected, and small inline captions needing fullscreen judgement. Original invalid compositor captures and the cropped native 2560 diagnostic do not count as PASS. No open verified P0/P1 layout fault is reported; human workflow and moving audio/video acceptance remain separate.

## Handoff and gates

PHASE: Phase10 Studio UX and video UAT remediation.

STATUS: Technical implementation, tests, actual persistence, explicit Refresh recovery and required responsive visible regions verified; personal Owner UAT pending.

FILES CHANGED: Shared frontend shell/workspace/picker/preview and additive Native media/profile/duration/projection support, tests, evidence and this report.

TESTS / EVIDENCE: 255 Native, final 79 Studio, earlier 50 restart checks, final eight-project persistence, 22 Storyboard checks, 114 historical proof files and the release/video/workflow receipts linked above.

NEW CAPABILITIES: Coherent navigation/workspace, immediate Assets workflow, reusable Library picker, ratio-aware review, explicit narration-fit duration and deliberate Refresh recovery after restart.

REGRESSIONS: No accepted Phase8/9 artifact/data/runtime regression observed. Original rejected and superseded Phase10 attempts remain preserved.

BLOCKERS: Personal Owner watch/listen acceptance of all five repaired videos and explicit Owner UX acceptance. No technical test, static screenshot or delegated Codex action closes these human gates.

NEXT ACTION: Use the [single Owner UAT entry and ten criteria](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/owner-uat-entry.md): [Production](http://127.0.0.1:8030/production?view=queue) → Project → Script → Assets → Storyboard → Video → Review. Owner checks menu consistency, stable layout, immediate/easy Assets workflow, correct portrait preview/review, discoverable shot actions, clear primary actions, hidden engineering detail and operation without CLI. Do not begin Phase11.

PRODUCTION_INTELLIGENCE_READY = YES

DRAMAGIC_STUDIO_READY = NO

PHASE10_READY = NO

OWNER_UAT_REQUIRED = YES
