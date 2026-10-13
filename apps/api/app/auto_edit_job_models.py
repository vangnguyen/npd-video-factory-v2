"""Explicit asynchronous video recognition; job completion is human review."""
from typing import Literal
from pydantic import Field
from .models import StrictModel, JobRecord
from .auto_edit_models import AutoEditAnalysisRequest, AutoEditAnalysisRead


class AutoEditJobCreate(StrictModel):
    configuration: AutoEditAnalysisRequest
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    idempotency_key: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$')


class AutoEditJobRead(StrictModel):
    schema_version: Literal['auto-edit-analysis-job.v1'] = 'auto-edit-analysis-job.v1'
    job: JobRecord
    analysis: AutoEditAnalysisRead
    source_sha256: str
    custody_sha256: str
    human_review_required: Literal[True] = True
    source_media_mutated: Literal[False] = False
    timeline_mutated: Literal[False] = False
    publishing_enabled: Literal[False] = False
