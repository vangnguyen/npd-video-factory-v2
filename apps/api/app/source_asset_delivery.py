"""Verified original media bytes; authorization/source ownership belongs to caller."""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import re
import tempfile

import anyio
from fastapi import HTTPException, Request
from starlette.responses import StreamingResponse

from .media_validation import MediaValidationError, safe_upload_filename, sniff_media
from .object_storage import ObjectStorageProvider, filesystem_path, validate_object_key
from .platform_models import AssetRead
from .bounded_storage_download import StorageDownloadError
from .frozen_storage_read import frozen_asset_read, completed_read

MAX_SOURCE_BYTES = 2 * 1024**3
CHUNK_BYTES = 128 * 1024


def fail(code: str, status: int = 409):
    raise HTTPException(status_code=status, detail={'code':code})


def source_range(value: str | None, size: int) -> tuple[int, int] | None:
    if value is None:
        return None
    match = re.fullmatch(r'bytes=([0-9]{0,20})-([0-9]{0,20})', value.strip(), re.I) if len(value) <= 128 else None
    if match is None or not any(match.groups()):
        raise HTTPException(416, detail={'code':'SOURCE_RANGE_INVALID'}, headers={'Content-Range':f'bytes */{size}'})
    left, right = match.groups()
    if not left:
        length = int(right)
        start, end = max(0, size-length), size-1
        valid = length > 0
    else:
        start = int(left)
        end = min(int(right), size-1) if right else size-1
        valid = start < size and start <= end
    if not valid:
        raise HTTPException(416, detail={'code':'SOURCE_RANGE_INVALID'}, headers={'Content-Range':f'bytes */{size}'})
    return start, end


class OwnedSourceResponse(StreamingResponse):
    """Close private descriptor/temp root even if the client disconnects."""
    def __init__(self, handle, temporary, *, start, end, **kwargs):
        self._handle, self._temporary = handle, temporary
        self._closed = False
        handle.seek(start)
        def chunks():
            remaining = end-start+1
            while remaining:
                chunk = handle.read(min(CHUNK_BYTES, remaining))
                if not chunk:
                    raise RuntimeError('SOURCE_DELIVERY_SHORT_READ')
                remaining -= len(chunk)
                yield chunk
        super().__init__(chunks(), **kwargs)

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._handle.close()
            finally:
                self._temporary.cleanup()

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(self.close)


def verified_handle(physical: Path, asset: AssetRead, declared: str):
    """Blocking filesystem validation runs off the ASGI event loop."""
    handle = None
    try:
        handle = physical.open('rb')
        if os.fstat(handle.fileno()).st_size != asset.size_bytes:
            fail('SOURCE_ASSET_SIZE_CHANGED')
        checksum = hashlib.sha256()
        for chunk in iter(lambda:handle.read(CHUNK_BYTES), b''):
            checksum.update(chunk)
        if checksum.hexdigest() != asset.checksum_sha256:
            fail('SOURCE_ASSET_CHECKSUM_CHANGED')
        detected_kind, detected_mime = sniff_media(physical, declared)
        equivalent = declared == detected_mime or {declared,detected_mime} <= {'audio/wav','audio/x-wav'}
        if detected_kind != asset.kind or not equivalent:
            fail('SOURCE_ASSET_MIME_CHANGED')
        return handle, detected_mime
    except BaseException:
        if handle is not None:
            handle.close()
        raise


async def deliver_source_asset(request: Request, *, asset: AssetRead,
    object_storage: ObjectStorageProvider, staging_root: Path,
    max_source_bytes: int = MAX_SOURCE_BYTES):
    """Call only after project/workspace, completed intake and snapshot guards."""
    asset = asset.model_copy(deep=True)
    if (type(max_source_bytes) is not int or not 1 <= max_source_bytes <= MAX_SOURCE_BYTES
        or type(asset.size_bytes) is not int or not 0 < asset.size_bytes <= max_source_bytes
        or asset.asset_class != 'source' or asset.kind not in {'audio','video','image'}
        or not re.fullmatch(r'[a-f0-9]{64}', asset.checksum_sha256)
        or asset.storage_provider != object_storage.name):
        fail('SOURCE_ASSET_METADATA_INVALID')
    try:
        validate_object_key(asset.object_key)
        proof = frozen_asset_read(asset, workspace_id=asset.workspace_id, project_id=asset.project_id,
            storage=object_storage, maximum=max_source_bytes)
    except (ValueError, TypeError):
        fail('SOURCE_ASSET_METADATA_INVALID')
    declared = asset.content_type.split(';',1)[0].strip().lower()
    etag = '"sha256-'+asset.checksum_sha256+'"'
    range_value = request.headers.get('range')
    if range_value is not None and request.headers.get('if-range') not in (None, etag):
        range_value = None
    selection = source_range(range_value, asset.size_bytes)
    root = Path(staging_root).absolute()
    io_root = filesystem_path(root)
    if root.is_symlink() or getattr(root, 'is_junction', lambda:False)() or root.resolve() != root:
        fail('SOURCE_STAGING_INVALID', 500)
    io_root.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix='vf-source-delivery-', dir=io_root)
    folder = Path(temporary.name)
    target = folder/'source.bin'
    handle = None
    handed_off = False
    try:
        try:
            await proof.download(object_storage, target)
        except FileNotFoundError:
            fail('SOURCE_OBJECT_NOT_FOUND', 404)
        except StorageDownloadError as error:
            if error.code in {'STORAGE_DOWNLOAD_SIZE_MISMATCH', 'STORAGE_DOWNLOAD_SIZE_LIMIT'}:
                fail('SOURCE_ASSET_SIZE_CHANGED')
            if error.code in {'STORAGE_DOWNLOAD_HASH_MISMATCH', 'STORAGE_DOWNLOAD_STAGE_HASH_MISMATCH'}:
                fail('SOURCE_ASSET_CHECKSUM_CHANGED')
            fail('SOURCE_STORAGE_UNAVAILABLE', 503)
        except Exception:
            fail('SOURCE_STORAGE_UNAVAILABLE', 503)
        if target.is_symlink() or target.resolve().parent != folder.resolve():
            fail('SOURCE_STAGED_FILE_INVALID')
        physical = filesystem_path(target)
        try:
            handle, detected_mime = await completed_read(asyncio.to_thread(verified_handle, physical, asset, declared),
                dispose_cancelled_result=lambda result:result[0].close())
        except MediaValidationError:
            fail('SOURCE_ASSET_MIME_CHANGED')
        except OSError:
            fail('SOURCE_STAGED_FILE_INVALID')
        start, end = selection if selection is not None else (0, asset.size_bytes-1)
        headers = {'Cache-Control':'no-store', 'Accept-Ranges':'bytes', 'ETag':etag,
            'X-Content-Type-Options':'nosniff', 'Content-Length':str(end-start+1),
            'Content-Disposition':'inline; filename="'+safe_upload_filename(asset.filename)+'"'}
        if selection is not None:
            headers['Content-Range'] = f'bytes {start}-{end}/{asset.size_bytes}'
        response = OwnedSourceResponse(handle, temporary, start=start, end=end,
            status_code=206 if selection is not None else 200, media_type=detected_mime, headers=headers)
        handed_off = True
        return response
    finally:
        if not handed_off:
            if handle is not None:
                handle.close()
            temporary.cleanup()
