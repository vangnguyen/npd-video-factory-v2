from fastapi import APIRouter, Depends, Header, Query, Request, Response
from .analytics_routes import error, private_analytics_response
from .human_auth import authorize_project
from .learning_models import LearningCreate, LearningSnapshot
from .learning_service import LearningError

router = APIRouter(prefix='/api/v1', tags=['channel learning'], dependencies=[Depends(private_analytics_response)])


def failure(exc):
    return error(404 if exc.code.endswith('_NOT_FOUND') else 409, exc.code, exc.code)


@router.post('/projects/{project_id}/analytics/learning-snapshots', response_model=LearningSnapshot, status_code=201)
async def create(project_id: str, payload: LearningCreate, request: Request, response: Response,
        key: str = Header(alias='Idempotency-Key', min_length=16, max_length=200)):
    principal = await authorize_project(request, project_id, 'editor')
    try:
        value, replay = await request.app.state.channel_learning_service.create(project_id, payload, actor=principal.subject, key=key)
        response.headers['X-Idempotent-Replay'] = 'true' if replay else 'false'
        return value
    except LearningError as exc: raise failure(exc) from None


@router.get('/projects/{project_id}/analytics/learning-snapshots', response_model=list[LearningSnapshot])
async def history(project_id: str, request: Request, limit: int = Query(default=50, ge=1, le=100)):
    try: return await request.app.state.channel_learning_service.list(project_id, limit=limit)
    except LearningError as exc: raise failure(exc) from None


@router.get('/workspaces/{workspace_id}/learning-snapshots/{identity}', response_model=LearningSnapshot)
async def get(workspace_id: str, identity: str, request: Request):
    try:
        value = await request.app.state.channel_learning_service.get(workspace_id, identity)
        if value is None: raise LearningError('LEARNING_SNAPSHOT_NOT_FOUND')
        return value
    except LearningError as exc: raise failure(exc) from None


@router.get('/workspaces/{workspace_id}/learning-snapshots/{identity}/recommendations')
async def recommendations(workspace_id: str, identity: str, request: Request):
    try: return await request.app.state.channel_learning_service.feedback(workspace_id, identity)
    except LearningError as exc: raise failure(exc) from None


@router.get('/projects/{project_id}/analytics/learning-snapshots/{identity}/subtitle-suggestions')
async def templates(project_id: str, identity: str, request: Request):
    from .learning_templates import subtitle_suggestions
    project = await request.app.state.platform_repository.get_project(project_id)
    try:
        value = await request.app.state.channel_learning_service.get(project.workspace_id, identity)
        if value is None: raise LearningError('LEARNING_SNAPSHOT_NOT_FOUND')
        if value.scope['niche'] != project.niche: raise LearningError('LEARNING_NICHE_MISMATCH')
        package = await request.app.state.production_package_service.get(project_id)
        return {**subtitle_suggestions(value, package), 'project_id': project_id}
    except LearningError as exc: raise failure(exc) from None
