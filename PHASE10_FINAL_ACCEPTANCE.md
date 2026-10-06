# Phase 10 final UAT — awaiting Owner watch/listen decisions

All required technical campaign, shot-edit, persistence, visual and regression checks have passed. Five new real NPD campaign videos are ready for personal review. None is counted as human accepted. Final Phase 10 certification remains **NO** until five explicit current-video decisions are ACCEPTED.

Baseline implementation: `82578d84dd762ccf6d6594f5d59bcde04d9907f6`. Implementation and final regression verification HEAD: `9772e146da727152d816f3fe757c6bbb7e1488f8`. Evidence/report commits follow this implementation commit; their exact identifiers are recorded in Git history and the final task response. No certified history or Phase 8/9 evidence was rewritten.

## Final verdict at the human review boundary

```text
PHASE10 FINAL VERDICT
HEAD SHA: 9772e146da727152d816f3fe757c6bbb7e1488f8 (verified implementation)
NATIVE TESTS: 231/231 PASS
STUDIO TESTS: 56/56 PASS

REAL IDEAS: 10 campaign selections from 50 retained real provider candidates
SELECTED FOR PRODUCTION: 5 — 01, 02, 04, 06, 08
NEW VIDEOS PRODUCED: 5 valid current MP4s
NEW VIDEOS ACCEPTED: 0 — Owner decisions PENDING

REPLACE ASSET: PASS
NARRATION EDIT: PASS
DURATION EDIT: PASS
REORDER: PASS
REGENERATE: PASS — selected existing-library source
AI EDIT: PASS — 3 actual proposals and explicit saved applies; undo verified
TIMELINE INTEGRITY: PASS — 13 saved operations; all five final projects reload exactly

1366 VISUAL QA: PASS
1920 VISUAL QA: PASS
2560 VISUAL QA: PASS

PHASE 8 REGRESSION: PASS
PHASE 9 REGRESSION: PASS

PRODUCTION_INTELLIGENCE_READY = YES
DRAMAGIC_STUDIO_READY = YES
PHASE10_READY = NO

BLOCKERS: five explicit Owner watch/listen decisions for these current videos
P0: none unresolved
P1: none unresolved
P2: no confirmed visual defect; bounded limitations documented below
```

## Current five productions

| Case | Title | Render revision | Canonical timeline | Duration | Dimensions | Human decision |
| --- | --- | --- | --- | ---: | --- | --- |
| 01 | Lời kỳ vọng hay dữ kiện? | r18 | v4 | 45.0 s | 1080 × 1920 | PENDING |
| 02 | Khởi động chưa phải đã đạt | r15 | v2 | 45.0 s | 1080 × 1920 | PENDING |
| 04 | Con số sự kiện nói lên điều gì? | r15 | v2 | 45.0 s | 1920 × 1080 | PENDING |
| 06 | Đọc tin bất động sản theo thời điểm | r14 | v1 | 45.0 s | 1080 × 1920 | PENDING |
| 08 | Bài đăng tháng 8 nói gì về quý II? | r17 | v4 | 60.0 s | 1920 × 1080 | PENDING |

[Open the five-video review bundle](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/videos/owner-review-bundle.md). It includes local MP4 copies, Studio links, full current narration, source dates, lineage, job/revision identifiers and exact hashes. [Current decision manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/videos/owner-review-current-manifest.json) explicitly leaves reviewer, personal decision and acceptance timestamp pending. Historical Phase 8/9 approvals and Codex preparation decisions are excluded from this count.

Actual ffprobe, H.264/AAC, dimensions, measured audio/video durations, artifact hashes, full source PCM checks, manifests, script/brief/research lineage and current project revision bindings passed for all five. [Five-video technical aggregation](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/videos/20261006T130319361436Z-execution-90231700/five-current-video-technical-verification.json) binds the individual byte-exact verification receipts. Output copies remain locally preserved with committed hash/manifest evidence; MP4/WAV files retain the repository's existing media-ignore convention.

[Committed-byte verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/regression/git-evidence-byte-integrity-repaired.json) passes for all 2,522 UAT evidence files tracked at its verification commit. An earlier probe found Git newline normalization in two test logs; that failed receipt is preserved, and the raw UAT files were reindexed under the exact-byte attributes before this complete passing check. Project data and MP4 files were not changed by this correction.

The last actual isolated Studio restart preserves all five final documents, canonical versions, stable IDs, history, approvals and jobs exactly. All five current MP4s remain authenticated HTTP 200 accessible with matching full hashes and HTTP 206 range bytes. Queue state persists as **VIDEO_REVIEW** for five items and **PRODUCED** for zero new items. [Final restart receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/shot-edits/restart-persistence-v2.json) records this separation.

All five current silent visual previews are now **READY**, with 25/25 shots complete and the current canonical timeline versions bound. [Current preview readiness](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/shot-edits/20261006T132831306687Z-execution-db758381/current-five-visual-previews-ready.json) verifies their actual bytes and unchanged final MP4s, project documents, production approvals and VIDEO_REVIEW state. Four stale previews were refreshed through the existing preview API; case 02 was already ready. The latest preview metadata records 20 cached and five new proxy shots across the five records, not five new shots generated by this last batch. These silent proxies use no provider or TTS calls and do not establish personal audio acceptance.

## Campaign and editing proof

[Real campaign report](C:/NPD-Video-Factory/source/PHASE10_REAL_CAMPAIGN_UAT.md) records ten source-aware case selections, profiles, published/retrieval dates, heuristic components, priority, similarity results, five new actual provider script calls and API-only handoff. Research was explicitly forked from real saved Phase 9 sources and provider-derived candidates; zero new retrieval calls were falsely presented as fresh research. Five new current renders use the existing production pipeline, original sourced editorial graphics and locked Thùy Dung Giọng B. Old accepted videos and synthetic technical clones do not count.

[Shot edit report](C:/NPD-Video-Factory/source/PHASE10_SHOT_EDIT_ACCEPTANCE.md) and [13-operation matrix](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/shot-edits/action-matrix-v4.json) bind before/after versions, affected stable shot IDs, invalidations, preserved assets and actual preview results. Replace, narration, duration, reorder and selected-source regeneration use the canonical timeline. Three real AI commands produced explainable mutations, were explicitly applied and persisted; the heading undo restores content while retaining its replacement asset. [AI proof index](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/ai-edit/acceptance-index.json) links the original provider responses and applied event bindings.

Case 02's requested first-shot duration is actually 9.000 seconds in the exported clip and measured narration timeline, with the next shot starting at 9.000 seconds. Its 46.5-second text-estimated draft becomes a 45-second measured export; the override is not ignored. Narration repair in case 06 regenerates only scenes 4–5 and reuses three identical source waves. Case 08 regenerates only its final narration source and reuses the first four. No edit silently regenerates the whole project.

Script/media execution decisions have the explicit **Codex delegated task preparation** actor. They are not Owner personally reading, watching or listening. The current task authorized preparation through render and explicitly directed stopping only for Owner watch/listen decisions. No personal acceptance is fabricated from generic backend event names, test results or prior approvals.

## Visual and regression proof

[Visual QA report](C:/NPD-Video-Factory/source/PHASE10_VISUAL_QA.md) and [pixel inspection ledger](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/visual-qa-ledger.json) cover 39/39 bounded required static view checks at 1366 × 768, 1920 × 1080 and 2560 × 1440. Current rendered frames, sidebar/header, Script → Assets → Storyboard → Video navigation, shot strip, right editor, scroll states, optional advanced timeline, queue, Content Intelligence, library, calendar, profiles and planning dialogs have actual usable captures. Final player frames are settled, not loading placeholders. Failed early capture diagnostics are excluded from PASS.

- [1366 final capture](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/screenshots/studio-1366x768-final.png)
- [1920 final capture](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/screenshots/studio-1920x1080-final.png)
- [2560 final capture](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/screenshots/studio-2560x1440-final.png)

The shot workflow was demonstrated through real saved edits and previews, not certified from CSS similarity alone. Detailed text in a portrait video requires the visible native fullscreen control on a smaller display. Optional unshown expansions and complete moving-video/audio quality are outside static pixel inspection; they do not substitute for the pending personal review.

[Native regression](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/tests/20261006T124519873582Z-native-boundary-suite-6d026ab4/summary.json): 231/231 PASS, exit 0. [Studio regression](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/regression/studio-frontend-tests.log): 56/56 PASS, exit 0. Provider-backed production receipts remain separately classified from these automated tests.

[Final Phase 8/9 regression receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/regression/20261006T131021369209Z-phase8-9-final-readiness-1d213266/phase8-9-final-regression-readiness.json) verifies 1,596 frozen evidence files, fifteen old accepted MP4 hashes/accessibility/ffprobe, both live database table digests and locked runtime/dependencies. The accepted main service on 8026 and original data were preserved; restarts affected only the isolated UAT service on 8030.

## Minimal UAT corrections and limitations

The only runtime corrections expose existing certified voice choices and resolve a measured quiet interval containing the native target onset when multiple nearby quiet intervals were falsely ambiguous. The 60 ms threshold, voice/model policy hash, defaults and prior eight accepted Giọng B cuts remain unchanged. Three meaningful conservative tests and actual old-wave/cut comparisons passed. Unsupported or unsafe boundaries still stop explicitly; English/misrecognized narration onsets were corrected through Studio and only affected dependencies regenerated.

Five planning rows were aligned through the existing planning API with their actual portrait/landscape templates and configured durations, preserving project revisions. UAT evidence uses exact-byte Git attributes, following existing accepted-receipt conventions. No large feature, second production pipeline, new secret/provider, publishing or scheduling was added.

Sources remain sourced claims rather than independently verified facts. Unknown publication dates, archival reporting periods, lexical similarity and heuristic scoring are explicit. The sourced graphics are original editorial text cards, not photographs proving a development's current condition. Real ASR alignment validates a cut boundary, not every word's pronunciation; Owner must judge the actual speech and pacing.

Next action: Owner watches/listens to all five current videos and records ACCEPTED or REJECTED, with reviewer, timestamp, duration, render revision and canonical timeline version. Only exact current accepted artifacts may move to PRODUCED. Rejected content will be repaired within the authorized UAT scope and presented again; Phase 10 remains uncertified until five acceptances exist.

PRODUCTION_INTELLIGENCE_READY = YES

DRAMAGIC_STUDIO_READY = YES

PHASE10_READY = NO
