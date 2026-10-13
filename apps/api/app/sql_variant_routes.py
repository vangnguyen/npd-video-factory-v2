"""Human-authenticated family endpoints; all bodies follow scope/role admission."""
import json
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import TypeAdapter, ValidationError

from .human_auth import authorize_human_request, authorize_project
from .sql_variant_models import FamilyReserveRequest, FamilyVersionRequest, FamilyRead, FamilyPage
from .sql_variant_repository import SqlVariantError
from .sql_variant_api_service import (ApiAvailability, FamilyMutationRead, DerivationRequest,
    DerivationReceipt, DerivationMutationRead)

MAX_BODY_BYTES = 64 * 1024
NOT_CONFIGURED = {'SQL_VARIANT_STORAGE_NOT_CONFIGURED',
    'SQL_VARIANT_UPLOADED_NOT_CONFIGURED', 'SQL_VARIANT_API_NOT_CONFIGURED'}


def error(status, code):
    return HTTPException(status, detail={'error': {'code': code, 'message': code}},
                         headers={'Cache-Control': 'no-store'})


class FamilyRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def scoped(request):
            try:
                # Explicit pre-body admission. No reliance on body-model/dependency
                # execution ordering in FastAPI; actor always comes from verifier.
                await authorize_human_request(request)
                response = await handler(request)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), 'Cache-Control': 'no-store'}
                raise
            response.headers['Cache-Control'] = 'no-store'
            return response
        return scoped


router = APIRouter(prefix='/api/v1/projects/{project_id}/variant-families', route_class=FamilyRoute)


def service(request):
    value = getattr(request.app.state, 'sql_variant_api_service', None)
    if value is None:
        raise error(503, 'SQL_VARIANT_API_NOT_CONFIGURED')
    return value


async def scope(request, project_id, *, write=False):
    actor = await authorize_project(request, project_id, 'editor' if write else 'viewer')
    project = await request.app.state.platform_repository.get_project(project_id)
    if project is None:
        raise error(404, 'SQL_VARIANT_NOT_FOUND')
    return actor, project.workspace_id


def query(request, *, page=False):
    allowed = {'limit', 'cursor'} if page else set()
    if any(k not in allowed for k in request.query_params) or any(
            len(request.query_params.getlist(k)) != 1 for k in request.query_params):
        raise error(422, 'SQL_VARIANT_QUERY_INVALID')
    if not page:
        return {}
    raw = request.query_params.get('limit', '25')
    if not re.fullmatch(r'[1-9][0-9]{0,2}', raw) or not 1 <= int(raw) <= 100:
        raise error(422, 'SQL_VARIANT_PAGE_INVALID')
    return {'limit': int(raw), 'cursor': request.query_params.get('cursor')}


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


async def body(request, contract):
    query(request)
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise error(415, 'SQL_VARIANT_JSON_REQUIRED')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_BODY_BYTES:
            raise error(413, 'SQL_VARIANT_BODY_LIMIT')
        data.extend(chunk)
    try:
        def nonfinite(_):
            raise ValueError('nonfinite JSON')
        parsed = json.loads(data, object_pairs_hook=unique_pairs, parse_constant=nonfinite)
        return TypeAdapter(contract).validate_python(parsed, strict=True)
    except (ValidationError, ValueError, TypeError, RecursionError):
        # Pydantic errors can echo private submitted fields. Return bounded codes.
        raise error(422, 'SQL_VARIANT_BODY_INVALID') from None


async def execute(action):
    try:
        return await action()
    except KeyError:
        raise error(404, 'SQL_VARIANT_NOT_FOUND') from None
    except SqlVariantError as exc:
        code = exc.code if re.fullmatch(r'SQL_VARIANT_[A-Z0-9_]{1,100}', exc.code) else 'SQL_VARIANT_CONFLICT'
        raise error(503 if code in NOT_CONFIGURED else 409, code) from None


def request_contract(contract):
    """Document strict request bodies without delegating pre-auth body parsing.

    Request DTOs contain primitive fields only. Inline local schema definitions
    so references remain valid when nested inside the host app's OpenAPI document.
    """
    schema = TypeAdapter(contract).json_schema()
    definitions = schema.pop('$defs', {})
    def inline(value):
        if isinstance(value, list):
            return [inline(v) for v in value]
        if not isinstance(value, dict):
            return value
        if '$ref' in value:
            return inline(definitions[value['$ref'].removeprefix('#/$defs/')])
        result = {key: inline(item) for key, item in value.items()}
        if 'discriminator' in result:
            result['discriminator'].pop('mapping', None)
        return result
    return {'requestBody': {'required': True, 'description': 'Strict finite JSON; maximum 65536 bytes.',
        'content': {'application/json': {'schema': inline(schema)}}}}


@router.get('/availability', response_model=ApiAvailability)
async def availability(project_id: str, request: Request):
    _, workspace = await scope(request, project_id)
    query(request)
    return await execute(lambda: service(request).availability(workspace, project_id))


@router.get('', response_model=FamilyPage)
async def listing(project_id: str, request: Request):
    _, workspace = await scope(request, project_id)
    values = query(request, page=True)
    return await execute(lambda: service(request).list(workspace, project_id, **values))


@router.post('', response_model=FamilyMutationRead, status_code=201,
             openapi_extra=request_contract(FamilyReserveRequest))
async def reserve(project_id: str, request: Request):
    actor, workspace = await scope(request, project_id, write=True)
    payload = await body(request, FamilyReserveRequest)
    return await execute(lambda: service(request).reserve(workspace, project_id, payload, actor_ref=actor.subject))


@router.get('/{family_id}', response_model=FamilyRead)
async def get(project_id: str, family_id: str, request: Request):
    _, workspace = await scope(request, project_id)
    query(request)
    return await execute(lambda: service(request).get(workspace, project_id, family_id))


@router.post('/{family_id}/cancel', response_model=FamilyMutationRead,
             openapi_extra=request_contract(FamilyVersionRequest))
async def cancel(project_id: str, family_id: str, request: Request):
    actor, workspace = await scope(request, project_id, write=True)
    payload = await body(request, FamilyVersionRequest)
    return await execute(lambda: service(request).cancel(workspace, project_id, family_id, payload, actor_ref=actor.subject))


@router.post('/{family_id}/derive', response_model=DerivationMutationRead, status_code=201,
             openapi_extra=request_contract(DerivationRequest))
async def derive(project_id: str, family_id: str, request: Request):
    actor, workspace = await scope(request, project_id, write=True)
    payload = await body(request, DerivationRequest)
    return await execute(lambda: service(request).derive(workspace, project_id, family_id, payload, actor_ref=actor.subject))


@router.get('/{family_id}/receipts/{receipt_id}', response_model=DerivationReceipt)
async def receipt(project_id: str, family_id: str, receipt_id: str, request: Request):
    _, workspace = await scope(request, project_id)
    query(request)
    return await execute(lambda: service(request).receipt(workspace, project_id, family_id, receipt_id))
