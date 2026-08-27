from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .models import StrictModel
from .platform_models import ProjectRead, ProjectVersionRead


BRIDGE_CONTRACT_VERSION = "agent-hub-bridge.v1"


class BridgeProjectRequestCreate(StrictModel):
    workspace_id: str | None = Field(default=None, pattern=r"^wsp_[A-Za-z0-9_-]{4,60}$")
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,80}$")
    name: str = Field(min_length=1, max_length=240)
    niche: str = Field(default="custom", min_length=1, max_length=80)
    source_campaign_id: str | None = Field(default=None, max_length=160)
    brief: dict[str, Any] = Field(default_factory=dict)
    execution_mode: Literal["draft_only"] = "draft_only"
    start_pipeline: Literal[False] = False
    publish_requested: Literal[False] = False
    external_action_requested: Literal[False] = False


class BridgeProjectRequestRead(StrictModel):
    request_id: str
    contract_version: Literal["agent-hub-bridge.v1"] = BRIDGE_CONTRACT_VERSION
    service_id: str
    workspace_id: str
    project_id: str | None
    project_version_id: str | None
    status: Literal["reserved", "succeeded", "failed"]
    request: dict[str, Any]
    result: dict[str, Any] | None
    failure_code: str | None
    failure_reason: str | None
    execution_started: Literal[False] = False
    external_action: Literal[False] = False
    created_at: datetime
    updated_at: datetime


class BridgeProjectCreatedResponse(StrictModel):
    bridge_request: BridgeProjectRequestRead
    project: ProjectRead
    project_version: ProjectVersionRead
    idempotent_replay: bool


class BridgeEventRead(StrictModel):
    event_id: str
    request_id: str
    project_id: str | None
    contract_version: Literal["agent-hub-bridge.v1"] = BRIDGE_CONTRACT_VERSION
    event_type: str
    payload: dict[str, Any]
    contains_secret: Literal[False] = False
    created_at: datetime


class WebhookDeliveryRead(StrictModel):
    delivery_id: str
    event_id: str
    destination_ref: str
    provider_mode: Literal["fixture", "http", "disabled"]
    status: Literal["queued", "running", "retry_scheduled", "succeeded", "not_configured", "failed"]
    attempt_count: int
    max_attempts: int
    key_id: str | None
    signed_at_unix: int | None
    body_sha256: str | None
    signature: str | None
    response_status: int | None
    receipt: dict[str, Any] | None
    failure_code: str | None
    failure_reason: str | None
    next_retry_at: datetime | None
    external_call: bool
    created_at: datetime
    updated_at: datetime


class BridgeProjectSummary(StrictModel):
    contract_version: Literal["agent-hub-bridge.v1"] = BRIDGE_CONTRACT_VERSION
    project: ProjectRead
    versions: int
    assets: int
    estimated_cost_vnd: str
    actual_cost_vnd: str
    publications: int
    analytics_snapshots: int
    execution_controlled_by_video_factory: Literal[True] = True
    external_action: Literal[False] = False


class BridgeContractRead(StrictModel):
    contract_version: Literal["agent-hub-bridge.v1"] = BRIDGE_CONTRACT_VERSION
    api_version: Literal["v1"] = "v1"
    service_auth: Literal["hmac-sha256"] = "hmac-sha256"
    webhook_auth: Literal["hmac-sha256-keyring"] = "hmac-sha256-keyring"
    inbound_actions: list[str]
    outbound_events: list[str]
    roles: list[str]
    execution_boundary: Literal["draft_only"] = "draft_only"
    agent_hub_runtime_dependency: Literal[False] = False
    shared_database: Literal[False] = False
    shared_redis: Literal[False] = False
    production_deployed: bool = False
