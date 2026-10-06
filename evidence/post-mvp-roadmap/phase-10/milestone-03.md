# Milestone 03 — Studio and integration verification

MILESTONE: Phase10A–10X Studio implementation and technical verification.

STATUS: Technical verification PASS within the documented scope; Phase10Y human campaign pending. Readiness remains NO.

HEAD SHA: Parent `2d0b3a0f03e42c6b8d7aff19c1f30ad45aa748ed`. This receipt accompanies the progressive Studio commit; its containing commit is the implementation marker.

UI CHANGES: Script/Assets/Storyboard/Video navigation; large preview; selected-shot properties and horizontal cards; drag/move, replace, duplicate, delete, revert, existing-source regeneration; reviewable scoped AI suggestions; asset usage/tags/provenance; source details; production queue, configured profiles, calendar/campaign grouping, explainable priority/similarity checks, explicit batches and approved video library. Original certified controls retained. New functionality loads only when the running backend advertises support.

BACKEND CHANGES: Runtime capability advertisement; historical video library checks actual timeline artifact/checkpoint hashes and schema where present; voice dependency scope includes scene ordinal as required by the unchanged certified warm-cache recipe. Asset-only changes preserve voice dependencies. No destructive migration or second editing state.

TESTS: Full Native226/226 PASS in99.966s; final full Studio54/54 PASS in252.0477ms. Includes10 isolated real HTTP tests, actual FFmpeg proxy/portrait/landscape rendering tests with labelled synthetic PCM, atomic persistence/restart/provenance/failure checks and legacy/capable frontend boot tests. Actual provider verification is separately recorded: two OpenAI suggestions with explicit scope and apply in an unapproved isolated clone, no new credential, no TTS/render/Owner acceptance.

SCREENSHOTS: Final1366x768 PNG;1920 preview, Assets, queue, profile and historical lineage images; old accepted project and live8026 compatibility captures. 2560 DOM geometry was checked; IAB bitmap capture remained unreliable and the images are retained as diagnostics, not visual PASS.

EVIDENCE: `final-native-regression.log`, `final-studio-regression.log`, `technical-browser-receipt.json`, `final-preservation-verification.json`, `mixed-runtime-compatibility.md`, `viewport-verification.json`, `uat-preparation.json`, `PHASE10_UAT_GUIDE.md`.

REGRESSIONS: A mixed old-backend/new-static-file bootstrap regression was discovered and fixed. Read-only browser checks confirm8026 Native and Content Intelligence work after reload. Main process unchanged/uninterrupted. All1,596 prior evidence files,15 accepted final MP4 hashes, live workflow/intelligence table digests and runtime dependencies match the baseline. Isolated fresh-process canonical readv5 and approved historical library15/15 pass.

BLOCKERS: Owner must complete a real campaign with10 chosen ideas, at least5 production selections, required human shot actions and final watch/listen acceptance. Full2560 pixel visual acceptance remains pending. Advanced Timeline is a canonical track/clip navigator into the same shot editor; regeneration selects another existing media source; AI media synthesis and multi-voice selection are not claimed.

NEXT ACTION: Commit the verified Studio implementation, then publish the truthful final report and gate ledger. Continue real campaign verification after the human performs the prepared Studio workflow.
