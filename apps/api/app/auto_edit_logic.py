from __future__ import annotations

import re
from typing import Any

from .asr_derived_timing import DownstreamTranscript
from .auto_edit_models import AutoEditAnalysisRequest
from .auto_edit_providers import MediaSignals


_HOOK_WORDS = {
    "quan trọng",
    "cơ hội",
    "lưu ý",
    "quyết định",
    "bằng chứng",
    "điểm nổi bật",
    "thử nghiệm",
    "important", "opportunity", "evidence", "breakthrough", "how to", "mistake",
}


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


def local_scene_metrics(signals: MediaSignals, start: float, end: float) -> dict[str,Any]:
    frames=[item for item in (signals.visual or {}).get('frames',[]) if start<=item['timestamp_seconds']<end]
    motion=[item['temporal_difference'] for item in frames if item['temporal_difference'] is not None]
    audio=[(item,max(0.,min(end,item['end_seconds'])-max(start,item['start_seconds'])))
        for item in (signals.waveform or {}).get('bins',[]) if min(end,item['end_seconds'])>max(start,item['start_seconds'])]
    span=sum(weight for _,weight in audio)
    rms=(sum(item['rms']**2*weight for item,weight in audio)/span)**.5 if span else None
    mean=lambda key:sum(item[key] for item in frames)/len(frames) if frames else None
    black=mean('black_frame');bright=mean('overexposure_candidate');dark=mean('underexposure_candidate')
    return {'sample_count':len(frames),'motion_score':_clamp(sum(motion)/len(motion)*5) if motion else None,
        'motion_semantics':'sampled pixel difference scaled by 5; not optical flow or subject tracking',
        'local_quality_score':_clamp(1-black-.4*bright-.4*dark) if frames else None,
        'quality_semantics':'exposure/black-frame heuristic over measured pixels; semantic quality requires Vision',
        'black_frame_ratio':black,'overexposure_ratio':bright,'underexposure_ratio':dark,
        'mean_luma':mean('mean_luma'),'mean_edge_strength':mean('edge_strength'),
        'duplicate_frame_ratio':sum(item['identical_to_previous'] is True for item in frames)/len(frames) if frames else None,
        'audio_rms':round(rms,6) if rms is not None else None,
        'audio_energy_score':_clamp(rms*5) if rms is not None else None,
        'sample_timestamps':[item['timestamp_seconds'] for item in frames]}


def build_scenes(
    *, duration: float, signals: MediaSignals, transcript: DownstreamTranscript | None
) -> list[dict[str, Any]]:
    segments = transcript.value.segments if transcript is not None else ()
    boundary_values = sorted(
        {round(float(timestamp), 6) for timestamp, _ in signals.shot_boundaries if 0 < timestamp < duration}
    )
    points = [0.0, *boundary_values, duration]
    scenes: list[dict[str, Any]] = []
    for ordinal, (start, end) in enumerate(zip(points, points[1:])):
        if end - start < 0.08:
            continue
        matching = [
            segment
            for segment in segments
            if _overlap(start, end, segment.start_seconds, segment.end_seconds) > 0
        ]
        text = " ".join(segment.text for segment in matching).strip()
        words = re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)
        speech_seconds = sum(
            _overlap(start, end, segment.start_seconds, segment.end_seconds) for segment in matching
        )
        speech_score = _clamp(speech_seconds / max(end - start, 0.001))
        boundary_score = next(
            (score for timestamp, score in signals.shot_boundaries if abs(timestamp - start) < 0.001),
            0.55 if ordinal else 0.5,
        )
        label = "Mở đầu" if ordinal == 0 else f"Phân đoạn {ordinal + 1}"
        metrics=local_scene_metrics(signals,start,end)
        scenes.append(
            {
                "ordinal": ordinal,
                "start_seconds": round(start, 6),
                "end_seconds": round(end, 6),
                "semantic_label": label,
                "description": text[:500] or "Phân đoạn hình ảnh không có lời thoại nhận diện.",
                "subjects": [],
                "quality_score": metrics['local_quality_score'] if metrics['local_quality_score'] is not None else _clamp(0.62 + 0.18 * speech_score),
                "motion_score": metrics['motion_score'] if metrics['motion_score'] is not None else _clamp(float(boundary_score)),
                "speech_score": speech_score,
                "confidence": _clamp(0.55 + 0.2 * float(boundary_score) + 0.2 * speech_score),
                "evidence": {
                    "shot_boundary": ordinal > 0,
                    "transcript_segment_count": len(matching),
                    "transcript_keywords":list(dict.fromkeys(word.casefold() for word in words if len(word)>=5))[:6],
                    "subjects_available":False,
                    "local_metrics":metrics,
                    "motion_score_basis":"measured_pixel_difference" if metrics['motion_score'] is not None else "legacy_boundary_heuristic_not_measured_motion",
                    "quality_score_basis":"measured_exposure_heuristic" if metrics['local_quality_score'] is not None else "legacy_speech_heuristic_not_measured_quality",
                    "confidence_basis":"heuristic_boundary_and_transcript_coverage_not_provider_probability",
                    "audio_boundaries":[{'start_seconds':a,'end_seconds':b} for a,b,_ in signals.silence_intervals if _overlap(start,end,a,b)>0],
                    "shot_detection_score":float(boundary_score) if ordinal else None,
                    "vision_used": False,
                    "vision_deferred_to": "V2-05",
                },
            }
        )
    return scenes


def build_silence_decisions(
    *,
    signals: MediaSignals,
    transcript: DownstreamTranscript,
    config: AutoEditAnalysisRequest,
) -> list[dict[str, Any]]:
    # Word timing is optional. A segment without words is a protected speech
    # interval, not permission to cut through speech at low audio energy.
    protected=[(word.start_seconds,word.end_seconds,'word') for segment in transcript.value.segments for word in segment.words]
    protected += [(segment.start_seconds,segment.end_seconds,'segment_without_word_timestamps')
                  for segment in transcript.value.segments if not segment.words]
    decisions: list[dict[str, Any]] = []
    for raw_start, raw_end, measured_db in signals.silence_intervals:
        start = round(raw_start + config.padding_before, 6)
        end = round(raw_end - config.padding_after, 6)
        conflicts = any(_overlap(start,end,a,b)>0 for a,b,_ in protected)
        long_enough = end - start >= config.minimum_silence_duration
        enabled = long_enough and not conflicts
        reason = (
            "Disabled because the proposed cut overlaps a spoken word."
            if conflicts
            else "Non-destructive silence cut proposed from audio energy and transcript gaps."
            if long_enough
            else "Disabled because padding leaves less than the minimum silence duration."
        )
        decisions.append(
            {
                "start_seconds": max(0.0, start),
                "end_seconds": max(max(0.0, start) + 0.000001, end),
                "padding_before_seconds": config.padding_before,
                "padding_after_seconds": config.padding_after,
                "enabled": enabled,
                "reason": reason,
                "conflicts_with_speech": conflicts,
                "evidence": {
                    "raw_start": raw_start,
                    "raw_end": raw_end,
                    "measured_db": measured_db,
                    "measured_db_available": measured_db is not None,
                    "speech_protection": sorted({kind for a,b,kind in protected if _overlap(start,end,a,b)>0}),
                    "threshold_db": config.silence_threshold_db,
                    "minimum_duration": config.minimum_silence_duration,
                    "source_media_mutated": False,
                },
            }
        )
    return decisions


def build_highlights(
    *, scenes: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for scene in scenes:
        text = str(scene["description"]).casefold()
        hooks = sorted(word for word in _HOOK_WORDS if word in text)
        word_count = len(text.split())
        information_density = _clamp(word_count / max(12.0, (scene["end_seconds"] - scene["start_seconds"]) * 3.2))
        hook_score = min(1.0, len(hooks) * 0.3)
        observed=scene.get('evidence',{});local=observed.get('local_metrics')
        motion=local.get('motion_score') if local is not None else scene.get('motion_score')
        quality=scene.get('quality_score') if observed.get('vision_used') else (
            local.get('local_quality_score') if local is not None else None)
        audio=local.get('audio_energy_score') if local is not None else None
        novelty=1-local['duplicate_frame_ratio'] if local is not None and local.get('duplicate_frame_ratio') is not None else None
        factors={'speech_coverage':float(scene['speech_score']) if scene.get('speech_score') is not None else None,'motion':motion,'information_density':information_density,
            'hook_keywords':hook_score,'quality':quality,'pixel_novelty':novelty,'audio_energy':audio}
        weights={'speech_coverage':.25,'motion':.15,'information_density':.2,'hook_keywords':.15,
            'quality':.1,'pixel_novelty':.05,'audio_energy':.1}
        present={key:value for key,value in factors.items() if value is not None}
        total=sum(weights[key] for key in present)
        contributions={key:round(weights[key]/total*float(value),6) for key,value in present.items()}
        score=_clamp(sum(contributions.values()))
        duration = float(scene["end_seconds"] - scene["start_seconds"])
        platform = "youtube" if duration > 60 else "facebook_reels"
        reasons = ['transcript coverage and keyword heuristics', 'information density']
        if motion is not None:reasons.append('measured pixel-change proxy' if local is not None else 'legacy scene score (unverified motion)')
        if audio is not None:reasons.append('measured audio energy')
        if quality is not None:reasons.append('saved Vision quality' if observed.get('vision_used') else 'measured exposure heuristic')
        if hooks:
            reasons.append(f"hook keywords: {', '.join(hooks)}")
        candidates.append(
            {
                "scene_ordinal": scene["ordinal"],
                "highlight_score": score,
                "reason": "; ".join(reasons),
                "recommended_start": scene["start_seconds"],
                "recommended_end": scene["end_seconds"],
                "recommended_platform": platform,
                "evidence": {
                    "algorithm":"multimodal-highlight-v2",
                    "speech_semantics": "keyword/information-density heuristic; no semantic model dispatched",
                    "audio_proxy": audio,
                    "motion": motion,
                    "information_density": information_density,
                    "hook_keywords": hooks,
                    "vision_used": bool(observed.get('vision_used')),
                    "factors":factors,"weights":weights,"available_weight":total,"contributions":contributions,
                    "missing_factors":[key for key,value in factors.items() if value is None],
                    "confidence":_clamp(float(scene.get('confidence') or 0)*total),
                },
            }
        )
    selected = sorted(
        candidates,
        key=lambda item: (-float(item["highlight_score"]), int(item["scene_ordinal"])),
    )[:top_k]
    for rank, item in enumerate(selected, start=1):
        item["rank"] = rank
    return selected
