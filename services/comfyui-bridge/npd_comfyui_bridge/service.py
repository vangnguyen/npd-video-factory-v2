from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from .backend import ComfyUIBackend
from .models import BridgeJobCreate, BridgeJobRead
from .workflows import WorkflowRegistry


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ComfyUIBridgeService:
    def __init__(self, registry: WorkflowRegistry, backend: ComfyUIBackend):
        self.registry = registry
        self.backend = backend
        self._jobs: dict[str, BridgeJobRead] = {}
        self._requests: dict[str, BridgeJobCreate] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def submit(self, payload: BridgeJobCreate) -> BridgeJobRead:
        if not self.backend.configured:
            raise RuntimeError("ComfyUI GPU backend is not configured")
        definition = self.registry.get(payload.workflow_id, payload.workflow_version)
        self.registry.validate_inputs(definition, payload.inputs)
        async with self._lock:
            existing = next(
                (item for item in self._jobs.values() if item.client_request_id == payload.client_request_id),
                None,
            )
            if existing:
                if self._requests[existing.job_id] != payload:
                    raise ValueError("client_request_id was reused with a different workflow request")
                return existing
            now = utc_now()
            job = BridgeJobRead(
                job_id=f"cui_{uuid.uuid4().hex[:24]}",
                workflow_id=definition.workflow_id,
                workflow_version=definition.version,
                client_request_id=payload.client_request_id,
                status="queued",
                progress=0,
                retry_count=0,
                result=None,
                error_code=None,
                failure_reason=None,
                created_at=now,
                updated_at=now,
            )
            self._jobs[job.job_id] = job
            self._requests[job.job_id] = payload
            self._cancel_events[job.job_id] = asyncio.Event()
            self._tasks[job.job_id] = asyncio.create_task(self._execute(job.job_id))
            return job

    async def get(self, job_id: str) -> BridgeJobRead | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> BridgeJobRead:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status in {"succeeded", "failed", "cancelled", "timed_out"}:
                return job
            self._cancel_events[job_id].set()
            task = self._tasks.get(job_id)
            if task:
                task.cancel()
            updated = job.model_copy(
                update={"status": "cancelled", "updated_at": utc_now(), "error_code": "CANCELLED"}
            )
            self._jobs[job_id] = updated
            return updated

    async def retry(self, job_id: str) -> BridgeJobRead:
        if not self.backend.configured:
            raise RuntimeError("ComfyUI GPU backend is not configured")
        previous_task: asyncio.Task | None = None
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status not in {"failed", "cancelled", "timed_out"}:
                raise ValueError("only failed, cancelled or timed-out jobs can be retried")
            previous_task = self._tasks.get(job_id)
        # A cancelled execution finalizes asynchronously. Wait outside the lock
        # so its cancellation handler cannot overwrite the new retry state.
        if previous_task and not previous_task.done():
            try:
                await previous_task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status not in {"failed", "cancelled", "timed_out"}:
                raise ValueError("job state changed before retry")
            updated = job.model_copy(
                update={
                    "status": "queued",
                    "progress": 0,
                    "retry_count": job.retry_count + 1,
                    "result": None,
                    "error_code": None,
                    "failure_reason": None,
                    "updated_at": utc_now(),
                }
            )
            self._jobs[job_id] = updated
            self._cancel_events[job_id] = asyncio.Event()
            self._tasks[job_id] = asyncio.create_task(self._execute(job_id))
            return updated

    async def _execute(self, job_id: str) -> None:
        try:
            async with self._lock:
                job = self._jobs[job_id]
                request = self._requests[job_id]
                definition = self.registry.get(job.workflow_id, job.workflow_version)
                self._jobs[job_id] = job.model_copy(
                    update={"status": "running", "progress": 5, "updated_at": utc_now()}
                )

            async def update_progress(value: int) -> None:
                async with self._lock:
                    current = self._jobs[job_id]
                    if current.status == "running":
                        self._jobs[job_id] = current.model_copy(
                            update={"progress": max(current.progress, min(95, value)), "updated_at": utc_now()}
                        )

            result = await asyncio.wait_for(
                self.backend.execute(
                    workflow=definition,
                    inputs=request.inputs,
                    progress=update_progress,
                    cancelled=self._cancel_events[job_id],
                ),
                timeout=definition.timeout_seconds,
            )
            self.registry.validate_output(definition, result)
            async with self._lock:
                current = self._jobs[job_id]
                if current.status != "cancelled":
                    self._jobs[job_id] = current.model_copy(
                        update={
                            "status": "succeeded",
                            "progress": 100,
                            "result": result,
                            "updated_at": utc_now(),
                        }
                    )
        except asyncio.TimeoutError:
            await self._fail(job_id, "TIMEOUT", "ComfyUI workflow timed out", status="timed_out")
        except asyncio.CancelledError:
            async with self._lock:
                current = self._jobs.get(job_id)
                if current and current.status != "cancelled":
                    self._jobs[job_id] = current.model_copy(
                        update={"status": "cancelled", "error_code": "CANCELLED", "updated_at": utc_now()}
                    )
        except Exception as exc:
            await self._fail(job_id, "EXECUTION_FAILED", str(exc))

    async def _fail(self, job_id: str, code: str, reason: str, *, status: str = "failed") -> None:
        async with self._lock:
            current = self._jobs[job_id]
            self._jobs[job_id] = current.model_copy(
                update={
                    "status": status,
                    "error_code": code,
                    "failure_reason": reason[:1000],
                    "updated_at": utc_now(),
                }
            )
