"""Existing normalized transcript contract and immutable edits for uploaded speech audio."""
import copy,json,re,unicodedata,uuid
from datetime import datetime,timezone
from app.auto_edit_models import TranscriptRead,TranscriptEditRequest
from .asr import analysis_for_asset
from .auto_edit_analysis import asset_reference,normalize_transcript
from .contracts import WorkflowError,digest
from .media import project_assets,_verify_library_record
from .store import now

MAX_VERSIONS=50
def original(document,asset):
    if asset.get('kind')!='audio' or asset.get('canonical_role')!='audio':return None
    record=analysis_for_asset(document,asset)
    if not record or not record.get('normalized_transcript'):return None
    try:value=TranscriptRead.model_validate(record['normalized_transcript'])
    except ValueError:raise WorkflowError('AUDIO_TRANSCRIPT_EVIDENCE_CHANGED') from None
    expected='ana_'+digest(['native-audio-transcript-v1',asset['id'],asset['sha256'],record['transcript']['provenance']['raw_response_sha256']])[:24]
    if value.analysis_id!=expected or value.asset_id!=asset_reference(asset) or not value.is_original_evidence or value.version!=1:
        raise WorkflowError('AUDIO_TRANSCRIPT_EVIDENCE_CHANGED')
    reconstructed=normalize_transcript(record['transcript'],analysis_id=expected,asset_id=value.asset_id,
        duration=record['media']['duration_seconds'] if record.get('provider_pcm_transcript') is not None else record['audio']['duration_seconds'],created_at=value.created_at)
    if reconstructed!=value:raise WorkflowError('AUDIO_TRANSCRIPT_EVIDENCE_CHANGED')
    return value

def selected(document,asset):
    base=original(document,asset)
    if base is None:return None
    values=[base]
    for row in document.get('audio_transcript_versions',[]):
        if row.get('analysis_id')!=base.analysis_id:continue
        try:value=TranscriptRead.model_validate(row)
        except ValueError:raise WorkflowError('AUDIO_TRANSCRIPT_HISTORY_CHANGED') from None
        if (digest(row)!=(document.get('audio_transcript_version_sha256') or {}).get(value.transcript_id) or
            value.asset_id!=base.asset_id or value.is_original_evidence or value.version!=len(values)+1 or
            value.provenance.get('derived_from_transcript_id') not in {v.transcript_id for v in values}):
            raise WorkflowError('AUDIO_TRANSCRIPT_HISTORY_CHANGED')
        values.append(value)
    return values[-1]

def source_rows(document):
    for asset in project_assets(document):
        base=original(document,asset)
        if base is not None:yield asset,base,selected(document,asset)

def view(store,project_id,workspace_id):
    project=store.get(project_id);document=project['document'];items=[]
    for asset,base,current in source_rows(document):
        record=analysis_for_asset(document,asset)
        items.append({'asset_id':asset['id'],'asset_sha256':asset['sha256'],'filename':asset.get('filename',asset['id']),
            'analysis_sha256':record['analysis_sha256'],'original':base.model_dump(mode='json'),'current':current.model_dump(mode='json'),
            'versions':[base.model_dump(mode='json'),*copy.deepcopy([v for v in document.get('audio_transcript_versions',[]) if v['analysis_id']==base.analysis_id])]})
    return {'schema_version':'native-audio-transcripts-v1','workspace_id':workspace_id,'project_id':project_id,'revision':project['revision'],
        'timeline_version':(document.get('canonical_timeline') or {}).get('version'),'items':items,'publishing_enabled':False,
        'human_review_required':True,'provider_calls':0,'source_media_mutated':False}

def edit(store,project_id,revision,asset_id,body,*,asset_sha256,analysis_sha256,actor_ref):
    try:payload=TranscriptEditRequest.model_validate(body)
    except ValueError:raise WorkflowError('AUDIO_TRANSCRIPT_EDIT_INVALID',400) from None
    if type(actor_ref) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',actor_ref):raise WorkflowError('AUDIO_TRANSCRIPT_ACTOR_INVALID',400)
    with store.transaction() as con:
        project=store.editable(con,project_id,revision);document=copy.deepcopy(project['document'])
        asset=next((a for a in project_assets(document) if a['id']==asset_id),None)
        if asset is None:raise WorkflowError('AUDIO_TRANSCRIPT_NOT_FOUND',404)
        record=analysis_for_asset(document,asset);base=original(document,asset);current=selected(document,asset)
        if base is None or current is None or record is None:raise WorkflowError('AUDIO_TRANSCRIPT_NOT_FOUND',404)
        if asset['sha256']!=asset_sha256 or record['analysis_sha256']!=analysis_sha256:raise WorkflowError('AUDIO_TRANSCRIPT_SOURCE_CHANGED')
        _verify_library_record(store,{'metadata':asset,'metadata_conflict':False})
        if payload.expected_version!=current.version:raise WorkflowError('AUDIO_TRANSCRIPT_VERSION_CHANGED')
        state=document.get('canonical_timeline')
        if payload.expected_timeline_version!= (state or {}).get('version'):raise WorkflowError('AUDIO_TRANSCRIPT_TIMELINE_VERSION_CHANGED')
        versions=[base,*[TranscriptRead.model_validate(v) for v in document.get('audio_transcript_versions',[]) if v['analysis_id']==base.analysis_id]]
        chosen=next((v for v in versions if v.transcript_id==(payload.base_transcript_id or current.transcript_id)),None)
        if chosen is None:raise WorkflowError('AUDIO_TRANSCRIPT_BASE_NOT_FOUND',400)
        changes={v.segment_id:unicodedata.normalize('NFC',v.text) for v in payload.segments}
        if not set(changes)<={v.segment_id for v in chosen.segments}:raise WorkflowError('AUDIO_TRANSCRIPT_SEGMENT_NOT_FOUND',400)
        changed=[];segments=[]
        for segment in chosen.segments:
            v=segment.model_dump(mode='json');text=changes.get(segment.segment_id,segment.text)
            if text!=segment.text:changed.append(segment.segment_id);v.update(text=text,words=[],confidence=None)
            v['segment_id']='seg_'+uuid.uuid4().hex[:24]
            for word in v['words']:word['word_id']='wrd_'+uuid.uuid4().hex[:24]
            segments.append(v)
        if not changed and chosen.transcript_id==current.transcript_id:return False
        history=document.get('audio_transcript_versions',[])
        if len(history)>=MAX_VERSIONS:raise WorkflowError('AUDIO_TRANSCRIPT_HISTORY_LIMIT')
        value=TranscriptRead(transcript_id='trn_'+uuid.uuid4().hex[:24],analysis_id=base.analysis_id,asset_id=base.asset_id,
            version=current.version+1,is_original_evidence=False,provider_key=base.provider_key,language=base.language,confidence=None,segments=segments,
            provenance={**copy.deepcopy(chosen.provenance),'human_edit':True,'actor_ref':actor_ref,'derived_from_transcript_id':chosen.transcript_id,
                'changed_segment_ids':changed,'word_timestamp_policy':'discard_for_changed_text','edit_note':payload.note,
                'source_media_mutated':False,'remote_calls':0,'timeline_application_required':True},created_at=datetime.now(timezone.utc))
        document['audio_transcript_versions']=[*history,value.model_dump(mode='json')]
        document['audio_transcript_version_sha256']={**document.get('audio_transcript_version_sha256',{}),
            value.transcript_id:digest(value.model_dump(mode='json'))}
        con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',
            (revision+1,json.dumps(document,ensure_ascii=False),now(),project_id))
        store.version(con,project_id);store.event(con,project_id,'audio_transcript_version_saved',{'revision':revision+1,
            'asset_id':asset_id,'analysis_id':base.analysis_id,'transcript_id':value.transcript_id,'version':value.version,
            'actor_ref':actor_ref,'provider_calls':0,'source_media_mutated':False,'approval_invalidated':True,'timeline_mutated':False})
    return True
