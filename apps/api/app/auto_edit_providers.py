from __future__ import annotations

import asyncio
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .auto_edit_models import MediaMetadata


class ProviderNotConfigured(RuntimeError):
    pass


class MediaProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderWord:
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float


@dataclass(frozen=True)
class ProviderSegment:
    start_seconds: float
    end_seconds: float
    text: str
    speaker: str | None
    confidence: float
    words: tuple[ProviderWord, ...]


@dataclass(frozen=True)
class ProviderTranscript:
    language: str
    confidence: float
    segments: tuple[ProviderSegment, ...]
    provenance: dict[str, object]


@dataclass(frozen=True)
class MediaSignals:
    shot_boundaries: tuple[tuple[float, float], ...]
    silence_intervals: tuple[tuple[float, float, float], ...]
    provenance: dict[str, object]


class MediaProbe(Protocol):
    async def probe(self, path: Path, *, detected_content_type: str, media_kind: str) -> MediaMetadata: ...


class TranscriptionProvider(Protocol):
    key: str

    async def transcribe(
        self, path: Path, *, metadata: MediaMetadata, checksum_sha256: str
    ) -> ProviderTranscript: ...


class MediaSignalProvider(Protocol):
    key: str

    async def analyze(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        silence_threshold_db: float,
        minimum_silence_duration: float,
    ) -> MediaSignals: ...


def _ratio(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        if float(denominator) == 0:
            return None
        return round(float(numerator) / float(denominator), 6)
    return round(float(value), 6)


class FFprobeMediaProbe:
    def __init__(self, executable: str = "ffprobe", *, timeout_seconds: int = 60):
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    async def probe(self, path: Path, *, detected_content_type: str, media_kind: str) -> MediaMetadata:
        if media_kind == "subtitle":
            return MediaMetadata(media_kind="subtitle", detected_content_type=detected_content_type)
        if shutil.which(self.executable) is None and not Path(self.executable).is_file():
            raise MediaProbeError("ffprobe is not configured")
        command = [
            self.executable,
            "-v",
            "error",
            "-show_entries",
            "format=format_name,duration:stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
            "-of",
            "json",
            str(path),
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise MediaProbeError("ffprobe timed out") from exc
        if process.returncode != 0:
            raise MediaProbeError(f"ffprobe rejected media: {stderr.decode('utf-8', 'replace')[:300]}")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise MediaProbeError("ffprobe returned invalid JSON") from exc
        streams = payload.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        if media_kind == "video" and video is None:
            raise MediaProbeError("video stream is missing")
        if media_kind in {"audio", "music"} and audio is None:
            raise MediaProbeError("audio stream is missing")
        duration_value = payload.get("format", {}).get("duration")
        duration = float(duration_value) if duration_value not in {None, "N/A"} else None
        return MediaMetadata(
            media_kind=media_kind,
            detected_content_type=detected_content_type,
            format_name=payload.get("format", {}).get("format_name"),
            duration_seconds=round(duration, 6) if duration is not None else None,
            width=int(video["width"]) if video and video.get("width") else None,
            height=int(video["height"]) if video and video.get("height") else None,
            fps=_ratio(video.get("r_frame_rate")) if video else None,
            video_codec=video.get("codec_name") if video else None,
            audio_codec=audio.get("codec_name") if audio else None,
            audio_channels=int(audio["channels"]) if audio and audio.get("channels") else None,
            audio_sample_rate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        )


class DeterministicTranscriptionProvider:
    key = "fixture-transcription"
    _phrases = (
        "Ba giây đầu tiên quyết định người xem có tiếp tục hay không.",
        "Nội dung tốt cần một thông tin rõ ràng và bằng chứng dễ kiểm tra.",
        "Khoảng lặng hợp lý giúp nhịp dựng tự nhiên mà không cắt vào lời nói.",
        "Điểm nổi bật này phù hợp để thử nghiệm trên video ngắn.",
    )

    async def transcribe(
        self, path: Path, *, metadata: MediaMetadata, checksum_sha256: str
    ) -> ProviderTranscript:
        del path
        duration = max(float(metadata.duration_seconds or 12.0), 4.0)
        slot = duration / len(self._phrases)
        segments: list[ProviderSegment] = []
        for index, phrase in enumerate(self._phrases):
            start = index * slot + slot * 0.08
            end = min(duration, (index + 1) * slot - slot * 0.12)
            tokens = phrase.split()
            word_span = (end - start) / len(tokens)
            words = tuple(
                ProviderWord(
                    start_seconds=round(start + word_index * word_span, 6),
                    end_seconds=round(start + (word_index + 1) * word_span, 6),
                    text=token,
                    confidence=0.99,
                )
                for word_index, token in enumerate(tokens)
            )
            segments.append(
                ProviderSegment(
                    start_seconds=round(start, 6),
                    end_seconds=round(end, 6),
                    text=phrase,
                    speaker=None,
                    confidence=0.99,
                    words=words,
                )
            )
        return ProviderTranscript(
            language="vi",
            confidence=0.99,
            segments=tuple(segments),
            provenance={
                "fixture": True,
                "paid_call": False,
                "source_checksum": checksum_sha256,
                "original_evidence": True,
            },
        )


class ContractOnlyTranscriptionProvider:
    key = "transcription-not-configured"

    async def transcribe(
        self, path: Path, *, metadata: MediaMetadata, checksum_sha256: str
    ) -> ProviderTranscript:
        del path, metadata, checksum_sha256
        raise ProviderNotConfigured("live transcription provider is not configured")


class DeterministicMediaSignalProvider:
    key = "fixture-media-signals"

    async def analyze(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        silence_threshold_db: float,
        minimum_silence_duration: float,
    ) -> MediaSignals:
        del path
        duration = max(float(metadata.duration_seconds or 12.0), 4.0)
        slot = duration / 4
        boundaries = tuple((round(slot * index, 6), 0.86 - index * 0.04) for index in range(1, 4))
        silences: list[tuple[float, float, float]] = []
        for index in range(1, 4):
            start = slot * (index - 0.10)
            end = slot * (index + 0.06)
            if end - start >= minimum_silence_duration:
                silences.append((round(start, 6), round(end, 6), silence_threshold_db - 6))
        return MediaSignals(
            shot_boundaries=boundaries,
            silence_intervals=tuple(silences),
            provenance={"fixture": True, "paid_call": False, "deterministic": True},
        )


class FFmpegMediaSignalProvider:
    key = "ffmpeg-media-signals"
    _SHOT_TIME = re.compile(r"pts_time:([0-9.]+)")
    _SILENCE_START = re.compile(r"silence_start: ([0-9.]+)")
    _SILENCE_END = re.compile(r"silence_end: ([0-9.]+).+silence_duration: ([0-9.]+)")

    def __init__(self, executable: str = "ffmpeg", *, timeout_seconds: int = 300):
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    async def _run(self, arguments: list[str]) -> str:
        if shutil.which(self.executable) is None and not Path(self.executable).is_file():
            raise ProviderNotConfigured("ffmpeg media analysis is not configured")
        process = await asyncio.create_subprocess_exec(
            self.executable,
            *arguments,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError("ffmpeg analysis timed out") from exc
        if process.returncode != 0:
            raise RuntimeError(f"ffmpeg analysis failed: {stderr.decode('utf-8', 'replace')[:300]}")
        return stderr.decode("utf-8", "replace")

    async def analyze(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        silence_threshold_db: float,
        minimum_silence_duration: float,
    ) -> MediaSignals:
        shot_task = self._run(
            [
                "-hide_banner",
                "-i",
                str(path),
                "-filter:v",
                "select='gt(scene,0.35)',showinfo",
                "-f",
                "null",
                "-",
            ]
        )
        if metadata.audio_codec:
            shot_output, silence_output = await asyncio.gather(
                shot_task,
                self._run(
                    [
                        "-hide_banner",
                        "-i",
                        str(path),
                        "-af",
                        f"silencedetect=noise={silence_threshold_db}dB:d={minimum_silence_duration}",
                        "-f",
                        "null",
                        "-",
                    ]
                ),
            )
        else:
            shot_output = await shot_task
            silence_output = ""
        duration = float(metadata.duration_seconds or 0)
        boundaries = tuple(
            (timestamp, 0.8)
            for timestamp in sorted({float(match) for match in self._SHOT_TIME.findall(shot_output)})
            if 0.05 < timestamp < max(0, duration - 0.05)
        )
        starts = [float(value) for value in self._SILENCE_START.findall(silence_output)]
        ends = [(float(end), float(span)) for end, span in self._SILENCE_END.findall(silence_output)]
        silences = tuple(
            (start, end, silence_threshold_db)
            for start, (end, span) in zip(starts, ends, strict=False)
            if span >= minimum_silence_duration and end > start
        )
        return MediaSignals(
            shot_boundaries=boundaries,
            silence_intervals=silences,
            provenance={
                "fixture": False,
                "paid_call": False,
                "scene_detector": "ffmpeg-showinfo",
                "silence_detector": "ffmpeg-silencedetect" if metadata.audio_codec else "no-audio-stream",
            },
        )
