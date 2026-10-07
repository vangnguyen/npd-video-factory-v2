"""Local, immutable canonical source-footage proxy; no TTS or API database."""
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import json
import subprocess
import uuid
from fractions import Fraction

from .auto_edit_timeline import validate_document
from .auto_edit_analysis import asset_reference
from .contracts import WorkflowError, file_sha
from .media import media_path, project_assets
from .source_assets import canonical_assets
from app.platform_models import AssetRead
from app.timeline_models import TimelineSnapshot
from app.timeline_proxy import FFmpegProxyRenderer

PROFILE = 'native-source-timeline-proxy-v1'
FULL_PROFILE = 'native-source-final-effects-preview-v2'


def profile_for(project):
    mode=project['document']['canonical_timeline']['snapshot']['metadata'].get('source_preview_mode','lightweight')
    if mode not in {'lightweight','final_effects'}:raise WorkflowError('SOURCE_PREVIEW_MODE_INVALID',400)
    return FULL_PROFILE if mode=='final_effects' else PROFILE


def resolve_assets(config, project):
    state = validate_document(project['document'])
    if state['snapshot']['metadata']['native_project_id'] != project['id']:
        raise WorkflowError('AUTO_EDIT_TIMELINE_PROJECT_MISMATCH')
    snapshot = TimelineSnapshot.model_validate(state['snapshot'])
    active = [clip for track in snapshot.tracks if not track.disabled
        for clip in track.clips if not clip.disabled and clip.asset_id
        and (track.type == 'video' or track.type == 'audio' and not track.muted and clip.volume > 0)]
    if sum(track.type == 'video' for track in snapshot.tracks for clip in track.clips
           if not track.disabled and not clip.disabled) > 128:
        raise WorkflowError('PREVIEW_VIDEO_CLIP_LIMIT', 400)
    if len(active) > 256:
        raise WorkflowError('PREVIEW_ACTIVE_CLIP_LIMIT', 400)
    needed = {clip.asset_id for clip in active}
    assets = {}
    timestamp = datetime.now(timezone.utc)
    for item in canonical_assets(project['document']):
        identifier = asset_reference(item)
        if identifier not in needed:
            continue
        path = media_path(config, item['id'])
        directory = config.data_root / 'assets'
        if (item.get('rights_confirmed') is not True or directory.is_symlink() or path.is_symlink()
                or path.resolve().parent != directory.resolve() or not path.is_file()
                or file_sha(path) != item['sha256']):
            raise WorkflowError('SOURCE_MEDIA_CHANGED_OR_MISSING')
        content_type = ('video/quicktime' if path.suffix.lower() == '.mov' else 'video/mp4') if item['kind'] == 'video' else (
            'audio/wav' if item['kind']=='audio' else 'image/png' if path.suffix.lower()=='.png' else 'image/jpeg')
        dto = AssetRead(asset_id=identifier, workspace_id='native-local', project_id='prj_'+project['id'],
            project_version_id=None, job_id=None, asset_class='source', kind=item['kind'],
            filename=item['id'], object_key='assets/'+item['id'], content_type=content_type,
            size_bytes=path.stat().st_size, checksum_sha256=item['sha256'], storage_provider='native-local',
            version=1, provenance={'native_asset_id':item['id'], 'rights_confirmed':True},
            created_at=timestamp, updated_at=timestamp)
        assets[identifier] = (dto, path)
    if set(assets) != needed:
        raise WorkflowError('PREVIEW_ASSET_UNAVAILABLE')
    return snapshot, assets


async def render(config, project, output, event):
    if profile_for(project)==FULL_PROFILE:
        return await asyncio.to_thread(render_final_effects,config,project,Path(output),event)
    snapshot, assets = resolve_assets(config, project)
    async def cancelled():
        return event.is_set()
    result = await FFmpegProxyRenderer(str(config.ffmpeg_bin/'ffmpeg.exe'),
        str(config.ffmpeg_bin/'ffprobe.exe')).render(snapshot=snapshot, assets=assets,
            output_path=Path(output), width=round(snapshot.width*.4), height=round(snapshot.height*.4),
            is_cancelled=cancelled,audio_processing=snapshot.metadata.get('source_audio_processing'))
    # Refuse a receipt if source bytes changed during the local encode.
    for asset, path in assets.values():
        if not path.is_file() or file_sha(path) != asset.checksum_sha256:
            result.path.unlink(missing_ok=True)
            raise WorkflowError('SOURCE_MEDIA_CHANGED_DURING_PREVIEW')
    return {**result.manifest, 'preview_profile':PROFILE,
        'timeline_version':project['document']['canonical_timeline']['version'],
        'timeline_sha256':project['document']['canonical_timeline']['sha256'],
        'canonical_audio_routing':True, 'canonical_source_audio':bool(result.manifest['audio_included']),
        'tts_calls':0, 'external_provider_calls':0,
        'final_approval_eligible':False, 'smart_reframe_keyframes_included':False,
        'width':round(snapshot.width*.4), 'height':round(snapshot.height*.4)}


def render_final_effects(config,project,output,event):
    # Lazy import avoids a cycle with the final worker's mandatory approval check.
    from .source_render import REPO,prepare_project,command_run
    if event.is_set():raise WorkflowError('PREVIEW_CANCELLED')
    if output.exists():raise WorkflowError('PREVIEW_OUTPUT_EXISTS')
    node=Path(getattr(config,'node_executable',r'C:\Program Files\nodejs\node.exe'))
    tsx=REPO/'renderer/node_modules/tsx/dist/cli.mjs'
    if not node.is_file() or not tsx.is_file():raise WorkflowError('AUTO_EDIT_RENDERER_NOT_CONFIGURED',503)
    directory=output.parent/'attempts'/('effects-preview-'+uuid.uuid4().hex)
    directory.mkdir(parents=True)
    snapshot,subtitles,assets,audio,_=prepare_project(config,project,directory,directory.name,event)
    command_run([str(node),str(tsx),str(REPO/'renderer/src/native-job-cli.ts'),str(directory),'--preview'],
        directory,'renderer.log',max(180,min(1800,snapshot.duration_seconds*12)),'AUTO_EDIT_RENDERER_FAILED',event)
    receipt=json.loads((directory/'renderer-receipt.json').read_bytes())
    width,height=round(snapshot.width*.4),round(snapshot.height*.4)
    if (receipt.get('fixture') is not False or receipt.get('preview') is not True
            or receipt.get('rendering_effects_parity') is not True or receipt.get('scale')!=.4
            or (receipt.get('width'),receipt.get('height'))!=(width,height)):
        raise WorkflowError('PREVIEW_RENDERER_RECEIPT_INVALID')
    rendered=directory/'final.mp4'
    probe=json.loads(subprocess.check_output([str(config.ffmpeg_bin/'ffprobe.exe'),'-v','error',
        '-show_streams','-show_format','-of','json',str(rendered)],timeout=30))
    video=next((s for s in probe['streams'] if s['codec_type']=='video'),{})
    sound=next((s for s in probe['streams'] if s['codec_type']=='audio'),{})
    if ((video.get('width'),video.get('height'))!=(width,height) or video.get('codec_name')!='h264'
            or video.get('pix_fmt')!='yuv420p' or float(Fraction(video.get('r_frame_rate','0/1')))!=snapshot.fps
            or sound.get('codec_name')!='aac' or sound.get('sample_rate')!='48000'
            or abs(float(probe['format']['duration'])-snapshot.duration_seconds)>.15):
        raise WorkflowError('PREVIEW_MEDIA_PROFILE_INVALID')
    command_run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-i',str(rendered),
        '-f','null','-'],directory,'decode-check.log',180,'PREVIEW_DECODE_FAILED',event)
    resolve_assets(config,project)
    if event.is_set():raise WorkflowError('PREVIEW_CANCELLED')
    rendered.replace(output)
    keyframes=any(clip.metadata.get('reframe',{}).get('keyframes') for track in snapshot.tracks
        if not track.disabled and track.type=='video' for clip in track.clips if not clip.disabled)
    return {'preview_profile':FULL_PROFILE,'playable':True,'fixture':False,
        'renderer':'remotion-local-native-job-v1','rendering_effects_parity':True,
        'composition_width':snapshot.width,'composition_height':snapshot.height,'scale':.4,
        'width':width,'height':height,'fps':snapshot.fps,'duration_seconds':snapshot.duration_seconds,
        'measured_container_duration_seconds':float(probe['format']['duration']),
        'timeline_version':project['document']['canonical_timeline']['version'],
        'timeline_sha256':project['document']['canonical_timeline']['sha256'],
        'source_hashes':{identifier:asset.checksum_sha256 for identifier,(asset,path) in assets.items()},
        'captions_included':bool(subtitles.cues),'smart_reframe_keyframes_included':keyframes,
        'canonical_audio_routing':True,'canonical_source_audio':bool(audio.clips),'audio_included':bool(audio.clips),
        'music_ducking':audio.processing['music_ducking'],'audio_processing':audio.processing,
        'audio_speech_normalization':bool(audio.processing['normalization_original_audio_clip_ids']),
        'tts_calls':0,'external_provider_calls':0,'final_qc_verified':False,
        'final_render_parity':False,'final_approval_eligible':False,'human_final_video_accepted':False}
