"""Explicit source-shot edits keep original audio and saved captions synchronized.

Existing independent advanced-track edits remain available. A divergent audio
track is refused instead of silently overwriting its independent edit decisions.
"""
import copy
import uuid

from pydantic import Field
from .auto_edit_timeline import _cas,_save,view,protected_window
from app.models import StrictModel
from app.auto_edit_models import TranscriptRead
from app.timeline_models import TimelineOperation,TimelineSnapshot
from app.timeline_logic import apply_operations,TimelineEditError
from .contracts import WorkflowError


class LinkedEdit(StrictModel):
    expected_version:int=Field(ge=1,strict=True)
    operation:TimelineOperation


def transcript_for(document,snapshot):
    binding=snapshot.metadata.get('transcript_revision')
    if not binding:return None
    candidates=list(document.get('auto_edit_transcripts',[]))
    candidates += [item['analysis']['transcript'] for item in document.get('auto_edit_analyses',[])
        if item['analysis'].get('transcript')]
    found=next((item for item in candidates if item['transcript_id']==binding['transcript_id']),None)
    if found is None:raise WorkflowError('AUTO_EDIT_TRANSCRIPT_BASE_NOT_FOUND')
    return TranscriptRead.model_validate(found)


def _key(clip):
    return (clip.asset_id,round(clip.source_start,6),round(clip.source_end,6),
        round(clip.timeline_start,6),round(clip.speed,6),clip.disabled)


def _captions(sources,transcript):
    if transcript is None:return []
    windows=[]
    for clip in sorted((item for item in sources if not item.disabled),key=lambda item:item.timeline_start):
        if (windows and abs(windows[-1].source_end-clip.source_start)<1e-6
                and abs(windows[-1].timeline_start+windows[-1].duration-clip.timeline_start)<1e-6
                and windows[-1].speed==clip.speed):
            windows[-1]=windows[-1].model_copy(update={'source_end':clip.source_end,'duration':windows[-1].duration+clip.duration})
        else:windows.append(clip.model_copy(deep=True))
    result=[]
    from app.timeline_models import TimelineClip
    for window in windows:
        for segment in transcript.segments:
            start=max(window.source_start,segment.start_seconds);end=min(window.source_end,segment.end_seconds)
            if end-start<.05:continue
            words=[word for word in segment.words if start<=word.start_seconds<word.end_seconds<=end]
            partial=start>segment.start_seconds or end<segment.end_seconds
            text=' '.join(word.text for word in words) if partial and segment.words else segment.text
            if not text.strip():continue
            result.append(TimelineClip(clip_id='clip_'+uuid.uuid4().hex[:24],kind='subtitle',label=text[:120],
                source_start=start,source_end=end,timeline_start=window.timeline_start+(start-window.source_start)/window.speed,
                duration=(end-start)/window.speed,speed=window.speed,metadata={
                    'transcript_id':transcript.transcript_id,'segment_id':segment.segment_id,'language':transcript.language,
                    'confidence':segment.confidence,'native_linked_caption':True,
                    'timing_source':'provider_native_word_intervals' if words else 'segment_bounds_without_word_alignment',
                    'measured_source_words':[{'text':word.text,'start_seconds':word.start_seconds,'end_seconds':word.end_seconds} for word in words],
                    **({'subtitle_text':text} if not segment.words else {})}))
    return result


def apply(snapshot,operation,document):
    tracks=[track for track in snapshot.tracks if track.type=='video' and track.kind=='source']
    if len(tracks)!=1:raise WorkflowError('AUTO_EDIT_LINKED_SOURCE_TRACK_REQUIRED')
    main=tracks[0]
    selected=next((clip for clip in main.clips if clip.clip_id==operation.clip_id),None)
    if selected is None:raise WorkflowError('AUTO_EDIT_LINKED_SOURCE_CLIP_NOT_FOUND',404)
    if operation.type not in {'trim','split','move','delete','duplicate','disable','reorder','set_clip_properties'}:
        raise WorkflowError('AUTO_EDIT_LINKED_OPERATION_INVALID',400)
    if operation.target_track_id or operation.track_id or operation.duration is not None or operation.volume is not None:
        raise WorkflowError('AUTO_EDIT_LINKED_OPERATION_INVALID',400)
    visual_only=operation.type=='set_clip_properties' and operation.speed is None
    if visual_only:
        return apply_operations(snapshot,[operation])
    audio=next((track for track in snapshot.tracks if track.kind=='original_audio'),None)
    if audio and not audio.clips:
        assets={item['id']:item for item in document.get('assets',[])}
        if any(assets.get(clip.metadata.get('native_asset_id'),{}).get('has_audio') for clip in main.clips):
            raise WorkflowError('AUTO_EDIT_LINKED_AUDIO_DIVERGED',400)
        audio=None
    captions=next((track for track in snapshot.tracks if track.kind=='subtitles'),None)
    if any(track and track.locked for track in (main,audio,captions)):
        raise WorkflowError('AUTO_EDIT_LINKED_TRACK_LOCKED',400)
    transcript=transcript_for(document,snapshot)
    if operation.type=='trim':
        start=operation.source_start if operation.source_start is not None else selected.source_start
        end=operation.source_end if operation.source_end is not None else selected.source_end
        if not 0<=start<end<=snapshot.metadata['source_duration_seconds']:
            raise WorkflowError('AUTO_EDIT_TIMELINE_SOURCE_WINDOW_INVALID',400)
        start,end=protected_window((start,end),transcript,snapshot.metadata['source_duration_seconds'])
        operation=operation.model_copy(update={'source_start':start,'source_end':end})
    if operation.type=='split' and transcript:
        point=selected.source_start+(operation.at_seconds-selected.timeline_start)*selected.speed
        for segment in transcript.segments:
            intervals=[(word.start_seconds,word.end_seconds) for word in segment.words] or [(segment.start_seconds,segment.end_seconds)]
            if any(start<point<end for start,end in intervals):
                raise WorkflowError('AUTO_EDIT_SPLIT_TOUCHES_SPOKEN_WORD',400)
    if operation.type=='delete' and len(main.clips)<=1:
        raise WorkflowError('AUTO_EDIT_LAST_SOURCE_CLIP_REQUIRED',400)
    # Match old A/V windows before changing anything. Preserve per-clip gain,
    # fades and disabled state; never reset independent source-audio edits.
    sound={}
    if audio:
        for clip in main.clips:
            found=[item for item in audio.clips if _key(item)==_key(clip)]
            if len(found)!=1:raise WorkflowError('AUTO_EDIT_LINKED_AUDIO_DIVERGED',400)
            sound[clip.clip_id]=found[0]
        if len(sound)!=len(audio.clips):raise WorkflowError('AUTO_EDIT_LINKED_AUDIO_DIVERGED',400)
    prepared=snapshot.model_copy(deep=True)
    prepared_main=next(track for track in prepared.tracks if track.track_id==main.track_id)
    for clip in prepared_main.clips:clip.metadata['native_link_origin']=clip.clip_id
    changed=apply_operations(prepared,[operation])
    changed_main=next(track for track in changed.tracks if track.track_id==main.track_id)
    if operation.type=='move':
        # Source-shot movement is a ripple reorder. Independent overlay/music
        # tracks still use exact placement through the ordinary edit route.
        # Never introduce accidental empty/overlapping source windows merely
        # because the requested position lies inside another source shot.
        changed_main.clips.sort(key=lambda clip:clip.timeline_start)
    cursor=0.
    for clip in changed_main.clips:
        clip.timeline_start=round(cursor,6)
        if not clip.disabled:cursor+=clip.duration
    if audio:
        output=next(track for track in changed.tracks if track.track_id==audio.track_id);output.clips=[]
        for clip in changed_main.clips:
            original=sound[clip.metadata['native_link_origin']]
            # Stable IDs for unchanged/edited windows; split/duplicate get new IDs.
            identifier=original.clip_id if clip.clip_id==clip.metadata['native_link_origin'] else 'clip_'+uuid.uuid4().hex[:24]
            output.clips.append(original.model_copy(deep=True,update={'clip_id':identifier,
                'source_start':clip.source_start,'source_end':clip.source_end,'timeline_start':clip.timeline_start,
                'duration':clip.duration,'speed':clip.speed,'disabled':clip.disabled,
                'metadata':{**copy.deepcopy(original.metadata),'native_linked_source_clip_id':clip.clip_id}}))
    if captions:
        output=next(track for track in changed.tracks if track.track_id==captions.track_id)
        output.clips=_captions(changed_main.clips,transcript)
    for clip in changed_main.clips:clip.metadata.pop('native_link_origin',None)
    changed.duration_seconds=max(.1,round(max((clip.timeline_start+clip.duration for track in changed.tracks
        if not track.disabled for clip in track.clips if not clip.disabled),default=.1),6))
    changed.metadata['linked_source_edit']={'operation':operation.model_dump(mode='json'),
        'captions_retimed_from_saved_transcript':transcript is not None,'source_audio_synchronized':audio is not None,
        **({'source_move_behavior':'ripple_reorder'} if operation.type=='move' else {}),
        'other_tracks_preserved':True,'broll_placement_review_required':True,'provider_calls':0}
    return TimelineSnapshot.model_validate(changed.model_dump(mode='json'))


def edit(store,project_id,revision,body):
    try:payload=LinkedEdit.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_EDIT_TIMELINE_REQUEST_INVALID',400) from None
    with store.transaction() as con:
        project=store.editable(con,project_id,revision);state=_cas(project,payload.expected_version)
        try:snapshot=apply(TimelineSnapshot.model_validate(state['snapshot']),payload.operation,project['document'])
        except (ValueError,TimelineEditError):raise WorkflowError('AUTO_EDIT_TIMELINE_OPERATION_INVALID',400) from None
        _save(store,con,project,snapshot,'auto_edit_linked_source_shot_edited')
    return view(store,project_id)
