"""Optional signed-proof settlement. Legacy unwitnessed contracts stay exact."""
from fastapi import APIRouter, HTTPException, Request, Response

from .broll_plan_review_api import _authority
from .broll_plan_review_command import BrollPlanConflict
from .broll_request_recovery_api import BrollRecoveryInspect, BrollRecoveryAbandon
from .broll_request_witness import WitnessEnvelope, WitnessError
from .broll_request_witness_api import witness_runtime, witness_authority_guard
from .human_auth import authorize_project, HumanAuthVerifier

router = APIRouter(prefix='/api/v1/projects/{project_id}/broll-plan-review/witnessed-recovery')


class WitnessedInspect(BrollRecoveryInspect):
    witness: WitnessEnvelope


class WitnessedAbandon(BrollRecoveryAbandon):
    witness: WitnessEnvelope


async def _invoke(request, project, response, function, *args):
    principal = await authorize_project(request, project, 'editor')
    verifier = getattr(request.app.state, 'human_auth_verifier', None)
    if not isinstance(verifier, HumanAuthVerifier):
        raise HTTPException(503, detail={'error': {'code': 'AUTH_UNAVAILABLE'}})
    response.headers['Cache-Control'] = 'no-store'
    try:
        return await function(request.app.state.media_planning_service, project,
            _authority(request, principal), verifier.registry, *args)
    except (WitnessError, BrollPlanConflict) as exc:
        raise HTTPException(exc.status, detail={'error': {'code': exc.code}}) from None
    except KeyError:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}}) from None


@router.post('/inspect')
async def inspect(project_id: str, payload: WitnessedInspect, request: Request, response: Response):
    from .broll_witnessed_recovery_command import inspect_witnessed
    provider, _settings = witness_runtime(request)
    return await _invoke(request, project_id, response, inspect_witnessed,
        payload, provider, witness_authority_guard(request))


@router.post('/abandon')
async def abandon(project_id: str, payload: WitnessedAbandon, request: Request, response: Response):
    from .broll_witnessed_recovery_command import abandon_witnessed
    provider, _settings = witness_runtime(request)
    return await _invoke(request, project_id, response, abandon_witnessed,
        payload, provider, witness_authority_guard(request))


@router.get('/settlements/{settlement_id}')
async def read(project_id: str, settlement_id: str, request: Request, response: Response):
    from .broll_witnessed_recovery_command import read_witnessed
    return await _invoke(request, project_id, response, read_witnessed, settlement_id)
