"""Signed local-only assessment and qualified server hash bindings."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .official_winner_models import Create
from app.analytics_channel_policy import WinnerChannelPolicy
BASE=r'/api/projects/([a-f0-9]{32})/official-winners'
IDENTITY=r'(nowa_[a-f0-9]{32})'

def get(handler,path):
    service=handler.server.official_winners;service.check();params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/official-winners':
        if params:raise WorkflowError('NATIVE_OFFICIAL_WINNER_PAGE_INVALID',400)
        policy=WinnerChannelPolicy()
        return {'schema_version':'native-official-winner-capabilities-v1','workspace_id':service.workspace,'default_policy':policy.model_dump(mode='json'),
            'default_policy_sha256':policy.digest(),'maximum_candidate_rows':500,'automatic_assessment':False,'provider_calls_enabled':False,
            'recommendation_only':True,'automatic_action':False,'publishing_enabled':False,'token_returned':False,'real_provider_tested':False}
    binding=re.fullmatch(BASE+r'/source/(noas_[a-f0-9]{32})',path)
    if binding:
        if params:raise WorkflowError('NATIVE_OFFICIAL_WINNER_PAGE_INVALID',400)
        project,identity=binding.groups()
        with service.store.transaction() as con:proof=service.proof(con,project,identity)
        return {'schema_version':'native-official-winner-source-binding-v1','workspace_id':service.workspace,'project_id':project,
            **{k:proof[k] for k in ('sync_id','publication_id','result_snapshot_id','result_sha256','consent_sha256','publication_receipt_sha256','scope')},
            'mock':proof['scope']['mock'],'real_audience_observation':not proof['scope']['mock'],'qualified':True,
            'recommendation_only':True,'automatic_action':False,'publishing_enabled':False,'token_returned':False}
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r')?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity=match.groups()
    if identity:
        if params:raise WorkflowError('NATIVE_OFFICIAL_WINNER_PAGE_INVALID',400)
        return service.get(project,identity)
    if set(params)-{'limit','cursor','publication'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_OFFICIAL_WINNER_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_OFFICIAL_WINNER_PAGE_INVALID',400) from None
    return service.page(project,limit=limit,cursor=params.get('cursor',[None])[0],publication=params.get('publication',[None])[0])

def post(handler,path,body):
    match=re.fullmatch(BASE,path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_OFFICIAL_WINNER_CURRENT_OWNER_REQUIRED',403)
    service=handler.server.official_winners;service.analytics.identity(session.principal)
    try:payload=Create.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_OFFICIAL_WINNER_FIELDS_INVALID',400) from None
    value,replay=service.create(match.group(1),payload,principal=session.principal)
    return {**value,'idempotent_replay':replay}
