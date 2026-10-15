"""Fresh human authority may inspect and explicitly seal one original request."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field, StrictBool, model_validator

from .models import StrictModel
from .human_auth import HumanAuthVerifier, authorize_project
from .broll_plan_review_api import _authority


class BrollRecoveryInspect(StrictModel):
    intent_json: str = Field(strict=True, min_length=1, max_length=5 * 1024 * 1024)
    intent_sha256: str = Field(strict=True, pattern=r'^[a-f0-9]{64}$')


class BrollRecoveryAbandon(BrollRecoveryInspect):
    observation_sha256: str = Field(strict=True, pattern=r'^[a-f0-9]{64}$')
    acknowledged: StrictBool

    @model_validator(mode='after')
    def explicit(self):
        if self.acknowledged is not True:
            raise ValueError('BROLL_RECOVERY_ACKNOWLEDGEMENT_REQUIRED')
        return self


router = APIRouter(prefix='/api/v1/projects/{project_id}/broll-plan-review/recovery')


async def _invoke(request, project, response, function, *args):
    from .broll_plan_review_command import BrollPlanConflict
    principal = await authorize_project(request, project, 'editor')
    verifier = getattr(request.app.state, 'human_auth_verifier', None)
    if not isinstance(verifier, HumanAuthVerifier):
        raise HTTPException(503, detail={'error': {'code': 'AUTH_UNAVAILABLE'}})
    response.headers['Cache-Control'] = 'no-store'
    try:
        return await function(request.app.state.media_planning_service, project,
            _authority(request, principal), verifier.registry, *args)
    except KeyError:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}}) from None
    except BrollPlanConflict as exc:
        raise HTTPException(exc.status, detail={'error': {'code': exc.code}}) from None


@router.post('/inspect')
async def inspect(project_id: str, payload: BrollRecoveryInspect, request: Request, response: Response):
    from .broll_request_recovery_command import inspect_request
    return await _invoke(request, project_id, response, inspect_request, payload)


@router.post('/abandon')
async def abandon(project_id: str, payload: BrollRecoveryAbandon, request: Request, response: Response):
    from .broll_request_recovery_command import abandon_request
    return await _invoke(request, project_id, response, abandon_request, payload)


@router.get('/settlements/{settlement_id}')
async def settlement(project_id: str, settlement_id: str, request: Request, response: Response):
    from .broll_request_recovery_command import read_settlement
    return await _invoke(request, project_id, response, read_settlement, settlement_id)


@router.get('/settlements/{settlement_id}/late-results')
async def late_results(project_id: str, settlement_id: str, request: Request, response: Response):
    from .broll_request_recovery_command import read_late_results
    return await _invoke(request, project_id, response, read_late_results, settlement_id)
