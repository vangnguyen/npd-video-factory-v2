"""Existing signed edit/read boundary, never an ASR/provider dispatch."""
import re
from pydantic import Field,StrictInt,ValidationError
from app.models import StrictModel
from app.auto_edit_models import TranscriptEditRequest
from .contracts import WorkflowError
from . import audio_transcripts

PATTERN=r'/api/projects/([a-f0-9]{32})/audio-transcripts(?:/([a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}))?'
class Edit(StrictModel):
    revision:StrictInt=Field(ge=1)
    asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    analysis_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    edit:TranscriptEditRequest
def handles(path):return re.fullmatch(PATTERN,path) is not None
def dispatch(handler,*,write):
    if '?' in handler.path:raise WorkflowError('AUDIO_TRANSCRIPT_QUERY_INVALID',400)
    project,asset=re.fullmatch(PATTERN,handler.path).groups();workspace=handler.server.publications.workspace_id
    if write:
        if asset is None:raise WorkflowError('AUDIO_TRANSCRIPT_ROUTE_NOT_FOUND',404)
        try:body=Edit.model_validate(handler.read_body(max_bytes=128000))
        except (ValidationError,ValueError,TypeError):raise WorkflowError('AUDIO_TRANSCRIPT_EDIT_INVALID',400) from None
        actor=handler.auth_session.principal.token_id if handler.server.access is not None else 'legacy-local-editor'
        changed=audio_transcripts.edit(handler.server.store,project,body.revision,asset,body.edit.model_dump(mode='json'),
            asset_sha256=body.asset_sha256,analysis_sha256=body.analysis_sha256,actor_ref=actor)
    elif asset is not None:raise WorkflowError('AUDIO_TRANSCRIPT_ROUTE_NOT_FOUND',404)
    result=audio_transcripts.view(handler.server.store,project,workspace)
    if write:result={**result,'changed':changed}
    # Handler.common already supplies the single no-store response header.
    return handler.reply(result)
