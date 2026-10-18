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
| Functional/contract failures selected for baseline replay | 11 failed | All eleven reproduce at the preserved pre-export HEAD `4162bc32260521277737f7c9ee118b5ba55b3f9b`. Includes storage tamper error precedence, the route-dependency structural assertion, rights/provenance fixtures and frozen read proofs. These failures predate this program; they remain unresolved. |
| Linux executor/custody and dependency modules | 26 failed | Observed failures include POSIX absolute-path assumptions, root/owner/file-mode custody, missing `O_NOFOLLOW`, missing `yaml`, security probes and Windows symlink privilege. These are not certified on this Windows venv; this group was not independently replayed on Linux. |
| MVP1 provider admission fixture setup | 17 errors | `os.getuid` is unavailable on Windows. No synthetic `getuid`/root or custody bypass was introduced. |

The baseline comparison also ran the actual variant-route pre-body admission behavior: **five cases passed** while the structural dependency assertion still failed. Source uses `FamilyRoute.get_route_handler` to call `authorize_human_request` before the body handler, plus project scope checks. A missing literal `Depends` entry is therefore not by itself evidence of an auth bypass. Runtime authorization was preserved; no guard was weakened merely to satisfy the structural assertion.

Baseline comparison: **11 failed, 5 passed / 88.78s**, helper wall time 92.484s. [Exact node IDs and receipt](../evidence/final-export-manual-publishing/baseline/api-failed-baseline-comparison.json). A separate detached checkout was used and then removed after verifying exact baseline HEAD and a clean working tree. [Cleanup receipt](../evidence/final-export-manual-publishing/baseline/temporary-checkout-cleanup.json): 703169497 bytes in that disposable checkout; source remains in Git and verified recovery bundles.

## Still pending

Full Native launched before later cover/recovery/QC/P6 additions and remains running. Its final result will be reported with that source cutline. The focused later cohorts do not turn it into a new complete full-runtime certification.

Browser visual checks, all five consolidated Owner export cases, human pronunciation/listening, real two-voice dialogue provider acceptance, series casting and the complete per-line audio/UI integration remain open. Phase 8/9/10 accepted files were rehashed unchanged; acceptance is not silently replaced by these fixtures. Docker/Linux and production are not certified by this Windows run.

`FINAL_VIDEO_QUALITY_READY=NO`, `EXPORT_CENTER_READY=NO`, `DELIVERY_PACKAGE_READY=NO`, `EXPORT_HISTORY_READY=NO`, `DRAMA_VOICE_CASTING_READY=NO`, `OWNER_EXPORT_UAT_COMPLETE=NO`.

`PLATFORM_API_PUBLISHING=DEFERRED`, `ANALYTICS=DEFERRED`, `FULL_TREND_RADAR=DEFERRED`, `PRODUCTION_DEPLOYED=NO`.
