# VF-POST-MVP-ROADMAP-EXECUTION-01 — execution status

Updated: 2026-10-05, Asia/Saigon. Repo: `C:\NPD-Video-Factory\source`. Branch: `codex/vf-post-mvp-roadmap-execution-01`. Implementation HEAD: `177ea75606b6f9ced09b2810979c415a07ec2186`. Subsequent evidence/report commits do not change application behavior.

**INTERNAL_PRODUCTION_READY = NO.** Phases 0–3 have evidence for the supported Windows Native scope. Phase 4 is stopped at the Owner credential/provider decision. Phases 5–8 have not been implemented or certified by this task. This is a progress report, not an internal production release certificate.

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

STATUS: BLOCKED — Owner decision required; actual speech-video acceptance NOT RUN.

HEAD SHA: `177ea75606b6f9ced09b2810979c415a07ec2186` (implementation at readiness check).

FILES CHANGED: Phase 4 readiness/acceptance evidence only; no provider configuration or application edits.

TESTS: Read-only profile and credential-presence inspection. No ASR request, extracted acceptance transcript or timestamp acceptance occurred. Existing passing regression results remain unchanged.

EVIDENCE: `evidence/post-mvp-roadmap/phase-4/provider-readiness.json`, `acceptance.md`.

CAPABILITIES ADDED: Readiness evidence. Explicit unavailable-ASR errors already prevent fake transcripts.

REGRESSIONS: No application change in this phase.

BLOCKERS: Existing selected AssemblyAI profile has no Windows credential. Existing OpenAI transcription adapter is available as an alternative requiring selection/ASR-charge authorization. Credential values were not read or printed.

NEXT ACTION: Owner chooses OpenAI ASR with the existing saved key, or securely connects AssemblyAI. Reuse the chosen existing adapter and complete real speech extraction/transcription/timestamp/persistence/restart/failure evidence before PASS.

The pause follows the task's explicit STOP CONDITIONS: “cần secret/credential chưa có” and “cần trả phí provider mới”. The asynchronous Owner question is pending. No answer or elapsed time is treated as approval.

## Remaining phases and release blockers

| Phase | Status in this task | Required next acceptance |
| --- | --- | --- |
| 5 — Scene Intelligence / Auto Editor | NOT STARTED | At least five assets, deterministic matching/timeline/motion/trim/subtitles/transitions/music ducking/CTA/safe-area, editable selection and actual QC-passing render |
| 6 — Approval Dashboard | PARTIAL existing UI; full phase NOT CERTIFIED | Duplicate/archive/history/storyboard reorder and final approval; complete non-CLI user walkthrough |
| 7 — Brand / Templates | NOT STARTED | Configurable NPD/Vang Nguyễn profiles and templates; reference configs where official assets are missing |
| 8 — Internal Production Release | NOT RUN | Full input/flow matrix, automated checks, restart recovery, hashes and at least ten final videos with human watch/listen approval |

| Severity | Blocker | Closing evidence |
| --- | --- | --- |
| P0 | None observed in the supported native work; no release certificate is issued | Existing data/artifact integrity remains verified |
| P1 | ASR provider/credential decision and real speech transcript/timestamps absent | Actual provider test, valid timestamps, persisted lineage, restart/failure proof |
| P1 | Scene Intelligence, complete Approval Dashboard and Brand/Template gates unfinished | Phase 5–7 implementation, tests and user walkthrough |
| P1 | Ten final human-reviewed production videos and full release matrix absent | Phase 8 acceptance records; twenty fixture jobs do not substitute |
| P1 | Legacy Windows test baseline: 46 failures, 24 errors after excluding POSIX collection blockers | Fix relevant compatibility gaps or document an explicitly accepted supported release scope; never label this suite PASS |
| P2 | Subtitle word alignment and historical original-upload provenance gaps | Real timing/alignment evidence; retain explicit provenance limits for historical media |

This task has made **zero new paid provider calls and zero new real TTS inferences**. Prior actual provider/TTS receipts remain attributed to the accepted MVP. Provider doubles/faults in unit tests and fixture approvals are never Owner acceptance. No publishing, analytics, autonomous loop, broker, distributed workers or multi-agent orchestration was implemented.
