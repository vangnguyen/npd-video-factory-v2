"""Approved canonical source footage -> private local renderer -> measured QC.

No narration synthesis, external provider, new project store or second timeline.
"""
import asyncio
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid

from .contracts import WorkflowError,digest,file_sha
from .hardening import Artifacts,durable_json
from .source_approval import validate_render_approval,reviewed_preview
from .source_preview import resolve_assets
from .north_star_quality import audio_activity
from app.timeline_audio_processing import build_processed_audio_graph
from app.production_logic import (build_timeline_render_manifest,derive_subtitle_cues,
    validate_subtitles,validate_timeline_renderability)
from app.production_models import SubtitleStyle,SubtitleVersionRead,MixConfig
from app.production_qc import FullProductionQC,ProductionQCError

REPO=Path(__file__).resolve().parents[2]
PROFILES={(1080,1920):'vertical-1080x1920',(1920,1080):'landscape-1920x1080',
    (1080,1080):'square-1080x1080',(1080,1350):'portrait-1080x1350'}


def command_run(command,directory,log_name,timeout,code,cancel_event=None):
    with (directory/log_name).open('ab') as log:
        process=subprocess.Popen(command,cwd=REPO,stdout=log,stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
        try:
            if cancel_event is None:result=process.wait(timeout=timeout)
            else:
                started=time.monotonic()
                while process.poll() is None:
                    if cancel_event.wait(.15):raise WorkflowError('PREVIEW_CANCELLED')
                    if time.monotonic()-started>timeout:raise WorkflowError('PREVIEW_TIMEOUT')
                result=process.returncode
        except BaseException:
            # Terminate only this owned child tree. The Native parent is also
            # contained by its Windows Job Object in the running application.
            if process.poll() is None:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
                else:os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=15)
            if cancel_event is not None:
                raise
            raise WorkflowError(code+'_INTERRUPTED',503) from None
    if result:raise WorkflowError(code)


def check_preview(config,job):
    approval=validate_render_approval(job)
    project={'id':job['project_id'],'revision':job['revision'],'document':job['snapshot']['document']}
    if reviewed_preview(config.data_root,project)!=approval['reviewed_preview']:
        raise WorkflowError('AUTO_EDIT_CURRENT_PREVIEW_REVIEW_REQUIRED',400)
    return project


def prepare(config,job,directory):
    project=check_preview(config,job)
    return prepare_project(config,project,directory,job['id'])


def prepare_project(config,project,directory,render_id,cancel_event=None):
    """Shared staged effects/audio preparation. Final dispatch still requires approval."""
    if cancel_event is not None and cancel_event.is_set():raise WorkflowError('PREVIEW_CANCELLED')
    snapshot,assets=resolve_assets(config,project)
    profile=PROFILES.get((snapshot.width,snapshot.height))
    if profile is None:raise WorkflowError('AUTO_EDIT_RENDER_PROFILE_INVALID',400)
    media=directory/'media';media.mkdir()
    staged={}
    for identifier,(asset,path) in assets.items():
        if cancel_event is not None and cancel_event.is_set():raise WorkflowError('PREVIEW_CANCELLED')
        destination=media/(identifier+path.suffix.lower())
        shutil.copyfile(path,destination)
        if file_sha(destination)!=asset.checksum_sha256:raise WorkflowError('SOURCE_MEDIA_CHANGED_DURING_RENDER')
        staged[identifier]=(asset,destination)
    audio=build_processed_audio_graph(snapshot,staged,first_input_index=0,
        processing=snapshot.metadata.get('source_audio_processing'))
    mixed=media/'mix.wav'
    command=[str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n']
    if audio.clips:
        filters=directory/'audio-filter.txt';filters.write_text(';'.join(audio.filters),encoding='utf-8')
        command += [*audio.inputs,'-/filter_complex',str(filters),'-map','[outa]']
    else:command += ['-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(snapshot.duration_seconds)]
    from .source_audio_cache import scope,fingerprint,materialize
    cache_request=fingerprint(scope(config.data_root,project),audio,staged,snapshot.duration_seconds,config.ffmpeg_bin/'ffmpeg.exe')
    def build_mix(destination):
        command_run([*command,'-c:a','pcm_s16le','-ar','48000','-ac','2',str(destination)],
            directory,'audio-mix.log',300,'AUTO_EDIT_AUDIO_MIX_FAILED',cancel_event)
    cache=materialize(config.data_root,cache_request,mixed,build_mix,cancel_event=cancel_event)
    # A cache hit does not waive current source checks or bind another timeline.
    resolve_assets(config,project)
    enabled_captions=any(track.kind=='subtitles' and not track.disabled and any(
        not clip.disabled and clip.label.strip() for clip in track.clips) for track in snapshot.tracks)
    cues=derive_subtitle_cues(snapshot) if enabled_captions else []
    style=SubtitleStyle.model_validate(snapshot.metadata.get('subtitle_style') or {'animation':'none'})
    subtitles=SubtitleVersionRead(subtitle_version_id='sub_'+digest([render_id,'captions'])[:24],
        package_id='pkg_'+project['id'],project_id='prj_'+project['id'],timeline_version_id='tlv_'+render_id,
        timeline_version=project['document']['canonical_timeline']['version'],version=1,cues=cues,style=style,
        actor_ref='native-session-owner',created_at=datetime.now(timezone.utc))
    root_analysis=next(value['analysis'] for value in project['document']['auto_edit_analyses']
        if value['analysis']['analysis_id']==snapshot.metadata['source_analysis_id'])
    language=((root_analysis.get('transcript') or {}).get('language') or 'vi')
    from .channel_profiles import resolve
    selected_channel=resolve(project['document'])
    if selected_channel is not None:
        from .branding import resolve as resolve_brand
        brand_name=resolve_brand(project['document'])[0].name
    else:brand_name='Video Factory'
    manifest=build_timeline_render_manifest(snapshot=snapshot,subtitles=subtitles,mix_config=MixConfig(),
        mixed_audio_path=mixed,asset_paths=staged,profile=profile,project_name=project['document']['name'],
        project_slug=project['id'],niche=project['document'].get('niche','custom'),brand_name=brand_name,language=language)
    # Source workflows use the expanded, strict v2.3 contract even without captions.
    manifest['version']='2.3'
    durable_json(directory/'timeline-render.json',manifest)
    durable_json(directory/'timeline.json',project['document']['canonical_timeline'])
    durable_json(directory/'subtitles.json',{'cues':[cue.model_dump(mode='json') for cue in cues],
        'style':style.model_dump(mode='json'),'word_alignment':'source_provider_intervals_where_available',
        'transcript_evidence':root_analysis.get('transcript')})
    durable_json(directory/'audio-analysis.json',{'schema':'canonical-source-audio-v1','clips':audio.clips,
        'muted_clip_ids':audio.muted_clip_ids,'source_audio_included':bool(audio.clips),
        'normalization_applied':bool(audio.processing['normalization_clip_ids']),
        'music_ducking':audio.processing['music_ducking'],'processing':audio.processing,
        'limiter_peak_db':-1 if audio.clips else None,
        'tts_calls':0,'actual_paid_cost':None,'intermediate_cache':cache})
    return snapshot,subtitles,assets,audio,profile


def run(config,job,out,stage):
    project=check_preview(config,job)
    node=Path(getattr(config,'node_executable',r'C:\Program Files\nodejs\node.exe'))
    tsx=REPO/'renderer/node_modules/tsx/dist/cli.mjs'
    if not node.is_file() or not tsx.is_file():raise WorkflowError('AUTO_EDIT_RENDERER_NOT_CONFIGURED',503)
    artifacts=Artifacts(out,job)
    # Source/approval/preview are verified even when reusing a final checkpoint.
    resolve_assets(config,project)
    checkpoint=artifacts.load('render')
    if checkpoint:
        stage('resuming_verified_source_render');return checkpoint['result']
    directory=out/'attempts'/('source-render-'+uuid.uuid4().hex)
    directory.mkdir(parents=True)
    started=time.monotonic();stage('source_timeline_audio_and_captions')
    snapshot,subtitles,assets,audio,profile=prepare(config,job,directory)
    original_render_manifest_sha=file_sha(directory/'timeline-render.json')
    stage('source_private_remotion_render')
    command_run([str(node),str(tsx),str(REPO/'renderer/src/native-job-cli.ts'),str(directory)],
        directory,'renderer.log',max(180,min(1800,snapshot.duration_seconds*12)),'AUTO_EDIT_RENDERER_FAILED')
    output=directory/'final.mp4'
    stage('source_full_media_qc')
    subtitle_qc=validate_subtitles(subtitles.cues,subtitles.style,snapshot.duration_seconds)
    timeline_qc=validate_timeline_renderability(snapshot,available_asset_ids=set(assets))
    timeline_qc['intentional_audio_silence']=not bool(audio.clips)
    try:
        report=asyncio.run(FullProductionQC(ffprobe_path=str(config.ffmpeg_bin/'ffprobe.exe'),
            ffmpeg_path=str(config.ffmpeg_bin/'ffmpeg.exe')).inspect(output,expected_duration=snapshot.duration_seconds,
                expected_width=snapshot.width,expected_height=snapshot.height,expected_fps=snapshot.fps,
                subtitle_qc=subtitle_qc,timeline_qc=timeline_qc))
    except ProductionQCError as error:
        durable_json(directory/'qc-report.json',{**error.report,'passed':False,'human_final_video_accepted':False})
        raise WorkflowError('AUTO_EDIT_MEDIA_QC_FAILED') from None
    probe=json.loads(subprocess.check_output([str(config.ffmpeg_bin/'ffprobe.exe'),'-v','error',
        '-show_streams','-show_format','-of','json',str(output)],timeout=30))
    video=next(value for value in probe['streams'] if value['codec_type']=='video')
    if video['pix_fmt']!='yuv420p':raise WorkflowError('AUTO_EDIT_MEDIA_QC_FAILED')
    # Inspect actual decoded PCM tail. Activity is never labeled as detected speech.
    raw=subprocess.check_output([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-i',str(output),
        '-vn','-f','f32le','-ac','1','-ar','48000','pipe:1'],timeout=90)
    import numpy as np
    activity=audio_activity(np.frombuffer(raw,dtype='<f4'),48000)
    if audio.clips and activity['trailing_silence_seconds']>2.08:
        durable_json(directory/'qc-report.json',{**report,'passed':False,'audio_activity':activity,'status':'failed',
            'failures':['unreviewed trailing audio silence exceeds two seconds']})
        raise WorkflowError('AUTO_EDIT_MEDIA_QC_FAILED')
    # Detect source changes during rendering before registering a ready artifact.
    resolve_assets(config,project)
    from .audio_loudness import measure
    try:
        loudness=measure(config,output)
        if loudness['input_sha256']!=report['checksum_sha256'] or loudness['input_sha256']!=file_sha(output):
            raise WorkflowError('NATIVE_AUDIO_LOUDNESS_INPUT_CHANGED')
    except WorkflowError as error:
        durable_json(directory/'qc-report.json',{**report,'passed':False,'status':'failed',
            'human_final_video_accepted':False,'failures':[error.code]})
        raise WorkflowError('AUTO_EDIT_MEDIA_QC_FAILED') from None
    qc={**report,'passed':True,'final_sha256':file_sha(output),'human_final_video_accepted':False,'published':False,
        'render_profile':profile,'audio_activity':activity,'intentional_audio_silence':not bool(audio.clips)}
    qc['measured_audio_loudness']=loudness
    from .render_frame_qc import build as render_frame_evidence,artifact_names as render_frame_artifacts
    try:
        qc['rendered_frame_evidence']=render_frame_evidence(config,directory,
            document_sha256=digest(project['document']),manifest_name='timeline-render.json')
        measured_frames=qc['rendered_frame_evidence']['observation']
        if (measured_frames['rendered_video_sha256']!=qc['final_sha256']
                or measured_frames['render_manifest_sha256']!=original_render_manifest_sha):
            raise WorkflowError('RENDER_FRAME_QC_INPUT_CHANGED')
    except WorkflowError as error:
        durable_json(directory/'qc-report.json',{**qc,'passed':False,'status':'failed',
            'failures':[error.code]})
        raise WorkflowError('AUTO_EDIT_MEDIA_QC_FAILED') from None
    analysis=json.loads((directory/'audio-analysis.json').read_bytes());analysis['final_output_loudness']=loudness
    durable_json(directory/'audio-analysis.json',analysis)
    durable_json(directory/'qc-report.json',qc);durable_json(directory/'ffprobe.json',probe)
    durable_json(directory/'render-manifest.json',{'renderer':'remotion-local-native-job-v1','profile':profile,
        'canonical_timeline':project['document']['canonical_timeline'],'approval':job['snapshot']['approval'],
        'source_hashes':{identifier:asset.checksum_sha256 for identifier,(asset,path) in assets.items()},
        'captions_included':bool(subtitles.cues),'canonical_audio_included':bool(audio.clips),
        'speech_normalization':bool(audio.processing['normalization_original_audio_clip_ids']),
        'music_ducking':audio.processing['music_ducking'],'audio_processing':audio.processing,
        'external_provider_calls':0,'tts_calls':0,
        'human_final_video_accepted':False,'publishing_allowed':False})
    durable_json(directory/'cost.json',{'external_operations':[],'paid_operation_count':0,
        'actual_local_compute_cost':None,'duration_seconds':time.monotonic()-started})
    files=('final.mp4','qc-report.json','ffprobe.json','render-manifest.json','timeline.json',
        'timeline-render.json','subtitles.json','audio-analysis.json','cost.json','renderer-receipt.json')
    try:files+=render_frame_artifacts(directory)
    except WorkflowError:raise WorkflowError('AUTO_EDIT_MEDIA_QC_FAILED') from None
    artifacts.path('render-frame-qc').mkdir(exist_ok=True)
    paths=[artifacts.publish(directory/name,name) for name in files]
    from .render_frame_qc import validate as validate_render_frames
    try:validate_render_frames(out,qc['rendered_frame_evidence'],document_sha256=digest(project['document']))
    except WorkflowError:raise WorkflowError('AUTO_EDIT_MEDIA_QC_FAILED') from None
    result={'video_url':f"/api/jobs/{job['id']}/video",'qc':qc,'output_directory':str(out),'review_required':True,
        'render_mode':'source_footage','provider_calls':0,'tts_calls':0,
        'render_version':digest({'snapshot':job['snapshot'],'job_id':job['id'],'final_sha256':qc['final_sha256']})}
    artifacts.commit('render',paths,result)
    return result
