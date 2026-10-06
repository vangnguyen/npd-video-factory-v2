"""Immutable transcript revisions coupled atomically to canonical subtitle edits."""
from __future__ import annotations
import copy
import uuid
from sqlalchemy import select
from .auto_edit_db import AutoEditAnalysisORM,TranscriptORM,TranscriptSegmentORM,TranscriptWordORM
from .auto_edit_models import TranscriptEditRequest
from .timeline_db import TimelineORM,TimelineVersionORM
from .timeline_models import TimelineSnapshot
from .timeline_repository import TimelineRepository


class TranscriptEditConflict(ValueError):pass


def _id(prefix):return prefix+'_'+uuid.uuid4().hex[:24]


async def edit_transcript(repository,project_id:str,analysis_id:str,payload:TranscriptEditRequest,actor_ref:str):
    """No ASR/paid calls; changed text loses its old word-alignment claims."""
    try:
        async with repository.session_factory() as session:
            async with session.begin():
                analysis=await session.scalar(select(AutoEditAnalysisORM).where(
                    AutoEditAnalysisORM.analysis_id==analysis_id,AutoEditAnalysisORM.project_id==project_id).with_for_update())
                if analysis is None:raise KeyError(analysis_id)
                if analysis.status!='succeeded':raise TranscriptEditConflict('analysis is not ready')
                current=await session.scalar(select(TranscriptORM).where(TranscriptORM.analysis_id==analysis_id).order_by(TranscriptORM.version.desc()))
                if current is None:raise TranscriptEditConflict('no transcript exists')
                if current.version!=payload.expected_version:raise TranscriptEditConflict('transcript version changed; reload before editing')
                base=await session.get(TranscriptORM,payload.base_transcript_id) if payload.base_transcript_id else current
                if base is None or base.analysis_id!=analysis_id:raise TranscriptEditConflict('base transcript belongs to another analysis')
                segments=(await session.scalars(select(TranscriptSegmentORM).where(TranscriptSegmentORM.transcript_id==base.transcript_id).order_by(TranscriptSegmentORM.ordinal))).all()
                words=(await session.scalars(select(TranscriptWordORM).where(TranscriptWordORM.transcript_id==base.transcript_id).order_by(TranscriptWordORM.ordinal))).all()
                edits={s.segment_id:s.text for s in payload.segments}
                if not set(edits)<={s.segment_id for s in segments}:raise TranscriptEditConflict('segment is not in this transcript version')
                changed={s.segment_id for s in segments if s.segment_id in edits and edits[s.segment_id]!=s.text}
                if not changed:return await repository.get_analysis(analysis_id,transcript_id=base.transcript_id)
                timeline=await session.scalar(select(TimelineORM).where(TimelineORM.project_id==project_id).with_for_update())
                if timeline is not None and timeline.source_analysis_id!=analysis_id:
                    raise TranscriptEditConflict('active timeline uses another source; edit its transcript instead')
                if timeline is not None and payload.expected_timeline_version!=timeline.current_version:
                    raise TranscriptEditConflict('timeline version changed or was omitted; reload before editing')
                if timeline is None and payload.expected_timeline_version is not None:
                    raise TranscriptEditConflict('timeline does not exist')
                snapshot=None
                if timeline is not None:
                    version=await session.get(TimelineVersionORM,timeline.current_version_id)
                    snapshot=copy.deepcopy(version.snapshot_json)
                    active=(snapshot['metadata'].get('transcript_revision') or {}).get('transcript_id')
                    inferred={c.get('metadata',{}).get('transcript_id') for t in snapshot['tracks'] for c in t['clips'] if c.get('metadata',{}).get('transcript_id')}
                    if (active and active!=base.transcript_id) or (not active and inferred and base.transcript_id not in inferred):
                        raise TranscriptEditConflict('base transcript is not the version selected by the canonical timeline')
                transcript_id=_id('trn');segment_ids={s.segment_id:_id('seg') for s in segments}
                provenance={**copy.deepcopy(base.provenance_json),'human_edit':True,'actor_ref':actor_ref,'edit_note':payload.note,
                    'derived_from_transcript_id':base.transcript_id,'derived_from_version':base.version,
                    'changed_segment_ids':sorted(changed),'word_timestamp_policy':'discard_for_changed_text',
                    'source_media_mutated':False,'remote_calls':0}
                session.add(TranscriptORM(transcript_id=transcript_id,analysis_id=analysis_id,asset_id=current.asset_id,
                    version=current.version+1,is_original_evidence=False,provider_key=base.provider_key,language=base.language,
                    confidence=None,provenance_json=provenance))
                for s in segments:
                    session.add(TranscriptSegmentORM(segment_id=segment_ids[s.segment_id],transcript_id=transcript_id,ordinal=s.ordinal,
                        start_seconds=s.start_seconds,end_seconds=s.end_seconds,text=edits.get(s.segment_id,s.text),speaker=s.speaker,
                        confidence=None if s.segment_id in changed else s.confidence))
                for w in words:
                    if w.segment_id in changed:continue
                    session.add(TranscriptWordORM(word_id=_id('wrd'),transcript_id=transcript_id,segment_id=segment_ids[w.segment_id],
                        ordinal=w.ordinal,start_seconds=w.start_seconds,end_seconds=w.end_seconds,text=w.text,confidence=w.confidence))
                if timeline is not None:
                    updated_clip_ids=[]
                    for track in snapshot['tracks']:
                        for clip in track['clips']:
                            meta=clip.get('metadata',{});segment=meta.get('segment_id')
                            if meta.get('transcript_id')!=base.transcript_id or segment not in segment_ids:continue
                            if segment in changed:
                                if track.get('locked'):raise TranscriptEditConflict('subtitle track is locked; unlock before editing')
                                clip['label']=edits[segment][:120]
                                meta['subtitle_text']=edits[segment]
                                meta['measured_source_words']=[]
                                meta['timing_source']='human_edited_segment_bounds_no_word_alignment'
                                meta['confidence']=None
                                updated_clip_ids.append(clip['clip_id'])
                            meta['transcript_id']=transcript_id;meta['segment_id']=segment_ids[segment]
                    snapshot['metadata']['transcript_revision']={'transcript_id':transcript_id,'version':current.version+1,
                        'human_edited':True,'review_required':True,'scene_highlight_semantics_stale':True}
                    await TimelineRepository(repository.session_factory).commit_mutation_in_session(session=session,
                        project_id=project_id,expected_version=timeline.current_version,snapshot=TimelineSnapshot.model_validate(snapshot),
                        mutation={'type':'transcript-text-edit','from_transcript_id':base.transcript_id,'transcript_id':transcript_id,
                                  'updated_clip_ids':updated_clip_ids},actor_ref=actor_ref)
                analysis.provenance_json={**analysis.provenance_json,'human_transcript_revision':current.version+1,
                    'semantic_analysis_refresh_required':True}
        return await repository.get_analysis(analysis_id)
    except Exception as exc:
        from sqlalchemy.exc import IntegrityError,OperationalError
        if isinstance(exc,IntegrityError):raise TranscriptEditConflict('concurrent transcript version changed; reload') from exc
        if isinstance(exc,OperationalError) and 'locked' in str(exc).lower():raise TranscriptEditConflict('concurrent transcript write; reload') from exc
        raise
