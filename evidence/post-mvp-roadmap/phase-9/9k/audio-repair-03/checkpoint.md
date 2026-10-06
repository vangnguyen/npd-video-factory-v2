# Phase 9K — Giọng B và năm video đầy đủ

PHASE: 9K — áp dụng giọng B qua pipeline Windows Native hiện có.

STATUS: FIVE_ACTUAL_WARM_B_MP4S_READY_FOR_OWNER_REVIEW. Tám mẫu đầu câu B có human acceptance; năm MP4 đầy đủ mới có 0/5 final approvals.

HEAD SHA: implementation `ebef5131e50641b93e3f7cf3b424dd151ce26d95`; exact preview verification helper `738de151ce5cc50fdbcc55ed3fb75c7618fc9ba9`. Initial actual TTS attempts used `e087b71`; case 04 passed before boundary refinement. Resumed jobs record the exact implementation/source hashes in their receipts. Evidence and subsequent report commits are visible in Git history. Accepted release remains `internal-production-v1`, baseline `f61d8de6545653ea46f8ab5f91e6c0c0c167b7af`.

FILES CHANGED: opt-in warm voice policy/coordinator and focused tests; Owner B receipt and eight real source/timing archives; approval snapshots; five actual MP4/WAV/metadata/QC/timelines; all nine TTS attempt archives including four failures; 25 sampled frames and Studio screenshots; verification and current reports. Core production schema, renderer, frozen voice profile/model/preset/dependencies and existing script/media/lineage are unchanged.

TESTS: 159/159 Native tests PASS; focused boundary suite 25/25 PASS. Historical Studio suite 32/32 PASS; UI source unchanged. Unit fixtures do not count as real provider evidence. Actual production: 5/5 MP4s, Native QC 11/11 each; exact source/approval/script/media/research lineage and archive hashes verified. All 25 retained scene PCM units equal their actual raw source after trimming; eight previously reviewed B sources and cuts match, with at most one PCM LSB difference from the earlier trial's second encoding. Decoded AAC/WAV correlation exceeds 0.999994 at the existing 1.1s offset, with no hard clipping. Five live previews are byte-exact, range seeks PASS and final downloads remain guarded. Fresh-process persistence PASS; main-service restart not performed.

EVIDENCE: [Owner B acceptance](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/owner-B-approval.json), [five videos/WAVs](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/review-bundle.md), [actual verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/actual-verification.json), [audio/preview guards](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/audio-and-preview-checks.json), [fresh-process persistence](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/fresh-process-persistence.json), [159 tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/native-tests-boundary-final.log), [implementation](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/implementation.md).

NEW CAPABILITIES: each later scene starts from the preceding scene's last approved sentence, then removes only that preceding context. Seed 604, speed 1 and the accepted sampling parameters are preserved. Actual local inference is offline; the existing AssemblyAI adapter provides raw native timings outside the inference process. Content-addressed durable caches avoid replaying known generation/provider outcomes. Four first attempts passed generation but failed explicitly at boundary checks; a conservative boundary refinement resumed the same approved jobs without source regeneration. Every failed receipt remains archived. New work across all attempts: 17 local inferences, 12 upload requests, 12 transcript creates and 27 observations. Including the eight earlier reviewed sources, complete source history covers 25 scene inferences and 20 timing transcripts; those totals are not newly billed work. Final passing attempt counters are separately recorded and must not replace the all-attempt totals.

REGRESSIONS: no verified regression to accepted Phase 8 scope. All ten accepted MP4s/evidence/tag/dependencies, 1,034 frozen historical files and original source/audio/video artifacts remain intact. Before-repair workflow rows preserved: 335 events, 35 job-runtime rows, 38 jobs, 117 versions, 18 render reviews and twelve other current projects. Intelligence retains 264 records, 389 versions, 62 decisions and 35 operations. No external publishing.

BLOCKERS: five genuine Owner full-video watch/listen decisions are still required. `Giọng B đạt` approves eight onset excerpts, not whole MP4s. Native timings and signal checks do not prove word accuracy or perceived voice quality. Inspect the onset/name pronunciation in ca 06/cảnh 2 (`Vang Nguyễn`) and ca 08/cảnh 5 (`Đây là dữ liệu lịch sử`): their actual ASR heads differ from approved text, with unique surrounding-word/quiet-gap anchors; raw differences are retained and not treated as narration edits or word-accuracy PASS. Ca 02/04/06 are shorter than the requested targets and require explicit duration acceptance or revision. Main-service stop/restart was previously rejected by automatic approval review before execution (`blocked by policy`); it was not retried. Fresh-process verification is separate from that unperformed restart.

NEXT ACTION: Owner xem/nghe [đúng năm MP4 mới](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/review-bundle.md), kiểm tra giọng/đầu câu/tên riêng/chữ/hình và xác nhận thời lượng, hoặc chỉ rõ bản/đoạn cần sửa. Chỉ sau quyết định thật mới ghi Native final review, xác nhận final download/queue PRODUCED và cập nhật readiness.

| Ca | Revision | Giây thực tế | Mục tiêu | Native QC | Final human approval |
|---|---:|---:|---|---|---|
| 01 | 13 | 33.715 | 30–45s, đạt khoảng | 11/11 PASS | PENDING |
| 02 | 13 | 39.605 | 45–60s, ngắn hơn | 11/11 PASS | PENDING |
| 04 | 13 | 34.615 | 45s, ngắn hơn | 11/11 PASS | PENDING |
| 06 | 12 | 35.475 | 45s, ngắn hơn | 11/11 PASS | PENDING |
| 08 | 12 | 46.866667 | 45–60s, đạt khoảng | 11/11 PASS | PENDING |

Read-only visual audit inspected all 25 sampled static frames and confirmed their frame/contact-sheet/source MP4 hashes. No obvious crop, blank frame, overlap or unreadable main text was found at sheet scale. This does not certify complete moving video, transitions, mobile-size readability or audio. Actual Studio case 04 playback progressed to 30.902313s and was paused, with its final-watch checkbox unchecked; no human listening decision was inferred.

![Studio thật: video mới và bước duyệt cuối chưa xác nhận](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/studio-case-04-final-review.jpg)

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
