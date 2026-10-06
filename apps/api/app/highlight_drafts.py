"""Saved, reversible highlight drafts over the existing canonical timeline."""
from __future__ import annotations
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Literal
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auto_edit_db import HighlightDraftORM
from .auto_edit_logic import build_highlights
from .models import StrictModel
from .timeline_logic import build_initial_timeline, TimelineEditError
from .timeline_models import TimelineSnapshot
from .timeline_repository import TimelineRepository


class HighlightDraftConflict(ValueError):pass


class HighlightDraftRequest(StrictModel):
    analysis_id: str = Field(pattern=r'^ana_[A-Za-z0-9_-]{4,60}$')
    transcript_id: str | None = Field(default=None, pattern=r'^trn_[A-Za-z0-9_-]{4,60}$')
    scene_intelligence_id: str | None = Field(default=None,pattern=r'^sci_[A-Za-z0-9_-]{4,60}$')
    count: Literal[3,5] = 3
    mode: Literal['top_highlights','auto_shorts'] = 'top_highlights'
    maximum_duration_seconds: float = Field(default=60,ge=3,le=180)


class HighlightDraftApply(StrictModel):
    expected_timeline_version: int | None = Field(default=None,ge=1,strict=True)


class HighlightDraftRead(StrictModel):
    draft_id: str
    project_id: str
    analysis_id: str
    transcript_id: str | None
    fingerprint: str
    snapshot: TimelineSnapshot
    evidence: dict[str,Any]
    actor_ref: str
    created_at: datetime


def _read(row):
    return HighlightDraftRead(draft_id=row.draft_id,project_id=row.project_id,analysis_id=row.analysis_id,
        transcript_id=row.transcript_id,fingerprint=row.fingerprint,snapshot=TimelineSnapshot.model_validate(row.snapshot_json),
        evidence=row.evidence_json,actor_ref=row.actor_ref,created_at=row.created_at)


def protected_window(start,end,transcript,duration):
    """Extend selection outward, never cut through a measured word/speech interval."""
    intervals=[]
    if transcript:
        for segment in transcript.segments:
            intervals.extend((word.start_seconds,word.end_seconds) for word in segment.words)
            if not segment.words:intervals.append((segment.start_seconds,segment.end_seconds))
    # Expansions can touch another interval; reach a fixed point without guessing words.
    while True:
        before=(start,end)
        for a,b in intervals:
            if a<start<b:start=a
            if a<end<b:end=b
        if before==(start,end):break
    return max(0.,start),min(duration,end)


def build_drafts(analysis,asset,payload,assessment=None):
    if analysis.status!='succeeded':raise HighlightDraftConflict('analysis is not ready')
    scenes=[scene.model_dump(mode='json') for scene in (assessment.scenes if assessment else analysis.scenes)]
    # Re-score against the exact selected transcript, including human text edits;
    # saved physical scene observations and provider evidence remain unchanged.
    for scene in scenes:
        if analysis.transcript:
            segments=[segment for segment in analysis.transcript.segments
                if min(scene['end_seconds'],segment.end_seconds)>max(scene['start_seconds'],segment.start_seconds)]
            if segments or not scene.get('evidence',{}).get('vision_used'):
                scene['description']=' '.join(segment.text for segment in segments)
            scene['evidence']={**scene.get('evidence',{}),'transcript_segment_count':len(segments),
                'transcript_segment_ids':[segment.segment_id for segment in segments]}
    scored=build_highlights(scenes=scenes,top_k=5)
    drafts=[]
    for item in scored:
        start,end=protected_window(item['recommended_start'],item['recommended_end'],analysis.transcript,
                                  float(analysis.source_media.duration_seconds))
        # Auto Shorts preserves complete speech; an over-limit selection needs editing.
        if end-start>payload.maximum_duration_seconds:continue
        windows=[scene.model_copy(update={'start_seconds':max(start,scene.start_seconds),'end_seconds':min(end,scene.end_seconds)})
            for scene in analysis.scenes if min(end,scene.end_seconds)-max(start,scene.start_seconds)>=.05]
        selected=analysis.model_copy(update={'scenes':windows,'silence_decisions':[]})
        snapshot=build_initial_timeline(analysis=selected,source_asset=asset,media_plan=None,media_assets={},silence_decision_ids=[])
        evidence={'algorithm':'highlight-draft-v2','source_start':start,'source_end':end,
            'score':item['highlight_score'],'reason':item['reason'],'factors':item['evidence'],
            'source_asset_sha256':asset.checksum_sha256,'scoring_transcript_id':analysis.transcript.transcript_id if analysis.transcript else None,
            'scene_intelligence_id':assessment.assessment_id if assessment else None,
            'scene_intelligence_fingerprint':assessment.fingerprint if assessment else None,
            'mode':payload.mode,'maximum_duration_seconds':payload.maximum_duration_seconds,
            'speech_protection':'whole_segment_when_no_words','human_approval_required':True,'provider_dispatches':0,
            'fixture_asr':bool(analysis.transcript and analysis.transcript.provenance.get('fixture'))}
        fingerprint=hashlib.sha256(json.dumps({'project_id':analysis.project_id,'analysis_id':analysis.analysis_id,**evidence},sort_keys=True).encode()).hexdigest()
        snapshot.metadata['highlight_draft']={'fingerprint':fingerprint,**evidence}
        drafts.append((fingerprint,snapshot,evidence))
        if len(drafts)>=payload.count:break
    return drafts


async def list_drafts(repository,project_id):
    async with repository.session_factory() as session:
        rows=(await session.scalars(select(HighlightDraftORM).where(HighlightDraftORM.project_id==project_id)
                                   .order_by(HighlightDraftORM.created_at.desc(),HighlightDraftORM.draft_id))).all()
        return [_read(row) for row in rows]


async def create_drafts(repository,project_id,payload,actor_ref):
    analysis=await repository.get_analysis(payload.analysis_id,transcript_id=payload.transcript_id)
    if analysis is None or analysis.project_id!=project_id:raise KeyError(payload.analysis_id)
    asset=await repository.get_asset(analysis.asset_id)
    if asset is None or asset.project_id!=project_id:raise KeyError(analysis.asset_id)
    assessment=None
    if payload.scene_intelligence_id:
        from .scene_intelligence import get_assessment
        assessment=await get_assessment(repository,project_id,payload.scene_intelligence_id)
        if (assessment.analysis_id!=analysis.analysis_id or assessment.source_asset_sha256!=asset.checksum_sha256
            or assessment.transcript_id!=(analysis.transcript.transcript_id if analysis.transcript else None)):
            raise HighlightDraftConflict('scene assessment differs from selected source/transcript')
    prepared=build_drafts(analysis,asset,payload,assessment)
    if not prepared:raise HighlightDraftConflict('no complete-speech highlight fits the requested duration')
    fingerprints=[item[0] for item in prepared]
    for attempt in range(3):
        async with repository.session_factory() as session:
            try:
                existing={row.fingerprint:row for row in (await session.scalars(select(HighlightDraftORM)
                    .where(HighlightDraftORM.project_id==project_id,HighlightDraftORM.fingerprint.in_(fingerprints)))).all()}
                for fingerprint,snapshot,evidence in prepared:
                    if fingerprint not in existing:
                        row=HighlightDraftORM(draft_id='hld_'+uuid.uuid4().hex[:24],project_id=project_id,analysis_id=analysis.analysis_id,
                            transcript_id=analysis.transcript.transcript_id if analysis.transcript else None,fingerprint=fingerprint,
                            snapshot_json=snapshot.model_dump(mode='json'),evidence_json=evidence,actor_ref=actor_ref)
                        session.add(row);existing[fingerprint]=row
                await session.commit()
                return [_read(existing[fingerprint]) for fingerprint in fingerprints]
            except IntegrityError:
                await session.rollback()
                if attempt==2:raise


async def apply_draft(repository,project_id,draft_id,payload,actor_ref):
    async with repository.session_factory() as session:
        row=await session.get(HighlightDraftORM,draft_id)
        if row is None or row.project_id!=project_id:raise KeyError(draft_id)
        draft=_read(row)
    analysis=await repository.get_analysis(draft.analysis_id)
    if analysis is None or analysis.project_id!=project_id:raise KeyError(draft.analysis_id)
    asset=await repository.get_asset(analysis.asset_id)
    if asset is None or asset.checksum_sha256!=draft.evidence['source_asset_sha256']:
        raise HighlightDraftConflict('source asset changed')
    timelines=TimelineRepository(repository.session_factory)
    active=await timelines.get_timeline(project_id)
    active_transcript=(active.snapshot.metadata.get('transcript_revision') or {}).get('transcript_id') if active else (analysis.transcript.transcript_id if analysis.transcript else None)
    if active_transcript!=draft.transcript_id:raise HighlightDraftConflict('transcript changed; create/review a new highlight draft')
    snapshot=draft.snapshot.model_copy(deep=True)
    snapshot.metadata['applied_highlight_draft_id']=draft.draft_id
    if active:
        if active.source_analysis_id!=draft.analysis_id:raise HighlightDraftConflict('active timeline uses another source analysis')
        if payload.expected_timeline_version is None:raise HighlightDraftConflict('expected timeline version required')
        if any(track.locked and track.type!='metadata' for track in active.snapshot.tracks):raise HighlightDraftConflict('unlock editable tracks first')
        return await timelines.commit_mutation(project_id=project_id,expected_version=payload.expected_timeline_version,snapshot=snapshot,
            mutation={'type':'highlight-draft-apply','draft_id':draft_id,'human_approval_required':True},actor_ref=actor_ref)
    if payload.expected_timeline_version is not None:raise HighlightDraftConflict('timeline no longer exists')
    timeline,created=await timelines.create_timeline(project_id=project_id,source_analysis_id=draft.analysis_id,
        source_media_plan_id=None,snapshot=snapshot,actor_ref=actor_ref)
    if not created and timeline.snapshot.metadata.get('applied_highlight_draft_id')!=draft_id:
        raise HighlightDraftConflict('timeline was created concurrently; review current version')
    return timeline
