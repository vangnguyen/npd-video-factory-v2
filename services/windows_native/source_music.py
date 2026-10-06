"""Rights-confirmed immutable music -> canonical source audio track."""
import copy
import math
import uuid
from .auto_edit_timeline import _save,validate_document,view
from .auto_edit_analysis import asset_reference
from .contracts import WorkflowError
from app.timeline_models import TimelineClip,TimelineTrack,TimelineSnapshot,TransitionSpec


def set_music(store,project_id,revision,music):
    if music.get('rights_confirmed') is not True or music.get('kind')!='music':
        raise WorkflowError('MEDIA_RIGHTS_CONFIRMATION_REQUIRED',400)
    duration=music.get('duration_seconds')
    if type(duration) not in (int,float) or not math.isfinite(duration) or not .05<=duration<=600:
        raise WorkflowError('MUSIC_AUDIO_INVALID_WAV_MP3_MAX_10_MINUTES',400)
    with store.transaction() as con:
        project=store.editable(con,project_id,revision)
        state=validate_document(project['document']);snapshot=TimelineSnapshot.model_validate(state['snapshot'])
        track=next((item for item in snapshot.tracks if item.kind=='music' and item.type=='audio'),None)
        if track and track.locked:raise WorkflowError('AUTO_EDIT_MUSIC_TRACK_LOCKED',400)
        count=math.ceil(snapshot.duration_seconds/duration)
        other=sum(len(item.clips) for item in snapshot.tracks if item.type=='audio' and item is not track)
        if count+other>128:raise WorkflowError('PREVIEW_AUDIO_CLIP_LIMIT',400)
        if track is None:
            if len(snapshot.tracks)>=32:raise WorkflowError('AUTO_EDIT_TIMELINE_LIMIT',400)
            track=TimelineTrack(track_id='trk_'+uuid.uuid4().hex[:24],type='audio',kind='music',
                label='Nhạc nền',order=len(snapshot.tracks));snapshot.tracks.append(track)
        project['document']['source_music_assets']=list({item['id']:item for item in [
            *project['document'].get('source_music_assets',[]),
            *([project['document']['music']] if project['document'].get('music') else []),
            {**copy.deepcopy(music),'license':'owner_upload_rights_attestation','rights_status':'owner_attested',
             'bpm':None,'mood':None,'energy':None,'provider':'user-upload',
             'source_reference':'originals/'+music['original_id'],'generation_provenance':{}}
        ]}.values())
        project['document']['music']=copy.deepcopy(music)
        track.clips=[]
        for index in range(count):
            start=round(index*duration,6);length=round(min(duration,snapshot.duration_seconds-start),6)
            if length<.000001:continue
            track.clips.append(TimelineClip(clip_id='clip_'+uuid.uuid4().hex[:24],kind='music',label=music['filename'][:120],
                asset_id=asset_reference(music),source_start=0,source_end=length,timeline_start=start,duration=length,
                volume=.12,transition_in=TransitionSpec(kind='fade' if index==0 else 'none',duration_seconds=min(.5,length)),
                transition_out=TransitionSpec(kind='fade' if index==count-1 else 'none',duration_seconds=min(.8,length)),
                metadata={'native_asset_id':music['id'],'source_checksum_sha256':music['sha256'],
                    'source_type':'user_upload','rights_status':'owner_attested','license':'owner_upload_rights_attestation',
                    'provider':'user-upload','source_reference':'originals/'+music['original_id'],
                    'generation_provenance':{},'music_repeat_index':index,'source_audio_preserved':True}))
        snapshot.metadata['music_review']={'rights_basis':'explicit owner upload attestation',
            'music_asset_id':music['id'],'human_approval_required':True,'automatic_ducking':False,
            'previous_versions_preserved':True,'provider_calls':0}
        _save(store,con,project,snapshot,'auto_edit_source_music_saved_review_required')
    return view(store,project_id)
