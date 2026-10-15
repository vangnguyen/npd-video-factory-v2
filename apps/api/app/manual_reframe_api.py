"""Human reviewed crop paths; no Vision/model execution or arbitrary metadata."""
from __future__ import annotations

import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field, field_validator, model_validator

from .human_auth import authorize_human_request, principal_from
from .models import StrictModel
from .source_linked_edit_api import SourceLinkedIdentity
from .timeline_models import TimelineRead


class ManualReframePoint(StrictModel):
    time: float = Field(ge=0, allow_inf_nan=False)
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    zoom: float = Field(ge=1, le=4, allow_inf_nan=False)

    @field_validator("time", "x", "y", "zoom", mode="before")
    @classmethod
    def finite_number(cls, value):
        try:
            valid = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("finite numeric crop coordinate required")
        return value


class ManualReframeSettings(StrictModel):
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"]
    points: list[ManualReframePoint] = Field(strict=True, min_length=1, max_length=200)

    @model_validator(mode="after")
    def increasing_source_times(self):
        if any(a.time >= b.time for a, b in zip(self.points, self.points[1:])):
            raise ValueError("crop source times must strictly increase")
        return self


class ManualReframeUpdate(ManualReframeSettings):
    expected_timeline_id: str = Field(strict=True, pattern=r"^tml_[A-Za-z0-9_-]{4,60}$")
    expected_version: int = Field(strict=True, ge=1)
    request_key: str = Field(strict=True, pattern=r"^[A-Za-z0-9_-]{8,128}$")
    acknowledged: bool = Field(strict=True)
    expected_source_binding_sha256: str = Field(strict=True, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def explicit_review(self):
        if self.acknowledged is not True:
            raise ValueError("acknowledge crop changes and invalidation of previous review")
        return self


class ManualReframeSource(SourceLinkedIdentity):
    width: int = Field(strict=True, ge=1)
    height: int = Field(strict=True, ge=1)
    fps: float = Field(gt=0, allow_inf_nan=False)


class ManualCropKeyframe(StrictModel):
    time: float = Field(ge=0, allow_inf_nan=False)
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def inside_source(self):
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("crop rectangle must stay inside measured source")
        return self


class ManualReframeReceipt(StrictModel):
    schema_version: Literal["manual-reframe-v1"]
    request_key: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    workspace_id: str
    project_id: str
    timeline_id: str
    parent_version_id: str
    parent_version: int = Field(ge=1)
    result_version: int = Field(ge=2)
    actor_ref: str
    source: ManualReframeSource
    settings: ManualReframeSettings
    applied_keyframes: list[ManualCropKeyframe] = Field(min_length=1, max_length=200)
    result_snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def one_canonical_version(self):
        if self.result_version != self.parent_version + 1:
            raise ValueError("manual reframe advances exactly one canonical version")
        if len(self.applied_keyframes) != len(self.settings.points) or any(
                a.time != b.time for a, b in zip(self.applied_keyframes, self.settings.points)):
            raise ValueError("applied crop times must match requested source times")
        return self


class ManualReframeRead(StrictModel):
    timeline: TimelineRead
    source: ManualReframeSource
    source_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    settings: ManualReframeSettings | None
    receipt: ManualReframeReceipt | None
    replayed: bool = False


router = APIRouter(prefix="/api/v1", tags=["manual-reframe"],
                   dependencies=[Depends(authorize_human_request)])


async def _command(request, project_id, payload=None):
    from .manual_reframe_command import ManualReframeConflict, apply_manual_reframe, read_manual_reframe
    service = getattr(request.app.state, "timeline_service", None)
    if service is None:
        raise HTTPException(503, detail={"code": "NOT_CONFIGURED"})
    try:
        value = await (read_manual_reframe(service, project_id) if payload is None else
            apply_manual_reframe(service, project_id, payload, actor_ref=principal_from(request).subject))
        return ManualReframeRead.model_validate(value)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "NOT_FOUND"}) from exc
    except ManualReframeConflict as exc:
        raise HTTPException(409, detail={"code": exc.code, "current_version": exc.current_version}) from exc


@router.get("/projects/{project_id}/timeline/manual-reframe", response_model=ManualReframeRead)
async def get_manual_reframe(project_id: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await _command(request, project_id)


@router.put("/projects/{project_id}/timeline/manual-reframe", response_model=ManualReframeRead)
async def put_manual_reframe(project_id: str, payload: ManualReframeUpdate, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await _command(request, project_id, payload)
