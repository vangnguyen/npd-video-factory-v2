"""Explicit, provider-free editing of the canonical source audio configuration.

The application must register this router. Its own admission dependency preserves
human authentication and the write emergency switch even when mounted alone.
"""
from __future__ import annotations

import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field, model_validator

from .human_auth import authorize_human_request, principal_from
from .models import StrictModel
from .timeline_models import TimelineRead
from .timeline_audio_processing import AudioProcessing


class ProcessingConfiguration(AudioProcessing):
    @model_validator(mode="before")
    @classmethod
    def explicit_types(cls, values):
        if isinstance(values, dict):
            boolean_fields = {"normalize_original_audio", "normalize_music", "duck_music"}
            for name, value in values.items():
                if name in boolean_fields:
                    if type(value) is not bool:
                        raise ValueError(f"{name} requires a boolean")
                elif name in cls.model_fields:
                    try:
                        finite = type(value) in {int, float} and math.isfinite(value)
                    except OverflowError:
                        finite = False
                    if not finite:
                        raise ValueError(f"{name} requires a finite number")
        return values


class ProcessingUpdate(StrictModel):
    expected_timeline_id: str = Field(pattern=r"^tml_[A-Za-z0-9_-]{4,60}$")
    expected_version: int = Field(strict=True, ge=1)
    request_key: str = Field(strict=True, pattern=r"^[A-Za-z0-9_-]{8,128}$")
    configuration: ProcessingConfiguration
    acknowledged: bool = Field(strict=True)

    @model_validator(mode="after")
    def explicit_acknowledgement(self):
        if not self.acknowledged:
            raise ValueError("Acknowledge invalidation of preview and production review")
        return self


class ProcessingReceipt(StrictModel):
    schema_version: Literal["source-audio-processing-v1"]
    request_key: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    workspace_id: str
    project_id: str
    timeline_id: str
    parent_version: int
    result_version: int
    actor_ref: str
    configuration: ProcessingConfiguration


class ProcessingRead(StrictModel):
    timeline: TimelineRead
    configuration: ProcessingConfiguration
    locked_audio_track_ids: list[str]
    receipt: ProcessingReceipt | None = None
    replayed: bool = False


router = APIRouter(prefix="/api/v1", tags=["source-audio-processing"],
                   dependencies=[Depends(authorize_human_request)])


def _service(request):
    service = getattr(request.app.state, "timeline_service", None)
    if service is None:
        raise HTTPException(503, detail={"code": "NOT_CONFIGURED"})
    return service


async def _command(request, project_id, payload=None):
    from .timeline_audio_processing_command import ProcessingConflict, apply_processing, read_processing
    try:
        if payload is None:
            value = await read_processing(_service(request), project_id)
        else:
            value = await apply_processing(_service(request), project_id, payload,
                                           actor_ref=principal_from(request).subject)
        return ProcessingRead.model_validate(value)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "NOT_FOUND"}) from exc
    except ProcessingConflict as exc:
        raise HTTPException(409, detail={"code": exc.code,
                                        "current_version": exc.current_version}) from exc


@router.get("/projects/{project_id}/timeline/audio-processing", response_model=ProcessingRead)
async def get_processing(project_id: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await _command(request, project_id)


@router.put("/projects/{project_id}/timeline/audio-processing", response_model=ProcessingRead)
async def update_processing(project_id: str, payload: ProcessingUpdate, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await _command(request, project_id, payload)
