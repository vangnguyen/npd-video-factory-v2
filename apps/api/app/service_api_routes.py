"""Master /v1 service facade over the existing canonical production services.

No service principal is converted into a human. Approved decisions/publication
submission additionally require the existing scoped human verifier and role.
"""
import re
from fastapi import APIRouter,Request,Response,HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import Field
from .service_api_auth import ServiceRoute,verify,workspace,project,human,error
from .service_api_contract import VERSION,CAPABILITIES
from .service_api_repository import OperationConflict,digest,ServiceOperationORM
from .service_outcome_context import bind
from .service_outcome_events import ServiceOutcomeEventORM,validate as validate_outcome_event
from .platform_models import ProjectCreate,ProjectVersionCreate
from .auto_edit_models import UploadInitRequest,UploadCompleteRequest,AutoEditAnalysisRequest
from .timeline_models import TimelineCreateRequest,TimelineMutationRequest,PreviewCreateRequest
from .production_models import ProductionPackageCreateRequest,ApprovalRequest,ApprovalDecisionRequest,RenderCreateRequest,FinalRenderCreateRequest
from .content_models import ContentDocument,ContentGenerateRequest,ContentSaveRequest,ContentApplyRequest
from .content_generation import ContentProviderUnavailable
from .publishing_models import PublicationCreateRequest
from .trend_models import TrendCollectionRequest,IdeaGenerateRequest,ContentQueueRefreshRequest
from . import auto_edit_routes as ingest,production_routes as production,publishing_routes as publishing,analytics_routes as analytics,timeline_routes as editing

router=APIRouter(prefix='/v1',tags=['Video Factory service API'],route_class=ServiceRoute)

class ProjectInput(ProjectCreate):workspace_id:str=Field(pattern=r'^wsp_[A-Za-z0-9_-]{4,60}$')
class CompleteInput(UploadCompleteRequest):upload_id:str=Field(pattern=r'^upl_[A-Za-z0-9_-]{4,60}$')
class TrendInput(TrendCollectionRequest):
    workspace_id:str=Field(pattern=r'^wsp_[A-Za-z0-9_-]{4,60}$')
    context:ContentQueueRefreshRequest=Field(default_factory=ContentQueueRefreshRequest)
class IdeaInput(IdeaGenerateRequest):cluster_id:str=Field(pattern=r'^trc_[A-Za-z0-9_-]{4,60}$')
class ApproveInput(ApprovalDecisionRequest):approval_id:str=Field(pattern=r'^apr_[A-Za-z0-9_-]{4,60}$')

def media_response(value):
    data=jsonable_encoder(value)
    if isinstance(data,dict) and data.get('playback_url') and data.get('project_id'):
        if data.get('preview_id'):data['playback_url']=f"/v1/projects/{data['project_id']}/previews/{data['preview_id']}/content"
        elif data.get('render_id'):data['playback_url']=f"/v1/projects/{data['project_id']}/renders/{data['render_id']}/content"
    return data

async def command(request,action,ws,pid,payload,call,*,actor=None,status=200):
    principal=await workspace(request,ws,action);actor=actor or principal.subject
    key=request.headers.get('Idempotency-Key','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,200}',key):raise error(400,'SERVICE_IDEMPOTENCY_KEY_REQUIRED')
    repository=request.app.state.service_api_repository
    try:row,replay=await repository.reserve(workspace=ws,service=principal.service_id,action=action,project=pid,
        actor=actor,key=key,payload={'method':request.method,'path':request.url.path,'query':request.url.query,
            'command':jsonable_encoder(payload)})
    except OperationConflict as exc:raise error(409,str(exc)) from None
    headers={'X-NPD-Service-Operation':row.operation_id,'X-Idempotent-Replay':'true' if replay else 'false'}
    if replay:
        if row.status in ('running','uncertain'):raise HTTPException(409,headers={**headers,'Retry-After':'2'},
            detail={'error':{'code':'SERVICE_OPERATION_UNCERTAIN','message':'Inspect the persisted operation before any new dispatch.'}})
        if row.response_sha256!=digest(row.response_json):raise error(409,'SERVICE_OPERATION_EVIDENCE_INVALID')
        return JSONResponse(row.response_json,status_code=row.response_status,headers=headers)
    kinds={'/v1/projects':'project.create'}
    kind=kinds.get(request.url.path)
    if request.method=='PUT' and request.url.path.endswith('/timeline'):kind='timeline.mutate'
    if request.url.path.endswith(('/review-render','/render')):kind='render.queue'
    if request.url.path.endswith('/publish'):kind='publication.finalize'
    if request.url.path=='/v1/uploads/init':kind='upload.initialize'
    if request.url.path.endswith('/preview'):kind='preview.queue'
    if request.url.path.endswith('/approve'):kind='approval.decide'
    async def writer(session,value):
        await repository.canonical_outcome(session,row.operation_id,status,media_response(value),kind)
    try:
        with bind(kind,writer):value=await call()
        content=media_response(value);result_status=status
    except HTTPException as exc:
        content={'detail':jsonable_encoder(exc.detail)};result_status=exc.status_code
    except KeyError:
        content={'detail':{'error':{'code':'NOT_FOUND','message':'NOT_FOUND'}}};result_status=404
    except ContentProviderUnavailable as exc:
        content={'detail':{'error':{'code':exc.code,'message':'The content provider is not configured.'}}};result_status=503
    except ValueError as exc:
        content={'detail':{'error':{'code':getattr(exc,'code','SERVICE_COMMAND_CONFLICT'),'message':'The canonical service rejected this request.'}}};result_status=409
    except Exception:
        await repository.uncertain(row.operation_id);raise error(409,'SERVICE_OPERATION_UNCERTAIN') from None
    try:await repository.complete(row.operation_id,result_status,content)
    except Exception:
        await repository.uncertain(row.operation_id);raise error(409,'SERVICE_OPERATION_UNCERTAIN') from None
    return JSONResponse(content,status_code=result_status,headers=headers)

async def scoped_command(request,pid,action,payload,call,*,actor=None,status=200):
    _,value=await project(request,pid,action)
    return await command(request,action,value.workspace_id,pid,payload,call,actor=actor,status=status)

@router.get('/contract')
async def contract(request:Request):
    actor=await verify(request)
    return {'contract_version':VERSION,'wire_auth_version':'agent-hub-bridge.v1','api_version':'v1',
        'service_id':actor.service_id,'workspace_grants':dict(actor.workspace_grants),'capabilities':sorted(CAPABILITIES),
        'operations':[{'method':method,'path':route.path} for route in router.routes for method in sorted(route.methods)],
        'human_approval_required':True,'publication_requires_human_owner':True,'shared_database':False,'shared_redis':False,
        'outcome_event_contract_versions':['agent-hub-service-outcomes.v1','agent-hub-service-outcomes.v2'],'outcome_event_delivery_enabled':False,
        'agent_hub_runtime_dependency':False,'production_deployed':False,'canonical_services_reused':True}

@router.post('/projects',status_code=201)
async def create_project(payload:ProjectInput,request:Request):
    actor=await workspace(request,payload.workspace_id,'project.create')
    core=ProjectCreate.model_validate({k:v for k,v in payload.model_dump().items() if k!='workspace_id'})
    core=core.model_copy(update={'provenance':{**core.provenance,'service_api_version':VERSION,'service_id':actor.service_id}})
    return await command(request,'project.create',payload.workspace_id,None,payload,
        lambda:request.app.state.platform_repository.create_project(payload.workspace_id,core),status=201)

@router.get('/projects/{project_id}')
async def get_project(project_id:str,request:Request):
    _,value=await project(request,project_id,'project.read');return value

@router.post('/projects/{project_id}/versions',status_code=201)
async def version(project_id:str,payload:ProjectVersionCreate,request:Request):
    actor,_=await project(request,project_id,'project.write')
    if 'content' in payload.snapshot:
        try:document=ContentDocument.model_validate(payload.snapshot['content'])
        except ValueError:raise error(422,'CONTENT_DOCUMENT_INVALID') from None
        if document.approved:await human(request,project_id,'reviewer')
    core=payload.model_copy(update={'provenance':{**payload.provenance,'service_api_version':VERSION,'service_id':actor.service_id}})
    return await scoped_command(request,project_id,'project.write',payload,
        lambda:request.app.state.platform_repository.create_version(project_id,core),status=201)

@router.put('/projects/{project_id}/content')
async def content(project_id:str,payload:ContentSaveRequest,request:Request):
    actor,_=await project(request,project_id,'project.write')
    if payload.document.approved:actor=await human(request,project_id,'reviewer')
    core=payload.model_copy(update={'actor_ref':actor.subject})
    return await scoped_command(request,project_id,'project.write',payload,
        lambda:request.app.state.content_service.save(project_id,core,actor_ref=actor.subject),actor=actor.subject)

@router.post('/projects/{project_id}/generate',status_code=202)
async def generate(project_id:str,payload:ContentGenerateRequest,request:Request):
    actor,_=await project(request,project_id,'content.generate')
    return await scoped_command(request,project_id,'content.generate',payload,
        lambda:request.app.state.content_generation_service.create(project_id,payload,actor_ref=actor.subject),status=202)

@router.get('/projects/{project_id}/generations/{generation_id}')
async def generation(project_id:str,generation_id:str,request:Request):
    await project(request,project_id,'project.read')
    value=await request.app.state.content_generation_service.get(project_id,generation_id)
    if value is None:raise error(404,'NOT_FOUND')
    return value

@router.post('/projects/{project_id}/generations/{generation_id}/apply')
async def apply_generation(project_id:str,generation_id:str,payload:ContentApplyRequest,request:Request):
    actor,_=await project(request,project_id,'project.write')
    return await scoped_command(request,project_id,'project.write',{'generation_id':generation_id,**payload.model_dump()},
        lambda:request.app.state.content_generation_service.apply(project_id,generation_id,
            expected_version=payload.expected_content_version_id,actor_ref=actor.subject))

@router.post('/uploads/init',status_code=201)
async def init_upload(payload:UploadInitRequest,request:Request):
    return await scoped_command(request,payload.project_id,'upload.write',payload,
        lambda:ingest.upload_service_from(request).initialize(payload),status=201)

async def upload_scope(request,identity,action):
    value=await ingest.upload_service_from(request).get(identity)
    if value is None:raise error(404,'NOT_FOUND')
    await project(request,value.project_id,action);return value

@router.get('/uploads/{upload_id}')
async def get_upload(upload_id:str,request:Request):return await upload_scope(request,upload_id,'upload.read')

@router.put('/uploads/{upload_id}/parts/{part_number}')
async def upload_part(upload_id:str,part_number:int,request:Request):
    value=await upload_scope(request,upload_id,'upload.write')
    from hashlib import sha256
    return await scoped_command(request,value.project_id,'upload.write',{'upload_id':upload_id,'part_number':part_number,
        'sha256':sha256(await request.body()).hexdigest(),'expected_part_sha256':request.headers.get('X-Part-SHA256')},
        lambda:ingest.upload_part(upload_id,part_number,request,x_part_sha256=request.headers.get('X-Part-SHA256')))

@router.post('/uploads/complete')
async def complete_upload(payload:CompleteInput,request:Request):
    value=await upload_scope(request,payload.upload_id,'upload.write')
    core=UploadCompleteRequest(checksum_sha256=payload.checksum_sha256)
    return await scoped_command(request,value.project_id,'upload.write',payload,
        lambda:ingest.complete_upload(payload.upload_id,core,request))

@router.post('/projects/{project_id}/analyze',status_code=201)
async def analyze(project_id:str,payload:AutoEditAnalysisRequest,request:Request):
    return await scoped_command(request,project_id,'analysis.create',payload,
        lambda:ingest.analyze_project(project_id,payload,request),status=201)

@router.get('/projects/{project_id}/analyses/{analysis_id}')
async def analysis(project_id:str,analysis_id:str,request:Request):
    await project(request,project_id,'analysis.read');return await ingest.get_project_analysis(project_id,analysis_id,request)

@router.post('/projects/{project_id}/timeline',status_code=201)
async def create_timeline(project_id:str,payload:TimelineCreateRequest,request:Request):
    actor,_=await project(request,project_id,'timeline.write');core=payload.model_copy(update={'actor_ref':actor.subject})
    return await scoped_command(request,project_id,'timeline.write',payload,
        lambda:request.app.state.timeline_service.create(project_id,core),status=201)

@router.get('/projects/{project_id}/timeline')
async def get_timeline(project_id:str,request:Request):
    await project(request,project_id,'timeline.read');value=await request.app.state.timeline_service.get(project_id)
    if value is None:raise error(404,'NOT_FOUND')
    return value

@router.put('/projects/{project_id}/timeline')
async def update_timeline(project_id:str,payload:TimelineMutationRequest,request:Request):
    actor,_=await project(request,project_id,'timeline.write');core=payload.model_copy(update={'actor_ref':actor.subject})
    return await scoped_command(request,project_id,'timeline.write',payload,
        lambda:request.app.state.timeline_service.mutate(project_id,core))

@router.post('/projects/{project_id}/preview',status_code=202)
async def preview(project_id:str,payload:PreviewCreateRequest,request:Request):
    actor,_=await project(request,project_id,'preview.create');core=payload.model_copy(update={'actor_ref':actor.subject})
    return await scoped_command(request,project_id,'preview.create',payload,
        lambda:request.app.state.preview_service.enqueue(project_id,core),status=202)

@router.get('/projects/{project_id}/previews/{preview_id}')
async def preview_state(project_id:str,preview_id:str,request:Request):
    await project(request,project_id,'project.read');value=await request.app.state.preview_service.get(project_id,preview_id)
    if value is None:raise error(404,'NOT_FOUND')
    return media_response(value)

@router.get('/projects/{project_id}/previews/{preview_id}/content')
async def preview_content(project_id:str,preview_id:str,request:Request):
    await project(request,project_id,'project.read');return await editing.preview_content(project_id,preview_id,request)

@router.post('/projects/{project_id}/production-package',status_code=201)
async def package(project_id:str,payload:ProductionPackageCreateRequest,request:Request):
    actor,_=await project(request,project_id,'project.write');core=payload.model_copy(update={'actor_ref':actor.subject})
    return await scoped_command(request,project_id,'project.write',payload,
        lambda:production.create_or_refresh_package(project_id,core,request),status=201)

@router.post('/projects/{project_id}/review-render',status_code=202)
async def review_render(project_id:str,payload:RenderCreateRequest,request:Request):
    actor,_=await project(request,project_id,'render.create');core=payload.model_copy(update={'actor_ref':actor.subject})
    return await scoped_command(request,project_id,'render.create',payload,
        lambda:production.enqueue_review_render(project_id,core,request),status=202)

@router.post('/projects/{project_id}/approval-requests',status_code=201)
async def request_approval(project_id:str,payload:ApprovalRequest,request:Request):
    actor,_=await project(request,project_id,'approval.submit');core=payload.model_copy(update={'requester_ref':actor.subject})
    return await scoped_command(request,project_id,'approval.submit',payload,
        lambda:production.request_approval(project_id,core,request),status=201)

@router.post('/projects/{project_id}/approve')
async def approve(project_id:str,payload:ApproveInput,request:Request):
    await project(request,project_id,'approval.submit');actor=await human(request,project_id,'reviewer')
    core=ApprovalDecisionRequest(decision=payload.decision,reviewer_ref=actor.subject,comment=payload.comment)
    return await scoped_command(request,project_id,'approval.submit',payload,
        lambda:production.decide_approval(project_id,payload.approval_id,core,request),actor=actor.subject)

@router.post('/projects/{project_id}/render',status_code=202)
async def render(project_id:str,payload:FinalRenderCreateRequest,request:Request):
    actor,_=await project(request,project_id,'render.create');core=payload.model_copy(update={'actor_ref':actor.subject})
    return await scoped_command(request,project_id,'render.create',payload,
        lambda:production.enqueue_final_render_command(project_id,core,request),status=202)

@router.get('/projects/{project_id}/renders/{render_id}')
async def render_state(project_id:str,render_id:str,request:Request):
    await project(request,project_id,'render.read');return media_response(await production.get_render(project_id,render_id,request))

@router.get('/projects/{project_id}/renders/{render_id}/content')
async def render_content(project_id:str,render_id:str,request:Request):
    await project(request,project_id,'render.read');return await production.render_content(project_id,render_id,request)

@router.post('/projects/{project_id}/publish',status_code=201)
async def publish(project_id:str,payload:PublicationCreateRequest,request:Request):
    await project(request,project_id,'publication.create');actor=await human(request,project_id,'owner')
    core=payload.model_copy(update={'actor_ref':actor.subject})
    return await scoped_command(request,project_id,'publication.create',payload,
        lambda:publishing.create_publication(project_id,core,request,Response(),request.headers.get('Idempotency-Key','')),
        actor=actor.subject,status=201)

@router.get('/projects/{project_id}/publications')
async def publications(project_id:str,request:Request):
    await project(request,project_id,'publication.read');return await publishing.list_publications(project_id,request)

@router.get('/projects/{project_id}/analytics')
async def report(project_id:str,request:Request):
    await project(request,project_id,'analytics.read');return await analytics.analytics_report(project_id,request)

@router.post('/trends/refresh',status_code=201)
async def refresh_trends(payload:TrendInput,request:Request):
    await workspace(request,payload.workspace_id,'trend.refresh')
    core=TrendCollectionRequest.model_validate({k:v for k,v in payload.model_dump().items() if k not in ('workspace_id','context')})
    async def refresh():
        service=request.app.state.trend_intelligence_service
        collection=await service.collect(payload.workspace_id,core)
        queue=await service.refresh_queue(payload.workspace_id,payload.context)
        return {'collection':collection,'clusters':await service.list_clusters(payload.workspace_id),'opportunities':queue}
    return await command(request,'trend.refresh',payload.workspace_id,None,payload,
        refresh,status=201)

@router.get('/trends')
async def trends(request:Request,workspace_id:str):
    await workspace(request,workspace_id,'trend.read');return await request.app.state.trend_intelligence_service.list_clusters(workspace_id)

@router.get('/opportunities')
async def opportunities(request:Request,workspace_id:str):
    await workspace(request,workspace_id,'trend.read');return await request.app.state.trend_intelligence_service.list_queue(workspace_id)

@router.post('/ideas/generate')
async def ideas(payload:IdeaInput,request:Request):
    cluster=await request.app.state.trend_intelligence_service.get_cluster(payload.cluster_id)
    if cluster is None:raise error(404,'NOT_FOUND')
    await workspace(request,cluster.workspace_id,'ideas.generate')
    core=IdeaGenerateRequest.model_validate({k:v for k,v in payload.model_dump().items() if k!='cluster_id'})
    return await command(request,'ideas.generate',cluster.workspace_id,None,payload,
        lambda:request.app.state.trend_intelligence_service.generate_ideas(payload.cluster_id,core))

@router.get('/operations/{operation_id}')
async def operation(operation_id:str,request:Request):
    row=await request.app.state.service_api_repository.get(operation_id);actor=await verify(request)
    if row is None or row.service_id!=actor.service_id:raise error(404,'NOT_FOUND')
    await workspace(request,row.workspace_id,row.action)
    if row.response_sha256 and digest(row.response_json)!=row.response_sha256:raise error(409,'SERVICE_OPERATION_EVIDENCE_INVALID')
    return {'operation_id':row.operation_id,'workspace_id':row.workspace_id,'service_id':row.service_id,'action':row.action,
        'project_id':row.project_id,'actor_ref':row.actor_ref,'status':row.status,'response_status':row.response_status,
        'response':row.response_json,'response_sha256':row.response_sha256,'automatic_redispatch':False,
        'created_at':row.created_at,'updated_at':row.updated_at}

@router.get('/operation-events')
async def operation_events(request:Request,workspace_id:str,after:int=0,limit:int=25):
    from sqlalchemy import select
    actor=await verify(request)
    if after<0 or not 1<=limit<=100:raise error(422,'SERVICE_EVENT_PAGE_INVALID')
    if workspace_id not in actor.workspace_grants:raise error(404,'NOT_FOUND')
    async with request.app.state.service_api_repository.factory() as session:
        events=(await session.scalars(select(ServiceOutcomeEventORM).where(ServiceOutcomeEventORM.workspace_id==workspace_id,
            ServiceOutcomeEventORM.service_id==actor.service_id,ServiceOutcomeEventORM.sequence>after)
            .order_by(ServiceOutcomeEventORM.sequence).limit(limit+1))).all()
        result=[]
        for item in events[:limit]:
            operation=await session.get(ServiceOperationORM,item.operation_id)
            if operation.action not in actor.workspace_grants[workspace_id]:raise error(403,'SERVICE_CAPABILITY_REQUIRED')
            if not validate_outcome_event(item,operation):
                raise error(409,'SERVICE_EVENT_EVIDENCE_INVALID')
            result.append({'sequence':item.sequence,'envelope':item.envelope_json,'envelope_sha256':item.envelope_sha256,'delivery_enabled':False})
    return {'contract_version':'agent-hub-service-outcomes.v1','items':result,'next_after':events[limit-1].sequence if len(events)>limit else None,
        'event_contract_versions':['agent-hub-service-outcomes.v1','agent-hub-service-outcomes.v2'],
        'delivery_enabled':False,'real_Agent_Hub':False}
