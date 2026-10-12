"""Opt-in audio/caption tracks over the existing measured storyboard timeline.

Legacy projects have no new fields. Generated voice remains a derived artifact
of the verified narration PCM and canonical shot times, with no new inference.
"""
import copy,json,math
from .contracts import WorkflowError,digest,normalize
from .store import now
from .source_assets import canonical_assets
from app.timeline_models import TimelineSnapshot,TimelineTrack,TimelineClip,TransitionSpec

SCHEMA='native-narrated-media-tracks-v1'
VOICE_TRACK='trk_narrated_measured_voice'
CAPTION_TRACK='trk_narrated_measured_captions'

def legacy_music(document,duration):
    from .narrated_music import track as loop_track
    loop=loop_track(document,duration)
    if loop is not None:return TimelineTrack.model_validate(loop)
    music=document.get('music') if document.get('music_enabled',True) else None
    if not music:return None
    from .branding import resolve
    from .auto_edit_analysis import asset_reference
    brand,_=resolve(document);length=music['duration_seconds'];count=math.ceil(duration/length)
    if count>127:raise WorkflowError('PREVIEW_AUDIO_CLIP_LIMIT',400)
    clips=[]
    for i in range(count):
        start=i*length;span=min(length,duration-start)
        clips.append(TimelineClip(clip_id='clip_narrated_legacy_music_'+str(i),kind='music',label=music['filename'][:120],asset_id=asset_reference(music),
            source_end=span,timeline_start=start,duration=span,volume=brand.music_profile.nominal_gain,
            transition_out=TransitionSpec(kind='fade',duration_seconds=min(1,span)) if i==count-1 else TransitionSpec(),
            metadata={'native_asset_id':music['id'],'source_checksum_sha256':music['sha256'],'narrated_legacy_music_decision':True}))
    return TimelineTrack(track_id='trk_narrated_legacy_music',type='audio',kind='music',label='Nhạc nền hiện có',order=1,clips=clips)

def enabled(document):
    value=(document.get('canonical_timeline') or {}).get('snapshot',{}).get('metadata',{}).get('native_narrated_media_schema')
    if value is not None and value!=SCHEMA:raise WorkflowError('NARRATED_MEDIA_SCHEMA_CHANGED')
    return value==SCHEMA

def ready(document):
    from .auto_edit_timeline import is_auto_edit
    return not is_auto_edit(document) and bool(document.get('canonical_timeline') and document.get('prepared_narration'))

def reference(document):
    ref=document.get('prepared_narration')
    if ref is None and document.get('prepared_narration_origin'):
        saved=(document.get('canonical_timeline') or {}).get('snapshot',{}).get('metadata',{}).get('narrated_generated_voice_reference')
        if isinstance(saved,dict) and saved.get('prepared_reference_sha256')==document['prepared_narration_origin'].get('source_reference_sha256'):
            return copy.deepcopy(saved)
    if not isinstance(ref,dict) or not ref.get('voice_audio_sha256'):raise WorkflowError('NARRATED_MEDIA_MEASURED_NARRATION_REQUIRED',400)
    return {'schema_version':SCHEMA,'prepared_reference_sha256':digest(ref),'source_voice_sha256':ref['voice_audio_sha256'],
        'source_job_id':ref['job_id'],'asset_id':'ast_'+digest([SCHEMA,ref])[:32],'processing':'legacy_rms_peak_bound_sample_preserving_voice_placement'}

def preserve(value,document,canvas):
    """Shot edits keep explicit audio/text decisions, and refuse implicit cuts."""
    if not canvas or canvas.get('metadata',{}).get('native_narrated_media_schema')!=SCHEMA:return value
    snapshot=TimelineSnapshot.model_validate(value);prior=TimelineSnapshot.model_validate(canvas)
    metadata=copy.deepcopy(prior.metadata)
    for key in ('native_narrated_media_schema','native_project_id','narrated_generated_voice_reference','narrated_caption_source_plan','subtitle_style','subtitle_template_ref','source_audio_processing','narrated_caption_edited_tracks'):
        if key in metadata:snapshot.metadata[key]=metadata[key]
    ref=reference(document);snapshot.metadata['narrated_generated_voice_reference']=ref
    plan=snapshot.metadata.get('narrated_caption_source_plan')
    if not isinstance(plan,dict) or plan.get('sha256')!=(document.get('prepared_narration') or {}).get('plan_sha256',plan.get('sha256')):
        raise WorkflowError('NARRATED_MEDIA_PLAN_REBIND_REQUIRED')
    music_changed=prior.metadata.get('music_sha256')!=snapshot.metadata.get('music_sha256')
    # Legacy music controls still update their own track; imported tracks remain explicit.
    snapshot.tracks=[t for t in snapshot.tracks if t.track_id=='trk_native_video']
    music_handled=False
    for track in prior.tracks:
        if track.track_id=='trk_native_video':continue
        original=track
        track=track.model_copy(deep=True)
        if track.type=='text' and track.kind=='subtitles' and any(c.metadata.get('source_video_mapping') for c in track.clips):
            from .source_caption_mapping import reflow
            track=reflow(document,snapshot,track,manual=track.track_id in metadata.get('narrated_caption_edited_tracks',[]))
        if track.track_id in {'trk_native_music','trk_narrated_legacy_music'}:
            imported=any(c.metadata.get('native_media_import_id') for c in track.clips)
            if imported and music_changed:raise WorkflowError('NARRATED_MEDIA_LEGACY_MUSIC_REPLACED_REVIEW_REQUIRED',400)
            if not imported:
                replacement=legacy_music(document,snapshot.duration_seconds);music_handled=True
                if replacement is None:
                    if track.locked:raise WorkflowError('NARRATED_MEDIA_TRACK_LOCKED',400)
                    continue
                replacement.order=track.order
                replacement.locked,replacement.muted,replacement.disabled=track.locked,track.muted,track.disabled
                track=replacement
        if track.track_id==CAPTION_TRACK:
            from .shot_adapter import shots_from_snapshot
            new_shots=shots_from_snapshot(value);old_shots=shots_from_snapshot(canvas)
            default=track.track_id not in metadata.get('narrated_caption_edited_tracks',[]) and all(c.metadata.get('narrated_generated_caption') and not c.metadata.get('human_caption_edit') for c in track.clips)
            if default:
                replacement=caption_track(plan['items'],new_shots,snapshot,ref)
                replacement.locked,replacement.muted,replacement.disabled=track.locked,track.muted,track.disabled
                track=replacement
            elif [s['subtitle'] for s in new_shots]!=[s['subtitle'] for s in old_shots]:
                raise WorkflowError('NARRATED_MEDIA_SHOT_SUBTITLE_OVERRIDDEN_USE_CAPTION_EDITOR',400)
        for clip in track.clips:
            if clip.metadata.get('narrated_generated_voice') is True:
                clip.asset_id=ref['asset_id'];clip.source_start=clip.timeline_start=0
                clip.source_end=clip.duration=snapshot.duration_seconds
                clip.metadata.update(narrated_generated_voice_reference=ref)
            if clip.timeline_start+clip.duration>snapshot.duration_seconds+1e-6:
                raise WorkflowError('NARRATED_MEDIA_OVERRIDES_EXCEED_NEW_TIMELINE_REVIEW_REQUIRED',400)
        if original.locked and track.model_dump(mode='json')!=original.model_dump(mode='json'):
            raise WorkflowError('NARRATED_MEDIA_TRACK_LOCKED',400)
        snapshot.tracks.append(track)
    if music_changed and not music_handled and not any(t.track_id in {'trk_native_music','trk_narrated_legacy_music'} for t in snapshot.tracks):
        music=legacy_music(document,snapshot.duration_seconds)
        if music is not None:music.order=len(snapshot.tracks);snapshot.tracks.append(music)
    return snapshot.model_dump(mode='json')

def rebind_canvas(canvas,plan_sha256,items):
    value=copy.deepcopy(canvas)
    if value.get('metadata',{}).get('native_narrated_media_schema')==SCHEMA:
        value['metadata']['narrated_caption_source_plan']={'sha256':plan_sha256,'items':copy.deepcopy(items),'items_sha256':digest(items)}
    return value

def validate(document):
    if not enabled(document):return
    state=document['canonical_timeline'];snapshot=TimelineSnapshot.model_validate(state['snapshot']);ref=reference(document)
    if snapshot.metadata.get('narrated_generated_voice_reference')!=ref:raise WorkflowError('NARRATED_MEDIA_VOICE_REFERENCE_CHANGED')
    plan=snapshot.metadata.get('narrated_caption_source_plan')
    if (not isinstance(plan,dict) or plan.get('items_sha256')!=digest(plan.get('items')) or
        document.get('prepared_narration') and plan.get('sha256')!=document['prepared_narration'].get('plan_sha256')):
        raise WorkflowError('NARRATED_MEDIA_CAPTION_PLAN_CHANGED')
    from .source_media_track_origins import validate_timeline
    validate_timeline(document)
    if len(snapshot.tracks)>32 or sum(len(t.clips) for t in snapshot.tracks if t.type=='audio')>128 or sum(len(t.clips) for t in snapshot.tracks)>2500:
        raise WorkflowError('NARRATED_MEDIA_TIMELINE_LIMIT',400)
    edited=snapshot.metadata.get('narrated_caption_edited_tracks',[])
    if not isinstance(edited,list) or len(edited)>32 or any(not isinstance(v,str) for v in edited) or len(set(edited))!=len(edited) or any(
        not any(t.track_id==v and t.type=='text' and t.kind=='subtitles' for t in snapshot.tracks) for v in edited):
        raise WorkflowError('NARRATED_MEDIA_CAPTION_OVERRIDE_TRACK_INVALID')
    generated=[];assets={v['id']:v for v in canonical_assets(document)}
    for track in snapshot.tracks:
        if track.track_id=='trk_native_video':continue
        if track.type not in {'audio','text'} or track.kind not in {'voice','music','sfx','subtitles'}:raise WorkflowError('NARRATED_MEDIA_TRACK_INVALID')
        for clip in track.clips:
            if clip.metadata.get('narrated_generated_voice') is True:
                if (track.track_id!=VOICE_TRACK or track.kind!='voice' or clip.kind!='voice' or clip.asset_id!=ref['asset_id'] or
                    clip.source_start!=0 or clip.timeline_start!=0 or clip.duration!=snapshot.duration_seconds or clip.source_end!=snapshot.duration_seconds or
                    clip.speed!=1 or clip.metadata.get('narrated_generated_voice_reference')!=ref):raise WorkflowError('NARRATED_MEDIA_VOICE_CLIP_CHANGED')
                generated.append(clip)
            elif clip.kind=='subtitle':
                if track.type!='text' or clip.asset_id is not None:raise WorkflowError('NARRATED_MEDIA_CAPTION_INVALID')
            else:
                asset=assets.get(clip.metadata.get('native_asset_id'))
                from .auto_edit_analysis import asset_reference
                if (asset is None or asset['kind']!='audio' or clip.asset_id!=asset_reference(asset) or clip.source_end is None or
                    clip.source_end>asset['duration_seconds']+.000001 or clip.metadata.get('source_checksum_sha256',clip.metadata.get('source_sha256'))!=asset['sha256']):
                    raise WorkflowError('NARRATED_MEDIA_AUDIO_SOURCE_CHANGED')
    if len(generated)>1:raise WorkflowError('NARRATED_MEDIA_VOICE_DUPLICATED')
    from .source_media_tracks import _check_captions
    if any(c.kind=='subtitle' and not c.disabled for t in snapshot.tracks if not t.disabled for c in t.clips):_check_captions(snapshot)

def caption_track(items,shots,snapshot,ref):
    from .source_media_tracks import _caption
    track=TimelineTrack(track_id=CAPTION_TRACK,type='text',kind='subtitles',label='Caption lời đọc đã đo',order=len(snapshot.tracks));cursor=0
    for shot,item in zip(shots,items):
        lead=item['intro_seconds'];offset=cursor+lead-item['source_start_seconds']
        units=item['units'];custom=normalize(shot['subtitle'])!=normalize(shot['narration'])
        if custom and units:
            units=[{'text':shot['subtitle'],'activity_start_seconds':units[0]['activity_start_seconds'],'activity_end_seconds':units[-1]['activity_end_seconds']}]
        if not normalize(shot['subtitle']):units=[]
        for unit_index,unit in enumerate(units):
            a=offset+unit['activity_start_seconds'];b=offset+unit['activity_end_seconds']
            if b>cursor+shot['duration']+.000001:raise WorkflowError('NARRATED_MEDIA_NARRATION_OVERFLOWS_SHOT',400)
            # Phrase timing is explicitly estimated inside measured unit bounds.
            words=unit['text'].split();phrases=[];part=[]
            for word in words:
                if part and len(' '.join([*part,word]))>55:phrases.append(' '.join(part));part=[]
                part.append(word)
            if part:phrases.append(' '.join(part))
            total=sum(len(p) for p in phrases);point=a
            for phrase_index,phrase in enumerate(phrases):
                end=point+(b-a)*len(phrase)/total
                cue=_caption(phrase,point,end,unit['activity_start_seconds'],unit['activity_end_seconds'],{
                    'narrated_generated_caption':True,'source_voice_reference':copy.deepcopy(ref),'subtitle_text':phrase,
                    'generated_shot_id':shot['shot_id'],'shot_custom_subtitle':custom,
                    'timing_source':'canonical_custom_subtitle_estimate_with_measured_scene_bounds_no_word_alignment' if custom else 'measured_TTS_unit_with_estimated_phrase_bounds_no_word_alignment','source_media_mutated':False})
                cue.clip_id='clip_'+digest([ref['prepared_reference_sha256'],shot['shot_id'],unit_index,phrase_index])[:24]
                track.clips.append(cue)
                point=end
        cursor+=shot['duration']
    return track

def seed(store,con,project,snapshot):
    if enabled(project['document']):return snapshot
    from .narration import load_reference,identity
    from .shot_adapter import shots_from_snapshot
    from .source_media_tracks import _caption,_style
    from app.subtitle_templates import load_templates
    _,_,result=load_reference(store,con,project['id'],project['document'])
    if project['document']['prepared_narration'].get('voice_input_sha256')!=identity(project['document']):raise WorkflowError('PREPARED_NARRATION_INPUT_CHANGED_REPREPARE')
    plan=result['plan'];shots=shots_from_snapshot(snapshot.model_dump(mode='json'))
    if len(shots)!=len(plan['items']):raise WorkflowError('NARRATED_MEDIA_NARRATION_SCENES_CHANGED')
    ref=reference(project['document']);snapshot.metadata.update(native_narrated_media_schema=SCHEMA,native_project_id=project['id'],narrated_generated_voice_reference=ref,
        source_audio_processing={'normalize_original_audio':False,'normalize_music':False,'duck_music':True,'duck_threshold':.015})
    snapshot.tracks.append(TimelineTrack(track_id=VOICE_TRACK,type='audio',kind='voice',label='Lời đọc đã đo',order=len(snapshot.tracks),clips=[
        TimelineClip(clip_id='clip_narrated_measured_voice',kind='voice',label='PCM lời đọc đã kiểm chứng',asset_id=ref['asset_id'],timeline_start=0,source_end=snapshot.duration_seconds,
            duration=snapshot.duration_seconds,metadata={'narrated_generated_voice':True,'narrated_generated_voice_reference':ref,'new_inference_calls':0})]))
    # Persist the prior implicit music bed, including its fade/repeat decisions.
    music=legacy_music(project['document'],snapshot.duration_seconds)
    if music is not None and not any(t.kind=='music' for t in snapshot.tracks):
        music.order=len(snapshot.tracks);snapshot.tracks.append(music)
    template=next(v for v in load_templates() if not v['requires_word_timestamps']);_style(snapshot,template['template_ref'])
    snapshot.metadata['narrated_caption_source_plan']={'sha256':result['plan_sha256'],'items':copy.deepcopy(plan['items']),'items_sha256':digest(plan['items'])}
    snapshot.tracks.append(caption_track(plan['items'],shots,snapshot,ref))
    return snapshot

def cas(store,con,project,expected_version,*,seed_tracks=False):
    from .shot_adapter import validate_document
    if not ready(project['document']):raise WorkflowError('NARRATED_MEDIA_MEASURED_NARRATION_REQUIRED',400)
    state=validate_document(project['document'])
    if state['version']!=expected_version:raise WorkflowError('AUTO_EDIT_TIMELINE_VERSION_CHANGED')
    snapshot=TimelineSnapshot.model_validate(state['snapshot'])
    return state,seed(store,con,project,snapshot) if seed_tracks else snapshot

def save(store,con,project,snapshot,action,*,restored_from_version=None):
    document=copy.deepcopy(project['document']);old=document['canonical_timeline']
    document['canonical_timeline']={'version':old['version']+1,'snapshot':snapshot.model_dump(mode='json'),'sha256':digest(snapshot.model_dump(mode='json'))}
    history=document.get('narrated_timeline_mutations',[])
    if not isinstance(history,list) or len(history)>=2000:raise WorkflowError('NARRATED_TIMELINE_HISTORY_LIMIT',400)
    document['narrated_timeline_mutations']=history+[{'version':old['version']+1,'sha256':document['canonical_timeline']['sha256'],
        'mutation':{'type':'restore' if restored_from_version is not None else 'edit',
            'restored_from_version':restored_from_version,'parent_sha256':old['sha256']}}]
    from .shot_adapter import validate_document
    validate_document(document)
    con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',
        (project['revision']+1,json.dumps(document,ensure_ascii=False),now(),project['id']))
    store.version(con,project['id']);store.event(con,project['id'],action,{'revision':project['revision']+1,'timeline_version':old['version']+1,
        'timeline_sha256':document['canonical_timeline']['sha256'],'source_media_mutated':False,'provider_calls':0,'approval_invalidated':True,'preview_invalidated':True})
