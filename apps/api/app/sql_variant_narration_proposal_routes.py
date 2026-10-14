"""Explicit preparation endpoint: dual-project human scope, no execution."""
from fastapi import APIRouter, Request

from .sql_variant_routes import FamilyRoute, query
from .sql_variant_narration_routes import scope, configured, execute
from .sql_variant_narration_proposal import NarrationProposalRead, read_narration_proposal

router = APIRouter(prefix='/api/v1/projects/{project_id}/variant-families/{family_id}/children/{child_project_id}',
                   route_class=FamilyRoute)


@router.get('/narration-reuse-proposal', response_model=NarrationProposalRead)
async def proposal(project_id: str, family_id: str, child_project_id: str, request: Request):
    actor, workspace = await scope(request, project_id, child_project_id)
    query(request)
    selected = await execute(lambda: configured(request))
    return await execute(lambda: read_narration_proposal(selected.service.repository, workspace,
        project_id, family_id, child_project_id, actor_ref=actor.subject))


def register_variant_narration_proposal_routes(app):
    if not getattr(app.state, 'sql_variant_narration_proposal_routes_registered', False):
        app.include_router(router)
        app.state.sql_variant_narration_proposal_routes_registered = True
