# Phase 10 visual QA

Status: **PASS_STATIC required view layout**. All 39 bounded Studio, CI, and production view/resolution cells have coherent inspected pixels at 1366 × 768, 1920 × 1080, and 2560 × 1440. No confirmed P0/P1/P2 CSS or layout defect was found in the usable inspected frames. The refreshed current final-player images are settled at the same paused frame without a loading spinner. There are **no remaining required screenshot gaps**. Optional AI receipt pixels and personal Owner acceptance remain separate.

This is technical static visual QA. Personal Owner acceptance of the campaign, moving video, voice, and publishing quality is **PENDING**. Codex preparation/review labels and automated checks do not establish that acceptance.

## Evidence and method

The browser is controlled exclusively by root. This reviewer read saved files with view_image and inspected metadata; no browser, provider, server, or live-data operation was performed. No product code was edited during this audit.

Evidence is under evidence/post-mvp-roadmap/phase-10/final-uat/screenshots/. The visual-qa-ledger.json binds each capture to its actual bitmap dimensions, SHA-256, bytes, modification time, inspection scope and latest same-named browser geometry when available. Unknown or changed image hashes are not carried forward as inspected evidence.

The reliable current method is supported CDP Page.captureScreenshot, PNG, fromSurface: true, captureBeyondViewport: false, **no clip**. Root checks requested viewport against actual DOM dimensions, allowing the normal scrollbar gutter. New native and studio-final captures use this method. Prior clip-based diagnostic failures remain separate and are never used to pass their intended views.

PASS_STATIC means only the named visible region is coherent and was pixel inspected. It does not certify invisible fields, every optional expansion, keyboard access, action success, audio, or moving-video behavior. Scroll pairs establish the visible lower region separately. The required matrix checks representative actual views at all three sizes; every optional control at every size is not an invented completion condition.

## Required view matrix

| Required visible view | 1366 × 768 | 1920 × 1080 | 2560 × 1440 | Evidence and exact limit |
| --- | --- | --- | --- | --- |
| Studio Video shell, current player layout and native controls | PASS_STATIC | PASS_STATIC | PASS_STATIC | Refreshed studio-{size}-final.png. Header/actions/stages/sidebar/editor fit. Same current 45-second case02 frame is settled with no spinner at all three sizes. |
| Shot strip, selected editor and lower scroll region | PASS_STATIC | PASS_STATIC | PASS_STATIC | shot-strip-1366x768-native.png, shot-strip-1920x1080-native.png, and shot-editor-bottom-{size}-native.png; all five strip cards and separate editor/page scroll regions inspected. |
| Script stage | PASS_STATIC | PASS_STATIC | PASS_STATIC | script-1366x768-native.png, script-new-1920x1080.png, script-2560x1440-native.png; upper entry/request controls. Full review controls also inspected at 1920 in script-review-bottom-new-1920x1080.png. |
| Assets stage | PASS_STATIC | PASS_STATIC | PASS_STATIC | assets-1366x768-native.png, assets-new-1920x1080.png, assets-2560x1440-native.png; upload/rights and contained cards. At 1366 only first thumbnails/names are in frame; all seven cards/tags/removal are visible at 1920/2560. |
| Storyboard stage | PASS_STATIC | PASS_STATIC | PASS_STATIC | storyboard-1366x768-native.png, storyboard-new-1920x1080.png, storyboard-2560x1440-native.png; four cards visible at 1366, all five at larger sizes. |
| CI source/findings | PASS_STATIC | PASS_STATIC | PASS_STATIC | intelligence-findings-1366x768-native.png, intelligence-findings-1920x1080-recapture.png, intelligence-findings-2560x1440-native.png; intended findings/source/date/provenance area and saved-run sidebar. |
| CI ranked ideas | PASS_STATIC | PASS_STATIC | PASS_STATIC | Corresponding intelligence-ideas native/1920-recapture files; first ranked candidate, heuristic/caveat and readable narrative. Lower candidates continue below the smaller frames. |
| CI brief | PASS_STATIC | PASS_STATIC | PASS_STATIC | Corresponding intelligence-brief native/1920-recapture files; objective/audience/angle and truthful Codex preparation/Owner-not-accepted wording. Lower review/preflight are not inferred. |
| Queue summary, filters, batch area and visible campaign cards | PASS_STATIC | PASS_STATIC | PASS_STATIC | queue-1366x768-native.png, queue-campaign-1920x1080-settled.png, queue-2560x1440-native.png; human-input fields and disabled no-selection actions fit. |
| Planning dialog and internal lower scroll | PASS_STATIC | PASS_STATIC | PASS_STATIC | Native 1366/2560 and 1920 top/bottom planning-modal pairs; title/Close, fields/long similarity notice, override/source/priority/reviewer/Open/Save reachability inspected. |
| Calendar grouped cards | PASS_STATIC | PASS_STATIC | PASS_STATIC | calendar-1366x768-native.png, calendar-1920x1080-settled.png, calendar-2560x1440-native.png; actual grouping/cards/source/status metadata. 1366/2560 captures are mid-page; top filters are evidenced separately at 1920 and prior valid 2560. |
| Loaded Library cards and visible actions | PASS_STATIC | PASS_STATIC | PASS_STATIC | library-1366x768-loaded.png shows three complete approved cards and next-row thumbnails; library-1920x1080.png and library-2560x1440-native.png show loaded grid/status/meta/action links. The earlier empty 1366 native frame remains diagnostic. |
| Profiles configuration view | PASS_STATIC | PASS_STATIC | PASS_STATIC | profiles-1366x768-native.png, profiles-1920x1080.png, profiles-2560x1440-native.png; representative configuration cards fit at each size. All five complete cards, including Infrastructure News and its action, are visible at 2560. |

Required view layout coverage is **39/39 bounded cells**. This count does not count diagnostic files, optional states, or personal acceptance.

## Observed layout and usability

- Studio header actions and four stages fit at 1366 without the prior button compression. At 1920/2560, the editor remains a narrow reading/control panel and the preview uses the available main area. Selected editor fields, Save/discard, reorder/duplicate/delete and AI instruction/request controls are visible in coherent scroll states.
- The complete final-review name, acknowledgement, note, approval/return and folder controls are visible in shot-editor-bottom-1920x1080-native.png. Their visibility does not show that anyone approved the final output.
- At 1366, the 9:16 video uses the 250 px preview height, producing approximately 140 px content width with intentional pillarboxing. Native fullscreen and a larger review entry are visible. This supports bounded operability; detailed caption/source text readability at that inline size is **not certified**. Fullscreen/larger viewing and personal watching/listening remain necessary for final content review.
- The 2560 Script column stays near 1160 px instead of stretching paragraphs across the full display. Production caps its column near 1600 px; CI caps near 1530 px. The right margin is deliberate, not missing content. Asset/storyboard media stays contained and card labels/controls stay separate.
- Current final-player records bind the same case02 project (206a81364b2e5d0d98fa0cfdf2b5bedb), v15, to all three exact-size PNGs. The document content widths account for the 15 px vertical scrollbar gutter, with no horizontal page overflow. Fresh captures without same-named geometry are checked from their actual pixels; older bounds are not substituted.
- The planning dialog has coherent internal scrolling at all three sizes. Expanded long source/priority content and bottom Save/Open remain reachable in the paired states. A naturally scrolled-away title is not a clipping defect.
- library-video-modal-2560x1440-native.png actually shows an **inline player expansion**, not a modal. Its contained native controls/fullscreen and grid growth are coherent; the visible spinner makes settled playback content pending.
- advanced-timeline-1366x768-native.png shows the current canonical snapshot Shots row and its local horizontal scrollbar. It does not certify every optional legacy clip action merely from one visible row.

| Current final capture | Bitmap / viewport | Main bounds and width | Editor bounds and width | Document scroll width |
| --- | --- | --- | --- | --- |
| studio-1366x768-final.png | 1366 × 768 | x 202..1351; width 1149 | x 1023..1329; width 306 | 1351 |
| studio-1920x1080-final.png | 1920 × 1080 | x 216..1905; width 1689 | x 1500..1865; width 365 | 1905 |
| studio-2560x1440-final.png | 2560 × 1440 | x 216..2545; width 2329 | x 2095..2495; width 400 | 2545 |

## Shot edits and supplemental states

Eight actual 1920 before/after edit images were independently inspected:

| Edit | Visible result |
| --- | --- |
| Case01 source replacement | Alternative source selected with Save/dirty guards; saved cream source and first thumbnail replace the green source. Timeline v1 and stale-preview label appear. |
| Case02 duration | 7.5 → 9.5 seconds visible in saved input/selected strip/badge; Timeline v1 and stale-preview label. |
| Case04 reorder | Selected source remains the same, selected third item moves to fourth and neighbor order changes; editor title Shot 3 → Shot 4. |
| Case08 source proposal | Existing-library source scene01 → scene05, preview/first thumbnail change. Help truthfully states another existing source is selected and no AI image/video is created. |

Saved comparison receipts for these four edits and three AI applies provide separate technical state evidence: stable project/shot IDs, expected field/order changes, invalidated approval/preview, and no human acceptance created. Their paths/hashes/revisions are recorded in the JSON ledger. They do not replace missing receipt pixels.

The original three ai-edit-case*-proposal.png images show request inputs or existing-source history, but **not** the lower suggestion receipt/rationale/scope/Apply. Their intended-receipt result remains PENDING. This optional lower-state evidence does not block the required three-resolution technical layout result.

The new voice-policy-apply-current-1920x1080.png closes voice control visibility: the Giọng B dropdown matches the explicit current policy text, Apply is visible and correctly disabled for the unchanged choice, and scope/help truthfully describes explicit whole-project save without creating voice/video. Expanded crop/motion/transition/narration controls also fit. Earlier before/applied images alone did not show Apply; this new still state proves visibility/current-policy wording, not the previous apply operation or listening acceptance.

ai-edit-history-controls-1920x1080.png additionally shows open selected-shot history: the existing-library source-proposal action and truthful no-AI-generation help, restore revision field and scoped “Khôi phục shot này” button all fit. AI instruction/request and the complete final-review form remain visible beside that pane. No suggestion receipt is present in this state; no history/restore/approval operation is inferred from static controls.

Opened source/history/music, every remaining candidate/legacy action, keyboard focus behavior, and full-screen playback are outside this static report unless separately recorded. These bounds are disclosed without making every optional state at every resolution a new requirement.

## Capture diagnostics retained

1. Original intelligence-ideas-2560x1440.png and intelligence-brief-2560x1440.png are byte-identical (SHA-256 1da1df0b1a396c1ed4506849b88ef073490d53aa063e9f78fb64ce461c6d7b88) despite different recorded scroll positions; they show the wrong intended section. The original findings frame also shows the wrong section.
2. Original intelligence-{findings,ideas,brief}-1920x1080.png are actually 2560 × 1440 and share that stale hash. They never pass 1920 coverage. Corrected 1920 recaptures and the new native 1366/2560 captures now provide independently inspected intended-section evidence.
3. 2560-fresh-tab-raw.jpg is actually 2545 × 1354 and remains diagnostic.
4. Initial blank clipped 1366 asset/storyboard/video files with hash 7e2cb9410ec8562437c8bf7af81ebfe678786ad6e934eb7e34457deac5427a55 do not pass their intended views. Correct no-clip native captures supersede their intended coverage while preserving the diagnostic files.

Root identified an old helper closing over a previous 2560 size and clip y = 0 despite page scroll. The correct no-clip viewport method avoids that mismatch. No product severity is inferred from capture artifacts.

## Sign-off and optional evidence bounds

- Open selected-shot history/restore and voice-quality Apply/current-policy controls are now independently visible at 1920. An actual AI suggestion receipt remains an optional bounded state, not a missing required screenshot.
- Personal Owner watching/listening/campaign acceptance, kept separate from technical QA.

Root sought the current case02 player to approximately 0.45 seconds, paused, with readyState 4 and recaptured all three exact-size final frames. The reviewer then independently inspected the new file hashes and clean pixels. The player still displays 0:00 / 0:45 because its timer rounds the subsecond position. A single settled paused frame does not certify the complete moving video or its audio.

P0 means catastrophic confirmed unusability; P1 means a primary control/content is inaccessible or materially obscured/misleading; P2 means a confirmed local readability/overlap/overflow issue with a workaround. **No confirmed P0/P1/P2 product layout defect** is established by the usable inspected pixels. No product code change is proposed from the diagnostic capture faults.

Frontend regression: **56/56 PASS**, zero failures/skips/cancellations, npm test exit 0. Runner duration 278.0978 ms; measured process wall time 824 ms. Saved log: evidence/post-mvp-roadmap/phase-10/final-uat/regression/studio-frontend-tests.log; SHA-256 5ab28c106595f7b5b54265ab6b4f81fed03551394af54e7940f28b534e952e77. This meaningful frontend suite ran once during the audit; report/metadata edits do not justify rerunning unchanged code.
