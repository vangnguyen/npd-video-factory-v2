from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from .config import Settings


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
    async def download_file(self, *, object_key: str, destination: Path) -> None: ...
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detected_content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class LocalObjectStorageProvider:
    name = "local"

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, object_key: str) -> Path:
        key = validate_object_key(object_key)
        candidate = (self.root / Path(*PurePosixPath(key).parts)).resolve()
        if self.root not in candidate.parents:
            raise ValueError("object key escaped local object store")
        return candidate

    async def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        probe = self.root / ".readyz"
        probe.write_bytes(b"ok")
        probe.unlink(missing_ok=True)

    async def put_file(self, *, object_key: str, path: Path, content_type: str | None = None) -> StoredObject:
        source = path.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination != source:
            await asyncio.to_thread(_copy_file, source, destination)
        return StoredObject(
            object_key=validate_object_key(object_key),
            checksum_sha256=sha256_file(source),
            size_bytes=source.stat().st_size,
            content_type=content_type or detected_content_type(source),
            storage_provider=self.name,
        )

    async def download_file(self, *, object_key: str, destination: Path) -> None:
        source = self._path(object_key)
        if not source.is_file():
            raise FileNotFoundError(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(_copy_file, source, destination)

    async def exists(self, *, object_key: str) -> bool:
        return self._path(object_key).is_file()


def _copy_file(source: Path, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


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
    ):
        self.bucket = bucket
        self.region = region
        self.auto_create_bucket = auto_create_bucket
        self.client: BaseClient = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
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
        source = path.resolve()
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

    async def download_file(self, *, object_key: str, destination: Path) -> None:
        key = validate_object_key(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        await asyncio.to_thread(self.client.download_file, self.bucket, key, str(temporary))
        temporary.replace(destination)

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
    )
