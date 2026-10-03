from __future__ import annotations

import asyncio
import hashlib
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
        if not getattr(settings, "production_tts_model", "") or not getattr(settings, "production_tts_voice_id", ""):
            return "model_voice_selection_required"
        return "tts_authority_required"  # Pure metadata: never inspect credential bytes.
    return "configured"


def create_audio_tts_provider(settings: Any, *, controller=None, credential_resolver=None,
                              approved_units=None, transport=None):
    provider = settings.audio_tts_provider
    if provider == "espeak":
        return EspeakVietnameseTTSProvider(
            voice=settings.audio_tts_voice,
            rate=settings.audio_tts_rate,
        )
    if provider == "openai":
        from .tts_evidence import ProductionTTSProfile
        from .tts_provider_execution import GovernedVietnameseTTSProvider
        if (
            getattr(settings, "provider_global_kill_switch_engaged", True)
            or not getattr(settings, "provider_external_execution_enabled", False)
            or not getattr(settings, "provider_paid_execution_enabled", False)
        ):
            raise TTSNotConfiguredError("external audio TTS is blocked by the global provider safety gate")
        if not settings.audio_external_execution_enabled:
            raise TTSNotConfiguredError("external audio TTS execution is disabled")
        if not settings.production_tts_model or not settings.production_tts_voice_id:
            raise TTSNotConfiguredError("TTS_MODEL_VOICE_SELECTION_REQUIRED")
        profile = ProductionTTSProfile(provider_key="openai-tts", model=settings.production_tts_model,
            voice_id=settings.production_tts_voice_id, style_instructions=settings.production_tts_style,
            speed=settings.production_tts_speed)
        candidate = GovernedVietnameseTTSProvider(profile, controller=controller,
            credential_resolver=credential_resolver, approved_units=approved_units or {}, transport=transport)
        if candidate.readiness() != "CONFIG_AND_SCOPE_PRESENT":
            raise TTSNotConfiguredError("TTS_CAPABILITY_INPUT_AUTHORITY_REQUIRED")
        return candidate
    return UnconfiguredVietnameseTTSProvider()


def create_available_audio_tts_provider(settings: Any, **bindings):
    # An unapproved TTS lane blocks synthesis, not the shared worker/content/ASR
    # lifecycle. Preserve the specific safe failure without loading a credential.
    try:
        return create_audio_tts_provider(settings, **bindings)
    except TTSNotConfiguredError as exc:
        return UnconfiguredVietnameseTTSProvider(str(exc))


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
    async def synthesize_planned_narration(self, provider, *, cues, config, duration_seconds,
                                         output_path, workdir, plan):
        """Sentence-level TTS, separately scheduled captions. No automatic fit speedup."""
        from .content_service import canonical_bytes
        from .production_logic import ProductionContractError
        sample_rate = config.sample_rate
        master = array("h", [0]) * int(round(duration_seconds*sample_rate))
        if not config.voice.enabled:
            _write_pcm16(output_path, master, sample_rate)
            return {"provider":"disabled", "timing":[], "cue_count":0}
        # Cue order must still represent the exact plan, not an edited/stale script.
        expected = " ".join(" ".join(u["text"].split()) for u in plan["units"])
        actual = " ".join(" ".join(c.text.split()) for c in cues)
        if expected != actual or len(cues) != sum(len(u["scene_indices"]) for u in plan["units"]):
            raise ProductionContractError("NARRATION_PLAN_CHANGED: rebuild storyboard after caption text/order edit")
        timing, captions, cue_offset, identity = [], [], 0, {}
        for index, unit in enumerate(plan["units"]):
            raw, normalized = workdir/f"unit-{index:03d}-raw.wav", workdir/f"unit-{index:03d}-normalized.wav"
            voice = await provider.synthesize(text=unit["text"], language=config.voice.language, output_path=raw)
            await self._normalize_chunk(raw, normalized, speed=config.voice.speed)
            samples, rate = _read_pcm16(normalized)
            if rate != sample_rate:
                raise ProductionContractError("PCM_SAMPLE_RATE_MISMATCH")
            samples = _trim_activity(samples)
            duration = len(samples)/rate
            if duration <= 0:
                raise ProductionContractError("NARRATION_PCM_EMPTY")
            group = cues[cue_offset:cue_offset+len(unit["scene_indices"])]
            cue_offset += len(group)
            start, slot_end = group[0].start_seconds, group[-1].end_seconds
            if start+duration > slot_end+0.002 or start+duration > duration_seconds+0.002:
                raise ProductionContractError("NARRATION_DURATION_ADJUSTMENT_REQUIRED: audio longer than editorial slot; no truncation/speedup")
            first_frame = int(round(start*rate))
            if first_frame+len(samples) > len(master):
                raise ProductionContractError("NARRATION_OUT_OF_AUDIO_BOUNDS")
            for offset, sample in enumerate(samples):
                master[first_frame+offset] = max(-32768,min(32767,master[first_frame+offset]+sample))
            timing.append({"unit_id":unit["unit_id"], "cue_ids":[c.cue_id for c in group],
                "start_seconds":start, "end_seconds":start+duration, "slot_end_seconds":slot_end,
                "rendered_audio_duration_seconds":duration, "source_audio_duration_seconds":voice.duration_seconds,
                "text_sha256":unit["text_sha256"], "applied_timing_speedup":1,
                "audio_duration_source":"decoded_pcm_sample_count", "placement_source":"editorial_unit_schedule",
                "word_alignment":"NOT_AVAILABLE", "measured_word_timestamps":False, "audible":True})
            if voice.evidence is not None:
                timing[-1]["provider_evidence"] = voice.evidence.model_dump(mode="json")
                timing[-1]["provider_audio_file"] = raw.name
                timing[-1]["alignment_source_audio_only"] = voice.evidence.timing.source
                # Normalization/trimming/placement is not forced alignment.
                # Preserve provider evidence separately; do not silently reuse
                # raw-audio boundaries as mixed-timeline word timestamps.
                timing[-1]["transformed_audio_requires_alignment_mapping"] = bool(voice.evidence.timing.words)
            # Segment-cue estimates only. Never expose these as word timestamps.
            total = sum(len(c.text.split()) for c in group)
            cursor = start
            for cue in group:
                end = cursor+duration*len(cue.text.split())/total
                captions.append({**cue.model_dump(mode="json"), "start_seconds":cursor,
                    "end_seconds":end,"words":[]})
                cursor = end
            identity = {"provider":voice.provider, "voice":voice.voice,"model":getattr(provider,"model",None),
                "adapter":type(provider).__name__,"configured_rate":getattr(provider,"rate",None),
                "configured_speed":config.voice.speed,"human_quality_accepted":False}
        _write_pcm16(output_path, master, sample_rate)
        if not any(abs(s)>=PCM_ACTIVITY_THRESHOLD for s in master):
            raise ProductionContractError("NARRATION_PCM_NOT_AUDIBLE")
        return {**identity, "plan_sha256":hashlib.sha256(canonical_bytes(plan)).hexdigest(),
            "cue_count":len(cues),"unit_count":len(timing),"duration_seconds":len(master)/sample_rate,
            "timing":timing,"caption_schedule":captions,
            "caption_timing_source":"estimated_editorial_segment_schedule_NOT_word_alignment"}

    def __init__(self, *, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    async def mix_original(self, *, narration_path, clips, duration_seconds, gain_db, output_path):
        command = [self.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y", "-i", str(narration_path)]
        filters, labels = [], ["[0:a]"]
        for index, (clip, path) in enumerate(clips, 1):
            command += ["-ss", str(clip.source_start), "-t", str(clip.source_end-clip.source_start), "-i", str(path)]
            delay = round(clip.timeline_start*1000)
            filters.append(f"[{index}:a]atempo={clip.speed},volume={gain_db}dB,volume={clip.volume},adelay={delay}|{delay}[orig{index}]")
            labels.append(f"[orig{index}]")
        filters.append("".join(labels)+f"amix=inputs={len(labels)}:normalize=0,apad,atrim=0:{duration_seconds}[out]")
        command += ["-filter_complex", ";".join(filters), "-map", "[out]", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(output_path)]
        await _run(command, "original audio mix")
        return {"source": "validated_original_video_audio", "clip_count": len(clips), "gain_db": gain_db}

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
        provider_identity: dict[str, Any] = {}
        previous_end = 0.0
        if len({cue.cue_id for cue in cues}) != len(cues):
            raise ValueError("duplicate narration cue identity")
        for cue in cues:
            if cue.start_seconds < previous_end or cue.end_seconds > duration_seconds or cue.start_seconds >= cue.end_seconds:
                raise ValueError("narration cues must be ordered, positive and timeline bounded")
            previous_end = cue.end_seconds
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
            voice_result = await provider.synthesize(
                text=cue.text,
                language=config.voice.language,
                output_path=raw,
            )
            provider_identity = {"provider": voice_result.provider, "voice": voice_result.voice,
                "model": getattr(provider, "model", None), "adapter": type(provider).__name__,
                "configured_rate": getattr(provider, "rate", None), "configured_speed": config.voice.speed,
                "human_quality_accepted": False}
            await self._normalize_chunk(raw, normalized, speed=config.voice.speed)
            samples, rate = _read_pcm16(normalized)
            if rate != sample_rate:
                raise ValueError("normalized TTS sample rate does not match audio mix contract")
            samples = _trim_activity(samples)
            slot_seconds = cue.end_seconds - cue.start_seconds
            chunk_seconds = len(samples) / sample_rate
            speedup = 1.0
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
                    "text_sha256": hashlib.sha256(cue.text.encode("utf-8")).hexdigest(),
                    "source_audio_duration_seconds": voice_result.duration_seconds,
                    "rendered_audio_duration_seconds": chunk_seconds,
                    "applied_timing_speedup": speedup,
                    "audio_duration_source": "decoded_pcm_sample_count",
                    "placement_source": "user_timeline_scene_cue",
                    "word_alignment": "NOT_AVAILABLE",
                    "measured_word_timestamps": False,
                }
            )
            if voice_result.evidence is not None:
                timing[-1]["provider_evidence"] = voice_result.evidence.model_dump(mode="json")
                timing[-1]["provider_audio_file"] = raw.name
                timing[-1]["alignment_source_audio_only"] = voice_result.evidence.timing.source
                timing[-1]["transformed_audio_requires_alignment_mapping"] = bool(voice_result.evidence.timing.words)

        _write_pcm16(output_path, master, sample_rate)
        if not any(abs(sample) >= PCM_ACTIVITY_THRESHOLD for sample in master):
            raise ValueError("narration output contains no audible samples")
        return {
            **provider_identity,
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
    if not any(abs(sample) >= PCM_ACTIVITY_THRESHOLD for sample in samples):
        raise ValueError("TTS chunk contains no audible samples")
    # Preserve quiet leading/trailing phonemes. Only exact digital silence is
    # removed; no amplitude threshold may cut a spoken word to fit a scene.
    nonzero = [index for index, sample in enumerate(samples) if sample]
    return samples[max(0, nonzero[0] - 480) : min(len(samples), nonzero[-1] + 481)]


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
