# Phase 1 — Windows Native MVP

STATUS: PASS for the accepted Windows-native MVP and the supported native persistence/failure boundaries. One actual Owner-reviewed final candidate exists. This package verifies and reuses that candidate; it does not claim a fresh live run of the current UI project's revision 9.

Source task: VF-MVP1-WINDOWS-NATIVE-FASTPATH-26. Source output: `C:\NPD-Video-Factory\outputs\MVP1`. Exact artifacts were copied without modifying the originals. Reproducible verification: `runtime\venv\Scripts\python.exe scripts/capture-windows-native-mvp-evidence.py`. An existing differing evidence file causes an explicit error, not overwrite.

| Gate | Status | Evidence |
| --- | --- | --- |
| A1 real provider prompt → script | PASS | `input.json`, actual OpenAI Responses id `resp_004762c771ea37fc016ac35f375afc87d0a708b0db87322c92`, HTTP 200, gpt-6-luna, usage 1,149 tokens; original one content attempt, zero retry |
| A2 stored/versioned script | PASS | `generated_script.json`; immutable script version `sha256:91bb3ef2f759233fbba07542102d5c08588a4b8d04de39a139f87ff797f953bb`, approved version links exact proposal/narration hashes; native project revision/CAS tests pass. Full browseable version history belongs to Phase 2 |
| A3 human edit + approve | PASS | Native edit/invalidation/stale-version/HTTP approval gate tests; actual `owner-content-approval.json` binds the exact accepted narration, approved 2026-10-05T08:37:07.221253+00:00 |
| A4 real Thùy Dung TTS | PASS | `tts.wav`, `tts-metadata.json`: four actual locked local inference calls, all utterances reached EOS, no retry, 20.86-second mono/48 kHz WAV |
| A5 actual 1080x1920 MP4 | PASS | `final.mp4`, `render-manifest.json`: real native FFmpeg H.264/AAC, 25 seconds, 750 frames |
| A6 valid audible audio | PASS | Original `qc-report.json`: audible speech, finite decoded audio, no hard clips, RMS -18.96 dBFS, peak -1.92 dBFS |
| A7 ffprobe | PASS | New read-only `ffprobe.json` on the copied byte-identical accepted MP4; original full audio/video decode and blackdetect passed |
| A8 app restart retains state | PASS | Existing queued/interrupted restart test plus `test_separate_process_restart_keeps_exact_document_and_revision`: two separate fresh processes read the same saved project/document/revision |
| A9 provider/TTS/render fault cannot corrupt project | PASS | Isolated fault tests for all three stages preserve document/revision/approval fingerprint, SQLite integrity `ok`, durable failed job and successful subsequent edit; no real provider result is simulated as acceptance |
| A10 human-reviewed final candidate | PASS | Actual `owner-final-video-approval.json`, Owner message “Duyệt”, recorded 2026-10-05T08:53:42.566299+00:00 for exact final SHA256 |

Native suite: **36/36 PASS**, including the two added persistence/failure acceptance checks and original 34 tests. Studio baseline remains 22/22 PASS; no web or production application behavior changed in this phase. The first run of the new test had a Windows temp cleanup error because the test's integrity-check connection was left open; the fixture now explicitly closes it. That failed local log is preserved in `evidence/post-mvp-roadmap/phase-0/native-phase1-tests.log`; it is not counted as a passing run.

The MVP final video SHA256 is `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`; TTS SHA256 is `2b5f57c31c2514683a6465e408b2cbe20e949cc9e3921a84f68c28ab983a73e5`. `artifact-manifest.json` records file sizes, hashes and lineage. MP4/WAV are present locally but excluded from Git by the existing media ignore rules.

Current revision 9 in the UI has no Owner approval and no scene assignments. The existing approval applies solely to the exact accepted MVP bytes/narration. This evidence neither changes that project nor dispatches its TTS/render. The new task has made zero paid requests and zero real TTS inferences while closing this gate.

Limits: subtitles retain estimated phrase timing inside measured sentences; word alignment remains open. Source project render is labeled illustrative. No publishing authorization, ASR acceptance, twenty-job batch, or internal production release is inferred. Legacy Windows test failures are recorded in Phase 0 and remain open.

CAPABILITIES ADDED: reproducible accepted-artifact verification/package and cross-process/fault acceptance checks.

REGRESSIONS: none observed in the supported native suite. BLOCKERS: Phase 2 hardening, Phase 3 canonical ingestion, real Phase 4 ASR, Phase 5–8 editing/dashboard/profiles/release matrix remain open. NEXT ACTION: backward-compatible native hardening and an isolated twenty-job batch.
