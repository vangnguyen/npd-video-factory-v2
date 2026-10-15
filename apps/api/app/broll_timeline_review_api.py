"""Human reviewed B-roll placement into the existing canonical timeline."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field, model_validator

from .human_auth import authorize_human_request, authorize_project
from .models import StrictModel


class BrollTimelineUpdate(StrictModel):
    expected_timeline_id: str = Field(strict=True, pattern=r'^tml_[A-Za-z0-9_-]{4,60}$')
    expected_version: int = Field(strict=True, ge=1)
    expected_context_sha256: str = Field(strict=True, pattern=r'^[a-f0-9]{64}$')
    request_key: str = Field(strict=True, pattern=r'^[A-Za-z0-9_-]{8,128}$')
    item_ids: list[str] = Field(strict=True, min_length=1, max_length=200)
    replace_plan_clips: bool = Field(default=False, strict=True)
    acknowledged: bool = Field(strict=True)

    @model_validator(mode='after')
    def reviewed_unique_items(self):
        if self.acknowledged is not True or len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError('review unique B-roll selections and approval invalidation')
        if any(not value or len(value) > 64 or any(ord(c) < 32 for c in value) for value in self.item_ids):
            raise ValueError('invalid B-roll item identifier')
        return self


class BrollTimelineReceipt(StrictModel):
    schema_version: Literal['broll-timeline-review.v1']
    workspace_id: str
    project_id: str
    timeline_id: str
    media_plan_id: str
    parent_version_id: str
    parent_version: int = Field(strict=True, ge=1)
    result_version: int = Field(strict=True, ge=2)
    actor_ref: str
    request_key: str
    request_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    context_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    media_binding_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    item_ids: list[str] = Field(min_length=1, max_length=200)
    replace_plan_clips: bool
    result_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    provider_calls: Literal[0] = 0
    publishing_enabled: Literal[False] = False
    owner_approval_inferred: Literal[False] = False

    @model_validator(mode='after')
    def one_version(self):
        if self.result_version != self.parent_version + 1 or len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError('one B-roll review advances one canonical version')
        return self


router = APIRouter(prefix='/api/v1/projects/{project_id}/timeline/broll-review/{media_plan_id}',
                   tags=['broll-timeline-review'], dependencies=[Depends(authorize_human_request)])


async def _invoke(request, project_id, media_plan_id, payload=None):
    from .broll_timeline_review_command import BrollTimelineConflict, read_broll_timeline, apply_broll_timeline
    principal = await authorize_project(request, project_id, 'viewer' if payload is None else 'editor')
    service = getattr(request.app.state, 'timeline_service', None)
    if service is None:
        raise HTTPException(503, detail={'error': {'code': 'NOT_CONFIGURED'}})
    try:
        return await (read_broll_timeline(service, project_id, media_plan_id, actor_ref=principal.subject)
            if payload is None else apply_broll_timeline(service, project_id, media_plan_id, payload,
                actor_ref=principal.subject))
    except KeyError:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}}) from None
    except BrollTimelineConflict as exc:
        raise HTTPException(409, detail={'error': {'code': exc.code, 'current_version': exc.current_version}}) from None


@router.get('')
async def read_review(project_id: str, media_plan_id: str, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return await _invoke(request, project_id, media_plan_id)


@router.put('')
async def apply_review(project_id: str, media_plan_id: str, payload: BrollTimelineUpdate,
                       request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return await _invoke(request, project_id, media_plan_id, payload)
