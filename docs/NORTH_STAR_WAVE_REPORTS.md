# North Star wave ledger

## Wave 0 — source preservation

WAVE: 0

STATUS: COMPLETE; SOURCE_PRESERVED = YES

HEAD SHA: initial `2ced7bc81f9402368fb22c9e7aca242e740531af`; baseline commit `106af19`.

CAPABILITIES COMPLETED: actual repo identity/divergence inventory; safe branch; GitHub preservation; full-history bundle verification; raw Git/archive CRC verification; 15 accepted artifact SHA256 comparisons/backup.

CAPABILITIES PARTIAL: no new capability acceptance claimed.

TESTS: archive and SHA256 verification; source clean before preservation.

REAL PROVIDER TESTS: none. MOCK TESTS: none.

EVIDENCE: `NORTH_STAR_BASELINE_2026.md`, `north-star/accepted-artifacts.json`; local recovery root `C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007` with manifest, complete commit/ref lists and verified archives.

REGRESSIONS: no source/runtime/database/artifact changes.

EXTERNAL BLOCKERS: none for preservation; original workspace was empty and long-path checkout failed, resolved using `C:\vfns01`.

OWNER ACTION REQUIRED: none. NEXT WAVE: 1.

## Wave 1 — Master Spec audit

WAVE: 1

STATUS: INITIAL AUDIT COMPLETE; verification findings remain explicit.

HEAD SHA: audit based on `2ced7bc81f9402368fb22c9e7aca242e740531af`, report committed separately after baseline.

CAPABILITIES COMPLETED: 64-row matrix, exact gaps/severities/dependencies/waves/acceptance, 90-section crosswalk, 96 source-file fingerprints, live Native UI read-only inspection and closure plan.

CAPABILITIES PARTIAL: 54 requirements; 2 interface-only; 1 mock-only; 1 missing general cache; 1 unverified Docker; 5 executable implementations still require integrated acceptance. These are inspection classifications, not readiness certification.

TESTS: Native **255/255 PASS**, 128.15 seconds using certified venv; Studio **79/79 PASS**, 499.98 ms. Initial wrong-runtime Native run failed with missing dependencies; preserved. Full API collection blocked on three POSIX modules. Long isolated-temp paths exceeded Windows MAX_PATH; short paths inside the checkout triggered the executor's required evidence-outside-source guard. That run reports 1759 passed / 60 failed / 24 errors / 12 skipped; these failures are not waived. An isolated short path outside the source is being tested before classifying the remaining Windows/Linux gates.

REAL PROVIDER TESTS: no new calls. MOCK TESTS: Native/Studio unit/HTTP fixture suites; API results pending, not claimed passing.

EVIDENCE: `NORTH_STAR_CAPABILITY_MATRIX.md`, `north-star/capabilities.json`, `north-star/master-crosswalk.json`, `north-star/source-inventory.json`, `NORTH_STAR_GAP_CLOSURE_PLAN.md`; exact baseline logs under recovery root.

REGRESSIONS: all accepted video hashes unchanged; no live project writes/restarts. Fresh Native and Studio suites pass.

EXTERNAL BLOCKERS: Windows-only host and absent Docker prevent Linux/Docker certification; several real providers have no complete official adapter yet. Credentials are not treated as the sole blocker for interface-only implementation.

OWNER ACTION REQUIRED: none for safe implementation. Phase 10 personal UAT remains pending. NEXT WAVE: 2, then all remaining safe waves.

## Wave 2 — technical quality remediation

WAVE: 2

STATUS: PHASE10_TECHNICALLY_READY = YES for the measured quality gates and retained repaired candidates; OWNER_UAT_REQUIRED = YES; PHASE10_READY = NO.

HEAD SHA: `ce4beeb` — pushed to the completion branch; no main merge.

CAPABILITIES COMPLETED: versioned policy for new UI projects; visible NFC/canonical proper names before review; approval/TTS/cached-render guards; raw provider/content result preservation; measured narration tail/gap gate before FFmpeg; decoded final-audio trailing-silence QC; hard canvas/profile checks; localized reviewable errors. Historical documents are not upgraded on read. Five repaired videos retain their hashes and pass fresh measured checks. New local-name audio is separate evidence.

CAPABILITIES PARTIAL: broader provider-neutral TTS/audio/full QC remain in Waves 6/16. Owner pronunciation and UX UAT remain pending. Case 04's historical input spells Sài Gòn Park; it is retained unchanged and explicitly marked for spelling review. New policy drafts and the real local diagnostic use Vinhomes Saigon Park. Existing shared shell/Assets/Asset Picker/portrait review remain intact; archived 1366/1920/2560 visual evidence is historical, not a new visual test.

TESTS: Native **264/264 PASS**, 165.22 seconds using the certified runtime; Studio **80/80 PASS**, 880.86 ms. Nine new quality tests cover normalization, policy tampering, unchanged originals, approval rejection, checkpoint replay, sample binding, dead-air rejection, a real FFmpeg fit-narration render and a padded-silence failure. An earlier 263-test run failed on the old exact capability assertion, which was updated for the additive capability and rerun.

REAL PROVIDER TESTS: no remote calls. Real local locked Thùy Dung TTS: **3 inference calls**, network blocked, measured **7.24 s**, SHA256 `e85b0a1a6e0b07e8fa5bd6efe3bf0ad1f08870dc8a836f7adac948066f6a32ed`. This does not certify pronunciation or Owner UAT.

MOCK TESTS: synthetic PCM/input fixtures for automated quality and HTTP contracts; no mock represented as real narration.

EVIDENCE: `docs/north-star/wave2-quality-evidence.json`; runner `scripts/north_star_phase10_quality.py`; full logs and local `voice.wav` under `C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007\phase10-quality-f637e328\proper-name-diagnostic`; `native-wave2-final.log`, `studio-wave2-tests.log` in recovery root.

REGRESSIONS: 255 previous Native tests plus nine new tests pass; 79 previous Studio tests plus one new test pass. No historical candidate/accepted video replacement, live server restart, live DB write, protected-main merge or external publication.

EXTERNAL BLOCKERS: Owner personal watch/listen and UX acceptance. These do not block safe Mode B implementation.

OWNER ACTION REQUIRED: review retained repaired candidates and the separately generated three-name sample when ready; no acceptance is inferred. NEXT WAVE: 3 — complete Mode B UI and analysis integration.

## Wave 3 — first Mode B increment

WAVE: 3

STATUS: IN PROGRESS. AUTO_EDIT_MODE_READY = NO. This transcript/history increment is complete; the wave is not certified complete.

HEAD SHA: `834d6dbf4506a30c78826481d040402e752cf67f`; pushed to the completion branch.

CAPABILITIES COMPLETED: authenticated editor transcript mutation route; original transcript/segments/words preserved; optimistic transcript/timeline versions; one transaction for transcript/canonical subtitle writes, preview staleness and production approval/render invalidation; changed text discards old word timestamps; full Vietnamese text with bounded sentence captions; canonical historical transcript selection; repeated undo/redo follows restored content states rather than decrementing the version counter; failed/stale/foreign/locked writes roll back without provider dispatch. Existing immutable tables are reused; no destructive migration.

CAPABILITIES PARTIAL: Native/production Mode B integration; combined scene intelligence; reviewable silence/highlight workflows; real waveform; all dynamic subtitle modes; shot-first Mode B UI; remaining full-wave acceptance. Edited transcript semantic analysis is explicitly marked stale for refresh rather than silently reusing prior semantics.

TESTS: **28/28 API PASS**, 35.75 s (transcript, auto-edit analysis, timeline and production regression suites). **85/85 frontend PASS**, 397.93 ms. Nine transcript tests include actual isolated HTTP role enforcement, stale conflict, atomic rollback, long Unicode captions and branching after undo. Full isolated Ubuntu API baseline at this HEAD: **1,896 passed / 5 skipped**, 470.49 s, including all three POSIX modules unavailable on Windows. Durable source/venv are under `/root/vfns-ci-20261007-c1`, not volatile `/tmp`; no live service/configuration changes.

REAL PROVIDER TESTS: none. MOCK TESTS: explicit deterministic transcription/media fixtures for transport/persistence; not real ASR. No new provider, render or publication dispatch from editing.

EVIDENCE: source/tests listed in the updated matrix; `mode-b-transcript-final.log`, `mode-b-transcript-studio.log` in recovery root.

REGRESSIONS: targeted previous auto-edit/timeline/production suites pass; Native 264/264 remains the latest Wave 2 result. Final corrected Windows baseline outside source/short paths: **1792 passed / 27 failed / 24 errors / 12 skipped** in 372.30 s. Remaining failures are Linux UID/custody/POSIX path/symlink assumptions; six error cases hit Windows environment-variable length. Three POSIX modules were explicitly excluded from that Windows run and remain mandatory for Linux. The baseline is not reported as passing.

EXTERNAL BLOCKERS: no blocker to continued safe implementation. Docker is absent. Real-provider acceptance and Owner UAT remain separate gates.

OWNER ACTION REQUIRED: none for this increment. NEXT WAVE: continue Wave 3, then remaining safe waves.

## Wave 3 — reviewed silence cuts, measured waveform and shot view

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. This increment closes concrete safety/UI gaps; combined scene intelligence, highlight selection, Native integration and full acceptance remain.

HEAD SHA: `510e6247a8c51fe8b8ef1bfd461183083f4a1121`; pushed to the completion branch and preserved in verified `north-star-510e624.bundle`.

CAPABILITIES COMPLETED: canonical silence cuts retain padding and reject speech overlap even with stale safety flags; whole speech segments are protected when words are absent. Editor-scoped selection requires timeline CAS, respects locked editable tracks and binds the historical transcript active after undo. All-source removal is rejected. Earlier versions remain immutable and approval/preview/render invalidate. Threshold configuration is distinguished from measured loudness. Local PCM waveform measurement streams bounded peak/RMS bins, persists provenance without migration, fingerprints the algorithm and follows source-relative trim/split/move. Shot cards and the collapsed advanced view select/edit identical canonical clip IDs. Pre-timeline transcript/scene/silence/highlight review is visible. New-project/upload authoring is collapsible and opens for empty projects. Explicit `hidden` semantics correct the inspector placeholder bug.

CAPABILITIES PARTIAL: Native/production bridge; combined scene/Vision/motion evidence; Top 3/5/Auto Shorts selection; dynamic subtitle completeness; full real spoken-media acceptance. Fixture ASR is clearly labeled and not accepted as real transcript evidence.

TESTS: **35/35 API PASS**, 44.23 s, in `mode-b-silence-35-final.log`. Frontend **88/88 PASS**, 388.76 ms. Seven silence/media tests cover segment/word protection, preserved padding, stale flags, keep-all selection, all-footage rejection, historical transcript binding, locks, CAS, authenticated actor attribution and real local FFmpeg measurement. Early runs exposed two test-fixture mistakes and the default metadata-track lock; corrected and rerun rather than ignored.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: FFmpeg synthetic tone/video decode, silence bounds and waveform amplitude; real persistence and browser HTTP mutations on a fresh isolated SQLite fixture. No genuine speech/remote ASR/Vision acceptance claim. MOCK TESTS: explicit deterministic transcript/media providers only.

EVIDENCE: `docs/north-star/studio-wave3-visual/evidence.json` and six browser images; `scripts/north_star_studio_fixture.py` reproducible loopback-only harness; `audio_waveform.py`, silence tests and logs in recovery. Browser checks at **1366×768 / 1920×1080 / 2560×1440** show no horizontal overflow; actual transcript save v2, undo v3, redo v4, silence rebuild v5; draft approval; no console warning/error. Temporary viewport override reset.

REGRESSIONS: focused API/Studio pass; full prior-head Ubuntu regression is **1,896 passed / 5 skipped** and is preserved separately. Native 264/264 is the latest Wave 2 run, not represented as retested here. Accepted/candidate media and live DB remain unchanged. No live restart, production deployment, paid call, external publishing or main merge.

EXTERNAL BLOCKERS: Docker absent; genuine provider acceptance and Owner UAT remain separate gates. No blocker to further safe implementation.

OWNER ACTION REQUIRED: none for continued implementation. NEXT WAVE: finish Wave 3 analysis/highlight/reframe/Native integration; continue all later safe waves.

## Wave 3 — editable highlight/Auto Shorts drafts

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Highlight draft workflow is implemented; remaining Mode B/Native/media integration is not waived.

HEAD SHA: parent `510e624`; commit `feat(auto-edit): save and apply immutable highlight drafts` records this increment.

CAPABILITIES COMPLETED: Top 3, Top 5 and Auto Shorts build separately persisted canonical drafts; repeats reuse fingerprinted drafts and leave the active master timeline unchanged. Scores use the selected transcript, including edited text, with explicit heuristic factors. Selection expands to whole measured words or whole segments without word timestamps; over-duration selections are omitted rather than cut through speech. Fewer available candidates are returned honestly. Editor identity is authoritative. Apply checks transcript/source identity, track locks and timeline CAS, preserves old master versions and invalidates approval. Original provider rows and raw media remain unchanged. Caption coverage merges continuous shots to retain words spanning visual boundaries, and rebuilt unaligned captions retain full Unicode text. The additive migration creates only a draft table; destructive downgrade is refused, and no live DB migration ran. Older APIs lacking the additive endpoint retain Studio loading with disabled draft controls.

CAPABILITIES PARTIAL: measured multimodal scoring, Native bridge, independent platform variants, dynamic subtitles/reframe and complete real spoken-footage E2E acceptance. Existing scene motion/quality remain explicitly identified heuristics, not real Vision/motion observations.

TESTS: **42/42 API PASS**, 61.37 s; **88/88 frontend PASS**, 383.53 ms. Seven new highlight tests cover Top 3/5/fewer candidates, fingerprint reuse, no master mutation, applied history, stale transcript/version rejection, foreign scopes, whole-word boundaries, shot-boundary word retention, long unaligned Unicode caption preservation, authenticated HTTP transport and additive SQLite migration preserving existing rows. An initial test used an extra `segment_id` field on `TranscriptWordRead`; corrected and rerun.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: fresh SQLite persistence and actual browser HTTP generation/application with locally generated synthetic media. MOCK TESTS: fixture ASR is visible and recorded; no speech/provider acceptance claim.

EVIDENCE: `docs/north-star/studio-wave3-visual/highlight-evidence.json`, `highlight-drafts.jpg`, `highlight-applied.jpg`; source/tests/migration indexed in matrix; `mode-b-highlights-42-final.log` and `mode-b-highlights-studio-final.log` in recovery. Browser created two stored mode-specific drafts from one actual scene, kept timeline v1 until selection, then saved v2 with Draft approval and no console errors. Test servers on 18031/18032 were verified and stopped; fresh data under `C:\vf-ui-fixture-a1`/`a2` remains for recovery.

REGRESSIONS: targeted analysis/transcript/timeline/production suites pass. Native 264/264 and prior-head full Ubuntu 1,896/5 results remain separately identified, not silently represented as rerun here. No accepted artifact replacement, live configuration/data write, protected-main merge, paid call or external publish.

EXTERNAL BLOCKERS: Docker absent; actual remote-provider and Owner acceptance remain separate. No blocker to safe work.

OWNER ACTION REQUIRED: none for continued implementation. NEXT WAVE: continue Wave 3/4 reframe, combined scene/media intelligence and Native bridge, then remaining safe waves.

## Wave 3 — canonical reframe, renderer and Studio integration

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. All four crop ratios now reach canonical persistence, Studio and local encoded rendering. Native integration and complete spoken-media acceptance remain required.

HEAD SHA: parent `7bc8a7d`; the following reframe capability commit records this increment. Cache fix `7bc8a7d` is already pushed.

CAPABILITIES COMPLETED: editor-scoped reframe applies an existing source/checksum-bound Vision plan, or an explicitly low-confidence center-crop fallback with `needs_attention=true`. No provider is dispatched by this action. Measured source geometry defines bounded normalized source-time keyframes for 9:16, 16:9, 1:1 and 4:5. CAS, immutable history, track locks and approval invalidation are preserved. Trims/splits/moves/speed retain source-relative paths; manual crop edits remove superseded tracking. Studio offers the four aspects and already-saved compatible Vision results. Reframed preview uses production A/V review. Render contract v2.2 transports paths without rewriting older contracts. Review/final profile mismatch is rejected before queue or provider work. 4:5 final is 1080×1350; review is 432×540 because H.264 YUV420 rounded an initial odd 675-pixel height to 674. Exact even dimensions prevent that mismatch.

CAPABILITIES PARTIAL: genuine Vision/subject tracking acceptance, Native pipeline integration, combined scene intelligence, dynamic subtitle completeness and full Mode B E2E. Synthetic paths are not represented as provider tracking results.

TESTS: **49/49 focused API PASS**, 16.05 s (`mode-b-reframe-api-final.log`); **90/90 Studio PASS**, 403.06 ms; **29/29 renderer PASS**, TypeScript and webpack bundle PASS. New tests cover eight measured source/target geometries, immutable persistence, actor/auth roles, stale versions, foreign/stale Vision evidence, manual crop precedence, render contract transport, profile rejection before queue, matching 4:5 review processing, and interpolation through source-time edits. The full prior checkpoint `21169f0` Linux run was **1,908 passed / 1 failed / 6 skipped** in 474.38 s. The failure exposed a null signal-algorithm cache salt changing exact legacy fingerprints. `7bc8a7d` omits that field for unversioned providers, while retaining the new FFmpeg algorithm salt; the original exact-legacy regression passes in the focused suite. A fresh full Linux run is still required at this checkpoint.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: real Remotion/Chrome/FFmpeg encoded four synthetic review videos at 540×960, 960×540, 540×540 and 432×540; FFprobe verifies H.264/AAC geometry and two-second duration (AAC container 2.048 s). Decoded portrait pixels verify the saved path traverses red to blue. Browser actual HTTP/SQLite apply saves timeline v2 and retains Draft status. MOCK TESTS: explicit ASR/Vision fixtures only; deterministic production review in API tests.

EVIDENCE: `docs/north-star/wave3-reframe-render-evidence.json` includes raw probe results, decoded pixel values and six media hashes; `renderer/src/north-star-reframe-smoke.ts` is reproducible and requires a fresh output directory. Actual videos and initial diagnostic failures remain under recovery `reframe-render-r1/r2/r3`, with passing run `r3`. Browser `studio-wave3-visual/reframe-evidence.json` and three screenshots verify 1366/1920/2560 layouts without horizontal overflow, center-crop attention status, Draft approval and no console warning/error. Temporary viewport and test tab reset/closed; loopback fixture server stopped. The browser stylesheet reference is versioned so clients receive the new controls' styles.

REGRESSIONS: focused previous API/Studio/renderer suites pass; full Linux checkpoint is transparently reported above. Native 264/264 is the latest separate Wave 2 result. No accepted media replacement, live data/configuration write, deployment, main merge, paid provider call or external publication occurred.

EXTERNAL BLOCKERS: Docker absent; genuine provider acceptance and Owner UAT remain separate gates. Neither blocks continued safe implementation.

OWNER ACTION REQUIRED: none for this implementation increment. NEXT WAVE: continue Wave 3/4 combined scene intelligence, subtitles/B-roll and Native integration, then all later safe waves.

## Wave 3/4 — measured local visual signals and explained highlights

WAVE: 3/4

STATUS: IN PROGRESS. Scene/media intelligence is partial until saved semantic Vision fusion, Native integration and final acceptance are complete.

HEAD SHA: parent `cc949003953d3a3c0904cacbd02ed8c52d881e88`; the measured-signal capability commit records this increment.

CAPABILITIES COMPLETED: actual FFmpeg `lavfi.scene_score` replaces the detector's constant confidence. A bounded local decoder samples at most 360 160×90 grayscale frames; it measures luma, dark/bright fraction, luminance edges, adjacent sample pixel difference, exact duplicate hashes and exposure/black-frame candidates. It does not claim semantic detection, calibrated blur or optical flow. Measurements and waveform persist with algorithm-version cache binding. Scene motion uses a documented pixel-change proxy; local quality is a documented exposure heuristic. Legacy fallback scores remain readable but are explicitly labeled unmeasured heuristics. Transcript keywords no longer masquerade as detected subjects. Scene evidence includes audio boundaries, speech coverage and source timestamps. Highlight scores explain each available weighted contribution; missing motion/audio/quality/novelty remain null in factor evidence rather than invented provider data. Local-stage failure cancels sibling analysis and decoder processes before source cleanup.

CAPABILITIES PARTIAL: saved structured Vision fusion and assessment-version UI, calibrated visual quality/subject tracking, real spoken-source E2E, Native bridge. Historical numeric scene scores are not retroactively changed or treated as new measurement evidence.

TESTS: **61/61 focused API PASS**, 44.41 s (`scene-signals-api.log`). Includes real local FFmpeg black-to-moving-video cut detection, frame sampling bounds, exposure/pixel-change/duplicate measurement, absent audio, null highlight factors, scoring contributions and sibling cancellation; previous upload/transcript/silence/highlight/cache tests pass.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: synthetic video encoded/decoded by FFmpeg with real cut measurements. MOCK TESTS: fixture ASR and provider-scoped HTTP tests retain explicit labels.

EVIDENCE: `visual_signals.py`, `test_visual_scene_signals.py`, analysis persistence and machine-readable capability/source inventory; log in recovery. Reframe checkpoint `cc94900` remains pushed with a verified full-history bundle; its fresh Linux full regression is running separately on the verified checkout. An earlier run was intentionally interrupted because checkout completion had not been verified before launch; it is not certification evidence.

REGRESSIONS: focused existing suites pass. No accepted artifact replacement, live DB migration/restart, external provider call, deployment or main merge.

EXTERNAL BLOCKERS: none to continued safe work; semantic provider acceptance and Docker remain separate limitations.

OWNER ACTION REQUIRED: none for this increment. NEXT WAVE: continue saved Vision/scene fusion and all subsequent safe waves.

## Wave 3/4 — immutable combined-scene review

WAVE: 3/4

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO; MEDIA_INTELLIGENCE_READY = NO. Saved semantic Vision is integrated without waiving real-provider/Native/final acceptance.

HEAD SHA: parent `468b88f`; the combined-scene capability commit records this increment. `468b88f` and prior reframe checkpoint are pushed to the completion branch.

CAPABILITIES COMPLETED: immutable scene assessments combine the exact selected transcript, original shot intervals, audio boundaries/energy, bounded measured pixel/exposure/duplicate signals and an optional already-saved structured Vision analysis. Source/project/analysis/checksum binding is enforced. Actual subject observations retain category, box, frame timestamp, provider, model, confidence and frame reference. Quality and motion stay null where measurements are absent. Legacy numeric heuristics are not promoted into measured data. Provider confidence is labeled as evidence confidence rather than calibrated fusion probability. Stale edited-text semantics, missing Vision, unsafe crop, black frames and low quality/confidence require attention. Repeated inputs reuse one fingerprinted immutable row. Transcript edits create new assessments while prior rows remain readable. Studio selects/reviews a saved assessment and Top 3/5/Auto Shorts bind its identity/fingerprint; stale transcript/source assessments cannot be used. Original analyses and the active master timeline remain unchanged until explicit draft application. Migration adds one table only; no live migration ran, and destructive downgrade is refused.

CAPABILITIES PARTIAL: Native bridge, genuine subject/scene Vision acceptance, semantic-boundary proposals, full dynamic subtitles/B-roll and final real-spoken-media E2E. Frame references point to already-saved provider evidence; this increment does not dispatch a provider or fabricate semantic subjects.

TESTS: **63/63 focused API PASS**, 73.70 s (`scene-intelligence-api-final.log`); **91/91 Studio PASS**, 437.77 ms, plus JavaScript syntax check. Four new tests cover idempotency, immutable history/original rows, nullable missing measurements, edited transcript binding, saved fixture Vision/model/frame provenance, foreign/stale evidence rejection, authenticated HTTP roles/project scope and additive migration preservation. The initial run found SQLite's naive reload timestamp differed from the UTC creation response; UTC normalization fixed it and the broad suite passes. The complete isolated Linux regression at **`cc949003953d3a3c0904cacbd02ed8c52d881e88` passed 1,922 tests / 6 skips** in 539.02 s (`api-linux-cc94900-final.log`). That result includes all POSIX modules, the cache regression fix and reframe integration; later measured/fusion changes retain their separately listed focused evidence.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: real FFmpeg sampling, actual HTTP/SQLite assessment generation and highlight binding through the browser. MOCK TESTS: explicitly labeled ASR and saved structured Vision fixture; no real semantic-provider acceptance.

EVIDENCE: `scene-intelligence-persistence-evidence.json` verifies one saved assessment and its bound highlight draft with zero provider dispatches; `studio-wave3-visual/scene-evidence.json` and three screenshots verify no horizontal overflow at 1366/1920/2560, 32 locally measured image samples, absent semantic Vision, fixture ASR and master timeline v1 after draft creation. The UI distinguishes exposure heuristics from semantic Vision quality. Test tab closed, viewport reset and only the verified fixture Python processes stopped; data retained under `C:\vf-ui-fixture-s1`.

REGRESSIONS: focused prior upload/analysis/transcript/silence/highlight/reframe/media tests pass. Full reframe checkpoint Linux is green as recorded. Latest Native regression remains the separate Wave 2 264/264 run. Accepted media, original live worktree/data/configuration remain untouched. No main merge, production deployment or external publishing.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker and Owner Phase 10 UAT remain separate limitations; safe work continues.

OWNER ACTION REQUIRED: none for continued implementation. NEXT WAVE: finish dynamic subtitle/B-roll/Native integration and continue the remaining safe waves.


## Wave 3 — versioned dynamic subtitle templates

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. API Studio caption behavior is implemented and locally tested; the Native bridge and genuine spoken-source acceptance remain.

HEAD SHA: parent `e99cba6c462c350b23585c1fe152f0e40f3b4f3d`; the dynamic-subtitle capability commit records this increment. Parent source is pushed and preserved in a verified complete-history bundle.

CAPABILITIES COMPLETED: seven immutable versioned template starters support sentence, word-by-word, karaoke, keyword highlight, pop, fade and historical aligned highlight. Full selected style/keywords/template identity persist with subtitle versions. Render contract v2.3 carries the extensions while old v2.0–2.2 manifests retain their original shape; newer still-image contracts use no fabricated source duration. NFC Unicode keywords use whole-word/phrase matches with Vietnamese accents. Karaoke progresses against measured intervals and retains punctuation; word-by-word leaves real timestamp gaps empty. Timed effects require saved word alignment, and mismatched text is rejected. Style-only Studio saves preserve exact timestamps; editing text/time clears stale words. Server-side CAS/history rejects invented or stale retained timestamps, independently of the UI. HTTP writes bind the authenticated editor identity. Old APIs without the catalog keep the existing sentence/animated paths available. Browser review found legacy 8px caption controls; they now use 14px input text with a two-column workbench at 1366px.

CAPABILITIES PARTIAL: accepted Native Studio template/render bridge; genuine spoken-video alignment and final Mode B E2E; caption edit/timeline integration and wider downstream work remain subject to the canonical timeline acceptance. No provider or Owner acceptance is inferred from fixtures.

TESTS: **68 focused API PASS / 3 SKIP**, 100.84 s (`subtitle-api-final.log`); **93/93 Studio PASS**, 419.31 ms, and final JavaScript syntax check; **33/33 renderer PASS**, 1.48 s, TypeScript and actual webpack bundle checks pass. Tests cover missing/mismatched alignment, forged words, CAS, immutable stored versions, authorized HTTP roles/workspace scope/actor binding, Unicode keyword boundaries, real timing gaps and historical version gates. The final extended-manifest/still-image contract check passes **6/6**, 7.10 s (`subtitle-api-contract-final.log`), after the last validation change. Three API skips are explicit infrastructure-dependent checks. Certified-runtime Native regression **264/264 PASS**, 134.690 s (`native-subtitle-regression.log`).

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: six actual Remotion/Chrome/FFmpeg H.264/AAC encodes, each 540×960 and 2.0s video / 2.048s AAC container; browser HTTP/SQLite saves and reload. MOCK TESTS: explicit ASR fixture and synthetic word timing/tone audio; no speech-recognition quality claim.

EVIDENCE: `subtitle-render-evidence.json` contains six output hashes, exact recovery paths, receipts and FFprobe data; runner `renderer/src/north-star-subtitle-smoke.ts` requires a fresh output directory and closes its server. Four decoded caption/gap frames are retained. `subtitle-persistence-evidence.json` verifies three stored versions: v2 style change preserves all words, v3 edited text clears only its stale alignment, and master timeline remains v1. `studio-wave3-visual/subtitle-evidence.json` and three screenshots show 14px caption controls, preserved Unicode keyword configuration and no horizontal overflow at 1366/1920/2560. Browser console has no errors/warnings. Fixture tab closed, viewport reset, exactly the two verified fixture Python processes stopped; `C:\vf-ui-fixture-c1` retained. First local render run is retained separately; the second adds crisp karaoke text and hides empty-gap caption background. An evidence-copy script initially hit Windows default text decoding; rerun explicitly used UTF-8 without replacing source or accepted media.

REGRESSIONS: focused existing production/approval/content/transcript/reframe paths pass; full Linux checkpoint remains the separately recorded 1,922/6 result at cc94900 until the next committed-source run. Original live source remains clean at `2ced7bc81f9402368fb22c9e7aca242e740531af`; live data/configuration and accepted media are untouched. No main merge, paid provider dispatch, external publication or production deployment.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker and Owner Phase 10 UAT are separate limitations; none blocks continued safe implementation.

OWNER ACTION REQUIRED: none for continued safe work. NEXT WAVE: continue B-roll/media resolver and Native integration, then all remaining safe waves.


## Wave 3/6 — stable media priority and transcript-bound planning

WAVE: 3/6

STATUS: IN PROGRESS. This closes planner priority/cache correctness; full supporting B-roll/Native/media-provider acceptance remains outstanding.

HEAD SHA: parent `2506539` (render-profile capability assertion correction); this planner capability commit records the increment. Subtitle checkpoint `0dc6bd5980d6c22b8ae1385fcfc4da923366cc3c` is pushed and preserved in `north-star-0dc6bd5.bundle` (verified complete history).

CAPABILITIES COMPLETED: configured media priority is applied to every scene by default instead of rotating through provider tiers by scene number. Explicit `scene_variety` retains the previous multi-provider capability, and old saved configurations read with that original policy. Strict stock selection requires known rights and actual search results when searched; empty/rights-rejected responses fall back. Unsearched counts remain null. B-roll decisions persist source analysis/asset checksum, exact transcript ID/version, saved Vision/frame/provider/model/confidence references, placement, query/prompt and recommendation-only status. Missing Vision no longer contributes an invented 0.55 confidence; the unmeasured scene heuristic is explicitly capped/labeled. Edited transcript semantics mark attention and prompts use selected transcript text. New plan fingerprints bind transcript identity/version; historical and current text produce distinct plans without rewriting prior evidence. Source and saved Vision checksum mismatch is refused before new plan rows or provider work.

CAPABILITIES PARTIAL: dedicated supporting-asset relevance ranking and selection/application UI, Native bridge, internal-library tier, official stock/generated providers, actual budgeted-media E2E and full MediaPlan integration. Primary footage reuse is distinct from a completed supporting B-roll resolver; this increment does not claim the whole B-roll engine ready.

TESTS: **36 focused API PASS**, 75.06 s (`media-planning-policy-final.log`), including existing media resolution/rights/cost/restart contracts and transcript/reframe/scene regressions. New tests cover every-scene priority, explicit variety, immutable/current/historical transcript plans, legacy configuration interpretation, source/Vision hash refusal and empty stock fallback. Expanded empty/unknown/restricted stock-rights cases pass **6/6**, 14.69 s (`media-planning-rights-final.log`). Earlier pre-fallback run passed 18 tests separately.

REAL PROVIDER TESTS: none. MOCK TESTS: explicit synthetic ASR/Vision/stock/image/video fixtures; real SQLite persistence and domain behavior. No external or paid provider was invoked.

EVIDENCE: executable source and `test_media_planning_policy.py`; focused logs in recovery. Complete isolated Linux regression for verified clean `0dc6bd5` finished **1,931 PASS / 1 FAIL / 7 SKIP**, 585.45 s (`api-linux-0dc6bd5.log`). The sole failure was the existing capability contract expecting three profiles after supported 4:5 rendering added a fourth. Separate pushed commit `2506539` updates that assertion; safety configuration tests pass **18/18**, 2.23 s (`render-profile-capabilities-final.log`). A fresh complete committed-source run remains required. The Linux launch's initial shell guard printed a Git-path error because command substitution resolved in the Windows worktree; explicit `/usr/bin/git -C` HEAD/status verified the actual clean checkout before tests. No force/reset or dirty-checkout discard occurred.

REGRESSIONS: accepted Native/source artifacts remain untouched. Previous Native **264/264**, Studio **93/93**, renderer **33/33**, six local-real caption encodes and subtitle contract **6/6** remain attached to the prior increment. New focused media/transcript/reframe/scene tests pass. No live database migration/restart, main merge, external publication or deployment.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker and Owner Phase 10 UAT remain separate; none blocks continued safe work.

OWNER ACTION REQUIRED: none. NEXT WAVE: dedicated B-roll suggestions/application and Native workflow integration, followed by remaining safe waves.

## Wave 3 — supporting B-roll picker and canonical application

WAVE: 3

STATUS: IN PROGRESS. AUTO_EDIT_MODE_READY = NO. Supporting B-roll selection/application is implemented in API Studio; Native and final spoken-media acceptance remain outstanding.

HEAD SHA: parent `bab4e2454babe206493b3d666db90e13d538acfc`; this supporting B-roll capability commit records the increment. Parent is pushed and preserved in verified `north-star-bab4e24.bundle`.

CAPABILITIES COMPLETED: transcript-bound supporting plans exclude primary footage, restricted media and videos without measured duration. Ranking uses saved filename/description/tags and labels lexical overlap; semantic confidence remains null. Explicitly registered licensed internal-library assets participate in priority. Unavailable generation preserves the original footage. Studio creates/selects plans, uses an asset picker, waits for async local resolution and explicitly applies selected resolved items. CAS creates a new version of the existing canonical timeline; source, captions and original audio tracks are preserved, history remains immutable and previews/approval are invalidated. Placement follows source trims, cuts, moves and speed; video clips are bounded to measured duration and image clips retain display-duration semantics. Locks, overlaps, duplicate application, foreign selections, transcript/source/checksum mismatches fail before mutation. Replacing clips from the same plan requires an explicit selection. Rights stay attached; unknown-rights review media cannot pass publishing. Reused registered-media provenance is readable in subsequent plan versions. Browser reload retains the actual selected filename.

CAPABILITIES PARTIAL: Native bridge, genuine semantic Vision ranking, official stock/generated-provider paths, supporting placement/duration controls and runtime-outage fallbacks, complete original-audio A/V/final E2E. The local visual proxy uses its existing contain/letterbox compositor; final A/V behavior still requires separate evidence. No fixture speech/provider acceptance or Owner UAT is inferred.

TESTS: final focused API **43/43 PASS**, 68.58 s (`broll-api-final-r2.log`), including previous media/rights/cost/restart, transcript, reframe and scene tests. Earlier focused run passed 41; expanded B-roll contracts passed 5/5 before final attention-state refinement. Studio **94/94 PASS**, 472.72 ms (`broll-studio-final-r3.log`) and syntax check. Tests cover preserved tracks/history, review-only unknown rights, cache/source scope, measured temporal bounds, move/trim/speed mapping, track lock, CAS, HTTP viewer/editor/workspace/actor enforcement and reused provenance. Complete isolated Linux regression at clean **`bab4e24` passed 1,938 tests / 7 skips**, 591.90 s (`api-linux-bab4e24.log`). That checkpoint precedes this B-roll increment; its full-run result is not attributed to later code.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual PNG/video uploads with FFprobe, HTTP/SQLite UI selection and application, a playable FFmpeg H.264 540×960 visual proxy and decoded frame. MOCK TESTS: explicitly labeled synthetic ASR, tone footage and provider fixtures. No external/paid provider execution or publication.

EVIDENCE: `broll-render-evidence.json` contains source hashes, raw probe, rendered clip receipt, frame hash and exact recovery paths. Original non-B-roll tracks and 16s duration compare equal to timeline v1; only v2 B-roll was added. Actual videos, exports and cost records remain in recovery `broll-render-r1/r2`; runner `scripts/north_star_broll_evidence.py` requires a fresh output folder and refuses unlabeled fixtures. `studio-wave3-visual/broll-evidence.json` plus screenshots at 1366/1920/2560 show no horizontal overflow, persisted blue image, v2 Draft and no console warnings/errors. Fixture `b1` retains the initial missing internal-media registration failure; `b2` retains an intermediate picker check. Final `b3` uses only local registered-media processing and contract-only unavailable providers. Browser viewport reset and tab closed; only the two verified fixture Python processes were stopped. Data/ephemeral auth files remain outside Git. The initial Node directory-style invocation failed on Windows; corrected explicit test-file expansion passes.

REGRESSIONS: previous accepted videos/live source/data/configuration remain untouched; Native 264/264, subtitle renderer 33/33 and six local-real caption encodes remain separately recorded earlier evidence. Full latest pre-B-roll Linux checkpoint is green. No main merge, live database migration/restart, production deployment or external publishing.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker and Phase 10 Owner UAT remain separate limitations; none blocks continued safe implementation.

OWNER ACTION REQUIRED: none. NEXT WAVE: complete remaining Mode B controls/Native integration and continue media intelligence plus subsequent safe waves.

## Wave 3/4 — absent semantic highlight factors

WAVE: 3/4

STATUS: IN PROGRESS. HEAD SHA: parent `94a7e3d898bbec58fbaa3976e6a20a0902cbf263`; this focused correction is separately committed.

CAPABILITIES COMPLETED: highlight scoring v3 excludes generic placeholder descriptions when scene evidence has no transcript or saved Vision. Information-density and keyword factors remain null instead of being scored from invented semantic content. All-absent observations yield zero available weight/score without division errors. Legacy caller-supplied descriptions remain explicitly labeled heuristics. Drafts record matching selected-transcript segments and preserve saved Vision descriptions when no speech segment overlaps.

CAPABILITIES PARTIAL: real spoken-source/provider and Native/final acceptance remain. TESTS: focused highlight/local-scene/combined-scene **16/16 PASS**, 21.51 s (`highlight-null-semantic.log`); final missing-text/saved-Vision contract **2/2 PASS**, 6.06 s (`highlight-null-contract-final.log`) after the last Vision-description preservation refinement. REAL PROVIDER TESTS: none. MOCK TESTS: saved synthetic ASR/Vision evidence; existing local FFmpeg scene tests remain labeled local-real.

EVIDENCE: scoring evidence includes `text_evidence_available`, its basis, missing factors and available weight; `test_visual_scene_signals.py` covers null placeholder/observed-text behavior. The full clean Linux B-roll checkpoint `94a7e3d` is running separately and is not attributed to this later correction.

REGRESSIONS: focused earlier highlight/scene contracts pass; accepted source/artifacts/live data untouched. EXTERNAL BLOCKERS: none for continued safe work. OWNER ACTION REQUIRED: none. NEXT WAVE: canonical still-image timing controls, remaining Mode B/Native integration and subsequent safe waves.

## Wave 3 — editable still-image duration and actor-bound timeline history

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. This increment completes supporting-image placement/duration control in API Studio; Native and complete spoken-source/final acceptance remain.

HEAD SHA: parent `521fcd290134338c1f388266e8da63b7dccb9b7b`; the image timing capability commit records this increment. Parent is pushed to the completion branch.

CAPABILITIES COMPLETED: image trim/property operations change display duration without source timestamps or playback speed. Temporal clips retain source-window/speed-derived timing. Duration is finite, positive and bounded; misplaced duration fields, fabricated image source windows and locked edits reject. The inspector shows an image-specific duration field. Create/edit/restore/preview HTTP writes record the authenticated principal rather than a caller-supplied actor. CAS, immutable history and preview/approval invalidation reuse the canonical repository. Browser image placement at 2s and display duration 4.25s survive undo, redo and reload.

CAPABILITIES PARTIAL: Native advanced/editor bridge, audio-complete preview parity, genuine ASR/Vision/provider acceptance and full Mode B A/V/final E2E. The rendered local proxy remains visual-only and does not certify Owner UAT.

TESTS: **47/47 focused API PASS**, 89.29s (`still-image-api-r1.log`); **94/94 Studio PASS**, 466.61ms (`still-image-studio-r1.log`) and syntax check. New contracts cover image split/source invariants, temporal misuse, NaN/infinite/invalid bounds, locks, CAS, immutable restoration, stale previews, checksum preservation, HTTP authentication/viewer denial and forged actor rejection. Full clean Linux checkpoint `94a7e3d` is still running and is not attributed to later changes.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual browser HTTP/SQLite edits and reload at 1366/1920/2560; real FFmpeg H.264 visual proxy and decoded samples before/during/after the supporting image. MOCK TESTS: explicitly labeled synthetic ASR and tone/video fixture; zero external provider dispatches.

EVIDENCE: `still-image-timing-browser-evidence.json`, three viewport screenshots and `still-image-timing-render-evidence.json`. The five immutable versions verify apply v2, edit v3, undo v4 equals v2 and redo v5 equals v3. Primary/audio/subtitle tracks and 16s master duration compare unchanged; original asset hashes are verified. Decoded blue-image mean RGB during placement is [11,9,115], while source frames before/after differ. Actual proxy hash is `2cdaf5b7daa160744b6829993c992a4d58d051444ab1c685186cec808c39242a`; complete exports remain in recovery `still-timing-render-r1`. Runner `scripts/north_star_still_timing_evidence.py` verifies only the explicit synthetic fixture history and never calls a provider. No horizontal overflow or browser warning/error occurred. Test tab closed and viewport reset; only the two exact verified fixture Python processes were stopped; `C:\vf-ui-fixture-b4` is retained outside Git.

REGRESSIONS: focused previous content/timeline/B-roll/approval contracts pass. Original live source, data/configuration and accepted artifacts are untouched; previous Native/renderer/full-Linux results remain separately identified. No main merge, production deployment or external publication.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker and Phase 10 Owner UAT remain separate limitations. OWNER ACTION REQUIRED: none for continued safe implementation. NEXT WAVE: remaining Mode B/Native integration, structured media intelligence and subsequent safe waves.

## Wave 3/6 — canonical source-audio preview

WAVE: 3/6

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Source-audio preview is implemented in API Studio; Native and complete final acceptance remain.

HEAD SHA: parent `cb924d5484a0c5799e59f6fa472df47f11a2bb7d`; this audio-preview capability commit records the increment. Parent is pushed and preserved in verified `north-star-cb924d5.bundle`.

CAPABILITIES COMPLETED: preview v2 derives audio only from active canonical audio tracks. It applies source trim, sample-based placement, pitch-preserving tempo, clip gain, fade-in/out and overlapping sums with a latency-compensated -1dB limiter and no auto-gain. Muted/disabled/zero-volume clips require no fetch. Audio-only assets participate in worker downloads and every source checksum is verified. Actual FFprobe requires an audio stream and measured bounds. Missing/out-of-bounds sources fail. Tempo, clips, duration and Windows command size are bounded. Filter graphs use a file; only CLI parser rejection permits the older file-option fallback, never encode failure. Cancellation/timeout reap FFmpeg and remove partial output; stderr is drained while running. FFprobe cancellation also reaps its child. Studio reports current audio, historical silent and nonplayable fixture previews separately, with readable 14px status text.

CAPABILITIES PARTIAL: final subtitle/reframe/mixer parity, speech normalization/music ducking, renderer-profile cache identity, Native integration and genuine spoken-source/final E2E. Historical cached visual-only previews are retained; no ready/accepted artifact is replaced. Source-tone tests do not establish real speech recognition or Owner UAT.

TESTS: **51/51 focused API PASS**, 38.89s (`timeline-audio-preview-final.log`), including previous timeline/image/analysis/production/QC contracts. One subsequent cancellation contract passes **1/1**, 2.22s (`timeline-audio-cancel-contract.log`). The standalone parser-fallback contract previously passed 1/1 and is included in the broad 51. Studio **94/94 PASS**, 460.64ms (`timeline-audio-studio-r1.log`) plus final syntax check. Real tests verify source-window trim, placement gaps, decoded RMS gain, retained 880Hz pitch at 2x duration, mute/no-audio output, fades, overlap/peak limiting, out-of-range refusal and initial cancellation. Contract tests verify audio-only fetching/checksum failures, tempo limits, parser-only fallback and running-child cancellation. Initial test attempts found missing fixture source identity, a wrong fixed preview-size request and FFmpeg 9 removal of the legacy filter-file flag; each is retained and corrected. Full clean Linux checkpoint **`94a7e3d` passed 1,943 tests / 7 skips**, 580.12s (`api-linux-94a7e3d.log`); that checkpoint precedes later semantic/image/audio changes and is not attributed to them.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual WAV/PNG/MP4/AAC encodes and decoded PCM; Studio HTTP/SQLite queue-to-download-to-browser decoding. MOCK TESTS: explicit fixture ASR and synthetic tone footage; zero paid/external calls.

EVIDENCE: `timeline-audio-render-evidence.json` verifies 16.0s stereo AAC/48kHz, canonical source checksum/timing, preserved primary/caption/audio tracks and actual proxy hash `fd3edf3e9667be0c84de2a2927440fe8e4983e31fcb8402d25b1ac804b533d4e`. Decoded expected quiet windows have RMS 0; source-tone window RMS is 0.06246. Full exports remain in recovery `timeline-audio-render-r2`, with earlier rejected flag run retained in r1. `scripts/north_star_preview_audio_evidence.py` only measures the labeled isolated fixture. Browser fixture p1 lacked download dependencies and did not load media; it is retained with its screenshot outside Git. Corrected p2 decoded 540x960/16s with readyState=4 and no media error at all three widths. Final p3 verifies readable status text. Fixture ASR is not real-provider acceptance; the preview has no captions and is not final-render parity.

REGRESSIONS: focused existing production/approval/QC/analysis/timeline contracts pass; original live source remains clean at its original HEAD. Source media, accepted artifacts, live data/configuration are untouched. No main merge, live migration/restart, production deployment or external publication.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker and Phase 10 Owner UAT remain separate. OWNER ACTION REQUIRED: none for continued safe implementation. NEXT WAVE: Native canonical workflow integration and remaining structured media/provider/audio/downstream waves.

Implementation references: [FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html) for sample-based delay, tempo, mixing and limiter latency/level controls; [FFmpeg option documentation](https://ffmpeg.org/ffmpeg.html) for loading filter arguments from files. This local implementation does not certify other deployment runtimes.

## Wave 3/4 — Native source-analysis and immutable transcript integration

WAVE: 3/4

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Native analysis/history are implemented; canonical application and final Mode B workflow remain.

HEAD SHA: parent `5fd3fa518cc02043a4b66c1dc2a8484fe07fa41b`; this capability commit records the Native increment. Parent is pushed and preserved in verified `north-star-5fd3fa5.bundle`.

CAPABILITIES COMPLETED: Native local analysis jobs reuse shared FFprobe, FFmpeg scenes, silence, waveform and measured pixel observations. Structured scene fusion is extracted into a pure shared module; the API persistence adapter retains its contract. Native uses its existing project store/history and job queue, with no API database, second project or timeline. Saved source-bound ASR receipts normalize to the existing Transcript/Segment/Word DTOs; this job dispatches no ASR, AI or paid provider call. Source checksums are verified before measurements and checkpoint reuse. Job idempotency, busy/revision guards and durable checkpoints remain active. Results append immutable original evidence; transcript revisions preserve originals and unchanged word alignment, discard changed alignment, use session actor identity, support optimistic conflicts and restore-as-new. Reads re-score current transcript text against saved physical evidence and protect full edited segments. Missing ASR blocks silence decisions. Duplicate projects retain source receipts but require their own project-bound local analysis. Native Assets adds capability-gated transcript editing/history and scene, silence and Top 3/5 views.

CAPABILITIES PARTIAL: Native evidence-to-canonical timeline application, silence/highlight selection, Auto Shorts, source-audio preview/final renderer, language-detecting ASR adapter and complete UI Mode B flow remain. Browser usability at 1366/1920/2560 is NOT VERIFIED for this Native panel: Chrome blocked the isolated 8047 URL with ERR_BLOCKED_BY_CLIENT before loading the document, including one reload. Browser protections were not bypassed. This does not supersede previous API Studio/Phase 10 UX evidence.

TESTS: Native **272/272 PASS**, 141.448s (`native-auto-edit-full-r1.log`), including accepted Phase 8/9/10 regression contracts. Focused HTTP + analysis **20/20 PASS**, 13.612s (`native-auto-edit-http-r1.log`); final checksum/checkpoint guard **7/7 PASS**, 1.205s (`native-auto-edit-final.log`). Studio **98/98 PASS**, 465.9473ms (`native-auto-edit-studio-r1.log`) and syntax checks. Shared scene/analysis API **17/17 PASS**, 48.21s (`native-scene-fusion-api-r2.log`). Its initial Windows run had 15 setup errors because the default pytest temporary directory was inaccessible; a fresh named basetemp resolves this without changing user files. Full clean Linux API checkpoint **5fd3fa5 passed 1,975 / 9 skips**, 553.16s (`api-linux-5fd3fa5.log`); it precedes this Native increment. Linux fetch used the verified bundle because Windows worktree pointers cannot resolve through WSL.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual Native SQLite/job/checkpoint/FFprobe/FFmpeg analysis of synthetic MP4/AAC, waveform and frame measurements; source drift rejects checkpoint reuse. MOCK TESTS: explicit saved ASR fixtures, immutable edit/restore, no-op, CAS, missing-transcript policy, source/actor/timing rejection, duplicate-project scoping and authenticated HTTP boundaries. Fixture narration does not establish real speech recognition or Owner UAT.

EVIDENCE: `native-analysis-evidence-n2.json` binds the isolated Native fixture to source SHA256 `86807ba66900c3bc9fee111db29e9314074c72c49e19f042c7585f158c8a9b1a`, 120 waveform bins, 12 measured frames, one scene and saved fixture ASR. Full analysis/project/job exports are hash-indexed in recovery `native-analysis-n2`. The blocked browser screenshot is retained in recovery `native-analysis-browser-blocked-n2.png`, not counted as UI acceptance. The initial fixture n1 rejected a data root containing its own secret path; n2 uses separate absent secret paths. Fixture servers/tabs are closed and temporary viewport overrides reset.

REGRESSIONS: source media/accepted artifacts and the original live repository remain untouched. Existing narrated canonical timeline schema and projections remain unchanged. No protected-main merge, live migration/restart, production deployment, external publication or new paid operation.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker, Phase 10 Owner UAT and current Native browser navigation remain separate limitations. OWNER ACTION REQUIRED: none for continued safe implementation. NEXT WAVE: apply reviewed source-footage decisions to the same Native canonical timeline; complete preview/render and remaining safe media/provider/downstream waves.

## Wave 3 — Native canonical source-footage timeline

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Canonical source-footage persistence/REST editing are implemented; complete non-developer UI/preview/approval/render acceptance remains.

HEAD SHA: parent `72c151074ff806ba1a705fb25cf940abc2a21210`; this source-timeline capability commit records the increment. Parent is pushed and preserved in verified `north-star-72c1510.bundle`, SHA256 `c6aafc570c21d74ac624f81e0fa597bd76a37e012ae49f62c45e12203ca5845d`.

CAPABILITIES COMPLETED: an opt-in source-footage schema persists in the existing Native `canonical_timeline` field and immutable project history. Narrated projects retain their schema. The shared timeline builder creates measured source video, original audio and transcript captions; no synthetic narration/proposal is required. Creation requires a separate media project and exact saved source/transcript identity. Only explicitly selected safe silence IDs apply; default creation keeps footage. Selected highlight/source windows reuse the same pure complete-speech boundary helper as API Studio. Four canvas shapes are validated. Shared operations support trim/split/move/delete/duplicate/disable/reorder, properties and track lock/mute with revision/timeline CAS, source bounds, rollback and restore-as-new. Native shot reads project the same snapshot. Source-mode transcript edits require timeline CAS, update canonical cues atomically and preserve media/audio edits; locked captions roll transcript and timeline back together. Session actor identity cannot be supplied by the client. Legacy content/TTS render, legacy shot mutations and silent preview are guarded for source-mode projects. Adding source assets preserves the canonical snapshot.

CAPABILITIES PARTIAL: source-footage preview/final render/approval, complete shot/advanced UI controls and linked multi-track source operations remain. REST track operations currently edit each selected track independently. Source-project duplication requires proper evidence/transcript/timeline rebinding and is explicitly refused while that implementation is incomplete; narrated/evidence-only duplication still passes. The source creation route is not yet exposed as a completed UI flow. Native browser verification remains unverified after the prior blocked navigation. These are implementation gaps, not credential blockers.

TESTS: full Native **279/279 PASS**, 120.743s (`native-source-timeline-full.log`), including Phase 8/9/10 suites. Focused source/analysis/shot/render/HTTP **62/62 PASS**, 48.479s (`native-source-timeline-r2.log`). Extended HTTP source-create/edit/security contract **1/1 PASS**, 1.223s (`native-source-timeline-http-final.log`). Final source guard tests **7/7 PASS**, 2.106s; after pure shared-helper extraction **7/7 PASS**, 1.391s (`native-source-timeline-shared-helper.log`). Shared API highlight drafts **7/7 PASS**, 6.10s (`native-speech-window-api.log`). Studio **98/98 PASS**, 459.9307ms (`native-source-timeline-studio.log`). Initial source tests had one fixture error: padding reduced a nominal quiet interval below the configured minimum; the corrected fixture provides a genuinely long enough interval and the production threshold remains unchanged. Earlier failure is retained in `native-source-timeline-r1.log`.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: Native SQLite/history and local FFmpeg measurements on preserved synthetic source footage. MOCK TESTS: source-bound saved ASR, canonical audio/caption construction, word protection, four shapes, explicit cuts, lock/mute/trim/source-bound guards, CAS, restore, locked-caption rollback and authenticated HTTP. No video render or Owner approval is claimed for this increment.

EVIDENCE: `native-source-timeline-evidence.json` binds a fresh isolated project to the unchanged six-second source hash `86807ba66900c3bc9fee111db29e9314074c72c49e19f042c7585f158c8a9b1a`. Requested 0.3–1.1s expands to fixture word bounds 0.2–1.2s, producing a 1.0s 1080×1350 canonical draft with original audio track. A subsequent transcript revision updates canonical version 2, discards changed caption alignment and leaves the source project and raw receipt untouched. Hash-indexed timeline/transcript/analysis/project/job exports remain in recovery `native-source-timeline-n2`. Preview/final/UI/provider/UAT/deployment readiness are explicitly false in that evidence.

REGRESSIONS: accepted narrated projects and artifacts retain their original path/schema. Original live repository/configuration/data/services are untouched. No external provider/publishing call, new paid operation, deployment, protected-main merge or destructive migration.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker, Owner UAT and blocked Native browser navigation remain separate. OWNER ACTION REQUIRED: none for continued safe work. NEXT WAVE: Native source preview/render and shot/advanced editor integration, followed by remaining media/providers/downstream waves.

## Wave 3/6 — Native canonical source-audio preview

WAVE: 3/6

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Native source proxy transport is implemented; complete source final render/approval and non-developer editing UI remain.

HEAD SHA: parent `74ab241307e01901149835da00b27e0ef128e76e`; this capability commit records source preview integration. Parent is pushed and preserved in verified `north-star-74ab241.bundle`, SHA256 `b58121e6231b756c7dc50b8a5746021c87fd330d2e200fdb3d339e62d58e94bb`.

CAPABILITIES COMPLETED: FFmpeg proxy render classes move into a pure shared module; API imports retain compatibility and a fresh subprocess verifies no repository or SQLAlchemy dependency. Native source previews resolve the same canonical snapshot/assets in the existing store, validate source windows/checksums/paths/rights, reuse original-audio trim/speed/gain/fade/placement/limiter behavior, and dispatch no TTS/ASR/external provider. A separate renderer profile binds the cache to project revision and timeline hash while preserving old silent narrated proxies. Durable cancellation, interrupted-worker policy, explicit retry, source drift rejection, checksum-verified video/manifest playback and current-revision invalidation remain. Preview leaves project/approval/history/source bytes unchanged. Studio accepts a source proxy only with its matching manifest/profile/version and labels original audio and omitted final effects.

CAPABILITIES PARTIAL: this proxy omits captions, smart-reframe keyframes, speech normalization and music ducking; final-render parity and approval eligibility are explicitly false. Native complete shot/advanced source editing, final render/QC/approval, duplication rebinding, music intake and genuine spoken-source UI E2E remain. Current Native browser acceptance remains NOT VERIFIED after the previously blocked isolated URL; no browser success is claimed by these transport tests.

TESTS: full Native **283/283 PASS**, 153.527s (`native-source-preview-full.log`), including Phase 8/9/10 regression suites. Focused Native source/canonical/legacy-render **23/23 PASS**, 33.640s (`native-source-preview-r1.log`). Final five source tests, including fresh import isolation and truthful muted-audio receipts, **5/5 PASS**, 5.182s (`native-source-preview-final.log`), cover the final receipt-only refinement after the full-suite launch. Shared API audio/reframe **31/31 PASS**, 15.86s (`native-source-preview-api-r2.log`); related analysis/multi-input/B-roll/silence **39/39 PASS**, 70.66s (`native-source-preview-api-r3.log`). Studio **99/99 PASS**, 522.515ms (`native-source-preview-studio-r1.log`). The initial API command referenced a nonexistent test filename and ran no tests; the corrected explicit suites pass and the initial log is retained.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual FFmpeg MP4/AAC, canonical source window/duration/geometry, decoded PCM audible placement, track mute, source hash drift, Native SQLite non-mutation and durable cancellation/retry. MOCK TESTS: saved ASR, cancellation barrier, version/profile/manifest/approval UI gates and import-isolation assertion. Synthetic tone and saved fixture ASR do not establish speech recognition quality or human UAT.

EVIDENCE: `native-source-preview-evidence.json` hashes full exports in recovery `native-source-preview-n2`. Preview MP4 SHA256 `7077456364a2004d4a194e71d7e5e4e3e87b3d02f55331620b3d2df66ffbbd8c`: 432×540, 1.0s, decoded RMS 0.0279108881. It derives from preserved source hash `86807ba66900c3bc9fee111db29e9314074c72c49e19f042c7585f158c8a9b1a` and canonical version 2/hash `9c1aa32feac84757a381e18e3d1c871ee6c19ba29952edf9f43535dff2af93bf`. Full preview receipt, render manifest, timeline, FFprobe and measured audio analysis are retained. Final/UI/provider/UAT/deployment readiness remain false.

REGRESSIONS: accepted narrated media/canonical schema, original live repository/data/configuration and live services remain untouched. No protected-main merge, production deployment, external publishing, new paid operation or destructive migration.

EXTERNAL BLOCKERS: real-provider acceptance, Docker, Phase 10 Owner UAT and current Native browser navigation remain separate limitations. OWNER ACTION REQUIRED: none for continued safe implementation. NEXT WAVE: source final render/approval and linked shot/advanced editor integration; then continue the remaining media/provider/downstream waves.

## Wave 3/6/15 — Private Native renderer transport

WAVE: 3/6/15

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. A working private renderer transport is added; Native source job/approval/QC wiring remains.

HEAD SHA: parent `6a1d71d3407c64026a2527a0dcb76e9f769cb22b`; this transport capability commit records the increment. Parent is pushed and preserved in verified `north-star-source-preview.bundle`, SHA256 `bccfe2c68d07fe771539a1ac61178d86287c760494c983034a702b297c35bc00`.

CAPABILITIES COMPLETED: the new private renderer entry point validates a timeline manifest before media execution. It serves only explicitly staged job media through random-token routes on an ephemeral loopback port, with Range playback, no render HTTP API and no static exposure of the Native database, raw manifest or other job files. External/cross-job/metadata paths and media junction escapes reject; existing outputs are preserved. Media serving closes on success and failure. CLI logs use allowlisted progress/receipts/errors without caption text, paths or signed URLs. Injected test engines are marked fixtures. A Native-specific encode profile produces limited-range YUV420p/BT.709, H.264/AAC and 48kHz; existing API engine defaults remain. Version 2.3 gains English, source edits up to 600s and intentionally absent captions; both Zod and JSON Schema preserve earlier-version limits. Shared planning no longer imports the optional API JSON Schema library when loaded in the locked Native environment; API validation and renderer validation remain.

CAPABILITIES PARTIAL: Native source final-render jobs, preview-bound human approval, durable source-render checkpoints, full QC, linked source UI and complete E2E are not yet wired. The low-level local encoder does not create a project approval or final-review decision. Real speech, provider and Owner acceptance remain separate. These are implementation gaps and safe work continues.

TESTS: renderer type checks PASS and **38/38 tests PASS** (`native-renderer-profile-tests.log`, 1.51s), including existing captions/reframe/render contracts and four private media/scope/Range/junction/cleanup cases. Shared API production/subtitle/extended contract **7/7 PASS**, 7.98s (`native-renderer-contract-api-final.log`). Earlier test-only fixtures expected raw JSON Schema exceptions rather than the validator's wrapped domain error; corrected assertions preserve rejection semantics. Initial long-duration fixture incorrectly retained image source timestamps; the corrected video fixture passes. All earlier failure logs remain in recovery.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual private Remotion/Chromium encode from retained synthetic Native source/timeline, measured H.264/AAC/48kHz/YUV420p canvas/duration and visually inspected Vietnamese caption. MOCK TESTS: injected nonplayable engine outputs are explicitly marked fixtures; security, old/new contract and failure/cleanup boundaries. The first Native script import revealed a missing API-only JSON Schema dependency; lazy explicit validator import resolves this without installing into the locked environment. The first encode was retained but its evidence-frame extraction used FFmpeg's rejected `.35` timestamp; the corrected fresh r2 uses `0.35`. The first encoder also revealed full-range YUV output, leading to the separate explicit Native profile; historical media/defaults are preserved.

EVIDENCE: `native-private-render-evidence.json` hashes recovery `native-private-render-r2` files. Actual MP4 SHA256 `96c756646a6fb87d3254a89bb8c21a7d05efea51b57e0cd1a4f906cfd8511cc1`, 1080×1350 at 30fps; measured container duration 1.045333s for a 1.0s video timeline (AAC padding is measured, not hidden). Caption frame clearly retains “Vang Nguyễn chào bạn.” in the safe area. Canonical hash `9c1aa32feac84757a381e18e3d1c871ee6c19ba29952edf9f43535dff2af93bf` and original source hash `86807ba66900c3bc9fee111db29e9314074c72c49e19f042c7585f158c8a9b1a` remain unchanged. Manifest, mixed PCM, staged source, renderer receipt/process log, probe and caption frame are retained externally. Final QC/UI/Owner/provider/deployment acceptance are false.

REGRESSIONS: prior accepted media, original live source/configuration/database/services and earlier render manifest versions remain preserved. No protected-main merge, deployment, external publishing, paid/provider request, destructive migration or runtime install.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker, Phase 10 Owner UAT and Native browser navigation remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: integrate private source renderer into Native approval/worker/checkpoint/QC flow, then source shot/advanced UI and remaining North Star waves.

## Wave 3/6 — Native source approval, final worker and QC

WAVE: 3/6

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Native source approval/worker/checkpoint/QC are implemented; complete source UI, audio DSP and genuine spoken-source acceptance remain.

HEAD SHA: parent `88bb3b1310d2939355aa9631fbee486704896a1d`; this capability commit records the source worker increment. Parent is pushed and preserved in verified `north-star-private-render.bundle`, SHA256 `f8942bffc3e66c7d39363ebae4666dd68eba60ac7694a53e4137a857e2198c5e`.

CAPABILITIES COMPLETED: explicit source pre-render review binds an actual current proxy, video/manifest checksums, canonical timeline version/hash and project revision. Enqueue and worker execution revalidate that binding and immutable source bytes. The existing Native job/store/approval/history path encodes original canonical audio and Vietnamese captions through the private renderer, with no narration/provider dispatch or second database. Final checkpoints bind artifacts to the same input/approval. Full measured resolution/fps/codecs/audio/A-V/black/freeze/decode/subtitle/timeline and pixel-sampled QC run before artifact registration. Decoded PCM verifies the trailing activity interval without claiming speech detection. Hard failures persist attempt QC evidence and transition to failed_qc/FAILED_QC without a ready final checkpoint. Explicit canonical muting permits intentional silence while retaining visual and codec checks; absent/nonfinite audio metrics serialize as null. Cancelled QC subprocesses are killed and drained. Successful encoding still requires separate explicit watch/listen final-video review before final download.

CAPABILITIES PARTIAL: Native source creation/linked shot/advanced editing UI, proxy/final effect parity, source-project duplication rebinding, speech normalization, music ducking, genuine source ASR/semantic Vision and complete Mode B E2E remain. The current proxy omits final captions/reframe/DSP, and the approval receipt retains that limitation plus mandatory final-video review. Existing Owner approval states are not changed. These are safe implementation gaps; none is waived by unavailable credentials.

TESTS: full Native **288/288 PASS**, 153.630s (`native-source-worker-full.log`), including Phase 8/9/10 regressions and the positive mock final-review/tamper case. Focused Native source/canonical/legacy workflow/Phase 10 HTTP **48/48 PASS**, 46.506s (`native-source-worker-r2.log`). API production/extended render contract/canonical audio/QC lifecycle **25/25 PASS**, 16.44s (`source-worker-api-r3.log`). Studio **99/99 PASS**, 449.0702ms (`source-worker-studio-r1.log`). Clean Linux API at parent `88bb3b1` **1,976 PASS / 9 SKIP**, 557.11s (`api-linux-88bb3b1.log`); it precedes this worker/QC increment. The initial source test incorrectly expected no analysis job in history; corrected assertion verifies no new job after rejected enqueue. That first run had eight passing tests and one assertion failure, retained in `native-source-worker-r1.log`. The initial API temp path exceeded Windows path-length limits; a shorter fresh isolated temp directory resolves it. An intermediate rerun lacked its parent directory; all failure logs are retained. Production rules were not loosened to pass fixtures.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: immutable Native intake/SQLite/job flow, measured FFmpeg source analysis and AAC proxy, actual private Remotion source encode and full FFprobe/FFmpeg QC, checksum checkpoint replay and retained source/project non-mutation. MOCK TESTS: saved ASR, explicitly automated synthetic pre-render review, QC rejection, stale/missing approval, missing preview, disabled/muted-audio policy, finite metrics and subprocess cancellation. Positive final approval is tested only as an explicitly named mock review; the retained worker bundle deliberately leaves final video unapproved. No Owner UAT or real speech recognition is inferred.

EVIDENCE: `native-source-worker-evidence.json` hashes 21 exports in recovery `native-source-worker-n3`, including final/preview, canonical timeline, transcript/scenes/highlights/silence decisions, source provenance, subtitles/audio analysis, manifest, QC, job events, costs and checkpoint. Actual final SHA256 `2ff273490f4f1117893a976b2e43256dfb042480ddf2377c0db537e4c999740f`: 1080×1350 at 30fps, H.264/AAC/YUV420p/BT.709/48kHz. Video is 3.0s; measured AAC/container duration is 3.050667s and A/V delta 0.051s. No measured black/freeze/broken frames; decoded tone activity and silence are reported explicitly. Caption frame visually retains “Xin chào.” in the safe area. Source SHA256 `63a8ac09149832792ef6780e77eed41b370188937550424aae9763f47da6e361` and canonical hash `5ac5b0d55d1013ca52920a100ea15f065a7c943f1cefd91728f6648a12bd2a75` remain bound. Final download correctly rejects `HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED`. Full Artifact A acceptance, UI/provider/Owner/deployment states remain false.

REGRESSIONS: all 15 accepted Phase 8/9 original videos rehashed unchanged; original live repository, configuration, database, services and accepted media remain untouched. Existing narrated paths and final-review gates are preserved. No destructive migration, protected-main merge, production deployment, external publication, new paid operation or runtime install.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker, Phase 10 Owner UAT and blocked Native browser navigation remain separate. OWNER ACTION REQUIRED: none for continued safe implementation. NEXT WAVE: source creation/linked shot and advanced timeline UI, then remaining media/provider/platform/distribution/analytics/learning/Hub/hardening waves.

## Wave 3 — Native source selection, linked editor and caption controls

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Source creation and canonical source editing now have Native UI integration; browser usability and complete spoken-footage acceptance remain unverified.

HEAD SHA: parent `5822ad98c1da3bcc65a441f9d742918bf3f8269f`; this editor capability commit records the increment. Parent is pushed and preserved in verified `north-star-source-worker.bundle`, SHA256 `e7f5ee7ffb45311238fa858536318f50350ddb35c39428ca34c06510fda4b81d`.

CAPABILITIES COMPLETED: authenticated Source create/rebuild selects saved full footage or a ranked highlight and explicit safe silence decisions (unchecked by default). The shot-first Source inspector supports word-safe trim/split, ripple move/reorder, duplicate/delete/disable and speed while retaining linked original audio and retiming captions from saved provider intervals. Independent audio edits and affected locked tracks reject linked changes instead of being overwritten. Advanced independent tracks retain trim/move/split/delete/duplicate/disable, gain, mute/lock/disable, zoom, measured waveform, playhead/snapping and manual crop. Source UI format and caption controls persist the same versioned canonical timeline; seven full subtitle templates reject missing word alignment for timed effects. Exact snapshot restore-as-new plus separate document mutation audit enables undo/redo without polluting the restored hash. Existing explicit pre-render review controls move into Source video review; final watch/listen approval stays separate. Session capability controls loading of the new source modules and static dependencies. Legacy narrated paths remain available.

CAPABILITIES PARTIAL: current Native browser layout/usability at 1366/1920/2560 is NOT VERIFIED because isolated navigation was blocked before page load. Node tests and HTTP contracts cannot substitute for browser/Owner review. Source B-roll/music/audio DSP, subject tracking, proxy/final effect parity, Auto Shorts multiple drafts, source-project duplication rebinding and genuine spoken-source ASR/E2E remain. No Mode B readiness claim is made.

TESTS: full Native **298/298 PASS**, 161.112s (`source-editor-native-final.log`); frontend **103/103 PASS**, 683.88ms (`source-editor-studio-final.log`), plus JavaScript syntax checks. HTTP contracts verify authentication, static dependency scope, CSRF/CAS, linked trim and persisted caption/format choices. The initial history metadata polluted exact snapshot restoration; moving mutation audit outside the snapshot preserves exact restore. A no-audio test initially retained contradictory audio codec metadata; its fixture now reflects no stream. The earlier static analysis-label assertion was updated for current-source binding. Failed logs remain retained. Shared API Linux full regression at pushed parent 5822: **1,979 PASS, 9 SKIP**, 613.77s (`api-linux-5822ad9.log`).

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: real source intake, FFmpeg local analysis/proxy, linked trim and split, karaoke settings, private renderer worker and full measured QC on a separate synthetic fixture. MOCK TESTS: saved ASR and automated pre-render reviewer are explicitly marked fixtures; final human review remains unapproved. No paid/external/TTS operation.

EVIDENCE: `docs/north-star/native-source-editor-evidence.json` hashes 21 exports in recovery `native-source-editor-n4`. Project `83ab4dda6f2740b3b6dc2d6e4030aab9`, job `45080fa438884110b9e0f845439fcc98`. Final SHA256 `bcd9444f0468afc944189c3bddf10d24a6139b207244a8442a5a9bec4dfbc94c`, 1080×1350/30fps/H.264/AAC/YUV420p/48kHz. Timeline 2.4s, measured container 2.453s and A/V delta 0.053s; no measured black/freeze/broken frames. Vietnamese karaoke “Xin chào.” is visually inspected inside the safe area. Source hash `63a8ac09149832792ef6780e77eed41b370188937550424aae9763f47da6e361` and project document are unchanged by render. Final download correctly stays blocked without final review. Full Artifact A/UI/Owner/provider/deployment acceptance remain false.

REGRESSIONS: original live source/database/configuration/services and accepted artifacts remain untouched. No protected-main merge, production deployment, external publication, paid/provider operation, destructive migration or runtime installation.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker, Owner UAT and blocked browser navigation remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: canonical Source supporting media and licensed music/audio processing, followed by remaining media/provider/platform/distribution/analytics/learning/Hub/hardening waves.

## Wave 3/6 — Canonical Source music intake and playback

WAVE: 3/6

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Rights-attested music now plays through Source timeline/proxy/final render; Source DSP and B-roll remain.

HEAD SHA: parent `24e5e2cfbf285425363834517e996d6115e11c7b`; this music capability commit records the increment. Parent is pushed and preserved in verified `north-star-source-editor.bundle`, SHA256 `8a6832da9f6ed51f6a5a3cc0a0e8c789b7a037757e96554c218198d0d9aeb783`.

CAPABILITIES COMPLETED: existing WAV/MP3 intake, actual codec/probe/decode and immutable original/checksum/explicit rights attestation are reused. Source music is projected into the canonical asset resolver and a bounded editable audio track with saved gain/fades and duration-matched repetitions, without source stretching or narration generation. Proxy, approval and final-worker hash/path/rights checks include active music. Replacing music retains prior metadata and original bytes so exact timeline history restores still resolve the previous track. Locked music rejects replacement. Legacy narrated music behavior is preserved. Source UI enables music upload, directs track edits/muting to Advanced Timeline and explicitly states that automatic ducking is not yet wired. BPM, mood and energy remain null without measured evidence.

CAPABILITIES PARTIAL: Source normalization/ducking and seamless music crossfade, B-roll, structured subject tracking, full proxy effect parity, Auto Shorts/duplication and genuine spoken-source/browser/Owner acceptance remain. Synthetic tones are not identified as speech or real music-performance acceptance.

TESTS: full Native **301/301 PASS**, 160.988s (`source-music-native-full.log`); frontend **104/104 PASS**, 636.306ms (`source-music-studio-r1.log`). Focused source music/linked/canonical tests **17/17 PASS**, 4.369s. New cases cover actual local source/music proxy, preservation of source tracks/hashes/approval gate, locked/unknown-rights rejection and replacement/history restore. API production code is unchanged in this increment; an uncommitted opt-in DSP engine is tested separately and not counted as integrated capability.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: separate actual synthetic source/music intake, proxy, linked trim/split/karaoke, private worker and full QC. MOCK TESTS: saved ASR and automated pre-render reviewer explicitly fixtures; final review unapproved.

EVIDENCE: `docs/north-star/native-source-music-evidence.json` indexes 21 exports in recovery `native-source-music-n5`. Project `2e797396ee444b4488cd174578087e66`, job `ba68ba9804834f4b815a5432ef1c8592`. Final SHA256 `811c69b20412da1d42c33cbd086672d8601e04604c516df850518afbda656243`; 1080×1350/30fps/H.264/AAC/48kHz, 2.4s video and 2.453s container. QC reports no clipping, black/freeze/broken frames or accidental silence; activity remains explicitly decoded signal activity, not speech detection. Source/music/original hashes and canonical project document are unchanged by rendering; download remains blocked pending final review. Full Artifact A/UI/Owner/provider/deployment acceptance are false.

REGRESSIONS: accepted media and original live source/database/configuration/services remain untouched. No protected-main merge, deployment, external publication, new paid/provider/TTS call, destructive migration or runtime installation.

EXTERNAL BLOCKERS: provider acceptance, Docker, browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: opt-in Source normalization/ducking in settings, preview and final render; supporting-media planning/application and remaining North Star work continue.

## Wave 3/6 — Source audio normalization and music ducking

WAVE: 3/6

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Source DSP is implemented and locally measured; complete Mode B/production acceptance is not inferred.

HEAD SHA: parent `f8e2f60426352b7fe5cc5ac59afd438b2a00be4a`; this audio-processing capability commit records the increment. Parent is pushed and preserved in verified `north-star-source-music.bundle`, SHA256 `ae4f723f3705de1fb913d4fe5349b0481fc0f1becb88dc3c5663166e1364c585`.

CAPABILITIES COMPLETED: optional strictly typed Source settings default off, version the canonical document and invalidate prior preview/approval. A shared pure audio graph normalizes original/music clips before saved gain/fades, sums canonical role stems, applies actual original-energy music sidechain compression and a latency-compensated limiter, then preserves the exact PCM sample duration. Muted/disabled roles do not claim processing; short windows explicitly skip normalization. Locked affected audio tracks reject settings changes. Source proxy and final worker use the same graph; old API/default audio filters remain exact. UI settings, version binding and preview labels report actual DSP receipts. Processing follows the official [FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html), with single-pass loudnorm targets and explicit 48kHz resampling. The receipt does not fabricate measured integrated LUFS or semantic speech detection.

CAPABILITIES PARTIAL: repeat-boundary music crossfade/advanced transition UI, measured integrated loudness, dialogue-specific source separation and genuine speech/music balance acceptance remain. Source B-roll, automatic subject tracking, Auto Shorts/duplication, caption/reframe proxy parity and Native browser usability remain before Mode B readiness. Full rendered effects parity stays false.

TESTS: full Native **303/303 PASS**, 177.227s (`source-dsp-native-full.log`); frontend **105/105 PASS**, 772.34ms (`source-dsp-studio-r1.log`), plus syntax checks. API canonical processing/audio preview/production QC/Native render contracts **31/31 PASS**, 27.48s (`source-dsp-api-r2.log`). Focused Native settings/music/proxy **13/13 PASS**, 12.562s. Real PCM assertions verify music decreases during original signal activity without changing the original component, saved gain remains proportional after normalization, limiter bounds hold and the 48kHz sample count is exact. The first absolute mono-to-stereo amplitude expectation ignored standard channel conversion; the corrected test compares measured unprocessed baseline while retaining attenuation/source/gain/duration assertions. Its failure log is preserved.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: real FFmpeg PCM checks and separate Native synthetic source/music/DSP/linked-edit/karaoke proxy/private worker/full QC. MOCK TESTS: saved ASR/pre-render reviewer remain explicit fixtures; final review unapproved. No provider/TTS/paid operation.

EVIDENCE: `docs/north-star/native-source-dsp-evidence.json` indexes 21 exports in recovery `native-source-dsp-n6`. Project `1699d4bdd81e43fea3b4dea9a65a038b`, job `9f516cb6c05d49f58c6b09f9230faa1a`. Final SHA256 `c2cc3b7f769977aa4ec8fc4bac065754ac41e6a62fb2f4d35e19add5c9b2381d`; 1080×1350/30fps/H.264/AAC/48kHz, 2.4s video and measured 2.453s container. QC reports no clipping, black/freeze/broken frames or accidental silence; measured peak -12.7dB and mean -20.9dB are not described as LUFS. Five saved clip normalizers and actual energy ducking have receipts; source/project bytes remain unchanged, and final download stays blocked without final review. Full Artifact A/UI/Owner/provider/deployment acceptance are false.

REGRESSIONS: legacy narrated paths and accepted media, original live source/database/configuration/services remain preserved. No protected-main merge, production deployment, external publication, new paid/provider/TTS call, destructive migration or runtime installation.

EXTERNAL BLOCKERS: provider acceptance, Docker, browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: Source B-roll planning and placement, then automatic media intelligence/remaining North Star capabilities; full Linux API regression follows preservation of the shared proxy changes.

## Wave 3/6 — Native Source supporting-media plans and placement

WAVE: 3/6

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Source supporting image/video planning, explicit selection and canonical placement are implemented; complete Mode B and provider acceptance remain separate.

HEAD SHA: parent `c9da451dc378aaa035d42bbeb9814aadfd3c1180`; this supporting-media commit records the increment. Parent is pushed and preserved in verified `north-star-source-dsp.bundle`, SHA256 `73830bb6ed43c3ede7897d5d3424d3e46535764663a55f3212be3422137275f4`.

CAPABILITIES COMPLETED: Native reuses the pure shared MediaPlan builder and B-roll placement engine in its existing project/history store. Saved recommendations and choices leave the canonical timeline unchanged until explicit application. Immutable plan versions, checksums and deduplication bind source/transcript/registered assets; project/timeline/plan CAS prevents stale writes. Supporting images/videos map source placements through trim/split/reorder/speed, preserve original audio/captions, respect track locks and reject overlaps/duplicate application without explicit replacement. Image clips remain editable and exact snapshot restore retains all asset metadata. Unknown rights reject selection/application; owner upload attestation is attributed without claiming independent licensing verification. Authenticated/CSRF/origin-checked HTTP routes and Source inspector controls expose saved intent/query/placement/heuristic confidence, candidate/provenance, explicit choice, apply and replacement. Media upload returns the current Source projection, preserving Studio editing after supporting upload. No new schema migration, provider call or duplicate Native database.

CAPABILITIES PARTIAL: actual structured Vision relevance and tracked crops, configured official stock/generation tiers and outage fallback, richer scene/channel/brand inputs, planner query/window editing, supporting audio policy, Auto Shorts/source-project rebinding and genuine spoken-source/current browser acceptance remain. Native stock/AI/semantic Vision are explicitly NOT_CONFIGURED. Asset ranking uses saved filename/description/tag overlap with semantic confidence null; planning confidence is a labelled heuristic. Final proxy caption/reframe parity remains false.

TESTS: full Native **308/308 PASS**, 182.291s (`source-broll-native-full.log`); frontend **107/107 PASS**, 560.9549ms (`source-broll-studio-r1.log`), plus module syntax checks. Focused Native HTTP/supporting-media **18/18 PASS**, 13.766s (`source-broll-native-r5.log`). Shared API B-roll/media-intelligence **11/11 PASS**, 51.72s (`source-broll-api-r1.log`). Full isolated Linux API regression at parent c9da451 **1,986 PASS, 11 SKIP**, 635.70s (`api-linux-c9da451.log`); skipped real-FFmpeg/provider/deployment cases are not claimed passing. New tests cover rights/version/transcript/file drift, no-op deduplication, locked placement, split/speed mapping, explicit replacement, actual proxy, exact restore, escaped UI metadata and authenticated write boundaries. Early fixtures incorrectly assumed base Store projections and clip equality on the changed B-roll track, exposed a nested transaction lock, and tried current intake without rights confirmation; the corrected tests use explicit historical unverified metadata and exact source-track checks. Failure logs remain preserved.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual synthetic source/image/music intake, canonical proxy, private worker/Remotion encode and full measured QC. MOCK TESTS: saved ASR, nonplayable HTTP source and automated pre-render reviewer are labelled fixtures. Final video remains unapproved.

EVIDENCE: `docs/north-star/native-source-broll-evidence.json` indexes 22 exports in recovery `native-source-broll-n7`. Project `298271fb1c824c6ab19e8ba3d52f3663`, job `30c6988e9aea4392a2125720c9165d4a`; canonical SHA256 `4df188befa405aa0b74c3b9073467328d61a088d065a46ab5ab37bb4bc1610ff`. Final SHA256 `2df413b65b94ec9095ffbba0e27a9a1492bf027e477de96aa9de53939ae45133`; 1080×1350/30fps/H.264/AAC/48kHz, 2.4s timeline and 2.453s measured container. Supporting image and Vietnamese karaoke are visually inspected within the canvas. QC reports zero black/broken frames, clipping or accidental silence; measured freeze intervals are attributed to 2.4s intentional still media, with unexplained padding ratio 0.0216. Source hash `63a8ac09149832792ef6780e77eed41b370188937550424aae9763f47da6e361`, all retained asset/original hashes and project document are unchanged by rendering. Final download remains blocked pending final human review. Artifact A/UI/Owner/provider/deployment acceptance are false.

REGRESSIONS: original live source is confirmed clean; live database/configuration/services and accepted artifacts remain untouched. No protected-main merge, deployment, external publication, new paid/provider/TTS call, destructive migration or runtime installation.

EXTERNAL BLOCKERS: provider acceptance, Docker, blocked Native browser navigation and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: Source-project evidence rebinding, duplication and reviewable Auto Shorts drafts, then remaining media/provider/platform/distribution/analytics/learning/Hub/hardening work.

## Wave 3 — Source project duplication with rebound evidence

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Source duplication is implemented and locally rendered; Auto Shorts and full UI/provider acceptance remain.

HEAD SHA: parent `c9ad5d75db214571fa2ebb9a23d98643b59913e9`; this source-rebinding commit records the increment. Parent is pushed and preserved in verified `north-star-source-broll.bundle`, SHA256 `c15175aef638e44a24ca37802d485855b0565d1d77509037a184436c6d586244`.

CAPABILITIES COMPLETED: Native validates active file hashes and saved analysis/plan records before copying. An independent project receives new analysis/transcript/segment/word/scene/decision/highlight/plan/item/evidence identities and project-scoped fingerprints. Exact media/source timing, audio, crop, subtitles, locks and supporting-media decisions are retained; canonical history starts at version 1. Explicit lineage saves original document/record/transcript/plan hashes and attributes evidence reuse rather than a fresh provider measurement. Historical stale observations stay stale. Original raw ASR/media/history remain intact; the child has no approval, jobs, preview or final-review decision. Independent trims and plan replacement work. The existing Studio duplicate action is enabled for Source projects, still under revision/session/CSRF guards. No provider dispatch, database migration or media copy/overwrite.

CAPABILITIES PARTIAL: multiple-draft Auto Shorts, durable linked master/platform variants, structured Vision/automatic tracking, full caption/reframe proxy parity and genuine VI/EN speech/current Native browser/Owner acceptance remain. Rebound saved ASR does not certify new speech recognition or create provider evidence.

TESTS: full Native **312/312 PASS**, 171.280s (`source-duplicate-native-full.log`). Focused source duplication/HTTP/legacy workflow **41/41 PASS**, 22.753s (`source-duplicate-native-r2.log`); frontend **107/107 PASS**, 512.1096ms (`source-duplicate-studio-r1.log`), plus syntax check. New checks cover edited transcript/word-policy binding, independent edits, exact parent/history/source preservation, applied plan rebinding/replacement, stale evidence retention, corrupt active media/record rejection without partial child creation and authenticated duplicate writes. API production code is unchanged in this increment.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: separate actual synthetic Source/B-roll/music/DSP/karaoke duplicate proxy/private worker/full QC. MOCK TESTS: saved ASR and automated pre-render reviewer remain explicit fixtures; final review is unapproved.

EVIDENCE: `docs/north-star/native-source-duplicate-evidence.json` indexes 23 exports in recovery `native-source-duplicate-n8`, including the unchanged parent project. Parent `a18c99e290364177917899874a73cf41`, child `580d0d7023ae47b28082a916756ffcce`, render `97589f2a3d634a5aa71ee2cc81534728`. Rebound canonical SHA256 `a92de2bcdb57bbd839ed5c9e820d848e69660a5cb0264abbbc2662e04fb8382e`; actual final SHA256 `2df413b65b94ec9095ffbba0e27a9a1492bf027e477de96aa9de53939ae45133` is identical to the preceding independent supporting-media fixture. Identity-bound timeline/manifest/project receipts differ. Real canvas is 1080×1350/30fps/H.264/AAC/48kHz with 2.4s timeline and 2.453s container. Intentional still intervals explain static-image QC; source, parent and child documents remain unchanged by rendering, and final download stays blocked pending human review. Artifact A/UI/Owner/provider/deployment acceptance remain false.

REGRESSIONS: original live source is confirmed clean; live database/configuration/services and all accepted artifacts remain untouched. No protected-main merge, deployment, external publication, new paid/provider/TTS call, destructive migration or runtime installation.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker, blocked Native browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: reuse the existing complete-speech highlight draft engine for independent, reviewable Native Auto Shorts; remaining North Star waves continue.

## Wave 3 — Native Auto Shorts independent review drafts

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Native Top 3/Top 5 Auto Shorts now create independent reviewable drafts; semantic tracking, preview parity and genuine source/UI/provider acceptance remain.

HEAD SHA: parent `d50866696f8b55d7ccd5afdb5989eb9411046997`; this Auto Shorts commit records the increment. Parent is pushed and preserved in verified `north-star-source-duplicate.bundle`, SHA256 `84a9fdb41513daf132bd3fedaa1b09bb21ce3599dedf795fba4d2ac9d3546c88`.

CAPABILITIES COMPLETED: the existing complete-speech highlight builder/request/conflict types are extracted into a pure shared module; API persistence keeps its existing imports/contracts and behavior. Native scores exact selected transcript plus saved fused scene observations, considers up to five candidates and preserves whole words/unaligned segments at boundaries. Over-limit windows are skipped; identical windows deduplicate and absent candidates are not fabricated. One transaction creates independent unapproved Source projects, saves parent/binding/evidence lineage and batch history, and leaves parent timeline/approval/revisions untouched. Durable request-key/body hashes and deterministic child IDs make retries idempotent and reject changed-body reuse. Active hash/rights/path validation happens before each child; failure after a prior insertion rolls back all drafts/events/versions. Four canvases work; missing tracking explicitly marks center_crop/needs_attention with confidence null. New projects intentionally require their own B-roll/music/manual choices, preview and human approval. Authenticated API and Native Assets controls expose count/duration/format, saved batches and opening each canonical shot/timeline. The client retains an uncertain request key for retry; new project opening updates the local selection. No provider dispatch, new database or migration.

CAPABILITIES PARTIAL: calibrated semantic/audience highlight relevance, actual subject tracking, final caption/reframe proxy parity, durable master/platform variant linkage and genuine Vietnamese/English footage/ASR/current browser/Owner acceptance remain. Auto Shorts evidence does not infer that synthetic tone is speech. Center crop must be reviewed; it is not automatic subject tracking.

TESTS: full Native **318/318 PASS**, 183.116s (`source-shorts-native-full.log`); frontend **109/109 PASS**, 546.5915ms (`source-shorts-studio-r1.log`), plus syntax checks. Native focused source/HTTP contracts **19/19 PASS**, 14.094s (`source-shorts-native-r2.log`); source/duplicate **9/9 PASS**, 2.710s (`source-shorts-native-r1.log`). API existing highlight/transcript/B-roll **21/21 PASS**, 57.08s (`source-shorts-api-r2.log`); new whole-segment maximum-duration/no-evidence-mutation check **1/1 PASS**, 2.58s (`source-shorts-limit-r1.log`). Checks cover Top 3 vs fewer Top 5 candidates, complete-word boundaries, no inherited approval/jobs, exact parent/history/bytes, initial project without a canonical timeline, locks/version/transcript/body validation, atomic rollback after second-child failure, corruption rejection, persisted history/retry and no API database/repository dependency in Native import. Linux full regression follows the preserved shared extraction.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual synthetic footage intake/measured analysis, one-candidate Auto Shorts batch, rebound proxy/private worker/full QC. MOCK TESTS: saved ASR, shot-boundary/unit-domain and nonplayable HTTP fixtures, automated pre-render reviewer. Final human review remains pending.

EVIDENCE: `docs/north-star/native-source-shorts-evidence.json` indexes 23 exports in recovery `native-source-shorts-n9`, including complete batch and unchanged parent. Parent `7aa291de64374f2ab188b154b88d369e`, child `a158304ee35f532ab9b78f69dc655a14`, job `409fbd3a534f4381a6b366175b2e05ed`. Requested 3 candidates, generated/rendered 1; no extra candidate is fabricated from the single observed scene. Canonical SHA256 `fea695b24af58b7728c3ac10a7908c79bbd5b9e089707a67a64077f919dec021`; actual final SHA256 `13112e8ca435a699c64fe2b9d3ec10574d85e346f9b794cd76c681556bdbba16`. Measured 1080×1920/30fps/H.264/AAC/48kHz, 3.0s video and 3.051s container/A-V delta 0.051s. Vietnamese “Xin chào.” is visibly within the safe area; subject confidence remains null. QC has zero black/freeze/broken frames or clipping. Synthetic source's 2.051s tone-free intervals and 0.991s tail are measured and retained; this does not certify speech audibility. Source SHA256 `63a8ac09149832792ef6780e77eed41b370188937550424aae9763f47da6e361`, parent and child documents are unchanged by rendering. Final download stays blocked without final review. Artifact A/UI/Owner/provider/deployment acceptance remain false.

REGRESSIONS: original live source remains clean; live database/configuration/services and accepted artifacts are untouched. No protected-main merge, deployment, external publication, new paid/provider/TTS call, destructive migration or runtime installation.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker, blocked Native browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: structured Native media/Vision evidence and tracked reframing/preview parity, then remaining media-provider/platform/distribution/analytics/learning/Hub/hardening capabilities.


## Wave 3 — Versioned Native final-effects preview

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. The optional Source preview now uses final-render effects and exact canonical audio. Genuine source/provider/UI acceptance and automatic tracking remain incomplete.

HEAD SHA: parent `a581102e7838c17770ef01d5906afa7dede2fc49`; this preview commit records the increment. Parent is pushed and preserved in verified `north-star-source-shorts.bundle`, SHA256 `2208586776f77b363c999fb4f37f6216e8fbfd67ed8154980ebbd2be8596f9bd`.

CAPABILITIES COMPLETED: the versioned Source setting exposes lightweight and final-effects preview modes in the inspector. The new private preview reuses final composition, caption style/words/timing, canonical crop paths, transitions, supporting media and processed audio preparation, with Remotion scale 0.4 preserving full-canvas geometry. Actual outputs pass resolution/fps/H.264/yuv420p/AAC/48kHz/duration and complete decode checks. Source hashes are rechecked before registration. Profile-scoped project/revision/timeline cache identities and immutable manifests prevent historical proxy replacement. Selection invalidates approval/preview and participates in exact timeline history/restore. Owned-child cancellation/timeout stops only its process tree. Authenticated existing configure routes retain revision/CSRF/origin controls. Preview approval remains explicitly bound to its file/manifest/version; final dispatch still checks human approval and final video still requires separate watch/listen acceptance. Legacy lightweight receipts and approved source workflows remain compatible. No provider/TTS dispatch, new database or migration.

CAPABILITIES PARTIAL: reduced-resolution preview rendering props/audio match final, while full-resolution encoding, full QC and final human review remain separate. Semantic Vision/actual subject tracking, cached master/platform variants and genuine VI/EN footage/ASR/current Native browser/Owner acceptance remain. A crop-path test uses saved explicit manual fixture coordinates; it is not detected subject tracking.

TESTS: full Native **322/322 PASS**, 188.295s (`source-effects-native-full.log`); frontend **110/110 PASS**, 692.8939ms (`source-effects-studio-r1.log`), plus syntax checks. Renderer **39/39 PASS**, 2.80s (`source-effects-renderer-r1.log`) and TypeScript checks pass. Native existing proxy/settings **10/10 PASS**, 10.212s (`source-effects-native-r1.log`); new actual effects/crop/audio, approval/hash, historical mode-cache and owned-child cancellation **3/3 PASS**, 16.552s (`source-effects-native-r2.log`). Full isolated Linux API at parent a581102 **1,987 PASS, 11 SKIP**, 616.82s (`api-linux-a581102.log`); skips are not passing acceptance. This increment changes Native/renderer code only. First retained n10 evidence comparison rejected fresh derived cue identities although words/timings/styles and PCM matched; comparison now excludes only non-rendering cue IDs, and a fresh n11 run succeeds. n10/failure logs remain untouched.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual synthetic Source/B-roll/music/DSP/karaoke full-effects preview, private final worker and measured full QC, plus explicit manual crop-path render. MOCK TESTS: saved ASR and automated pre-render reviewer; final human review is pending.

EVIDENCE: `docs/north-star/native-source-effects-preview-evidence.json` indexes 27 exports in recovery `native-source-effects-preview-n11`. Project `a5fc7e42e54a43a1a5bf23365e91407b`, job `3ee377c9d3c249a8ab2fdac2431e1008`; canonical SHA256 `e4e29e991fe91ea3b9ef818c2060a5ff4f4940e4768607b51047011a63157899`. Actual preview SHA256 `dce031cbe9f207659efe69983332958eaf200023f9cf23f37394fd4f358a415a`, 432×540/30fps/H.264/AAC/48kHz; full composition/final 1080×1350, 2.4s timeline and 2.453s container. Vietnamese karaoke is visually inspected within the reduced canvas. Matching preview/final canonical PCM SHA256 `f1e44ba804c1f591838ebebf839dc09627f3e69e672d810a4106cfbac3f7030d`; all rendering effect props match after excluding independent cue identities/local media paths. Actual final SHA256 `2df413b65b94ec9095ffbba0e27a9a1492bf027e477de96aa9de53939ae45133` retains preceding source/B-roll fixture bytes. Full QC passes with intentional still intervals attributed; source/project document remain unchanged and final download remains blocked. Artifact A/UI/Owner/provider/deployment acceptance are false.

REGRESSIONS: original live source is confirmed clean; live database/configuration/services and accepted artifacts remain untouched. No protected-main merge, deployment, external publication, new paid/provider/TTS call, destructive migration or runtime installation.

EXTERNAL BLOCKERS: genuine provider acceptance, Docker, blocked Native browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: Native source crop-path/fallback controls, structured Vision/media evidence, then remaining provider/platform/distribution/analytics/learning/Hub/hardening capabilities.
