"""Trusted uploaded video custody; owned staging and explicit task draining."""
import asyncio
from contextlib import asynccontextmanager
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from .auto_edit_db import UploadSessionORM
from .auto_edit_models import MediaMetadata
from .db import AssetORM, VideoProjectORM
from .object_storage import sha256_file
from .local_video_transcription_provider import completed_io
from .frozen_storage_read import FrozenStorageRead


async def trusted_video_snapshot(repository, project_id, asset_id, storage_name, max_bytes):
    async with repository.session_factory() as session:
        return await trusted_video_in_session(session, project_id, asset_id, storage_name, max_bytes)


async def trusted_video_in_session(session, project_id, asset_id, storage_name, max_bytes):
    project = await session.get(VideoProjectORM, project_id)
    asset = await session.get(AssetORM, asset_id)
    if project is None or asset is None or asset.project_id != project_id or asset.workspace_id != project.workspace_id:
        raise ValueError('AUTO_EDIT_VIDEO_SOURCE_SCOPE_CHANGED')
    if (asset.asset_class != 'source' or asset.kind != 'video' or not asset.content_type.startswith('video/')
        or asset.storage_provider != storage_name or not 0 < asset.size_bytes <= max_bytes):
        raise ValueError('AUTO_EDIT_VIDEO_SOURCE_REQUIRED_OR_LIMIT')
    upload = await session.get(UploadSessionORM, asset.provenance.get('source_reference', ''))
    if (asset.provenance.get('source_type') != 'user_upload' or upload is None or upload.asset_id != asset_id
        or upload.project_id != project_id or upload.workspace_id != project.workspace_id
        or upload.status not in {'completed', 'completed_duplicate'} or upload.quarantine_state != 'trusted'
        or upload.trusted_at is None or upload.scan_checksum_sha256 != asset.checksum_sha256):
        raise ValueError('AUTO_EDIT_VIDEO_TRUSTED_UPLOAD_REQUIRED')
    media = MediaMetadata.model_validate(asset.provenance.get('media_metadata'))
    if (media.media_kind != 'video' or media.video_codec is None or media.duration_seconds is None
        or not math.isfinite(media.duration_seconds) or media.duration_seconds <= 0 or media.detected_content_type != asset.content_type
        or upload.media_metadata_json != media.model_dump(mode='json')):
        raise ValueError('AUTO_EDIT_VIDEO_METADATA_CHANGED')
    return {'project_id': project_id, 'workspace_id': project.workspace_id, 'asset_id': asset_id,
        'source_sha256': asset.checksum_sha256, 'source_size_bytes': asset.size_bytes,
        'storage_provider': asset.storage_provider, 'object_key': asset.object_key,
        'media_metadata': media.model_dump(mode='json'), 'upload_id': upload.upload_id}


async def verify_file(path, snapshot):
    if not path.is_file() or path.stat().st_size != snapshot['source_size_bytes'] \
            or await completed_io(asyncio.to_thread(sha256_file, path)) != snapshot['source_sha256']:
        raise ValueError('AUTO_EDIT_VIDEO_SOURCE_BYTES_CHANGED')


@asynccontextmanager
async def staged_trusted_video(repository, storage, project_id, asset_id, staging_root, max_bytes, expected=None):
    snapshot = await trusted_video_snapshot(repository, project_id, asset_id, storage.name, max_bytes)
    if expected is not None and snapshot != expected:
        raise ValueError('AUTO_EDIT_VIDEO_SOURCE_CUSTODY_CHANGED')
    root = Path(staging_root);root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='trusted-video-', dir=root) as owned:
        path = Path(owned)/'source.video'
        proof=FrozenStorageRead(snapshot['object_key'],snapshot['workspace_id'],snapshot['project_id'],
            snapshot['source_size_bytes'],snapshot['source_sha256'],snapshot['storage_provider'],max_bytes)
        await proof.download(storage,path)
        await verify_file(path, snapshot)
        if await trusted_video_snapshot(repository,project_id,asset_id,storage.name,max_bytes)!=snapshot:
            raise ValueError('AUTO_EDIT_VIDEO_SOURCE_CUSTODY_CHANGED')
        yield path, snapshot


async def gather_drained(*coroutines):
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            if not task.done():task.cancel()
        async def collect():
            return await asyncio.gather(*tasks, return_exceptions=True)
        await completed_io(collect())
        raise
