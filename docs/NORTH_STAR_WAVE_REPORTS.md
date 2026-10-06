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

HEAD SHA: parent `834d6db`; commit `feat(studio): review safe silence cuts with measured waveforms and shot view` records this increment.

CAPABILITIES COMPLETED: canonical silence cuts retain padding and reject speech overlap even with stale safety flags; whole speech segments are protected when words are absent. Editor-scoped selection requires timeline CAS, respects locked editable tracks and binds the historical transcript active after undo. All-source removal is rejected. Earlier versions remain immutable and approval/preview/render invalidate. Threshold configuration is distinguished from measured loudness. Local PCM waveform measurement streams bounded peak/RMS bins, persists provenance without migration, fingerprints the algorithm and follows source-relative trim/split/move. Shot cards and the collapsed advanced view select/edit identical canonical clip IDs. Pre-timeline transcript/scene/silence/highlight review is visible. New-project/upload authoring is collapsible and opens for empty projects. Explicit `hidden` semantics correct the inspector placeholder bug.

CAPABILITIES PARTIAL: Native/production bridge; combined scene/Vision/motion evidence; Top 3/5/Auto Shorts selection; dynamic subtitle completeness; full real spoken-media acceptance. Fixture ASR is clearly labeled and not accepted as real transcript evidence.

TESTS: **35/35 API PASS**, 44.23 s, in `mode-b-silence-35-final.log`. Frontend **88/88 PASS**, 388.76 ms. Seven silence/media tests cover segment/word protection, preserved padding, stale flags, keep-all selection, all-footage rejection, historical transcript binding, locks, CAS, authenticated actor attribution and real local FFmpeg measurement. Early runs exposed two test-fixture mistakes and the default metadata-track lock; corrected and rerun rather than ignored.

REAL PROVIDER TESTS: none. LOCAL-REAL TESTS: FFmpeg synthetic tone/video decode, silence bounds and waveform amplitude; real persistence and browser HTTP mutations on a fresh isolated SQLite fixture. No genuine speech/remote ASR/Vision acceptance claim. MOCK TESTS: explicit deterministic transcript/media providers only.

EVIDENCE: `docs/north-star/studio-wave3-visual/evidence.json` and six browser images; `scripts/north_star_studio_fixture.py` reproducible loopback-only harness; `audio_waveform.py`, silence tests and logs in recovery. Browser checks at **1366×768 / 1920×1080 / 2560×1440** show no horizontal overflow; actual transcript save v2, undo v3, redo v4, silence rebuild v5; draft approval; no console warning/error. Temporary viewport override reset.

REGRESSIONS: focused API/Studio pass; full prior-head Ubuntu regression is **1,896 passed / 5 skipped** and is preserved separately. Native 264/264 is the latest Wave 2 run, not represented as retested here. Accepted/candidate media and live DB remain unchanged. No live restart, production deployment, paid call, external publishing or main merge.

EXTERNAL BLOCKERS: Docker absent; genuine provider acceptance and Owner UAT remain separate gates. No blocker to further safe implementation.

OWNER ACTION REQUIRED: none for continued implementation. NEXT WAVE: finish Wave 3 analysis/highlight/reframe/Native integration; continue all later safe waves.
