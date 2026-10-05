# Native ASR and measured media analysis

PHASE: 4 — ASR + Media Understanding.

STATUS: PASS for the supported native path: a real speech video is extracted, transcribed by the selected AssemblyAI model, validated and persisted. This is technical acceptance; the resulting editorial draft is unapproved and needs human checking.

HEAD SHA: `6e0c7f6db1eadaa68c880b597e36da64a6f0b018`.

FILES CHANGED: `services/windows_native/asr.py`, native pipeline/store/ingestion/server/hardening integration, Studio analysis controls/transcript display, additive `requirements-asr.txt`, ASR safety tests and Phase 4 evidence. Existing strict AssemblyAI profile/adapter is reused unchanged. The new job kind and optional `media_analysis` document field are additive; prior project documents/approvals are not rewritten.

TESTS: 77/77 native, 25/25 Studio, 26/26 shared AssemblyAI adapter PASS; final ASR transport/model/secret guards 11/11 PASS. Fixtures are expressly labeled and never counted as real ASR. Tests cover actual local FFmpeg extraction/scene analysis, valid/invalid provider word intervals, failure preservation, unknown-outcome refusal, restart-safe known-job GET observation, no duplicate upload/create on resume, checkpoint corruption, missing credential, source lineage, protected-origin/no-proxy/no-redirect HTTP and credential echo rejection. The first shared-adapter run hit an inaccessible Windows temporary folder (18 passed, eight setup errors); rerunning in a fresh explicitly named validation folder passes 26/26. Both logs are retained.

EVIDENCE: `connection-real-account.json`, `real-speech-video.json`, `real-transcript.json`, `asr-real-transcript.png`, test logs. Actual isolated data remains at `C:\NPD-Video-Factory\post-mvp-validation\phase4-real-asr-20261005-2025`. Full provider receipts and extracted WAV remain there; no upload URL or credential value is copied into Git evidence. Accepted source MP4 SHA256 remains `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`.

CAPABILITIES ADDED: Explicit non-CLI media-analysis action; measured dimensions/duration/fps/audio, source-pixel colour/luminance/orientation descriptors and FFmpeg scene-score shot intervals. Audio is extracted to bounded 16-kHz mono PCM, then the existing `asr-assemblyai-vi-direct-v1` / `universal-3-5-pro` / `vi` adapter supplies original transcript, positive provider-native word intervals and confidence. Per-asset checkpoints bind audio/raw receipt/canonical result to exact source/snapshot/profile hashes. Known acknowledgements resume observation with GET only; ambiguous upload/create refuses replay. Completed transcript becomes a separately editable draft without changing its immutable provider text. Mixed-input context includes explicitly unverified transcript evidence.

ACTUAL PROVIDER: One real account verification GET, followed by one audio upload, one transcript creation and three observation GETs. The real response reports `speech_model_used=universal-3-5-pro`, `language_code=vi`; 63 provider word items have positive monotonic in-audio intervals. There is no model fallback, automatic paid replay, new content-provider request or new TTS inference. Actual isolated server restart plus browser reload preserves transcript/timing with no new dispatch. Subsequent UI draft preparation uses zero provider calls and remains awaiting human review.

REGRESSIONS: Supported suites pass. Voice SDK/model/preset/dependency pins remain accepted and unchanged. Only the already-pinned shared import dependency `tiktoken==0.12.0` was added with `--no-deps`; no voice package was upgraded. Existing main project/job/event rows and accepted artifacts are verified against a consistent backup before installing this increment.

BLOCKERS / LIMITS: The provider transcript says “cái kênh” where the approved narration says “cái tên”; the original response is preserved and human accuracy review is NOT APPROVED. Word timing refers to extracted audio. Visual descriptors describe measured pixels/technical metadata; semantic Vision recognition has not been enabled or fabricated. Estimated phrase subtitles for newly synthesized narration remain a later edit/alignment concern. Phase 5–8 and ten human-reviewed final videos remain open, so `INTERNAL_PRODUCTION_READY=NO`.

NEXT ACTION: Continue scene intelligence/auto-editor using the measured metadata and immutable transcript linkage, while preserving human script and final-video approval gates.

Primary API contracts verified: [upload](https://www.assemblyai.com/docs/pre-recorded-audio/api-reference/files/upload), [submit](https://www.assemblyai.com/docs/pre-recorded-audio/api-reference/transcripts/submit), [get](https://www.assemblyai.com/docs/pre-recorded-audio/api-reference/transcripts/get). The selected model is sent as the sole `speech_models` entry; the actual `speech_model_used` field is checked, including rejection of a different returned model.
