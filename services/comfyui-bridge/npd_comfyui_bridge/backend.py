from __future__ import annotations

import asyncio
import hashlib
from typing import Awaitable, Callable, Protocol

from .models import WorkflowDefinition


ProgressCallback = Callable[[int], Awaitable[None]]


class ComfyUIBackend(Protocol):
    configured: bool

    async def execute(
        self,
        *,
        workflow: WorkflowDefinition,
        inputs: dict,
        progress: ProgressCallback,
        cancelled: asyncio.Event,
    ) -> dict: ...


class DisabledComfyUIBackend:
    configured = False

    async def execute(self, **kwargs) -> dict:
        raise RuntimeError("ComfyUI GPU backend is not configured")


class DeterministicMockComfyUIBackend:
    configured = True

    def __init__(self, *, delay_seconds: float = 0.01, fail: bool = False):
        self.delay_seconds = delay_seconds
        self.fail = fail

    async def execute(
        self,
        *,
        workflow: WorkflowDefinition,
        inputs: dict,
        progress: ProgressCallback,
        cancelled: asyncio.Event,
    ) -> dict:
        for value in (15, 45, 80):
            if cancelled.is_set():
                raise asyncio.CancelledError
            await asyncio.sleep(self.delay_seconds)
            await progress(value)
        if self.fail:
            raise RuntimeError("deterministic mock backend failure")
        token = hashlib.sha256(
            f"{workflow.workflow_id}|{workflow.version}|{sorted(inputs.items())}".encode("utf-8")
        ).hexdigest()
        return {
            "artifact_reference": f"fixture://comfyui/{workflow.workflow_id}/{token[:24]}",
            "checksum_sha256": token,
            "workflow_id": workflow.workflow_id,
            "workflow_version": workflow.version,
            "fixture": True,
        }
