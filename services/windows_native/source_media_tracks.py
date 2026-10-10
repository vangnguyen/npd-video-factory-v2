"""Uploaded voice/music and captions mutate the existing canonical Source timeline."""
import asyncio,copy,hashlib,json,math,re,unicodedata,uuid
from .contracts import WorkflowError,digest
from .store import now
from .media import _verify_library_record
from .source_assets import canonical_assets
from .auto_edit_timeline import is_auto_edit
from .auto_edit_analysis import asset_reference
from .source_media_track_models import Audio,Subtitles,EditCaptions
from .source_media_track_origins import SCHEMA,LIMIT,binding,records,verify_physical
from app.timeline_models import TimelineSnapshot,TimelineTrack,TimelineClip,TransitionSpec
from app.production_models import SubtitleStyle
from app.production_logic import derive_subtitle_cues,validate_subtitles,subtitle_character_capacity,ProductionContractError
from app.subtitle_templates import load_templates,template_catalog

PAGE_SIZE=50

def _cas(project,expected_version,*,store=None,con=None,seed_tracks=False):
    if is_auto_edit(project['document']):
        from .auto_edit_timeline import _cas as source_cas
        state=source_cas(project,expected_version)
        return state,TimelineSnapshot.model_validate(state['snapshot'])
    from .narrated_media_timeline import cas
    return cas(store,con,project,expected_version,seed_tracks=seed_tracks)

def _save(store,con,project,snapshot,action):
    if is_auto_edit(project['document']):
        from .auto_edit_timeline import _save as source_save
        return source_save(store,con,project,snapshot,action)
    from .narrated_media_timeline import save
    return save(store,con,project,snapshot,action)

def catalog(store,project_id,workspace_id,*,caption_page=1):
    if type(caption_page) is not int or not 1<=caption_page<=1000:raise WorkflowError('SOURCE_MEDIA_TRACK_PAGE_INVALID',400)
    project=store.get(project_id);document=project['document']
    from .narrated_media_timeline import ready as narrated_ready
    source_mode=is_auto_edit(document);ready=source_mode or narrated_ready(document)
    pending=False
    if ready and not source_mode:
        from .narrated_media_timeline import enabled
        pending=not enabled(document)
        with store.transaction() as con:
            state,projection=_cas(project,document['canonical_timeline']['version'],store=store,con=con,seed_tracks=pending)
        snapshot=projection.model_dump(mode='json')
    else:
        state=_cas(project,document['canonical_timeline']['version'])[0] if ready else None
        snapshot=state['snapshot'] if state else None
    assets=[]
    for asset in canonical_assets(document):
        if asset['kind'] not in {'audio','subtitle'}:continue
        current=None;analysis_sha=None
        if asset.get('canonical_role')=='audio':
            from .audio_transcripts import selected
            from .asr import analysis_for_asset
            current=selected(document,asset);analysis_sha=(analysis_for_asset(document,asset) or {}).get('analysis_sha256') if current else None
        assets.append({'asset_id':asset['id'],'asset_sha256':asset['sha256'],'kind':asset['kind'],
            'role':asset.get('canonical_role'),'filename':asset.get('filename',asset['id']),'duration_seconds':asset.get('duration_seconds'),
            'rights_status':asset.get('rights_status','unknown'),'license':asset.get('license'),
            'cue_count':len(asset.get('cues',[])) if asset['kind']=='subtitle' else None,
            'transcript_id':current.transcript_id if current else None,'transcript_version':current.version if current else None,
            'analysis_sha256':analysis_sha,'word_timing_available':bool(current and any(s.words for s in current.segments))})
    tracks=[{k:copy.deepcopy(t[k]) for k in ('track_id','type','kind','label','locked','muted','disabled')} for t in (snapshot or {}).get('tracks',[])]
    from .source_caption_mapping import video_assets,human_layout
    source_videos=video_assets(document,TimelineSnapshot.model_validate(snapshot)) if snapshot else []
    video_choices=[{'asset_id':v['id'],'asset_sha256':v['sha256'],'filename':v['filename'],'duration_seconds':v['duration_seconds']} for v in source_videos]
    captions=[{'track_id':t['track_id'],'track_locked':t['locked'],'track_disabled':t['disabled'],
        'clip_id':c['clip_id'],'text':c['metadata'].get('subtitle_text',c['label']),
        'timeline_start':c['timeline_start'],'duration':c['duration'],'disabled':c['disabled'],
        'import_id':c['metadata'].get('native_media_import_id'),'native_asset_id':c['metadata'].get('native_asset_id'),
        'source_video_asset_id':c['metadata'].get('source_video_mapping',{}).get('video_reference',{}).get('asset_id'),
        'source_video_mapping_mode':('disabled' if t['disabled'] or c['disabled'] else 'human_layout' if human_layout(snapshot,t) else 'follow_video') if c['metadata'].get('source_video_mapping') else None,
        'has_word_timing':bool(c['metadata'].get('measured_source_words'))} for t in (snapshot or {}).get('tracks',[])
        if t['type']=='text' and t['kind']=='subtitles' for c in t['clips'] if c['kind']=='subtitle']
    captions.sort(key=lambda c:(c['timeline_start'],c['clip_id']));start=(caption_page-1)*PAGE_SIZE
    history=list(records(document).values())
    return {'schema_version':'native-source-media-tracks-v1','workspace_id':workspace_id,'project_id':project_id,'revision':project['revision'],
        'timeline_available':ready,'timeline_mode':'source' if source_mode else 'narrated' if ready else None,'pending_generated_tracks':pending,
        'timeline_version':state['version'] if state else None,'timeline_sha256':state['sha256'] if state else None,
        'duration_seconds':snapshot['duration_seconds'] if snapshot else None,'assets':assets[:200],'assets_total':len(assets),'assets_truncated':len(assets)>200,
        'tracks':tracks,'captions':captions[start:start+PAGE_SIZE],'caption_page':caption_page,'caption_page_size':PAGE_SIZE,
        'source_video_assets':video_choices[:200],'source_video_assets_total':len(video_choices),'source_video_assets_truncated':len(video_choices)>200,
        'source_video_mapping_available':bool(video_choices),
        'captions_total':len(captions),'captions_has_next':start+PAGE_SIZE<len(captions),
        'imports':[{'import_id':v['import_id'],'operation':v['operation'],'asset_id':v['asset_id'],'asset_sha256':v['asset_sha256'],
            'result':copy.deepcopy(v['result']),'created_at':v['created_at'],'inherited':bool(v.get('inherited_original'))} for v in history[-50:]],
        'imports_total':len(history),'imports_truncated':len(history)>50,'subtitle_templates':template_catalog(),
        'selected_subtitle_template_ref':(snapshot or {}).get('metadata',{}).get('subtitle_template_ref'),
        'provider_calls':0,'publishing_enabled':False,'human_review_required':True,'source_media_mutated':False}

def _parse(model,body):
    try:return model.model_validate(body)
    except ValueError:raise WorkflowError('SOURCE_MEDIA_TRACK_REQUEST_INVALID',400) from None

def _track(snapshot,identifier,role,*,replace=False):
    if identifier:
        track=next((t for t in snapshot.tracks if t.track_id==identifier),None)
        if track is None or track.kind!=role or track.type!=('text' if role=='subtitles' else 'audio'):
            raise WorkflowError('SOURCE_MEDIA_TRACK_NOT_FOUND',400)
        if track.locked:raise WorkflowError('SOURCE_MEDIA_TRACK_LOCKED',400)
        if track.disabled:raise WorkflowError('SOURCE_MEDIA_TRACK_DISABLED',400)
        if replace:track.clips=[]
        return track
    if len(snapshot.tracks)>=32:raise WorkflowError('AUTO_EDIT_TIMELINE_LIMIT',400)
    track=TimelineTrack(track_id='trk_'+uuid.uuid4().hex[:24],type='text' if role=='subtitles' else 'audio',kind=role,
        label={'voice':'Giọng nói tải lên','music':'Nhạc tải lên','subtitles':'Phụ đề tải lên'}[role],order=len(snapshot.tracks))
    snapshot.tracks.append(track);return track

def _asset(store,document,payload,kind):
    asset=next((v for v in canonical_assets(document) if v['id']==payload.asset_id),None)
    if asset is None or asset['kind']!=kind or asset.get('rights_confirmed') is not True:raise WorkflowError('SOURCE_MEDIA_TRACK_ASSET_INVALID',400)
    if asset['sha256']!=payload.asset_sha256:raise WorkflowError('SOURCE_MEDIA_TRACK_ASSET_CHANGED')
    path=_verify_library_record(store,{'metadata':asset,'metadata_conflict':False})
    return asset,path

def _style(snapshot,reference):
    template=next((t for t in load_templates() if t['template_ref']==reference),None)
    if template is None:raise WorkflowError('SUBTITLE_TEMPLATE_UNKNOWN',400)
    snapshot.metadata['subtitle_style']=copy.deepcopy(template['style']);snapshot.metadata['subtitle_template_ref']=reference
    return SubtitleStyle.model_validate(template['style'])

def _check_captions(snapshot):
    try:
        cues=derive_subtitle_cues(snapshot);style=SubtitleStyle.model_validate(snapshot.metadata.get('subtitle_style') or {})
        selected=next((t for t in load_templates() if t['template_ref']==style.template_ref),None)
        if selected and selected['requires_word_timestamps'] and any(not cue.words for cue in cues):raise ProductionContractError('WORD_ALIGNMENT_UNAVAILABLE')
        validate_subtitles(cues,style,snapshot.duration_seconds)
    except (ProductionContractError,ValueError) as e:
        code='WORD_ALIGNMENT_UNAVAILABLE' if 'WORD_ALIGNMENT' in str(e) else 'SOURCE_MEDIA_TRACK_CAPTION_LAYOUT_INVALID'
        raise WorkflowError(code,400) from None

def _caption(text,start,end,source_start,source_end,metadata):
    text=unicodedata.normalize('NFC',text)
    return TimelineClip(clip_id='clip_'+uuid.uuid4().hex[:24],kind='subtitle',label=text[:180],source_start=round(source_start,6),
        source_end=round(source_end,6),timeline_start=round(start,6),duration=round(end-start,6),
        metadata={**metadata,'subtitle_text':text,'measured_source_words':[],'confidence':None})

def _audio_captions(document,snapshot,payload,asset,metadata):
    from .audio_transcripts import selected
    from .asr import analysis_for_asset
    transcript=selected(document,asset);record=analysis_for_asset(document,asset)
    if transcript is None or record is None or transcript.transcript_id!=payload.captions.transcript_id or record['analysis_sha256']!=payload.captions.analysis_sha256:
        raise WorkflowError('SOURCE_MEDIA_TRACK_TRANSCRIPT_CHANGED')
    style=_style(snapshot,payload.captions.subtitle_template_ref);track=_track(snapshot,payload.captions.replace_track_id,'subtitles',replace=True)
    capacity=min(180,subtitle_character_capacity(style));count=0
    for segment in transcript.segments:
        lo=max(segment.start_seconds,payload.source_start);hi=min(segment.end_seconds,payload.source_end)
        if hi-lo<.05:continue
        words=[w for w in segment.words if lo<=w.start_seconds<w.end_seconds<=hi]
        meta={**metadata,'transcript_id':transcript.transcript_id,'segment_id':segment.segment_id,'language':transcript.language,
            'timing_source':'uploaded_audio_provider_words' if words else 'uploaded_audio_segment_bounds_no_word_alignment'}
        if words:
            chunks=[];chunk=[]
            for word in words:
                if len(word.text)>capacity:raise WorkflowError('SOURCE_MEDIA_TRACK_CAPTION_LAYOUT_INVALID',400)
                if chunk and len(' '.join(w.text for w in [*chunk,word]))>capacity:chunks.append(chunk);chunk=[]
                chunk.append(word)
            if chunk:chunks.append(chunk)
            for group in chunks:
                a,b=group[0].start_seconds,group[-1].end_seconds
                clip=_caption(' '.join(w.text for w in group),payload.timeline_start+a-payload.source_start,
                    payload.timeline_start+b-payload.source_start,a,b,meta)
                clip.metadata.pop('subtitle_text');clip.metadata['measured_source_words']=[w.model_dump(mode='json') for w in group]
                track.clips.append(clip);count+=1
        else:
            track.clips.append(_caption(segment.text,payload.timeline_start+lo-payload.source_start,
                payload.timeline_start+hi-payload.source_start,lo,hi,meta));count+=1
    if not count:raise WorkflowError('SOURCE_MEDIA_TRACK_NO_CAPTIONS_IN_WINDOW',400)
    _check_captions(snapshot)
    return track,transcript.model_dump(mode='json')

def _request(payload):
    # Absent new optional bindings must retain historical idempotency hashes.
    body=payload.model_dump(mode='json',exclude={'request_key'})
    for key in ('source_video_asset_id','source_video_asset_sha256'):
        if body.get(key) is None:body.pop(key,None)
    return body

def _save_import(store,con,project,snapshot,payload,operation,asset,result,*,cue_source_sha256=None,transcript_reference=None,waveform=None,source_video_reference=None,actor_ref):
    history=list(records(project['document']).values())
    if len(history)>=LIMIT:raise WorkflowError('SOURCE_MEDIA_IMPORT_HISTORY_LIMIT')
    identifier=result.pop('_import_id');body=_request(payload)
    row={'schema_version':SCHEMA,'import_id':identifier,'project_id':project['id'],'operation':operation,
        'asset_id':asset['id'],'asset_sha256':asset['sha256'],'asset_binding_sha256':digest(binding(asset)),
        'request_key_sha256':hashlib.sha256(payload.request_key.encode()).hexdigest(),'request':body,'request_sha256':digest(body),
        'result':result,'cue_source_sha256':cue_source_sha256,'transcript_reference':transcript_reference,'waveform':waveform,'created_at':now(),'actor_ref':actor_ref}
    if source_video_reference is not None:row['source_video_reference']=copy.deepcopy(source_video_reference)
    row['sha256']=digest(row)
    for track in snapshot.tracks:
        for clip in track.clips:
            if clip.metadata.get('native_media_import_id')==identifier:clip.metadata['native_media_import_sha256']=row['sha256']
    project['document']['source_media_track_imports']=[*history,row]
    _save(store,con,project,snapshot,'source_media_track_import_saved_review_required')
    return {'import_id':identifier,'operation':operation,'replayed':False,'asset_id':asset['id'],
        'asset_sha256':asset['sha256'],'request_sha256':row['request_sha256'],**copy.deepcopy(result)}

def _prior(document,payload,operation,*,root=None):
    key=hashlib.sha256(payload.request_key.encode()).hexdigest()
    row=next((r for r in records(document).values() if r.get('request_key_sha256')==key),None)
    if row:
        if row['operation']!=operation or row['request_sha256']!=digest(_request(payload)):raise WorkflowError('SOURCE_MEDIA_TRACK_IDEMPOTENCY_CONFLICT')
        if row.get('source_video_reference'):
            if root is None:raise WorkflowError('SOURCE_CAPTION_VIDEO_PHYSICAL_VERIFICATION_REQUIRED')
            from .source_caption_mapping import verify_reference
            verify_reference(document,row['source_video_reference'],root=root)
        return {'import_id':row['import_id'],'operation':operation,'replayed':True,'asset_id':row['asset_id'],
            'asset_sha256':row['asset_sha256'],'request_sha256':row['request_sha256'],**copy.deepcopy(row['result'])}

def _snapshot(store,con,project_id,payload):
    project=store.editable(con,project_id,payload.revision);state,snapshot=_cas(project,payload.expected_version,store=store,con=con,seed_tracks=True)
    if state['sha256']!=payload.timeline_sha256:raise WorkflowError('SOURCE_MEDIA_TRACK_TIMELINE_CHANGED')
    return project,snapshot

def add_audio(store,project_id,body,*,actor_ref,config=None):
    payload=_parse(Audio,body)
    # The local decoder runs outside the SQLite write transaction. A second CAS
    # and physical source check below fences changes while measuring.
    with store.transaction() as con:
        before=store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())
        prior=_prior(before['document'],payload,'audio')
        if prior:return prior
        before,_=_snapshot(store,con,project_id,payload);prepared,path=_asset(store,before['document'],payload,'audio')
    cached=next((r.get('waveform') for r in records(before['document']).values() if r['operation']=='audio' and
        r['asset_binding_sha256']==digest(binding(prepared)) and r.get('waveform')),None)
    if cached:waveform=copy.deepcopy(cached)
    else:
        from .pipeline import Config
        from app.audio_waveform import measure_waveform
        config=config or Config(data_root=store.root)
        try:waveform=asyncio.run(measure_waveform(path,executable=str(config.ffmpeg_bin/'ffmpeg.exe'),
            duration_seconds=prepared['duration_seconds'],timeout_seconds=300))
        except (ValueError,RuntimeError,TimeoutError,OSError):raise WorkflowError('SOURCE_MEDIA_TRACK_WAVEFORM_FAILED',400) from None
    with store.transaction() as con:
        prior=_prior(store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())['document'],payload,'audio')
        if prior:return prior
        project,snapshot=_snapshot(store,con,project_id,payload);asset,_=_asset(store,project['document'],payload,'audio')
        if payload.source_end>asset['duration_seconds']+.000001:raise WorkflowError('SOURCE_MEDIA_TRACK_SOURCE_WINDOW_INVALID',400)
        end=payload.repeat_until if payload.repeat_until is not None else payload.timeline_start+payload.source_end-payload.source_start
        if end>snapshot.duration_seconds+.000001:raise WorkflowError('SOURCE_MEDIA_TRACK_TIMELINE_WINDOW_INVALID',400)
        from .audio_transcripts import selected
        from .auto_edit_timeline import protected_window
        transcript=selected(project['document'],asset)
        if payload.role=='voice' and transcript:
            a,b=protected_window((payload.source_start,payload.source_end),transcript,asset['duration_seconds'])
            if abs(a-payload.source_start)>1e-6 or abs(b-payload.source_end)>1e-6:raise WorkflowError('SOURCE_MEDIA_TRACK_SPOKEN_WORD_CUT',400)
        identifier='smi_'+uuid.uuid4().hex[:24];meta={'native_media_import_id':identifier,'native_asset_id':asset['id'],
            'source_checksum_sha256':asset['sha256'],'source_media_mutated':False,'speech_boundary_verified':bool(payload.role=='voice' and transcript),
            'source_audio_waveform':copy.deepcopy(waveform)}
        track=_track(snapshot,payload.track_id,payload.role,replace=payload.replace_existing)
        length=payload.source_end-payload.source_start;step=length-payload.crossfade_seconds
        count=max(1,math.ceil(max(0,end-payload.timeline_start-length)/step)+1) if payload.repeat_until is not None else 1
        existing=sum(len(t.clips) for t in snapshot.tracks if t.type=='audio')
        if existing+count>128:raise WorkflowError('PREVIEW_AUDIO_CLIP_LIMIT',400)
        clips=[]
        for index in range(count):
            start=round(payload.timeline_start+index*step,6);duration=round(min(length,end-start),6)
            if duration<.05:raise WorkflowError('SOURCE_MEDIA_TRACK_REPEAT_WINDOW_TOO_SHORT',400)
            fade_in=payload.fade_in_seconds if index==0 else payload.crossfade_seconds
            fade_out=payload.fade_out_seconds if index==count-1 else payload.crossfade_seconds
            clip=TimelineClip(clip_id='clip_'+uuid.uuid4().hex[:24],kind=payload.role,label=asset['filename'][:120],asset_id=asset_reference(asset),
                source_start=payload.source_start,source_end=round(payload.source_start+duration,6),timeline_start=start,duration=duration,volume=payload.volume,
                transition_in=TransitionSpec(kind='fade' if index==0 else 'crossfade' if fade_in else 'none',duration_seconds=min(fade_in,duration)),
                transition_out=TransitionSpec(kind='fade' if index==count-1 else 'crossfade' if fade_out else 'none',duration_seconds=min(fade_out,duration)),
                metadata={**meta,'repeat_index':index})
            track.clips.append(clip);clips.append(clip.clip_id)
        caption_track,reference=_audio_captions(project['document'],snapshot,payload,asset,meta) if payload.captions else (None,None)
        result={'_import_id':identifier,'track_id':track.track_id,'clip_ids':clips,'caption_track_id':caption_track.track_id if caption_track else None,
            'caption_count':len(caption_track.clips) if caption_track else 0,'source_window':[payload.source_start,payload.source_end],
            'timeline_window':[payload.timeline_start,end],'speech_boundary_verified':bool(payload.role=='voice' and transcript)}
        return _save_import(store,con,project,snapshot,payload,'audio',asset,result,transcript_reference=reference,waveform=waveform,actor_ref=actor_ref)

def add_subtitles(store,project_id,body,*,actor_ref):
    payload=_parse(Subtitles,body)
    with store.transaction() as con:
        prior=_prior(store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())['document'],payload,'subtitles',root=store.root)
        if prior:return prior
        project,snapshot=_snapshot(store,con,project_id,payload);asset,path=_asset(store,project['document'],payload,'subtitle')
        if not is_auto_edit(project['document']) and payload.timebase=='source' and payload.source_video_asset_id is None:
            raise WorkflowError('NARRATED_MEDIA_SOURCE_TIME_REQUIRES_EXPLICIT_VIDEO_MAPPING',400)
        from .multipart_ingestion import subtitle_cues,CHUNK_BYTES
        if path.stat().st_size>CHUNK_BYTES:raise WorkflowError('SOURCE_MEDIA_TRACK_SUBTITLE_SIZE_INVALID',400)
        cues=subtitle_cues(path.read_bytes(),asset['source_mime'])
        if digest(cues)!=digest(asset['cues']):raise WorkflowError('SOURCE_MEDIA_TRACK_CUES_CHANGED')
        _style(snapshot,payload.subtitle_template_ref);track=_track(snapshot,payload.replace_track_id,'subtitles',replace=True)
        identifier='smi_'+uuid.uuid4().hex[:24];clipped=0;dropped=0;mapped=0
        if payload.source_video_asset_id is not None:
            from .source_caption_mapping import reference,verify_reference,clips,edited_field
            ref=reference(project['document'],snapshot,payload.source_video_asset_id,payload.source_video_asset_sha256)
            verify_reference(project['document'],ref,root=store.root)
            track.clips,detail=clips(snapshot,cues,ref,identifier,asset,_request(payload))
            if not track.clips:raise WorkflowError('SOURCE_MEDIA_TRACK_NO_CAPTIONS_IN_WINDOW',400)
            # An explicit full source import replaces the manual layout decision
            # of this track; old snapshots and import records remain immutable.
            field=edited_field(snapshot);edited=snapshot.metadata.get(field,[])
            if track.track_id in edited:snapshot.metadata[field]=[v for v in edited if v!=track.track_id]
            _check_captions(snapshot)
            result={'_import_id':identifier,'track_id':track.track_id,'clip_ids':[c.clip_id for c in track.clips],**detail}
            return _save_import(store,con,project,snapshot,payload,'subtitles',asset,result,cue_source_sha256=digest(cues),source_video_reference=ref,actor_ref=actor_ref)
        windows=[c for t in snapshot.tracks if t.type=='video' and t.kind=='source' and not t.disabled for c in t.clips if not c.disabled]
        for ordinal,cue in enumerate(cues):
            intervals=[(cue['start'],cue['end'],cue['start'],cue['end'])] if payload.timebase=='timeline' else [
                (c.timeline_start+(max(cue['start'],c.source_start)-c.source_start)/c.speed,
                 c.timeline_start+(min(cue['end'],c.source_end)-c.source_start)/c.speed,
                 max(cue['start'],c.source_start),min(cue['end'],c.source_end)) for c in windows
                 if min(cue['end'],c.source_end)-max(cue['start'],c.source_start)>=.05]
            if not intervals:dropped+=1
            for a,b,sa,sb in intervals:
                a+=payload.offset_seconds;b+=payload.offset_seconds
                if a<0 or b>snapshot.duration_seconds:
                    if not payload.trim_to_timeline:raise WorkflowError('SOURCE_MEDIA_TRACK_CAPTION_OUT_OF_BOUNDS',400)
                    clipped+=1;a=max(0,a);b=min(snapshot.duration_seconds,b)
                if b-a<.05:dropped+=1;continue
                metadata={'native_media_import_id':identifier,'native_asset_id':asset['id'],'source_checksum_sha256':asset['sha256'],
                    'cue_ordinal':ordinal,'cue_source_sha256':digest(cue),'timing_source':'uploaded_cue_bounds_no_word_alignment',
                    'timebase':payload.timebase,'mapped_from_source':payload.timebase=='source','source_media_mutated':False}
                track.clips.append(_caption(cue['text'],a,b,sa,sb,metadata));mapped+=1
        if not mapped:raise WorkflowError('SOURCE_MEDIA_TRACK_NO_CAPTIONS_IN_WINDOW',400)
        if mapped>2000:raise WorkflowError('AUTO_EDIT_TIMELINE_LIMIT',400)
        _check_captions(snapshot)
        result={'_import_id':identifier,'track_id':track.track_id,'clip_ids':[c.clip_id for c in track.clips],
            'caption_count':mapped,'source_cue_count':len(cues),'clipped_intervals':clipped,'dropped_intervals':dropped,'timebase':payload.timebase}
        return _save_import(store,con,project,snapshot,payload,'subtitles',asset,result,cue_source_sha256=digest(cues),actor_ref=actor_ref)

def edit_captions(store,project_id,body,*,actor_ref):
    payload=_parse(EditCaptions,body)
    with store.transaction() as con:
        project,snapshot=_snapshot(store,con,project_id,payload);verify_physical(store.root,project['document'])
        _style(snapshot,payload.subtitle_template_ref);changed=[]
        for edit in payload.edits:
            found=next(((t,c) for t in snapshot.tracks if t.type=='text' and t.kind=='subtitles' for c in t.clips if c.clip_id==edit.clip_id),None)
            if found is None:raise WorkflowError('SOURCE_MEDIA_TRACK_CAPTION_NOT_FOUND',400)
            track,clip=found
            if track.locked:raise WorkflowError('SOURCE_MEDIA_TRACK_LOCKED',400)
            if edit.timeline_start+edit.duration>snapshot.duration_seconds+.000001:raise WorkflowError('SOURCE_MEDIA_TRACK_CAPTION_OUT_OF_BOUNDS',400)
            text=unicodedata.normalize('NFC',edit.text)
            if text==clip.metadata.get('subtitle_text',clip.label) and edit.timeline_start==clip.timeline_start and edit.duration==clip.duration:continue
            clip.label=text[:180];clip.timeline_start=edit.timeline_start;clip.duration=edit.duration;clip.source_end=clip.source_start+edit.duration*clip.speed
            clip.metadata.update(subtitle_text=text,measured_source_words=[],confidence=None,timing_source='human_edited_caption_bounds_no_word_alignment',
                human_caption_edit=True,transcript_evidence_mutated=False,source_media_mutated=False);changed.append(clip.clip_id)
        _check_captions(snapshot)
        if not changed and snapshot.model_dump(mode='json')==project['document']['canonical_timeline']['snapshot']:return {'changed':False,'clip_ids':[]}
        _save(store,con,project,snapshot,'source_caption_edits_saved_review_required')
        store.event(con,project_id,'source_caption_editor_attributed',{'actor_ref':actor_ref,'clip_ids':changed,'provider_calls':0,'private_text_logged':False})
    return {'changed':True,'clip_ids':changed}
