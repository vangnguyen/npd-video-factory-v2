"""Signed local descriptive learning; no provider request or execution grant."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError,digest
from .official_learning_models import Create
from app.learning_models import LearningPolicy,DIMENSIONS
BASE=r'/api/projects/([a-f0-9]{32})/official-learning'
IDENTITY=r'(nols_[a-f0-9]{32})'

def get(handler,path):
    service=handler.server.official_learning;service.check();params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/official-learning':
        if params:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_PAGE_INVALID',400)
        return {'schema_version':'native-official-learning-capabilities-v1','workspace_id':service.workspace,'default_policy':LearningPolicy().model_dump(mode='json'),
            'dimensions':list(DIMENSIONS),'maximum_candidate_rows':500,'automatic_learning':False,'provider_calls_enabled':False,
            'recommendation_only':True,'automatic_action':False,'publishing_enabled':False,'token_returned':False,'real_provider_tested':False}
    binding=re.fullmatch(BASE+r'/source/(nowa_[a-f0-9]{32})',path)
    if binding:
        if params:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_PAGE_INVALID',400)
        project,identity=binding.groups()
        with service.store.transaction() as con:value=service.source(con,project,identity)
        return {'schema_version':'native-official-learning-source-binding-v1','workspace_id':service.workspace,'project_id':project,
            'assessment_id':value['assessment_id'],'assessment_sha256':value['snapshot_sha256'],'publication_id':value['publication_id'],
            'result_snapshot_id':value['result_snapshot_id'],'candidate_sha256':digest(value['snapshot']['candidate']),
            'scope':service.scope(value),'winner_policy_sha256':value['snapshot']['policy_sha256'],'winner_factor_basis_sha256':service.basis(value),
            'qualified_scope':service.winners.known_scope(value['snapshot']['candidate']),'mock':value['mock'],'real_audience_observation':not value['mock'],
            'recommendation_only':True,'automatic_action':False,'publishing_enabled':False,'token_returned':False}
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r')?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity=match.groups()
    if identity:
        if params:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_PAGE_INVALID',400)
        return service.get(project,identity)
    if set(params)-{'limit','cursor','publication'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_OFFICIAL_LEARNING_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_PAGE_INVALID',400) from None
    return service.page(project,limit=limit,cursor=params.get('cursor',[None])[0],publication=params.get('publication',[None])[0])

def post(handler,path,body):
    match=re.fullmatch(BASE,path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_CURRENT_OWNER_REQUIRED',403)
    service=handler.server.official_learning;service.winners.analytics.identity(session.principal)
    try:payload=Create.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_OFFICIAL_LEARNING_FIELDS_INVALID',400) from None
    value,replay=service.create(match.group(1),payload,principal=session.principal)
    return {**value,'idempotent_replay':replay}
