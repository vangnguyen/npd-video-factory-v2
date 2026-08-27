from __future__ import annotations

import asyncio
import math
import struct
import sys
import wave
from array import array
from pathlib import Path
from typing import Any

from .production_models import MixConfig, SubtitleCue
from .providers import (
    EspeakVietnameseTTSProvider,
    OpenAIVietnameseTTSProvider,
    TTSNotConfiguredError,
    UnconfiguredVietnameseTTSProvider,
    VoiceResult,
)


PCM_ACTIVITY_THRESHOLD = 128


def audio_provider_status(settings: Any) -> str:
    provider = settings.audio_tts_provider
    if provider == "contract":
        return "not_configured"
    if provider == "openai":
        return "configured" if settings.audio_external_execution_enabled and settings.openai_api_key.strip() else "not_configured"
    return "configured"


def create_audio_tts_provider(settings: Any):
    provider = settings.audio_tts_provider
    if provider == "espeak":
        return EspeakVietnameseTTSProvider(
            voice=settings.audio_tts_voice,
            rate=settings.audio_tts_rate,
        )
    if provider == "openai":
        if not settings.audio_external_execution_enabled:
            raise TTSNotConfiguredError("external audio TTS execution is disabled")
        return OpenAIVietnameseTTSProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            instructions=settings.openai_tts_instructions,
            base_url=settings.openai_base_url,
            timeout_seconds=120,
        )
    return UnconfiguredVietnameseTTSProvider()


class DeterministicWaveTTSProvider:
    """Audible offline fixture used only by unit tests."""

    async def synthesize(self, *, text: str, language: str, output_path: Path) -> VoiceResult:
        if language != "vi" or not text.strip():
            raise ValueError("deterministic TTS requires non-empty Vietnamese text")
        sample_rate = 48_000
        duration = min(1.2, max(0.28, len(text.split()) * 0.11))
        total = int(sample_rate * duration)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            frames = bytearray()
            for index in range(total):
                envelope = min(1.0, index / 800, (total - index) / 800)
                value = int(6500 * envelope * math.sin(2 * math.pi * 220 * index / sample_rate))
                frames.extend(struct.pack("<h", value))
            wav.writeframes(bytes(frames))
        return VoiceResult(
            path=output_path,
            duration_seconds=duration,
            provider="deterministic-wave",
            voice="fixture-vi",
        )


class AudioMixEngine:
    def __init__(self, *, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    async def synthesize_narration(
        self,
        provider: Any,
        *,
        cues: list[SubtitleCue],
        config: MixConfig,
        duration_seconds: float,
        output_path: Path,
        workdir: Path,
    ) -> dict[str, Any]:
        sample_rate = config.sample_rate
        total_frames = int(round(duration_seconds * sample_rate))
        master = array("h", [0]) * total_frames
        timing: list[dict[str, Any]] = []
        if not config.voice.enabled:
            _write_pcm16(output_path, master, sample_rate)
            return {
                "provider": "disabled",
                "voice": config.voice.voice,
                "cue_count": 0,
                "duration_seconds": duration_seconds,
                "timing": [],
            }

        for index, cue in enumerate(cues):
            raw = workdir / f"voice-{index:03d}-raw.wav"
            normalized = workdir / f"voice-{index:03d}-normalized.wav"
            await provider.synthesize(
                text=cue.text,
                language=config.voice.language,
                output_path=raw,
            )
            await self._normalize_chunk(raw, normalized, speed=config.voice.speed)
            samples, rate = _read_pcm16(normalized)
            if rate != sample_rate:
                raise ValueError("normalized TTS sample rate does not match audio mix contract")
            samples = _trim_activity(samples)
            slot_seconds = cue.end_seconds - cue.start_seconds
            chunk_seconds = len(samples) / sample_rate
            if chunk_seconds > slot_seconds:
                speedup = chunk_seconds / max(0.08, slot_seconds - 0.02)
                if speedup > config.voice.max_timing_adjustment:
                    raise ValueError(
                        f"subtitle cue {cue.cue_id} needs {speedup:.3f}x TTS speed, above the configured limit"
                    )
                fitted = workdir / f"voice-{index:03d}-fitted.wav"
                await self._atempo(normalized, fitted, speedup)
                samples, rate = _read_pcm16(fitted)
                samples = _trim_activity(samples)
                chunk_seconds = len(samples) / rate
            start_frame = int(round(cue.start_seconds * sample_rate))
            end_frame = start_frame + len(samples)
            maximum_end = int(round(cue.end_seconds * sample_rate))
            if end_frame > maximum_end + 2 or end_frame > total_frames:
                raise ValueError(f"TTS audio exceeds subtitle cue {cue.cue_id}")
            for offset, sample in enumerate(samples):
                target = start_frame + offset
                mixed = master[target] + sample
                master[target] = max(-32768, min(32767, mixed))
            timing.append(
                {
                    "cue_id": cue.cue_id,
                    "start_seconds": cue.start_seconds,
                    "end_seconds": round(cue.start_seconds + chunk_seconds, 3),
                    "slot_end_seconds": cue.end_seconds,
                    "audible": True,
                }
            )

        _write_pcm16(output_path, master, sample_rate)
        if not any(abs(sample) >= PCM_ACTIVITY_THRESHOLD for sample in master):
            raise ValueError("narration output contains no audible samples")
        return {
            "provider": getattr(provider, "voice", provider.__class__.__name__),
            "voice": config.voice.voice,
            "cue_count": len(timing),
            "duration_seconds": round(len(master) / sample_rate, 3),
            "timing": timing,
        }

    async def mix(
        self,
        *,
        narration_path: Path,
        music_path: Path | None,
        cues: list[SubtitleCue],
        config: MixConfig,
        duration_seconds: float,
        output_path: Path,
    ) -> dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(narration_path),
        ]
        voice_gain = math.pow(10, config.voice.gain_db / 20)
        limiter = math.pow(10, config.limiter_peak_db / 20)
        if music_path is None:
            filter_graph = (
                f"[0:a]aresample={config.sample_rate},"
                f"volume={voice_gain:.8f},alimiter=limit={limiter:.8f},"
                f"apad,atrim=0:{duration_seconds:.6f}[outa]"
            )
            music_manifest = {"configured": False, "ducking_applied": False}
        else:
            command.extend(["-stream_loop", "-1", "-i", str(music_path)])
            music_gain = math.pow(10, config.music.gain_db / 20)
            duck_gain = math.pow(10, config.music.ducking_db / 20)
            speech_terms = "+".join(
                f"between(t,{cue.start_seconds:.3f},{cue.end_seconds:.3f})" for cue in cues
            ) or "0"
            fade_out_start = max(0.0, duration_seconds - config.music.fade_out_seconds)
            filter_graph = (
                f"[0:a]aresample={config.sample_rate},volume={voice_gain:.8f}[voice];"
                f"[1:a]aresample={config.sample_rate},volume={music_gain:.8f},"
                f"volume='if(gt({speech_terms},0),{duck_gain:.8f},1)':eval=frame,"
                f"afade=t=in:st=0:d={config.music.fade_in_seconds:.3f},"
                f"afade=t=out:st={fade_out_start:.3f}:d={config.music.fade_out_seconds:.3f},"
                f"atrim=0:{duration_seconds:.6f}[music];"
                f"[voice][music]amix=inputs=2:duration=longest:dropout_transition=0,"
                f"alimiter=limit={limiter:.8f},atrim=0:{duration_seconds:.6f}[outa]"
            )
            music_manifest = {
                "configured": True,
                "ducking_applied": True,
                "music_gain_db": config.music.gain_db,
                "ducking_db": config.music.ducking_db,
                "speech_windows": len(cues),
            }
        command.extend(
            [
                "-filter_complex",
                filter_graph,
                "-map",
                "[outa]",
                "-ac",
                "2",
                "-ar",
                str(config.sample_rate),
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ]
        )
        await _run(command, "audio mix")
        samples, rate = _read_pcm16(output_path, allow_stereo=True)
        if rate != config.sample_rate or not samples:
            raise ValueError("audio mix output is empty or has the wrong sample rate")
        peak = max(abs(item) for item in samples) / 32768
        if peak < math.pow(10, -35 / 20):
            raise ValueError("audio mix output is effectively silent")
        return {
            "engine": "ffmpeg-audio-mix-v2-08",
            "sample_rate": rate,
            "duration_seconds": duration_seconds,
            "peak_dbfs": round(20 * math.log10(max(peak, 1e-9)), 3),
            "limiter_peak_db": config.limiter_peak_db,
            **music_manifest,
        }

    async def _normalize_chunk(self, source: Path, destination: Path, *, speed: float) -> None:
        await self._atempo(source, destination, speed)

    async def _atempo(self, source: Path, destination: Path, speed: float) -> None:
        await _run(
            [
                self.ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-af",
                f"atempo={speed:.6f}",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ],
            "TTS timing normalization",
        )


async def _run(command: list[str], label: str) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{label} failed: {detail[-700:] or process.returncode}")


def _read_pcm16(path: Path, *, allow_stereo: bool = False) -> tuple[array, int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        if (channels != 1 and not (allow_stereo and channels == 2)) or wav.getsampwidth() != 2:
            raise ValueError("audio must be mono or stereo 16-bit PCM WAV")
        if wav.getcomptype() != "NONE":
            raise ValueError("compressed WAV is not supported")
        rate = wav.getframerate()
        values = array("h")
        values.frombytes(wav.readframes(wav.getnframes()))
    if sys.byteorder == "big":
        values.byteswap()
    return values, rate


def _trim_activity(samples: array) -> array:
    active = [index for index, sample in enumerate(samples) if abs(sample) >= PCM_ACTIVITY_THRESHOLD]
    if not active:
        raise ValueError("TTS chunk contains no audible samples")
    return samples[max(0, active[0] - 480) : min(len(samples), active[-1] + 481)]


def _write_pcm16(path: Path, samples: array, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = array("h", samples)
    if sys.byteorder == "big":
        frames.byteswap()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames.tobytes())
