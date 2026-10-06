# Phase 9K — Five audio revisions, Owner listening pending

PHASE: 9K — actual Owner feedback covering 01, 02, 04, 06, 08

STATUS: REPAIRED_VIDEOS_AWAIT_OWNER_LISTENING; 5/5 real revised MP4s technically verified; new audio/final acceptance 0/5

HEAD SHA: ce21b4ae8f62c65955209abfc87c5beb395b2169, tested application/TTS child. The following evidence commit contains these real outputs. Main Studio parent remains 9ce137afa8ac62fdb8ce5b35fbba997013adfef3 with its unchanged render code; no service restart was performed.

FILES CHANGED: optional Native speech context policy and revision setter, five unit/persistence/failure tests, repair/signal/codec verification helpers; actual Owner negative feedback/backup/approval receipts, five new job snapshots/MP4/WAV/QC/timeline/source manifests, 25 actual frame samples, Studio screenshot and independent process verification. Original outputs and accepted Phase 8 evidence are preserved.

TESTS: 139/139 Native PASS. Studio source unchanged, latest relevant 32/32 PASS. Five actual repaired videos: 11/11 Native QC each; 5/5 artifact/source/lineage/live preview/range seek/final download guards PASS. Fresh-process database/project/job/approval/artifact reopen PASS. No fabricated provider integration or audio acceptance.

EVIDENCE: owner-feedback.json, production-approval-manifest.json, jobs.json, actual-verification.json, audio-and-preview-checks.json, fresh-process-persistence.json, review-bundle.md, review-manifest.json, native-studio.png and case-01/02/04/06/08 output directories.

NEW CAPABILITIES: real Owner negative decisions are bound to the original five MP4/snapshot hashes. All five projects advance from revision 9 to 10 (rejection), then 11 (explicit scene-context-v1 policy). Original script reviews stay current; approved text/graphics/editor settings/research remain byte/hash-identical. Reused production approval cites both the original media/script review and actual audio repair request; it explicitly does not accept new audio or final videos. Existing serial worker generates 27 fresh local TTS calls (5/5/5/5/7), network blocked, zero retries, original model/preset/sampling parameters and speed 1. It renders five distinct new previews through the same editor/FFmpeg pipeline.

REGRESSIONS: no verified change in the accepted Phase 8 release. Ten accepted videos/evidence, release marker, SDK/model/preset/profile/dependencies and prior rows remain intact. The five Phase 9K original videos retain actual audio-quality rejection receipts; technical PASS never proved listening quality. Their MP4s and raw WAVs are unchanged.

BLOCKERS: new subjective audio quality and five final watch/listen decisions require actual Owner review. Cases 02/04/06 remain shorter than requested targets and need explicit acceptance or further revision. This does not become a quality PASS from signal metrics.

NEXT ACTION: Owner hears/watches the exact new versions in review-bundle.md, then approves or identifies remaining issues. Only genuine approval permits final download/PRODUCED/readiness. No publishing.

| Case | Original seconds | Revised seconds | Target | New TTS calls | Technical QC | New human audio/final |
|---|---:|---:|---|---:|---|---|
| 01 | 34.17 | 34.43 | 30–45s, within | 5 | 11/11 PASS | PENDING |
| 02 | 40.47 | 39.97 | 45–60s, below | 5 | 11/11 PASS | PENDING |
| 04 | 36.04 | 34.30 | 45s, below | 5 | 11/11 PASS | PENDING |
| 06 | 36.74 | 35.38 | 45s, below | 5 | 11/11 PASS | PENDING |
| 08 | 47.23 | 46.97 | 45–60s, within | 7 | 11/11 PASS | PENDING |

## Audio verification and limits

Original and revised raw WAVs have no measured saturation. Decoding each actual MP4 back to PCM gives waveform correlation above 0.99999 with the new raw voice at the existing 1.1-second narration offset. Decoded peaks are below 0.9; no hard clipping, time stretching or pitch shifting is detected. All measured scene joins have zero sample jump. This establishes transport/joins, not whether the model sounds rough or natural.

Measured ranges of unit median F0 (semitones) are original → revised: 01 1.633 → 1.515; 02 1.465 → 1.101; 04 3.827 → 0.955; 06 1.711 → 1.361; 08 0.945 → 1.938. Unit boundaries change from sentences to scenes; these are descriptive diagnostics, not a controlled proof of voice stability. Case 08's range increases, so there is no claim that every metric or all audible defects improved. Vietnamese tone variation must remain; no pitch flattening/raise, slowdown, EQ or denoising was added. The lower-temperature trial is experimental only; production keeps locked 0.8.

Scene grouping reduces independent short speech contexts while preserving exact words. SDK splitting still occurs for longer text (case 08 has seven calls for five scenes). It cannot guarantee one uninterrupted model context per whole video. Captions still use measured scene audio and estimated phrase splits; words are not aligned. Very short phrase cues and pronunciation/cadence require review; sampled screenshots do not validate complete subtitle timing or auditory quality.

## Persistence and preservation

Two consistent pre-repair backups are hash-bound in the actual Owner receipt. All 33 existing jobs, 287 events, 104 project versions and 10 prior final review rows remain identical; only the five authorized current project rows change. Twelve other current projects remain identical. All 264 intelligence records, 389 versions, 62 decisions and 35 operations are unchanged. The 292 frozen historical Phase 9K files match their recorded hashes. Existing accepted Phase 8 rows and earlier Owner IHG history remain intact.

Both databases and all five new projects/approvals/jobs/artifacts reopen correctly in a separate verification process, with identical table and case-state hashes. The earlier main-service stop/restart was rejected before execution as “blocked by policy”; no retry or workaround was used, and no main-service restart PASS is claimed. Fresh TTS children are the existing normal dispatch path, not replacement video orchestration.

## Actual Studio and visual scope

![Actual revised case 01 and unchecked final acceptance](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/native-studio.png)

The real Studio video source is job 40428232bdb940b8abdabb00e5043c95. It starts playback and pauses at 13.238614 seconds, duration 34.433333; the final-watch checkbox remains unchecked. Codex inspected 25 frames via the five contact sheets. No full watch/listen acceptance is claimed.

[All five exact new videos and raw audio](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/review-bundle.md).

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
