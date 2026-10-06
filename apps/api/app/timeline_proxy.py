"""Pure timeline proxy rendering shared by API and Native; no repositories."""
from __future__ import annotations
import asyncio
import json
import math
import time
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol
from .platform_models import AssetRead
from .timeline_models import TimelineSnapshot
from .timeline_audio import build_timeline_audio_graph
from .auto_edit_providers import FFprobeMediaProbe


class PreviewCancelledError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProxyRenderResult:
    path: Path
    manifest: dict[str, object]


class ProxyRenderer(Protocol):
    async def render(
        self,
        *,
        snapshot: TimelineSnapshot,
        assets: dict[str, tuple[AssetRead, Path]],
        output_path: Path,
        width: int,
        height: int,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> ProxyRenderResult: ...


class DeterministicProxyRenderer:
    """Test-only renderer; its output is evidence, never represented as playable video."""

    async def render(
        self,
        *,
        snapshot: TimelineSnapshot,
        assets: dict[str, tuple[AssetRead, Path]],
        output_path: Path,
        width: int,
        height: int,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> ProxyRenderResult:
        if await is_cancelled():
            raise PreviewCancelledError("preview was cancelled")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(
            json.dumps(
                {
                    "fixture": True,
                    "duration_seconds": snapshot.duration_seconds,
                    "assets": sorted(assets),
                },
                sort_keys=True,
            ).encode("utf-8")
        )
        return ProxyRenderResult(
            path=output_path,
            manifest={
                "renderer": "deterministic-contract-fixture",
                "playable": False,
                "fixture": True,
                "audio_included": False,
            },
        )


class FFmpegProxyRenderer:
    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.media_probe = FFprobeMediaProbe(ffprobe_path)

    async def render(
        self,
        *,
        snapshot: TimelineSnapshot,
        assets: dict[str, tuple[AssetRead, Path]],
        output_path: Path,
        width: int,
        height: int,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> ProxyRenderResult:
        if await is_cancelled():
            raise PreviewCancelledError("preview was cancelled")
        if snapshot.duration_seconds > 3600:
            raise ValueError("PREVIEW_DURATION_LIMIT")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration = max(0.1, snapshot.duration_seconds)
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0b132b:s={width}x{height}:r=30:d={duration:.6f}",
        ]
        renderable: list[tuple[object, AssetRead, int]] = []
        ignored: list[str] = []
        for track in sorted(snapshot.tracks, key=lambda item: item.order):
            if track.type != "video" or track.disabled:
                continue
            for clip in track.clips:
                if clip.disabled or not clip.asset_id or clip.asset_id not in assets:
                    ignored.append(clip.clip_id)
                    continue
                asset, path = assets[clip.asset_id]
                content_type = asset.content_type.lower()
                supported_raster_types = {"image/jpeg", "image/png", "image/webp"}
                if not (content_type.startswith("video/") or content_type in supported_raster_types):
                    ignored.append(clip.clip_id)
                    continue
                if content_type.startswith("image/"):
                    command.extend(["-loop", "1", "-t", f"{clip.duration:.6f}", "-i", str(path)])
                else:
                    command.extend(
                        [
                            "-ss",
                            f"{clip.source_start:.6f}",
                            "-t",
                            f"{clip.source_end - clip.source_start:.6f}",
                            "-i",
                            str(path),
                        ]
                    )
                renderable.append((clip, asset, len(renderable) + 1))

        filters = ["[0:v]setpts=PTS-STARTPTS[base]"]
        previous = "base"
        rendered_ids: list[str] = []
        for ordinal, (clip, _asset, input_index) in enumerate(renderable):
            crop = clip.crop
            target_width = max(2, int(width * clip.transform.scale))
            target_height = max(2, int(height * clip.transform.scale))
            alpha = clip.opacity
            rotation_radians = clip.transform.rotation_degrees * math.pi / 180
            filters.append(
                f"[{input_index}:v]"
                f"crop=iw*{crop.width:.6f}:ih*{crop.height:.6f}:iw*{crop.x:.6f}:ih*{crop.y:.6f},"
                f"format=rgba,rotate={rotation_radians:.9f}:ow=rotw(iw):oh=roth(ih):c=black@0,"
                f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fps=30,setpts=(PTS-STARTPTS)/{clip.speed:.6f}+{clip.timeline_start:.6f}/TB,"
                f"format=rgba,colorchannelmixer=aa={alpha:.6f}[clip{ordinal}]"
            )
            output = f"layer{ordinal}"
            x = f"(W-w)/2+{clip.transform.x:.6f}*W/2"
            y = f"(H-h)/2+{clip.transform.y:.6f}*H/2"
            start = clip.timeline_start
            end = clip.timeline_start + clip.duration
            filters.append(
                f"[{previous}][clip{ordinal}]overlay=x={x}:y={y}:eof_action=pass:shortest=0:"
                f"enable='between(t,{start:.6f},{end:.6f})'[{output}]"
            )
            previous = output
            rendered_ids.append(clip.clip_id)
        filters.append(f"[{previous}]format=yuv420p[outv]")
        audio = build_timeline_audio_graph(snapshot, assets, first_input_index=len(renderable) + 1)
        probed_audio = {}
        for clip in audio.clips:
            if await is_cancelled():
                raise PreviewCancelledError("preview was cancelled")
            asset, path = assets[clip['asset_id']]
            if asset.asset_id not in probed_audio:
                probed_audio[asset.asset_id] = await self.media_probe.probe(path,
                    detected_content_type=asset.content_type, media_kind="video" if asset.content_type.startswith("video/") else "audio")
            metadata = probed_audio[asset.asset_id]
            if not metadata.audio_codec or not metadata.duration_seconds or clip['source_end'] > metadata.duration_seconds + .05:
                raise ValueError("PREVIEW_AUDIO_WINDOW_UNAVAILABLE")
        command.extend(audio.inputs)
        filters.extend(audio.filters)
        # Keep long edit graphs outside Windows' process command line.
        filter_path = output_path.with_suffix('.ffmpeg-filter.txt')
        filter_path.write_text(';'.join(filters), encoding='utf-8')
        command.extend(
            [
                "-/filter_complex",
                str(filter_path),
                "-map",
                "[outv]",
                *(["-map", "[outa]", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"] if audio.clips else ["-an"]),
                "-t",
                f"{duration:.6f}",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "30",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        if sys.platform == 'win32' and sum(len(argument) + 3 for argument in command) > 30000:
            raise ValueError('PREVIEW_INPUT_COMMAND_LIMIT')
        async def execute(command):
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            communication = asyncio.create_task(process.communicate())
            deadline = time.monotonic() + min(900, max(60, duration * 6))
            try:
                while not communication.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(communication), timeout=.25)
                    except TimeoutError:
                        if await is_cancelled():
                            raise PreviewCancelledError("preview was cancelled")
                        if time.monotonic() >= deadline:
                            raise RuntimeError("PREVIEW_RENDER_TIMEOUT")
                _, stderr_bytes = await communication
            except BaseException:
                if process.returncode is None:
                    process.kill()
                await communication
                output_path.unlink(missing_ok=True)
                raise
            return process.returncode, stderr_bytes.decode("utf-8", errors="replace")

        returncode, stderr = await execute(command)
        if returncode != 0 and "Unrecognized option '/filter_complex'" in stderr:
            # Older FFmpeg uses the legacy file option. Retry only parser
            # rejection, before media execution; never retry a failed encode.
            command[command.index('-/filter_complex')] = '-filter_complex_script'
            returncode, stderr = await execute(command)
        if returncode != 0 or not output_path.is_file():
            raise RuntimeError(f"ffmpeg proxy render failed: {stderr[-700:]}")
        return ProxyRenderResult(
            path=output_path,
            manifest={
                "renderer": "ffmpeg-proxy-v2",
                "playable": True,
                "fixture": False,
                "audio_included": bool(audio.clips),
                "audio_mixing": "canonical_timeline_volume_fades_limiter_v1",
                "audio_clip_receipts": audio.clips,
                "muted_audio_clip_ids": audio.muted_clip_ids,
                "audio_limiter_peak_db": -1 if audio.clips else None,
                "audio_speech_normalization": False,
                "music_ducking": False,
                "captions_included": False,
                "final_render_parity": False,
                "rendered_clip_ids": rendered_ids,
                "ignored_clip_ids": sorted(set(ignored)),
            },
        )


