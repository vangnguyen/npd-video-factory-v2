"""Immutable fusion of saved evidence; never dispatches ASR or semantic Vision."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime,timezone
from typing import Any
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import StrictModel
from .auto_edit_db import SceneIntelligenceORM
from .auto_edit_providers import MediaSignals
from .auto_edit_logic import local_scene_metrics


class SceneIntelligenceConflict(ValueError):pass


class SceneIntelligenceRequest(StrictModel):
    analysis_id: str = Field(pattern=r'^ana_[A-Za-z0-9_-]{4,60}$')
    transcript_id: str | None = Field(default=None,pattern=r'^trn_[A-Za-z0-9_-]{4,60}$')
    vision_analysis_id: str | None = Field(default=None,pattern=r'^vis_[A-Za-z0-9_-]{4,60}$')


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


class SceneIntelligenceRead(StrictModel):
    assessment_id: str
    project_id: str
    analysis_id: str
    transcript_id: str | None
    vision_analysis_id: str | None
    fingerprint: str
    algorithm: str
    source_asset_sha256: str
    scenes: list[SceneObservation]
    provenance: dict[str,Any]
    actor_ref: str
    created_at: datetime


def read(row):
    return SceneIntelligenceRead(assessment_id=row.assessment_id,project_id=row.project_id,
        analysis_id=row.analysis_id,transcript_id=row.transcript_id,vision_analysis_id=row.vision_analysis_id,
        fingerprint=row.fingerprint,actor_ref=row.actor_ref,
        created_at=row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc),**row.snapshot_json)


def combine_scene_evidence(analysis,asset,vision=None):
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
            evidence={'quality_basis':'saved_structured_vision' if frames else metrics['quality_semantics'],
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
                    'evidence_frame_reference':f.evidence_frame_reference} for f in frames]}))
    return output


async def get_assessment(repository,project_id,assessment_id):
    async with repository.session_factory() as session:
        row=await session.get(SceneIntelligenceORM,assessment_id)
        if row is None or row.project_id!=project_id:raise KeyError(assessment_id)
        return read(row)


async def list_assessments(repository,project_id):
    async with repository.session_factory() as session:
        rows=(await session.scalars(select(SceneIntelligenceORM).where(SceneIntelligenceORM.project_id==project_id)
            .order_by(SceneIntelligenceORM.created_at.desc(),SceneIntelligenceORM.assessment_id).limit(100))).all()
        return [read(row) for row in rows]


async def create_assessment(repository,vision_repository,project_id,payload,actor_ref):
    analysis=await repository.get_analysis(payload.analysis_id,transcript_id=payload.transcript_id)
    if analysis is None or analysis.project_id!=project_id:raise KeyError(payload.analysis_id)
    if analysis.status!='succeeded':raise SceneIntelligenceConflict('source analysis is not ready')
    asset=await repository.get_asset(analysis.asset_id)
    if asset is None or asset.project_id!=project_id:raise KeyError(analysis.asset_id)
    if analysis.provenance.get('source_asset_checksum')!=asset.checksum_sha256:
        raise SceneIntelligenceConflict('source analysis checksum is stale')
    vision=None
    if payload.vision_analysis_id:
        if vision_repository is None:raise SceneIntelligenceConflict('Vision repository is not configured')
        vision=await vision_repository.get_analysis(payload.vision_analysis_id)
        if vision is None or vision.project_id!=project_id or vision.analysis_id!=analysis.analysis_id or vision.asset_id!=asset.asset_id:
            raise KeyError(payload.vision_analysis_id)
        if vision.status!='succeeded' or vision.provenance.get('source_asset_checksum')!=asset.checksum_sha256:
            raise SceneIntelligenceConflict('saved Vision evidence is not ready or source checksum differs')
    snapshot={'algorithm':'scene-intelligence-v1','source_asset_sha256':asset.checksum_sha256,
        'scenes':[scene.model_dump(mode='json') for scene in combine_scene_evidence(analysis,asset,vision)],
        'provenance':{'provider_dispatches':0,'source_analysis_fingerprint':analysis.fingerprint,
            'vision_fingerprint':vision.fingerprint if vision else None,'source_media_mutated':False,
            'fixture_asr':bool(analysis.transcript and analysis.transcript.provenance.get('fixture')),
            'vision_provider_evidence':vision.provenance.get('provider_evidence') if vision else None,
            'human_approval_required':True,'canonical_timeline_mutated':False}}
    transcript_id=analysis.transcript.transcript_id if analysis.transcript else None
    fingerprint=hashlib.sha256(json.dumps({'project_id':project_id,'analysis_id':analysis.analysis_id,
        'transcript_id':transcript_id,'vision_analysis_id':payload.vision_analysis_id,**snapshot},sort_keys=True).encode()).hexdigest()
    for attempt in range(3):
        async with repository.session_factory() as session:
            try:
                row=await session.scalar(select(SceneIntelligenceORM).where(SceneIntelligenceORM.project_id==project_id,
                    SceneIntelligenceORM.fingerprint==fingerprint))
                if row is None:
                    row=SceneIntelligenceORM(assessment_id='sci_'+uuid.uuid4().hex[:24],project_id=project_id,
                        analysis_id=analysis.analysis_id,transcript_id=transcript_id,vision_analysis_id=payload.vision_analysis_id,
                        fingerprint=fingerprint,snapshot_json=snapshot,actor_ref=actor_ref)
                    session.add(row);await session.commit()
                return read(row)
            except IntegrityError:
                await session.rollback()
                if attempt==2:raise
