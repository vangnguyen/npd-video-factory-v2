# Phase 9K — Script approval and proposed storyboard/media

PHASE: 9K — Content Intelligence practical acceptance, after Owner script approval

STATUS: PHASE9K_STORYBOARD_MEDIA_REVIEW_REQUIRED. The five exact v2 scripts are Owner-approved; 25 proposed graphics are ready for review. Phase 9K final acceptance remains PENDING.

HEAD SHA: `2980fdf16e6580fb4a9fbefb82f689cba22ea7da` at this checkpoint capture, including the tested application change and actual human script receipts. Baseline: `f61d8de6545653ea46f8ab5f91e6c0c0c167b7af`, annotated tag `internal-production-v1`. The subsequent evidence/report commits are recorded in Git history.

FILES CHANGED: `services/windows_native/store.py`, `services/windows_native/tests/test_script_review.py`, `apps/studio-web/native.html`, `native.mjs`, `tests/native-workflow.test.mjs`; script-approval, storyboard preparation and read-only verification helpers; Owner receipts, current per-case acceptance/storyboard/asset/render plans; two test logs, before/after restart snapshots, Studio screenshot, and `storyboard-media-review/` containing 25 original assets and static previews. No Phase 8 evidence changed.

TESTS: 132/132 Native and 32/32 Studio PASS. Three new Native checks cover durable/idempotent script-only approval, stale/unacknowledged decisions, narration edits versus scene-only edits and the existing render guard. One new Studio check verifies the saved-script label while production remains disabled. Actual restart, source/lineage integrity, all 25 graphic file hashes/dimensions and five unchanged narration bindings PASS.

EVIDENCE: [Owner script authorization](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/owner-script-authorization-v2.json), [approval manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-approval-manifest.json), [25-scene review bundle](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-review-bundle.md), [media manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-review/review-manifest.json), [Codex visual inspection](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-review/visual-review.json), [restart verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-after-restart.json), [Native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/native-tests-storyboard.log), [Studio tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/studio-tests-storyboard.log).

NEW CAPABILITIES: actual Owner script approval is stored separately in the existing append-only event table, bound to exact narration and research-lineage hashes. It changes neither project revision/document nor production approval. Content Intelligence projects expose this saved-script status in Studio. Existing production approval and render dispatch remain authoritative. No schema migration, new production pipeline or new public write endpoint was introduced.

REGRESSIONS: none observed in the accepted Native scope. Ten accepted Phase 8 MP4s, all Phase 8 evidence, release tag, dependencies, pre-task production rows and intelligence histories remain unchanged. Nineteen records of the original Owner Case 01 research run are preserved. Both database table snapshots match across the actual restart. All five projects remain native revision 3, with no assets imported and only their original content jobs awaiting review.

BLOCKERS: Owner review of the exact storyboard/media/rights and proposed edit plan; then five actual video productions, technical/artifact/persistence checks and five explicit human watch/listen decisions. No new credential, paid provider, destructive migration or architecture replacement is required.

NEXT ACTION: return the concrete 25-scene bundle for Owner review. If approved, import only those exact graphics and unchanged v2 narration into the existing Native pipeline, apply the reviewed scene options, record production approval and continue. At this checkpoint TTS/render dispatches = 0, new MP4s = 0 and external publishing = 0.

## Actual script decisions

Owner replied exactly `Duyệt v2: 01, 02, 04, 06, 08`. No text edits accompanied that reply. Reviewer identity is recorded as `Owner — duyệt v2 qua Codex`; no personal name is invented. Scope is SCRIPT_ONLY.

| Case | Native script review ID | Script review | Proposed scenes | Storyboard/media/rights |
|---|---|---|---:|---|
| 01 | `87dc9b64195f4fb3b4f4cdb0710510ca` | OWNER_APPROVED v2 | 5 | PENDING |
| 02 | `4db80dfdbed34a76b7e1e7342c5a41d4` | OWNER_APPROVED v2 | 5 | PENDING |
| 04 | `04318d0346bd45429cfbf93552cb2ce3` | OWNER_APPROVED v2 | 5 | PENDING |
| 06 | `15c2261a5974424a8070794b756103cd` | OWNER_APPROVED v2 | 5 | PENDING |
| 08 | `eeb021a90af74fea990e7819b664e31e` | OWNER_APPROVED v2 | 5 | PENDING |

The authorization contains a frozen copy of the original review manifest, whose per-case pending fields describe that earlier snapshot. Current decisions are the native event receipts and `script-approval-manifest.json`. Earlier script review bundles/manifests, v1 provider receipts and v2 narration files remain unchanged.

## Proposed visual treatment and scope

All 25 assets are locally authored text/shape graphics using existing Pillow and installed Windows fonts. Business directions live in `storyboard-graphic-directions.json`, outside the core domain. No third-party photographs, official logos, property renderings, portraits or font files are included. Each asset retains its source IDs/URLs/content hashes, recipe hash, font hashes, exact script hash and proposed stable asset ID. Rights approval remains pending.

The 1080 × 830 source graphics fit the existing Native media plane. Proposed production settings are contain, no motion, fade and no music. Full 1080 × 1920 PNGs illustrate the existing Native composition; they are static proposals, with excerpt captions and unmeasured timing. They are not renderer outputs or production/video QC evidence. The shortened scene headings are proposed only; live project documents remain unchanged.

Codex inspected all five contact sheets and full-size previews for Case 02's launch date and Case 08's comparisons. All 25 Native headings passed the measured two-line/safe-width check. The Case 08 bars use separate 100% baselines and show 71.5% and 63.7% OF those periods. This is editorial preparation, not Owner media acceptance.

Review bundle SHA256: `d9fe7af9329c5bc293a155b9f152fdd65730e3f1b6f83bb65149291a81ac7000`. The media manifest binds the bundle, HTML, every asset/preview/contact sheet and proposed per-case plan. The browser disallowed the local HTML's file protocol; the Markdown bundle supplies all 25 scenes and full-size image links through the workspace file viewer. Its open request was queued, so no visible gallery opening is claimed.

![Actual Native Studio after script approval and restart](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-approved-media-pending-studio.png)

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
