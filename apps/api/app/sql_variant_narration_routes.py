"""Explicit dual-project S5 admission before reading any submitted JSON."""
import re
from fastapi import APIRouter, Request
from .human_auth import authorize_project
from .sql_variant_routes import FamilyRoute, body, query, error, request_contract
from .sql_variant_repository import SqlVariantError
from .sql_variant_narration_models import NarrationReuseRequest, NarrationReuseRead
from .sql_variant_narration_activation import NarrationMutationRead, NarrationAvailabilityRead, NarrationReviewCreateRequest, VariantNarrationQueueUnknownError
from .sql_variant_narration_runtime import VariantNarrationRuntime
from .production_models import RenderJobRead
from .production_repository import ApprovalBoundaryError, ProductionConflictError
from .production_logic import ProductionContractError

router = APIRouter(prefix='/api/v1/projects/{project_id}/variant-families/{family_id}/children/{child_project_id}',
    route_class=FamilyRoute)


def runtime(request):
    value = getattr(request.app.state, 'sql_variant_narration_runtime', None)
    if type(value) is not VariantNarrationRuntime:
        raise error(503, 'SQL_VARIANT_NARRATION_NOT_CONFIGURED')
    return value


async def scope(request, project_id, child_project_id, *, write=False):
    role = 'editor' if write else 'viewer'
    actor = await authorize_project(request, project_id, role)
    await authorize_project(request, child_project_id, role)
    platform = request.app.state.platform_repository
    master, child = await platform.get_project(project_id), await platform.get_project(child_project_id)
    if master.workspace_id != child.workspace_id or master.project_id == child.project_id:
        raise error(404, 'SQL_VARIANT_NOT_FOUND')
    return actor, master.workspace_id


async def execute(action):
    try:
        return await action()
    except KeyError:
        raise error(404, 'SQL_VARIANT_NOT_FOUND') from None
    except SqlVariantError as exc:
        code = exc.code if re.fullmatch(r'SQL_VARIANT_[A-Z0-9_]{1,100}', exc.code) else 'SQL_VARIANT_CONFLICT'
        raise error(503 if code.endswith(('NOT_CONFIGURED', 'DISABLED')) else 409, code) from None
    except VariantNarrationQueueUnknownError as exc:
        raise error(503, 'SQL_VARIANT_NARRATION_QUEUE_OUTCOME_UNKNOWN') from None
    except (ApprovalBoundaryError, ProductionConflictError):
        raise error(409, 'SQL_VARIANT_NARRATION_REVIEW_CONFLICT') from None
    except ProductionContractError:
        raise error(422, 'SQL_VARIANT_NARRATION_REVIEW_INVALID') from None


@router.get('/narration-reuse-availability', response_model=NarrationAvailabilityRead)
async def availability(project_id: str, family_id: str, child_project_id: str, request: Request):
    _, workspace = await scope(request, project_id, child_project_id)
    query(request)
    from .sql_variant_repository import SqlVariantFamilyRepository
    family = await execute(lambda: SqlVariantFamilyRepository(request.app.state.platform_repository.session_factory).get(
        workspace, project_id, family_id))
    if not any(member.child_project_id == child_project_id for member in family.members):
        raise error(404, 'SQL_VARIANT_NOT_FOUND')
    value = runtime(request)
    result = value.availability()
    if result['state'] == 'CONFIGURED' and not paired(request, value):
        result.update(state='NOT_CONFIGURED', reason_code='SQL_VARIANT_NARRATION_NOT_CONFIGURED')
    result.update(source_current=family.source_current, source_current_reason=family.source_current_reason,
        family_version=family.version, family_snapshot_sha256=family.snapshot_sha256)
    return result


@router.post('/narration-reuse', response_model=NarrationMutationRead, status_code=201,
    openapi_extra=request_contract(NarrationReuseRequest))
async def reuse(project_id: str, family_id: str, child_project_id: str, request: Request):
    actor, workspace = await scope(request, project_id, child_project_id, write=True)
    selected = await execute(lambda: configured(request))
    payload = await body(request, NarrationReuseRequest)
    if payload.child_project_id != child_project_id:
        raise error(409, 'SQL_VARIANT_NARRATION_CHILD_LINEAGE_REQUIRED')
    receipt, replay = await execute(lambda: selected.service.reuse(workspace, project_id, family_id, payload, actor_ref=actor.subject))
    return NarrationMutationRead(receipt=receipt, replayed=replay)


async def configured(request):
    value = runtime(request).require()
    if not paired(request, value):
        raise error(503, 'SQL_VARIANT_NARRATION_NOT_CONFIGURED')
    return value


def paired(request, value):
    service = getattr(request.app.state, 'production_package_service', None)
    return (service is not None and service.repository.variant_narration_admission is value.admission
        and service.repository.variant_narration_fence is value.fence)


@router.get('/narration-receipts/{receipt_id}', response_model=NarrationReuseRead)
async def read_receipt(project_id: str, family_id: str, child_project_id: str, receipt_id: str, request: Request):
    _, workspace = await scope(request, project_id, child_project_id)
    query(request)
    # Archived SQL is readable even when activation is disabled; GET stages no bytes.
    from .sql_variant_repository import SqlVariantFamilyRepository
    from .sql_variant_narration_repository import SqlVariantNarrationRepository
    repository = SqlVariantNarrationRepository(SqlVariantFamilyRepository(request.app.state.platform_repository.session_factory))
    from .sql_variant_db import SqlVariantArtifactReceiptORM
    async with repository.session_factory() as session:
        row = await session.get(SqlVariantArtifactReceiptORM, receipt_id)
        if (row is None or row.kind != 'approved_narration_reuse' or (row.workspace_id, row.family_id) != (workspace, family_id)
                or row.input_json.get('master_project_id') != project_id or row.input_json.get('child_project_id') != child_project_id):
            raise error(404, 'SQL_VARIANT_NOT_FOUND')
    value = await execute(lambda: repository.get(workspace, project_id, family_id, receipt_id))
    if value is None or value.child_project_id != child_project_id:
        raise error(404, 'SQL_VARIANT_NOT_FOUND')
    return value


@router.post('/narration-review-render', response_model=RenderJobRead, status_code=202,
    openapi_extra=request_contract(NarrationReviewCreateRequest))
async def review(project_id: str, family_id: str, child_project_id: str, request: Request):
    actor, _ = await scope(request, project_id, child_project_id, write=True)
    selected = await execute(lambda: configured(request))
    payload = await body(request, NarrationReviewCreateRequest)
    if (payload.selection.family_id, payload.selection.master_project_id) != (family_id, project_id):
        raise error(409, 'SQL_VARIANT_NARRATION_CHILD_LINEAGE_REQUIRED')
    service = getattr(request.app.state, 'production_package_service', None)
    if (service is None or service.repository.variant_narration_admission is not selected.admission
            or service.repository.variant_narration_fence is not selected.fence):
        raise error(503, 'SQL_VARIANT_NARRATION_NOT_CONFIGURED')
    return await execute(lambda: service.enqueue_variant_review(child_project_id, payload, actor_ref=actor.subject))
