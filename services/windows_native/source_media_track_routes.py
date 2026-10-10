"""Typed Source media decisions over the existing signed edit boundary."""
import re
from urllib.parse import parse_qs
from .contracts import WorkflowError
from . import source_media_tracks as media

PATTERN=r'/api/projects/([a-f0-9]{32})/auto-edit/media-tracks(?:/(audio|subtitles|captions))?'
def handles(path):return re.fullmatch(PATTERN,path) is not None
def dispatch(handler,*,write):
    path,_,query=handler.path.partition('?');project,action=re.fullmatch(PATTERN,path).groups()
    params=parse_qs(query,keep_blank_values=True)
    if write:
        if query or action is None:raise WorkflowError('SOURCE_MEDIA_TRACK_ROUTE_INVALID',400)
        body=handler.read_body(max_bytes=1000000)
        actor=handler.auth_session.principal.token_id if handler.server.access is not None else 'legacy-local-editor'
        fn={'audio':media.add_audio,'subtitles':media.add_subtitles,'captions':media.edit_captions}[action]
        mutation=fn(handler.server.store,project,body,actor_ref=actor,**({'config':handler.server.config} if action=='audio' else {}))
        value=media.catalog(handler.server.store,project,handler.server.publications.workspace_id)
        return handler.reply({**value,'mutation':mutation})
    if action is not None or set(params)-{'caption_page'} or any(len(v)!=1 for v in params.values()):
        raise WorkflowError('SOURCE_MEDIA_TRACK_ROUTE_INVALID',400)
    try:page=int(params.get('caption_page',['1'])[0])
    except ValueError:raise WorkflowError('SOURCE_MEDIA_TRACK_PAGE_INVALID',400) from None
    return handler.reply(media.catalog(handler.server.store,project,handler.server.publications.workspace_id,caption_page=page))
