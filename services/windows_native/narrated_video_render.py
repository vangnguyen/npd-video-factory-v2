"""Render actual canonical visual windows with existing narrated brand overlays."""
import copy,json,shutil
from pathlib import Path
from types import SimpleNamespace
from .contracts import WorkflowError,digest,file_sha,write_json
from .media import media_path
from .narrated_video_timeline import enabled,coverage
from .source_render import command_run
from app.timeline_models import TimelineSnapshot
from app.production_logic import build_timeline_render_manifest
from app.production_models import SubtitleVersionRead,SubtitleStyle,MixConfig

REPO=Path(__file__).resolve().parents[2]
FILES=('narrated-video.mp4','narrated-video-render.json','narrated-video-receipt.json')

def artifact_names(directory):
    if not (directory/'narrated-video-render.json').is_file():return ()
    record=json.loads((directory/'narrated-video-render.json').read_bytes())
    names=tuple(record.get('header_sha256',{}))
    if any(not name.startswith('narrated-video-overlays/scene-') or Path(name).suffix!='.png' or '..' in Path(name).parts for name in names):
        raise WorkflowError('NARRATED_VIDEO_OVERLAY_SCOPE_INVALID')
    return FILES+names

def content_type(asset,path):
    # Native ingest retains the original MIME separately; normalized legacy
    # image/video records may omit it. Identify the registered render bytes.
    with path.open('rb') as source:header=source.read(32)
    if asset['kind']=='image':
        from PIL import Image
        with Image.open(path) as image:
            mime={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}.get(image.format);image.verify()
        if mime:return mime
    elif asset['kind']=='video':
        if header[4:8]==b'ftyp':return 'video/quicktime' if header[8:12]==b'qt  ' else 'video/mp4'
        if header[:4]==b'\x1a\x45\xdf\xa3':return 'video/webm'
    raise WorkflowError('NARRATED_VIDEO_SOURCE_FORMAT_INVALID')

def motion_keyframes(clip,original):
    motion=original.metadata.get('motion','none')
    if clip['type']!='image' or motion=='none' or 'crop_keyframes' in clip:return
    start=copy.deepcopy(clip['crop']);end=copy.deepcopy(start)
    if motion=='zoom_in':
        end.update(width=start['width']/1.08,height=start['height']/1.08,x=start['x']+start['width']*(1-1/1.08)/2,y=start['y']+start['height']*(1-1/1.08)/2)
    else:
        start.update(width=start['width']/1.06,height=start['height']/1.06,y=start['y']+start['height']*(1-1/1.06)/2)
        end=copy.deepcopy(start);delta=clip['crop']['width']*(1-1/1.06)
        if motion=='pan_left':start['x']+=delta
        else:end['x']+=delta
    clip['crop_keyframes']=[{'time':0,**start},{'time':clip['duration'],**end}]

def render(config,document,directory,frames,geometry,brand):
    canonical=document['canonical_timeline'];snapshot=TimelineSnapshot.model_validate(canonical['snapshot'])
    if not enabled(snapshot):raise WorkflowError('NARRATED_VIDEO_SCHEMA_REQUIRED')
    if coverage(document)['status']!='passed':raise WorkflowError('NARRATED_VIDEO_VISUAL_GAPS_REVIEW_REQUIRED')
    child=directory/'canonical-visual';media=child/'media';media.mkdir(parents=True)
    from .source_assets import canonical_assets
    registered={v['id']:v for v in canonical_assets(document)};assets={};sources={}
    primary=next(t for t in snapshot.tracks if t.track_id=='trk_native_video');visual=snapshot.model_copy(deep=True)
    visual.tracks=[primary.model_copy(deep=True)]
    for clip in primary.clips:
        if clip.disabled or clip.opacity<=0 or primary.disabled:continue
        asset=registered.get(clip.metadata.get('native_asset_id'))
        if not asset or asset.get('rights_confirmed') is not True:raise WorkflowError('NARRATED_VIDEO_SOURCE_UNAVAILABLE_OR_UNREVIEWED')
        path=media_path(config,asset['id'])
        if file_sha(path)!=asset['sha256']:raise WorkflowError('NARRATED_VIDEO_SOURCE_CHANGED')
        mime=content_type(asset,path)
        target=media/(clip.asset_id+{'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','video/mp4':'.mp4','video/quicktime':'.mov','video/webm':'.webm'}[mime])
        if not target.exists():shutil.copyfile(path,target)
        if file_sha(target)!=asset['sha256']:raise WorkflowError('NARRATED_VIDEO_SOURCE_CHANGED')
        assets[clip.asset_id]=(SimpleNamespace(asset_id=clip.asset_id,content_type=mime,provenance={'rights_status':asset.get('rights_status','unknown')}),target)
        sources[asset['id']]=asset['sha256']
    mix=media/'mix.wav';shutil.copyfile(directory/'narrated-mix.wav',mix)
    # Empty subtitle layer: existing measured ASS captions are applied once by
    # the narrated final mux, with its certified font/layout/QC path.
    subtitles=SubtitleVersionRead(subtitle_version_id='sub_narrated_visual_only',package_id='pkg_'+snapshot.metadata['native_project_id'],
        project_id='prj_'+snapshot.metadata['native_project_id'],timeline_version_id='tlv_narrated_visual_only',timeline_version=canonical['version'],
        version=1,cues=[],style=SubtitleStyle.model_validate(snapshot.metadata['subtitle_style']),actor_ref='native-session-owner',
        created_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc))
    profile={(1080,1920):'vertical-1080x1920',(1920,1080):'landscape-1920x1080',(1080,1080):'square-1080x1080',(1080,1350):'portrait-1080x1350'}[(snapshot.width,snapshot.height)]
    manifest=build_timeline_render_manifest(snapshot=visual,subtitles=subtitles,mix_config=MixConfig(),mixed_audio_path=mix,asset_paths=assets,
        profile=profile,project_name=document['name'],project_slug=snapshot.metadata['native_project_id'],niche=document.get('niche','custom'),brand_name=brand.name)
    if manifest['version']!='2.4':manifest['version']='2.3'
    viewport={'x':0,'y':geometry['media_top']/snapshot.height,'width':1,'height':geometry['plane_height']/snapshot.height}
    for clip in manifest['visual_clips']:
        clip['viewport']=viewport
        original=next(c for c in primary.clips if c.clip_id==clip['clip_id'])
        motion_keyframes(clip,original)
    overlays={};overlay_dir=directory/'narrated-video-overlays';overlay_dir.mkdir()
    for frame in frames:
        source=directory/frame['header_file'];target=media/source.name;shutil.copyfile(source,target)
        retained=overlay_dir/source.name;shutil.copyfile(source,retained);overlays[retained.relative_to(directory).as_posix()]=file_sha(retained)
        manifest['visual_clips'].append({'clip_id':'clip_brand_'+str(frame['scene']).zfill(4),'track_order':primary.order+1,'type':'image','uri':str(target),
            'timeline_start':frame['start'],'duration':frame['end']-frame['start'],'source_start':0,'source_end':None,'fit':'contain',
            'crop':{'x':0,'y':0,'width':1,'height':1},'transform':{'x':0,'y':0,'scale':1,'rotation_degrees':0},'opacity':1})
    write_json(child/'timeline-render.json',manifest)
    from .export_encoder import write as write_export_encoder
    write_export_encoder(document,child)
    manifest_file_sha=file_sha(child/'timeline-render.json')
    node=Path(getattr(config,'node_executable',r'C:\Program Files\nodejs\node.exe'));tsx=REPO/'renderer/node_modules/tsx/dist/cli.mjs'
    if not node.is_file() or not tsx.is_file():raise WorkflowError('NARRATED_VIDEO_RENDERER_NOT_CONFIGURED')
    command_run([str(node),str(tsx),str(REPO/'renderer/src/native-job-cli.ts'),str(child)],child,'renderer.log',max(180,min(1800,snapshot.duration_seconds*12)),'NARRATED_VIDEO_RENDER_FAILED')
    if file_sha(child/'timeline-render.json')!=manifest_file_sha:raise WorkflowError('NARRATED_VIDEO_MANIFEST_CHANGED')
    shutil.copyfile(child/'final.mp4',directory/'narrated-video.mp4');shutil.copyfile(child/'renderer-receipt.json',directory/'narrated-video-receipt.json')
    for identifier,sha in sources.items():
        if file_sha(media_path(config,identifier))!=sha:raise WorkflowError('NARRATED_VIDEO_SOURCE_CHANGED')
    record={'schema_version':'native-narrated-canonical-video-render-v1','document_sha256':digest(document),'timeline_sha256':canonical['sha256'],
        'manifest':manifest,'manifest_sha256':digest(manifest),'source_sha256':sources,'header_sha256':overlays,'mix_sha256':file_sha(mix),
        'video_sha256':file_sha(directory/'narrated-video.mp4'),'renderer_receipt_sha256':file_sha(directory/'narrated-video-receipt.json'),
        'actual_canonical_visual_windows':True,'narration_timing_changed':False,'new_provider_calls':0,'human_final_video_accepted':False}
    write_json(directory/'narrated-video-render.json',record)
    return record

def validate_bundle(config,document,directory):
    if not enabled(document['canonical_timeline']['snapshot']):return
    from .backup import guard
    data=json.loads(guard(directory/'narrated-video-render.json',exists=True).read_bytes())
    if (data.get('schema_version')!='native-narrated-canonical-video-render-v1' or data.get('document_sha256')!=digest(document) or
        data.get('timeline_sha256')!=document['canonical_timeline']['sha256'] or data.get('manifest_sha256')!=digest(data.get('manifest')) or
        data.get('video_sha256')!=file_sha(guard(directory/'narrated-video.mp4',exists=True)) or
        data.get('renderer_receipt_sha256')!=file_sha(guard(directory/'narrated-video-receipt.json',exists=True)) or
        data.get('mix_sha256')!=file_sha(guard(directory/'narrated-mix.wav',exists=True))):raise WorkflowError('NARRATED_VIDEO_RENDER_BINDING_CHANGED')
    snapshot=TimelineSnapshot.model_validate(document['canonical_timeline']['snapshot']);primary=next(t for t in snapshot.tracks if t.track_id=='trk_native_video')
    from .source_assets import canonical_assets
    from .branding import validate_assets,resolve
    from .narrated_layout import layout
    from .north_star_quality import validate_render_profile
    from .narrated_video_timeline import semantic_shots
    brand=validate_assets(config,document);_,template=resolve(document)
    default={(1080,1920):'vertical-short',(1920,1080):'landscape',(1080,1080):'square',(1080,1350):'portrait-feed'}[(snapshot.width,snapshot.height)]
    profile=validate_render_profile(document.get('render_profile',default),snapshot.width,snapshot.height,template.aspect_ratio if template else '9:16')
    geometry=layout(profile['id'],snapshot.width,snapshot.height,profile['aspect_ratio'],brand,editable=bool(document.get('edit_plan')))
    viewport={'x':0,'y':geometry['media_top']/snapshot.height,'width':1,'height':geometry['plane_height']/snapshot.height}
    registered={a['id']:a for a in canonical_assets(document)};expected=[];sources={}
    styled=any(c.effects or c.metadata.get('clip_style_schema')=='clip-style-v1' for c in primary.clips if not primary.disabled and not c.disabled)
    for clip in sorted(primary.clips,key=lambda c:(c.timeline_start,c.clip_id)):
        if primary.disabled or clip.disabled or clip.opacity<=0:continue
        asset=registered[clip.metadata['native_asset_id']];sources[asset['id']]=asset['sha256']
        item={'clip_id':clip.clip_id,'track_order':primary.order,'type':asset['kind'],'timeline_start':clip.timeline_start,
            'duration':clip.duration,'source_start':0 if clip.kind=='image' else clip.source_start,'source_end':None if clip.kind=='image' else clip.source_end,
            'fit':clip.metadata['fit'],'crop':clip.crop.model_dump(mode='json'),'transform':clip.transform.model_dump(mode='json'),
            'opacity':clip.opacity,'viewport':viewport}
        if snapshot.schema_version=='1.1':item['transition_in']=clip.transition_in.model_dump(mode='json')
        if styled:
            from app.production_logic import render_visual_effects
            item.update(transition_in=clip.transition_in.model_dump(mode='json'),transition_out=clip.transition_out.model_dump(mode='json'),effects=render_visual_effects(clip.effects))
        if clip.metadata.get('reframe'):item['crop_keyframes']=clip.metadata['reframe']['keyframes']
        motion_keyframes(item,clip);expected.append(item)
    cursor=0.;headers={}
    for i,shot in enumerate(semantic_shots(snapshot),1):
        start=round(cursor*30)/30;cursor+=shot['duration'];end=round(cursor*30)/30
        name='narrated-video-overlays/scene-'+str(i-1).zfill(2)+'.png';headers[name]=data.get('header_sha256',{}).get(name)
        expected.append({'clip_id':'clip_brand_'+str(i).zfill(4),'track_order':primary.order+1,'type':'image','timeline_start':start,'duration':end-start,
            'source_start':0,'source_end':None,'fit':'contain','crop':{'x':0,'y':0,'width':1,'height':1},
            'transform':{'x':0,'y':0,'scale':1,'rotation_degrees':0},'opacity':1})
    manifest=data['manifest'];actual=[{k:v for k,v in c.items() if k!='uri'} for c in manifest.get('visual_clips',[])]
    if (manifest.get('version')!=('2.4' if styled else '2.3') or actual!=expected or data.get('source_sha256')!=sources or data.get('header_sha256')!=headers or
        manifest.get('safety')!={'human_approval_required':True,'publishing_allowed':False,'external_publish_requested':False,'source_media_mutated':False} or
        any(manifest.get('metadata',{}).get(k)!=v for k,v in {'width':snapshot.width,'height':snapshot.height,'fps':round(snapshot.fps),'duration_seconds':snapshot.duration_seconds}.items())):
        raise WorkflowError('NARRATED_VIDEO_CANONICAL_RENDER_CHANGED')
    receipt=json.loads(guard(directory/'narrated-video-receipt.json',exists=True).read_bytes())
    if any(receipt.get(k)!=v for k,v in {'status':'success','renderer':'remotion-local-native-job-v1','fixture':False,
            'duration_seconds':snapshot.duration_seconds,'width':snapshot.width,'height':snapshot.height,'fps':round(snapshot.fps),
            'private_job_media_only':True,'external_publish_requested':False,'human_final_video_accepted':False}.items()):
        raise WorkflowError('NARRATED_VIDEO_RENDERER_RECEIPT_CHANGED')
    for name,sha in headers.items():
        if file_sha(guard(directory/name,exists=True))!=sha:raise WorkflowError('NARRATED_VIDEO_OVERLAY_CHANGED')
    for identifier,sha in sources.items():
        if file_sha(media_path(config,identifier))!=sha:raise WorkflowError('NARRATED_VIDEO_SOURCE_CHANGED')
