# Phase 2 — native pipeline hardening

STATUS: PASS for the supported Windows Native path. The legacy Windows incompatibilities recorded at Phase 0 remain open; this is not full legacy-stack or internal-production certification.

## Changes and evidence

- Original project/job/event tables and response fields remain compatible. Two additive tables retain immutable project revisions/component hashes and per-job retry/resume counts. Initial history records only the actual current revision; old versions are not reconstructed or invented. `upgrade-compatibility.json` proves the original project's documents, approval, jobs and events stayed byte-equivalent after upgrade on an isolated consistent SQLite backup.
- Jobs expose CREATED/RUNNING/WAITING_HUMAN/RETRYING/FAILED/SUCCEEDED as `lifecycle`, while retaining existing lowercase status values. Retrying blocks project edits and another dispatch.
- Only a durable HTTP 429 rejection permits one provider retry. SDK hidden retries remain zero, same model/parameters, 15-second connect and 90-second read timeouts. Connection/timeout/500/ambiguous accepted outcomes do not replay automatically. An interrupted job with an unknown paid intent cannot be resumed into another request.
- TTS child startup can retry transient sharing/busy IO once. Failed synthesis, frame-cap/EOS failures and TTS timeouts are not automatically inferred again. Locked preset, runtime, sentence plan, speed and parameters are unchanged. Valid completed child audio is recoverable before parent checkpoint publication; publishing retries do not repeat inference.
- Render timeout retries once in a new isolated attempt directory; transient file IO retries once. TTS subprocess/render calls have bounded timeouts. Valid completed TTS/render/content checkpoints resume without repeating the completed step. Existing differing output bytes are refused rather than overwritten.
- Explicit resume uses the original job ID/idempotency receipt, requires the exact current project revision/document/approval, validates every checkpoint file size/SHA256, and is capped at three manual resumes. Repeated resume clicks keep one queued/running receipt.
- All eight required error categories have actionable guidance. Durable SQLite `job_step` events carry job_id, project_id, step, provider, duration, retry_count and error_code without error body/prompt/credential exposure. `/api/jobs/<id>/logs` exports structured logs; `/api/projects/<id>/versions` exposes revision history. The UI shows retry state and a resume action.
- Checkpoints contain SHA256, file sizes, timestamps, approved snapshot lineage, component versions and render versions. Content/script/storyboard edits invalidate approval as before. No new provider or subsystem was introduced.

Tests: **48/48 native**, **23/23 Studio JavaScript** PASS. Existing 36 native checks remain passing. New cases cover additive legacy upgrade, immutable history, busy retry state, duplicate resume, stale revision, unknown paid outcome, tampered checkpoint, completed content recovery, 429-only provider retry, TTS startup IO retry with later render recovery, permanent IO failure, structured redacted logs and taxonomy. Provider/TTS doubles in unit tests are explicitly test fixtures and are not real-provider acceptance evidence.

## Twenty local jobs

`batch-20.json`: **20/20 actual local FFmpeg render jobs PASS**, all 1080x1920 H.264/AAC with full decode/audio/no-black QC, SQLite integrity `ok`. Every job has one project/job receipt and a verified render checkpoint. Two jobs exercised retry (render timeout and transient output publication); two exercised explicit resume (render failure and interrupted job). All twenty generated actual MP4 outputs.

Reproduce on a fresh directory:

```powershell
C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe scripts/windows-native-hardening-batch.py --data-root C:\NPD-Video-Factory\post-mvp-validation\NEW-BATCH --report evidence/post-mvp-roadmap/phase-2/NEW-REPORT.json --jobs 20
```

The batch deliberately reuses the exact accepted real MVP narration/WAV and source image, with separate **fixture** script approvals. It made zero SDK requests and zero new TTS inferences. Injected faults test recovery, while completed video bytes and QC come from actual FFmpeg. It is twenty operational jobs on the same input, not twenty distinct editorial videos or ten Owner-reviewed release videos. No fixture approval is imported into the Owner project.

The live project remains revision 9, approval null, updated_at `2026-10-05T10:42:34.030478+00:00`; accepted MVP video/audio hashes remain those in Phase 1. Live server upgrade is deferred until the next UI increment is tested, so the current server process continues its loaded implementation.

FILES CHANGED: native hardening helpers/store/pipeline/server, native UI retry behavior, regression tests, reproducible batch script, evidence in this directory.

CAPABILITIES ADDED: durable history/checkpoints, guarded retry/resume, lifecycle/taxonomy/logs, immutable publication and version/lineage metadata.

REGRESSIONS: none observed in the supported native/Studio suites; legacy source/renderer implementation was not changed.

BLOCKERS: native all-input router and real ASR still absent; word alignment and the Phase 5–8 features/release gates remain open. Full legacy Windows suite remains NOT PASS as documented at baseline.

NEXT ACTION: Phase 3, extend the existing ingestion route with canonical prompt/idea/script/document/mixed inputs, preserving current snapshots and immutable originals.
