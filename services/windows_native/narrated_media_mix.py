"""Actual canonical audio graph for opt-in storyboard media tracks."""
from datetime import datetime,timezone
import copy,json,shutil,subprocess
from pathlib import Path
from .contracts import WorkflowError,digest,file_sha,write_json
from .backup import guard
from .narrated_media_timeline import enabled,reference
from .source_assets import canonical_assets
from .source_media_track_origins import records,verify_physical
from .auto_edit_analysis import asset_reference
from .media import media_path
from app.timeline_models import TimelineSnapshot
from app.platform_models import AssetRead
from app.timeline_audio_processing import build_processed_audio_graph

def verify(config,document,*,store=None,con=None):
    if not enabled(document):return None
    from .shot_adapter import validate_document
    from .narration import load_reference
    from .store import Store
    validate_document(document);store=store or Store(config.data_root);project_id=document['canonical_timeline']['snapshot']['metadata']['native_project_id']
    if con is None:
        with store.transaction() as current:_,_,result=load_reference(store,current,project_id,document)
    else:_,_,result=load_reference(store,con,project_id,document)
    plan=document['canonical_timeline']['snapshot']['metadata']['narrated_caption_source_plan']
    if (plan['sha256']!=result['plan_sha256'] or plan['items_sha256']!=digest(result['plan']['items']) or
        plan['items']!=result['plan']['items']):raise WorkflowError('NARRATED_MEDIA_CAPTION_SOURCE_CHANGED')
    return verify_physical(config.data_root,document)

def prepare(config,document,directory,voice_file,gain):
    verified=verify(config,document)
    if verified is None:return None
    snapshot=TimelineSnapshot.model_validate(document['canonical_timeline']['snapshot']);assets={};now=datetime.now(timezone.utc)
    media=directory/'media';media.mkdir(exist_ok=False);ref=reference(document)
    active=[c for t in snapshot.tracks if t.type=='audio' and not t.disabled and not t.muted for c in t.clips if not c.disabled and c.volume>0]
    needed={c.asset_id for c in active}
    generated=ref['asset_id'] in needed
    def register(identifier,path,sha,provenance):
        target=media/(identifier+path.suffix.lower())
        if path!=target:shutil.copyfile(path,target)
        if file_sha(target)!=sha:raise WorkflowError('NARRATED_MEDIA_SOURCE_CHANGED_DURING_COPY')
        dto=AssetRead(asset_id=identifier,workspace_id='native-local',project_id='prj_'+snapshot.metadata['native_project_id'],project_version_id=None,job_id=None,
            asset_class='source',kind='audio',filename=target.name,object_key='media/'+target.name,content_type='audio/wav',size_bytes=target.stat().st_size,
            checksum_sha256=sha,storage_provider='native-local',version=1,provenance=provenance,created_at=now,updated_at=now)
        assets[identifier]=(dto,target)
    source_voice=guard(directory/voice_file,exists=True)
    normalized_sha=None
    if generated:
        target=media/(ref['asset_id']+'.wav')
        command=[str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-i',str(source_voice),'-af',f'volume={gain:.8f}',
            '-ar','48000','-ac','1','-c:a','pcm_s16le',str(target)]
        run(config,command,directory,'narrated-reference-gain.log')
        normalized_sha=file_sha(target)
        register(ref['asset_id'],target,normalized_sha,{'verified_prepared_narration_reference':ref,'placed_source_sha256':file_sha(source_voice),
            'legacy_rms_peak_gain':gain,'new_inference_calls':0,'rights_status':'unknown'})
    for item in canonical_assets(document):
        identifier=asset_reference(item)
        if identifier not in needed:continue
        path=guard(media_path(config,item['id']),exists=True)
        if item['kind']!='audio' or item.get('rights_confirmed') is not True or file_sha(path)!=item['sha256']:raise WorkflowError('NARRATED_MEDIA_AUDIO_ASSET_CHANGED')
        register(identifier,path,item['sha256'],{'native_asset_id':item['id'],'rights_status':item.get('rights_status','unknown')})
    if set(assets)!=needed:raise WorkflowError('NARRATED_MEDIA_AUDIO_ASSET_UNAVAILABLE')
    graph=build_processed_audio_graph(snapshot,assets,first_input_index=0,processing=snapshot.metadata.get('source_audio_processing'),packet_alignment=True)
    filters=directory/'narrated-audio-filter.txt';filters.write_text(';'.join(graph.filters),encoding='utf-8')
    mix=directory/'narrated-mix.wav'
    if graph.clips:
        command=[str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-filter_complex_threads','1',*graph.inputs,'-/filter_complex',str(filters),'-map','[outa]']
    else:command=[str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(snapshot.duration_seconds)]
    run(config,[*command,'-ar','48000','-ac','2','-c:a','pcm_s16le',str(mix)],directory,'narrated-canonical-mix.log')
    manifest={'schema_version':'native-narrated-canonical-audio-v1','document_sha256':digest(document),'timeline_version':document['canonical_timeline']['version'],
        'timeline_sha256':document['canonical_timeline']['sha256'],'duration_seconds':snapshot.duration_seconds,'audio':{'mix_uri':str(mix),'mix_sha256':file_sha(mix)},
        'clips':graph.clips,'processing':graph.processing,'generated_voice_active':generated,'generated_voice_reference':ref,
        'placed_generated_voice_sha256':file_sha(source_voice),'normalized_generated_voice_sha256':normalized_sha,'legacy_generated_voice_gain':gain,
        'source_sha256':{key:asset.checksum_sha256 for key,(asset,path) in assets.items()},'imported_source_sha256':verified,
        'source_PCM_mutated':False,'new_inference_calls':0,'external_provider_calls':0,'human_final_video_accepted':False}
    write_json(directory/'timeline-render.json',manifest)
    from .audio_balance import source_stems
    role=source_stems(config,snapshot,assets,directory,packet_alignment=True)
    write_json(directory/'source-media-imports.json',{'schema_version':'native-render-media-imports-v1','imports':list(records(document).values()),
        'verified_active_source_sha256':verified,'generated_voice_reference':ref,'source_media_mutated':False,'provider_calls':0,'human_review_required':True})
    manifest['reference_role']=role;manifest['audio_filter_sha256']=file_sha(filters)
    write_json(directory/'narrated-media-mix.json',manifest)
    return manifest

def run(config,command,directory,name):
    with (directory/name).open('xb') as log:
        result=subprocess.run(command,cwd=directory,stdout=log,stderr=subprocess.STDOUT,timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0)
    if result.returncode:raise WorkflowError('NARRATED_MEDIA_AUDIO_RENDER_FAILED')

def artifact_names(directory):
    if not (directory/'narrated-media-mix.json').is_file():return ()
    from .narrated_video_render import artifact_names as visual_names
    return ('narrated-media-mix.json','narrated-mix.wav','timeline-render.json','source-media-imports.json','narrated-audio-filter.txt')+visual_names(directory)

def validate_bundle(config,document,directory,*,store=None,con=None):
    if not enabled(document):return
    verify(config,document,store=store,con=con)
    from .narrated_video_render import validate_bundle as validate_video
    validate_video(config,document,directory)
    body=json.loads(guard(directory/'narrated-media-mix.json',exists=True).read_bytes())
    timeline=json.loads(guard(directory/'timeline-render.json',exists=True).read_bytes())
    if (body.get('schema_version')!='native-narrated-canonical-audio-v1' or body.get('document_sha256')!=digest(document) or
        body.get('timeline_sha256')!=document['canonical_timeline']['sha256'] or
        body.get('audio',{}).get('mix_sha256')!=file_sha(guard(directory/'narrated-mix.wav',exists=True)) or
        {k:v for k,v in body.items() if k not in {'reference_role','audio_filter_sha256'}}!=timeline or
        body.get('audio_filter_sha256')!=file_sha(guard(directory/'narrated-audio-filter.txt',exists=True))):raise WorkflowError('NARRATED_MEDIA_MIX_BINDING_CHANGED')
    imports=json.loads(guard(directory/'source-media-imports.json',exists=True).read_bytes())
    if imports.get('imports')!=list(records(document).values()) or imports.get('verified_active_source_sha256')!=verify_physical(config.data_root,document):
        raise WorkflowError('NARRATED_MEDIA_IMPORT_CHECKPOINT_CHANGED')
