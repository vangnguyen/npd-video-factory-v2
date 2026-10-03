"""Isolated preset-only CPU server. No clone routes, credentials or outbound IO.

Public downloads are a separate preparation phase. Startup rehashes pinned
artifacts, SDK engine, presets and license before binding loopback. The existing
MI04 pipeline remains the caller. Synthesis cache is content/version-bound;
ambiguous interrupted requests cannot be regenerated automatically.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import inspect
import io
import json
from pathlib import Path
import shutil
import socket
import sys
import threading
import wave

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps/api"))
from app.content_service import canonical_bytes
from app.vieneu_contracts import VieNeuTTSProfile, MODEL_CARD_SHA, CODEC_CARD_SHA, PRESETS_SHA

MODEL_FILES = {
    "config.json": "17d89d414ee302a82db7b330bf57b4cdf8541569392119c81f552178cafcb79b",
    "tokenizer.json": "6cc6bcbe380b8c37bd9f2514e37c5dfa3e00e122c6e3125dae5c4afe48e39158",
    "vieneu_prefill.onnx": "27f8b064f6b57b5448e95d095f1959588c005d614678045c2b97ecccf3b7a0f7",
    "vieneu_decode_step.onnx": "bedc379cea61ea5d616312750d95ad3924e055856662d19187a889a5edc24ceb",
    "vieneu_acoustic_cached.onnx": "f631e3387c788c3d8b9a5ac5df94952af5bc4c4d1049ff8a751e76a246fff2d4",
    "vieneu_backbone_shared.data": "c7c072193db33d0542457e2612c7272c44c4279d1cafaf0aa4c379964911db2f",
    "vieneu_v3_heads.npz": "fb22484baa424bbb775133a6e5f0d00d6299b2b256fbe3312a864b85b9aed01e",
}
CODEC_FILES = {
    "moss_audio_tokenizer_decode_full.onnx": "0fbbafe3fd4afa2a019af5c5ced204af6e2d1db044fa40f021525d2aee95b4ac",
    "moss_audio_tokenizer_decode_shared.data": "e69d52e0f4e84ca27850557ee54face46632d3a5a16c89bd246c7c408466dcad",
}


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify_files(root, expected):
    for name, digest in expected.items():
        path = root / name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError("VIENEU_PINNED_FILE_MISMATCH: " + name)


def run(args):
    import numpy as np
    import vieneu
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps, phonemize_text_with_emotions
    from vieneu_utils.core_utils import join_audio_chunks, gaps_to_silence
    from fastapi import FastAPI, Request
    from fastapi.responses import Response
    import uvicorn
    expected_versions = {"vieneu": "3.8.3", "onnxruntime": "1.30.0", "numpy": "2.5.3", "sea-g2p": "0.9.1"}
    if any(importlib.metadata.version(k) != v for k, v in expected_versions.items()):
        raise ValueError("VIENEU_RUNTIME_VERSION_MISMATCH")
    sdk = Path(vieneu.__file__).parent
    verify_files(sdk / "assets", {"voices_v3_turbo.json": PRESETS_SHA})
    verify_files(args.model / "onnx_update", MODEL_FILES)
    verify_files(args.codec, CODEC_FILES)
    verify_files(args.model, {"README.md": MODEL_CARD_SHA})
    verify_files(args.codec, {"README.md": CODEC_CARD_SHA})
    # Source installation must be the reviewed SDK, not merely a same-version wheel.
    import subprocess
    # Windows-created worktrees retain Windows Git indirection/CRLF filters.
    # Use that installed Git under WSL, not a different checkout interpretation.
    git = (shutil.which("git.exe") if str(args.sdk_source.resolve()).startswith("/mnt/") else None) or "git"
    sdk_commit = subprocess.check_output([git, "rev-parse", "HEAD"], cwd=args.sdk_source, text=True).strip()
    from app.vieneu_contracts import SDK_COMMIT, SDK_LICENSE_SHA
    if sdk_commit != SDK_COMMIT or subprocess.check_output([git, "status", "--porcelain"], cwd=args.sdk_source, text=True).strip():
        raise ValueError("VIENEU_SDK_SOURCE_MISMATCH")
    verify_files(args.sdk_source, {"LICENSE": SDK_LICENSE_SHA})
    source_tree = args.sdk_source / "src"
    for installed_dir in (sdk, sdk.parent / "vieneu_utils"):
        for file in installed_dir.rglob("*.py"):
            expected = source_tree / file.relative_to(sdk.parent)
            if not expected.is_file() or sha(file) != sha(expected):
                raise ValueError("VIENEU_INSTALLED_SDK_BYTES_MISMATCH")
    # No default hub fetch/denoiser/cloning code paths may contact a network.
    def blocked_connect(*_a, **_kw):
        raise RuntimeError("LOCAL_INFERENCE_OUTBOUND_NETWORK_BLOCKED")
    socket.socket.connect = blocked_connect
    class PresetEngine(OnnxV3LiteEngine):
        def _load_denoiser(self):
            return None  # no cloning or reference-audio input exists in this service
    engine = PresetEngine(checkpoint_path=str(args.model), onnx_dir=str(args.model / "onnx_update"),
        codec_dir=str(args.codec), threads=args.threads)
    engine.babble_retries = 0
    presets = json.loads((sdk / "assets/voices_v3_turbo.json").read_bytes())["presets"]
    if args.cache.is_symlink():
        raise ValueError("VIENEU_CACHE_CUSTODY_INVALID")
    args.cache.mkdir(parents=True, mode=0o700, exist_ok=True)
    service_sha = sha(Path(__file__))
    lock = threading.Lock()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/v1/audio/speech")
    async def speech(request: Request):
        raw = await request.body()
        if len(raw) > 40000:
            return Response(status_code=413)
        try:
            body = json.loads(raw)
            if set(body) != {"profile", "text", "scope", "format"} or body["format"] != "wav":
                raise ValueError()
            profile = VieNeuTTSProfile.model_validate(body["profile"])
            text = body["text"]
            if not isinstance(text, str) or not text.strip() or len(text) > 4096:
                raise ValueError()
            if body["scope"] is not None and (not isinstance(body["scope"], dict) or
                    set(body["scope"]) != {"workspace_id", "project_id", "content_version_id", "render_id"} or
                    any(not isinstance(v, str) or not v or len(v) > 160 for v in body["scope"].values())):
                raise ValueError()
        except Exception:
            return Response(status_code=422)  # no prompt/body/exception echo
        key = hashlib.sha256(canonical_bytes(body)).hexdigest()
        audio_path, meta_path, intent = (args.cache / (key + ext) for ext in (".wav", ".json", ".intent"))
        try:
            with lock:
                if audio_path.is_symlink() or meta_path.is_symlink() or intent.is_symlink():
                    raise ValueError()
                if audio_path.exists() and meta_path.exists():
                    record = json.loads(meta_path.read_bytes())
                    if sha(audio_path) != record["audio_sha256"]:
                        raise ValueError()
                else:
                    # An interrupted synthesis is not retried, even after restart.
                    with intent.open("xb") as dst:
                        dst.write(canonical_bytes({"request_sha256": key, "state": "LOCAL_SYNTHESIS_STARTED"}))
                    chunks, gaps = normalize_to_chunks_v3_with_gaps(text, max_chars=profile.parameters.max_chars)
                    if not chunks:
                        raise ValueError()
                    phonemes = [phonemize_text_with_emotions(c) for c in chunks]
                    voice = presets[profile.voice_id]
                    waves = [engine.infer(phonemes=ph, speaker_emb=np.array(voice["speaker_emb"], dtype=np.float32),
                        ref_codes=np.array(voice["codes"], dtype=np.int64),
                        temperature=profile.parameters.temperature, top_k=profile.parameters.top_k,
                        top_p=profile.parameters.top_p, repetition_penalty=profile.parameters.repetition_penalty,
                        max_new_frames=profile.parameters.max_new_frames) for ph in phonemes]
                    audio = join_audio_chunks(waves, 48000, silence_ps=gaps_to_silence(gaps))
                    if not np.isfinite(audio).all() or len(audio) == 0 or len(audio) > 48000 * profile.max_audio_seconds:
                        raise ValueError()
                    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
                    buf = io.BytesIO()
                    with wave.open(buf, "wb") as wav:
                        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000); wav.writeframes(pcm)
                    with audio_path.open("xb") as dst:
                        dst.write(buf.getvalue())
                    normalization = {"original_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "layer": profile.parameters.normalization_layer, "chunks": chunks,
                        "phonemes": phonemes, "gaps": gaps, "proper_name_rewrites": "NONE"}
                    record = {"profile": profile.model_dump(mode="json"), "request_sha256": key,
                        "audio_sha256": sha(audio_path), "decoded_duration_seconds": len(pcm) / 96000,
                        "normalization": normalization, "local_synthesis_requests": 1,
                        "engine_infer_calls": len(phonemes), "automatic_retry": False,
                        "server_source_sha256": service_sha, "runtime_versions": expected_versions,
                        "timing_source": "ESTIMATED_SEGMENT", "words": [], "human_quality_accepted": False}
                    with meta_path.open("xb") as dst:
                        dst.write(canonical_bytes(record))
                return Response(audio_path.read_bytes(), media_type="audio/wav", headers={
                    "x-vieneu-profile-sha256": profile.sha256, "x-vieneu-server-sha256": service_sha,
                    "x-vieneu-normalization-sha256": hashlib.sha256(canonical_bytes(record["normalization"])).hexdigest()})
        except Exception:
            return Response(status_code=503)
    print("PINNED_PRESET_LOCAL_SERVICE_LISTENING 127.0.0.1:18083", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=18083, access_log=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--codec", type=Path, required=True)
    parser.add_argument("--sdk-source", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--threads", type=int, choices=range(1, 9), default=4)
    run(parser.parse_args())
