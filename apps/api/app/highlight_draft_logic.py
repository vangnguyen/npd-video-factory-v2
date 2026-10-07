"""Pure complete-speech highlight planning shared by API and Native adapters."""
from __future__ import annotations
import hashlib
import json
from typing import Literal
from pydantic import Field
from .models import StrictModel
from .auto_edit_logic import build_highlights
from .timeline_logic import build_initial_timeline
from .speech_windows import protected_window

class HighlightDraftConflict(ValueError):pass

class HighlightDraftRequest(StrictModel):
    analysis_id: str = Field(pattern=r'^ana_[A-Za-z0-9_-]{4,60}$')
    transcript_id: str | None = Field(default=None, pattern=r'^trn_[A-Za-z0-9_-]{4,60}$')
    scene_intelligence_id: str | None = Field(default=None,pattern=r'^sci_[A-Za-z0-9_-]{4,60}$')
    count: Literal[3,5] = 3
    mode: Literal['top_highlights','auto_shorts'] = 'top_highlights'
    maximum_duration_seconds: float = Field(default=60,ge=3,le=180)

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
