# Phase 9K — Final review register, awaiting storyboard/media decisions

Current checkpoint: **PHASE9K_STORYBOARD_MEDIA_REVIEW_REQUIRED**. This register records actual script decisions and outstanding media/video acceptance. Phase 9K has not passed.

Five native projects and five actual script responses exist. Review version is v2 after Codex editorial preparation; original v1 provider responses are preserved. Owner replied exactly `Duyệt v2: 01, 02, 04, 06, 08`. All five approvals are bound to the unchanged v2 narration/lineage and persisted as SCRIPT_ONLY native events. Twenty-five original graphics and proposed scene plans are ready for the next human review. No text edits accompanied the approval reply.

| Case | Brief/handoff | Script human review | Storyboard/media human review | New final MP4 | ffprobe | Video artifact integrity | Human watch/listen |
|---|---|---|---|---|---|---|---|
| 01 | APPROVED / REAL | OWNER_APPROVED v2 | PENDING; 5 proposed scenes | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |
| 02 | APPROVED / REAL | OWNER_APPROVED v2 | PENDING; 5 proposed scenes | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |
| 04 | APPROVED / REAL | OWNER_APPROVED v2 | PENDING; 5 proposed scenes | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |
| 06 | APPROVED / REAL | OWNER_APPROVED v2 | PENDING; 5 proposed scenes | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |
| 08 | APPROVED / REAL | OWNER_APPROVED v2 | PENDING; 5 proposed scenes | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |

Script/source/hash integrity and persisted project state: **5/5 PASS**, including the latest actual server restart and reopened Studio API with current human script receipts. Both database table snapshots are unchanged across that restart. Proposed graphic/preview hashes and dimensions: **25/25 PASS**. These results do not substitute for Owner media approval, video ffprobe/QC, MP4 integrity or human watch/listen.

Each case contains `research.json`, `idea.json`, `brief.json`, `script-v1.json`, `script-v2.json`, `script-review.json`, `storyboard.json`, `asset-lineage.json`, `proposed-production-proposal.json`, `render-manifest.json` and `acceptance.json`. Actual provider request/response/result files remain unchanged. Proposed asset metadata now lists five original graphic files per case; no assets have been imported into live Native projects. Storyboard/media approval remains pending and the render manifest says not requested. `ffprobe.json` and `final.mp4` do not exist; no fabricated video files or PASS records are used.

## Editorial preparation and remaining checks

These are Codex observations on usefulness and grounding. Owner has approved the scripts; the notes do not imply media/video acceptance or statistical validation of ranking.

| Case | Useful viewer value and hook | Grounding and CTA | Production feasibility remaining |
|---|---|---|---|
| 01 | Directly asks what IHG cooperation means; names four brands and explains the multi-segment lodging direction | Agreement date, developer relationship and brands match retained findings; expectation attributed to IHG; invitation to ask about a brand | 30–45s target, 122 whitespace-separated Vietnamese/brand tokens; five original text graphics proposed, media approval and measured timing pending |
| 02 | Keeps the requested smart-city hook and introduces the three source-named organizations | Launch dated 03/03/2026, not award; no new ISO/current-status claim; asks what criteria interest viewers | 45–60s target, 152 tokens; launch date and organizations shown as text, no logo/certificate image; pronunciation and media review pending |
| 04 | Three actionable buyer questions: event/progress, marketing/facts, documents/time | Kick-Off example and marketing wording remain source-attributed; no conclusion about current price, progress or legality; asks which documents to explain | 45s target, 146 tokens; five educational comparison/question graphics proposed; no property photo or guaranteed-return imagery |
| 06 | Keeps approved opening and three-date reading method with Vang Nguyễn branding | Publication 24/04/2026 vs Q1/2026 vs editorial date 06/10/2026; no invented transactions/credentials; question-based CTA | 45s target, 141 tokens; text branding without invented portrait/credentials; media review pending; date wording must stay correct if revised later |
| 08 | Opens with supply/transaction contrast and focuses on Q2/2026 historical context | All three indicators and approximate 100.005 count match retained source; 71.5% OF Q1 and 63.7% OF prior-year period, not percentage declines; asks locality/indicator | 45–60s target, 159 tokens; comparison bars have separate 100% baselines; numerical pronunciation and media approval pending; no TTS run |

Token counts are not word counts, measured speech durations, or proof of voice quality. The script-only decision is not a scored effectiveness evaluation of hook/ranking/CTA. Original practical assessment of ten cases remains in `../practical-editorial-assessment.md`; the other five cases are not selected or approved by this task.

## Evidence and boundaries

- [Exact five-script review bundle](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-review-bundle.md), bound to stable IDs, v2 hashes and native revision 3 by `script-review-manifest.json`.
- [Real handoff matrix](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-handoff-matrix.md), with research → idea → approved brief → native script identity chain.
- [Actual provider ledger](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/actual-script-provider-ledger.json): five completed `gpt-6-luna` responses, five actual script calls, no editorial regeneration calls.
- [Actual Owner script decisions](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-approval-manifest.json): 5/5 exact v2 scripts; raw Owner reply and bound authorization retained.
- [Concrete storyboard/media bundle](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-review-bundle.md): five contact sheets and 25 full-size previews, SHA256 `d9fe7af9329c5bc293a155b9f152fdd65730e3f1b6f83bb65149291a81ac7000`.
- [Latest restart/preservation verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-after-restart.json): accepted release and pre-task Owner rows unchanged; original Case 01 records/history preserved; sources, drafts and current script receipts reopened; media/import/production counts remain zero.
- [Native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/native-tests-storyboard.log): 132/132 PASS. [Studio tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/studio-tests-storyboard.log): 32/32 PASS.
- [Subphase checkpoint](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-checkpoint.md): complete report fields, actual review IDs, visual QA scope and limitations.

![Actual Native Studio showing saved script approved and media review pending](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-approved-media-pending-studio.png)

Ten accepted Phase 8 videos remain immutable and are not counted here. The earlier isolated render-contract MP4 is not counted. The five script decisions come directly from Owner; no storyboard/media/final-video approval is invented. No TTS/render/publishing action was dispatched for these five candidates. Static layout previews contain excerpt captions with ellipsis; audio timing/subtitle synchronization and final video QC remain unmeasured.

## Remaining acceptance gates

1. Owner reviews the 25 proposed scenes, exact assets/rights and scene options. Possible decision: `Duyệt storyboard/media đồ họa: 01, 02, 04, 06, 08`, or identify cases/scenes needing edits. This includes using the reviewed original graphics and continuing internal production; it does not approve final videos or publishing.
2. Import only those reviewed assets and apply the reviewed plan with unchanged approved narration, then record the existing Native production approval and generate five new video previews with measured TTS duration and subtitles.
3. Store actual ffprobe/QC and artifact hashes, verify persistence/restart, and record five explicit human watch/listen decisions for the exact final MP4s. Preserve research → final-video lineage.

This checkpoint stops at storyboard/media review: five script approvals are complete and the next concrete review bundle is ready. No credentials/provider/architecture blocker exists. The local HTML gallery was not opened because the browser blocks file URLs; the Markdown bundle supplies the images through workspace file links.

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
