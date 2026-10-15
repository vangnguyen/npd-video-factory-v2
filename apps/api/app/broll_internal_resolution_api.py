"""Explicit human-only admission and exact-job observation for internal B-roll."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Path
from pydantic import Field, model_validator, ValidationError

from .human_auth import authorize_human_request, authorize_project
from .models import StrictModel
from .broll_plan_review_api import _authority
from .broll_internal_resolution_core import InternalResolutionConflict
from .frozen_storage_read import FrozenReadRejected
from .source_linked_edit_command import SourceLinkedConflict


class InternalResolutionRequest(StrictModel):
    request_key: str = Field(strict=True, pattern=r'^[A-Za-z0-9_-]{8,128}$')
    context_sha256: str = Field(strict=True, pattern=r'^[a-f0-9]{64}$')
    asset_id: str = Field(strict=True, pattern=r'^ast_[A-Za-z0-9_-]{4,60}$')
    acknowledged: bool = Field(strict=True)

    @model_validator(mode='after')
    def reviewed(self):
        if self.acknowledged is not True:
            raise ValueError('explicit internal B-roll selection acknowledgement required')
        return self


router = APIRouter(prefix='/api/v1/projects/{project_id}/media-plans/{media_plan_id}/items/{media_plan_item_id}/internal-resolution-review',
    tags=['broll-internal-resolution'], dependencies=[Depends(authorize_human_request)])


async def invoke(request, project_id, plan_id, item_id, *, payload=None, key=None, job_id=None):
    from .broll_internal_resolution_command import inspect_context, admit, inspect_job
    principal = await authorize_project(request, project_id, 'editor' if payload is not None else 'viewer')
    service = getattr(request.app.state, 'media_resolution_service', None)
    if service is None:
        raise HTTPException(503, detail={'error': {'code': 'NOT_CONFIGURED'}})
    authority = _authority(request, principal)
    try:
        if payload is not None:
            return await admit(service, project_id, plan_id, item_id, authority, payload)
        if key is not None:
            return await inspect_job(service, project_id, plan_id, item_id, authority, key, job_id)
        return await inspect_context(service, project_id, plan_id, item_id, authority)
    except KeyError:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}}) from None
    except InternalResolutionConflict as exc:
        raise HTTPException(exc.status, detail={'error': {'code': exc.code}}) from None
    except (SourceLinkedConflict, ValidationError, FrozenReadRejected, ValueError):
        raise HTTPException(409, detail={'error': {'code': 'BROLL_INTERNAL_SOURCE_INVALID'}}) from None


@router.get('')
async def read_context(project_id: str, media_plan_id: str, media_plan_item_id: str,
                       request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return await invoke(request, project_id, media_plan_id, media_plan_item_id)


@router.post('', status_code=202)
async def submit(project_id: str, media_plan_id: str, media_plan_item_id: str,
                 payload: InternalResolutionRequest, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return await invoke(request, project_id, media_plan_id, media_plan_item_id, payload=payload)


@router.get('/requests/{request_key}/jobs/{resolution_job_id}')
async def read_exact_job(project_id: str, media_plan_id: str, media_plan_item_id: str,
        request_key: Annotated[str, Path(pattern=r'^[A-Za-z0-9_-]{8,128}$')],
        resolution_job_id: Annotated[str, Path(pattern=r'^mrj_[A-Za-z0-9_-]{4,60}$')],
        request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return await invoke(request, project_id, media_plan_id, media_plan_item_id,
        key=request_key, job_id=resolution_job_id)
