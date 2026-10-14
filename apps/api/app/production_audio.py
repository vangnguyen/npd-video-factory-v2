from __future__ import annotations

import asyncio
import hashlib
import json
import math
import struct
import sys
import wave
from array import array
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from .models import StrictModel
from .timeline_models import TimelineSnapshot
from .timeline_audio_processing import AudioProcessing

from .production_models import MixConfig, SubtitleCue
from .providers import (
    EspeakVietnameseTTSProvider,
    TTSNotConfiguredError,
    UnconfiguredVietnameseTTSProvider,
    VoiceResult,
)


PCM_ACTIVITY_THRESHOLD = 128


def audio_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def active_canonical_audio(snapshot):
    return [(track, clip) for track in sorted(snapshot.tracks, key=lambda t: t.order)
        if track.type == 'audio' and not track.disabled and not track.muted
        for clip in track.clips if not clip.disabled and clip.volume > 0]


class CanonicalAudioInput(StrictModel):
    schema_version: Literal['canonical-production-audio-input.v1'] = 'canonical-production-audio-input.v1'
    snapshot_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    mix_config_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    processing: AudioProcessing
    clip_schedule_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    source_custodies: dict[str, dict[str, Any]] = Field(max_length=128)
    legacy_music_custody: dict[str, Any] | None = None


class CanonicalAudioReceipt(StrictModel):
    schema_version: Literal['canonical-production-audio.v1'] = 'canonical-production-audio.v1'
    input: CanonicalAudioInput
    input_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    source_audio_clocks: dict[str, Any]
    audio_clip_receipts: list[dict[str, Any]] = Field(min_length=1, max_length=128)
    audio_processing: dict[str, Any]
    output_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    output_size_bytes: int = Field(strict=True, gt=0)
    sample_rate: Literal[48000] = 48000
    channels: Literal[2] = 2
    sample_count: int = Field(strict=True, gt=0, le=28_800_000)
    duration_seconds: float = Field(gt=0, le=600)
    legacy_base_sha256: str | None = Field(default=None, pattern='^[a-f0-9]{64}$')
    external_provider_calls: Literal[0] = 0
    original_media_mutated: Literal[False] = False


def canonical_audio_input(snapshot, assets, config):
    from .frozen_storage_read import asset_custody
    selected = active_canonical_audio(snapshot)
    if not selected or len(selected) > 128:
        raise ValueError('CANONICAL_AUDIO_CLIP_COUNT_INVALID')
    identifiers = {clip.asset_id for _, clip in selected}
    if None in identifiers or any(identifier not in assets for identifier in identifiers):
        raise ValueError('CANONICAL_AUDIO_ASSET_UNAVAILABLE')
    music = config.music.asset_id
    if music is not None and music not in assets:
        raise ValueError('CANONICAL_AUDIO_ASSET_UNAVAILABLE')
    return CanonicalAudioInput(
        snapshot_sha256=audio_digest(snapshot.model_dump(mode='json')),
        mix_config_sha256=audio_digest(config.model_dump(mode='json')),
        processing=AudioProcessing.model_validate({} if snapshot.metadata.get('source_audio_processing') is None
            else snapshot.metadata['source_audio_processing']),
        clip_schedule_sha256=audio_digest([{'track_id': track.track_id, 'kind': track.kind,
            'order': track.order, 'clip': clip.model_dump(mode='json')} for track, clip in selected]),
        source_custodies={identifier: asset_custody(assets[identifier][0]) for identifier in sorted(identifiers)},
        legacy_music_custody=asset_custody(assets[music][0]) if music is not None else None)


def canonical_audio_custodies(value):
    result = dict(value.source_custodies)
    if value.legacy_music_custody is not None:
        result[value.legacy_music_custody['asset_id']] = value.legacy_music_custody
    return result


def canonical_audio_graph(snapshot, assets, config, *, first_input_index):
    from .timeline_audio_processing import build_processed_audio_graph
    effective = snapshot.model_copy(deep=True)
    gain = math.pow(10, (config.original_audio_gain_db or 0) / 20)
    for track, clip in active_canonical_audio(effective):
        if track.kind == 'original_audio':
            clip.volume *= gain
    graph = build_processed_audio_graph(effective, assets, first_input_index=first_input_index,
        processing=snapshot.metadata.get('source_audio_processing'), packet_alignment=True)
    # The shared preview graph keeps its own -1 dB default. Production's saved
    # MixConfig is authoritative for the actual terminal limiter and receipt.
    marker = 'alimiter=limit=0.891250938:level=0:latency=1'
    if not graph.clips or graph.filters[-1].count(marker) != 1 or not graph.filters[-1].endswith('[outa]'):
        raise ValueError('CANONICAL_AUDIO_LIMITER_BOUNDARY_INVALID')
    filters = list(graph.filters)
    limiter = math.pow(10, config.limiter_peak_db / 20)
    filters[-1] = filters[-1].replace(marker, f'alimiter=limit={limiter:.9f}:level=0:latency=1')
    return replace(graph, filters=filters, processing={**graph.processing,'limiter_peak_db':config.limiter_peak_db})


def validate_canonical_audio_receipt(value, snapshot, assets, config):
    receipt = CanonicalAudioReceipt.model_validate(value)
    expected = canonical_audio_input(snapshot, assets, config)
    if (receipt.input != expected or receipt.input_sha256 != audio_digest(expected.model_dump(mode='json'))
            or abs(receipt.sample_count / 48000 - snapshot.duration_seconds) > 1 / 48000
            or abs(receipt.duration_seconds - receipt.sample_count / 48000) > 1e-12
            or receipt.audio_processing.get('configuration') != expected.processing.model_dump(mode='json')
            or set(receipt.source_audio_clocks.get('assets', {})) != set(expected.source_custodies)):
        raise ValueError('CANONICAL_AUDIO_RECEIPT_CHANGED')
    selected = {clip.clip_id: (track, clip) for track, clip in active_canonical_audio(snapshot)}
    if {item.get('clip_id') for item in receipt.audio_clip_receipts} != set(selected):
        raise ValueError('CANONICAL_AUDIO_RECEIPT_CHANGED')
    graph = canonical_audio_graph(snapshot, assets, config, first_input_index=0)
    if receipt.audio_clip_receipts != graph.clips or receipt.audio_processing != graph.processing:
        raise ValueError('CANONICAL_AUDIO_RECEIPT_CHANGED')
    for identifier, custody in expected.source_custodies.items():
        if receipt.source_audio_clocks['assets'][identifier].get('source_sha256') != custody['checksum_sha256']:
            raise ValueError('CANONICAL_AUDIO_RECEIPT_CHANGED')
    return receipt


def audio_provider_status(settings: Any) -> str:
    provider = settings.audio_tts_provider
    if provider == "contract":
        return "not_configured"
    if provider == "vieneu":
        from .vieneu_contracts import SELECTED_VOICE
        if getattr(settings, "vieneu_voice_id", None) != SELECTED_VOICE:
            return "selected_voice_mismatch"
        return "configured" if getattr(settings, "vieneu_local_execution_enabled", False) else "not_configured"
    if provider == "openai":
        if not getattr(settings, "production_tts_model", "") or not getattr(settings, "production_tts_voice_id", ""):
            return "model_voice_selection_required"
        return "tts_authority_required"  # Pure metadata: never inspect credential bytes.
    return "configured"


def create_audio_tts_provider(settings: Any, *, controller=None, credential_resolver=None,
                              approved_units=None, transport=None):
    provider = settings.audio_tts_provider
    if provider == "vieneu":
        from .vieneu_contracts import selected_vieneu_profile, SELECTED_VOICE
        from .vieneu_tts_provider import VieNeuTTSProvider
        if not getattr(settings, "vieneu_local_execution_enabled", False):
            raise TTSNotConfiguredError("VIENEU_LOCAL_EXECUTION_DISABLED")
        if settings.vieneu_voice_id != SELECTED_VOICE:
            raise TTSNotConfiguredError("VIENEU_SELECTED_VOICE_CHANGE_REQUIRES_OWNER_REVIEW")
        return VieNeuTTSProvider(selected_vieneu_profile(), local_execution_enabled=True,
            transport=transport, selected_voice_only=True)
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
    if bindings.pop("admission_error", None):
        return UnconfiguredVietnameseTTSProvider("MVP1_LANE_ADMISSION_BLOCKED")
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
            if voice.reuse is not None:
                timing[-1]['raw_audio_reuse'] = voice.reuse
            if voice.cache_origin is not None:
                timing[-1]['raw_audio_cache_origin'] = voice.cache_origin
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

    def __init__(self, *, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    async def mix_canonical_timeline(self, *, snapshot, assets, config, base_audio_path,
                                     output_path, is_cancelled):
        """Mix canonical sources; raw/generated narration remains a separate file."""
        from .auto_edit_providers import FFprobeMediaProbe
        from .source_audio_clock import verify_audio_inputs, INPUT_TIMESTAMP_OPTIONS
        from .frozen_storage_read import completed_read
        from .object_storage import sha256_file
        if not math.isfinite(snapshot.duration_seconds) or not 0 < snapshot.duration_seconds <= 600:
            raise ValueError('CANONICAL_AUDIO_DURATION_INVALID')
        maximum = (math.ceil(snapshot.duration_seconds * 48000) + 1) * 4 + 65536
        frozen = canonical_audio_input(snapshot, assets, config)
        graph = canonical_audio_graph(snapshot, assets, config,
            first_input_index=1 if base_audio_path is not None else 0)
        stopped = asyncio.Event()
        async def cancelled():
            return stopped.is_set() or await is_cancelled()
        async def drained(awaitable):
            task = asyncio.ensure_future(awaitable)
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                stopped.set()
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not task.cancelled():
                    task.exception()
                raise
        async def current_bytes():
            if await cancelled():
                raise ValueError('CANONICAL_AUDIO_CANCELLED')
            for identifier, custody in canonical_audio_custodies(frozen).items():
                path = assets[identifier][1]
                if (path.stat().st_size != custody['size_bytes']
                        or await completed_read(asyncio.to_thread(sha256_file, path)) != custody['checksum_sha256']):
                    raise ValueError('CANONICAL_AUDIO_SOURCE_CHANGED')
            if await cancelled():
                raise ValueError('CANONICAL_AUDIO_CANCELLED')
        await current_bytes()
        source_clocks = await drained(verify_audio_inputs(snapshot, assets,
            executable=self.ffmpeg_path, is_cancelled=cancelled))
        probe = FFprobeMediaProbe(self.ffprobe_path)
        metadata = {}
        for track, clip in active_canonical_audio(snapshot):
            if clip.asset_id not in metadata:
                asset, path = assets[clip.asset_id]
                metadata[clip.asset_id] = await drained(probe.probe(path,
                    detected_content_type=asset.content_type,
                    media_kind='video' if asset.content_type.startswith('video/') else 'audio'))
            measured = metadata[clip.asset_id]
            if (not measured.audio_codec or not measured.duration_seconds or clip.source_end is None
                    or clip.source_end > measured.duration_seconds + .05):
                raise ValueError('CANONICAL_AUDIO_SOURCE_WINDOW_UNAVAILABLE')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            *INPUT_TIMESTAMP_OPTIONS, '-protocol_whitelist', 'file,pipe']
        filters = list(graph.filters)
        base_sha = None
        if base_audio_path is not None:
            await completed_read(asyncio.to_thread(_canonical_pcm, base_audio_path,
                snapshot.duration_seconds, maximum))
            base_sha = await completed_read(asyncio.to_thread(sha256_file, base_audio_path))
            command += ['-i', str(base_audio_path)]
            filters = [item.replace('[outa]', '[canonical_audio]') for item in filters]
            limiter = math.pow(10, config.limiter_peak_db / 20)
            filters += ['[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,'
                'asetpts=PTS-STARTPTS[legacy_audio]',
                '[canonical_audio][legacy_audio]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,'
                f'alimiter=limit={limiter:.9f}:level=0:latency=1,apad,'
                f'atrim=duration={snapshot.duration_seconds:.9f},asetpts=PTS-STARTPTS[outa]']
        command += graph.inputs
        filter_path = output_path.with_suffix('.canonical-filter.txt')
        filter_path.write_text(';'.join(filters), encoding='utf-8')
        command += ['-filter_complex_threads', '1', '-/filter_complex', str(filter_path),
            '-map', '[outa]', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le',
            '-t', f'{snapshot.duration_seconds:.9f}', '-fs', str(maximum), str(output_path)]
        if sys.platform == 'win32' and sum(len(v) + 3 for v in command) > 30000:
            raise ValueError('CANONICAL_AUDIO_INPUT_COMMAND_LIMIT')
        await drained(_run_canonical_audio(command, output_path=output_path, is_cancelled=cancelled,
            timeout_seconds=min(900, max(60, snapshot.duration_seconds * 6))))
        await current_bytes()
        shape = await completed_read(asyncio.to_thread(_canonical_pcm, output_path,
            snapshot.duration_seconds, maximum))
        output_sha = await completed_read(asyncio.to_thread(sha256_file, output_path))
        await current_bytes()
        if shape['peak_dbfs'] is None or shape['peak_dbfs'] < -35:
            raise ValueError('CANONICAL_AUDIO_EFFECTIVELY_SILENT')
        receipt = CanonicalAudioReceipt(input=frozen,
            input_sha256=audio_digest(frozen.model_dump(mode='json')), source_audio_clocks=source_clocks,
            audio_clip_receipts=graph.clips, audio_processing=graph.processing,
            output_sha256=output_sha, output_size_bytes=output_path.stat().st_size,
            sample_count=shape['sample_count'], duration_seconds=shape['sample_count'] / 48000,
            legacy_base_sha256=base_sha)
        validate_canonical_audio_receipt(receipt, snapshot, assets, config)
        return {'engine': 'canonical-timeline-audio.v1', 'sample_rate': 48000,
            'duration_seconds': receipt.duration_seconds, 'peak_dbfs': shape['peak_dbfs'],
            'limiter_peak_db': config.limiter_peak_db, 'configured': bool(config.music.asset_id),
            'ducking_applied': graph.processing['music_ducking'],
            'canonical_timeline_audio': receipt.model_dump(mode='json')}

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
            if voice_result.reuse is not None:
                timing[-1]['raw_audio_reuse'] = voice_result.reuse
            if voice_result.cache_origin is not None:
                timing[-1]['raw_audio_cache_origin'] = voice_result.cache_origin

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
        if not math.isfinite(duration_seconds) or not 0 < duration_seconds <= 600:
            raise ValueError('AUDIO_MIX_DURATION_INVALID')
        maximum = (math.ceil(duration_seconds * config.sample_rate) + 1) * 4 + 65536
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
                "-t",
                f"{duration_seconds:.9f}",
                "-fs",
                str(maximum),
                str(output_path),
            ]
        )
        await _run(command, "audio mix")
        _canonical_pcm(output_path, duration_seconds, maximum)
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


async def _run_canonical_audio(command, *, output_path, is_cancelled, timeout_seconds):
    """One owned child, bounded stderr, no retry; cleanup survives repeated cancel."""
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(*command,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE))
    process = None
    communication = None
    chunks = []
    async def consume():
        size = 0
        oversized = False
        while chunk := await process.stderr.read(65536):
            size += len(chunk)
            if size > 4 * 1024 * 1024:
                oversized = True
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
            if not oversized:
                chunks.append(chunk)
        await process.wait()
        if oversized:
            raise ValueError('CANONICAL_AUDIO_LOG_LIMIT')
        return b''.join(chunks)
    async def drain(task):
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
    try:
        process = await asyncio.shield(spawn)
        communication = asyncio.create_task(consume())
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while not communication.done():
            if await is_cancelled():
                raise ValueError('CANONICAL_AUDIO_CANCELLED')
            if asyncio.get_running_loop().time() >= deadline:
                raise ValueError('CANONICAL_AUDIO_TIMEOUT')
            await asyncio.wait([communication], timeout=.1)
        stderr = await communication
        if process.returncode != 0:
            output_path.with_suffix('.canonical-stderr.txt').write_bytes(stderr)
            raise ValueError('CANONICAL_AUDIO_DSP_FAILED')
    except BaseException as error:
        was_running = process is None or process.returncode is None
        await drain(spawn)
        if not spawn.cancelled() and spawn.exception() is None:
            process = spawn.result()
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            if communication is None:
                communication = asyncio.create_task(consume())
            await drain(communication)
        if not isinstance(error, asyncio.CancelledError):
            output_path.with_suffix('.canonical-stderr.txt').write_bytes(b''.join(chunks))
            output_path.with_suffix('.canonical-failure.json').write_text(json.dumps({
                'error': str(error), 'process_was_running': was_running,
                'returncode_after_drain': process.returncode if process else None,
                'output_size_before_cleanup': output_path.stat().st_size if output_path.exists() else None}),
                encoding='utf-8')
        output_path.unlink(missing_ok=True)
        raise


def _canonical_pcm(path, duration, maximum):
    if not 0 < path.stat().st_size <= maximum:
        raise ValueError('CANONICAL_AUDIO_PCM_LIMIT')
    with wave.open(str(path), 'rb') as wav:
        count, rate = wav.getnframes(), wav.getframerate()
        if (wav.getnchannels(), wav.getsampwidth(), rate) != (2, 2, 48000) or count <= 0 \
                or abs(count / rate - duration) > 1 / rate:
            raise ValueError('CANONICAL_AUDIO_PCM_CLOCK_INVALID')
        peak = 0
        remaining = count
        while remaining:
            amount = min(remaining, 48000)
            data = wav.readframes(amount)
            if len(data) != amount * 4:
                raise ValueError('CANONICAL_AUDIO_PCM_TRUNCATED')
            values = array('h')
            values.frombytes(data)
            if sys.byteorder != 'little':
                values.byteswap()
            peak = max(peak, max(map(abs, values)))
            remaining -= amount
    return {'sample_count': count, 'peak_dbfs': 20 * math.log10(peak / 32768) if peak else None}


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
