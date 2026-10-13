"""Explicit human word/timing revisions; no provider evidence rewrite or inference."""
import copy,math,unicodedata,uuid
from datetime import datetime,timezone
from pydantic import Field,model_validator
from .models import StrictModel
from .auto_edit_models import TranscriptRead

def timing_evidence(transcript):
    """Label a mixed manual/provider transcript without claiming measurement."""
    if transcript.provenance.get('word_timestamp_policy')!='human_supplied_source_intervals':return {}
    return {'timing_source':'human_supplied_or_retained_transcript_word_intervals',
        'timing_independently_measured':False,'human_word_timing_review':True}

class Word(StrictModel):
    word_id:str|None=Field(default=None,pattern=r'^wrd_[a-f0-9]{24}$')
    text:str=Field(min_length=1,max_length=240)
    start_seconds:float=Field(ge=0,allow_inf_nan=False,strict=True)
    end_seconds:float=Field(gt=0,allow_inf_nan=False,strict=True)
    @model_validator(mode='after')
    def window(self):
        if not self.text.strip() or self.end_seconds<=self.start_seconds:raise ValueError('invalid word')
        return self

class Segment(StrictModel):
    segment_id:str=Field(pattern=r'^seg_[a-f0-9]{24}$')
    start_seconds:float=Field(ge=0,allow_inf_nan=False,strict=True)
    end_seconds:float=Field(gt=0,allow_inf_nan=False,strict=True)
    words:list[Word]=Field(min_length=1,max_length=2000)
    @model_validator(mode='after')
    def window(self):
        if self.end_seconds<=self.start_seconds:raise ValueError('invalid segment')
        previous=self.start_seconds;ids=[]
        for word in self.words:
            if word.start_seconds<previous or word.end_seconds>self.end_seconds:raise ValueError('word order/bounds invalid')
            previous=word.end_seconds
            if word.word_id:ids.append(word.word_id)
        if len(ids)!=len(set(ids)):raise ValueError('duplicate word identity')
        return self

class WordReview(StrictModel):
    expected_version:int=Field(ge=1,strict=True)
    expected_transcript_id:str=Field(pattern=r'^trn_[a-f0-9]{24}$')
    expected_timeline_version:int|None=Field(default=None,ge=1,strict=True)
    acknowledged:bool=Field(strict=True)
    segments:list[Segment]=Field(min_length=1,max_length=1000)
    note:str=Field(default='',max_length=2000)
    @model_validator(mode='after')
    def unique(self):
        if not self.acknowledged:raise ValueError('explicit review acknowledgement required')
        ids=[s.segment_id for s in self.segments]
        if len(ids)!=len(set(ids)) or sum(len(s.words) for s in self.segments)>10000:
            raise ValueError('duplicate segments or word limit')
        return self

def revised(base:TranscriptRead,payload:WordReview,*,duration,actor_ref,gaps=()):
    if payload.expected_version!=base.version or payload.expected_transcript_id!=base.transcript_id:
        raise ValueError('TRANSCRIPT_WORD_REVIEW_VERSION_CHANGED')
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0:
        raise ValueError('TRANSCRIPT_WORD_REVIEW_SOURCE_DURATION_INVALID')
    changes={s.segment_id:s for s in payload.segments}
    if not set(changes)<={s.segment_id for s in base.segments}:raise ValueError('TRANSCRIPT_WORD_REVIEW_SEGMENT_FOREIGN')
    output=[];mapping={};ordinal=0;previous=0.
    for old in base.segments:
        change=changes.get(old.segment_id);item=old.model_dump(mode='json')
        if change:
            old_ids={w.word_id for w in old.words}
            if any(w.word_id and w.word_id not in old_ids for w in change.words):raise ValueError('TRANSCRIPT_WORD_REVIEW_WORD_FOREIGN')
            item.update(start_seconds=change.start_seconds,end_seconds=change.end_seconds,
                text=' '.join(unicodedata.normalize('NFC',w.text.strip()) for w in change.words),confidence=None,
                words=[{'word_id':'wrd_'+uuid.uuid4().hex[:24],'ordinal':0,'text':unicodedata.normalize('NFC',w.text.strip()),
                    'start_seconds':w.start_seconds,'end_seconds':w.end_seconds,'confidence':None} for w in change.words])
            for word in item['words']:
                if any(min(word['end_seconds'],end)>max(word['start_seconds'],start) for start,end in gaps):
                    raise ValueError('TRANSCRIPT_WORD_REVIEW_SOURCE_AUDIO_GAP')
        if item['start_seconds']<previous or item['end_seconds']>duration:
            raise ValueError('TRANSCRIPT_WORD_REVIEW_SEGMENT_ORDER_OR_SOURCE_BOUNDS')
        previous=item['end_seconds'];item['segment_id']='seg_'+uuid.uuid4().hex[:24]
        mapping[old.segment_id]=item['segment_id']
        for word in item['words']:
            if not change:word['word_id']='wrd_'+uuid.uuid4().hex[:24]
            word['ordinal']=ordinal;ordinal+=1
        output.append(item)
    if ordinal>10000:raise ValueError('TRANSCRIPT_WORD_REVIEW_LIMIT')
    return TranscriptRead(transcript_id='trn_'+uuid.uuid4().hex[:24],analysis_id=base.analysis_id,asset_id=base.asset_id,
        version=base.version+1,is_original_evidence=False,provider_key=base.provider_key,language=base.language,
        confidence=None,segments=output,created_at=datetime.now(timezone.utc),provenance={**copy.deepcopy(base.provenance),
            'human_edit':True,'actor_ref':actor_ref,'derived_from_transcript_id':base.transcript_id,
            'changed_segment_ids':list(changes),'reviewed_segment_ids':list(changes),'segment_id_mapping':mapping,
            'word_timestamp_policy':'human_supplied_source_intervals','word_alignment_source':'human_supplied',
            'timing_rewrite_applied':True,'human_timing_acknowledged':True,'timing_independently_measured':False,
            'review_required':True,'edit_note':payload.note,'source_media_mutated':False,'remote_calls':0})
