"""Human-scoped word review/readback and original media playback."""
import re
from pydantic import Field,StrictInt
from app.models import StrictModel
from app.transcript_word_review import WordReview
from .contracts import WorkflowError
from .media import project_assets,_verify_library_record

ROOT=r'/api/projects/([a-f0-9]{32})/transcript-word-review'
PATTERN=ROOT+r'(?:/(video/ana_[a-f0-9]{24}|audio/[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}|source/[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}))?'
class Save(StrictModel):
    revision:StrictInt=Field(ge=1)
    asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    analysis_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    review:WordReview

def handles(path):return re.fullmatch(PATTERN,path) is not None

def view(store,project_id,workspace):
    from .auto_edit_analysis import view as videos
    from .audio_transcripts import view as audios
    video=videos(store,project_id);audio=audios(store,project_id,workspace);items=[]
    if video['revision']!=audio['revision']:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_PROJECT_CHANGED')
    for value in video['analyses']:
        if not value['analysis']['transcript']:continue
        items.append({'kind':'video','identity':value['analysis']['analysis_id'],'asset_id':value['native_asset_id'],
            'filename':value['filename'],'asset_sha256':value['asset_sha256'],'analysis_sha256':value['analysis_sha256'],
            'current':value['analysis']['transcript'],'versions':value['transcript_history'],
            'source_url':f'/api/projects/{project_id}/transcript-word-review/source/{value["native_asset_id"]}'})
    for value in audio['items']:
        items.append({'kind':'audio','identity':value['asset_id'],'asset_id':value['asset_id'],'filename':value['filename'],
            'asset_sha256':value['asset_sha256'],'analysis_sha256':value['analysis_sha256'],'current':value['current'],
            'versions':value['versions'],'source_url':f'/api/projects/{project_id}/transcript-word-review/source/{value["asset_id"]}'})
    project=store.get(project_id)
    if project['revision']!=video['revision']:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_PROJECT_CHANGED')
    return {'schema_version':'native-transcript-word-review.v1','workspace_id':workspace,'project_id':project_id,
        'revision':project['revision'],'timeline_version':(project['document'].get('canonical_timeline') or {}).get('version'),
        'items':items,'source_media_mutated':False,'provider_calls':0,'human_review_required':True,'publishing_enabled':False}

def dispatch(handler,*,write):
    project,suffix=re.fullmatch(PATTERN,handler.path).groups();store=handler.server.store
    workspace=handler.server.publications.workspace_id
    if suffix and suffix.startswith('source/'):
        if write:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_ROUTE_NOT_FOUND',404)
        asset_id=suffix.split('/',1)[1]
        asset=next((a for a in project_assets(store.get(project)['document']) if a['id']==asset_id),None)
        if not asset or asset['kind'] not in ('audio','video'):raise WorkflowError('TRANSCRIPT_WORD_REVIEW_SOURCE_NOT_FOUND',404)
        path=_verify_library_record(store,{'metadata':asset,'metadata_conflict':False})
        return handler.file(path,video=True,headers={'Cache-Control':'no-store'})
    if write:
        if not suffix:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_ROUTE_NOT_FOUND',404)
        try:body=Save.model_validate(handler.read_body(max_bytes=2000000))
        except (ValueError,TypeError):raise WorkflowError('TRANSCRIPT_WORD_REVIEW_INVALID',400) from None
        kind,identity=suffix.split('/',1)
        actor=handler.auth_session.principal.token_id if handler.server.access is not None else 'legacy-local-editor'
        from .transcript_word_review import save
        save(store,project,body.revision,identity,body.review.model_dump(mode='json'),actor_ref=actor,
            asset_sha256=body.asset_sha256,analysis_sha256=body.analysis_sha256,audio=kind=='audio',workspace_id=workspace)
    elif suffix:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_ROUTE_NOT_FOUND',404)
    return handler.reply(view(store,project,workspace))
