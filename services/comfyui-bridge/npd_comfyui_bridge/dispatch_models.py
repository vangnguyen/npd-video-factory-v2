"""Private bridge journal contains hashes and identities, never prompt bodies."""
from datetime import datetime
from typing import Literal
from pydantic import Field, StrictBool, StrictInt
from .model_base import StrictModel


class PromptDispatch(StrictModel):
    schema_version: Literal['comfy-http-dispatch-v1'] = 'comfy-http-dispatch-v1'
    workspace_id: str = Field(min_length=1, max_length=200, pattern=r'^\S+$')
    job_id: str = Field(pattern=r'^cui_[a-zA-Z0-9_-]{1,80}$')
    retry_count: StrictInt = Field(ge=0, le=10)
    prompt_id: str = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    binding_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    graph_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    inputs_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    state: Literal['dispatching', 'submitted', 'uncertain', 'not_submitted', 'completed', 'failed', 'cancelled']
    cancel_attempted: StrictBool = False
    artifact_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    artifact_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    adapter_elapsed_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    created_at: datetime
    updated_at: datetime
