"""Bounded FFmpeg audio graph derived solely from the canonical timeline."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import math
from typing import Any

from .platform_models import AssetRead
from .timeline_models import TimelineSnapshot


@dataclass(frozen=True)
class TimelineAudioGraph:
    inputs: list[str]
    filters: list[str]
    clips: list[dict[str, Any]]
    muted_clip_ids: list[str]


def tempo_filters(speed: float) -> list[str]:
    """Avoid sample-skipping tempo factors above two and support slow edits."""
    if not math.isfinite(speed) or not .1 <= speed <= 8:
        raise ValueError("PREVIEW_AUDIO_SPEED_RANGE")
    factors = []
    while speed > 2:
        factors.append(2.0)
        speed /= 2
    while speed < .5:
        factors.append(.5)
        speed /= .5
    if abs(speed - 1) > 1e-9:
        factors.append(speed)
    return [f"atempo={factor:.9f}" for factor in factors]


def build_timeline_audio_graph(snapshot: TimelineSnapshot, assets: dict[str, tuple[AssetRead, Path]], *,
                               first_input_index: int) -> TimelineAudioGraph:
    inputs, filters, receipts, muted = [], [], [], []
    for track in sorted(snapshot.tracks, key=lambda item: item.order):
        if track.type != "audio":
            continue
        for clip in track.clips:
            if track.disabled or track.muted or clip.disabled or clip.volume == 0:
                muted.append(clip.clip_id)
                continue
            if not clip.asset_id or clip.asset_id not in assets:
                raise ValueError("PREVIEW_AUDIO_ASSET_UNAVAILABLE")
            asset, path = assets[clip.asset_id]
            if not asset.content_type.startswith(("video/", "audio/")) or clip.source_end is None:
                raise ValueError("PREVIEW_AUDIO_SOURCE_INVALID")
            if len(receipts) >= 128:
                raise ValueError("PREVIEW_AUDIO_CLIP_LIMIT")
            index = first_input_index + len(receipts)
            inputs.extend(["-i", str(path)])
            chain = [f"[{index}:a:0]atrim=start={clip.source_start:.9f}:end={clip.source_end:.9f}",
                     "asetpts=PTS-STARTPTS", *tempo_filters(clip.speed),
                     "aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo",
                     f"volume={clip.volume:.9f}", f"atrim=duration={clip.duration:.9f}"]
            for direction, transition in (("in", clip.transition_in), ("out", clip.transition_out)):
                if transition.kind in {"fade", "crossfade"} and transition.duration_seconds > 0:
                    length = min(transition.duration_seconds, clip.duration)
                    start = 0 if direction == "in" else max(0, clip.duration - length)
                    chain.append(f"afade=t={direction}:st={start:.9f}:d={length:.9f}")
            delay_samples = round(clip.timeline_start * 48000)
            chain.append(f"adelay=delays={delay_samples}S:all=1[audio{len(receipts)}]")
            filters.append(",".join(chain))
            receipts.append({"clip_id": clip.clip_id, "track_id": track.track_id, "asset_id": clip.asset_id,
                             "source_sha256": asset.checksum_sha256, "source_start": clip.source_start,
                             "source_end": clip.source_end, "timeline_start": clip.timeline_start,
                             "duration": clip.duration, "speed": clip.speed, "volume": clip.volume})
    if receipts:
        labels = "".join(f"[audio{index}]" for index in range(len(receipts)))
        filters.append(f"{labels}amix=inputs={len(receipts)}:duration=longest:dropout_transition=0:normalize=0,"
                       "alimiter=limit=0.891250938:level=0:latency=1,apad,"
                       f"atrim=duration={snapshot.duration_seconds:.9f},asetpts=PTS-STARTPTS[outa]")
    return TimelineAudioGraph(inputs, filters, receipts, muted)
