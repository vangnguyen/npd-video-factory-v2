# Drama usability 03 — baseline

Task: `VF-DRAMA-ENTRY-VOICE-CHOICES-USABILITY-03`.

Baseline HEAD `f0979e6ad47e61fd47769dfa0e0160f79bc8bf9c` is already preserved on remote and by the prior verified source bundles. Work proceeds in `C:/vfdr03`, branch `codex/vf-drama-usability-03`; the serving checkout `C:/vfns01` is left unchanged. No regression process was observed. The review server is PID 9264 at `http://127.0.0.1:62684/native.html`, with data in `C:/vfct/final-export-review-n1`. Its Python code started at `1cf600f7`; HTML/JS currently match the baseline files byte for byte and return `Cache-Control: no-store`. The data has zero queued/running/retrying core jobs. No restart has occurred in this task.

The create action currently goes to `/?new=1` and `POST /api/projects`. There is no production-workflow chooser or Drama production profile. `native_drama_voice_casting` is enabled, but `native-drama-panel` is a collapsed details element inside the assets card. Its frontend requires an existing proposal/shots and an explicit load button. This is a discoverability/mounting and workflow implementation gap; observed HTTP bytes do not support attributing it to a stale browser cache. The existing shell also routes Settings to an ASR connection page.

The locked local runtime passes full byte/version verification without inference: VieNeu SDK 3.8.3, SDK commit `85344322b7258b4e25479b692e8e3396baf9db34`, ONNX Runtime 1.30.0 CPU, NumPy 2.5.3, sea-g2p 0.9.1, model `vieneu-v3-turbo` revision `61b85e3d937fbbacb387714180e8182823512523`. Its supported installed manifest contains 25 presets, 25 distinct speaker/code payloads, and ten featured entries. Regional/style descriptions come from that manifest, not names. No models, SDKs, preset bytes or existing casts are changed.

The locked model card documents Apache-2.0 for shipped preset embeddings/reference codes and generated commercial audio, and records the upstream consent statement. These are source-license facts, distinct from an Owner quality/listening verdict. Exact file hashes and the installed roster are in [baseline evidence](../evidence/drama-usability-03/baseline.json). The prior adapter's catalog accidentally labels the TTS model with the content-LLM constant; new voice metadata must use the pinned TTS model while historical definitions remain immutable.

All 15 accepted historical MP4 files were rehashed unchanged. Prior source/review backups and policy-denied directories remain untouched. Baseline regression limitations remain in [the export regression report](FINAL_EXPORT_REGRESSION_STATUS.md): broad Native initial failures/errors with targeted closure, API 4310 pass/26 tool failures/40 skips with qualified replays, three real PostgreSQL concurrency cases still unqualified. Do not relabel them a fresh full pass.

Both browser-control runtimes failed initialization with `failed to write kernel assets: The system cannot find the path specified. (os error 3)`, before capturing a page. No screenshot/browser layout/Owner acceptance is claimed. Continue safe UI/backend work; browser walkthrough remains a separate gate.

`SOURCE_PRESERVED=YES`; `ACCEPTED_ARTIFACTS_PRESERVED=YES`; `OWNER_UAT=NOT_RECORDED`; `PLATFORM_API_PUBLISHING=DEFERRED`; `ANALYTICS=DEFERRED`; `FULL_TREND_RADAR=DEFERRED`; `PRODUCTION_DEPLOYED=NO`.
