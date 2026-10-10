"""Canonical visual clips with independent, measured narration/shot semantics.

Semantic fields remain inside the same TimelineSnapshot. They describe voice,
titles and the default shot view; visual clip windows are never reconstructed
from those fields during an advanced edit or render.
"""
import copy,math
from app.timeline_models import TimelineSnapshot
from .contracts import WorkflowError,digest

SCHEMA='native-narrated-video-timeline-v1'
FIELD='narrated_visual_semantics'

def enabled(snapshot):
    metadata=snapshot.metadata if hasattr(snapshot,'metadata') else snapshot.get('metadata',{})
    value=metadata.get(FIELD)
    if value is not None and (not isinstance(value,dict) or value.get('schema_version')!=SCHEMA):
        raise WorkflowError('NARRATED_VIDEO_SCHEMA_CHANGED')
    return value is not None

def semantic_shots(snapshot):
    metadata=snapshot.metadata if hasattr(snapshot,'metadata') else snapshot['metadata'];value=metadata[FIELD]
    from .shot_adapter import SNAPSHOT_FIELDS,MAX_SHOTS
    shots=value.get('shots')
    if (set(value)!={'schema_version','shots','sha256'} or not isinstance(shots,list) or not 1<=len(shots)<=MAX_SHOTS or
        value.get('sha256')!=digest(shots) or any(not isinstance(s,dict) or set(s)!=SNAPSHOT_FIELDS|{'shot_id'} for s in shots) or
        len({s['shot_id'] for s in shots})!=len(shots)):
        raise WorkflowError('NARRATED_VIDEO_SEMANTICS_CHANGED')
    return copy.deepcopy(shots)

def enable(snapshot):
    if enabled(snapshot):return
    from .shot_adapter import shots_from_snapshot
    shots=shots_from_snapshot(snapshot.model_dump(mode='json'))
    snapshot.metadata[FIELD]={'schema_version':SCHEMA,'shots':shots,'sha256':digest(shots)}

def preserve(value,document,canvas):
    """Default shot edits update their own visual group and keep other decisions."""
    if not canvas or not enabled(canvas):return value
    from .shot_adapter import shots_from_snapshot
    after=shots_from_snapshot(value);before=semantic_shots(canvas)
    old={s['shot_id']:s for s in before};new={s['shot_id']:s for s in after}
    primary=next(t for t in value['tracks'] if t['track_id']=='trk_native_video')
    prior=next(t for t in canvas['tracks'] if t['track_id']=='trk_native_video')
    def starts(shots):
        cursor=0.;out={}
        for s in shots:out[s['shot_id']]=cursor;cursor+=s['duration']
        return out
    old_starts,new_starts=starts(before),starts(after)
    replaced={key for key,s in new.items() if key not in old or any(s[k]!=old[key][k] for k in ('asset_id','source_start','duration'))}
    clips=[]
    for c in prior['clips']:
        identifier=c['metadata'].get('shot_id')
        if identifier not in new or identifier in replaced:continue
        c=copy.deepcopy(c);s=new[identifier]
        c['timeline_start']=round(c['timeline_start']+new_starts[identifier]-old_starts[identifier],6)
        if s!=old[identifier]:
            if 'shot' in c['metadata']:c['metadata']['shot']=copy.deepcopy({k:v for k,v in s.items() if k!='shot_id'})
            c['metadata'].update(shot_number=after.index(s)+1,fit=s['crop_strategy'],motion=s['motion'])
        if s['on_screen_text']!=old[identifier]['on_screen_text']:c['label']=s['on_screen_text']
        if s['transition']!=old[identifier]['transition']:
            c['transition_in']={'kind':s['transition'],'duration_seconds':min(.15,c['duration']) if s['transition']=='fade' else 0}
        clips.append(c)
    clips.extend(copy.deepcopy(c) for c in primary['clips'] if c['metadata']['shot_id'] in replaced)
    result={**copy.deepcopy(prior),'clips':clips}
    if prior['locked'] and result!=prior:raise WorkflowError('NARRATED_VIDEO_TRACK_LOCKED',400)
    primary.clear();primary.update(result)
    value['metadata'][FIELD]={'schema_version':SCHEMA,'shots':after,'sha256':digest(after)}
    return value

def validate(document):
    snapshot=TimelineSnapshot.model_validate(document['canonical_timeline']['snapshot'])
    if not enabled(snapshot):return
    from .shot_adapter import _assets,_check_shot
    assets=_assets(document);shots=semantic_shots(snapshot);known={s['shot_id']:s for s in shots}
    for s in shots:_check_shot(s,assets)
    primary=[t for t in snapshot.tracks if t.type=='video']
    if len(primary)!=1 or primary[0].track_id!='trk_native_video' or primary[0].kind!='source':
        raise WorkflowError('NARRATED_VIDEO_PRIMARY_TRACK_INVALID')
    if abs(sum(s['duration'] for s in shots)-snapshot.duration_seconds)>1e-6:raise WorkflowError('NARRATED_VIDEO_MEASURED_CANVAS_CHANGED')
    for clip in primary[0].clips:
        semantic=known.get(clip.metadata.get('shot_id'));asset=assets.get(clip.metadata.get('native_asset_id'))
        if (semantic is None or asset is None or asset['id']!=semantic['asset_id'] or clip.asset_id!='ast_'+digest(asset['id'])[:32] or
            clip.metadata.get('source_sha256')!=asset['sha256'] or clip.kind!=('source' if asset['kind']=='video' else 'image') or
            clip.metadata.get('fit') not in {'cover','contain'} or clip.metadata.get('motion') not in {'none','zoom_in','pan_left','pan_right'} or
            clip.source_start<0 or clip.duration<.05 or clip.timeline_start+clip.duration>snapshot.duration_seconds+1e-6):
            raise WorkflowError('NARRATED_VIDEO_SOURCE_BINDING_CHANGED')
        if asset['kind']=='video' and (clip.source_end is None or clip.source_end>asset['duration_seconds']+1e-6 or
            abs((clip.source_end-clip.source_start)/clip.speed-clip.duration)>1e-6):raise WorkflowError('NARRATED_VIDEO_SOURCE_WINDOW_INVALID')
        if asset['kind']=='image' and (clip.source_start!=0 or clip.source_end is not None or clip.speed!=1):
            raise WorkflowError('NARRATED_IMAGE_SOURCE_CLOCK_INVALID')

def reflow_captions(document,snapshot):
    from .source_caption_mapping import reflow,human_layout
    for i,t in enumerate(snapshot.tracks):
        if t.type=='text' and t.kind=='subtitles' and any(c.metadata.get('source_video_mapping') for c in t.clips):
            changed=reflow(document,snapshot,t,manual=human_layout(snapshot,t))
            if t.locked and changed.model_dump(mode='json')!=t.model_dump(mode='json'):raise WorkflowError('NARRATED_VIDEO_CAPTION_TRACK_LOCKED',400)
            snapshot.tracks[i]=changed
    return snapshot

def coverage(document):
    """Actual canonical visuals, independent from titles/narration scene slots."""
    snapshot=document['canonical_timeline']['snapshot'];primary=next(t for t in snapshot['tracks'] if t['track_id']=='trk_native_video')
    clips=[] if primary['disabled'] else [c for c in primary['clips'] if not c['disabled'] and c['opacity']>0]
    intervals=sorted((c['timeline_start'],c['timeline_start']+c['duration']) for c in clips);cursor=0.;gaps=[]
    for a,b in intervals:
        if a>cursor+1/30:gaps.append({'start':cursor,'end':a})
        cursor=max(cursor,b)
    if cursor<snapshot['duration_seconds']-1/30:gaps.append({'start':cursor,'end':snapshot['duration_seconds']})
    return {'status':'failed' if gaps else 'passed','basis':'canonical_visual_clips','missing_visual_intervals':gaps,
        'active_visual_count':len(clips),'duration_seconds':snapshot['duration_seconds'],
        'intentional_still_intervals':[{'start':c['timeline_start'],'end':c['timeline_start']+c['duration'],'asset_id':c['asset_id']} for c in clips if c['kind']=='image']}
