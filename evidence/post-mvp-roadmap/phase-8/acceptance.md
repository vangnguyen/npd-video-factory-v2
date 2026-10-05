# Phase 8 — Windows Native internal production release

**STATUS: PASS for Windows Native internal production. INTERNAL_PRODUCTION_READY = YES.** All ten actual final videos have actual Owner watch/listen approval bound to the exact files and snapshots. The legacy stack is outside this explicitly accepted certificate.

Ten actual production projects were appended to the main Windows Native Studio, preserving the original Owner project at revision 9/unapproved and every existing row. The original accepted MVP MP4/WAV remain unchanged. Ten exact draft snapshots were presented in `review-bundle.md`. The actual user replied **“duyệt”** to that specific ten-draft question. `owner-script-authorization.json` records the answer, question identity, reviewed bundle hash and all ten project/revision/document hashes. Those delegated human decisions were applied through the real Studio UI with reviewer label **Owner — duyệt qua Codex**. This script/source approval does not authorize final-video acceptance.

The user then explicitly stated **“Đã xem/nghe và duyệt 01–10 cho Windows Native”**. `owner-final-authorization.json` preserves that actual statement, the accepted scope, original review bundle/manifest hashes and all ten exact job/project/revision/snapshot/MP4 identities. Delegated final approvals were applied through the actual Studio UI. All ten now expose the final-download route with the same verified MP4 bytes; no new provider request, voice inference or render was dispatched for final approval. `approved-final-manifest.json` and `final-videos.md` provide the accepted outputs.

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

All ten rows also have actual final watch/listen decisions PASS. These ten are real production renders, separate from the earlier twenty-job operational fixtures and Phase 5–7 reference renders. They use **54 new local voice inference calls**, no fixture audio, no inference retries, exact locked voice profile `f2d848766784e7bd892680f933a799ec812c1c8acff62b019ac777aa1292c4d3`, network blocked in the voice child and speed 1. Voice durations are 25.98, 24.35, 20.60, 19.14, 25.28, 26.94, 21.20, 24.62, 23.88 and 23.23 seconds. Every MP4 is 30 seconds, 1080×1920, 30 fps, H.264/AAC/yuv420p, 48 kHz audio; all decode/audio/no-black/clipping/duration checks PASS. File, voice, input, storyboard, checkpoint and approval hashes bind the actual artifacts.

## Persistence, UI and evidence

- Current production implementation: **103/103 native and 27/27 Studio tests PASS**. No production code changed during this practical release run.
- All four release evidence helpers compile. Before final authorization, actual checks correctly refused readiness at 0/10 final decisions; the historical `technical-gate-verification.json` preserves that gate. After actual final authorization, the certifier and capture helper reuse the same fresh full checks and report YES with 10/10 exact human final decisions. Every certificate check is true; no provider/TTS request is made by these read checks.
- Scoped Git attributes preserve the exact review bundle/JSON receipt bytes, including Windows line endings. Twelve staged blobs and a fresh artifact checkout are verified byte-identical to the original files in `git-review-byte-integrity.json`, so a checkout cannot silently invalidate the bound review hashes. The first scan refused a stale normalized technical receipt; scoped restaging resolved it without modifying any review file.
- Exact new-intake original/derived/document hashes and all ten draft snapshots verified in a fresh process. Previously existing rows retained byte-for-byte; SQLite integrity `ok`.
- Actual production server restarted after all ten renders and zero active jobs. All seven relevant tables, ten content approvals, real TTS/render checkpoints and MP4 hashes match the consistent pre-restart backup. No provider or voice dispatch occurred for restart. Original Owner browser draft was not reloaded or edited.
- After final approval, a fresh process reopens all ten exact final decisions and verified downloads. All preexisting rows in all seven tables are unchanged; exactly ten review rows and ten approval events were appended. SQLite integrity is `ok`, jobs remain unchanged and none is active. Actual Studio reload preserves the final decision. Browser final-download video 10 is byte-identical to its approved MP4; the prior download is preserved. Consistent before/after approval backups and `final-decisions-persistence.json` record this check. No additional server restart after final approval is claimed.
- Actual Studio playback loads 30-second 1080×1920 media without an error; keyboard play confirmed. Main connection UI still shows AssemblyAI verified. The completed isolated dashboard fixture helper was stopped; its files/data/logs remain.
- Evidence: `review-drafts.json`, `owner-script-authorization.json`, `real-candidates.json`, `real-candidates.log`, `real-release-restart.json`, `live-state-integrity.json`, `fresh-process-reopen.json`, `owner-final-authorization.json`, `owner-final-ui-decisions.json`, `final-decisions-persistence.json`, `approved-final-manifest.json`, `release-gate.json`, `release-certification.json`, historical refusal/byte-integrity receipts, per-video extracted frames and actual Studio screenshots including `final-accepted-studio.png`.
- Actual outputs remain under `C:\NPD-Video-Factory\phase2\jobs\<job-id>\final.mp4`; no media was published or pushed externally. `final-review-bundle.md` and its immutable `final-review-manifest.json` identify the exact ten files for human viewing. Final download promotes the same verified bytes rather than rerendering after approval.

## Closed gate and scoped limits

No P0/P1 blocker remains for the accepted Windows Native internal scope. Actual watch/listen decisions, exact file/snapshot bindings, native test/QC matrix, runtime lock, restart/reopen and data integrity evidence are present. `release-certification.json` and `release-gate.json` both report YES.

Outside this accepted scope, the legacy Windows baseline remains **46 failures / 24 errors** after excluding POSIX collection blockers. It is NOT PASS. The user's explicit Windows Native scope decision excludes it from this certificate; no whole-stack release claim is made.

P2: branding/font/palette/logo absence and safe margins remain disclosed references; platform/device preview is needed before publishing. Newly synthesized captions use measured sentence activity and phrase estimates, not word alignment. Historical original-upload byte gaps are retained explicitly. No background music is used in this ten-video run; actual music/ducking acceptance is separately evidenced in Phase 5. The provider ambiguity remains a visible preserved failed job with the explicitly approved local editorial alternative. ASR case 07 retains “cái kênh” from the provider text; it was not silently corrected. Owner final acceptance applies to these exact operational samples, including their disclosed pronunciation/text, pacing and imagery; it does not approve later edits or new projects.

No publishing, analytics, autonomous learning, broker, distributed workers or multi-agent orchestration was added.
