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
