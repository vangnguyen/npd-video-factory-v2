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

Full Native launched before later cover/recovery/QC/P6 additions completed **2156 tests / 7802.239s: 2139 passed, 3 failed, 14 errors**. The long-lived test process used an older in-memory static route map while reading newer UI imports; two failures requested `native-export-settings.mjs` from that mixed version. The capability contract fixture needed the three deliberately added export capabilities. Fourteen restore errors came from old seven-field runtime manifests missing the later optional `local_asr_manifest` field.

Current-source closure: **38 pass / 302.792s**, `final-export-native-regression-closure-n1.log`. This reruns all seventeen originally failing/error cases plus backup and static regression checks. It is not a new full 2156-test run. The exact capability test retains all prior fields and adds manual delivery, manual-delivery focus and the runtime folder capability. HTTP module-dependency closure passes using the current route map.

Legacy backup compatibility now accepts omission of exactly `local_asr_manifest`, supplies an absolute absent sentinel in the new restore destination and records the defaulted field. Missing required paths and unknown fields still fail; entry hashes, archive trusted hash and database checks remain enforced. No legacy archive is rewritten or service started. The older Facebook/Instagram fixture archives retain SHA256 `c487444e3c4bcef7d26c82c6e6204887e373c8080ef01e62814751e69842ed6c` and `16b33273f92bb23a9031b2cae4821d7406eb4d4b52a9cb511c5118f1006c0dbf` respectively. These are regression fixtures, not platform deployment or expanded publishing work.

## Current P6 integration regression

Native signed HTTP/casting/canonical runtime/media delivery/static cohort: **36 pass / 67.023s**, `final-export-drama-Studio-Native-n4.log`. This includes explicit legacy narrator-policy conversion and stale voice-library admission/current-preview/render/new-delivery closure. The earlier n3 run found a real canonical binding defect when explicitly clearing the legacy policy; the source now rebuilds/validates that binding before commit. The n1 command also included a nonexistent test selector; it was corrected rather than treating the failed command as pass.

Current full Studio Node suite: **2143 pass, 0 fail/skip / 28.9655272s**, `final-export-current-full-Studio-n6.log`. Twenty focused drama controls tests overlap this full suite. Current Native quality/legacy/export/backup cohort: **71 pass / 159.212s**, `final-export-drama-quality-regression-Native-n2.log`. Renderer: **7 files / 52 pass / 10.92s**, TypeScript typecheck pass, `final-export-renderer-full-n3.log` / `final-export-renderer-typecheck-n3.log`.

These are current-source focused/full-Studio/renderer results, not a fresh full Native 2156+ run or a passing full SQL/API run. The earlier broad API failures and Linux/environment qualification limits remain as classified above. TTS in these new tests is explicitly mock; actual local WAV/FFmpeg/render/QC/ZIP processing does not certify real speech or browser layout.

## Still pending

Measured dialogue activity/speaker QC is now pinned to the render/preview/recovery/manual-package evidence. Current Native cohorts: **64 pass / 160.451s** and an overlapping **15 pass / 42.910s**, `final-export-dialogue-cue-qc-Native-n3.log` / `n4.log`. Moving a caption into another actor's interval through the real canonical editor fails before ASS/video generation. Synthetic tones establish physical timing only; no ASR, word alignment, real voice or Owner acceptance is inferred. See [QC evidence](../evidence/final-export-manual-publishing/quality-closure/dialogue-speaker-window-qc.json).

Browser visual checks, all five consolidated Owner export cases, human pronunciation/listening and real two-voice dialogue provider acceptance remain open. Series persistence and per-line audio/UI integration are now implemented and mock/local-media tested. A separate local review Studio is available, with synthetic fixture data and no deferred workers; HTTP byte verification is not browser acceptance. Phase 8/9/10 accepted files were rehashed unchanged; acceptance is not silently replaced by fixtures. Docker/Linux and production are not certified by this Windows run.

`FINAL_VIDEO_QUALITY_READY=NO`, `EXPORT_CENTER_READY=NO`, `DELIVERY_PACKAGE_READY=NO`, `EXPORT_HISTORY_READY=NO`, `DRAMA_VOICE_CASTING_READY=NO`, `OWNER_EXPORT_UAT_COMPLETE=NO`.

`PLATFORM_API_PUBLISHING=DEFERRED`, `ANALYTICS=DEFERRED`, `FULL_TREND_RADAR=DEFERRED`, `PRODUCTION_DEPLOYED=NO`.
