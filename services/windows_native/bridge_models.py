"""Native DTOs under the shared Agent Hub v1 wire contract; no Hub internals."""
from typing import Literal
from pydantic import Field, StrictBool
from . import ingestion
from app.models import StrictModel


class NativeBridgeDraft(StrictModel):
    workspace_id: str = Field(pattern=r'^wsp_[A-Za-z0-9_-]{4,64}$')
    name: str = Field(min_length=1,max_length=150)
    input_kind: Literal['prompt','script','media'] = 'prompt'
    prompt: str = Field(default='',max_length=20000)
    niche: str = Field(default='custom',pattern=r'^[A-Za-z0-9_-]{1,80}$')
    channel_profile_ref: str | None = Field(default=None,max_length=100)
    execution_mode: Literal['draft_only'] = 'draft_only'
    start_pipeline: StrictBool = False
    publish_requested: StrictBool = False
    external_action_requested: StrictBool = False
