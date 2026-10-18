# Final export and manual delivery baseline

Recorded 2026-10-18 for `VF-FINAL-EXPORT-MANUAL-PUBLISHING-FOCUS-01`.

## Source safety before product changes

- Repository: `C:\vfns01`; chat directory is not the repository.
- Baseline branch: `codex/vf-north-star-completion-01`.
- Exact HEAD: `4162bc32260521277737f7c9ee118b5ba55b3f9b`.
- Origin: `https://github.com/vangnguyen/npd-video-factory-v2.git`.
- Fresh fetch: remote main `fa81c59fbe6b745cba8fed979e30e52a13199afa`; HEAD is 492 ahead / 0 behind main, 0 ahead / 0 behind its upstream. No local-only committed history.
- Working tree was clean before baseline evidence was created. Full worktree, tag and tracking inventory is in [repository-state.json](../evidence/final-export-manual-publishing/baseline/repository-state.json).
- Protected live source `C:\NPD-Video-Factory\source` remains clean at `2ced7bc81f9402368fb22c9e7aca242e740531af`.
- Five unfinished B-roll Root UI files and six unfinished generative suggestion files were archived with binary tracked patches, untracked file bytes, base revisions and SHA256 inventories. Both original worktrees remain intact; this work is frozen, unreviewed and not imported into this program. [Preservation record](../evidence/final-export-manual-publishing/baseline/deferred-work-preservation.json).
- Complete Git recovery bundle: `C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007\final-export-source-baseline-n1.bundle`, 204634353 bytes, SHA256 `fac3c4ecefba914c12663859a503257ced32d3df5fbddecfff029cd6066850ff`. Includes baseline and both deferred branches. `git bundle verify` succeeded; [verification](../evidence/final-export-manual-publishing/baseline/bundle-verify.txt).
- All 15 historical accepted MP4s were rehashed and match the prior preservation record. Exact paths, sizes and hashes: [accepted-artifacts.json](../evidence/final-export-manual-publishing/baseline/accepted-artifacts.json).

`SOURCE_PRESERVED = YES`  
`ACCEPTED_ARTIFACTS_PRESERVED = YES`  
`RECOVERY_BUNDLE_VALID = YES`

## Existing runtime and implementation

Windows Native Studio is served at `/` and `/native.html` by `services/windows_native/server.py`, with `native.mjs`, `native.css` and the shared shot workspace. SQL/API Studio also exists (`apps/studio-web/studio.html`, `studio.js`); its contracts remain preserved. Native and SQL are distinct runtimes, so acceptance of one does not imply the other.

- Native `north_star_quality.py::PROFILES`: vertical-short 1080x1920 / 9:16, landscape 1920x1080 / 16:9, square 1080x1080 / 1:1, portrait-feed 1080x1350 / 4:5. Exact canvas validation exists. Native storyboard output is driven by selected brand/template; source footage uses canonical timeline geometry.
- Existing Native final path: `Store.approve` -> idempotent `Store.enqueue(kind=render)` -> Pipeline/source or narrated render -> QC -> `Store.review_render` -> `Store.final_video`. It validates current document, approval, checkpoint and artifact hash. Relevant edits invalidate approval; historical files are not replaced.
- Existing UI offers preview, create render, watch/listen final approval, final MP4 download, output-folder action, and technical artifact details. There is no consolidated user-facing local delivery package/caption history/export history center at this baseline.
- Download routes `/api/jobs/{job}/video` and `/final` validate current render; `/final` additionally requires exact final review. POST `/api/jobs/{job}/open-folder` is Windows-specific and checks the current render.
- Existing `render_thumbnails.py` and Studio thumbnail controller select an original rendered PNG with source provenance. Rights review is separate. Do not fabricate cover rights.
- Existing publishing and analytics implementations remain in source. They are frozen for this program; local delivery must not create external publication records.

## Quality findings to close or verify

- Native production-quality policy already canonicalizes the three required proper names; human pronunciation/listening acceptance remains pending.
- Narration fit policy measures actual speech and binds dependent timings. Tests must cover this rather than treating requested target duration as measured speech.
- Native policy renders and source renders have measured trailing audio checks (2 seconds plus existing measurement tolerance); shared `app.production_qc.FullProductionQC` only checks total silence ratio at baseline. Add a shared explicit trailing-silence gate; do not rewrite historical QC reports.
- Shared full QC measures metadata, codecs, FPS, A/V duration delta, black/freeze intervals, signal samples, decode errors, volume and subtitle/timeline reports. Signalstats is not semantic Vision or a listening acceptance.
- Subtitle masks, Vietnamese glyph bounds, canonical audio stems/mix and narration binding have existing tests. Final export must require current measured QC and exact approval; legacy transport-only QC is insufficient for a new delivery claim.
- Browser observation was previously rejected by URL policy. No browser workaround is used. Current UI interaction acceptance is not established by source/Node tests.

## Test baseline on exact source 4162bc32

Logs are retained in `C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007`:

| Suite | Result | Log |
|---|---|---|
| SQL/API render, QC, verified delivery, final render admission | 52 passed, 51.61s | `final-export-baseline-API-n1.log` |
| Full Studio | 2092 tests: 2026 pass, 66 fail, 0 skipped | `final-export-baseline-Studio-n1.log` |
| Native quality, source render, full storyboard QC | Running when baseline was first recorded; final result will be appended | `final-export-baseline-Native-n1.log` |

The Studio failures precede product changes and are concentrated in the B-roll internal Root harness. Investigate captured session expiry versus its test clock; retain the failure log and fix the harness only if demonstrated. No full regression pass is claimed. Phase 8/9/10, renderer and Mode B historical certifications are preserved but are not a new full-suite result for this export program.

## Focus and acceptance

Implementation order: P1 final quality gates, P2 Export Center, P3 manual package/copy/cover, P4 immutable history, P5 recovery, then P6 drama casting. Use reviewable commits on `codex/vf-final-export-manual-01`. Do not merge main or mutate the protected live checkout.

`FINAL_VIDEO_QUALITY_READY = NO`  
`EXPORT_CENTER_READY = NO`  
`DELIVERY_PACKAGE_READY = NO`  
`EXPORT_HISTORY_READY = NO`  
`DRAMA_VOICE_CASTING_READY = NO`  
`OWNER_EXPORT_UAT_COMPLETE = NO`  
`OWNER_VOICE_UAT_REQUIRED = YES`  
`PLATFORM_API_PUBLISHING = DEFERRED`  
`ANALYTICS = DEFERRED`  
`FULL_TREND_RADAR = DEFERRED`  
`PRODUCTION_DEPLOYED = NO`
