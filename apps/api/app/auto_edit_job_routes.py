"""Scoped asynchronous video API. Reading saved work never selects a provider."""
from fastapi import APIRouter,HTTPException,Request
from .human_auth import authorize_project
from .auto_edit_job_models import AutoEditJobCreate,AutoEditJobRead
from .auto_edit_job_repository import AnalysisJobConflict
from .auto_edit_providers import ProviderNotConfigured
from .uploaded_audio_routes import AudioRoute

router=APIRouter(prefix='/api/v1/projects/{project_id}/analysis-jobs',route_class=AudioRoute)


async def execute(request,project_id,action,*,write=False):
    principal=await authorize_project(request,project_id,'editor' if write else 'viewer')
    try:return await action(request.app.state.auto_edit_job_service,principal.subject)
    except KeyError:raise HTTPException(404,detail={'error':{'code':'VIDEO_JOB_NOT_FOUND','message':'Video analysis job not found'}}) from None
    except ProviderNotConfigured:raise HTTPException(503,detail={'error':{'code':'VIDEO_PROVIDER_NOT_CONFIGURED','message':'Video recognition is not configured'}}) from None
    except AnalysisJobConflict as exc:raise HTTPException(409,detail={'error':{'code':exc.code,'message':exc.code}}) from None
    except ValueError:raise HTTPException(409,detail={'error':{'code':'VIDEO_SOURCE_OR_CONFIGURATION_CHANGED','message':'Source/configuration requires review'}}) from None


@router.post('',response_model=AutoEditJobRead,status_code=202)
async def create(project_id:str,payload:AutoEditJobCreate,request:Request):
    return await execute(request,project_id,lambda service,actor:service.create(project_id,payload,actor),write=True)


@router.get('',response_model=list[AutoEditJobRead])
async def saved(project_id:str,request:Request):
    return await execute(request,project_id,lambda service,_:service.repository.list(project_id))


@router.get('/{job_id}',response_model=AutoEditJobRead)
async def detail(project_id:str,job_id:str,request:Request):
    return await execute(request,project_id,lambda service,_:service.repository.get(project_id,job_id))


@router.post('/{job_id}/cancel',response_model=AutoEditJobRead)
async def cancel(project_id:str,job_id:str,request:Request):
    return await execute(request,project_id,lambda service,actor:service.cancel(project_id,job_id,actor),write=True)
