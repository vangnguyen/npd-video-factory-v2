"""Explicit SRT/video clocks over actual canonical source windows, no inference."""
import copy,math,re
from types import SimpleNamespace
from .contracts import WorkflowError,digest
from .source_assets import canonical_assets
from .source_media_track_origins import binding

SCHEMA='native-source-video-caption-mapping-v1'
FIELDS=('clip_id','asset_id','source_start','source_end','timeline_start','duration','speed')

def video_assets(document,snapshot):
    used={c.metadata.get('native_asset_id') for t in snapshot.tracks if t.type=='video' and t.kind=='source' and not t.disabled
        for c in t.clips if c.kind=='source' and not c.disabled}
    return [v for v in canonical_assets(document) if v['kind']=='video' and v['id'] in used]

def reference(document,snapshot,identifier,sha):
    video=next((v for v in video_assets(document,snapshot) if v['id']==identifier),None)
    if video is None or video['sha256']!=sha:raise WorkflowError('SOURCE_CAPTION_VIDEO_BINDING_CHANGED',400)
    return {'schema_version':SCHEMA,'asset_id':identifier,'asset_sha256':sha,'asset_binding_sha256':digest(binding(video))}

def verify_reference(document,ref,*,root=None):
    if not isinstance(ref,dict) or set(ref)!={'schema_version','asset_id','asset_sha256','asset_binding_sha256'} or ref['schema_version']!=SCHEMA:
        raise WorkflowError('SOURCE_CAPTION_VIDEO_REFERENCE_INVALID')
    video=next((v for v in canonical_assets(document) if v['id']==ref['asset_id']),None)
    if video is None or video['kind']!='video' or video['sha256']!=ref['asset_sha256'] or digest(binding(video))!=ref['asset_binding_sha256']:
        raise WorkflowError('SOURCE_CAPTION_VIDEO_BINDING_CHANGED')
    if root is not None:
        from .media import _verify_library_record
        _verify_library_record(SimpleNamespace(root=root),{'metadata':video,'metadata_conflict':False})
    return video

def clips(snapshot,cues,ref,import_id,subtitle_asset,request):
    from .source_media_tracks import _caption
    windows=[c for t in snapshot.tracks if t.type=='video' and t.kind=='source' and not t.disabled for c in t.clips
        if c.kind=='source' and not c.disabled and c.metadata.get('native_asset_id')==ref['asset_id']]
    output=[];clipped=dropped=0
    for ordinal,cue in enumerate(cues):
        intersected=False
        for c in windows:
            sa=max(cue['start'],c.source_start);sb=min(cue['end'],c.source_end)
            if sb-sa<.000001:continue
            intersected=True
            a=c.timeline_start+(sa-c.source_start)/c.speed+request['offset_seconds'];b=c.timeline_start+(sb-c.source_start)/c.speed+request['offset_seconds']
            if a<0 or b>snapshot.duration_seconds:
                if not request['trim_to_timeline']:raise WorkflowError('SOURCE_MEDIA_TRACK_CAPTION_OUT_OF_BOUNDS',400)
                left=max(0,a);right=min(snapshot.duration_seconds,b);clipped+=1
                sa+=(left-a)*c.speed;sb-=(b-right)*c.speed;a,b=left,right
            if b-a<.05:dropped+=1;continue
            meta={'native_media_import_id':import_id,'native_asset_id':subtitle_asset['id'],'source_checksum_sha256':subtitle_asset['sha256'],
                'cue_ordinal':ordinal,'cue_source_sha256':digest(cue),'timing_source':'explicit_source_video_cue_mapping_no_word_alignment',
                'timebase':'source','mapped_from_source':True,'source_media_mutated':False,'source_video_mapping':{
                    'schema_version':SCHEMA,'video_reference':copy.deepcopy(ref),'video_clip':{k:float(getattr(c,k)) if k not in {'clip_id','asset_id'} else getattr(c,k) for k in FIELDS},
                    'source_interval':[round(sa,6),round(sb,6)],'timeline_interval':[round(a,6),round(b,6)]}}
            cue_clip=_caption(cue['text'],a,b,sa,sb,meta);cue_clip.speed=c.speed
            cue_clip.clip_id='clip_'+digest([SCHEMA,import_id,ordinal,c.clip_id])[:24];output.append(cue_clip)
            if len(output)>2000:raise WorkflowError('AUTO_EDIT_TIMELINE_LIMIT',400)
        if not intersected:dropped+=1
    output.sort(key=lambda c:(c.timeline_start,c.clip_id))
    return output,{'caption_count':len(output),'source_cue_count':len(cues),'clipped_intervals':clipped,'dropped_intervals':dropped,'timebase':'source',
        'source_video_asset_id':ref['asset_id'],'source_video_asset_sha256':ref['asset_sha256'],'mapping_schema':SCHEMA}

def reflow(document,snapshot,track,*,manual=False):
    """Derived placements follow video; explicit human layout stays reviewable."""
    mapped=[c for c in track.clips if c.metadata.get('source_video_mapping')]
    if not mapped:return track
    if track.disabled or manual or any(c.metadata.get('human_caption_edit') for c in track.clips):return track
    identifiers={c.metadata['native_media_import_id'] for c in mapped}
    if len(identifiers)!=1 or len(mapped)!=len(track.clips):raise WorkflowError('SOURCE_CAPTION_MAPPING_TRACK_MIX_REVIEW_REQUIRED',400)
    from .source_media_track_origins import records
    row=records(document).get(next(iter(identifiers)));ref=row.get('source_video_reference') if row else None
    verify_reference(document,ref);subtitle=next(v for v in canonical_assets(document) if v['id']==row['asset_id'])
    result,_=clips(snapshot,subtitle['cues'],ref,row['import_id'],subtitle,row['request'])
    if not result:raise WorkflowError('SOURCE_CAPTION_MAPPING_NO_VIDEO_REVIEW_REQUIRED',400)
    for clip in result:clip.metadata['native_media_import_sha256']=row['sha256']
    new=track.model_copy(deep=True);new.clips=result
    return new

def validate(document,row,clip,snapshot,*,cache=None):
    ref=row.get('source_video_reference');verify_reference(document,ref)
    meta=clip['metadata'];mapping=meta.get('source_video_mapping')
    if not isinstance(mapping,dict) or set(mapping)!={'schema_version','video_reference','video_clip','source_interval','timeline_interval'} or mapping.get('schema_version')!=SCHEMA or mapping.get('video_reference')!=ref:
        raise WorkflowError('SOURCE_CAPTION_MAPPING_REFERENCE_CHANGED')
    cue_asset=next(v for v in canonical_assets(document) if v['id']==row['asset_id']);ordinal=meta.get('cue_ordinal')
    if type(ordinal) is not int or not 0<=ordinal<len(cue_asset['cues']) or meta.get('cue_source_sha256')!=digest(cue_asset['cues'][ordinal]):
        raise WorkflowError('SOURCE_CAPTION_MAPPING_CUE_CHANGED')
    window=mapping['video_clip'];video=verify_reference(document,ref)
    if not isinstance(window,dict) or set(window)!=set(FIELDS) or not re.fullmatch(r'clip_[A-Za-z0-9_-]{4,60}',str(window.get('clip_id',''))) or not re.fullmatch(r'ast_[A-Za-z0-9_-]{4,64}',str(window.get('asset_id',''))):
        raise WorkflowError('SOURCE_CAPTION_MAPPING_WINDOW_INVALID')
    for key in ('source_start','source_end','timeline_start','duration','speed'):
        if type(window[key]) not in (int,float) or not math.isfinite(window[key]):raise WorkflowError('SOURCE_CAPTION_MAPPING_WINDOW_INVALID')
    if window['asset_id']!='ast_'+digest(video['id'])[:32] or not 0<=window['source_start']<window['source_end']<=video['duration_seconds']+.000001 or not .000001<window['speed']<=8 or window['duration']<=0 or window['timeline_start']<0 or abs(window['duration']-(window['source_end']-window['source_start'])/window['speed'])>.00001:
        raise WorkflowError('SOURCE_CAPTION_MAPPING_WINDOW_INVALID')
    for key in ('source_interval','timeline_interval'):
        interval=mapping[key]
        if not isinstance(interval,list) or len(interval)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in interval) or not 0<=interval[0]<interval[1]<=600.000001:
            raise WorkflowError('SOURCE_CAPTION_MAPPING_WINDOW_INVALID')
    sa,sb=mapping['source_interval'];cue=cue_asset['cues'][ordinal]
    if sa<max(cue['start'],window['source_start'])-.000001 or sb>min(cue['end'],window['source_end'])+.000001:
        raise WorkflowError('SOURCE_CAPTION_MAPPING_CUE_INTERVAL_INVALID')
    a,b=mapping['timeline_interval'];offset=row['request']['offset_seconds']
    if abs(a-(window['timeline_start']+(sa-window['source_start'])/window['speed']+offset))>.00001 or abs(b-(window['timeline_start']+(sb-window['source_start'])/window['speed']+offset))>.00001:
        raise WorkflowError('SOURCE_CAPTION_MAPPING_CLOCK_INVALID')
    # Human overrides are explicit canonical decisions; retain their original
    # source/video evidence without claiming that new timing follows the video.
    track=next(t for t in snapshot['tracks'] if any(c['clip_id']==clip['clip_id'] for c in t['clips']))
    overridden=track['disabled'] or clip['disabled'] or track['track_id'] in snapshot['metadata'].get('narrated_caption_edited_tracks',[]) or any(c['metadata'].get('human_caption_edit') for c in track['clips'])
    if overridden:return
    from app.timeline_models import TimelineSnapshot
    cache={} if cache is None else cache
    if row['import_id'] not in cache:
        expected,_=clips(TimelineSnapshot.model_validate(snapshot),cue_asset['cues'],ref,row['import_id'],cue_asset,row['request'])
        cache[row['import_id']]={c.clip_id:c for c in expected}
    found=cache[row['import_id']].get(clip['clip_id'])
    if found is None or mapping!=found.metadata['source_video_mapping'] or any(clip[k]!=getattr(found,k) for k in ('timeline_start','duration','source_start','source_end','speed')):
        raise WorkflowError('SOURCE_CAPTION_MAPPING_VIDEO_WINDOW_CHANGED')
