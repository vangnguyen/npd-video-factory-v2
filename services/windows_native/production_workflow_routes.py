"""Human-authorized authoring only; never synthesis, approval or publishing."""
import re,subprocess
from functools import lru_cache
from pathlib import Path
from .contracts import WorkflowError
from .production_workflows import catalog,save_script,is_drama

LOCAL=r'/api/projects/([a-f0-9]{32})/drama-script'
def handles(path):return path.partition('?')[0] in ('/api/production-workflows','/api/app-info') or re.fullmatch(LOCAL,path.partition('?')[0]) is not None

@lru_cache(maxsize=1)
def app_info():
    root=Path(__file__).resolve().parents[2]
    def git(*args):
        try:return subprocess.check_output(['git','-C',str(root),*args],text=True,timeout=3,stderr=subprocess.DEVNULL).strip()
        except (OSError,subprocess.SubprocessError):return None
    return {'application':'NPD Video Studio','application_source':str(root),'branch':git('branch','--show-current'),'commit':git('rev-parse','HEAD'),
        'build':'drama-usability-03','platform_api_publishing':'DEFERRED','analytics':'DEFERRED','full_trend_radar':'DEFERRED','production_deployed':False}

def dispatch(handler,*,write=False):
    path=handler.path
    if '?' in path:raise WorkflowError('DRAMA_QUERY_INVALID',400)
    if not write:
        if path=='/api/production-workflows':return handler.reply(catalog())
        if path=='/api/app-info':return handler.reply(app_info(),headers={'Cache-Control':'no-store'})
        project=handler.server.store.get(re.fullmatch(LOCAL,path)[1])
        if not is_drama(project['document']):raise WorkflowError('DRAMA_WORKFLOW_REQUIRED',400)
        return handler.reply({'project_id':project['id'],'revision':project['revision'],'script':project['document'].get('drama_script'),'provider_calls':0})
    match=re.fullmatch(LOCAL,path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    def authorized():
        if handler.server.access is not None:handler.server.access.authorize(handler.auth_session,'POST',path)
    actor=handler.auth_session.principal.token_id if getattr(handler,'auth_session',None) else 'loopback-owner'
    return handler.reply(save_script(handler.server.store,match[1],handler.read_body(max_bytes=180000),actor_ref=actor,authorization_check=authorized))
