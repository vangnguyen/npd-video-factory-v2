"""Bounded canonical video/audio/text edits and same-preparation restoration.

The default shot view and advanced video/audio/text share canonical state. Restores copy only editing fields;
uploads, rights, provider/cost journals, jobs and approval authority never rewind.
"""
import copy,json,math
from typing import Literal
from pydantic import Field,StrictInt,field_validator,model_validator
from app.models import StrictModel
from app.timeline_models import TimelineSnapshot,TimelineOperation
from app.timeline_logic import apply_operations,TimelineEditError
from app.timeline_audio_processing import AudioProcessing
from .contracts import WorkflowError,digest
from . import narrated_media_timeline as media

SCHEMA='native-narrated-timeline-editor-v1'
SHA=r'^[a-f0-9]{64}$'
ALLOWED={
    'move':{'clip_id','timeline_start','target_track_id'},'trim':{'clip_id','source_start','source_end','timeline_start','duration'},
    'split':{'clip_id','at_seconds'},'delete':{'clip_id'},'reorder':{'clip_id','target_index'},
    'disable':{'clip_id','disabled'},'duplicate':{'clip_id','timeline_start','target_track_id'},
    'set_clip_properties':{'clip_id','volume','speed','duration','crop','transform','opacity'},'set_track_state':{'track_id','locked','muted','disabled'}}

def numbers(value):
    if isinstance(value,dict):
        for key,v in value.items():
            if key in {'timeline_start','source_start','source_end','at_seconds','volume','speed','duration','opacity','x','y','width','height','scale','rotation_degrees','original_target_lufs',
                    'music_target_lufs','duck_threshold','duck_ratio','duck_attack_ms','duck_release_ms'}:
                if type(v) not in (int,float) or not math.isfinite(v):raise ValueError('finite numeric decision required')
            elif key=='target_index' and type(v) is not int:raise ValueError('integer index required')
            elif key in {'locked','muted','disabled','normalize_original_audio','normalize_music','duck_music'} and type(v) is not bool:
                raise ValueError('boolean decision required')
            elif isinstance(v,dict):numbers(v)

class Binding(StrictModel):
    revision:StrictInt=Field(ge=1)
    expected_version:StrictInt=Field(ge=1)
    timeline_sha256:str=Field(pattern=SHA)

class Edit(Binding):
    operations:list[TimelineOperation]=Field(min_length=1,max_length=100)
    @field_validator('operations',mode='before')
    @classmethod
    def closed(cls,v):
        if not isinstance(v,list):raise ValueError('operation list required')
        for op in v:
            if not isinstance(op,dict) or op.get('type') not in ALLOWED or set(op)-{'type'}-ALLOWED[op['type']]:
                raise ValueError('closed operation required')
            numbers(op)
        return v

class Configure(Binding):
    audio_processing:AudioProcessing|None=None
    subtitle_template_ref:str|None=Field(default=None,min_length=1,max_length=100)
    keywords:list[str]=Field(default_factory=list,max_length=30)
    @field_validator('audio_processing',mode='before')
    @classmethod
    def finite(cls,v):
        if v is not None:
            if not isinstance(v,dict):raise ValueError('processing object required')
            numbers(v)
        return v
    @model_validator(mode='after')
    def choice(self):
        if self.audio_processing is None and self.subtitle_template_ref is None or self.keywords and self.subtitle_template_ref is None:
            raise ValueError('settings choice required')
        return self

class Restore(Binding):
    restore_revision:StrictInt=Field(ge=1)
    restore_timeline_sha256:str=Field(pattern=SHA)

def _parse(model,body):
    try:return model.model_validate(body)
    except ValueError:raise WorkflowError('NARRATED_TIMELINE_REQUEST_INVALID',400) from None

def _cas(store,con,project,payload,*,restoring=False):
    state,snapshot=media.cas(store,con,project,payload.expected_version,seed_tracks=not restoring)
    if state['sha256']!=payload.timeline_sha256:raise WorkflowError('NARRATED_TIMELINE_SHA_CHANGED')
    _physical(store,con,project['id'],project['document'],allow_stale_voice_input=restoring)
    return state,snapshot

def _physical(store,con,project_id,document,*,allow_stale_voice_input=False):
    from .pipeline import Config
    from .narrated_media_mix import verify
    from .narration import load_reference,identity
    if not allow_stale_voice_input and document['prepared_narration']['voice_input_sha256']!=identity(document):
        raise WorkflowError('PREPARED_NARRATION_INPUT_CHANGED_REPREPARE')
    if media.enabled(document):verify(Config(data_root=store.root),document,store=store,con=con)
    else:
        load_reference(store,con,project_id,document)

def _candidate(project,snapshot):
    document=copy.deepcopy(project['document'])
    document['canonical_timeline']={**document['canonical_timeline'],'snapshot':snapshot.model_dump(mode='json'),'sha256':digest(snapshot.model_dump(mode='json'))}
    from .shot_adapter import validate_document
    validate_document(document)
    return document

def _bounds(snapshot,duration):
    body=snapshot.model_dump(mode='json');body['duration_seconds']=duration
    for track in body['tracks']:
        for clip in track['clips']:
            if clip['duration']<.05 or clip['timeline_start']+clip['duration']>duration+.000001:
                raise WorkflowError('NARRATED_TIMELINE_CLIP_OUTSIDE_MEASURED_DURATION',400)
    return TimelineSnapshot.model_validate(body)

def _word_cuts(document,snapshot):
    from .source_assets import canonical_assets
    from .audio_transcripts import selected
    assets={v['id']:v for v in canonical_assets(document)}
    for track in snapshot.tracks:
        if track.kind!='voice':continue
        for clip in track.clips:
            asset=assets.get(clip.metadata.get('native_asset_id'))
            transcript=selected(document,asset) if asset is not None else None
            if transcript is None:continue
            for segment in transcript.segments:
                for word in segment.words:
                    if any(word.start_seconds+.000001<p<word.end_seconds-.000001 for p in (clip.source_start,clip.source_end)):
                        raise WorkflowError('NARRATED_TIMELINE_CUT_THROUGH_SPOKEN_WORD',400)

def edit(store,project_id,body,workspace_id):
    payload=_parse(Edit,body)
    with store.transaction() as con:
        project=store.editable(con,project_id,payload.revision);_,snapshot=_cas(store,con,project,payload);duration=snapshot.duration_seconds
        try:
            for op in payload.operations:
                track=next((t for t in snapshot.tracks if t.track_id==op.track_id),None) if op.type=='set_track_state' else next((t for t in snapshot.tracks if any(c.clip_id==op.clip_id for c in t.clips)),None)
                if track is None:raise WorkflowError('NARRATED_TIMELINE_SELECTION_NOT_FOUND',404)
                if track.type not in {'video','audio','text'}:raise WorkflowError('NARRATED_TIMELINE_TRACK_INVALID',400)
                if track.type=='video':
                    from .narrated_video_timeline import enable
                    enable(snapshot)
                clip=next((c for c in track.clips if c.clip_id==op.clip_id),None)
                if clip and clip.metadata.get('narrated_generated_voice') and not (op.type=='disable' or op.type=='set_clip_properties' and
                        op.volume is not None and all(getattr(op,key) is None for key in ('speed','duration','crop','transform','opacity'))):
                    raise WorkflowError('NARRATED_TIMELINE_MEASURED_VOICE_TIMING_PROTECTED',400)
                if op.type=='set_clip_properties' and (track.type=='video' and op.volume is not None or
                        track.type=='audio' and any(getattr(op,key) is not None for key in ('duration','crop','transform','opacity'))):
                    raise WorkflowError('NARRATED_TIMELINE_CLIP_PROPERTIES_ROLE_MISMATCH',400)
                if op.target_track_id:
                    target=next((t for t in snapshot.tracks if t.track_id==op.target_track_id),None)
                    if target is None or target.kind!=track.kind:raise WorkflowError('NARRATED_TIMELINE_TRACK_ROLE_MISMATCH',400)
                if track.type=='text' and op.type!='set_track_state':
                    if op.type=='set_clip_properties':raise WorkflowError('NARRATED_TIMELINE_CAPTION_PROPERTIES_INVALID',400)
                    snapshot.metadata['narrated_caption_edited_tracks']=sorted(set(snapshot.metadata.get('narrated_caption_edited_tracks',[]))|{track.track_id})
                    # A human structural edit must not be rebuilt as a default caption,
                    # or reuse old word timestamps after moving/splitting its source.
                    for caption in track.clips:
                        caption.metadata['human_caption_edit']=True
                        if op.type in {'move','trim','split','duplicate'}:
                            caption.metadata.update(measured_source_words=[],timing_source='human_timeline_edit_no_word_alignment')
                snapshot=_bounds(apply_operations(snapshot,[op]),duration)
                if track.type=='video' and op.type=='reorder':
                    primary=next(t for t in snapshot.tracks if t.track_id==track.track_id);cursor=0.
                    for c in primary.clips:c.timeline_start=round(cursor,6);cursor+=c.duration
                    snapshot=_bounds(snapshot,duration)
            from .narrated_video_timeline import reflow_captions
            snapshot=reflow_captions(project['document'],snapshot)
            _word_cuts(project['document'],snapshot)
            candidate=_candidate(project,snapshot);_physical(store,con,project_id,candidate)
        except (TimelineEditError,ValueError):raise WorkflowError('NARRATED_TIMELINE_OPERATION_INVALID',400) from None
        media.save(store,con,project,snapshot,'narrated_canonical_tracks_edited')
    return view(store,project_id,workspace_id)

def configure(store,project_id,body,workspace_id):
    payload=_parse(Configure,body)
    with store.transaction() as con:
        project=store.editable(con,project_id,payload.revision);_,snapshot=_cas(store,con,project,payload)
        if payload.audio_processing is not None:
            if any(t.locked for t in snapshot.tracks if t.type=='audio'):raise WorkflowError('NARRATED_TIMELINE_AUDIO_TRACK_LOCKED',400)
            snapshot.metadata['source_audio_processing']=payload.audio_processing.model_dump(mode='json')
        if payload.subtitle_template_ref is not None:
            if any(t.locked for t in snapshot.tracks if t.kind=='subtitles'):raise WorkflowError('NARRATED_TIMELINE_SUBTITLE_TRACK_LOCKED',400)
            from .source_media_tracks import _style,_check_captions
            from app.production_models import SubtitleStyle
            _style(snapshot,payload.subtitle_template_ref)
            try:snapshot.metadata['subtitle_style']=SubtitleStyle.model_validate({**snapshot.metadata['subtitle_style'],'keywords':payload.keywords}).model_dump(mode='json')
            except ValueError:raise WorkflowError('SUBTITLE_TEMPLATE_KEYWORDS_INVALID',400) from None
            _check_captions(snapshot)
        candidate=_candidate(project,snapshot);_physical(store,con,project_id,candidate)
        media.save(store,con,project,snapshot,'narrated_canonical_settings_edited')
    return view(store,project_id,workspace_id)

def restore(store,project_id,body,workspace_id):
    payload=_parse(Restore,body)
    with store.transaction() as con:
        project=store.editable(con,project_id,payload.revision);state,_=_cas(store,con,project,payload,restoring=True)
        row=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project_id,payload.restore_revision)).fetchone()
        if row is None or payload.restore_revision>=project['revision']:raise WorkflowError('NARRATED_TIMELINE_RESTORE_NOT_FOUND',404)
        prior=json.loads(row['document']);old=prior.get('canonical_timeline')
        if not media.ready(prior) or old['sha256']!=payload.restore_timeline_sha256 or old['version']>=state['version']:
            raise WorkflowError('NARRATED_TIMELINE_RESTORE_BINDING_CHANGED',400)
        if digest(prior['prepared_narration'])!=digest(project['document']['prepared_narration']):
            raise WorkflowError('NARRATED_TIMELINE_RESTORE_REQUIRES_SAME_PREPARATION',400)
        from .shot_adapter import validate_document
        validate_document(prior)
        snapshot=TimelineSnapshot.model_validate(old['snapshot']);current=state['snapshot']
        targets={t.track_id:t.model_dump(mode='json') for t in snapshot.tracks}
        for track in current['tracks']:
            if track['locked'] and {k:v for k,v in track.items() if k not in {'locked','muted','disabled'}}!={k:v for k,v in targets.get(track['track_id'],{}).items() if k not in {'locked','muted','disabled'}}:
                raise WorkflowError('NARRATED_TIMELINE_RESTORE_TRACK_LOCKED',400)
        document=copy.deepcopy(project['document'])
        for key in ('proposal','scene_media','edit_plan'):
            if key in prior:document[key]=copy.deepcopy(prior[key])
            else:document.pop(key,None)
        candidate_project={**project,'document':document}
        candidate=_candidate(candidate_project,snapshot);_physical(store,con,project_id,candidate)
        media.save(store,con,candidate_project,snapshot,'narrated_canonical_timeline_restored',restored_from_version=old['version'])
    return view(store,project_id,workspace_id)

def view(store,project_id,workspace_id):
    project=store.get(project_id);document=project['document']
    if not media.ready(document):raise WorkflowError('NARRATED_MEDIA_MEASURED_NARRATION_REQUIRED',400)
    with store.transaction() as con:
        state,snapshot=media.cas(store,con,project,document['canonical_timeline']['version'])
        from .narration import identity
        voice_current=document['prepared_narration']['voice_input_sha256']==identity(document)
        if voice_current:snapshot=media.seed(store,con,project,snapshot)
        else:snapshot.metadata['native_project_id']=project_id
        # Reads are bounded, inert and return no private document/job/provider data.
        rows=con.execute('SELECT revision,document FROM project_versions WHERE project_id=? ORDER BY revision DESC LIMIT 201',(project_id,)).fetchall()
    versions={}
    for row in reversed(rows[:200]):
        doc=json.loads(row['document']);saved=doc.get('canonical_timeline')
        if not media.ready(doc) or saved['version'] in versions:continue
        journal=next((v for v in doc.get('narrated_timeline_mutations',[]) if v.get('version')==saved['version'] and v.get('sha256')==saved['sha256']),None)
        versions[saved['version']]={'version':saved['version'],'revision':row['revision'],'sha256':saved['sha256'],
            'same_preparation':digest(doc['prepared_narration'])==digest(document['prepared_narration']),
            'mutation':copy.deepcopy(journal['mutation']) if journal else {'type':'edit'}}
    history=list(versions.values())[-100:]
    from app.subtitle_templates import template_catalog
    return {'schema_version':SCHEMA,'workspace_id':workspace_id,'project_id':project_id,'revision':project['revision'],
        'timeline_version':state['version'],'timeline_sha256':state['sha256'],'duration_seconds':snapshot.duration_seconds,
        'snapshot':snapshot.model_dump(mode='json'),'projection_pending':not media.enabled(document),'projection_sha256':digest(snapshot.model_dump(mode='json')),'voice_input_current':voice_current,
        'history':history,'history_truncated':len(rows)>200 or len(versions)>100,'subtitle_templates':template_catalog(),
        'provider_calls':0,'publishing_enabled':False,'human_review_required':True,'source_media_mutated':False,'video_editing_available':True}
