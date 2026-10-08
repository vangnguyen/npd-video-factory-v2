"""Existing Native human session/origin/CSRF/RBAC boundary for Trend Radar."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .publication_routes import actor
from .trend_radar_models import CollectRequest,RefreshRequest,HandoffRequest,LearningRequest

def get(handler,path):
    radar=handler.server.trends;params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if any(len(v)!=1 for v in params.values()):raise WorkflowError('TREND_PAGE_INVALID',400)
    if path=='/api/trends/radar':
        if set(params)-{'view','channel','platform','target_platform','country','language','niche','format','objective','days','offset','limit'}:raise WorkflowError('TREND_PAGE_INVALID',400)
        values={k:v[0] for k,v in params.items()}
        try:
            for key in ('days','offset','limit'):
                if key in values:values[key]=int(values[key])
        except ValueError:raise WorkflowError('TREND_PAGE_INVALID',400) from None
        return radar.page(**values)
    if params:raise WorkflowError('TREND_PAGE_INVALID',400)
    match=re.fullmatch(r'/api/trends/learning/qualified/([a-f0-9]{32})/templates',path)
    if match:return handler.server.qualified_learning.suggestions(match[1])
    if path=='/api/trends/providers':return radar.states()
    if path in ('/api/trends/collections','/api/trends/learning'):
        record_type='collection' if path.endswith('collections') else 'learning'
        with radar.store.transaction() as con:values=radar.records(record_type,con,101)
        if record_type=='collection':values=[{**v,'payload':{k:x for k,x in v['payload'].items() if k!='receipt'}} for v in values]
        return {'workspace_id':radar.workspace,'items':values[:100],'truncated':len(values)>100}
    match=re.fullmatch(r'/api/trends/records/([a-f0-9]{32})',path)
    if match:return radar.detail(match[1])
    raise WorkflowError('ROUTE_NOT_FOUND',404)

def post(handler,path,body):
    radar=handler.server.trends
    try:
        if path=='/api/trends/collections':return radar.collect(CollectRequest.model_validate(body),actor=actor(handler))
        if path=='/api/trends/refresh':return radar.refresh(RefreshRequest.model_validate(body),actor=actor(handler))
        if path=='/api/trends/handoff':return radar.handoff(HandoffRequest.model_validate(body),actor=actor(handler))
        if path=='/api/trends/learning':
            from .trend_radar_learning import create
            return create(radar,LearningRequest.model_validate(body),actor=actor(handler))
        if path=='/api/trends/learning/qualified':
            from .qualified_learning_feedback import Create
            from .contracts import digest
            session=getattr(handler,'auth_session',None)
            if session is None:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_CURRENT_OWNER_REQUIRED',403)
            service=handler.server.qualified_learning;service.learning.winners.analytics.identity(session.principal)
            value,replay=service.create(Create.model_validate(body),principal=session.principal)
            return {'schema_version':'native-qualified-learning-feedback-result-v1','workspace_id':radar.workspace,
                'record':value,'record_sha256':digest(value),'idempotent_replay':replay,'recommendation_only':True,
                'automatic_application':False,'provider_calls':0,'publishing_enabled':False,'token_returned':False}
        match=re.fullmatch(r'/api/trends/collections/([a-f0-9]{32})/cancel',path)
        if match:
            if set(body)!={'version'} or type(body['version']) is not int:raise WorkflowError('TREND_FIELDS_INVALID',400)
            return radar.cancel(match[1],body['version'],actor=actor(handler))
    except (ValidationError,TypeError):raise WorkflowError('TREND_FIELDS_INVALID',400) from None
    raise WorkflowError('ROUTE_NOT_FOUND',404)
