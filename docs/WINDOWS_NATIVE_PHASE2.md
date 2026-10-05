# Video Factory Phase 2 — Windows Native UI

Source checkout: `C:\NPD-Video-Factory\source`, branch `phase2-windows-native-ui`.
Baseline: `d99ace29e5f0ae5de7394889b56c1f62e1a22a17` and the accepted MVP1 runtime.

This increment makes the accepted Windows pipeline repeatable from a dedicated screen in
the existing Studio web source. The previous Studio navigation links to this local screen.
It uses the existing Python venv, VieNeu models, SDK, secret file and FFmpeg installation.
The native server serves both UI and API on loopback; SQLite and files hold its state.
There is one worker, with no WSL, Docker, PostgreSQL, Redis, VPS or Broker dependency.
The legacy API/worker and their ASR, publishing, analytics and Agent Hub features are unchanged.

## Open Studio on this PC

Double-click `scripts\start-windows-native.cmd` in this checkout, then open
<http://127.0.0.1:8026>. Keep the launcher window open. Ctrl+C stops it.
If Studio is already running, just open the address; a second server cannot take over the same data root.

PowerShell alternative, from this checkout:

```powershell
./scripts/start-windows-native.ps1
./scripts/start-windows-native.ps1 -Preflight
```

Or directly with the accepted runtime:

```powershell
C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe -m services.windows_native.server --port 8026
```

No additional installation is needed on the current PC. Dependencies are the already accepted
Python 3.12.14, OpenAI SDK 3.24.0 / httpx2 2.13.1 / Pydantic 2.13.5, Pillow 12.3.0,
VieNeu 3.8.3, ONNX Runtime 1.30.0, NumPy 2.5.3 and sea-g2p 0.9.1, plus FFmpeg/FFprobe.
Full startup preflight checks the locked profile, runtime versions, installed SDK source bytes,
clean SDK commit, licenses, voice preset and all local model/codec hashes before serving requests.
The same locked SDK source commit has been copied to `runtime\sdk\vieneu-85344322` locally,
so Phase 2 does not depend on keeping the previous chat's temporary SDK checkout.
Preflight sends no provider request. It does not replace an owner review or a live generation test.

## Normal workflow

1. Enter a project name and prompt; save the project. The accepted Cần Giờ prompt is the default.
2. Click **Tạo đề xuất nội dung**. Exactly one `gpt-6-luna` Responses request creates a structured
   narration, 3–5 scenes and source notes. The SDK has `max_retries=0`, a 90-second timeout,
   15-second connect timeout, explicit key/base URL and `store=false`.
3. Add a JPEG/PNG image, confirm its usage rights and select whether it is an architectural rendering.
   The image is validated and saved under an immutable generated name. Client paths are never accepted.
4. Read source notes and review/edit narration, scene headings and visual directions; save changes.
   The narration is assembled from scene excerpts, preserving exact coverage.
5. Enter the reviewer's name, check the human review acknowledgement and click **Duyệt nội dung này**.
   Approval binds the full project snapshot, revision, image hash, reviewer and time.
6. Click **Tạo giọng đọc & video**. Thùy Dung uses the exact accepted profile, model/codec revisions,
   SDK, CPU runtime and synthesis parameters. Inference networking is blocked; there is no audition,
   fallback voice, speech-speed adjustment or babble retry. Exact sentence boundaries feed the
   locked SDK normalization. Reaching the frame cap without EOS stops the job.
7. FFmpeg creates 1080×1920 / 30 fps / H.264 / AAC / 48 kHz MP4, then checks full decode,
   duration, A/V duration difference, audio signal/clipping and black intervals. The UI exposes
   playback and download only after QC passes for the current approved version.

Human content review and video quality acceptance are different. The UI does not automatically
declare final video acceptance. Watch the result before using it. No publishing path is exposed.
Neither factual accuracy nor media rights can be verified automatically by this local increment.

## Persistence and failure handling

- Data: `C:\NPD-Video-Factory\phase2\workflow.sqlite3`, `assets\`, and `jobs\<job-id>\`.
- Secret: the existing `C:\NPD-Video-Factory\secrets\openai.env`; never copied into source,
  browser, database, output manifest or logs. No key hashes are calculated.
- Accepted MVP1 evidence remains in `outputs\MVP1`; this service never writes there.
- SQLite transactions with synchronous FULL persist dispatch state and review binding.
- One active job per project, one worker globally, with atomic idempotency receipts.
- Restart resumes only jobs that were still queued. A job marked running becomes
  `interrupted`, preserving its last stage; it is never automatically dispatched again.
- The Windows process job kills TTS/FFmpeg children when the server exits. A data-root lock
  prevents two processes from consuming the same queue.
- Provider failures preserve error category and HTTP status, without raw error messages or secrets.
  Timeout outcome is explicitly unknown. A fresh job requires a deliberate retry button.
- Editing prompt, narration, scene headings/directions or image invalidates approval and the current
  output link. Stale revisions and edits during active jobs are rejected by the server.
- Historical outputs stay on disk as evidence but are unavailable as the current video after an edit.

The loopback UI uses a process-local HttpOnly/SameSite cookie, a CSRF header, Host/Origin checks,
and a static-route allowlist. It is for the owner on this PC and has no multi-user identity system.
It is intentionally not a remote deployment or a replacement for the existing V2 production database.

## Current media scope

One user-supplied image is retained in full inside a portrait composition and reused across scenes.
Scene headings and narration change per scene. Visual directions are review notes; the UI clearly
states the common-image behavior. This first native increment does not resolve footage from those
directions or provide a timeline/media editor. Captions use estimated phrase timing inside measured
sentence audio, with no word timestamps or ASR. Long text/layout or audio limits produce an explicit
failure rather than silently truncating narration.

## Tests and evidence

From this checkout:

```powershell
C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe -m unittest discover -s services/windows_native/tests -v
node --test apps/studio-web/tests/*.test.mjs
```

The tests use temporary roots and injected provider/engine fixtures, with zero paid calls and zero
real model inference. They cover review gates, exact text/scene mapping, invalidation, concurrent
idempotency, recovery without replay, SDK request settings, TTS parameters/frame cap/network block,
HTTP origin/session/CSRF, image validation, video ranges, source path traversal, single-server lock
and forced-parent-exit child cleanup. Existing Studio tests remain in the JavaScript suite.

Offline real-FFmpeg regression can reuse the already accepted MVP1 WAV without generating new
content or TTS, into a **fresh** output directory:

```powershell
C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe scripts/windows-native-render-smoke.py --output C:\NPD-Video-Factory\phase2-validation\render-next
```

Its report explicitly says `OFFLINE_RENDER_REGRESSION_ONLY`, zero provider calls, zero TTS inference,
and no new human approval. The fresh UI proposal must be reviewed separately before real TTS.

## Configuration and backup

Defaults target the current PC. `--config <absolute-json-path>` (or PowerShell `-Config`) can override
`runtime_root`, `secret_file`, `data_root`, `sdk_source`, `git`, and `ffmpeg_bin`, using paths only.
Do not put a key in this JSON. Do not choose MVP1 or synced `sources/` as `data_root`.
The voice profile and model identifiers have no configurable override.

Stop Studio before copying the whole `phase2` folder to a backup. Start again against that same
folder to reopen projects and evidence. The cookie is renewed after a restart; reload the browser.
Autostart and OS reboot recovery have not been configured or accepted in this increment.
