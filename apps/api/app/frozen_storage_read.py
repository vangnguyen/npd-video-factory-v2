"""Server-owned byte proofs for bounded reads; no provider or authority transfer."""
import asyncio
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .object_storage import validate_object_key

MAX_SOURCE_BYTES = 2 * 1024**3


class FrozenReadRejected(ValueError):
    def __init__(self, code='STORAGE_READ_PROOF_INVALID'):
        self.code = code
        super().__init__(code)


async def completed_read(awaitable, *, dispose_cancelled_result=None, cancel_operation=False):
    """Drain owned I/O through repeated cancellation before caller cleanup."""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        if cancel_operation and not task.done():
            # Bounded storage owns its thread drain and stop flag. Cancel once;
            # subsequent caller cancellation must not interrupt that drain.
            task.cancel()
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            error = task.exception()  # Retrieve a drained worker's failure.
            if error is None and dispose_cancelled_result is not None:
                dispose_cancelled_result(task.result())
        raise


@dataclass(frozen=True)
class FrozenStorageRead:
    object_key: str
    workspace_id: str
    project_id: str
    size_bytes: int
    checksum_sha256: str
    storage_provider: str
    maximum: int

    def __post_init__(self):
        if (type(self.maximum) is not int or not 0 < self.maximum <= MAX_SOURCE_BYTES
            or type(self.size_bytes) is not int or not 0 < self.size_bytes <= self.maximum
            or not isinstance(self.checksum_sha256, str)
            or re.fullmatch('[a-f0-9]{64}', self.checksum_sha256) is None
            or any(not isinstance(value, str) or not value for value in
                (self.object_key, self.workspace_id, self.project_id, self.storage_provider))
            or any('/' in value or '\\' in value for value in (self.workspace_id, self.project_id))):
            raise FrozenReadRejected()
        try:
            key = validate_object_key(self.object_key)
        except (TypeError, ValueError):
            raise FrozenReadRejected() from None
        if key != self.object_key or not key.startswith(self.prefix):
            raise FrozenReadRejected('STORAGE_READ_SCOPE_CHANGED')

    @property
    def prefix(self):
        return f'workspaces/{self.workspace_id}/projects/{self.project_id}/'

    async def download(self, storage, destination):
        if storage.name != self.storage_provider:
            raise FrozenReadRejected('STORAGE_READ_PROVIDER_CHANGED')
        # An adapter with an old signature fails closed; never retry unbounded.
        await completed_read(storage.download_file(object_key=self.object_key, destination=Path(destination),
            max_bytes=self.maximum, expected_size_bytes=self.size_bytes,
            expected_sha256=self.checksum_sha256, expected_prefix=self.prefix), cancel_operation=True)


def asset_custody(asset):
    """Freeze metadata as values, without keeping a mutable ORM/DTO reference."""
    try:
        value = {name:copy.deepcopy(getattr(asset, name)) for name in (
            'asset_id', 'workspace_id', 'project_id', 'project_version_id', 'asset_class', 'kind',
            'object_key', 'storage_provider', 'content_type', 'size_bytes', 'checksum_sha256', 'version')}
        provenance = json.dumps(asset.provenance, ensure_ascii=False, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()
        value['provenance_sha256'] = hashlib.sha256(provenance).hexdigest()
        return value
    except (AttributeError, TypeError, ValueError, RecursionError):
        raise FrozenReadRejected() from None


def frozen_asset_read(asset, *, workspace_id, project_id, storage, maximum):
    if asset.workspace_id != workspace_id or asset.project_id != project_id:
        raise FrozenReadRejected('STORAGE_READ_SCOPE_CHANGED')
    value = FrozenStorageRead(asset.object_key, workspace_id, project_id, asset.size_bytes,
        asset.checksum_sha256, asset.storage_provider, maximum)
    if value.storage_provider != storage.name:
        raise FrozenReadRejected('STORAGE_READ_PROVIDER_CHANGED')
    return value
