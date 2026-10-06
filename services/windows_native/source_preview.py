"""Local, immutable canonical source-footage proxy; no TTS or API database."""
from datetime import datetime, timezone
from pathlib import Path

from .auto_edit_timeline import validate_document
from .auto_edit_analysis import asset_reference
from .contracts import WorkflowError, file_sha
from .media import media_path, project_assets
from .source_assets import canonical_assets
from app.platform_models import AssetRead
from app.timeline_models import TimelineSnapshot
from app.timeline_proxy import FFmpegProxyRenderer

PROFILE = 'native-source-timeline-proxy-v1'


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
