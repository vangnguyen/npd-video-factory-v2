"""Human/CSRF-scoped Native generation routes; no browser provider configuration."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .publication_routes import actor
from .generation_models import GenerationCreate,GenerationAction,GenerationRecovery,GenerationImport,NativeImageParameters,NativeVideoParameters


def providers(worker):
    queue=worker.queue;dummy={'asset_id':'0'*32+'.jpg','asset_sha256':'0'*64};items=[]
    for modality,operations in [('image',['generate','image_to_image','variation','inpaint','upscale']),('video',['text_to_video','image_to_video','reference_assisted'])]:
        for operation in operations:
            value={'prompt':'static capability inspection','aspect_ratio':'16:9'}
            if modality=='image':
                value['operation']=operation
                if operation!='generate':value['references']=[dummy]
                if operation=='inpaint':value['mask']=dummy
                parameters=NativeImageParameters.model_validate(value)
            else:
                value['mode']=operation
                if operation!='text_to_video':value['references']=[dummy]
                parameters=NativeVideoParameters.model_validate(value)
            selected=queue.selection(parameters);items.append({'modality':modality,'operation':operation,**selected})
    return {'schema_version':'native-generation-providers-v1','workspace_id':queue.workspace,'items':items,'ui_enablement_supported':False,
        'owner_enabled':queue.factory is not None and queue.factory.enabled,'automatic_attachment':False,'publish_enabled':False,'real_provider_tested':False}


def get(handler,path):
    worker=handler.server.generation
    if path=='/api/generation/providers':
        if '?' in handler.path:raise WorkflowError('NATIVE_GENERATION_PAGE_INVALID',400)
        return providers(worker)
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/generation(?:/([a-f0-9]{32}))?',path)
    if not match:raise WorkflowError('NATIVE_GENERATION_ROUTE_NOT_FOUND',404)
    project,identity=match.groups();params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if identity:
        if params or '?' in handler.path:raise WorkflowError('NATIVE_GENERATION_PAGE_INVALID',400)
        return worker.get(project,identity)
    if set(params)-{'limit'} or any(len(values)!=1 for values in params.values()):raise WorkflowError('NATIVE_GENERATION_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_GENERATION_PAGE_INVALID',400) from None
    return worker.page(project,limit=limit)


def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/generation(?:/([a-f0-9]{32})/(cancel|recover|import))?',path)
    if not match:raise WorkflowError('NATIVE_GENERATION_ROUTE_NOT_FOUND',404)
    project,identity,action=match.groups();worker=handler.server.generation;queue=worker.queue
    try:
        if identity is None:
            value,replay=queue.create(project,GenerationCreate.model_validate(body),actor=actor(handler));worker.wake.set()
            return {**worker.get(project,value['generation_id']),'idempotent_replay':replay}
        if action=='import':return worker.attach(project,identity,GenerationImport.model_validate(body),actor=actor(handler))
        if action=='recover':result=queue.recover(project,identity,GenerationRecovery.model_validate(body),actor=actor(handler))
        else:queue.cancel(project,identity,GenerationAction.model_validate(body),actor=actor(handler));result=worker.get(project,identity)
        worker.wake.set();return result
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_GENERATION_FIELDS_INVALID',400) from None
