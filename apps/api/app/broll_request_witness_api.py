"""Optional, human-authenticated authorization proof. Never executes a plan."""
from fastapi import APIRouter, HTTPException, Request, Response

from .broll_plan_review_api import BrollPlanPrepare, _authority
from .broll_plan_review_command import BrollPlanConflict
from .broll_request_witness import WitnessEnvelope, WitnessError
from .human_auth import authorize_project, HumanAuthVerifier
from .models import StrictModel

router = APIRouter(prefix='/api/v1/projects/{project_id}/broll-plan-review/witness')


class WitnessVerifyRequest(StrictModel):
    request: BrollPlanPrepare
    witness: WitnessEnvelope


def witness_runtime(request):
    from .config import settings
    from .broll_request_witness_secrets import SettingsWitnessSecretProvider
    provider = getattr(request.app.state, 'broll_witness_secret_provider', None)
    return provider if provider is not None else SettingsWitnessSecretProvider(settings), settings


def witness_authority_guard(request):
    # A private server closure. Never accepted from route/body data. Expired or
    # revoked current credentials and a changed write switch cannot cross SQL awaits.
    def current():
        verifier = getattr(request.app.state, 'human_auth_verifier', None)
        try:
            if not isinstance(verifier, HumanAuthVerifier) or getattr(request.app.state, 'human_write_enabled', False) is not True:
                raise ValueError()
            return _authority(request, verifier.verify(request.headers.get('Authorization')))
        except Exception:
            raise WitnessError('BROLL_WITNESS_AUTHORITY_CHANGED', 403) from None
    return current


async def _invoke(request, project, response, function, *args):
    principal = await authorize_project(request, project, 'editor')
    provider, _settings = witness_runtime(request)
    response.headers['Cache-Control'] = 'no-store'
    try:
        return await function(request.app.state.media_planning_service, project, _authority(request, principal), provider, *args)
    except (WitnessError, BrollPlanConflict) as exc:
        raise HTTPException(exc.status, detail={'error': {'code': exc.code}}) from None
    except KeyError:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}}) from None


@router.post('')
async def issue(project_id: str, payload: BrollPlanPrepare, request: Request, response: Response):
    from .broll_request_witness_command import issue_witness
    async def perform(service, project, authority, provider):
        _, settings = witness_runtime(request)
        ttl = getattr(request.app.state, 'broll_witness_ttl_seconds', settings.broll_request_witness_ttl_seconds)
        return await issue_witness(service, project, authority, request.headers.get('Authorization', ''),
            payload, provider, ttl_seconds=ttl, authority_guard=witness_authority_guard(request))
    return await _invoke(request, project_id, response, perform)


@router.post('/verify')
async def verify(project_id: str, payload: WitnessVerifyRequest, request: Request, response: Response):
    from .broll_request_witness_command import verify_witness
    async def perform(service, project, authority, provider):
        return await verify_witness(service, project, authority, payload.request, payload.witness, provider,
            authority_guard=witness_authority_guard(request))
    return await _invoke(request, project_id, response, perform)
