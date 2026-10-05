# VF-POST-MVP-ROADMAP-EXECUTION-01 — Phase 0 baseline

Captured 2026-10-05, Asia/Saigon, before changing application code.

## Repository lock

| Item | Baseline |
| --- | --- |
| Active source | `C:\NPD-Video-Factory\source` |
| Branch on discovery | `phase2-windows-native-ui` |
| HEAD | `1a8744e496449d3088ee39f77b34564116696633` |
| Tracked working tree on discovery | CLEAN |
| Untracked files on discovery | None |
| Current task's new files | This report and `evidence/post-mvp-roadmap/phase-0/`; all are discovery/test evidence |
| Running application | Windows Native Studio, `http://127.0.0.1:8026` |
| Application data | `C:\NPD-Video-Factory\phase2\workflow.sqlite3`, isolated from accepted MVP1 |
| Accepted MVP output | `C:\NPD-Video-Factory\outputs\MVP1` |

The chat's starting directory, `C:\Users\PC\Documents\ChatGPT\Video Factory`, contains an empty Git repository with an unborn master branch. It is not the application source. An older checkout at `C:\Users\PC\Documents\Codex\2026-09-28\ti-p-t-c-vf-executor\work\vf-mvp1-real-provider-enablement-01` is clean at `d99ace2` on `codex/vf-mvp1-vieneu-tts-01`. The other completion checkout, `C:\Users\PC\Documents\Codex\2026-09-30\task\video-factory-completion`, is clean at `d42cb40` on main and predates the native implementation. Neither is the target of application edits.

No existing user change was overwritten. No reset, rebase, force push, branch deletion, or artifact deletion was performed. Initial tests run in the older checkout were moved to this task's `legacy-reference` evidence directory and identified as reference tests. The newer source was then tested separately. No applicable AGENTS.md was found.

## Documents and history reconciled

Read README, ARCHITECTURE, TESTING, MVP1_MULTI_INPUT, MEDIA_INTELLIGENCE, AUTO_EDIT_STUDIO, PRODUCTION_HARDENING, the master roadmap/gap register, Thùy Dung/provider/integration handoffs, WINDOWS_NATIVE_PHASE2, and `docs/acceptance/windows-native-phase2/HANDOFF.md`. Historical approval and acceptance records are evidence, not authorization for a different script or video. The current task's deferred Publishing/Analytics/Autonomous scope overrides older roadmap sections.

Relevant history:

| Commit | Capability/evidence |
| --- | --- |
| `1a8744e` | Per-scene image/video sources in Windows Native Studio; 34 native and 22 web tests in its handoff |
| `4e388d1` | Repeatable Windows native UI, SQLite project/revision state, human approval binding, single worker, real direct SDK/TTS/FFmpeg pipeline |
| `d99ace2` | Owner-selected locked Thùy Dung voice and artifact-bound review |
| `f642e48`, `e521350` | VieNeu HTTP binding and pinned local preset TTS |
| `0eaa865`, `3b0db4a` | Responses reasoning binding, provider configuration, no reuse of ASR gate as TTS evidence |
| Earlier multi-input/media/ASR/dashboard work | Present in the legacy API/worker/renderer and reviewed through docs, tests, adapter source and acceptance records; it does not establish native UI availability |

`renderer` tree is `f06cefe1a5c5bf47d7bbea542a90632d9f39f50a` at both current HEAD and `d99ace2`. `apps/api` tree is `b8a88d43d527698fc5df61e10d8906c2ce7f534d` at both. This supports reuse of component test results on identical trees; it does not imply an entire older checkout certified the new HEAD.

## Tests at baseline

| Check | Result and scope |
| --- | --- |
| Native Python unittest | PASS: 34/34 at current HEAD; temporary roots, injected SDK/TTS doubles for fault/contract tests, no real paid dispatch |
| Studio JavaScript | PASS: 22/22 at current HEAD |
| Locked native runtime preflight | PASS; native Windows, exact voice/model/runtime/artifact verification, provider_calls=0 |
| Legacy renderer tests | PASS: 26/26 on identical renderer tree in reference checkout |
| Legacy renderer TypeScript/bundle | PASS on identical tree; bundle produced successfully |
| Historical repository register | PASS: 60 matrix rows, 16 gaps, 13 schemas, 77 approval records, 3 rights records, 39 evidence runs; structural validation only |
| Legacy Python compile | PASS on unchanged API/worker/bridge code |
| Full legacy pytest collection on Windows | FAIL: 3 modules import POSIX `grp`, unavailable on native Windows |
| Portable legacy pytest, excluding those 3 modules | 1,817 passed, 46 failed, 24 errors, 12 skipped, 1,899 collected; NOT PASS |

Portable regression used a new, isolated temp directory, FFmpeg on PATH, and an external socket-connect blocker while permitting loopback. Failures include Linux path/custody/systemd assumptions, Windows symlink privileges, and legacy rendering/asset-boundary behavior. Details, test identifiers and concise error messages are in `test-summary.json`; none is attributed to a new application change because no application code had been changed. They remain open compatibility findings until individually resolved or explicitly scoped to the supported runtime.

Two earlier portable attempts were invalidated by environment setup (an inaccessible shared pytest temp root, then an absent parent for a fresh temp directory). Their logs/XML remain locally preserved in `legacy-reference`; they are not substituted for the corrected run. The corrected run is the table above. Large raw failure reports are locally ignored to keep the baseline commit reviewable; their SHA256 and sizes are recorded in `test-summary.json`.

Evidence: `evidence/post-mvp-roadmap/phase-0/{native-tests.log,studio-tests.log,test-summary.json,runtime-preflight.json,live-state.json,artifact-inventory.json,tracked-file-inventory.txt}` plus the labeled reference reports.

## Runtime inventory

Windows desktop, Python 3.12.14, Node 24.19.0, Git 2.53.0, FFmpeg/ffprobe 9.0.2. FFmpeg binaries are available by absolute configured path. npm is not on the global PATH; installed reference renderer dependencies and the bundled Node executable were used.

The accepted native venv is `C:\NPD-Video-Factory\runtime\venv`: OpenAI SDK 3.24.0, httpx2 2.13.1, VieNeu 3.8.3, ONNX Runtime 1.30.0 CPU, NumPy 2.5.3, sea-g2p 0.9.1, Pillow 12.3.0. A separate `runtime\post-mvp-venv` holds the declared API/worker/bridge test dependencies; the accepted voice venv was not modified.

Thùy Dung profile SHA256: `f2d848766784e7bd892680f933a799ec812c1c8acff62b019ac777aa1292c4d3`. Model revision `61b85e3d937fbbacb387714180e8182823512523`, codec revision `ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae`, SDK source commit `85344322b7258b4e25479b692e8e3396baf9db34`. Locked preset, parameters, sentence plan, no proper-name rewriting, and no hidden inference retry are retained.

The existing OpenAI credential file is present outside Git at `C:\NPD-Video-Factory\secrets\openai.env`. Its value was not read, printed or copied during discovery. No WSL, Docker, Broker or Cloud Network Secret was used. Current roadmap discovery incurred zero provider calls and zero TTS inference calls.

## Native MVP and newest state

The original real fastpath is `COMPLETE_OWNER_ACCEPTED`: real direct OpenAI Responses → stored proposal → Owner-approved narration → four local Thùy Dung inferences → FFmpeg → 25-second 1080x1920 H.264/AAC MP4. Technical QC and Owner acceptance are separate records. Owner final-video approval was recorded at `2026-10-05T08:53:42.566299+00:00` for the exact final video SHA256 below. This is one accepted final candidate, not ten production trials.

Current SQLite was inspected read-only and reports integrity `ok`. It has one project (`3a9a98846f14467fba72a6da18ca6276`, Vinhomes Green Paradise Cần Giờ), revision **9**, a generated proposal, two media assets, no scene assignments, and **no approval**. Three real content jobs await review; no job is queued/running. The handoff's revision 5 is historical. Do not import the old MVP approval into this revision or dispatch its TTS until the human has reviewed its concrete document/source choices.

Latest outputs:

| Artifact | SHA256 | Meaning |
| --- | --- | --- |
| `outputs/MVP1/final.mp4` | `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a` | Real accepted final video, 25 s, 1080x1920/30 fps, H.264/AAC, 11,467,955 bytes |
| `outputs/MVP1/voice.wav` | `2b5f57c31c2514683a6465e408b2cbe20e949cc9e3921a84f68c28ab983a73e5` | Real locked Thùy Dung audio, 20.86 s, mono/48 kHz |
| `phase2-validation/single-media-regression/final.mp4` | `730409c3844186f7b4a9552a2a1884516ac3e787f58d0dfa6377bc3d23e3341a` | Local renderer regression using accepted WAV; no fresh TTS or Owner approval |
| `phase2-validation/mixed-media-regression/final.mp4` | `aeca2c096f0a8731e23357894ff7cdc7ba3e2ca165476abdaa675503f8a5b053` | Synthetic red/image, moving video, blue/image fixture; real FFmpeg output; no Owner approval |

Complete sizes/timestamps/hashes of these and the other render-02 output are in `artifact-inventory.json`. MULTI_MEDIA_RESULTS records actual browser uploads/reload/restart on an isolated data root, valid real MP4 QC, source audio muted, and zero new TTS/provider calls for that increment. It is not a speech-video/ASR or human final acceptance report.

## Capabilities PASS

- Real Windows-native direct SDK/content, locked local TTS, 1080x1920 FFmpeg and ffprobe/full decode/audio QC, with one artifact-bound Owner-reviewed MVP output.
- Project creation/list/open, edit/revision CAS, explicit human script approval, invalidation on edits, idempotent dispatch, serialized jobs and restart persistence in the native UI/store.
- Multi-image/video immutable originals with hashes, MIME/content checks, preview thumbnails, per-scene source selection and real image/video/image rendering.
- Loopback authentication/CSRF/origin protections, process-tree containment, interrupted jobs not silently replayed, explicit errors.

## Capabilities PARTIAL / blockers

| Priority | Gap | Roadmap phase |
| --- | --- | --- |
| P1 | Native current project lacks scene assignments and human approval; no real TTS/render of that new proposal has been accepted | 1 / 6 |
| P1 | No persisted immutable input/script/storyboard/render history; only current revision and dispatched snapshots | 2 |
| P1 | No bounded safe retry/checkpoint resume; running jobs become interrupted, paid outcomes must remain protected | 2 |
| P1 | Native lifecycle, structured logs, actionable taxonomy and complete artifact lineage need hardening; 20-job batch not yet run | 2 |
| P1 | Native router lacks idea/script/document ingestion and canonical all-input representation | 3 |
| P1 | Native ASR absent; video original speech is muted. Legacy adapters/evidence do not satisfy a real native speech-video acceptance | 4 |
| P1 | Word alignment open; captions use measured sentences with estimated phrase timing | 4 / 5 |
| P1 | Native auto matching, crop/motion, trims, transitions, music ducking and editable canonical storyboard incomplete | 5 |
| P1 | Dashboard duplicate/archive/history/reject/storyboard reorder/final approval/system status incomplete | 6 |
| P2 | Brand/template abstraction and reference seeds missing; official assets not assumed | 7 |
| P1 | No full release matrix or ten human-reviewed final videos | 8 |
| P1 | Full legacy regression suite is not Windows compatible/PASS; preserve exact baseline and triage before claiming release | 2 / 8 |

No evidence supports `INTERNAL_PRODUCTION_READY = YES`. Current baseline verdict: **NO**.

## Execution order and protection

1. Close Phase 1 with exact real accepted artifacts, provenance/version bindings, and isolated restart/failure evidence. Distinguish the accepted fastpath from the pending native UI revision; do not silently fabricate approval or re-run paid calls just to fill a folder.
2. Add backward-compatible native hardening: optional/additive state, bounded safe retries, verified checkpoints, history/lineage and twenty isolated local jobs. Unknown paid request outcomes must never auto-replay.
3. Extend the existing native ingestion model; reuse validated immutable media handling.
4. Reuse existing ASR/vision abstractions where applicable. Require a real available provider, valid timestamps and persisted transcript. Stop for a missing credential or new paid provider; never manufacture a transcript.
5. Complete deterministic scene editing, dashboard and profiles in order.
6. Certify the requested real release matrix and ten final human reviews; report NO with concrete blockers until those gates pass.

Use small commits on a `codex/` task branch. Keep accepted MVP files, existing project documents and approvals intact. Additive compatible schema changes may be tested against an isolated SQLite backup; incompatible migration/public API/architecture changes, missing secrets, a new paid provider, risk to current data, irreversible actions or production publishing require stopping and notifying Owner under the task's STOP CONDITIONS.
