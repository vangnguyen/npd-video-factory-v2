"""Explicit human-only SQL source-shot linking; no queue or provider dispatch."""
from __future__ import annotations

import math
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field, model_validator

from .human_auth import authorize_human_request, principal_from
from .models import StrictModel
from .timeline_models import TimelineOperation, TimelineRead


class SourceLinkedOperation(TimelineOperation):
    @model_validator(mode="before")
    @classmethod
    def explicit_arguments(cls, value):
        if not isinstance(value, dict):
            return value
        allowed = {"trim": {"source_start", "source_end"}, "split": {"at_seconds"},
            "move": {"timeline_start"}, "delete": set(), "reorder": {"target_index"},
            "disable": {"disabled"}, "duplicate": {"timeline_start"},
            "set_clip_properties": {"speed", "opacity", "crop", "transform", "transition_in", "transition_out", "effects"}}
        kind = value.get("type")
        fields = allowed.get(kind) if isinstance(kind, str) else None
        if fields is None or set(value) - {"type", "clip_id"} - fields:
            raise ValueError("unsupported linked source operation arguments")
        for name, item in value.items():
            if name in {"type", "clip_id"}:
                if not isinstance(item, str):
                    raise ValueError("string operation identity required")
            elif name == "disabled":
                if type(item) is not bool:
                    raise ValueError("disabled requires a boolean")
            elif name == "target_index":
                if type(item) is not int:
                    raise ValueError("target_index requires an integer")
            elif name in {"source_start", "source_end", "at_seconds", "timeline_start", "speed", "opacity"}:
                try:
                    finite = type(item) in (int, float) and math.isfinite(item)
                except OverflowError:
                    finite = False
                if not finite:
                    raise ValueError("finite numeric operation argument required")
                if name == "speed" and item < .1:
                    raise ValueError("linked source audio speed must be at least 0.1")
            elif name in {"crop", "transform"} and isinstance(item, dict):
                for coordinate in item.values():
                    try:
                        finite = type(coordinate) in (int, float) and math.isfinite(coordinate)
                    except OverflowError:
                        finite = False
                    if not finite:
                        raise ValueError("finite numeric coordinate required")
        return value


class SourceLinkedUpdate(StrictModel):
    expected_timeline_id: str = Field(strict=True, pattern=r"^tml_[A-Za-z0-9_-]{4,60}$")
    expected_version: int = Field(strict=True, ge=1)
    request_key: str = Field(strict=True, pattern=r"^[A-Za-z0-9_-]{8,128}$")
    acknowledged: bool = Field(strict=True)
    operations: list[SourceLinkedOperation] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def reviewed(self):
        if not self.acknowledged:
            raise ValueError("acknowledge linked audio/caption changes and invalidation of the old review")
        return self


class SourceLinkedIdentity(StrictModel):
    analysis_id: str
    analysis_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    asset_id: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    object_key: str = Field(min_length=1, max_length=768)
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    has_audio: bool = Field(strict=True)
    transcript_id: str | None
    transcript_version: int | None = Field(ge=1)
    transcript_sha256: str | None = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def transcript_binding(self):
        values = (self.transcript_id, self.transcript_version, self.transcript_sha256)
        if any(v is None for v in values) and not all(v is None for v in values):
            raise ValueError("complete selected transcript identity required")
        return self


class SourceLinkedReceipt(StrictModel):
    schema_version: Literal["source-linked-edit-v1"]
    request_key: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    workspace_id: str
    project_id: str
    timeline_id: str
    parent_version_id: str
    parent_version: int = Field(ge=1)
    result_version: int = Field(ge=2)
    actor_ref: str
    source: SourceLinkedIdentity
    requested_operations: list[dict[str, Any]]
    applied_operations: list[dict[str, Any]]
    result_snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def one_canonical_version(self):
        if self.result_version != self.parent_version + 1:
            raise ValueError("linked edit advances exactly one canonical version")
        return self


class SourceLinkedRead(StrictModel):
    timeline: TimelineRead
    receipt: SourceLinkedReceipt | None
    replayed: bool = False


router = APIRouter(prefix="/api/v1", tags=["source-linked-edit"],
                   dependencies=[Depends(authorize_human_request)])


async def _command(request, project_id, payload=None):
    from .source_linked_edit_command import SourceLinkedConflict, apply_source_linked_edit, read_source_linked_edit
    service = getattr(request.app.state, "timeline_service", None)
    if service is None:
        raise HTTPException(503, detail={"code": "NOT_CONFIGURED"})
    try:
        result = await (read_source_linked_edit(service, project_id) if payload is None else
            apply_source_linked_edit(service, project_id, payload, actor_ref=principal_from(request).subject))
        return SourceLinkedRead.model_validate(result)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "NOT_FOUND"}) from exc
    except SourceLinkedConflict as exc:
        raise HTTPException(409, detail={"code": exc.code, "current_version": exc.current_version}) from exc


@router.get("/projects/{project_id}/timeline/source-linked-edit", response_model=SourceLinkedRead)
async def get_linked_edit(project_id: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await _command(request, project_id)


@router.put("/projects/{project_id}/timeline/source-linked-edit", response_model=SourceLinkedRead)
async def put_linked_edit(project_id: str, payload: SourceLinkedUpdate, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await _command(request, project_id, payload)
