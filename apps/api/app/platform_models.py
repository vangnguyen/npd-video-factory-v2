from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from .models import StrictModel


WorkspaceId = str
ProjectId = str
ProjectVersionId = str


class WorkspaceCreate(StrictModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(min_length=1, max_length=200)
    owner_ref: str = Field(min_length=1, max_length=160)
    provenance: dict[str, Any] = Field(default_factory=dict)


class WorkspaceRead(StrictModel):
    workspace_id: WorkspaceId
    slug: str
    name: str
    owner_ref: str
    version: int
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProjectCreate(StrictModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,80}$")
    name: str = Field(min_length=1, max_length=240)
    niche: str = Field(default="custom", min_length=1, max_length=80)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ProjectRead(StrictModel):
    project_id: ProjectId
    workspace_id: WorkspaceId
    slug: str
    name: str
    niche: str
    status: str
    current_version_id: ProjectVersionId | None
    version: int
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProjectVersionCreate(StrictModel):
    label: str = Field(default="draft", min_length=1, max_length=120)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ProjectVersionRead(StrictModel):
    project_version_id: ProjectVersionId
    workspace_id: WorkspaceId
    project_id: ProjectId
    ordinal: int
    label: str
    snapshot: dict[str, Any]
    source_job_id: str | None
    version: int
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AssetRegister(StrictModel):
    project_version_id: ProjectVersionId | None = None
    asset_class: Literal["source", "generated", "stock", "render", "metadata"]
    kind: str = Field(min_length=1, max_length=64)
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    object_key: str = Field(min_length=1, max_length=768)
    content_type: str = Field(default="application/octet-stream", max_length=160)
    size_bytes: int = Field(ge=0)
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    storage_provider: str = Field(min_length=1, max_length=80)
    provenance: dict[str, Any] = Field(default_factory=dict)


class AssetRead(StrictModel):
    asset_id: str
    workspace_id: WorkspaceId
    project_id: ProjectId
    project_version_id: ProjectVersionId | None
    job_id: str | None
    asset_class: str
    kind: str
    filename: str
    object_key: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    storage_provider: str
    version: int
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProviderRead(StrictModel):
    provider_id: str
    workspace_id: WorkspaceId | None
    provider_key: str
    display_name: str
    capability: str
    adapter: str
    routing_mode: Literal["primary", "fallback", "disabled"]
    status: Literal["healthy", "degraded", "unavailable", "not_configured"]
    enabled: bool
    supports_dry_run: bool
    config_ref: str | None
    version: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProviderUsageRead(StrictModel):
    usage_id: str
    workspace_id: WorkspaceId
    project_id: ProjectId | None
    job_id: str | None
    provider_id: str
    provider_key: str
    capability: str
    model: str | None
    operation: str
    units: Decimal | None
    unit_name: str | None
    status: str
    metadata: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None


class CostRecordRead(StrictModel):
    cost_id: str
    workspace_id: WorkspaceId
    project_id: ProjectId | None
    job_id: str | None
    provider_usage_id: str
    estimated_cost: Decimal | None
    actual_cost: Decimal | None
    currency: Literal["VND"]
    needs_approval: bool
    approved: bool
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProjectCostSummary(StrictModel):
    project_id: ProjectId
    currency: Literal["VND"] = "VND"
    estimated_cost: Decimal
    actual_cost: Decimal
    unpriced_operations: int
    needs_approval: bool
    records: int


class JobEventRead(StrictModel):
    event_id: str
    job_id: str
    workspace_id: WorkspaceId | None
    event_type: str
    from_status: str | None
    to_status: str | None
    from_stage: str | None
    to_stage: str | None
    from_progress: int | None
    to_progress: int | None
    actor_ref: str
    payload: dict[str, Any]
    created_at: datetime


class JobContext(StrictModel):
    workspace_id: WorkspaceId
    project_id: ProjectId
    project_version_id: ProjectVersionId
