"""Scoped Native manual word decisions in existing transcript/canonical histories."""
import copy,json,re
from app.transcript_word_review import WordReview,revised
from .contracts import WorkflowError,digest
from .media import project_assets,_verify_library_record
from .asr import analysis_for_asset

def gaps(document,asset):
    record=analysis_for_asset(document,asset) or {}
    audio=record.get('audio') or {};clock=audio.get('decoded_source_clock') or {}
    missing=[]
    if clock.get('contiguous') is False:
        from .asr_audio_clock import validate_padding
        plan=validate_padding(audio);origin=plan['source_origin_sample']
        missing=[((v['pcm_start_sample']+origin)/16000,(v['pcm_end_sample']+origin)/16000) for v in plan['gaps']]
    start=clock.get('source_start_seconds',0);end=clock.get('source_end_seconds',asset['duration_seconds'])
    if start>0:missing.append((0,start))
    if end<asset['duration_seconds']:missing.append((end,asset['duration_seconds']))
    return missing

def save(store,project_id,revision,identity,body,*,actor_ref,asset_sha256,analysis_sha256,audio=False,workspace_id=None):
    try:payload=WordReview.model_validate(body)
    except ValueError:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_INVALID',400) from None
    if not isinstance(actor_ref,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',actor_ref):
        raise WorkflowError('TRANSCRIPT_WORD_REVIEW_ACTOR_INVALID',400)
    with store.transaction() as con:
        project=store.editable(con,project_id,revision);document=copy.deepcopy(project['document'])
        if audio:
            from .audio_transcripts import original,selected,MAX_VERSIONS
            asset=next((a for a in project_assets(document) if a['id']==identity),None)
            if asset is None:raise WorkflowError('AUDIO_TRANSCRIPT_NOT_FOUND',404)
            record=analysis_for_asset(document,asset);base=original(document,asset);current=selected(document,asset)
            expected_sha=record.get('analysis_sha256') if record else None;limit=MAX_VERSIONS
            history_key='audio_transcript_versions'
        else:
            from .auto_edit_analysis import validate_record,selected_transcript,MAX_TRANSCRIPT_VERSIONS
            record=next((r for r in document.get('auto_edit_analyses',[]) if r['analysis']['analysis_id']==identity),None)
            asset=next((a for a in project_assets(document) if record and a['id']==record['native_asset_id']),None)
            if record is None or asset is None:raise WorkflowError('AUTO_EDIT_ANALYSIS_NOT_FOUND',404)
            analysis=validate_record(record,project_id,document,asset);base=analysis.transcript
            current=selected_transcript(document,analysis);expected_sha=record['sha256'];limit=MAX_TRANSCRIPT_VERSIONS
            history_key='auto_edit_transcripts'
        if base is None or current is None:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_NOT_AVAILABLE',404)
        if asset['sha256']!=asset_sha256 or expected_sha!=analysis_sha256:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_SOURCE_CHANGED')
        _verify_library_record(store,{'metadata':asset,'metadata_conflict':False})
        state=document.get('canonical_timeline');version=(state or {}).get('version')
        if payload.expected_timeline_version!=version:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_TIMELINE_CHANGED')
        history=document.get(history_key,[])
        if len(history)>=limit:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_HISTORY_LIMIT')
        try:value=revised(current,payload,duration=float(asset['duration_seconds']),actor_ref=actor_ref,gaps=gaps(document,asset))
        except (ValueError,KeyError,TypeError) as exc:
            code=str(exc) if str(exc).startswith('TRANSCRIPT_WORD_REVIEW_') else 'TRANSCRIPT_WORD_REVIEW_INVALID'
            raise WorkflowError(code,409) from None
        mutated=False
        if state is not None and not audio:
            from .auto_edit_timeline import is_auto_edit
            if not is_auto_edit(document):raise WorkflowError('TRANSCRIPT_WORD_REVIEW_TIMELINE_APPLICATION_UNSUPPORTED')
            from .transcript_word_timeline import protect_and_sync
            protect_and_sync(document,current,value);mutated=True
        document[history_key]=history+[value.model_dump(mode='json')]
        if audio:document['audio_transcript_version_sha256']={**document.get('audio_transcript_version_sha256',{}),
            value.transcript_id:digest(value.model_dump(mode='json'))}
        else:document['auto_edit_transcript_version_sha256']={**document.get('auto_edit_transcript_version_sha256',{}),
            value.transcript_id:digest(value.model_dump(mode='json'))}
        from .auto_edit_analysis import _save
        _save(store,con,project,document,'transcript_words_reviewed',{'analysis_id':base.analysis_id,
            'transcript_id':value.transcript_id,'version':value.version,'actor_ref':actor_ref},timeline_mutated=mutated)
    if audio:
        from .audio_transcripts import view
        return view(store,project_id,workspace_id)
    from .auto_edit_analysis import view
    return view(store,project_id)
