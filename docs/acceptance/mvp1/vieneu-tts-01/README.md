# VF-MVP1-VIENEU-TTS-ENABLEMENT-01

Local preset audition candidate, not production TTS acceptance. Child branch
`codex/vf-mvp1-vieneu-tts-01` starts at provider PR109 head
`0eaa865fc1515dffc7e7482befc8e88a9cacd53f`; stack on
`codex/vf-mvp1-real-provider-enablement-01`, not main. PR108/109 remain untouched.
Exact final commit, remote CI and audio evidence are in the external closeout
receipt, because recording a commit's own SHA here would change that commit.

## Pinned sources / rights provenance

- Model: `pnnbao-ump/VieNeu-TTS-v3-Turbo` at
  `61b85e3d937fbbacb387714180e8182823512523`, ONNX update fp32.
- SDK: `pnnbao97/VieNeu-TTS` commit
  `85344322b7258b4e25479b692e8e3396baf9db34`, package 3.8.3.
- Codec: `OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX` at
  `ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae`.
- CPU runtime: onnxruntime 1.30.0, numpy 2.5.3, sea-g2p 0.9.1.
- No container image is claimed; `server_image=NOT_CONTAINERIZED`.
- License: Apache-2.0. The **exact model card revision** FAQ states coverage
  includes weights and bundled presets and describes speaker/rightsholder
  consent. This is upstream provenance, not invented Owner G03 approval or
  permission to clone voices. `VieNeuLicenseProvenance` is equivalent bounded
  evidence, distinct from ASR RightsRecords. Startup checks raw card/license,
  model/codec files, installed SDK source and preset bytes before inference.
- Exact SDK preset names: Mai Anh (North/news), Thùy Dung (South/news),
  Ngọc Huyền (North/natural). No mapping from an older model-card voice roster.

Public source URLs:
[model card](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo/blob/61b85e3d937fbbacb387714180e8182823512523/README.md),
[SDK](https://github.com/pnnbao97/VieNeu-TTS/tree/85344322b7258b4e25479b692e8e3396baf9db34),
[codec](https://huggingface.co/OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX/tree/ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae).

## Existing pipeline / safety

`AUDIO_TTS_PROVIDER=vieneu` is an independent factory entry. Local enable is
false by default; it is rejected in production Settings. Fixed endpoint only:
`http://127.0.0.1:18083/v1/audio/speech`, no redirects, proxy or ambient auth.
Credential mode `none/local_service`: no OpenAI alias, key or resolver use.
The source-pinned local wrapper has only one preset speech route; no upload,
reference-audio, cloning, arbitrary model, shell command or caller URL routes.
It cannot make outbound connections during inference. Public unauthenticated
model/source downloads are preparation network reads, NOT provider calls.

Version/content-bound adapter → existing persisted narration evidence → actual
decoded PCM duration → existing narration reflow → review render → full QC.
Changing the named voice through audio config retains normal stale-approval
invalidation. Local style/speed controls are rejected rather than silently
claiming unsupported model features. Existing eSpeak fixture and OpenAI paths
remain separate; no authority transfers from RC28 or previous ASR receipts.

Audio/result cache replays exact byte/hash-bound real output. A leftover
inference intent without complete output is blocked after restart; no automatic
regeneration. Cancellation does not promise to preempt ONNX CPU work already
started, but stale/late responses cannot persist current audio or approval.

## Timing / normalization

No VieNeu word timestamps exist in this API: `WORD_ALIGNMENT_OPEN`.
`ESTIMATED_SEGMENT` labels editorial subtitle scheduling only. Actual audio
duration is measured by complete decoded sample count. No per-word intervals,
character timing, ASR transcript, forced aligner or fake successful receipt.

Original audition script bytes are preserved. Upstream sea-g2p normalization
and phonemization (including number/punctuation normalization) are an explicit
versioned layer. The service stores original text hash, actual normalized
chunks, phonemes and gaps separately. No project-name spelling substitutions.
Do not treat pronunciation or script completeness as PASS until human listen.

## Reproduction (isolated development only)

Use a fresh Python 3.12 venv; install SDK from the exact Git commit, not latest.
The preset-only engine does not use the SDK's Gradio UI or cloning extra paths.
Download the fixed model `onnx_update/*` and codec `decode_full.onnx` plus
`decode_shared.data` using explicit HF revisions with `token=False`. Keep each
exact original README. Files are checked by the wrapper's allowlist SHA table.
No default floating `from_pretrained` download occurs during inference.

Start `scripts/vieneu-local-server.py` with `--model`, `--codec`, `--sdk-source`
and a fresh `--cache` outside executor/runtime/discovery paths. It binds only
127.0.0.1:18083 and does no warmup inference. Start the existing renderer bound
to 127.0.0.1:3017 with STORAGE_ROOT covering only the fresh dev proof root.
Run `scripts/vieneu-audition.py --output <fresh-root> --ffmpeg <tool>
--ffprobe <tool>` from a clean commit. The harness reuses existing dev SQLite
repositories, owned synthetic image, scene planner, timeline mutation,
production render processor, Remotion renderer and full QC; it is not a second
product stack. Synthetic editorial approvals are explicitly dev-only, never
human voice acceptance. Review uses exact persisted real VieNeu unit audio,
not fixture syntheses, and preserves raw units plus metadata and mixed WAV.

## Human audition rubric (no automatic winner)

Listen to all three candidates with the **same** AUDITION_SCRIPT.txt. Score
Vietnamese pronunciation, all three project names, English phrases, numbers
and percentages, naturalness, warmth/softness, cadence, long sentences,
swallowed syllables, stutters, robotic sound, wrong pauses and suitability for
premium real-estate video. Record observations and explicit human selection;
machine decode/loudness/QC does not substitute for this review.

OpenAI Realtime `gpt-realtime-2.1-mini` / marin remains an unapproved comparator
candidate via the existing adapter; no live comparator run in this task.
`gpt-4o-mini-tts` is historical only, not the new production selection.

## Boundaries / status accounting

Local inference ≠ external provider call. Source downloads ≠ zero network.
External provider calls, provider credential reads, external spend and
production writes are zero in this task. Local compute is not cost-metered.
Host-lifetime counters are NOT_VERIFIED. No production/deployment/merge/RC,
ASR spent-context, systemd or authority mutation. An audition package may be
ready for human review without production TTS being accepted.
