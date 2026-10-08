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


## Wave 3 — Native source crop-path review and four-ratio binding

WAVE: 3

STATUS: IN PROGRESS; AUTO_EDIT_MODE_READY = NO. Four-ratio center fallback and explicit manual crop paths are implemented; automatic provider tracking and genuine UI/source acceptance remain.

HEAD SHA: parent `f3cd011b1f295a29f377f3b1fbd4283015d90f9f`; this crop-path commit records the increment. Parent is pushed and preserved in verified `north-star-source-effects-preview.bundle`, SHA256 `baebc74e7b0a1dd3ab55867c483a01652e76731b7889541a07a2279805030e7a`.

CAPABILITIES COMPLETED: Native reuses the shared typed plan builder/crop binder without API persistence dependencies. Correcting shared binding keeps aspect_ratio and physical canvas consistent. Four canvases use measured source geometry; typed unique source-time points, normalized centers and bounded zoom create manual paths, while no tracking produces center_crop/needs_attention. Saved plans retain exact source checksum/analysis/geometry, provider NOT_CONFIGURED, tracking confidence null and explicit human-coordinate confidence attribution. Source locks, project/timeline CAS, rights/path/hash drift and invalid/extra fields reject without mutation. Original audio/captions/source bytes stay unchanged; paths survive linked trim/split/speed, duplicate evidence rebinding and exact restore. Ordinary canvas settings reject incompatible saved crop paths instead of silently stretching them. Authenticated existing timeline routes expose the new operation. Native numerical point rows support add/remove/edit, measured source-time limits, four ratios, explicit center/manual mode and separate unsaved trim/crop guards. Selecting a locked clip no longer disables unrelated global settings. Final-effects preview and final render include saved keyframes; both keep human review separate. No provider call, new database or migration.

CAPABILITIES PARTIAL: real subject/face/object tracking, semantic Vision safety/headroom and current Native 1366/1920/2560 browser usability remain. User crop coordinates are not provider observations. Genuine VI/EN uploaded footage/ASR and full non-developer Mode B/Owner acceptance remain.

TESTS: full Native **327/327 PASS**, 190.617s (`source-reframe-native-full.log`); frontend **111/111 PASS**, 578.652ms (`source-reframe-studio-r2.log`) and syntax checks. Native crop/settings **9/9 PASS**, 2.786s (`source-reframe-native-r3.log`); authenticated crop HTTP **1/1 PASS**, 0.859s (`source-reframe-http-r2.log`). Shared API reframe **13/13 PASS**, 14.95s (`source-reframe-api-r1.log`), including new aspect-ratio assertions in existing four-geometry cases. Prior full Linux API at a581102 remains **1,987 PASS, 11 SKIP**; this single shared binding fix has targeted API validation. Initial new fixtures used the wrong Native bootstrap import order, expected a generic stale error rather than the exact version code, and supplied unsupported job name analyze instead of asr; corrected fixtures/bridge import now pass, with failure logs retained.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual synthetic source/manual keyframes/music/DSP/karaoke full-effects preview/private final render/full QC. MOCK TESTS: saved ASR, explicit nonplayable HTTP source/analysis and automated pre-render reviewer. Final review remains unapproved.

EVIDENCE: `docs/north-star/native-source-reframe-evidence.json` indexes 27 exports in recovery `native-source-reframe-n12`, including `reframe-plan.json` and paired preview/final effect/audio receipts. Project `71d436cd349c4475825182c0714c1c89`, job `efeeaf46836f403ab41898f2f9c2113a`; canonical SHA256 `d52ac9db0715fc05c305ecc5bb9f195dea5266e9addcdb5febdc1ab079067c16`. Final SHA256 `fa2677439da380daa30eb52a6b0796f000b01c3a39b62fa8c9e247fa5df06b7e`; preview `a62d38617e51af1f027de1cbf400cad94f37c21a959bc0952dcfc391eee5bc3e`. Actual final 1080×1920 and preview 432×768, 30fps/H.264/AAC/48kHz, 2.4s video and 2.453s container/A-V delta 0.053s. Vietnamese karaoke is visually inspected inside the portrait preview. Matching rendering effect props and identical canonical PCM SHA256 `f1e44ba804c1f591838ebebf839dc09627f3e69e672d810a4106cfbac3f7030d` are verified. QC reports no black/frozen/broken frames, clipping or detected accidental silence; measured audio tail is 0.273s. Automatic tracking and speech detection remain false. Source SHA256 `63a8ac09149832792ef6780e77eed41b370188937550424aae9763f47da6e361` and document are unchanged; final download remains blocked. Artifact A/UI/Owner/provider/deployment acceptance remain false.

REGRESSIONS: original live source remains clean; live database/configuration/services and accepted artifacts are untouched. No protected-main merge, deployment, external publication, new paid/provider/TTS call, destructive migration or runtime installation.

EXTERNAL BLOCKERS: configured provider acceptance, Docker, blocked Native browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: structured Native media/Vision evidence and saved-evidence consumers, then remaining provider/platform/distribution/analytics/learning/Hub/hardening work.


## Wave 4 - Retained Native pixel observations and evidence consumers

WAVE: 4

STATUS: IN PROGRESS; MEDIA_INTELLIGENCE_READY = NO. Local measured frame evidence and physical ranking are implemented; semantic Vision and provider-driven tracking remain separate gaps.

HEAD SHA: parent `4834e959fc8ffacede353f1614044d0d1ca4dc40`; this media-frame capability commit records the increment. Parent is pushed and preserved in verified `north-star-source-reframe.bundle`, SHA256 `9741fdafa2e42329400ba95f9acb0dc10ba0dbe389b469cd4d945f936113dc84`.

CAPABILITIES COMPLETED: asynchronous Native CPU jobs save actual bounded PNG samples, source/project/job fingerprints, immutable checkpoints and typed measured pixel mean/stddev, luma fractions, Laplacian variance, black-sample and exact sampled-pixel duplicate facts. Sharpness/brightness rankings are explicitly uncalibrated; model confidence/calibration and unavailable semantic fields stay null. Requested seek times are recorded with decoded PTS unavailable. Persisting results increments project history and invalidates approval without changing the canonical timeline or raw ASR. Stale/wrong-job/forged-semantic results roll back; changed source/checkpoint/frame bytes fail closed. Recovery requires explicit resume and does not replay paid operations. Scoped session-authenticated HTTP serves only saved checksum-bound frames; Native Assets displays samples and review-only thumbnail suggestions. Scene/highlight views and Auto Shorts consume matching saved pixel evidence. Supporting asset lexical ranking uses measured physical quality only as a tie-breaker; evidence enters immutable MediaPlan fingerprints without relaxing rights gates. Project copies rebind evidence IDs/fingerprints while retaining actual immutable samples and explicit original-record lineage, with no fresh-provider claim. No new database, migration, provider dispatch or runtime install.

CAPABILITIES PARTIAL: structured semantic captions, scene descriptions, object/person detection, OCR, environment/action understanding, subject positions/tracks, safe crop, saliency, headroom, watermark/logo evidence, semantic B-roll relevance and semantic QC require a configured Vision provider and Native dispatch/approval integration. These fields remain NOT_CONFIGURED/null. Sampled duplicates do not establish full-video frozen-frame detection. Native browser acceptance at 1366/1920/2560 remains NOT VERIFIED after the prior client-side block. Genuine spoken source/ASR, Owner acceptance and full Artifact A/B/C remain incomplete.

TESTS: full Native **336/336 PASS**, 199.876s (`media-frames-native-full.log`); frontend **113/113 PASS**, 595.0604ms (`media-frames-studio-r2.log`) and syntax check passes. Focused Native frame/HTTP/Shorts/B-roll **19/19 PASS**, 32.522s (`media-frames-native-r3.log`); new extraction/HTTP **8/8 PASS**, 11.177s (`media-frames-native-r2.log`). API pixel/fusion/scene/B-roll **13/13 PASS**, 35.99s (`media-frames-api-r1.log`). Pixel math first run **2/2 PASS**. The initial static-image test used an 8px fixture below the existing 240px intake minimum; it was corrected to valid 320x240 source without weakening intake. The initial Node directory invocation failed to collect; the explicit rg-discovered file list passed. Prior failure logs remain retained.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual FFmpeg video/image pixels, isolated SQLite jobs/HTTP, same-effect preview, private renderer and full QC. MOCK TESTS: ASR/transcript/provider/approval fixtures; n13 pre-render reviewer is AUTOMATED MOCK, not Owner UAT. No semantic provider result is synthesized.

EVIDENCE: `docs/north-star/native-media-frame-evidence.json` indexes **41 exports** in recovery `native-source-frame-analysis-n13`, with nine actual samples over two assets, frame job/results, scene/highlight rankings, supporting plan, unchanged parent and source copy, timeline, processed audio, previews/final/QC/cost. Parent `254144d559d24072898102255bfed7ce`, child `3fcbd6dd2f324981b60f6fe4eb86965d`, final job `f6a16bfdb7b34eecbdcdcd1083178171`. Canonical SHA256 `8d80a9430870cb04922be9c52ec34c0fdcc3c585a34f0b6ab6e6ac8f73a496b3`; final SHA256 `2df413b65b94ec9095ffbba0e27a9a1492bf027e477de96aa9de53939ae45133`, identical to the earlier synthetic B-roll render. Preview SHA256 `dce031cbe9f207659efe69983332958eaf200023f9cf23f37394fd4f358a415a`; canonical PCM SHA256 `f1e44ba804c1f591838ebebf839dc09627f3e69e672d810a4106cfbac3f7030d`, identical preview/final. Video/image samples at 480x360/384x480 were visually inspected and match the synthetic source/illustration. Final download stays blocked without final review. Artifact A/UI/Owner/provider/deployment acceptance remain false.

REGRESSIONS: original live checkout remains clean at `2ced7bc81f9402368fb22c9e7aca242e740531af`; live database/configuration/processes and accepted artifacts are untouched. No main merge, production deployment, external publication, new paid/provider/TTS call, destructive migration or runtime installation.

EXTERNAL BLOCKERS: configured semantic/provider acceptance, Docker, Native browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: configured-provider architecture/consumers and legal stock/generative media adapters, followed by the remaining audio/profile/platform/distribution/analytics/learning/Trend/Hub/hardening work.


## Wave 5 — Official stock adapter contracts

WAVE: 5

STATUS: IN PROGRESS; GENERATIVE_MEDIA_READY = NO. Official stock architecture is implemented and mock-tested; Native integration and real provider acceptance remain open.

HEAD SHA: parent `03b94bfe08338236366b22be1aee1ee87803fcbd`; this separate stock commit records the increment. Parent is pushed and preserved in verified `north-star-media-frames.bundle`, SHA256 `d5e1ad86f21504fe5adc3773815ec8b38a5702cbd0d689ae212f7c7e62369b2f`.

CAPABILITIES COMPLETED: provider-neutral Pexels/Pixabay official image/video search, canonical get and bounded download methods; fixed authorized API paths, HTTPS/CDN allowlists, no redirect following, MIME/magic/size/timeout validation and safe retry hints without automatic replay. Durable checksum-bound 24h workspace caches survive restart and isolate concurrent scopes. Pixabay credentials are injected only at the transport boundary; neither adapter exposes keys in HTTPX logs, cache, settings serialization/errors or CDN requests. Candidates preserve selected-rendition dimensions, creator/source/license/attribution and null unavailable semantic/Vision relevance. Saved MediaPlan candidates survive persistence; worker materialization binds workspace scope and refreshes provider IDs instead of trusting caller URLs/rights. PNG/JPEG asset registration now uses image kinds instead of generated_video. Configured adapters are registered without exposing keys and their owned clients close during API/worker shutdown. Existing external/paid/global safety and publishing/production rights gates remain enforced. Mock transports identify their fixture evidence; production eligibility and real_provider_tested remain false.

CAPABILITIES PARTIAL: stock Native controls/import, complete downloaded-media decoding, actual official provider acceptance, independent rights records and credential/right admission remain. Planning ledger metadata describes provider traits rather than counting every request/cache hit/failure; uniform per-operation accounting is a Wave 8 gap. Configured status is not a live provider health check. Image/video generation modes, full ComfyUI lifecycle and playable provider acceptance remain open.

TESTS: API stock/media/planning/safety/B-roll **81/81 PASS**, 57.82s (`stock-providers-api-r7.log`); worker media queue/pipeline **27/27 PASS**, 4.18s (`stock-providers-worker-r1.log`); Native B-roll/Auto Shorts **10/10 PASS**, 9.472s (`stock-providers-native-r1.log`). New stock contracts alone first passed **18/18**, 3.77s (`stock-providers-api-r6.log`), then six asset-kind cases were added. Initial fixture failures were corrected to preserve the existing global configuration gate, register the provider in the isolated ledger and supply required worker capability/external/paid fields. The integration test also confirms the normal fail-closed controller prevents dispatch, even with an injected mock adapter. Failed logs r1/r3/r4/r5 remain retained. The complete Linux API regression at preserved parent 03b94bf passed **1,991 tests, 11 SKIP**, 634.07s (`api-linux-03b94bf.log`); skipped checks are not accepted evidence.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: isolated SQLite planning/persistence and CPU regression; no downloaded official media decoded. MOCK TESTS: all official endpoint, rate-limit, download and media payloads use explicit HTTP mocks; supplied image/video bytes are deliberately nonplayable contract fixtures.

EVIDENCE: `docs/north-star/stock-provider-contract-evidence.json` indexes exact source/test/log hashes and the official reference URLs. No credential was inspected or configured and no external stock, paid provider, publishing or GPU request was dispatched.

REGRESSIONS: preserved Native source workflows pass focused regression; original live checkout, database, configuration, services and accepted artifacts remain untouched. No main merge, production deployment, new runtime installation or destructive migration.

EXTERNAL BLOCKERS: authorized provider credentials/acceptance, optional GPU, Docker, Native browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe implementation continuation. NEXT WAVE: approved generative media/ComfyUI lifecycle and remaining semantic media, audio, profiles, platform, publishing, analytics, learning, Trend Radar, Agent Hub and hardening work.


## Wave 5 — Durable scoped ComfyUI lifecycle

WAVE: 5

STATUS: IN PROGRESS; GENERATIVE_MEDIA_READY = NO. CPU persistence/authentication/queue contracts are implemented; live generation and binary media acceptance remain open.

HEAD SHA: parent `aa59491c086f0cea08bd6d80d8455d40947b4cb3`; this separate lifecycle commit records the increment. Parent is pushed and preserved in verified `north-star-stock-providers.bundle`, SHA256 `6433269a3b00565f4c31ad8dd28c1e6fe5042210ebae9122492e4c055f00ce6a`.

CAPABILITIES COMPLETED: the existing bridge service now persists private requests, jobs, progress, definition/graph fingerprints, result JSON hashes and a content-free event audit in its own SQLite store with a single-owner lease. Bounded concurrency/waiting jobs/retained jobs/retries; explicit shutdown/restart recovery; offline terminal replay; no automatic resumed generation. Exact approved workflow drift, corrupted state and nested arbitrary graph/model-weight inputs reject. Deep returned copies prevent external state mutation; cancellation is saved before stopping its owned task. Service Bearer authentication and required workspace headers scope submissions and all list/read/event/cancel/retry operations. API/worker context scopes include workspace/project/resolution-job identity; mismatched or unsafe job responses reject before polling. SecretStr settings exclude service tokens, errors omit provider bodies/private inputs, clients avoid environment proxies/redirects. Compose defines a separate persistent bridge volume without adding it to CPU startup. Unknown GPU estimates/actual costs now remain null; configured unpriced resolution requires approval before queueing, while unconfigured NOT_CONFIGURED behavior remains compatible. Legacy numeric plan totals are lower bounds with explicit unknown-estimate flags. No migration of the accepted Native/API database.

CAPABILITIES PARTIAL: live GPU backend transport, owner-reviewed executable graphs, variation/image-to-image/inpaint/upscale/reference/video mode routing, provider progress/cost evidence, binary artifact registration/decoding and real GPU acceptance remain. Current result hashes validate metadata only. Native generation controls/admission, uniform per-operation accounting, backups/retention/production soak and actual Docker execution remain.

TESTS: bridge lifecycle/security/CPU contracts **19/19 PASS**, 2.01s (`comfyui-durable-r4.log`); API generation-scope/media/planning/safety/stock **60/60 PASS**, 30.04s (`comfyui-durable-api-r3.log`); worker media queue/pipeline **27/27 PASS**, 2.70s (`comfyui-durable-worker-r1.log`); Native B-roll/Auto Shorts **10/10 PASS**, 6.110s (`comfyui-durable-native-r1.log`). Initial tiny timeout fixture was corrected for Windows timer granularity without changing the saved workflow at retry. Cost regression first caught an overbroad approval rule for unconfigured providers; configured-state binding now preserves the original NOT_CONFIGURED path, and the passing rerun includes it. Failure logs r1/API-r2 remain retained. Full isolated Linux API at preserved aa59491 is **2,015 PASS, 11 SKIP**, 642.49s (`api-linux-aa59491.log`); skips remain unaccepted.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual isolated SQLite, file lease, integrity, restart and ASGI request handling. MOCK TESTS: all GPU execution/output, interrupted-state injection, HTTP adapter and result references are explicit contract fixtures; zero external/GPU/paid requests.

EVIDENCE: `docs/north-star/comfyui-durable-contract-evidence.json` indexes nine exports under recovery `comfyui-durable-contract-n1`, stable closed-store SHA256, source and successful/failure test logs. The script rejects existing/symlinked evidence directories. Artifacts include saved request/job/events, unauthorized/foreign-workspace HTTP receipts, offline replay, explicit interrupted-state recovery and retried job/audit. This is no generated binary media or Owner acceptance bundle.

REGRESSIONS: preserved Native source/editor flows pass focused regression; live source/database/configuration/services and accepted artifacts remain untouched. No protected-main merge, deployment, external publication, new provider budget, GPU infrastructure change or runtime install.

EXTERNAL BLOCKERS: optional GPU/models, authorized provider acceptance, Docker, Native browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for further safe implementation. NEXT WAVE: mode-specific generation/reference contracts, approved live backend/artifact architecture and remaining semantic media, audio/profile/platform/distribution/analytics/learning/Trend/Hub/hardening work.


## Wave 5 — Typed generation modes and approved envelope routing

WAVE: 5

STATUS: IN PROGRESS; GENERATIVE_MEDIA_READY = NO. All required request modes have manifest/bridge contract evidence; live generated media and Native integration remain open.

HEAD SHA: parent `ffc8ec111b800109da5b43e41ea3a02021186b35`; this mode-contract commit records the increment. Parent is pushed and preserved in verified `north-star-comfyui-durable.bundle`, SHA256 `e872383e48efdfbb76e982bad7cf0f289540e07b60e71c0ba724270074b359e0`.

CAPABILITIES COMPLETED: typed image-to-image/variation/inpaint/upscale contracts enforce required references, inpaint masks and 2x/4x factors. Video image/reference-assisted modes require references. Text requests with a reference select the image-to-image descriptor. Immutable copied mode routes preserve configured primary workflow overrides and reject invalid IDs/unknown mode keys. Each mode produces only approved input-envelope fields; legacy plain text-generation serialization/fingerprints remain unchanged. Provenance now saves actual routed model/workflow/version, requested/resolved mode, seed, references, mask/scale, null estimated/actual cost and measured local adapter elapsed time. Mode-specific namespace/binding checks remain workspace/project/job scoped. Nine request variants submit, persist and poll through the real ASGI bridge handlers/registry/SQLite using an explicit mock backend. No client graph or arbitrary asset download/read is performed.

CAPABILITIES PARTIAL: actual verified-reference staging, live backend transport and executable reviewed graphs; binary media registration/decoding, independent rights and actual GPU accounting; Native controls/approved budget integration and real provider acceptance. Local adapter elapsed time is not GPU execution time. Mock artifact references/checksum tokens are not generated media bytes.

TESTS: new manifest/mode/schema/provenance/legacy-fingerprint contracts **20/20 PASS**, 0.42s (`generation-routes-api-r2.log`); existing generation scope/media/planning **18/18 PASS**, 42.18s (`generation-modes-api-r1.log`); Native B-roll/Auto Shorts **10/10 PASS**, 6.087s (`generation-modes-native-r1.log`). Actual ASGI bridge mode bundle **PASS**, nine distinct saved jobs over all nine request variants, offline replay and explicit interruption recovery, eleven exports (`comfyui-generation-modes-n3.log`). Full Linux regression at preserved ffc8ec1 is still running and must not be reported as passed. The previous full aa59491 result remains 2,015 PASS/11 SKIP.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual isolated bridge HTTP/SQLite/metadata integrity. MOCK TESTS: all GPU execution/output and source/reference strings; no binary image/video created and zero external/GPU/paid provider calls.

EVIDENCE: `docs/north-star/generation-mode-contract-evidence.json` indexes the eleven immutable exports in recovery `comfyui-generation-modes-n3`, closed-store hash, source and test logs. The original n1/n2 bundles remain unchanged. The fresh n3 receipt pins executed-source hashes after failure-response sanitization. Generated-media readiness, Owner UAT and production deployment remain false.

REGRESSIONS: existing generation/Native source flows pass; live source/database/configuration/services and accepted media remain untouched. No merge/deployment/publication, new provider budget, GPU infrastructure change or runtime install.

EXTERNAL BLOCKERS: GPU/models/approved executable graphs and real-provider acceptance, Docker, Native browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: scoped verified-reference/binary artifact architecture and approved backend execution, then remaining media/audio/profile/platform/distribution/analytics/learning/Trend/Hub/hardening work.


## Wave 5 — Pinned reviewed graph compilation

WAVE: 5

STATUS: IN PROGRESS; GENERATIVE_MEDIA_READY = NO. Reviewed graph compilation is CPU-tested; live admission/backend/media acceptance remain incomplete.

HEAD SHA: parent `c71bbbe63e48cb3a95a8460981d21035b9f2aa9d`; this compiler commit records the increment. Parent is pushed and preserved in verified `north-star-generation-modes.bundle`, SHA256 `ca58d1be402c567dbb0960c999fa482e9b7ed330a151c0b9f91de96a2e1e8cc8`.

CAPABILITIES COMPLETED: optional typed manifest execution declarations bind graph SHA256, declared approval kind/reference, permitted node classes, exact scalar parameter/index/transform bindings, output nodes and approved dimensions. The compiler validates manifest identity/input schema, reads only the selected pinned source graph, preserves file bytes/node classes/unbound model choices and rejects changed hashes, absent nodes/bindings/outputs, incompatible transforms, non-scalar values and unavailable aspect dimensions. Image/mask inputs require typed matching workspace/reference/upload tokens; compiler performs no URL/local-asset lookup. Test graphs reject unless explicitly permitted. Checked-in placeholders have no execution declaration and remain NOT_CONFIGURED. Strict model base extraction keeps existing JSON contracts; omitting new null execution fields preserves historical workflow fingerprints exactly.

CAPABILITIES PARTIAL: declared approval references and token types do not independently prove Owner approval, uploaded bytes or rights. Live pinned-manifest admission, actual verified-reference staging, backend submit/poll/targeted cancel, artifact registration/decode/rights/cost and Native integration remain. No GPU work was dispatched and no model weights/executable repository graph were added.

TESTS: complete bridge/graph lifecycle/security CPU suite **29/29 PASS**, 2.35s (`comfyui-graph-compiler-r1.log`), including ten new compiler/binding/compatibility cases. Full isolated Linux API at preserved ffc8ec1 is now **2,021 PASS, 11 SKIP**, 689.84s (`api-linux-ffc8ec1.log`); skips remain unaccepted. This compiler change is confined to the bridge package.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual isolated pinned JSON file reads/checksum checks and unchanged bytes. MOCK TESTS: graph nodes, approval declarations and upload tokens are explicit non-executable fixtures; no independently verified asset/GPU/Owner acceptance is asserted.

EVIDENCE: `docs/north-star/comfyui-graph-compiler-evidence.json` indexes exact source/test/log hashes and the compatibility/null-execution assertions. Earlier n1/n2/n3 media-contract bundles remain unchanged.

REGRESSIONS: existing bridge auth/queue/restart tests remain passing; live source/database/configuration/services and accepted artifacts remain untouched. No merge/deployment/publishing, new paid/GPU operation, model install or destructive migration.

EXTERNAL BLOCKERS: reviewed executable graphs/GPU/provider acceptance, Docker, Native browser verification and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe source continuation. NEXT WAVE: admitted backend transport, scoped reference staging and binary artifacts, then remaining media/profile/platform/distribution/analytics/learning/Trend/Hub/hardening work.
## Wave 5 — Bounded official ComfyUI transport

WAVE: 5

STATUS: IN PROGRESS; GENERATIVE_MEDIA_READY = NO.

HEAD SHA: parent `6b5e4b3464b27fa65524224ed759892bbb375921`; this transport commit records the increment. Parent is pushed and preserved in verified `north-star-comfyui-graph-compiler.bundle`, SHA256 `ca2666722f4e93079ff3e6e9b1ce5e024a7b085689169b8ddb57e2fc10142822`.

CAPABILITIES COMPLETED: inert official wire client for an explicitly configured origin/source-pin profile; bounded submit/job/history/targeted cancellation, reference upload/no-overwrite/checksum readback, and typed PNG/JPEG/MP4 retrieval. URL/userinfo/path/plaintext-host restrictions, finite time/byte limits, isolated credentials, fixed failure codes and Retry-After normalization are enforced. No redirect, global interruption/queue clearing or automatic write retry exists. Lost/malformed/5xx submit results retain explicit dispatch uncertainty; repeated UUIDs do not establish deduplication. Foreign job/history bindings and upload mismatches reject. HTTPX is now a runtime dependency.

CAPABILITIES PARTIAL: client is not yet selected by the service backend factory. Durable dispatch/reconciliation, reviewed executable graphs, actual server pin verification, independent scoped reference rights/decode, binary media registration/full decoding, Native integration and actual GPU cost remain. MIME/magic checks are explicitly not decode evidence.

TESTS: complete bridge suite **60/60 PASS**, 2.23s (`comfyui-http-r2.log`), including **31** new HTTP/origin/error/upload/media contracts. First run also passed 60/60. Full API regression remains the preserved ffc8ec1 result, 2,021 PASS/11 SKIP; this change is bridge-only.

REAL PROVIDER TESTS: none. MOCK TESTS: all new wire interactions use explicit MockTransport and fixture server-source pins. LOCAL-REAL TESTS: existing durable SQLite/pinned graph regressions remain passing. No GPU generation/external/paid call occurred.

EVIDENCE: `docs/north-star/comfyui-http-contract-evidence.json` binds source and logs; earlier accepted exports remain unchanged.

REGRESSIONS: all existing bridge lifecycle/security/compiler checks pass. Live source/database/configuration/processes and accepted artifacts remain untouched. No main merge, deployment or publishing.

EXTERNAL BLOCKERS: actual approved executable graph/GPU/server/provider acceptance, Docker, Owner UAT and Native browser verification remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: durable admitted backend dispatch, verified-reference staging and binary artifacts; remaining media/platform/distribution/analytics/learning/Trend/Hub/hardening work continues afterward.
## Wave 5 — Actual binary registration and scoped delivery

WAVE: 5

STATUS: IN PROGRESS; GENERATIVE_MEDIA_READY = NO.

HEAD SHA: parent `b1a61c4`; this binary commit records the increment. Parent is pushed and preserved in verified `north-star-comfyui-http.bundle`, SHA256 `60a037569f073768ef29d69a2863f0a1347306fc8c0c2143f35935015bd98ea9`.

CAPABILITIES COMPLETED: bounded actual FFprobe/full FFmpeg PNG/JPEG/MP4 decode with observed frame counts, codec/dimensions/duration/fps/audio facts. Scoped immutable media/typed provenance/manifest hashes persist and replay exactly; corruption, provenance changes and linked paths reject. Fresh temporary files are cleaned without recursive deletion. Successful bridge jobs bind their actual content under the existing five-field output schema. Authenticated workspace-scoped metadata/download routes verify result/workflow/fixture/checksum and never serve an unbound known artifact ID. Neutral API generation now consumes binary bytes only from those fixed routes, validates result/input/prompt/seed/byte bindings and decoded facts, and preserves legacy JSON receipts. Cost remains null; rights unknown and production/QC readiness false. GPU Docker source declares decoding tools and owned volume; no Docker execution claimed.

CAPABILITIES PARTIAL: actual generated AI media, admitted durable live dispatch/reconciliation, reviewed executable graphs, verified reference staging, server/GPU/cost/provider acceptance, full QC/rights and Native UI integration remain. Full decode does not establish QC or legal clearance. The fresh binary evidence uses synthetic FFmpeg media and explicitly fixture-bound mock GPU job results.

TESTS: complete bridge suite **69/69 PASS**, 5.86s (`comfyui-binary-r3.log`); focused API **54/54 PASS**, 23.04s (`comfyui-binary-api-r2.log`); full worker **35/35 PASS**, 2.26s; Native B-roll/Shorts **10/10 PASS**, 3.898s. Windows symlink creation was unavailable in r1 (67 PASS/1 SKIP); the security test now creates a real owned junction and later runs have no skips. Actual binary ASGI/API/SQLite/offline bundle **PASS**, 14 exports in `comfyui-binary-contract-n2`. Earlier n1 exports remain unchanged. Full API remains ffc8ec1 at 2,021 PASS/11 SKIP until a fresh pinned run completes.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual synthetic PNG/JPEG/MP4 decode, owned storage/junction rejection, binary HTTP/API delivery, exact offline replay and closed SQLite checksum. MOCK TESTS: all GPU generation/server pins/model declarations; API malformed-wire fixtures are explicitly not decode proof. Zero external/paid/GPU operations.

EVIDENCE: `docs/north-star/comfyui-binary-contract-evidence.json` binds executed sources, nine logs and all 14 fresh n2 exports. Two actual delivered binaries are PNG and MP4; JPEG decode is covered by the media suite. Owner UAT, full QC, rights clearance, provider acceptance and production deployment remain false.

REGRESSIONS: bridge/compiler/wire, API media/planning/scope/modes, worker and Native B-roll/Shorts checks pass. Accepted artifacts/live source/database/configuration/processes remain untouched; no merge/deployment/publishing/new budget.

EXTERNAL BLOCKERS: actual approved executable workflow/GPU/provider acceptance, Docker and Owner UAT/browser verification remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: complete verified-reference/durable backend architecture, and continue remaining media/planner/audio/profile/platform/distribution/analytics/learning/Trend/Hub/hardening gaps.
## Wave 7 — Configuration-only technology/AI profile

WAVE: 7

STATUS: IN PROGRESS; MULTI_NICHE_READY = NO.

HEAD SHA: parent `75d0391d364e84e3584f060aaf4c8a822578b67d`; this configuration commit records the increment. Parent is pushed and preserved in verified `north-star-comfyui-binary.bundle`, SHA256 `447dc988961dab2a300b82e8aa4365ac4887f351e14d724470bb38e5d870c9ab`.

CAPABILITIES COMPLETED: an AI-education reference profile, generic reference brand and explanation templates at 30/45/60s in portrait/landscape. Existing five profiles, three brands, four families, defaults/durations and frozen selections remain exact objects; catalog now exposes six profiles, fifteen portrait templates and thirty combined templates. New family uses fit-narration duration without voice-speed changes, owned configurable styling and no default unclear-rights music or implied official logo. The existing research/ideas/scoring/brief/project/editor/brand functions process a non-property fixture into five scored ideas, a brief, unapproved production project, frozen selection, edit plan and canonical shot state. Eleven core modules compare unchanged after Git LF/Windows CRLF normalization; raw source and baseline blob hashes are separately retained. No core niche-specific source edit or provider/render dispatch was needed. Restart preserves documents and unrelated project exactly; human production approval still blocks render.

CAPABILITIES PARTIAL: full non-property playable render and non-developer browser acceptance; complete versioned channel/niche/brand/content/video/publishing/analytics profile integration; all six platform variants/cache and real-provider acceptance remain. Native legacy general constraints still include property-related research warnings and need contextual policy integration. No real AI research/narration/voice or final video is certified by this planning proof.

TESTS: full Native **338/338 PASS**, 253.252s (`multi-niche-native-full-r1.log`); two new focused contracts **2/2 PASS**, 0.600s. Initial selected regression was 59 PASS/1 fixture error: a 320x180 card correctly failed the existing 240px minimum, then the fixture was fixed to 640x360 without weakening ingestion. Fresh evidence **PASS**, twelve exports in `multi-niche-contract-n4`. Failed n1/n2/n3 roots/logs are preserved: raw CRLF/blob comparison, minimum image size and canonical timeline persistence before the first editor operation were corrected in the evidence harness. Full Linux API at preserved 75d0391 now **2,057 PASS, 11 SKIP**, 632.59s; skipped checks remain unaccepted.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual isolated Native SQLite/source-byte/asset ingestion, frozen selection, canonical editor persistence and restart/preservation. MOCK TESTS: research source is `test_fixture`; ideas/script/brief gate exercise are explicit fixtures. No actual retrieval/AI/TTS/render/publish call or Owner UAT.

EVIDENCE: `docs/north-star/multi-niche-contract-evidence.json` indexes exact source/log hashes and twelve immutable n4 exports. Template duration receipt is explicitly a calculation for hypothetical five-second narration, not a generated or measured voice.

REGRESSIONS: full Native Phase 8/9/10 source checks and current API regression pass with skips separately recorded. Prior catalog objects/frozen selections and live source/database/configuration/processes/accepted media are retained. Remote main remains `fa81c59fbe6b745cba8fed979e30e52a13199afa`; live source remains clean `2ced7bc81f9402368fb22c9e7aca242e740531af`. No merge/deployment/publication/new budget.

EXTERNAL BLOCKERS: actual provider/GPU/OAuth/Docker/Owner UAT/browser acceptance remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: platform cost/ownership/storage/cache/recovery integration and remaining media/durable backend/profile/variants/distribution/analytics/learning/Trend/Hub/hardening work.

## Wave 8 — Nullable cost totals and reservation separation

WAVE: 8

STATUS: IN PROGRESS; PLATFORM_FOUNDATION_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `7f45444625c1149213b0c0ec6fe9167928e5e679`; this cost commit records the increment. Parent is pushed and preserved in verified `north-star-ai-education-profile.bundle`, SHA256 `cbd9d6ca34fadc6d2a370b9cc7871928381770bd764dec88dd68f5a1d13a5e49`.

CAPABILITIES COMPLETED: existing cost subtotal fields remain compatible and explicitly described as known subtotals. Separate estimated/actual totals stay null if their respective recorded operations are unpriced; unknown counts/completeness and recorded-operations-only basis are exposed. ASR configured rate times duration is an estimate; unavailable billed cost remains null, even when an untyped provider credit debit exists. Auto Edit persists billing from the result separately from safety-controller budget reservation and no longer replaces an unavailable estimate with zero. Negative/nonfinite amounts and mismatched workspace/project/job bindings reject before cost persistence. An explicit cost limit marks an unpriced record as needing approval; this record-time flag does not itself authorize or prevent an earlier provider dispatch. Winner cost efficiency uses only complete actual totals for recorded operations, and states that full project billing coverage is not certified.

CAPABILITIES PARTIAL: uniform capture of every operation, Native Cost Summary/ledger, project-level admission before dispatch, billing reconciliation and whole-project capture remain. Existing provider safety budget gates are retained. The new evidence uses synthetic monetary inputs and mock provider responses; it is not actual spend or real billing acceptance.

TESTS: focused cost truth/provider safety **50/50 PASS**, 50.13s; existing Auto Edit/analytics/ASR/durable platform **50/50 PASS**, 41.71s; worker **35/35 PASS**, 3.43s; Native ASR **11/11 PASS**, 11.609s. Initial run had 76 PASS/2 test assertion errors against a nonexistent `TranscriptRead` billing field; the assertions were corrected without changing runtime behavior. A fresh local SQLite contract **PASS**, five JSON exports plus closed database, exact restart/replay and null winner-cost factor. Previous pinned Linux 75d0391 result remains 2,057 PASS/11 SKIP until this increment's full run.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: isolated SQLite, restart, JSON null serialization, project/job isolation and immutable replay. MOCK TESTS: all prices, billed inputs, ASR wire responses, controller reservation and analytics/publication fixtures. No external/paid operation.

EVIDENCE: `docs/north-star/cost-truth-evidence.json` binds source, six logs, five JSON exports and closed database in `cost-truth-contract-n1`. Historical records/artifacts are not rewritten.

REGRESSIONS: analysis, analytics, provider safety, worker and Native ASR checks pass. Live source/database/configuration/processes/accepted media are untouched. No main merge, deployment, publication or new budget.

EXTERNAL BLOCKERS: real billing/provider/OAuth/GPU/Docker and Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe implementation. NEXT WAVE: Native cost/ownership/storage/cache/recovery integration and remaining profile/media/distribution/analytics/learning/Trend/Hub/hardening work.

## Wave 8 — Native cost intents, budget and Studio summary

WAVE: 8

STATUS: IN PROGRESS; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `f0459996c723a0171b450ab1031a25c458672429`; this Native increment records the change. Parent is pushed and preserved in verified `north-star-cost-truth.bundle`, SHA256 `e41ac58907422ed12242c205efc27bffef1bea0817036fdaee53109f2d47b0ae`.

CAPABILITIES COMPLETED: additive Native SQLite cost table, content-free intents and immutable outcome receipts; project/job/request/model bindings; exact restart/replay; null estimates/billing and known subtotals. Optional project budget is revisioned, requires current session/CSRF and invalidates approval. Concurrent paid admission accounts for reserved/known actual exposure in one transaction; unknown or excessive estimated spend under an explicit limit blocks before dispatch. Existing authorization/checkpoints remain independent. Content-generation attempts, live shot-edit suggestions and actual ASR upload/create/poll wire calls are metered. Known ASR observation can resume without repeating writes. Token usage does not become a billed price. Capability-gated Studio Cost Summary presents incomplete history and unknown costs, escapes output and preserves pending budget edits; legacy servers require no new optional module/route. Cost information appears in the Video stage without changing default shot UX.

CAPABILITIES PARTIAL: all pre-project intelligence/external provider/job capture, configured admission estimates, historical/full billing reconciliation, real receipts, multi-user RBAC/storage/recovery and current 1366/1920/2560 browser acceptance. A budget-constrained paid operation with no configured estimate remains blocked. A missing optional project limit preserves existing provider authority; the ledger grants no provider/publishing authority. Historical data is not backfilled or recertified. Platform/cost readiness remains NO.

TESTS: full Native **351/351 PASS**, 231.820s; latest cost/HTTP **13/13 PASS**, 5.236s; Studio **116/116 PASS**, zero skips. Full Native loaded the server before the subsequently added capability flag; latest HTTP tests verify that additive flag, while core ledger/provider logic was unchanged. First focused run passed 61 tests, including an imported duplicate Phase10 test class; discovery was corrected to import the helper module, not duplicate its tests. Fresh Native local contract **PASS**, six exports and closed database in `native-cost-contract-n1`. Full Linux API at pushed f045999 **2,085 PASS/11 SKIP**, 582.39s; skips remain unaccepted.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: SQLite, CAS/versioning, actual concurrent admission, Native HTTP/session/CSRF/stale/scope controls, restart and exact uncertain-operation no-replay. MOCK TESTS: provider SDK/wire responses and all monetary/billing hashes; these are explicit fixtures, not actual bills. No external/paid call.

EVIDENCE: `docs/north-star/native-cost-evidence.json` binds source, seven logs, six exports and closed database. `docs/NATIVE_COST_LEDGER.md` describes scope and remaining limits. Prior artifacts and failure roots remain unchanged.

REGRESSIONS: full Native Phase8/9/10 source tests and Studio checks pass; pinned API passes with skips disclosed. Live source/database/configuration/processes/accepted videos remain untouched. No main merge, deployment, publication or new budget.

EXTERNAL BLOCKERS: provider/billing/OAuth/GPU/Docker/browser/Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: finish safe backup/restore, storage/ownership/cache and remaining media/profiles/distribution/analytics/learning/Trend/Hub/hardening implementation.

## Wave 8 — Offline Native backup and fresh recovery

WAVE: 8

STATUS: IN PROGRESS; Native recovery increment complete; PLATFORM_FOUNDATION_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `0944b7b876d39d63bb9e2cbc191dc73272714ab5`; this recovery commit records the increment. Parent is pushed and preserved in verified `north-star-native-costs.bundle`, SHA256 `8a9f3dc5e18e8eb9d7ca4084eef27945fba82be0234c43f0033506a14ed30c42`.

CAPABILITIES COMPLETED: explicit offline snapshot/fresh restore CLI for the existing Native SQLite/data root. Snapshot uses the server lease and SQLite backup API, includes committed WAL state, verifies current immutable project/intelligence versions and all-table logical hashes, copies owned state/configuration evidence, and rejects active work, source changes, links/hardlinks/junctions, unknown databases and embedded secret files. Restore requires an independent trusted package checksum and a nonexistent destination; strict archive membership/names/type/size/hash checks and restored database/history checks precede directory commit. Hash-scoped receipts/runtime configuration preserve prior recovery evidence. No source-root replacement, service termination/startup, migration, provider dispatch, publishing or invented approval. Failed partial/staging packages remain available for inspection.

CAPABILITIES PARTIAL: production PostgreSQL/Redis/S3/GPU/Docker restore, cross-host runtime/credential recovery and full playable/provider/browser recovery remain unaccepted. ZIP packages contain private state and are unencrypted; protected parent permissions are required. Credential-file contents are excluded and their configured paths remain references. Native restore does not certify production recovery or full Mode A/B.

TESTS: full Native **365/365 PASS**, 191.985s (`native-backup-full-r2.log`); fourteen backup/security tests pass, latest focused run 2.223s. First full run had 364 PASS/1 stale test expectation omitting the previously implemented cost capability flag; only its expected response was corrected. Earlier focused fixture/platform failures and their fixes are retained in the evidence index. Actual CLI backup and fresh restore pass. Fresh restore rehearsal **PASS**, ten exports and eighteen verified entries in `native-restore-contract-n3`. n1 expected a revision from an unchanged reorder; n2 assumed multiple shots in a single-shot fixture. n3 exercises a real on-screen-text update without weakening runtime idempotency. Both failed roots/logs remain retained. Unchanged Studio remains 116 PASS; pinned Linux API f045999 remains 2,085 PASS/11 SKIP.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual Native SQLite backup/WAL/restart/history, owned filesystem security, trusted package/file hashes, CLI execution, exact research/cost/assets recovery with original fixture root unavailable, full FFmpeg decode of the restored two-second video/audio and subsequent canonical editing. MOCK TESTS: research/ideas and the unpriced ledger operation are explicit fixtures; no real billing, spoken ASR, generated AI output or Owner UAT is implied.

EVIDENCE: `docs/north-star/native-restore-evidence.json` binds six source files, thirteen logs, ten exports, the original package SHA256 `783ca3ba75c5ff49fcccfa45419c9818e6356fb68d8d143991ed9a9e988294c7` and a subsequent CLI backup. Fresh owned rehearsal root `C:\vf-native-restore-n3` retains originals under `retained-original`; accepted/live roots are untouched. Runbook: `docs/NATIVE_BACKUP_RESTORE.md`.

REGRESSIONS: full Native Phase8/9/10 source checks pass. Existing accepted artifacts, live source/database/configuration/processes and historical bundles remain unchanged. Remote main remains `fa81c59fbe6b745cba8fed979e30e52a13199afa`; no merge, production deployment, real publication or new paid operation.

EXTERNAL BLOCKERS: real credentials/billing/GPU/Docker/browser/Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: Native health/logging/role enforcement and remaining platform/media/profiles/distribution/analytics/learning/Trend/Hub/hardening work.

## Wave 8 — Native health and content-free operational telemetry

WAVE: 8

STATUS: IN PROGRESS; Native health/logging increment complete; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `96f3b980eb25eb92f8ca52b30a8f974f8d1fd75d`; this telemetry commit records the increment. Parent is pushed and preserved in verified `north-star-native-recovery.bundle`, SHA256 `8a5bb9efb6621fadaadb422b16fbf31106851969bd38d590cafac8696dd0b6c4`.

CAPABILITIES COMPLETED: `/healthz` liveness and `/readyz` required local state/schema/worker/tool-presence availability under the existing loopback Host/origin boundary. Missing/corrupt/linked databases never become newly created or followed; reads are bounded. Missing/disabled/stopped required dependencies return 503 while HTTP can remain alive. No optional GPU/provider/secret test or external call. Every GET/POST dispatch generates an opaque response request ID; incoming arbitrary IDs are ignored. Fixed-category JSON telemetry records scoped IDs/duration/status with null unknown context, production steps and intelligence outcomes. Raw paths, queries, bodies, headers, filenames, cookies, secrets, provider errors and private content are excluded. Only the Native logger is configured; SDK/global logging levels remain untouched. Sink failure cannot change workflow results. Existing durable database step events and legacy health/session responses remain compatible.

CAPABILITIES PARTIAL: all-service correlation, production log access/collection/retention, metrics/alerts and soak acceptance. Readiness is availability/tool-presence evidence, not full tool/model/database integrity or real-provider acceptance. Intelligence provider context remains null when unknown. Pipeline provider categories alone do not prove actual dispatch, spend or media acceptance.

TESTS: full Native **376/376 PASS**, 195.490s (`native-observability-full-r1.log`); latest focused HTTP/cost/worker/intelligence **75/75 PASS**, 30.249s, including eleven new telemetry/privacy/readiness checks. Earlier focused run was 60/60 before intelligence instrumentation. Fresh actual local contract **PASS**, seven exports/eight requests in `native-observability-contract-n3`. n1 was correctly refused because an absent-secret path parent overlapped the fixture data root; only fixture layout changed. n2 research correctly failed relevance for a sentinel-only query; n3 uses the existing valid AI-education fixture query and waits for a terminal result without weakening research validation. Failed roots/logs remain retained. Unchanged Studio remains 116 PASS; pinned Linux API f045999 remains 2,085 PASS/11 SKIP.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual isolated HTTP, SQLite, worker/intelligence threads, generated correlation, required-dependency loss, corrupt/missing/linked database rejection and content-free logger capture. MOCK TESTS: generated content/research/ideas and worker failure bodies are explicit fixtures. No paid/external operation or Owner approval.

EVIDENCE: `docs/north-star/native-observability-evidence.json` binds six source files, six logs and seven n3 exports; `docs/NATIVE_OBSERVABILITY.md` defines exact readiness/logging limits. All owned contract threads are closed; live/accepted roots are untouched.

REGRESSIONS: full Native Phase8/9/10 checks pass; project/queue/provider authorization, session/CSRF, approval and no-replay boundaries remain intact. No main merge, production deployment, publication or new provider budget.

EXTERNAL BLOCKERS: actual credentials/billing/GPU/Docker/browser/Owner UAT remain separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: role enforcement and remaining media/platform/profiles/distribution/analytics/learning/Trend/Hub/hardening implementation.

## Wave 8 — Shared existing human identity prerequisite

WAVE: 8

STATUS: IN PROGRESS; identity reuse prerequisite implemented; NATIVE_RBAC_READY = NO.

HEAD SHA: parent `17c5b0cbb3568250e14bd2b7a5134ca57404943d`; this identity commit records the increment. Parent is pushed and preserved in verified `north-star-native-observability.bundle`, SHA256 `908017fdf7984d113c9186e56500b8275e02386169c7745af5c77c2cd9696788`.

CAPABILITIES COMPLETED: existing `vf1` hash-token registry/principal/workspace/expiry verifier extracted into a provider-free shared module, with API public names reexported. Eleven identity definitions and nine retained API authentication/authorization/rate-limit definitions have identical AST hashes to the parent. Token/role/lifecycle/schema behavior is unchanged. Pinned Native executes the same contract without FastAPI, database, Redis, provider SDK or GPU package imports. No new credential, permission, production change or service-identity sharing is introduced.

CAPABILITIES PARTIAL: Native registry/workspace/session integration, every-route authorization before dispatch, review-actor binding and Studio login/permission behavior remain. The existing dedicated Agent Hub service identity remains separate. No Native HTTP RBAC completion is inferred from pure contract tests. Whole program implementation remains incomplete.

TESTS: Native identity/observability **16/16 PASS**, 3.315s, including five new identity cases; existing API ingress **4/4 PASS**, 4.10s. Fresh local contract **PASS**, three exports and exact eleven/nine AST comparisons. Prior Native full 376 PASS and Linux API f045999 2,085 PASS/11 SKIP are retained; full current pinned refactor regression remains pending.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: pinned Native import/execution, fixture registry file, lifecycle/hash/workspace validation and Git/source AST comparisons. MOCK TESTS: all human tokens/principals are explicit fixtures; no real credential file was read or issued.

EVIDENCE: `docs/north-star/human-identity-evidence.json` binds five source files, three logs and three exports. `docs/HUMAN_IDENTITY_CONTRACT.md` defines exact scope and remaining integration.

REGRESSIONS: focused existing API/Native checks pass; registry schema, API rate/role behavior and prior source/artifacts remain. Live roots/processes/credentials and accepted artifacts are untouched. No main merge/deployment/publication/provider budget.

EXTERNAL BLOCKERS: current provider/OAuth/GPU/Docker/browser/Owner UAT acceptance remains separate. OWNER ACTION REQUIRED: none for safe continuation. NEXT WAVE: bind existing identity to Native sessions/permissions/UI, rerun pinned regressions, then remaining media/platform/distribution/analytics/learning/Trend/Hub/hardening work.

### Wave 8 — configured Native sessions, RBAC and Studio sign-in

WAVE: 8 / platform foundation. STATUS: IN PROGRESS; configured Native access implementation and isolated fixture acceptance pass. Full platform RBAC, non-developer/browser UAT and production acceptance remain PARTIAL.

HEAD SHA: parent `583d9eaf445622f70ae05d52f8fc4ee3311ad284`; this access commit records the increment. Parent is pushed and preserved in verified `north-star-human-identity.bundle`, SHA256 `10e201444d5242f6934e39accebe464bda6d8c23e6c1ea07c24a604539ea8a49`.

CAPABILITIES COMPLETED: optional external hashed registry/workspace binding, distinct in-memory human sessions and CSRF, login/logout, four explicit read/edit/review/manage role sets, authorization before body processing/dispatch, identity-bound review actors, bounded expiry/rates/capacity, profile-change revocation and fail-closed auth readiness. A non-secret workspace marker binds the state root durably and rejects relabelling or startup without a registry on bound state. No database migration or credential issuance. Studio login clears credentials before waiting; four pages optionally provide identity/logout/role controls and restrict dynamically created/re-enabled controls. HTTP remains authoritative. Unbound legacy local Owner and old backend capability paths stay supported; human service credentials remain separate. Existing revision, hash, acknowledgement, rights, cost and production approval gates remain.

CAPABILITIES PARTIAL: production identity lifecycle/TLS/multi-user acceptance, Native service bridge integration, cross-runtime role-policy acceptance and browser/non-developer UAT. Native is one workspace per state root. Access was not enabled on the accepted live installation. No full Mode A/B or North Star readiness inferred.

TESTS: full pinned Native **400/400 PASS**, 194.017s (`native-access-full-r2.log`), including nineteen new session/HTTP/security tests. Earlier full r1 also passed 400 in 195.743s; final omitted-registry fallback and non-ASCII CSRF hardening are covered by r2. Full Studio **123/123 PASS**, 622.8104ms, including seven login/role/runtime cases. Fresh actual HTTP/session/SQLite acceptance **PASS**, **37 requests/eight exports** at `C:\vf-native-access-n2`; n1 also passed. The unchanged shared-identity prerequisite at `583d9ea` additionally passed **381 Native** (324.671s) and **2,085 Linux API/11 SKIP** (722.87s); those completed logs are now indexed. No duplicate unchanged API rerun claimed.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: real loopback HTTP, hashed fixture file, cookie/CSRF/session expiry/revocation/permissions, SQLite canonical shot revision, scoped script review record, immutable unrelated project and administrative budget policy. MOCK TESTS: all identities and human decisions are explicit fixtures. Fixture script-only review has media/production approval false and no jobs. Node DOM fixtures prove controls/login behavior, not browser layout or Owner UAT.

EVIDENCE: `docs/north-star/native-access-evidence.json` binds seventeen source files, nine logs, eight exports and a new preservation receipt. `docs/NATIVE_ACCESS.md` defines operation, backup binding and limits. Parent identity evidence now records its completed full regressions. All fifteen accepted Phase 8/9 videos were freshly hashed unchanged; live source remains clean at `2ced7bc81f9402368fb22c9e7aca242e740531af`.

REGRESSIONS: full Native/Studio pass. Live data/processes/credentials, accepted videos, existing application modules and the locked Native runtime remain untouched. No main merge, provider call, publishing, budget consumption or deployment. Provider/OAuth/GPU/Docker/browser/Owner UAT acceptance remains separate.

EXTERNAL BLOCKERS: none for continued safe implementation; configured production/browser/real-provider acceptance remains pending. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve the access milestone, then complete official distribution protocols, media/provider integration, analytics, learning, Trend Radar, Agent Hub and production hardening with distinct acceptance evidence.

### Wave 9 — bounded official wire transport and YouTube resumable protocol

WAVE: 9 / distribution prerequisites. STATUS: IN PROGRESS; protocol implementation and mock acceptance pass. PUBLISHING_READY = NO. No live adapter/factory is activated.

HEAD SHA: parent `6ad3517429a41174d741b42cf66597cf9b84d96f`; this wire commit records the increment. Parent is pushed and preserved in verified `north-star-native-access.bundle`, SHA256 `552290bf38b3d3dcac429a4bdc8ca1da6fb7a187e2496fd3f29d0fe2d8e94a20`. Remote completion branch matches the parent; main remains `fa81c59fbe6b745cba8fed979e30e52a13199afa`.

CAPABILITIES COMPLETED: bounded official-origin HTTP transport with disabled default network mode, TLS verification, no redirect/retry/proxy/cookie behavior, fixed private errors, context-local sensitive wire log suppression and request/response/timeout bounds. YouTube official request/response helpers for metadata/disclosures/private future scheduling, resumable initiation/chunks/status, confirmed upload and processing lookup, plus a separate deletion request builder. UTF8 Vietnamese description bytes and aggregate tags are checked. Unsupported thumbnails fail explicitly. No vendor idempotency header or deduplication guarantee invented. TikTok official API/upload origin separation rejects OAuth headers on its signed upload host. Current primary official docs are linked in the protocol runbook.

CAPABILITIES PARTIAL: durable before-POST dispatch intent, private encrypted session references, exclusive claims/process-restart recovery, fresh approval/rights/QC/source-byte binding, OAuth lifecycle, cost capture, thumbnail stage, complete YouTube/TikTok/Meta PublishingProvider adapters, Native Publishing Queue/scheduler/approval/history/UI and real-provider acceptance. The existing application official provider remains contract-only and `PUBLISH_ENABLED=false`. Protocol builders grant no publishing/deletion permission and do not waive the original North Star.

TESTS: new wire/protocol tests plus existing publishing **38/38 PASS**, 7.55s. Expanded existing publishing/analytics/human-ingress/authority regression **68/68 PASS**, 20.61s. Thirty-five new tests cover transport privacy/origins/bounds, metadata, chunks, ambiguous outcomes and scoped status. r1/r2 each failed a fixture whose individual tag was 81 characters; corrected to valid 80-character tags to exercise the aggregate platform limit. Neither existing schema nor new platform validation was weakened. Full Linux API at this forthcoming commit remains pending; prior `583d9ea` 2,085/11 and Native `6ad3517` 400/Studio 123 results remain distinct.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: FFmpeg creates a fresh **570,463-byte H.264/AAC synthetic MP4**, FFprobe metadata and full A/V decode pass. MOCK TESTS: its exact bytes traverse five official-format mock transport requests: one initialization POST, three chunks, final-response loss, then a zero-byte status query of the same session returns a fixture ID. The receiver has identical bytes and no repeated initialization. This proves protocol reconciliation, not durable process restart, actual post creation or Owner UAT. Application default factory refusal is explicitly checked.

EVIDENCE: `docs/north-star/publishing-wire-evidence.json` binds six source files, five logs, five exports and the synthetic MP4 hash under `C:\vf-publishing-wire-n1`. `docs/PUBLISHING_WIRE_PROTOCOLS.md` names remaining integration and official source contracts. Capability 41 now PARTIAL rather than INTERFACE_ONLY; 42 includes scoped current protocol validation. No publishing-ready state claimed.

REGRESSIONS: focused existing application checks pass; no application settings/factory/routes, accepted videos, live source/data/processes, Native runtime or production infrastructure changed. No real secret read, provider call, paid action, post/deletion, main merge or deployment.

EXTERNAL BLOCKERS: credentials/account audit/Owner real-publish authorization remain eventual external acceptance gates; they do not block remaining safe implementation. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve this protocol increment, then implement durable dispatch/reconciliation and full provider adapters while completing Native/media/platform/analytics/Trend/Hub gaps.

### Wave 9 — separate publish consent and durable dispatch intent

WAVE: 9 / distribution prerequisites. STATUS: IN PROGRESS; consent/journal implementation, additive migration rehearsal and isolated restart evidence pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `f2aa91e7a3de77cc31718c89de8d412293bfee58`; this dispatch commit records the increment. Parent is pushed and preserved in verified `north-star-publishing-wire.bundle`, SHA256 `7042dcac94a481a0c434cfea1b3099b1aa748f82bfd36af079b9828d3c7e819b`.

CAPABILITIES COMPLETED: distinct publish-only consent from a current registered Owner, exact metadata/artifact/production approval/timeline/audio/subtitle/final-QC/rights binding, immutable idempotency/deadline, current identity revision checks and explicit revocation. Additive approval/dispatch tables retain existing production approvals. Versioned compare-and-swap claims commit intent before issuing a private worker ticket. Initialization ambiguity never automatically restarts a POST; known-session chunk/query ambiguity supports bounded-lease reconciliation with stale reply fencing. Public projections/audit exclude private nonce/session references. Uploaded is distinct from processing-ready/published. The factory remains disabled/contract-only; the journal performs no network call.

CAPABILITIES PARTIAL: encrypted durable sessions, verified source bytes and atomic admission across concurrent edits, OAuth lifecycle, cost/budget capture, actual wire dispatch and terminal processing/receipts, consent renewal/recovery policy, complete YouTube/TikTok/Meta adapters and Native queue/scheduler/history/approval UI. Database fencing cannot cancel an in-flight provider call; adapter serialization remains required. PostgreSQL migration/production rollout and full Publishing/Mode A/B remain unaccepted.

TESTS: expanded publishing/wire/analytics/identity/authority **81/81 PASS**, 53.88s (`publishing-dispatch-r3.log`), including thirteen new dispatch/security/recovery cases. Additive SQLite migration/ORM/FK parity **1/1 PASS**, 2.98s; all existing rows and table SQL unchanged, destructive downgrade refused. Earlier r1 failed a fixture that attempted direct mutation of frozen HumanTokenRecord; replacement uses model_copy without changing identity immutability. r2 passed 49 before stricter ticket/query-restart cases. Full Linux API at parent `f2aa91e` completed **2,120 PASS/11 SKIP**, 534.69s; wire evidence now indexes it. Full API at the forthcoming dispatch commit remains pending. Unchanged Native 400/Studio 123 are retained as separately pinned results.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: SQLite transactions/conditional claims, filesystem persistence, additive migration and three separate Python process reads. MOCK TESTS: every identity, consent, production approval, media/render/QC, private session reference and provider receipt is an explicit fixture. Fresh owned rehearsal `C:\vf-publishing-dispatch-n1` emits seven exports, proving one initialization claim, commit before simulated callback, lost-chunk outcome reconciliation, revocation and permanently ambiguous initialization. It does not establish real media quality, encrypted sessions, a real post or Owner UAT.

EVIDENCE: `docs/north-star/publishing-dispatch-evidence.json` binds seven source files, six logs and seven exports. `docs/PUBLISHING_DISPATCH_JOURNAL.md` defines admission, recovery and exact limits. `0019_ns_publish_dispatch` was rehearsed only against fresh owned SQLite; accepted/live state was not migrated.

REGRESSIONS: expanded existing checks pass, and full prior API passes. Live/accepted artifacts, source/database/processes/credentials and locked Native runtime remain untouched. No main merge, deployment, external publish/delete, secret read or paid operation.

EXTERNAL BLOCKERS: real credentials/account audit/provider/Owner acceptance remain eventual gates; none blocks safe implementation. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve dispatch milestone and run its pinned API regression, then finish encrypted sessions/provider integration and remaining media/platform/analytics/learning/Trend/Hub/hardening capabilities.

### Wave 9 — immutable encrypted publishing session receipts

WAVE: 9 / distribution prerequisites. STATUS: IN PROGRESS; inert private session vault and owned encryption/restart/migration acceptance pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `302c090868789d0745f42521a5dcb90ac4cf1b53`; this vault commit records the increment. Parent is pushed and preserved in verified `north-star-publishing-dispatch.bundle`, SHA256 `80cfd1fa69e5745a9ca98df706de5a612253c501402c021a48f5405a5910db8c`. Recovery receipt freshly verifies all fifteen accepted Phase 8/9 videos unchanged, live source clean at `2ced7bc81f9402368fb22c9e7aca242e740531af`, remote completion branch matching and main unchanged.

CAPABILITIES COMPLETED: one immutable encrypted YouTube session receipt per publication; AES-256-GCM, random 96-bit nonce, key/nonce uniqueness, authenticated workspace/project/publication/artifact/size/key/expiry metadata and exact current private initialization ticket. Keys are externally injected in memory; no bootstrap, plaintext fallback, overwritten receipt, automatic key replacement or replay deadline extension. Malformed key IDs are refused before calling a resolver. Missing old keys, altered ciphertext/nonce/metadata, expired sessions and foreign scope fail closed. Sealed receipts commit before returning an opaque ref; public status/audit retain neither key nor URI. Loading for reconciliation does not authorize another chunk after consent revocation. An additive table migration preserves old owned rows/schema and refuses destructive downgrade.

CAPABILITIES PARTIAL: orphaned-receipt recovery between vault/journal commits, production external-key custody/rotation/backup and OAuth lifecycle, verified artifact-byte/concurrent-edit admission, costs/budget, full YouTube dispatch/processing/thumbnail/provider adapter, TikTok/Meta official session types and Native publishing UI/scheduler/history. Current vault only validates YouTube resumable URIs. Database leases do not cancel network work. Production PostgreSQL/key-provider/real account acceptance and full Publishing/Mode A/B remain unaccepted.

TESTS: expanded publishing/analytics/identity/authority/vault/migrations **97/97 PASS**, 176.78s (`publishing-vault-r2.log`), including fourteen vault cases at collection and the new additive migration rehearsal. Final missing-dependency/key-ID/rotation boundary **3/3 PASS**, 20.64s; the additional missing-crypto case independently passed 1/1 in 8.21s. Total new vault tests now fifteen plus one migration test. Earlier vault/dispatch checks passed 27/27 in 108.40s. Without optional crypto the unmodified API runtime passed two base tests/explicitly skipped twelve AEAD tests; dependency absence is not a cryptographic pass. Actual cryptography 50.0.2 executes from a separate test dependency directory. Fresh six-export contract passes encryption, SQLite inspection and separate-process decrypt. Full Linux parent `302c090` remains running; full forthcoming vault commit requires its own pinned regression. Prior full wire API 2,120/11, Native 400 and Studio 123 remain distinct.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual AES encryption/authentication, immutable SQLite transactions, rotation/tamper checks, additive schema/ORM/FK/unique parity, database/sidecar byte inspection and one separate Python restart. MOCK TESTS: every key, human consent/identity, production approval, media/QC and provider URI is an explicit fixture. No real key/token file is read; no provider request is issued. Crypto package installation is confined to `C:\vfns-test-deps\publishing-crypto-50.0.2`; installed Native/API runtimes are unchanged.

EVIDENCE: `docs/north-star/publishing-private-sessions-evidence.json` binds nine source files, seven logs, six exports and the prior milestone preservation receipt. Fresh root `C:\vf-publishing-vault-n1`; runbook `docs/PUBLISHING_PRIVATE_SESSIONS.md`. Migration `0020_ns_private_publish_session` is only rehearsed against new owned SQLite, never production.

REGRESSIONS: expanded existing suites pass. Live source/data/schema/processes/credentials, accepted videos and original provider factory/activation flags remain untouched. No main merge, real publish/delete, paid call, deployment or production key provisioning.

EXTERNAL BLOCKERS: real OAuth/key-provider/account audit/Owner acceptance are eventual separate gates; no current safe-work blocker. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve vault increment and run pinned Linux regression including isolated optional AEAD, then complete verified source admission/official adapters and remaining media/analytics/learning/Trend/Hub/hardening capabilities.

### Wave 9 — scoped storage and verified publishing artifact ranges

WAVE: 9 / distribution prerequisites. STATUS: IN PROGRESS; inert source admission, real media QC and private byte-range verification pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `bf450587061d5d9836f8d760affe1e93e6be569b`; this artifact commit records the increment. Parent is pushed and preserved in verified `north-star-publishing-sessions.bundle`, SHA256 `9419197b68ea76949087f3370a430adb626f60219ebc9b2af9c620d3c02fc4e2`. Main remains unchanged; prior preservation receipt binds fifteen accepted hashes and clean live source.

CAPABILITIES COMPLETED: exact scoped registered local/S3 storage reads into new private directories, size/whole-file SHA/MP4 checks, existing FullProductionQC against the canonical final profile/timeline, current consent/identity/rights/binding rechecks and internal per-block verification for every transmitted range, including unaligned ranges. Local links/hardlinks/junctions reject. S3 exact ContentLength, bounded reads/timeouts, one-attempt retry configuration, stream closure and context-local SDK logging privacy are tested. The existing S3 constructor accepts an optional explicit publishing request configuration; other defaults stay intact. Repeated cancellation stops/waits for the owned copy thread before cleaning its verified private directory. No original object, accepted artifact or configured root is deleted. Quality facts retain publishing-blocked status and confer no publish authority.

CAPABILITIES PARTIAL: complete durable upload worker/adapters and terminal processing/status/receipts, atomic admission across edits, orphaned session recovery, OAuth/external keys, costs/budget, consent renewal, YouTube thumbnail stage, TikTok/Meta protocols and Native publishing UI/scheduler/history. Actual S3 endpoint pinning/regional redirects/network policy remain unaccepted; retry configuration alone is not their certification. Full Mode A/B and final acceptance bundles remain incomplete.

TESTS: expanded publishing/analytics/identity/authority/artifact/vault/migration **116/116 PASS**, 157.31s (`publishing-artifact-r3.log`). Latest SDK profile/stream/privacy cases **4/4 PASS**, 2.61s; fresh SDK account/profile isolation **1/1 PASS**, 2.18s; verified private-root cleanup/repeated cancellation **2/2 PASS**, 5.47s. Total twenty new artifact tests now exist; earlier artifact r1/r2 passed 12/17 before added boundaries. Fresh real-media rehearsal passes five exports. Full Linux dispatch commit `302c090` passed **2,134/11 SKIP**, 957.82s; full vault commit `bf45058`, including actual isolated optional AEAD, passed **2,150/11 SKIP**, 910.30s. Their evidence indexes now record completion. Full forthcoming artifact commit remains pending. Unchanged separately pinned Native 400/Studio 123 remain distinct.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual owned storage/file/checksum/range operations, SDK profile construction without a request, actual FFmpeg synthetic 1080×1920/30fps H.264/AAC media and existing full QC. MOCK TESTS: unit S3 streams/QC, all project/identity/production/publish consent fixtures. Fresh `C:\vf-publishing-artifact-n1` retains the **4,256,257-byte** original; seventeen ranges reconstruct it exactly. Corruption is confined to a disposable copied object and refused before QC/wire. This is not real speech/semantic quality, a Video Factory final render, Owner UAT or final bundle A/B/C.

EVIDENCE: `docs/north-star/publishing-artifact-evidence.json` binds five source files, ten logs, five exports, synthetic MP4 hash and prior preservation receipt. Runbook `docs/PUBLISHING_ARTIFACT_ADMISSION.md`. Prior dispatch/vault evidence now indexes their passing full Linux results. The first evidence-recorder check incorrectly formatted 910.30 as 910.3; only fixed decimal verification was corrected, with no test or production behavior change.

REGRESSIONS: expanded suites and full previous commits pass. Existing timelines, production providers, activation flags, installed runtimes, accepted/live artifacts/data/schema/processes/credentials and main remain untouched. No real storage/provider request, publication/deletion, paid operation or deployment.

EXTERNAL BLOCKERS: actual S3/credentials/account audit/Owner real publishing acceptance are eventual gates; none blocks safe continuation. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve this increment and run pinned regression, then connect verified source/journal/encrypted sessions to the official upload worker and finish remaining distribution/media/analytics/learning/Trend/Hub/hardening work.

### Wave 9 — reviewed destination and fresh publishing configuration binding

WAVE: 9 / distribution admission. STATUS: IN PROGRESS; destination consent/configuration/restart checks pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `21d02dfd63e5470272dac3d3dcd8834a21ee8efe`; this target-binding commit records the increment. Parent is pushed and preserved in verified `north-star-publishing-artifact.bundle`, SHA256 `337ae98d28bce6f9faffc07de58d98fbfc07ae69e956a91c312401f675633187`. Its fresh preservation receipt verifies fifteen accepted hashes, clean live source at `2ced7bc81f9402368fb22c9e7aca242e740531af`, unchanged remote main and 147 ahead/0 behind.

CAPABILITIES COMPLETED: strict frozen versioned public destination/profile/credential-configuration binding, exact Owner-reviewed target digest, fresh trusted server lookup before initialization/chunks, full provider-validation revision binding and fixed private errors. Changed account, profile, credential binding, workspace/provider or validation invalidates consent. Exact replay preserves the grant/deadline; fresh consent cannot silently rebind an existing dispatch. Strict worker policy rejects legacy unbound grants; old dry runs remain readable without schema migration. Public configuration is not official account verification.

CAPABILITIES PARTIAL: configured profile administration and official account/scope verification, consent-gated queue/upload worker, atomic edit admission, orphaned-session recovery, OAuth/key custody, costs, processing/thumbnail receipts, full YouTube/TikTok/Meta adapters and Native distribution UI/scheduler/history. No factory activation or real provider acceptance. Full Mode A/B, Waves 10–16 and North Star remain incomplete.

TESTS: expanded publishing/wire/vault/artifact/migration/analytics/identity/authority regression **129 PASS**, 148.39s; twenty-four new target cases. First run passed 39/failed 1 because SQLAlchemy skipped a malformed fixture update whose boolean True compared equal to integer 1; the test now explicitly persists that corrupted JSON and strict validation remains unchanged. r2 selected nonexistent test paths and ran no tests; r3 uses discovered actual files. Full Linux parent `21d02df` passed **2,170 PASS/11 SKIP**, 801.54s and artifact evidence now indexes it. Full forthcoming target commit remains pending. Native 400/Studio 123 results remain separately pinned.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual SQLite transactions and four separate Python process revalidations. MOCK TESTS: every account/profile/credential fingerprint/human/production approval/QC/consent input is an explicit fixture. Fresh `C:\vf-publishing-target-n1` emits four exports and refuses changed account/profile/credential configuration after restart while dispatch remains unstarted. Zero wire calls/actual secrets read/paid operations; no official account claim.

EVIDENCE: `docs/north-star/publishing-target-evidence.json`, `docs/PUBLISHING_TARGET_BINDING.md`, four fresh exports and full parent regression/preservation receipt. Capability 41 remains PARTIAL; no readiness inflation.

REGRESSIONS: expanded existing checks and full prior API pass. Existing accepted/live media, source/data/schema/processes, runtime/credentials, main and default publishing flags remain untouched. No real publish/delete, deployment, paid operation or destructive migration.

EXTERNAL BLOCKERS: eventual OAuth/account audit/key-provider/Owner real-publish gates; none blocks remaining safe work. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve this increment, then implement consent-gated queue/provider worker and remaining media/analytics/learning/Trend/Hub/hardening work.

### Wave 9 — consent-gated validation queue and Owner publishing API

WAVE: 9 / distribution queue. STATUS: IN PROGRESS; backend queue/Owner API/restart acceptance pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `a2359d4b1f3ef788cd946773890f1951612e819c`; this queue commit records the increment. Parent is pushed/preserved in verified `north-star-publishing-target.bundle`, SHA256 `eba5a6e445b56fa7fd79038041b28bc42617c007222642f38682788da78f6cff`. Fresh receipt rechecks fifteen accepted hashes, clean live source, unchanged remote main and 148 ahead/0 behind.

CAPABILITIES COMPLETED: live create independently enforces three Owner configuration gates, scoped ready destination and existing production/rights/platform checks, then persists awaiting_publish_approval without calling provider.publish. Separate Owner-only strict API consent and publication-scoped revocation use current journal identity/target binding; viewer dispatch reads expose no nonce/private refs. Consent creation leaves the queue unstarted. Later prepare conditionally changes parent state and creates one dispatch in one transaction. No journal/worker is activated by the default factory. Live execution visibility requires an attached worker. SQLite publication/event reads normalize UTC so initial/replayed responses agree exactly.

CAPABILITIES PARTIAL: complete configured profiles/official account and OAuth scopes, full upload/processing/thumbnail/cost worker, atomic edit admission, orphaned receipts, key/OAuth lifecycle, consent renewal, TikTok/Meta adapters and Native distribution UI/scheduler/history. API consent is not browser acceptance, Owner UAT, a real post or full Mode A/B.

TESTS: expanded existing publishing/wire/vault/artifact/migration/analytics/identity/authority/queue regression **145/145 PASS**, 335.55s. Sixteen new queue/security cases. First run passed 59/failed 1 and first contract failed exact replay: a real UTC-naive SQLite reload defect. Normalization fixes read projections without changing stored data. r2 and fresh n2 contract pass. Full pinned target API at a2359d4 remains running; full queue commit requires its own pinned result. Previously indexed 21d02df **2,170 PASS/11 SKIP**, Native 400 and Studio 123 remain separate evidence.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: sixteen authenticated ASGI HTTP requests, actual SQLite transitions and two separate process reads. MOCK TESTS: ready provider/capability/account/credential/human/production approval/render/QC/publish consent fixtures. Fresh `C:\vf-publishing-queue-n2` emits six exports. No provider call, actual credential read or paid operation. The first failed rehearsal remains preserved at n1.

EVIDENCE: `docs/north-star/publishing-queue-evidence.json`, `docs/PUBLISHING_CONSENT_QUEUE.md`, four logs, six n2 exports and current parent preservation receipt. Capability 41 remains PARTIAL.

REGRESSIONS: expanded accepted code checks pass; installed runtimes, accepted/live source/media/data/processes/credentials and main stay untouched. No deployed schema migration, real publishing/deletion, paid call, main merge or production deployment.

EXTERNAL BLOCKERS: eventual real credentials/account audit/Owner publish enablement; no current safe-work blocker. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve queue increment, then connect official account/credential checks, journal, encrypted sessions and verified bytes to the upload worker; continue all remaining North Star waves.

### Wave 9 — scoped in-memory OAuth and exact account protocol

WAVE: 9 / official account admission. STATUS: IN PROGRESS; inert credential/account protocol fixtures pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `472754aaf293a5475e910a590a9e34a96503ffc0`; this OAuth prerequisite commit records the increment. Parent is pushed and preserved in verified `north-star-publishing-queue.bundle`, SHA256 `b2ed7d5be00405c331a3e1938781caff6c99d5619f478ce46060b7308aa06dcc`. Receipt binds prior fresh fifteen-artifact/live-source verification, unchanged main and 149 ahead/0 behind.

CAPABILITIES COMPLETED: strict frozen scoped in-memory token envelope with hidden token, exact reviewed account/profile/provider/credential revision, aware expiry/margin and dedicated upload/account-read scope admission. Resolver/malformed credential failures contain fixed codes, no raw secret text. Official YouTube channels.mine request and exact single-account parser reject ambiguity/pagination/errors without selecting another account. Primary official account/OAuth contracts are linked. No secret acquisition, refresh, persistence or default factory activation.

CAPABILITIES PARTIAL: actual official account verification and OAuth acquisition/refresh/key custody, full consent/byte/session/cost upload worker, processing/thumbnail/scheduler/receipts, profile administration, atomic edit admission/orphan recovery, complete TikTok/Meta and Native UI. Scope/account protocol builders alone confer no permission and do not establish Publishing/Mode A/B Ready.

TESTS: credential/wire/YouTube protocol **66 PASS**, 0.45s, including thirty-one new credential/account fixture cases. r1 21/21, r2 53/53 before existing thirteen YouTube protocol cases were included in r3. Full Linux target commit `a2359d4` passed **2,194 PASS/11 SKIP**, 1,090.57s; target/queue evidence now records this result. The queue's source-specific expanded regression remains 145/145; a full combined queue/OAuth commit regression will follow. Native 400/Studio 123 remain separately pinned.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: type/expiry/scope/identity checks in the actual API runtime. MOCK TESTS: every account/OAuth token/profile/scope/response is a fixture; one explicit MockTransport GET checks official origin/header/body and returns a fixture account. Zero real provider requests, real credentials read or paid operations; no official account claim.

EVIDENCE: `docs/north-star/publishing-oauth-evidence.json`, three logs, current parent preservation receipt and `docs/PUBLISHING_OAUTH_ACCOUNT_ADMISSION.md`. The evidence index records original primary contract URLs and distinguishes the single mock account request from all protocol mocks.

REGRESSIONS: existing wire/YouTube protocol and preserved target full API pass. No installed runtime modification, accepted/live source/media/data/processes/secrets, production schema, main merge, real publish/delete or deployment change.

EXTERNAL BLOCKERS: eventual configured OAuth/account audit/Owner external publishing enablement; no current safe-work blocker. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve increment/run combined pinned Linux API, then implement the durable upload/cost worker and remaining North Star waves.

### Waves 8/9 — pre-wire costs and fenced upload/reconciliation worker

WAVE: 8/9 / costs and upload. STATUS: IN PROGRESS; inert one-step worker/cost/mock wire and actual media/restart acceptance pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `de9546b07e0ad492775789aa7c9755185e47bb97`; this worker commit records the increment. Parent is pushed/preserved in verified `north-star-publishing-oauth.bundle`, SHA256 `e64f114abd635090d5d8a5e49ab372c251088d3585237d511ecebc4167e93a51`. Receipt binds unchanged main and prior fresh fifteen-artifact/live-source verification; 150 ahead/0 behind.

CAPABILITIES COMPLETED: a strictly scoped inert one-step worker ties fresh Owner gates/target/account/scopes/expiry to actual byte/QC admission, committed request/cost intent, fenced writes and encrypted receipts. Shared session factory is required. Missing key/crypto blocks before wire; changed refreshed token receives another account check. Overall request timeout is sixty seconds and changed policy blocks. Mock parent/cost state is explicit and cannot silently go live. Lost initialization never re-POSTs; lost known-session final response reconciles from one encrypted URI after restart/consent revocation. Upload is separate from processing/publication. Existing provider/cost/event tables record unavailable amounts/model/job/quota as null, planned units, fixed outcomes and request-key refusal. Configured cap blocks unknown/overspend; publishing reservations serialize; proven-unsent estimates retain history without fabricated actual zero. No schema migration or factory activation.

CAPABILITIES PARTIAL: orphaned receipts, atomic edit admission, full job/scheduler/locking and cached QC/copy reuse, processing/receipt/thumbnail finalization, profile/price/OAuth/key administration, actual billing/global provider budget coordination, full TikTok/Meta and Native UI. This does not complete Publishing, Mode A/B or final A/B/C bundles.

TESTS: initial worker/cost **18/18 PASS**, 329.74s; expanded credential/protocol/queue/worker/cost **104/104 PASS**, 95.63s, including fifteen cost/seven worker cases. Final outcome metadata **2 PASS/13 deselected**, 7.53s. First cost run 13 passed/1 fixture assertion failed by including old render costs; the assertion now targets exactly the three new publishing reservations, retaining old records. Second cost run 15/15 passed. Final source/session-factory/outcome changes are additionally exercised by fresh real-media n2 contract. Full Linux parent de9546b **2,241 PASS/11 SKIP**, 1,288.13s indexes queue/OAuth together; full forthcoming worker commit remains pending. Native 400/Studio 123 remain separately pinned.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual existing SQLite transactions/costs/CAS, AES-GCM, local byte/range operations and two full QC scans of the preserved synthetic **1080×1920 H.264/AAC, 4,256,257-byte** source. MOCK TESTS: six official-format mock requests, one init, lost final reply and separate-process query reconciliation. All identity/account/key/OAuth/approvals/provider receipts/timeline/subtitle QC inputs are fixtures; media quality is actual. No real speech, Video Factory final render, Owner UAT, paid invoice or real post. Original source hash remains unchanged.

EVIDENCE: `docs/north-star/publishing-worker-evidence.json`, `docs/PUBLISHING_UPLOAD_WORKER.md`, seven logs and six fresh exports under `publishing-worker-contract-n2`. Both n1/n2 owned rehearsals pass and remain preserved. Roots `C:\vf-publishing-worker-n1` and n2; received media matches the original hash. Processing acceptance NOT_CHECKED; published false. Cost model/job/actual fields remain null when unavailable.

REGRESSIONS: expanded checks and full previous API pass. Accepted/live source/media/data/processes/credentials, installed runtimes, main and default publishing settings remain untouched. No deployed schema change, real publishing/deletion, paid call, main merge or deployment.

EXTERNAL BLOCKERS: eventual OAuth/key/account audit/Owner real publishing authorization; no current safe-work blocker. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve/run pinned worker regression, finish session recovery/processing/scheduler/adapters/UI and continue remaining media/analytics/learning/Trend/Hub/hardening waves.

### Wave 9 — sealed-session recovery and observed processing

WAVE: 9. STATUS: IN PROGRESS; local receipt recovery, processing/visibility/schedule persistence and mock completion pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `5522f3825726b57c49437373fc05400ae15e336c` pushed/preserved in full-history `north-star-publishing-worker.bundle`, SHA256 `6c59a29b16304353a7c285d183dc6232da1bd33d0bcf884a4bbb5a0ea09d00fc`; receipt binds 151 ahead/0 behind and unchanged remote main. New recovery/processing source is this increment.

CAPABILITIES COMPLETED: exact-version scoped AES receipt recovery from orphaned initialization, no provider call/re-POST/receipt extension, stale-ticket fencing, revoked-consent past-response recovery while future chunks remain blocked. Scoped processing GETs and cost intents; selected privacy/deadline observations retain nulls, immutable mock/real-mode receipt boundary, append-only audit, exact scheduled deadline followed by observed public release. Correct consent/scheduled Studio labels.

CAPABILITIES PARTIAL: durable scheduler, poll/backoff/worker ownership/QC reuse, atomic edit admission, thumbnail/profile/OAuth/key administration, full TikTok/Meta, Native UI and production wiring/actual acceptance. Uploaded remains distinct from processed/published. Mock completion is not real publishing or final A/B/C acceptance.

TESTS: recovery/vault/worker **33 PASS**, 162.04s; processing/protocol **23 PASS**, 47.65s; **21 new cases** total. Studio **123 PASS**, 786.9062ms. Parent full Linux 5522f38 is running; current recovery increment full regression pending a pinned commit.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual SQLite/AES and two full QC scans of the preserved 4,256,257-byte synthetic portrait MP4; two separate Python processes recover and record processing; receiver bytes match unchanged source. MOCK TESTS: six official-format requests with one initialization, zero recovery requests, mock processed/private receipt with null URL and published=false. Identity/account/OAuth/key/human approval/provider/timeline/subtitle inputs remain fixtures; no real speech, Video Factory final render or Owner UAT.

EVIDENCE: `docs/north-star/publishing-completion-evidence.json`, `docs/PUBLISHING_RECOVERY_PROCESSING.md`, four logs and seven exports in `publishing-completion-contract-n1`. Owned root `C:\vf-publishing-completion-n1` retained. Actual billing remains null.

REGRESSIONS: 56 focused API and 123 Studio checks pass. Accepted/live media, source, database/processes/credentials, installed runtimes, main and default disabled publishing remain untouched. No deployed migration, paid call, external post/deletion, protected-main merge or deployment.

EXTERNAL BLOCKERS: eventual real OAuth/key/account audit/Owner real publishing enablement; no safe-work blocker now. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve this increment; finish durable scheduling/adapters/UI and continue all media/analytics/learning/Trend/Hub/hardening waves.

### Wave 9 — durable leased publishing scheduler and work API

WAVE: 9. STATUS: IN PROGRESS; durable queue/leases/retry/polling and Owner/API admission pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `51ce5a0b54791b3eb1080fe91759722baf2e3fed` pushed/preserved in verified `north-star-publishing-completion.bundle`, SHA256 `5e71c4baaab46b332126961053ced7dd596d3abe5dba7b8e52ef0f5826a99994`. Fresh receipt verifies all fifteen accepted hashes, clean live source `2ced7b`, unchanged remote main and 152 ahead/0 behind. New scheduler is this increment.

CAPABILITIES COMPLETED: additive scoped one-work-per-publication queue, current Owner consent/enablement admission, no-wire enqueue, viewer status, exact-version exclusive leases, private ownership guards before admission/intent/wire, expired-worker fencing, bounded step/time/retries, numeric Retry-After and partial-ack delay, no-wire wait for active dispatch lease. Known final ambiguity queries; unknown init cannot repeat. Actual leased restart mock completion and immutable processing evidence. Prior failed-processing reason survives later unknown observations.

CAPABILITIES PARTIAL: production startup/configuration, cancellation/resume administration, copy/QC reuse, atomic edit admission, thumbnail/profile/OAuth/key lifecycle, full TikTok/Meta, Native UI and actual acceptance. Work identifiers are real; generic JobORM IDs/actual billing remain unavailable/null.

TESTS: first scheduler/migration/worker/processing **29 PASS**, 168.72s; ownership expansion **11 PASS**, 58.21s; final scheduler/API/queue/migration/worker/protocol/processing **64 PASS**, 171.27s; active-dispatch lease **1 PASS/12 deselected**, 10.11s; API/queue **19 PASS**, 88.51s. **17 new cases** (13 scheduler/3 API/1 migration). Full Linux pinned **5522f38: 2,263 PASS/11 SKIP**, 1,471.00s; worker evidence now indexes that result. Current scheduler/full recovery descendant regression awaits the new pinned commit. Studio 123 remains separately verified.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual SQLite leases/costs/CAS/AES, additive owned migration preserving every old table SQL/row and ORM/FK/unique/check/index parity, two actual full QC scans of unchanged 4,256,257-byte synthetic portrait source, two separate processes claiming/querying/completing durable work. MOCK TESTS: eight official-format calls, one initialization, lost final response, known-session query and mock processing receipt; no real post/URL/paid invoice. Human/account/OAuth/key/approval/provider/timeline/subtitle inputs remain fixtures; no real speech/Video Factory final render/Owner UAT.

EVIDENCE: `docs/north-star/publishing-scheduler-evidence.json`, `docs/PUBLISHING_DURABLE_SCHEDULER.md`, seven logs and six n2 exports. Both owned n1/n2 rehearsals pass and are retained. Root `C:\vf-publishing-scheduler-n2`. Publishing-worker full Linux result and fresh preservation receipt are linked.

REGRESSIONS: final focused API checks pass. Accepted/live source, media, database/processes/credentials, installed runtimes, main and default disabled publishing remain untouched. No production migration, paid call, real post/deletion, main merge or deployment. Old pre-0019/0020 migration fixtures exclude the later additive work table, preserving their historical boundary.

EXTERNAL BLOCKERS: eventual real OAuth/key/account audit/Owner real publishing enablement; no current safe-work blocker. OWNER ACTION REQUIRED: none now. NEXT WAVE: preserve/run full pinned scheduler regression; finish providers/runtime/Native distribution UI and all remaining media/analytics/learning/Trend/Hub/hardening waves.

### Waves 7/9 — versioned scoped publishing profile configuration

WAVE: 7/9. STATUS: IN PROGRESS; strict public profile configuration/unit contracts pass. MULTI_NICHE_READY = NO; PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `f7858b6d2a451c2fe82b2b6baaaaa99c5559dea0` pushed/preserved in verified `north-star-publishing-scheduler.bundle`, SHA256 `a0720d267fd18e55aa5a43940cb4cdb8a2ee31c042d71bf715fab96891fec157`; receipt links fresh fifteen accepted hashes/clean live source/unchanged main and 153 ahead/0 behind. Profile configuration is this increment.

CAPABILITIES COMPLETED: versioned public PublishingProfile/catalog schema, official platform/provider mapping, workspace/channel selection, no foreign fallback, copied immutable revision history, additive catalog replacement, required explicit YouTube disclosures, exact nullable costs and bounded secret-free JSON.

CAPABILITIES PARTIAL: provider/runtime registration, persistent Owner administration/profile custody, channel/catalog Native UI, complete configuration-family integration, credentials/key lifecycle and real account/provider acceptance. This is configuration evidence, not an external publishing or full multi-channel production acceptance.

TESTS: **20 PASS**, 3.92s. First harness run passed nineteen but produced two setup/teardown errors when pytest expanded the 256 KiB test payload into a Windows environment-variable case name. Short case IDs correct it; current rerun has no warnings/errors. Underlying oversized catalog rejects. Full Linux scheduler parent f7858b6 is running; new profile full regression not yet run. Latest complete API at 5522f38 remains 2,263 pass/11 skip.

REAL PROVIDER TESTS: none. MOCK TESTS: profile/account/binding identities and price inputs are explicit fixtures; no fabricated observed cost or verification. EVIDENCE: `docs/north-star/publishing-profile-evidence.json`, `docs/PUBLISHING_PROFILE_CONFIGURATION.md`, two private recovery logs. Initial oversized output is preserved by hash and never copied into public evidence.

REGRESSIONS: current pure configuration checks pass; source engine, accepted/live data/media/processes/credentials, main and disabled defaults remain unchanged. No migration, provider/paid call, new budget approval, real publish/delete, main merge or deployment.

EXTERNAL BLOCKERS: eventual authorized account/OAuth/key/real-provider acceptance; no safe-work blocker now. OWNER ACTION REQUIRED: none now. NEXT WAVE: connect configured provider/runtime/Native distribution controls and continue all remaining media/analytics/learning/Trend/Hub/hardening work.

### Waves 8/9 — explicit scoped configured publishing runtime

WAVE: 8/9. STATUS: IN PROGRESS; configured runtime/local-real-media mock contract pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `45b945375a514bb330bbd108eea9fdd8dc827c37` pushed/preserved in verified `north-star-publishing-profiles.bundle`, SHA256 `1398b8d61d77d89388973015ab2fe73401e653efc35e9029e761d0e002998fe6`; 154 ahead/0 behind, main unchanged. Receipt links prior fresh fifteen-artifact/live-source verification. Runtime is this increment.

CAPABILITIES COMPLETED: explicit scoped runtime/provider registration, optional channel-profile selection with backward fingerprints, queued provider submissions, authenticated existing queue path, fresh profile resolution within owned step, bounded due scans/claim races, exact persisted receipt scoping and truthful mock publication/Studio labels. Construction/install performs no request, secret read, task or enablement.

CAPABILITIES PARTIAL: production startup/supervisor, persistent Owner profile and secret administration, local cancel/resume, Native distribution UI, atomic edit/wire admission, QC reuse, thumbnails, TikTok/Meta adapters, actual account acceptance/billing/shared budgets. No production readiness claim.

TESTS: expanded runtime/profile/publishing/queue/scheduler/target/API **86 PASS**, 212.31s; later due-scan competition **1 PASS**, 2.09s. New runtime cases: eight. Studio **123 PASS**, 586.2535ms. Initial run rejected a changed target correctly but its expected fixture code was stale; assertion corrected. Full Linux scheduler `f7858b6`: **2,301 PASS / 11 SKIP**, 1,498.79s; indexed separately. Current runtime full regression awaits pinned commit.

REAL PROVIDER TESTS: none. MOCK TESTS: six authenticated ASGI requests, eight mock provider requests, one initialization, lost final reply, known-session recovery and processing after revocation in two separate reconstructed runtime processes. Actual SQLite/AES and two FFmpeg/FFprobe QC scans pass; 4,256,257-byte synthetic portrait source remains unchanged. Eight actual cost fields remain null; identity/account/OAuth/key/approval/timeline/subtitle inputs are fixtures. Published = false; no remote URL/external action.

EVIDENCE: `docs/north-star/publishing-runtime-evidence.json`, `docs/PUBLISHING_CONFIGURED_RUNTIME.md`, five recovery logs and eight hashed contract exports. Contract is not Owner UAT or final A/B/C acceptance.

REGRESSIONS: focused checks pass; full current commit pending. Accepted/live media, source/processes/data/credentials, main, disabled defaults and existing schemas remain untouched. No real publish/delete, paid operation, migration or deployment.

EXTERNAL BLOCKERS: eventual authorized provider/account/credential/key acceptance. OWNER ACTION REQUIRED: none for remaining safe work. NEXT WAVE: complete official TikTok/Meta mock provider paths, distribution controls and remaining media/analytics/learning/Trend/Hub/hardening capabilities.

### Waves 8/9 — official TikTok transfer/status and stable account protocol

WAVE: 8/9. STATUS: IN PROGRESS; protocol/account fixture and real synthetic-byte mock transfer pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `dad237a7f6772e1b1bdbe8db795e339337aa00a7`, pushed and preserved in verified `north-star-publishing-runtime.bundle`, SHA256 `9aee43cbdf7bdc4c3d84390c03b411e5861b23a2a95b0a9f8bad682506fc32e6`; 155 ahead/0 behind, main unchanged. TikTok protocol/account is this increment.

CAPABILITIES COMPLETED: inert official device FILE_UPLOAD and trusted-prefix server PULL_FROM_URL builders, explicit privacy/interaction/commercial/AI/music/branded choices, UTF16 captions, fresh creator limits, floor/sequential chunk plan and merged tail, signed upload URL/expiry/origin/auth fences, processing/null public-ID parser, dedicated in-memory scopes/expiry/target checks and exact stable open_id lookup. Regional documented upload host added to strict allowlist; existing YouTube behavior retained.

CAPABILITIES PARTIAL: durable TikTok intent/lease/session/cost/consent binding, verified-pull custody/lifetime, provider supervision, Studio UI and actual account audit/credentials. Helpers perform no automatic request/retry/initialization replay. No invented provider idempotency, billing, URL or metric.

TESTS: **147 PASS**, 0.70s; 57 new protocol and 24 credential cases. Earlier incremental selections **79 PASS**, 1.20s; **80 PASS**, 1.62s; **92 PASS**, 0.57s. Existing YouTube/HTTP/account contracts pass. Full runtime parent dad237a runs independently in pinned Linux checkout; current protocol full suite pending.

REAL PROVIDER TESTS: none. MOCK TESTS: six official MockTransport requests with one initialization transfer preserved 4,256,257-byte synthetic portrait source exactly and observe processing then private completion with absent public IDs. Actual FFprobe inspection/hash pass; source unchanged. No full QC in this protocol contract, no durable job or cost records; actual cost null. Credentials/account/disclosure/user confirmations are fixtures. Published = false; real/paid requests and secret reads = zero.

EVIDENCE: `docs/north-star/tiktok-protocol-evidence.json`, `docs/TIKTOK_OFFICIAL_PUBLISHING_PROTOCOL.md`, five logs and five hashed contract exports. Not Owner UAT/final A/B/C acceptance.

REGRESSIONS: focused contracts pass; current full suite pending. Accepted/live data/media/processes, main, publishing defaults and schemas remain untouched. No real publish/delete, paid operation, live migration or deployment.

EXTERNAL BLOCKERS: TikTok official guidance excludes private/internal team upload utilities and requires eligible creator-facing product/provider review, private accounts for unaudited clients and verified ownership for server pull media. Actual product/provider/credential acceptance remains BLOCKED_EXTERNAL; no safe-work blocker. OWNER ACTION REQUIRED: none now. NEXT WAVE: durable authorized adapter paths, Meta official providers/controls and all remaining safe North Star capabilities.

### Waves 8/9 — API Studio exact publish review and separate consent/queue controls

WAVE: 8/9. STATUS: IN PROGRESS; review/API/Studio fixture and actual-media mock restart checks pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `27dce5d516d7beae357fed1b365c2b97d5d971e0`, pushed/preserved in verified `north-star-tiktok-protocol.bundle`, SHA256 `29c301757060a4aecc5eadd9417a391a60bc96bae73c6f6933eff5f859a92c86`; 156 ahead/0 behind. Fresh preservation verifies all fifteen accepted hashes and clean live source 2ced7bc; main unchanged. Console is this increment.

CAPABILITIES COMPLETED: project-scoped latest public profiles; current no-store review snapshot with exact render/artifact/target/metadata binding and active consent validation; API Studio separate prepare, acknowledge/consent, explicit enqueue, status refresh and selected-consent revoke; exact Owner workspace/global/slug role, textContent metadata rendering, stale scope/expiry/hash rejection, disabled defaults and optional explicit schedule input. Reads/consent never chain queue/provider execution.

CAPABILITIES PARTIAL: Native distribution controls, browser sizes/Owner usability acceptance, persistent Owner configuration/secret administration, cancel/resume, production supervision and non-YouTube durable adapters/real acceptance. No readiness or UAT acceptance claim.

TESTS: expanded API review/profile/runtime/work/queue **51 PASS**, 516.95s; four new API cases independently **4 PASS**, 45.92s. Studio **130 PASS**, 2,551.8853ms; seven focused console cases after final binding additions **7 PASS**, 111.4237ms. JS syntax/diff checks pass. Initial collection error was an incorrect new-test AssetORM import, corrected to app.db. Full dad237a Linux runtime parent remains running; current full suite pending pinned commit.

REAL PROVIDER TESTS: none. MOCK TESTS: expanded real-media runtime contract has nine authenticated ASGI requests including viewer profiles/exact review/revoked review; two actual QC scans, SQLite/AES, two reconstructed runtime processes, one initialization and eight mock provider requests. Source remains identical 4,256,257-byte synthetic portrait; actual costs null. All roles/accounts/keys/credentials/approval/timeline/subtitle fixtures; published=false, no real/paid calls/secret reads. UI tests use an explicit DOM/API harness, not a browser acceptance.

EVIDENCE: `docs/north-star/publishing-console-evidence.json`, `docs/STUDIO_PUBLISH_REVIEW_QUEUE.md`, six recovery logs and nine preserved hashed JSON exports in publishing-runtime-contract-n2. Prior n1 is retained. Not final A/B/C acceptance or Owner UAT.

REGRESSIONS: current focused selections pass; full suite pending. Accepted/live media/source/data/processes, main, existing schemas and publishing defaults remain untouched. No actual publish/delete, paid operation, live migration or deployment.

EXTERNAL BLOCKERS: eventual actual account/credential/provider acceptance and Owner UAT; no safe-work blocker. OWNER ACTION REQUIRED: none now. NEXT WAVE: official Meta protocol/adapters, durable non-YouTube paths, Native integration and remaining media/analytics/learning/Trend/Hub/hardening capabilities.

### Wave 9 — official Meta container/upload/status protocol

WAVE: 9. STATUS: IN PROGRESS; Meta mock protocol and exact physical synthetic-byte transfer pass. PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `e6754e232a31dc771762d9bf86e38f72da9fe5c4`, pushed/preserved in verified `north-star-publishing-console.bundle`, SHA256 `bd13b3ba7b8cc67fbb08416fe60a43b1e728ec37fff55425dd698b47b408a1d2`; 157 ahead/0 behind. Fresh preservation verifies fifteen accepted hashes and clean live source 2ced7bc; main unchanged. Meta protocol is this increment.

CAPABILITIES COMPLETED: inert Facebook-Login explicit Graph version/account/object helpers; Instagram create REELS container, exact status observation, target-bound FINISHED admission and separate publish request; Facebook start, exact official rupload binding, bounded bytes/authorized hosted URL, explicit DRAFT/PUBLISHED finish and separate nullable phase/progress observation. Strict official Meta hosts added without default network activation. Raw errors/secret URLs never become public evidence; no vendor idempotency is invented.

CAPABILITIES PARTIAL: durable Meta credential/account/permission/consent/cost/intent/session/lease/reconciliation/supervisor paths, full metadata/login variants, actual hosted retrieval, provider-specific UI and current real provider acceptance. Local binary body cap 16 MiB and caption cap 2,200 are internal supported profiles; no claim about current vendor maxima. Draft/upload/finish success is not an accepted public receipt.

TESTS: **153 PASS**, 0.73s including 37 new Meta cases and existing TikTok/YouTube/HTTP checks. Initial new-module exception syntax collection error corrected before passing run. Full runtime parent dad237a Linux remains running; current pinned full regression pending.

REAL PROVIDER TESTS: none. MOCK TESTS: seven official MockTransport requests; exact preserved 4,256,257-byte synthetic portrait bytes received by Facebook fixture, draft finish and nullable phases; separate Instagram FINISHED container/fixture media ID. Actual hosted download/account/permissions/version not verified, no full QC in this protocol-only contract. Actual costs null; no cost records, real/paid requests or secret reads. Published=false; no production activation.

EVIDENCE: `docs/north-star/meta-protocol-evidence.json`, `docs/META_OFFICIAL_PUBLISHING_PROTOCOL.md`, three logs and four preserved hashed JSON exports. Official Meta collections used after reference pages returned rate limits. This is mock protocol evidence, not Owner UAT/final A/B/C/provider/production acceptance.

REGRESSIONS: selected protocols pass; current full suite pending. Accepted/live source/media/data/processes, main, schemas and publishing defaults remain unchanged. No real publish/delete, paid operation, live migration or deployment.

EXTERNAL BLOCKERS: eventual current authorized provider/version/account/permissions/credential/storage acceptance; no safe-work blocker. OWNER ACTION REQUIRED: none now. NEXT WAVE: durable scoped Meta/TikTok adapters and account admission, remaining Native/provider controls, analytics/learning/Trend/Hub/hardening capabilities.

### Wave 10 — scoped official analytics reads and immutable observations

WAVE: 10. STATUS: IN PROGRESS. ANALYTICS_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `5a5686d4ef758f9342e3e67fc0246842867fe56b`, pushed/preserved in `north-star-meta-protocol.bundle`, SHA256 `4ff09fa2fb70791b7bdbd60408c32f382ac791198958c857b2587c5dfa0ec655`; fresh prior receipt verifies 15 accepted media and clean live 2ced7bc, main unchanged. This analytics increment will be separately pushed/bundled.

CAPABILITIES COMPLETED: explicitly installed scoped read-only YouTube/TikTok adapters; account/video/receipt/workspace binding; dedicated in-memory read credential admission; bounded official transport with separate host purpose; strict nullable normalization, seconds/VND provider estimates; privacy/error/backoff handling; atomic claim and attempt fences; durable per-read cost intents and null actual billing; historical snapshots/evidence; frozen published edit features; private API response cache policy.

CAPABILITIES PARTIAL: Meta collectors, operator bootstrap/configuration, Native analytics, channel refresh policy, channel/time-series/comparison UI, PostgreSQL migration/queue recovery acceptance, winner baselines and publication-time project feature freezing.

TESTS: 92 selected checks PASS in 56.40s; after frozen edit-feature changes, 15 affected runtime/legacy checks PASS in 52.44s (overlap, not added). Offline migration retains every seeded old row with zero FK violations and refuses unsafe online SQLite before writes. Initial default temp folder access errors, an offset-naive ORM evaluation error, and missing legacy analysis fixture were corrected and retained in logs. First standalone contract used nonexistent `/events` rather than existing `/history`; corrected into fresh bundles without replacing prior files. Prior full Linux at 5a5686d4ef758f9342e3e67fc0246842867fe56b: **2451 PASS / 11 SKIP**, 924.32s; analytics full regression pending pinned commit.

REAL PROVIDER TESTS: 0. MOCK TESTS: six official mock reads, five authenticated API requests, two immutable snapshots, six cost records with actual_cost=null; fresh process restores exact snapshot JSON. Transport-true unit test is explicitly a flag simulation, not real-provider evidence.

EVIDENCE: `docs/north-star/analytics-read-evidence.json`; recovery `analytics-read-contract-n3` has eight JSON exports and cloned SQLite DB; retained source DB is byte-identical, its pre-existing fixture FK debt is recorded unchanged. No media replaced.

REGRESSIONS: no accepted media/Owner UAT/source rewritten; default provider and publishing gates retained. Schema changes rehearsed only on owned copies, no live migration.

EXTERNAL BLOCKERS: actual authorized accounts, OAuth scopes/permissions and provider acceptance; PostgreSQL/Docker isolated rehearsal unavailable. OWNER ACTION REQUIRED: none for ongoing safe implementation; separate credentials/permission required for real acceptance and Owner UAT remains pending.

NEXT WAVE: complete analytics operator/UI/channel integration, winner baselines, learning personalization, full Trend Radar/Hub/production/final acceptance gaps; all original Master Spec waves remain in scope.

Wave 10 follow-up: after final capability reporting and real-transport admission guards, 18 safety/capability checks and nine affected runtime checks pass. These overlap earlier counts. Real transport additionally requires an explicit trusted project cost-policy callback and enabled analytics registry; omitted policy leaves it not configured. No actual provider call occurred.

### Wave 10 — Studio source/publication controls and observation history

WAVE: 10. STATUS: IN PROGRESS. ANALYTICS_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `32db5d9c1cd631819ab768d76e7472e6e4eefe31`, pushed/preserved in `north-star-analytics-reads.bundle`, SHA256 `c335574ba7f1f0c28db905a128d5cceb41cb46cc965e545e9da2bcf87559c34a`; 159 ahead/0 behind, fresh 15 artifact hashes and clean live source verified. Source/UI increment will be separately preserved.

CAPABILITIES COMPLETED: explicit publication/source collection, fixture profile default normal, YouTube date/revenue choice and TikTok cumulative semantics; editor/Owner queue and viewer reads; scoped source-filtered API report/history/assessment/learning; null-preserving chart/table and report-scope comparison; stable ordering; idempotent unknown-submit retry, new confirmed manual refresh; stale project/source/sync guards and active-job polling. No read/selection chains a mutation.

CAPABILITIES PARTIAL: channel-wide overview/refresh, Native analytics, operator/bootstrap, Meta collectors, production pagination, actual browser/viewport/Owner UAT, provider acceptance and winner/learning/channel baselines.

TESTS: **18 PASS**, 97.22s selected authenticated API/runtime/legacy tests (three new publication/source/role cases); **139 PASS** full Studio suite, 595.39ms (nine new analytics cases). JS syntax and diff checks pass. Full Linux parent `32db5d9c1cd631819ab768d76e7472e6e4eefe31`: **2498 PASS / 11 SKIP**, 1000.51s. Current increment pinned full regression pending.

REAL PROVIDER TESTS: 0. MOCK TESTS: six official mock reads and nine authenticated API requests; two immutable snapshots restore exactly in a fresh process, six actual-cost-null records. Official/fixture scoped reads show two/zero snapshots respectively. DOM harness is not a real browser acceptance.

EVIDENCE: `docs/north-star/analytics-console-evidence.json`, fresh `analytics-read-contract-n4` eight JSON exports plus copied database; original database SHA unchanged. Prior n1/n2/n3 bundles are retained.

REGRESSIONS: accepted media/source/Owner UAT untouched; all selected tests pass. Default fixture/disabled-network/publishing gates retained. EXTERNAL BLOCKERS: authorized accounts/credentials/provider acceptance; browser UAT and isolated deployment infrastructure. OWNER ACTION REQUIRED: none for remaining safe work; actual credentials/UAT/deployment are separate gates. NEXT WAVE: channel analytics, winner baselines, frozen learning features/personalization, Trend Radar, Hub, hardening and final A/B/C acceptance; full original scope remains.

### Wave 10 — Bounded history and channel observation UI

WAVE: 10. STATUS: IN PROGRESS. ANALYTICS_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `2b191184b008a7a6144c51a55b7658ad452de17c`, pushed/preserved in `north-star-analytics-console.bundle`, SHA256 `5f6038d4eb946bae2671942b0c25b117dd4c0982c4c3aa5a712fdbafe97142f9`; 160 ahead/0 behind, fresh 15 artifact hashes and clean live source verified. This channel increment will be separately preserved.

CAPABILITIES COMPLETED: 1–100 row keyset observation pages with stable timestamp ties and exact scope; bounded latest-summary queries and SQL history counts; latest assessment/learning alignment; channel publication pages with exact account/profile/provider/transport separation; individual report intervals/nullable metrics, no account totals; explicit 50-row Studio history/channel reads, 500-row view bound, text-node rendering and stale response guards.

CAPABILITIES PARTIAL: Native/operator/AnalyticsProfile integration; durable recurring refresh; Meta collectors; actual account-level analytics/winner baselines; legacy complete-list pagination; browser/viewport/Owner UAT and provider acceptance.

TESTS: **24 PASS**, 116.12s expanded API before final summary refinement; **16 PASS**, 60.55s final affected API tests, overlapping counts (seven new projection cases). **145 PASS** full Studio suite, 757.51ms (six new frontend cases). Syntax/diff checks pass. Full Linux parent `2b191184b008a7a6144c51a55b7658ad452de17c` running; latest completed full at `32db5d9`: 2498 PASS / 11 SKIP. Current channel source full regression awaits pinned commit. Initial API run: 12 PASS/1 FAIL from an incorrect expected fixture value, corrected; old log retained.

REAL PROVIDER TESTS: 0. MOCK TESTS: six official-protocol mock reads and 14 authenticated ASGI requests; two immutable snapshots restore exactly in a fresh process, six actual-cost-null records. Channel transport flag isolation test is deliberate metadata simulation, not observed provider acceptance. DOM harness does not certify browser usability.

EVIDENCE: `docs/north-star/analytics-views-evidence.json`; fresh `analytics-read-contract-n6` nine JSON exports plus owned clone DB. Original source DB hash unchanged; n1–n5 retained.

REGRESSIONS: accepted media and live source untouched; fixture/network/publishing defaults retained. No live schema migration, provider credential read or paid call. EXTERNAL BLOCKERS: real authorized account/provider acceptance and Owner/browser UAT. OWNER ACTION REQUIRED: none for continuing safe implementation; real credentials, UAT and deployment are separate gates. NEXT WAVE: durable refresh and queue safety, frozen learning features/channel winner baselines, remaining Native/media/Trend/Hub/hardening and final A/B/C acceptance. Original Waves 0–16 remain in scope.

### Wave 10 — Scheduling, UTC and queue recovery safety

WAVE: 10. STATUS: IN PROGRESS. ANALYTICS_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `421975542225e1429136678032d15df86aa3adf5`, pushed/preserved in `north-star-analytics-views.bundle`, SHA256 `dac67fae94f87160e331969d740305d68a813e16e60498dac8d6e54adbb0314b`; 161 ahead/0 behind, fresh 15 artifact hashes and clean live source verified. Safety increment will be separately preserved.

CAPABILITIES COMPLETED: explicit schedule gate cannot be bypassed by another trigger; worker and each official read recheck revocation; provider minimum retry interval respected; bounded due CAS/skip-locked claims; stable queued-job recovery after failed admission; atomic Redis-list admission architecture; content-free queue errors; disabled fixture capability state; new offset timestamps normalized to UTC across restart with naive provider timestamps rejected. Historical rows/exports remain intact; legacy non-UTC schedules are not recertified.

CAPABILITIES PARTIAL: durable recurring refresh and Owner controls; Native/operator/AnalyticsProfile integration; real Redis Lua/PostgreSQL skip-locked/outage/soak acceptance; active-attempt restart; Meta/account-level collectors, winner/learning baselines; browser/UAT and real provider acceptance.

TESTS: **46 PASS**, 149.22s final selected API/worker suite (17 new API and two new worker cases); **145 PASS** Studio, 713.5628ms. Earlier overlapping runs: 29 PASS; 34 PASS; corrected worker-only four PASS. Initial failures were test expectations: concurrent readers can select the same first page, and an existing queue assertion was misplaced while adding a test. Both were corrected and logs retained. Full Linux `2b19118`: **2501 PASS / 11 SKIP**, 1177.88s; channel parent `4219755` running. Current safety source awaits pinned full regression.

REAL PROVIDER TESTS: 0. MOCK TESTS: mocked queue outage/recovery, concurrent owned SQLite claims, between-read schedule revocation, long Retry-After and +07:00 timestamp restart. Fresh n8 contract performs six official mock reads/14 authenticated requests, restores two exact snapshots and records six unknown billed costs. Redis mock does not execute Lua; PostgreSQL skip-locked remains unverified.

EVIDENCE: `docs/north-star/analytics-scheduler-safety-evidence.json`, fresh `analytics-read-contract-n8` nine JSON files plus clone DB; original DB hash unchanged. All n1–n7 retained.

REGRESSIONS: accepted media/live source/default network/publishing/Owner gates retained; no live migration, provider call, credential read or paid operation. EXTERNAL BLOCKERS: optional isolated Redis/PostgreSQL/Docker runtime and actual provider/UAT acceptance. OWNER ACTION REQUIRED: none for remaining safe work; real credentials, UAT and deployment remain separate gates. NEXT WAVE: persisted recurring plans, frozen learning/channel baselines, remaining Native/media/Trend/Hub/hardening and final A/B/C acceptance. Original Waves 0–16 remain the objective.

### Wave 10 — Durable recurring read plans and Owner controls

WAVE: 10. STATUS: IN PROGRESS. ANALYTICS_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `6751c27ff7f3dc0677e5af55cef6f0a6e7492e60`, pushed/preserved in `north-star-analytics-scheduler-safety.bundle`, SHA256 `76b8ae651099d988194f04ca0e6a00f0c04801217b17069f95f957a1fc3b8448`; 162 ahead/0 behind, all 15 accepted artifact hashes and clean live source verified. This increment will be separately committed/preserved.

CAPABILITIES COMPLETED: versioned bounded immutable refresh configuration, verified Owner creation/state changes, same-key concurrency, revision/audit and exact provider/publication/destination binding; default-disabled explicit Studio controls; atomic bounded due occurrence/job creation, no catch-up burst and maximum run count; pre-collection/each official read/reservation/completion fences; revoked error retries terminate; re-enablement never revives old occurrences. Successful/error domain responses preserve no-store. Additive three-table migration and refusal of destructive downgrade.

CAPABILITIES PARTIAL: Native/operator/AnalyticsProfile/channel-wide integration; actual Redis Lua/PostgreSQL scheduler/recovery/soak; bounded plan/history pagination; Meta collectors; browser/viewport/Owner UAT; real provider acceptance; frozen project learning features and channel winner baselines.

TESTS: final **64 PASS**, 117.88s selected API/worker/migration/runtime suite (28 new API cases); **152 PASS** full Studio suite, 672.1551ms (seven new cases). Earlier overlapping 61/41/23/38 and model/repository runs are retained. Full Linux safety parent **2525 PASS / 11 SKIP**, 1176.15s; channel parent `4219755` **2508 PASS / 11 SKIP**, 1326.47s. Current refresh source pinned full regression pending. Initial migration fixture omitted Python defaults; fixed. Fresh contract first used an incorrect table/class name, then exposed a missing no-store exception header; corrected with regression coverage. Failed logs/directories remain intact.

REAL PROVIDER TESTS: 0. MOCK TESTS: authenticated Owner ASGI/revocation/concurrency/typed query tests, DOM controls and between-wire/error revocation. Fresh n4 recurring contract: three official mock reads/nine authenticated requests, two prior exact snapshots retained and one new snapshot, two occurrences/one revoked without collection, five plan audit entries, nine unknown billed analytics costs. Fresh process restores exact state. No scheduler fixture date certifies provider coverage.

EVIDENCE: `docs/ANALYTICS_REFRESH_PLANS.md`, `docs/north-star/analytics-refresh-evidence.json`; fresh `analytics-refresh-contract-n4` five JSON exports plus owned clone database. All n1–n3 and manual n9/source databases remain unchanged.

REGRESSIONS: accepted media/live source/default publishing/provider/Owner gates preserved. No live migration, credential read, paid operation or external call. EXTERNAL BLOCKERS: actual authorized provider accounts, Owner/browser acceptance and isolated production infrastructure acceptance. OWNER ACTION REQUIRED: none for remaining safe implementation; live secrets/UAT/deployment are separate gates. NEXT WAVE: freeze remaining published project features, channel winner baselines/personalized learning, remaining Native/media/Trend/Hub/hardening and final A/B/C bundles. Original Waves 0–16 remain the objective.

### Wave 12 — Frozen render learning metadata and asset lineage

WAVE: 12. STATUS: IN PROGRESS. LEARNING_LOOP_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `d3d3a77fd1ceca32baa8ae191cfdfbbd4096ce52`, pushed/preserved in `north-star-analytics-refresh.bundle`, SHA256 `ff55c92190d75ac3837249af2631cd57c7781a69b2f98fd391568b92b43e434a`; 163 ahead/0 behind, fresh 15 accepted hashes and clean live source. This increment will be separately committed/preserved.

CAPABILITIES COMPLETED: bounded versioned/digested metadata capture at render request; explicit storyboard-content/version precedence, project/idea source attribution; exact workspace/project/timeline validation; completion replacement refusal/rollback; persisted render evidence and supporting/provider-audio/final assets retain frozen project-version lineage. Analytics uses the published render's metadata, never later current tags; legacy absent metadata stays null. Studio displays available labels and historical-source status.

CAPABILITIES PARTIAL: observed publishing time, semantic label validation, Native parity, channel cohorts/winner baselines, cross-video recommendation aggregation and personalized Trend/Idea/Media/Template feedback. Browser/viewport/Owner UAT and final playable E2E remain.

TESTS: **26 PASS**, 150.27s selected production/publishing/analytics regression (five new cases); **152 PASS** Studio, 767.2223ms. Initial run 22 PASS/1 FAIL: test tried to read cleaned staging evidence; changed to download the persisted evidence asset and added lineage assertion. Original log retained. Parent full Linux `d3d3a77` running; latest completed safety parent 2525 PASS/11 SKIP. Current increment pinned full regression pending.

REAL PROVIDER TESTS: 0. MOCK TESTS: owned SQLite renderer/approval/provider fixtures; four authenticated ASGI calls, two immutable fixture observations, exact fresh-process state, unchanged queue-time labels and persisted asset/evidence lineage after later edits. Media is nonplayable fixture bytes; no full media QC or Owner acceptance implied.

EVIDENCE: `docs/FROZEN_RENDER_FEATURES.md`, `docs/north-star/feature-context-evidence.json`; fresh `feature-context-contract-n1` six JSON exports plus owned fixture database/objects. No prior artifact is replaced.

REGRESSIONS: accepted media/live source/timeline/approval/provider/publishing defaults preserved; no live migration or paid/external operation. EXTERNAL BLOCKERS: actual provider, Owner/browser and isolated production acceptance. OWNER ACTION REQUIRED: none for ongoing safe work; concrete real acceptance remains separately gated. NEXT WAVE: channel winner cohorts and personalized recommendations, remaining Native/media/Trend/Hub/hardening and final A/B/C acceptance. Original Waves 0–16 remain in scope.

### Wave 11 — Scoped channel baselines and cumulative counter history

WAVE: 11. STATUS: IN PROGRESS. WINNER_DETECTION_READY = NO; LEARNING_LOOP_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `681d0c6552132ca70e4cfff94bcd878612757cb6`, pushed/preserved in `north-star-feature-context.bundle`, SHA256 `b67e0e0658b629558eda4d88c9e65beb82922e122fc82efaeaa0d8c2a6fda5a0`; 164 ahead/0 behind, fresh 15 accepted hashes and clean live source. Cohort increment will be separately committed/preserved.

CAPABILITIES COMPLETED: versioned configurable ten-factor median channel assessment, distinct remote-post dedupe, exact account/provider/report/transport and frozen niche/format/duration compatibility; valid alternate observations survive corrupt ones, corrupt feature bindings reject; bounded candidate/peer scans and truncation evidence; raw/median/peer refs and policy digest; algorithm-specific learning references; cumulative two-observation growth with both current and peer histories, unknown provider lag and null publishing age/window. No missing retention/completion is invented to classify a winner. Full long annotations retained with explicit safe legacy-column projection.

CAPABILITIES PARTIAL: Native/full channel UI, independent AnalyticsProfile, actual provider/account/coverage/quota acceptance, channel-wide history/soak and personalized aggregate learning. Existing fixture thresholds remain historical/mock behavior. Counter comparisons describe reported changes, not exact event timestamps or lifetime publishing age.

TESTS: **90 PASS**, 240.32s broad selected API/worker suite before final peer/counter refinements; **45 PASS**, 42.96s final affected cohort/feature/config tests. Counts overlap. Twenty-one new cohort cases and one feature boundary case. Prior 39-pass run retained. Initial integrity-test expectation ignored a valid duplicate-post observation; now verifies fallback and later exclusion when both are corrupt. TikTok fixture initially supplied a forbidden validation field; corrected. Initial counter export asserted all cost rows rather than analytics-only rows; corrected to 24 analytics records among 28 fixture ledger rows. Failure logs/directories retained. Full Linux recurring parent **2553 PASS / 11 SKIP**, 1353.10s; feature parent running. Current increment pinned full regression pending. Studio source is unchanged from the previously passing 152-test suite.

REAL PROVIDER TESTS: 0. MOCK TESTS: fresh relative n3 contract retains ten observations/nine prior exact snapshots, five distinct compatible peers, three official mock reads and explicit transport-flag seed simulation. Fresh cumulative n2 contract performs 24 TikTok mock reads over twelve collections, retains twelve exact restored observations and 24 null billed analytics costs; actual publication age, retention, completion and normalized observation-window remain null and assessment is insufficient_data. Earlier clocks/media/approval/receipts are fixtures. Recurring n5 contract still passes three mock reads/nine authenticated requests, one revocation and prior snapshot preservation.

EVIDENCE: `docs/CHANNEL_WINNER_ASSESSMENT.md`, `docs/north-star/channel-cohort-evidence.json`; fresh `channel-cohort-contract-n3`, `counter-history-contract-n2` and recurring n5 JSON/owned databases. All earlier bundles retained; fixture media is nonplayable and does not certify full QC or Owner UAT.

REGRESSIONS: accepted media/live source/default provider/publishing/approval boundaries preserved; no live schema/data migration or paid/external operation. EXTERNAL BLOCKERS: real accounts/provider/Owner/browser and isolated production acceptance. OWNER ACTION REQUIRED: none for continuing safe implementation. NEXT WAVE: personalized recommendation aggregation and Trend/Idea/Media/Template feedback, remaining Native/media/Trend/Hub/hardening and final A/B/C bundles. Original Waves 0–16 remain in scope.

### Wave 12 — Immutable channel learning and reviewed downstream guidance

WAVE: 12. STATUS: IN PROGRESS. LEARNING_LOOP_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `1439c4dae90e83d622c390f09e0baae8af0a10ed`, pushed/preserved in `north-star-channel-cohort.bundle`, SHA256 `644e58f442ea755b579d056e7f4779c005b8cdcebd1361fbf8aaa875998bf69b`; 165 ahead/0 behind, fresh 15 accepted hashes and clean live source. Learning increment will be separately committed/preserved.

CAPABILITIES COMPLETED: additive immutable/digested snapshot persistence and versioned policy; exact channel/report/provider/transport/frozen niche/format scope, distinct remote posts, matching winner policy and scored-factor basis, bounded scan/truncation/exclusion evidence. Descriptive feature/control medians require independent sample thresholds; missing data and actual publishing windows stay unavailable. Authenticated idempotent creation/history/recommendation routes, concurrent replay, reviewed Trend/Idea/Queue/project/MediaPlan advisory lineage and explicit Studio controls preserve approval/cost/publish boundaries. Legacy unrequested fingerprints retain their original serialization.

CAPABILITIES PARTIAL: personalized opportunity ranking, direct catalog template selection, Native integration, semantic labels, actual publication-time evidence, history pagination, real account/provider/browser/Owner acceptance and final playable A/B/C. Original Waves 0–16 remain in scope.

TESTS: **58 PASS**, 143.19s affected API/analytics/trend/media suites (24 new API/migration cases); **159 PASS** Studio, 764.8956ms (seven new cases). Counts overlap prior increments. Initial run 18 PASS/1 FAIL had a new test assuming reviewer lacked existing editing rank; expectation corrected. Next run 33 PASS/2 FAIL had a test assuming existing idea replay order was identical and a schema comparison using reflected type-object identity; fixed to compare candidate identity and SQLite table metadata. All logs retained. Full Linux at `681d0c6`: **2558 PASS/11 SKIP**, 1361.43s. Cohort parent `1439c4d`: **2580 PASS/11 SKIP**, 1398.23s. Current learning pinned full suite pending.

REAL PROVIDER TESTS: 0. MOCK TESTS: owned SQLite histories, six explicit synthetic metric seeds, three official adapter MockTransport reads, three authenticated learning requests, exact seven metric snapshots/assessments/learning/cost restore, fixture Trend evidence and persisted advisory idea lineage. Media-planner guidance-reader integration is a declared stub test. No paid/external operation, actual posting or budget change. Publishing windows remain unavailable.

EVIDENCE: `docs/CHANNEL_LEARNING_SNAPSHOTS.md`, `docs/north-star/channel-learning-evidence.json`; fresh `channel-learning-contract-n2` seven JSON exports plus owned database/objects, prior n1 retained. Fixture media is nonplayable; no full media QC or Owner acceptance.

REGRESSIONS: prior metrics/accepted media/live source and timeline/approval/publishing/provider defaults preserved. Migration 0024 rehearsed on a new owned SQLite database only; live schema unchanged. EXTERNAL BLOCKERS: real accounts/provider/Owner/browser and isolated production acceptance. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: personalized opportunity ranking/template review/Native learning; remaining media/Trend/Hub/production hardening and final A/B/C. Continue the full original North Star.

### Wave 12 — Personalized proposals and explicit subtitle-template review

WAVE: 12. STATUS: IN PROGRESS. LEARNING_LOOP_READY = NO; TREND_RADAR_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `45e274be77d26876856ed0b836739dc666ba4caa`, pushed/preserved in `north-star-channel-learning.bundle`, SHA256 `9eaa545eb3436832655454b6d7da61b1012ca0e8f1661160a4e4ddbc0573a62b`; 166 ahead/0 behind, fresh 15 accepted hashes and clean live source. Personalized increment will be separately committed/preserved.

CAPABILITIES COMPLETED: explicit versioned/bounded history ranking controls, separate base/history/result estimates and snapshot/group refs; insufficient history retains null adjustment and original estimate. Read/refresh/Idea/Queue proposals persist policy/source lineage; same-state queues replay and changed policies produce distinct runs. Subtitle-style associations map to versioned catalog starters with compatibility/unknown-style/word-timing guards. Studio provides explicit stored-history ranking, source labels, template reading/form selection and existing version-checked save; no automatic edit or irreversible action.

CAPABILITIES PARTIAL: Native parity, independent channel/operator configuration, semantic feature validation, authoritative publication times/windows, full first-class Trend Radar, real accounts/providers/audience acceptance, browser/Owner and final playable A/B/C. Style-field matching does not prove full historical template identity.

TESTS: **54 PASS**, 154.38s affected API/learning/trend/media/production suites; later route/compatibility **3 PASS**, 19.35s; **164 PASS** Studio, 868.7654ms plus app/studio parse checks. Sixteen new API cases and five new Studio cases; counts overlap previous increments. Full parent Linux `45e274b`: **2604 PASS/11 SKIP**, 1432.09s. Current personalized pinned full suite pending.

REAL PROVIDER TESTS: 0. MOCK TESTS: six explicit synthetic metric seeds tied to fixture trend families/styles, three official adapter MockTransport reads; four authenticated calls cover ranked read, queue, suggestion read and explicit subtitle save. Positive/negative history adjustments, new subtitle version, unchanged historical metrics/learning/cost and exact fresh-process restore pass. Rehearsal n1 found incorrect new application-state service binding; fixed to existing production_package_service. n2 reached export but found Windows Vietnamese console encoding; machine JSON uses Unicode escapes. Failed logs/databases retained; n3 passes.

EVIDENCE: `docs/PERSONALIZED_OPPORTUNITY_REVIEW.md`, `docs/north-star/personalized-review-evidence.json`; fresh `personalized-contract-n3` eight JSON exports plus owned database/objects. Fixture media is nonplayable; no full media QC or Owner acceptance implied.

REGRESSIONS: base scores/unrequested cache serialization/historical metrics/accepted media/live source and timeline/approval/provider/publishing defaults preserved. No live migration, paid/external operation, deployment or main merge. EXTERNAL BLOCKERS: real accounts/provider/Owner/browser and isolated production acceptance. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: Native/channel integration, authoritative publication-time evidence, remaining media/full Trend/Hub/production and final A/B/C. Continue original Waves 0–16.

### Wave 10/12 — Response-bound provider posting times

WAVE: 10/12. STATUS: IN PROGRESS. ANALYTICS_READY = NO; LEARNING_LOOP_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `8c585a4ed29b7387d0e49b95f2180a38d751a24b`, pushed/preserved in `north-star-personalized-review.bundle`, SHA256 `de5a041089ab105e9ae699b49d9ab7bb8f50829af06087aee6f2c2af08546ce2`; 167 ahead/0 behind, fresh 15 accepted hashes and clean live source. Timestamp increment will be separately committed/preserved.

CAPABILITIES COMPLETED: typed exact account/video/response/clock/transport evidence; TikTok create_time request and UTC provider-posted normalization; YouTube valid reported timestamp retention with explicit ambiguity and verified time null. Frozen features bind the same evidence and retain verified UTC offsets on SQLite reads. Learning checks identical feature/metric evidence and groups compatible UTC weekday/four-hour provider-posted history. Missing/invalid/future/rebound values stay null. Studio labels provider-posted/missing/mock evidence without optimal-window or first-public-exposure claims.

CAPABILITIES PARTIAL: Native/channel/operator/AnalyticsProfile integration, Meta, semantic features, unambiguous YouTube/public-exposure semantics, full original Trend/Hub/production and playable A/B/C. TikTok supported counters do not provide sufficient retention/completion for a winner or learning recommendation by themselves.

TESTS: **135 PASS**, 181.05s affected analytics/cohort/learning/API suites; later null-evidence guard **1 PASS**. **165 PASS** Studio, 779.88ms. Thirty-nine new API cases and one new Studio case; counts overlap prior increments. Pinned full parent Linux 8c585a4 is running; current timestamp pinned full suite pending.

REAL PROVIDER TESTS: 0. MOCK TESTS: four actual read-adapter MockTransport requests across two snapshots, two authenticated review/learning calls, exact fresh-process restore of snapshots/assessments/features/learning/costs. Missing refresh stays null, earlier history remains unchanged and insufficient retention prevents winner/learning claims. Initial rehearsal/tests exposed SQLite UTC-offset loss in the feature read projection; fixed only for new verified times. A test also assumed +00:00 rather than equivalent JSON Z serialization; corrected to compare typed timestamps. Failed evidence retained.

EVIDENCE: `docs/ANALYTICS_PUBLICATION_TIME.md`, `docs/north-star/publication-time-evidence.json`; `publication-time-contract-n2` six JSON exports plus owned database/objects. Official semantics sources are linked in the document. Fixture bytes/approvals/receipts do not certify real rights, playable media QC or Owner UAT.

REGRESSIONS: older analytics and learning snapshots, fixture serialization, canonical timeline/approval/provider/publishing defaults and accepted/live source preserved. No live migration, paid/external call, deployment or main merge. EXTERNAL BLOCKERS: actual accounts/provider/Owner/browser and isolated production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: Native distribution/channel integration and remaining original Waves 0–16.

### Wave 9 / Native Mode B — Bound publication review and dry runs

WAVE: 9 / 3 / 16. STATUS: IN PROGRESS. PUBLISHING_READY = NO; AUTO_EDIT_MODE_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `0cda6793f80725b1d7a32e0037dcc2578430292b`, pushed/preserved in `north-star-publication-time.bundle`, SHA256 `80beea11ba7ff6ae200eb5df9b11b910891a9216a3586215e6c58bc6d81cc49b`; 168 ahead/0 behind, fresh 15 accepted media hashes and clean live source verified. Native increment will be separately committed/preserved.

CAPABILITIES COMPLETED: Native same-origin/session/CSRF/RBAC publication routes and Video review controls; exact frozen render/final-review/file/capability/rights/platform binding; additive immutable requests, content-free events, Owner-only dry-run approval, UTC schedule/cancel, concurrent/repeated idempotency, keyset history and four-platform pure mock provider receipts. Late UI responses are scoped and rendered as text. Live transport remains unconfigured/default-disabled.

CAPABILITIES PARTIAL: Native live adapters/operator/credentials/profiles, generated voice/thumbnail rights, repeated intentional identical request UX, Native analytics/channel/winner/learning, durable TikTok/Meta runtime, official real/provider/policy and browser/Owner acceptance. Full original Waves 0–16 remain applicable.

TESTS: final focused **26 PASS**, 26.638s; full Native **413 PASS**; Studio **171 PASS**, 847.2475ms. Thirteen new Native and six Studio cases, overlapping counts. Initial full Native 411 tests had one failure from an exact capability assertion omitting the new two flags; corrected without removing prior checks. Initial media contract used the wrong fixture account workspace; corrected. Failed logs/folders remain. Prior pinned Linux `8c585a4`: **2620 PASS / 11 SKIP**, 1511.09s; pinned `0cda679` regression remains running.

REAL PROVIDER TESTS: 0. MOCK TESTS: four pure shared publishing receipts, explicit fixture final/publish human reviews and saved ASR. LOCAL-REAL TESTS: fresh synthetic testsrc2/tone source, portrait effects preview/final render and actual FullQC; **23 authenticated Native requests**, two history pages and exact fresh-process restore. Final/source bytes and canonical state after fixture review remain unchanged. No fabricated real platform posts or analytics.

EVIDENCE: `docs/NATIVE_PUBLICATION_REVIEW.md`, `docs/north-star/native-publication-evidence.json`; fresh `native-publication-render-n1` media bundle and `native-publication-contract-n2` six JSON exports. Source/preview/final/QC/transcript/scene/highlights/silence/captions/audio/timeline/provenance/cost/events are retained. This remains a synthetic partial Artifact A rehearsal, not non-developer UI or real-provider/Owner acceptance.

REGRESSIONS: accepted Phase 8–10 artifacts, live source, canonical timeline and existing capabilities/approval/provider defaults preserved. EXTERNAL BLOCKERS: actual credentials/provider/policy/Owner/browser and isolated production acceptance. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: Native analytics/channel integration and remaining original Trend/media/Hub/hardening/final A/B/C capabilities. No main merge, deployment, live migration, paid provider or external publication occurred.

### Wave 10/11/12 / Native Mode B — Analytics history and recovery

WAVE: 10/11/12 / 8 / 16. STATUS: IN PROGRESS. ANALYTICS_READY = NO; WINNER_DETECTION_READY = NO; LEARNING_LOOP_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `e442371ecf1ce46a6477de8da8331a3eab3f87c5`, pushed/preserved in `north-star-native-publications.bundle`, SHA256 `7ad9fda2659f44a4c859d08ef97f3d3e26a3f412491e7ba6bed42e1d5a082cf1`; 169 ahead/0 behind, fresh 15 accepted hashes and clean live source. Analytics/recovery increment will be separately committed/preserved.

CAPABILITIES COMPLETED: Native authenticated Owner fixture sync, shared pure analytics contracts/provider/scoring, immutable metric/feature/assessment/insight history, frozen render context, due dates/backoff/cancel/concurrent replay, per-video/time-series/recorded-workspace review and explicit official unavailability. Missing metrics, provider-posted times and costs stay null. Source subtitle selections now retain versioned references. Completion failure rolls back observations. Checksum-anchored backup/fresh restore preserves all new histories/media and repairs guarded Windows staging long paths; pending queues refuse offline snapshot.

CAPABILITIES PARTIAL: Native live/read-account/operator/AnalyticsProfile integration, recurring refresh plans, actual channel cohorts and learning feedback, semantic features, selection pagination/graphical comparison, Meta, original Trend/media/Hub/hardening and final playable A/B/C. Native fixture assessments explicitly lack channel-baseline acceptance. Restore has not rebound absolute render paths or rendered after recovery.

TESTS: final full Native **428 PASS**, 241.317s; affected Native/HTTP/source settings/Phase 10 **31 PASS**, 30.538s; later overlapping backup/analytics checks **29 PASS**, 12.088s. API shared provider/history/timestamp **45 PASS**, 36.10s; Studio **178 PASS**, 804.843ms. Fifteen new Native and seven Studio cases, overlapping counts. Initial import ordering, wrong Node directory invocation and absent pytest basetemp parent were corrected; failed logs retained. Pinned Linux `0cda679`: **2659 PASS / 11 SKIP**, 1825.49s. Current API provider source awaits pinned full regression.

REAL PROVIDER TESTS: 0. MOCK TESTS: five explicit analytics collections across four prior mock publications, saved ASR/mock human approvals, no actual audience/account/provider call. LOCAL-REAL TESTS: **26 authenticated Native requests**, exact process restore, checksum-anchored offline backup/fresh database/config/media restore; previously generated playable synthetic source retained with unchanged FullQC media hashes.

EVIDENCE: `docs/NATIVE_ANALYTICS_REVIEW.md`, `docs/north-star/native-analytics-evidence.json`; fresh `native-analytics-contract-n2` nine JSON exports and `native-analytics-restore-n3` four JSON exports plus backup archive. Failed n1 analytics export/backslash error and n1 long staging restore remain intact. Fresh owned fixture copy preserves original failed state and resets only cloned fixture analytics rows. No live data/accepted artifact was touched.

REGRESSIONS: earlier metrics/publications/project history, canonical timeline/approval/default provider/publishing and accepted/live source preserved. EXTERNAL BLOCKERS: authorized actual accounts/provider/policy/Owner/browser and isolated production acceptance. OWNER ACTION REQUIRED: none for remaining safe work. NEXT WAVE: Native real adapter/operator integration, channel learning/personalization, media/Trend/Hub/hardening and full original A/B/C acceptance. No protected-main merge, live migration, real external publication, paid provider or deployment occurred.

### Wave 4 / Native Mode B — Structured Vision evidence and review

WAVE: 4 / 3 / 8 / 16. STATUS: IN PROGRESS. MEDIA_INTELLIGENCE_READY = NO; AUTO_EDIT_MODE_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `e59a7d57ec7929d3b9cc44657d5255aa48870a02`, pushed/preserved in `north-star-native-analytics.bundle`, SHA256 `cf06000fcdeffe2855eb660d41f2c273906909b040fe2d5018404ac4040f3893`; 170 ahead/0 behind, fresh 15 accepted hashes and clean live source. Vision increment will be separately committed/preserved.

CAPABILITIES COMPLETED: additive scoped Native Vision queue/history/audit persistence; immutable source/CPU observation/frame/transcript/scene binding; generic shared structured fixture contracts; Assets evidence review with actual frame URLs, literal text and explicit sample labels; Owner-only acknowledged fixture admission, CSRF/auth-before-body, idempotency/concurrency/cancel/revision/integrity/atomic completion guards; deterministic attention-bound four-ratio center fallbacks with no tracking or timeline application. Pending Vision work refuses offline backup; exact new histories and actual frame files restore to a fresh root.

CAPABILITIES PARTIAL: configured official Native semantic dispatch/credentials/cost/budget, genuine inference/tracking/calibrated confidence, B-roll relevance and automatic media/scene/crop/thumbnail/QC consumers, actual browser/Owner and full original A/B/C acceptance. Official mode remains NOT_CONFIGURED with no mock fallback. Fixed fixture detections/OCR are not real model results.

TESTS: full Native **442 PASS**, 259.429s; final affected Native/HTTP/backup **30 PASS**, 11.348s; Studio **182 PASS**, 783.1961ms, plus parse checks. Fourteen new Native and four Studio cases; counts overlap earlier suites. Unchanged API parent `e59a7d5` pinned Linux **2659 PASS / 11 SKIP**, 1512.89s. Earlier new tests exposed an absent Native MIME field and empty-result integrity bypass; fixed to check actual magic bytes and non-null results. Backup fixture initially placed absent-secret paths under an ancestor of source; corrected to a separate private sibling. Initial evidence script imported a nonexistent helper; corrected to the existing analysis view. Failed logs remain.

REAL PROVIDER TESTS: 0. MOCK TESTS: structured generic semantic/person/face/OCR/composition/quality fixture predictions bound to actual local samples; saved ASR fixture, no real semantic inference or subject tracking. LOCAL-REAL TESTS: fresh six-second synthetic video/audio ingestion and CPU scene/frame measurement, **nine authenticated Native requests**, eight real PNG frames, one fixture semantic scene, replay/cancel/history/unconfigured path and exact fresh-process/checksum-anchored fresh-root restoration. Source/project/CPU evidence stays unchanged.

EVIDENCE: `docs/NATIVE_VISION_REVIEW.md`, `docs/north-star/native-vision-evidence.json`; `native-vision-contract-n3` ten JSON exports plus private backup archive. Earlier import failure/n2 rehearsal remain preserved. Costs are unknown/null; no provider, secret or paid operation occurs. DOM is not browser/viewport/Owner acceptance.

REGRESSIONS: canonical project/timeline, separate real CPU facts, existing provider/approval/publishing defaults, accepted videos and live checkout preserved. EXTERNAL BLOCKERS: actual approved semantic/provider configuration and browser/Owner/isolated production acceptance. OWNER ACTION REQUIRED: none for continuing safe implementation. NEXT WAVE: remaining Native media/provider integration, cached multi-platform variants, independent channel/learning/full Trend/Hub/hardening and original final A/B/C. No main merge, live migration, real publishing, paid provider or deployment occurred.

### Wave 7 / Native Mode B — Linked six-format source variants

WAVE: 7 / 3 / 8 / 16. STATUS: IN PROGRESS. MULTI_NICHE_READY = NO; AUTO_EDIT_MODE_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `bff53659a22acd8c477d7214b34fd9bd139015b1`, pushed/preserved in `north-star-native-vision.bundle`, SHA256 `0fec8b6ee39b0e3454d2b0dbd3da887c914dd79cb6a394c64132a99ccbf54943`; 171 ahead/0 behind, fresh 15 accepted hashes and clean live source. Variant increment will be separately committed/preserved.

CAPABILITIES COMPLETED: versioned six-format configuration catalog; atomic Native source master-to-draft families; frozen workspace/master/request/catalog/initial-child-version bindings; existing identity/evidence reuse with no inherited approvals/jobs; measured center-attention visual plans, locked-track protection, B-roll geometry and generic-copy membership separation. Scoped editor creation and read-only no-store history/catalog, CAS/replay/concurrency/rollback/corruption/cursor/history checks and explicit Studio controls preserve canonical timeline and human-review gates. Private backup counts family records and restores exact initial histories plus six final files.

CAPABILITIES PARTIAL: narrated Mode A variants, ChannelProfile/BrandKit/voice/CTA/template UI, expensive generated/audio/render intermediate caching, channel publishing/analytics linkage, actual ASR/Vision/tracking and browser/non-developer/Owner/final A/B/C acceptance. A saved technology fixture configuration is not Native channel-profile UI acceptance. Identical actual PCM is measured; intermediate processing is still repeated.

TESTS: full Native **452 PASS**, 291.242s; focused final Native/HTTP/Phase 10/backup **39 PASS**, 67.107s; independent duplicate/reframe/variant checks **18 PASS**, 11.146s. Studio **185 PASS**, 945.4482ms plus parse checks. Ten new Native and three Studio cases; counts overlap. API source is unchanged from pinned `e59a7d5` **2659 PASS / 11 SKIP**, 1512.89s. Earlier six-case and 21-case runs remain retained. Final rehearsal explicitly compares actual Native render manifests to each canonical child; prior n1 used an absent optional manifest field and is retained separately.

REAL PROVIDER TESTS: 0. MOCK TESTS: saved ASR and pre-render test approvals are fixtures, not Owner UAT; subject tracking is unavailable. LOCAL-REAL TESTS: final n2 generates synthetic footage/tone, measures local scene/audio/eight-frame evidence, creates six linked drafts and makes **16 authenticated requests**. Six effects previews/finals pass exact geometry/canonical manifest and FullQC; all six PCM hashes match. Master/document/history/source hashes stay unchanged. Exact process and checksum-anchored fresh-root backup restore preserve families, children, jobs, events, configuration and final bytes.

EVIDENCE: `docs/NATIVE_SOURCE_VARIANTS.md`, `docs/north-star/native-variants-evidence.json`; final `native-variants-contract-n2` six format media bundles, root JSON exports and private archive, with n1 preserved. Independent Source timelines remain the canonical edit truth for their own drafts; master lineage is frozen, not a second editable representation.

REGRESSIONS: existing source/asset/transcript/scene/frame/audio/caption decisions, master timeline/approval, phase defaults, accepted videos and live checkout preserved. EXTERNAL BLOCKERS: actual provider/browser/Owner and isolated production acceptance. OWNER ACTION REQUIRED: none for continuing safe implementation. NEXT WAVE: scoped intermediate cache reuse, remaining Native media/providers/Mode A/channel/learning/full Trend/Hub/hardening and final original A/B/C. No main merge, live migration, paid provider, real external publishing or deployment occurred.

### Wave 7/8 / Native Mode B — Verified PCM intermediate reuse

WAVE: 7 / 8 / 3 / 16. STATUS: IN PROGRESS. MULTI_NICHE_READY = NO; AUTO_EDIT_MODE_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `ac3806ab504175472c66eb11e85d1695d0621707`, pushed/preserved in `north-star-native-variants.bundle`, SHA256 `8fb0e22f0d761e18241cbb24a10ad76ac610b8d87e74c59b21297563f81607a7`; 172 ahead/0 behind, fresh 15 accepted hashes and clean live source. Cache increment will be separately committed/preserved.

CAPABILITIES COMPLETED: canonical-source PCM reuse for effects previews/final preparation; actual source/tool/filter/duration fingerprint; persisted workspace/root/project scope and immutable registered-family/history admission. Process/thread leases, atomic receipt/PCM commit, format/frame/byte/hash measurement, verified private job copies, current source revalidation and corruption/link/cancellation/failure guards preserve canonical timelines and review/QC gates. Bounded committed retention bypasses privately without eviction. Separate-process reuse and fresh-root recovery/recomputation pass.

CAPABILITIES PARTIAL: all remaining research/trend/transcript/Vision/stock/generated/preview/render general cache coverage and quotas/TTL, narrated Mode A variants, unified profiles/channel/media/learning/Trend/Hub/hardening, actual provider/browser/Owner and complete original A/B/C acceptance. Failed private attempts are retained outside the committed-PCM bound; total temporary-storage quota remains hardening work.

TESTS: affected Native/effects-preview/render/variant/backup **41 PASS**, 54.025s. Studio **185 PASS**, 945.5619ms. Ten new Native cases; counts overlap. Full Native **462 PASS**, 288.105s. API source remains unchanged from pinned `e59a7d5` **2659 PASS / 11 SKIP**, 1512.89s. Initial tests caught Windows read-only descriptor flushing and incorrect fixture view/clip-identity/hash assumptions; corrected without relaxing source/canonical validation. Failed logs remain.

REAL PROVIDER TESTS: 0. MOCK TESTS: saved ASR and approval fixtures; generated PCM process-lock fixture. LOCAL-REAL TESTS: new six-format synthetic footage/tone effects previews and independently approved fixture final renders; actual FullQC; **16 authenticated Native requests**. One PCM build and eleven preview/final hits; exact timeline manifests/source/master histories remain unchanged. A fresh process hits the same entry; checksum-anchored backup restores exact family/projects/jobs/source/finals/cache, then a new process recomputes identical PCM under the restored root's distinct scope.

EVIDENCE: `docs/NATIVE_SOURCE_AUDIO_CACHE.md`, `docs/north-star/native-audio-cache-evidence.json`; `native-audio-cache-contract-n1` six media bundles, JSON exports and private archive. Earlier uncached variant n1/n2 and all accepted artifacts remain unchanged. New rendering after restore and browser acceptance are not tested; PCM preparation after restore is verified.

REGRESSIONS: existing phase/provider/approval/publishing defaults and canonical source/audio/caption/variant decisions preserved. EXTERNAL BLOCKERS: configured real providers, Owner/browser and isolated production acceptance. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: remaining unified Native channel/profile/media/provider integration, Mode A, learning/full Trend/Agent Hub/hardening and original final A/B/C. No main merge, live migration, paid provider, external publication or deployment occurred.

### Wave 8/15 / Native Source — Operational render after recovery

WAVE: 8 / 15 / 3 / 16. STATUS: IN PROGRESS. PRODUCTION_HARDENING_READY = NO; AUTO_EDIT_MODE_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `b9698a3c2186029376f656a18af99f39c3e9e683`, pushed/preserved in `north-star-native-audio-cache.bundle`, SHA256 `c3dc3448f90d2835bbef336370e997a8fa2a28095b7d6e8996848d4c0c36fb06`; 173 ahead/0 behind, fresh 15 accepted hashes and clean live source. Recovery acceptance increment will be separately committed/preserved.

CAPABILITIES COMPLETED: reproducible operational Source-mode recovery contract; independently verified restore/snapshot/second restore; retained owned seed with unavailable original path; exact old media/history/master/family/other-variant preservation. New canonical edit clears approval, unapproved render blocks, fresh effects preview and explicit fixture approval bind a new final render with actual FullQC. New source/audio/staging paths belong to the restored root, and a separate process recovers exact post-render state.

CAPABILITIES PARTIAL: PostgreSQL/Redis/S3/credential and isolated production recovery, genuine source/ASR/semantic/browser/Owner acceptance, remaining original Mode A/B/media/channel/learning/Trend/Hub/hardening and A/B/C bundles. Historical absolute result paths remain original evidence and are not falsely rewritten as new execution locations.

TESTS: new final n2 operational contract PASS; new actual portrait preview/final/FullQC and **six authenticated requests**. Existing Native core is unchanged from **462 PASS**, 288.105s; Studio is unchanged from **185 PASS**, 945.5619ms; API remains pinned **2659 PASS / 11 SKIP**, 1512.89s. Broad suites are not repeated for an evidence-script/documentation-only increment. First n1 expected HTTP 400 instead of the established 409 approval gate; script corrected and failed fixture/log retained.

REAL PROVIDER TESTS: 0. MOCK TESTS: saved ASR and automated human-review fixture; no Owner UAT. LOCAL-REAL TESTS: checksum-anchored owned offline backup/restore, source/caption timeline edit, new preview and actual 1080×1920 final/FullQC. Preview builds PCM under restored scope and final hits it. Previous files, frozen project versions/family/master and other variants retain exact hashes/state; fresh-process post-render state matches.

EVIDENCE: `docs/NATIVE_BACKUP_RESTORE.md`, `docs/north-star/native-recovery-render-evidence.json`; `native-recovery-render-contract-n2` preview/final/timeline/audio/subtitle/QC/probe/cost/checkpoint, requests/commands/state/restore exports and private seed archive. Retained owned seed: `C:\vf-native-fixture-source-recovery-seed-02-offline`; operational fixture: `C:\vf-native-fixture-source-recovery-02`.

REGRESSIONS: original six-format media/archive, all accepted artifacts, live source, existing source/provider/approval/publish gates remain unchanged. EXTERNAL BLOCKERS: real provider/browser/Owner and isolated production acceptance. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: remaining full Native channel/profile/media/provider integration, Mode A variants, learning/full Trend/Hub/hardening and original final A/B/C. No main merge, live migration, paid provider, external publication or deployment occurred.

### Wave 7 / Native — Frozen channel/niche configuration and creation controls

WAVE: 7 / 3 / 8 / 16. STATUS: IN PROGRESS. MULTI_NICHE_READY = NO; AUTO_EDIT_MODE_READY = NO; IMPLEMENTATION_COMPLETE = NO.

HEAD SHA: parent `77c63255ad8a56ee479c1d9d01f395fe96757a65`, pushed/preserved in `north-star-native-recovery-render.bundle`, SHA256 `5fbd44c5976aa6e9fe472cb4c077b25b3a9e9a19b7fa9da9a6ce257ccb762619`; 174 ahead/0 behind, fresh 15 accepted hashes and clean live source. Profile increment will be separately committed/preserved.

CAPABILITIES COMPLETED: versioned typed Native channel/niche/Source/publishing/analytics preference definitions referencing existing content/brand/video/subtitle configuration; atomic frozen project selection/defaults/niche and strict read integrity; Source canonical binding/defaults and niche/brand render metadata. Two reference niches and a third configuration-only unit case use the generic core. Capability-gated literal-text creation selector, explicit default application, current project summaries, read-only/busy/stale guards and no dispatch on selection preserve human/cost/provider boundaries.

CAPABILITIES PARTIAL: full profile administration and channel/Trend/learning/MediaPlan/publishing/analytics runtime consumers, real account/provider configuration, additional voices/languages, visible Source brand overlays, narrated Mode A variants and browser/non-developer/Owner/production/final original A/B/C acceptance. Disabled preference definitions are not configured accounts. The same synthetic Source/caption preferences yield identical video hashes, with different saved niche/brand metadata only.

TESTS: final affected Native/profile/HTTP/variant/PCM/Phase 10 **40 PASS**, 42.230s before the final added project-read validator; full Native **471 PASS**, 293.508s includes that validator. Studio **188 PASS**, 843.076ms; three focused DOM cases and parsing pass. Nine new Native and three Studio cases; counts overlap. API is unchanged from pinned **2659 PASS / 11 SKIP**, 1512.89s. Initial tests incorrectly assumed the prepared ASR fixture had no completed analysis job and used an absent metadata field rather than the actual brand contract; corrected. Failed logs remain.

REAL PROVIDER TESTS: 0. MOCK TESTS: saved ASR and automated approval fixtures; reference catalog configuration, no account/performance claim. LOCAL-REAL TESTS: final n1 **19 authenticated requests**, two HTTP-selected profiles and actual uploaded synthetic footage, local scene/audio/eight-frame measurement, two effects previews/finals with FullQC, exact saved profile/niche/brand metadata and canonical manifests, PCM reuse, unchanged source bytes and separate-process/fresh-root offline restore. No manual niche seed or core niche mapping is used.

EVIDENCE: `docs/NATIVE_CHANNEL_PROFILES.md`, `docs/north-star/native-channel-profiles-evidence.json`; `native-channel-profiles-contract-n1` two media/project bundles, catalog/request/state/backup/restore exports and private archive. No browser or narrated Mode A render acceptance is claimed.

REGRESSIONS: existing profiles/default voice, legacy/no-profile projects, canonical Source and independent review/rights/publishing gates preserved. Accepted videos and live source remain untouched. EXTERNAL BLOCKERS: configured providers/accounts, real source/browser/Owner and isolated production acceptance. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: remaining Native Mode A/profile/media/provider consumers, full Trend/learning/Hub/hardening and original A/B/C. No main merge, live migration, paid provider, external publication or deployment occurred.

### Wave 14 / Native — Versioned service boundary and independent signed outbox

WAVE: 14 / 8 / 16. STATUS: IN PROGRESS. AGENT_HUB_BRIDGE_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `2404b3edef8134a9c30ed6cea5e7f0d68a846592`, preserved/pushed in `north-star-native-channel-profiles.bundle`, SHA256 `153e0dcf5e86022a881dc57c1e905ad33403427be3e5c40314f5292e4ffcc6c2`; 175 ahead/0 behind. Bridge increment will be separately committed/preserved with a fresh receipt and accepted artifact verification.

CAPABILITIES COMPLETED: Native /v1 HMAC boundary independent of human cookies, scoped durable nonce replay and bounded body/header/query guards. Atomic unapproved draft/history/event/idempotency creation for prompt/script/media, frozen receipt replay, content-free scoped project/event/delivery DTOs. Native transaction outbox, separate intelligence source envelope/cursor transfer, lifecycle producer links, strict provenance flags, independent default-disabled webhook worker, exact signing/key rotation, pinned destination, claims/fenced completion, five-attempt backoff and durable audit. External registries stay outside state; protected HTTP enablement is explicit and unused. Offline backup refuses pending delivery and restores outbox/source metadata exactly.

CAPABILITIES PARTIAL: full Native resource API/operator controls/retention, real receiver/network/secrets, cross-runtime/deployed/offline soak, official Native publishing/analytics and full Trend/personalized learning/Mode A/B/media/provider/channel/hardening/original A/B/C. Fixture research is not global-platform trend data; mock publication/analytics/winner records are not real posts/audience. Runtime rights editor and Owner/browser UAT remain open.

TESTS: Native full **492 PASS**, 301.843s; affected r2 42 PASS/15.231s and r3 50 PASS/25.383s, overlapping subsets. New Native cases 21. HTTPS wire is mock-tested. Studio source is unchanged from 188 PASS/843.076ms and API source from 2659 PASS/11 SKIP/1512.89s; these broad suites were not repeated without product changes. Failed fixture assertions and first two playable rehearsal roots/logs are retained.

REAL PROVIDER TESTS: 0. MOCK TESTS: service keys, signed in-process receiver, saved ASR, research/ideas, dry-run publication and fixture winner analytics. LOCAL-REAL TESTS: actual CPU source scene/audio/frame analysis, portrait effects preview, canonical human approval gate, actual 1080×1920 final/FullQC, persistent HMAC nonce/idempotency and DB restart/recovery. Fifteen events cover eleven event types, with sixteen signed attempts and one 429 retry; thirty-three authenticated HTTP requests. Actual Hub/provider calls = 0; no paid operation, real secret, external publication or production action.

EVIDENCE: `docs/NATIVE_AGENT_HUB_BRIDGE.md`, `docs/north-star/native-bridge-evidence.json`; `native-bridge-contract-n3` contains 20 media/project/research/publication/analytics/event/wire/HTTP/recovery/archive files. Source fixture `C:\vf-native-fixture-bridge-03`, fresh restore `C:\vf-native-fixture-bridge-restore-03`. Actual synthetic source provenance is explicitly seeded before frozen render; uploaded unknown rights correctly blocked the n2 attempt. Final SHA256 `5cae013b924493561de30578d3525af7a500f1ca56a1e9c7f7f528683796c398`; preview `1b19c136467326a7ec77c5f532dd758c1c8702efa025e1a09c277f2af44091c7`. No accepted artifact was replaced.

REGRESSIONS: full Native passes; existing separate-media, canonical approval, unknown-rights and default-off publishing guards remain. EXTERNAL BLOCKERS: real Hub/provider/Owner/browser/production acceptance; no blocker stops remaining safe implementation. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: remaining Native media/rights/provider/learning/full Trend/operator integration, narrated Mode A variants, hardening and complete original A/B/C. No main merge or production deployment.

### Wave 14 / Native — Human operator review and persistent workspace binding

WAVE: 14 / 8 / 16. STATUS: IN PROGRESS. AGENT_HUB_BRIDGE_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `20264b96863deccd625644f775272c6d266a8557`, pushed/preserved in `north-star-native-agent-hub-bridge.bundle`, SHA256 `c803ea796fd0a08be68a89ae00b5726462a30c6fb1046cf5bd193553bffde18a`; 176 ahead/0 behind, fresh 15 accepted hashes and clean live source. Operator increment will be separately committed/preserved.

CAPABILITIES COMPLETED: persistent workspace binding before any event/auth request and conflict protection for legacy nonce-only state. Separate human read/Owner selection/cancellation routes, existing session/origin/CSRF/RBAC before mutation body, exact event/destination/mode/provenance acknowledgment and frozen actor/idempotency receipts. Queued/retrying delivery can be cancelled after disabling configuration, without network or key loading; running/completed cannot be falsely cancelled. Capability-gated explicit literal-text operator panel with stable lost-reply keys, stale workspace guards, review and attempt history. No browser enablement/key or service selection authority. Backup includes bindings/receipts and persists default-disabled cancellation/recovery.

CAPABILITIES PARTIAL: real browser/1366/1920/2560/non-developer/Owner acceptance, real receiver/network/secrets, retention/cross-runtime/deployed/offline soak and all remaining original Native media/rights/provider/channel/Trend/learning/Mode A/B/hardening/final A/B/C.

TESTS: Native full **497 PASS**, 295.079s; affected 55 PASS/26.854s and prior binding subset 48 PASS/16.676s, overlapping. Studio full **192 PASS**, 863.1459ms, plus four focused DOM cases. New Native cases 5. Unchanged API retains 2659 PASS/11 SKIP/1512.89s without unnecessary broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: human Owner/viewer identities, explicit fixture signer/receiver and DOM. LOCAL-REAL TESTS: actual scoped HTTP/database selection/cancellation/idempotency, new-process and offline checksum-anchored recovery in a fresh clone of the prior playable source/QC bundle. Thirteen authenticated requests, one cancelled event, one signed fixture delivery. Existing final/preview/old project histories/media remain unchanged; media was not rendered again. Actual Hub/provider/paid/real-secret/publication/deployment actions = 0.

EVIDENCE: `docs/NATIVE_AGENT_HUB_BRIDGE.md`, `docs/north-star/native-bridge-operator-evidence.json`; `native-bridge-operator-contract-n1` has 12 operator/event/HTTP/wire/recovery/archive files. Owned source `C:\vf-native-fixture-bridge-operator-01`, fresh restore `C:\vf-native-fixture-bridge-operator-restore-01`. Parent final `5cae013b924493561de30578d3525af7a500f1ca56a1e9c7f7f528683796c398`, preview `1b19c136467326a7ec77c5f532dd758c1c8702efa025e1a09c277f2af44091c7` unchanged.

REGRESSIONS: full Native/Studio pass and existing default-off publishing, separate source/canonical review/rights gates remain. EXTERNAL BLOCKERS: genuine Hub/provider/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: remaining original Native media/rights/provider/personalized Trend/learning, narrated Mode A variants, hardening and full A/B/C. No main merge, live migration, real external message/publication or production action.

### Wave 5B / Native — Media rights declarations and provenance defaults

WAVE: 5B / 3 / 8 / 16. STATUS: IN PROGRESS. MEDIA_INTELLIGENCE_READY = NO; GENERATIVE_MEDIA_READY = NO; PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `6656848291ee93966cdf9110ee9c6accf4dcbe1f`, pushed/preserved in `north-star-native-bridge-operator.bundle`, SHA256 `ebbfe6ec748661d8353a5b1e9103edb41ab383ecac8af7b3365bed38221d92da`; 177 ahead/0 behind, fresh 15 accepted hashes and clean live source. Rights increment will be separately committed/preserved.

CAPABILITIES COMPLETED: explicit new image/video/music and legacy image upload actual provenance with unknown rights. Typed Owner-only declaration/read routes, session/origin/CSRF/RBAC before body, revision/physical SHA, immutable version-bound receipt replay, malformed/rehashed/foreign/detached record guards, atomic document/history/approval/event/receipt changes. Human claims stay unverified and separate from actual provider/source/license metadata. Derived projects keep physical restrictions and discard foreign declaration scope. Capability-gated literal Assets form with explicit acknowledgment/read/save, stable keys and workspace/project/revision/dirty/busy/archived/active guards. Existing immutable render revision/publishing gates remain; no redundant weaker dispatch path. Backup preserves records/receipts and default-off state.

CAPABILITIES PARTIAL: provider-backed license evidence/stock/generation/internal-library provenance, explicit Owner legal override architecture/review, full music metadata/rights and real browser/non-developer/viewport/Owner. All original downstream Trend/learning/Mode A/B/hardening/A/B/C remain applicable.

TESTS: Native full **508 PASS**, 309.569s; affected **57 PASS**, 31.928s; new Native cases 11. Studio full **196 PASS**, 909.1149ms; four focused DOM cases. Counts overlap. Unchanged API retains 2659 PASS/11 SKIP/1512.89s; not rerun. Failed affected r3 is retained: wrong module filename and an expectation contrary to the existing stale-render guard; corrected fixture/command without relaxing product behavior.

REAL PROVIDER TESTS: 0. MOCK TESTS: Owner/editor/viewer identities, synthetic known-owned provenance, nonplayable unit render fixture and DOM. LOCAL-REAL TESTS: actual physical image ingestion, scoped HTTP/database/CAS/digest/event rollback, and checksum-anchored clone of the prior playable source/full-QC bundle. Fifteen authenticated requests, two unverified declarations, identical frozen retry after newer restriction, blocked previously approved publishing intent, unchanged old jobs/versions/other projects/media. New-process and fresh-root offline restore match exactly. No media rerender, real credential, external provider/Hub/publication, paid action, Owner UAT or production.

EVIDENCE: `docs/NATIVE_MEDIA_RIGHTS.md`, `docs/north-star/native-rights-evidence.json`; `native-rights-contract-n1` contains 11 rights/HTTP/blocked-publication/event/recovery/archive files. Owned root `C:\vf-native-fixture-rights-01`, restore `C:\vf-native-fixture-rights-restore-01`. Parent final `5cae013b924493561de30578d3525af7a500f1ca56a1e9c7f7f528683796c398`, preview `1b19c136467326a7ec77c5f532dd758c1c8702efa025e1a09c277f2af44091c7` remain unchanged.

REGRESSIONS: Native/Studio full pass; original human review/canonical timeline/rights/render/source gates preserved. EXTERNAL BLOCKERS: actual legal/provider/credential/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: approved stock/provider/media planning and remaining original full media/Trend/learning/Mode A/B/hardening/A/B/C. No main merge, live migration, legal override, external publication or production action.

### Wave 5A / Native — Official stock adapter intake and explicit attachment

WAVE: 5A / 5B / 3 / 8 / 16. STATUS: IN PROGRESS. MEDIA_INTELLIGENCE_READY = NO; GENERATIVE_MEDIA_READY = NO; PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `97c2e05e0c2b3b4041c937f18c28d44bc240610e`, pushed/preserved in `north-star-native-media-rights.bundle`, SHA256 `be2688417b92516aed834a629e7a90b6e46cd39e8b2070b4f2ea24e0f5fb854d`; 178 ahead/0 behind, fresh 15 accepted hashes and clean live source. Stock increment will be separately committed/preserved.

CAPABILITIES COMPLETED: reuse of existing official Pexels/Pixabay neutral adapters, protected strict external registry and independent enablement, default NOT_CONFIGURED without mock fallback. Owner-only hash-bound search/download/cancel, scoped immutable snapshots/history, queued lease/claim/retry/cost dispatch independent of renderer. MIME/magic/full decode/FFprobe/original bytes, local authenticated review and actual/provider dimension distinction. Explicit Editor/Owner atomic attachment/approval invalidation/frozen receipts; no automatic placement. Actual stock provenance and fixture unknown rights persist through B-roll projection. Scoped API cache, bounded local UI progress and literal context/permission/acknowledgment guards. Backup refuses pending work and preserves terminal evidence.

CAPABILITIES PARTIAL: real provider credentials/policy/rights acceptance, explicit Owner legal review/override, global quota/retention/health and real browser/viewport/non-developer/Owner. Remaining original generation/MediaPlan/Mode A/B/full Trend/learning/channel provider/hardening/A/B/C work remains applicable.

TESTS: Native full **521 PASS**, 327.169s; latest affected **32 PASS**, 15.160s, earlier stock/HTTP/media/backup 51 PASS/31.649s, official API wire 24 PASS/14.51s. New Native cases 13. Studio full **201 PASS**, 948.2869ms, five focused DOM cases. Counts overlap. Unchanged API retains 2659 PASS/11 SKIP/1512.89s; broad suite not rerun. Failed initial fixture assertions retained and corrected without changing product gates.

REAL PROVIDER TESTS: 0. MOCK TESTS: official API/CDN wire, fixture keys in memory, Owner/Editor/Viewer identities and DOM. LOCAL-REAL TESTS: independent worker, actual image/full video decoding, original and normalized hash checks, HTTP/scoped database/atomic receipt/replay and checksum-anchored prior playable bundle recovery. Two searches, two downloads, six mock wire attempts, 28 authenticated requests, two explicit attachments, four new cost operations with actual cost unknown. Existing source/final/preview/old jobs and histories remain unchanged. Fresh process and offline restore match exactly. No rerender, real credentials, paid operation, external provider/Hub/post, browser/Owner UAT or production.

EVIDENCE: `docs/NATIVE_STOCK_MEDIA.md`, `docs/north-star/native-stock-evidence.json`; `native-stock-contract-n1` contains 13 contract/media/provenance/cost/event/HTTP/restore/archive files. Owned root `C:\vf-native-fixture-stock-01`, restore `C:\vf-native-fixture-stock-restore-01`. Parent final `5cae013b924493561de30578d3525af7a500f1ca56a1e9c7f7f528683796c398`, preview `1b19c136467326a7ec77c5f532dd758c1c8702efa025e1a09c277f2af44091c7` unchanged.

REGRESSIONS: all Native/Studio pass, original approval/source/rights/publishing gates preserved; no accepted artifact replaced. EXTERNAL BLOCKERS: real legal/provider/credentials/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for continuing safe work. NEXT WAVE: explicit legal review/override architecture, generative media and full Native MediaPlan/Mode A, remaining full Trend/learning/hardening and original A/B/C. No main merge, live migration, legal override, external publication or deployment.

### Wave 5B / Native — Explicit scoped Owner exception architecture

WAVE: 5B / 3 / 8 / 14 / 16. STATUS: IN PROGRESS. MEDIA_INTELLIGENCE_READY = NO; GENERATIVE_MEDIA_READY = NO; PUBLISHING_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `a691a555eaccfe5f4e5c96b477362285888ccdc5`, pushed/preserved in `north-star-native-stock.bundle`, SHA256 `bd2599a9558feae430cbea23ab190830d8b7c5ad6da11e9564a87936ab20287a`; 179 ahead/0 behind, fresh 15 accepted hashes and clean live source. Exception increment will be separately committed/preserved.

CAPABILITIES COMPLETED: default-disabled human-auth-required configuration, separate strict Owner grant/revoke/read routes, exact workspace/project/revision/physical/current-rights digests, explicit reason/reference/acknowledgment, 1–30-day expiry and optional publishing-review scope. Atomic approval invalidation/history/content-free bridge event/immutable receipts, frozen retries after later revoke/disable, no client enablement/verification/publish authorization. Restricted/provider fixture promotion blocked. Derived projects drop exception scope. Local B-roll and publication revalidation consume exact active exceptions without changing actual source/license/unknown rights; expiry blocks placement and even previously approved mock dispatch. Capability-gated literal Assets form with lost-reply and context/role/busy guards; terminal backup recovery stays default-disabled.

CAPABILITIES PARTIAL: actual asset-specific legal decisions, independent third-party/provider clearance, internal/generation/music and legacy/derived attestation reconciliation; real browser/viewport/non-developer/Owner. Original generation/MediaPlan/Mode A/B/full Trend/learning/channel provider/hardening/A/B/C remain.

TESTS: Native full **533 PASS**, 331.869s; affected **58 PASS**, 34.884s; earlier 32 PASS/8.287s, HTTP/backup/Phase10 35 PASS/26.134s, focused 40 PASS/15.884s. New Native cases 12. Studio full **206 PASS**, 1000.2963ms, five focused DOM cases. Counts overlap. Unchanged API retains 2659 PASS/11 SKIP/1512.89s without broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: human identities, synthetic Owner decisions, saved ASR and nonplayable unit publication fixture. LOCAL-REAL TESTS: actual local image/source/B-roll and authenticated database/CAS/rollback/expiry, plus checksum-anchored prior playable clone. Thirteen HTTP requests, one deliberately unverified synthetic declaration, one scoped exception, disable/revoke/frozen replay, unchanged old jobs/versions/source/final/preview. New-process/offline restore exact/default-disabled. Original generated fixture bytes have known test ownership; no real uncertain asset was cleared. No rerender, real secret/provider/Hub/post/paid action, actual browser/Owner UAT or production.

EVIDENCE: `docs/NATIVE_OWNER_RIGHTS_OVERRIDES.md`, `docs/north-star/native-owner-rights-evidence.json`; `native-rights-override-contract-n1` contains 11 grant/revoke/declaration/review/HTTP/event/restore/archive files. Owned root `C:\vf-native-fixture-rights-override-01`, restore `C:\vf-native-fixture-rights-override-restore-01`. Parent final `5cae013b924493561de30578d3525af7a500f1ca56a1e9c7f7f528683796c398`, preview `1b19c136467326a7ec77c5f532dd758c1c8702efa025e1a09c277f2af44091c7` unchanged.

REGRESSIONS: all Native/Studio pass, original default-blocked unknown rights unless explicit active Owner exception; separate approval/source/QC/platform/publishing-off gates preserved. No accepted artifact replaced. EXTERNAL BLOCKERS: real legal/provider/credentials/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for continuing safe implementation; actual legal decisions remain explicit Owner actions. NEXT WAVE: original generation and full Native MediaPlan/Mode A, remaining Trend/personalized learning/Hardening/A/B/C and legacy attestation reconciliation. No main merge, live migration, real external publication or production deployment.

### Wave 5B / Native — Preserve reviewed rights across derivation

WAVE: 5B / 3 / 7 / 8 / 16. STATUS: IN PROGRESS. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `c7e89fe8408139387d746a601c532df3ea198b45`, pushed/preserved in `north-star-native-owner-rights.bundle`, SHA256 `41b70bbea4bece87f65e109a5084b962245c3fa0ee480b9bab5c265255bb1c38`; 180 ahead/0 behind, fresh 15 accepted hashes and clean live source. Derived guard increment will be separately committed/preserved.

CAPABILITIES COMPLETED: reviewed asset markers survive removing project-scoped claims/exceptions during duplicate/variant derivation. Actual unknown/restricted rights remain in B-roll projection; copied plan active exception records are cleared, with source ID/hash historical evidence explicitly lacking authority. New placement requires new child-scoped admission. Existing unmarked asset/grant fingerprints and original source/history stay unchanged.

CAPABILITIES PARTIAL: genuine legal/provider clearance, remaining legacy attestation semantics, real browser/Owner and original generation/MediaPlan/Mode A/B/full Trend/learning/channel providers/hardening/A/B/C.

TESTS: 82 affected PASS/44.828s, prior 35 PASS/12.901s; overlapping subsets. Two existing security consumer cases strengthened, no inflated new count. Failed pre-fix r0 is retained: both observed the old unknown-to-verified derived projection. Latest full Native at c7e89fe remains 533 PASS/331.869s; targeted rights/HTTP/publication/B-roll/duplicate/six-variant/backup/stock suites cover this narrow fix instead of unnecessary broad repetition. Unchanged Studio 206 PASS/1000.2963ms and API 2659 PASS/11 SKIP/1512.89s were not rerun.

REAL PROVIDER TESTS: 0. MOCK TESTS: synthetic identities/Owner decisions/saved ASR/nonplayable unit publish fixtures. LOCAL-REAL TESTS: actual local uploaded image/video/B-roll consumers and authenticated Source duplicate over checksum-cloned playable evidence. Fifteen HTTP operations; child unknown/review-required/unapproved with no inherited authority, immutable parent jobs/old versions/media. Separate process and fresh offline restore exact/default-disabled. No real uncertain asset clearance, rerender, secret/provider/Hub/post/paid action, actual browser/Owner UAT or production.

EVIDENCE: `docs/NATIVE_OWNER_RIGHTS_OVERRIDES.md`, `docs/north-star/native-derived-rights-evidence.json`; `native-rights-override-contract-n2` has 13 declaration/grant/revoke/derived project/review/HTTP/event/archive/recovery files. Owned source `C:\vf-native-fixture-rights-override-derived-01`, restore `C:\vf-native-fixture-rights-override-derived-restore-01`. Parent final `5cae013b924493561de30578d3525af7a500f1ca56a1e9c7f7f528683796c398`, preview `1b19c136467326a7ec77c5f532dd758c1c8702efa025e1a09c277f2af44091c7` unchanged.

REGRESSIONS: reproduced consumer gap fixed; affected suites pass, default-off publishing and independent source/QC/human gates preserved. EXTERNAL BLOCKERS: actual legal/provider/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation. NEXT WAVE: original Native generative integration and MediaPlan/Mode A, remaining full Trend/learning/hardening/A/B/C. No main merge, live migration, real external publishing or deployment.

### Wave 5C/D/E — Trusted generation lifecycle and targeted cancellation

WAVE: 5C / 5D / 5E / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `a68c25f7a8977048ab7e1e874804a84af98cf4c3`, pushed/preserved in `north-star-native-derived-rights.bundle`, SHA256 `209d5764ffd224cb3409d5578e50237b21fd7db5af8a766fdd20d8b60072d5a5`; 181 ahead/0 behind, fresh 15 accepted hashes and clean live source. Lifecycle increment will be separately committed/preserved.

CAPABILITIES COMPLETED: optional trusted server observer and strict boolean cancellation hooks in the existing neutral adapter. Bound content-free provider ticket/status/progress projections, null absent progress and callback isolation. Journal failure stops without another submit/poll. Cancellation before submission makes no request; subsequent cancellation targets the authenticated exact bridge job once. Foreign receipts reject, non-200 outcomes have safe errors/no write retry, terminal success racing cancel remains success. Legacy unhooked routing/binary/rights/cost contracts remain.

CAPABILITIES PARTIAL: Native durable generative request/claim/ticket/progress/cancel/recovery, protected approved factory/scoped references/cost/result full local decode/explicit attachment/Assets controls. Approved actual graph/model/GPU/provider provisioning and genuine acceptance. Original MediaPlan/Mode A/B/full Trend/learning/hardening/A/B/C remain.

TESTS: 63 affected API PASS/27.59s; 15 new lifecycle cases, earlier overlapping 61 PASS/40.85s. Native compatibility 20 PASS/2.968s. Latest full API e59a7d5 2659 PASS/11 SKIP/1512.89s and unchanged Native 533 PASS/331.869s plus derived 82 affected PASS, Studio 206 PASS/1000.2963ms retained without unnecessary broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: HTTP workflow/job/progress/cancel/binary/scope/API fixtures. LOCAL-REAL TESTS: process/typed provider and Native import/cost/rights compatibility; no actual GPU/generated media/decode or new playable bundle. Existing binary wire fixtures include deliberately non-decodable bytes and are not media acceptance. Real secret/paid/Hub/post/browser/Owner/production actions = 0.

EVIDENCE: `docs/COMFYUI_GENERATION_LIFECYCLE.md`, `docs/north-star/comfyui-lifecycle-evidence.json`, three hashed external logs. Existing actual accepted media and local fixture archives are unchanged; no artifact replaced.

REGRESSIONS: all affected API and Native compatibility tests pass; unchanged caller/provenance/cost/rights/publishing gates preserved. EXTERNAL BLOCKERS: real reviewed workflow/model/GPU/provider and browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for remaining safe integration. NEXT WAVE: Native durable generation/factory/reference/result/attachment/UI and original full MediaPlan/Mode A/B/Trend/learning/hardening/A/B/C. No merge, live migration, paid provider, external publishing or deployment.

### Wave 5C/D/E / Native — Typed admission and protected approved factory

WAVE: 5C / 5D / 5E / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `31b8fa67d01d8a2f397d157196a7411f6679ff32`, pushed/preserved in `north-star-comfyui-lifecycle.bundle`, SHA256 `5eba080e3eb96a0d5702c198c9ffeff34104196b8e019e92dea1264cba7b3cf1`; 182 ahead/0 behind, fresh 15 accepted hashes and clean live source. Admission increment will be separately committed/preserved.

CAPABILITIES COMPLETED: strict native image/video/reference/mask/mode/duration/seed/scale/acknowledgment contracts selecting owned asset IDs and hashes, no client URI/graph/result/credentials/rights. Protected external workspace-bound default-off registry and local/isolated token destination, pure shared approved workflow model reuse, frozen manifest/graph/Owner-review/executable structure, pre-dispatch drift rejection. Existing placeholders stay NOT_CONFIGURED despite enabled credentials. Injection-only wire fixture mode reuses nine existing routes and lifecycle without rights/cost/production promotion.

CAPABILITIES PARTIAL: modules not wired into Native server/queue/UI. Durable requests/tickets/progress/cancel/recovery, physical scoped references/rights/staging, worker/cost/result full local decode/attachment/Assets remain. Actual reviewed models/workflows/GPU and genuine acceptance. Full original MediaPlan/Mode A/B/Trend/learning/hardening/A/B/C remain applicable.

TESTS: 40 affected Native PASS/21.953s, seven new cases; earlier overlapping 27 PASS/6.292s. New modules plus stock/rights/Phase10 HTTP compatibility checked. No existing Native runtime/UI/API source changed; prior full Native 533 PASS/331.869s, derived 82 affected PASS, SDK affected API 63 PASS/27.59s, full API 2659 PASS/11 SKIP/1512.89s and Studio 206 PASS/1000.2963ms retained without broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: Native typed admission, synthetic protected tokens/manifests/approval metadata, local wire lifecycle and nine route combinations. LOCAL-REAL TESTS: guarded source manifest/graph/temp configuration reads and drift, existing actual stock media/rights/Phase10 HTTP compatibility. No actual generated media/decode, GPU, real key, paid operation, Hub/post, browser/Owner UAT or production.

EVIDENCE: `docs/NATIVE_GENERATION_ADMISSION.md`, `docs/north-star/native-generation-admission-evidence.json`, two hashed external logs. Accepted/source/playable artifacts remain unchanged; no replacement.

REGRESSIONS: all affected tests pass; unconfigured graphs cannot execute and no Native capability flag/runtime enablement is introduced. EXTERNAL BLOCKERS: actual reviewed workflow/model/GPU/provider and browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for continuing safe integration. NEXT WAVE: Native persistent generation/factory/reference/cost/result/attachment/UI, original MediaPlan/Mode A/B/full Trend/learning/hardening/A/B/C. No main merge, live migration, paid provider, external publishing or deployment.

### Wave 5E — Reviewed HTTP execution and durable GPU write reconciliation

WAVE: 5E / 5C / 5D / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `8d029250e04bda9b17ecd94f0a5cd601a2183f5f`, pushed/preserved in `north-star-native-generation-admission.bundle`, SHA256 `b092c79cb7aafb6c12bc7457f2db00650127862a04cfbfdfda19f9aba175da38`; 183 ahead/0 behind, fresh 15 accepted hashes and clean live source. This backend increment will be separately committed/preserved.

CAPABILITIES COMPLETED: optional runtime HTTP backend reusing approved compiler/transport/bridge-owned SQLite and decoded binary store. Trusted server workspace/job/retry context, workflow admission, default disabled and placeholder NOT_CONFIGURED. FULL synchronous prompt write reservation, exact identity/config/compiled graph hashes, interrupted write/startup/timeout reconciliation with no automatic POST retry; only definitive rejection or remote terminal failure/cancel allows an explicit new attempt. Targeted cancellation remains pending until exact remote terminal, lost-reply reconciliation and success race preservation. Bound saved history/graph/output, one allowed PNG/JPEG/MP4, full FFprobe/FFmpeg decode, immutable scoped storage and deeper Windows path support. Optional GPU Compose settings remain inert to CPU mode.

CAPABILITIES PARTIAL: no default trusted physical reference resolver/staging endpoint, Native durable queue/reference/worker/cost/attachment/UI, real executable reviewed workflow/models/custom nodes/GPU/source-pin verification or genuine generated quality acceptance. Full original MediaPlan/Mode A/B/Trend/learning/hardening/A/B/C remain applicable. Model labels are reviewed manifest declarations; costs remain null and rights unknown/ineligible.

TESTS: 138 affected bridge/API PASS/42.65s, including 26 new backend cases; 26 Native compatibility PASS/6.395s. Earlier overlapping r1 20 PASS, r4 33 PASS/12.93s and r5 136 PASS/41.23s retained. R2/R3 failed timeout fixture and a real Windows deep-path registration issue; monotonic test deadline and extended owned paths resolve them. Latest full Native 533 PASS/331.869s, full Linux API 2659 PASS/11 SKIP/1512.89s and unchanged Studio 206 PASS/1000.2963ms retained; broad repeat not required for this isolated optional bridge change.

REAL PROVIDER TESTS: 0. MOCK TESTS: explicit fake reviewed nodes/model/approval metadata, GPU HTTP/ASGI wire responses, write errors/lost replies/cancel races/status/history/input/output corruption and scope/config drift. LOCAL-REAL TESTS: actual FFmpeg synthetic PNG/JPEG/MP4 full decode and filesystem registration; authenticated neutral provider consumer; three saved backend-produced artifacts and fresh-process exact offline replay. No manually injected job result in this rehearsal, real key/GPU/paid provider, Hub/post, browser/Owner UAT or production.

EVIDENCE: `docs/COMFYUI_HTTP_BACKEND.md`, `docs/north-star/comfyui-http-backend-evidence.json`, twelve hashed exports under `recovery/comfy-http-backend-n2`, eleven hashed logs. Fresh owned data root `C:\vf-comfy-http-fixture-02`. Earlier n1 and failed test roots/logs retained; accepted media is not replaced.

REGRESSIONS: final affected tests pass and Native pure-contract compatibility passes; placeholder/default-disabled, rights, null cost and production eligibility gates stay closed. EXTERNAL BLOCKERS: actual reviewed workflows/licensed models/GPU/source-pin, configured real providers, browser/Owner UAT and production acceptance. OWNER ACTION REQUIRED: none for continuing safe implementation. NEXT WAVE: trusted physical reference staging and Native durable generation/worker/cost/result/attachment/Assets, original MediaPlan/Mode A/B/Trend/learning/hardening/A/B/C. No main merge, live migration, external publishing or production deployment.

### Wave 5E / Native prerequisite — Physical scoped reference staging

WAVE: 5E / 5C / 5D / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `ab80dfd7e2cb390f68fd1660a656524cc79948c1`, pushed/preserved in `north-star-comfy-http-backend.bundle`, SHA256 `90228ef950096dcc99f44d6c9d25b8393a999a798bd4c1b30e702f3d0c4d4da5`; 184 ahead/0 behind, fresh 15 accepted hashes and clean live source. Reference increment will be separately committed/preserved.

CAPABILITIES COMPLETED: default-disabled authenticated 32 MiB/30s streamed PNG/JPEG intake, strict receipt metadata/no duplicate keys/extra graph/secret/path fields, actual MIME/magic/full FFprobe/FFmpeg decode, immutable scoped reference files and metadata, byte/receipt/project/expiry integrity and bounded storage. Trusted physical resolver, deterministic target-bound filename, FULL-commit no-overwrite upload intent, exact readback and no unresolved POST replay. Project binding in registered-reference submission/poll/cancel and compiler tokens, input/target drift before staging, source-fixture/live prohibition, compatible legacy text wire/request/journal retry. Unknown generation/upload costs remain null, output unknown rights/ineligible.

CAPABILITIES PARTIAL: admission is a trusted authenticated service assertion; bridge cannot independently verify project existence, licensing or Owner decision from its hash. Native actual project/physical asset/current rights/scoped Owner receipt issuance, protected service intake, durable generation queue/worker/cost/tickets/result/attachment/Assets UI remain. Genuine reviewed models/workflows/GPU/source-pin/generated quality acceptance; production S3/backup/retention/Docker/soak. Full original MediaPlan/Mode A/B/Trend/learning/hardening/A/B/C remains applicable.

TESTS: 163 affected bridge/API PASS/47.18s, 25 new cases (20 reference, three SDK project-response, two early-drift/legacy-journal). Native compatibility 26 PASS/5.647s. Earlier overlapping compatibility 47 PASS/15.16s and reference/scope subset 28 PASS/8.22s retained. First subset failed one composite wire fixture with duplicated Authorization casing; fixture corrected, no product gate weakened. Prior full Native 533 PASS/331.869s, full Linux API 2659 PASS/11 SKIP/1512.89s and unchanged Studio 206 PASS/1000.2963ms retained without broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: explicit synthetic source rights assertions/nodes/models/approval references, GPU upload/prompt/status/history and lost replies/cancellation/scope/corruption. LOCAL-REAL TESTS: actual local FFmpeg source/mask PNG and JPEG decoding, scoped byte storage, authenticated streamed intake/neutral adapter, ten actual decoded outputs over mock wires, new-process exact offline output/reference/confirmed journal replay. No actual Source Owner exception/legal clearance, real key/GPU/paid provider, Hub/post, browser/Owner UAT or production.

EVIDENCE: `docs/COMFYUI_REFERENCE_STAGING.md`, `docs/north-star/comfyui-reference-staging-evidence.json`, 29 hashed exports under `recovery/comfy-references-n2`, eight hashed logs. Fresh owned data `C:\vf-comfy-reference-fixture-02`; two source/mask images, nine request variants and ten outputs, exactly two mock image uploads and ten prompt writes despite lost replies. No manually replaced job result. Earlier n1 and failed roots/logs retained, accepted artifacts not replaced.

REGRESSIONS: final affected and Native compatibility pass; legacy request/journal replay, default-disabled, unknown generated rights/cost, fixture/live and production gates remain. EXTERNAL BLOCKERS: actual licensed reviewed models/workflows/GPU/source-pin, real configured providers, browser/Owner UAT and production acceptance. OWNER ACTION REQUIRED: none for continuing safe implementation. NEXT WAVE: Native actual source/rights/receipt binding and persistent generation/worker/cost/result/attachment/Assets, original MediaPlan/Mode A/B/full Trend/learning/hardening/A/B/C. No main merge, live migration, paid provider, external publishing or production deployment.

### Wave 5C/5D/5E — Native physical source and rights admission prerequisite

WAVE: 5C / 5D / 5E / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `464481425e5adabd3a8c7ee9fd73ffdcb0bdb0c8`, pushed and preserved in `north-star-comfy-references.bundle`, SHA256 `88d87847b90444c85716cd6bfd58a9f5feffd8a283bceefbe156846c28e4171e`; 185 ahead/0 behind. Native source increment will receive its own commit/push/bundle and fresh 15 accepted hash verification.

CAPABILITIES COMPLETED: actual registered project/image/revision/document and SHA/magic/size/dimension/local full-decode binding with link rejection; unknown upload attestation rejection; registered raw rights or current scoped expiring/revocable Owner exception; derived review-marker guard; fixture/live and acknowledgment gates; frozen typed source/parameter/configuration/rights snapshots, credential/origin/transport/graph drift check; immutable expiring service admissions; durable FULL SQLite pre-upload intent, exact protected authenticated metadata readback and lost-reply reconciliation without repeat POST; bounded 64-KiB/35-second response, no redirect/proxy/client path/graph/secret; exact confirmed URI/mask provider projection. Raw rights, project/approval/timeline and actual billed cost remain preserved/unknown.

CAPABILITIES PARTIAL: Native server generation routes/jobs/independent worker/tickets/progress/cancel/recovery/cost/result decoding/attachment/Assets are not wired. Genuine licensed reviewed workflows/models/GPU/source-pin/quality; full original Mode A/B/MediaPlan/Trend/learning/hardening/A/B/C remain.

TESTS: Native affected 40 PASS/7.898s (15 new source-admission cases), bridge/API affected 58 PASS/76.87s (one new known-status scoped-exception case); counts overlap prior suites. Snapshot timestamp/hash bug corrected; fixture version/reuse assertions corrected; shared Windows pytest temp denial avoided with a fresh owned base. Failed logs/partial rehearsal roots retained. Prior full Native 533 PASS/331.869s, Linux API 2659 PASS/11 SKIP/1512.89s and Studio 206 PASS/1000.2963ms retained without broad repeats.

REAL PROVIDER TESTS: 0. MOCK TESTS: scoped Owner exception/rights metadata, authenticated bridge/explicit GPU nodes/models/wires and lost replies; no actual license/Owner clearance. LOCAL-REAL TESTS: actual owned Pillow source/mask pixels, Native JPEG intake/decode, authenticated ASGI bridge FFmpeg decode/storage, two actual PNG/MP4 outputs through neutral adapter, separate-process exact offline bytes/projects/versions/admissions/output/upload journals within TTL. No manually injected result, real credentials/model/GPU/paid call, external post/Hub, browser/Owner UAT or production.

EVIDENCE: `docs/NATIVE_GENERATION_REFERENCES.md`, `docs/north-star/native-generation-reference-evidence.json`, 16 hashed exports under external `recovery/native-generation-references-n4`; eleven hashed logs. Owned data `C:\vf-native-generation-references-fixture-04`; three immutable Native references and three mock GPU uploads, two prompt writes despite lost intake response. Native project/timeline unchanged.

REGRESSIONS: affected suites pass; accepted source/media unchanged pending fresh preservation verification. EXTERNAL BLOCKERS: actual licensed reviewed models/workflows/GPU/source-pin, configured providers, browser/Owner and production acceptance. OWNER ACTION REQUIRED: none for safe implementation. NEXT WAVE: Native generation queue/worker/lifecycle/cost/result/attachment/Assets, then original Mode A/B/MediaPlan/full Trend/learning/hardening/A/B/C. No main merge/live migration/new budget/real publishing/deployment.

### Wave 5C/5D/5E — Read-only lost generation submission reconciliation

WAVE: 5C / 5D / 5E / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `562f5fca6bccebbb1ef00c4c93a014edbc461c7f`, pushed/preserved in `north-star-native-generation-references.bundle`, SHA256 `1703b07c19df96ccec15dbfca7a80cc848cd80628be2ac4b1c8053ec8b192e5e`; 186 ahead/0 behind, fresh 15 accepted hashes/live source clean. Lookup increment receives a separate commit/push/bundle.

CAPABILITIES COMPLETED: authenticated workspace/client-key lookup returns copied job plus complete frozen request SHA with no inputs/secrets/dispatch/events; neutral reconciliation verifies full request/key and optional saved ticket before scope/workflow/project/lifecycle/cancel/registered binary reads; bounded response and duplicate/mime/redirect guards; no generation POST or bridge retry; legacy submit fingerprint preserved; targeted pending cancellation only after binding; persistent lookup with execution disabled. Actual local PNG/MP4 recovery after lost reply keeps exactly two submission/prompt writes.

CAPABILITIES PARTIAL: Native durable generation queue/worker/tickets/progress/cancel/recovery/cost/result ingestion/explicit attachment/Assets not wired. Genuine licensed workflows/models/GPU/source-pin/quality and full original Mode A/B/MediaPlan/Trend/learning/hardening/A/B/C remain.

TESTS: 173 affected bridge/API PASS/39.61s; final focused 17 PASS/1.53s including an additional restart case; counts overlap. Fourteen new API and two new bridge cases plus enhanced existing actual-media consumer. Native compatibility 22 PASS/5.271s. First command typo ran no tests; log retained. Prior full Native 533 PASS/331.869s, Linux API 2659 PASS/11 SKIP/1512.89s and Studio 206 PASS/1000.2963ms retained without broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: authenticated service/lost replies/typed nodes/models/GPU wires/scope corruption/targeted cancel, explicitly synthetic media/rights. LOCAL-REAL TESTS: actual Native source JPEGs, authenticated ASGI intake, FFmpeg decode and two binary outputs; lost generation reply with no ticket and known-ticket read return exact same jobs/bytes; 17 retained exports and separate-process exact offline replay. No manual job result injection, genuine credentials/GPU/cost/legal/Owner UAT/external publish/Hub/deployment.

EVIDENCE: `docs/COMFYUI_JOB_RECONCILIATION.md`, `docs/north-star/comfyui-job-reconciliation-evidence.json`; external `recovery/native-generation-references-n5`, owned data `C:\vf-native-generation-references-fixture-05`, six hashed logs. Exactly three reference intake/GPU input writes, two generation submission/prompt writes and two read-only lookup calls. Native project/approval/timeline unchanged.

REGRESSIONS: final affected/focused/Native checks pass; fresh accepted verification follows preservation. EXTERNAL BLOCKERS: real licensed reviewed workflows/models/GPU/source-pin, configured providers and Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation. NEXT WAVE: Native generation queue/worker/cost/result/attachment/Assets, original Mode A/B/MediaPlan/full Trend/learning/hardening/A/B/C. No main merge/live migration/new budget/real publishing/deployment.

### Wave 5C/5D/5E — Native durable generation admission and claim foundation

WAVE: 5C / 5D / 5E / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `ec16784652488777f10701394f594095651f07df`, pushed/preserved in `north-star-comfyui-job-reconciliation.bundle`, SHA256 `334ff7bc50e321d564c2e2bdca711ec7e4c7ef753e4cc994f4f3205055732047`; 187 ahead/0 behind and 15 accepted hashes/live source clean. Native queue increment receives a separate commit/push/bundle.

CAPABILITIES COMPLETED: additive owned Native generation workspace/jobs/events/recovery journal, frozen strict request/project/document/source/workflow/configuration, concurrent idempotent admission, default-inactive history, one 900-second fenced claim, expired claims require review, current confirmed reference/scalar/mask binding and final pre-dispatch recheck, unique exact generation cost intent prevents reuse/duplicate submission, typed content-free ticket/version/workspace observations and deduplication, unstarted local cancel/running pending cancel, budget refusal state, explicit bounded read-only recovery receipt/claim, no automatic generation/retry authority. Project/approval/timeline and actual billing remain untouched/unknown.

CAPABILITIES PARTIAL: executing Native generation worker, actual generated-result intake/success/explicit attachment and HTTP/Assets/RBAC integration not connected. Genuine licensed reviewed workflows/models/GPU/source-pin/quality and full original Mode A/B/MediaPlan/Trend/learning/hardening/A/B/C remain.

TESTS: affected Native queue/registry/reference/cost 49 PASS/11.921s, 14 new queue cases. Earlier overlapping 34 PASS/6.505s and 48 PASS/8.997s retained; no failed test. Final pre-dispatch source/project/URI recheck and exact cost-operation binding added during review. Latest prior bridge/API 173 PASS/39.61s plus final focused 17 PASS/1.53s retained; full Native 533 PASS/331.869s, Linux API 2659 PASS/11 SKIP/1512.89s and Studio 206 PASS/1000.2963ms unchanged, no broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: provider observations/cancellation/reconciliation and one source-intake wire, strictly fixtures, no generation results. LOCAL-REAL TESTS: actual SQLite/concurrent transactions/claims/cost intents, actual owned image/source binding, three fresh-root jobs and separate-process exact default-inactive projects/versions/jobs/events/cost/recovery replay. Queue rehearsal external requests=0, paid operations=0, generated result assets=0; cost intents are not paid/billed outcomes. No real keys/GPU/models/legal/Owner UAT/publish/Hub/deployment.

EVIDENCE: `docs/NATIVE_GENERATION_QUEUE.md`, `docs/north-star/native-generation-queue-evidence.json`, four hashed exports under external `recovery/native-generation-queue-n2`, seven logs, owned data `C:\vf-native-generation-queue-fixture-02`. Earlier n1 retained. Native project/approval/timeline unchanged.

REGRESSIONS: final affected tests pass; fresh accepted verification follows preservation. EXTERNAL BLOCKERS: genuine reviewed workflows/models/GPU/source-pin/provider and Owner/production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: connect independent Native generation worker/read-only recovery/actual result intake/attachment/HTTP/Assets, then original Mode A/B/MediaPlan/full Trend/learning/hardening/A/B/C. No main merge/live migration/new budget/real publishing/deployment.

### Wave 5C/5D/5E — Native actual generated-media staging

WAVE: 5C / 5D / 5E / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `483cc1687382d9ce2d39e06d25e6ee133d00f7a8`, pushed/preserved in `north-star-native-generation-queue.bundle`, SHA256 `b013b90748d2dc0956e710785fd7bd38866ddebd1413b994ae8944cf7feef1ec`; 188 ahead/0 behind, 15 accepted hashes/live source clean. Staging receives a separate commit/push/bundle.

CAPABILITIES COMPLETED: fenced registered binary/job/workspace/input/provenance binding; frozen workflow definition/model/graph/reference hashes; actual Native MIME/magic/PIL or FFprobe/full FFmpeg decoding; video dimensions/duration/fps/audio agreement; immutable SQLite stage receipt; exact repeat produces no extra files; physical original/normalized/thumbnail hash checks; unknown rights/ineligibility/attention, unknown cost, fixture distinction; failed-intake cleanup restricted to new owned files; default-inactive separate-process exact replay. Project/approval/canonical timeline remain unchanged.

CAPABILITIES PARTIAL: executing independent Native worker, terminal success, explicit result attachment, HTTP/Assets/RBAC still next. Genuine GPU/provider/model/source-pin/license/quality, alpha-aware mask/logo editing, full original Mode A/B/MediaPlan/Trend/learning/hardening/A/B/C remain.

TESTS: final affected Native media/queue/registry/reference/cost 56 PASS/21.311s, 7 new media cases. Initial overlapping 35 count included 14 duplicate helper-discovered queue cases; import corrected. Intermediate r2/r3 failures retained: fixture model mismatch and incorrect source-snapshot field name, fixed without weakening gates. Focused r4 21 PASS/4.097s before final video metadata binding. Prior full Native 533 PASS/331.869s, Linux API 2659 PASS/11 SKIP/1512.89s and Studio 206 PASS/1000.2963ms unchanged; no broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: registered bridge metadata and provider observations, no bridge request or actual GPU/model generation. LOCAL-REAL TESTS: actual synthetic PNG and FFmpeg MP4, Native full media decoding, SQLite immutable stage/replay, original/normalized/thumbnail hashes and separate-process exact default-inactive projects/versions/jobs/events/cost/staged-media replay. Two assets, external requests=0, generation POSTs=0, paid operations=0; cost intents are not billed outcomes. Rehearsal claims end recovery_required rather than claiming execution success.

EVIDENCE: `docs/NATIVE_GENERATION_MEDIA.md`, `docs/north-star/native-generation-media-evidence.json`, 12 hashed exports under external `recovery/native-generation-media-n1`, seven logs, owned `C:\vf-native-generation-media-fixture-01`. No accepted artifacts replaced.

REGRESSIONS: final affected checks pass; fresh accepted verification follows preservation. EXTERNAL BLOCKERS: genuine reviewed workflows/models/GPU/source-pin/provider and Owner/production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: independent Native generation worker/read-only reconciliation/success/explicit attachment/HTTP/Assets; continue original full Mode A/B/MediaPlan/Trend/learning/hardening/A/B/C. No main merge/live migration/new budget/real publishing/deployment.

### Wave 5C/5D/5E — Native executing generation worker and explicit asset import

WAVE: 5C / 5D / 5E / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `d69e27acb61ef447323b0f639ade819751b4dd99`, pushed/preserved in `north-star-native-generation-media.bundle`, SHA256 `d1895a23c527a02ad0411b70e4d5285ff5d781b6d318a08360a6f32c8cd88505`; 189 ahead/0 behind, 15 accepted hashes/live source clean. Worker increment receives a separate commit/push/bundle.

CAPABILITIES COMPLETED: independent default-inactive Native generation worker; actual scoped reference staging; conservative generation dispatch cost intent before call; unknown-price budget refusal; source/input/config/fenced lease checks; bound observations; actual Native decoded media staging; immutable terminal receipts; explicit read-only existing-job recovery without duplicate submission; actual post-stage crash recovery with no new calls; duplicate source hash order matching bridge; configuration drift fails affected queue head; unknown rights/cost/ineligibility retained; explicit acknowledged hash/revision/key-bound atomic asset import, approval clear/version/frozen replay. No timeline automatic placement.

CAPABILITIES PARTIAL: human Native HTTP/Assets/RBAC and all typed operation UX next; genuine reviewed workflows/models/GPU/source-pin/rights/quality/accounting, full original Mode A/B/MediaPlan/Trend/learning/hardening/A/B/C remain.

TESTS: final Native worker/media/queue/registry/reference/cost/observability 78 PASS/40.393s, 11 new worker cases. Earlier overlapping 30 PASS/10.743s and 10 PASS/2.733s retained; no failed test. Prior full Native 533 PASS/331.869s, Linux API 2659 PASS/11 SKIP/1512.89s and Studio 206 PASS/1000.2963ms retained; no broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: provider-unit callbacks and official budget configuration are explicit fixtures; connected bridge uses approved fixture graphs/model/node names and mock GPU APIs. LOCAL-REAL TESTS: actual Native worker/SQLite/fences/costs, authenticated bridge REST/ref intake, actual graph compilation/FFprobe/full FFmpeg binary registration/Native normalization, three synthetic PNG/MP4 outputs and original/normalized/thumbnail hashes. Exactly three Native submits/three mock GPU prompt writes/three Native reference and GPU upload writes/one read-only lookup; no manually injected generation result. Three explicit imports/six unknown-cost operations/zero paid operations. Separate-process default-inactive exact histories/receipts/physical replay passes. No AI model, licensed content, paid outcome or Owner UAT.

EVIDENCE: `docs/NATIVE_GENERATION_WORKER.md`, `docs/north-star/native-generation-worker-evidence.json`, 22 hashed exports under external `recovery/native-generation-worker-n2`, six logs, owned `C:\vf-native-generation-worker-fixture-02`. Earlier n1 retained before final review adjustments. Project remains unchanged until explicit imports; approval clears and versions increment three times, no automatic timeline edit.

REGRESSIONS: final affected checks pass; fresh accepted verification follows preservation. EXTERNAL BLOCKERS: genuine provider/GPU/quality/license/accounting and Owner/production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: wire Native HTTP/Assets/RBAC protected default-off generation, then original full Mode A/B/MediaPlan/Trend/learning/hardening/A/B/C. No main merge/live migration/new budget/real publishing/deployment.

### Wave 5C/5D/5E — Native generation HTTP, Assets controls and actual recovery

WAVE: 5C / 5D / 5E / 3 / 8. STATUS: IN PROGRESS. GENERATIVE_MEDIA_READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `cb0bdbc3fe88bde0eadb39f2544d3562c5bdaceb`, pushed/preserved in `north-star-native-generation-worker.bundle`, SHA256 `a8e28d6299c4e01b3385b6a32e6b5d5a091f24ad01a07955f243dc8fe87ff315`; 190 ahead/0 behind, 15 accepted hashes/live source clean. HTTP/Assets increment receives a separate commit/push/bundle.

CAPABILITIES COMPLETED: Native Assets eight typed image/video operations, owned references/mask/aspect/seed/negative prompt/scale/duration, explicit provider/fixture consent, saved progress/bounded polling/history, scoped local review, targeted cancellation, acknowledged existing-job reconciliation and explicit asset import; human editor session/CSRF/scope checks before bodies, reviewer/viewer read-only, service bearer cannot replace human, browser receives no key/origin/graphs/results input; protected external reviewed workflow manifest outside state plus CLI default-off/human registry, unsupported optional operations NOT_CONFIGURED; exact frozen import projection; active generation blocks backup, actual restore and separate-process disabled physical/history replay. Existing shot/advanced canonical timeline and other provider capabilities retained.

CAPABILITIES PARTIAL: genuine reviewed GPU/model/workflow/source-pin/quality/licensing/accounting, alpha-aware mask/logo editing, browser viewport/non-developer/Owner UAT, full versioned Mode A Media Planner/resolver/script/storyboard, full original Mode A/B/Trend/learning/hardening/A/B/C remain. API/worker/DOM evidence is not Owner acceptance.

TESTS: final full Native 594 PASS/376.826s; final affected Native 56 PASS/22.949s; full Studio 214 PASS/859.8792ms. Added five HTTP, one backup, one protected-registry and eight DOM cases. Earlier overlapping 32 PASS/28.300s and Studio 213 PASS/1057.2891ms retained. First full Native 593/376.526s had one stale exact capability-list assertion; updated to include new capability while retaining all cookie/CSRF/no-write assertions, then full 594 passes. No accepted behavior was removed. Latest prior Linux API 2659 PASS/11 SKIP/1512.89s unchanged; no API implementation edits or broad repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: approved fixture graphs/model/node names and mock GPU APIs; UI DOM/human credentials clearly fixtures. LOCAL-REAL TESTS: actual loopback human HTTP/editor/viewer scopes, independent Native worker, authenticated bridge/ref intake/graph compilation, actual PNG/MP4 full decode/normalization/original/thumbnail hashes; 51 human requests, three Native generation submits/three mock GPU prompt writes/three reference intake and GPU upload writes/one read-only lookup; lost reply never resubmits, post-stage crash recovers locally with no extra calls. Three explicit imports/six null-billing cost operations/zero paid operations. Actual owned backup/restore and separate-process exact source/restored replay with inactive generation pass. No manually injected generation result, genuine AI model/licensed content/paid outcome/Owner UAT/publish/Hub/deployment.

EVIDENCE: `docs/NATIVE_GENERATION_HTTP_STUDIO.md`, `docs/north-star/native-generation-http-studio-evidence.json`, 26 hashed exports under external `recovery/native-generation-http-n3`, eleven logs, owned `C:\vf-native-generation-http-fixture-03` and restore `C:\vf-native-generation-http-restore-03`. First n1 retained after script helper naming collision before import, fixed without changing product gates; n2 successful earlier source retained. No accepted artifact replaced.

REGRESSIONS: final full Native/Studio and affected checks pass; fresh 15 accepted/live verification follows preservation. EXTERNAL BLOCKERS: genuine provider/GPU/quality/license/accounting, browser/Owner and production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: full versioned Native Mode A Media Planner using existing script/storyboard/shot/canonical timeline/imported stock/generated media; continue original full Mode A/B/Trend/learning/hardening/A/B/C. No main merge/live migration/new budget/real publishing/deployment.

### Wave 6A — Native versioned storyboard Media Planner and canonical apply

WAVE: 6A / 3 / 7 / 8. STATUS: IN PROGRESS. MODE A READY = NO; MODE B READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `cf6a3dd1a12c1b401680a00f0a09533f64fe155d`, pushed/preserved in `north-star-native-generation-http-studio.bundle`, SHA256 `b98bd533c06131f55517f02f143844e6adf37f007c6533d7d394220cef3a1908`; 191 ahead/0 behind, 15 accepted hashes/live source clean. Planner increment receives a separate commit/push/bundle.

CAPABILITIES COMPLETED: typed versioned storyboard plans from actual script/shot/niche/channel/brand/canvas/assets/budget/protected provider availability; strategy/fallback/query/prompt/attributed rights/null confidence/null price; fingerprint deduplication and bounded saved history; current CAS/hash/source/configuration checks; select/revise without canonical edits, acknowledged atomic same-shot TimelineSnapshot apply/history/approval clearing; source-footage B-roll retained; duplicate plan scope reset. Native Assets UI and human editor/reviewer/viewer/CSRF/strict input/late-response guards. Actual two-niche visual proxies and database/media/preview/cost/history recovery.

CAPABILITIES PARTIAL: finite-budget unpriced-AI feasible planning fallback, explicit plan-to-provider resolver/import/replanning, automatic semantic ranking/Vision, researched/genuine generated/spoken Mode A, full Mode B, original Trend/publishing/analytics/learning/Hub/hardening/A/B/C. A silent proxy is not final audio/QC/Owner acceptance.

TESTS: full Native 605 PASS/397.205s; affected Native 40 PASS/43.901s; focused Native 11 PASS/13.977s; full Studio 221 PASS/1039.8603ms, seven new DOM cases. Earlier overlapping eight HTTP PASS/10.141s retained. No failed product test. Latest Linux API 2659 PASS/11 SKIP/1512.89s unchanged; no API implementation edits.

REAL PROVIDER TESTS: 0. MOCK TESTS: authored narration/storyboard, owned synthetic PNGs, human credentials and protected generation catalog fixture. LOCAL-REAL TESTS: actual human loopback HTTP/ingest/SQLite/asset hashes/saved decisions/canonical apply/FFmpeg 540x960 three-second silent proxies/Vietnamese captions; 29 requests, zero provider calls/paid operations; source and unrelated shots preserved. Actual separate-process exact reopen and backup/restore pass. No approval, research, LLM, ASR, TTS, generated/stock provider, final render/QC, browser/Owner/publishing/Hub/deployment acceptance.

EVIDENCE: `docs/NATIVE_STORYBOARD_MEDIA_PLANNER.md`, `docs/north-star/native-studio-media-plan-evidence.json`, 24 hashed exports under external `recovery/native-studio-media-plan-n4`, ten logs, owned `C:\vf-native-fixture-studio-media-plan-04` and restore `C:\vf-native-fixture-studio-media-plan-restore-04`. Both decoded preview frames inspected. Failed n1 catalog-vs-frozen profile comparison, n2 raw Vietnamese HTTP header and n3 cp1252 child stdout are retained; script fixes use exact frozen project selection, existing percent-encoded filename convention and ASCII-escaped JSON transport. No product gate changed or accepted artifact replaced.

REGRESSIONS: full Native/Studio and affected cases pass; fresh 15 accepted/live verification follows preservation. EXTERNAL BLOCKERS: genuine provider/quality/legal/billing/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: budget-feasible planner fallback, explicit plan-to-stock/generation resolution/import/replanning, then original full Mode A/B/MediaIntelligence/Trend/learning/hardening/A/B/C. No main merge/live migration/new paid budget/real publishing/deployment.

### Wave 6A/8A — Budget-feasible storyboard planning and exact historical policies

WAVE: 6A / 8A / 7 / 3. STATUS: IN PROGRESS. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; MODE A/B READY = NO.

HEAD SHA: parent `0b8b90e95939373d54c52b8cc79742331207f206`, pushed/preserved in `north-star-native-studio-media-plan.bundle`, SHA256 `7bc177b877763dba98f6054caead0f84b6435018a70f2928335e3bdd65f9ad97`; 192 ahead/0 behind, 15 accepted hashes/live source clean. Budget-policy increment receives separate commit/push/bundle.

CAPABILITIES COMPLETED: planner v2 finite/zero/positive cap treats unknown generation estimates as blocked new generation, continues to eligible registered media/configured stock, allows existing AI asset reuse without new budget/provider, and keeps null-price requires_approval when no feasible fallback. Budget blocks are explained in Assets. Prior v1 histories return exact original JSON/SHA, no added DTO defaults/destructive migration, and require explicit new v2 decisions before current apply. Four meaningful Native budget/history/reuse/stock cases and one DOM policy case added.

CAPABILITIES PARTIAL: explicit plan-to-provider resolver and durable job/result/import/replanning, genuine legal/pricing/quality/semantic provider acceptance, full original Mode A/B/Trend/learning/Hub/hardening/A/B/C and browser/Owner/production acceptance remain.

TESTS: affected Native planner/cost 28 PASS/20.525s; full Studio 222 PASS/1305.203ms. Earlier overlapping 26 PASS/31.925s retained. Added reuse fixture initially failed in 28/19.855s because its filename did not match actual visual queries; corrected explicit fixture metadata, retained relevance/right/budget gates; final 28 passes. Prior full Native 605 PASS/397.205s at parent `0b8b90e` retained, not claimed as final changed-policy full run. Latest Linux API 2659 PASS/11 SKIP/1512.89s unchanged. No broad repeat beyond affected suites.

REAL PROVIDER TESTS: 0. MOCK TESTS: configured generation catalog with transport forbidding all calls, registered-AI rights and stock availability are explicit mock assertions. LOCAL-REAL TESTS: actual human HTTP/SQLite/capped budget/normalized owned synthetic images/canonical selections/FFmpeg 540x960 three-second silent visual proxies, 31 requests/two niches, zero provider/paid operations; actual exact separate-process backup/restore. No TTS/final QC/browser/Owner/provider/license/billing/publish/Hub/deployment acceptance.

EVIDENCE: `docs/NATIVE_STORYBOARD_MEDIA_PLANNER.md`, `docs/north-star/native-media-plan-budget-evidence.json`, 24 hashed exports in external `recovery/native-studio-media-plan-budget-n1`, five retained logs, owned `C:\vf-native-fixture-studio-media-plan-budget-01` and restore `C:\vf-native-fixture-studio-media-plan-budget-restore-01`. Previous v1 evidence roots/videos/receipts remain intact.

REGRESSIONS: affected Native/full Studio pass; fresh 15 accepted/live preservation follows. EXTERNAL BLOCKERS: genuine provider/quality/legal/billing/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: explicit storyboard plan-to-stock/generation resolution/job/result/import/replanning, then full original Mode A/B/MediaIntelligence/Trend/learning/hardening/A/B/C. No main merge/live migration/new paid budget/real publishing/deployment.


### Wave 6A / 5 / 8 — Native storyboard plan-to-provider resolution

WAVE: 6A / 5A / 5C / 5D / 5E / 3 / 8. STATUS: IN PROGRESS. MODE A READY = NO; MODE B READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `cea77ce4dab9952eb1a843922020473947ec829f`, pushed/preserved in `north-star-native-media-plan-budget.bundle`, SHA256 `35a5396542fa1e44a9c17033e6ebdec35ea8c0a41c3b70f916c3de262744407d`; 193 ahead/0 behind, 15 accepted hashes/live source clean. Resolution increment receives a separate commit/push/full-history bundle.

CAPABILITIES COMPLETED: immutable workspace/project/plan/version/SHA/shot/revision/document/request/child bindings and job/event atomic admission; concurrent deduplication and losing-child rollback; lost-response exact replay after later project edits; frozen plan-derived generation prompt/aspect/seed/exact supported duration and stock query/type/orientation/parent/result/candidate; current policy/source/budget/provider admission; existing stock Owner/manage permission and editor generation/import, read-only reviewers/viewers, human/CSRF/origin/strict input/foreign scope guards; saved per-shot Studio request/result review/download/import/replan with same-body explicit uncertain-response recovery; no unsaved prompt dispatch, automatic provider writes/import/placement or rights promotion. Original worker/cost/config/manifest/decode/recovery paths reused; scoped binding tables included in actual recovery.

CAPABILITIES PARTIAL: researched/script/storyboard/spoken full Mode A, scene TTS/voice-fit/audio/full QC integration, genuine Vision/ranking/tracking, full Mode B, licensed/priced genuine stock/GPU/model/quality acceptance and original Trend/publishing/analytics/winner/learning/Hub/hardening/final A/B/C. Browser/non-developer/Owner UAT remains unaccepted.

TESTS: full Native 620 PASS/411.034s; final full Studio 232 PASS/1119.6627ms. Eleven new actual backend cases and ten new DOM/composition cases. Earlier overlapping eight backend PASS/16.712s, 16 planner/resolution DOM PASS/136.9423ms and full Studio 230 PASS/1107.9116ms retained. No failed product test; final UI-only history/composition refinement followed the full Native run with unchanged Native implementation and fresh final UI suite/rehearsals. Latest Linux API 2659 PASS/11 SKIP/1512.89s unchanged; no API implementation edits or repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: reviewed synthetic GPU graphs/model/node/API responses, stock official adapter wire responses, authored narration/storyboard and human credentials. LOCAL-REAL TESTS: actual Native human HTTP/SQLite/independent worker/private bridge graph compilation/authenticated physical registration/PNG+MP4 full decode/normalization/scoped review, immutable binding and explicit import/replan; generation fixture 62 human requests/three actual decoded synthetic outputs/three submits/one lost-submit read-only lookup/post-stage local recovery/three reference intakes/uploads/three imports/six null-billing records/zero paid operations. Stock fixture technology channel 17 human requests/three mock API/media wires/two bindings/one decoded import/two null-billing operations/rights-blocked fresh plan. Actual backup/source+restore separate-process exact disabled replay in both. No manually injected Native provider results, real GPU/ASR/TTS/research/license/billing/browser/Owner/publish/Hub/deployment claim.

EVIDENCE: `docs/NATIVE_STORYBOARD_MEDIA_RESOLUTION.md`, `docs/north-star/native-media-resolution-evidence.json`; 28 hashed generation exports in external `recovery/native-storyboard-resolution-n4`, 10 stock exports in `recovery/native-storyboard-stock-resolution-n3`, plus final evidence/reopen files. Owned generation root `C:f-native-generation-resolution-fixture-04` and restore `C:f-native-generation-resolution-restore-04`; stock root `C:f-native-fixture-studio-stock-resolution-03` and restore `C:f-native-fixture-studio-stock-resolution-restore-03`. Earlier failed roots/logs retained: generation n1 authored fixture lacked full narration coverage, n2 compared the entire advancing canonical version wrapper rather than unchanged snapshot/SHA; corrected rehearsal assertions without weakening product coverage/timeline behavior. Stock n1 initial flow passed but separate process import order lacked bridge pure-contract initialization; reordered script imports and retained failure. Successful earlier n3 generation/n2 stock evidence retained after final UI refinement; no accepted artifact replaced.

REGRESSIONS: full Native/final Studio pass; actual source/restored media and immutable journals pass; fresh 15 accepted/live verification follows preservation. EXTERNAL BLOCKERS: genuine provider/quality/legal/billing/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: full Mode A content/script/storyboard/scene voice-fit/audio/QC orchestration over reused canonical components, then remaining original Mode B/Vision/Trend/publishing/analytics/learning/Hub/hardening/A/B/C. No main merge/live migration/new paid budget/real publication/deployment.


### Wave 6E / 8 — Native storyboard full media QC

WAVE: 6E / 2 / 3 / 8. STATUS: IN PROGRESS. MODE A READY = NO; MODE B READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `0dd276ba4ebb06bb572b736de0e0594c06165549`, pushed/preserved in `north-star-native-media-resolution.bundle`, SHA256 `c3abb95f786db24298e2347e689e4f1223c2f162f95ad4e934ed9858c18939f7`; 194 ahead/0 behind. This increment receives a separate commit/push/full-history bundle and fresh accepted-artifact/live-source verification.

CAPABILITIES COMPLETED: new quality-policy storyboard consumer of shared encoded-media duration/resolution/fps/codec/audio/black/freeze/silence/clipping/full-decode/A-V/CPU-luma checks; exact document/approval/canonical/source/manifest/voice binding and contiguous frame-count scene validation; actual libass Vietnamese glyph/outline alpha-mask safe bounds with centisecond/frame coverage and bounded inspection; same intentional-image policy as shared renderer, no video exemption; full/transport/combined reports and masks in immutable render checkpoints; exact first-result/replay JSON shape; mask-corruption rejection; storyboard hard failure terminal failed_qc; legacy reports/checkpoints preserved without assertion upgrades.

CAPABILITIES PARTIAL: genuine speech quality/scene TTS, canonical measured duration editing, audible-preview/final approval flow, semantic Vision, independent rights, all original Mode A/B/Trend/learning/Hub/hardening/A/B/C and browser/Owner/provider/production acceptance.

TESTS: full Native 630 PASS/468.47s, including ten new actual-media/checkpoint/state cases. Earlier overlapping nine QC PASS/21.536s and fit-narration consumer PASS/5.253s retained. Unchanged prior Studio 232 PASS/1119.6627ms and Linux API 2659 PASS/11 SKIP/1512.89s; no UI or API implementation edits warrant repeat. The initial QC integration rejected synthetic planned image freezes; consumer aligned to the existing shared image policy while frozen video remains a hard failure. First checkpoint replay exposed Python tuple/JSON list mismatch; normalize the shared report before first delivery. Earlier failed fixtures/logs preserved, not summed as passing results.

REAL PROVIDER TESTS: 0. MOCK TESTS: signed human credentials, authored script/storyboard, cached 1.2-second synthetic PCM and runtime verification are explicit fixture substitutions. LOCAL-REAL TESTS: 38 human HTTP requests, owned technology image/video ingestion, saved MediaPlan/canonical apply, independent native claim/stage/finish, actual 1080x1920/30fps/3.3s FFmpeg output, two subtitle pixel masks, complete shared QC, actual frozen-video failed_qc with no successful checkpoint, raw PCM unchanged, actual database/files backup/restore and separate-process exact verified checkpoint replay. Zero paid/provider operations, no manually injected final video/QC. Preview remains a silent visual proxy, final approval in this rehearsal is signed fixture only, never Owner UAT.

EVIDENCE: `docs/NATIVE_STORYBOARD_FULL_QC.md`, `docs/north-star/native-storyboard-full-qc-evidence.json`; 27 hashed exports in external `recovery/20261007/native-storyboard-full-qc-n4`, owned `C:/vf-native-fixture-storyboard-qc-04` and restore `C:/vf-native-fixture-storyboard-qc-restore-04`; separate-process replay. Earlier n1 shot-alias-conflict, n2 wrong preview response key and n3 nonexistent standalone job GET assumptions were rehearsal defects, corrected to actual existing APIs without product relaxation. All earlier roots/logs retained. No accepted video replaced.

REGRESSIONS: full Native and actual worker/recovery pass; fresh 15 accepted/live verification follows preservation. EXTERNAL BLOCKERS: genuine provider/quality/legal/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: measured scene voice preparation and audible preview/canonical duration/human review over the existing locked voice engine/cache, then remaining original Mode A/B/Vision/Trend/publishing/analytics/learning/Hub/hardening/A/B/C. No main merge/live migration/new paid budget/real publication/deployment.


### Wave 6B / 3 / 8 — Native measured scene narration preparation

WAVE: 6B / 2 / 3 / 8. STATUS: IN PROGRESS. MODE A READY = NO; MODE B READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `c9b0624b48602eb6e4d8a855dff53cf78dc91651`, pushed/preserved in `north-star-native-storyboard-full-qc.bundle`, SHA256 `ddc9ff1c2301df794f34a085fa87a932e3a1692cb879a8f09da92eb5e9d04572`; 195 ahead/0 behind. Narration increment receives separate commit/push/full-history bundle and fresh 15 accepted/live-source verification.

CAPABILITIES COMPLETED: separate approved canonical narration job using existing worker/TTS child/cache/checkpoints; immutable actual PCM/scene/approval/document/canonical/profile/policy plans; measured sample intervals and intro/outro recommendations; exact scoped history/audio; acknowledgement/CAS/hash/fit-template/current-source guarded one-transaction shared canonical duration apply and approval clearing; current voice-input fingerprint and physical checkpoint verified original-PCM final reuse with source proof in checkpoints; sample-index timestamp mapping; source-mode exclusion, project scope, duplicate authority removal, corruption/CSRF/RBAC guards; literal-text Studio audio/timing review, exact-key manual uncertain-response retry and late response rejection. Preparation performs no edit/render, apply no provider call, reuse no inference.

CAPABILITIES PARTIAL: combined audible preview/current-preview approval, genuine scene voice quality and new-flow local inference, provider-neutral languages/styles, full original Mode A/B/Vision/Trend/publishing/analytics/winner/learning/Hub/hardening/A/B/C plus browser/Owner/provider/production acceptance remain.

TESTS: full Native 642 PASS/522.686s; full Studio 238 PASS/1244.8678ms; affected narration/shot/quality/full-QC 39 PASS/61.221s. Eight new core, four HTTP, six DOM cases. Earlier logs retained: r1 new function import shadowed request SHA, corrected alias; r2 float literal equality and Store-vs-shot-view fixture comparisons corrected; r3 meaningful final-render boundary inversion fixed by mapping actual PCM sample indices; HTTP 26 run had only old exact-capability expectation failure, updated explicit advertised capability; initial DOM test had a fixture brace typo, corrected. Final full suites include all corrections. Latest Linux API 2659 PASS/11 SKIP/1512.89s unchanged, no API implementation changes or unnecessary repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: cached synthetic tone TTS, signed human credentials, authored content and runtime verification are explicit fixtures. LOCAL-REAL TESTS: technology channel, 51 actual human HTTP calls, image/video ingestion, MediaPlan/canonical apply, native narration claim/finish, immutable measured plan and actual served WAV, explicit timing apply and approval clearing/reapproval, original-PCM reused 1080x1920/30fps/3.3s FFmpeg/full QC/masks, real frozen-video failed_qc, actual backup/restore and exact new-process source/restored narration/render checkpoint replay. Zero paid/provider operations, no manually injected final video/QC. Silent proxy remains unsuitable for combined audible-preview acceptance; approvals are signed fixtures and never Owner UAT.

EVIDENCE: `docs/NATIVE_SCENE_NARRATION_PREPARATION.md`, `docs/north-star/native-narration-preparation-evidence.json`; 32 hashed exports in external `recovery/20261007/native-narration-preparation-n1`, owned `C:/vf-native-fixture-storyboard-qc-narration-01` and restore `C:/vf-native-fixture-storyboard-qc-narration-restore-01`; exact separate-process replay and logs. Prior QC/source/media/accepted video evidence remains untouched.

REGRESSIONS: full Native/Studio and worker/recovery pass; fresh 15 accepted/live verification follows preservation. EXTERNAL BLOCKERS: genuine provider/speech/legal/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: combined audible storyboard preview and current-preview human approval, followed by genuine existing local model tests and remaining original Mode A/B/Vision/Trend/publishing/analytics/learning/Hub/hardening/A/B/C. No main merge/live migration/new paid budget/real publishing/deployment.


### Wave 6B / 3 / 8 — Combined narrated storyboard preview and scoped approval

WAVE: 6B / 2 / 3 / 8. STATUS: IN PROGRESS. MODE A READY = NO; MODE B READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `c1db6aaf3f594f6091d3f1ca47ab44197a694bac`, pushed/preserved in `north-star-native-narration-preparation.bundle`, SHA256 `39848f3bd37574201bc302f6c61927311d78c3ed3537157da6a8366e446b2f07`; 196 ahead/0 behind. This increment receives separate commit/push/full-history bundle and fresh 15 accepted/live-source verification.

CAPABILITIES COMPLETED: actual prepared-PCM combined audible storyboard preview using the same canonical subtitle/crop/motion/music/mix effects and full media QC/libass pixels; separate preview authorization with no final/inference/publish authority; scoped immutable output/manifest/reports/mask/source hashes; corruption/current edit/stale rejection; human narration-only approval cannot render; production approval binds current audible preview and exact document/canonical/source plan/audio; guarded final admission and new rendering; unchanged historical verified checkpoint replay after later edits; Studio preview labels and asynchronous production-approval readiness; narration-only final controls suppressed. No automatically dispatched job, synthesis or publish.

CAPABILITIES PARTIAL: genuine local inference/speech quality for the combined workflow, guided default new-project path, provider-neutral languages/styles, semantic Vision and remaining original Mode A/B/Trend/publishing/analytics/winner/learning/Hub/hardening/A/B/C; browser/non-developer/Owner/provider/production acceptance.

TESTS: full Native 648 PASS/539.58s; full Studio 241 PASS/1474.9825ms; affected Native 28 PASS/97.457s and Studio 25 PASS/129.481ms. Six new actual-media/authority/corruption/stale/cancel cases and three new DOM cases. Earlier r1 UI copy expectation failed because timing instructions omitted reapproval; corrected actual copy and retained log. Initial reviewed-preview absent-folder exception corrected to explicit workflow error; nested SQLite approval lookup avoided with the same transaction. Historical replay remains ahead of live-current final authorization validation. Latest Linux API 2659 PASS/11 SKIP/1512.89s unchanged; no API implementation edits or unnecessary repeat.

REAL PROVIDER TESTS: 0. MOCK TESTS: cached synthetic PCM, authored content, signed human identity and runtime verification. LOCAL-REAL TESTS: 147 actual human HTTP calls, technology ingestion/MediaPlan/canonical apply, narration worker, explicit measured timing apply, actual audible 1080x1920/30fps/3.3s preview/full QC/masks, exact production approval, original PCM final reuse/full QC, real frozen-video preview failed_qc report and blocked approval/render admission, actual backup/restore and new-process exact source/restored checkpoint replay. Frozen negative has no terminal render job; admission is blocked. Zero paid/provider operations, no manually injected preview/final/QC. No genuine voice/semantic Vision/legal/browser/Owner acceptance inferred.

EVIDENCE: `docs/NATIVE_NARRATED_STORYBOARD_PREVIEW.md`, `docs/north-star/native-narrated-preview-evidence.json`; 38 hashed exports in external `recovery/20261007/native-narrated-preview-n1`, owned `C:/vf-native-fixture-storyboard-qc-narrated-preview-01` and restore `C:/vf-native-fixture-storyboard-qc-narrated-preview-restore-01`; exact separate-process replay and retained logs. Prior accepted and repaired review videos untouched.

REGRESSIONS: full Native/Studio and actual worker/recovery pass; fresh 15 accepted/live verification follows preservation. EXTERNAL BLOCKERS: genuine provider/speech/legal/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe work. NEXT WAVE: genuine existing local locked-model narrated workflow and guided project defaults, then all original Mode A/B/Vision/Trend/publishing/analytics/learning/Hub/hardening/A/B/C. No main merge/live migration/new paid budget/real publishing/deployment.


### Wave 6B / 3 / 8 — Guided project review and actual installed local narration

WAVE: 6B / 2 / 3 / 8. STATUS: IN PROGRESS. MODE A READY = NO; MODE B READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.

HEAD SHA: parent `cecf6652be9c66ca31a90edb577622fd889519c9`, pushed/preserved in `north-star-native-narrated-preview.bundle`, SHA256 `98beab24520df9b686446e2e682f9ff21c8e945a681c4cb40e3e0eda200fe8b9`; 197 ahead/0 behind. This increment receives separate commit/push/full-history bundle and fresh 15 accepted/live-source verification.

CAPABILITIES COMPLETED: strict versioned guided creation preferences for direct projects and approved-idea imports; first saved/completed script persists one canonical snapshot and projections in the existing transaction without arbitrary edit/read-side mutation; legacy/source paths preserved; production approval/new rendering require measured narrator/current audible preview; frozen brief retry cannot change initial policies; duplicate review authority does not carry; explicit next-step/approval/render copy; actual installed scene-context local TTS without warm paid-ASR policy or external credentials; SDK/model lock checks before/after, no download; original PCM preview/final reuse and separate-process verified replay.

CAPABILITIES PARTIAL: provider-neutral voice/language/style, genuine pronunciation/intelligibility/Owner/browser acceptance, semantic Vision and full original Mode A/B/Trend/publishing/analytics/winner/learning/Hub/hardening/A/B/C and production infrastructure acceptance.

TESTS: full Native 656 PASS/529.006s; final full Studio 243 PASS/1107.108ms; eight new Native cases PASS/7.724s and two new DOM cases. Earlier affected 52 run had two fixture defects (unsaved canonical and Store-vs-shot-view comparison); corrected fixtures, retained failures. Seven-case rerun had remaining Store response comparison; corrected. The saved-script gap identified during review was fixed in the actual shared canonical transaction and tested without arbitrary edits. Final full suite includes these changes. First genuine n1 succeeded against prior source; final n2 is fresh against final source, both preserved. Latest Linux API 2659 PASS/11 SKIP/1512.89s unchanged; no API implementation edits or repeat.

REAL PROVIDER TESTS: actual installed local VieNeu/locked SDK scene inference (2 calls), separate from external provider tests (0). MOCK TESTS: authored technology content, owned synthetic image/frozen-video and signed human credentials; no synthetic voice substitution in final n2. LOCAL-REAL TESTS: 93 actual human HTTP calls, source ingestion/MediaPlan/canonical edits, native narration worker/child, 7.32s actual PCM, three canonical proper names in script, explicit timing apply, actual audible preview/full QC, exact production approval, 9.433s 1080x1920/30fps final PCM reuse/FullQC/three libass subtitle masks, actual frozen-preview failure and blocked final admission, actual backup/restore and new-process exact source/restored checkpoints with no new inference. Zero paid/external calls. Human speech/pronunciation/Owner/word alignment/semantic Vision/licensing/browser acceptance remain false or unverified.

EVIDENCE: `docs/NATIVE_GUIDED_NARRATION_WORKFLOW.md`, `docs/north-star/native-guided-narration-evidence.json`; 41 hashed exports in external `recovery/20261007/native-guided-real-narration-n2`, owned `C:/vf-native-fixture-storyboard-qc-real-narration-02` and restore `C:/vf-native-fixture-storyboard-qc-real-narration-restore-02`; genuine earlier n1 and failures retained. No accepted video or model/SDK file replaced.

REGRESSIONS: full Native/Studio, actual local worker/QC/runtime/recovery pass; fresh 15 accepted/live verification follows preservation. EXTERNAL BLOCKERS: real remote provider/speech/semantic/legal/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for remaining safe work. NEXT WAVE: integrate original first-class Trend Radar/channel-history opportunity flow with Native production and continue all original Mode A/B/Vision/distribution/analytics/learning/Hub/hardening/A/B/C. No main merge/live migration/new paid budget/real publishing/deployment.


### Wave 13 / 12 / 9 / 8 — Native first-class Trend Radar and frozen feedback

WAVE: 13 / 12 / 9 / 8. STATUS: IN PROGRESS. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.

HEAD SHA: parent `19244fb463895dd9b4713eaa3ff3040b1cefff81`, already pushed/preserved in `north-star-native-guided-narration.bundle`, SHA256 `cedf6d172dd3e587dda324ee1db909d4432bbecfebbcd93a6071f328c230aba1`; 198 ahead/0 behind. This increment receives its separate commit/push/bundle and fresh accepted/live-source verification.

CAPABILITIES COMPLETED: scoped append-only Native normalized signal/provider/cluster/assessment/handoff/learning evidence; explicit configured/fixture collection, cached receipts, bounded provider timeout, atomic claims/cancel/no interrupted automatic replay; public HTTPS RSS/Atom registry/wire contract; configurable explained similarity/lifecycle/weighted estimates; eight Studio Radar views and role/auth guards; exact frozen research-to-idea-to-project context and channel/trend render features; compatible latest distinct fixture-history minimum-group/control learning and recommendation-only ranking; bridge estimated trend events; full storyboard QC measured-platform projection without weakening generated-voice rights.

CAPABILITIES PARTIAL: authorized real social/search/RSS/embedding sources and calibrated longitudinal trends; official channel/account analytics and relative winner history; generated voice/model legal provenance; browser/non-developer/Owner acceptance; semantic Vision, full original Mode A/B, provider acceptance, production infrastructure and final A/B/C.

TESTS: full Native 674 PASS/508.604s; final full Studio 249 PASS/1001.3953ms; affected Native 51 PASS/40.434s, 18 new Native and six new DOM cases. Existing four API Radar tests were accidentally replaced by a new same-name file, detected from the full suite count, restored byte-exactly from HEAD, and the new tests moved to `native-trend-radar.test.mjs`; final 249 includes both sets. Earlier fixture/query, revision seeding, factor-coverage and asynchronous DOM failures are retained; guards were preserved. Linux API 2659 PASS/11 SKIP/1512.89s unchanged; no API implementation changes.

REAL PROVIDER TESTS: two actual installed locked local VieNeu scene inferences, 7.32s original PCM; zero external provider/paid operations. MOCK TESTS: explicit trend/research/idea fixtures, authored geometric images/script, signed fixture legal/human approvals, six-publication learning unit fixture. LOCAL-REAL TESTS: 118 signed HTTP calls, frozen Radar/channel lineage, actual narration/canonical timing/current audible preview/production approval/9.433s 1080x1920 30fps final original-PCM reuse/full FFmpeg/libass QC/three subtitle masks/frozen-preview rejection; actual two-database/source backup, restore and separate-process exact checkpoint replay without new inference. Generated voice provenance blocks dry-run approval; platform/image-exception checks pass; no publication, analytics snapshot or winner worker result exists. Official analytics returns NOT_CONFIGURED/zero attempts; learning remains zero observations/insufficient data. Independent Hub harvest five events, duplicate zero, external zero.

EVIDENCE: `docs/NATIVE_TREND_RADAR.md`, `docs/north-star/native-trend-radar-evidence.json`; final 56 hashed exports in external `recovery/20261007/native-trend-radar-flow-n3`, owned `C:/vf-native-fixture-storyboard-qc-trend-03`, restore `C:/vf-native-fixture-storyboard-qc-trend-restore-03`. n1/n2 failure bundles and all logs retained. All 44 rehearsal source hashes/56 exports independently rechecked. No accepted artifact/model/SDK bytes replaced.

REGRESSIONS: full Native/Studio and actual queue/media/QC/recovery pass; fresh accepted/live verification follows preservation. EXTERNAL BLOCKERS: authorized real sources/account/provider/semantic/legal/speech/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; optional speech listening deferred by Owner. NEXT WAVE: exact scoped generated-narration provenance review and narrated distribution dry-run, then remaining original North Star capabilities. No protected-main merge/live migration/new paid budget/real publishing/deployment.


### Wave 5B / 6B / 9–12 / 8 — Exact generated narration publication review

WAVE: 5B / 6B / 9–12 / 8. STATUS: IN PROGRESS. MODE A READY = NO; MODE B READY = NO; IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.

HEAD SHA: parent `358a1186c66939f2a8b459d0af5439debfd1b740`, pushed/preserved in `north-star-native-trend-radar.bundle`, SHA256 `d85f5cbea272b2adac85b59358adb10b75f0a0a20ca5540329ca33510c30ee89`; 199 ahead/0 behind. This increment receives separate commit/push/bundle and fresh 15 accepted/live-source verification.

CAPABILITIES COMPLETED: strict default-disabled Owner-only narration/model provenance exceptions; exact source job/plan/PCM/profile/manifest/metadata binding, attributed license labels/raw rights unknown, TTL/revoke/durable exact retries/version/event history; no browser enablement/actor spoof/source schema substitution; grants/revoke clear approval without canonical/media changes; copies drop preparation/authority; UI source/evidence/reason/TTL/separate review controls and stale/lost-response guards; publishing exact frozen/current exception and final TTS/render/original PCM/reuse/rendered-wave verification; fresh preview/production/final/publish approval remain separate; actual narrated dry-run with synthetic analytics/absolute-normal and one compatible frozen learning observation; revoke blocks pending approval, historical observation unchanged; backup/restore explicitly includes distribution/analytics/exception receipt rows and both databases.

CAPABILITIES PARTIAL: legal/model/preset/music/speech/pronunciation/browser/non-developer/Owner acceptance; official Native live/read account integration, TikTok/Meta durable runtime/credential custody, real channel cohorts/history/winners, semantic Vision, narrated variants, audio loop/loudness technical gaps and full original Mode A/B/Hub/hardening/A/B/C acceptance.

TESTS: full Native 686 PASS/521.507s; full Studio 254 PASS/1015.4109ms; focused Native 36 PASS/40.692s, 12 new Native and five new DOM cases. First focused run retained one empty foreign-project prompt fixture error; second retained a helper dereferencing intentionally missing current provenance during a profile-change test. Corrected fixtures and reused explicit prepared request; all guards preserved. An imported TestCase initially duplicated eight pre-existing cases in the focused count; module-qualified fixture reuse removes the duplicate. Latest Linux API 2659 PASS/11 SKIP/1512.89s unchanged; no API implementation changes.

REAL PROVIDER TESTS: two genuine installed locked local VieNeu scene calls/7.32s PCM; zero external/paid operations. MOCK TESTS: market/research/idea/authored images/script and signed legal/human exceptions/approvals, dry-run publication, explicit fixture normal metrics and absolute assessment. LOCAL-REAL TESTS: 141 signed HTTP, original model/SDK before/after hashes, actual canonical timing/current audible preview/production approval/final PCM reuse/9.433s 1080x1920 30fps FullQC/three libass subtitle masks, frozen-preview hard rejection, exact narration exception retries/revoke and actual copied project without authority, actual both-database backup/restore/new-process checkpoint replay without new inference. One synthetic analytics observation is not real audience history; learning remains insufficient/no adjustment. Official analytics is NOT_CONFIGURED/zero attempts. Five independent bridge events, duplicate zero/external zero.

EVIDENCE: `docs/NATIVE_NARRATION_PUBLICATION_PROVENANCE.md`, `docs/north-star/native-narration-rights-evidence.json`; 67 hashed exports in external `recovery/20261007/native-narration-rights-flow-n1`; owned `C:/vf-native-fixture-storyboard-qc-voice-rights-01` and restore `C:/vf-native-fixture-storyboard-qc-voice-rights-restore-01`; 52 rehearsal source hashes verified. Prior blocked Trend bundle and all failure logs retained. No accepted video/model/SDK replacement.

REGRESSIONS: full Native/Studio and actual queue/media/QC/distribution/history/recovery pass; fresh accepted/live verification follows preservation. EXTERNAL BLOCKERS: legal/speech/Owner/real account/provider/semantic/browser/deployment acceptance. OWNER ACTION REQUIRED: none for safe implementation; optional sample review deferred. NEXT WAVE: close audio loop seam/measured loudness and remaining narrated variants/analytics/runtime/provider/Hub/hardening/full E2E gaps. No main merge/live migration/new paid budget/real publication/deployment.


### Wave 5B / 6C / 6D / 6E / 8 — Canonical music crossfades and measured output loudness

WAVE: 5B / 6C / 6D / 6E / 8. STATUS: IN PROGRESS. HEAD SHA: parent `2e8b4ac864e10612c65d30a78371be25d51c287f`, preserved remote branch 200 ahead/0 behind; new milestone receives its own commit/push/bundle/fresh accepted-source verification.

CAPABILITIES COMPLETED: bounded opt-in Source loop overlap/fades on the same canonical timeline; legacy zero behavior, edit/restore/approval/locked-track limits; Studio capability and Source guards with localized errors; actual hash-bound final LUFS/true peak/range/threshold receipts in Source and narrated full QC; scan/time/result/input-change errors become failed_qc; silent measurements null and no target/speech/balance assertion; exact physical .music.wav rights models/routes/RBAC/Studio; unknown/restricted declarations, separate default-disabled scoped exception, expiry/revoke/exact retries/copy isolation and physical/canonical preservation; both-database/music/narration checkpoint recovery.

CAPABILITIES PARTIAL: narrated loop crossfades/master variants; measured music BPM/mood/energy; speech/voice/music perceptual acceptance; actual licensing/Owner/non-developer/browser/provider/semantic/official Native publishing/analytics/cohort/production acceptance. Original Mode A/B and full A/B/C remain incomplete.

TESTS: full Native 699 PASS/508.54s; full Studio 258 PASS/1119.3069ms, 13 new Native/four new DOM cases. Focused Native 29 PASS before final additional input-binding/parser/storyboard failure guards, focused Studio 13 PASS. Prior unchanged Linux API 2659 PASS/11 SKIP/1512.89s; API implementation unchanged. Studio full rerun follows localized music-error messages; both runs retained.

REAL PROVIDER TESTS: two genuine installed locked local VieNeu scene inferences, model/SDK unchanged, no model download/external/paid call. MOCK TESTS: Source synthetic picture/tone/saved ASR and signed human/legal decisions; no real speech recognition/licensing or Owner UAT. LOCAL-REAL TESTS: portrait Source linked trim/split/karaoke/music crossfade/normalization/ducking/current full-effects preview/final same PCM and full QC; measured Source output -15.73 LUFS/-12.66 dBFS true peak. Genuine narration 93 signed HTTP/current audible preview/FullQC/frozen-preview failed_qc/backup/restore/new-process reuse. Music 13 signed HTTP/declaration and exception exact retries/revoke after disabling/copied-project authority isolation/immutable PCM/canonical/both-database backup/restore/new-process historical replay, no new render.

EVIDENCE: `docs/NATIVE_MUSIC_CROSSFADE_LOUDNESS.md`, `docs/north-star/native-audio-quality-evidence.json`; external `recovery/20261007/native-music-crossfade-flow-n2`, `native-music-review-flow-n1`, `native-audio-quality-narration-n2`. Earlier n1 rehearsals retained; final-source n2 verifies the added physical input/QC binding and localized UI messages. All indexed exports and rehearsal source hashes verified before index. No accepted artifact replacement.

REGRESSIONS: full Native/Studio and actual media/approval/QC/rights/history/recovery pass; fresh accepted/live-source verification follows preservation. EXTERNAL BLOCKERS: actual provider/semantic/legal/speech/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; optional listening review remains deferred. NEXT WAVE: narrated master variants/audio path and remaining analytics/runtime/provider/Hub/hardening/final acceptance. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO. No main merge/live migration/new paid budget/real publication/deployment.


### Wave 10 — Native saved-history Analytics plots and comparison

WAVE: 10. STATUS: IN PROGRESS. HEAD SHA: parent `0fa21bfa2aade6de38fb8089c39f87c278b57aa2`, pushed/preserved 201 ahead/0 behind in `north-star-native-audio-quality.bundle`, SHA256 `aab25c4bc6ea8dc9d49926b006319665dab7c2c69a5f97d9a4d3c8de0e006a08`; fresh prior preservation verified 15 accepted artifacts/live source. This increment receives separate commit/push/bundle and fresh verification.

CAPABILITIES COMPLETED: all 15 normalized metrics selectable; scoped saved-history SVG plots, null gaps/known zero/all-null absence, literal accessible labels/raw IDs/semantic comparison table; series split by publication/platform/provenance, latest-two distinct times/known values only, zero/nonfinite denominator safeguards, percent/percentage points/seconds/VND/RPM, bounded loaded history/12 drawn video series and visible pagination scope; no sum/account/cohort/velocity/winner/automatic-action inference. Metric redraw makes no provider request; project switch clears charts. Contained narrow-panel scrolling and full currency-axis digits verified. Actual restored fixture history/readonly project/media preservation and backup, direct response-to-component SVG/HTML/model/PNG evidence.

CAPABILITIES PARTIAL: official Native credentials/account/read runtime/recurring sync/accepted AnalyticsProfile; genuine channel cohorts/history/relative winner/learning; browser/non-developer/Owner viewport acceptance; full original modes/semantic/provider/integration/hardening/A/B/C/deployment. Data are explicit fixture scenarios, not audience trajectory.

TESTS: full Studio 268 PASS/1105.2995ms, ten new DOM cases; affected Native analytics/HTTP/Phase 10 26 PASS/22.039s. Backend runtime unchanged; last full Native 699 PASS/508.540s and Linux API 2659 PASS/11 SKIP/1512.89s remain valid prior checks. First integration fixture omitted external-call marker and correctly failed provenance validation. First retained HTTP helper incorrectly expected snapshot key on create; now accepts absent snapshot. Initial component assumption of all-null revenue corrected against actual winner fixture's declared value, preserving three unknowns and an explicitly scoped all-null subset. Raster inspection exposed clipped leading revenue digit; moved units to heading/widened margin, full Studio rerun/current-source n4 render/raster inspection confirms complete value. Earlier logs/roots/outputs retained; guards unchanged.

REAL PROVIDER TESTS: none new; official Native NOT_CONFIGURED/zero attempts/no metrics substituted. MOCK TESTS: three acknowledged fixture profiles append to one prior fixture publication, four total observations; same saved responses feed the real chart functions. LOCAL-REAL TESTS: 14 signed HTTP, original snapshot/project/jobs/physical media unchanged, actual checksum restore/backup, scoped page/workspace overview, four SVG/models/PNG and all-null subset, literal Vietnamese typography/gap/full revenue digits inspected. Zero TTS/render/external/paid operations; no real audience/non-developer/Owner/browser acceptance.

EVIDENCE: `docs/NATIVE_ANALYTICS_VISUALS.md`, `docs/north-star/native-analytics-visuals-evidence.json`; external `recovery/20261007/native-analytics-visuals-flow-n4`, owned `C:/vf-native-fixture-analytics-visuals-04`. All source/export/component hashes verified. REGRESSIONS: Studio/affected Native and actual historical/physical guards pass, fresh accepted/live verification follows preservation. EXTERNAL BLOCKERS: actual account/provider/cohort/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; speech review remains deferred. NEXT WAVE: original remaining recurring analytics/profile/provider, narrated variants/audio, authorized durable publication/credential/operator paths, semantic/Hub/isolation/hardening/final acceptance. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 10 / 7 — Native bounded recurring analytics and runtime AnalyticsProfile

WAVE: 10 / 7. STATUS: IN PROGRESS. HEAD SHA: parent `429ddf517691428e53dbbc49532efb5fe798f224`, pushed/preserved 202 ahead/0 behind in `north-star-native-analytics-visuals.bundle`, SHA256 `9779d2b02b42d13c64229a90e0b9d09fca06e50f31e975ccf0b77cab5f9b199f`; fresh prior preservation verified all 15 accepted artifacts/live source. This increment receives separate commit/push/bundle and fresh verification.

CAPABILITIES COMPLETED: pure shared provider-neutral report-policy model; Native default-off bounded recurring plans/versioned frozen runtime AnalyticsProfile and unchanged channel base; signed Owner/read-only/fixture gates, strict aware schedule/integer bounds, exact-key idempotency/CAS state changes, scoped cursor pages/occurrences/events, atomic occurrence/existing-sync creation, single worker due admission, no missed-slot burst or overlapping pending retry, finite runs, final occurrence admission, cancellation/revision fence at every restart, immutable historical snapshots/frozen features, existing backoff/winner/recommendation-only consumers. Studio Vietnamese capability-gated policy review/create/enable/disable/tick/limits/acknowledgment/stale/provenance guards. Backup includes all new tables and exact restore/restart.

CAPABILITIES PARTIAL: official Native account/token/query/read runtime and provider acceptance; real audience/channel cohorts/relative winner/learning, browser/non-developer/Owner acceptance; narrated variants and remaining original full Mode A/B/media/distribution/Hub/hardening/final A/B/C. Official plans are saved NOT_CONFIGURED and cannot be enabled or substituted with fixtures.

TESTS: full Native 713 PASS/530.623s (14 new Native contract/HTTP), full Studio 273 PASS/1172.6025ms (5 new DOM). API runtime code unchanged; prior Linux API 2659 PASS/11 SKIP/1512.89s remains prior verification. First binding-corruption fixture exposed invalid receipt handling; scheduler now blocks affected plan safely while retaining fail-closed guards. Initial detail DOM fixture returned page rather than required plan; corrected fixture. Initial focused HTTP process started before capability flag edit and failed that flag assertion; current full suite covers final source. First actual restore failed Windows staging rename before analytics; retained log/staging, fresh n2 checksum restore passed with unchanged safety checks.

REAL PROVIDER TESTS: none new; official NOT_CONFIGURED/zero jobs. MOCK TESTS: acknowledged normal/rate-limit observations and explicit simulated schedule clock; two new snapshots, no audience trajectory. LOCAL-REAL TESTS: 29 signed HTTP; frozen `ai-education-reference@1` base stays disabled; eight missed slots skipped; pending retry cancelled; three bounded retry attempts; existing project/jobs/physical media and four old snapshots exact; full both-DB row counts/backup/restore/new-process replay, no new work after reopen. Zero TTS/render/external/paid operations; no real publication/Owner/speech/legal/browser/production acceptance.

EVIDENCE: `docs/NATIVE_RECURRING_ANALYTICS.md`, `docs/north-star/native-analytics-refresh-evidence.json`; external `recovery/20261007/native-analytics-refresh-flow-n2`, owned `C:/vf-native-fixture-analytics-refresh-02` and `C:/vf-native-fixture-analytics-refresh-restore-02`. All source/export hashes verified. REGRESSIONS: full Native/Studio/current history/physical guards pass; fresh accepted/live verification follows preservation. EXTERNAL BLOCKERS: actual account/provider/audience/cohort/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe continuation; listening review deferred. NEXT WAVE: original narrated master variants/audio and durable authorized official publication/analytics/credential runtime, semantic/provider/Hub/isolation/hardening/final acceptance. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 7 — Narrated four-canvas render foundation

WAVE: 7. STATUS: IN PROGRESS. HEAD SHA: parent `1a1d77eda758a0e9b8727f3307cf437e15a60c6a`, pushed/preserved 203 ahead/0 behind in `north-star-native-analytics-refresh.bundle`, SHA256 `0f38538f55076e952ebff2c9bb28498b5405ac29b27eabaf10b917dae15f2b23`; fresh prior preservation verified all 15 accepted artifacts/live source. This increment receives separate commit/push/bundle and fresh verification.

CAPABILITIES COMPLETED: exact 9:16/16:9/1:1/4:5 template dimensions, opt-in catalog retaining 15/default and 30/landscape forms, original portrait/landscape geometry, bounded compact margins/even media planes/title/illustration/footer/caption regions, compact editable-plan guard, unchanged hard vertical/profile validation, actual ASS resolution/effective font and correctly labelled square/feed transport QC, existing canonical source/Full QC/subtitle pixel bounds and historical checkpoint behavior. Four local MP4s/decoded frames/manifests/timelines/ASS/PCM/audio/full QC/eight mask evidence retained and inspected.

CAPABILITIES PARTIAL: narrated master family creation/UI, verified cross-project prepared PCM/reference/cache reuse and fresh per-child preview/approval/provenance; Source Mode B family remains independently implemented. Genuine speech/semantic/rights/provider/browser/non-developer/Owner/mode A/B and full final acceptance remain.

TESTS: full Native 717 PASS/529.556s, four new cases including actual square/feed render/QC. Earlier focused new 4 PASS/6.814s and existing branding/storyboard QC 18 PASS/23.914s; final full suite includes final correct QC-label change. Frontend unchanged, prior full Studio 273 PASS/1172.6025ms; API runtime unchanged, prior Linux 2659 PASS/11 SKIP. No test/approval gate removed.

REAL PROVIDER TESTS: none. MOCK TESTS: declared synthetic image/tone PCM/approval fixtures, no real speech claim. LOCAL-REAL TESTS: four format renders at exact declared dimensions, original PCM hash retained, Full QC/two actual libass masks per render, measured final loudness/decode/A/V/hash evidence and all four decoded frames inspected. n1 retained; n2 adds decoded-frame evidence. Zero provider inference/external/paid operation; no real publication/deployment/Owner UAT.

EVIDENCE: `docs/NATIVE_NARRATED_CANVAS_GEOMETRY.md`, `docs/north-star/native-narrated-canvas-evidence.json`; external `recovery/20261007/native-narrated-canvas-flow-n2`, owned `C:/vf-native-fixture-narrated-canvas-02`. All source/export hashes verified. REGRESSIONS: full Native/old geometry/catalog/quality guards pass; fresh accepted/live verification follows preservation. EXTERNAL BLOCKERS: genuine voice/semantic/account/provider/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe continuation; listening review deferred. NEXT WAVE: narrated master family/verified prepared narration derivation/individual fresh approvals and remaining official runtime/provider/Hub/hardening/final acceptance. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 7 — Narrated six-format families and verified original narration reuse

WAVE: 7. STATUS: IN PROGRESS. HEAD SHA: parent `be237b59da075b0faccafc2b1dbea3e053bf84f1`, pushed/preserved 204 ahead/0 behind in `north-star-native-narrated-canvas.bundle`, SHA256 `56f7c1e805b68a721ce0bc05e1d91cc4855f99a1e15120807755486dd7d2fe87`. This increment receives separate commit/push/bundle and fresh accepted/live verification.

CAPABILITIES COMPLETED: atomic scoped typed narrated families/six format drafts; immutable master/child/catalog/canonical snapshots; original narration project/job/approval/plan/PCM/input/checkpoint proof, nested source resolution, no new inference, per-child fresh audible preview/production/final review; cleared inherited approval/rights/planner authority, exact-key/concurrent replay/failed-child rollback and cursor/restart guards; signed editor/CSRF/viewer history and exact derived audio, authenticating original/derived reads; derived plan retains source identity/reuse and rights receipts identify original source; Studio explicit select/create/history/open/audio/permission/stale controls; app JSON adapter accepts existing plain-body and POST-options panel conventions without leaking method/credential control. Additive backup table and both-DB/media recovery pass.

CAPABILITIES PARTIAL: remaining channel/brand/subtitle/voice/CTA preferences, generated/render intermediate caches, narrated audio loop path; official Native account/token/publishing/analytics runtime and real cohorts; genuine speech/semantic/legal/provider/browser/non-developer/Owner/production and full original Mode A/B/A-B-C acceptance.

TESTS: full Native 732 PASS/571.264s (15 new Native), full Studio 278 PASS (five new DOM). Earlier focused 17 Native and 12 DOM pass; additional atomic/nested cases covered by final full suite. API runtime unchanged; prior Linux 2659 PASS/11 SKIP remains prior verification. Initial nested unit fixture used unknown profile name; corrected to existing catalog ref, final full regression passes. No test/approval/QC gate is removed.

REAL PROVIDER TESTS: no new inference. LOCAL-REAL TESTS: six actual audible previews/finals/FullQC/four canvases/unchanged previously generated genuine local locked narration PCM; 270 signed HTTP, immutable master/source files, actual ASS masks/manifests/decoded frames/cost/event/provenance, both-DB row counts/backup/restore/fresh-process proof, zero new jobs/inference after reopen. MOCK TESTS: authored synthetic visual and signed approval fixtures, no speech/legal/Owner acceptance. Earlier n1–n4 roots/logs are retained: harness status/current-revision/export assumptions and genuine frozen-video QC rejection. Successful n5 restores the passed historical visual selection by explicit canonical edit in the isolated copy before freezing the new master; QC is unchanged.

EVIDENCE: `docs/NATIVE_NARRATED_VARIANTS.md`, `docs/north-star/native-narrated-variants-evidence.json`; `recovery/20261007/native-narrated-variants-flow-n5`, owned `C:/vf-native-fixture-narrated-variants-05` and `C:/vf-native-fixture-narrated-variants-restore-05`. All 173 rehearsal exports plus fresh-process proof verified. Runtime source hashes are exact; the one subsequent non-runtime nested-test catalog-ref correction is recorded separately with full final source fingerprints. Four decoded canvas frames inspected; no Owner listening/UAT inference.

REGRESSIONS: full Native/Studio/media/rights/scope/history/recovery pass; fresh 15 accepted/live verification follows preservation. EXTERNAL BLOCKERS: actual speech/legal/semantic/account/provider/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; optional listening review remains deferred. NEXT WAVE: original remaining narrated audio, authorized durable official Native publishing/analytics credential/account runtime, semantic providers/Hub/isolation/hardening/final E2E. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 6D/6E — Canonical narrated music overlaps and shared PCM proof

WAVE: 6D/6E. STATUS: IN PROGRESS. HEAD SHA: parent `a23457f443717a0e0329f88967f0ec5ba39f8b15`, pushed/preserved 205 ahead/0 behind in `north-star-native-narrated-variants.bundle`, SHA256 `c18e344bed8ce361f22757906d0197f1c129928bfc6c3c16565ca3ce7f4c18c6`. This increment receives separate commit/push/bundle and fresh accepted/live verification.

CAPABILITIES COMPLETED: distinct capability-gated narrated Studio music loop intake; actual decoded stereo PCM/hash/frame policy, repeat placement/source trim/brand volume/provenance and reversible fades in the same canonical timeline; bounded RMS/peak normalization, voice sidechain ducking/limiter, exact shared preview/final music stem and unchanged prepared voice without inference; source/policy/canonical/receipt/output verification, strict flags/nonfinite rejection, review/QC hard corruption failures, family source admission/atomic rollback; zero/default/source behavior retained; artifacts included in checkpoints, both databases/media backup/restore and fresh-process replay.

CAPABILITIES PARTIAL: narrated advanced audio clip/lock/mute UI, independent speech/perceptual balance, uploaded BPM/mood/energy, complete voices/languages/rights/browser/non-developer/Owner acceptance; authorized official Native account/token/publishing/analytics runtime, semantic media/trend/cohort observations, Hub/isolation/production/final Mode A/B/A-B-C acceptance.

TESTS: full Native 745 PASS/630.835s (13 new); full Studio 279 PASS/1.1306372s (one new). Focused ten PASS, expanded thirteen initially had one test reading the published instead of failed-attempt QC path; corrected assertion verifies retained failed-attempt output, single focused rerun and final full suite pass. Initial pilot TimelineTrack metadata shape and test timing/quality setup were corrected before final evidence; no product/QC gate was relaxed. Prior Linux API 2659 PASS/11 SKIP is unchanged prior verification, not rerun by this increment.

REAL PROVIDER TESTS: no new provider call. LOCAL-REAL TESTS: six actual audible previews/finals/FullQC on four canvases using previously generated genuine local voice PCM; 138 signed HTTP, one exact shared four-repeat music bed, actual 144000 source/452160 output PCM frames, no clipped samples, measured source RMS/peak/gain and final delivered loudness; unchanged original assets/prior media; canonical/ASS/FFprobe/mask/provenance/cost/events, both-DB backup/restore and six verified fresh-process music/voice/final fixture checkpoints with zero new jobs. MOCK TESTS: synthetic tone music/visuals and signed approval identities; speech, perceptual balance, rights and Owner acceptance remain false.

EVIDENCE: `docs/NATIVE_NARRATED_MUSIC_LOOPS.md`, `docs/north-star/native-narrated-music-evidence.json`; `recovery/20261007/native-narrated-music-flow-n1`, owned `C:/vf-native-fixture-narrated-music-01` and `C:/vf-native-fixture-narrated-music-restore-01`. All 181 rehearsal exports plus fresh-process proof verified; source hashes exact. Portrait/square decoded frames inspected. Existing accepted artifacts are not replaced.

REGRESSIONS: full Native/Studio/source/preview/render/QC/rights/scope/family/recovery pass; fresh 15 accepted/live checks follow preservation. EXTERNAL BLOCKERS: real speech/perceptual/legal/semantic/provider/account/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; optional listening review remains deferred. NEXT WAVE: authorized official Native credential/account/publishing/analytics runtime, narrated advanced audio/semantic/provider/cohort/Hub/isolation/hardening and final E2E acceptance. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Waves 8/9/10 — Native explicit official account review prerequisite

WAVE: 8/9/10. STATUS: IN PROGRESS. HEAD SHA: parent `c73724880455de197a2711b74d6972fe401e0ae4`, pushed/preserved 206 ahead/0 behind in `north-star-native-narrated-music.bundle`, SHA256 `c721dab8fac988f202e0f07fa733e1250974f3ab2e6c577df91ae6750e71f2be`. This increment receives a separate commit/push/bundle and fresh accepted/live checks.

CAPABILITIES COMPLETED: strict scoped account registry, absolute external domain-separated DPAPI token mount/private ACL and approved-resolver boundary; unchanged AssemblyAI defaults; default-off/no-startup secret or account read; fixed official YouTube/TikTok read-only account protocols; frozen target/root/configuration/client/wire/transport/resolver checked before/after response and final commit; signed Owner/manage/CSRF before body, strict acknowledgement/current saved idle project, idempotency and immutable project/configuration snapshot; durable read queue/response proof/cost intent with unknown costs null; foreign/expired/stale/tampered evidence rejection, uncertain-restart no automatic resend, scoped pagination; explicit capability-gated Studio configuration/check/history controls, no secret input or automatic request; check/event backup and active-operation admission, both-database/fresh-process recovery.

CAPABILITIES PARTIAL: official Native publication and analytics collection/receipt/runtime, protected OAuth acquisition/refresh/rotation, Meta Native coverage, authentic metrics/rights/credential/provider acceptance; narrated advanced audio and perceptual/speech acceptance; semantic media/trend/cohorts, Hub/isolation/production and original Mode A/B/final A-B-C/browser/non-developer/Owner acceptance.

TESTS: full Native 765 PASS/598.568s (20 new); full Studio 285 PASS/1.2290982s (six new). Integrated 40 PASS includes Phase 10 HTTP and AssemblyAI regression; strengthened account suite 20 PASS. Early focused test fixtures used nonexistent CostSummary/Store fields; corrected fixture assumptions before final passing suites, without weakening gates. Numeric-zero publishing flag acceptance was fixed with a strict before-validator. Prior Linux API 2659 PASS/11 SKIP is unchanged prior verification, not rerun.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual Windows DPAPI/domain/private-file handling, SQLite, 19 signed HTTP requests, both-database backup/restore, four account checks/eight audit events and fresh-process history/project/job/token replay, all 1280 prior media/artifacts unchanged. MOCK TESTS: two explicit YouTube/TikTok account responses, synthetic access tokens/identities and interrupted/expired fixtures; zero external provider/paid/new inference/render calls. Mock checks never enable publishing or become audience evidence. Unknown costs remain null.

EVIDENCE: `docs/NATIVE_OFFICIAL_ACCOUNT_REVIEW.md`, `docs/north-star/native-official-account-evidence.json`; `recovery/20261007/native-official-accounts-flow-n1`, owned `C:/vf-native-fixture-official-accounts-01`, `C:/vf-native-fixture-official-accounts-restore-01`; synthetic encrypted mounts remain separately in `C:/vf-native-fixture-official-accounts-secrets-01`. Backup SHA256 `dede897ae134b35e8a8da76d60d82184286dfc02ea512db9a9807692e1257e10`. Twenty retained exports plus fresh-process proof and exact source hashes verified. Existing accepted artifacts are not replaced.

REGRESSIONS: full Native/Studio/source/preview/render/QC/rights/scope/AssemblyAI/recovery pass; fresh 15 accepted/live checks follow preservation. EXTERNAL BLOCKERS: authentic provider secrets/account/legal/audience, browser/non-developer/Owner and production acceptance. OWNER ACTION REQUIRED: none for safe implementation; optional listening review remains deferred. NEXT WAVE: official Native publishing/analytics worker and protected credential integration, then original remaining semantic/audio/cohort/Hub/isolation/hardening and final E2E/Owner acceptance. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 9 — Native separate official publish consent and dispatch journal

WAVE: 9. STATUS: IN PROGRESS. HEAD SHA: parent `803960d5decc90f7fb72eaf76fb779018955580e`, pushed/preserved 207 ahead/0 behind in `north-star-native-official-accounts.bundle`, SHA256 `be17fccdb0c0190a912e917507d5c74b71b6e4d5abb9f7e4b36d34e8f1259d6b`. This increment receives separate commit/push/bundle and fresh accepted/live checks.

CAPABILITIES COMPLETED: typed scoped YouTube target/disclosures/chunking and strict default-off frozen publishing factory; no startup credential/provider read; current dry-run/account proof/project/revision/document/final checkpoint/hash/approval/rights/official platform revalidation; independent verified human Owner grant with current authoritative identity fingerprint, bounded expiry/revocation/role/not-before; durable immutable review/consent/event/prepared-dispatch records, exact-key replay, atomic concurrency, same-account/final-file duplicate guard per execution mode, unsent cancelled/unconfigured replacement with history retained; strict rehashed flags/size/fingerprint rejection and sanitized errors; cancellation revokes only unsent authority, begun dispatch requires reconciliation; four-table backup counts and pending admission, exact workflow-DB/fresh-process replay without configured credentials or dispatcher; pure-contract imports without API ORM/framework/crypto/GPU.

CAPABILITIES PARTIAL: official Native upload worker, encrypted resumable-session persistence, protected publishing OAuth acquisition/refresh/rotation, scheduling/reconciliation/processing/privacy receipts, signed HTTP/Studio integration, other platform Native runtimes/thumbnails, authentic rights/account/platform/provider/Owner acceptance; official Native analytics/audience/cohorts and all original remaining Mode A/B/media/audio/trend/learning/Hub/isolation/hardening/final E2E acceptance.

TESTS: full Native 785 PASS/614.12s (20 new); related consent/account/registry/dry-run/backup suite 63 PASS/20.631s before one added invalid-size case, which is covered by final full suite. Initial 14-case run hit one minimal render-fixture edit error; the fixture lacks an editable Source timeline, so the test now uses an explicit persisted revision-edit fixture without relaxing Source validation. Expanded 16-case run and 61/63 related cases passed. Studio 285 and Linux API 2659 PASS/11 SKIP remain unchanged prior verification, not rerun.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: SQLite/checkpoint hashes/human verifier, pending offline backup rejection, one review/separate grant/prepared dispatch, revocation and three audit events, workflow-database backup/restore and fresh-process exact history/project/jobs/artifact replay. MOCK TESTS: nonplayable render, synthetic QC/rights/Owner/account/platform-capability fixtures and one mocked account read. No real media QC, account/platform limits, rights or Owner UAT is inferred. Official upload/HTTP/Studio E2E remains pending; zero official upload/external provider/paid/new production media operations.

EVIDENCE: `docs/NATIVE_OFFICIAL_PUBLISH_REVIEW.md`, `docs/north-star/native-official-publish-review-evidence.json`; `recovery/20261007/native-official-publish-review-flow-n1`, owned `C:/vf-native-fixture-official-publish-review-restore-01`; backup SHA256 `c8fc541635348909a25945959cb97807af0ba9d96a291a73131af218f30c0211`. Exact source/export hashes and fresh-process proof verified. This rehearsal exercises workflow SQLite only; the previous account increment separately verifies both databases and 1280 prior media/artifacts.

REGRESSIONS: full Native/current account/dry-run/backup/consent pass; existing Studio/API source unchanged; fresh 15 accepted/live checks follow preservation. EXTERNAL BLOCKERS: authentic provider secrets/rights/platform/account/audience, browser/non-developer/Owner and production acceptance. OWNER ACTION REQUIRED: none for safe implementation; listening review remains deferred. NEXT WAVE: bounded Native official upload worker and protected session/credential lifecycle, signed HTTP/Studio integration and authentic publication/analytics paths, then all original remaining safe capabilities. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Waves 8/9 — Fresh account-check cost intent correction

WAVE: 8/9. STATUS: IN PROGRESS. HEAD SHA: parent `f66257252bc60f5e8fb9f6eab0dcd58bc05fd369`, pushed/preserved 208 ahead/0 behind in `north-star-native-official-publish-review.bundle`, SHA256 `3500a551aaa622de1512518d384d4221b955ddba887dcb55935e63671e52baee`. This correction receives a separate reviewable commit/push/bundle and fresh accepted/live checks.

CAPABILITIES COMPLETED: each fresh explicit account check has its own cost operation, preventing an earlier project/provider lookup from blocking subsequent Owner checks; exact idempotent retries still perform no new read or cost intent; existing operation labels/rows remain unchanged, unknown estimated/actual costs remain null, publishing/production authority unchanged. Two meaningful service/signed HTTP regressions cover fresh-check and exact-replay behavior. Both-database/fresh-process recovery retains prior cost/account history and 1280 prior media/artifacts.

CAPABILITIES PARTIAL: official Native upload worker, encrypted sessions/credential lifecycle, scheduling/reconciliation/receipts, signed publication UI/HTTP, authentic analytics and remaining platform/provider/rights/Owner acceptance; all original remaining Mode A/B/media/audio/trend/learning/Hub/hardening/final acceptance.

TESTS: current account/service/HTTP/registry/official-consent/cost regression 55 PASS/39.927s, including two new tests. Full Native 785 PASS at parent `f66257252bc60f5e8fb9f6eab0dcd58bc05fd369` predates this isolated one-line cost-operation-label correction and is explicitly prior verification, not a new full run. Studio 285 and Linux API 2659 PASS/11 SKIP are unchanged prior verification.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: nine signed HTTP requests on a fresh genuine prior media-bundle recovery, actual DPAPI fixture token reads, distinct immutable cost/check rows, old history/media unchanged, both SQLite databases/backup/restore and fresh-process exact replay without credentials configured. MOCK TESTS: two YouTube account responses plus synthetic tokens/identities; no external provider, paid, render, inference, real account or Owner acceptance.

EVIDENCE: `docs/north-star/native-official-account-cost-retry-evidence.json`; `recovery/20261007/native-official-account-rechecks-flow-n2`, owned `C:/vf-native-fixture-official-accounts-rechecks-02` and `C:/vf-native-fixture-official-accounts-rechecks-restore-02`; backup SHA256 `acbfb0bea385f9444b097c735e64785cd52624ca43e3d8cf63b0d8be9aaa914f`; exact source/export hashes and fresh-process proof verified. Synthetic DPAPI mounts from the previous account fixture remain outside source/state/backup. Accepted artifacts are not replaced.

REGRESSIONS: 55 related tests plus signed exact replay, old history and both-DB/media recovery pass. EXTERNAL BLOCKERS: authentic credentials/provider/rights/account/audience/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; listening review remains deferred. NEXT WAVE: official Native upload worker and protected session lifecycle, signed publication/analytics controls and all remaining original safe capabilities. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 9 — Native bounded resumable upload worker and private sessions

WAVE: 9. STATUS: IN PROGRESS. HEAD SHA: parent `771b6983072659bfed952de7994b26b283f9762c`, pushed/preserved 209 ahead/0 behind in `north-star-native-official-account-cost-retries.bundle`, SHA256 `024b81895881724e05f578b1631eef8ce8996368a206a9801dd12ab6d85f7f5c`. This capability receives a separate reviewable commit/push/bundle and fresh accepted/live checks.

CAPABILITIES COMPLETED: durable versioned init/chunk/reconcile intents before mutation; one initialization per publication; unchanged duplicate guard on uncertainty/session expiry; scoped encrypted DPAPI sessions/private ACLs outside source/state/archive; strict mock/binding/expiry/domain admission; known response retained after consent expiry without further-byte authority; exact physical-file chunking/current credential/channel/Owner/final checks; same-session uncertain-byte reconciliation; monotonic aligned acknowledgements bounded by sent windows; durable Retry-After; distinct immutable null-cost operation records; append-only processing/privacy observations and qualified terminal receipts without guessed URLs or mock-to-real relabelling; additive journal backup counts and private-file exclusion.

CAPABILITIES PARTIAL: signed HTTP/Studio/runner activation, protected publishing credentials/refresh, explicit consent renewal/read reconciliation, read-backoff/interrupted-cost handling, scheduling, authentic Native analytics, other official platform execution and real account/rights/provider/Owner acceptance. All original remaining Mode A/B/media/audio/cohort/trend/learning/Hub/isolation/hardening/final A/B/C requirements remain.

TESTS: current full Native 815 PASS/613.934s, including 28 new tests; focused official account/review/dispatch/session/worker/cost/backup 86 PASS/48.931s. Initial focused run found known initialization response discarded after consent expiry; local persistence now retains the sealed response and blocks further bytes. An assertion was corrected to the existing sanitized network-outcome code. Repaired focused/full checks pass. Studio 285 and Linux API 2659 PASS/11 SKIP remain unchanged prior verification.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual Windows DPAPI/domain/private ACLs, SQLite/current-identity/version/artifact fences, immutable costs/history, pending backup rejection, archive/private-secret exclusion and workflow-database/fresh-process exact recovery. MOCK TESTS: 12 bounded official protocol requests, one init, three exact chunks, one status reconciliation after a lost chunk response, one processing/privacy-confirmed mock receipt; explicitly nonplayable render/QC/rights/identity/account/platform fixtures. Zero real publication, external provider, paid, render or inference call.

EVIDENCE: `docs/north-star/native-official-resumable-worker-evidence.json`, `docs/NATIVE_OFFICIAL_RESUMABLE_WORKER.md`; retained `recovery/20261007/native-official-resumable-worker-flow-n1`, restored `C:/vf-native-fixture-official-resumable-worker-restore-01`; backup SHA256 `3edb219c852143f87c87b8d7595773f82c6ad8f07baa69cc5309d1dd8981a5ae`. All ten publication/cost journals, original fixture project/job/artifact hashes and terminal mock receipt replay exactly; vault/factories remain unconfigured after restore. Source/export/log/new-process hashes verified. Prior accepted artifacts are not replaced.

REGRESSIONS: current 815 Native cases and exact fixture recovery pass. EXTERNAL BLOCKERS: authentic provider/secret/account/legal/audience/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; listening review remains deferred. NEXT WAVE: protected credential/consent lifecycle, interrupted-cost/read backoff and signed Native publication controls/queue/analytics; then all original remaining safe capabilities. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 9 — Native consent renewal, read backoff and interrupted-cost recovery

WAVE: 9. STATUS: IN PROGRESS. HEAD SHA: parent `67d09ddf7cf806fd90080c64c15ba014b724e0d7`, pushed/preserved 210 ahead/0 behind in `north-star-native-official-resumable-worker.bundle`, SHA256 `349cd41c2044a63d0a22a0c0f6b1d90fe41bc2ce03058ea729cdb7f23fce7d25`. This capability receives a separate reviewable commit/push/bundle and fresh accepted/live checks.

CAPABILITIES COMPLETED: explicit strict snapshot/version/key/TTL Owner renewal; atomic prior-grant revocation/ancestry and current-source/config/account checks; original session/offset retained; exact concurrent replay issues one new grant; uncertain initialization/active request/expired upload cannot restart; already uploaded processing can receive fresh explicit consent; append-only scoped read backoff and chunk delay checked before credential/account/cost/wire work; renewal preserves delays; upload cost intent IDs refuse second dispatch; owned startup cost/dispatch recovery marks unfinished nonpaid calls unknown without decrypting/resending or changing unrelated/finished history; scope/size and receipt binding strengthened; additive renewal/backoff backup counts.

CAPABILITIES PARTIAL: protected publishing OAuth acquisition/refresh/rotation, signed Native HTTP/Studio/runner integration, bounded scheduling/queue, authentic analytics and other platforms, real media/QC/account/legal/provider/browser/Owner acceptance; all original remaining Mode A/B/audio/media/trend/cohort/learning/Hub/isolation/hardening/final A/B/C requirements.

TESTS: current related Native 98 PASS/67.84s, including 12 new lifecycle cases. Initial test setup incorrectly reused another TestCase's super-bound setup and was corrected to its plain fixture helper; the long-expiry test was corrected to use explicit fresh human-login and OAuth fixtures after their one-hour expiry. Product gates remained strict. Full Native 815 PASS at parent `67d09ddf7cf806fd90080c64c15ba014b724e0d7` is explicitly prior to this isolated lifecycle increment; Studio 285 and Linux API 2659 PASS/11 SKIP remain unchanged prior verification.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual SQLite/DPAPI scope/grant/backoff/cost persistence, explicit current-role/expiry/source/refusal, startup without vault/credentials, twelve-journal workflow backup/restore/fresh-process exact replay and unchanged fixture project/job/artifact hashes. MOCK TESTS: 13 official protocol requests, one initialization/three data chunks/one rate-limited account read/one explicit renewal/one status reconciliation/one terminal mock receipt; explicitly unsent interrupted third-chunk/cost fixture and synthetic media/QC/rights/human/account/platform inputs. Zero real publication, external provider, paid, render or inference call.

EVIDENCE: `docs/north-star/native-official-publish-lifecycle-evidence.json`, `docs/NATIVE_OFFICIAL_PUBLISH_LIFECYCLE.md`; `recovery/20261007/native-official-publish-lifecycle-flow-n1`, restored `C:/vf-native-fixture-official-publish-lifecycle-restore-01`; backup SHA256 `200690616289c7b863b9ec55aa425a60bb24095f7b49054e6e9143739fff56c6`. All twelve journals, terminal mock receipt and artifact hashes replay exactly in a fresh process; repeating startup changes no history/costs and activates no credentials/vault/factory. Source/export/log/new-process hashes verified; no accepted video replacement.

REGRESSIONS: current 98 related tests and exact recovery pass; 815 full Native is prior verification. EXTERNAL BLOCKERS: genuine credentials/rights/account/platform/provider/audience/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; listening review remains deferred. NEXT WAVE: protected publishing credentials and signed Native publication controls/queue/scheduling/authentic analytics; then remaining original safe requirements. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 9 — Native protected publishing tokens and profile registry

WAVE: 9. STATUS: IN PROGRESS. HEAD SHA: parent `b40a05719412ef23862d49832737fb698cf222b2`, pushed/preserved 211 ahead/0 behind in `north-star-native-official-publish-lifecycle.bundle`, SHA256 `d890a6bcf7a4c1a903058631f024fb063306b962c3432328c5d12228ef828259`. This capability receives a separate reviewable commit/push/bundle and fresh accepted/live checks.

CAPABILITIES COMPLETED: separate domain-scoped publishing OAuth DPAPI/ACL storage; full immutable target/profile/version/account/alias/fingerprint/expiry/scope checks; required upload/read permissions; read-only/publishing domain isolation; atomic create/no overwrite, path/link/hardlink/corruption/foreign refusal and sanitized errors; public receipts with no token/private path/enablement; bounded unique external registry with strict false defaults and separate Owner runtime enablement; frozen profile/binding/client/resolver/root/mount/configuration; authoritative registry file pin blocks change/removal; default startup/public status no decryption or provider request; existing bounded worker uses protected token loading at admitted calls; approved injected secret resolvers remain supported without Windows-only core architecture.

CAPABILITIES PARTIAL: signed Native HTTP/Studio/runner integration, secure OAuth acquisition/refresh/rotation, scheduling/queue, Meta/TikTok Native execution, thumbnails, authentic receipt-to-analytics, genuine account/platform/legal/provider/browser/Owner acceptance and all original remaining Mode A/B/audio/media/trend/cohort/learning/Hub/isolation/hardening/final A/B/C requirements.

TESTS: current related Native 124 PASS/63.114s, including 12 new token/registry cases. Initial 123 related pass preceded an added authoritative-file pin/check; current 124 verifies that additional concern. Duplicate inherited pure tests were removed from the Windows-specific class. Full Native 815 PASS at `67d09ddf7cf806fd90080c64c15ba014b724e0d7` is explicitly prior to lifecycle/credentials; Studio 285 and Linux API 2659 PASS/11 SKIP remain unchanged prior verification.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: actual Windows DPAPI/domain/private ACLs, scoped protected token loads, configuration source pin, SQLite/current-source/grant/receipt/cost/history, archive/secret exclusion and twelve-journal/fresh-process exact recovery. MOCK TESTS: ten official protocol requests with 25 publishing-token decryptions and three separately protected session decryptions, one init/three chunks/one terminal mock receipt; explicitly nonplayable QC/rights/human/account/platform/OAuth fixtures. Zero real publication, external provider, paid, render or inference call.

EVIDENCE: `docs/north-star/native-official-publish-credential-evidence.json`, `docs/NATIVE_OFFICIAL_PUBLISH_CREDENTIALS.md`; current `recovery/20261007/native-official-publish-credentials-flow-n3`, restored `C:/vf-native-fixture-official-publish-credentials-restore-03`; backup SHA256 `e625bc19257129e86b886a7d3b586a743c841806106197bbbe42925167fd5d89`. Earlier n1/n2 rehearsals remain retained at their earlier source points; n3 adds the authoritative pin to the configured mock worker. All twelve journals, both old-unsent/new-completed review histories, receipt and original fixture project/job/artifact hashes replay exactly with credential/vault/factory absence. Source/export/log/new-process hashes verified; no accepted video is replaced.

REGRESSIONS: current 124 related cases and exact recovery pass; 815 full Native is prior verification. EXTERNAL BLOCKERS: actual OAuth/accounts/platform/rights/provider/audience/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; listening review remains deferred. NEXT WAVE: signed Native publication controls/runner/queue/scheduling and authentic analytics integration; then all original remaining safe requirements. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 9 — Signed Native publishing HTTP and Studio controls

WAVE: 9. STATUS: IN PROGRESS. HEAD SHA: parent `8d04e89db08ba0a1532641308a4107736afc4979`, pushed/preserved 212 ahead/0 behind in `north-star-native-official-publish-credentials.bundle`, SHA256 `4c16cd07f0a2854041decef50271a768e2230fc3c233a76300802b4e3e2ed194`. This capability receives a separate reviewable commit/push/bundle and fresh accepted/live checks.

CAPABILITIES COMPLETED: protected registry/vault CLI/server configuration with false default enablement and human-auth requirements; mock-only direct transport injection; signed Owner/CSRF checks before mutation body; scoped checksum-validated history/detail/state with bounded cursor pagination and qualified receipts; explicit current-source review, separate approval, idempotent renewal, unsent cancellation and one snapshot/version-bound upload or processing step; startup local recovery with no decryption/send and no Runner auto-selection; optional Studio controls inside the same shot-centric review shell; no automatic loading/polling/upload/retry, no client token/endpoint/mode/URI input; current saved/idle/unarchived/Owner/project/workspace/revision/dirty/active guards, global working state, late-response invalidation, fresh per-step acknowledgement/read, unknown review/renewal key reuse, uncertain upload state reload and text-node mock qualification.

CAPABILITIES PARTIAL: durable automatic upload queue/scheduling including immutable future metadata; secure OAuth acquisition/refresh/rotation; Meta/TikTok Native execution, thumbnails, authentic receipt-to-analytics, genuine media/account/platform/legal/provider/browser/Owner acceptance and all original remaining Mode A/B/audio/media/trend/cohort/learning/Hub/isolation/hardening/final A/B/C requirements.

TESTS: current full Native 846 PASS/672.15s and current full Studio 295 PASS, including seven new signed HTTP and ten new DOM cases. Selected 31 HTTP/access cases passed before final full regression. Initial HTTP failures were fixture wiring/configuration setup; the boolean null-delay UI issue was corrected. Rehearsal n1 was a setup failure missing an explicit registry version; n2 is current and earlier evidence remains retained. A Studio wrapper stdout encoding error occurred after its child tests passed; the retained UTF-8 log confirms the full result, without rerunning or changing tests. Linux API 2659 PASS/11 SKIP remains unchanged prior verification.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: signed loopback HTTP, actual Windows DPAPI/domain/private ACLs, scoped protected token loads, SQLite/current-source/grant/dispatch/receipt/cost/history, served Studio source bytes, secret-free archive and twelve-journal/fresh-process exact recovery. MOCK TESTS: 12 official protocol requests with 30 publishing-token and four session decryptions; one init/three exact data chunks/one same-session reconcile after a lost chunk response, expired consent refused before another wire request, explicit renewed grant/replay, and one processing-confirmed mock receipt. Thirty signed HTTP requests; explicitly nonplayable QC/rights/human/account/platform/OAuth fixtures. Zero real publication, external provider, paid, new render or inference call.

EVIDENCE: `docs/north-star/native-official-publish-controls-evidence.json`, `docs/NATIVE_OFFICIAL_PUBLISH_CONTROLS.md`; `recovery/20261007/native-official-publish-controls-flow-n2`, restored `C:/vf-native-fixture-official-publish-controls-restore-02`; backup SHA256 `a4ce4d841e9a80aa601a8c4ca44cd1f9f66f07facd397a0ae3ab97abe67c07f9`. All twelve journals, old/new grants and renewal, qualified receipt and original fixture project/job/artifact hashes replay exactly with credential/vault/factory absence. Source/export/log/new-process hashes verified; no accepted video is replaced.

REGRESSIONS: current full Native/Studio and exact recovery pass. EXTERNAL BLOCKERS: actual OAuth/accounts/platform/rights/provider/audience/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; listening/UAT remains deferred. NEXT WAVE: durable Native queue/scheduling and authentic analytics integration, secure OAuth and all original remaining safe requirements. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 9 — Immutable Native publication metadata and scheduled visibility

WAVE: 9. STATUS: IN PROGRESS. HEAD SHA: parent `fac51977fa8bfb482670533b05bcfcf73ab6c81a`, pushed/preserved 213 ahead/0 behind in `north-star-native-official-publish-controls.bundle`, SHA256 `282545e9cac6fdde3721ad040e8d5d32caed1cc57a9bad7513d6c546a3488dd2`. This increment receives a separate reviewable commit/push/bundle and fresh accepted/live checks.

CAPABILITIES COMPLETED: optional strictly typed publication metadata; legacy default/null metadata request fingerprints retained; explicit metadata/current official platform and protocol validation; metadata source/frozen review time; current final/document/rights/account/configuration/grant revalidation without rejecting a known upload solely because scheduled time passed; current-clock internal 60-second initial margin before new approval/prepared renewal/credential/account/init wire; past/near/nonprivate/malformed/numeric/unknown/unchecked refusal and sanitized warnings/errors; one-init/known-session metadata/offset preservation; exact future private observation pending and actual post-time public observation required; optional Studio device-zone schedule input normalized to UTC, current saved/Owner/idle/scope safeguards and separate review/approval/state/step controls retained; source/project/dry-run/artifact/old receipt preservation.

CAPABILITIES PARTIAL: durable automatic upload queue/scheduling execution, secure OAuth acquisition/refresh/rotation, other platforms, thumbnails, authentic receipt-to-analytics, genuine media/account/platform/legal/provider/schedule/browser/Owner acceptance and every original remaining Mode A/B/media/audio/cohort/learning/trend/Hub/isolation/hardening/final A/B/C requirement.

TESTS: current related Native 103 PASS/106.32s and current full Studio 297 PASS; ten new Native and two new DOM cases. Earlier selected 39 passed before boundary cases. An initial assertion confused equivalent UTC Z/+00:00 serialization; it now compares the represented instant. Full Native 846 PASS/672.150s at fac5197 is prior, not a new full 856-case run. Linux API 2659 PASS/11 SKIP remains unchanged prior verification.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: signed loopback HTTP, SQLite/current-source/review/grant/metadata/dispatch/receipt/history/cost, actual existing protected session vault, served Studio bytes, archive secret exclusion and twelve-journal/fresh-process/previous receipt exact recovery. MOCK TESTS: 23 signed HTTP/12 provider protocol requests, one init/three exact chunks/two processing observations; private future schedule stays pending, later public reply permits qualified mock receipt, stale processing version adds no request. Media/QC/rights/human/account/platform/OAuth/provider/clock values are explicitly synthetic and nonplayable. Zero real publication/external provider/paid/new render/inference call.

EVIDENCE: `docs/north-star/native-official-publish-metadata-evidence.json`, `docs/NATIVE_OFFICIAL_PUBLISH_METADATA.md`; `recovery/20261007/native-official-publish-metadata-flow-n1`, restored `C:/vf-native-fixture-official-publish-metadata-restore-01`; backup SHA256 `5dd5460dbb74042cc65dd8abd91ecc31261051ed950f00815d6b46c03a1a98ee`. All twelve journals/current receipt/original project/job/artifact hashes replay exactly without credentials/profiles/vault/dispatcher; preceding signed-controls receipt and twelve journals remain exact under the additive metadata model. Source/export/log/new-process hashes verified; no accepted video replaced.

REGRESSIONS: current related Native/full Studio and exact historical/new recovery pass; full Native 846 remains prior. EXTERNAL BLOCKERS: actual OAuth/accounts/platform/rights/provider/audience/schedule/browser/Owner/production acceptance. OWNER ACTION REQUIRED: none for safe implementation; listening/UAT remains deferred. NEXT WAVE: durable bounded Native queue execution/scheduling, secure OAuth and authentic analytics/other platforms, then all original remaining safe work. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO.


### Wave 9 — Revocable Native per-publication Owner grants

WAVE: 9. STATUS: IN PROGRESS. HEAD SHA: parent `27ac774738f88252b9bc5ce956f06ec95524a1e4`, pushed/preserved 214 ahead/0 behind in `north-star-native-official-publish-metadata.bundle`, SHA256 `9e574592422f9b354f32a2b54a22e43696373d5e21522225daff25eb6f90e71f`. This increment receives its own commit/push/bundle and fresh accepted/live checks.

CAPABILITIES COMPLETED: signed current Owner/CSRF-before-body scoped revoke endpoint; strict expected snapshot, role/foreign/unchecked/completed/unapproved refusal; revoke all active scoped grants without current source/media/rights/configuration or old grant expiry dependency; exact replay/one audit event; keep dispatch version/intent/session/offset/approval/history unchanged; parent review_required/CONSENT_REVOKED sticky under unknown response/recovery; known late initialization protected/no new bytes; chunk progress never invented; explicit renewal/known-session reconciliation/one initialization; processing race no terminal receipt; completed receipts unchanged/no remote deletion; historical Studio stop after edits/archive/active analysis, no send acknowledgement or auto-action.

CAPABILITIES PARTIAL: durable bounded background queue/scheduling, OAuth acquisition/refresh/rotation, other platforms/thumbnails/authentic analytics, genuine media/account/platform/legal/provider/browser/Owner acceptance and every original remaining Mode A/B/media/audio/cohort/learning/trend/Hub/isolation/hardening/final A/B/C requirement.

TESTS: current related Native 113 PASS/105.608s, current full Studio 299 PASS/1222.6287ms; ten new Native/two DOM cases plus expanded signed roles/CSRF. Focused Native 17 PASS/63.452s. First Studio wrapper passed a directory and failed before suite enumeration; corrected explicit 54-file run passed 299. Full Native 846 PASS/672.150s at fac5197 is prior, not a current full 866 run. Prior unchanged Linux API 2659 PASS/11 SKIP retained.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: signed owned HTTP/SQLite/history/CAS/grant/race/cost/archive/actual protected session vault, exact served Studio bytes and fresh-process restore. MOCK TESTS: 36 signed HTTP/12 provider requests; two stops/two explicit renewals/one init/three unique chunks/one same-session reconciliation/qualified mock receipt. All media/QC/rights/identity/account/platform/OAuth/provider values are explicit nonplayable fixtures. Zero real publication/external request/paid/new render/inference call.

EVIDENCE: `docs/north-star/native-official-publish-revocation-evidence.json`, `docs/NATIVE_OFFICIAL_PUBLISH_REVOCATION.md`, `recovery/20261007/native-official-publish-revocation-flow-n1`; restored `C:/vf-native-fixture-official-publish-revocation-restore-01`, backup SHA256 `2d3d8428bd5245092131ba18e606b92c893352d8e00ae76f1f51c1fb558e8506`. Original project/dry run/job/artifact hashes, all twelve journals, current receipt and preceding metadata receipt/twelve journals remain exact. Protected tokens/session files/private URLs excluded from backup. Hashes/export/log/fresh-process replay indexed; no accepted artifact replaced.

REGRESSIONS: none observed in current scoped Native/full Studio/recovery; full Native remains prior. EXTERNAL BLOCKERS: actual OAuth/authorized provider/account/media/rights/schedule/browser/Owner acceptance and Docker/production environment. OWNER ACTION REQUIRED: none for safe work; listening/UAT deferred; real publishing/new paid budget/deployment/main merge require separate Owner action. NEXT WAVE: continue Wave 9 bounded explicit background execution and every original remaining safe wave. SOURCE_PRESERVED is anchored to the prior clean receipt until this increment is committed/pushed/bundled. PHASE10_READY/IMPLEMENTATION_COMPLETE/REAL_PROVIDER_ACCEPTANCE_COMPLETE/PRODUCTION_DEPLOYED/NORTH_STAR_READY remain NO; no STOP pending.


### Wave 9 — Default-off finite Native official publication queue kernel

WAVE: 9. STATUS: IN PROGRESS. HEAD SHA: parent `d92568efa1219143c2126a193105cc89f43684a2`, pushed/preserved 215 ahead/0 behind in `north-star-native-official-publish-revocation.bundle`, SHA256 `01071659039940f238a9cc9387f6fce407db147c01993690da133acbb93d8b78`. This capability receives a separate commit/push/bundle and fresh accepted/live preservation checks.

CAPABILITIES COMPLETED: default-disabled standalone queue kernel; publication approval alone cannot execute; strict separate Owner background acknowledgement, snapshot/dispatch/current approval/Owner/mock policy, 1–100 steps/30–3600-second intervals/aware start-deadline bounded by consent; idempotent exact replay/conflict/one active plan; atomic claims/count before send; typed qualified outcomes and checksum/scoped/ordinal/history verification before further wire; existing worker guard before each request; known read backoff; queue cancel independent of publication grant/remote deletion; source/Owner/grant/operator/deadline/exhaustion stops; known init/chunk response retained after plan stop, publication revocation still forbids progress/receipt; uncertainty stops, a new explicit plan reconciles the same session/one init; startup local outcome_unknown/no decrypt/renewal/resend; historical credential-free reads; backup counts/busy handling and fifteen-journal recovery.

CAPABILITIES PARTIAL: HTTP/Runner/Studio scheduling integration, OAuth acquisition/refresh/rotation, other platforms/thumbnails/authentic analytics, genuine media/account/platform/legal/provider/browser/Owner acceptance and every original remaining Mode A/B/media/audio/cohort/learning/trend/Hub/isolation/hardening/final A/B/C requirement.

TESTS: current full Native 890 PASS/737.501s, including 24 new queue cases; the focused 19 passed/23.612s before the last five boundary cases. Earlier 16-case run passed but exposed test temporary-directory lifecycle; independent fixtures now cover each reason and the expanded runs are clean. Prior unchanged full Studio 299 at d92568e and Linux API 2659 PASS/11 SKIP remain prior checks. No new Studio test claim.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: SQLite claims/scopes/CAS/policy/history/current-source/cost, actual existing protected session vault, archive and exact fresh-process recovery. MOCK TESTS: 12 provider protocol requests, separately authorized first plan stops at lost chunk reply, a new explicit plan reconciles same session and finishes; one init/three unique chunks/one reconciliation/two histories/qualified mock receipt. Zero signed HTTP in this kernel rehearsal; zero real publication/external request/paid/new render/inference call. Fixtures explicitly nonplayable/synthetic.

EVIDENCE: `docs/north-star/native-official-publish-queue-kernel-evidence.json`, `docs/NATIVE_OFFICIAL_PUBLISH_QUEUE_KERNEL.md`, `recovery/20261007/native-official-publish-queue-kernel-flow-n1`, restored `C:/vf-native-fixture-official-publish-queue-restore-01`; backup SHA256 `695c4040eb63594e3d4854e25ee9ed213f51a09ead2c0d18c74f9f5184e533d5`. Original source/dry run/job/artifacts, all fifteen journals/current receipt/two histories and preceding revocation receipt/twelve journals replay exactly, protected credentials/session files/private URLs excluded. All source/export/log/fresh-process hashes indexed; no accepted artifact replaced.

REGRESSIONS: none observed in current full Native and owned recovery; unchanged Studio/API retain prior results. EXTERNAL BLOCKERS: genuine authorized provider/account/media/rights/OAuth/schedule/browser/Owner acceptance, Docker/production environment. OWNER ACTION REQUIRED: none for safe work; listening/UAT deferred; real publishing/new paid budget/deployment/main merge need separate Owner action. NEXT WAVE: attach finite queue to signed runtime/HTTP/Studio with independent default-off operator gate, then every original remaining safe wave. SOURCE_PRESERVED anchored to prior receipt until this commit is pushed/bundled. PHASE10_READY/IMPLEMENTATION_COMPLETE/REAL_PROVIDER_ACCEPTANCE_COMPLETE/PRODUCTION_DEPLOYED/NORTH_STAR_READY remain NO; no STOP pending.


### Wave 9 — Signed Native finite queue runtime and Studio controls

WAVE: 9. STATUS: IN PROGRESS. HEAD SHA: parent `65e4e6458023cc74b0d1ebb958863786ce110247`, pushed/preserved 216 ahead/0 behind in `north-star-native-official-publish-queue-kernel.bundle`, SHA256 `01c8cb7560d3363ffea03dd1803e9e50e1f7429103883403c4e028d73052c6df`. This increment receives its own commit/push/bundle/fresh accepted/live checks.

CAPABILITIES COMPLETED: independent strict default-off operator flag/protected publishing registry+vault+human-auth before socket/mock-only injected factories; signed no-store runtime/page/detail/create/cancel routes; Owner/CSRF before body, strict finite acknowledgement/time/count/version/scope/client-field/hash/key/cursor checks; creation stores/wakes only, one due Runner step and no early calls; worker-intent recovery before queue-claim recovery before thread start; original kernel current-source/grant/backoff/one-init/uncertainty/cancel fences retained; credential-free historical reads; Studio explicit runtime read, saved publication snapshot/dispatch/grant binding, separate finite plan/UTC device dates/limits/ack, exact uncertain-key retention, text nodes/mock qualification/history/stored read/historical cancellation/late-scope-role-grant reset, same shot-review shell; cold pure-contract import bootstrap; five served files exact.

CAPABILITIES PARTIAL: secure OAuth acquisition/refresh/rotation, other platforms/thumbnails/authentic receipt-to-analytics, genuine media/account/platform/legal/provider/schedule/browser/Owner acceptance and every original remaining Mode A/B/media/audio/cohort/learning/trend/Hub/isolation/hardening/final A/B/C requirement. Native finite queue implementation is mock/local tested; full publishing and North Star remain incomplete.

TESTS: current full Native 899 PASS/737.542s, nine new cases (eight signed HTTP/Runner plus one cold import); current full Studio 307 PASS/1224.4233ms, eight new DOM cases. Focused Native 31 PASS/48.177s before last two HTTP cases; expanded HTTP eight PASS/18.513s; focused DOM 22 PASS. Initial test collection multiline context-manager syntax repaired before execution; no gate relaxed. Prior unchanged Linux API 2659 PASS/11 SKIP retained.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: signed loopback HTTP/SQLite/current source/strict DTO/CAS/policy/history/cost/Runner/gates, actual existing protected session vault, five served UI files, archive/fresh-process recovery. MOCK TESTS: 22 actual signed HTTP/10 provider protocol requests; first separately approved plan runs one initialization, cancellation exact replay prevents future queue requests, a new explicit plan uses same session for three unique chunks and processing; qualified mock receipt/two histories preserved, completed cancel no-op. Zero real publication/external request/paid/new render/inference call; all acceptance-sensitive inputs explicitly synthetic/nonplayable.

EVIDENCE: `docs/north-star/native-official-publish-queue-controls-evidence.json`, `docs/NATIVE_OFFICIAL_PUBLISH_QUEUE_CONTROLS.md`, `recovery/20261007/native-official-publish-queue-controls-flow-n1`, restored `C:/vf-native-fixture-official-publish-queue-controls-restore-01`, backup SHA256 `ef52dff6c55ebbe585fb208845017eacb744b13dd69eb3d125cd975cf4e68d8d`. Original project/dry run/job/artifacts, two histories/current receipt/all fifteen journals and preceding kernel receipt/histories/journals replay exactly. Private token/session files/URLs excluded; all source/export/log/fresh-process hashes indexed. No accepted artifact replaced.

REGRESSIONS: none in current full Native/full Studio/owned legacy/recovery. EXTERNAL BLOCKERS: authorized real OAuth/provider/account/media/rights/schedule/browser/Owner acceptance and Docker/production environment. OWNER ACTION REQUIRED: none for safe implementation; listening/UAT deferred; real publishing/new paid budget/deployment/main merge need separate approval. NEXT WAVE: continue secure credential lifecycle/authentic analytics/other platform integration and every original remaining safe wave. SOURCE_PRESERVED anchored to previous receipt until this source is committed/pushed/bundled. PHASE10_READY/IMPLEMENTATION_COMPLETE/REAL_PROVIDER_ACCEPTANCE_COMPLETE/PRODUCTION_DEPLOYED/NORTH_STAR_READY remain NO; no STOP pending.


### Wave 10 — Native official receipt-bound analytics kernel

WAVE: 10. STATUS: IN PROGRESS. HEAD SHA: parent `3f0aab38740e0f0b26870882d6181765f7a8ed39`, pushed/preserved 217 ahead/0 behind in `north-star-native-official-publish-queue-controls.bundle`, SHA256 `7a7a145b91fca05054878181db00081e7434bf9e2fe9316a920843f55a187f04`. This increment receives its own commit/push/bundle/fresh accepted/live checks.

CAPABILITIES COMPLETED: pure Native read-only YouTube kernel/default-off independent operator gate; separate strict current-human Owner finite read consent with exact qualified publication receipt/source/current account/config/query/raw-mock binding; no publishing/recurring authority or synthetic fallback; atomic bounded claim/attempts before reads, fresh credentials and exact authenticated channel/video ownership before report, response-time and same-write source/consent/config fences; later project edits/expired publishing grant preserve original published render features; typed nullable metrics/zero/watch-time conversion/optional scoped VND estimated revenue, no coverage/window/completion/CTR/RPM/publishing-time inference; distinct per-attempt/operation cost intents and hashed sanitized response proofs; immutable snapshots/historical reads/no credentials required, bounded scoped pages; explicit finite known 429/5xx retries/default one attempt/durable backoff, unknown outcome review/no replay, local idempotent cancel; scoped interrupted/cancelled cost recovery including crash during recovery; all five additive journals counted in backup/busy checks.

CAPABILITIES PARTIAL: kernel has no signed Native routes/Runner/Studio/finite official scheduled refresh/cohort/winner/learning/Bridge projection yet. Secure OAuth acquisition/refresh/rotation, other platform publishing/analytics/thumbnails, genuine media/account/platform/legal/provider/browser/Owner acceptance and every original remaining Mode A/B/media/audio/trend/Hub/isolation/hardening/final A/B/C requirement continue. Full analytics/publishing/North Star are not ready.

TESTS: current full Native 935 PASS/853.195s, 36 new cases; current full unchanged Studio 307 PASS/1230.3636ms. First targeted 33-case run had 32 passing plus an empty-text foreign-project fixture error, corrected to a media project without changing any gate; rerun 34 PASS/89.982s, then four final-fence cases PASS/8.004s and two cancellation/source-race cases PASS/4.235s. Prior unchanged Linux API 2659 PASS/11 SKIP retained.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: SQLite/strict contracts/current identity/scope/CAS/journal/cost/known-backoff/cancel/startup recovery, existing protected session vault, archive and fresh-process restore. MOCK TESTS: initial owned protocol publication has ten requests plus one initial account-check fixture; seven fixed read requests demonstrate known backoff, approved retry, two immutable nullable observations and local cancellation of a third request. No signed HTTP/Studio/Runner test is claimed for this kernel. Zero real publication/audience/external request/paid/new render/inference or Owner acceptance. All sensitive acceptance inputs explicitly synthetic/nonplayable.

EVIDENCE: `docs/north-star/native-official-analytics-kernel-evidence.json`, `docs/NATIVE_OFFICIAL_ANALYTICS_KERNEL.md`, `recovery/20261007/native-official-analytics-kernel-flow-n1`, restored `C:/vf-native-fixture-official-analytics-restore-01`, backup SHA256 `d6032a3e3d73dc46fa52b3b760ff16dd6231fa20d35d55dec0dce199b35cf4ca`/962541B. Original project/dry run/current receipt/job/physical artifacts, three analytics histories/all twenty journals and preceding queue receipt/two histories/fifteen journals replay exactly. Private token/session files/URLs excluded. All source/export/log/fresh-process hashes indexed. No accepted video replaced.

REGRESSIONS: none in current full Native/full Studio/owned legacy/recovery. EXTERNAL BLOCKERS: authorized real OAuth/provider/account/media/rights/browser/Owner acceptance and Docker/production environment. OWNER ACTION REQUIRED: none for safe implementation; listening/UAT deferred; real publishing/new paid budget/deployment/main merge need separate approval. NEXT WAVE: attach official analytics to signed routes/Runner/Studio, then finite refresh/qualified winner/learning/Bridge and every original remaining safe wave. SOURCE_PRESERVED anchored to previous receipt until this source is committed/pushed/bundled. PHASE10_READY/IMPLEMENTATION_COMPLETE/REAL_PROVIDER_ACCEPTANCE_COMPLETE/PRODUCTION_DEPLOYED/NORTH_STAR_READY remain NO; no STOP pending.


### Waves 8/10 — Protected read-account registry and final resolution fences

WAVE: 8/10. STATUS: IN PROGRESS. HEAD SHA: parent `0ec96022e4ef860e6e9c1669e6b16d9144170ba9`, pushed/preserved 218 ahead/0 behind in `north-star-native-official-analytics-kernel.bundle`, SHA256 `900e425a6a79eab6bab4e89ac461252b819b73adca493747346a052de1fe53ef`. This increment receives its own commit/push/bundle/fresh accepted/live checks.

CAPABILITIES COMPLETED: strict protected read-account registry load with absolute external unlinked bounded unique JSON/hash consistency and Boolean operator gate, exact frozen registry bytes/configuration hash and replacement/removal/rebinding checks before/after token resolution; unchanged constructor-only hashes; final post-resolution current Owner/source/claim/registry/credential-lifetime fence before analytics wire dispatch; registry/Owner/clock mutation during final resolution sends zero requests; changed configuration requires fresh explicit consent; immutable history and prior journals read without registry/factory/credentials; no startup token read or private path/token output.

CAPABILITIES PARTIAL: signed Native analytics routes/Runner/Studio, finite official scheduled refresh, qualified cohorts/winner/learning/Bridge, secure OAuth acquisition/refresh/rotation, other platforms and every original remaining Mode A/B/media/audio/trend/Hub/isolation/hardening/final A/B/C requirement. Full analytics/publishing/North Star remain incomplete.

TESTS: current related Native 204 PASS/281.182s across all fifteen official account/publishing/queue/analytics modules; fourteen new cases (eight registry/six analytics). Earlier focused 20 PASS/11.219s, related 201 PASS/271.848s before final-resolution fences, then three focused timing cases PASS/6.456s. Prior full Native 935 PASS/853.195s and unchanged Studio 307 PASS/1230.3636ms at parent; no current full Native 949 claim. Prior unchanged Linux API 2659 PASS/11 SKIP retained.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: registry filesystem/hash/path/DTO/frozen configuration/SQLite/current source/identity/cost/consent/claims, archive and exact fresh-process recovery. MOCK TESTS: six fixed analytics read requests create two qualified mock observations; intervening changed registry stops collection with zero additional reads, fresh configuration and separate new consent allow second observation, registry/factory removal preserves history. Initial publication ten wire requests plus one account lookup are synthetic. Zero real publication/audience/external/paid/new render/inference or Owner acceptance. All sensitive acceptance inputs explicitly synthetic/nonplayable.

EVIDENCE: `docs/north-star/native-official-read-registry-fences-evidence.json`, `docs/NATIVE_OFFICIAL_READ_REGISTRY_FENCES.md`, `recovery/20261007/native-official-read-registry-fences-flow-n1`, restored `C:/vf-native-fixture-official-analytics-read-registry-restore-01`, backup SHA256 `d932a9aa54a04c441748d81a93682704cac42734bf8d407dcc7d117d9964604a`/962540B. Original project/current receipt/job/physical artifacts, three analytics histories/all twenty journals and preceding analytics kernel receipt/histories/journals replay exactly. Private token/session files/URLs excluded; source/export/log/fresh-process hashes indexed. No accepted video replaced.

REGRESSIONS: none in current related suites/owned legacy/recovery. EXTERNAL BLOCKERS: authorized real OAuth/provider/account/media/rights/browser/Owner acceptance and Docker/production environment. OWNER ACTION REQUIRED: none for safe implementation; listening/UAT deferred; real publishing/new paid budget/deployment/main merge need separate approval. NEXT WAVE: signed Native official analytics routes/Runner/Studio, finite refresh/cohort/winner/learning/Bridge/OAuth and every original remaining safe wave. SOURCE_PRESERVED anchored to prior receipt until this increment is committed/pushed/bundled. PHASE10_READY/IMPLEMENTATION_COMPLETE/REAL_PROVIDER_ACCEPTANCE_COMPLETE/PRODUCTION_DEPLOYED/NORTH_STAR_READY remain NO; no STOP pending.


### Wave 10 — Signed Native official analytics runtime and Studio

WAVE: 10. STATUS: IN PROGRESS. HEAD SHA: parent `36a07fc8d6702edbdfef11e8775d44f6707d6af4`, pushed/preserved 219 ahead/0 behind in `north-star-native-official-read-registry-fences.bundle`, SHA256 `fb0c7895c90c361653b49c24ca40f6a12daae529bfab5104b5818e51ad3ea880`. This increment receives its own commit/push/bundle/fresh accepted/live checks.

CAPABILITIES COMPLETED: independent strict default-off analytics flag/protected read-registry/human gate and malformed-registry pre-socket refusal; no startup token read; server canonical qualified receipt binding; signed Owner/CSRF permission before body/local-only create and completed exact-key result replay/history/detail/local cancellation; finite due Runner attempts and ordered interrupted-claim recovery; current Owner/source/account/configuration/credential/deadline/backoff kernel fences; fixed scoped telemetry; shot-review Studio explicit dates/read-only/mock/retry consent, no automatic requests/poll/fallback, exact uncertain key retention including old-selection draft reset, completed replay, bounded opaque cursors, late/foreign/target/receipt/query/mock rejection, historical cancellation and fifteen nullable metric/unit cards.

CAPABILITIES PARTIAL: official finite scheduled refresh, relative channel cohorts/winner/learning/Bridge, secure OAuth acquisition/refresh/rotation, other platforms and every original remaining Mode A/B/media/audio/trend/Hub/isolation/hardening/final A/B/C requirement. Full analytics/publishing/North Star remain incomplete.

TESTS: full current Native 962 PASS/938.529s and Studio 319 PASS/1231.7905ms. Thirteen new Native cases (eleven signed HTTP/Runner/two observability), twelve new DOM cases. Initial DOM 12 PASS/147.321ms. Prior unchanged Linux API 2659 PASS/11 SKIP retained.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: 22 signed local HTTP requests, SQLite/source/hash/claim/cost/identity/consent/finite Runner/served Studio/archive and exact fresh-process recovery. MOCK TESTS: seven fixed analytics reads include approved known backoff/no early Runner call, two immutable observations, completed exact-key result replay with zero extra reads and a cancelled third request. Initial publication ten wire requests plus one account lookup are synthetic. Zero real publication/audience/external/paid/new render/inference, browser or Owner acceptance. All sensitive acceptance inputs explicitly synthetic/nonplayable.

EVIDENCE: `docs/north-star/native-official-analytics-controls-evidence.json`, `docs/NATIVE_OFFICIAL_ANALYTICS_CONTROLS.md`, `recovery/20261007/native-official-analytics-controls-flow-n1`, restored `C:/vf-native-fixture-official-analytics-controls-restore-01`, backup SHA256 `4c8ca9b7a387c5c268161e175c5867adce55160b06ef5680782d4408bedb5fcb`/1381866B. Six Studio files served exactly. Original project/current receipt/dry run/job/physical artifacts, three analytics histories/all twenty journals and preceding read-registry receipt/histories/journals replay exactly. Private token/session files/URLs excluded; source/export/log/fresh-process hashes indexed. No accepted video replaced.

REGRESSIONS: none in current full suites/owned legacy/recovery. EXTERNAL BLOCKERS: authorized real OAuth/provider/account/media/rights/browser/Owner acceptance and Docker/production environment. OWNER ACTION REQUIRED: none for safe implementation; listening/UAT deferred; real publishing/new paid budget/deployment/main merge need separate approval. NEXT WAVE: finite official refresh/cohort/winner/learning/Bridge/OAuth and every original remaining safe wave. SOURCE_PRESERVED anchored to prior receipt until this increment is committed/pushed/bundled. PHASE10_READY/IMPLEMENTATION_COMPLETE/REAL_PROVIDER_ACCEPTANCE_COMPLETE/PRODUCTION_DEPLOYED/NORTH_STAR_READY remain NO; no STOP pending.
