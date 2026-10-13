"""Bounded independent local object copies; exclusive destinations, no alias/hardlink.

This local adapter does not attest S3 support or upload trust. A process crash
can leave unregistered child bytes; persisted unknown receipts prohibit replay.
"""
import asyncio
import hashlib
import os
import stat
import struct
import threading
import time
import zlib
from pathlib import Path, PurePosixPath
from .object_storage import LocalObjectStorageProvider, validate_object_key, filesystem_path
from .sql_variant_repository import SqlVariantError
from .local_video_transcription_provider import completed_io


def image_dimensions(data, content_type):
    """Bounded magic/structural header validation, not a visual-quality decoder."""
    try:
        dimensions = None
        if content_type == 'image/png':
            if data[:8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError()
            offset, count, idat, ended = 8, 0, False, False
            while offset < len(data):
                count += 1
                if count > 8192 or len(data)-offset < 12:
                    raise ValueError()
                length = struct.unpack('>I', data[offset:offset+4])[0]
                kind, end = data[offset+4:offset+8], offset+12+length
                if end > len(data) or zlib.crc32(data[offset+4:end-4]) & 0xffffffff != struct.unpack('>I',data[end-4:end])[0]:
                    raise ValueError()
                if count == 1:
                    if kind != b'IHDR' or length != 13:
                        raise ValueError()
                    width,height,depth,color,compression,filtering,interlace = struct.unpack('>IIBBBBB',data[offset+8:end-4])
                    if depth not in (1,2,4,8,16) or color not in (0,2,3,4,6) or compression or filtering or interlace not in (0,1):
                        raise ValueError()
                    dimensions = [width,height]
                elif kind == b'IHDR':
                    raise ValueError()
                if kind == b'IDAT':
                    idat = True
                if kind == b'IEND':
                    if length or not idat or end != len(data):
                        raise ValueError()
                    ended = True
                offset = end
            if not ended:
                raise ValueError()
        elif content_type == 'image/jpeg':
            if data[:2] != b'\xff\xd8' or data[-2:] != b'\xff\xd9':
                raise ValueError()
            offset, count = 2, 0
            while offset < len(data)-2:
                count += 1
                if count > 8192 or data[offset] != 255:
                    raise ValueError()
                while data[offset] == 255:
                    offset += 1
                marker = data[offset]; offset += 1
                if marker == 0xda:
                    break
                if marker in range(0xd0,0xda) or marker == 1:
                    continue
                length = struct.unpack('>H',data[offset:offset+2])[0]
                if length < 2 or offset+length > len(data):
                    raise ValueError()
                if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
                    if length < 8 or dimensions is not None:
                        raise ValueError()
                    height,width = struct.unpack('>HH',data[offset+3:offset+7])
                    dimensions = [width,height]
                offset += length
        elif content_type == 'image/webp':
            if data[:4] != b'RIFF' or data[8:12] != b'WEBP' or struct.unpack('<I',data[4:8])[0]+8 != len(data):
                raise ValueError()
            kind, length = data[12:16], struct.unpack('<I',data[16:20])[0]
            if length+20 > len(data):
                raise ValueError()
            if kind == b'VP8X' and length >= 10:
                dimensions = [1+int.from_bytes(data[24:27],'little'),1+int.from_bytes(data[27:30],'little')]
            elif kind == b'VP8 ' and length >= 10 and data[23:26] == b'\x9d\x01\x2a':
                width,height = struct.unpack('<HH',data[26:30]); dimensions=[width&0x3fff,height&0x3fff]
            elif kind == b'VP8L' and length >= 5 and data[20] == 0x2f:
                bits=int.from_bytes(data[21:25],'little'); dimensions=[(bits&0x3fff)+1,((bits>>14)&0x3fff)+1]
        if dimensions is None or any(not 1 <= n <= 32768 for n in dimensions) or dimensions[0]*dimensions[1] > 40_000_000:
            raise ValueError()
        return dimensions
    except (ValueError, IndexError, struct.error):
        raise SqlVariantError('SQL_VARIANT_COPY_MEDIA_INVALID') from None


def plain(path):
    path = filesystem_path(Path(path))
    if not path.is_absolute():
        raise SqlVariantError('SQL_VARIANT_COPY_PATH_REJECTED')
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise SqlVariantError('SQL_VARIANT_COPY_LINK_REJECTED')
    return path


class LocalStoryboardCopier:
    def __init__(self, storage, *, max_file_bytes=64 * 1024 * 1024, max_total_bytes=256 * 1024 * 1024,
                 timeout_seconds=120):
        if type(storage) is not LocalObjectStorageProvider:
            raise SqlVariantError('SQL_VARIANT_STORAGE_NOT_CONFIGURED')
        if (type(max_file_bytes) is not int or not 1 <= max_file_bytes <= 256 * 1024 * 1024
                or type(max_total_bytes) is not int or not max_file_bytes <= max_total_bytes <= 1024 * 1024 * 1024
                or type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 600):
            raise ValueError('SQL_VARIANT_COPY_LIMIT_INVALID')
        self.storage = storage
        self._root = str(storage.root)
        self._io_root = str(storage._io_root)
        self.max_file_bytes, self.max_total_bytes = max_file_bytes, max_total_bytes
        self.timeout_seconds = timeout_seconds

    def _binding(self):
        if (type(self.storage) is not LocalObjectStorageProvider or self.storage.name != 'local'
                or str(self.storage.root) != self._root or str(self.storage._io_root) != self._io_root):
            raise SqlVariantError('SQL_VARIANT_STORAGE_BINDING_CHANGED')

    def _paths(self, source_key, target_key):
        self._binding()
        root = plain(self.storage._io_root)
        source = plain(root / Path(*PurePosixPath(validate_object_key(source_key)).parts))
        target = root / Path(*PurePosixPath(validate_object_key(target_key)).parts)
        if source == target or root not in source.parents or root not in target.parents:
            raise SqlVariantError('SQL_VARIANT_COPY_PATH_REJECTED')
        # Verify each parent before and after mkdir. No project/accepted files are removed.
        current = root
        for part in target.relative_to(root).parts[:-1]:
            current = current / part
            current.mkdir(exist_ok=True)
            plain(current)
        plain(target.parent)
        if target.exists() or target.is_symlink():
            raise SqlVariantError('SQL_VARIANT_COPY_TARGET_EXISTS')
        return source, target

    def _copy(self, items, stop):
        self._binding()
        result, total = {}, 0
        deadline = time.monotonic() + self.timeout_seconds
        def active():
            if stop.is_set():
                raise SqlVariantError('SQL_VARIANT_COPY_CANCELLED')
            if time.monotonic() > deadline:
                raise SqlVariantError('SQL_VARIANT_COPY_TIMEOUT')
        for source_id, item in items.items():
            active()
            self._binding()
            size = item['size_bytes']
            if type(size) is not int or not 0 < size <= self.max_file_bytes or total + size > self.max_total_bytes:
                raise SqlVariantError('SQL_VARIANT_COPY_SIZE_LIMIT')
            source, target = self._paths(item['object_key'], item['target_key'])
            before = source.stat()
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != size:
                raise SqlVariantError('SQL_VARIANT_COPY_SOURCE_CHANGED')
            checksum, written = hashlib.sha256(), 0
            with source.open('rb') as inp, target.open('xb') as out:
                opened = os.fstat(inp.fileno())
                if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, size):
                    raise SqlVariantError('SQL_VARIANT_COPY_SOURCE_CHANGED')
                while True:
                    active()
                    block = inp.read(min(1024 * 1024, size - written + 1))
                    if not block:
                        break
                    written += len(block)
                    if written > size:
                        raise SqlVariantError('SQL_VARIANT_COPY_SOURCE_CHANGED')
                    checksum.update(block)
                    out.write(block)
                out.flush()
                os.fsync(out.fileno())
            after = plain(source).stat()
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                    or written != size or checksum.hexdigest() != item['checksum_sha256']):
                raise SqlVariantError('SQL_VARIANT_COPY_SOURCE_CHANGED')
            # Structural headers only: no inference or claim of decoded visual QC.
            dimensions = self.verify(target, item['content_type'], size, checksum.hexdigest())
            result[source_id] = {'object_key': item['target_key'], 'sha256': checksum.hexdigest(),
                'size_bytes': size, 'content_type': item['content_type'], 'storage_provider': 'local',
                'dimensions': dimensions}
            total += size
            active()
        return result

    @staticmethod
    def verify(path, content_type, size, checksum):
        path = plain(path)
        before = path.stat()
        if before.st_size != size or before.st_nlink != 1 or not stat.S_ISREG(before.st_mode):
            raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
        sha = hashlib.sha256()
        count = 0
        image_parts, head = [], b''
        is_image = content_type in {'image/png', 'image/jpeg', 'image/webp'}
        if is_image and size > 256 * 1024 * 1024:
            raise SqlVariantError('SQL_VARIANT_COPY_SIZE_LIMIT')
        with path.open('rb') as inp:
            while True:
                block = inp.read(min(1024 * 1024, size-count+1))
                if not block:
                    break
                count += len(block)
                if count > size:
                    raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
                sha.update(block)
                if is_image:
                    image_parts.append(block)
                if len(head) < 16:
                    head = (head + block)[:16]
        after = plain(path).stat()
        if count != size or sha.hexdigest() != checksum or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) != (
                after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
            raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
        if is_image:
            # Header and checksum must describe the same immutable read snapshot.
            return image_dimensions(b''.join(image_parts), content_type)
        valid = (content_type in {'audio/wav', 'audio/x-wav'} and head[:4] == b'RIFF' and head[8:12] == b'WAVE'
                 or content_type == 'audio/mpeg' and (head[:3] == b'ID3' or head[:2] in {b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'})
                 or content_type == 'audio/ogg' and head[:4] == b'OggS')
        if not valid:
            raise SqlVariantError('SQL_VARIANT_S3_SOURCE_UNSUPPORTED')
        return None

    async def copy(self, items):
        stop = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(self._copy, items, stop))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            stop.set()
            # Drain owned IO before returning cancellation: no late completion/SQL write.
            async def drained():
                return await asyncio.shield(task)
            try:
                # completed_io shields its own waiter through repeated cancellation;
                # this additional shield protects the original thread task proxy.
                await completed_io(drained())
            except BaseException:
                pass  # Preserve the caller's original cancellation after the writer closes.
            raise
        except SqlVariantError:
            raise
        except Exception:
            raise SqlVariantError('SQL_VARIANT_COPY_IO_FAILED') from None

    async def verify_all(self, copies, *, source_items=None):
        def check():
            self._binding()
            for item in copies.values():
                path = plain(self.storage._io_root / Path(*PurePosixPath(validate_object_key(item['object_key'])).parts))
                if self.verify(path, item['content_type'], item['size_bytes'], item['sha256']) != item['dimensions']:
                    raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
            for item in (source_items or {}).values():
                path = plain(self.storage._io_root / Path(*PurePosixPath(validate_object_key(item['object_key'])).parts))
                self.verify(path, item['content_type'], item['size_bytes'], item['checksum_sha256'])
            self._binding()
        try:
            await completed_io(asyncio.to_thread(check))
        except SqlVariantError:
            raise
        except Exception:
            raise SqlVariantError('SQL_VARIANT_COPY_IO_FAILED') from None
