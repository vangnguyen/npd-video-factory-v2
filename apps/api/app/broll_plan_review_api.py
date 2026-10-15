"""Human-only, source-bound preparation; provider execution is a separate review."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field, StrictBool, model_validator

from .human_auth import authorize_project
from .models import StrictModel


class BrollPlanSettings(StrictModel):
    allow_stock: StrictBool = False
    allow_ai_image: StrictBool = False
    allow_ai_video: StrictBool = False
    max_ai_cost_vnd: Literal["0"] = "0"
    resolver_priority: list[Literal['user_asset', 'internal_library', 'licensed_stock']] = Field(
        default_factory=lambda: ['user_asset', 'internal_library'], min_length=1, max_length=3)

    @model_validator(mode='after')
    def exact_tiers(self):
        if self.allow_ai_image or self.allow_ai_video:
            raise ValueError('BROLL_GENERATIVE_APPROVAL_UNAVAILABLE')
        if len(set(self.resolver_priority)) != len(self.resolver_priority):
            raise ValueError('BROLL_PRIORITY_DUPLICATE')
        if self.allow_stock != ('licensed_stock' in self.resolver_priority):
            raise ValueError('BROLL_STOCK_OPT_IN_REQUIRED')
        return self


class BrollPlanPrepare(StrictModel):
    request_key: str = Field(strict=True, pattern=r'^[A-Za-z0-9_-]{8,128}$')
    context_sha256: str = Field(strict=True, pattern=r'^[a-f0-9]{64}$')
    acknowledged: StrictBool
    settings: BrollPlanSettings
    learning_snapshot_id: str | None = Field(default=None, strict=True, pattern=r'^lsn_[A-Za-z0-9_-]{4,60}$')

    @model_validator(mode='after')
    def reviewed(self):
        if self.acknowledged is not True:
            raise ValueError('BROLL_REVIEW_REQUIRED')
        return self


router = APIRouter(prefix='/api/v1/projects/{project_id}/broll-plan-review')


def _authority(request, principal):
    import hashlib
    from dataclasses import asdict
    value = asdict(principal)
    value['workspace_roles'] = dict(principal.workspace_roles)
    value['expires_at'] = principal.expires_at.isoformat()
    value['credential_sha256'] = hashlib.sha256(request.headers.get('Authorization', '').encode()).hexdigest()
    return value


async def _invoke(request, project_id, role, function, *args):
    from .broll_plan_review_command import BrollPlanConflict
    principal = await authorize_project(request, project_id, role)
    try:
        return await function(request.app.state.media_planning_service, project_id,
            _authority(request, principal), *args)
    except KeyError:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}}) from None
    except BrollPlanConflict as exc:
        raise HTTPException(exc.status, detail={'error': {'code': exc.code}}) from None


@router.get('')
async def read_context(project_id: str, request: Request, response: Response):
    from .broll_plan_review_command import read_context
    response.headers['Cache-Control'] = 'no-store'
    return await _invoke(request, project_id, 'viewer', read_context)


@router.post('', status_code=201)
async def prepare_plan(project_id: str, payload: BrollPlanPrepare, request: Request, response: Response):
    from .broll_plan_review_command import prepare_plan
    from .broll_request_recovery_command import private_identity
    async def prepare_with_identity(service, project, authority, body):
        identity = private_identity(authority, request.headers.get('Authorization', ''),
            getattr(request.app.state, 'human_write_enabled', False))
        return await prepare_plan(service, project, authority, body, recovery_identity=identity)
    response.headers['Cache-Control'] = 'no-store'
    value = await _invoke(request, project_id, 'editor', prepare_with_identity, payload)
    if value['state'] == 'unknown':
        response.status_code = 202
    elif value['state'] == 'rejected':
        response.status_code = 409
    return value


@router.get('/requests/{request_key}')
async def read_request(project_id: str, request_key: str, request: Request, response: Response):
    from .broll_plan_review_command import read_request
    import re
    if re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_key) is None:
        raise HTTPException(422, detail={'error': {'code': 'BROLL_REQUEST_KEY_INVALID'}})
    response.headers['Cache-Control'] = 'no-store'
    return await _invoke(request, project_id, 'viewer', read_request, request_key)
