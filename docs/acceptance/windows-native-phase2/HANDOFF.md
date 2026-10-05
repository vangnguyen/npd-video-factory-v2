# Windows Native Phase 2 UI handoff — 2026-10-05

Verdict: **WINDOWS_NATIVE_UI_READY_AWAITING_OWNER_REVIEW**.

The repeatable local workflow is implemented in a separate source worktree,
`C:\NPD-Video-Factory\source`, branch `phase2-windows-native-ui`, based on the accepted
MVP1 source commit `d99ace29e5f0ae5de7394889b56c1f62e1a22a17`.
Open <http://127.0.0.1:8026>. Restart with `scripts\start-windows-native.cmd`.
The [operating guide](../../WINDOWS_NATIVE_PHASE2.md) covers the workflow, tests and configuration.

## Implemented

- Native local UI/API with project persistence, snapshot revisions and multi-image/video library.
- Exactly one selected image or video per scene, with thumbnails and persistent scene choices.
- SQLite durable queue, one worker, idempotency receipts and explicit manual retry.
- gpt-6-luna Content via official SDK with explicit credentials/timeout and zero retries.
- A mandatory human review receipt before TTS, bound to the entire content/library/scene snapshot.
- The exact locked Thùy Dung profile and original model/codec/SDK/runtime parameters.
- FFmpeg MP4 1080×1920, H.264/AAC, player/download after media QC.
- Approval/output invalidation on edits; stale revision and active-job edit rejection.
- Restart of queued work; interrupted dispatched work preserved without automatic replay.
- Windows singleton lock and child-process cleanup on forced server exit.

## Validation

1. **34 Python tests PASS**, including per-scene gates, immutable multi-file upload/thumbnail/ranges,
   stale-upload cleanup, source hash failure before TTS, synthetic TTS and forced-parent-exit cleanup.
2. **22 Studio JavaScript tests PASS**, including scene selections, legacy image compatibility and file types.
3. Full local runtime preflight PASS: locked profile, preset/SDK bytes, SDK commit, local model/codec
   hashes and runtime versions. No provider request in preflight.
4. **One live Content job initiated through the UI PASS**:
   - job `3620e53e06bb4e8aa5e195a95a5d9a60`;
   - project `3a9a98846f14467fba72a6da18ca6276`;
   - returned model `gpt-6-luna`, 1,171 total tokens, zero retries;
   - narration, four scenes and source notes persisted;
   - stopped at `awaiting_review`; no approval or real TTS execution for this new content.
5. UI image upload PASS using the same project image already used in accepted MVP1.
   Current project revision: **3**, human approval: **absent**.
6. UI reload after server restart preserved project, proposal, queue history and image.
   The render control remained disabled before human approval.
7. **Real FFmpeg render regression PASS**, with already accepted MVP1 WAV and image, into
   `C:\NPD-Video-Factory\phase2-validation\render-02\final.mp4`.
   This is an offline render regression, not a new TTS or human-accepted video:
   25 seconds, 1080×1920, 30 fps, H.264/AAC, 48 kHz; full decode, A/V duration, audio
   signal/clipping and black-interval checks passed. Captions preserve narration exactly.
8. The accepted MVP1 final video retains SHA-256
   `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`.
   The original accepted source checkout is clean. No accepted runtime scripts or MVP1 evidence
   were edited, and no synced `sources/` files were touched.

Screenshots and machine-readable results are stored outside Git under
`C:\NPD-Video-Factory\phase2-validation`.

### Multi-image/video increment

- Browser upload of two PNG images plus one MP4 in a single selection PASS, in an isolated
  test data root/server on port 8027. Scene sources saved as image / video / image; thumbnails
  and choices persist after reload and server restart. Review stays blocked while choices are missing or unsaved.
  No owner approval or TTS was created by this browser test.
- **Real FFmpeg mixed-media regression PASS** at
  `C:\NPD-Video-Factory\phase2-validation\mixed-media-regression\final.mp4`:
  red image first, moving video second, blue image third, visible motion across loops,
  silent scene segments and identical output AAC bytes to the single-image regression.
  All existing 1080×1920 / H.264 / AAC / decode / audio / duration / black checks PASS.
- Single-image backwards-compatible FFmpeg regression PASS at
  `C:\NPD-Video-Factory\phase2-validation\single-media-regression\final.mp4`.
- Both regressions reuse the accepted MVP1 WAV, with zero new Content calls, zero new TTS
  inference, no new owner approval and no writes to MVP1.
- Live Studio on port 8026 uses the updated implementation; the existing Cần Giờ proposal
  remains at its latest saved revision (5 at this update) without approval. Existing edits and
  sources were preserved. Test sources were not added to the live project.

## Owner's next step

Open the existing Cần Giờ project in Studio. Upload your images/videos and choose one source
for every scene. Review narration, source notes and headings; save selections/edits.
Enter your reviewer name, acknowledge the review and click
**Duyệt nội dung này**, then **Tạo giọng đọc & video**. No fresh Content call is needed.

Fresh TTS for this proposal and the full newly approved UI render remain pending that real human
decision. The local implementation is ready; a new final video has not been accepted.

## Practical scope

This increment accepts multiple supplied images/videos and one chosen source per scene, with
full-source portrait composition and scene-specific headings. Video starts at the beginning,
loops to fill short clips and mutes original audio. There is no trim editor. Captions have estimated phrase timing within measured sentence
audio; there are no word timestamps. The legacy V2 API/database remains separate. ASR,
auto-publish, analytics and Agent Hub source were not modified. No WSL, Docker or VPS was used.
Local service autostart and an OS reboot persistence test remain outside this increment.
