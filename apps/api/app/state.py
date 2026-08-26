from __future__ import annotations

from typing import Protocol

from .models import Artifact, JobError, JobRecord, JobStage, JobStatus, STAGE_ORDER


QUEUE_KEY = "npd:video-jobs:queue"


class JobStore(Protocol):
    async def create(self, record: JobRecord, *, idempotency_key: str | None = None) -> JobRecord: ...
    async def enqueue(self, job_id: str) -> None: ...
    async def get(self, job_id: str) -> JobRecord | None: ...
    async def update_stage(
        self, job_id: str, *, status: JobStatus, stage: JobStage, progress: int
    ) -> JobRecord: ...
    async def add_artifact(self, job_id: str, *, artifact: Artifact) -> JobRecord: ...
    async def fail(self, job_id: str, *, error: JobError) -> JobRecord: ...


def validate_transition(current: JobRecord, *, stage: JobStage, progress: int) -> None:
    if progress < current.progress:
        raise ValueError("job progress cannot decrease")
    if stage != JobStage.FAILED and STAGE_ORDER[stage] < STAGE_ORDER[current.stage]:
        raise ValueError("job stage cannot move backwards")
