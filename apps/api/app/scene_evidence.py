"""Pure scene-evidence fusion shared by HTTP and Native persistence adapters."""
from __future__ import annotations
import re
from typing import Any
from pydantic import Field
from .models import StrictModel
from .auto_edit_providers import MediaSignals
from .auto_edit_logic import local_scene_metrics
from .media_frame_facts import MeasuredFrame


class SceneObservation(StrictModel):
    scene_id: str
    ordinal: int = Field(ge=0)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    semantic_label: str
    description: str
    transcript_excerpt: str
    subjects: list[dict[str,Any]]
    quality_score: float | None = Field(default=None,ge=0,le=1)
    motion_score: float | None = Field(default=None,ge=0,le=1)
    speech_score: float | None = Field(default=None,ge=0,le=1)
    confidence: float | None = Field(default=None,ge=0,le=1)
    needs_attention: bool
    evidence: dict[str,Any]


def combine_scene_evidence(analysis,asset,vision=None,*,pixel_frames=()):
    pixels=[frame if isinstance(frame,MeasuredFrame) else MeasuredFrame.model_validate(frame) for frame in pixel_frames]
    if any(frame.source_sha256!=asset.checksum_sha256 for frame in pixels):
        raise ValueError('pixel observations source checksum mismatch')
    signals=analysis.provenance.get('media_signals',{})
    local=MediaSignals((),(),{},waveform=signals.get('waveform'),visual=signals.get('visual'))
    output=[]
    for source in analysis.scenes:
        start,end=source.start_seconds,source.end_seconds
        segments=[s for s in (analysis.transcript.segments if analysis.transcript else [])
            if min(end,s.end_seconds)>max(start,s.start_seconds)]
        text=' '.join(segment.text for segment in segments)
        metrics=local_scene_metrics(local,start,end)
        frames=[f for f in (vision.frames if vision else []) if start<=f.timestamp_seconds<end]
        samples=[f for f in pixels if start<=f.timestamp_seconds<end]
        semantics=[s for s in (vision.scenes if vision else []) if s.scene_id==source.scene_id and s.evidence_frame_ids]
        speech=min(1.,sum(min(end,s.end_seconds)-max(start,s.start_seconds) for s in segments)/(end-start)) if analysis.transcript else (0. if analysis.source_media.audio_codec is None else None)
        subjects=[]
        for frame in frames:
            subjects.extend({'label':item.label,'category':item.category,'confidence':item.confidence,
                'bounding_box':item.bounding_box.model_dump(mode='json'),'frame_id':frame.frame_id,
                'timestamp_seconds':frame.timestamp_seconds,'provider':frame.provider_key,'model':frame.model,
                'evidence_frame_reference':frame.evidence_frame_reference} for item in frame.objects if item.category not in {'text','logo'})
        confidences=[frame.confidence for frame in frames]
        if not confidences:confidences=[segment.confidence for segment in segments if segment.confidence is not None]
        confidence=round(sum(confidences)/len(confidences),6) if confidences else None
        quality=round(sum(frame.quality.quality_score for frame in frames)/len(frames),6) if frames else metrics['local_quality_score']
        if not frames and samples:quality=round(sum(f.pixel_facts.heuristic_quality_score for f in samples)/len(samples),6)
        semantic=semantics[0] if semantics else None
        output.append(SceneObservation(scene_id=source.scene_id,ordinal=source.ordinal,start_seconds=start,end_seconds=end,
            semantic_label=semantic.semantic_label if semantic else (' '.join(text.split()[:8]) or source.semantic_label),
            description=semantic.description if semantic else text[:2000] or source.description,
            transcript_excerpt=text[:2000],subjects=subjects,quality_score=quality,motion_score=metrics['motion_score'],
            speech_score=speech,confidence=confidence,
            needs_attention=not frames or confidence is None or confidence<.6 or quality is None or quality<.5
                or bool(analysis.provenance.get('semantic_analysis_refresh_required'))
                or any(not frame.composition.safe_crop or frame.quality.black_frame for frame in frames)
                or bool(metrics['black_frame_ratio'] and metrics['black_frame_ratio']>.25),
            evidence={'quality_basis':'saved_structured_vision' if frames else 'uncalibrated sampled pixel sharpness/brightness heuristic' if samples else metrics['quality_semantics'],
                'pixel_quality_confidence':None,'pixel_quality_semantic_inference':False,
                'pixel_quality_facts':[frame.model_dump(mode='json') for frame in samples],
                'motion_basis':metrics['motion_semantics'],'local_metrics':metrics,'vision_used':bool(frames),
                'confidence_basis':'mean of saved provider evidence, not a calibrated fusion probability',
                'source_asset_sha256':asset.checksum_sha256,'source_scene_id':source.scene_id,
                'transcript_segment_ids':[s.segment_id for s in segments],'transcript_excerpt_truncated':len(text)>2000,
                'transcript_keywords':list(dict.fromkeys(word.casefold() for word in re.findall(r'[\wÀ-ỹ]+',text) if len(word)>=5))[:6],
                'semantics_may_be_stale':bool(analysis.provenance.get('semantic_analysis_refresh_required')),
                'vision_quality_issues':[{'frame_id':frame.frame_id,'quality':frame.quality.model_dump(mode='json'),
                    'safe_crop':frame.composition.safe_crop} for frame in frames],
                'audio_boundaries':source.evidence.get('audio_boundaries',[]),
                'shot_detection_score':source.evidence.get('shot_detection_score'),
                'provider_dispatches':0,'frame_evidence':[{'frame_id':f.frame_id,'timestamp_seconds':f.timestamp_seconds,
                    'provider':f.provider_key,'model':f.model,'confidence':f.confidence,
                    'evidence_frame_reference':f.evidence_frame_reference} for f in frames]+[{'frame_id':f.frame_id,
                    'timestamp_seconds':f.timestamp_seconds,'provider':f.provider,'model':f.model,'confidence':None,
                    'evidence_frame_reference':f.reference,'sha256':f.sha256} for f in samples]}))
    return output


