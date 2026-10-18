# Final Export regression status

Updated 2026-10-18. Implementation and evidence remain on the separate `codex/vf-final-export-manual-01` branch. No merge or production deployment.

## Completed cohorts

- Full Studio: 2123 pass, zero failure/skip, 32.768s (`final-export-current-full-Studio-n3.log`).
- Renderer: 7 files / 52 pass, 5.35s; TypeScript typecheck pass.
- Focused QC: 32 pass, including actual encoded three-second silent tail and a single black frame. Geometry, rotation and unexplained terminal freeze gates are retained.
- Local actual MP4 export includes all four shapes. Additional landscape/square-60-FPS/feed subcases passed preview, approval fixture, render, full QC and matching delivery. This is synthetic technical content, not Owner UAT.
- Native recovery includes actual child process exits during/after render, handoff reconciliation, disk/write/collision/tamper faults, backup restore and bounded concurrent exact replay.
- Native/HTTP history pagination: 9 pass; 105 export and 105 caption rows, project/workspace scope, strict queries and viewer reads.
- P6 components: 57 pass (9 casting, 9 planned dependencies, 9 library, 17 backup, 13 storyboard QC), 57.894s. No dialogue TTS inference, physical cache reuse or new casting UI is claimed.

These cohorts overlap. Do not add their totals or call the combined set a fresh full runtime run.

## Wide API run: not a pass

Initial collection failed in five Windows modules because the SQL test venv lacks NumPy/websockets and the OS lacks Unix `grp`. The explicitly filtered run then completed:

**4139 passed, 37 failed, 17 errors, 63 skipped, 6513.19s.**

Log: `recovery/20261007/final-export-compatible-API-n2.log`.

| Group | Count | Evidence / interpretation |
|---|---:|---|
| Functional/contract failures selected for baseline replay | 11 failed in the earlier wide run; now closed in targeted cohorts | All eleven reproduce at the preserved pre-export HEAD `4162bc32260521277737f7c9ee118b5ba55b3f9b`. Includes storage tamper error precedence, the route-dependency structural assertion, rights/provenance fixtures and frozen read proofs. Updated fixtures/assertions now pass without changing production guards; this is not a new passing full API run. |
| Linux executor/custody and dependency modules | 26 failed | Observed failures include POSIX absolute-path assumptions, root/owner/file-mode custody, missing `O_NOFOLLOW`, missing `yaml`, security probes and Windows symlink privilege. These are not certified on this Windows venv; this group was not independently replayed on Linux. |
| MVP1 provider admission fixture setup | 17 errors | `os.getuid` is unavailable on Windows. No synthetic `getuid`/root or custody bypass was introduced. |

The baseline comparison also ran the actual variant-route pre-body admission behavior: **five cases passed** while the structural dependency assertion still failed. Source uses `FamilyRoute.get_route_handler` to call `authorize_human_request` before the body handler, plus project scope checks. A missing literal `Depends` entry is therefore not by itself evidence of an auth bypass. Runtime authorization was preserved; no guard was weakened merely to satisfy the structural assertion.

Baseline comparison: **11 failed, 5 passed / 88.78s**, helper wall time 92.484s. [Exact node IDs and receipt](../evidence/final-export-manual-publishing/baseline/api-failed-baseline-comparison.json). A separate detached checkout was used and then removed after verifying exact baseline HEAD and a clean working tree. [Cleanup receipt](../evidence/final-export-manual-publishing/baseline/temporary-checkout-cleanup.json): 703169497 bytes in that disposable checkout; source remains in Git and verified recovery bundles.

## Native wide run and targeted closure

The eleven pre-existing API failures now have current-source closure: **58 pass / 87.57s** (CPU/storage, W1 mock HTTP and human auth) and **58 pass / 226.74s** (uploaded derivation, variant API, storyboard rebuild and existing mock service flow). The exhaustive registered FamilyRoute pre-body test supplements actual RBAC checks. First-party synthetic sources declare owned rights explicitly; derived assets still default to unknown. W1 uses real scoped bounded local reads and complete custody metadata, without forging a proof or calling a live provider. [Closure receipt and initial failed attempts](../evidence/final-export-manual-publishing/baseline/api-fixture-closure.json). Linux/environment qualifications remain open.

Targeted Linux closure is now available: **291 pass / 2 root skips / 345.55s** over ten files, followed by **2 pass / 15.77s** for those exact skipped cases under real UID/GID 65534. The latter checks real DAC failure and rejection of non-root self-owned public authority; it does not mock root or file ownership. The five formerly uncollectable NumPy/websocket/Unix modules are included in the ten-file cohort. [Environment and scope](../evidence/final-export-manual-publishing/baseline/linux-security-closure.json). No production host qualification or Docker E2E is inferred. The new full Linux API result is recorded below.

Full Native launched before later cover/recovery/QC/P6 additions completed **2156 tests / 7802.239s: 2139 passed, 3 failed, 14 errors**. The long-lived test process used an older in-memory static route map while reading newer UI imports; two failures requested `native-export-settings.mjs` from that mixed version. The capability contract fixture needed the three deliberately added export capabilities. Fourteen restore errors came from old seven-field runtime manifests missing the later optional `local_asr_manifest` field.

Current-source closure: **38 pass / 302.792s**, `final-export-native-regression-closure-n1.log`. This reruns all seventeen originally failing/error cases plus backup and static regression checks. It is not a new full 2156-test run. The exact capability test retains all prior fields and adds manual delivery, manual-delivery focus and the runtime folder capability. HTTP module-dependency closure passes using the current route map.

Legacy backup compatibility now accepts omission of exactly `local_asr_manifest`, supplies an absolute absent sentinel in the new restore destination and records the defaulted field. Missing required paths and unknown fields still fail; entry hashes, archive trusted hash and database checks remain enforced. No legacy archive is rewritten or service started. The older Facebook/Instagram fixture archives retain SHA256 `c487444e3c4bcef7d26c82c6e6204887e373c8080ef01e62814751e69842ed6c` and `16b33273f92bb23a9031b2cae4821d7406eb4d4b52a9cb511c5118f1006c0dbf` respectively. These are regression fixtures, not platform deployment or expanded publishing work.

## Current P6 integration regression

New disjoint full Native discovery: **2285 loaded, 2264 executed, 3 failures, 2 errors / 4516.547s**, source trees unchanged during the run. Twenty-one Render Vision cases did not execute because their shared setup's final render job failed; the bare assertion did not retain its error code. All 21 replayed successfully in 167.349s with unchanged runtime/conditions. The original cause is unclassified, not silently attributed to CPU pressure. The setup assertion now reports safe status/error code for future failures.

The three assertion failures were reproduced as fixture issues: an early router import escaped the HTTP fixture's provider mock, and the cache test's recursive ordinary-path inspection missed children beyond Windows MAX_PATH even though the real cache wrote/reused them. Explicit resolver alias scope and extended owned-path inspection close the full HTTP/cache cohort at **22 pass / 55.324s**. The second error was a non-atomic readiness JSON publication in the local webhook test receiver; atomic temporary-file/fsync/replace closes both source-type process cohorts at **8 pass / 259.406s**. Production provider, cache, webhook and QC logic are unchanged. [Full result and closure evidence](../evidence/final-export-manual-publishing/baseline/native-regression-closure-n2.json). This is broad discovery plus targeted replays, not a new zero-error full Native run. Fixture changes are committed at `e3fd473b`.

Native signed HTTP/casting/canonical runtime/media delivery/static cohort: **36 pass / 67.023s**, `final-export-drama-Studio-Native-n4.log`. This includes explicit legacy narrator-policy conversion and stale voice-library admission/current-preview/render/new-delivery closure. The earlier n3 run found a real canonical binding defect when explicitly clearing the legacy policy; the source now rebuilds/validates that binding before commit. The n1 command also included a nonexistent test selector; it was corrected rather than treating the failed command as pass.

Current full Studio Node suite: **2143 pass, 0 fail/skip / 28.9655272s**, `final-export-current-full-Studio-n6.log`. Twenty focused drama controls tests overlap this full suite. Current Native quality/legacy/export/backup cohort: **71 pass / 159.212s**, `final-export-drama-quality-regression-Native-n2.log`. Renderer: **7 files / 52 pass / 10.92s**, TypeScript typecheck pass, `final-export-renderer-full-n3.log` / `final-export-renderer-typecheck-n3.log`.

These are current-source focused/full-Studio/renderer results, not a fresh passing full Native or SQL/API run. The earlier broad API failures and later Linux qualifications are kept separately below. TTS in these new tests is explicitly mock; actual local WAV/FFmpeg/render/QC/ZIP processing does not certify real speech or browser layout.

## Full Linux API result and tool-qualified closure

Two disjoint shards completed **4376 collected: 4310 passed, 26 failed, zero errors, 40 skipped / 7823.726s helper wall time**. Shard times are 7610.397/7747.803s in JUnit; they are concurrent and must not be added. All **630 pinned API/worker/contracts/workflow source files stayed unchanged**. The run began at `b49b0a9a`; later commits changed Native fixtures/messages and docs outside that pinned set. [Exact wide result, node IDs and reasons](../evidence/final-export-manual-publishing/baseline/api-full-linux-n4.json).

The 26 failures classify as 24 explicit missing-FFmpeg assertions, one unconfigured FFprobe and one `shutil.which('ffmpeg')=None` passed to subprocess. Complete related files replay with unchanged source and isolated portable tools: variant API **30 pass / 359.509s**; uploaded derivation + canonical processing **26 pass / 152.865s**; storyboard rebuild **11 pass / 126.872s**; uploaded consumer + silence safety **14 pass / 115.363s**. The first storyboard replay had **10 pass/1 missing-Node failure**; official portable Node 24.19.0, matching Windows, closes the entire file. No production guard is weakened to accommodate absent tools.

Of 40 original skips, **27** pass in Linux portable-media replays, **2** pass with real non-root UID/GID, **5** physical MP4/SQL/decoder cases pass on Windows (73.42s), and **3** Windows rename/reverification cases pass on Windows (10.64s). The three remaining cases require real isolated PostgreSQL row-lock/transaction barriers. They are unqualified; no production database was contacted. [Exact skip-to-environment map](../evidence/final-export-manual-publishing/baseline/api-full-linux-qualification-n4.json). Scene-signals replay is **5 pass / 2.199s**; media-skip replay is **20 pass/5 intentional Windows-only skips / 235.337s**, later closed by the five Windows cases. Replays overlap; this is not a newly passing full run.

Portable FFmpeg/FFprobe and Node are private to the owned Linux CI root, with recorded binary/archive SHA256; no system packages, shared PATH, Windows locked runtime or production services were changed. Real media processing is qualified separately from explicit mock/saved ASR/TTS and fixture approvals. Docker E2E, production qualification, genuine new two-voice speech, browser layout and Owner UAT remain open. The 69-file regression archive has verified CRC and every entry hash: [archive receipt](../evidence/final-export-manual-publishing/recovery/regression-evidence-archive-n1.json).

## Still pending

Measured dialogue activity/speaker QC is now pinned to the render/preview/recovery/manual-package evidence. Current Native cohorts: **64 pass / 160.451s** and an overlapping **15 pass / 42.910s**, `final-export-dialogue-cue-qc-Native-n3.log` / `n4.log`. Moving a caption into another actor's interval through the real canonical editor fails before ASS/video generation. Synthetic tones establish physical timing only; no ASR, word alignment, real voice or Owner acceptance is inferred. See [QC evidence](../evidence/final-export-manual-publishing/quality-closure/dialogue-speaker-window-qc.json).

Browser visual checks, all five consolidated Owner export cases, human pronunciation/listening and real two-voice dialogue provider acceptance remain open. Series persistence and per-line audio/UI integration are now implemented and mock/local-media tested. A separate local review Studio is available, with synthetic fixture data and no deferred workers; HTTP byte verification is not browser acceptance. Phase 8/9/10 accepted files were rehashed unchanged; acceptance is not silently replaced by fixtures. Docker/Linux and production are not certified by this Windows run.

`FINAL_VIDEO_QUALITY_READY=NO`, `EXPORT_CENTER_READY=NO`, `DELIVERY_PACKAGE_READY=NO`, `EXPORT_HISTORY_READY=NO`, `DRAMA_VOICE_CASTING_READY=NO`, `OWNER_EXPORT_UAT_COMPLETE=NO`.

`PLATFORM_API_PUBLISHING=DEFERRED`, `ANALYTICS=DEFERRED`, `FULL_TREND_RADAR=DEFERRED`, `PRODUCTION_DEPLOYED=NO`.


## Drama Save Self Conflict 05 — 18/10/2026

Candidate code/application HEAD `758466ed97cdd6c204bed3f6d1e7fd06a6db807c`, served `C:/vfdr05`, build `drama-save-fix-05`. Full Studio 2165 PASS; Native related 76 PASS (one parent executes nine real-HTTP/callback scenarios); API related 92 PASS; renderer 52 PASS and typecheck PASS. Source frozen for all checks. Browser bootstrap remains BLOCKED; no browser/Owner acceptance claimed. Details: [report](DRAMA_SAVE_SELF_CONFLICT_05.md), evidence `evidence/drama-save-self-conflict-05/`.

The previous full Native four-group run at `2acd7fdd` finished: 2306 loaded, 2306 run, 0 failures, 2 errors, 0 skips — NOT PASS. Both errors belong to the same TikTok cold-history fixture: HTTP timeout and following cleanup WinError32 while SQLite is open. This focused save fix does not resolve that qualification. Related tests and replays are not substituted for a full pass. Three PostgreSQL cases remain NOT_RUN and previous full API qualification remains separate. Publishing/analytics/trend expansion remains deferred.


## Drama Casting Save / Next Step 06 — 18/10/2026

Current code/application HEAD `2b8ff625cfcb299642367b8ac2bfa2f07f94c0bd`, source `C:/vfdr06`, build `drama-casting-next-06`, loopback port 62684. Full Studio **2168 PASS**; Native related **80 PASS** (two parents run 15 casting + 9 script HTTP/production callback cases); API related **92 PASS**; renderer **52 PASS**, typecheck PASS. All suites ran on fixed clean candidate. Notes-only autosave preserves verified speaker confirmation/casting/timeline/audio references; save-and-continue verifies scoped casting receipt/GET and enters scenes without media/TTS prerequisites. Replay and actual CAS conflicts retain safeguards. [Full scope and preservation](DRAMA_CASTING_SAVE_NEXT_STEP_06.md).

These are not a new passing full Native/API run. M4 full Native 2306 run/2 errors remains NOT PASS; three real PostgreSQL cases remain NOT_RUN and do not lie on the Native SQLite path. Browser bootstrap BLOCKED; no screenshot or Owner acceptance. Seven preexisting projects, 15 historical MP4 hashes, 25 voices/10 real samples unchanged. Standard/Drama Export UAT and readiness declarations remain open; deferred scopes/production unchanged.
