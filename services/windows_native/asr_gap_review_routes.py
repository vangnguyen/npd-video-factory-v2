"""Signed read/edit routes; save never queues or calls a speech provider."""
import re
from .contracts import WorkflowError
from . import asr_gap_reviews as reviews
from .media import project_assets,media_path

PATTERN=r'/api/projects/([a-f0-9]{32})/asr-gap-reviews(?:/([a-f0-9]{32})/([a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3})(/source)?)?'
def handles(path):return re.fullmatch(PATTERN,path) is not None

def dispatch(handler,*,write):
    if '?' in handler.path:raise WorkflowError('ASR_GAP_REVIEW_QUERY_INVALID',400)
    project,job,asset,source=re.fullmatch(PATTERN,handler.path).groups();store=handler.server.store;config=handler.server.config
    if source:
        if write:raise WorkflowError('ASR_GAP_REVIEW_ROUTE_INVALID',404)
        job=store.get_job(job)
        if job['project_id']!=project:raise WorkflowError('ASR_GAP_REVIEW_NOT_FOUND',404)
        store.get(project);item=next((a for a in project_assets(job['snapshot']['document']) if a['id']==asset),None)
        if not item or not reviews.candidate_for(store,config,job,item):raise WorkflowError('ASR_GAP_CANDIDATE_NOT_FOUND',404)
        return handler.file(media_path(config,asset),video=True)
    if write:
        if not job or not asset:raise WorkflowError('ASR_GAP_REVIEW_ROUTE_INVALID',404)
        actor=handler.auth_session.principal.token_id if handler.server.access is not None else 'legacy-local-editor'
        changed=reviews.save(store,config,project,job,asset,handler.read_body(max_bytes=2000000),actor_ref=actor)
    elif job or asset:raise WorkflowError('ASR_GAP_REVIEW_ROUTE_INVALID',404)
    value=reviews.view(store,config,project,handler.server.publications.workspace_id)
    return handler.reply({**value,'changed':changed} if write else value)
