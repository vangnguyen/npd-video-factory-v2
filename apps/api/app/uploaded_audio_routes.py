"""Human scoped audio recognition/edit/read; source playback never calls ASR."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute
from .auto_edit_providers import ProviderNotConfigured
from .human_auth import authorize_project
from .repositories import _asset_read
from .uploaded_audio_models import AudioTranscriptionCreate, AudioTranscriptionRead, AudioTextEdit, AudioWordEdit, AudioRestore, AudioCaptionApply
from .uploaded_audio_repository import AudioConflict, source

class AudioRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def no_store(request):
            try:
                response = await handler(request)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}),'Cache-Control':'no-store'}
                raise
            response.headers['Cache-Control'] = 'no-store'
            return response
        return no_store


router = APIRouter(prefix='/api/v1/projects/{project_id}/audio-transcriptions',route_class=AudioRoute)


def service(request):
    return request.app.state.uploaded_audio_service


def error(status, code):
    return HTTPException(status, detail={'error':{'code':code,'message':code}}, headers={'Cache-Control':'no-store'})


async def execute(request, project_id, action, *, write=False):
    principal = await authorize_project(request, project_id, 'editor' if write else 'viewer')
    try:
        return await action(principal)
    except KeyError:
        raise error(404,'AUDIO_NOT_FOUND') from None
    except AudioConflict as exc:
        raise error(409,exc.code) from None
    except ProviderNotConfigured:
        raise error(503,'AUDIO_PROVIDER_NOT_CONFIGURED') from None


@router.post('', response_model=AudioTranscriptionRead, status_code=202)
async def create(project_id:str, payload:AudioTranscriptionCreate, request:Request):
    return await execute(request,project_id,lambda actor:service(request).create(project_id,payload,actor.subject),write=True)


@router.get('', response_model=list[AudioTranscriptionRead])
async def saved(project_id:str, request:Request):
    return await execute(request,project_id,lambda _:service(request).repository.list(project_id))


@router.get('/{audio_id}', response_model=AudioTranscriptionRead)
async def get(project_id:str, audio_id:str, request:Request):
    return await execute(request,project_id,lambda _:service(request).repository.get(project_id,audio_id))


@router.post('/{audio_id}/transcript', response_model=AudioTranscriptionRead)
async def text(project_id:str, audio_id:str, payload:AudioTextEdit, request:Request):
    return await execute(request,project_id,lambda actor:service(request).edit_text(project_id,audio_id,payload,actor.subject),write=True)


@router.post('/{audio_id}/transcript-words', response_model=AudioTranscriptionRead)
async def words(project_id:str, audio_id:str, payload:AudioWordEdit, request:Request):
    return await execute(request,project_id,lambda actor:service(request).edit_words(project_id,audio_id,payload,actor.subject),write=True)


@router.post('/{audio_id}/restore', response_model=AudioTranscriptionRead)
async def restore(project_id:str, audio_id:str, payload:AudioRestore, request:Request):
    return await execute(request,project_id,lambda actor:service(request).restore(project_id,audio_id,payload,actor.subject),write=True)


@router.post('/{audio_id}/cancel', response_model=AudioTranscriptionRead)
async def cancel(project_id:str, audio_id:str, request:Request):
    return await execute(request,project_id,lambda actor:service(request).cancel(project_id,audio_id,actor.subject),write=True)


@router.post('/{audio_id}/apply-captions')
async def apply_captions(project_id:str, audio_id:str, payload:AudioCaptionApply, request:Request):
    return await execute(request,project_id,lambda actor:service(request).apply_captions(project_id,audio_id,payload,actor.subject),write=True)


@router.get('/{audio_id}/source')
async def playback(project_id:str, audio_id:str, request:Request):
    async def deliver(_):
        from .source_asset_delivery import deliver_source_asset
        audio = service(request)
        async with audio.session_factory() as session:
            parent = await audio.repository.parent(session,project_id,audio_id)
            _,asset,_ = await source(session,project_id,parent.asset_id,parent=parent)
            if asset.storage_provider != audio.object_storage.name:
                raise AudioConflict('AUDIO_STORAGE_CHANGED')
            media_asset = _asset_read(asset)
        return await deliver_source_asset(request,asset=media_asset,object_storage=audio.object_storage,staging_root=audio.staging_root)
    return await execute(request,project_id,deliver)
