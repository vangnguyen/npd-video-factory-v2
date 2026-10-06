# Phase 9K — Final audio/video review register

Current state: WARM_B_VIDEOS_AWAIT_FULL_OWNER_REVIEW. Owner accepted eight B onset excerpts with exact reply “Giọng B đạt”. Five new complete B MP4s exist, but full audio/final acceptance is 0/5. Phase9K has not passed.

Evidence SHA: 7a18ab22c71a92fde3466483252628245099d36f; metadata f9a9411261eaeb1873bb1dc53caf0845520ce5a4. Tested Native application/TTS child: ebef5131e50641b93e3f7cf3b424dd151ce26d95; preview helper 738de15. Parent Studio 9ce137afa8ac62fdb8ce5b35fbba997013adfef3 retains unchanged render code. Following verification/report-only commit is identified in Git history.

Owner's original v2 script and storyboard/media/internal-production approvals remain separate immutable receipts. Initial feedback requests audio revision in all five originals, which retain actual reject decisions. Later specific onset feedback rejects repair01 versions of 01/02/04; 06/08 stay pending. None of these responses claims full five-video watch/listen.

| Case | Original MP4 | Repair01 MP4 | Current B project | New B seconds | Target | QC/integrity/persistence | Full new audio/final |
|---|---|---|---:|---:|---|---|---|
| 01 |REJECTED|REJECTED_ONSETS|13|33.715|30–45s, within|PASS|PENDING|
| 02 |REJECTED|REJECTED_ONSETS|13|39.605|45–60s, below|PASS|PENDING|
| 04 |REJECTED|REJECTED_ONSETS|13|34.615|45s, below|PASS|PENDING|
| 06 |REJECTED|PENDING|12|35.475|45s, below|PASS|PENDING|
| 08 |REJECTED|PENDING|12|46.866667|45–60s, within|PASS|PENDING|

The Owner B receipt binds eight short onsets to the exact combined A/B WAV and per-sample sources/cuts. It approves onset timbre only; full words and full videos remain unaccepted. Reproduction confirms all eight actual B raw sources/cuts are used, with no provider replay. New production approvals cite unchanged approved script/media/internal-production authority and explicitly exclude final approval.

Opt-in warm-scene-context-v1 prefixes the preceding scene's last approved sentence, preserves the locked Thùy Dung/model/preset/sampling/speed and resets seed 604 per scene. Explicit normalization override 4096 keeps the context in one call under 512 characters; accepted default remains 256. First scene has no prefix. A separate child blocks local-inference networking; coordinator uses the existing AssemblyAI adapter outside that block. Actual raw ASR words plus exact canonical prefix/abbreviation or jointly anchored quiet-gap rules determine trimming. Timings remain approximate, not forced alignment. No pitch/speed/EQ/denoiser, new provider/credentials or second renderer is added.

Source history: 25 resolved scene inferences = 8 reviewed B + 17 new local calls for this repair (2/3/2/5/5 by case). 12 new actual ASR uploads/creates and 27 observations are retained. Four boundary failures in 01/02/06/08 were explicit; their generation sources and known paid outcomes were reused when the same approved jobs resumed after correction. Nine TTS attempts (4 failed + 5 pass) retain exact statuses/logs/JSON/WAV/provider receipts. Passing attempts alone used 2 fresh + 23 reused local sources, 5 uploads/creates and 12 observations. Complete source history totals 20 uploads/creates and 43 observations, including eight earlier reviewed-source requests and 16 observations; it must not be described as all newly billed work.

Every new MP4 has 11/11 Native QC, exact source/approval/snapshot/cut/lineage integrity, 159/159 Native suite PASS and actual fresh-process persistence PASS. Historical Studio 32/32 PASS remains applicable to unchanged UI; no new rerun is claimed. All 25 trimmed scene PCM units are sample-exact against their raw sources; reviewed targets differ at most 1 LSB from historical reencoding. Decoded AAC/raw correlation 0.99999478–0.99999564 and decoded peak below 0.901 verify transport, not naturalness. Decoded audio is bound to the actual MP4 SHA. All previews serve byte-exact MP4s and range seeks; final endpoints still deny unaccepted downloads. Queue remains IN_PRODUCTION.

ASR disagreements remain in immutable raw evidence, including CTA “Để lại câu hỏi”, international brand names, ca04 “tách/dữ kiện”, some numbers/abbreviations. They are not proof that the voice reads those words incorrectly; no full word-accuracy PASS or automatic rewrite is claimed. Full cadence/timbre/pronunciation, prefix cuts, estimated phrase subtitles and moving-video pacing need Owner review. Independent sheet-scale inspection of 25 sampled frames PASS does not replace full watch/listen.

Research → idea → approved brief → approved v2 script → reviewed graphics/editor settings → new job/timeline/render lineage is unchanged. 1,034 historical repository evidence hashes, ten Phase8 MP4s/evidence/tag/dependencies, original and repair01 output hashes/reviews, pre-B 38 jobs/335 events/117 versions/18 review rows and 12 other projects are preserved. Intelligence 264 records/389 versions/62 decisions/35 operations and older IHG history remain unchanged.

- [Five exact full B videos/raw voices](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/review-bundle.md) and [exact review manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/review-manifest.json).
- [Owner B sample-only approval/backups](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/owner-B-approval.json), [new production snapshots](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/production-approval-manifest.json), [earlier onset rejections](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-02/owner-negative-decisions.json).
- [Actual source/attempt/count/integrity verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/actual-verification.json), [actual PCM/codec/preview guards](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/audio-and-preview-checks.json), [fresh-process persistence](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/fresh-process-persistence.json).
- [159 Native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/native-tests-boundary-final.log), [32 historical Studio tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/studio-tests-storyboard.log), [current checkpoint](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/checkpoint.md).

![Actual B case01 sampled scenes](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-01/contact-sheet.png)

Main-service stop/restart was previously rejected before execution with “blocked by policy” and was not retried. Actual fresh-process reopen is separately verified. No content has been published.

Remaining gate: Owner watches/listens to the exact five complete B MP4s and approves full voice/words/final result, including below-target durations 02/04/06, or identifies remaining issues. Only genuine exact-artifact final decisions unlock final download, PRODUCED queue and readiness. “Giọng B đạt” and earlier words/media approvals do not replace this final review. No credential/provider/migration/major-replacement blocker exists.

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
