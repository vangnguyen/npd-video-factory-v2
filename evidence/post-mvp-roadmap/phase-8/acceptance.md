# Phase 8 — actual native production candidates

**STATUS: technical matrix PASS; actual human final-video approval pending. INTERNAL_PRODUCTION_READY = NO.**

Ten actual production projects were appended to the main Windows Native Studio, preserving the original Owner project at revision 9/unapproved and every existing row. The original accepted MVP MP4/WAV remain unchanged. Ten exact draft snapshots were presented in `review-bundle.md`. The actual user replied **“duyệt”** to that specific ten-draft question. `owner-script-authorization.json` records the answer, question identity, reviewed bundle hash and all ten project/revision/document hashes. Those delegated human decisions were applied through the real Studio UI with reviewer label **Owner — duyệt qua Codex**. This script/source approval does not authorize final-video acceptance.

## Actual input and flow matrix

| Case | Input | Actual content preparation | Actual downstream result |
| --- | --- | --- | --- |
| 01 | Prompt | One real OpenAI response | Owner script approval → storyboard → fresh Thùy Dung → 30-second MP4/QC PASS |
| 02 | Idea | One real OpenAI response | Same actual native flow PASS |
| 03 | Existing script | Exact accepted MVP narration prepared locally; zero new provider request | Fresh synthesis/render PASS; earlier accepted audio is not reused |
| 04 | Image with brief | One real provider attempt refused with CONTENT_AMBIGUOUS_RESPONSE; preserved, never replayed. Explicit local editorial alternative prepared and disclosed before Owner approval | Approved alternative → fresh synthesis/render PASS; no provider output is fabricated |
| 05 | Multiple images | One real OpenAI response; accepted portrait plus frame derived from rights-confirmed original video, with exact lineage | Native flow PASS |
| 06 | Silent video | One real OpenAI response; six-second derivative with source audio removed and recorded lineage | Native flow PASS |
| 07 | Speech video | Byte-identical actual MVP speech video and unchanged real AssemblyAI analysis/transcript imported with original source project/job/hash lineage; zero fresh ASR requests | Exact transcript prepared for Owner review → fresh synthesis/render PASS |
| 08 | Mixed media | One real OpenAI response using image/video plus unverified source-note document | Native flow PASS |
| 09 | Text/document | One real OpenAI response using the source-note document and brief | Native flow PASS |
| 10 | Multiple videos | One real OpenAI response using two actual source files; original source speech muted in output | Native flow PASS |

These ten are real current candidate renders, separate from the earlier twenty-job operational fixtures and Phase 5–7 reference renders. They use **54 new local voice inference calls**, no fixture audio, no inference retries, exact locked voice profile `f2d848766784e7bd892680f933a799ec812c1c8acff62b019ac777aa1292c4d3`, network blocked in the voice child and speed 1. Voice durations are 25.98, 24.35, 20.60, 19.14, 25.28, 26.94, 21.20, 24.62, 23.88 and 23.23 seconds. Every MP4 is 30 seconds, 1080×1920, 30 fps, H.264/AAC/yuv420p, 48 kHz audio; all decode/audio/no-black/clipping/duration checks PASS. File, voice, input, storyboard, checkpoint and approval hashes bind the actual artifacts.

## Persistence, UI and evidence

- Current production implementation: **103/103 native and 27/27 Studio tests PASS**. No production code changed during this practical release run.
- All four release evidence helpers compile. Actual capture/certifier execution validates the ten current file/snapshot/checkpoint bindings and correctly refuses readiness with 0/10 human final decisions. `technical-gate-verification.json` records the consistent matrix status, preserved review hashes and credential-pattern scan; no provider/TTS request is made by these read checks.
- Scoped Git attributes preserve the exact review bundle/JSON receipt bytes, including Windows line endings. Twelve staged blobs and a fresh artifact checkout are verified byte-identical to the original files in `git-review-byte-integrity.json`, so a checkout cannot silently invalidate the bound review hashes. The first scan refused a stale normalized technical receipt; scoped restaging resolved it without modifying any review file.
- Exact new-intake original/derived/document hashes and all ten draft snapshots verified in a fresh process. Previously existing rows retained byte-for-byte; SQLite integrity `ok`.
- Actual production server restarted after all ten renders and zero active jobs. All seven relevant tables, ten content approvals, real TTS/render checkpoints and MP4 hashes match the consistent pre-restart backup. No provider or voice dispatch occurred for restart. Original Owner browser draft was not reloaded or edited.
- Actual Studio playback loads 30-second 1080×1920 media without an error; keyboard play confirmed. Main connection UI still shows AssemblyAI verified. The completed isolated dashboard fixture helper was stopped; its files/data/logs remain.
- Evidence: `review-drafts.json`, `owner-script-authorization.json`, `real-candidates.json`, `real-candidates.log`, `real-release-restart.json`, `live-state-integrity.json`, `fresh-process-reopen.json`, `release-certification.json`, `technical-gate-verification.json`, per-video extracted frames and actual Studio screenshots including `final-review-preview.png` at 9.6 seconds of video 01.
- Actual outputs remain under `C:\NPD-Video-Factory\phase2\jobs\<job-id>\final.mp4`; no media was published or pushed externally. `final-review-bundle.md` and its immutable `final-review-manifest.json` identify the exact ten files for human viewing. Final download promotes the same verified bytes rather than rerendering after approval.

## Open gate and scoped limits

P1: actual watch/listen final decisions for all ten exact candidates are absent at this checkpoint. The separate final question asks for those decisions and acceptance of **Windows Native internal production only**. Until the actual records exist, release readiness stays NO.

P1: the legacy Windows baseline remains **46 failures / 24 errors** after excluding POSIX collection blockers. It is NOT PASS and is outside the proposed native certificate; an explicit native scope decision is required. No whole-stack release claim is made.

P2: branding/font/palette/logo absence and safe margins are disclosed references; platform/device preview is needed before publishing. Newly synthesized captions use measured sentence activity and phrase estimates, not word alignment. Historical original-upload byte gaps are retained explicitly. No background music is used in this ten-video run; actual music/ducking acceptance is separately evidenced in Phase 5. The provider ambiguity remains a visible preserved failed job. ASR case 07 retains “cái kênh” from the provider text; the reviewed draft was not silently corrected. Human final viewing must judge that pronunciation/text, pacing, image matching and the operational sample topics.

No publishing, analytics, autonomous learning, broker, distributed workers or multi-agent orchestration was added.
