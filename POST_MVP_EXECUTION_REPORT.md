# VF-POST-MVP-ROADMAP-EXECUTION-01 — execution status

Updated: 2026-10-05, Asia/Saigon. Repo: `C:\NPD-Video-Factory\source`. Branch: `codex/vf-post-mvp-roadmap-execution-01`. Implementation HEAD: `6e0c7f6db1eadaa68c880b597e36da64a6f0b018`. Subsequent evidence/report commits do not change application behavior.

**INTERNAL_PRODUCTION_READY = NO.** Phases 0–7 have technical evidence for the supported Windows Native scope. AssemblyAI is connected, and a real speech video produced a persisted transcript with valid native word timestamps. The editor, approval dashboard and frozen brand/template choices are implemented. Phase 8 remains open for production-flow coverage and at least ten actual human-reviewed final videos; technical fixtures do not satisfy that gate.

Windows Native Studio is running at <http://127.0.0.1:8026> with the new implementation. The original project remains revision 9 with approval null. Projects/jobs/events match their pre-upgrade row hash; SQLite integrity is `ok`. Existing accepted MVP video/audio bytes are unchanged. A consistent backup was made before the upgrade at `C:\NPD-Video-Factory\post-mvp-validation\owner-before-roadmap-upgrade-20261005.sqlite3`. Evidence: `evidence/post-mvp-roadmap/phase-3/live-upgrade-before.json` and `live-upgrade-after.json`.

## Phase 0

PHASE: 0 — Discovery / Baseline Lock

STATUS: PASS — baseline recorded before application edits.

HEAD SHA: `fdd660f6b72451b13c74b3d065b329c5093080da`.

FILES CHANGED: `BASELINE_REPORT.md`, `evidence/post-mvp-roadmap/phase-0/`.

TESTS: Native 34/34 and Studio 22/22 PASS; matching legacy renderer reference 26 tests/typecheck/bundle PASS; historical register checks PASS. Full legacy Python collection on Windows failed on three POSIX-only modules. The corrected portable selection reported 1,817 passed, 46 failed, 24 errors, 12 skipped; it is NOT PASS.

EVIDENCE: `BASELINE_REPORT.md`; Phase 0 test summary, runtime preflight, artifact/live-state inventories and logs.

CAPABILITIES ADDED: Baseline/source/runtime/artifact provenance and an execution order tied to actual accepted capabilities.

REGRESSIONS: No application code changed in discovery. Legacy Windows failures are baseline findings.

BLOCKERS: Legacy Windows compatibility, native hardening/multi-input/ASR and later release gates.

NEXT ACTION: Verify the real accepted Windows Native MVP and persistence/failure boundaries.

## Phase 1

PHASE: 1 — Close Windows Native MVP

STATUS: PASS — accepted real MVP artifact and native persistence/failure boundaries verified. This reuses the exact previously Owner-reviewed final candidate; it does not certify a fresh render of the live revision-9 project.

HEAD SHA: `6adcbf84baa6140b86e3ac6f42141f88e2e74a01`.

FILES CHANGED: `scripts/capture-windows-native-mvp-evidence.py`, native MVP acceptance tests, `evidence/windows-native-mvp/`.

TESTS: Native 36/36 PASS; separate-process restart and isolated provider/TTS/render corruption checks PASS. Fresh read-only ffprobe on byte-identical actual MP4 PASS.

EVIDENCE: `evidence/windows-native-mvp/acceptance.md` records A1–A10 and actual provider/Owner receipts. Required input, generated/approved scripts, WAV, MP4, ffprobe and execution log are present locally; existing media ignore rules exclude WAV/MP4 from Git.

CAPABILITIES ADDED: Reproducible accepted artifact verification and restart/failure acceptance coverage.

REGRESSIONS: No production code changed; existing native tests remain passing.

BLOCKERS: Estimated phrase subtitle timing still lacks word alignment; current Owner project remains unapproved. Hardening and later phases remain open at this checkpoint.

NEXT ACTION: Add guarded retries, versioned history, checkpoints, resume and a twenty-job local batch.

## Phase 2

PHASE: 2 — MVP-1 Hardening

STATUS: PASS for the supported Windows Native path. Full legacy Windows regression remains NOT PASS; this is not whole-stack certification.

HEAD SHA: `7f40c2248e9c58838e96075b959d8f7eea214472`.

FILES CHANGED: Native hardening/store/pipeline/server/UI, hardening tests, `scripts/windows-native-hardening-batch.py`, Phase 2 evidence.

TESTS: Native 48/48, Studio 23/23 PASS. Actual 20/20 local FFmpeg jobs PASS with decode/audio/no-black QC and SQLite integrity. Two jobs exercise retry and two exercise resume, with one receipt/output per job.

EVIDENCE: `evidence/post-mvp-roadmap/phase-2/acceptance.md`, `batch-20.json`, `upgrade-compatibility.json`, regression logs. Actual outputs remain in `C:\NPD-Video-Factory\post-mvp-validation\phase2-batch-20261005-1907`.

CAPABILITIES ADDED: Lifecycle/error taxonomy, bounded retry/timeouts, structured logs, immutable version/artifact metadata, verified checkpoints, same-job resume and idempotent publication. Unknown paid outcomes refuse automatic replay. TTS startup/publication can retry transient IO without repeating failed synthesis or changing the accepted preset.

REGRESSIONS: Existing supported native/Studio suites pass; legacy API/renderer implementation is unchanged. Additive upgrade on an isolated copy preserves original rows.

BLOCKERS: The batch reuses the exact real accepted WAV/image with clearly labeled fixture approvals: zero new provider calls/TTS inferences. It is operational recovery evidence, not twenty independent editorial videos or ten Owner-reviewed release candidates. Legacy Windows failures and Phase 3–8 gates remain open at this checkpoint.

NEXT ACTION: Canonical multi-input ingestion while preserving snapshots/original files.

## Phase 3

PHASE: 3 — Multi-input Router

STATUS: PASS for ingestion/routing of all nine requested input families. Real ASR belongs to Phase 4; document support is UTF-8 TXT/Markdown/DOCX with explicit errors for unsupported formats.

HEAD SHA: `177ea75606b6f9ced09b2810979c415a07ec2186`.

FILES CHANGED: `services/windows_native/ingestion.py`, compatible native contracts/store/media/pipeline/server/UI changes, input regression tests, Phase 3 evidence.

TESTS: Native 57/57, Studio 24/24 PASS. Actual isolated browser flow: create → existing script → TXT upload → deterministic script preparation → reload, with exact content persisted at revision 3 and zero provider/TTS calls. Original input byte/hash and MIME/content/security tests PASS. Subsequent live upgrade read-only state/SQLite checks PASS.

EVIDENCE: `evidence/post-mvp-roadmap/phase-3/acceptance.md`, test logs, `ui-verification.json`, `ui-script-document.jpg`, live-upgrade before/after receipts.

CAPABILITIES ADDED: Additive canonical `ProjectInput` projection, provenance/source/version hashes, exact original-media copies, document upload/extraction, script-preserving preparation and explicit workflow routing. Existing approved documents are not rewritten to add the projection. No filename-only semantic guesses or fake transcripts.

REGRESSIONS: Supported native/Studio suites pass. Existing Owner project, jobs/events and accepted MVP artifacts are preserved. The isolated UI helper was stopped after testing; its database/artifacts/logs remain available. Main Studio remains running.

BLOCKERS: Speech transcription/word alignment and Phases 5–8 certification. Historical media uploads without an original byte copy retain their prior evidence; missing provenance is not invented.

NEXT ACTION: Phase 4 readiness, then real ASR integration after the Owner provider decision.

## Phase 4

PHASE: 4 — ASR + Media Understanding

STATUS: PASS for the supported native extraction/transcription/validation/persistence/restart/failure path; editorial draft remains awaiting human review.

HEAD SHA: `6e0c7f6db1eadaa68c880b597e36da64a6f0b018` (native ASR implementation). Connection setup: `4420a9247ac4a1bd533fa740e0c90435b7f3e7d8`; real account connection evidence: `eee3259`.

FILES CHANGED: Native `asr.py`, compatible pipeline/store/ingestion/server/hardening changes, Studio analysis/transcript controls, optional media-analysis records and new ASR job kind, additive `requirements-asr.txt`, meaningful tests and Phase 4 evidence. The existing strict provider/profile implementation is reused unchanged.

TESTS: **77/77 native, 25/25 Studio, 26/26 shared AssemblyAI adapter PASS**; final transport/model/secret validation 11/11 PASS after tightening returned-model checks. Actual isolated browser: analyze real speech video → show transcript/word times → actual server restart/reload → prepare unapproved script without a content-provider call. Native voice/runtime locks and live row/SQLite checks PASS. First shared-adapter test run encountered an inaccessible temp folder; a fresh dedicated validation folder passes all 26, and both logs are retained.

EVIDENCE: `evidence/post-mvp-roadmap/phase-4/asr-acceptance.md`, `connection-real-account.json`, `real-speech-video.json`, `real-transcript.json`, screenshots, test logs and `asr-live-upgrade.json`. Actual isolated DB/extracted WAV/raw provider receipts remain at `C:\NPD-Video-Factory\post-mvp-validation\phase4-real-asr-20261005-2025`.

CAPABILITIES ADDED: Non-CLI bounded video-audio extraction and actual AssemblyAI ASR, native word intervals/confidence, transcript lineage/hashes/checkpoints, GET-only resume of acknowledged jobs, explicit ambiguous-outcome refusal and editable draft preparation from immutable transcript evidence. Technical media dimensions/duration/fps/audio/shot metadata plus measured colour/luminance/orientation descriptors are persisted; semantic Vision claims are not fabricated. Mixed-input content context can use explicitly unverified transcript text.

ACTUAL PROVIDER: One account-authentication GET succeeded after Owner requests “Kết nối AssemblyAI” and “Sử dụng máy tính để lấy key”. Existing benchmark key retrieved through active Chrome UI, encrypted under current-user DPAPI outside Git, protected ACL checked, browser clipboard cleared; no key value printed or recorded and no new credential created. Then **one upload, one transcript creation and three observation GETs** on the exact accepted 25-second MVP video; actual response model `universal-3-5-pro`, language `vi`, 63 positive monotonic in-audio word items. No fallback, automatic paid replay, new OpenAI generation or new TTS inference.

REGRESSIONS: Supported suites pass. Original main project/job/event rows still exactly match a consistent pre-ASR-upgrade backup at `C:\NPD-Video-Factory\post-mvp-validation\owner-before-phase4-asr-upgrade-20261005.sqlite3`; SQLite integrity is `ok`. Accepted MVP MP4/WAV bytes and voice SDK/model/preset/dependency pins remain unchanged. Only the already-pinned shared import dependency `tiktoken==0.12.0` was added with `--no-deps`. The Owner’s original project remains revision 9/unapproved, and its original browser draft was not reloaded or edited.

BLOCKERS / LIMITS: ASR said “cái kênh” where the accepted narration said “cái tên”; original provider text/times remain immutable and human accuracy approval is NOT granted. Word timestamps refer to extracted audio. Semantic Vision is not enabled; measured technical descriptors are the supported media-understanding scope. Newly synthesized narration still uses disclosed phrase-level subtitle estimates. Phases 5–8 and ten human-reviewed final videos remain open.

NEXT ACTION: Continue Phase 5 scene intelligence/auto-editor with measured media and immutable transcript lineage, preserving script/final-video human approval.

Main Studio at <http://127.0.0.1:8026> now runs the verified ASR increment, and the real connection remains verified. No runtime/audio/credential value is copied into Git. Historical missing-key/readiness receipts remain preserved as earlier checkpoints.

## Phase 5

PHASE: 5 — Scene Intelligence / Auto Editor

STATUS: PASS for supported native technical acceptance; final editorial approval remains human-owned.

HEAD SHA: `c95d0a3`.

FILES CHANGED: Native editor/music extensions, compatible store/pipeline/server/hardening, Studio scene/music controls, ten native safety/lineage tests, Studio regression, real-render acceptance script and Phase 5 evidence.

TESTS: 87/87 native, 26/26 Studio PASS. Two real FFmpeg 1080×1920/30 fps renders with five assets, both pan directions/zoom, video start trim/loop, contain/cover, fade/cut, captions, CTA and no-black/audio/decode QC PASS. Exact production ducking filter measured voiced/quiet music amplitude ratio 0.17545. Browser play, auto-plan, source change/save/reload and approval invalidation PASS.

EVIDENCE: `evidence/post-mvp-roadmap/phase-5/acceptance.md`, `editor-real-render.json`, `ui-verification.json`, screenshots and test logs. Actual video/database/original reference inputs remain at `C:\NPD-Video-Factory\post-mvp-validation\phase5-editor-20261005`.

CAPABILITIES ADDED: Rich native planned scenes extend the current scene contract and export reused canonical timeline schema 1.1, including explicit source-loop windows and voice/music tracks. Deterministic hash-verified transcript matching/library rotation, manual fit/motion/trim/transition choices, measured phrase captions, rights-confirmed immutable WAV/MP3 music and measured ducking. Changes invalidate approval before synthesis/render.

REGRESSIONS: Supported native/Studio suites PASS. Existing accepted speech/voice lock and original Owner data are preserved. Generated technical fixtures and exact reused accepted WAV cause zero provider calls or new voice inference; their explicit fixture approvals are not human acceptance.

BLOCKERS / LIMITS: Human visual matching and final watch/listen review are still required. Semantic Vision and new-voice word alignment remain unavailable. Safe areas are internal reference text margins requiring actual platform/device preview, not official TikTok/Reels certification. These two reference videos do not satisfy Phase 8's ten human-reviewed production videos.

NEXT ACTION: Complete Phase 6 project management/history/scene reorder/final render approval and non-CLI walkthrough, then Brand/Templates and the human release gate.

## Phase 6

PHASE: 6 — Approval Dashboard

STATUS: PASS supported native dashboard technical scope. Current production revisions still require actual human content/final approval.

HEAD SHA: `69faa0a`.

FILES CHANGED: Additive dashboard/review tables and guarded native store/server operations, Studio management/history/reorder/final-review/status/download/artifact/folder controls, eight dashboard regressions and explicit isolated browser-fixture harness/evidence.

TESTS: 95/95 native, 27/27 Studio PASS. Actual non-CLI script → five uploads/music → prepare/edit/reorder/history/auto-plan → explicit fixture review → actual render/play → final acknowledgment guard → explicit fixture final decision/exact-hash download → reject/revise/reapprove/rerender → duplicate/archive/restore → actual restart/play PASS. Two real renders pass FFmpeg/QC. Folder opening is tested with an exact derived-path OS-call double; actual browser MP4 download is verified.

EVIDENCE: `evidence/post-mvp-roadmap/phase-6/acceptance.md`, `ui-restart-real-render.json`, three screenshots and regression logs. Actual fixtures/database/outputs at `C:\NPD-Video-Factory\post-mvp-validation\phase6-dashboard-20261005`. All six relevant tables exactly match their pre-restart backup.

CAPABILITIES ADDED: Unapproved duplication with lineage, reversible archive/restore, immutable script history, source/narration edits and scene reorder, content rejection, current preview/errors/status, artifact metadata/download/scoped folder opening and separate final watch/listen approval. Decisions bind exact project/job/revision/snapshot/MP4 SHA. Idempotent unchanged approval avoids invalidating a verified render; rejection advances the revision and cannot transfer acceptance. Final download promotes byte-identical verified candidate output.

REGRESSIONS: Supported suites PASS; stronger playback integrity requires a render checkpoint and actual file hash. Additive tables preserve old project/job/document/approval/version data. Production has no fixture fallback. Two isolated real renders reuse accepted speech and measured sentence activity with explicit scene-ID projection; zero new providers or TTS inference.

BLOCKERS / LIMITS: These test-operator decisions explicitly say `INTEGRATION FIXTURE — NOT OWNER ACCEPTANCE`; they are not human release acceptance. Current revised fixture candidate is final-unapproved. Brand/Templates, full production matrix and ten human-reviewed final videos remain open.

NEXT ACTION: Phase 7 configurable brand profiles/templates, then prepare concrete human-review candidates and close Phase 8 when its actual acceptance records exist.

## Phase 7

PHASE: 7 — Brand / Template System

STATUS: PASS supported native technical scope; seed brand assets are explicit references.

HEAD SHA: `9c3e9e9`.

FILES CHANGED: Frozen BrandProfile/VideoTemplate models and JSON catalog, configured native editor/renderer/store/server, Studio selection controls, seven brand regressions, bounded early-refusal transport fix/regression, four-real-render script and Phase 7 evidence.

TESTS: 103/103 native, 27/27 Studio PASS. Four real FFmpeg renders cover property/news/personal/event purposes and actual 30/45/60-second outputs, all QC PASS. Actual browser NPD/property30 → Vang/personal45 → reload → persisted selection/approval invalidation PASS.

EVIDENCE: `evidence/post-mvp-roadmap/phase-7/acceptance.md`, `brand-real-render.json`, `ui-verification.json`, `studio-brand.png`, extracted render frames and test logs. Real outputs at `C:\NPD-Video-Factory\post-mvp-validation\phase7-brand-20261005`.

CAPABILITIES ADDED: Two named reference brands plus generic profile, twelve portrait templates, validated configurable logo/font/palette/subtitle/CTA/intro/outro/music/safe-margin/disclaimer settings, frozen snapshot hashes, locked voice, exact-duration hold/refuse policy and pre-TTS asset checks. Later catalog edits cannot alter selected snapshots. Style changes preserve source/options/music and invalidate approval; legacy stored documents remain unchanged.

REGRESSIONS: Supported suites PASS. Initial early header rejections exposed Windows TCP resets; the server now flushes/half-closes and drains bounded unread bytes/time, with a 288 KiB regression and original full-audio security tests retained. Main Studio was backed up/restarted; all seven original tables and accepted MP4/WAV match their pre-upgrade values, SQLite integrity `ok`, original Owner revision 9/unapproved. Original browser draft untouched. `live-upgrade.json` records this check.

BLOCKERS / LIMITS: No official logos/assets are fabricated; fonts/palettes/margins are references. Long target holds (8.04/23.04/38.04 seconds after this short reference voice) require pacing review and do not certify useful production content. Four isolated renders use exact accepted WAV with explicit fixture approvals and zero new provider/TTS calls. Ten real human final reviews remain open.

NEXT ACTION: Prepare ten concrete unapproved production review drafts, then actual human script/source review, fresh TTS/render and human watch/listen approval. Keep release readiness NO until the complete Phase 8 matrix is evidenced.

## Remaining phases and release blockers

| Phase | Status in this task | Required next acceptance |
| --- | --- | --- |
| 5 — Scene Intelligence / Auto Editor | PASS technical native scope | Final human viewing and platform/device overlay review remain release requirements |
| 6 — Approval Dashboard | PASS technical native scope | New production content and final decisions remain actual-human steps |
| 7 — Brand / Templates | PASS technical native scope | Official assets absent; reference margins and production pacing require human review |
| 8 — Internal Production Release | NOT RUN | Full input/flow matrix, automated checks, restart recovery, hashes and at least ten final videos with human watch/listen approval |

| Severity | Blocker | Closing evidence |
| --- | --- | --- |
| P0 | None observed in the supported native work; no release certificate is issued | Existing data/artifact integrity remains verified |
| P1 | Ten final human-reviewed production videos and full release matrix absent | Phase 8 acceptance records; twenty fixture jobs do not substitute |
| P1 | Legacy Windows test baseline: 46 failures, 24 errors after excluding POSIX collection blockers | Fix relevant compatibility gaps or document an explicitly accepted supported release scope; never label this suite PASS |
| P2 | Subtitle word alignment and historical original-upload provenance gaps | Real timing/alignment evidence; retain explicit provenance limits for historical media |

This task has created **one real AssemblyAI transcript job and zero new real TTS inferences**, plus one authentication GET, one upload and three transcript-observation GETs. Prior actual provider/TTS receipts remain attributed to the accepted MVP. Provider doubles/faults in unit tests and fixture approvals are never Owner acceptance. No publishing, analytics, autonomous loop, broker, distributed workers or multi-agent orchestration was implemented.
