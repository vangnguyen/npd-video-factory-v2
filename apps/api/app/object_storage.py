from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import ntpath
import os
import uuid
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import Settings
from .bounded_storage_download import (
    DownloadBounds,
    StorageDownloadError,
    StorageDownloadNotFound,
    counted_download,
    drained_download,
    guarded_source,
    legacy_sdk_download,
    private_sdk_download,
)


OBJECT_KEY_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    checksum_sha256: str
    size_bytes: int
    content_type: str
    storage_provider: str


class ObjectStorageProvider(Protocol):
    name: str

    async def ensure_ready(self) -> None: ...
    async def put_file(self, *, object_key: str, path: Path, content_type: str | None = None) -> StoredObject: ...
    async def download_file(self, *, object_key: str, destination: Path,
                            max_bytes: int | None = None, expected_size_bytes: int | None = None,
                            expected_sha256: str | None = None, expected_prefix: str | None = None) -> None: ...
    async def exists(self, *, object_key: str) -> bool: ...


def validate_object_key(object_key: str) -> str:
    key = PurePosixPath(object_key)
    if key.is_absolute() or not key.parts or any(part in {"", ".", ".."} for part in key.parts):
        raise ValueError("invalid object key")
    if any(not OBJECT_KEY_SEGMENT.fullmatch(part) for part in key.parts):
        raise ValueError("invalid object key segment")
    normalized = key.as_posix()
    if len(normalized) > 768:
        raise ValueError("object key is too long")
    return normalized


def artifact_object_key(*, workspace_id: str, project_id: str, job_id: str, filename: str) -> str:
    return validate_object_key(
        f"workspaces/{workspace_id}/projects/{project_id}/jobs/{job_id}/{filename}"
    )


def extended_windows_path(name: str) -> str:
    """Normalize before the Win32 extended prefix; no machine policy change."""
    name = name.replace("/", "\\")
    if name.startswith("\\\\?\\UNC\\"):
        name = "\\\\" + name[8:]
    elif name.startswith("\\\\?\\"):
        name = name[4:]
    if name.startswith("\\\\.\\") or name.startswith("\\\\?\\"):
        raise ValueError("device namespaces are not filesystem paths")
    name = ntpath.normpath(name)
    drive, tail = ntpath.splitdrive(name)
    if not drive or not tail.startswith("\\"):
        raise ValueError("an absolute filesystem path is required")
    if drive.startswith("\\\\"):
        return "\\\\?\\UNC\\" + name[2:]
    if len(drive) != 2 or drive[1] != ":" or not drive[0].isalpha():
        raise ValueError("device namespaces are not filesystem paths")
    return "\\\\?\\" + name


def filesystem_path(path: Path) -> Path:
    """Private I/O path; portable object keys and public roots stay unchanged."""
    return Path(extended_windows_path(os.path.abspath(path))) if os.name == "nt" else path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with filesystem_path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detected_content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _download_bounds(object_key, max_bytes, expected_size_bytes, expected_sha256, expected_prefix):
    bounds = DownloadBounds(max_bytes, expected_size_bytes, expected_sha256)
    key = validate_object_key(object_key)
    if expected_prefix is not None:
        if not isinstance(expected_prefix, str) or not expected_prefix:
            raise StorageDownloadError('STORAGE_DOWNLOAD_INVALID_PREFIX')
        raw_prefix = expected_prefix.removesuffix('/')
        if any(part in {'', '.', '..'} for part in raw_prefix.split('/')):
            raise StorageDownloadError('STORAGE_DOWNLOAD_INVALID_PREFIX')
        try:
            prefix = validate_object_key(raw_prefix)
        except ValueError:
            raise StorageDownloadError('STORAGE_DOWNLOAD_INVALID_PREFIX') from None
        if key != prefix and not key.startswith(prefix + '/'):
            raise StorageDownloadError('STORAGE_DOWNLOAD_PREFIX_MISMATCH')
    return key, bounds


def bounded_download_request_config() -> Config:
    """Explicit profile for counted S3 requests; no configured client is changed."""
    return Config(connect_timeout=5, read_timeout=30, retries={'total_max_attempts': 1})


def _require_bounded_download_client(client):
    try:
        config = client.meta.config
        retries = config.retries or {}
        total = retries.get('total_max_attempts')
        maximum = retries.get('max_attempts')
        if (type(config.connect_timeout) not in {int, float} or not 0 < config.connect_timeout <= 5
                or type(config.read_timeout) not in {int, float} or not 0 < config.read_timeout <= 30
                or not (type(total) is int and total == 1
                        or ('total_max_attempts' not in retries and type(maximum) is int and maximum == 0))):
            raise StorageDownloadError('STORAGE_DOWNLOAD_SDK_PROFILE_REQUIRED')
    except (AttributeError, TypeError):
        raise StorageDownloadError('STORAGE_DOWNLOAD_SDK_PROFILE_REQUIRED') from None


class LocalObjectStorageProvider:
    name = "local"

    def __init__(self, root: Path):
        self._download_root = Path(root).absolute()
        self.root = root.resolve()
        self._io_root = filesystem_path(self.root).resolve()

    def _path(self, object_key: str) -> Path:
        key = validate_object_key(object_key)
        candidate = (self._io_root / Path(*PurePosixPath(key).parts)).resolve()
        if self._io_root not in candidate.parents:
            raise ValueError("object key escaped local object store")
        return candidate

    async def ensure_ready(self) -> None:
        self._io_root.mkdir(parents=True, exist_ok=True)
        probe = self._io_root / (".readyz-" + uuid.uuid4().hex)
        probe.write_bytes(b"ok")
        probe.unlink(missing_ok=True)

    async def put_file(self, *, object_key: str, path: Path, content_type: str | None = None) -> StoredObject:
        source = filesystem_path(path).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = self._path(object_key)
        destination = filesystem_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination != source:
            await asyncio.to_thread(_copy_file, source, destination)
        return StoredObject(
            object_key=validate_object_key(object_key),
            checksum_sha256=sha256_file(destination),
            size_bytes=destination.stat().st_size,
            content_type=content_type or detected_content_type(source),
            storage_provider=self.name,
        )

    async def download_file(self, *, object_key: str, destination: Path,
                            max_bytes: int | None = None, expected_size_bytes: int | None = None,
                            expected_sha256: str | None = None, expected_prefix: str | None = None) -> None:
        key, bounds = _download_bounds(object_key, max_bytes, expected_size_bytes, expected_sha256, expected_prefix)
        # Keep existing containment rules; inspect unresolved components as well
        # so an in-root symlink cannot disappear behind resolve().
        source = self._download_root / Path(*PurePosixPath(key).parts)
        def open_source():
            try:
                self._path(key)
                path = guarded_source(source, filesystem_path)
                stream = path.open('rb')
                try:
                    return stream, os.fstat(stream.fileno()).st_size
                except Exception:
                    stream.close()
                    raise
            except FileNotFoundError:
                raise StorageDownloadNotFound() from None
        await drained_download(lambda control: counted_download(opener=open_source, destination=destination,
            bounds=bounds, control=control, io_path=filesystem_path))

    async def exists(self, *, object_key: str) -> bool:
        return self._path(object_key).is_file()


def _copy_file(source: Path, destination: Path) -> None:
    source, destination = filesystem_path(source), filesystem_path(destination)
    temporary = destination.with_name(".vf-object-" + uuid.uuid4().hex + ".tmp")
    created = False
    try:
        with temporary.open("xb") as output:
            created = True
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
    finally:
        if created:
            temporary.unlink(missing_ok=True)


class S3ObjectStorageProvider:
    name = "s3"

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        auto_create_bucket: bool,
        request_config: Config | None = None,
    ):
        self.bucket = bucket
        self.region = region
        self.auto_create_bucket = auto_create_bucket
        client_options = {"config": request_config} if request_config is not None else {}
        self.client: BaseClient = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            **client_options,
        )

    async def ensure_ready(self) -> None:
        try:
            await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if not self.auto_create_bucket or code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            kwargs: dict[str, object] = {"Bucket": self.bucket}
            if self.region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
            await asyncio.to_thread(self.client.create_bucket, **kwargs)
            await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)

    async def put_file(self, *, object_key: str, path: Path, content_type: str | None = None) -> StoredObject:
        key = validate_object_key(object_key)
        source = filesystem_path(path).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        checksum = sha256_file(source)
        resolved_content_type = content_type or detected_content_type(source)
        await asyncio.to_thread(
            self.client.upload_file,
            str(source),
            self.bucket,
            key,
            ExtraArgs={
                "ContentType": resolved_content_type,
                "Metadata": {"sha256": checksum},
            },
        )
        return StoredObject(
            object_key=key,
            checksum_sha256=checksum,
            size_bytes=source.stat().st_size,
            content_type=resolved_content_type,
            storage_provider=self.name,
        )

    async def download_file(self, *, object_key: str, destination: Path,
                            max_bytes: int | None = None, expected_size_bytes: int | None = None,
                            expected_sha256: str | None = None, expected_prefix: str | None = None) -> None:
        key, bounds = _download_bounds(object_key, max_bytes, expected_size_bytes, expected_sha256, expected_prefix)
        constrained = any(value is not None for value in (max_bytes, expected_size_bytes, expected_sha256, expected_prefix))
        def missing_or_failed(error):
            if str(error.response.get('Error', {}).get('Code', '')) in {'404', 'NoSuchKey', 'NotFound'}:
                raise StorageDownloadNotFound() from None
            raise StorageDownloadError('STORAGE_DOWNLOAD_READ_FAILED') from None
        if not constrained:
            # Backwards compatible SDK signature only for explicitly unbounded
            # legacy callers. A constrained request never falls back here.
            def legacy(path):
                try:
                    self.client.download_file(self.bucket, key, str(path))
                except ClientError as error:
                    missing_or_failed(error)
            await drained_download(lambda control: legacy_sdk_download(
                operation=legacy,
                destination=destination, control=control, io_path=filesystem_path))
            return
        _require_bounded_download_client(self.client)
        def open_source():
            try:
                response = self.client.get_object(Bucket=self.bucket, Key=key)
            except ClientError as exc:
                missing_or_failed(exc)
            return response.get('Body'), response.get('ContentLength')
        def transfer(control):
            with private_sdk_download():
                counted_download(opener=open_source, destination=destination,
                    bounds=bounds, control=control, io_path=filesystem_path)
        await drained_download(transfer)

    async def exists(self, *, object_key: str) -> bool:
        key = validate_object_key(object_key)
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise


def create_object_storage(settings: Settings) -> ObjectStorageProvider:
    if settings.object_storage_provider == "local":
        return LocalObjectStorageProvider(settings.object_storage_local_root)
    return S3ObjectStorageProvider(
        endpoint_url=settings.object_storage_endpoint_url,
        bucket=settings.object_storage_bucket,
        region=settings.object_storage_region,
        access_key=settings.object_storage_access_key,
        secret_key=settings.object_storage_secret_key,
        auto_create_bucket=settings.object_storage_auto_create_bucket,
        request_config=bounded_download_request_config(),
    )
