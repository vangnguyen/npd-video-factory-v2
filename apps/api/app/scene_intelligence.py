"""Immutable fusion of saved evidence; never dispatches ASR or semantic Vision."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime,timezone
from typing import Any
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import StrictModel
from .auto_edit_db import SceneIntelligenceORM
from .scene_evidence import SceneObservation, combine_scene_evidence


class SceneIntelligenceConflict(ValueError):pass


class SceneIntelligenceRequest(StrictModel):
    analysis_id: str = Field(pattern=r'^ana_[A-Za-z0-9_-]{4,60}$')
    transcript_id: str | None = Field(default=None,pattern=r'^trn_[A-Za-z0-9_-]{4,60}$')
    vision_analysis_id: str | None = Field(default=None,pattern=r'^vis_[A-Za-z0-9_-]{4,60}$')


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
