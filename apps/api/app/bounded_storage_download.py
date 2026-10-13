"""Counted atomic downloads and cancellation custody; no SDK or runtime imports."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import logging
import os
from pathlib import Path
import re
import stat
import threading
import time
from typing import BinaryIO, Callable
import uuid

BLOCK_BYTES = 256 * 1024
READ_DEADLINE_SECONDS = 120
_PRIVATE = ContextVar('storage_download_private', default=False)
_SDK_NAMES = ('botocore', 'boto3', 's3transfer', 'urllib3')


def _clock():
    return time.monotonic()


class StorageDownloadError(OSError):
    """Public bounded code only; paths, keys and SDK messages stay private."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class StorageDownloadNotFound(StorageDownloadError, FileNotFoundError):
    """Missing source keeps existing FileNotFoundError/HTTP404 contracts."""

    def __init__(self):
        super().__init__('STORAGE_DOWNLOAD_NOT_FOUND')


@dataclass(frozen=True)
class DownloadBounds:
    max_bytes: int | None = None
    expected_size_bytes: int | None = None
    expected_sha256: str | None = None

    def __post_init__(self):
        if ((self.max_bytes is not None and (type(self.max_bytes) is not int or self.max_bytes <= 0))
                or (self.expected_size_bytes is not None
                    and (type(self.expected_size_bytes) is not int or self.expected_size_bytes < 0))
                or (self.max_bytes is not None and self.expected_size_bytes is not None
                    and self.expected_size_bytes > self.max_bytes)
                or (self.expected_sha256 is not None
                    and (not isinstance(self.expected_sha256, str)
                         or re.fullmatch('[a-f0-9]{64}', self.expected_sha256) is None))):
            raise StorageDownloadError('STORAGE_DOWNLOAD_INVALID_BOUNDS')

    def check_size(self, size: int):
        if type(size) is not int or size < 0:
            raise StorageDownloadError('STORAGE_DOWNLOAD_STREAM_INVALID')
        if self.max_bytes is not None and size > self.max_bytes:
            raise StorageDownloadError('STORAGE_DOWNLOAD_SIZE_LIMIT')
        if self.expected_size_bytes is not None and size != self.expected_size_bytes:
            raise StorageDownloadError('STORAGE_DOWNLOAD_SIZE_MISMATCH')


class DownloadControl:
    """Cancellation and verified replacement have one local linearization lock."""

    def __init__(self):
        self.cancelled = threading.Event()
        self._lock = threading.Lock()

    def cancel(self):
        with self._lock:
            self.cancelled.set()

    def check(self):
        if self.cancelled.is_set():
            raise StorageDownloadError('STORAGE_DOWNLOAD_CANCELLED')

    def replace(self, temporary: Path, destination: Path, *, identity, parent_identity,
                expected_size, io_path, reverify=None):
        # Windows metadata readers/scanners can briefly deny atomic replacement.
        # Only this local rename is retried: never reopen storage or redo a wire.
        for attempt in range(4):
            self.check()
            if attempt and reverify is not None:
                reverify()
            with self._lock:
                self.check()
                guarded_destination(destination, io_path)
                _admit_owned(temporary, identity, parent_identity, expected_size, io_path)
                try:
                    temporary.replace(destination)
                    return
                except PermissionError as error:
                    if os.name != 'nt' or getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 3:
                        raise
            time.sleep(.01 * (attempt + 1))


async def drained_download(operation: Callable[[DownloadControl], None]):
    """A cancelled caller waits for the writer, including repeated cancellation."""
    control = DownloadControl()
    task = asyncio.create_task(asyncio.to_thread(operation, control))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        control.cancel()
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        with suppress(Exception, asyncio.CancelledError):
            await task
        raise


class _SDKPrivacyFilter(logging.Filter):
    def filter(self, record):
        private_sdk = record.name.split('.', 1)[0] in _SDK_NAMES
        return not (_PRIVATE.get() and private_sdk)


@contextmanager
def private_sdk_download():
    """Suppress private SDK diagnostics in this counted-reader thread only."""
    names = set(_SDK_NAMES)
    names.update(name for name in logging.Logger.manager.loggerDict
                 if name.split('.', 1)[0] in _SDK_NAMES)
    loggers = [logging.getLogger(name) for name in names]
    for logger in loggers:
        if not any(isinstance(value, _SDKPrivacyFilter) for value in logger.filters):
            logger.addFilter(_SDKPrivacyFilter())
    # Ancestor logger filters do not run for child propagation. Handler filters
    # also cover SDK child loggers created during this one synchronous request.
    for logger in [logging.getLogger(), *loggers]:
        for handler in logger.handlers:
            if not any(isinstance(value, _SDKPrivacyFilter) for value in handler.filters):
                handler.addFilter(_SDKPrivacyFilter())
    token = _PRIVATE.set(True)
    try:
        yield
    finally:
        _PRIVATE.reset(token)


def _plain_parts(path: Path, io_path: Callable[[Path], Path], *, create_parent=False):
    """Reject links/reparse points on canonical components before private I/O."""
    path = Path(path)
    if '..' in path.parts:
        raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_INVALID')
    path = path.absolute()
    for part in reversed(path.parents):
        candidate = io_path(part)
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            if not create_parent:
                raise StorageDownloadNotFound() from None
            candidate.mkdir(exist_ok=True)
            info = candidate.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
            raise StorageDownloadError('STORAGE_DOWNLOAD_LINK_REJECTED')
        if not stat.S_ISDIR(info.st_mode):
            raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_INVALID')
    return io_path(path)


def guarded_source(path: Path, io_path: Callable[[Path], Path]) -> Path:
    source = _plain_parts(path, io_path)
    info = source.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
        raise StorageDownloadError('STORAGE_DOWNLOAD_LINK_REJECTED')
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_INVALID')
    return source


def guarded_destination(path: Path, io_path: Callable[[Path], Path]) -> Path:
    destination = _plain_parts(path, io_path, create_parent=True)
    try:
        info = destination.lstat()
    except FileNotFoundError:
        return destination
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
        raise StorageDownloadError('STORAGE_DOWNLOAD_LINK_REJECTED')
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_INVALID')
    return destination


def _identity(info):
    return info.st_dev, info.st_ino


def _admit_owned(temporary, identity, parent_identity, expected_size, io_path):
    try:
        path = _plain_parts(temporary, io_path)
        if _identity(path.parent.lstat()) != parent_identity:
            raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED')
        info = path.lstat()
    except FileNotFoundError:
        # A missing owned stage is not evidence that the source is missing.
        raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED') from None
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & 1024 or info.st_nlink != 1
            or _identity(info) != identity or info.st_size != expected_size):
        raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED')


def _verify_owned_bytes(temporary, identity, parent_identity, expected_size, expected_sha256,
                        io_path, control, deadline):
    """Recheck persisted bytes, including same-inode/same-size modification."""
    _admit_owned(temporary, identity, parent_identity, expected_size, io_path)
    checksum = hashlib.sha256()
    count = 0
    with temporary.open('rb') as persisted:
        if _identity(os.fstat(persisted.fileno())) != identity:
            raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED')
        while True:
            control.check()
            if _clock() >= deadline:
                raise StorageDownloadError('STORAGE_DOWNLOAD_TIMEOUT')
            block = persisted.read(min(BLOCK_BYTES, expected_size - count + 1))
            if not block:
                break
            count += len(block)
            if count > expected_size:
                raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED')
            checksum.update(block)
    if count != expected_size or checksum.hexdigest() != expected_sha256:
        raise StorageDownloadError('STORAGE_DOWNLOAD_STAGE_HASH_MISMATCH')
    _admit_owned(temporary, identity, parent_identity, expected_size, io_path)


def _cleanup_owned(temporary, identity, parent_identity, io_path):
    try:
        # Never unlink a replacement file or a path redirected after creation.
        path = _plain_parts(temporary, io_path)
        if _identity(path.parent.lstat()) != parent_identity:
            raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED')
        info = path.lstat()
        if (_identity(info) != identity or not stat.S_ISREG(info.st_mode)
                or getattr(info, 'st_file_attributes', 0) & 1024):
            raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED')
        path.unlink()
    except FileNotFoundError:
        return
    except StorageDownloadError:
        raise
    except OSError:
        raise StorageDownloadError('STORAGE_DOWNLOAD_CLEANUP_FAILED') from None


def counted_download(*, opener: Callable[[], tuple[BinaryIO, int]], destination: Path,
                     bounds: DownloadBounds, control: DownloadControl,
                     io_path: Callable[[Path], Path]):
    """Check actual bytes before writing; only verified bytes replace the target."""
    stream = None
    temporary = None
    created = False
    identity = parent_identity = None
    deadline = _clock() + READ_DEADLINE_SECONDS
    try:
        control.check()
        destination = guarded_destination(destination, io_path)
        parent_identity = _identity(destination.parent.lstat())
        stream, declared_size = opener()
        bounds.check_size(declared_size)
        if not callable(getattr(stream, 'read', None)) or not callable(getattr(stream, 'close', None)):
            raise StorageDownloadError('STORAGE_DOWNLOAD_STREAM_INVALID')
        ceiling = min(value for value in (declared_size, bounds.max_bytes, bounds.expected_size_bytes)
                      if value is not None)
        temporary = destination.with_name('.vf-object-' + uuid.uuid4().hex + '.tmp')
        digest = hashlib.sha256()
        count = 0
        with temporary.open('xb') as output:
            created = True
            identity = _identity(os.fstat(output.fileno()))
            while True:
                control.check()
                if _clock() >= deadline:
                    raise StorageDownloadError('STORAGE_DOWNLOAD_TIMEOUT')
                requested = min(BLOCK_BYTES, ceiling - count + 1)
                content = stream.read(requested)
                control.check()
                if _clock() >= deadline:
                    raise StorageDownloadError('STORAGE_DOWNLOAD_TIMEOUT')
                if not isinstance(content, bytes) or len(content) > requested:
                    raise StorageDownloadError('STORAGE_DOWNLOAD_STREAM_INVALID')
                if not content:
                    break
                count += len(content)
                if bounds.max_bytes is not None and count > bounds.max_bytes:
                    raise StorageDownloadError('STORAGE_DOWNLOAD_SIZE_LIMIT')
                if count > ceiling:
                    raise StorageDownloadError('STORAGE_DOWNLOAD_SIZE_MISMATCH')
                output.write(content)
                digest.update(content)
            if count != declared_size:
                raise StorageDownloadError('STORAGE_DOWNLOAD_SIZE_MISMATCH')
            bounds.check_size(count)
            if bounds.expected_sha256 is not None and digest.hexdigest() != bounds.expected_sha256:
                raise StorageDownloadError('STORAGE_DOWNLOAD_HASH_MISMATCH')
            stream.close()
            stream = None
            output.flush()
            os.fsync(output.fileno())
        # Recheck path custody immediately before atomic replacement.
        guarded_destination(destination, io_path)
        if _identity(destination.parent.lstat()) != parent_identity:
            raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED')
        if _clock() >= deadline:
            raise StorageDownloadError('STORAGE_DOWNLOAD_TIMEOUT')
        _verify_owned_bytes(temporary, identity, parent_identity, count, digest.hexdigest(),
            io_path, control, deadline)
        control.replace(temporary, destination, identity=identity,
            parent_identity=parent_identity, expected_size=count, io_path=io_path,
            reverify=lambda: _verify_owned_bytes(temporary, identity, parent_identity, count,
                digest.hexdigest(), io_path, control, deadline))
    except StorageDownloadError:
        raise
    except FileNotFoundError:
        raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED') from None
    except Exception:
        raise StorageDownloadError('STORAGE_DOWNLOAD_READ_FAILED') from None
    finally:
        if stream is not None:
            with suppress(Exception):
                stream.close()
        if created and temporary is not None:
            _cleanup_owned(temporary, identity, parent_identity, io_path)


def legacy_sdk_download(*, operation: Callable[[Path], None], destination: Path,
                        control: DownloadControl, io_path: Callable[[Path], Path]):
    """Existing no-bound SDK call; safely drain and keep replacement atomic."""
    temporary = None
    created = False
    identity = parent_identity = None
    try:
        control.check()
        destination = guarded_destination(destination, io_path)
        parent_identity = _identity(destination.parent.lstat())
        temporary = destination.with_name('.vf-object-' + uuid.uuid4().hex + '.tmp')
        with temporary.open('xb') as output:
            created = True
            identity = _identity(os.fstat(output.fileno()))
        operation(temporary)
        # Successful SDK transfer may atomically replace its requested private
        # target. Adopt its returned regular file once, before cancellation and
        # destination callbacks; failed/unknown transfers never adopt a new file.
        returned = guarded_source(temporary, io_path).lstat()
        identity = _identity(returned)
        control.check()
        guarded_destination(destination, io_path)
        if _identity(destination.parent.lstat()) != parent_identity:
            raise StorageDownloadError('STORAGE_DOWNLOAD_PATH_CHANGED')
        control.replace(temporary, destination, identity=identity,
            parent_identity=parent_identity, expected_size=returned.st_size, io_path=io_path)
    except StorageDownloadError:
        raise
    except Exception:
        raise StorageDownloadError('STORAGE_DOWNLOAD_READ_FAILED') from None
    finally:
        if created and temporary is not None:
            _cleanup_owned(temporary, identity, parent_identity, io_path)
