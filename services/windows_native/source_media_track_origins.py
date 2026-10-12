"""Immutable upload/ASR provenance remains checked through edits and rendering."""
import copy,re
from types import SimpleNamespace
from .contracts import WorkflowError,digest
from .source_assets import canonical_assets
from .media import _verify_library_record

SCHEMA='native-source-media-import-v1'
LIMIT=200

def binding(asset):
    return {k:asset.get(k) for k in ('id','kind','canonical_role','sha256','source_sha256','source_mime','duration_seconds')}

def records(document):
    values=document.get('source_media_track_imports',[])
    if not isinstance(values,list) or len(values)>LIMIT:raise WorkflowError('SOURCE_MEDIA_IMPORT_HISTORY_INVALID')
    output={}
    for row in values:
        if (not isinstance(row,dict) or row.get('schema_version')!=SCHEMA or
            not re.fullmatch(r'smi_[a-f0-9]{24}',str(row.get('import_id',''))) or row['import_id'] in output or
            row.get('operation') not in {'audio','subtitles'} or row.get('sha256')!=digest({k:v for k,v in row.items() if k!='sha256'}) or
            row.get('request_sha256')!=digest(row.get('request')) or not isinstance(row.get('result'),dict)):
            raise WorkflowError('SOURCE_MEDIA_IMPORT_HISTORY_INVALID')
        output[row['import_id']]=row
    return output

def validate_timeline(document):
    rows=records(document);snapshot=(document.get('canonical_timeline') or {}).get('snapshot',{})
    assets={v['id']:v for v in canonical_assets(document)};checked_transcripts=set();mapping_cache={}
    for track in snapshot.get('tracks',[]):
        for clip in track['clips']:
            metadata=clip['metadata'];identifier=metadata.get('native_media_import_id')
            if identifier is None:continue
            row=rows.get(identifier);asset=assets.get(metadata.get('native_asset_id'))
            if (row is None or row['project_id']!=snapshot['metadata'].get('native_project_id') or asset is None or
                digest(binding(asset))!=row.get('asset_binding_sha256') or row['asset_id']!=asset['id'] or
                metadata.get('source_checksum_sha256')!=asset['sha256'] or metadata.get('native_media_import_sha256')!=row['sha256']):
                raise WorkflowError('SOURCE_MEDIA_IMPORT_SOURCE_CHANGED')
            if clip['kind']=='subtitle':
                if track['type']!='text' or track['kind']!='subtitles' or clip['asset_id'] is not None:
                    raise WorkflowError('SOURCE_MEDIA_IMPORT_CAPTION_INVALID')
                if row['operation']=='subtitles' and (asset['kind']!='subtitle' or digest(asset.get('cues'))!=row.get('cue_source_sha256')):
                    raise WorkflowError('SOURCE_MEDIA_IMPORT_CAPTION_SOURCE_CHANGED')
                if row.get('source_video_reference'):
                    from .source_caption_mapping import validate
                    validate(document,row,clip,snapshot,cache=mapping_cache)
                if row['operation']=='audio' and not row.get('transcript_reference'):
                    raise WorkflowError('SOURCE_MEDIA_IMPORT_TRANSCRIPT_REQUIRED')
                if row['operation']=='audio' and identifier not in checked_transcripts:
                    from .audio_transcripts import original,selected
                    selected(document,asset)
                    base=original(document,asset);reference=row['transcript_reference']
                    history=[base.model_dump(mode='json') if base else None,*document.get('audio_transcript_versions',[])]
                    if base is None or not any(v==reference for v in history):
                        raise WorkflowError('SOURCE_MEDIA_IMPORT_TRANSCRIPT_CHANGED')
                    checked_transcripts.add(identifier)
            elif (row['operation']!='audio' or track['type']!='audio' or clip['kind'] not in {'voice','music','sfx'} or asset['kind']!='audio'
                or not isinstance(row.get('request'),dict) or track['kind']!=clip['kind'] or row['request'].get('role')!=clip['kind']):
                raise WorkflowError('SOURCE_MEDIA_IMPORT_AUDIO_INVALID')
            elif metadata.get('source_audio_waveform')!=row.get('waveform'):
                raise WorkflowError('SOURCE_MEDIA_IMPORT_WAVEFORM_CHANGED')

def verify_physical(root,document):
    validate_timeline(document);rows=records(document);assets={v['id']:v for v in canonical_assets(document)}
    snapshot=(document.get('canonical_timeline') or {}).get('snapshot',{})
    used={clip['metadata']['native_media_import_id'] for track in snapshot.get('tracks',[]) if not track['disabled']
        for clip in track['clips'] if not clip['disabled'] and 'native_media_import_id' in clip['metadata'] and
        (track['type']!='audio' or not track['muted'] and clip['volume']>0)}
    verified={}
    for identity in used:
        row=rows[identity];asset=assets[row['asset_id']]
        path=_verify_library_record(SimpleNamespace(root=root),{'metadata':asset,'metadata_conflict':False})
        if row['operation']=='subtitles':
            from .multipart_ingestion import subtitle_cues,CHUNK_BYTES
            if path.stat().st_size>CHUNK_BYTES or digest(subtitle_cues(path.read_bytes(),asset['source_mime']))!=row['cue_source_sha256']:
                raise WorkflowError('SOURCE_MEDIA_IMPORT_CAPTION_BYTES_CHANGED')
        verified[asset['id']]=asset['sha256']
        if row.get('source_video_reference'):
            from .source_caption_mapping import verify_reference
            video=verify_reference(document,row['source_video_reference'],root=root);verified[video['id']]=video['sha256']
    return verified

def inherit(document,source_id,target_id,revision):
    """Copies keep the original record as lineage, without replay authority."""
    rows=records(document);changed=[];mapping={}
    if not rows:return
    for row in rows.values():
        if row['project_id']!=source_id:raise WorkflowError('SOURCE_MEDIA_IMPORT_SCOPE_INVALID')
        new={k:copy.deepcopy(v) for k,v in row.items() if k!='sha256'}
        new.update(import_id='smi_'+digest([target_id,row['import_id']])[:24],project_id=target_id,request_key_sha256=None,
            inherited_original={'source_project_id':source_id,'source_revision':revision,'record':copy.deepcopy(row),
                'record_sha256':digest(row),'request_replay_authority_transferred':False})
        new['sha256']=digest(new);changed.append(new);mapping[row['import_id']]=new
    document['source_media_track_imports']=changed
    for track in document['canonical_timeline']['snapshot']['tracks']:
        for clip in track['clips']:
            meta=clip['metadata'];new=mapping.get(meta.get('native_media_import_id'))
            if new:meta.update(native_media_import_id=new['import_id'],native_media_import_sha256=new['sha256'])
    if any(r.get('source_video_reference') for r in changed):
        from app.timeline_models import TimelineSnapshot
        from .source_caption_mapping import reflow,human_layout
        snapshot=TimelineSnapshot.model_validate(document['canonical_timeline']['snapshot'])
        for index,track in enumerate(snapshot.tracks):
            if track.type=='text' and track.kind=='subtitles':
                snapshot.tracks[index]=reflow(document,snapshot,track,manual=human_layout(snapshot,track))
        document['canonical_timeline']['snapshot']=snapshot.model_dump(mode='json')
