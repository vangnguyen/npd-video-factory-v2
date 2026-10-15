"""Human-only settlement of an existing terminal internal-resolution intent."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import Field, model_validator

from .broll_plan_review_api import _authority
from .broll_internal_resolution_core import InternalResolutionConflict
from .human_auth import authorize_human_request, authorize_project, HumanAuthVerifier
from .models import StrictModel


class TerminalInspect(StrictModel):
    intent_json: str = Field(strict=True, min_length=1, max_length=5 * 1024 * 1024)
    intent_sha256: str = Field(strict=True, pattern=r'^[a-f0-9]{64}$')


class TerminalSettle(TerminalInspect):
    observation_sha256: str = Field(strict=True, pattern=r'^[a-f0-9]{64}$')
    acknowledged: bool = Field(strict=True)

    @model_validator(mode='after')
    def explicit(self):
        if self.acknowledged is not True:
            raise ValueError('explicit terminal intent release acknowledgement required')
        return self


router = APIRouter(prefix='/api/v1/projects/{project_id}/media-plans/{media_plan_id}/items/{media_plan_item_id}/internal-resolution-settlement',
    tags=['broll-internal-terminal-settlement'], dependencies=[Depends(authorize_human_request)])


async def _invoke(request, response, project, plan, item, function, payload, *, write=False):
    principal = await authorize_project(request, project, 'editor')
    authority = _authority(request, principal)
    service = getattr(request.app.state, 'media_resolution_service', None)
    if service is None:
        raise HTTPException(503, detail={'error': {'code': 'NOT_CONFIGURED'}})
    def guard():
        try:
            verifier = getattr(request.app.state, 'human_auth_verifier', None)
            if (not isinstance(verifier, HumanAuthVerifier) or getattr(request.app.state, 'human_api_enabled', False) is not True
                    or write and getattr(request.app.state, 'human_write_enabled', False) is not True):
                raise ValueError()
            return _authority(request, verifier.verify(request.headers.get('Authorization')))
        except Exception:
            raise InternalResolutionConflict('BROLL_INTERNAL_SETTLEMENT_AUTHORITY_CHANGED', 403) from None
    response.headers['Cache-Control'] = 'no-store'
    try:
        return await function(service, project, plan, item, authority, payload, guard)
    except KeyError:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}}) from None
    except InternalResolutionConflict as exc:
        raise HTTPException(exc.status, detail={'error': {'code': exc.code}}) from None
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise HTTPException(409, detail={'error': {'code': 'BROLL_INTERNAL_SETTLEMENT_INVALID'}}) from None


@router.post('/inspect')
async def inspect(project_id: str, media_plan_id: str, media_plan_item_id: str,
        payload: TerminalInspect, request: Request, response: Response):
    from .broll_internal_settlement_command import inspect
    return await _invoke(request, response, project_id, media_plan_id, media_plan_item_id, inspect, payload)


@router.post('/settle')
async def settle(project_id: str, media_plan_id: str, media_plan_item_id: str,
        payload: TerminalSettle, request: Request, response: Response):
    from .broll_internal_settlement_command import settle
    return await _invoke(request, response, project_id, media_plan_id, media_plan_item_id, settle, payload, write=True)


@router.get('/settlements/{settlement_id}')
async def read(project_id: str, media_plan_id: str, media_plan_item_id: str,
        settlement_id: Annotated[str, Path(pattern=r'^sop_[a-f0-9]{32}$')], request: Request, response: Response):
    from .broll_internal_settlement_command import read
    return await _invoke(request, response, project_id, media_plan_id, media_plan_item_id, read, settlement_id)
