from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any


class ProductionQCError(RuntimeError):
    def __init__(self, message: str, report: dict[str, Any]):
        self.report = report
        super().__init__(message)


class DeterministicProductionQC:
    async def inspect(
        self,
        path: Path,
        *,
        expected_duration: float,
        expected_width: int,
        expected_height: int,
        expected_fps: float,
        subtitle_qc: dict[str, Any],
        timeline_qc: dict[str, Any],
    ) -> dict[str, Any]:
        if not path.is_file() or path.stat().st_size == 0:
            raise ProductionQCError("deterministic render artifact is missing", {"status": "failed"})
        return {
            "status": "passed",
            "profile": "deterministic-test",
            "duration_seconds": expected_duration,
            "width": expected_width,
            "height": expected_height,
            "fps": expected_fps,
            "video_codec": "h264",
            "audio_codec": "aac",
            "black_frame_ratio": 0,
            "freeze_frame_ratio": 0,
            "silence_ratio": 0,
            "audio_peak_db": -1,
            "audio_clipping": False,
            "broken_frames": 0,
            "av_sync_delta_seconds": 0,
            "subtitle_bounds": subtitle_qc,
            "timeline": timeline_qc,
            "sampled_vision_qc": {"status": "passed", "provider": "deterministic-signal-fixture"},
            "checksum_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "publishing_blocked": True,
        }


class FullProductionQC:
    def __init__(self, *, ffprobe_path: str = "ffprobe", ffmpeg_path: str = "ffmpeg"):
        self.ffprobe_path = ffprobe_path
        self.ffmpeg_path = ffmpeg_path

    async def inspect(
        self,
        path: Path,
        *,
        expected_duration: float,
        expected_width: int,
        expected_height: int,
        expected_fps: float,
        subtitle_qc: dict[str, Any],
        timeline_qc: dict[str, Any],
    ) -> dict[str, Any]:
        base = {
            "status": "failed",
            "expected": {
                "duration_seconds": expected_duration,
                "width": expected_width,
                "height": expected_height,
                "fps": expected_fps,
            },
            "subtitle_bounds": subtitle_qc,
            "timeline": timeline_qc,
            "publishing_blocked": True,
        }
        if not path.is_file() or path.stat().st_size < 10_000:
            raise ProductionQCError("render output is missing or implausibly small", base)

        probe = await self._probe(path)
        streams = probe.get("streams") or []
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        if video is None or audio is None:
            raise ProductionQCError("render output requires both video and audio streams", {**base, "probe": probe})
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
        fps = _parse_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate"))
        duration = float((probe.get("format") or {}).get("duration") or video.get("duration") or 0)
        video_duration = float(video.get("duration") or duration)
        audio_duration = float(audio.get("duration") or duration)
        metadata = {
            "duration_seconds": round(duration, 3),
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "video_codec": video.get("codec_name"),
            "audio_codec": audio.get("codec_name"),
            "sample_rate": int(audio.get("sample_rate") or 0),
            "av_sync_delta_seconds": round(abs(video_duration - audio_duration), 3),
            "size_bytes": path.stat().st_size,
        }
        failures: list[str] = []
        if width != expected_width or height != expected_height:
            failures.append("resolution does not match the requested render profile")
        if abs(fps - expected_fps) > 0.02:
            failures.append("frame rate does not match the timeline")
        if abs(duration - expected_duration) > 0.5:
            failures.append("render duration differs from the timeline")
        if video.get("codec_name") != "h264":
            failures.append("final video codec must be H.264")
        if audio.get("codec_name") != "aac":
            failures.append("final audio codec must be AAC")
        if int(audio.get("sample_rate") or 0) != 48_000:
            failures.append("final audio sample rate must be 48 kHz")
        if metadata["av_sync_delta_seconds"] > 0.25:
            failures.append("audio/video stream durations are out of sync")

        black, freeze, volume, silence, vision, decode = await asyncio.gather(
            self._black(path, duration),
            self._freeze(path, duration),
            self._volume(path),
            self._silence(path, duration),
            self._vision_samples(path),
            self._decode(path),
        )
        if black["black_frame_ratio"] > 0.10:
            failures.append("black-frame ratio exceeds 10 percent")
        if freeze["freeze_frame_ratio"] > 0.15:
            failures.append("freeze-frame ratio exceeds 15 percent")
        if volume["audio_peak_db"] < -35:
            failures.append("audio is effectively silent")
        if volume["audio_peak_db"] > -0.05:
            failures.append("audio may be clipping")
        if silence["silence_ratio"] > 0.80:
            failures.append("audio silence exceeds 80 percent of the output")
        if vision["dark_visual_sample_ratio"] > 0.10:
            failures.append("sampled Vision QC found excessive dark output")
        if decode["broken_frames"]:
            failures.append("render contains undecodable or broken frames")
        if subtitle_qc.get("status") != "passed":
            failures.append("subtitle safe-area validation failed")
        if timeline_qc.get("status") != "passed":
            failures.append("timeline renderability validation failed")

        report = {
            **base,
            **metadata,
            **black,
            **freeze,
            **volume,
            **silence,
            **decode,
            "sampled_vision_qc": vision,
            "checksum_sha256": _sha256(path),
            "failures": failures,
        }
        if failures:
            raise ProductionQCError("; ".join(failures), report)
        report["status"] = "passed"
        return report

    async def _probe(self, path: Path) -> dict[str, Any]:
        stdout, _stderr = await _run(
            [
                self.ffprobe_path,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(path),
            ],
            "ffprobe",
        )
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ProductionQCError("ffprobe returned invalid JSON", {"status": "failed"}) from exc

    async def _black(self, path: Path, duration: float) -> dict[str, Any]:
        _stdout, stderr = await _run(
            [self.ffmpeg_path, "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.20:pix_th=0.10", "-an", "-f", "null", "-"],
            "black-frame inspection",
        )
        total = sum(float(item) for item in re.findall(r"black_duration:([0-9.]+)", stderr))
        return {"black_frame_seconds": round(total, 3), "black_frame_ratio": round(total / max(duration, 0.001), 4)}

    async def _freeze(self, path: Path, duration: float) -> dict[str, Any]:
        _stdout, stderr = await _run(
            [self.ffmpeg_path, "-hide_banner", "-i", str(path), "-vf", "freezedetect=n=0.003:d=0.5", "-an", "-f", "null", "-"],
            "freeze-frame inspection",
        )
        total = sum(float(item) for item in re.findall(r"freeze_duration:\s*([0-9.]+)", stderr))
        return {"freeze_frame_seconds": round(total, 3), "freeze_frame_ratio": round(total / max(duration, 0.001), 4)}

    async def _volume(self, path: Path) -> dict[str, Any]:
        _stdout, stderr = await _run(
            [self.ffmpeg_path, "-hide_banner", "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"],
            "audio volume inspection",
        )
        mean_match = re.search(r"mean_volume:\s*(-?(?:inf|\d+(?:\.\d+)?))\s*dB", stderr, re.I)
        peak_match = re.search(r"max_volume:\s*(-?(?:inf|\d+(?:\.\d+)?))\s*dB", stderr, re.I)
        if mean_match is None or peak_match is None:
            raise ProductionQCError("audio volume metadata is unavailable", {"status": "failed"})
        mean = float(mean_match.group(1))
        peak = float(peak_match.group(1))
        return {"audio_mean_db": round(mean, 3), "audio_peak_db": round(peak, 3), "audio_clipping": peak > -0.05}

    async def _silence(self, path: Path, duration: float) -> dict[str, Any]:
        _stdout, stderr = await _run(
            [self.ffmpeg_path, "-hide_banner", "-i", str(path), "-vn", "-af", "silencedetect=n=-45dB:d=0.5", "-f", "null", "-"],
            "audio silence inspection",
        )
        total = sum(float(item) for item in re.findall(r"silence_duration:\s*([0-9.]+)", stderr))
        return {"silence_seconds": round(total, 3), "silence_ratio": round(total / max(duration, 0.001), 4)}

    async def _vision_samples(self, path: Path) -> dict[str, Any]:
        stdout, _stderr = await _run(
            [
                self.ffmpeg_path,
                "-v",
                "error",
                "-i",
                str(path),
                "-vf",
                "fps=1,crop=iw*0.5:ih*0.4:iw*0.25:ih*0.3,signalstats,metadata=mode=print:file=-",
                "-an",
                "-f",
                "null",
                "-",
            ],
            "sampled Vision QC",
        )
        values = [float(item) for item in re.findall(r"lavfi\.signalstats\.YAVG=([0-9.eE+-]+)", stdout)]
        if not values:
            raise ProductionQCError("sampled Vision QC produced no frames", {"status": "failed"})
        dark = sum(item < 8 for item in values)
        return {
            "status": "passed",
            "provider": "ffmpeg-signalstats",
            "sample_count": len(values),
            "dark_visual_sample_ratio": round(dark / len(values), 4),
            "luma_min": round(min(values), 3),
            "luma_max": round(max(values), 3),
            "external_vision_call": False,
        }

    async def _decode(self, path: Path) -> dict[str, Any]:
        _stdout, stderr = await _run(
            [self.ffmpeg_path, "-v", "error", "-i", str(path), "-f", "null", "-"],
            "decode inspection",
        )
        errors = [line for line in stderr.splitlines() if line.strip()]
        return {"broken_frames": len(errors), "decode_errors": errors[:5]}


def _parse_fraction(value: Any) -> float:
    try:
        numerator, denominator = str(value).split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise ProductionQCError("frame rate metadata is unavailable", {"status": "failed"}) from exc


async def _run(command: list[str], label: str) -> tuple[str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise ProductionQCError(f"{label} failed", {"status": "failed", "tool": label, "detail": err[-700:]})
    return out, err


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
