"""Full local storyboard QC, including actual libass subtitle-mask bounds.

Only new quality-policy renders use this consumer. Existing reports/checkpoints
remain readable and are never upgraded by assertion or rewritten in place.
"""
import asyncio,io,json,math,subprocess,time
from PIL import Image
from .backup import guard
from .contracts import WorkflowError,digest,file_sha,write_json
from .media import verify_selected_files
from app.production_qc import FullProductionQC,ProductionQCError

MAX_CAPTIONS=128

def number(value):return type(value) in (int,float) and math.isfinite(value)

def timeline_evidence(config,document,manifest,duration):
    assets=verify_selected_files(config,document);scenes=manifest.get('scenes');cursor=0.;stills=[]
    if not isinstance(scenes,list) or not 1<=len(scenes)<=20 or any(not isinstance(scene,dict) for scene in scenes):raise WorkflowError('STORYBOARD_QC_SCENE_LAYOUT_INVALID')
    for ordinal,scene in enumerate(scenes,1):
        asset=assets.get(ordinal);start,end=scene.get('start'),scene.get('end');count=scene.get('frames')
        if (asset is None or scene.get('scene')!=ordinal or scene.get('asset_id')!=asset['id'] or scene.get('kind')!=asset['kind'] or scene.get('source_sha256')!=asset['sha256']
            or not number(start) or not number(end) or abs(start-cursor)>.001 or end<=start or end>duration+1/30
            or type(count) is not int or count<=0 or abs(count/30-(end-start))>.001):raise WorkflowError('STORYBOARD_QC_SCENE_LAYOUT_INVALID')
        cursor=end
        # Reuse the shared renderer policy for explicitly planned image intervals.
        # The video kind is never exempt, including loops and constant frames.
        if asset['kind']=='image':stills.append({'start':start,'end':end,'asset_id':asset['id']})
    if abs(cursor-duration)>1/30:raise WorkflowError('STORYBOARD_QC_TIMELINE_DURATION_CHANGED')
    return {'status':'passed','basis':'actual_native_render_manifest_and_registered_source_hashes','duration_seconds':duration,
        'scene_count':len(scenes),'missing_assets':[],'source_sha256':{value['id']:value['sha256'] for value in assets.values()},
        'intentional_still_intervals':stills,'intentional_audio_silence':False,'canonical_timeline':manifest.get('canonical_timeline'),
        'word_alignment_claimed':False,'semantic_vision_used':False}

def subtitle_evidence(config,directory,manifest,duration,width,height):
    layout=manifest.get('subtitle_layout');captions=manifest.get('captions');source=guard(directory/'subtitles.ass',exists=True)
    if (not isinstance(layout,dict) or layout.get('schema_version')!='native-ass-render-layout-v1' or layout.get('width')!=width or layout.get('height')!=height
        or source.stat().st_size>256*1024 or layout.get('ass_sha256')!=file_sha(source) or not isinstance(captions,list) or len(captions)>MAX_CAPTIONS):raise WorkflowError('STORYBOARD_QC_SUBTITLE_BINDING_INVALID')
    rect=layout.get('safe_rectangle')
    if not isinstance(rect,list) or len(rect)!=4 or any(type(n) is not int for n in rect) or not (0<=rect[0]<rect[2]<=width and 0<=rect[1]<rect[3]<=height):raise WorkflowError('STORYBOARD_QC_SUBTITLE_SAFE_AREA_INVALID')
    dialogue=[line.split(',',9) for line in source.read_text(encoding='utf-8').splitlines() if line.startswith('Dialogue:')]
    if len(dialogue)!=len(captions) or any(len(row)!=10 for row in dialogue):raise WorkflowError('STORYBOARD_QC_SUBTITLE_BINDING_INVALID')
    folder=directory/'subtitle-qc';folder.mkdir(exist_ok=False);samples=[];failures=[];started=time.monotonic()
    from .pipeline import ass_time
    for index,cue in enumerate(captions):
        if not isinstance(cue,dict):raise WorkflowError('STORYBOARD_QC_SUBTITLE_TIMING_INVALID')
        start,end=cue.get('start'),cue.get('end')
        if (not number(start) or not number(end) or not 0<=start<end<=duration+.001 or not isinstance(cue.get('text'),str) or not cue['text'].strip()):raise WorkflowError('STORYBOARD_QC_SUBTITLE_TIMING_INVALID')
        # Native ASS writes centiseconds; sample an actual 30-fps frame in that interval.
        if dialogue[index][1]!=ass_time(start) or dialogue[index][2]!=ass_time(end):raise WorkflowError('STORYBOARD_QC_SUBTITLE_BINDING_INVALID')
        left=round(start*100)/100;right=round(end*100)/100;first=math.ceil(left*30-1e-8);last=math.ceil(right*30-1e-8)-1
        if first>last:failures.append({'cue_index':index,'reason':'caption_has_no_visible_output_frame'});continue
        stamp=(first+last)//2/30
        if time.monotonic()-started>90:raise WorkflowError('STORYBOARD_QC_SUBTITLE_TIMEOUT')
        command=[str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','error','-f','lavfi','-i',f'color=c=black@0.0:s={width}x{height}:r=30,format=rgba',
            '-vf',f'setpts=PTS+{stamp:.9f}/TB,ass=subtitles.ass:alpha=1','-frames:v','1','-fps_mode','passthrough','-f','image2pipe','-c:v','png','pipe:1']
        try:result=subprocess.run(command,cwd=directory,capture_output=True,timeout=20,check=True)
        except (subprocess.SubprocessError,OSError):raise WorkflowError('STORYBOARD_QC_SUBTITLE_MASK_FAILED') from None
        if len(result.stdout)>16*1024*1024:raise WorkflowError('STORYBOARD_QC_SUBTITLE_MASK_FAILED')
        try:
            with Image.open(io.BytesIO(result.stdout)) as image:
                image.load()
                if image.mode!='RGBA' or image.size!=(width,height):raise ValueError()
                bounds=image.getchannel('A').getbbox()
        except (ValueError,OSError):raise WorkflowError('STORYBOARD_QC_SUBTITLE_MASK_FAILED') from None
        path=folder/(f'{index:03}.png');path.write_bytes(result.stdout)
        inside=bounds is not None and bounds[0]>=rect[0] and bounds[1]>=rect[1] and bounds[2]<=rect[2] and bounds[3]<=rect[3]
        sample={'cue_index':index,'timestamp_seconds':stamp,'bounds':list(bounds) if bounds else None,'inside_safe_area':inside,
            'evidence_frame_reference':str(path.relative_to(directory)).replace('\\','/'),'sha256':file_sha(path),'actual_libass_pixels':True}
        samples.append(sample)
        if not inside:failures.append({'cue_index':index,'reason':'subtitle_pixels_missing_or_outside_safe_area'})
        if file_sha(source)!=layout['ass_sha256']:raise WorkflowError('STORYBOARD_QC_SUBTITLE_BINDING_INVALID')
    return {'status':'failed' if failures else 'passed','provider':'local-ffmpeg-libass-alpha-mask','model':None,'confidence':None,
        'cue_count':len(captions),'sample_count':len(samples),'safe_rectangle':rect,'ass_sha256':layout['ass_sha256'],
        'samples':samples,'failures':failures,'external_provider_calls':0,'word_alignment_claimed':False}

def inspect(config,snapshot,directory,legacy_report,*,preview_only=False):
    document=snapshot['document'];manifest_path=guard(directory/'render-manifest.json',exists=True);manifest=json.loads(manifest_path.read_bytes())
    duration=manifest['duration_seconds'];layout=manifest.get('subtitle_layout') or {};width,height=layout.get('width'),layout.get('height')
    binding={'schema_version':'native-storyboard-full-qc-v1','document_sha256':digest(document),'render_manifest_sha256':file_sha(manifest_path),
        'final_sha256':legacy_report['final_sha256'],'human_final_video_accepted':False,'published':False,'external_provider_calls':0,'paid_operations':0,
        'semantic_vision_used':False,'rights_independently_verified':False}
    if preview_only:binding['render_purpose']='narration_preview'
    full=None;subtitle=None;timeline=None
    write_json(directory/'transport-qc-report.json',legacy_report)
    try:
        if not legacy_report['passed'] or not number(duration) or duration<=0 or type(width) is not int or type(height) is not int:raise WorkflowError('STORYBOARD_QC_RENDER_BINDING_INVALID')
        if preview_only:
            from .narration_preview import validate_context
            validate_context(config,snapshot)
            if manifest.get('approval') is not None or manifest.get('render_purpose')!='narration_preview' or manifest.get('preview_authorization')!=snapshot['preview_authorization']:raise WorkflowError('STORYBOARD_QC_PREVIEW_AUTHORIZATION_CHANGED')
        elif manifest.get('approval')!=snapshot.get('approval') or not snapshot.get('approval') or snapshot['approval'].get('snapshot_sha256')!=digest(document):raise WorkflowError('STORYBOARD_QC_APPROVAL_CHANGED')
        canonical=document.get('canonical_timeline')
        if canonical and manifest.get('canonical_timeline')!={'version':canonical['version'],'sha256':canonical['sha256']}:raise WorkflowError('STORYBOARD_QC_CANONICAL_TIMELINE_CHANGED')
        voice=manifest.get('voice_audio_file')
        if voice not in {'voice.wav','render-voice.wav'} or file_sha(guard(directory/voice,exists=True))!=manifest.get('voice_sha256'):raise WorkflowError('STORYBOARD_QC_VOICE_CHANGED')
        timeline=timeline_evidence(config,document,manifest,duration);subtitle=subtitle_evidence(config,directory,manifest,duration,width,height)
        full=asyncio.run(FullProductionQC(ffprobe_path=str(config.ffmpeg_bin/'ffprobe.exe'),ffmpeg_path=str(config.ffmpeg_bin/'ffmpeg.exe')).inspect(directory/'final.mp4',
            expected_duration=duration,expected_width=width,expected_height=height,expected_fps=30,subtitle_qc=subtitle,timeline_qc=timeline))
        # Shared measurements contain interval tuples; freeze the exact JSON shape
        # before returning it, so first delivery and checkpoint replay are identical.
        full=json.loads(json.dumps(full,allow_nan=False))
        if (file_sha(manifest_path)!=binding['render_manifest_sha256'] or file_sha(directory/'final.mp4')!=binding['final_sha256'] or full['checksum_sha256']!=binding['final_sha256']):raise WorkflowError('STORYBOARD_QC_RENDER_BINDING_INVALID')
        verify_selected_files(config,document)
        report={**binding,'status':'passed','full_production_qc':full,'subtitle_bounds':subtitle,'timeline':timeline}
        write_json(directory/'full-qc-report.json',report)
        combined={**legacy_report,'checks':{**legacy_report['checks'],'full_production_qc':True},'full_quality':report,'passed':True}
        write_json(directory/'qc-report.json',combined);return combined
    except (WorkflowError,ProductionQCError) as error:
        report={**binding,'status':'failed_qc','failure_code':error.code if isinstance(error,WorkflowError) else 'FULL_PRODUCTION_QC_FAILED',
            'full_production_qc':error.report if isinstance(error,ProductionQCError) else full,'subtitle_bounds':subtitle,'timeline':timeline}
        write_json(directory/'full-qc-report.json',report)
        write_json(directory/'qc-report.json',{**legacy_report,'checks':{**legacy_report['checks'],'full_production_qc':False},'full_quality':report,'passed':False})
        raise WorkflowError('STORYBOARD_FULL_MEDIA_QC_FAILED') from None
