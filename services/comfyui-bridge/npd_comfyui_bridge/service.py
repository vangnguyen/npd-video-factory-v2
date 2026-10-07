from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from .backend import ComfyUIBackend
from .models import BridgeJobCreate, BridgeJobRead
from .job_store import SQLiteBridgeJobStore, checksum, encoded
from .workflows import WorkflowRegistry


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ComfyUIBridgeService:
    def __init__(self, registry: WorkflowRegistry, backend: ComfyUIBackend, *,
                 job_store: SQLiteBridgeJobStore | None = None, max_concurrent_jobs=1,
                 max_queued_jobs=32, max_retries=3):
        if (type(max_concurrent_jobs) is not int or not 1 <= max_concurrent_jobs <= 8 or
                type(max_queued_jobs) is not int or not 1 <= max_queued_jobs <= 200 or
                type(max_retries) is not int or not 0 <= max_retries <= 10):
            raise ValueError('BRIDGE_QUEUE_BOUNDS_INVALID')
        self.registry = registry
        self.backend = backend
        self.job_store = job_store
        self.max_queued_jobs = max_queued_jobs
        self.max_concurrent_jobs = max_concurrent_jobs
        self.max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self._closing = False
        self._jobs: dict[str, BridgeJobRead] = {}
        self._requests: dict[str, BridgeJobCreate] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        if job_store:
            for job, request in job_store.load():
                self._jobs[job.job_id] = job
                self._requests[job.job_id] = request
                if job.status in {'running', 'queued'}:
                    self._set_job(job.model_copy(update={'status': 'failed', 'error_code': 'RECOVERY_REQUIRED',
                        'recovery_required': True, 'failure_reason': 'Interrupted execution requires explicit review and retry.',
                        'updated_at': utc_now()}))

    def _set_job(self, job):
        if self.job_store:
            self.job_store.save(job, self._requests[job.job_id])
        self._jobs[job.job_id] = job.model_copy(deep=True)

    def _check_capacity(self):
        if self._closing:
            raise RuntimeError('BRIDGE_SHUTTING_DOWN')
        active = sum(job.status in {'queued', 'running'} for job in self._jobs.values())
        if active >= self.max_concurrent_jobs + self.max_queued_jobs:
            raise RuntimeError('BRIDGE_QUEUE_FULL')

    async def submit(self, payload: BridgeJobCreate) -> BridgeJobRead:
        encoded(payload.model_dump(mode='json'))
        definition = self.registry.get(payload.workflow_id, payload.workflow_version)
        self.registry.validate_inputs(definition, payload.inputs)
        async with self._lock:
            existing = next(
                (item for item in self._jobs.values() if item.client_request_id == payload.client_request_id and item.workspace_id == payload.workspace_id),
                None,
            )
            if existing:
                if self._requests[existing.job_id] != payload:
                    raise ValueError("client_request_id was reused with a different workflow request")
                return existing.model_copy(deep=True)
            if not self.backend.configured:
                raise RuntimeError("ComfyUI GPU backend is not configured")
            self._check_capacity()
            if len(self._jobs) >= 5000:
                raise RuntimeError('BRIDGE_STORE_LIMIT_REACHED')
            now = utc_now()
            job = BridgeJobRead(
                workspace_id=payload.workspace_id,
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
                definition_sha256=self.registry.fingerprint(definition),
            )
            self._requests[job.job_id] = payload.model_copy(deep=True)
            try:
                self._set_job(job)
            except Exception:
                self._requests.pop(job.job_id, None)
                raise
            self._cancel_events[job.job_id] = asyncio.Event()
            self._tasks[job.job_id] = asyncio.create_task(self._execute(job.job_id))
            return job.model_copy(deep=True)

    async def get(self, job_id: str) -> BridgeJobRead | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    async def list_jobs(self, *, limit=100, workspace_id=None):
        async with self._lock:
            jobs = sorted((j for j in self._jobs.values() if workspace_id is None or j.workspace_id == workspace_id),
                key=lambda j: (j.created_at, j.job_id), reverse=True)
            return [job.model_copy(deep=True) for job in jobs[:min(200, max(1, limit))]]

    async def events(self, job_id):
        async with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self.job_store.events(job_id) if self.job_store else []

    async def cancel(self, job_id: str) -> BridgeJobRead:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status in {"succeeded", "failed", "cancelled", "timed_out"}:
                return job.model_copy(deep=True)
            updated = job.model_copy(
                update={"status": "cancelled", "updated_at": utc_now(), "error_code": "CANCELLED"}
            )
            self._set_job(updated)
            self._cancel_events[job_id].set()
            task = self._tasks.get(job_id)
            if task:
                task.cancel()
            return updated.model_copy(deep=True)

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
            self._check_capacity()
            if job.retry_count >= self.max_retries:
                raise ValueError('BRIDGE_RETRY_LIMIT_REACHED')
            definition = self.registry.get(job.workflow_id, job.workflow_version)
            if self.registry.fingerprint(definition) != job.definition_sha256:
                raise ValueError('APPROVED_WORKFLOW_CHANGED')
            updated = job.model_copy(
                update={
                    "status": "queued",
                    "progress": 0,
                    "retry_count": job.retry_count + 1,
                    "result": None,
                    "error_code": None,
                    "failure_reason": None,
                    "updated_at": utc_now(),
                    "result_metadata_sha256": None,
                    "recovery_required": False,
                }
            )
            self._set_job(updated)
            self._cancel_events[job_id] = asyncio.Event()
            self._tasks[job_id] = asyncio.create_task(self._execute(job_id))
            return updated.model_copy(deep=True)

    async def _execute(self, job_id: str) -> None:
        acquired = False
        try:
            await self._semaphore.acquire()
            acquired = True
            async with self._lock:
                job = self._jobs[job_id]
                if job.status != 'queued' or self._closing:
                    return
                request = self._requests[job_id].model_copy(deep=True)
                definition = self.registry.get(job.workflow_id, job.workflow_version).model_copy(deep=True)
                if self.registry.fingerprint(definition) != job.definition_sha256:
                    raise ValueError('APPROVED_WORKFLOW_CHANGED')
                self._set_job(job.model_copy(
                    update={"status": "running", "progress": 5, "updated_at": utc_now()}
                ))

            async def update_progress(value: int) -> None:
                async with self._lock:
                    current = self._jobs[job_id]
                    if type(value) is not int:
                        raise ValueError('BRIDGE_PROGRESS_INVALID')
                    progress = max(current.progress, min(95, value))
                    if current.status == "running" and current.retry_count == job.retry_count and progress != current.progress:
                        self._set_job(current.model_copy(update={"progress": progress, "updated_at": utc_now()}))

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
            result_hash = checksum(result)
            if self.registry.fingerprint(definition) != job.definition_sha256:
                raise ValueError('APPROVED_WORKFLOW_CHANGED')
            async with self._lock:
                current = self._jobs[job_id]
                if current.status == "running" and not self._closing and current.retry_count == job.retry_count:
                    self._set_job(current.model_copy(
                        update={
                            "status": "succeeded",
                            "progress": 100,
                            "result": result,
                            "result_metadata_sha256": result_hash,
                            "updated_at": utc_now(),
                        }
                    ))
        except asyncio.TimeoutError:
            await self._fail(job_id, "TIMEOUT", "ComfyUI workflow timed out", status="timed_out")
        except asyncio.CancelledError:
            async with self._lock:
                current = self._jobs.get(job_id)
                if current and current.status != "cancelled":
                    self._set_job(current.model_copy(update={
                        'status': 'failed' if self._closing else 'cancelled',
                        'error_code': 'RECOVERY_REQUIRED' if self._closing else 'CANCELLED',
                        'recovery_required': self._closing, 'updated_at': utc_now()}))
        except Exception:
            await self._fail(job_id, "EXECUTION_FAILED", 'Workflow execution or result validation failed.')
        finally:
            if acquired:
                self._semaphore.release()

    async def _fail(self, job_id: str, code: str, reason: str, *, status: str = "failed") -> None:
        async with self._lock:
            current = self._jobs[job_id]
            if current.status == 'cancelled':
                return
            self._set_job(current.model_copy(
                update={
                    "status": status,
                    "error_code": code,
                    "failure_reason": reason[:1000],
                    "updated_at": utc_now(),
                }
            ))

    async def close(self):
        async with self._lock:
            if self._closing:
                return
            self._closing = True
            tasks = list(self._tasks.values())
            for task in tasks:
                if not task.done():
                    task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        async with self._lock:
            for job in list(self._jobs.values()):
                if job.status in {'queued', 'running'}:
                    self._set_job(job.model_copy(update={'status': 'failed', 'error_code': 'RECOVERY_REQUIRED',
                        'recovery_required': True, 'updated_at': utc_now()}))
            if self.job_store:
                self.job_store.close()
