# Phase 9K — Final review register, awaiting script decisions

Current checkpoint: **PHASE9K_SCRIPT_REVIEW_REQUIRED**. This register records outstanding acceptance rather than declaring Phase 9K PASS.

The Owner request approves only five idea briefs and asks for all scripts before the next decision. Five native projects and five actual script responses exist. Review version is v2 after Codex editorial preparation; original v1 provider responses are preserved. Owner has not reviewed these scripts yet.

| Case | Brief/handoff | Script human review | Storyboard/media human review | New final MP4 | ffprobe | Video artifact integrity | Human watch/listen |
|---|---|---|---|---|---|---|---|
| 01 | APPROVED / REAL | PENDING v2 | PENDING | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |
| 02 | APPROVED / REAL | PENDING v2 | PENDING | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |
| 04 | APPROVED / REAL | PENDING v2 | PENDING | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |
| 06 | APPROVED / REAL | PENDING v2 | PENDING | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |
| 08 | APPROVED / REAL | PENDING v2 | PENDING | NOT_GENERATED | NOT_RUN | NOT_APPLICABLE_YET | PENDING |

Script/source/hash integrity and persisted project state: **5/5 PASS**, including actual server restart and reopened Studio API. These results do not substitute for video ffprobe/QC, MP4 integrity or Owner watch/listen.

Each case contains `research.json`, `idea.json`, `brief.json`, `script-v1.json`, `script-v2.json`, `storyboard.json`, `asset-lineage.json`, `render-manifest.json` and `acceptance.json`. Actual provider request/response/result files are also retained. `storyboard.json` is only an unapproved proposal, assets are empty, and render manifest explicitly says not requested. `ffprobe.json` and `final.mp4` do not exist because no real video has been generated; no fabricated files or PASS records are used.

## Editorial assessment before Owner review

These are Codex observations on usefulness and grounding, not human acceptance or statistical validation of the ranking layer.

| Case | Useful viewer value and hook | Grounding and CTA | Production feasibility remaining |
|---|---|---|---|
| 01 | Directly asks what IHG cooperation means; names four brands and explains the multi-segment lodging direction | Agreement date, developer relationship and brands match retained findings; expectation attributed to IHG; invitation to ask about a brand | 30–45s target, 122 whitespace-separated Vietnamese/brand tokens; timing unmeasured; approved images/text assets still needed |
| 02 | Keeps the requested smart-city hook and introduces the three source-named organizations | Launch dated 03/03/2026, not award; no new ISO/current-status claim; asks what criteria interest viewers | 45–60s target, 152 tokens; removed internal Owner/TTS line; organization-name pronunciation and assets need review |
| 04 | Three actionable buyer questions: event/progress, marketing/facts, documents/time | Kick-Off example and marketing wording remain source-attributed; no conclusion about current price, progress or legality; asks which documents to explain | 45s target, 146 tokens; removes extraneous attendance figures and unavailable-checklist offer; media not selected |
| 06 | Keeps approved opening and three-date reading method with Vang Nguyễn branding | Publication 24/04/2026 vs Q1/2026 vs editorial date 06/10/2026; no invented transactions/credentials; question-based CTA | 45s target, 141 tokens; branding/text assets require review; current-date wording must stay correct if revised later |
| 08 | Opens with supply/transaction contrast and focuses on Q2/2026 historical context | All three indicators and approximate 100.005 count match retained source; 71.5% OF Q1 and 63.7% OF prior-year period, not percentage declines; asks locality/indicator | 45–60s target, 159 tokens; numerical pronunciation and comparison graphics require review; no TTS run |

Token counts are not word counts, measured speech durations, or proof of voice quality. Human hook/ranking/CTA usefulness assessment remains open. Original practical assessment of ten cases is in `../practical-editorial-assessment.md`; the other five cases are not selected or approved by this task.

## Evidence and boundaries

- [Exact five-script review bundle](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-review-bundle.md), bound to stable IDs, v2 hashes and native revision 3 by `script-review-manifest.json`.
- [Real handoff matrix](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-handoff-matrix.md), with research → idea → approved brief → native script identity chain.
- [Actual provider ledger](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/actual-script-provider-ledger.json): five completed `gpt-6-luna` responses, five actual script calls, no editorial regeneration calls.
- [Restart/preservation verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-review-after-restart.json): accepted release and pre-task Owner production rows unchanged; original Case 01 records/history preserved; sources and drafts reopened.
- [Native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/native-tests-final.log): 129/129 PASS. Existing Studio suite remains 31/31 PASS with unchanged Studio source.

![Real native Studio showing the unapproved v2 script](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-review-studio.png)

Ten accepted Phase 8 videos remain immutable and are not counted here. The earlier isolated render-contract MP4 is not counted. No script, storyboard, media or final-video approval has been invented. No TTS/render/publishing action was dispatched for these five candidates.

## Remaining acceptance gates

1. Owner reviews/approves or edits the exact v2 scripts for 01, 02, 04, 06 and 08.
2. Owner reviews proposed scenes and available assets/rights before native production approval. Native production approval covers both narration and selected media, so it is not used to fabricate a script-only decision.
3. Five new videos are generated through the accepted Windows Native pipeline with measured TTS duration, subtitles, preview and final review.
4. Store actual ffprobe/QC and artifact hashes, verify persistence/restart, and record five explicit human watch/listen decisions for the exact final MP4s. Preserve research → final-video lineage.

This task stops now at the script gate required by Owner. No credentials/provider/architecture blocker exists at this checkpoint.

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
