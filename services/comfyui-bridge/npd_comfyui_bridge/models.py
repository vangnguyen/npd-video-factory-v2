from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowDefinition(StrictModel):
    workflow_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,80}$")
    version: str = Field(min_length=1, max_length=40)
    graph_file: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    capability: Literal[
        "text_to_image",
        "image_to_image",
        "inpainting",
        "outpainting",
        "upscale",
        "background_replacement",
        "image_to_video",
        "video_generation",
    ]
    required_custom_nodes: list[str]
    required_model_identifiers: list[str]
    vram_expectation_gb: float = Field(gt=0, le=256)
    timeout_seconds: float = Field(default=300, gt=0, le=7200)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class WorkflowManifest(StrictModel):
    manifest_version: str
    workflows: list[WorkflowDefinition]


class BridgeJobCreate(StrictModel):
    workflow_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,80}$")
    workflow_version: str | None = Field(default=None, max_length=40)
    inputs: dict[str, Any]
    client_request_id: str = Field(min_length=4, max_length=160)


class BridgeJobRead(StrictModel):
    job_id: str
    workflow_id: str
    workflow_version: str
    client_request_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled", "timed_out"]
    progress: int = Field(ge=0, le=100)
    retry_count: int = Field(ge=0)
    result: dict[str, Any] | None
    error_code: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
