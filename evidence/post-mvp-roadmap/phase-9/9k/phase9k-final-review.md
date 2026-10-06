# Phase 9K — Final audio/video review register

Current state: REPAIRED_VIDEOS_AWAIT_OWNER_LISTENING. The five original MP4s have actual Owner audio-revision decisions; five new versions exist. New audio/final acceptance is 0/5. Phase 9K has not passed.

Evidence SHA: 235e90664dbddd6a820ad751e32e09d7b8ca84a8. Tested application/TTS child: ce21b4ae8f62c65955209abfc87c5beb395b2169. Main Studio parent remains 9ce137afa8ac62fdb8ce5b35fbba997013adfef3 with unchanged render code. Following report-only commit is in Git history.

Owner's actual script reply “Duyệt v2: 01, 02, 04, 06, 08” and storyboard/media reply “Duyệt storyboard/media: 01, 02, 04, 06, 08” remain exact separate receipts. Later actual feedback “Giọng nói giữa các câu không giữ được độ cao âm, bị rè, âm giọng bị xuống thấp” with scope “Nhiều/cả 5 video — kiểm tra toàn bộ” requests audio revision across all five. No complete five-video watch/listen or new positive decision is inferred.

Existing Store.review_render records five negative decisions bound to original MP4/snapshot hashes, with acknowledgement false. Projects move v9 → v10 (negative review) → v11 (explicit speech-context policy). Script reviews remain current. New production approval cites unchanged approved script/media and actual repair request, and explicitly sets new_audio_quality_accepted=false/final_video_approved=false. All original outputs/evidence stay intact.

| Case | Brief/script/media | Original final state | New seconds | Target | Technical/source/integrity/persistence | New audio/final decision |
|---|---|---|---:|---|---|---|
| 01 | OWNER_APPROVED | AUDIO_REVISION_REQUIRED | 34.43 | 30–45s, within | PASS | PENDING |
| 02 | OWNER_APPROVED | AUDIO_REVISION_REQUIRED | 39.97 | 45–60s, below | PASS | PENDING |
| 04 | OWNER_APPROVED | AUDIO_REVISION_REQUIRED | 34.30 | 45s, below | PASS | PENDING |
| 06 | OWNER_APPROVED | AUDIO_REVISION_REQUIRED | 35.38 | 45s, below | PASS | PENDING |
| 08 | OWNER_APPROVED | AUDIO_REVISION_REQUIRED | 46.97 | 45–60s, within | PASS | PENDING |

All five new projects are Native v11. Existing sequential Runner generates 27 fresh local inference calls (5/5/5/5/7), with network blocked, zero retries, Thùy Dung and locked model/preset/sampling parameters, speed 1. Scene context and seed 604 are an explicit opt-in policy; accepted sentence default remains unchanged. No pitch/time manipulation, EQ, denoiser, new paid provider or second pipeline.

Signal/transport verification: raw WAVs have zero measured saturation; decoded MP4s have no hard clipping, correlation >0.99999 with the raw voice at the existing 1.1s offset, and measured scene joins have zero sample jump. These checks do not prove roughness/naturalness or stable perceived timbre. F0 unit boundaries differ; case 08 range increases, so no all-five subjective quality PASS is claimed. Vietnamese lexical tones must remain.

Every new MP4 has actual 11/11 Native QC, exact hash/approval/snapshot/source/lineage checks and fresh-process persistence PASS. All five live previews serve byte-exact MP4s, support range seeking, and final endpoints require genuine human final approval. Queue remains IN_PRODUCTION. Captions use measured scene audio with estimated phrase splits, not word alignment; short cues and pronunciation/cadence require human review. Cases 02/04/06 remain shorter than targets.

Research → idea → approved brief → approved script → reviewed graphics/editor settings → new job/timeline/render lineage remains unchanged. The source, idea/ranking/hook/CTA assessments of ten cases remain in their historical evidence; Codex assessments are not Owner acceptance or performance validation.

- [Five exact revised videos and raw voices](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/review-bundle.md) and [review manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/review-manifest.json).
- [Actual Owner feedback and preservation receipts](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/owner-feedback.json), [repair production approval](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/production-approval-manifest.json).
- [Actual source/artifact verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/actual-verification.json), [audio/preview guards](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/audio-and-preview-checks.json), [fresh-process persistence](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/fresh-process-persistence.json).
- [139 Native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/native-tests.log), [32 Studio tests, UI unchanged](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/studio-tests-storyboard.log), [repair checkpoint](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/checkpoint.md).

![Actual repaired case 01 in Studio, final-watch unchecked](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/native-studio.png)

Codex inspected 25 actual sampled frames and real Studio playback/source/paused state. No full moving-video or audio listening acceptance is claimed. Main-service stop/restart was previously rejected before execution with “blocked by policy”; it was not retried. Actual fresh-process reopen is separate from an unperformed main-service restart.

Ten Phase 8 MP4s/evidence/tag/dependencies remain unchanged. All old job/event/version/review rows, twelve other current projects, old IHG history, 292 frozen Phase 9K files and original raw WAVs are preserved. Two pre-repair backups and current table/project/job/artifact checks are recorded. No content has been published.

Remaining gate: Owner listens/watches all five exact repaired MP4s and approves the voice/final result including the disclosed durations, or identifies the remaining case/segment to revise. Only a genuine positive decision permits final download, PRODUCED queue and readiness. Earlier words/media approvals do not accept new audio. No credential/provider/migration/major-replacement blocker exists.

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
